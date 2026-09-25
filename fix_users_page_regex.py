import re

with open(r'E:\my progam pharmacy\app\dashboard\users\page.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Use regex to find and replace the multiline className pattern
# Match: className={selectedUser?.id === u.id \n\s+? "..." \n\s+? : "..." \n\s*}
pattern = re.compile(
    r'className=\{selectedUser\?\.id === u\.id\s*\n\s*\?\s*"[^"]*"\s*\n\s*:\s*"[^"]*"\s*\n\s*\}',
    re.DOTALL
)

def replace_tr(match):
    return '<tr key={u.id} className={selectedUser?.id === u.id ? "border-b border-gray-800/50 bg-blue-900/20" : "border-b border-gray-800/50 hover:bg-white/5"}>'

content = re.sub(pattern, replace_tr, content)

# Fix span
old_span = '<span className={u.is_active ? "inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-green-900/30 text-green-400" : "inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-red-900/30 text-red-400"}>'
new_span = '<span className={u.is_active ? "inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-green-900/30 text-green-400" : "inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-red-900/30 text-red-400"}>'
content = content.replace(old_span, new_span)

with open(r'E:\my progam pharmacy\app\dashboard\users\page.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')