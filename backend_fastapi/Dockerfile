# Pharmacy Suite — FastAPI backend (B7)
# Build context: backend_fastapi/
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install runtime dependencies via the editable install (pyproject.toml is the
# single source of truth for deps). The app package is importable as `app`.
COPY . .
RUN pip install --upgrade pip && pip install -e .

# SQLite is the default. Override with PHARMACY_DB_URL=postgresql+asyncpg://...
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
