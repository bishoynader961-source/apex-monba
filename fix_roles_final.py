with open(r'E:\my progam pharmacy\app\dashboard\roles\page.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix line 257: missing closing parenthesis for useMemo
old = '    }), [canWrite, t]);'
new = '    }))), [canWrite, t]);'
content = content.replace(old, new)

with open(r'E:\my progam pharmacy\app\dashboard\roles\page.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')