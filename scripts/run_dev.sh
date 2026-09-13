#!/usr/bin/env bash
# Stop any Flask dev server already listening on the port, then start a
# fresh one using the app factory (src.app:create_app).
set -euo pipefail

cd "$(dirname "$0")/.."

PORT="${1:-5000}"

PID=$(lsof -ti "tcp:${PORT}" 2>/dev/null || true)
if [ -n "$PID" ]; then
    echo "Stopping existing server on port ${PORT} (pid ${PID})"
    kill "$PID"
    sleep 1
fi

echo "Starting Flask dev server on port ${PORT}"
exec uv run flask --app src.app:create_app run --port "$PORT"
