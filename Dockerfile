# SubseaSim: single container for internal-server deployment.
# Stage 1 builds the React frontend; stage 2 runs FastAPI, which serves both
# the API/WebSocket and the static frontend on one port.

FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npx tsc -b --noEmit && npx vite build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SUBSEASIM_FRONTEND_DIST=/app/frontend_dist
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=frontend /build/dist ./frontend_dist
RUN useradd --create-home --uid 10001 subseasim
USER subseasim
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
