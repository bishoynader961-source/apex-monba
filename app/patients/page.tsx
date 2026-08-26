"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuthStore, useCan } from "@/stores/authStore";
import { usePatients } from "@/hooks/usePatients";
import type {
  DispenseRead,
  InsurancePlanRead,
  MembersGroupRead,
  PatientHistoryEntry,
  PatientRead,
  PatientUpdate,
} from "@/types/contracts";

import * as patientsApi from "@/lib/api/patients";
import * as insuranceApi from "@/lib/api/insurance";
import * as dispenseApi from "@/lib/api/dispense";
import { parseMoney, formatMoney } from "@/lib/decimalCurrency";

const TABS = ["General", "Insurance Plan", "Members Group", "Rx / Refill", "Patient History", "Billing Info", "Comments"] as const;
type TabName = (typeof TABS)[number];

// ── Sub-components (co-located, no micro-files) ────────────────────────────

function GeneralTab({ patient, onUpdate, canWrite }: {
  patient: PatientRead;
  onUpdate: (patch: PatientUpdate) => Promise<void>;
  canWrite: boolean;
}) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px 16px" }}>
      <Field label="Full Name" value={patient.name} canWrite={canWrite} onChange={(v) => onUpdate({ name: v })} />
      <Field label="DOB" value={patient.dob} canWrite={canWrite} onChange={(v) => onUpdate({ dob: v })} />
      <Field label="Address" value={patient.address} canWrite={canWrite} onChange={(v) => onUpdate({ address: v })} fullWidth />
      <Field label="Driver License" value={patient.driver_license} canWrite={canWrite} onChange={(v) => onUpdate({ driver_license: v })} />
      <Field label="Sex" value={patient.sex} canWrite={canWrite} onChange={(v) => onUpdate({ sex: v })} />
      <Field label="Employer ID" value={patient.employer_id} canWrite={canWrite} onChange={(v) => onUpdate({ employer_id: v })} />
      <Field label="Contact Phone" value={patient.contact_phone} canWrite={canWrite} onChange={(v) => onUpdate({ contact_phone: v })} />
      <Field label="Email" value={patient.email} canWrite={canWrite} onChange={(v) => onUpdate({ email: v })} />
      <div style={{ gridColumn: "1 / -1" }}>
        <Field label="Patient Allergies" value={patient.patient_allergies} canWrite={canWrite} onChange={(v) => onUpdate({ patient_allergies: v })} placeholder="e.g. Penicillin, Sulfa" />
      </div>
    </div>
  );
}

function Field({ label, value, canWrite, onChange, placeholder, fullWidth }: {
  label: string;
  value: string;
  canWrite: boolean;
  onChange: (v: string) => void;
  placeholder?: string;
  fullWidth?: boolean;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <label style={{ fontSize: 12, fontWeight: 600, color: "#6b7280" }}>{label}</label>
      {canWrite ? (
        <input
          defaultValue={value}
          placeholder={placeholder}
          onBlur={(e) => { if (e.target.value !== value) onChange(e.target.value); }}
          style={{
            padding: "6px 8px",
            fontSize: 13,
            border: "1px solid #d1d5db",
            borderRadius: 6,
            width: fullWidth ? "100%" : "auto",
          }}
        />
      ) : (
        <span style={{ fontSize: 13, padding: "6px 8px", color: "#374151" }}>{value || <span style={{ color: "#9ca3bf" }}>—</span>}</span>
      )}
    </div>
  );
}

