"use client";

import { useState, useEffect } from "react";
import { Search, LogOut, Plus, Edit2, Trash2, Save, RefreshCw, Image } from "lucide-react";
import { Medicine, MedicineCreate, MedicineUpdate, PriceCodeRead } from "@/types/contracts";
import { listMedicines, searchMedicines, createMedicine, updateMedicine, deleteMedicine } from "@/lib/api/inventory";
import { listPriceCodes } from "@/lib/api/dictionaries";
import { useRouter } from "next/navigation";
import { useConfirmDrug } from "@/hooks/useDrugConfirm";
import { DashboardLayout } from "@/components/DashboardLayout";

const DEA_SCHEDULES = ["", "II", "III", "IV", "V"];
const DOSAGE_FORMS = ["Tablet", "Capsule", "Solution", "Suspension", "Injection", "Cream", "Ointment", "Inhaler", "Patch", "Drops", "Suppository", "Other"];

function validateNdc(ndc: string): boolean {
  const digits = ndc.replace(/[^0-9]/g, "");
  return digits.length === 11;
}

export default function DrugFilePage() {
  const router = useRouter();
  const [drugs, setDrugs] = useState<Medicine[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [formData, setFormData] = useState<Partial<MedicineCreate>>({});
  const [priceCodes, setPriceCodes] = useState<PriceCodeRead[]>([]);
  const [ndcError, setNdcError] = useState(false);
  const [pillImageUrl, setPillImageUrl] = useState<string | null>(null);
  const { mutateAsync: confirmDrug, isPending: isConfirming } = useConfirmDrug();

  useEffect(() => { loadDrugs(); loadPriceCodes(); }, []);

  const loadDrugs = async () => {
    try {
      if (searchQuery.trim()) {
        const data = await searchMedicines(searchQuery);
        setDrugs(data);
      } else {
        const data = await listMedicines();
        setDrugs(data.items);
      }
    } catch (err) { console.error(err); }
  };

  const loadPriceCodes = async () => {
    try { setPriceCodes(await listPriceCodes()); } catch { /* ignore */ }
  };

  const handleSearch = async () => { await loadDrugs(); };

  const handleSelect = (id: number) => {
    const drug = drugs.find(d => d.id === id);
    if (drug) {
      setSelectedId(id);
      setFormData({
        name: drug.name, price: drug.price, dea_schedule: drug.dea_schedule ?? null,
        wholesale_price: drug.wholesale_price ?? null, category: drug.category ?? null,
        ndc_code: drug.ndc_code ?? null, form: drug.form ?? null, strength: drug.strength ?? null,
        manufacturer_name: drug.manufacturer_name ?? null, therapeutic_class: drug.therapeutic_class ?? null,
        is_generic: drug.is_generic ?? 0, is_controlled: drug.is_controlled ?? 0,
        manufacturer_barcode: drug.manufacturer_barcode, internal_unique_barcode: drug.internal_unique_barcode,
        status: drug.status, expiry_date: drug.expiry_date, vendor_name: drug.vendor_name,
        reorder_threshold: drug.reorder_threshold ?? null,
      });
      setIsEditing(false);
      setNdcError(false);
    }
  };

  const handleNew = () => {
    setSelectedId(null);
    setFormData({
      name: "", price: "0.00", manufacturer_barcode: "", internal_unique_barcode: "",
      status: "active", expiry_date: "", vendor_name: "", dea_schedule: null,
      wholesale_price: null, reorder_threshold: null, category: null,
      ndc_code: null, form: null, strength: null, manufacturer_name: null,
      therapeutic_class: null, is_generic: 0, is_controlled: 0,
    });
    setIsEditing(true);
    setNdcError(false);
  };

  const handleSave = async () => {
    if (!formData.name) return alert("Drug name is required");
    if (formData.ndc_code && !validateNdc(formData.ndc_code)) { setNdcError(true); return; }
    try {
      if (selectedId) {
        await updateMedicine(selectedId, formData as MedicineUpdate);
      } else {
        await createMedicine(formData as MedicineCreate);
      }
      await loadDrugs();
      setIsEditing(false);
      setNdcError(false);
    } catch (err) { console.error(err); alert("Error saving drug"); }
  };

  const handleDelete = async () => {
    if (!selectedId) return;
    if (confirm("Delete this drug?")) {
      await deleteMedicine(selectedId);
      setSelectedId(null); setFormData({}); await loadDrugs();
    }
  };

  const updateField = (field: string, value: unknown) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    if (field === "ndc_code") setNdcError(false);
  };

  return (
    <DashboardLayout>
      <div className="p-6 h-full flex flex-col gap-6">
        <div className="flex justify-between items-end border-b border-white/10 pb-4">
          <div>
            <h1 className="text-3xl font-bold bg-gradient-to-r from-green-400 to-emerald-300 bg-clip-text text-transparent">
              Master Drug File
            </h1>
            <p className="text-sm text-gray-400 mt-1">Drug catalog with NDC validation and pricing linkage</p>
          </div>
          <div className="flex gap-2">
            {isEditing ? (
              <>
                <button onClick={handleSave} className="flex items-center gap-2 bg-green-600 hover:bg-green-500 text-white px-4 py-2 rounded-lg transition-colors text-sm font-medium">
                  <Save size={16} /> Save
                </button>
                <button onClick={() => { setIsEditing(false); if (!selectedId) setFormData({}); setNdcError(false); }} className="flex items-center gap-2 bg-white/5 hover:bg-white/10 px-4 py-2 rounded-lg transition-colors text-sm font-medium">
                  Cancel
                </button>
              </>
            ) : (
              <>
                <button onClick={handleNew} className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg transition-colors text-sm font-medium">
                  <Plus size={16} /> Add New
                </button>
                <button onClick={() => setIsEditing(true)} disabled={!selectedId} className="flex items-center gap-2 bg-white/5 hover:bg-white/10 disabled:opacity-50 px-4 py-2 rounded-lg transition-colors text-sm font-medium">
                  <Edit2 size={16} /> Edit
                </button>
                <button onClick={handleDelete} disabled={!selectedId} className="flex items-center gap-2 bg-red-900/50 hover:bg-red-900/80 text-red-300 disabled:opacity-50 px-4 py-2 rounded-lg transition-colors text-sm font-medium">
                  <Trash2 size={16} /> Delete
                </button>
              </>
            )}
            <button onClick={() => router.push("/")} className="flex items-center gap-2 bg-white/5 hover:bg-white/10 px-4 py-2 rounded-lg transition-colors text-sm font-medium">
              <LogOut size={16} /> Exit
            </button>
          </div>
        </div>

        <div className="flex gap-6 h-full min-h-0">
          {/* Sidebar */}
          <div className="w-1/4 bg-white/5 rounded-xl overflow-hidden border border-white/10 flex flex-col">
            <div className="p-3 bg-white/5 border-b border-white/10 flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={14} />
                <input type="text" placeholder="Search drugs..." value={searchQuery} onChange={e => setSearchQuery(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && handleSearch()}
                  className="w-full bg-black/40 border border-white/10 rounded-md pl-8 pr-3 py-1.5 text-sm focus:border-green-500 outline-none" />
              </div>
              <button onClick={handleSearch} className="px-3 py-1.5 bg-green-600 hover:bg-green-500 rounded-md text-sm text-white transition-colors">Go</button>
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              {drugs.map(d => (
                <button key={d.id} onClick={() => handleSelect(d.id)}
                  className={`w-full text-left px-3 py-2 rounded-md text-sm transition-colors ${selectedId === d.id ? 'bg-green-600/30 text-green-300' : 'hover:bg-white/5'}`}>
                  <div className="font-medium truncate">{d.name}</div>
                  <div className="text-xs text-gray-500 truncate">{d.strength || "—"} {d.form || ""}</div>
                </button>
              ))}
              {drugs.length === 0 && <div className="text-center text-gray-500 text-sm py-4">No drugs found</div>}
            </div>
          </div>

          {/* Main Content */}
          <div className="w-3/4 flex flex-col gap-4 overflow-y-auto">
            {!selectedId && !isEditing ? (
              <div className="h-full flex items-center justify-center text-gray-500">Select a drug or create a new one.</div>
            ) : (
              <div className="grid grid-cols-2 gap-x-8 gap-y-5">
                <div className="col-span-2 text-lg font-semibold text-green-300 border-b border-white/10 pb-2">Drug Identification</div>

                <div className="space-y-1">
                  <label htmlFor="drugs-184" className="text-xs text-gray-400 font-medium uppercase tracking-wider">Drug Name</label>
                  <input id="drugs-184" disabled={!isEditing} type="text" value={formData.name || ""} onChange={e => updateField("name", e.target.value)}
                    className="w-full bg-black/40 border border-white/10 rounded-md p-2.5 text-sm focus:border-green-500 outline-none disabled:opacity-50" />
                </div>

                <div className="space-y-1">
                  <label htmlFor="drugs-190" className="text-xs text-gray-400 font-medium uppercase tracking-wider">NDC Code (11-digit)</label>
                  <div className="flex gap-2">
                    <input id="drugs-190" disabled={!isEditing} type="text" value={formData.ndc_code || ""} onChange={e => updateField("ndc_code", e.target.value)}
                      placeholder="00000-0000-00" maxLength={13}
                      className={`flex-1 bg-black/40 border rounded-md p-2.5 text-sm font-mono focus:outline-none disabled:opacity-50 ${ndcError ? 'border-red-500 focus:border-red-500' : 'border-white/10 focus:border-green-500'}`} />
                    {ndcError && <span className="text-xs text-red-400">Must be exactly 11 digits</span>}
                    {isEditing && formData.ndc_code && (
                      <button
                        type="button"
                        onClick={async () => {
                          try {
                            const result = await confirmDrug(formData.ndc_code || "");
                            if (result.found) {
                              updateField("name", result.name || "");
                              updateField("strength", result.strength || "");
                              updateField("form", result.form || "");
                              updateField("manufacturer_name", result.manufacturer || "");
                              updateField("dea_schedule", result.dea_schedule || "");
                              if (result.pill_image_url) setPillImageUrl(result.pill_image_url);
                            } else {
                              alert("NDC not found in database");
                            }
                          } catch (err) {
                            console.error(err);
                            alert("Confirmation failed");
                          }
                        }}
                        disabled={isConfirming}
                        className="px-3 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-md text-sm font-medium disabled:opacity-50 flex items-center gap-2"
                      >
                        {isConfirming ? (
                          <>
                            <RefreshCw className="animate-spin" size={14} />
                            Confirming...
                          </>
                        ) : (
                          <>
                            <RefreshCw size={14} />
                            Confirm via API
                          </>
                        )}
                      </button>
                    )}
                  </div>
                </div>

                <div className="space-y-1">
                  <label htmlFor="drugs-237" className="text-xs text-gray-400 font-medium uppercase tracking-wider">Strength</label>
                  <input id="drugs-237" disabled={!isEditing} type="text" value={formData.strength || ""} onChange={e => updateField("strength", e.target.value)}
                    placeholder="e.g. 500mg" className="w-full bg-black/40 border border-white/10 rounded-md p-2.5 text-sm focus:border-green-500 outline-none disabled:opacity-50" />
                </div>

                <div className="space-y-1">
                  <label htmlFor="drugs-243" className="text-xs text-gray-400 font-medium uppercase tracking-wider">Dosage Form</label>
                  <select id="drugs-243" disabled={!isEditing} value={formData.form || ""} onChange={e => updateField("form", e.target.value || null)}
                    className="w-full bg-black/40 border border-white/10 rounded-md p-2.5 text-sm focus:border-green-500 outline-none disabled:opacity-50">
                    <option value="">—</option>
                    {DOSAGE_FORMS.map(f => <option key={f} value={f}>{f}</option>)}
                  </select>
                </div>

                <div className="col-span-2 text-lg font-semibold text-green-300 border-b border-white/10 pb-2 mt-2">Classification</div>

                <div className="space-y-1">
                  <label htmlFor="drugs-254" className="text-xs text-gray-400 font-medium uppercase tracking-wider">DEA Schedule</label>
                  <select id="drugs-254" disabled={!isEditing} value={formData.dea_schedule || ""} onChange={e => updateField("dea_schedule", e.target.value || null)}
                    className="w-full bg-black/40 border border-white/10 rounded-md p-2.5 text-sm focus:border-green-500 outline-none disabled:opacity-50">
                    <option value="">—</option>
                    {DEA_SCHEDULES.filter(Boolean).map(s => <option key={s} value={s}>Schedule {s}</option>)}
                  </select>
                </div>

                <div className="space-y-1">
                  <label htmlFor="drugs-263" className="text-xs text-gray-400 font-medium uppercase tracking-wider">Therapeutic Class</label>
                  <input id="drugs-263" disabled={!isEditing} type="text" value={formData.therapeutic_class || ""} onChange={e => updateField("therapeutic_class", e.target.value || null)}
                    className="w-full bg-black/40 border border-white/10 rounded-md p-2.5 text-sm focus:border-green-500 outline-none disabled:opacity-50" />
                </div>

                <div className="space-y-1">
                  <label htmlFor="drugs-269" className="text-xs text-gray-400 font-medium uppercase tracking-wider">Manufacturer</label>
                  <input id="drugs-269" disabled={!isEditing} type="text" value={formData.manufacturer_name || ""} onChange={e => updateField("manufacturer_name", e.target.value || null)}
                    className="w-full bg-black/40 border border-white/10 rounded-md p-2.5 text-sm focus:border-green-500 outline-none disabled:opacity-50" />
                </div>

                {pillImageUrl && (
                  <div className="col-span-2 space-y-1">
                    <span className="text-xs text-gray-400 font-medium uppercase tracking-wider">Pill Image (from API)</span>
                    <div className="flex items-center gap-4">
                      <img src={pillImageUrl} alt="Pill image" className="max-h-40 max-w-40 rounded border border-gray-700" />
                      <button type="button" onClick={() => setPillImageUrl(null)} className="text-sm text-red-400 hover:text-red-300">Remove</button>
                    </div>
                  </div>
                )}

                <div className="space-y-1">
                  <label htmlFor="drugs-285" className="text-xs text-gray-400 font-medium uppercase tracking-wider">Category</label>
                  <input id="drugs-285" disabled={!isEditing} type="text" value={formData.category || ""} onChange={e => updateField("category", e.target.value || null)}
                    className="w-full bg-black/40 border border-white/10 rounded-md p-2.5 text-sm focus:border-green-500 outline-none disabled:opacity-50" />
                </div>

                <div className="space-y-1 flex items-end gap-6">
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" disabled={!isEditing} checked={!!formData.is_generic} onChange={e => updateField("is_generic", e.target.checked ? 1 : 0)}
                      className="rounded border-white/20" />
                    <span className="text-gray-400">Generic</span>
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" disabled={!isEditing} checked={!!formData.is_controlled} onChange={e => updateField("is_controlled", e.target.checked ? 1 : 0)}
                      className="rounded border-white/20" />
                    <span className="text-gray-400">Controlled</span>
                  </label>
                </div>

                <div className="col-span-2 text-lg font-semibold text-green-300 border-b border-white/10 pb-2 mt-2">Pricing</div>

                <div className="space-y-1">
                  <label htmlFor="drugs-306" className="text-xs text-gray-400 font-medium uppercase tracking-wider">Retail Price</label>
                  <input id="drugs-306" disabled={!isEditing} type="number" step="0.01" value={formData.price || "0.00"} onChange={e => updateField("price", e.target.value)}
                    className="w-full bg-black/40 border border-white/10 rounded-md p-2.5 text-sm font-mono focus:border-green-500 outline-none disabled:opacity-50" />
                </div>

                <div className="space-y-1">
                  <label htmlFor="drugs-312" className="text-xs text-gray-400 font-medium uppercase tracking-wider">Wholesale Price</label>
                  <input id="drugs-312" disabled={!isEditing} type="number" step="0.01" value={formData.wholesale_price || ""} onChange={e => updateField("wholesale_price", e.target.value || null)}
                    className="w-full bg-black/40 border border-white/10 rounded-md p-2.5 text-sm font-mono focus:border-green-500 outline-none disabled:opacity-50" />
                </div>

                <div className="col-span-2 text-lg font-semibold text-green-300 border-b border-white/10 pb-2 mt-2">Inventory Info</div>

                <div className="space-y-1">
                  <label htmlFor="drugs-320" className="text-xs text-gray-400 font-medium uppercase tracking-wider">Vendor</label>
                  <input id="drugs-320" disabled={!isEditing} type="text" value={formData.vendor_name || ""} onChange={e => updateField("vendor_name", e.target.value)}
                    className="w-full bg-black/40 border border-white/10 rounded-md p-2.5 text-sm focus:border-green-500 outline-none disabled:opacity-50" />
                </div>

                <div className="space-y-1">
                  <label htmlFor="drugs-326" className="text-xs text-gray-400 font-medium uppercase tracking-wider">Reorder Threshold</label>
                  <input id="drugs-326" disabled={!isEditing} type="number" value={formData.reorder_threshold ?? ""} onChange={e => updateField("reorder_threshold", parseInt(e.target.value) || null)}
                    className="w-full bg-black/40 border border-white/10 rounded-md p-2.5 text-sm font-mono focus:border-green-500 outline-none disabled:opacity-50" />
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
