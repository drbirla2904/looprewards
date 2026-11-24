#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

set -a
. ./.env
set +a

BRANCH="${BRANCH:-main}"
SERVICE="${SERVICE:-offlet}"
APP_BIND_PORT="${APP_BIND_PORT:-18080}"
PREVIOUS="$(git rev-parse HEAD)"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Refusing to deploy with uncommitted changes. Commit or safely resolve them first." >&2
  exit 1
fi

sudo install -d -m 2750 -o offlet -g www-data /srv/offlet/offlet/private-media

if systemctl is-active --quiet "$SERVICE"; then
  echo "Creating pre-upgrade database and media backup..."
  bash ./deploy/backup.sh
fi

rollback_on_error() {
  result=$?
  trap - ERR
  echo "Upgrade failed; restoring code to $PREVIOUS (database migrations are not reversed)." >&2
  git reset --hard "$PREVIOUS" || true
  ./venv/bin/pip install -r requirements.txt || true
  sudo systemctl restart "$SERVICE" || true
  exit "$result"
}
trap rollback_on_error ERR

git fetch --quiet origin "$BRANCH"
git merge --ff-only "origin/$BRANCH"
./venv/bin/pip install -r requirements.txt
./venv/bin/python manage.py check
./venv/bin/python manage.py migrate --noinput
./venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart "$SERVICE"

for _ in $(seq 1 30); do
  if curl --fail --silent --show-error "http://127.0.0.1:$APP_BIND_PORT/healthz" >/dev/null 2>&1; then
    printf '%s\n' "$PREVIOUS" > .previous_release
    trap - ERR
    echo "Deployed $(git rev-parse --short HEAD) successfully."
    exit 0
  fi
  sleep 2
done

echo "Health check failed. Recent app logs:" >&2
sudo journalctl -u "$SERVICE" -n 60 --no-pager >&2 || true
false
