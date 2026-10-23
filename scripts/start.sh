#!/usr/bin/env bash
# Start CareerPilot (personal edition) and report local entry points.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

[ -f .env ] || { echo "ERROR: .env missing (copy .env.example and fill required values)"; exit 1; }
for key in SESSION_SECRET MAILBOX_SECRET_KEY LLM_API_KEY; do
  val="$(grep -E "^${key}=" .env | cut -d= -f2- || true)"
  [ -n "$val" ] || echo "WARN: $key is empty"
done

docker compose up -d --wait
echo
docker compose ps

echo
echo "Web :  http://localhost:3000"
echo "API :  http://localhost:8000/readyz"
