"""Repair the label codemod artifacts.

The codemod inserted htmlFor into <label ...> tags but dropped the tag's
closing '>'. For each injected pair (htmlFor="*-field-N" + id="*-field-N"):
  - restore the missing '>' on the label tag
  - if the control is INSIDE the label (wrapping): implicit association already
    exists, so remove both injected attributes (cleanest markup)
  - if the control is a SIBLING after the label: keep htmlFor/id (the fix works)

Only touches attributes matching the codemod's `*-field-N` naming scheme.
"""
import os
import re

SKIP_DIRS = {
    ".next", "node_modules", ".git", "archive", ".kilo", "venv", ".venv", "dist", "build",
    "tauri-build-target", "src-tauri", "snapshots", "test-results", "e2e-artifacts",
    "backend_fastapi", "mobile", "hwid-client", "bin", ".vercel", ".idea",
    "__pycache__", ".pytest_cache", ".mypy_cache", "public",
}
INJECTED_LABEL_RE = re.compile(r'<label htmlFor="([A-Za-z0-9-]+-field-\d+)"')
INJECTED_ID_RE = re.compile(r'<(input|select|textarea)( id="[A-Za-z0-9-]+-field-\d+")')

fixed_labels = 0
reverted_pairs = 0
touched = []

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
        if "-field-" not in s or "<label htmlFor=" not in s:
            continue
        orig = s
        out = s
        # Process matches from last to first so offsets stay valid.
        matches = list(INJECTED_LABEL_RE.finditer(s))
        for m in reversed(matches):
            label_id = m.group(1)
            label_start = m.start()
            # The corrupted tag runs from '<label' up to the newline that
            # precedes the next element line; find the end of that line block.
            nl = out.find("\n", m.end())
            if nl == -1:
                continue
            tag_body = out[label_start:nl].rstrip()
            # Restore the closing '>' on the label tag.
            out = out[:label_start] + tag_body + ">" + out[nl:]
            # Now inspect: is the control inside this label (wrapping)?
            close = out.find("</label>", label_start)
            control = re.compile(r"<(input|select|textarea)\b").search(out, label_start)
            wrapping = close != -1 and control is not None and control.start() < close
            if wrapping:
                # Remove injected htmlFor from the label.
                out = out.replace(f'<label htmlFor="{label_id}"', "<label", 1)
                # Remove injected id from the control.
                out = re.sub(
                    r'<(input|select|textarea)( id="' + re.escape(label_id) + r'")',
                    r"<\1",
                    out,
                    count=1,
                )
                reverted_pairs += 1
            else:
                fixed_labels += 1
        if out != orig:
            touched.append(p)
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(out)

for t in touched:
    print("repaired:", t)
print("sibling links kept (label tag repaired):", fixed_labels)
print("wrapping pairs reverted to implicit:", reverted_pairs)
