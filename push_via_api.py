import urllib.request, json, os, hashlib, base64, time, sys

TOKEN = "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"
REPO = "bishoynader961-source/apex-monba"
API = "https://api.github.com"
HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "pharmacy-deploy"
}

def api_call(method, path, data=None):
    url = f"{API}{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers={**HEADERS, "Content-Type": "application/json"} if body else HEADERS, method=method)
    try:
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read()) if resp.read else {}
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        print(f"API Error {e.code}: {err[:500]}")
        raise

def get_blob_sha(filepath):
    with open(filepath, "rb") as f:
        content = f.read()
    return hashlib.sha1(content).hexdigest()

def create_blob(filepath):
    with open(filepath, "rb") as f:
        content = f.read()
    sha = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
    data = {"content": base64.b64encode(content).decode(), "encoding": "base64"}
    url = f"{API}/repos/{REPO}/git/blobs"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers={**HEADERS, "Content-Type": "application/json"}, method="POST")
    try:
        resp = urllib.request.urlopen(req)
        result = json.loads(resp.read())
        return result["sha"]
    except urllib.error.HTTPError as e:
        print(f"Error creating blob for {filepath}: {e.read().decode()[:200]}")
        raise

SKIP_DIRS = {".git", "venv", ".venv", "__pycache__", "node_modules", ".next", "build", "dist",
             "target", ".idea", "labels", ".github", "archive"}
SKIP_EXTS = {".pyc", ".exe", ".db", ".png", ".jpg", ".ico", ".spec"}
SKIP_FILES = {".env", ".env.local"}

def collect_files(root_dir):
    files = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        rel = os.path.relpath(dirpath, root_dir).replace("\\", "/")
        if rel == ".":
            rel = ""
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            if any(f.endswith(ext) for ext in SKIP_EXTS):
                continue
            if f in SKIP_FILES:
                continue
            if f == ".env.example":
                continue
            full = os.path.join(dirpath, f)
            relpath = os.path.join(rel, f).replace("\\", "/") if rel else f
            files.append((relpath, full))
    return files

def create_tree(base_tree_sha, files_data):
    tree_items = []
    for relpath, sha in files_data:
        tree_items.append({"path": relpath, "mode": "100644", "type": "blob", "sha": sha})
    data = {"tree": tree_items}
    if base_tree_sha:
        data["base_tree"] = base_tree_sha
    url = f"{API}/repos/{REPO}/git/trees"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers={**HEADERS, "Content-Type": "application/json"}, method="POST")
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())["sha"]

def main():
    print("Collecting files...")
    file_list = collect_files(r"E:\my progam pharmacy")
    print(f"Found {len(file_list)} files to upload")

    print("Creating blobs...")
    blob_shas = []
    for i, (relpath, fullpath) in enumerate(file_list):
        print(f"  [{i+1}/{len(file_list)}] {relpath}", end="", flush=True)
        try:
            sha = create_blob(fullpath)
            blob_shas.append((relpath, sha))
            print(f" -> {sha[:8]}")
        except Exception as e:
            print(f" FAILED: {e}")

    print("Creating tree...")
    tree_sha = create_tree(None, blob_shas)
    print(f"Tree SHA: {tree_sha[:12]}")

    print("Creating commit...")
    commit_data = {
        "message": "Production: license server, subscription webhooks, deployment scripts, web platform, HWID client, 59 tests",
        "tree": tree_sha,
    }
    url = f"{API}/repos/{REPO}/git/commits"
    body = json.dumps(commit_data).encode()
    req = urllib.request.Request(url, data=body, headers={**HEADERS, "Content-Type": "application/json"}, method="POST")
    resp = urllib.request.urlopen(req)
    commit_sha = json.loads(resp.read())["sha"]
    print(f"Commit SHA: {commit_sha}")

    print("Updating main branch reference...")
    ref_data = {"sha": commit_sha, "force": True}
    url = f"{API}/repos/{REPO}/git/refs/heads/main"
    body = json.dumps(ref_data).encode()
    req = urllib.request.Request(url, data=body, headers={**HEADERS, "Content-Type": "application/json"}, method="PATCH")
    resp = urllib.request.urlopen(req)
    print("SUCCESS! Branch 'main' updated.")
    print(f"View at: https://github.com/{REPO}")

if __name__ == "__main__":
    main()
