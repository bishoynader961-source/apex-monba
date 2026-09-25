"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { DashboardLayout } from "@/components/DashboardLayout";
import { RouteGuard } from "@/components/RouteGuard";
import { useCan } from "@/stores/authStore";
import { useVendorsStore } from "@/stores/vendorsStore";
import type { Vendor, VendorItem, PurchaseHistoryEntry } from "@/lib/api/vendors";
import { getVendorItems } from "@/lib/api/vendors";
import { DataTable } from "@/components/DataTable";
import type { Column } from "@/components/DataTable";
import {
  Building2, Plus, Search, Phone, Mail, Wallet,
  X, Check, Loader2, PackagePlus, AlertTriangle,
  Edit3, Trash2, History, Package, ChevronDown, ChevronUp,
} from "lucide-react";

type DetailTab = "items" | "purchases";

export default function VendorsPage() {
  const canWrite = useCan("inventory.write");
  const canRead = useCan("inventory.read");

  const {
    vendors, selected, purchases, isLoading, error, feedback,
    fetchVendors, setSelected, fetchPurchases, addVendor, editVendor,
    deactivateVendor, receiveStock, clearFeedback,
  } = useVendorsStore();

  const [search, setSearch] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [showReceive, setShowReceive] = useState(false);
  const [detailTab, setDetailTab] = useState<DetailTab>("items");
  const [vendorItems, setVendorItems] = useState<VendorItem[]>([]);

  const [createForm, setCreateForm] = useState({ company_name: "", contact_phone: "", contact_email: "", tax_id: "", address: "", notes: "" });
  const [editForm, setEditForm] = useState({ company_name: "", contact_phone: "", contact_email: "", tax_id: "", address: "", notes: "" });
  const [receiveForm, setReceiveForm] = useState({ product_name: "", quantity: 1, unit_cost: 0, invoice_ref: "", notes: "" });

  useEffect(() => { void fetchVendors(search || undefined); }, [fetchVendors, search]);

  const loadDetail = useCallback(async (v: Vendor) => {
    setSelected(v);
    setDetailTab("items");
    try {
      const items = await getVendorItems(v.id);
      setVendorItems(items);
    } catch {
      setVendorItems([]);
    }
  }, [setSelected]);

  const switchTab = useCallback(async (tab: DetailTab) => {
    setDetailTab(tab);
    if (tab === "purchases" && selected) {
      await fetchPurchases(selected.id);
    }
  }, [selected, fetchPurchases]);

  const handleCreate = async () => {
    await addVendor(createForm);
    setShowCreate(false);
    setCreateForm({ company_name: "", contact_phone: "", contact_email: "", tax_id: "", address: "", notes: "" });
  };

  const handleEdit = async () => {
    if (!selected) return;
    await editVendor(selected.id, editForm);
    setShowEdit(false);
  };

  const handleReceive = async () => {
    if (!selected) return;
    await receiveStock({ vendor_id: selected.id, ...receiveForm });
    setShowReceive(false);
    setReceiveForm({ product_name: "", quantity: 1, unit_cost: 0, invoice_ref: "", notes: "" });
  };

  const openEdit = (v: Vendor) => {
    setEditForm({
      company_name: v.company_name,
      contact_phone: v.contact_phone ?? "",
      contact_email: v.contact_email ?? "",
      tax_id: v.tax_id ?? "",
      address: v.address ?? "",
      notes: v.notes ?? "",
    });
    setShowEdit(true);
  };

  const columns = useMemo<Column<Vendor>[]>(() => [
    { key: "company_name", header: "Company", render: (row) => (
      <div>
        <p className="font-semibold text-gray-800 dark:text-gray-100 text-sm">{row.company_name}</p>
        {row.tax_id && <p className="text-xs text-gray-500">TIN: {row.tax_id}</p>}
      </div>
    )},
    { key: "contact_phone", header: "Phone", render: (row) => row.contact_phone || "—" },
    { key: "contact_email", header: "Email", render: (row) => row.contact_email || "—" },
    { key: "balance_due", header: "Balance Due", render: (row) => (
      <span className="text-orange-400 font-medium">
        ${row.balance_due.toLocaleString(undefined, { minimumFractionDigits: 2 })}
      </span>
    ), className: "text-right" },
    { key: "is_active", header: "Status", render: (row) => (
      <span className={`text-xs px-2 py-0.5 rounded-full ${row.is_active ? "bg-green-900/30 text-green-400" : "bg-gray-800 text-gray-500"}`}>
        {row.is_active ? "Active" : "Inactive"}
      </span>
    )},
  ], []);

  return (
    <DashboardLayout>
      <RouteGuard permission="vendors.read">
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-800 dark:text-gray-100 flex items-center gap-3">
              <Building2 className="w-7 h-7 text-blue-400" />
              Vendor Management
            </h1>
            <p className="text-gray-600 dark:text-gray-400 text-sm mt-1">Manage supplier directory and receive shipments</p>
          </div>
          {canWrite && (
            <button
              id="btn-create-vendor"
              onClick={() => setShowCreate(true)}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md font-medium transition-colors text-sm"
            >
              <Plus className="w-4 h-4" /> Add Vendor
            </button>
          )}
        </div>

        {/* Feedback */}
        {feedback && (
          <div className={`flex items-center gap-3 p-3 rounded-md border text-sm ${
            feedback.type === "success"
              ? "bg-green-900/20 border-green-600/30 text-green-400"
              : "bg-red-900/20 border-red-600/30 text-red-400"
          }`}>
            {feedback.type === "success" ? <Check className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
            {feedback.msg}
            <button onClick={clearFeedback} className="ml-auto"><X className="w-4 h-4" /></button>
          </div>
        )}

        {error && (
          <div className="flex items-center gap-3 p-3 rounded-md border text-sm bg-red-900/20 border-red-600/30 text-red-400">
            <AlertTriangle className="w-4 h-4" /> {error}
            <button onClick={() => useVendorsStore.setState({ error: null })} className="ml-auto"><X className="w-4 h-4" /></button>
          </div>
        )}

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 w-4 h-4" />
          <input
            id="vendor-search"
            className="w-full pl-9 pr-4 py-2.5 bg-[#0d0d20] border border-gray-700 rounded-md text-gray-800 dark:text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            placeholder="Search vendors..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        {/* Main Content: Grid + Detail Panel */}
        <div className="flex gap-6">
          {/* Vendor Grid */}
          <div className={`${selected ? "w-1/2" : "w-full"} transition-all`}>
            <DataTable
              columns={columns}
              data={vendors}
              keyExtractor={(row) => row.id}
              loading={isLoading}
              emptyMessage="No vendors found."
              onRowClick={loadDetail}
              selection={{
                selectedKeys: selected ? new Set([selected.id]) : new Set(),
                onSelectionChange: (keys) => {
                  if (keys.size > 0) {
                    const v = vendors.find((vendor) => vendor.id === Array.from(keys)[0]);
                    if (v) loadDetail(v);
                  }
                },
              }}
              actions={canWrite ? {
                header: "Actions",
                render: (row) => (
                  <div className="flex gap-2">
                    <button
                      onClick={(e) => { e.stopPropagation(); setSelected(row); setShowReceive(true); }}
                      className="text-xs text-blue-400 hover:text-blue-300"
                    >
                      Receive
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); openEdit(row); }}
                      className="text-xs text-gray-400 hover:text-gray-300"
                    >
                      Edit
                    </button>
                  </div>
                )
              } : undefined}
              className="bg-[#1a1a2e] border border-gray-800"
            />
          </div>

          {/* Detail Panel */}
          {selected && (
            <div className="w-1/2 bg-[#1a1a2e] border border-gray-800 rounded-lg p-5 sticky top-6 self-start max-h-[calc(100vh-8rem)] overflow-y-auto">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-bold text-gray-800 dark:text-gray-100">{selected.company_name}</h2>
                <button onClick={() => setSelected(null)} className="text-gray-500 hover:text-gray-300">
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Vendor Info */}
              <div className="grid grid-cols-2 gap-3 text-sm mb-4">
                {selected.contact_phone && (
                  <div className="flex items-center gap-2 text-gray-600 dark:text-gray-400">
                    <Phone className="w-4 h-4" /> {selected.contact_phone}
                  </div>
                )}
                {selected.contact_email && (
                  <div className="flex items-center gap-2 text-gray-600 dark:text-gray-400">
                    <Mail className="w-4 h-4" /> {selected.contact_email}
                  </div>
                )}
                <div className="flex items-center gap-2 text-orange-400 font-medium">
                  <Wallet className="w-4 h-4" /> ${selected.balance_due.toFixed(2)} due
                </div>
                {selected.address && (
                  <div className="text-gray-600 dark:text-gray-400 text-xs">Address: {selected.address}</div>
                )}
                {selected.notes && (
                  <div className="col-span-2 text-gray-500 text-xs italic">{selected.notes}</div>
                )}
              </div>

              {/* Action Buttons */}
              {canWrite && (
                <div className="flex gap-2 mb-4">
                  <button
                    onClick={() => setShowReceive(true)}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs rounded-md transition-colors"
                  >
                    <PackagePlus className="w-3.5 h-3.5" /> Receive Shipment
                  </button>
                  <button
                    onClick={() => openEdit(selected)}
                    className="flex items-center gap-1.5 px-3 py-1.5 border border-gray-700 text-gray-300 hover:bg-gray-800 text-xs rounded-md transition-colors"
                  >
                    <Edit3 className="w-3.5 h-3.5" /> Edit
                  </button>
                  {selected.is_active === 1 && (
                    <button
                      onClick={() => void deactivateVendor(selected.id)}
                      className="flex items-center gap-1.5 px-3 py-1.5 border border-red-800 text-red-400 hover:bg-red-900/20 text-xs rounded-md transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" /> Deactivate
                    </button>
                  )}
                </div>
              )}

              {/* Tabs */}
              <div className="flex border-b border-gray-800 mb-4">
                <button
                  onClick={() => void switchTab("items")}
                  className={`flex items-center gap-1.5 px-4 py-2 text-xs font-medium border-b-2 transition-colors ${
                    detailTab === "items"
                      ? "border-blue-500 text-blue-400"
                      : "border-transparent text-gray-500 hover:text-gray-300"
                  }`}
                >
                  <Package className="w-3.5 h-3.5" /> Items ({vendorItems.length})
                </button>
                <button
                  onClick={() => void switchTab("purchases")}
                  className={`flex items-center gap-1.5 px-4 py-2 text-xs font-medium border-b-2 transition-colors ${
                    detailTab === "purchases"
                      ? "border-blue-500 text-blue-400"
                      : "border-transparent text-gray-500 hover:text-gray-300"
                  }`}
                >
                  <History className="w-3.5 h-3.5" /> Purchase History ({purchases.length})
                </button>
              </div>

              {/* Tab Content */}
              {detailTab === "items" ? (
                vendorItems.length === 0 ? (
                  <p className="text-gray-500 text-sm text-center py-8">No items recorded for this vendor.</p>
                ) : (
                  <div className="space-y-2">
                    {vendorItems.map((item) => (
                      <div key={item.id} className="flex items-center justify-between p-3 bg-[#0d0d20] border border-gray-800 rounded-md">
                        <div>
                          <p className="text-sm text-gray-800 dark:text-gray-200 font-medium">{item.product_name}</p>
                          {item.sku && <p className="text-xs text-gray-500">SKU: {item.sku}</p>}
                        </div>
                        <div className="text-right">
                          {item.unit_cost != null && (
                            <p className="text-sm text-orange-400">${item.unit_cost.toFixed(2)}</p>
                          )}
                          {item.is_primary === 1 && (
                            <span className="text-xs text-green-400">Primary</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )
              ) : (
                purchases.length === 0 ? (
                  <p className="text-gray-500 text-sm text-center py-8">No purchase history.</p>
                ) : (
                  <div className="space-y-2">
                    {purchases.map((p) => (
                      <div key={p.id} className="p-3 bg-[#0d0d20] border border-gray-800 rounded-md">
                        <div className="flex items-center justify-between mb-1">
                          <p className="text-sm text-gray-800 dark:text-gray-200 font-medium">{p.product_name}</p>
                          <p className="text-sm text-orange-400">${p.total_cost.toFixed(2)}</p>
                        </div>
                        <div className="flex items-center gap-4 text-xs text-gray-500">
                          <span>Qty: {p.quantity}</span>
                          <span>Unit: ${p.unit_cost.toFixed(2)}</span>
                          {p.invoice_ref && <span>Inv: {p.invoice_ref}</span>}
                          {p.received_date && <span>{p.received_date}</span>}
                        </div>
                        {p.received_by && (
                          <p className="text-xs text-gray-600 mt-1">Received by: {p.received_by}</p>
                        )}
                      </div>
                    ))}
                  </div>
                )
              )}
            </div>
          )}
        </div>

        {/* Create Vendor Modal */}
        {showCreate && (
          <Modal title="Add New Vendor" onClose={() => setShowCreate(false)}>
            <VendorForm form={createForm} onChange={setCreateForm} />
            <div className="flex gap-3 mt-5">
              <button onClick={() => setShowCreate(false)} className="flex-1 py-2 border border-gray-700 text-gray-300 hover:bg-gray-800 rounded-md text-sm">Cancel</button>
              <button onClick={() => void handleCreate()} className="flex-1 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-sm font-medium">Create Vendor</button>
            </div>
          </Modal>
        )}

        {/* Edit Vendor Modal */}
        {showEdit && selected && (
          <Modal title="Edit Vendor" onClose={() => setShowEdit(false)}>
            <VendorForm form={editForm} onChange={setEditForm} />
            <div className="flex gap-3 mt-5">
              <button onClick={() => setShowEdit(false)} className="flex-1 py-2 border border-gray-700 text-gray-300 hover:bg-gray-800 rounded-md text-sm">Cancel</button>
              <button onClick={() => void handleEdit()} className="flex-1 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-sm font-medium">Save Changes</button>
            </div>
          </Modal>
        )}

        {/* Receive Shipment Modal */}
        {showReceive && selected && (
          <Modal title="Receive Shipment" onClose={() => setShowReceive(false)}>
            <p className="text-sm text-blue-400 mb-4">from <strong>{selected.company_name}</strong></p>
            <div className="space-y-3">
              {[
                { field: "product_name", label: "Product Name", type: "text" },
                { field: "quantity", label: "Quantity", type: "number" },
                { field: "unit_cost", label: "Unit Cost ($)", type: "number" },
                { field: "invoice_ref", label: "Invoice Reference", type: "text" },
                { field: "notes", label: "Notes", type: "text" },
              ].map(({ field, label, type }) => (
                <div key={field}>
                  <label htmlFor={`receive-${field}`} className="block text-xs text-gray-600 dark:text-gray-400 mb-1">{label}</label>
                  <input
                    id={`receive-${field}`}
                    type={type}
                    step={field.includes("cost") ? "0.01" : undefined}
                    className="w-full bg-[#0d0d20] border border-gray-700 rounded-md px-3 py-2 text-gray-800 dark:text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                    value={(receiveForm as any)[field]}
                    onChange={(e) => setReceiveForm((f) => ({ ...f, [field]: type === "number" ? Number(e.target.value) : e.target.value }))}
                  />
                </div>
              ))}
            </div>
            <div className="flex gap-3 mt-5">
              <button onClick={() => setShowReceive(false)} className="flex-1 py-2 border border-gray-700 text-gray-300 hover:bg-gray-800 rounded-md text-sm">Cancel</button>
              <button onClick={() => void handleReceive()} className="flex-1 py-2 bg-green-600 hover:bg-green-700 text-white rounded-md text-sm font-medium flex items-center justify-center gap-2">
                <PackagePlus className="w-4 h-4" /> Confirm Receive
              </button>
            </div>
          </Modal>
        )}
      </div>
      </RouteGuard>
    </DashboardLayout>
  );
}

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-[#1a1a2e] border border-gray-700 rounded-xl p-6 w-full max-w-md shadow-2xl">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-bold text-gray-800 dark:text-gray-100">{title}</h2>
          <button onClick={onClose}><X className="w-5 h-5 text-gray-600 dark:text-gray-400" /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

function VendorForm({ form, onChange }: { form: Record<string, string>; onChange: (f: any) => void }) {
  return (
    <div className="space-y-3">
      {(["company_name", "contact_phone", "contact_email", "tax_id", "address", "notes"] as const).map((field) => (
        <div key={field}>
          <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1 capitalize" htmlFor="page-field-1">{field.replace("_", " ")}</label>
          <input id="page-field-1"
            className="w-full bg-[#0d0d20] border border-gray-700 rounded-md px-3 py-2 text-gray-800 dark:text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            value={form[field] ?? ""}
            onChange={(e) => onChange((f: any) => ({ ...f, [field]: e.target.value }))}
          />
        </div>
      ))}
    </div>
  );
}
