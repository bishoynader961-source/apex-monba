"""Codemod v2 (safe): link <label> to its following sibling control.

Safety rules (learned from the v1 failure):
  1. Only handles the SIBLING pattern: <label ...> is closed (tag ends with
     '>'), and the next control opening tag appears before any '</label>'.
  2. The label opening tag is only modified by inserting htmlFor="..." 
     immediately before the final '>' -- no tag is ever rebuilt or truncated.
  3. The control tag gets id="..." inserted right after the tag name.
  4. Wrapping labels (control inside <label>...</label>) are skipped: they are
     already implicitly associated.
  5. Skip controls that already have an id, and labels that already have htmlFor.
"""
import os
import re

SKIP_DIRS = {
    ".next", "node_modules", ".git", "archive", ".kilo", "venv", ".venv", "dist", "build",
    "tauri-build-target", "src-tauri", "snapshots", "test-results", "e2e-artifacts",
    "backend_fastapi", "mobile", "hwid-client", "bin", ".vercel", ".idea",
    "__pycache__", ".pytest_cache", ".mypy_cache", "public",
}

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
        rel = p.replace("." + chr(92), "").replace(chr(92), "/")
        stem = re.sub(r"[^a-z0-9]+", "-", fn.replace(".tsx", "").lower()).strip("-")
        out = s
        ordinal = 0
        n_linked = 0
        pos = 0

        while True:
            lm = re.compile(r"<label\b").search(out, pos)
            if not lm:
                break
            # Find end of the label OPENING tag (respect braces minimally: JSX
            # attributes may contain { but a '>' inside braces only occurs in
            # arrow fns like =>; treat '=>' by scanning for '>' not preceded by '='.)
            i = lm.end()
            tag_end = -1
            while i < len(out):
                ch = out[i]
                if ch == ">" and out[i - 1] != "=" and out[i - 1] != "-":
                    tag_end = i
                    break
                i += 1
            if tag_end == -1:
                pos = lm.end()
                continue
            open_tag = out[lm.start(): tag_end + 1]
            if "htmlFor=" in open_tag:
                pos = tag_end + 1
                continue
            # Find the matching </label>
            close = out.find("</label>", tag_end)
            # Find the next control opening tag after the label tag
            cm = re.compile(r"<(input|select|textarea)\b").search(out, tag_end + 1)
            if cm is None:
                pos = tag_end + 1
                continue
            # Skip wrapping labels (control inside label)
            if close != -1 and cm.start() < close:
                pos = close + len("</label>")
                continue
            # Gap may contain the label's own </label> (text-only label) but
            # must not contain structural closers, another opening tag, or any
            # other closing tag (</span>, </div>...).
            gap = out[tag_end + 1: cm.start()]
            gap_no_own_close = gap.replace("</label>", "")
            if re.search(r"</|<label\b|<(?:h\d|p|div|span|button|table)\b", gap_no_own_close):
                pos = tag_end + 1
                continue
            # Parse the control opening tag safely
            j = cm.end()
            ctl_end = -1
            while j < len(out):
                ch = out[j]
                if ch == ">" and out[j - 1] not in "=-":
                    ctl_end = j
                    break
                j += 1
            if ctl_end == -1:
                pos = tag_end + 1
                continue
            ctl_tag = out[cm.start(): ctl_end + 1]
            if re.search(r"\bid=", ctl_tag):
                pos = ctl_end + 1
                continue
            ordinal += 1
            field_id = f"{stem}-field-{ordinal}"
            # Insert id right after the control tag name
            new_ctl = re.sub(
                r"(<(input|select|textarea)\b)",
                r"\1 id=" + '"' + field_id + '"',
                ctl_tag,
                count=1,
            )
            # Insert htmlFor right before the label tag's final '>'
            new_label_tag = open_tag[: -1] + f' htmlFor="{field_id}"' + ">"
            out = out[: lm.start()] + new_label_tag + out[tag_end + 1: cm.start()] + new_ctl + out[ctl_end + 1:]
            n_linked += 1
            total += 1
            pos = lm.start() + len(new_label_tag)

        if n_linked:
            changed[rel] = n_linked
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(out)

for f, n in sorted(changed.items()):
    print(f, n)
print("linked:", total, "files:", len(changed))
