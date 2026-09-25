with open(r'E:\my progam pharmacy\app\dashboard\roles\page.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the actions block with a simpler pattern - define actions outside useMemo
old = '''  const actions = useMemo(() => ({
    header: "",
    render: (row) => {
      if (!canWrite || row.is_system) return null;
      return (
        <div className="flex gap-1">
          <button onClick={(e) => { e.stopPropagation(); setEditOpen(true); setSelectedRole(row); }} className="text-xs text-blue-400 hover:text-blue-300">
            {t("roles.edit")}
          </button>
          <button onClick={(e) => { e.stopPropagation(); void handleDeleteRole(row); }} className="text-xs text-red-400 hover:text-red-300">
            {t("roles.delete")}
          </button>
        </div>
      );
    }
  }), [canWrite, t]);'''

new = '''  const actions = {
    header: "",
    render: (row) => {
      if (!canWrite || row.is_system) return null;
      return (
        <div className="flex gap-1">
          <button onClick={(e) => { e.stopPropagation(); setEditOpen(true); setSelectedRole(row); }} className="text-xs text-blue-400 hover:text-blue-300">
            {t("roles.edit")}
          </button>
          <button onClick={(e) => { e.stopPropagation(); void handleDeleteRole(row); }} className="text-xs text-red-400 hover:text-red-300">
            {t("roles.delete")}
          </button>
        </div>
      );
    }
  };'''

content = content.replace(old, new)

with open(r'E:\my progam pharmacy\app\dashboard\roles\page.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')