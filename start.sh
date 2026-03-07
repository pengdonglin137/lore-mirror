#!/bin/bash
# Start lore-mirror: backend API + frontend dev server
# Usage: ./start.sh [--build] [--port PORT]
#   --build:      build frontend for production, serve via FastAPI
#   --port PORT:  API port (default: 8000, or $LORE_PORT env var)

set -e
cd "$(dirname "$0")"

BUILD=0
PORT="${LORE_PORT:-8000}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --build) BUILD=1; shift ;;
        --port)  PORT="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Stop any existing instances
pkill -f "uvicorn server.app" 2>/dev/null || true
pkill -f "vite.*--host" 2>/dev/null || true
sleep 1

if [ "$BUILD" = "1" ]; then
    echo "Building frontend for production..."
    (cd frontend && npx vite build)
    echo ""
    echo "Starting backend (serves frontend from frontend/dist/)..."
    echo "Access at: http://localhost:${PORT}"
    python3 -m uvicorn server.app:app --host 0.0.0.0 --port "${PORT}" --workers 4
else
    echo "Starting backend on :${PORT}..."
    nohup python3 -m uvicorn server.app:app --host 0.0.0.0 --port "${PORT}" --workers 4 > server.log 2>&1 &
    echo "  Backend PID: $! (log: server.log)"

    echo "Starting frontend dev server on :3000..."
    (cd frontend && nohup npx vite --host 0.0.0.0 > ../frontend.log 2>&1 &)
    echo "  Frontend PID: $! (log: frontend.log)"

    sleep 2
    echo ""
    echo "lore-mirror is running:"
    echo "  Frontend: http://localhost:3000"
    echo "  API:      http://localhost:${PORT}/api/stats"
    echo "  API docs: http://localhost:${PORT}/docs"
    echo ""
    echo "To stop: pkill -f 'uvicorn server.app'; pkill -f vite"
fi
