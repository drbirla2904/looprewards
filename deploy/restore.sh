#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

DUMP="${1:-}"
[[ -f "$DUMP" ]] || { echo "Usage: $0 backups/db-DATE.dump [backups/media-DATE.tgz]" >&2; exit 2; }
MEDIA_ARCHIVE="${2:-}"
PROOF_ARCHIVE="${3:-}"
if [[ -n "$MEDIA_ARCHIVE" && ! -f "$MEDIA_ARCHIVE" ]]; then
  echo "Media archive not found: $MEDIA_ARCHIVE" >&2
  exit 2
fi
if [[ -n "$PROOF_ARCHIVE" && ! -f "$PROOF_ARCHIVE" ]]; then
  echo "Proof archive not found: $PROOF_ARCHIVE" >&2
  exit 2
fi

set -a
. ./.env
set +a

read -r -p "This replaces the live OFFLet database. Type RESTORE to continue: " answer
[[ "$answer" == RESTORE ]] || exit 1

sudo systemctl stop offlet
export PGPASSWORD="$POSTGRES_PASSWORD"
pg_restore -h "${POSTGRES_HOST:-127.0.0.1}" -p "${POSTGRES_PORT:-5432}" \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --role="$POSTGRES_USER" < "$DUMP"
unset PGPASSWORD
if [[ -n "$MEDIA_ARCHIVE" ]]; then
  sudo mkdir -p "${MEDIA_ROOT:-$PWD/media}"
  sudo tar -xzf "$MEDIA_ARCHIVE" -C "${MEDIA_ROOT:-$PWD/media}"
fi
if [[ -n "$PROOF_ARCHIVE" ]]; then
  sudo install -d -m 2750 -o offlet -g www-data "$PWD/private-media"
  sudo tar -xzf "$PROOF_ARCHIVE" -C "$PWD/private-media"
  sudo chown -R offlet:www-data "$PWD/private-media"
fi
sudo systemctl start offlet
echo "Restore completed. Review logs and test the site before reopening traffic."
