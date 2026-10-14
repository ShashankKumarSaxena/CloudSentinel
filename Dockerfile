FROM node:24-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CLOUDSENTINEL_DB=/var/lib/cloudsentinel/cloudsentinel.db \
    CLOUDSENTINEL_ALLOWED_HOSTS=127.0.0.1,localhost \
    CLOUDSENTINEL_MONITORING=1
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
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
COPY --from=frontend /build/dist frontend/dist
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)"
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-graceful-shutdown", "150"]
