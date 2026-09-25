import json, os, datetime

ROOT = r'E:\my progam pharmacy'
FRONTEND_JSON = os.path.join(ROOT, 'scripts', 'frontend_calls.json')
BACKEND_JSON = os.path.join(ROOT, 'scripts', 'backend_routes.json')

def load(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def normalize(entry):
    """Normalize a route entry for set comparison.

    * HTTP method is upper‑cased.
    * Any ``${...}`` placeholder variables (e.g. ``${API_BASE}``) are stripped –
      frontend source often injects the base URL at runtime.
    * Query strings are removed so that ``/api/v1/analytics/top-selling?period=${p}``
      matches the backend definition ``/api/v1/analytics/top-selling``.
    * Leading slashes are ensured and trailing slashes are removed for a
      canonical representation.
    """
    method = entry['method'].upper()
    path = entry.get('path', '')
    # Remove placeholder variables like ${API_BASE} or ${serverUrl}
    import re
    path = re.sub(r"\$\{[^}]+\}", "", path)
    # Remove query string if present to match backend definitions.
    if '?' in path:
        path = path.split('?', 1)[0]
    # Strip whitespace and ensure a leading slash for consistency.
    path = path.strip()
    if path and not path.startswith('/'):
        path = '/' + path
    # Remove any trailing slash for canonical form.
    path = path.rstrip('/')
    return method, path

def main():
    fe = load(FRONTEND_JSON)
    be = load(BACKEND_JSON)
    fe_set = {normalize(e) for e in fe}
    be_set = {normalize(e) for e in be}

    # Determine orphaned backend routes and unmatched frontend calls.
    # Exclude entries with empty or placeholder paths (e.g., "", "${API_BASE}")
    def is_valid_path(p: str) -> bool:
        """Validate a backend route path for orphan detection.

        The function now simply ensures the path is non‑empty. Placeholder
        detection is handled earlier by ``normalize``; we also provide a whitelist
        for internal endpoints that should not be reported as orphaned.
        """
        return bool(p and p.strip())

    # Whitelist internal or testing‑only backend routes that are intentional
    # without a corresponding frontend call.
    whitelist_paths = {"/api/v1/webhook/creem"}

    orphan_backend = [
        e for e in be
        if normalize(e) not in fe_set
        and is_valid_path(e.get('path', ''))
        and normalize(e)[1] not in whitelist_paths
    ]
    # Explicitly drop known internal webhook route that should not be reported.
    orphan_backend = [e for e in orphan_backend if e.get('path') != '/api/v1/webhook/creem']
    # For frontend calls we match after normalization, ignoring placeholder
    # patterns; therefore we do not filter with ``is_valid_path`` here.
    unmatched_frontend = [e for e in fe if normalize(e) not in be_set]

    ts = datetime.datetime.utcnow().isoformat() + 'Z'
    lines = []
    lines.append('## API Usage Audit')
    lines.append(f'_Generated on {ts}_')
    lines.append('')
    lines.append('### Orphaned Backend Routes (no frontend call)')
    lines.append('| Method | Path | File | Line |')
    lines.append('|---|---|---|---|')
    for r in orphan_backend:
        lines.append(f"| {r['method']} | {r['path']} | {r['file']} | {r['line']} |")
    lines.append('')
    lines.append('### Unmatched Frontend Calls (no backend route)')
    lines.append('| Method | Path | File | Line |')
    lines.append('|---|---|---|---|')
    for r in unmatched_frontend:
        lines.append(f"| {r['method']} | {r['path']} | {r['file']} | {r['line']} |")
    report = '\n'.join(lines)
    # Append to PROJECT_MAP.md
    proj_path = os.path.join(ROOT, 'PROJECT_MAP.md')
    with open(proj_path, 'a', encoding='utf-8') as f:
        f.write('\n' + report + '\n')
    print('Audit report appended to PROJECT_MAP.md')

if __name__ == '__main__':
    main()