# Edge Kiosk TLS & Loopback Binding

The kiosk never exposes a network listener beyond the local machine. All TLS is
terminated by Caddy using its built-in **internal CA** (self-signed, trusted only
on the device that generated it).

## Topology (loopback only)

```
Browser (kiosk)  ──https://127.0.0.1:8443──▶  Caddy (tls internal)
                                                    ├─ /api/*  ─▶ FastAPI  127.0.0.1:8000  (--workers 1)
                                                    └─ *       ─▶ Next.js  127.0.0.1:3000  (standalone)
```

- `Caddyfile` sets `bind 127.0.0.1` so the proxy socket is loopback-only.
- Backend (`uvicorn`) and frontend (`next start` / standalone `server.js`) both
  bind `127.0.0.1`. They are unreachable from any other host on the LAN.
- Caddy's `tls internal` issues a certificate from its on-disk root; the root is
  stored under the install dir and is unique per machine.

## Why internal CA (not public certs)

A pharmacy kiosk is a single-device, single-user terminal. There is no public
hostname, so a public ACME certificate is impractical. The internal CA gives the
browser a trusted `https://` origin (required for secure cookies, `fetch`,
`crypto.subtle`, and service workers) without external trust anchors.

## Rotation / recovery

- The Caddy root lives in `<install>\caddy\storage`. Back it up with the database
  snapshot (see `deployment/policies.json` `backup`). On a fresh machine the cert
  is regenerated; the browser will re-prompt once to trust the new root.
- If the root is lost, delete `<install>\caddy\storage` and restart the
  `PharmacyCaddy` service — a new internal CA is created automatically.
