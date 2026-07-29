#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"
MAODIE_BIND_HOST="${MAODIE_BIND_HOST:-0.0.0.0}"

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]]; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

cd "$BACKEND_DIR"
PYTHONDONTWRITEBYTECODE=1 .venv/bin/uvicorn app.main:app \
  --host "$MAODIE_BIND_HOST" \
  --port 8000 \
  --reload &
BACKEND_PID=$!

cd "$FRONTEND_DIR"
npm run dev -- --hostname "$MAODIE_BIND_HOST"
