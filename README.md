# Tiny Shop — Stage 1 v2

A small FastAPI microservice application designed as the application foundation for an observability lab.

## Services

- **Order Service** — persists orders in PostgreSQL and orchestrates inventory reservation and payment.
- **Inventory Service** — persists products and stock in PostgreSQL.
- **Payment Service** — simulates successful, delayed, and failed payments.

All services write structured JSON logs to stdout and expose liveness/readiness endpoints.

## Run

```bash
docker compose up --build
```

API documentation:

- Order: http://localhost:8000/docs
- Inventory: http://localhost:8001/docs
- Payment: http://localhost:8002/docs

## Verify

```bash
curl http://localhost:8001/items

curl -X POST http://localhost:8000/orders \
  -H 'Content-Type: application/json' \
  -d '{"item_id":1,"quantity":2}'

curl http://localhost:8000/orders
```

Or run:

```bash
bash scripts/test-order.sh
```

## Failure experiments

Set in `docker-compose.yml` under `payment-service`:

```yaml
PAYMENT_FAILURE_RATE: "1"
PAYMENT_DELAY_MS: "3000"
```

`PAYMENT_FAILURE_RATE` is a value from `0` to `1`. Restart the payment service after changes:

```bash
docker compose up -d --build payment-service
```

When payment fails, the order remains in PostgreSQL with status `failed`, and the reserved inventory is released.

## Health endpoints

Every service has:

- `/health/live` — process is alive
- `/health/ready` — service dependencies are available

## Reset databases

```bash
docker compose down -v
```

## Next stage

Add Fluent Bit to collect these JSON stdout logs and fan them out to Elasticsearch and an OpenTelemetry Collector.
