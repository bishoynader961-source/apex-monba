"use client";

import { useState, useEffect } from "react";
import { useI18n } from "@/components/I18nProvider";
import {
  listReceiptTemplates,
  createReceiptTemplate,
  updateReceiptTemplate,
  deleteReceiptTemplate,
} from "@/lib/api/receiptTemplates";
import type { ReceiptTemplateRead, ReceiptTemplateSection } from "@/types/contracts";
import { DashboardLayout } from "@/components/DashboardLayout";

const SECTION_TYPES = ["header", "separator", "text", "items_header", "items", "total", "footer"];
const ALIGNMENTS = ["left", "center", "right"];

const DEFAULT_SECTIONS: ReceiptTemplateSection[] = [
  { type: "header", content: "PHARMACY RECEIPT", align: "center", font_bold: true, visible: true },
  { type: "text", content: "{{receipt_number}}", align: "center", font_bold: false, visible: true },
  { type: "text", content: "DATE: {{date}}", align: "center", font_bold: false, visible: true },
  { type: "separator", content: "-", align: "center", font_bold: false, visible: true },
  { type: "text", content: "PATIENT: {{patient_name}}", align: "left", font_bold: false, visible: true },
  { type: "separator", content: "-", align: "center", font_bold: false, visible: true },
  { type: "items_header", content: "Item                    Price", align: "left", font_bold: false, visible: true },
  { type: "items", content: "", align: "left", font_bold: false, visible: true },
  { type: "separator", content: "-", align: "center", font_bold: false, visible: true },
  { type: "total", content: "TOTAL: {{total}}", align: "right", font_bold: true, visible: true },
  { type: "text", content: "PAYMENT: {{payment_method}}", align: "left", font_bold: false, visible: true },
  { type: "text", content: "CASHIER: {{cashier}}", align: "left", font_bold: false, visible: true },
  { type: "footer", content: "THANK YOU!", align: "center", font_bold: false, visible: true },
];

