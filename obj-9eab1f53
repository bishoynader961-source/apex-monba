import re

with open(r'E:\my progam pharmacy\app\dashboard\users\page.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix line 128: replace the template literal with a computed className
old_line_128 = '<tr key={u.id} className="border-b border-gray-800/50 ${selectedUser?.id === u.id ? "bg-blue-900/20" : "hover:bg-white/5"}">'
new_line_128 = '<tr key={u.id} className={selectedUser?.id === u.id ? "border-b border-gray-800/50 bg-blue-900/20" : "border-b border-gray-800/50 hover:bg-white/5"}>'
content = content.replace(old_line_128, new_line_128)

# Fix line 134
old_line_134 = '<span className="inline-block px-2 py-0.5 rounded-full text-xs font-medium ${u.is_active ? "bg-green-900/30 text-green-400" : "bg-red-900/30 text-red-400"}">'
new_line_134 = '<span className={u.is_active ? "inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-green-900/30 text-green-400" : "inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-red-900/30 text-red-400"}>'
content = content.replace(old_line_134, new_line_134)

# Fix line 209
old_line_209 = '<div key={String(label)} className="flex justify-between py-1.5 border-b border-gray-800/50">'
new_line_209 = '<div key={String(label)} className="flex justify-between py-1.5 border-b border-gray-800/50">'
content = content.replace(old_line_209, new_line_209)

# Fix line 274
old_line_274 = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
new_line_274 = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
content = content.replace(old_line_274, new_line_274)

# Fix line 302
old_line_302 = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
new_line_302 = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
content = content.replace(old_line_302, new_line_302)

# Fix line 361
old_line_361 = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
new_line_361 = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
content = content.replace(old_line_361, new_line_361)

# Fix line 361
old_line_361b = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
new_line_361b = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
content = content.replace(old_line_361b, new_line_361b)

# Fix line 302
old_line_302b = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
new_line_302b = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
content = content.replace(old_line_302b, new_line_302b)

# Fix line 380
old_line_380 = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
new_line_380 = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
content = content.replace(old_line_380, new_line_380)

# Fix line 361
old_line_361c = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
new_line_361c = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
content = content.replace(old_line_361c, new_line_361c)

with open(r'E:\my progam pharmacy\app\dashboard\users\page.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')