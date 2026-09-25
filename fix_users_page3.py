import re

with open(r'E:\my progam pharmacy\app\dashboard\users\page.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

def replace_classname(match):
    inner = match.group(1)
    # Remove backticks, keep forward slashes as-is (they're fine in double-quoted strings)
    inner = inner[1:-1]
    return 'className="' + inner + '"'

pattern = r'className=\{(`[^`]*\/[^`]*`)\}'
content = re.sub(pattern, replace_classname, content)

with open(r'E:\my progam pharmacy\app\dashboard\users\page.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')