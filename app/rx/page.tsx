"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { DrugEducationModal } from "@/components/rx/DrugEducationModal";
import { EditRxModal } from "@/components/rx/EditRxModal";
import { EligibilityModal } from "@/components/rx/EligibilityModal";
import { FillsForRxModal } from "@/components/rx/FillsForRxModal";
import { NewRxModal } from "@/components/rx/NewRxModal";
import { PriceCheckModal } from "@/components/rx/PriceCheckModal";
import { RefillModal } from "@/components/rx/RefillModal";
import { ReverseRxModal } from "@/components/rx/ReverseRxModal";
import { TransferRxModal } from "@/components/rx/TransferRxModal";
import { useRxStore } from "@/stores/rxStore";
import { getDispenseLabel } from "@/lib/api/dispense";

const SYSTEM_MENUS = [
  "File", "Rx Processing", "Reports", "Billing", "Inventory",
  "Live Processing", "Financial Analytics", "Utilities",
  "E-Rx/EPCS", "Administration", "User Pref", "Help", "Lock", "Exit",
];

const RX_RIBBON = [
  { label: "New Rx", color: "bg-blue-600 hover:bg-blue-500", key: "newRx" as const },
  { label: "Refill", color: "bg-emerald-600 hover:bg-emerald-500", key: "refill" as const },
  { label: "Edit", color: "bg-amber-600 hover:bg-amber-500", key: "editRx" as const },
  { label: "Rx Processing", color: "bg-purple-600 hover:bg-purple-500", key: null },
  { label: "DUR", color: "bg-red-600 hover:bg-red-500", key: "dur" as const },
  { label: "Reverse Rx", color: "bg-red-800 hover:bg-red-700", key: "reverseRx" as const },
  { label: "Drug Education", color: "bg-teal-600 hover:bg-teal-500", key: "drugEducation" as const },
  { label: "Eligibility", color: "bg-cyan-600 hover:bg-cyan-500", key: "eligibility" as const },
  { label: "COB", color: "bg-indigo-600 hover:bg-indigo-500", key: null },
  { label: "Compound", color: "bg-orange-600 hover:bg-orange-500", key: null },
  { label: "Claim Response", color: "bg-violet-600 hover:bg-violet-500", key: null },
  { label: "Fills for Rx", color: "bg-green-700 hover:bg-green-600", key: "fillsForRx" as const },
  { label: "Transfer Rx", color: "bg-sky-600 hover:bg-sky-500", key: "transferRx" as const },
  { label: "Display/Reprint Label", color: "bg-gray-600 hover:bg-gray-500", key: "reprint" as const },
  { label: "Price Check", color: "bg-yellow-600 hover:bg-yellow-500 text-black", key: "priceCheck" as const },
];

const QUICK_LAUNCH = [
  "Important Contacts",
  "Online Documentation",
  "Eligibility Confirmations",
  "Auto Refill Submissions",
  "Print Screen/Report",
  "Save Screenshot",
];

