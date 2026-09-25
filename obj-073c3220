"""Codemod pass 3: link labels to sibling controls that ALREADY have an id.

Handles two zero-risk cases:
  A. Label ... then up to 2 wrapper lines ... then a control whose opening tag
     already carries an explicit `id="..."` -> inject the matching htmlFor.
  B. Reversed order: control (with id) first, label after -> same injection.
"""
import os
import re

SKIP_DIRS = {
    ".next", "node_modules", ".git", "archive", ".kilo", "venv", ".venv", "dist", "build",
    "tauri-build-target", "src-tauri", "snapshots", "test-results", "e2e-artifacts",
    "backend_fastapi", "mobile", "hwid-client", "bin", ".vercel", ".idea",
    "__pycache__", ".pytest_cache", ".mypy_cache", "public",
}


def find_tag_end(s, start):
    """End index of the JSX opening tag starting at `start` ('<' position)."""
    i = start + 1
    while i < len(s):
        ch = s[i]
        if ch == ">" and s[i - 1] not in "=-":
            return i
        i += 1
    return -1


changed = {}
total = 0

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
        out = s
        n_linked = 0
        pos = 0

        while True:
            lm = re.compile(r"<label\b").search(out, pos)
            if not lm:
                break
            tag_end = find_tag_end(out, lm.start())
            if tag_end == -1:
                pos = lm.end()
                continue
            open_tag = out[lm.start(): tag_end + 1]
            if "htmlFor=" in open_tag:
                pos = tag_end + 1
                continue
            close = out.find("</label>", tag_end)

            # Case A: scan forward up to 2 wrapper lines for a control with id
            window_end = min(len(out), tag_end + 1 + 400)
            window = out[tag_end + 1: window_end]
            # Cut window at the label's own close or a structural boundary
            stop = len(window)
            m_stop = re.search(r"</(div|form|p|span|td|tr)>|<label\b", window)
            if m_stop:
                stop = m_stop.start()
            if close != -1:
                rel_close = close - (tag_end + 1)
                if 0 <= rel_close < stop:
                    stop = rel_close
            window = window[:stop]

            cm = re.compile(r"<(input|select|textarea)\b").search(window)
            if cm:
                ctl_abs = tag_end + 1 + cm.start()
                ctl_tag_end = find_tag_end(out, ctl_abs)
                if ctl_tag_end != -1:
                    ctl_tag = out[ctl_abs: ctl_tag_end + 1]
                    idm = re.search(r'\bid="([^"]+)"', ctl_tag)
                    if idm and cm.start() > 0 and "{" not in window[: cm.start()].split("\n")[-1]:
                        field_id = idm.group(1)
                        new_tag = open_tag[: -1] + f' htmlFor="{field_id}"' + ">"
                        out = out[: lm.start()] + new_tag + out[tag_end + 1:]
                        n_linked += 1
                        total += 1
                        pos = lm.start() + len(new_tag)
                        continue
            pos = tag_end + 1

        if n_linked:
            changed[p.replace("." + chr(92), "").replace(chr(92), "/")] = n_linked
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(out)

for f, n in sorted(changed.items()):
    print(f, n)
print("linked-by-existing-id:", total, "files:", len(changed))
