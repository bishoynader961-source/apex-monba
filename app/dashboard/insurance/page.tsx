"use client";

import { useState, useEffect } from "react";
import { Save, Trash2, X, RefreshCw, Edit, Plus } from "lucide-react";
import { InsurancePlanRead } from "@/types/contracts";
import { listPlans, createPlan, updatePlan, deletePlan } from "@/lib/api/insurance";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { insurancePlanSchema, InsurancePlanForm } from "@/lib/validations/insurance";

const TABS = ["General", "Billing", "340B / Over-Rides", "Processor", "EDI Response", "Documents"];

export default function InsurancePlanMaster() {
  const [activeTab, setActiveTab] = useState("General");
  const [plans, setPlans] = useState<InsurancePlanRead[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState<number | null>(null);
  const [isEditing, setIsEditing] = useState(false);

  const { register, handleSubmit, reset, formState: { errors, isDirty } } = useForm<InsurancePlanForm>({
    resolver: zodResolver(insurancePlanSchema),
    defaultValues: {
      active: 1,
      copay_tier: "1",
      copay_amount: "0.00",
      plan_type: "COMMERCIAL",
      pharmacy_verified: 0,
      deductible: "0.00",
      ncpcp_copay: "0.00",
      wc_copay: "0.00",
      co_insurance_pct: "0.00",
      standard_copay: "0.00",
    },
  });

  useEffect(() => { loadPlans(); }, []);

  const loadPlans = async () => {
    try { setPlans(await listPlans()); } catch (err) { console.error(err); }
  };

  const handleSelect = (id: number) => {
    const plan = plans.find(p => p.id === id);
    if (plan) {
      setSelectedPlanId(id);
      reset({
        plan_name: plan.plan_name, plan_code: plan.plan_code ?? "", carrier_id: plan.carrier_id,
        group_number: plan.group_number, bin: plan.bin, pcn: plan.pcn,
        plan_type: plan.plan_type ?? "COMMERCIAL", active: plan.active, copay_tier: plan.copay_tier ?? "1",
        copay_amount: plan.copay_amount ?? "0.00", pharmacy_verified: plan.pharmacy_verified ?? 0,
        deductible: plan.deductible ?? "0.00", ncpcp_copay: plan.ncpcp_copay ?? "0.00",
        wc_copay: plan.wc_copay ?? "0.00", co_insurance_pct: plan.co_insurance_pct ?? "0.00",
        standard_copay: plan.standard_copay ?? "0.00", help_desk_phone: plan.help_desk_phone ?? "",
        fax_number: plan.fax_number ?? "", alt_phone: plan.alt_phone ?? "", contact_name: plan.contact_name ?? "",
        address_line1: plan.address_line1 ?? "", address_line2: plan.address_line2 ?? "",
        city: plan.city ?? "", state: plan.state ?? "", zip: plan.zip ?? "",
        processor_id: plan.processor_id ?? "", notes: plan.notes ?? "",
      });
      setIsEditing(false);
    }
  };

  const handleNew = () => {
    setSelectedPlanId(null);
    reset({
      plan_name: "", plan_code: "", carrier_id: "", group_number: "", bin: "", pcn: "",
      plan_type: "COMMERCIAL", active: 1, copay_tier: "1", copay_amount: "0.00",
      pharmacy_verified: 0, deductible: "0.00", ncpcp_copay: "0.00", wc_copay: "0.00",
      co_insurance_pct: "0.00", standard_copay: "0.00",
      help_desk_phone: "", fax_number: "", alt_phone: "", contact_name: "",
      address_line1: "", address_line2: "", city: "", state: "", zip: "",
      processor_id: "", notes: "",
    });
    setIsEditing(true);
  };

  const onSubmit = async (data: InsurancePlanForm) => {
    try {
      const payload = { ...data, bin: data.bin ?? "", pcn: data.pcn ?? "", group_number: data.group_number ?? "", copay_tier: data.copay_tier ?? "1", copay_amount: data.copay_amount ?? "0.00" } as any;
      if (selectedPlanId) {
        await updatePlan(selectedPlanId, payload);
      } else {
        await createPlan(payload);
      }
      await loadPlans();
      setIsEditing(false);
    } catch (err) {
      console.error(err);
      alert("Error saving plan");
    }
  };

  const handleDelete = async () => {
    if (!selectedPlanId) return;
    if (confirm("Are you sure you want to delete this plan?")) {
      await deletePlan(selectedPlanId);
      setSelectedPlanId(null);
      reset({});
      await loadPlans();
    }
  };

  const FieldError = ({ error }: { error?: string }) =>
    error ? <span className="text-xs text-red-400 mt-1">{error}</span> : null;

  return (
    <div className="p-6 h-full flex flex-col gap-6">
      <div className="flex justify-between items-end border-b border-white/10 pb-4">
        <div>
          <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-400 to-cyan-300 bg-clip-text text-transparent">
            Insurance Plan Master File
          </h1>
          <p className="text-sm text-gray-400 mt-1">Manage payer records, coverage gates, and EDI configurations</p>
        </div>
        <div className="flex gap-2">
          {isEditing ? (
            <>
              <button onClick={handleSubmit(onSubmit)} className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg transition-colors text-sm font-medium">
                <Save size={16} /> Save
              </button>
              <button onClick={() => { setIsEditing(false); if (!selectedPlanId) reset({}); }} className="flex items-center gap-2 bg-white/5 hover:bg-white/10 px-4 py-2 rounded-lg transition-colors text-sm font-medium">
                <X size={16} /> Cancel
              </button>
            </>
          ) : (
            <>
              <button onClick={handleNew} className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg transition-colors text-sm font-medium">
                <Plus size={16} /> Add New
              </button>
              <button onClick={() => setIsEditing(true)} disabled={!selectedPlanId} className="flex items-center gap-2 bg-white/5 hover:bg-white/10 disabled:opacity-50 px-4 py-2 rounded-lg transition-colors text-sm font-medium">
                <Edit size={16} /> Edit
              </button>
              <button onClick={handleDelete} disabled={!selectedPlanId} className="flex items-center gap-2 bg-red-900/50 hover:bg-red-900/80 text-red-300 disabled:opacity-50 px-4 py-2 rounded-lg transition-colors text-sm font-medium">
                <Trash2 size={16} /> Delete
              </button>
            </>
          )}
        </div>
      </div>

      <div className="flex gap-6 h-full">
        {/* Sidebar List */}
        <div className="w-1/4 bg-white/5 rounded-xl overflow-hidden border border-white/10 flex flex-col">
          <div className="p-3 bg-white/5 border-b border-white/10 font-medium text-sm text-gray-300 uppercase tracking-wider">
            Available Plans
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {plans.map(p => (
              <button key={p.id} onClick={() => handleSelect(p.id)}
                className={`w-full text-left px-3 py-2 rounded-md text-sm transition-colors ${selectedPlanId === p.id ? 'bg-blue-600/30 text-blue-300' : 'hover:bg-white/5'}`}>
                <div className="font-medium truncate">{p.plan_name}</div>
                <div className="text-xs text-gray-500 truncate">{p.carrier_id} / {p.plan_code || 'No Code'}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Main Content */}
        <div className="w-3/4 flex flex-col gap-4">
          <div className="flex space-x-1 bg-white/5 p-1 rounded-lg border border-white/10">
            {TABS.map(tab => (
              <button key={tab} onClick={() => setActiveTab(tab)}
                className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-all duration-200 ${activeTab === tab ? 'bg-blue-600 text-white shadow-lg' : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'}`}>
                {tab}
              </button>
            ))}
          </div>

          <div className="flex-1 bg-white/5 rounded-xl border border-white/10 p-6 overflow-y-auto">
            {!selectedPlanId && !isEditing ? (
              <div className="h-full flex items-center justify-center text-gray-500">Select a plan from the list or create a new one.</div>
            ) : (
              <div className="grid grid-cols-2 gap-x-8 gap-y-6">
                {activeTab === "General" && (
                  <>
                    <div className="col-span-2 text-lg font-semibold text-blue-300 border-b border-white/10 pb-2">Plan Identification</div>

                    <div className="space-y-1">
                      <label className="text-xs text-gray-400 font-medium uppercase tracking-wider">Plan Name</label>
                      <input disabled={!isEditing} type="text" {...register("plan_name")}
                        className="w-full bg-black/40 border border-white/10 rounded-md p-2.5 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none transition-all disabled:opacity-50" />
                      <FieldError error={errors.plan_name?.message} />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs text-gray-400 font-medium uppercase tracking-wider">Plan Code</label>
                      <input disabled={!isEditing} type="text" {...register("plan_code")}
                        className="w-full bg-black/40 border border-white/10 rounded-md p-2.5 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none transition-all disabled:opacity-50" />
                    </div>

                    <div className="space-y-1">
                      <label className="text-xs text-gray-400 font-medium uppercase tracking-wider">Carrier ID</label>
                      <input disabled={!isEditing} type="text" {...register("carrier_id")}
                        className="w-full bg-black/40 border border-white/10 rounded-md p-2.5 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none transition-all disabled:opacity-50" />
                      <FieldError error={errors.carrier_id?.message} />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs text-gray-400 font-medium uppercase tracking-wider">Group #</label>
                      <input disabled={!isEditing} type="text" {...register("group_number")}
                        className="w-full bg-black/40 border border-white/10 rounded-md p-2.5 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none transition-all disabled:opacity-50" />
                    </div>

                    <div className="space-y-1">
                      <label className="text-xs text-gray-400 font-medium uppercase tracking-wider">BIN</label>
                      <input disabled={!isEditing} type="text" {...register("bin")}
                        className="w-full bg-black/40 border border-white/10 rounded-md p-2.5 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none transition-all disabled:opacity-50" />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs text-gray-400 font-medium uppercase tracking-wider">PCN</label>
                      <input disabled={!isEditing} type="text" {...register("pcn")}
                        className="w-full bg-black/40 border border-white/10 rounded-md p-2.5 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none transition-all disabled:opacity-50" />
                    </div>

                    <div className="col-span-2 text-lg font-semibold text-blue-300 border-b border-white/10 pb-2 mt-2">Contact Information</div>

                    <div className="space-y-1">
                      <label className="text-xs text-gray-400 font-medium uppercase tracking-wider">Help Desk Phone</label>
                      <input disabled={!isEditing} type="text" {...register("help_desk_phone")}
                        className="w-full bg-black/40 border border-white/10 rounded-md p-2.5 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none transition-all disabled:opacity-50" />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs text-gray-400 font-medium uppercase tracking-wider">Fax Number</label>
                      <input disabled={!isEditing} type="text" {...register("fax_number")}
                        className="w-full bg-black/40 border border-white/10 rounded-md p-2.5 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none transition-all disabled:opacity-50" />
                    </div>

                    <div className="space-y-1">
                      <label className="text-xs text-gray-400 font-medium uppercase tracking-wider">Address Line 1</label>
                      <input disabled={!isEditing} type="text" {...register("address_line1")}
                        className="w-full bg-black/40 border border-white/10 rounded-md p-2.5 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none transition-all disabled:opacity-50" />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs text-gray-400 font-medium uppercase tracking-wider">City, State, Zip</label>
                      <div className="flex gap-2">
                        <input disabled={!isEditing} type="text" placeholder="City" {...register("city")}
                          className="flex-2 bg-black/40 border border-white/10 rounded-md p-2.5 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none transition-all disabled:opacity-50" />
                        <input disabled={!isEditing} type="text" placeholder="ST" {...register("state")}
                          className="w-16 bg-black/40 border border-white/10 rounded-md p-2.5 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none transition-all disabled:opacity-50" />
                        <input disabled={!isEditing} type="text" placeholder="Zip" {...register("zip")}
                          className="w-24 bg-black/40 border border-white/10 rounded-md p-2.5 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none transition-all disabled:opacity-50" />
                      </div>
                    </div>

                    <div className="col-span-2 text-lg font-semibold text-blue-300 border-b border-white/10 pb-2 mt-2">Coverage Details</div>

                    <div className="space-y-1">
                      <label className="text-xs text-gray-400 font-medium uppercase tracking-wider">Standard Copay</label>
                      <input disabled={!isEditing} type="number" step="0.01" {...register("standard_copay")}
                        className="w-full bg-black/40 border border-white/10 rounded-md p-2.5 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none transition-all disabled:opacity-50" />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs text-gray-400 font-medium uppercase tracking-wider">Co-Insurance %</label>
                      <input disabled={!isEditing} type="number" step="0.1" {...register("co_insurance_pct")}
                        className="w-full bg-black/40 border border-white/10 rounded-md p-2.5 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none transition-all disabled:opacity-50" />
                    </div>

                    <div className="col-span-2 space-y-1 mt-2">
                      <label className="text-xs text-gray-400 font-medium uppercase tracking-wider">Notes</label>
                      <textarea disabled={!isEditing} rows={3} {...register("notes")}
                        className="w-full bg-black/40 border border-white/10 rounded-md p-2.5 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none transition-all disabled:opacity-50 resize-none" />
                    </div>
                  </>
                )}

                {activeTab !== "General" && (
                  <div className="col-span-2 flex items-center justify-center h-64 text-gray-500 italic">
                    {activeTab} settings are currently not configured.
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
