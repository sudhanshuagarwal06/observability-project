#!/usr/bin/env sh
set -eu
COUNT="${1:-50}"
for i in $(seq 1 "$COUNT"); do
  curl -sS -o /dev/null -w "%{http_code}\n" \
    -X POST http://localhost:8000/orders \
    -H 'Content-Type: application/json' \
    -d '{"item_id":2,"quantity":1}' || true
  sleep 0.2
done
