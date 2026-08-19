# B7 — Docker / Nginx / CI (Execution Plan)

> **Scope:** Finalize the already-scaffolded B7 stack. Audit shows ~80% present:
> `docker-compose.yml`, both `Dockerfile`s, `nginx.conf`, `.dockerignore`, and a
> complete `.github/workflows/ci.yml` (pytest + mypy --strict + tsc + vitest + next build
> + docker build) already exist. This plan closes the gaps and adds a clean opt-in prod overlay.
> **Mode:** Plan only — no source edits here.

---

## 0. Audit (verified against disk, 2026-08-18)

**Present & correct**
- `docker-compose.yml` — `backend` + `frontend` + `nginx` (:8080); Postgres service exists but commented out (SQLite default). `restart: unless-stopped`.
- `Dockerfile` (root) — multi-stage Next **standalone** build (valid: `next.config.ts` has `output: "standalone"`).
- `backend_fastapi/Dockerfile` — `python:3.12-slim`, `pip install -e .`, uvicorn entrypoint.
- `nginx.conf` — `/api/` → `backend:8000`, `/` → `frontend:3000` (HTTP only).
- `.dockerignore` (root) — excludes `backend_fastapi` from the frontend image (correct).
- `.github/workflows/ci.yml` — already runs the full gate matrix (backend pytest/mypy, frontend tsc/vitest/build, docker-build). **No CI rewrite needed.**
- Backend `GET /health` (`app/api/routers/health_route.py`, mounted at root).

