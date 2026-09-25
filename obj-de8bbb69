#!/usr/bin/env node
/**
 * Back-navigation coverage audit.
 *
 * Verifies that every dashboard-era page inherits the universal BackButton by
 * rendering inside DashboardLayout. Pages outside the shell (login, setup, POS
 * kiosk, standalone print views) are expected exceptions and live in the
 * allowlist below.
 *
 * Usage: node scripts/audit-backnav.mjs
 * Exit 1 if a page neither uses DashboardLayout nor appears in the allowlist.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

// Routes that intentionally render WITHOUT the dashboard shell. The POS kiosk
// is full-screen by design; login/setup/print views have no app chrome.
const ALLOWLIST = new Set([
  "app/page.tsx",
  "app/login/page.tsx",
  "app/setup/page.tsx",
  "app/pos/page.tsx",
  "app/print-label/page.tsx",
  "app/label-engine-preview/page.tsx",
  "app/dashboard/label-engine-preview/page.tsx",
  "app/dashboard/label-engine/page.tsx",
  "app/rx/page.tsx",
  "app/portal/page.tsx",
  "app/_global-error/page.tsx",
]);

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) {
      if (name === "api" || name === "_global-error") continue;
      walk(p, out);
    } else if (name === "page.tsx" || name === "page.ts" || name === "page.jsx") {
      out.push(p);
    }
  }
  return out;
}

const pages = walk("app");
const missing = [];
const covered = [];
const allowed = [];

for (const file of pages) {
  const rel = relative(".", file).split(sep).join("/");
  const src = readFileSync(file, "utf8");
  if (/DashboardLayout|DashboardNav/.test(src)) {
    covered.push(rel);
  } else if (ALLOWLIST.has(rel)) {
    allowed.push(rel);
  } else {
    missing.push(rel);
  }
}

console.log(`Pages scanned:            ${pages.length}`);
console.log(`Covered (dashboard shell): ${covered.length}`);
console.log(`Allowlisted (no shell):    ${allowed.length}`);
console.log(`MISSING shell/back button: ${missing.length}`);
for (const f of covered) console.log(`  ✓ ${f}`);
console.log("");
if (missing.length) {
  console.log("Pages without DashboardLayout and not allowlisted:");
  for (const f of missing) console.log(`  ✗ ${f}`);
  process.exit(1);
}
console.log("Back-navigation coverage: PASS");
