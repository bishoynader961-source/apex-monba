with open(r'E:\my progam pharmacy\app\dashboard\roles\page.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix line 243: useMemo should have () not ((())
old = 'const actions = useMemo<{ header: string; render: (row: RoleRead) => React.ReactNode }>((() => ({'
new = 'const actions = useMemo<{ header: string; render: (row: RoleRead) => React.ReactNode }>(() => ({'
content = content.replace(old, new)

# Fix line 257: remove one extra closing paren
old = '    }))), [canWrite, t]);'
new = '    })), [canWrite, t]);'
content = content.replace(old, new)

with open(r'E:\my progam pharmacy\app\dashboard\roles\page.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')