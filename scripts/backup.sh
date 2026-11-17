#!/usr/bin/env bash
# CareerPilot personal-edition backup.
#
# Creates a timestamped backup containing:
#   - database.sql            (consistent pg_dump, NOT a raw data-dir copy)
#   - uploads.tar.gz          (private uploaded files, if present)
#   - mailbox_secret.key      (Fernet key: REQUIRED to decrypt mailbox credentials)
#
# Failure policy: a failed backup never overwrites the previous good backup.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BACKUP_ROOT="${BACKUP_ROOT:-$ROOT/backups}"
KEEP="${BACKUP_KEEP:-7}"
STAMP="$(date +%Y%m%d-%H%M%S)"
DEST="$BACKUP_ROOT/$STAMP"
TMP="$DEST.tmp"

log() { printf '[backup] %s\n' "$*"; }

if [ ! -f .env ]; then
  log "ERROR: .env not found"; exit 1
fi

# shellcheck disable=SC1091
set -a; . ./.env; set +a

CONTAINER="${POSTGRES_CONTAINER:-careerpilot-postgres-1}"
DB_USER="${POSTGRES_USER:-career}"
DB_NAME="${POSTGRES_DB:-careerpilot}"

mkdir -p "$TMP"
trap 'rm -rf "$TMP"' ERR

log "dumping database $DB_NAME from container $CONTAINER"
if ! docker exec "$CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" --no-owner --no-acl > "$TMP/database.sql"; then
  log "ERROR: pg_dump failed"; exit 1
fi
[ -s "$TMP/database.sql" ] || { log "ERROR: dump is empty"; exit 1; }

# Private uploads (resumes / imported files).
UPLOAD_DIR="${UPLOAD_DIR:-}"
if [ -z "$UPLOAD_DIR" ] && docker volume inspect careerpilot_uploads >/dev/null 2>&1; then
  UPLOAD_DIR="/_upload_probe"
fi
if [ -n "$UPLOAD_DIR" ] && [ "$UPLOAD_DIR" != "/_upload_probe" ] && [ -d "$UPLOAD_DIR" ]; then
  log "archiving uploads from $UPLOAD_DIR"
  tar -czf "$TMP/uploads.tar.gz" -C "$UPLOAD_DIR" . 2>/dev/null || log "warn: uploads archive skipped"
fi

# Fernet key for mailbox credentials. Without it, restored credentials are
# unreadable, so it is backed up separately with restrictive permissions.
if [ -n "${MAILBOX_SECRET_KEY:-}" ]; then
  printf '%s\n' "$MAILBOX_SECRET_KEY" > "$TMP/mailbox_secret.key"
  chmod 600 "$TMP/mailbox_secret.key"
  log "Fernet key backed up (mode 600)"
else
  log "WARN: MAILBOX_SECRET_KEY empty — restored mailbox credentials would be unreadable"
fi

# Integrity manifest.
(
  cd "$TMP"
  for f in *; do
    if command -v shasum >/dev/null 2>&1; then
      shasum -a 256 "$f"
    elif command -v sha256sum >/dev/null 2>&1; then
      sha256sum "$f"
    fi
  done > MANIFEST.sha256
)
date -u +%Y-%m-%dT%H:%M:%SZ > "$TMP/BACKUP_TIME"

chmod -R go-rwx "$TMP"
mv "$TMP" "$DEST"
log "backup complete: $DEST"

# Retention.
if [ "$KEEP" -gt 0 ]; then
  # POSIX-compatible retention: keep the newest KEEP, delete the rest.
  ls -1d "$BACKUP_ROOT"/*/ 2>/dev/null | sort | tail -n +"$((KEEP + 1))" | while read -r old; do
    log "removing old backup: $old"
    rm -rf "$old"
  done
fi

log "NOTE: keep the Fernet key safe and separate from the SQL dump."
