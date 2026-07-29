FROM node:22-alpine AS frontend-builder

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci
COPY frontend/ ./
ENV MAODIE_STATIC_EXPORT=1
RUN npm run build


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MAODIE_STATIC_DIR=/app/static \
    PORT=8080

WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/skills ./skills
COPY backend/data/nutrition.db ./data/nutrition.db
COPY --from=frontend-builder /build/frontend/out ./static

RUN useradd --create-home --uid 10001 maodie \
    && mkdir -p /app/data \
    && chown -R maodie:maodie /app

USER maodie
EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
