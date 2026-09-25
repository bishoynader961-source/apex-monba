import os, re, json, sys

def main():
    root = r'E:\my progam pharmacy'
    frontend_calls = []
    backend_routes = []
    # Frontend file extensions
    fe_exts = {'.js', '.jsx', '.ts', '.tsx'}
    # Limit walk to known frontend and backend directories for performance
    target_dirs = [
        os.path.join(root, 'app'),
        os.path.join(root, 'components'),
        os.path.join(root, 'stores'),
        os.path.join(root, 'backend_fastapi', 'app', 'api', 'routers')
    ]
    for base in target_dirs:
        if not os.path.isdir(base):
            continue
        for dirpath, _, filenames in os.walk(base):
            for fn in filenames:
                _, ext = os.path.splitext(fn)
                if ext.lower() in fe_exts:
                    path = os.path.join(dirpath, fn)
                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                    except Exception:
                        continue
                    for i, line in enumerate(lines, start=1):
                        if 'fetch(' in line:
                            # extract URL literal if possible
                            m = re.search(r'fetch\s*\(\s*([`\"\'])(.+?)\1', line)
                            url = m.group(2) if m else ''
                            # default method GET, look for method in same line
                            method = 'GET'
                            meth_match = re.search(r'method\s*[:=]\s*[`\"\']?(GET|POST|PUT|DELETE|PATCH)[`\"\']?', line, re.I)
                            if meth_match:
                                method = meth_match.group(1).upper()
                            else:
                                # look ahead few lines for method spec
                                for look in lines[i:i+4]:
                                    m2 = re.search(r'method\s*[:=]\s*[`\"\']?(GET|POST|PUT|DELETE|PATCH)[`\"\']?', look, re.I)
                                    if m2:
                                        method = m2.group(1).upper()
                                        break
                            frontend_calls.append({
                                'file': os.path.relpath(path, root),
                                'line': i,
                                'method': method,
                                'path': url
                            })
    # Scan backend routers separately
    backend_dir = os.path.join(root, 'backend_fastapi', 'app', 'api', 'routers')
    if os.path.isdir(backend_dir):
        for dirpath, _, filenames in os.walk(backend_dir):
            for fn in filenames:
                if not fn.lower().endswith('.py'):
                    continue
                path = os.path.join(dirpath, fn)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        text = f.read()
                except Exception:
                    continue
                # find router prefix if defined
                prefix = ''
                prefix_match = re.search(r'APIRouter\s*\(\s*prefix\s*=\s*([`\"])(.+?)\1', text)
                if prefix_match:
                    prefix = prefix_match.group(2)
                # iterate decorators
                for m in re.finditer(r'@router\.(get|post|put|delete|patch)\s*\(\s*([`\"])(.+?)\2', text):
                    verb = m.group(1).upper()
                    route_path = m.group(3)
                    full_path = (prefix.rstrip('/') + '/' + route_path.lstrip('/')) if prefix else route_path
                    line_num = text[:m.start()].count('\n') + 1
                    backend_routes.append({
                        'file': os.path.relpath(path, root),
                        'line': line_num,
                        'method': verb,
                        'path': full_path
                    })
    # write JSON files
    out_dir = os.path.join(root, 'scripts')
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, 'frontend_calls.json'), 'w', encoding='utf-8') as f:
        json.dump(frontend_calls, f, indent=2)
    with open(os.path.join(out_dir, 'backend_routes.json'), 'w', encoding='utf-8') as f:
        json.dump(backend_routes, f, indent=2)

if __name__ == '__main__':
    main()