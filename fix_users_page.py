import re

with open(r'E:\my progam pharmacy\app\dashboard\users\page.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Pattern: className={`.../...`}
# Replace template literals with forward slashes in className with regular strings
def replace_classname(match):
    inner = match.group(1)
    # Remove backticks and escape forward slashes
    inner = inner[1:-1].replace('/', '\\/')
    return 'className="' + inner + '"'

pattern = r'className=\\{(`[^`]*\/[^`]*`)\\}'
content = re.sub(pattern, replace_classname, content)

with open(r'E:\my progam pharmacy\app\dashboard\users\page.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')