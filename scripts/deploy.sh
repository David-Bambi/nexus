#!/usr/bin/env bash
# Deploy the current checkout to the local production service: run the tests,
# sync dependencies, restart the systemd user unit and check it answers.
# Backup and migrations run on app start.
#
# Usage: scripts/deploy.sh [--force]   (--force allows a dirty working tree)
set -euo pipefail

cd "$(dirname "$0")/.."

SERVICE="nexus"
URL="http://127.0.0.1:8765/"

if [ "${1:-}" != "--force" ] && [ -n "$(git status --porcelain)" ]; then
    echo "Working tree is dirty; commit first or use --force" >&2
    exit 1
fi

echo "==> Running tests"
uv run pytest -q

echo "==> Syncing dependencies"
uv sync --frozen

echo "==> Restarting ${SERVICE}"
systemctl --user restart "$SERVICE"

echo "==> Waiting for ${URL}"
for _ in $(seq 1 20); do
    if curl -fsS -o /dev/null "$URL"; then
        echo "Deployed $(git rev-parse --short HEAD): service is up"
        exit 0
    fi
    sleep 1
done

echo "Service did not answer within 20s" >&2
journalctl --user -u "$SERVICE" -n 20 --no-pager >&2 || true
exit 1
