import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, Numeric, String, create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .logging_config import configure_logging

SERVICE_NAME = os.getenv("SERVICE_NAME", "inventory-service")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://shop:shop@localhost:5432/inventory")
logger = configure_logging(SERVICE_NAME)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    quantity: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))


class ItemCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    price: Decimal = Field(gt=0, decimal_places=2)
    quantity: int = Field(ge=0)


class ItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sku: str
    name: str
    price: Decimal
    quantity: int
    created_at: datetime
    updated_at: datetime


class StockChange(BaseModel):
    quantity: int = Field(gt=0, le=10000)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def seed_inventory() -> None:
    with SessionLocal() as db:
        if db.scalar(select(InventoryItem.id).limit(1)) is not None:
            return
        db.add_all([
            InventoryItem(sku="LAPTOP-001", name="Developer Laptop", price=Decimal("1499.00"), quantity=20),
            InventoryItem(sku="MOUSE-001", name="Wireless Mouse", price=Decimal("49.90"), quantity=100),
            InventoryItem(sku="KEYBOARD-001", name="Mechanical Keyboard", price=Decimal("129.00"), quantity=50),
        ])
        db.commit()
        logger.info("Seeded inventory database")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    seed_inventory()
    yield


app = FastAPI(title="Inventory Service", version="1.1.0", lifespan=lifespan)


@app.get("/health/live")
def live():
    return {"status": "alive", "service": SERVICE_NAME}


@app.get("/health/ready")
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "available"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc


@app.get("/items", response_model=list[ItemRead])
def list_items(db: Session = Depends(get_db)):
    return list(db.scalars(select(InventoryItem).order_by(InventoryItem.id)))


@app.get("/items/{item_id}", response_model=ItemRead)
def get_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@app.post("/items", response_model=ItemRead, status_code=status.HTTP_201_CREATED)
def create_item(payload: ItemCreate, db: Session = Depends(get_db)):
    item = InventoryItem(**payload.model_dump())
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="SKU already exists") from exc
    db.refresh(item)
    logger.info("Inventory item created", extra={"item_id": item.id, "quantity": item.quantity})
    return item


@app.post("/items/{item_id}/reserve", response_model=ItemRead)
def reserve_stock(item_id: int, payload: StockChange, db: Session = Depends(get_db)):
    item = db.scalar(select(InventoryItem).where(InventoryItem.id == item_id).with_for_update())
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    if item.quantity < payload.quantity:
        raise HTTPException(status_code=409, detail="Insufficient inventory")
    item.quantity -= payload.quantity
    db.commit()
    db.refresh(item)
    logger.info("Inventory reserved", extra={"item_id": item.id, "quantity": payload.quantity, "status": "reserved"})
    return item


@app.post("/items/{item_id}/release", response_model=ItemRead)
def release_stock(item_id: int, payload: StockChange, db: Session = Depends(get_db)):
    item = db.scalar(select(InventoryItem).where(InventoryItem.id == item_id).with_for_update())
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    item.quantity += payload.quantity
    db.commit()
    db.refresh(item)
    logger.info("Inventory released", extra={"item_id": item.id, "quantity": payload.quantity, "status": "released"})
    return item
