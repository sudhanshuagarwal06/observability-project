#!/usr/bin/env sh
set -eu
COUNT="${1:-120}"
echo "Generating ${COUNT} order requests."
echo "For payment alerts, set PAYMENT_FAILURE_RATE=0.5 and PAYMENT_DELAY_MS=1500 in docker-compose.yml first."
for i in $(seq 1 "$COUNT"); do
  curl -sS -o /dev/null -X POST http://localhost:8000/orders \
    -H 'Content-Type: application/json' \
    -d '{"item_id":1,"quantity":1}' || true
  sleep 0.1
done
echo "Prometheus alerts: http://localhost:9090/alerts"
echo "Alertmanager: http://localhost:9093"
echo "Receiver logs: docker compose logs -f alert-receiver"
