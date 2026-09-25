import re
file_path = r'E:\my progam pharmacy\src-tauri\src\lib.rs'
with open(file_path, 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('if let Some(win) = app.get_webview_window("label-engine") {', 'if let Some(win) = app.get_webview_window("label-engine-preview") {')

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(text)
