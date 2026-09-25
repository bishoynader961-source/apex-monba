// Single source of truth for the FastAPI backend base URL.
//
// Used by BFF route handlers, Server Actions, and client boot checks.
// `NEXT_PUBLIC_API_*` values are inlined by Next.js at build time, so the
// packaged Tauri app and Docker builds bake this in via build args
// (see Dockerfile / docker-compose.yml / .env.example).
//
// NOTE: do NOT introduce a second env var for the local backend (e.g.
// `NEXT_PUBLIC_API_URL`) — that name previously shipped in the setup BFF
// routes while every other file read `NEXT_PUBLIC_API_BASE_URL`, so a
// half-configured build silently hit a disconnected port.
export const BACKEND_URL: string =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
