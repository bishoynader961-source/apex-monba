"use client";

import { useState, useEffect } from "react";
import { Search, Plus, Trash2 } from "lucide-react";
import { SigCodeRead } from "@/types/contracts";
import { listSigCodes, createSigCode, deleteSigCode } from "@/lib/api/dictionaries";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { sigCodeSchema, SigCodeForm } from "@/lib/validations/sigCode";

export default function SigCodeEngine() {
  const [activeMode, setActiveMode] = useState<"LIST" | "ADD">("LIST");
  const [sigs, setSigs] = useState<SigCodeRead[]>([]);
  const [searchQuery, setSearchQuery] = useState("");

  const { register, handleSubmit, reset, watch, setValue, formState: { errors } } = useForm<SigCodeForm>({
    resolver: zodResolver(sigCodeSchema),
    defaultValues: { language: "EN", days_accumulated: "0", offset: 0 },
  });

  const codeValue = watch("code");

  useEffect(() => { loadSigs(); }, []);

  const loadSigs = async () => {
    try { setSigs(await listSigCodes()); } catch (err) { console.error(err); }
  };

  const filteredSigs = sigs.filter(s =>
    s.code.toLowerCase().includes(searchQuery.toLowerCase()) ||
    s.full_text.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const onSubmit = async (data: SigCodeForm) => {
    try {
      await createSigCode(data);
      await loadSigs();
      setActiveMode("LIST");
      reset({ language: "EN", days_accumulated: "0", offset: 0 });
    } catch (err) {
      console.error(err);
      alert("Error saving Sig code");
    }
  };

  const handleDelete = async (id: number) => {
    if (confirm("Delete this Sig Code?")) {
      try { await deleteSigCode(id); await loadSigs(); } catch (err) { console.error(err); }
    }
  };

  return (
    <div className="p-6 h-full flex flex-col gap-6">
      <div className="flex justify-between items-end border-b border-white/10 pb-4">
        <div>
          <h1 className="text-3xl font-bold bg-gradient-to-r from-teal-400 to-emerald-300 bg-clip-text text-transparent">
            Sig Code Engine
          </h1>
          <p className="text-sm text-gray-400 mt-1">Multi-lingual structured dosage instructions</p>
        </div>
        <div className="flex gap-2">
          {activeMode === "ADD" && (
            <button onClick={handleSubmit(onSubmit)} className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg transition-colors text-sm font-medium">
              <Plus size={16} /> Save New Sig
            </button>
          )}
        </div>
      </div>

      <div className="flex space-x-1 bg-white/5 p-1 rounded-lg border border-white/10 w-fit">
        <button onClick={() => setActiveMode("LIST")}
          className={`py-2 px-6 rounded-md text-sm font-medium transition-all duration-200 ${activeMode === "LIST" ? 'bg-teal-600 text-white shadow-lg' : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'}`}>
          Sig Code List
        </button>
        <button onClick={() => { setActiveMode("ADD"); reset({ language: "EN", days_accumulated: "0", offset: 0 }); }}
          className={`py-2 px-6 rounded-md text-sm font-medium transition-all duration-200 ${activeMode === "ADD" ? 'bg-teal-600 text-white shadow-lg' : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'}`}>
          Add New Sig
        </button>
      </div>

      <div className="flex-1 bg-white/5 rounded-xl border border-white/10 overflow-hidden flex flex-col">
        {activeMode === "LIST" ? (
          <>
            <div className="p-4 border-b border-white/10 bg-black/20 flex gap-4 items-center">
              <div className="relative flex-1 max-w-md">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={16} />
                <input type="text" placeholder="Search by code or description..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full bg-black/40 border border-white/10 rounded-md pl-9 p-2 text-sm focus:border-teal-500 focus:ring-1 focus:ring-teal-500 outline-none transition-all" />
              </div>
            </div>
            <div className="flex-1 overflow-auto">
              <table className="w-full text-left border-collapse">
                <thead className="bg-white/5 text-gray-400 text-xs uppercase tracking-wider sticky top-0">
                  <tr>
                    <th className="px-6 py-3 font-medium">Sig Code</th>
                    <th className="px-6 py-3 font-medium">Lang</th>
                    <th className="px-6 py-3 font-medium">Description</th>
                    <th className="px-6 py-3 font-medium text-right">D.A.</th>
                    <th className="px-6 py-3 font-medium text-right">Offset</th>
                    <th className="px-6 py-3 font-medium text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {filteredSigs.map(sig => (
                    <tr key={sig.id} className="hover:bg-white/[0.02] transition-colors">
                      <td className="px-6 py-3 font-mono font-medium text-teal-300">{sig.code}</td>
                      <td className="px-6 py-3 text-sm">{sig.language}</td>
                      <td className="px-6 py-3 text-sm text-gray-300">{sig.full_text}</td>
                      <td className="px-6 py-3 text-sm text-right font-mono">{sig.days_accumulated}</td>
                      <td className="px-6 py-3 text-sm text-right font-mono">{sig.offset}</td>
                      <td className="px-6 py-3 text-right">
                        <button onClick={() => handleDelete(sig.id)} className="text-gray-500 hover:text-red-400 transition-colors p-1">
                          <Trash2 size={16} />
                        </button>
                      </td>
                    </tr>
                  ))}
                  {filteredSigs.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-6 py-8 text-center text-gray-500">No Sig codes found matching &quot;{searchQuery}&quot;</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <form onSubmit={handleSubmit(onSubmit)} className="p-8 max-w-2xl">
            <div className="grid grid-cols-2 gap-6">
              <div className="space-y-1">
                <label className="text-xs text-gray-400 font-medium uppercase tracking-wider">Sig Code (Abbreviation)</label>
                <input type="text" {...register("code", { onChange: (e) => setValue("code", e.target.value.toUpperCase()) })}
                  placeholder="e.g. BID"
                  className="w-full bg-black/40 border border-white/10 rounded-md p-2.5 text-sm focus:border-teal-500 outline-none uppercase font-mono" />
                {errors.code && <span className="text-xs text-red-400">{errors.code.message}</span>}
              </div>

              <div className="space-y-1">
                <label className="text-xs text-gray-400 font-medium uppercase tracking-wider">Language</label>
                <select {...register("language")}
                  className="w-full bg-black/40 border border-white/10 rounded-md p-2.5 text-sm focus:border-teal-500 outline-none">
                  <option value="EN">English (EN)</option>
                  <option value="ES">Spanish (ES)</option>
                </select>
              </div>

              <div className="col-span-2 space-y-1">
                <label className="text-xs text-gray-400 font-medium uppercase tracking-wider">Full Instruction Text</label>
                <textarea rows={3} {...register("full_text")} placeholder="e.g. Take one tablet by mouth twice daily"
                  className="w-full bg-black/40 border border-white/10 rounded-md p-2.5 text-sm focus:border-teal-500 outline-none resize-none" />
                {errors.full_text && <span className="text-xs text-red-400">{errors.full_text.message}</span>}
              </div>

              <div className="space-y-1">
                <label className="text-xs text-gray-400 font-medium uppercase tracking-wider">Days Accumulated (D.A.) Multiplier</label>
                <input type="number" step="0.01" {...register("days_accumulated")}
                  className="w-full bg-black/40 border border-white/10 rounded-md p-2.5 text-sm focus:border-teal-500 outline-none font-mono" />
              </div>

              <div className="space-y-1">
                <label className="text-xs text-gray-400 font-medium uppercase tracking-wider">Days Supply Offset</label>
                <input type="number" {...register("offset", { valueAsNumber: true })}
                  className="w-full bg-black/40 border border-white/10 rounded-md p-2.5 text-sm focus:border-teal-500 outline-none font-mono" />
              </div>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
