# B7 — CI Restoration (Docker / Nginx stack-smoke)

> **Date:** 2026-08-19
> **Scope:** Restore the B7 container-build + stack-smoke CI gate that was
> accidentally removed from `.github/workflows/ci.yml` during the B2 session.
> **Mode:** Plan only — implementation is for a follow-up agent.

---

## 1. Context & Root Cause

B7 (containerized FastAPI + Next.js stack behind an nginx edge, plus a prod
PostgreSQL/TLS overlay) is **infrastructure-complete and verified**:

- `Dockerfile` (root) — multi-stage `node:22-slim` standalone Next build → `node server.js` on :3000, with `ARG NEXT_PUBLIC_API_BASE_URL` baked to the nginx edge.
- `backend_fastapi/Dockerfile` — `python:3.12-slim`, `pip install -e .`, uvicorn on :8000 (single worker, per the M9 lock-guardrail).
- `nginx.conf` / `nginx.tls.conf` — `/api/` → backend:8000, `/` → frontend:3000, `location = /health` passthrough.
- `docker-compose.yml` / `docker-compose.prod.yml` — backend + frontend + nginx :8080, healthchecks + `depends_on: service_healthy`, opt-in Postgres/TLS overlay.
- `docs/DEPLOYMENT.md` present.

All of the above are confirmed present (glob) and marked **✅ VERIFIED** in
`CHANGELOG.md` M14 (2026-08-18) and **DONE** in `PROJECT_MAP.md`.

**Correction (post-implementation):** During planning, `ci.yml` was read in a
stale state (only `backend-test` + `dependency-scan` + `contract-check`), which
suggested the `frontend` / `docker-build` / `stack-smoke` jobs had been dropped
during the B2 session. On implementation the actual file (173 lines) was already
**complete**: it contains `backend-test`, `backend-postgres`, `frontend`
(`tsc`+`vitest`+`build`), `contract-check` (`npm run check:contracts`),
`docker-build` (both images), `e2e` (Playwright), and `dependency-scan`. The
**only** B7 job from b7 plan §3 P5 that was actually missing was **`stack-smoke`**.
No regression of the other jobs occurred.

**Net effect:** this plan's implemented change adds the single missing
`stack-smoke` job (compose up → assert `/` + `/health` through nginx → down),
which completes B7's stack-verification guarantee in CI.

---

## 2. Goal

Restore the full B7 CI gate in `.github/workflows/ci.yml` so both images build
and the compose stack boots + routes through nginx on every push/PR, while
**preserving** the B2-added `dependency-scan` and `contract-check` jobs.

---

## 3. Tasks

### T1 — Add `stack-smoke` job (the only missing B7 job)
Add a job `needs: [docker-build]` that runs `docker compose up -d --build`,
polls `curl -sf http://localhost:8080/` **and** `curl -sf http://localhost:8080/health`
(retry loop), then `docker compose down -v`. This is exactly b7 plan §3 P5.

### Already present (no change needed)
`backend-test`, `backend-postgres`, `frontend`, `contract-check`
(`npm run check:contracts`), `docker-build`, `e2e` (Playwright), and
`dependency-scan` were all already in `ci.yml` — verified on implementation.
Do **not** duplicate them.

---

## 4. Affected File

| File | Change |
|------|--------|
| `.github/workflows/ci.yml` | **MODIFY** — add the single missing `stack-smoke` job (the `frontend` / `docker-build` jobs were already present; do not duplicate them). |

No source, Docker, or compose files need editing — the B7 infra is already in place.

---

## 5. Constraints / Risks

- CI runs on `ubuntu-latest` where Docker is available; the **local** environment has no Docker daemon (cannot run a live `docker compose up` here — matches M14).
- Single-writer guarantee: backend `Dockerfile` already launches uvicorn with `--workers 1`; do not change it.
- Regression guard: the new `frontend` job must keep `tsc --noEmit` + `vitest` + `next build` green so a broken frontend image can't ship.

---

## 6. Validation

- `git push` / PR → CI runs the full matrix: `backend-test`, `dependency-scan`, `contract-check`, `frontend`, `docker-build`, `stack-smoke`.
- `stack-smoke` logs `/` = 200 and `/health` = 200 through nginx (proves the stack boots and routes).
- Images build clean (no layer errors); `docker compose down -v` cleans up.

---

## 7. Open Questions

None. The lost jobs are fully specified by `CHANGELOG.md` M14:88 and b7 plan
§3 P5; this plan restores them verbatim.
