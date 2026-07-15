# Tiny Shop — Stage 3: OpenTelemetry Tracing with Jaeger

This stage extends the logging stack with distributed tracing.

## Architecture

```text
FastAPI services
  ├─ JSON logs → Docker fluentd driver → Fluent Bit → Elasticsearch → Kibana
  └─ traces → OTLP/gRPC → OpenTelemetry Collector → OTLP/gRPC → Jaeger
```

The OpenTelemetry Python SDK creates spans. FastAPI instrumentation creates server spans, HTTPX instrumentation creates outgoing client spans, and SQLAlchemy instrumentation creates database spans. W3C trace context is propagated automatically between services.

## Start

```bash
docker compose up --build
```

Open:

- Order API: http://localhost:8000/docs
- Inventory API: http://localhost:8001/docs
- Payment API: http://localhost:8002/docs
- Jaeger UI: http://localhost:16686
- Kibana: http://localhost:5601
- Elasticsearch: http://localhost:9200
- Collector health: http://localhost:13133

## Generate a trace

```bash
bash scripts/test-order.sh
```

Or:

```bash
curl -X POST http://localhost:8000/orders \
  -H 'Content-Type: application/json' \
  -d '{"item_id":1,"quantity":1}'
```

In Jaeger:

1. Select `order-service`.
2. Click **Find Traces**.
3. Open the newest `POST /orders` trace.
4. Expand spans from `order-service`, `inventory-service`, `payment-service`, and PostgreSQL.

## Test slow payment

Set in `docker-compose.yml`:

```yaml
PAYMENT_DELAY_MS: "3000"
```

Then restart payment service and create an order:

```bash
docker compose up -d --build payment-service
docker compose up -d --build order-service inventory-service
bash scripts/test-order.sh
```

The payment span should dominate the trace duration.

## Test failed payment

Set:

```yaml
PAYMENT_FAILURE_RATE: "1"
```

Restart payment service and create an order. Jaeger will show an error response path, while Elasticsearch/Kibana will contain logs with the same `trace_id` and `span_id`.

## Trace/log correlation

Application JSON logs now include:

```json
{
  "service.name": "order-service",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "message": "Order confirmed"
}
```

Copy a trace ID from Jaeger and search it in Kibana:

```text
trace_id : "<trace-id>"
```

## Important files

- `*/app/telemetry.py`: tracer provider and OTLP exporter
- `*/app/logging_config.py`: JSON logging with trace/span IDs
- `otel-collector/config.yaml`: receives traces and exports them to Jaeger
- `docker-compose.yml`: Jaeger, Collector, and app environment configuration