**Gaps (this plan's tasks)**
1. **CRITICAL — frontend cannot reach the API in Docker.** `lib/api.ts:5` hardcodes `API_BASE ?? "http://localhost:8000"`. In the container stack only nginx `:8080` is published; `:8000` is not, so the browser call to `localhost:8000` fails. Fix: bake `NEXT_PUBLIC_API_BASE_URL` for the nginx edge into the frontend image. (Backend CORS is *not* an issue — via nginx the page and `/api` share origin `localhost:8080`, so no cross-origin request is made.)
2. **`docs/DEPLOYMENT.md` missing** (master-prompt §3.3 requires it). Root `README.md` is stale (describes the old Tkinter app).
3. **No healthchecks / `depends_on` conditions** in compose; nginx can start before deps are ready.
4. **No CI proof the stack boots** (only that images build).
5. **No production overlay** (Postgres default + nginx TLS) — required as an opt-in.
6. Minor: backend image has no `.dockerignore` (copies `.venv`/`tests` into the image).

**Design fork (resolved):** Two distinct deployment paradigms coexist and must stay separate:
- **Docker/Nginx B7 stack** = container edge for local/dev/CI (this plan, primary).
- **Caddyfile loopback kiosk** = on-device TLS via Caddy internal-CA (`docs/edge_tls.md`, Phase 4). Nginx TLS here is intentionally **not** the device TLS path.

---

## 1. Decisions (per user, 2026-08-18)

- **Primary (default): kiosk / local container stack** — nginx HTTP edge on `localhost:8080`; SQLite default; Postgres opt-in (already commented in compose). On-device TLS remains Caddy's job (Phase 4).
- **Opt-in secondary overlay (clean, separate files):** PostgreSQL default + Nginx TLS, provided as `docker-compose.prod.yml` + `nginx.tls.conf`, activated with `-f` (no edits to the default stack). Documented, not defaulted.
- Frontend API base: baked at **build time** via `NEXT_PUBLIC_API_BASE_URL` (Next inlines `NEXT_PUBLIC_*` into the standalone bundle). Default the image to `http://localhost:8080`; dev keeps `http://localhost:8000` via the existing default + CORS (`localhost:3000`).
- Backend stays **uvicorn** for the kiosk (single worker, matches `docs/edge_tls.md`); prod overlay documents an optional gunicorn/uvicorn-workers switch.

---

## 2. Affected files

**Modify**
- `Dockerfile` (root) — add build `ARG NEXT_PUBLIC_API_BASE_URL`.
- `docker-compose.yml` — healthchecks, `depends_on` conditions, frontend build arg, (optional) backend `.dockerignore` reference.
- `nginx.conf` — add `location = /health` → backend (so the edge exposes health).
- `backend_fastapi/Dockerfile` — (optional) add `backend_fastapi/.dockerignore` to slim the image.
- `.github/workflows/ci.yml` — add a `stack-smoke` job (or new `deploy-smoke.yml`).

**Create**
- `docs/DEPLOYMENT.md` — local stack + prod-overlay guide + env reference.
- `docker-compose.prod.yml` — Postgres + TLS overlay (opt-in).
- `nginx.tls.conf` — TLS-enabled nginx (self-signed documented; certbot-ready).
- `backend_fastapi/.dockerignore` — exclude `.venv`, `__pycache__`, `.pytest_cache`, `tests`.
- (Optional) root `README.md` — replace stale Tkinter content with the real FastAPI+Next stack + link to `docs/DEPLOYMENT.md`.

**Unchanged**
- `lib/api.ts` (default `localhost:8000` kept for dev), backend CORS (`localhost:3000`), `Caddyfile`, `vercel.json`, `ci.yml` gate matrix.

---

## 3. Ordered tasks

### Primary — kiosk / local container stack
- **P1 — Frontend API origin (fixes the stack).** In `Dockerfile` (root), before `RUN npm run build` add:
  ```dockerfile
  ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8080
  ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
  ```
  In `docker-compose.yml` `frontend` service, pass `build: { args: { NEXT_PUBLIC_API_BASE_URL: "http://localhost:8080" } }`. Validate: built bundle calls the nginx edge.
- **P2 — nginx health location.** Add to `nginx.conf`:
  ```nginx
  location = /health { proxy_pass http://backend:8000/health; }
  ```
- **P3 — Compose healthchecks + ordering.** Add to `backend`:
  ```yaml
  healthcheck:
    test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"]
    interval: 30s
    timeout: 5s
    retries: 3
    start_period: 10s
  ```
  Mirror for `frontend` (`node -e "fetch('http://localhost:3000/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"`). Make `nginx.depends_on` use `condition: service_healthy` for both.
- **P4 — `docs/DEPLOYMENT.md` (NEW).** Sections: Prereqs; `cp backend_fastapi/.env.example backend_fastapi/.env` (SECRET_KEY); `docker compose up --build` → http://localhost:8080; env vars (`SECRET_KEY`, `PHARMACY_DB_URL`, `TAX_RATE`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `NEXT_PUBLIC_API_BASE_URL`); Postgres opt-in (uncomment `db`, set `PHARMACY_DB_URL=postgresql+asyncpg://pharmacy:pharmacy@db:5432/pharmacy`); how TLS fits (Caddy on-device vs nginx prod overlay); CI note; health endpoints (`/health`, nginx `/health`).
- **P5 — CI stack smoke test.** Add job `stack-smoke` to `ci.yml` (or `deploy-smoke.yml`): `docker compose up -d --build`; poll `curl -sf http://localhost:8080/ && curl -sf http://localhost:8080/health`; `docker compose down -v`. Proves the stack boots and routes through nginx. (Keeps the existing pytest/mypy/tsc/vitest/build/docker-build jobs intact.)
- **P6 (optional) — slim backend image.** Add `backend_fastapi/.dockerignore` (`__pycache__`, `.venv`, `.pytest_cache`, `tests`, `*.db`, `.mypy_cache`).

### Opt-in overlay — production-ready (separate, default untouched)
- **O1 — `docker-compose.prod.yml`.** Defines `db` (postgres:16-alpine) + overrides backend env `PHARMACY_DB_URL=postgresql+asyncpg://pharmacy:${POSTGRES_PASSWORD}@db:5432/pharmacy`, mounts `nginx.tls.conf` into the nginx service, optionally switches backend command to `gunicorn` (uvicorn workers). Activated via `docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build`.
- **O2 — `nginx.tls.conf`.** `listen 443 ssl`; `ssl_certificate`/`ssl_certificate_key` (volume-mounted; document `openssl req -x509 ...` self-signed for demo, or certbot for real); `location /` + `/api/` + `/health` identical to `nginx.conf`; `server { listen 80; return 308 https://$host$request_uri; }`.
- **O3 — secrets.** Document `.env` (git-ignored) injection of `SECRET_KEY`, `POSTGRES_PASSWORD`; never commit secrets. `.env` already git-ignored (`.gitignore`/`.dockerignore` present).
- **O4 — docs.** Add a "Production overlay" section to `docs/DEPLOYMENT.md` covering O1–O3.

---

## 4. Validation

**Primary (kiosk/local)**
- `docker compose up --build` → all three containers `healthy`; browse http://localhost:8080 → login → POS收银 (scan + checkout) works end-to-end (proves P1 API wiring).
- `curl -f http://localhost:8080/health` → 200 (nginx → backend).
- `pytest` 110 + `mypy app --strict` 0 + `tsc --noEmit` 0 + `next build` 12/12 (unchanged — regression guard).
- Push/PR → `ci.yml` runs gates **and** `stack-smoke` (stack boots, routes 200).

**Overlay (opt-in, manual)**
- `docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build` → Postgres migrates, nginx serves `https://localhost` with a valid (self-signed) cert; `http://localhost` 308→https.

---

## 5. Risks / open questions
- **NEXT_PUBLIC_*` is build-time:** the frontend image is pinned to the baked `API_BASE`. For a single configurable image, a future runtime-injected config (`public/config.js` or Next `runtimeConfig`) could replace the build arg — deferred (out of B7 scope; baking is acceptable for the kiosk).
- **SQLite + multiple workers:** kiosk uses uvicorn `--workers 1` (WAL-safe); prod overlay with gunicorn must keep a single writer or move to Postgres — O2 documents this.
- **Root README is stale** — P4/O4 cover deployment docs; refreshing the root README is recommended but optional (non-plan doc; implementation agent may do it).
