# ---- stage 1: build the frontend -------------------------------------------
FROM node:20-alpine AS frontend

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- stage 2: runtime -------------------------------------------------------
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SIGNAL_FRONTEND_DIR=/app/frontend_dist \
    SIGNAL_DATABASE_PATH=/data/signal.db

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY --from=frontend /build/dist ./frontend_dist

# Run as an unprivileged user, and give it the data directory.
RUN useradd --create-home --uid 10001 gjallar \
 && mkdir -p /data \
 && chown -R gjallar:gjallar /app /data

USER gjallar
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]