export default function RxProcessingPage() {
  const router = useRouter();
  const { fillDate, rxNumber, setFillDate, setRxNumber, openModal, lastDispenseResult } = useRxStore();
  const [activeMenu, setActiveMenu] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  };

  const handleRibbonClick = async (key: string | null, label: string) => {
    if (!key) {
      showToast(`${label} — coming soon`);
      return;
    }
    if (key === "reprint") {
      // Reprint label from last dispense
      if (lastDispenseResult) {
        try {
          const blob = await getDispenseLabel(lastDispenseResult.id);
          const url = URL.createObjectURL(blob);
          const w = window.open(url);
          if (w) {
            w.onload = () => w.print();
          }
          showToast("Label sent to printer");
        } catch {
          showToast("Failed to print label");
        }
      } else {
        showToast("No Rx to reprint — submit a prescription first");
      }
      return;
    }
    if (key === "dur" && rxNumber) {
      // DUR on current Rx — navigate to it or show result
      showToast("DUR check — viewing current Rx alerts");
    }
    openModal(key as import("@/stores/rxStore").ActiveModal);
  };

  return (
    <div className="h-screen flex flex-col bg-gray-950 text-white">
      {/* System Menu Bar */}
      <div className="flex items-center bg-gray-900 border-b border-gray-800 px-2 py-1 text-sm shrink-0">
        {SYSTEM_MENUS.map(menu => (
          <div key={menu} className="relative">
            <button
              onClick={() => setActiveMenu(activeMenu === menu ? null : menu)}
              onMouseEnter={() => activeMenu && setActiveMenu(menu)}
              className={`px-3 py-1.5 rounded transition-colors ${activeMenu === menu ? 'bg-blue-600 text-white' : 'text-gray-300 hover:bg-white/10'}`}
            >
              {menu}
            </button>
            {activeMenu === menu && (
              <div className="absolute top-full left-0 mt-1 bg-gray-800 border border-gray-700 rounded-lg shadow-xl py-1 min-w-[200px] z-50">
                {menu === "File" && (
                  <>
                    <button className="w-full text-left px-4 py-2 text-sm hover:bg-blue-600/30" onClick={() => { setActiveMenu(null); router.push("/patients"); }}>New Patient</button>
                    <button className="w-full text-left px-4 py-2 text-sm hover:bg-blue-600/30" onClick={() => { setActiveMenu(null); router.push("/patients"); }}>Open Patient</button>
                    <div className="border-t border-gray-700 my-1" />
                    <button className="w-full text-left px-4 py-2 text-sm hover:bg-blue-600/30" onClick={() => { setActiveMenu(null); showToast("Report printed"); }}>Print</button>
                    <div className="border-t border-gray-700 my-1" />
                    <button className="w-full text-left px-4 py-2 text-sm hover:bg-red-600/30 text-red-400" onClick={() => { setActiveMenu(null); router.push("/dashboard"); }}>Exit</button>
                  </>
                )}
                {menu === "Rx Processing" && (
                  <>
                    <button className="w-full text-left px-4 py-2 text-sm hover:bg-blue-600/30" onClick={() => { setActiveMenu(null); openModal("newRx"); }}>New Rx</button>
                    <button className="w-full text-left px-4 py-2 text-sm hover:bg-blue-600/30" onClick={() => { setActiveMenu(null); openModal("refill"); }}>Refill</button>
                    <button className="w-full text-left px-4 py-2 text-sm hover:bg-blue-600/30" onClick={() => { setActiveMenu(null); openModal("editRx"); }}>Edit Rx</button>
                    <button className="w-full text-left px-4 py-2 text-sm hover:bg-blue-600/30" onClick={() => { setActiveMenu(null); openModal("reverseRx"); }}>Cancel Rx</button>
                    <button className="w-full text-left px-4 py-2 text-sm hover:bg-blue-600/30" onClick={() => { setActiveMenu(null); openModal("transferRx"); }}>Transfer</button>
                  </>
                )}
                {menu === "Reports" && (
                  <>
                    <button className="w-full text-left px-4 py-2 text-sm hover:bg-blue-600/30" onClick={() => { setActiveMenu(null); router.push("/dashboard/analytics/demand"); }}>Daily Summary</button>
                    <button className="w-full text-left px-4 py-2 text-sm hover:bg-blue-600/30" onClick={() => { setActiveMenu(null); showToast("Dispensing Log — coming soon"); }}>Dispensing Log</button>
                    <button className="w-full text-left px-4 py-2 text-sm hover:bg-blue-600/30" onClick={() => { setActiveMenu(null); router.push("/dashboard/inventory"); }}>Inventory Report</button>
                    <button className="w-full text-left px-4 py-2 text-sm hover:bg-blue-600/30" onClick={() => { setActiveMenu(null); showToast("Controlled Substances — coming soon"); }}>Controlled Substances</button>
                  </>
                )}
                {menu === "Help" && (
                  <>
                    <button className="w-full text-left px-4 py-2 text-sm hover:bg-blue-600/30" onClick={() => setActiveMenu(null)}>About</button>
                    <button className="w-full text-left px-4 py-2 text-sm hover:bg-blue-600/30" onClick={() => setActiveMenu(null)}>Keyboard Shortcuts</button>
                    <button className="w-full text-left px-4 py-2 text-sm hover:bg-blue-600/30" onClick={() => setActiveMenu(null)}>Documentation</button>
                  </>
                )}
                {menu === "Exit" && (
                  <button className="w-full text-left px-4 py-2 text-sm hover:bg-red-600/30 text-red-400" onClick={() => router.push("/dashboard")}>Exit Rx Processing</button>
                )}
                {!["File", "Rx Processing", "Reports", "Help", "Exit"].includes(menu) && (
                  <div className="px-4 py-2 text-sm text-gray-500 italic">No items</div>
                )}
              </div>
            )}
          </div>
        ))}
        <div className="ml-auto text-xs text-gray-500">F1:Patients | F2:Prescribers | F3:Drugs | F4:Insurance | F6:Price Codes</div>
      </div>

      {/* Metadata Bar */}
      <div className="flex items-center gap-6 bg-gray-900/50 border-b border-gray-800 px-4 py-2 shrink-0">
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-400 font-medium uppercase tracking-wider">Fill Date</label>
          <input type="date" value={fillDate} onChange={e => setFillDate(e.target.value)}
            className="bg-black/40 border border-white/10 rounded px-3 py-1.5 text-sm focus:border-blue-500 outline-none" />
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-400 font-medium uppercase tracking-wider">Rx Number</label>
          <input type="text" value={rxNumber ?? ""} onChange={e => setRxNumber(e.target.value || null)} placeholder="Enter Rx #"
            className="bg-black/40 border border-white/10 rounded px-3 py-1.5 text-sm w-40 focus:border-blue-500 outline-none font-mono" />
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex min-h-0">
        {/* Rx Ribbon */}
        <div className="flex-1 flex flex-col p-4 gap-3 overflow-y-auto">
          <div className="text-xs text-gray-500 uppercase tracking-wider font-medium mb-1">Rx Processing Ribbon</div>
          <div className="grid grid-cols-5 gap-2">
            {RX_RIBBON.map(btn => (
              <button
                key={btn.label}
                onClick={() => void handleRibbonClick(btn.key, btn.label)}
                className={`${btn.color} text-white px-3 py-4 rounded-lg text-sm font-medium transition-colors shadow-md hover:shadow-lg`}
              >
                {btn.label}
              </button>
            ))}
          </div>

          {/* Quick Info Panel */}
          <div className="mt-4 bg-white/5 rounded-xl border border-white/10 p-4 flex-1">
            <div className="text-xs text-gray-500 uppercase tracking-wider font-medium mb-3">Current Rx</div>
            {lastDispenseResult ? (
              <div className="space-y-1 text-sm">
                <div className="font-mono text-blue-400 text-lg">Rx #{lastDispenseResult.rx_number}</div>
                <div className="text-gray-300">{lastDispenseResult.product_name}</div>
                <div className="text-gray-400">Qty: {lastDispenseResult.quantity} | Sig: {lastDispenseResult.sig_code}</div>
                <div className="text-gray-400">Fill: {lastDispenseResult.fill_date} | Refill #{lastDispenseResult.refill_count}/{lastDispenseResult.refills_authorized}</div>
                {lastDispenseResult.days_supply && (
                  <div className="text-gray-400">Days Supply: {lastDispenseResult.days_supply}</div>
                )}
                {lastDispenseResult.allergy_flags.length > 0 && (
                  <div className="text-amber-400 text-xs">Allergy Flags: {lastDispenseResult.allergy_flags.join(", ")}</div>
                )}
                {lastDispenseResult.ddi_alerts.length > 0 && (
                  <div className="text-red-400 text-xs">DDI Alerts: {lastDispenseResult.ddi_alerts.length} warning(s)</div>
                )}
              </div>
            ) : rxNumber ? (
              <div className="text-center text-gray-400 py-8">
                <div className="text-lg font-mono text-blue-400">Rx #{rxNumber}</div>
                <div className="text-sm mt-2">Fill Date: {fillDate}</div>
                <div className="text-sm mt-4 italic">Select an action from the ribbon above</div>
              </div>
            ) : (
              <div className="text-center text-gray-500 py-8 italic">Enter an Rx number or click &quot;New Rx&quot; to begin</div>
            )}
          </div>
        </div>

        {/* Right Quick-Launch Bar */}
        <div className="w-56 bg-white/5 border-l border-white/10 flex flex-col shrink-0">
          <div className="p-3 bg-white/5 border-b border-white/10 text-xs text-gray-500 uppercase tracking-wider font-medium">
            Quick Launch
          </div>
          <div className="flex-1 flex flex-col p-2 gap-1">
            {QUICK_LAUNCH.map(item => (
              <button key={item} className="w-full text-left px-3 py-2.5 rounded-md text-sm text-gray-300 hover:bg-white/10 hover:text-white transition-colors">
                {item}
              </button>
            ))}
          </div>
          <div className="p-3 border-t border-white/10">
            <button onClick={() => router.push("/dashboard")} className="w-full px-3 py-2 bg-red-900/50 hover:bg-red-900/80 text-red-300 rounded-md text-sm transition-colors">
              Exit to Dashboard
            </button>
          </div>
        </div>
      </div>

      {/* Modals */}
      <NewRxModal />
      <RefillModal />
      <EditRxModal />
      <ReverseRxModal />
      <EligibilityModal />
      <TransferRxModal />
      <PriceCheckModal />
      <FillsForRxModal />
      <DrugEducationModal />

      {/* Toast */}
      {toast && (
        <div className="fixed bottom-4 right-4 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-sm text-white shadow-lg z-50 animate-pulse">
          {toast}
        </div>
      )}
    </div>
  );
}
