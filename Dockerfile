# SubseaSim: single container (internal server, Docker or Railway).
# Stage 1 builds the React frontend; stage 2 runs FastAPI, which serves both
# the API/WebSocket and the static frontend on one port.
#
# The listening port comes from $PORT (set automatically by Railway and most
# PaaS hosts); it defaults to 8000 for `docker compose` / local use.

FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npx tsc -b --noEmit && npx vite build

# Python 3.13 = the version the test suite is run on.
FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SUBSEASIM_FRONTEND_DIST=/app/frontend_dist \
    PORT=8000
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=frontend /build/dist ./frontend_dist
RUN useradd --create-home --uid 10001 subseasim
USER subseasim
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import os,urllib.request;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/api/health')"
# Shell form so $PORT is expanded. --proxy-headers: Railway terminates TLS at
# its edge proxy. exec: uvicorn becomes PID 1 and receives stop signals.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
