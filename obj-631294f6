import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Emit a self-contained server bundle for web/kiosk deployment AND for the
  // Tauri desktop app, which runs this standalone server as a sidecar (the
  // frontend relies on Next.js BFF route handlers + httpOnly-cookie auth that
  // cannot be statically exported). `scripts/prepare-standalone.mjs` copies the
  // static assets next to `server.js` so Tauri can bundle the whole tree.
  output: "standalone",
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  async rewrites() {
    // Proxy same-origin /api/v1/* client fetches to the FastAPI sidecar.
    // Client components (login/setup gate, crash-report, session settings)
    // call relative /api/v1/... paths; without this rewrite they 404 against
    // the Next server in the packaged desktop app. The /api/setup/* and
    // /api/auth/* BFF route handlers are separate paths and unaffected.
    const backend =
      process.env.BACKEND_URL ??
      process.env.NEXT_PUBLIC_API_BASE_URL ??
      "http://127.0.0.1:8000";
    return [
      {
        source: "/api/v1/:path*",
        destination: `${backend}/api/v1/:path*`,
      },
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "no-referrer" },
        ],
      },
    ];
  },
};

export default nextConfig;
