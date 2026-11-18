# ── 1. Build the React frontend ────────────────────────────────────────────
FROM node:22-alpine AS frontend
WORKDIR /app/react-frontend
COPY react-frontend/package.json react-frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY react-frontend/ ./
RUN npm run build

# ── 2. Python API (serves the built SPA too) ───────────────────────────────
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000
WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY backend/ ./backend/
COPY --from=frontend /app/react-frontend/dist ./react-frontend/dist

# Bake the embedding model + a few pre-indexed 10-Ks into the image.
ARG PREBUILD_TICKERS="AAPL,AMZN,MSFT,NVDA"
RUN PREBUILD_TICKERS="$PREBUILD_TICKERS" python -m backend.scripts.prebuild

RUN useradd --create-home --uid 1000 app && chown -R app:app /app/backend/data
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/api/health')"
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]
