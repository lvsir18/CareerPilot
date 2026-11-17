#!/usr/bin/env bash
# CareerPilot personal-edition restore.
#
# SAFETY: never writes to the live database unless --force is given, and always
# requires an explicit confirmation token. Intended for an isolated database
# during restore drills.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SRC=""
TARGET_DB=""
FORCE="no"
DRY_RUN="no"

usage() {
  cat <<'USAGE'
Usage: restore.sh --from <backup-dir> [--target-db <name>] [--force] [--dry-run]

  --from         backup directory (contains database.sql)
  --target-db    destination database name (default: careerpilot_restore_test)
  --force        allow restoring INTO the live database (DANGEROUS)
  --dry-run      print actions without executing

By default the restore targets `careerpilot_restore_test`, so the live data is
never overwritten. Provide --force only when you intend to replace live data.
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --from) SRC="$2"; shift 2 ;;
    --target-db) TARGET_DB="$2"; shift 2 ;;
    --force) FORCE="yes"; shift ;;
    --dry-run) DRY_RUN="yes"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1"; usage; exit 1 ;;
  esac
done

if [ -z "$SRC" ]; then usage; exit 1; fi
[ -d "$SRC" ] || { echo "ERROR: backup dir not found: $SRC"; exit 1; }
[ -f "$SRC/database.sql" ] || { echo "ERROR: database.sql missing"; exit 1; }

TARGET_DB="${TARGET_DB:-careerpilot_restore_test}"

# shellcheck disable=SC1091
set -a; . ./.env; set +a
CONTAINER="${POSTGRES_CONTAINER:-careerpilot-postgres-1}"
DB_USER="${POSTGRES_USER:-career}"
LIVE_DB="${POSTGRES_DB:-careerpilot}"

if [ "$TARGET_DB" = "$LIVE_DB" ] && [ "$FORCE" != "yes" ]; then
  echo "ERROR: refusing to restore into live database '$LIVE_DB' without --force"
  exit 1
fi

echo "About to restore:"
echo "  from : $SRC"
echo "  into : $TARGET_DB (live db is '$LIVE_DB')"
echo "  mode : $([ "$DRY_RUN" = yes ] && echo dry-run || echo execute)"
if [ "$TARGET_DB" = "$LIVE_DB" ]; then
  echo "  !! THIS REPLACES LIVE DATA !!"
fi
printf 'Type the target database name to continue: '
read -r CONFIRM
[ "$CONFIRM" = "$TARGET_DB" ] || { echo "aborted"; exit 1; }

if [ "$DRY_RUN" = "yes" ]; then
  echo "dry-run: would create $TARGET_DB and load $SRC/database.sql"
  exit 0
fi

echo "creating database $TARGET_DB"
docker exec "$CONTAINER" psql -U "$DB_USER" -d postgres \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${TARGET_DB}'" >/dev/null 2>&1 || true
docker exec "$CONTAINER" psql -U "$DB_USER" -d postgres -c "DROP DATABASE IF EXISTS ${TARGET_DB}"
docker exec "$CONTAINER" psql -U "$DB_USER" -d postgres -c "CREATE DATABASE ${TARGET_DB}"

echo "loading dump"
docker exec -i "$CONTAINER" psql -U "$DB_USER" -d "$TARGET_DB" -q < "$SRC/database.sql"

echo "verifying"
docker exec "$CONTAINER" psql -U "$DB_USER" -d "$TARGET_DB" -tAc \
  "SELECT 'users='||count(*) FROM users" 2>/dev/null || true
docker exec "$CONTAINER" psql -U "$DB_USER" -d "$TARGET_DB" -tAc \
  "SELECT 'mailbox_connections='||count(*) FROM mailbox_connections" 2>/dev/null || true

if [ -f "$SRC/mailbox_secret.key" ]; then
  echo "Fernet key present at $SRC/mailbox_secret.key — restore it to .env as MAILBOX_SECRET_KEY"
  echo "(do NOT commit it; keep it separate from the SQL dump)"
fi

echo "restore finished into '$TARGET_DB'"
