"""Find <label> elements that are missing htmlFor across app .tsx pages.

Temporary diagnostics tool — delete after the accessibility bulk fix lands.
"""
import os
import re
from collections import defaultdict

SKIP_DIRS = {
    ".next", "node_modules", ".git", "archive", ".kilo", "venv", ".venv", "dist", "build",
    "tauri-build-target", "src-tauri", "snapshots", "test-results", "e2e-artifacts",
    "backend_fastapi", "mobile", "hwid-client", "bin", ".vercel", ".idea",
    "__pycache__", ".pytest_cache", ".mypy_cache", "public",
}
BACKSLASH = chr(92)
SLASH = chr(47)

results = []
for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
    for fn in files:
        if not fn.endswith(".tsx"):
            continue
        p = os.path.join(root, fn)
        try:
            with open(p, encoding="utf-8") as fh:
                s = fh.read()
        except Exception:
            continue
        for m in re.finditer(r"<label\b([^>]*)>", s):
            tag = m.group(1)
            if "htmlFor" in tag:
                continue
            line = s[: m.start()].count(chr(10)) + 1
            rel = p.replace("." + BACKSLASH, "").replace(BACKSLASH, SLASH)
            results.append((rel, line))

byfile = defaultdict(list)
for f, l in results:
    byfile[f].append(l)
for f, lines in sorted(byfile.items()):
    print(f, len(lines), lines[:14])
print("TOTAL unlinked labels:", len(results), "in", len(byfile), "files")
