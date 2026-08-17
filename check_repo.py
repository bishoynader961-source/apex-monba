import urllib.request, json, os

with open('push_via_api.py', 'r') as f:
    content = f.read()
TOKEN = content.split('TOKEN = "')[1].split('"')[0]
HEADERS = {'Authorization': f'Bearer {TOKEN}', 'Accept': 'application/vnd.github+json', 'User-Agent': 'check'}
req = urllib.request.Request('https://api.github.com/repos/bishoynader961-source/apex-monba/git/trees/main?recursive=1', headers=HEADERS)
resp = urllib.request.urlopen(req, timeout=15)
data = json.loads(resp.read())
files = [t['path'] for t in data['tree'] if t['type'] == 'blob']
print(f'Total files on GitHub: {len(files)}')
for f in sorted(files):
    print(f'  {f}')

# Also list local Rust crate source files for Phase 6 verification
print()
print("Local Rust crate files:")
rust_paths = []
for root in ('rust_crypto/src', 'hw_client/src'):
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            rust_paths.append(os.path.join(dirpath, fn).replace('\\', '/'))
for rp in sorted(rust_paths):
    print(f'  {rp}')
print(f"  Cargo.toml files:")
for d in ('rust_crypto/Cargo.toml', 'hw_client/Cargo.toml'):
    if os.path.exists(d):
        print(f'  {d}')
pyd_files = [f for f in os.listdir('.') if f.endswith('.pyd')]
if pyd_files:
    print(f"  Compiled .pyd modules:")
    for f in sorted(pyd_files):
        size = os.path.getsize(f)
        print(f'  {f} ({size:,} bytes)')
