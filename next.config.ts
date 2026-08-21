import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Emit a self-contained server bundle for web/kiosk deployment AND for the
  // Tauri desktop app, which runs this standalone server as a sidecar (the
  // frontend relies on Next.js BFF route handlers + httpOnly-cookie auth that
  // cannot be statically exported). `scripts/prepare-standalone.mjs` copies the
  // static assets next to `server.js` so Tauri can bundle the whole tree.
  output: "standalone",
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
