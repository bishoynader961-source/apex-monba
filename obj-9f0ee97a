import os
import re

folder = 'e:\\my progam pharmacy'
files_to_check = []

for root, dirs, files in os.walk(folder):
    if 'node_modules' in root or '.git' in root or '.next' in root: continue
    for file in files:
        if file.endswith('.tsx') or file.endswith('.ts'):
            files_to_check.append(os.path.join(root, file))

found = []

for path in files_to_check:
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Let's find tags that have text-gray-200, 300, 400 but don't have bg-gray-700, 800, 900
    # Also exclude things inside <button> because buttons are usually fine (they have colored backgrounds).
    
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if re.search(r'text-(gray|slate)-(100|200|300|400|500)', line):
            if not re.search(r'bg-(gray|slate|blue|red|green|emerald|indigo|purple|amber)-(600|700|800|900|950|500)', line):
                # If there's no dark background, and it's light text, it might be a bug.
                # Just print the line to review
                if 'className' in line:
                    found.append((path, i + 1, line.strip()))

print(f"Found {len(found)} instances of light text without explicit dark background on the same line.")
for f in found[:30]: # print first 30 to see pattern
    print(f"{f[0]}:{f[1]} -> {f[2]}")
