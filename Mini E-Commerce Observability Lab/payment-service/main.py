import logging
import os
import random
import time
from pythonjsonlogger import jsonlogger

from fastapi import FastAPI, Request, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

SERVICE_NAME = os.getenv("SERVICE_NAME", "payment-service")
os.environ.setdefault("PORT", "8002")

logger = logging.getLogger(SERVICE_NAME)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s %(service)s %(request_id)s %(path)s %(method)s %(status_code)s %(duration_ms)s"))
logger.addHandler(handler)
logger.propagate = False

app = FastAPI(title="Payment Service")
REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["service", "method", "path", "status"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency", ["service", "method", "path"])
PAYMENT_FAILURES = Counter("payment_failures_total", "Total payment failures", ["service"])


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
    request_id = request.headers.get("x-request-id", "-")
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
        log_event("info", "request_completed", request_id=request_id, path=path, method=request.method, status_code=status_code, duration_ms=round(duration * 1000, 2))


@app.get("/health")
def health():
    return {"status": "ok", "service": SERVICE_NAME}


@app.post("/pay")
def pay(request: Request):
    request_id = request.headers.get("x-request-id", "-")
    if random.random() < 0.35:
        PAYMENT_FAILURES.labels(SERVICE_NAME).inc()
        log_event("error", "payment_failed", request_id=request_id, path="/pay", method="POST", status_code=500)
        return Response(content='{"error":"payment provider failed"}', status_code=500, media_type="application/json")

    log_event("info", "payment_success", request_id=request_id, path="/pay", method="POST", status_code=200)
    return {"status": "paid", "request_id": request_id}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
