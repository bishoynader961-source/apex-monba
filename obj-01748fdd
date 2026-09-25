with open(r'E:\my progam pharmacy\app\dashboard\users\page.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Find all className with backticks
count = 0
for i, line in enumerate(content.split('\n'), 1):
    if 'className={' in line and '`' in line:
        print(f'Line {i}: {line.strip()[:150]}')
        count += 1
print(f'Total: {count}')