export default function ReceiptTemplatesPage() {
  const { t } = useI18n();
  const [templates, setTemplates] = useState<ReceiptTemplateRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<ReceiptTemplateRead | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  // Form state
  const [formName, setFormName] = useState("");
  const [formType, setFormType] = useState("receipt");
  const [formWidth, setFormWidth] = useState("42");
  const [formSections, setFormSections] = useState<ReceiptTemplateSection[]>(DEFAULT_SECTIONS);

  const load = async () => {
    setLoading(true);
    try { setTemplates(await listReceiptTemplates()); } catch { /* ignore */ }
    setLoading(false);
  };

  useEffect(() => { void load(); }, []);

  const resetForm = () => {
    setFormName(""); setFormType("receipt"); setFormWidth("42");
    setFormSections([...DEFAULT_SECTIONS]);
  };

  const handleSave = async () => {
    if (!formName.trim()) return;
    const payload = {
      name: formName, template_type: formType, paper_width: parseInt(formWidth) || 42,
      sections: formSections,
    };
    if (selected) {
      await updateReceiptTemplate(selected.id, payload);
    } else {
      await createReceiptTemplate(payload);
    }
    resetForm(); setShowCreate(false); setSelected(null);
    await load();
  };

  const handleEdit = (tpl: ReceiptTemplateRead) => {
    setSelected(tpl);
    setFormName(tpl.name); setFormType(tpl.template_type);
    setFormWidth(String(tpl.paper_width));
    setFormSections([...tpl.sections]);
    setShowCreate(true);
  };

  const handleDelete = async (id: number) => {
    await deleteReceiptTemplate(id);
    if (selected?.id === id) setSelected(null);
    await load();
  };

  const updateSection = (idx: number, field: keyof ReceiptTemplateSection, value: string | boolean) => {
    setFormSections((prev) => prev.map((s, i) => i === idx ? { ...s, [field]: value } : s));
  };

  const addSection = () => {
    setFormSections((prev) => [...prev, { type: "text", content: "", align: "left", font_bold: false, visible: true }]);
  };

  const removeSection = (idx: number) => {
    setFormSections((prev) => prev.filter((_, i) => i !== idx));
  };

  return (
    <DashboardLayout>
    <div style={{ padding: 24, maxWidth: 1000, margin: "0 auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <h1 style={{ fontSize: 22, fontWeight: 700 }}>{t("receiptTpl.title") ?? "Receipt Templates"}</h1>
          <button
            onClick={() => { resetForm(); setShowCreate(true); setSelected(null); }}
            style={{ padding: "8px 16px", background: "#7c3aed", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer" }}
          >
            + {t("receiptTpl.new") ?? "New Template"}
          </button>
        </div>
  );

      <div style={{ display: "flex", gap: 16 }}>
        {/* Template list */}
        <div style={{ width: 240, flexShrink: 0 }}>
          {loading ? (
            <div style={{ textAlign: "center", padding: 24, color: "#6b7280" }}>Loading…</div>
          ) : (
            <div style={{ display: "grid", gap: 6 }}>
              {templates.map((tpl) => (
                <button
                  key={tpl.id}
                  onClick={() => { setSelected(tpl); setShowCreate(false); }}
                  style={{
                    textAlign: "left", padding: "8px 10px", border: "1px solid #e5e7eb", borderRadius: 6,
                    background: selected?.id === tpl.id ? "#7c3aed15" : "transparent",
                    borderColor: selected?.id === tpl.id ? "#7c3aed" : "#e5e7eb",
                    cursor: "pointer",
                  }}
                >
                  <div style={{ fontSize: 13, fontWeight: 600, display: "flex", justifyContent: "space-between" }}>
                    <span>{tpl.name}</span>
                    {tpl.is_default ? <span style={{ color: "#f59e0b" }}>★</span> : null}
                  </div>
                  <div style={{ fontSize: 11, color: "#6b7280" }}>{tpl.template_type} · {tpl.paper_width}ch</div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Editor / Detail */}
        <div style={{ flex: 1 }}>
          {showCreate || selected ? (
            <div>
              <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>
                {selected ? `Edit: ${selected.name}` : "New Template"}
              </h3>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginBottom: 12 }}>
                <div>
                  <label style={{ fontSize: 12, fontWeight: 600, color: "#6b7280" }} htmlFor="page-field-1">Name *</label>
                  <input id="page-field-1" value={formName} onChange={(e) => setFormName(e.target.value)} style={{ width: "100%", padding: "6px 8px", border: "1px solid #d1d5db", borderRadius: 4, fontSize: 13 }} />
                </div>
                <div>
                  <label style={{ fontSize: 12, fontWeight: 600, color: "#6b7280" }} htmlFor="page-field-2">Type</label>
                  <select id="page-field-2" value={formType} onChange={(e) => setFormType(e.target.value)} style={{ width: "100%", padding: "6px 8px", border: "1px solid #d1d5db", borderRadius: 4, fontSize: 13 }}>
                    <option value="receipt">Receipt</option>
                    <option value="label">Label</option>
                  </select>
                </div>
                <div>
                  <label style={{ fontSize: 12, fontWeight: 600, color: "#6b7280" }} htmlFor="page-field-3">Paper Width (chars)</label>
                  <input id="page-field-3" value={formWidth} onChange={(e) => setFormWidth(e.target.value)} type="number" style={{ width: "100%", padding: "6px 8px", border: "1px solid #d1d5db", borderRadius: 4, fontSize: 13 }} />
                </div>
              </div>

              {/* Sections */}
              <div style={{ marginBottom: 12 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>Sections</span>
                  <button onClick={addSection} style={{ fontSize: 12, color: "#7c3aed", background: "none", border: "none", cursor: "pointer" }}>+ Add Section</button>
                </div>
                <div style={{ display: "grid", gap: 4 }}>
                  {formSections.map((sec, idx) => (
                    <div key={idx} style={{ display: "flex", gap: 6, alignItems: "center", padding: "4px 8px", background: "#f9fafb", borderRadius: 4 }}>
                      <select value={sec.type} onChange={(e) => updateSection(idx, "type", e.target.value)} style={{ width: 100, padding: "4px", fontSize: 12, border: "1px solid #d1d5db", borderRadius: 3 }}>
                        {SECTION_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                      </select>
                      <input value={sec.content} onChange={(e) => updateSection(idx, "content", e.target.value)} placeholder="Content / {{variable}}" style={{ flex: 1, padding: "4px 6px", fontSize: 12, border: "1px solid #d1d5db", borderRadius: 3 }} />
                      <select value={sec.align} onChange={(e) => updateSection(idx, "align", e.target.value)} style={{ width: 70, padding: "4px", fontSize: 12, border: "1px solid #d1d5db", borderRadius: 3 }}>
                        {ALIGNMENTS.map((a) => <option key={a} value={a}>{a}</option>)}
                      </select>
                      <label style={{ fontSize: 11, display: "flex", alignItems: "center", gap: 2 }}>
                        <input type="checkbox" checked={sec.font_bold ?? false} onChange={(e) => updateSection(idx, "font_bold", e.target.checked)} />B
                      </label>
                      <label style={{ fontSize: 11, display: "flex", alignItems: "center", gap: 2 }}>
                        <input type="checkbox" checked={sec.visible ?? true} onChange={(e) => updateSection(idx, "visible", e.target.checked)} />V
                      </label>
                      <button onClick={() => removeSection(idx)} style={{ fontSize: 12, color: "#dc2626", background: "none", border: "none", cursor: "pointer" }}>×</button>
                    </div>
                  ))}
                </div>
              </div>

              <div style={{ display: "flex", gap: 8 }}>
                <button onClick={() => void handleSave()} style={{ padding: "6px 16px", background: "#16a34a", color: "#fff", border: "none", borderRadius: 4, fontSize: 13 }}>
                  {selected ? "Update" : "Create"}
                </button>
                {selected && (
                  <button onClick={() => void handleDelete(selected.id)} style={{ padding: "6px 16px", background: "#dc2626", color: "#fff", border: "none", borderRadius: 4, fontSize: 13 }}>
                    Delete
                  </button>
                )}
                <button onClick={() => { resetForm(); setShowCreate(false); setSelected(null); }} style={{ padding: "6px 16px", border: "1px solid #d1d5db", borderRadius: 4, fontSize: 13 }}>
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div style={{ textAlign: "center", padding: 48, color: "#6b7280" }}>
              ← Select a template to edit
            </div>
          )}
        </div>
      </div>
    </div>
    </DashboardLayout>
  );
}
