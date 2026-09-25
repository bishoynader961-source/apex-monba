import re

with open(r'E:\my progam pharmacy\app\dashboard\users\page.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Restore original file first
content = content.replace(
    '<tr key={u.id} className={selectedUser?.id === u.id \n                            ? "border-b border-gray-800/50 bg-blue-900/20" \n                            : "border-b border-gray-800/50 hover:bg-white/5"}>',
    '<tr key={u.id} className={`border-b border-gray-800/50 ${selectedUser?.id === u.id ? "bg-blue-900/20" : "hover:bg-white/5"}`}>'
)

content = content.replace(
    '<span className={u.is_active ? "inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-green-900/30 text-green-400" : "inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-red-900/30 text-red-400"}>',
    '<span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${u.is_active ? "bg-green-900/30 text-green-400" : "bg-red-900/30 text-red-400"}`}>'
)

with open(r'E:\my progam pharmacy\app\dashboard\users\page.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')