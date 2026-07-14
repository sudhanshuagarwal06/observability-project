#!/usr/bin/env bash
set -euo pipefail

echo "Inventory before:"
curl -fsS http://localhost:8001/items
echo -e "\n\nCreating order:"
curl -fsS -X POST http://localhost:8000/orders \
  -H 'Content-Type: application/json' \
  -d '{"item_id":1,"quantity":2}'
echo -e "\n\nOrders:"
curl -fsS http://localhost:8000/orders
echo -e "\n\nInventory after:"
curl -fsS http://localhost:8001/items
echo
