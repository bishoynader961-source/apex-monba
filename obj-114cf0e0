"""Codemod: link <label> to the immediately-following <input>/<select>/<textarea>.

For every <label ...> without htmlFor that is followed (within a few lines) by
an <input|select|textarea> without an id, inject:
  - a stable id on the control, derived from file name + ordinal
  - htmlFor on the label pointing at it

Skips labels wrapping their control (implicit association already works) and
checkbox/radio rows are handled the same way (still improves a11y).

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
CONTROL_RE = re.compile(r"<(input|select|textarea)\b")
LABEL_RE = re.compile(r"<label\b([^>]*)>")
CONTROL_ID_RE = re.compile(r"<(input|select|textarea)\b([^>]*?)\bid=([\"'])(.*?)\3", re.S)

changed_files = {}
total_linked = 0
already_ok = 0

for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
    for fn in sorted(files):
        if not fn.endswith(".tsx"):
            continue
        p = os.path.join(root, fn)
        try:
            with open(p, encoding="utf-8") as fh:
                s = fh.read()
        except Exception:
            continue
        rel = p.replace("." + BACKSLASH, "").replace(BACKSLASH, SLASH)
        stem = re.sub(r"[^A-Za-z0-9]", "-", fn.replace(".tsx", "")).lower()
        out = s
        ordinal = 0
        file_linked = 0

        # Iterate over label tags with a shifting offset as we mutate text.
        pos = 0
        while True:
            m = LABEL_RE.search(out, pos)
            if not m:
                break
            tag = m.group(1)
            if "htmlFor" in tag:
                pos = m.end()
                continue
            # Find the next control after this label within ~600 chars.
            window = out[m.end(): m.end() + 600]
            c = CONTROL_RE.search(window)
            if not c:
                pos = m.end()
                continue
            # The control must start on the same statement block; require the
            # gap to contain no other label or closing tag sequence like </div>
            gap = window[: c.start()]
            if re.search(r"</(div|form|label)>|<label\b", gap):
                pos = m.end()
                continue
            control_abs_start = m.end() + c.start()
            cm = CONTROL_ID_RE.match(out, control_abs_start) if False else None
            # Check whether the control tag already carries an id.
            control_tag_m = re.match(r"<(input|select|textarea)\b([^>]*?)(/?)>", out[control_abs_start:], re.S)
            if not control_tag_m:
                pos = m.end()
                continue
            control_tag = control_tag_m.group(0)
            if re.search(r"\bid=", control_tag):
                already_ok += 1
                pos = control_abs_start + control_tag_m.end()
                continue
            ordinal += 1
            input_id = f"{stem}-field-{ordinal}"
            label_id = f"{stem}-label-{ordinal}"
            # 1) add id to the control tag (right after tag name)
            new_control_tag = control_tag_m.group(0).replace(
                f"<{control_tag_m.group(1)}",
                f"<{control_tag_m.group(1)} id={chr(34)}{input_id}{chr(34)}",
                1,
            )
            out = out[: control_abs_start] + new_control_tag + out[control_abs_start + len(control_tag):]
            # 2) add htmlFor to the label tag
            label_start = m.start()
            label_len = m.end() - m.start()
            new_label = f"<label htmlFor={chr(34)}{input_id}{chr(34)}" + tag
            out = out[:label_start] + new_label + out[label_start + label_len:]
            file_linked += 1
            total_linked += 1
            pos = label_start + len(new_label)

        if file_linked:
            changed_files[rel] = file_linked
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(out)

for f, n in sorted(changed_files.items()):
    print(f, n)
print("linked:", total_linked, "files:", len(changed_files), "already-had-id:", already_ok)
