with open(r'E:\my progam pharmacy\app\dashboard\users\page.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix line 128: tr className
old_tr = '<tr key={u.id} className={`border-b border-gray-800/50 ${selectedUser?.id === u.id ? "bg-blue-900/20" : "hover:bg-white/5"}`}>'
new_tr = '<tr key={u.id} className={selectedUser?.id === u.id ? "border-b border-gray-800/50 bg-blue-900/20" : "border-b border-gray-800/50 hover:bg-white/5"}>'
content = content.replace(old_tr, new_tr)

# Fix line 134: span className
old_span = '<span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${u.is_active ? "bg-green-900/30 text-green-400" : "bg-red-900/30 text-red-400"}`}>'
new_span = '<span className={u.is_active ? "inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-green-900/30 text-green-400" : "inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-red-900/30 text-red-400"}>'
content = content.replace(old_span, new_span)

# Fix line 209
old_209 = '<div key={String(label)} className="flex justify-between py-1.5 border-b border-gray-800/50">'
new_209 = '<div key={String(label)} className="flex justify-between py-1.5 border-b border-gray-800/50">'
content = content.replace(old_209, new_209)

# Fix line 274
old_274 = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
new_274 = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
content = content.replace(old_274, new_274)

# Fix line 302
old_302 = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
new_302 = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
content = content.replace(old_302, new_302)

# Fix line 361
old_361 = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
new_361 = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
content = content.replace(old_361, new_361)

# Fix line 361 (second occurrence)
old_361b = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
new_361b = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
content = content.replace(old_361b, new_361b)

# Fix line 302 (second)
old_302b = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
new_302b = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
content = content.replace(old_302b, new_302b)

# Fix line 380
old_380 = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
new_380 = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
content = content.replace(old_380, new_380)

# Fix line 361 (second occurrence in CreateUserModal)
old_361c = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
new_361c = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
content = content.replace(old_361c, new_361c)

with open(r'E:\my progam pharmacy\app\dashboard\users\page.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')