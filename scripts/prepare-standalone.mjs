import { cpSync, existsSync } from "node:fs";
import { join } from "node:path";

// After `next build` with output:"standalone", the server bundle is emitted to
// `.next/standalone/server.js` but the static assets that it serves at runtime
// live in `.next/static`. Next requires those to sit next to the standalone
// tree so Tauri can bundle the whole thing as the desktop frontend.
const root = process.cwd();
const standalone = join(root, ".next", "standalone");
const staticSrc = join(root, ".next", "static");
const staticDst = join(standalone, ".next", "static");

if (existsSync(staticSrc)) {
  cpSync(staticSrc, staticDst, { recursive: true });
  console.log("[prepare-standalone] copied .next/static -> .next/standalone/.next/static");
} else {
  console.warn("[prepare-standalone] .next/static not found; skipping");
}

const publicSrc = join(root, "public");
if (existsSync(publicSrc)) {
  cpSync(publicSrc, join(standalone, "public"), { recursive: true });
  console.log("[prepare-standalone] copied public -> .next/standalone/public");
}
