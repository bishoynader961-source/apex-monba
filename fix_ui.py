import re

page_path = r'E:\my progam pharmacy\app\patients\page.tsx'
with open(page_path, 'r', encoding='utf-8') as f:
    text = f.read()

new_custom_fields_tab = '''function CustomFieldsTab({ patient, canWrite, onUpdate }: {
  patient: PatientRead;
  canWrite: boolean;
  onUpdate: (patch: PatientUpdate) => Promise<void>;
}) {
  let fields: Array<{ field_name: string; field_value: string | null }> = [];
  try {
    if (patient.custom_fields) {
      fields = JSON.parse(patient.custom_fields);
      if (!Array.isArray(fields)) fields = [];
    }
  } catch (e) {}

  const [newName, setNewName] = useState("");
  const [newValue, setNewValue] = useState("");
  const [saving, setSaving] = useState(false);

  const handleAdd = async () => {
    if (!newName.trim()) return;
    setSaving(true);
    const newField = { field_name: newName.trim(), field_value: newValue || null };
    const updated = [...fields.filter(f => f.field_name !== newField.field_name), newField];
    try {
      await onUpdate({ custom_fields: JSON.stringify(updated) });
      setNewName("");
      setNewValue("");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (fieldName: string) => {
    const updated = fields.filter(f => f.field_name !== fieldName);
    await onUpdate({ custom_fields: JSON.stringify(updated) });
  };

  return (
    <div>
      <p style={{ fontSize: 12, color: "#6b7280", marginBottom: 12 }}>
        Site-specific custom fields for this patient (e.g. loyalty number, referral source).
      </p>
      {fields.length > 0 ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
          {fields.map((f) => (
            <div key={f.field_name} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 10px", border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg-input)" }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: "var(--fg)", minWidth: 120 }}>{f.field_name}</span>
              <span style={{ fontSize: 12, color: "var(--fg-muted)", flex: 1 }}>{f.field_value ?? "—"}</span>
              {canWrite && (
                <button onClick={() => void handleDelete(f.field_name)} style={{ fontSize: 11, color: "#dc2626", cursor: "pointer", border: "none", background: "none" }}>Remove</button>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p style={{ fontSize: 12, color: "#6b7280", marginBottom: 12 }}>No custom fields yet.</p>
      )}
      {canWrite && (
        <div style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 4, flex: 1 }}>
            <label style={{ fontSize: 11, fontWeight: 600, color: "#6b7280" }}>Field Name</label>
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="e.g. loyalty_number"
              style={{ padding: "6px 10px", fontSize: 12, border: "1px solid var(--border)", borderRadius: 4, background: "var(--bg-input)", color: "var(--fg)" }}
            />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4, flex: 1 }}>
            <label style={{ fontSize: 11, fontWeight: 600, color: "#6b7280" }}>Value</label>
            <input
              value={newValue}
              onChange={(e) => setNewValue(e.target.value)}
              placeholder="Optional"
              style={{ padding: "6px 10px", fontSize: 12, border: "1px solid var(--border)", borderRadius: 4, background: "var(--bg-input)", color: "var(--fg)" }}
            />
          </div>
          <button
            onClick={() => void handleAdd()}
            disabled={saving || !newName.trim()}
            style={{ padding: "6px 14px", fontSize: 12, background: saving || !newName.trim() ? "#9ca3af" : "#16a34a", color: "white", border: "none", borderRadius: 4, cursor: saving || !newName.trim() ? "default" : "pointer", fontWeight: 500 }}
          >
            {saving ? "..." : "Add"}
          </button>
        </div>
      )}
    </div>
  );
}'''

# Replace the old CustomFieldsTab function
# It starts at unction CustomFieldsTab({ and ends just before // ── Main page
text = re.sub(
    r'function CustomFieldsTab\(\{ patient, canWrite \}: \{[\s\S]*?(?=// ─── Main page|// ── Main page)',
    new_custom_fields_tab + '\n\n',
    text
)

# Update the rendering in PatientsPage
text = text.replace(
    '{activeTab === "Custom Fields" && <CustomFieldsTab patient={selected} canWrite={canWrite} />}',
    '{activeTab === "Custom Fields" && <CustomFieldsTab patient={selected} canWrite={canWrite} onUpdate={handleUpdate} />}'
)

with open(page_path, 'w', encoding='utf-8') as f:
    f.write(text)
