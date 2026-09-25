with open(r'E:\my progam pharmacy\app\dashboard\roles\page.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the specific block
old = '''    })),
  [canWrite, t]);'''

new = '''  }, [canWrite, t]);'''

content = content.replace(old, new)

with open(r'E:\my progam pharmacy\app\dashboard\roles\page.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')