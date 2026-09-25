"use client";

import { useCallback, useEffect, useState } from "react";
import {
  createAllergyRecord,
  createClinicalNote,
  deleteAllergyRecord,
  deleteClinicalNote,
  getClinicalReview,
  listAllergyRecords,
  listClinicalNotes,
} from "@/lib/api/clinical";
import type {
  AllergyRecordRead,
  ClinicalNoteRead,
  ClinicalReviewSummary,
} from "@/types/contracts";

type Tab = "notes" | "allergies" | "attachments" | "review";

const SEVERITY_COLORS: Record<string, string> = {
  mild: "bg-green-900/30 text-green-400 border-green-600/40",
  moderate: "bg-yellow-900/30 text-yellow-400 border-yellow-600/40",
  severe: "bg-red-900/30 text-red-400 border-red-600/40",
  "life-threatening": "bg-red-950/50 text-red-300 border-red-500/50",
  unknown: "bg-gray-800/50 text-gray-400 border-gray-600/40",
};

const TAB_DEFS: { key: Tab; label: string; icon: string }[] = [
  { key: "notes", label: "Clinical Notes", icon: "📝" },
  { key: "allergies", label: "Allergies", icon: "⚠️" },
  { key: "attachments", label: "Attachments", icon: "📎" },
  { key: "review", label: "Review Summary", icon: "✓" },
];

interface Props {
  patientId: number;
}

