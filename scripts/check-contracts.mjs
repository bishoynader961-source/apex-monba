// Contract-parity check (C3): every backend Pydantic schema that is part of the
// public API contract must have a matching TypeScript interface in the frontend
// contract surface. This is a dependency-free guard so a forgotten DTO surfaces
// in CI instead of at runtime.
//
// The frontend surface is split across two files:
//   * types/contracts.ts        — the core, actively-consumed contracts
//   * types/contracts-parity.ts — parity mirrors for schemas not called yet
//     (split out because contracts.ts exceeded editor size limits)
// A name in either file satisfies the check.
//
// Usage: node scripts/check-contracts.mjs
//   exit 0 = parity OK (only allow-listed backend schemas are unmatched)
//   exit 1 = at least one public backend schema has no frontend interface

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, "..");

const schemasPath = resolve(root, "backend_fastapi/app/shared/schemas.py");
const frontendPaths = [
  resolve(root, "types/contracts.ts"),
  resolve(root, "types/contracts-parity.ts"),
];

// Backend schemas that are intentionally NOT mirrored on the frontend:
//  * TokenPayload   — JWT internal claim shape, never deserialized client-side
//  * ProductBase / MedicineBase / SupplierBase — abstract base classes; only
//    their *Read/*Create/*Update subclasses are part of the wire contract.
const ALLOWLIST = new Set(["TokenPayload", "ProductBase", "MedicineBase", "SupplierBase"]);

function read(p) {
  return readFileSync(p, "utf8");
}

function backendSchemas(src) {
  const names = new Set();
  const re = /class\s+(\w+)\s*\(/g;
  let m;
  while ((m = re.exec(src))) names.add(m[1]);
  return names;
}

function frontendTypes(paths) {
  const names = new Set();
  for (const path of paths) {
    const re = /export\s+(?:interface|type)\s+(\w+)/g;
    let m;
    while ((m = re.exec(read(path)))) names.add(m[1]);
  }
  return names;
}

const backend = backendSchemas(read(schemasPath));
const frontend = frontendTypes(frontendPaths);

const gaps = [...backend]
  .filter((name) => !ALLOWLIST.has(name) && !frontend.has(name))
  .sort();

if (gaps.length === 0) {
  console.log("✓ Contract parity OK: every public backend schema has a frontend type.");
  process.exit(0);
} else {
  console.error("✗ Contract parity FAILED — backend schemas missing a frontend interface:");
  for (const g of gaps) console.error("   - " + g);
  console.error(
    "\nAdd a matching `export interface <Name>` to types/contracts.ts, or to\n" +
      "types/contracts-parity.ts when contracts.ts is at its size limit."
  );
  process.exit(1);
}
