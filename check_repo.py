import urllib.request, json

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
