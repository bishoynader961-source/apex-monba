"use client";

import { useState, useEffect } from "react";
import { useI18n } from "@/components/I18nProvider";
import {
  listDrugInteractions,
  createDrugInteraction,
  updateDrugInteraction,
  deleteDrugInteraction,
} from "@/lib/api/drugInteractions";
import type { DrugInteractionRead } from "@/types/contracts";
import { DashboardLayout } from "@/components/DashboardLayout";

const SEVERITIES = ["mild", "moderate", "severe", "contraindicated"];

export default function DrugInteractionsPage() {
  const { t } = useI18n();
  const [interactions, setInteractions] = useState<DrugInteractionRead[]>([]);
  const [loading, setLoading] = useState(true);

  // Form
  const [drugA, setDrugA] = useState("");
  const [drugB, setDrugB] = useState("");
  const [severity, setSeverity] = useState("moderate");
  const [description, setDescription] = useState("");
  const [recommendation, setRecommendation] = useState("");
  const [editId, setEditId] = useState<number | null>(null);

  const load = async () => {
    setLoading(true);
    try { setInteractions(await listDrugInteractions()); } catch { /* ignore */ }
    setLoading(false);
  };

  useEffect(() => { void load(); }, []);

  const resetForm = () => {
    setDrugA(""); setDrugB(""); setSeverity("moderate");
    setDescription(""); setRecommendation(""); setEditId(null);
  };

  const handleSave = async () => {
    if (!drugA.trim() || !drugB.trim()) return;
    if (editId) {
      await updateDrugInteraction(editId, { severity, description, recommendation });
    } else {
      await createDrugInteraction({ drug_a: drugA, drug_b: drugB, severity, description, recommendation });
    }
    resetForm(); await load();
  };

  const handleEdit = (ix: DrugInteractionRead) => {
    setEditId(ix.id); setDrugA(ix.drug_a); setDrugB(ix.drug_b);
    setSeverity(ix.severity); setDescription(ix.description); setRecommendation(ix.recommendation);
  };

  const handleDelete = async (id: number) => {
    await deleteDrugInteraction(id);
    if (editId === id) resetForm();
    await load();
  };

  return (
    <DashboardLayout>
    <div style={{ padding: 24, maxWidth: 900, margin: "0 auto" }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 16 }}>{t("interactions.title") ?? "Drug Interactions"}</h1>

        {/* Form */}
        <div style={{ border: "1px solid #e5e7eb", borderRadius: 8, padding: 16, marginBottom: 16 }}>
          <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 10 }}>{editId ? "Edit Interaction" : "Add Interaction"}</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>
            <div>
              <label style={{ fontSize: 12, color: "#6b7280" }} htmlFor="page-field-1">Drug A *</label>
              <input id="page-field-1" value={drugA} onChange={(e) => setDrugA(e.target.value)} placeholder="e.g. Warfarin" style={{ width: "100%", padding: "6px 8px", border: "1px solid #d1d5db", borderRadius: 4, fontSize: 13 }} />
            </div>
            <div>
              <label style={{ fontSize: 12, color: "#6b7280" }} htmlFor="page-field-2">Drug B *</label>
              <input id="page-field-2" value={drugB} onChange={(e) => setDrugB(e.target.value)} placeholder="e.g. Aspirin" style={{ width: "100%", padding: "6px 8px", border: "1px solid #d1d5db", borderRadius: 4, fontSize: 13 }} />
            </div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 8, marginBottom: 8 }}>
            <div>
              <label style={{ fontSize: 12, color: "#6b7280" }} htmlFor="page-field-3">Severity</label>
              <select id="page-field-3" value={severity} onChange={(e) => setSeverity(e.target.value)} style={{ width: "100%", padding: "6px 8px", border: "1px solid #d1d5db", borderRadius: 4, fontSize: 13 }}>
                {SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <label style={{ fontSize: 12, color: "#6b7280" }} htmlFor="page-field-4">Description</label>
              <input id="page-field-4" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Interaction description" style={{ width: "100%", padding: "6px 8px", border: "1px solid #d1d5db", borderRadius: 4, fontSize: 13 }} />
            </div>
          </div>
          <div style={{ marginBottom: 8 }}>
            <label style={{ fontSize: 12, color: "#6b7280" }} htmlFor="page-field-5">Recommendation</label>
            <input id="page-field-5" value={recommendation} onChange={(e) => setRecommendation(e.target.value)} placeholder="Clinical recommendation" style={{ width: "100%", padding: "6px 8px", border: "1px solid #d1d5db", borderRadius: 4, fontSize: 13 }} />
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={() => void handleSave()} style={{ padding: "6px 16px", background: "#16a34a", color: "#fff", border: "none", borderRadius: 4, fontSize: 13 }}>
              {editId ? "Update" : "Add"}
            </button>
            {editId && <button onClick={resetForm} style={{ padding: "6px 16px", border: "1px solid #d1d5db", borderRadius: 4, fontSize: 13 }}>Cancel</button>}
          </div>
        </div>
  );

      {/* List */}
      {loading ? (
        <div style={{ textAlign: "center", padding: 24, color: "#6b7280" }}>Loading…</div>
      ) : interactions.length === 0 ? (
        <div style={{ textAlign: "center", padding: 24, color: "#6b7280" }}>No interactions defined yet</div>
      ) : (
        <div style={{ display: "grid", gap: 6 }}>
          {interactions.map((ix) => (
            <div
              key={ix.id}
              style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "8px 12px", border: "1px solid #e5e7eb", borderRadius: 6,
              }}
            >
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>
                  {ix.drug_a} ↔ {ix.drug_b}
                </div>
                <div style={{ fontSize: 12, color: "#6b7280" }}>
                  {ix.description}
                  {ix.recommendation ? ` — ${ix.recommendation}` : ""}
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span style={{
                  fontSize: 11, fontWeight: 700, textTransform: "uppercase",
                  color: ix.severity === "contraindicated" ? "#dc2626" : ix.severity === "severe" ? "#ea580c" : ix.severity === "moderate" ? "#d97706" : "#16a34a",
                  padding: "2px 8px", borderRadius: 4,
                  background: (ix.severity === "contraindicated" || ix.severity === "severe") ? "#fef2f2" : "#fefce8",
                }}>
                  {ix.severity}
                </span>
                <button onClick={() => handleEdit(ix)} style={{ fontSize: 12, color: "#7c3aed", background: "none", border: "none", cursor: "pointer" }}>Edit</button>
                <button onClick={() => void handleDelete(ix.id)} style={{ fontSize: 12, color: "#dc2626", background: "none", border: "none", cursor: "pointer" }}>Delete</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
    </DashboardLayout>
  );
}
