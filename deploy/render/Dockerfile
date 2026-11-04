# Hosted offline demo for Render. Synthetic data only; no cloud credentials or live scans.
FROM node:24-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CLOUDSENTINEL_MODE=demo \
    CLOUDSENTINEL_DB=/var/lib/cloudsentinel/cloudsentinel.db \
    CLOUDSENTINEL_MODEL_DIR=/var/lib/cloudsentinel/models \
    CLOUDSENTINEL_MONITORING=1 \
    CLOUDSENTINEL_SECURE_COOKIES=1 \
    CLOUDSENTINEL_DOCS=0 \
    CLOUDSENTINEL_SMTP_ENABLED=0
WORKDIR /app
COPY backend/requirements.txt backend/
RUN python -m pip install --no-cache-dir -r backend/requirements.txt \
    && groupadd --gid 10001 cloudsentinel \
    && useradd --uid 10001 --gid 10001 --create-home cloudsentinel \
    && mkdir -p /var/lib/cloudsentinel \
    && chown 10001:10001 /var/lib/cloudsentinel \
    && chmod 700 /var/lib/cloudsentinel
COPY backend/__init__.py backend/__init__.py
COPY backend/app/ backend/app/
COPY data/ data/
COPY scripts/ scripts/
COPY deploy/render/start.sh deploy/render/start.sh
COPY --from=frontend /build/dist frontend/dist
USER 10001:10001
EXPOSE 10000
CMD ["sh", "deploy/render/start.sh"]
