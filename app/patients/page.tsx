"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

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
import * as wcApi from "@/lib/api/wc";
import { parseMoney, formatMoney } from "@/lib/decimalCurrency";
import { useI18n } from "@/components/I18nProvider";
import type { WCClaimRead, WCClaimUpdate } from "@/types/contracts";
import { patientGeneralSchema, type PatientGeneralForm } from "@/lib/validations/patient";
import { workersCompSchema, type WorkersCompForm } from "@/lib/validations/workersComp";
import { DashboardLayout } from "@/components/DashboardLayout";

const TABS = ["General", "Insurance Plan", "Members Group", "Rx / Refill", "Patient History", "Billing Info", "Comments", "Emergency Contact", "Employment", "Workers' Comp", "Demographics", "Communication"] as const;
type TabName = (typeof TABS)[number];

// ── Sub-components (co-located, no micro-files) ────────────────────────────

function GeneralTab({ patient, onUpdate, canWrite }: {
  patient: PatientRead;
  onUpdate: (patch: PatientUpdate) => Promise<void>;
  canWrite: boolean;
}) {
  const { t } = useI18n();
  
  const form = useForm<PatientGeneralForm>({
    resolver: zodResolver(patientGeneralSchema),
    defaultValues: {
      last_name: patient.last_name ?? "",
      first_name: patient.first_name ?? "",
      middle_initial: patient.middle_initial ?? "",
      dob: patient.dob ?? "",
      ssn: patient.ssn ?? "",
      sex: patient.sex === 'M' || patient.sex === 'F' || patient.sex === 'O' ? patient.sex : undefined,
      address: patient.address ?? "",
      city: patient.city ?? "",
      state: patient.state ?? "",
      zip: patient.zip ?? "",
      home_phone: patient.home_phone ?? "",
      cell_phone: patient.cell_phone ?? "",
      email: patient.email ?? "",
      primary_care_physician: patient.primary_care_physician ?? "",
      driver_license: patient.driver_license ?? "",
      employer_id: patient.employer_id ?? "",
      contact_phone: patient.contact_phone ?? "",
      insurance_provider: patient.insurance_provider ?? "",
      policy_number: patient.policy_number ?? "",
      group_number: patient.group_number ?? "",
      patient_allergies: patient.patient_allergies ?? "",
      comments: patient.comments ?? "",
    },
    mode: "onBlur",
  });

  const handleSubmit = async (data: PatientGeneralForm) => {
    await onUpdate(data as PatientUpdate);
  };

  const renderField = (name: keyof PatientGeneralForm, label: string, options?: { fullWidth?: boolean; placeholder?: string }) => {
    const error = form.formState.errors[name as keyof typeof form.formState.errors];
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 4, gridColumn: options?.fullWidth ? "1 / -1" : "auto" }}>
        <label htmlFor="pt-80" style={{ fontSize: 12, fontWeight: 600, color: "#6b7280" }}>{label}</label>
        {canWrite ? (
          <>
            <input id="pt-80"
              {...form.register(name)}
              placeholder={options?.placeholder}
              style={{
                padding: "6px 8px",
                fontSize: 13,
                border: error ? "1px solid #ef4444" : "1px solid #d1d5db",
                borderRadius: 6,
                width: options?.fullWidth ? "100%" : "auto",
              }}
            />
            {error && <span style={{ fontSize: 11, color: "#ef4444" }}>{error.message}</span>}
          </>
        ) : (
          <span style={{ fontSize: 13, padding: "6px 8px", color: "#374151" }}>
            {form.watch(name as any) || <span style={{ color: "#9ca3bf" }}>—</span>}
          </span>
        )}
      </div>
    );
  };

  return (
    <form onSubmit={form.handleSubmit(handleSubmit)} style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px 16px" }}>
      {renderField("last_name", t("patients.fieldLastName"))}
      {renderField("first_name", t("patients.fieldFirstName"))}
      {renderField("middle_initial", t("patients.fieldMiddleInitial"))}
      {renderField("dob", t("patients.colDob"))}
      {renderField("ssn", t("patients.fieldSSN"), { placeholder: "XXX-XX-XXXX" })}
      {renderField("sex", t("patients.fieldSex"))}
      {renderField("address", t("patients.fieldAddress"), { fullWidth: true } )}
      {renderField("city", t("patients.fieldCity"))}
      {renderField("state", t("patients.fieldState"), { placeholder: "XX" })}
      {renderField("zip", t("patients.fieldZip"), { placeholder: "XXXXX" })}
      {renderField("home_phone", t("patients.fieldHomePhone"), { placeholder: "XXX-XXX-XXXX" })}
      {renderField("cell_phone", t("patients.fieldCellPhone"), { placeholder: "XXX-XXX-XXXX" })}
      {renderField("email", t("patients.emailField"), { placeholder: "user@example.com" })}
      {renderField("primary_care_physician", t("patients.fieldPrimaryCarePhysician"))}
      {renderField("driver_license", t("patients.fieldDriverLicense"))}
      {renderField("employer_id", t("patients.fieldEmployerId"))}
      {renderField("contact_phone", t("patients.fieldContactPhone"), { placeholder: "XXX-XXX-XXXX" })}
      {renderField("insurance_provider", t("patients.insuranceProvider"))}
      {renderField("policy_number", t("patients.policyNumber"))}
      {renderField("group_number", t("patients.groupNumber"))}
      <div style={{ gridColumn: "1 / -1" }}>
        {renderField("patient_allergies", t("patients.fieldAllergies"), { fullWidth: true, placeholder: "e.g. Penicillin, Sulfa" })}
        <div style={{ marginTop: 8 }}>
          {patient.allergy_alerts && patient.allergy_alerts.length > 0 ? (
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {patient.allergy_alerts.map((tag: string, i: number) => (
                <span key={i} style={{ background: "#fee2e2", color: "#991b2b", padding: "2px 8px", borderRadius: 12, fontSize: 12, fontWeight: 500 }}>
                  {tag}
                </span>
              ))}
            </div>
          ) : (
            <span style={{ fontSize: 12, color: "#9ca3af" }}>{t("patients.noAllergies")}</span>
          )}
        </div>
      </div>
      {canWrite && (
        <div style={{ gridColumn: "1 / -1", display: "flex", justifyContent: "flex-end", marginTop: 8 }}>
          <button type="submit" style={{ padding: "8px 16px", fontSize: 13, fontWeight: 600, background: "#16a34a", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer" }}>
            {t("common.save")}
          </button>
        </div>
      )}
    </form>
  );
}

function WorkersCompTab({ patient, onUpdate, canWrite }: {
  patient: PatientRead;
  onUpdate: (patch: PatientUpdate) => Promise<void>;
  canWrite: boolean;
}) {
  const { t } = useI18n();
  const [claim, setClaim] = useState<WCClaimRead | null>(null);
  const [claimPatch, setClaimPatch] = useState<Partial<WCClaimUpdate>>({});
  const [loading, setLoading] = useState(false);

  const form = useForm<WorkersCompForm>({
    resolver: zodResolver(workersCompSchema),
    defaultValues: {
      employer_name: patient.employer_name ?? "",
      claim_reference: patient.wc_claim_number ?? "",
      injury_date: patient.wc_injury_date ?? "",
      carrier_id: patient.wc_carrier_id ?? "",
      pay_to_name: claim?.pay_to ?? "",
      pay_to_address: claim?.pay_to_addr_line1 ?? "",
      wc_carrier_name: patient.wc_carrier_name ?? "",
      wc_injury_description: patient.wc_injury_description ?? "",
      employer_address: patient.employer_address ?? "",
      employer_phone: patient.employer_phone ?? "",
      employer_phone_ext: claim?.employer_phone_ext ?? "",
      employer_contact_name: claim?.employer_contact_name ?? "",
      employer_addr_line1: claim?.employer_addr_line1 ?? "",
      employer_addr_line2: claim?.employer_addr_line2 ?? "",
      employer_city: claim?.employer_city ?? "",
      employer_state: claim?.employer_state ?? "",
      employer_zip: claim?.employer_zip ?? "",
      pay_to_contact: claim?.pay_to_contact ?? "",
      pay_to_phone: claim?.pay_to_phone ?? "",
      pay_to_addr_line2: claim?.pay_to_addr_line2 ?? "",
      pay_to_city: claim?.pay_to_city ?? "",
      pay_to_state: claim?.pay_to_state ?? "",
      pay_to_zip: claim?.pay_to_zip ?? "",
      status: claim?.status === 'open' || claim?.status === 'pending_approval' || claim?.status === 'approved' || claim?.status === 'denied' || claim?.status === 'closed' ? claim.status : undefined,
      notes: claim?.notes ?? "",
    },
    mode: "onBlur",
  });

  // Load claim on mount
  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const claims = await wcApi.listWCClaims({ patient_id: patient.id });
        if (claims.length > 0) {
          setClaim(claims[0]);
          // Sync claim data to form
          form.reset({
            employer_name: patient.employer_name ?? "",
            claim_reference: patient.wc_claim_number ?? "",
            injury_date: patient.wc_injury_date ?? "",
            carrier_id: patient.wc_carrier_id ?? "",
            pay_to_name: claims[0].pay_to ?? "",
            pay_to_address: claims[0].pay_to_addr_line1 ?? "",
            wc_carrier_name: patient.wc_carrier_name ?? "",
            wc_injury_description: patient.wc_injury_description ?? "",
            employer_address: patient.employer_address ?? "",
            employer_phone: patient.employer_phone ?? "",
            employer_phone_ext: claims[0].employer_phone_ext ?? "",
            employer_contact_name: claims[0].employer_contact_name ?? "",
            employer_addr_line1: claims[0].employer_addr_line1 ?? "",
            employer_addr_line2: claims[0].employer_addr_line2 ?? "",
            employer_city: claims[0].employer_city ?? "",
            employer_state: claims[0].employer_state ?? "",
            employer_zip: claims[0].employer_zip ?? "",
            pay_to_contact: claims[0].pay_to_contact ?? "",
            pay_to_phone: claims[0].pay_to_phone ?? "",
            pay_to_addr_line2: claims[0].pay_to_addr_line2 ?? "",
            pay_to_city: claims[0].pay_to_city ?? "",
            pay_to_state: claims[0].pay_to_state ?? "",
            pay_to_zip: claims[0].pay_to_zip ?? "",
            status: claims[0].status === 'open' || claims[0].status === 'pending_approval' || claims[0].status === 'approved' || claims[0].status === 'denied' || claims[0].status === 'closed' ? claims[0].status : undefined,
            notes: claims[0].notes ?? "",
          });
        }
      } catch { /* no claim yet */ }
      finally {
        setLoading(false);
      }
    })();
  }, [patient.id]);

  const handleClaimField = (field: keyof WCClaimUpdate, value: string) => {
    setClaimPatch(prev => ({ ...prev, [field]: value }));
  };

  const saveClaim = async () => {
    if (!claim) return;
    try {
      await wcApi.updateWCClaim(claim.id, claimPatch);
    } catch (err) {
      console.error(err);
    }
  };

  const onSubmit = async (data: WorkersCompForm) => {
    await onUpdate(data as PatientUpdate);
    if (claim) {
      await wcApi.updateWCClaim(claim.id, {
        employer_name: data.employer_name,
        claim_number: data.claim_reference,
        injury_date: data.injury_date,
        carrier_id: data.carrier_id,
        carrier_name: data.wc_carrier_name,
        injury_description: data.wc_injury_description,
        employer_address: data.employer_address,
        employer_phone: data.employer_phone,
        employer_phone_ext: data.employer_phone_ext,
        employer_contact_name: data.employer_contact_name,
        employer_addr_line1: data.employer_addr_line1,
        employer_addr_line2: data.employer_addr_line2,
        employer_city: data.employer_city,
        employer_state: data.employer_state,
        employer_zip: data.employer_zip,
        pay_to: data.pay_to_name,
        pay_to_contact: data.pay_to_contact,
        pay_to_phone: data.pay_to_phone,
        pay_to_addr_line1: data.pay_to_address,
        pay_to_addr_line2: data.pay_to_addr_line2,
        pay_to_city: data.pay_to_city,
        pay_to_state: data.pay_to_state,
        pay_to_zip: data.pay_to_zip,
        status: data.status,
        notes: data.notes,
      });
    }
  };

  const renderField = (name: keyof WorkersCompForm, label: string, options?: { fullWidth?: boolean; placeholder?: string }) => {
    const error = form.formState.errors[name as keyof typeof form.formState.errors];
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 4, gridColumn: options?.fullWidth ? "1 / -1" : "auto" }}>
        <label htmlFor="pt-290" style={{ fontSize: 12, fontWeight: 600, color: "#6b7280" }}>{label}</label>
        {canWrite ? (
          <>
            <input id="pt-290"
              {...form.register(name)}
              placeholder={options?.placeholder}
              style={{
                padding: "6px 8px",
                fontSize: 13,
                border: error ? "1px solid #ef4444" : "1px solid #d1d5db",
                borderRadius: 6,
                width: options?.fullWidth ? "100%" : "auto",
              }}
            />
            {error && <span style={{ fontSize: 11, color: "#ef4444" }}>{error.message}</span>}
          </>
        ) : (
          <span style={{ fontSize: 13, padding: "6px 8px", color: "#374151" }}>
            {form.watch(name as any) || <span style={{ color: "#9ca3bf" }}>—</span>}
          </span>
        )}
      </div>
    );
  };

  return (
    <form onSubmit={form.handleSubmit(onSubmit)}>
      {/* Summary fields on Patient record */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px 16px" }}>
        {renderField("employer_name", t("patients.fieldEmployerName"))}
        {renderField("claim_reference", t("patients.fieldClaimNumber"))}
        {renderField("injury_date", t("patients.fieldInjuryDate"))}
        {renderField("carrier_id", t("patients.fieldCarrierId"))}
        {renderField("wc_carrier_name", t("patients.fieldCarrierName"))}
        {renderField("wc_injury_description", t("patients.fieldInjuryDescription"), { fullWidth: true })}
      </div>

      {/* Extended Employer Address */}
      <div style={{ marginTop: 20 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: "#2563eb", borderBottom: "1px solid #e5e7eb", paddingBottom: 6, marginBottom: 12 }}>
          Employer Address
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px 16px" }}>
          {renderField("employer_contact_name", "Contact Name")}
          {renderField("employer_phone_ext", "Phone Ext.")}
          {renderField("employer_addr_line1", "Address Line 1", { fullWidth: true })}
          {renderField("employer_addr_line2", "Address Line 2", { fullWidth: true })}
          {renderField("employer_city", "City")}
          <div style={{ display: "flex", gap: 8 }}>
            {renderField("employer_state", "State", { placeholder: "XX" })}
            {renderField("employer_zip", "Zip", { placeholder: "XXXXX" })}
          </div>
        </div>
      </div>

      {/* Pay To Section */}
      <div style={{ marginTop: 20 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: "#2563eb", borderBottom: "1px solid #e5e7eb", paddingBottom: 6, marginBottom: 12 }}>
          Pay To
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px 16px" }}>
          {renderField("pay_to_name", "Pay To")}
          {renderField("pay_to_contact", "Contact Person")}
          {renderField("pay_to_phone", "Phone", { placeholder: "XXX-XXX-XXXX" })}
          {renderField("pay_to_address", "Address Line 1", { fullWidth: true })}
          {renderField("pay_to_addr_line2", "Address Line 2", { fullWidth: true })}
          {renderField("pay_to_city", "City")}
          <div style={{ display: "flex", gap: 8 }}>
            {renderField("pay_to_state", "State", { placeholder: "XX" })}
            {renderField("pay_to_zip", "Zip", { placeholder: "XXXXX" })}
          </div>
        </div>
      </div>

      {/* Action bar */}
      <div style={{ marginTop: 16, display: "flex", gap: 8, alignItems: "center" }}>
        {claim && canWrite && (
          <button type="button" onClick={saveClaim} style={{ padding: "6px 16px", fontSize: 13, fontWeight: 600, background: "#2563eb", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer" }}>
            Save Claim Details
          </button>
        )}
        {canWrite && (
          <button type="submit" style={{ padding: "8px 16px", fontSize: 13, fontWeight: 600, background: "#16a34a", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer" }}>
            {t("common.save")}
          </button>
        )}
        <Link
          href={`/dashboard/wc-claims?patient_id=${patient.id}`}
          style={{ color: "#2563eb", fontSize: 14, textDecoration: "underline" }}
        >
          {t("patients.viewAllWcClaims")}
        </Link>
      </div>
    </form>
  );
}

// Shared Field component for non-RHF tabs
function Field({ label, value, canWrite, onChange, placeholder, fullWidth }: {
  label: string;
  value: string;
  canWrite: boolean;
  onChange: (v: string) => void;
  placeholder?: string;
  fullWidth?: boolean;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, gridColumn: fullWidth ? "1 / -1" : "auto" }}>
      <label htmlFor="pt-398" style={{ fontSize: 12, fontWeight: 600, color: "#6b7280" }}>{label}</label>
      {canWrite ? (
        <input id="pt-398"
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
  const { t } = useI18n();
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
        <Field label={t("patients.insuranceProvider")} value={patient.insurance_provider} canWrite={canWrite} onChange={(v) => onUpdate({ insurance_provider: v })} />
        <Field label="Policy #" value={patient.policy_number} canWrite={canWrite} onChange={(v) => onUpdate({ policy_number: v })} />
        <Field label="Group #" value={patient.group_number} canWrite={canWrite} onChange={(v) => onUpdate({ group_number: v })} />
      </div>

      <div style={{ paddingTop: 12, borderTop: "1px solid #e5e7eb" }}>
        <p style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>{t("patients.insurancePlans")}</p>
        {plans.map((p) => (
          <div key={p.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: "1px solid #f3f4f6" }}>
            <div>
              <strong style={{ fontSize: 13 }}>{p.plan_name}</strong>
              <span style={{ fontSize: 11, color: "#9ca3bf" }}> — BIN: {p.bin} PCN: {p.pcn} Copay: ${p.copay_amount}</span>
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              <button onClick={() => void handleValidate(p.id)} disabled={loading} style={{ fontSize: 11, padding: "4px 8px", border: "1px solid #d1d5db", borderRadius: 4 }}>
                {t("patients.validate")}
              </button>
              {patient.insurance_plan_id !== p.id && canWrite && (
                <button onClick={() => void handleBind(p.id)} style={{ fontSize: 11, padding: "4px 8px", background: "#3b82f6", color: "#fff", border: "none", borderRadius: 4 }}>
                  {t("patients.bind")}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {validation && (
        <div style={{ padding: 12, background: validation.active ? "#dcfce8" : "#fee2e2", borderRadius: 6, fontSize: 13 }}>
          {t("patients.active")} <strong>{validation.active ? t("patients.yes") : t("patients.no")}</strong> | Copay: ${validation.copay} | Coverage: {validation.coverage}%
        </div>
      )}
    </div>
  );
}

function MembersTab({ patient, canWrite }: {
  patient: PatientRead;
  canWrite: boolean;
}) {
  const { t } = useI18n();
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
          <Field label={t("patients.memberName")} value={form.member_name} canWrite={canWrite} onChange={(v) => setForm({ ...form, member_name: v })} />
          <Field label={t("patients.relationship")} value={form.relationship} canWrite={canWrite} onChange={(v) => setForm({ ...form, relationship: v })} />
          <Field label={t("patients.dob")} value={form.dob} canWrite={canWrite} onChange={(v) => setForm({ ...form, dob: v })} />
          <button onClick={() => void handleAdd()} style={{ padding: "6px 12px", background: "#16a34a", color: "#fff", border: "none", borderRadius: 6, fontSize: 13 }}>
            {t("patients.add")}
          </button>
        </div>
      )}
      {members.length === 0 ? (
        <p style={{ fontSize: 12, color: "#9ca3bf" }}>{t("patients.noDependents")}</p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #e5e7eb" }}>
              <th style={{ padding: "6px 8px", textAlign: "left" }}>{t("patients.memberName")}</th>
              <th style={{ padding: "6px 8px", textAlign: "left" }}>{t("patients.relationship")}</th>
              <th style={{ padding: "6px 8px", textAlign: "left" }}>{t("patients.dob")}</th>
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
  const { t } = useI18n();
  const [dispenses, setDispenses] = useState<DispenseRead[]>([]);
  const [loading, setLoading] = useState(false);
  const [rxNumber, setRxNumber] = useState("");

  useEffect(() => {
    void patientsApi.listPatientDispenses(patient.id).then(setDispenses).catch(() => {});
  }, [patient.id]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div>
        <label htmlFor="pt-561" style={{ fontSize: 12, fontWeight: 600 }}>{t("patients.rxNumber")}</label>
        <input id="pt-561"
          value={rxNumber}
          onChange={(e) => setRxNumber(e.target.value)}
          placeholder={t("patients.enterRxNumber")}
          style={{ padding: "6px 8px", fontSize: 13, border: "1px solid #d1d5db", borderRadius: 6, width: 240 }}
        />
      </div>
      {loading && <p style={{ fontSize: 12, color: "#9ca3bf" }}>{t("patients.processing")}</p>}
      {dispenses.length === 0 ? (
        <p style={{ fontSize: 12, color: "#9ca3bf" }}>{t("patients.noDispenses")}</p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #e5e7eb" }}>
              <th style={{ padding: "6px 8px" }}>{t("patients.date")}</th>
              <th style={{ padding: "6px 8px" }}>{t("patients.product")}</th>
              <th style={{ padding: "6px 8px" }}>{t("patients.qty")}</th>
              <th style={{ padding: "6px 8px" }}>{t("patients.sig")}</th>
              <th style={{ padding: "6px 8px" }}>{t("patients.price")}</th>
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
  const { t } = useI18n();
  const [history, setHistory] = useState<PatientHistoryEntry[]>([]);

  useEffect(() => {
    void patientsApi.getPatientHistory(patient.id).then(setHistory).catch(() => {});
  }, [patient.id]);

  if (history.length === 0) return <p style={{ fontSize: 12, color: "#9ca3bf" }}>{t("patients.noHistory")}</p>;

  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
      <thead>
        <tr style={{ textAlign: "left", borderBottom: "1px solid #e5e7eb" }}>
          <th style={{ padding: "6px 8px" }}>{t("patients.receiptNum")}</th>
          <th style={{ padding: "6px 8px" }}>{t("patients.date")}</th>
          <th style={{ padding: "6px 8px" }}>{t("patients.amount")}</th>
          <th style={{ padding: "6px 8px" }}>{t("patients.payment")}</th>
          <th style={{ padding: "6px 8px" }}>{t("patients.dispenses")}</th>
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
  const { t } = useI18n();
  const [history, setHistory] = useState<PatientHistoryEntry[]>([]);

  useEffect(() => {
    void patientsApi.getPatientHistory(patient.id).then(setHistory).catch(() => {});
  }, [patient.id]);

  const totalOutstanding = history.reduce((sum, h) => sum + Number(h.total_amount), 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, fontSize: 13 }}>
      <div>
        <span style={{ fontSize: 12, fontWeight: 600 }}>{t("patients.insuranceProvider")}</span>
        <span style={{ fontSize: 13 }}>{patient.insurance_provider || t("patients.none")}</span>
      </div>
      <div>
        <span style={{ fontSize: 12, fontWeight: 600 }}>{t("patients.policyNumber")}</span>
        <span style={{ fontSize: 13 }}>{patient.policy_number || "—"}</span>
      </div>
      <div>
        <span style={{ fontSize: 12, fontWeight: 600 }}>{t("patients.totalSpending")}</span>
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
  const { t } = useI18n();
  return (
    <div>
      <textarea
        defaultValue={patient.comments}
        onBlur={(e) => { if (e.target.value !== patient.comments) onUpdate({ comments: e.target.value }); }}
        disabled={!canWrite}
        placeholder={t("patients.clinicalNotes")}
        style={{ width: "100%", minHeight: 120, padding: 8, fontSize: 13, border: "1px solid #d1d5db", borderRadius: 6, fontFamily: "inherit" }}
      />
    </div>
  );
}

// ── Emergency Contact Tab ────────────────────────────────────────────────────
function EmergencyContactTab({ patient, onUpdate, canWrite }: {
  patient: PatientRead;
  onUpdate: (patch: PatientUpdate) => Promise<void>;
  canWrite: boolean;
}) {
  const { t } = useI18n();
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px 16px" }}>
      <Field label="Contact Name" value={patient.emergency_contact_name ?? ""} canWrite={canWrite} onChange={(v) => onUpdate({ emergency_contact_name: v })} />
      <Field label={t("patients.phone")} value={patient.emergency_contact_phone ?? ""} canWrite={canWrite} onChange={(v) => onUpdate({ emergency_contact_phone: v })} />
      <Field label={t("patients.relationship")} value={patient.emergency_contact_relationship ?? ""} canWrite={canWrite} onChange={(v) => onUpdate({ emergency_contact_relationship: v })} />
    </div>
  );
}

// ── Employment Tab ───────────────────────────────────────────────────────────
function EmploymentTab({ patient, onUpdate, canWrite }: {
  patient: PatientRead;
  onUpdate: (patch: PatientUpdate) => Promise<void>;
  canWrite: boolean;
}) {
  const { t } = useI18n();
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px 16px" }}>
      <Field label={t("patients.fieldEmployerName")} value={patient.employer_name ?? ""} canWrite={canWrite} onChange={(v) => onUpdate({ employer_name: v })} />
      <Field label={t("patients.fieldEmployerPhone")} value={patient.employer_phone ?? ""} canWrite={canWrite} onChange={(v) => onUpdate({ employer_phone: v })} />
      <Field label={t("patients.fieldEmployerAddress")} value={patient.employer_address ?? ""} canWrite={canWrite} onChange={(v) => onUpdate({ employer_address: v })} fullWidth />
      <Field label={t("patients.fieldCellPhone")} value={patient.cell_phone ?? ""} canWrite={canWrite} onChange={(v) => onUpdate({ cell_phone: v })} />
      <Field label={t("patients.fieldWorkPhone")} value={patient.work_phone ?? ""} canWrite={canWrite} onChange={(v) => onUpdate({ work_phone: v })} />
      <Field label={t("patients.fieldFax")} value={patient.fax ?? ""} canWrite={canWrite} onChange={(v) => onUpdate({ fax: v })} />
    </div>
  );
}

// ── Workers' Compensation Tab ────────────────────────────────────────────────

function DemographicsTab({ patient, onUpdate, canWrite }: {
  patient: PatientRead;
  onUpdate: (patch: PatientUpdate) => Promise<void>;
  canWrite: boolean;
}) {
  const { t } = useI18n();
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px 16px" }}>
      <Field label={t("patients.fieldPreferredLanguage")} value={patient.preferred_language ?? ""} canWrite={canWrite} onChange={(v) => onUpdate({ preferred_language: v })} />
      <Field label={t("patients.fieldEthnicity")} value={patient.ethnicity ?? ""} canWrite={canWrite} onChange={(v) => onUpdate({ ethnicity: v })} />
      <Field label={t("patients.fieldRace")} value={patient.race ?? ""} canWrite={canWrite} onChange={(v) => onUpdate({ race: v })} />
      <Field label={t("patients.fieldMaritalStatus")} value={patient.marital_status ?? ""} canWrite={canWrite} onChange={(v) => onUpdate({ marital_status: v })} />
      <Field label={t("patients.fieldPatientType")} value={patient.patient_type ?? ""} canWrite={canWrite} onChange={(v) => onUpdate({ patient_type: v })} />
      <Field label={t("patients.fieldDeliveryZone")} value={patient.delivery_zone ?? ""} canWrite={canWrite} onChange={(v) => onUpdate({ delivery_zone: v })} />
      <Field label={t("patients.fieldDeliveryStatus")} value={patient.delivery_status ?? ""} canWrite={canWrite} onChange={(v) => onUpdate({ delivery_status: v })} />
      <Field label={t("patients.fieldSurveyNum")} value={patient.survey_num ?? ""} canWrite={canWrite} onChange={(v) => onUpdate({ survey_num: v })} />
    </div>
  );
}

// ── Communication Preferences Tab ────────────────────────────────────────────
function CommunicationTab({ patient, onUpdate, canWrite }: {
  patient: PatientRead;
  onUpdate: (patch: PatientUpdate) => Promise<void>;
  canWrite: boolean;
}) {
  const { t } = useI18n();
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px 16px" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: "#6b7280" }}>{t("patients.consentFlag")}</span>
        <button
          type="button"
          onClick={() => canWrite && onUpdate({ consent_flag: patient.consent_flag ? 0 : 1 })}
          style={{
            padding: "6px 12px",
            fontSize: 13,
            border: "1px solid #d1d5db",
            borderRadius: 6,
            background: patient.consent_flag ? "#dcfce7" : "#f3f4f6",
            color: patient.consent_flag ? "#166534" : "#6b7280",
            cursor: canWrite ? "pointer" : "default",
            fontWeight: 500,
          }}
        >
          {patient.consent_flag ? t("patients.consented") : t("patients.notConsented")}
        </button>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: "#6b7280" }}>{t("patients.preferredContact")}</span>
        <div style={{ display: "flex", gap: 6 }}>
          {(["prefer_call", "prefer_text", "prefer_email"] as const).map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => canWrite && onUpdate({ [key]: patient[key] ? 0 : 1 })}
              style={{
                padding: "4px 10px",
                fontSize: 12,
                border: patient[key] ? "2px solid #3b82f6" : "1px solid #d1d5db",
                borderRadius: 4,
                background: patient[key] ? "#eff6ff" : "#fff",
                cursor: canWrite ? "pointer" : "default",
                fontWeight: patient[key] ? 600 : 400,
              }}
            >
              {key === "prefer_call" ? t("patients.call") : key === "prefer_text" ? t("patients.text") : t("patients.email")}
            </button>
          ))}
        </div>
      </div>

      <Field label={t("patients.fieldPharmacyHomeId")} value={patient.pharmacy_home_id ?? ""} canWrite={canWrite} onChange={(v) => onUpdate({ pharmacy_home_id: v })} />
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: "#6b7280" }}>{t("patients.is340b")}</span>
        <button
          type="button"
          onClick={() => canWrite && onUpdate({ is_340b: patient.is_340b ? 0 : 1 })}
          style={{
            padding: "6px 12px",
            fontSize: 13,
            border: "1px solid #d1d5db",
            borderRadius: 6,
            background: patient.is_340b ? "#dbeafe" : "#f3f4f6",
            color: patient.is_340b ? "#1e40af" : "#6b7280",
            cursor: canWrite ? "pointer" : "default",
            fontWeight: 500,
          }}
        >
          {patient.is_340b ? t("patients.eligible340b") : t("patients.not340b")}
        </button>
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────

export default function PatientsPage() {
  const { t } = useI18n();
  const router = useRouter();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const { patients, isLoading, error, getPatient, createPatient, deletePatient, search } = usePatients();
  const canWrite = useCan("patients.write");
  const canDelete = useCan("patients.delete");

  const [selected, setSelected] = useState<PatientRead | null>(null);
  const [activeTab, setActiveTab] = useState<TabName>("General");
  const [createOpen, setCreateOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");

  const tabLabel: Record<TabName, string> = {
    General: t("patients.tabGeneral"),
    "Insurance Plan": t("patients.tabInsurance"),
    "Members Group": t("patients.tabMembers"),
    "Rx / Refill": t("patients.tabRx"),
    "Patient History": t("patients.tabHistory"),
    "Billing Info": t("patients.tabBilling"),
    Comments: t("patients.tabComments"),
    "Emergency Contact": t("patients.tabEmergency"),
    Employment: t("patients.tabEmployment"),
    "Workers' Comp": t("patients.tabWc"),
    Demographics: t("patients.tabDemographics"),
    Communication: t("patients.tabCommunication"),
  };

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

  const handleDelete = async () => {
    if (!selected) return;
    if (!confirm(`Delete patient "${selected.name}"? This cannot be undone.`)) return;
    try {
      await deletePatient(selected.id);
      setSelected(null);
      void search("");
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Delete failed");
    }
  };

  const handleCreateSubmit = async (name: string, dob: string) => {
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
      setCreateOpen(false);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Create failed");
    }
  };

  return (
    <main style={{ maxWidth: 1000, margin: "2rem auto", padding: "0 1.5rem", fontFamily: "Inter, system-ui" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 16 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700 }}>{t("patients.title")}</h1>
        <div style={{ display: "flex", gap: 8 }}>
          {canWrite && (
            <button onClick={() => setCreateOpen(true)} style={{ padding: "0.5rem 1rem", background: "#16a34a", color: "#fff", border: "none", borderRadius: 6, fontSize: 13 }}>
              + {t("patients.newPatient")}
            </button>
          )}
          {selected && canDelete && (
            <button onClick={() => void handleDelete()} style={{ padding: "0.5rem 1rem", background: "#dc2626", color: "#fff", border: "none", borderRadius: 6, fontSize: 13 }}>
              {t("patients.delete")}
            </button>
          )}
        </div>
      </header>

      <input
        type="text"
        placeholder={t("patients.searchPlaceholder")}
        value={searchTerm}
        onChange={(e) => { setSearchTerm(e.target.value); void search(e.target.value); }}
        style={{ width: "100%", padding: "8px 10px", fontSize: 13, border: "1px solid #d1d5db", borderRadius: 6, marginBottom: 12 }}
      />

      {isLoading && <p style={{ fontSize: 13, color: "#9ca3bf" }}>{t("patients.loading")}</p>}
      {error && <p style={{ fontSize: 13, color: "#dc2626" }}>{error}</p>}

      <div style={{ display: "flex", gap: 16 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "2px solid #e5e7eb" }}>
                <th style={{ padding: "6px 8px" }}>{t("patients.colName")}</th>
                <th style={{ padding: "6px 8px" }}>{t("patients.colDob")}</th>
                <th style={{ padding: "6px 8px" }}>{t("patients.colPhone")}</th>
                <th style={{ padding: "6px 8px" }}>{t("patients.colInsurance")}</th>
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
                  {tabLabel[tab]}
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
            {activeTab === "Emergency Contact" && <EmergencyContactTab patient={selected} onUpdate={handleUpdate} canWrite={canWrite} />}
            {activeTab === "Employment" && <EmploymentTab patient={selected} onUpdate={handleUpdate} canWrite={canWrite} />}
            {activeTab === "Workers' Comp" && <WorkersCompTab patient={selected} onUpdate={handleUpdate} canWrite={canWrite} />}
            {activeTab === "Demographics" && <DemographicsTab patient={selected} onUpdate={handleUpdate} canWrite={canWrite} />}
            {activeTab === "Communication" && <CommunicationTab patient={selected} onUpdate={handleUpdate} canWrite={canWrite} />}
          </div>
        )}
      </div>

      {createOpen && (
        <CreatePatientModal
          onClose={() => setCreateOpen(false)}
          onSubmit={handleCreateSubmit}
        />
      )}
    </main>
  );
}

