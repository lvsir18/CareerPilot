#!/usr/bin/env bash
# CareerPilot status: containers, mailbox sync, agent runs.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== containers =="
docker compose ps --format '{{.Service}}  {{.Status}}'

echo
echo "== mailbox sync =="
docker compose exec -T postgres psql -U career -d careerpilot -tAc \
  "SELECT provider || ' | ' || status || ' | auto=' || sync_enabled || ' | last_success=' || COALESCE(to_char(last_success_at,'YYYY-MM-DD HH24:MI'),'never') || ' | err=' || COALESCE(left(last_error,80),'') FROM mailbox_connections ORDER BY provider" 2>/dev/null || echo "(query failed)"

echo
echo "== recent sync runs =="
docker compose exec -T postgres psql -U career -d careerpilot -tAc \
  "SELECT c.provider || ' | ' || r.status || ' | scanned=' || r.scanned_count || ' | cand=' || r.candidate_count || ' | dup=' || r.duplicate_count FROM mailbox_sync_runs r JOIN mailbox_connections c ON c.id=r.connection_id ORDER BY r.created_at DESC LIMIT 5" 2>/dev/null || echo "(query failed)"

echo
echo "== latest agent runs =="
docker compose exec -T postgres psql -U career -d careerpilot -tAc \
  "SELECT status || ' | ' || count(*) FROM agent_runs GROUP BY status ORDER BY 1" 2>/dev/null || echo "(query failed)"
