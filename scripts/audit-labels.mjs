#!/usr/bin/env node
/**
 * Read-only a11y audit: find <label> elements that are not linked to a control.
 * - Reports labels with no htmlFor at all.
 * - Reports labels whose STATIC htmlFor value has no matching id="..." in the same file.
 * Dynamic htmlFor (`htmlFor={expr}`) is counted separately (assumed linked).
 * Usage: node scripts/audit-labels.mjs [--root app]
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

const root = process.argv.includes("--root") ? process.argv[process.argv.indexOf("--root") + 1] : "app";

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) walk(p, out);
    else if (/\.(tsx|ts|jsx|js)$/.test(name) && !/\.test\./.test(name)) out.push(p);
  }
  return out;
}

const files = walk(root);
let totalLabels = 0, missingHtmlFor = 0, dynamicHtmlFor = 0, danglingHtmlFor = 0, implicitHtmlFor = 0;
const report = [];

for (const file of files) {
  const src = readFileSync(file, "utf8");
  // All <label ...> opening tags (may span multiple lines).
  const labelRe = /<label\b/g;
  let m;
  const fileIssues = [];
  let fileLabels = 0;
  while ((m = labelRe.exec(src)) !== null) {
    fileLabels++;
    totalLabels++;
    // Capture from the tag start to its closing '>' — labels may span lines.
    const tagEnd = src.indexOf(">", m.index);
    if (tagEnd === -1) continue;
    const tag = src.slice(m.index, tagEnd + 1);
    const selfClosing = /\/>$/.test(tag);
    void selfClosing;
    const htmlFor = tag.match(/htmlFor\s*=\s*(?:"([^"]*)"|\{([^}]*)\})/);
    if (!htmlFor) {
      // Implicit association: a <input|select|textarea opened before </label>.
      const closeIdx = src.indexOf("</label>", m.index);
      const inner = closeIdx === -1 ? "" : src.slice(m.index, closeIdx);
      if (/<(?:input|select|textarea)\b/.test(inner)) {
        implicitHtmlFor++;
        continue;
      }
      missingHtmlFor++;
      const line = src.slice(0, m.index).split("\n").length;
      const text = tag.replace(/\s+/g, " ").slice(0, 110);
      fileIssues.push({ line, kind: "no-htmlFor", text });
    } else if (htmlFor[1] !== undefined) {
      // static string: verify an id="..." exists in this file
      const idRe = new RegExp(`id\\s*=\\s*["'{]` + htmlFor[1].replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
      if (!idRe.test(src)) {
        danglingHtmlFor++;
        const line = src.slice(0, m.index).split("\n").length;
        fileIssues.push({ line, kind: `dangling htmlFor="${htmlFor[1]}"`, text: tag.replace(/\s+/g, " ").slice(0, 110) });
      }
    } else {
      dynamicHtmlFor++;
    }
  }
  if (fileIssues.length) {
    report.push({ file: relative(".", file).split(sep).join("/"), fileLabels, issues: fileIssues });
  }
}

console.log(`Files scanned: ${files.length}`);
console.log(`Total <label> tags: ${totalLabels}`);
console.log(`  missing htmlFor:    ${missingHtmlFor}`);
console.log(`  implicit (nested):  ${implicitHtmlFor} (linked via wrapping — OK)`);
console.log(`  dynamic htmlFor:    ${dynamicHtmlFor} (assumed linked)`);
console.log(`  static htmlFor OK:  ${totalLabels - missingHtmlFor - dynamicHtmlFor - danglingHtmlFor}`);
console.log(`  DANGLING htmlFor:   ${danglingHtmlFor} (htmlFor present but id= not found in same file)`);
console.log("");
for (const f of report) {
  console.log(`${f.file}  (${f.issues.length} issue(s))`);
  for (const i of f.issues) console.log(`  L${i.line}  ${i.kind}   ${i.text}`);
}
