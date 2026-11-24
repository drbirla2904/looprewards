#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

set -a
. ./.env
set +a

PREVIOUS="${1:-$(cat .previous_release 2>/dev/null || git rev-parse HEAD^)}"
CURRENT="$(git rev-parse HEAD)"
APP_BIND_PORT="${APP_BIND_PORT:-18080}"
git cat-file -e "$PREVIOUS^{commit}"
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Refusing rollback with uncommitted changes." >&2
  exit 1
fi

bash ./deploy/backup.sh
printf '%s\n' "$CURRENT" > .previous_release
git reset --hard "$PREVIOUS"
./venv/bin/pip install -r requirements.txt
./venv/bin/python manage.py migrate --noinput
./venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart offlet
curl --fail --silent --show-error --retry 15 --retry-delay 2 "http://127.0.0.1:$APP_BIND_PORT/healthz"
echo "Rolled back code to $PREVIOUS. Database migrations were not reversed."