// ── Create Patient Modal ─────────────────────────────────────────────────────

function CreatePatientModal({ onClose, onSubmit }: { onClose: () => void; onSubmit: (name: string, dob: string) => Promise<void> }) {
  const { t } = useI18n();
  const [name, setName] = useState("");
  const [dob, setDob] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!name.trim()) { setError(t("patients.nameRequired")); return; }
    setSaving(true);
    setError(null);
    try {
      await onSubmit(name.trim(), dob);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Create failed");
      setSaving(false);
    }
  };

  return (
    <DashboardLayout>
      <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16, zIndex: 50 }}>
        <div style={{ width: "100%", maxWidth: 400, background: "white", borderRadius: 8, padding: 24, boxShadow: "0 4px 24px rgba(0,0,0,0.15)" }}>
          <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 16 }}>{t("patients.newPatientModal")}</h2>
          {error && <p style={{ fontSize: 13, color: "#dc2626", marginBottom: 12 }}>{error}</p>}
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div>
              <label htmlFor="pt-fullname" style={{ display: "block", fontSize: 13, fontWeight: 500, color: "#374151", marginBottom: 4 }}>{t("patients.fullName")}</label>
              <input id="pt-fullname"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="John Doe"
                autoFocus
                style={{ width: "100%", padding: "8px 12px", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 14 }}
              />
            </div>
            <div>
              <label htmlFor="pt-dob" style={{ display: "block", fontSize: 13, fontWeight: 500, color: "#374151", marginBottom: 4 }}>{t("patients.dateOfBirth")}</label>
              <input id="pt-dob"
                type="date"
                value={dob}
                onChange={(e) => setDob(e.target.value)}
                style={{ width: "100%", padding: "8px 12px", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 14 }}
              />
            </div>
            <div>
              <label htmlFor="pt-1066" style={{ display: "block", fontSize: 13, fontWeight: 500, color: "#374151", marginBottom: 4 }}>{t("patients.phone")}</label>
              <input id="pt-1066"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="(555) 123-4567"
                style={{ width: "100%", padding: "8px 12px", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 14 }}
              />
            </div>
            <div>
              <label htmlFor="pt-1075" style={{ display: "block", fontSize: 13, fontWeight: 500, color: "#374151", marginBottom: 4 }}>{t("patients.emailField")}</label>
              <input id="pt-1075"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="john@example.com"
                style={{ width: "100%", padding: "8px 12px", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 14 }}
              />
            </div>
          </div>
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 20 }}>
            <button onClick={onClose} disabled={saving} style={{ padding: "8px 16px", border: "1px solid #d1d5db", borderRadius: 6, background: "white", fontSize: 14, cursor: saving ? "default" : "pointer" }}>
              {t("common.cancel")}
            </button>
            <button onClick={() => void handleSubmit()} disabled={saving || !name.trim()} style={{ padding: "8px 16px", borderRadius: 6, border: "none", background: saving || !name.trim() ? "#9ca3af" : "#16a34a", color: "white", fontSize: 14, fontWeight: 500, cursor: saving || !name.trim() ? "default" : "pointer" }}>
              {saving ? "Creating..." : t("patients.createPatient")}
            </button>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
