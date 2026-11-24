#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

set -a
# .env is a trusted, owner-controlled deployment file.
. ./.env
set +a

: "${POSTGRES_DB:?Missing POSTGRES_DB in .env}"
: "${POSTGRES_USER:?Missing POSTGRES_USER in .env}"
: "${POSTGRES_PASSWORD:?Missing POSTGRES_PASSWORD in .env}"
MEDIA_DIR="${MEDIA_ROOT:-$PWD/media}"
PRIVATE_MEDIA_DIR="$PWD/private-media"
BACKUP_DIR="${BACKUP_DIR:-$PWD/backups}"
REMOTE="${RCLONE_REMOTE:-}"
STAMP="$(date +%F-%H%M%S)"
mkdir -p "$BACKUP_DIR"

export PGPASSWORD="$POSTGRES_PASSWORD"
pg_dump -h "${POSTGRES_HOST:-127.0.0.1}" -p "${POSTGRES_PORT:-5432}" \
  -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" > "$BACKUP_DIR/db-$STAMP.dump"
tar -czf "$BACKUP_DIR/media-$STAMP.tgz" -C "$MEDIA_DIR" .
tar -czf "$BACKUP_DIR/proofs-$STAMP.tgz" -C "$PRIVATE_MEDIA_DIR" .
unset PGPASSWORD

if [[ -n "$REMOTE" ]]; then
  command -v rclone >/dev/null || { echo "RCLONE_REMOTE set but rclone is not installed." >&2; exit 1; }
  rclone copy "$BACKUP_DIR/db-$STAMP.dump" "$REMOTE"
  rclone copy "$BACKUP_DIR/media-$STAMP.tgz" "$REMOTE"
  rclone copy "$BACKUP_DIR/proofs-$STAMP.tgz" "$REMOTE"
fi

find "$BACKUP_DIR" -type f \( -name 'db-*.dump' -o -name 'media-*.tgz' -o -name 'proofs-*.tgz' \) -mtime +14 -delete
echo "Backup $STAMP completed."
