# ── Stage 1: Frontend build ──────────────────────────────────────────────────
FROM node:20-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci --prefer-offline
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python runtime ───────────────────────────────────────────────────
FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[api]"

COPY ikon/ ./ikon/
COPY config/ ./config/
COPY migrations/ ./migrations/

# Frontend statikus fájlok a build stage-ből
COPY --from=frontend-build /frontend/dist ./frontend/dist

# Perzisztens könyvtárak (Railway Volume: /app/data)
RUN mkdir -p /app/data /app/output

ENV IKON_DB_PATH=/app/data/ikon.db
# HuggingFace model cache a Volume-ra → csak egyszer töltődik le
ENV SENTENCE_TRANSFORMERS_HOME=/app/data/models
ENV HF_HOME=/app/data/models

EXPOSE 8000

CMD uvicorn ikon.api.app:app --host 0.0.0.0 --port ${PORT:-8000}
