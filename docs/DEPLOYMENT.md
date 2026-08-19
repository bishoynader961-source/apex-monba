# Deployment Guide — Pharmacy Suite

Covers the containerized stack (B7): a local/kiosk **Docker Compose** deployment with an
nginx edge, plus an **opt-in production overlay** (PostgreSQL + Nginx TLS). On-device
TLS for the kiosk is handled separately by Caddy (`docs/edge_tls.md`, Phase 4) — this
file's nginx TLS is strictly the server/container edge.

## Prerequisites
- Docker >= 27 and Docker Compose >= 2.29 (or Podman Compose).
- (Prod overlay) OpenSSL for a self-signed cert, or certbot for a real one.

## 1. Local / kiosk stack (default)
1. Configure secrets:
   ```bash
   cp backend_fastapi/.env.example backend_fastapi/.env
   # edit SECRET_KEY to a long random value
   ```
2. Build & start:
   ```bash
   docker compose up --build
   ```
   → http://localhost:8080 (nginx routes `/` → frontend, `/api` → backend).
3. The frontend image is built with `NEXT_PUBLIC_API_BASE_URL=http://localhost:8080`
   (pinned at build time) so the browser calls the nginx edge, not the unpublished
   `:8000`. For local dev *without* containers, the default `http://localhost:8000`
   applies and `app/main.py` CORS already allows `localhost:3000`.

### Environment variables
| Var | Default | Notes |
|---|---|---|
| `SECRET_KEY` | `change-me-in-production` | JWT signing secret — set a real value. |
| `PHARMACY_DB_URL` | `sqlite+aiosqlite:///./data/pharmacy.db` | Swap for Postgres via the overlay. |
| `TAX_RATE` | `0.14` | Sales tax rate. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | JWT lifetime. |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8080` | Baked into the frontend image at build time. |

### Health
- Backend: `GET /health` → JSON (also proxied at the edge as `GET /health`).
- `docker compose ps` shows all services `healthy` after ~15s.

## 2. Production overlay (opt-in)
Enables PostgreSQL and Nginx TLS **without touching the default stack**:
```bash
# generate a self-signed demo cert (or drop a real cert.pem/key.pem into ./certs)
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout certs/key.pem -out certs/cert.pem -days 365 -subj "/CN=localhost"

docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build
```
- Postgres becomes the default DB (`PHARMACY_DB_URL` overridden to
  `postgresql+asyncpg://pharmacy:${POSTGRES_PASSWORD}@db:5432/pharmacy`).
- nginx serves **HTTPS on :443** (self-signed by default; replace `certs/` with a
  certbot-issued pair for production) and redirects :80 → :443.
- **Secrets:** supply `POSTGRES_PASSWORD` and `SECRET_KEY` via a local `.env`
  (git-ignored). Never commit them; CI injects them from the platform secret store.

> Note: SQLite is single-writer; the kiosk runs uvicorn with one worker. Under the
> prod overlay, run gunicorn/uvicorn with workers only against **Postgres** (not SQLite).

## 3. CI
`.github/workflows/ci.yml` runs: backend `pytest` + `mypy --strict`, frontend
`tsc --noEmit` + `vitest` + `next build`, both `docker build`s, and a `stack-smoke`
job that brings the stack up, asserts `/health` + `/` return 200 through nginx, then
tears down.
