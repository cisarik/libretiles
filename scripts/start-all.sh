#!/usr/bin/env bash
# Start both backend and frontend for Libre Tiles (dev mode)
# Usage: ./scripts/start-all.sh
#
# Starts Django and Next.js in background, shows combined output.
# Press Ctrl+C to stop both.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cleanup() {
    echo ""
    echo "Stopping services..."
    kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
    echo "Done."
}
trap cleanup EXIT INT TERM

echo "============================================"
echo "  Libre Tiles — Starting MVP"
echo "============================================"
echo ""

# Backend setup
cd "$SCRIPT_DIR/../backend"
if [ ! -f .env ]; then
    cp .env.example .env
    echo "[backend] Created .env from .env.example"
fi
poetry install --quiet
poetry run python manage.py migrate --run-syncdb --verbosity 0
poetry run python manage.py seed_models 2>/dev/null || true

# Frontend setup
cd "$SCRIPT_DIR/../frontend"
if [ ! -f .env.local ]; then
    cp .env.local.example .env.local
    echo "[frontend] Created .env.local — edit AI_GATEWAY_API_KEY!"
fi
npm install --silent

echo ""
echo "[backend]  Starting Django on http://localhost:8000"
echo "[frontend] Starting Next.js on http://localhost:3000"
echo ""
echo "Open http://localhost:3000 to play."
echo "Press Ctrl+C to stop both services."
echo ""

# Start backend
cd "$SCRIPT_DIR/../backend"
poetry run python manage.py runserver 0.0.0.0:8000 2>&1 | sed 's/^/[backend]  /' &
BACKEND_PID=$!

# Start frontend
cd "$SCRIPT_DIR/../frontend"
npm run dev 2>&1 | sed 's/^/[frontend] /' &
FRONTEND_PID=$!

wait
