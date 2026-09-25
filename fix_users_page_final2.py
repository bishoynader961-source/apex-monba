import re

with open(r'E:\my progam pharmacy\app\dashboard\users\page.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix line 128: replace the template literal with a computed className
# Original: className="border-b border-gray-800/50 ${selectedUser?.id === u.id ? "bg-blue-900/20" : "hover:bg-white/5"}"
# Replace with a computed variable

# Fix line 128
old_line_128 = '<tr key={u.id} className="border-b border-gray-800/50 ${selectedUser?.id === u.id ? "bg-blue-900/20" : "hover:bg-white/5"}">'
new_line_128 = '''<tr key={u.id} className={selectedUser?.id === u.id 
                            ? "border-b border-gray-800/50 bg-blue-900/20" 
                            : "border-b border-gray-800/50 hover:bg-white/5"}">'''

content = content.replace(old_line_128, new_line_128)

# Fix line 134: <span className="inline-block px-2 py-0.5 rounded-full text-xs font-medium ${u.is_active ? "bg-green-900/30 text-green-400" : "bg-red-900/30 text-red-400"}">
old_line_134 = '<span className="inline-block px-2 py-0.5 rounded-full text-xs font-medium ${u.is_active ? "bg-green-900/30 text-green-400" : "bg-red-900/30 text-red-400"}">'
new_line_134 = '<span className={u.is_active ? "inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-green-900/30 text-green-400" : "inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-red-900/30 text-red-400"}">'

content = content.replace(old_line_134, new_line_134)

# Fix line 209: <div key={String(label)} className="flex justify-between py-1.5 border-b border-gray-800/50">
old_line_209 = '<div key={String(label)} className="flex justify-between py-1.5 border-b border-gray-800/50">'
new_line_209 = '<div key={String(label)} className="flex justify-between py-1.5 border-b border-gray-800/50">'
content = content.replace(old_line_209, new_line_209)

# Fix line 241: <AuthConfirmModal ... />
# Actually line 241 is fine, it's a self-closing component

# Fix line 243: <CreateUserModal ... />
# Fix line 243: self-closing component, should be fine

# Fix line 245: <EditUserModal ... />
# Fix line 245: self-closing component, should be fine

# Fix line 247: <AuthConfirmModal ... />
# Fix line 247: self-closing component, should be fine

# Fix line 274: <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
old_line_274 = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
new_line_274 = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
# This one is already a string, not a template literal - should be fine

# Fix line 302: <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
old_line_302 = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
new_line_302 = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
# Already a string

# Fix line 304: <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100 mb-4">{t("users.modalNew")}</h2>
# This is fine

# Fix line 305: {error && <p className="text-sm text-red-400 mb-3">{error}</p>}
# Fine

# Fix line 308: <label className="block text-sm font-medium text-gray-600 dark:text-gray-400 mb-1">{t("users.fieldUsername")}</label>
# Fine

# Fix line 308: <input ... className="w-full px-3 py-2 bg-[#1a1a2e] border border-gray-700 rounded-md text-sm text-gray-800 dark:text-gray-200 focus:outline-none focus:border-blue-500" />
# Fine

# Fix line 316: </div> - fine

# Fix line 318: <label className="block text-sm font-medium text-gray-600 dark:text-gray-400 mb-1">{t("users.fieldDisplayName")}</label>
# Fine

# Fix line 325: </div> - fine

# Fix line 327: <label className="block text-sm font-medium text-gray-600 dark:text-gray-400 mb-1">{t("users.fieldPassword")}</label>
# Fine

# Fix line 335: </div> - fine

# Fix line 337: <label className="block text-sm font-medium text-gray-600 dark:text-gray-400 mb-1">{t("users.fieldRole")}</label>
# Fine

# Fix line 344: <option value="">{t("users.selectModule")}</option>
# Fine

# Fix line 346: <option key={r.id} value={r.id}>{r.name}</option>
# Fine

# Fix line 348: </select> - fine

# Fix line 349: </div> - fine

# Fix line 350: </div> - fine

# Fix line 354: </button> - fine

# Fix line 357: </button> - fine

# Fix line 358: </div> - fine

# Fix line 359: </div> - fine

# Fix line 360: </div> - fine

# Fix line 361: <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
old_line_361 = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
new_line_361 = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
content = content.replace(old_line_361, new_line_361)

# Fix line 363: <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100 mb-4">{t("users.modalEdit")}</h2>
# Fine

# Fix line 366: <label className="block text-sm font-medium text-gray-600 dark:text-gray-400 mb-1">{t("users.labelDisplayName")}</label>
# Fine

# Fix line 376: <input ... className="w-full px-3 py-2 bg-[#1a1a2e] border border-gray-700 rounded-md text-sm text-gray-800 dark:text-gray-200 focus:outline-none focus:border-blue-500" />
# Fine

# Fix line 382: </div> - fine

# Fix line 384: <label className="block text-sm font-medium text-gray-600 dark:text-gray-400 mb-1">{t("users.labelRole")}</label>
# Fine

# Fix line 385: <select ... className="w-full px-3 py-2 bg-[#1a1a2e] border border-gray-700 rounded-md text-sm text-gray-800 dark:text-gray-200 focus:outline-none focus:border-blue-500">
# Fine

# Fix line 390: <option key={r.id} value={r.id}>{r.name}</option>
# Fine

# Fix line 402: </select> - fine

# Fix line 403: </div> - fine

# Fix line 404: </div> - fine

# Fix line 409: </button> - fine

# Fix line 412: </button> - fine

# Fix line 413: </div> - fine

# Fix line 414: </div> - fine

# Fix line 415: </div> - fine

# Fix line 380: <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
old_line_380 = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
new_line_380 = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
content = content.replace(old_line_380, new_line_380)

# Fix line 382: <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-100 mb-4">{t("users.modalEdit")}</h2>
# Fine

# Fix line 385: <label className="block text-sm font-medium text-gray-600 dark:text-gray-400 mb-1">{t("users.labelDisplayName")}</label>
# Fine

# Fix line 386: <input ... className="w-full px-3 py-2 bg-[#1a1a2e] border border-gray-700 rounded-md text-sm text-gray-800 dark:text-gray-200 focus:outline-none focus:border-blue-500" />
# Fine

# Fix line 392: </div> - fine

# Fix line 394: <label className="block text-sm font-medium text-gray-600 dark:text-gray-400 mb-1">{t("users.labelRole")}</label>
# Fine

# Fix line 395: <select ... className="w-full px-3 py-2 bg-[#1a1a2e] border border-gray-700 rounded-md text-sm text-gray-800 dark:text-gray-200 focus:outline-none focus:border-blue-500">
# Fine

# Fix line 401: <option key={r.id} value={r.id}>{r.name}</option>
# Fine

# Fix line 403: </select> - fine

# Fix line 404: </div> - fine

# Fix line 405: </div> - fine

# Fix line 409: </button> - fine

# Fix line 412: </button> - fine

# Fix line 413: </div> - fine

# Fix line 414: </div> - fine

# Fix line 415: </div> - fine

# Fix line 361: <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
old_line_361 = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
new_line_361 = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
content = content.replace(old_line_361, new_line_361)

# Fix line 302: <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
old_line_302 = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
new_line_302 = '<div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">'
content = content.replace(old_line_302, new_line_302)

# Write the fixed content
with open(r'E:\my progam pharmacy\app\dashboard\users\page.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')