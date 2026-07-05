import logging
import os
import time
import uuid
from pythonjsonlogger import jsonlogger

import requests
from fastapi import FastAPI, Request, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

SERVICE_NAME = os.getenv("SERVICE_NAME", "api-service")
INVENTORY_URL = os.getenv("INVENTORY_URL", "http://localhost:8001")
PAYMENT_URL = os.getenv("PAYMENT_URL", "http://localhost:8002")

logger = logging.getLogger(SERVICE_NAME)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s %(service)s %(request_id)s %(path)s %(method)s %(status_code)s %(duration_ms)s"))
logger.addHandler(handler)
logger.propagate = False

app = FastAPI(title="API Service")

REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["service", "method", "path", "status"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency", ["service", "method", "path"])
CHECKOUT_FAILURES = Counter("checkout_failures_total", "Total checkout failures", ["service"])


def log_event(level: str, message: str, **fields):
    extra = {
        "service": SERVICE_NAME,
        "request_id": fields.pop("request_id", "-"),
        "path": fields.pop("path", "-"),
        "method": fields.pop("method", "-"),
        "status_code": fields.pop("status_code", "-"),
        "duration_ms": fields.pop("duration_ms", "-"),
        **fields,
    }
    getattr(logger, level)(message, extra=extra)


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    start = time.time()
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        duration = time.time() - start
        path = request.url.path
        REQUEST_COUNT.labels(SERVICE_NAME, request.method, path, str(status_code)).inc()
        REQUEST_LATENCY.labels(SERVICE_NAME, request.method, path).observe(duration)
        log_event(
            "info",
            "request_completed",
            request_id=request_id,
            path=path,
            method=request.method,
            status_code=status_code,
            duration_ms=round(duration * 1000, 2),
        )


@app.get("/health")
def health():
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/products")
def products():
    return {
        "products": [
            {"id": "p100", "name": "Keyboard", "price": 49.99},
            {"id": "p200", "name": "Mouse", "price": 24.99},
            {"id": "p300", "name": "Monitor", "price": 199.99},
        ]
    }


@app.get("/cart")
def cart():
    return {"items": [{"product_id": "p100", "quantity": 1}]}


@app.post("/checkout")
def checkout():
    request_id = str(uuid.uuid4())
    product_id = "p100"
    quantity = 1

    stock_response = requests.get(f"{INVENTORY_URL}/stock/{product_id}", headers={"x-request-id": request_id}, timeout=3)
    stock_response.raise_for_status()
    stock = stock_response.json()["stock"]

    if stock < quantity:
        CHECKOUT_FAILURES.labels(SERVICE_NAME).inc()
        log_event("warning", "checkout_failed_no_stock", request_id=request_id, path="/checkout", method="POST", status_code=400)
        return Response(content='{"error":"not enough stock"}', status_code=400, media_type="application/json")

    payment_response = requests.post(
        f"{PAYMENT_URL}/pay",
        json={"product_id": product_id, "amount": 49.99},
        headers={"x-request-id": request_id},
        timeout=3,
    )

    if payment_response.status_code >= 400:
        CHECKOUT_FAILURES.labels(SERVICE_NAME).inc()
        log_event("error", "checkout_failed_payment_error", request_id=request_id, path="/checkout", method="POST", status_code=payment_response.status_code)
        return Response(content=payment_response.text, status_code=payment_response.status_code, media_type="application/json")

    log_event("info", "checkout_success", request_id=request_id, path="/checkout", method="POST", status_code=200)
    return {"status": "success", "request_id": request_id}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
