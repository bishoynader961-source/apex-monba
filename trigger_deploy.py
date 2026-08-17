import urllib.request, json

with open('push_via_api.py', 'r') as f:
    content = f.read()
TOKEN = content.split('TOKEN = "')[1].split('"')[0]
HEADERS = {'Authorization': f'Bearer {TOKEN}', 'Accept': 'application/vnd.github+json', 'User-Agent': 'vercel-trigger'}
REPO = 'bishoynader961-source/apex-monba'

# Get current commit SHA on main
req = urllib.request.Request(f'https://api.github.com/repos/{REPO}/git/refs/heads/main', headers=HEADERS)
resp = urllib.request.urlopen(req, timeout=15)
main_ref = json.loads(resp.read())
old_sha = main_ref['object']['sha']
print(f'Current main SHA: {old_sha}')

# Create blob for .vercelignore
with open('.vercelignore', 'rb') as f:
    content = f.read()
blob_body = json.dumps({'content': content.decode(), 'encoding': 'utf-8'}).encode()
req = urllib.request.Request(f'https://api.github.com/repos/{REPO}/git/blobs', data=blob_body, headers={**HEADERS, 'Content-Type': 'application/json'}, method='POST')
resp = urllib.request.urlopen(req, timeout=15)
blob = json.loads(resp.read())
blob_sha = blob['sha']
print(f'Blob SHA: {blob_sha}')

# Create tree
tree_body = json.dumps({'base_tree': old_sha, 'tree': [{'path': '.vercelignore', 'mode': '100644', 'type': 'blob', 'sha': blob_sha}]}).encode()
req = urllib.request.Request(f'https://api.github.com/repos/{REPO}/git/trees', data=tree_body, headers={**HEADERS, 'Content-Type': 'application/json'}, method='POST')
resp = urllib.request.urlopen(req, timeout=15)
tree = json.loads(resp.read())
tree_sha = tree['sha']
print(f'Tree SHA: {tree_sha}')

# Create commit
commit_body = json.dumps({
    'message': 'Trigger clean Vercel deployment with verified Git email',
    'tree': tree_sha,
    'parents': [old_sha]
}).encode()
req = urllib.request.Request(f'https://api.github.com/repos/{REPO}/git/commits', data=commit_body, headers={**HEADERS, 'Content-Type': 'application/json'}, method='POST')
resp = urllib.request.urlopen(req, timeout=15)
commit = json.loads(resp.read())
commit_sha = commit['sha']
print(f'New commit SHA: {commit_sha}')

# Update ref
ref_body = json.dumps({'sha': commit_sha, 'force': True}).encode()
req = urllib.request.Request(f'https://api.github.com/repos/{REPO}/git/refs/heads/main', data=ref_body, headers={**HEADERS, 'Content-Type': 'application/json'}, method='PATCH')
resp = urllib.request.urlopen(req, timeout=15)
result = json.loads(resp.read())
print(f'Ref updated: {result["object"]["sha"]}')
print('SUCCESS! Empty commit pushed to main.')
