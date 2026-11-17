#!/usr/bin/env bash
# Stop CareerPilot without removing volumes or database data.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
docker compose stop
echo "stopped (volumes and database data preserved)"
