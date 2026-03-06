# Multi-stage build: Node (frontend) → Python (backend)

# ── Stage 1: Build Vue SPA ─────────────────────────
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python runtime ────────────────────────
FROM python:3.12-slim
WORKDIR /app

# Install git (needed for mirror/sync/import scripts)
RUN apt-get update && apt-get install -y --no-install-recommends git cron \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY scripts/ ./scripts/
COPY server/ ./server/
COPY config.yaml ./

# Copy built frontend from stage 1
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Data directories (mount as volumes in production)
RUN mkdir -p /app/repos /app/db /app/sync_status

# Default port
EXPOSE 8000

# Default: run web server
CMD ["python3", "-m", "uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
