#!/bin/bash
# Start lore-mirror: backend API + frontend dev server
# Usage: ./start.sh [--build] [--port PORT] [--dev-port PORT]
#   --build:         build frontend for production, serve via FastAPI
#   --port PORT:     API port (default: 8000, or $LORE_PORT env var)
#   --dev-port PORT: frontend dev server port (default: 3000, or $LORE_DEV_PORT env var)

set -e
cd "$(dirname "$0")"

BUILD=0
PORT="${LORE_PORT:-8000}"
DEV_PORT="${LORE_DEV_PORT:-3000}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --build)    BUILD=1; shift ;;
        --port)     PORT="$2"; shift 2 ;;
        --dev-port) DEV_PORT="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

export LORE_PORT="${PORT}"
export LORE_DEV_PORT="${DEV_PORT}"

# PID file for clean lifecycle management
PIDFILE_BACKEND=".pid.backend"
PIDFILE_FRONTEND=".pid.frontend"

# ── Cleanup on exit ──────────────────────────────────────────
cleanup() {
    echo ""
    echo "Shutting down..."
    [[ -f "$PIDFILE_BACKEND" ]] && kill "$(cat "$PIDFILE_BACKEND")" 2>/dev/null
    [[ -f "$PIDFILE_FRONTEND" ]] && kill "$(cat "$PIDFILE_FRONTEND")" 2>/dev/null
    rm -f "$PIDFILE_BACKEND" "$PIDFILE_FRONTEND"
}
trap cleanup EXIT

# ── Stop existing instances (by PID file, then fallback to port check) ──
stop_existing() {
    # Prefer PID files for precision
    for pf in "$PIDFILE_BACKEND" "$PIDFILE_FRONTEND"; do
        if [[ -f "$pf" ]]; then
            kill "$(cat "$pf")" 2>/dev/null || true
            rm -f "$pf"
        fi
    done

    # If port is still occupied, find and kill the specific process
    local retries=0
    while ss -tlnp 2>/dev/null | grep -q ":${PORT} "; do
        if (( retries >= 10 )); then
            echo "ERROR: Port ${PORT} still occupied after 10s. Manual cleanup needed:"
            echo "  ss -tlnp | grep :${PORT}"
            exit 1
        fi
        # Kill only the process on this specific port
        local pid
        pid=$(ss -tlnp 2>/dev/null | grep ":${PORT} " | grep -oP 'pid=\K[0-9]+' | head -1)
        if [[ -n "$pid" ]]; then
            echo "Killing stale process $pid on port ${PORT}..."
            kill "$pid" 2>/dev/null || true
        fi
        sleep 1
        (( retries++ ))
    done
}

# ── Health check: wait until API responds ────────────────────
wait_for_api() {
    local retries=0
    local max=30
    while (( retries < max )); do
        if curl -sf "http://localhost:${PORT}/api/stats" >/dev/null 2>&1; then
            return 0
        fi
        # Abort if the process died
        if [[ -f "$PIDFILE_BACKEND" ]] && ! kill -0 "$(cat "$PIDFILE_BACKEND")" 2>/dev/null; then
            echo ""
            echo "ERROR: Backend process died. Check server.log:"
            tail -5 server.log 2>/dev/null
            return 1
        fi
        sleep 1
        (( retries++ ))
    done
    echo ""
    echo "ERROR: Backend not responding after ${max}s. Check server.log:"
    tail -5 server.log 2>/dev/null
    return 1
}

# ── Dependency checks ────────────────────────────────────────
ensure_python_deps() {
    if ! python3 -c "import fastapi" 2>/dev/null; then
        echo "Installing Python dependencies..."
        pip install -r requirements.txt
    fi
}

ensure_frontend_deps() {
    if [ ! -d frontend/node_modules ]; then
        echo "Installing frontend dependencies..."
        (cd frontend && npm install)
    fi
}

# ── Main ─────────────────────────────────────────────────────
stop_existing
ensure_python_deps

if [ "$BUILD" = "1" ]; then
    ensure_frontend_deps
    echo "Building frontend for production..."
    (cd frontend && npx vite build)
    echo ""
    echo "Starting backend (serves frontend from frontend/dist/)..."
    echo "Access at: http://localhost:${PORT}"
    python3 -m uvicorn server.app:app --host 0.0.0.0 --port "${PORT}" --workers 4
else
    ensure_frontend_deps

    echo "Starting backend on :${PORT}..."
    nohup python3 -m uvicorn server.app:app --host 0.0.0.0 --port "${PORT}" --workers 4 > server.log 2>&1 &
    echo $! > "$PIDFILE_BACKEND"

    echo "Waiting for API to respond..."
    if ! wait_for_api; then
        exit 1
    fi
    echo "  Backend OK (PID: $(cat "$PIDFILE_BACKEND"))"

    echo "Starting frontend dev server on :${DEV_PORT}..."
    (cd frontend && nohup npx vite --host 0.0.0.0 > ../frontend.log 2>&1 &)
    echo $! > "$PIDFILE_FRONTEND"

    sleep 2
    echo ""
    echo "lore-mirror is running:"
    echo "  Frontend: http://localhost:${DEV_PORT}"
    echo "  API:      http://localhost:${PORT}/api/stats"
    echo "  API docs: http://localhost:${PORT}/docs"
    echo ""
    echo "To stop: ./start.sh handles cleanup automatically (Ctrl+C)"
fi
