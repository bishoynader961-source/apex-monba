# Pharmacy Suite — FastAPI Backend

Stateless FastAPI service for the Pharmacy Suite refactor. Interfaces with the preserved
`pharmacy.db` (read/write) and proxies license validation to the isolated Flask microservice
(`backend/app.py` on :5000). Never imports the Flask app.

## Layout
```
app/
  main.py            FastAPI app: CORS, uniform error contract, routers, lifespan
  core/              database.py (async engine/session), models.py (ORM), repositories.py
  api/routers/       health_route, auth_route, inventory_route
  shared/            config, exceptions, schemas, security, logging_config
tests/               conftest (in-memory aiosqlite) + unit/integration tests
```

## Setup
```bash
python -m venv .venv && .venv\Scripts\activate      # or use the repo venv
pip install -e ".[dev]"                              # installs app + dev deps
cp .env.example .env                                 # set SECRET_KEY, PHARMACY_DB_URL
```

## Run
```bash
# Terminal 1 — isolated Flask license microservice (unchanged)
python backend/app.py            # listens on :5000

# Terminal 2 — FastAPI backend
uvicorn app.main:app --reload --port 8000
```
Interactive docs: http://localhost:8000/docs

## Verify
```bash
python -m pytest -q          # 16 passing
python -m mypy app --strict  # 0 errors
```

## Notes
- Legacy `users.password_hash` values (scrypt BLOB) are auto-upgraded to bcrypt on first
  successful login; no users are locked out.
- WAL mode + `busy_timeout` are applied to file-backed databases for safe concurrent POS writes.
- All error responses follow `{"error": {"code": str, "message": str, "details": {}}}`.
