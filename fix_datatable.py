import re
file_path = r'E:\my progam pharmacy\components\DataTable.tsx'
with open(file_path, 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('index % 2 === 1 ? "bg-white/5 dark:bg-white/5"', 'index % 2 === 1 ? "bg-black/5 dark:bg-white/5"')

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(text)