export default function ClinicalWorkflowPanel({ patientId }: Props) {
  const [tab, setTab] = useState<Tab>("notes");
  const [notes, setNotes] = useState<ClinicalNoteRead[]>([]);
  const [allergies, setAllergies] = useState<AllergyRecordRead[]>([]);
  const [review, setReview] = useState<ClinicalReviewSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [noteText, setNoteText] = useState("");
  const [noteCategory, setNoteCategory] = useState<string>("general");
  const [allergyDrug, setAllergyDrug] = useState("");
  const [allergyReaction, setAllergyReaction] = useState("");
  const [allergySeverity, setAllergySeverity] = useState<string>("unknown");

  const loadNotes = useCallback(async () => {
    try {
      const data = await listClinicalNotes(patientId);
      setNotes(data);
    } catch { /* empty */ }
  }, [patientId]);

  const loadAllergies = useCallback(async () => {
    try {
      const data = await listAllergyRecords(patientId);
      setAllergies(data);
    } catch { /* empty */ }
  }, [patientId]);

  const loadReview = useCallback(async () => {
    try {
      const data = await getClinicalReview(patientId);
      setReview(data);
    } catch { /* empty */ }
  }, [patientId]);

  useEffect(() => {
    if (!patientId) return;
    setLoading(true);
    Promise.all([loadNotes(), loadAllergies(), loadReview()]).finally(() => setLoading(false));
  }, [patientId, loadNotes, loadAllergies, loadReview]);

  const handleAddNote = async () => {
    if (!noteText.trim()) return;
    try {
      await createClinicalNote({
        patient_id: patientId,
        content: noteText.trim(),
        category: noteCategory as "general" | "allergy" | "interaction" | "assessment",
      });
      setNoteText("");
      await loadNotes();
    } catch { /* empty */ }
  };

  const handleDeleteNote = async (id: number) => {
    await deleteClinicalNote(id);
    await loadNotes();
  };

  const handleAddAllergy = async () => {
    if (!allergyDrug.trim()) return;
    try {
      await createAllergyRecord({
        patient_id: patientId,
        drug_name: allergyDrug.trim(),
        reaction: allergyReaction.trim(),
        severity: allergySeverity as "mild" | "moderate" | "severe" | "life-threatening" | "unknown",
      });
      setAllergyDrug("");
      setAllergyReaction("");
      setAllergySeverity("unknown");
      await loadAllergies();
      await loadReview();
    } catch { /* empty */ }
  };

  const handleDeleteAllergy = async (id: number) => {
    await deleteAllergyRecord(id);
    await loadAllergies();
    await loadReview();
  };

  if (!patientId) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500 text-sm">
        Select a patient first to view clinical data.
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* Tab bar */}
      <div className="flex border-b border-gray-700">
        {TAB_DEFS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2.5 text-sm font-medium transition-colors ${
              tab === t.key
                ? "text-white border-b-2 border-blue-500 bg-white/5"
                : "text-gray-400 hover:text-gray-200 hover:bg-white/5"
            }`}
          >
            <span className="mr-1.5">{t.icon}</span>
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto p-4">
        {loading && (
          <div className="text-center text-gray-500 text-sm py-8">Loading clinical data...</div>
        )}

        {/* ── Notes Tab ── */}
        {!loading && tab === "notes" && (
          <div className="space-y-4">
            {/* Add note form */}
            <div className="rounded-lg bg-white/5 border border-white/10 p-4 space-y-3">
              <div className="flex gap-2">
                <select
                  value={noteCategory}
                  onChange={(e) => setNoteCategory(e.target.value)}
                  className="rounded bg-black/40 border border-white/10 text-gray-700 dark:text-gray-300 text-sm px-3 py-2"
                >
                  <option value="general">General</option>
                  <option value="allergy">Allergy</option>
                  <option value="interaction">Interaction</option>
                  <option value="assessment">Assessment</option>
                </select>
                <input
                  type="text"
                  placeholder="Type a clinical note..."
                  value={noteText}
                  onChange={(e) => setNoteText(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleAddNote()}
                  className="flex-1 rounded bg-black/40 border border-white/10 text-gray-900 dark:text-white text-sm px-3 py-2 placeholder-gray-500 focus:outline-none focus:border-blue-500"
                />
                <button
                  onClick={handleAddNote}
                  disabled={!noteText.trim()}
                  className="px-4 py-2 rounded bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  Add
                </button>
              </div>
            </div>

            {/* Notes list */}
            {notes.length === 0 ? (
              <div className="text-center text-gray-500 text-sm py-8">No clinical notes yet.</div>
            ) : (
              <div className="space-y-2">
                {notes.map((n) => (
                  <div key={n.id} className="rounded-lg bg-white/5 border border-white/10 p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-[10px] font-medium uppercase tracking-wider text-gray-500">
                            {n.category}
                          </span>
                          <span className="text-[10px] text-gray-600">{new Date(n.created_at).toLocaleString()}</span>
                        </div>
                        <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">{n.content}</p>
                      </div>
                      <button
                        onClick={() => handleDeleteNote(n.id)}
                        className="text-gray-600 hover:text-red-400 text-xs shrink-0 transition-colors"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── Allergies Tab ── */}
        {!loading && tab === "allergies" && (
          <div className="space-y-4">
            {/* Add allergy form */}
            <div className="rounded-lg bg-white/5 border border-white/10 p-4 space-y-3">
              <div className="grid grid-cols-3 gap-2">
                <input
                  type="text"
                  placeholder="Drug name"
                  value={allergyDrug}
                  onChange={(e) => setAllergyDrug(e.target.value)}
                  className="rounded bg-black/40 border border-white/10 text-gray-900 dark:text-white text-sm px-3 py-2 placeholder-gray-500 focus:outline-none focus:border-blue-500"
                />
                <input
                  type="text"
                  placeholder="Reaction (optional)"
                  value={allergyReaction}
                  onChange={(e) => setAllergyReaction(e.target.value)}
                  className="rounded bg-black/40 border border-white/10 text-gray-900 dark:text-white text-sm px-3 py-2 placeholder-gray-500 focus:outline-none focus:border-blue-500"
                />
                <select
                  value={allergySeverity}
                  onChange={(e) => setAllergySeverity(e.target.value)}
                  className="rounded bg-black/40 border border-white/10 text-gray-700 dark:text-gray-300 text-sm px-3 py-2"
                >
                  <option value="unknown">Unknown</option>
                  <option value="mild">Mild</option>
                  <option value="moderate">Moderate</option>
                  <option value="severe">Severe</option>
                  <option value="life-threatening">Life-Threatening</option>
                </select>
              </div>
              <button
                onClick={handleAddAllergy}
                disabled={!allergyDrug.trim()}
                className="px-4 py-2 rounded bg-red-600 hover:bg-red-500 text-white text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Add Allergy
              </button>
            </div>

            {/* Allergies list */}
            {allergies.length === 0 ? (
              <div className="text-center text-gray-500 text-sm py-8">No allergy records on file.</div>
            ) : (
              <div className="space-y-2">
                {allergies.map((a) => (
                  <div key={a.id} className="rounded-lg bg-white/5 border border-white/10 p-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-gray-900 dark:text-white">{a.drug_name}</span>
                          <span className={`text-[10px] font-medium uppercase tracking-wider px-2 py-0.5 rounded border ${SEVERITY_COLORS[a.severity] || SEVERITY_COLORS.unknown}`}>
                            {a.severity}
                          </span>
                        </div>
                        {a.reaction && (
                          <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">Reaction: {a.reaction}</p>
                        )}
                        <span className="text-[10px] text-gray-600">{new Date(a.created_at).toLocaleString()}</span>
                      </div>
                      <button
                        onClick={() => handleDeleteAllergy(a.id)}
                        className="text-gray-600 hover:text-red-400 text-xs shrink-0 transition-colors"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── Attachments Tab ── */}
        {!loading && tab === "attachments" && (
          <div className="space-y-4">
            <div className="rounded-lg bg-white/5 border border-white/10 p-4">
              <p className="text-sm text-gray-600 dark:text-gray-400">
                File attachments can be uploaded when processing a prescription. Attachments are linked to
                the patient&apos;s clinical record for reference during future dispensing.
              </p>
            </div>
            <div className="text-center text-gray-500 text-sm py-8">
              Attachments are managed during the dispense workflow.
            </div>
          </div>
        )}

        {/* ── Review Tab ── */}
        {!loading && tab === "review" && review && (
          <div className="space-y-4">
            <div className="rounded-lg bg-white/5 border border-white/10 p-4">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">Patient: {review.patient_name}</h3>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-gray-500">Active Allergies:</span>
                  <span className="ml-2 text-gray-900 dark:text-white font-medium">{review.allergies.length}</span>
                </div>
                <div>
                  <span className="text-gray-500">Clinical Notes:</span>
                  <span className="ml-2 text-gray-900 dark:text-white font-medium">{review.recent_notes.length}</span>
                </div>
                <div>
                  <span className="text-gray-500">Active Prescriptions:</span>
                  <span className="ml-2 text-gray-900 dark:text-white font-medium">{review.active_prescriptions}</span>
                </div>
                <div>
                  <span className="text-gray-500">Pending Refills:</span>
                  <span className="ml-2 text-gray-900 dark:text-white font-medium">{review.pending_refills}</span>
                </div>
              </div>
            </div>

            {/* Allergy summary */}
            {review.allergies.length > 0 && (
              <div className="rounded-lg bg-white/5 border border-white/10 p-4">
                <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">Allergies</h4>
                <div className="space-y-1">
                  {review.allergies.map((a) => (
                    <div key={a.id} className="flex items-center gap-2 text-sm">
                      <span className={`text-[10px] font-medium uppercase px-1.5 py-0.5 rounded border ${SEVERITY_COLORS[a.severity] || SEVERITY_COLORS.unknown}`}>
                        {a.severity}
                      </span>
                      <span className="text-gray-900 dark:text-white">{a.drug_name}</span>
                      {a.reaction && <span className="text-gray-600 dark:text-gray-400">— {a.reaction}</span>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Recent notes */}
            {review.recent_notes.length > 0 && (
              <div className="rounded-lg bg-white/5 border border-white/10 p-4">
                <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">Recent Notes</h4>
                <div className="space-y-2">
                  {review.recent_notes.slice(0, 5).map((n) => (
                    <div key={n.id} className="text-sm">
                      <span className="text-[10px] text-gray-500 uppercase">{n.category}</span>
                      <p className="text-gray-700 dark:text-gray-300">{n.content}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