function InsuranceTab({ patient, onUpdate, canWrite }: {
  patient: PatientRead;
  onUpdate: (patch: PatientUpdate) => Promise<void>;
  canWrite: boolean;
}) {
  const [plans, setPlans] = useState<InsurancePlanRead[]>([]);
  const [validation, setValidation] = useState<{ active: boolean; copay: string; coverage: number } | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    void insuranceApi.listPlans().then(setPlans).catch(() => {});
  }, []);

  const handleValidate = async (planId: number) => {
    setLoading(true);
    try {
      const r = await insuranceApi.validatePlan({ plan_id: planId });
      setValidation({ active: r.active, copay: r.copay_amount, coverage: r.coverage_percentage });
    } catch (err: unknown) {
      setValidation(null);
    } finally {
      setLoading(false);
    }
  };

  const handleBind = (planId: number) => onUpdate({ insurance_plan_id: planId });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
        <Field label="Insurance Provider" value={patient.insurance_provider} canWrite={canWrite} onChange={(v) => onUpdate({ insurance_provider: v })} />
        <Field label="Policy #" value={patient.policy_number} canWrite={canWrite} onChange={(v) => onUpdate({ policy_number: v })} />
        <Field label="Group #" value={patient.group_number} canWrite={canWrite} onChange={(v) => onUpdate({ group_number: v })} />
      </div>

      <div style={{ paddingTop: 12, borderTop: "1px solid #e5e7eb" }}>
        <p style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Insurance Plans</p>
        {plans.map((p) => (
          <div key={p.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: "1px solid #f3f4f6" }}>
            <div>
              <strong style={{ fontSize: 13 }}>{p.plan_name}</strong>
              <span style={{ fontSize: 11, color: "#9ca3bf" }}> — BIN: {p.bin} PCN: {p.pcn} Copay: ${p.copay_amount}</span>
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              <button onClick={() => void handleValidate(p.id)} disabled={loading} style={{ fontSize: 11, padding: "4px 8px", border: "1px solid #d1d5db", borderRadius: 4 }}>
                Validate
              </button>
              {patient.insurance_plan_id !== p.id && canWrite && (
                <button onClick={() => void handleBind(p.id)} style={{ fontSize: 11, padding: "4px 8px", background: "#3b82f6", color: "#fff", border: "none", borderRadius: 4 }}>
                  Bind
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {validation && (
        <div style={{ padding: 12, background: validation.active ? "#dcfce8" : "#fee2e2", borderRadius: 6, fontSize: 13 }}>
          Active: <strong>{validation.active ? "Yes" : "No"}</strong> | Copay: ${validation.copay} | Coverage: {validation.coverage}%
        </div>
      )}
    </div>
  );
}

function MembersTab({ patient, canWrite }: {
  patient: PatientRead;
  canWrite: boolean;
}) {
  const [members, setMembers] = useState<MembersGroupRead[]>([]);
  const [form, setForm] = useState({ member_name: "", relationship: "", dob: "" });

  useEffect(() => {
    void patientsApi.listPatientMembers(patient.id).then(setMembers).catch(() => {});
  }, [patient.id]);

  const handleAdd = async () => {
    if (!form.member_name || !form.dob) return;
    try {
      await patientsApi.createMember({ patient_id: patient.id, ...form });
      const updated = await patientsApi.listPatientMembers(patient.id);
      setMembers(updated);
      setForm({ member_name: "", relationship: "", dob: "" });
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to add member");
    }
  };

  return (
    <div>
      {canWrite && (
        <div style={{ display: "flex", gap: 8, marginBottom: 12, alignItems: "end" }}>
          <Field label="Member Name" value={form.member_name} canWrite={canWrite} onChange={(v) => setForm({ ...form, member_name: v })} />
          <Field label="Relationship" value={form.relationship} canWrite={canWrite} onChange={(v) => setForm({ ...form, relationship: v })} />
          <Field label="DOB" value={form.dob} canWrite={canWrite} onChange={(v) => setForm({ ...form, dob: v })} />
          <button onClick={() => void handleAdd()} style={{ padding: "6px 12px", background: "#16a34a", color: "#fff", border: "none", borderRadius: 6, fontSize: 13 }}>
            Add
          </button>
        </div>
      )}
      {members.length === 0 ? (
        <p style={{ fontSize: 12, color: "#9ca3bf" }}>No dependents added.</p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #e5e7eb" }}>
              <th style={{ padding: "6px 8px", textAlign: "left" }}>Name</th>
              <th style={{ padding: "6px 8px", textAlign: "left" }}>Relationship</th>
              <th style={{ padding: "6px 8px", textAlign: "left" }}>DOB</th>
            </tr>
          </thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.id} style={{ borderBottom: "1px solid #f3f4f6" }}>
                <td style={{ padding: "6px 8px" }}>{m.member_name}</td>
                <td style={{ padding: "6px 8px" }}>{m.relationship || "—"}</td>
                <td style={{ padding: "6px 8px" }}>{m.dob}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function RefillTab({ patient }: { patient: PatientRead }) {
  const [dispenses, setDispenses] = useState<DispenseRead[]>([]);
  const [loading, setLoading] = useState(false);
  const [rxNumber, setRxNumber] = useState("");

  useEffect(() => {
    void patientsApi.listPatientDispenses(patient.id).then(setDispenses).catch(() => {});
  }, [patient.id]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div>
        <label style={{ fontSize: 12, fontWeight: 600 }}>Rx Number</label>
        <input
          value={rxNumber}
          onChange={(e) => setRxNumber(e.target.value)}
          placeholder="Enter prescription number"
          style={{ padding: "6px 8px", fontSize: 13, border: "1px solid #d1d5db", borderRadius: 6, width: 240 }}
        />
      </div>
      {loading && <p style={{ fontSize: 12, color: "#9ca3bf" }}>Processing...</p>}
      {dispenses.length === 0 ? (
        <p style={{ fontSize: 12, color: "#9ca3bf" }}>No dispenses on record.</p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #e5e7eb" }}>
              <th style={{ padding: "6px 8px" }}>Date</th>
              <th style={{ padding: "6px 8px" }}>Product</th>
              <th style={{ padding: "6px 8px" }}>Qty</th>
              <th style={{ padding: "6px 8px" }}>Sig</th>
              <th style={{ padding: "6px 8px" }}>Price</th>
            </tr>
          </thead>
          <tbody>
            {dispenses.map((d) => (
              <tr key={d.id} style={{ borderBottom: "1px solid #f3f4f6" }}>
                <td style={{ padding: "6px 8px" }}>{d.fill_date}</td>
                <td style={{ padding: "6px 8px" }}>{d.product_name}</td>
                <td style={{ padding: "6px 8px" }}>{d.quantity}</td>
                <td style={{ padding: "6px 8px" }}>{d.sig_code}</td>
                <td style={{ padding: "6px 8px" }}>${d.price_at_time}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function HistoryTab({ patient }: { patient: PatientRead }) {
  const [history, setHistory] = useState<PatientHistoryEntry[]>([]);

  useEffect(() => {
    void patientsApi.getPatientHistory(patient.id).then(setHistory).catch(() => {});
  }, [patient.id]);

  if (history.length === 0) return <p style={{ fontSize: 12, color: "#9ca3bf" }}>No patient history.</p>;

  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
      <thead>
        <tr style={{ textAlign: "left", borderBottom: "1px solid #e5e7eb" }}>
          <th style={{ padding: "6px 8px" }}>Receipt #</th>
          <th style={{ padding: "6px 8px" }}>Date</th>
          <th style={{ padding: "6px 8px" }}>Amount</th>
          <th style={{ padding: "6px 8px" }}>Payment</th>
          <th style={{ padding: "6px 8px" }}>Dispenses</th>
        </tr>
      </thead>
      <tbody>
        {history.map((h) => (
          <tr key={h.receipt_id} style={{ borderBottom: "1px solid #f3f4f6" }}>
            <td style={{ padding: "6px 8px" }}>{h.receipt_number}</td>
            <td style={{ padding: "6px 8px" }}>{h.timestamp.slice(0, 10)}</td>
            <td style={{ padding: "6px 8px" }}>${h.total_amount}</td>
            <td style={{ padding: "6px 8px" }}>{h.payment_method}</td>
            <td style={{ padding: "6px 8px" }}>{h.dispense_ids.join(", ") || "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function BillingInfoTab({ patient }: { patient: PatientRead }) {
  const [history, setHistory] = useState<PatientHistoryEntry[]>([]);

  useEffect(() => {
    void patientsApi.getPatientHistory(patient.id).then(setHistory).catch(() => {});
  }, [patient.id]);

  const totalOutstanding = history.reduce((sum, h) => sum + Number(h.total_amount), 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, fontSize: 13 }}>
      <div>
        <label style={{ fontSize: 12, fontWeight: 600 }}>Insurance Provider</label>
        <span style={{ fontSize: 13 }}>{patient.insurance_provider || "None"}</span>
      </div>
      <div>
        <label style={{ fontSize: 12, fontWeight: 600 }}>Policy Number</label>
        <span style={{ fontSize: 13 }}>{patient.policy_number || "—"}</span>
      </div>
      <div>
        <label style={{ fontSize: 12, fontWeight: 600 }}>Total Patient Spending</label>
        <span style={{ fontSize: 13, fontWeight: 600 }}>${formatMoney(parseMoney(totalOutstanding.toFixed(2)))}</span>
      </div>
    </div>
  );
}

function CommentsTab({ patient, onUpdate, canWrite }: {
  patient: PatientRead;
  onUpdate: (patch: PatientUpdate) => Promise<void>;
  canWrite: boolean;
}) {
  return (
    <div>
      <textarea
        defaultValue={patient.comments}
        onBlur={(e) => { if (e.target.value !== patient.comments) onUpdate({ comments: e.target.value }); }}
        disabled={!canWrite}
        placeholder="Free-text clinical notes, prescription history notes, etc."
        style={{ width: "100%", minHeight: 120, padding: 8, fontSize: 13, border: "1px solid #d1d5db", borderRadius: 6, fontFamily: "inherit" }}
      />
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────

export default function PatientsPage() {
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const { patients, isLoading, error, getPatient, createPatient, search } = usePatients();
  const canWrite = useCan("patients.write");

  const [selected, setSelected] = useState<PatientRead | null>(null);
  const [activeTab, setActiveTab] = useState<TabName>("General");
  const [creating, setCreating] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");

  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login");
  }, [isAuthenticated, router]);

  if (!isAuthenticated()) return null;

  const handleSelect = (p: PatientRead) => {
    setSelected(p);
    setActiveTab("General");
  };

  const handleUpdate = async (patch: PatientUpdate) => {
    if (!selected) return;
    try {
      await patientsApi.updatePatient(selected.id, patch);
      const updated = await patientsApi.getPatient(selected.id);
      setSelected(updated);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Update failed");
    }
  };

  const handleCreate = async () => {
    const name = prompt("Patient name:")?.trim();
    if (!name) return;
    const dob = prompt("DOB (YYYY-MM-DD):")?.trim() ?? "";
    try {
      const created = await createPatient({
        name,
        dob,
        address: "",
        driver_license: "",
        sex: "",
        employer_id: "",
        contact_phone: "",
        email: "",
        insurance_provider: "",
        policy_number: "",
        group_number: "",
        patient_allergies: "",
        comments: "",
      });
      setSelected(created);
      setActiveTab("General");
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Create failed");
    }
  };

  return (
    <main style={{ maxWidth: 1000, margin: "2rem auto", padding: "0 1.5rem", fontFamily: "Inter, system-ui" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 16 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700 }}>Patient Records</h1>
        {canWrite && (
          <button onClick={() => void handleCreate()} style={{ padding: "0.5rem 1rem", background: "#16a34a", color: "#fff", border: "none", borderRadius: 6, fontSize: 13 }}>
            + New Patient
          </button>
        )}
      </header>

      <input
        type="text"
        placeholder="Search patients by name..."
        value={searchTerm}
        onChange={(e) => { setSearchTerm(e.target.value); void search(e.target.value); }}
        style={{ width: "100%", padding: "8px 10px", fontSize: 13, border: "1px solid #d1d5db", borderRadius: 6, marginBottom: 12 }}
      />

      {isLoading && <p style={{ fontSize: 13, color: "#9ca3bf" }}>Loading patients…</p>}
      {error && <p style={{ fontSize: 13, color: "#dc2626" }}>{error}</p>}

      <div style={{ display: "flex", gap: 16 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "2px solid #e5e7eb" }}>
                <th style={{ padding: "6px 8px" }}>Name</th>
                <th style={{ padding: "6px 8px" }}>DOB</th>
                <th style={{ padding: "6px 8px" }}>Phone</th>
                <th style={{ padding: "6px 8px" }}>Insurance</th>
              </tr>
            </thead>
            <tbody>
              {patients?.items.map((p) => (
                <tr
                  key={p.id}
                  onClick={() => handleSelect(p)}
                  style={{
                    cursor: "pointer",
                    borderBottom: "1px solid #f3f4f6",
                    background: selected?.id === p.id ? "#eff6ff" : "transparent",
                  }}
                >
                  <td style={{ padding: "6px 8px" }}>{p.name}</td>
                  <td style={{ padding: "6px 8px" }}>{p.dob}</td>
                  <td style={{ padding: "6px 8px" }}>{p.contact_phone || "—"}</td>
                  <td style={{ padding: "6px 8px" }}>{p.insurance_provider || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {selected && (
          <div style={{ flex: 1, minWidth: 280, border: "1px solid #e5e7eb", borderRadius: 8, padding: 16, background: "#fafafa" }}>
            <div style={{ display: "flex", gap: 4, marginBottom: 12, overflowX: "auto" }}>
              {TABS.map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  style={{
                    padding: "6px 12px",
                    fontSize: 12,
                    fontWeight: activeTab === tab ? 600 : 400,
                    border: activeTab === tab ? "2px solid #3b82f6" : "1px solid #d1d5db",
                    borderRadius: 4,
                    background: activeTab === tab ? "#eff6ff" : "#fff",
                    cursor: "pointer",
                    whiteSpace: "nowrap",
                  }}
                >
                  {tab}
                </button>
              ))}
            </div>

            {activeTab === "General" && <GeneralTab patient={selected} onUpdate={handleUpdate} canWrite={canWrite} />}
            {activeTab === "Insurance Plan" && <InsuranceTab patient={selected} onUpdate={handleUpdate} canWrite={canWrite} />}
            {activeTab === "Members Group" && <MembersTab patient={selected} canWrite={canWrite} />}
            {activeTab === "Rx / Refill" && <RefillTab patient={selected} />}
            {activeTab === "Patient History" && <HistoryTab patient={selected} />}
            {activeTab === "Billing Info" && <BillingInfoTab patient={selected} />}
            {activeTab === "Comments" && <CommentsTab patient={selected} onUpdate={handleUpdate} canWrite={canWrite} />}
          </div>
        )}
      </div>
    </main>
  );
}
