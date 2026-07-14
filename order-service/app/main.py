import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, Numeric, String, create_engine, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .logging_config import configure_logging

SERVICE_NAME = os.getenv("SERVICE_NAME", "order-service")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://shop:shop@localhost:5433/orders")
INVENTORY_URL = os.getenv("INVENTORY_URL", "http://localhost:8001")
PAYMENT_URL = os.getenv("PAYMENT_URL", "http://localhost:8002")
logger = configure_logging(SERVICE_NAME)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class OrderStatus(str, Enum):
    pending = "pending"
    confirmed = "confirmed"
    failed = "failed"


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    item_id: Mapped[int]
    sku: Mapped[str] = mapped_column(String(64))
    quantity: Mapped[int]
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(String(20), index=True)
    payment_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))


class OrderCreate(BaseModel):
    item_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=100)


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    item_id: int
    sku: str
    quantity: int
    unit_price: Decimal
    total: Decimal
    status: str
    payment_id: str | None
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    app.state.http_client = httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=2.0))
    yield
    await app.state.http_client.aclose()


app = FastAPI(title="Order Service", version="1.1.0", lifespan=lifespan)


@app.get("/health/live")
def live():
    return {"status": "alive", "service": SERVICE_NAME}


@app.get("/health/ready")
async def ready(request: Request, db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        client: httpx.AsyncClient = request.app.state.http_client
        inventory, payment = await __import__('asyncio').gather(
            client.get(f"{INVENTORY_URL}/health/ready"),
            client.get(f"{PAYMENT_URL}/health/ready"),
        )
        if inventory.status_code != 200 or payment.status_code != 200:
            raise RuntimeError("Dependency unavailable")
        return {"status": "ready", "database": "available", "dependencies": "available"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Order service is not ready") from exc


@app.get("/orders", response_model=list[OrderRead])
def list_orders(db: Session = Depends(get_db)):
    return list(db.scalars(select(Order).order_by(Order.created_at.desc())))


@app.get("/orders/{order_id}", response_model=OrderRead)
def get_order(order_id: str, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@app.post("/orders", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
async def create_order(payload: OrderCreate, request: Request, db: Session = Depends(get_db)):
    client: httpx.AsyncClient = request.app.state.http_client
    try:
        item_response = await client.get(f"{INVENTORY_URL}/items/{payload.item_id}")
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail="Inventory service unavailable") from exc
    if item_response.status_code == 404:
        raise HTTPException(status_code=404, detail="Item not found")
    if item_response.status_code != 200:
        raise HTTPException(status_code=502, detail="Inventory lookup failed")

    item = item_response.json()
    unit_price = Decimal(str(item["price"]))
    total = unit_price * payload.quantity
    order = Order(
        id=str(uuid4()), item_id=payload.item_id, sku=item["sku"], quantity=payload.quantity,
        unit_price=unit_price, total=total, status=OrderStatus.pending.value,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    logger.info("Order created", extra={"order_id": order.id, "item_id": order.item_id, "quantity": order.quantity, "status": order.status})

    reserved = False
    try:
        reserve_response = await client.post(
            f"{INVENTORY_URL}/items/{payload.item_id}/reserve", json={"quantity": payload.quantity}
        )
        if reserve_response.status_code == 409:
            raise HTTPException(status_code=409, detail="Insufficient inventory")
        reserve_response.raise_for_status()
        reserved = True

        payment_response = await client.post(
            f"{PAYMENT_URL}/payments", json={"order_id": order.id, "amount": str(total)}
        )
        payment_response.raise_for_status()
        payment = payment_response.json()
        order.status = OrderStatus.confirmed.value
        order.payment_id = payment["payment_id"]
        db.commit()
        db.refresh(order)
        logger.info("Order confirmed", extra={"order_id": order.id, "item_id": order.item_id, "quantity": order.quantity, "payment_id": order.payment_id, "status": order.status})
        return order
    except HTTPException as exc:
        order.status = OrderStatus.failed.value
        order.failure_reason = str(exc.detail)
        db.commit()
        if reserved:
            try:
                await client.post(f"{INVENTORY_URL}/items/{payload.item_id}/release", json={"quantity": payload.quantity})
            except httpx.RequestError:
                logger.exception("Inventory compensation failed", extra={"order_id": order.id, "item_id": order.item_id, "quantity": order.quantity, "error_type": "CompensationFailure"})
        logger.error("Order failed", extra={"order_id": order.id, "item_id": order.item_id, "quantity": order.quantity, "status": order.status, "error_type": "OrderFailure"})
        raise
    except (httpx.HTTPError, httpx.RequestError) as exc:
        order.status = OrderStatus.failed.value
        order.failure_reason = f"Downstream service failure: {type(exc).__name__}"
        db.commit()
        if reserved:
            try:
                release_response = await client.post(f"{INVENTORY_URL}/items/{payload.item_id}/release", json={"quantity": payload.quantity})
                release_response.raise_for_status()
            except httpx.HTTPError:
                logger.exception("Inventory compensation failed", extra={"order_id": order.id, "item_id": order.item_id, "quantity": order.quantity, "error_type": "CompensationFailure"})
        logger.exception("Order failed because of downstream service", extra={"order_id": order.id, "item_id": order.item_id, "quantity": order.quantity, "status": order.status, "error_type": type(exc).__name__})
        raise HTTPException(status_code=502, detail="Order processing failed") from exc
