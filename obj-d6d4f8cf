"use client";

import { useState, useEffect } from "react";
import { useI18n } from "@/components/I18nProvider";
import {
  listQuickSigTemplates,
  createQuickSigTemplate,
  updateQuickSigTemplate,
  deleteQuickSigTemplate,
  toggleQuickSigFavorite,
} from "@/lib/api/quickSig";
import type { QuickSigTemplateRead } from "@/types/contracts";
import { DashboardLayout } from "@/components/DashboardLayout";

const ROUTES = ["Oral", "Topical", "Inhalation", "Injection", "Ophthalmic", "Rectal", "Sublingual", "Transdermal"];
const FREQUENCIES = ["QD", "BID", "TID", "QID", "QHS", "PRN", "Q4H", "Q6H", "Q8H", "Q12H"];
const DURATIONS = ["7 days", "10 days", "14 days", "21 days", "30 days", "60 days", "90 days", "Ongoing"];

export default function QuickSigPage() {
  const { t } = useI18n();
  const [templates, setTemplates] = useState<QuickSigTemplateRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<QuickSigTemplateRead | null>(null);
  const [favoritesOnly, setFavoritesOnly] = useState(false);

  // Form state
  const [formName, setFormName] = useState("");
  const [formDrug, setFormDrug] = useState("");
  const [formDose, setFormDose] = useState("");
  const [formRoute, setFormRoute] = useState("Oral");
  const [formFreq, setFormFreq] = useState("BID");
  const [formDuration, setFormDuration] = useState("7 days");
  const [formDirections, setFormDirections] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const data = await listQuickSigTemplates({ favorites_only: favoritesOnly, q: search });
      setTemplates(data);
    } catch { /* ignore */ }
    setLoading(false);
  };

  useEffect(() => { void load(); }, [favoritesOnly, search]);

  const resetForm = () => {
    setFormName(""); setFormDrug(""); setFormDose("");
    setFormRoute("Oral"); setFormFreq("BID"); setFormDuration("7 days"); setFormDirections("");
    setEditing(null);
  };

  const handleSave = async () => {
    if (!formName.trim()) return;
    const payload = {
      name: formName, drug_name: formDrug, dose: formDose,
      route: formRoute, frequency: formFreq, duration: formDuration,
      directions: formDirections || `${formDose} ${formRoute} ${formFreq} for ${formDuration}`,
    };
    if (editing) {
      await updateQuickSigTemplate(editing.id, payload);
    } else {
      await createQuickSigTemplate(payload);
    }
    resetForm();
    setShowForm(false);
    await load();
  };

  const handleEdit = (t: QuickSigTemplateRead) => {
    setEditing(t);
    setFormName(t.name); setFormDrug(t.drug_name); setFormDose(t.dose);
    setFormRoute(t.route); setFormFreq(t.frequency); setFormDuration(t.duration);
    setFormDirections(t.directions);
    setShowForm(true);
  };

  const handleDelete = async (id: number) => {
    await deleteQuickSigTemplate(id);
    await load();
  };

  const handleFavorite = async (id: number) => {
    await toggleQuickSigFavorite(id);
    await load();
  };

  return (
    <DashboardLayout>
    <div style={{ padding: 24, maxWidth: 960, margin: "0 auto" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <h1 style={{ fontSize: 22, fontWeight: 700 }}>{t("quickSig.title") ?? "Quick-SIG Templates"}</h1>
          <button
            onClick={() => { resetForm(); setShowForm(true); }}
            style={{ padding: "8px 16px", background: "#7c3aed", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer" }}
          >
            + {t("quickSig.new") ?? "New Template"}
          </button>
        </div>
  );

      {/* Search + Filter */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t("quickSig.search") ?? "Search templates…"}
          style={{ flex: 1, padding: "8px 12px", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 14 }}
        />
        <button
          onClick={() => setFavoritesOnly(!favoritesOnly)}
          style={{
            padding: "8px 12px", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 14,
            background: favoritesOnly ? "#7c3aed15" : "transparent",
            color: favoritesOnly ? "#7c3aed" : "#6b7280",
          }}
        >
          {favoritesOnly ? "★ Favorites" : "☆ All"}
        </button>
      </div>

      {/* Form */}
      {showForm && (
        <div style={{ background: "#f9fafb", borderRadius: 8, padding: 16, marginBottom: 16, border: "1px solid #e5e7eb" }}>
          <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 12 }}>{editing ? "Edit Template" : "New Template"}</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, color: "#6b7280" }} htmlFor="page-field-1">Name *</label>
              <input id="page-field-1" value={formName} onChange={(e) => setFormName(e.target.value)} placeholder="e.g. Amoxicillin BID" style={{ width: "100%", padding: "6px 8px", border: "1px solid #d1d5db", borderRadius: 4, fontSize: 13 }} />
            </div>
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, color: "#6b7280" }} htmlFor="page-field-2">Drug Name</label>
              <input id="page-field-2" value={formDrug} onChange={(e) => setFormDrug(e.target.value)} placeholder="e.g. Amoxicillin" style={{ width: "100%", padding: "6px 8px", border: "1px solid #d1d5db", borderRadius: 4, fontSize: 13 }} />
            </div>
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, color: "#6b7280" }} htmlFor="page-field-3">Dose</label>
              <input id="page-field-3" value={formDose} onChange={(e) => setFormDose(e.target.value)} placeholder="e.g. 500mg" style={{ width: "100%", padding: "6px 8px", border: "1px solid #d1d5db", borderRadius: 4, fontSize: 13 }} />
            </div>
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, color: "#6b7280" }} htmlFor="page-field-4">Route</label>
              <select id="page-field-4" value={formRoute} onChange={(e) => setFormRoute(e.target.value)} style={{ width: "100%", padding: "6px 8px", border: "1px solid #d1d5db", borderRadius: 4, fontSize: 13 }}>
                {ROUTES.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, color: "#6b7280" }} htmlFor="page-field-5">Frequency</label>
              <select id="page-field-5" value={formFreq} onChange={(e) => setFormFreq(e.target.value)} style={{ width: "100%", padding: "6px 8px", border: "1px solid #d1d5db", borderRadius: 4, fontSize: 13 }}>
                {FREQUENCIES.map((f) => <option key={f} value={f}>{f}</option>)}
              </select>
            </div>
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, color: "#6b7280" }} htmlFor="page-field-6">Duration</label>
              <select id="page-field-6" value={formDuration} onChange={(e) => setFormDuration(e.target.value)} style={{ width: "100%", padding: "6px 8px", border: "1px solid #d1d5db", borderRadius: 4, fontSize: 13 }}>
                {DURATIONS.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            </div>
          </div>
          <div style={{ marginTop: 8 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: "#6b7280" }} htmlFor="page-field-7">Custom Directions (optional)</label>
            <textarea id="page-field-7" value={formDirections} onChange={(e) => setFormDirections(e.target.value)} placeholder="Override auto-generated directions" rows={2} style={{ width: "100%", padding: "6px 8px", border: "1px solid #d1d5db", borderRadius: 4, fontSize: 13, resize: "vertical" }} />
          </div>
          <div style={{ marginTop: 8, padding: "6px 8px", background: "#eff6ff", borderRadius: 4, fontSize: 12, color: "#1e40af" }}>
            Preview: {formDose || "…"} {formRoute} {formFreq} for {formDuration}
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <button onClick={() => void handleSave()} style={{ padding: "6px 16px", background: "#16a34a", color: "#fff", border: "none", borderRadius: 4, fontSize: 13, cursor: "pointer" }}>
              {editing ? "Update" : "Create"}
            </button>
            <button onClick={() => { resetForm(); setShowForm(false); }} style={{ padding: "6px 16px", border: "1px solid #d1d5db", borderRadius: 4, fontSize: 13, cursor: "pointer" }}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* List */}
      {loading ? (
        <div style={{ textAlign: "center", padding: 24, color: "#6b7280" }}>Loading…</div>
      ) : templates.length === 0 ? (
        <div style={{ textAlign: "center", padding: 24, color: "#6b7280" }}>
          {t("quickSig.empty") ?? "No templates found. Create one to get started."}
        </div>
      ) : (
        <div style={{ display: "grid", gap: 8 }}>
          {templates.map((tpl) => (
            <div key={tpl.id} style={{ display: "flex", alignItems: "center", padding: "10px 12px", border: "1px solid #e5e7eb", borderRadius: 6, gap: 12 }}>
              <button onClick={() => void handleFavorite(tpl.id)} style={{ fontSize: 18, cursor: "pointer", color: tpl.is_favorite ? "#f59e0b" : "#d1d5db", background: "none", border: "none" }}>
                {tpl.is_favorite ? "★" : "☆"}
              </button>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 14, fontWeight: 600 }}>
                  {tpl.name}
                  {tpl.usage_count > 0 && (
                    <span style={{ fontSize: 11, color: "#6b7280", fontWeight: 400, marginLeft: 6 }}>
                      ×{tpl.usage_count}
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 12, color: "#6b7280" }}>
                  {tpl.dose} {tpl.route} {tpl.frequency} for {tpl.duration}
                </div>
                {tpl.directions && <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 2 }}>{tpl.directions}</div>}
              </div>
              <button onClick={() => handleEdit(tpl)} style={{ fontSize: 12, color: "#7c3aed", cursor: "pointer", background: "none", border: "none" }}>Edit</button>
              <button onClick={() => void handleDelete(tpl.id)} style={{ fontSize: 12, color: "#dc2626", cursor: "pointer", background: "none", border: "none" }}>Delete</button>
            </div>
          ))}
        </div>
      )}
    </div>
    </DashboardLayout>
  );
}
