import time

from fastapi import FastAPI, Request
from prometheus_client import Counter, Gauge, Histogram, make_asgi_app

HTTP_REQUESTS = Counter(
    "tiny_shop_http_requests_total",
    "Total HTTP requests processed by a service.",
    ["service", "method", "route", "status_code"],
)
HTTP_DURATION = Histogram(
    "tiny_shop_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ["service", "method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
INVENTORY_RESERVATIONS = Counter(
    "tiny_shop_inventory_reservations_total",
    "Successful inventory reservations.",
)
INVENTORY_RELEASES = Counter(
    "tiny_shop_inventory_releases_total",
    "Successful inventory releases.",
)
INVENTORY_RESERVATION_FAILURES = Counter(
    "tiny_shop_inventory_reservation_failures_total",
    "Failed inventory reservations.",
    ["reason"],
)
INVENTORY_STOCK = Gauge(
    "tiny_shop_inventory_stock_quantity",
    "Current inventory quantity by item.",
    ["item_id", "sku"],
)


def setup_metrics(app: FastAPI, service_name: str) -> None:
    @app.middleware("http")
    async def observe_requests(request: Request, call_next):
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            route_path = getattr(route, "path", "unmatched")
            HTTP_REQUESTS.labels(
                service=service_name,
                method=request.method,
                route=route_path,
                status_code=str(status_code),
            ).inc()
            HTTP_DURATION.labels(
                service=service_name,
                method=request.method,
                route=route_path,
            ).observe(time.perf_counter() - start)

    app.mount("/metrics", make_asgi_app())
