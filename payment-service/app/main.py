import asyncio
import os
import random
from decimal import Decimal
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .logging_config import configure_logging

SERVICE_NAME = os.getenv("SERVICE_NAME", "payment-service")
FAILURE_RATE = float(os.getenv("PAYMENT_FAILURE_RATE", "0"))
DELAY_MS = int(os.getenv("PAYMENT_DELAY_MS", "0"))
logger = configure_logging(SERVICE_NAME)
app = FastAPI(title="Payment Service", version="1.1.0")


class PaymentRequest(BaseModel):
    order_id: str
    amount: Decimal = Field(gt=0, decimal_places=2)


class PaymentResponse(BaseModel):
    payment_id: str
    order_id: str
    amount: Decimal
    status: str


@app.get("/health/live")
def live():
    return {"status": "alive", "service": SERVICE_NAME}


@app.get("/health/ready")
def ready():
    return {"status": "ready"}


@app.post("/payments", response_model=PaymentResponse)
async def create_payment(payload: PaymentRequest):
    if DELAY_MS > 0:
        await asyncio.sleep(DELAY_MS / 1000)
    if random.random() < FAILURE_RATE:
        logger.error("Payment rejected", extra={"order_id": payload.order_id, "status": "failed", "error_type": "SimulatedPaymentFailure"})
        raise HTTPException(status_code=503, detail="Simulated payment failure")
    payment_id = str(uuid4())
    logger.info("Payment completed", extra={"order_id": payload.order_id, "payment_id": payment_id, "status": "completed"})
    return PaymentResponse(payment_id=payment_id, order_id=payload.order_id, amount=payload.amount, status="completed")
