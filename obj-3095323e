import re
file_path = r'E:\my progam pharmacy\app\dashboard\label-engine\page.tsx'
with open(file_path, 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('defaultPath: `label-.png`,', 'defaultPath: `label-${tplName || "export"}.png`,')
text = text.replace('link.download = `label-.png`;', 'link.download = `label-${tplName || "export"}.png`;')

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(text)
