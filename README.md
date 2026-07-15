# Tiny Shop Stage 4: Metrics with Prometheus and Grafana

This stage keeps the Stage 3 logging and tracing pipelines and adds Prometheus metrics plus an automatically provisioned Grafana dashboard.

## Architecture

- Logs: FastAPI → Fluent Bit → Elasticsearch → Kibana
- Traces: OpenTelemetry SDK → OpenTelemetry Collector → Jaeger
- Metrics: FastAPI `/metrics` → Prometheus → Grafana

## Start

```bash
docker compose up --build
```

Open:

- Order API: http://localhost:8000/docs
- Inventory API: http://localhost:8001/docs
- Payment API: http://localhost:8002/docs
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (`admin` / `admin`)
- Jaeger: http://localhost:16686
- Kibana: http://localhost:5601

Grafana automatically provisions Prometheus, Jaeger, and the **Tiny Shop Overview** dashboard.

## Generate telemetry

```bash
bash scripts/test-order.sh
bash scripts/generate-load.sh 50
```

To create failures and latency, set these under `payment-service` in `docker-compose.yml`:

```yaml
PAYMENT_FAILURE_RATE: "0.30"
PAYMENT_DELAY_MS: "1500"
```

Then restart it:

```bash
docker compose up -d --build payment-service
bash scripts/generate-load.sh 50
```

## Metrics

Each service exposes `/metrics` and records:

- `tiny_shop_http_requests_total`
- `tiny_shop_http_request_duration_seconds`
- `tiny_shop_orders_created_total`
- `tiny_shop_orders_confirmed_total`
- `tiny_shop_orders_failed_total`
- `tiny_shop_payments_succeeded_total`
- `tiny_shop_payments_failed_total`
- `tiny_shop_payment_processing_duration_seconds`
- `tiny_shop_inventory_reservations_total`
- `tiny_shop_inventory_releases_total`
- `tiny_shop_inventory_reservation_failures_total`
- `tiny_shop_inventory_stock_quantity`

The HTTP metrics use bounded labels only: service, method, route template, and status code. Order IDs and user IDs are intentionally excluded to avoid high cardinality.

## Useful PromQL

Request rate:

```promql
sum by (service) (rate(tiny_shop_http_requests_total[5m]))
```

Error percentage:

```promql
100 * sum(rate(tiny_shop_http_requests_total{status_code=~"4..|5.."}[5m]))
/
clamp_min(sum(rate(tiny_shop_http_requests_total[5m])), 0.000001)
```

p95 latency:

```promql
histogram_quantile(
  0.95,
  sum by (le, service, route) (
    rate(tiny_shop_http_request_duration_seconds_bucket[5m])
  )
)
```

Inventory:

```promql
tiny_shop_inventory_stock_quantity
```

## Validate targets

Open http://localhost:9090/targets. All three application targets should be `UP`.

You can also inspect endpoints directly:

```bash
curl http://localhost:8000/metrics
curl http://localhost:8001/metrics
curl http://localhost:8002/metrics
```
