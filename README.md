# Tiny Shop — Stages 5, 6 and 7

This package extends the Tiny Shop observability lab with:

- **Stage 5:** Fluent Bit sends every JSON application log to both Elasticsearch and Loki.
- **Stage 6:** Grafana is provisioned for Prometheus metrics, Loki logs and Jaeger traces, including log-to-trace and trace-to-log navigation.
- **Stage 7:** Prometheus evaluates alerts and sends them to Alertmanager, which forwards them to a local webhook receiver whose container logs are easy to inspect.

## Architecture

```text
FastAPI services
├── logs ─── stdout → Docker fluentd driver → Fluent Bit ─┬→ Elasticsearch → Kibana
│                                                         └→ Loki → Grafana
├── traces ─ OpenTelemetry SDK → OTel Collector → Jaeger → Grafana
└── metrics → /metrics → Prometheus → Grafana
                               └→ Alertmanager → local alert receiver
```

## Start

```bash
docker compose up --build
```

Main endpoints:

- Grafana: http://localhost:3000 (`admin` / `admin`)
- Loki: http://localhost:3100/ready
- Prometheus: http://localhost:9090
- Prometheus alerts: http://localhost:9090/alerts
- Alertmanager: http://localhost:9093
- Jaeger: http://localhost:16686
- Kibana: http://localhost:5601
- Elasticsearch: http://localhost:9200
- Fluent Bit health/metrics: http://localhost:2020
- Order API: http://localhost:8000/docs

## Stage 5 validation: dual log outputs

Generate an order:

```bash
bash scripts/test-order.sh
```

Check Elasticsearch:

```bash
curl 'http://localhost:9200/tiny-shop-*/_search?pretty' \
  -H 'Content-Type: application/json' \
  -d '{"size":5,"sort":[{"@timestamp":"desc"}],"query":{"match_all":{}}}'
```

Check Loki:

```bash
curl -G -s 'http://localhost:3100/loki/api/v1/query_range' \
  --data-urlencode 'query={project="tiny-shop"}' \
  --data-urlencode 'limit=5' | python -m json.tool
```

Fluent Bit uses only bounded Loki labels: `project`, `environment`, `service_name`, and `level`. Unique values such as `trace_id`, `span_id`, and `order_id` stay in the JSON body.

## Stage 6 validation: correlation

Open **Grafana → Dashboards → Tiny Shop → Tiny Shop Overview**.

The dashboard contains metrics, recent Loki logs, errors with trace links, and active alert state.

### Logs to traces

1. Open a log entry in the Grafana logs panel or Explore.
2. Expand the log details.
3. Click **Open trace in Jaeger** beside the derived `TraceID` field.

### Traces to logs

1. Open the Jaeger data source in Grafana Explore and select a trace.
2. Use the trace-to-logs link for a span.
3. Grafana queries Loki using both `service_name` and the trace ID.

Useful LogQL:

```logql
{project="tiny-shop"} | json
```

```logql
{service_name="payment-service"} | json | level="ERROR"
```

```logql
{project="tiny-shop"} | json | trace_id="YOUR_TRACE_ID"
```

## Stage 7 alerts

Provisioned rules:

- `TinyShopHighP95Latency`: p95 latency above 1 second for 1 minute.
- `TinyShopHighHTTPErrorRate`: HTTP 5xx ratio above 5% for 1 minute.
- `TinyShopPaymentFailures`: payment failures above 0.05/second for 1 minute.
- `TinyShopLowInventory`: stock below 5 for 30 seconds.
- `TinyShopServiceDown`: application target unavailable for 30 seconds.

### Trigger latency and payment alerts

Set these values under `payment-service` in `docker-compose.yml`:

```yaml
PAYMENT_FAILURE_RATE: "0.5"
PAYMENT_DELAY_MS: "1500"
```

Then run:

```bash
docker compose up -d --build payment-service
bash scripts/trigger-alerts.sh 120
```

Inspect:

```bash
docker compose logs -f alert-receiver
```

### Trigger service-down alert

```bash
docker compose stop payment-service
```

Wait at least 30 seconds, then inspect Prometheus and Alertmanager.

### Trigger low-inventory alert

Repeatedly order an item until its stock is under five. The current stock is visible in the Grafana inventory panel.

## Important local-development notes

- Elasticsearch security is disabled.
- Grafana uses default local credentials.
- Jaeger all-in-one stores traces in memory.
- Alertmanager sends to a local webhook receiver rather than email/Slack.
- Do not expose this stack publicly without security, authentication, TLS and production storage configuration.
