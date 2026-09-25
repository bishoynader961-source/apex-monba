#!/usr/bin/env node
/**
 * Release builder: produces a SIGNED, updater-ready release.
 *
 * Usage (requires the updater private key — see docs/UPDATE_STRATEGY.md):
 *   TAURI_SIGNING_PRIVATE_KEY_PATH=src-tauri/updater-key/pharmacy-suite.key \
 *     node scripts/prepare-release.mjs [notes]
 *
 * Steps:
 *   1. next build + tauri build with the release overlay (createUpdaterArtifacts)
 *   2. locate the signed .msi/.nsis + their .sig signatures
 *   3. emit latest.json (the manifest the updater endpoint serves)
 *
 * The base `npm run build` / `npm run tauri build` paths are untouched and
 * never require the signing key.
 */
import { execSync } from "node:child_process";
import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { join } from "node:path";

const conf = JSON.parse(readFileSync("src-tauri/tauri.conf.json", "utf8"));
const version = conf.version;
const notes = process.argv.slice(2).join(" ") || `Pharmacy Suite ${version}`;
const pubkey = conf.plugins?.updater?.pubkey;
if (!pubkey || pubkey.startsWith("REPLACE_")) {
  console.error("FATAL: updater pubkey not configured in tauri.conf.json");
  process.exit(1);
}
if (!process.env.TAURI_SIGNING_PRIVATE_KEY && !process.env.TAURI_SIGNING_PRIVATE_KEY_PATH) {
  console.error("FATAL: set TAURI_SIGNING_PRIVATE_KEY_PATH=src-tauri/updater-key/pharmacy-suite.key");
  process.exit(1);
}

console.log(`Building release ${version} (signed updater artifacts)…`);
execSync(
  'npm run build && npx tauri build --config src-tauri/tauri.release.conf.json',
  { stdio: "inherit", env: process.env },
);

const msiDir = "src-tauri/target/release/bundle/msi";
const nsisDir = "src-tauri/target/release/bundle/nsis";

// Tauri v2 emits <name>_<ver>_x64_en-US.msi.zip + .sig when updater artifacts
// are on (msi is zipped; nsis is the exe itself with a .sig sidecar).
const candidates = [
  { platform: "windows-x86_64", dir: msiDir },
  { platform: "windows-x86_64", dir: nsisDir },
];

const distDir = "release-updates";
mkdirSync(distDir, { recursive: true });

const platforms = {};
for (const c of candidates) {
  if (!existsSync(c.dir)) continue;
  const files = execSync(`ls -1 "${c.dir}"`, { encoding: "utf8" })
    .split("\n").filter((f) => f.endsWith(".zip") || f.endsWith(".exe"));
  for (const f of files) {
    const sig = join(c.dir, `${f}.sig`);
    if (!existsSync(sig)) {
      console.warn(`WARN: ${f} has no .sig — not updater-eligible`);
      continue;
    }
    const signature = readFileSync(sig, "utf8").trim();
    const url = `https://github.com/pharmacysuite/pharmacy-suite/releases/download/v${version}/${encodeURIComponent(f)}`;
    platforms[c.platform] = { signature, url };
    console.log(`✓ ${c.platform}: ${f}`);
  }
}

if (Object.keys(platforms).length === 0) {
  console.error("FATAL: no signed updater artifacts found — check createUpdaterArtifacts overlay");
  process.exit(1);
}

const manifest = {
  version,
  notes,
  pub_date: new Date().toISOString(),
  platforms,
};
writeFileSync(join(distDir, "latest.json"), JSON.stringify(manifest, null, 2));
console.log(`\nWrote ${distDir}/latest.json — publish it + the signed artifacts as a GitHub Release.`);
console.log("Release checklist:");
console.log("  1. Verify version bumped in tauri.conf.json + Cargo.toml + package.json");
console.log("  2. Tag the commit (v" + version + ") and push it");
console.log("  3. Create the GitHub Release with latest.json + artifacts + .sig files");
console.log("  4. Smoke-test: install previous version, run app, Check for Updates, confirm signature verification passes and restart lands on " + version);
