import re

with open(r'E:\my progam pharmacy\app\dashboard\users\page.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the multiline className for tr
old_tr = '''<tr key={u.id} className={selectedUser?.id === u.id 
                            ? "border-b border-gray-800/50 bg-blue-900/20" 
                            : "border-b border-gray-800/50 hover:bg-white/5"}>'''
new_tr = '<tr key={u.id} className={selectedUser?.id === u.id ? "border-b border-gray-800/50 bg-blue-900/20" : "border-b border-gray-800/50 hover:bg-white/5"}>'
content = content.replace(old_tr, new_tr)

# Fix span
old_span = '<span className={u.is_active ? "inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-green-900/30 text-green-400" : "inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-red-900/30 text-red-400"}>'
new_span = '<span className={u.is_active ? "inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-green-900/30 text-green-400" : "inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-red-900/30 text-red-400"}>'
content = content.replace(old_span, new_span)

with open(r'E:\my progam pharmacy\app\dashboard\users\page.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')