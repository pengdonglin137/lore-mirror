#!/bin/bash
# Start lore-mirror: backend API + frontend dev server
# Usage: ./start.sh [--build]
#   --build: build frontend for production, serve via FastAPI

set -e
cd "$(dirname "$0")"

# Stop any existing instances
pkill -f "uvicorn server.app" 2>/dev/null || true
pkill -f "vite.*--host" 2>/dev/null || true
sleep 1

if [ "$1" = "--build" ]; then
    echo "Building frontend for production..."
    (cd frontend && npx vite build)
    echo ""
    echo "Starting backend (serves frontend from frontend/dist/)..."
    echo "Access at: http://localhost:8000"
    python3 -m uvicorn server.app:app --host 0.0.0.0 --port 8000 --workers 4
else
    echo "Starting backend on :8000..."
    nohup python3 -m uvicorn server.app:app --host 0.0.0.0 --port 8000 --workers 4 > server.log 2>&1 &
    echo "  Backend PID: $! (log: server.log)"

    echo "Starting frontend dev server on :3000..."
    (cd frontend && nohup npx vite --host 0.0.0.0 > ../frontend.log 2>&1 &)
    echo "  Frontend PID: $! (log: frontend.log)"

    sleep 2
    echo ""
    echo "lore-mirror is running:"
    echo "  Frontend: http://localhost:3000"
    echo "  API:      http://localhost:8000/api/stats"
    echo "  API docs: http://localhost:8000/docs"
    echo ""
    echo "To stop: pkill -f 'uvicorn server.app'; pkill -f vite"
fi
