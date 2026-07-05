# Observability Project

A beginner-friendly observability lab using:

- FastAPI microservices
- Fluent Bit
- Elasticsearch
- Kibana
- Prometheus
- Grafana

## Architecture

```text
API Service + Inventory Service + Payment Service
      | JSON container logs
      v
Fluent Bit -> Elasticsearch -> Kibana

Services expose /metrics
      v
Prometheus -> Grafana
```

## Run the project

```bash
docker compose up --build
```

## URLs

- API service: http://localhost:8000
- Inventory service: http://localhost:8001
- Payment service: http://localhost:8002
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000
- Kibana: http://localhost:5601
- Elasticsearch: http://localhost:9200

Grafana login:

```text
username: admin
password: admin
```

## Generate traffic

Open another terminal and run:

```bash
curl http://localhost:8000/products
curl http://localhost:8000/cart
curl -X POST http://localhost:8000/checkout
```

Generate many checkout requests:

```bash
for i in {1..30}; do curl -s -X POST http://localhost:8000/checkout; echo; done
```

The payment service randomly fails, so you should see errors in logs and metrics.

## Prometheus queries to try

```promql
sum(rate(http_requests_total[1m])) by (service)
sum(rate(http_requests_total{status=~"5..|4.."}[1m])) by (service)
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, service))
sum(increase(checkout_failures_total[5m]))
sum(increase(payment_failures_total[5m]))
```

## Kibana setup

1. Open Kibana: http://localhost:5601
2. Go to **Stack Management** → **Data Views**.
3. Create a data view:
   - Name: `observability-logs`
   - Index pattern: `observability-logs*`
   - Timestamp field: `@timestamp` or `time`
4. Go to **Discover** and search logs.

Useful Kibana filters:

```text
service : "api-service"
levelname : "ERROR"
message : "payment_failed"
request_id : "<copy-request-id-here>"
```

## Learning tasks

1. Check logs in Kibana when checkout fails.
2. Check request rate in Grafana.
3. Check latency with the P95 panel.
4. Compare API errors with payment-service errors.
5. Add your own endpoint and metric.

## Possible improvements

- Add alert rules in Grafana.
- Add OpenTelemetry traces later.
- Add Kubernetes manifests.
- Add Nginx as an entry point.
