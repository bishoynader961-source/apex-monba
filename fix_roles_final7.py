with open(r'E:\my progam pharmacy\app\dashboard\roles\page.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the entire actions definition with a simpler version
old = '''  const actions = useMemo<{ header: string; render: (row: RoleRead) => React.ReactNode }>(
  (() => ({
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
    }))), [canWrite, t]);'''

new = '''  const actions = useMemo(() => ({
    header: "",
    render: (row: RoleRead) => {
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

content = content.replace(old, new)

with open(r'E:\my progam pharmacy\app\dashboard\roles\page.tsx', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')