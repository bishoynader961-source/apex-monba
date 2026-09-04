"use client";

import { useState, useEffect, useMemo } from "react";
import { Search, Plus, Edit2, Trash2, Save } from "lucide-react";
import { PriceCodeRead } from "@/types/contracts";
import { listPriceCodes, createPriceCode, updatePriceCode, deletePriceCode } from "@/lib/api/dictionaries";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { priceCodeSchema, PriceCodeForm } from "@/lib/validations/priceCode";

function computePreview(cost: number, data: PriceCodeForm): { price: number; clamped: boolean } {
  const markup = Number(data.markup_pct) || 0;
  const factor = Number(data.cost_factor_pct) || 0;
  const fee = Number(data.dispensing_fee) || 0;
  const min = Number(data.min_price) || 0;
  const max = Number(data.max_price) || 999999.99;

  let computed: number;
  if (markup > 0) { computed = cost * (markup / 100) + fee; }
  else if (factor > 0) { computed = cost * (factor / 100) + fee; }
  else { computed = cost + fee; }

  let clamped = false;
  if (computed < min) { computed = min; clamped = true; }
  if (computed > max) { computed = max; clamped = true; }

  return { price: Math.round(computed * 100) / 100, clamped };
}

export default function PriceCodeEngine() {
  const [codes, setCodes] = useState<PriceCodeRead[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [acqCost, setAcqCost] = useState<number>(0);

  const { register, handleSubmit, watch, reset, formState: { errors } } = useForm<PriceCodeForm>({
    resolver: zodResolver(priceCodeSchema),
    defaultValues: { price_level: "AWP", cost_factor_pct: "100", markup_pct: "0.00", dispensing_fee: "0.00", min_price: "0.00", max_price: "999999.99", price: "0.00" },
  });

  const formValues = watch();

  const preview = useMemo(() => computePreview(acqCost, formValues), [acqCost, formValues]);

  useEffect(() => { loadCodes(); }, []);

  const loadCodes = async () => {
    try { setCodes(await listPriceCodes()); } catch (err) { console.error(err); }
  };

  const filtered = codes.filter(c =>
    c.code.toLowerCase().includes(searchQuery.toLowerCase()) ||
    c.description.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleSelect = (id: number) => {
    const pc = codes.find(c => c.id === id);
    if (pc) {
      setSelectedId(id);
      reset({
        code: pc.code, description: pc.description, price: pc.price ?? "0.00",
        price_level: pc.price_level ?? "AWP", cost_factor_pct: pc.cost_factor_pct ?? "100",
        markup_pct: pc.markup_pct ?? "0.00", dispensing_fee: pc.dispensing_fee ?? "0.00",
        min_price: pc.min_price ?? "0.00", max_price: pc.max_price ?? "999999.99",
      });
      setIsEditing(false);
      setAcqCost(0);
    }
  };

  const handleNew = () => {
    setSelectedId(null);
    reset({ code: "", description: "", price: "0.00", price_level: "AWP", cost_factor_pct: "100", dispensing_fee: "0.00", min_price: "0.00", max_price: "999999.99", markup_pct: "0.00" });
    setIsEditing(true);
    setAcqCost(0);
  };

  const onSubmit = async (data: PriceCodeForm) => {
    try {
      if (selectedId) { await updatePriceCode(selectedId, data as any); }
      else { await createPriceCode(data as any); }
      await loadCodes();
      setIsEditing(false);
    } catch (err) { console.error(err); alert("Error saving price code"); }
  };

  const handleDelete = async () => {
    if (!selectedId) return;
    if (confirm("Delete this price code?")) {
      await deletePriceCode(selectedId);
      setSelectedId(null); reset({}); await loadCodes();
    }
  };

  return (
    <div className="p-6 h-full flex flex-col gap-6">
      <div className="flex justify-between items-end border-b border-white/10 pb-4">
        <div>
          <h1 className="text-3xl font-bold bg-gradient-to-r from-amber-400 to-orange-300 bg-clip-text text-transparent">
            Price Code Engine
          </h1>
          <p className="text-sm text-gray-400 mt-1">Multi-tier pricing configuration with live formula preview</p>
        </div>
        <div className="flex gap-2">
          {isEditing ? (
            <>
              <button onClick={handleSubmit(onSubmit)} className="flex items-center gap-2 bg-amber-600 hover:bg-amber-500 text-white px-4 py-2 rounded-lg transition-colors text-sm font-medium">
                <Save size={16} /> Save
              </button>
              <button onClick={() => { setIsEditing(false); if (!selectedId) reset({}); }} className="flex items-center gap-2 bg-white/5 hover:bg-white/10 px-4 py-2 rounded-lg transition-colors text-sm font-medium">
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
        </div>
      </div>

      <div className="flex gap-6 h-full min-h-0">
        {/* Sidebar */}
        <div className="w-1/4 bg-white/5 rounded-xl overflow-hidden border border-white/10 flex flex-col">
          <div className="p-3 bg-white/5 border-b border-white/10">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={14} />
              <input type="text" placeholder="Search codes..." value={searchQuery} onChange={e => setSearchQuery(e.target.value)}
                className="w-full bg-black/40 border border-white/10 rounded-md pl-8 pr-3 py-1.5 text-sm focus:border-amber-500 outline-none" />
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {filtered.map(pc => (
              <button key={pc.id} onClick={() => handleSelect(pc.id)}
                className={`w-full text-left px-3 py-2 rounded-md text-sm transition-colors ${selectedId === pc.id ? 'bg-amber-600/30 text-amber-300' : 'hover:bg-white/5'}`}>
                <div className="font-medium truncate">{pc.code}</div>
                <div className="text-xs text-gray-500 truncate">{pc.description}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Main Content */}
        <div className="w-3/4 flex flex-col gap-4 overflow-y-auto">
          {!selectedId && !isEditing ? (
            <div className="h-full flex items-center justify-center text-gray-500">Select a price code or create a new one.</div>
          ) : (
            <>
              {/* Acquisition Cost for Preview */}
              <div className="bg-white/5 rounded-xl border border-white/10 p-4">
                <label className="text-xs text-gray-400 font-medium uppercase tracking-wider">Acquisition Cost (for preview)</label>
                <input type="number" step="0.01" value={acqCost || ""} onChange={e => setAcqCost(parseFloat(e.target.value) || 0)}
                  className="mt-1 w-48 bg-black/40 border border-white/10 rounded-md p-2.5 text-sm focus:border-amber-500 outline-none font-mono" placeholder="0.00" />
              </div>

              {/* Editable Grid */}
              <div className="bg-white/5 rounded-xl border border-white/10 overflow-hidden">
                <table className="w-full text-left border-collapse text-sm">
                  <thead className="bg-white/5 text-gray-400 text-xs uppercase tracking-wider">
                    <tr>
                      <th className="px-4 py-3 font-medium">Code</th>
                      <th className="px-4 py-3 font-medium">Description</th>
                      <th className="px-4 py-3 font-medium">Price Level</th>
                      <th className="px-4 py-3 font-medium text-right">Cost Factor %</th>
                      <th className="px-4 py-3 font-medium text-right">Markup %</th>
                      <th className="px-4 py-3 font-medium text-right">Dispensing Fee</th>
                      <th className="px-4 py-3 font-medium text-right">Min Price</th>
                      <th className="px-4 py-3 font-medium text-right">Max Price</th>
                      <th className="px-4 py-3 font-medium text-right">Preview Price</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/5">
                    <tr className="hover:bg-white/[0.02]">
                      <td className="px-4 py-2">
                        <input disabled={!isEditing} type="text" {...register("code")}
                          className="w-full bg-black/40 border border-white/10 rounded px-2 py-1.5 text-sm font-mono disabled:opacity-50 focus:border-amber-500 outline-none" />
                        {errors.code && <span className="text-xs text-red-400">{errors.code.message}</span>}
                      </td>
                      <td className="px-4 py-2">
                        <input disabled={!isEditing} type="text" {...register("description")}
                          className="w-full bg-black/40 border border-white/10 rounded px-2 py-1.5 text-sm disabled:opacity-50 focus:border-amber-500 outline-none" />
                        {errors.description && <span className="text-xs text-red-400">{errors.description.message}</span>}
                      </td>
                      <td className="px-4 py-2">
                        <select disabled={!isEditing} {...register("price_level")}
                          className="w-full bg-black/40 border border-white/10 rounded px-2 py-1.5 text-sm disabled:opacity-50 focus:border-amber-500 outline-none">
                          <option value="AWP">AWP</option>
                          <option value="WAC">WAC</option>
                          <option value="MAC">MAC</option>
                          <option value="Direct Cost">Direct Cost</option>
                        </select>
                      </td>
                      <td className="px-4 py-2">
                        <input disabled={!isEditing} type="number" step="0.01" {...register("cost_factor_pct")}
                          className="w-full bg-black/40 border border-white/10 rounded px-2 py-1.5 text-sm text-right font-mono disabled:opacity-50 focus:border-amber-500 outline-none" />
                      </td>
                      <td className="px-4 py-2">
                        <input disabled={!isEditing} type="number" step="0.01" {...register("markup_pct")}
                          className="w-full bg-black/40 border border-white/10 rounded px-2 py-1.5 text-sm text-right font-mono disabled:opacity-50 focus:border-amber-500 outline-none" />
                      </td>
                      <td className="px-4 py-2">
                        <input disabled={!isEditing} type="number" step="0.01" {...register("dispensing_fee")}
                          className="w-full bg-black/40 border border-white/10 rounded px-2 py-1.5 text-sm text-right font-mono disabled:opacity-50 focus:border-amber-500 outline-none" />
                      </td>
                      <td className="px-4 py-2">
                        <input disabled={!isEditing} type="number" step="0.01" {...register("min_price")}
                          className="w-full bg-black/40 border border-white/10 rounded px-2 py-1.5 text-sm text-right font-mono disabled:opacity-50 focus:border-amber-500 outline-none" />
                      </td>
                      <td className="px-4 py-2">
                        <input disabled={!isEditing} type="number" step="0.01" {...register("max_price")}
                          className="w-full bg-black/40 border border-white/10 rounded px-2 py-1.5 text-sm text-right font-mono disabled:opacity-50 focus:border-amber-500 outline-none" />
                      </td>
                      <td className="px-4 py-2 text-right">
                        <span className={`font-mono font-bold ${preview.clamped ? 'text-amber-400' : 'text-emerald-400'}`}>
                          ${preview.price.toFixed(2)}
                        </span>
                        {preview.clamped && <span className="text-xs text-amber-500 ml-1">(clamped)</span>}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              {/* All Codes Grid (read-only overview) */}
              {!isEditing && (
                <div className="bg-white/5 rounded-xl border border-white/10 overflow-hidden">
                  <div className="px-4 py-3 bg-white/5 border-b border-white/10 text-xs text-gray-400 uppercase tracking-wider font-medium">
                    All Price Codes ({codes.length})
                  </div>
                  <div className="overflow-auto max-h-64">
                    <table className="w-full text-left border-collapse text-sm">
                      <thead className="bg-white/5 text-gray-400 text-xs uppercase tracking-wider sticky top-0">
                        <tr>
                          <th className="px-4 py-2 font-medium">Code</th>
                          <th className="px-4 py-2 font-medium">Level</th>
                          <th className="px-4 py-2 font-medium text-right">Factor %</th>
                          <th className="px-4 py-2 font-medium text-right">Markup %</th>
                          <th className="px-4 py-2 font-medium text-right">Fee</th>
                          <th className="px-4 py-2 font-medium text-right">Min</th>
                          <th className="px-4 py-2 font-medium text-right">Max</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/5">
                        {codes.map(pc => (
                          <tr key={pc.id} onClick={() => handleSelect(pc.id)} className="hover:bg-white/[0.02] cursor-pointer transition-colors">
                            <td className="px-4 py-2 font-mono text-amber-300">{pc.code}</td>
                            <td className="px-4 py-2 text-xs">{pc.price_level || "—"}</td>
                            <td className="px-4 py-2 text-right font-mono">{pc.cost_factor_pct}</td>
                            <td className="px-4 py-2 text-right font-mono">{pc.markup_pct}</td>
                            <td className="px-4 py-2 text-right font-mono">{pc.dispensing_fee}</td>
                            <td className="px-4 py-2 text-right font-mono">{pc.min_price}</td>
                            <td className="px-4 py-2 text-right font-mono">{pc.max_price}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
