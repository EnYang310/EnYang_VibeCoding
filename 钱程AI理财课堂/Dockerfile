FROM node:22-alpine AS web

WORKDIR /web
COPY client/package.json client/package-lock.json ./
RUN npm ci
COPY client/ ./
ARG API_BASE=""
ENV API_BASE=${API_BASE}
RUN npm run build:h5

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    FRONTEND_DIR=/app/frontend

WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend ./backend
COPY --from=web /web/dist/h5 ./frontend

# The service only needs read access to its packaged files. Running it as an
# unprivileged account limits the impact of an application-level compromise.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"
CMD ["python", "-m", "app.server"]
