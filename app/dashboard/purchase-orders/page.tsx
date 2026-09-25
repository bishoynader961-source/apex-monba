"use client";

import { useState, useEffect, useMemo } from "react";
import { useI18n } from "@/components/I18nProvider";
import { DataTable } from "@/components/DataTable";
import type { Column } from "@/components/DataTable";
import {
  listPurchaseOrders,
  createPurchaseOrder,
  addPOItem,
  removePOItem,
  transitionPOStatus,
  deletePurchaseOrder,
  receivePO,
  autoReorder,
  listSuppliers,
  searchSuppliers,
  createSupplier,
  updateSupplier,
  deleteSupplier,
  setPreferredSupplier,
} from "@/lib/api/purchaseOrders";
import { formatMoney, parseMoney } from "@/lib/decimalCurrency";
import type { PurchaseOrderRead, SupplierRead, SupplierCreate } from "@/types/contracts";
import { DashboardLayout } from "@/components/DashboardLayout";

const STATUS_COLORS: Record<string, string> = {
  Draft: "bg-gray-600",
  Submitted: "bg-blue-600",
  Received: "bg-amber-600",
  Closed: "bg-green-600",
};

const EMPTY_SUPPLIER: SupplierCreate = {
  name: "",
  contact_name: "",
  contact_email: "",
  contact_phone: "",
  address: "",
  tax_id: "",
  preferred: 0,
  sku: "",
  min_stock_level: 0,
  lead_time_days: 0,
};

type SupplierModalMode = "list" | "create" | "edit";

export default function PurchaseOrdersPage() {
  const { t } = useI18n();
  const [orders, setOrders] = useState<PurchaseOrderRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<PurchaseOrderRead | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const [vendorName, setVendorName] = useState("");
  const [notes, setNotes] = useState("");

  const [itemName, setItemName] = useState("");
  const [itemSku, setItemSku] = useState("");
  const [itemQty, setItemQty] = useState("1");
  const [itemPrice, setItemPrice] = useState("0");

  const [suppliers, setSuppliers] = useState<SupplierRead[]>([]);
  const [supplierModalMode, setSupplierModalMode] = useState<SupplierModalMode>("list");
  const [editingSupplier, setEditingSupplier] = useState<SupplierRead | null>(null);
  const [supplierForm, setSupplierForm] = useState<SupplierCreate>({ ...EMPTY_SUPPLIER });
  const [supplierSearch, setSupplierSearch] = useState("");
  const [supplierLoading, setSupplierLoading] = useState(false);

  const [showReceiveModal, setShowReceiveModal] = useState(false);
  const [receiveItems, setReceiveItems] = useState<Record<number, { received_qty: number; lot_number: string; expiry_date: string; mfg_date: string }>>({});

  const load = async () => {
    setLoading(true);
    try { setOrders(await listPurchaseOrders(filter)); } catch { /* ignore */ }
    setLoading(false);
  };

  const loadSuppliers = async () => {
    setSupplierLoading(true);
    try {
      setSuppliers(supplierSearch.trim() ? await searchSuppliers(supplierSearch) : await listSuppliers());
    } catch { /* ignore */ }
    setSupplierLoading(false);
  };

  useEffect(() => { void load(); }, [filter]);
  useEffect(() => { if (supplierModalMode === "list") void loadSuppliers(); }, [supplierSearch, supplierModalMode]);

  const poItemColumns = useMemo<Column<{ id: number; line_number: number; product_name: string; quantity: number; unit_price: string; line_total: string; status: string }>[]>(() => [
    { key: "line_number", header: "#", render: (row) => row.line_number },
    { key: "product_name", header: "Product", render: (row) => row.product_name },
    { key: "quantity", header: "Qty", render: (row) => row.quantity, className: "text-center" },
    { key: "unit_price", header: "Price", render: (row) => `$${formatMoney(parseMoney(row.unit_price))}`, className: "text-right" },
    { key: "line_total", header: "Total", render: (row) => `$${formatMoney(parseMoney(row.line_total))}`, className: "text-right" },
    { key: "status", header: "Status", render: (row) => row.status, className: "text-right" },
  ], []);

  const poColumns = useMemo<Column<PurchaseOrderRead>[]>(() => [
    { key: "po_number", header: "PO #", render: (row) => row.po_number },
    { key: "vendor_name", header: "Vendor", render: (row) => row.vendor_name || "—" },
    { key: "status", header: "Status", render: (row) => (
      <span style={{ fontSize: 11, padding: "2px 6px", borderRadius: 4, background: STATUS_COLORS[row.status] ?? "#6b7280", color: "#fff" }}>
        {row.status}
      </span>
    )},
    { key: "total_cost", header: "Total", render: (row) => (
      <span style={{ fontSize: 12, color: "#16a34a", fontWeight: 500 }}>
        ${formatMoney(parseMoney(row.total_cost))}
      </span>
    ), className: "text-right" },
  ], []);

  const handleCreate = async () => {
    if (!vendorName.trim()) return;
    const po = await createPurchaseOrder({ vendor_name: vendorName, notes });
    setSelected(po);
    setShowCreate(false);
    setVendorName(""); setNotes("");
    await load();
  };

  const handleAddItem = async () => {
    if (!selected || !itemName.trim()) return;
    const po = await addPOItem(selected.id, {
      product_name: itemName, vendor_sku: itemSku,
      quantity: parseInt(itemQty) || 1, unit_price: parseFloat(itemPrice) || 0,
    });
    setSelected(po);
    setItemName(""); setItemSku(""); setItemQty("1"); setItemPrice("0");
    await load();
  };

  const handleRemoveItem = async (itemId: number) => {
    if (!selected) return;
    setSelected(await removePOItem(selected.id, itemId));
    await load();
  };

  const handleTransition = async () => {
    if (!selected) return;
    setSelected(await transitionPOStatus(selected.id));
    await load();
  };

  const handleDelete = async (id: number) => {
    await deletePurchaseOrder(id);
    if (selected?.id === id) setSelected(null);
    await load();
  };

  const handleSupplierCreate = async () => {
    if (!supplierForm.name.trim()) return;
    try {
      await createSupplier(supplierForm);
      setSupplierModalMode("list");
      setEditingSupplier(null);
      setSupplierForm({ ...EMPTY_SUPPLIER });
      await loadSuppliers();
    } catch { /* ignore */ }
  };

  const handleSupplierUpdate = async () => {
    if (!editingSupplier || !supplierForm.name.trim()) return;
    try {
      await updateSupplier(editingSupplier.id, supplierForm);
      setSupplierModalMode("list");
      setEditingSupplier(null);
      setSupplierForm({ ...EMPTY_SUPPLIER });
      await loadSuppliers();
    } catch { /* ignore */ }
  };

  const handleSupplierDelete = async (id: number) => {
    if (!window.confirm("Delete this supplier?")) return;
    try { await deleteSupplier(id); await loadSuppliers(); } catch { /* ignore */ }
  };

  const handleSetPreferred = async (id: number) => {
    try { await setPreferredSupplier(id); await loadSuppliers(); } catch { /* ignore */ }
  };

  const openSupplierEdit = (supplier?: SupplierRead) => {
    if (supplier) {
      setEditingSupplier(supplier);
      setSupplierForm({
        name: supplier.name,
        contact_name: supplier.contact_name ?? "",
        contact_email: supplier.contact_email ?? "",
        contact_phone: supplier.contact_phone ?? "",
        address: supplier.address ?? "",
        tax_id: supplier.tax_id ?? "",
        preferred: supplier.preferred,
        sku: supplier.sku ?? "",
        min_stock_level: supplier.min_stock_level ?? 0,
        lead_time_days: supplier.lead_time_days ?? 0,
      });
      setSupplierModalMode("edit");
    } else {
      setEditingSupplier(null);
      setSupplierForm({ ...EMPTY_SUPPLIER });
      setSupplierModalMode("create");
    }
  };

  const openReceiveModal = () => {
    if (!selected) return;
    const initial: Record<number, { received_qty: number; lot_number: string; expiry_date: string; mfg_date: string }> = {};
    selected.items.forEach((item) => {
      initial[item.id] = { received_qty: item.quantity, lot_number: "", expiry_date: "", mfg_date: "" };
    });
    setReceiveItems(initial);
    setShowReceiveModal(true);
  };

  const handleReceive = async () => {
    if (!selected) return;
    const items = Object.entries(receiveItems).map(([itemId, data]) => ({
      item_id: parseInt(itemId), ...data,
    }));
    try {
      setSelected(await receivePO(selected.id, items));
      setShowReceiveModal(false);
      setReceiveItems({});
      await load();
    } catch { /* ignore */ }
  };

  const handleAutoReorder = async () => {
    try { await autoReorder(); await load(); } catch { /* ignore */ }
  };

  const inputStyle: React.CSSProperties = { padding: "6px 8px", border: "1px solid #d1d5db", borderRadius: 4, fontSize: 13 };
  const inputStyleFull: React.CSSProperties = { width: "100%", ...inputStyle };

  return (
    <DashboardLayout>
    <>
        <div style={{ padding: 24, maxWidth: 1100, margin: "0 auto" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
            <h1 style={{ fontSize: 22, fontWeight: 700 }}>{t("po.title") ?? "Purchase Orders"}</h1>
            <div style={{ display: "flex", gap: 8 }}>
              <button onClick={() => { setSupplierModalMode("list"); setSupplierSearch(""); }} style={{ padding: "8px 16px", background: "#0d9488", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer" }}>
                Suppliers
              </button>
              <button onClick={() => { setShowCreate(true); setSelected(null); }} style={{ padding: "8px 16px", background: "#7c3aed", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer" }}>
                + {t("po.new") ?? "New PO"}
              </button>
              <button onClick={handleAutoReorder} style={{ padding: "8px 16px", background: "#16a34a", color: "#fff", border: "none", borderRadius: 6, cursor: "pointer" }}>
                Auto Reorder
              </button>
            </div>
          </div>

          <div style={{ display: "flex", gap: 4, marginBottom: 16 }}>
            {["", "Draft", "Submitted", "Received", "Closed"].map((s) => (
              <button key={s} onClick={() => setFilter(s)} style={{
                padding: "6px 12px", borderRadius: 4, fontSize: 13, border: "1px solid #d1d5db",
                background: filter === s ? "#7c3aed" : "transparent",
                color: filter === s ? "#fff" : "#6b7280",
              }}>
                {s || "All"}
              </button>
            ))}
          </div>

          <div style={{ display: "flex", gap: 16 }}>
            <div style={{ width: 320, flexShrink: 0 }}>
              <DataTable
                columns={poColumns}
                data={orders}
                keyExtractor={(row) => row.id}
                loading={loading}
                emptyMessage="No purchase orders"
                onRowClick={setSelected}
                selection={{
                  selectedKeys: selected ? new Set([selected.id]) : new Set(),
                  onSelectionChange: (keys) => {
                    if (keys.size > 0) {
                      const po = orders.find((o) => o.id === Array.from(keys)[0]);
                      if (po) setSelected(po);
                    }
                  },
                }}
                className="bg-white dark:bg-gray-900"
              />
            </div>

            <div style={{ flex: 1 }}>
              {!selected ? (
                <div style={{ textAlign: "center", padding: 48, color: "#6b7280" }}>
                  {showCreate ? (
                    <div style={{ maxWidth: 400, margin: "0 auto", textAlign: "left" }}>
                      <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>New Purchase Order</h3>
                      <div style={{ marginBottom: 8 }}>
                        <label style={{ fontSize: 12, fontWeight: 600, color: "#6b7280" }} htmlFor="page-field-1">Vendor Name *</label>
                        <input id="page-field-1" value={vendorName} onChange={(e) => setVendorName(e.target.value)} style={inputStyleFull} />
                      </div>
                      <div style={{ marginBottom: 12 }}>
                        <label style={{ fontSize: 12, fontWeight: 600, color: "#6b7280" }} htmlFor="page-field-2">Notes</label>
                        <textarea id="page-field-2" value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} style={{ ...inputStyleFull, resize: "vertical" }} />
                      </div>
                      <div style={{ display: "flex", gap: 8 }}>
                        <button onClick={() => void handleCreate()} style={{ padding: "6px 16px", background: "#16a34a", color: "#fff", border: "none", borderRadius: 4, fontSize: 13 }}>Create</button>
                        <button onClick={() => setShowCreate(false)} style={{ padding: "6px 16px", border: "1px solid #d1d5db", borderRadius: 4, fontSize: 13 }}>Cancel</button>
                      </div>
                    </div>
                  ) : "← Select a purchase order"}
                </div>
              ) : (
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                    <div>
                      <h2 style={{ fontSize: 18, fontWeight: 700 }}>{selected.po_number}</h2>
                      <p style={{ fontSize: 13, color: "#6b7280" }}>{selected.vendor_name}</p>
                    </div>
                    <div style={{ display: "flex", gap: 8 }}>
                      {selected.status === "Submitted" && (
                        <button onClick={openReceiveModal} style={{ padding: "6px 12px", background: "#0d9488", color: "#fff", border: "none", borderRadius: 4, fontSize: 13, cursor: "pointer" }}>
                          Receive Items
                        </button>
                      )}
                      {selected.status !== "Closed" && (
                        <button onClick={() => void handleTransition()} style={{ padding: "6px 12px", background: "#16a34a", color: "#fff", border: "none", borderRadius: 4, fontSize: 13 }}>
                          → {selected.status === "Draft" ? "Submit" : selected.status === "Submitted" ? "Mark Received" : "Close"}
                        </button>
                      )}
                      {selected.status === "Draft" && (
                        <button onClick={() => void handleDelete(selected.id)} style={{ padding: "6px 12px", background: "#dc2626", color: "#fff", border: "none", borderRadius: 4, fontSize: 13 }}>
                          Delete
                        </button>
                      )}
                    </div>
                  </div>

                  {/* PO Items Table */}
                  <div style={{ border: "1px solid #e5e7eb", borderRadius: 6, overflow: "hidden", marginBottom: 12 }}>
                    <DataTable
                      columns={poItemColumns}
                      data={selected.items}
                      keyExtractor={(row) => row.id}
                      loading={false}
                      emptyMessage="No items in this purchase order"
                      actions={selected.status === "Draft" ? {
                        header: "",
                        render: (row) => (
                          <button
                            onClick={() => void handleRemoveItem(row.id)}
                            style={{ color: "#dc2626", fontSize: 12, background: "none", border: "none", cursor: "pointer" }}
                          >
                            ×
                          </button>
                        )
                      } : undefined}
                      className="w-full"
                    />
                  </div>

                  {selected.status === "Draft" && (
                    <div style={{ display: "flex", gap: 8, marginBottom: 12, alignItems: "flex-end" }}>
                      <input value={itemName} onChange={(e) => setItemName(e.target.value)} placeholder="Product name" style={{ flex: 2, ...inputStyle }} />
                      <input value={itemSku} onChange={(e) => setItemSku(e.target.value)} placeholder="SKU" style={{ flex: 1, ...inputStyle }} />
                      <input value={itemQty} onChange={(e) => setItemQty(e.target.value)} type="number" min="1" placeholder="Qty" style={{ width: 60, ...inputStyle }} />
                      <input value={itemPrice} onChange={(e) => setItemPrice(e.target.value)} type="number" min="0" step="0.01" placeholder="Price" style={{ width: 80, ...inputStyle }} />
                      <button onClick={() => void handleAddItem()} style={{ padding: "6px 12px", background: "#374151", color: "#fff", border: "none", borderRadius: 4, fontSize: 13 }}>Add</button>
                    </div>
                  )}

                  <div style={{ textAlign: "right", fontSize: 14 }}>
                    <div>Subtotal: <strong>${formatMoney(parseMoney(selected.subtotal))}</strong></div>
                    <div style={{ fontSize: 16, color: "#16a34a", fontWeight: 700 }}>Total: ${formatMoney(parseMoney(selected.total_cost))}</div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
  );

      {/* Supplier Modal */}
      {supplierModalMode !== "list" && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50" onClick={() => setSupplierModalMode("list")}>
          <div className="bg-[#1a1a2e] border border-gray-800 rounded-lg w-full max-w-md max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between p-4 border-b border-gray-800">
              <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-100">{supplierModalMode === "edit" ? "Edit Supplier" : "New Supplier"}</h3>
              <button onClick={() => setSupplierModalMode("list")} className="text-gray-600 dark:text-gray-400 hover:text-white text-xl p-1">×</button>
            </div>
            <div className="p-4 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1" htmlFor="page-field-3">Name *</label>
                <input id="page-field-3" value={supplierForm.name} onChange={(e) => setSupplierForm({ ...supplierForm, name: e.target.value })} className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-2 text-sm text-gray-100" />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1" htmlFor="page-field-4">Contact Name</label>
                  <input id="page-field-4" value={supplierForm.contact_name ?? ""} onChange={(e) => setSupplierForm({ ...supplierForm, contact_name: e.target.value })} className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-2 text-sm text-gray-100" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1" htmlFor="page-field-5">Contact Phone</label>
                  <input id="page-field-5" value={supplierForm.contact_phone ?? ""} onChange={(e) => setSupplierForm({ ...supplierForm, contact_phone: e.target.value })} className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-2 text-sm text-gray-100" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1" htmlFor="page-field-6">Contact Email</label>
                  <input id="page-field-6" value={supplierForm.contact_email ?? ""} onChange={(e) => setSupplierForm({ ...supplierForm, contact_email: e.target.value })} className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-2 text-sm text-gray-100" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1" htmlFor="page-field-7">Tax ID</label>
                  <input id="page-field-7" value={supplierForm.tax_id ?? ""} onChange={(e) => setSupplierForm({ ...supplierForm, tax_id: e.target.value })} className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-2 text-sm text-gray-100" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1" htmlFor="page-field-8">SKU</label>
                  <input id="page-field-8" value={supplierForm.sku ?? ""} onChange={(e) => setSupplierForm({ ...supplierForm, sku: e.target.value })} className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-2 text-sm text-gray-100" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1" htmlFor="page-field-9">Min Stock Level</label>
                  <input id="page-field-9" type="number" value={supplierForm.min_stock_level ?? 0} onChange={(e) => setSupplierForm({ ...supplierForm, min_stock_level: parseInt(e.target.value) || 0 })} className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-2 text-sm text-gray-100" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1" htmlFor="page-field-10">Lead Time (days)</label>
                  <input id="page-field-10" type="number" value={supplierForm.lead_time_days ?? 0} onChange={(e) => setSupplierForm({ ...supplierForm, lead_time_days: parseInt(e.target.value) || 0 })} className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-2 text-sm text-gray-100" />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1" htmlFor="page-field-11">Address</label>
                <textarea id="page-field-11" value={supplierForm.address ?? ""} onChange={(e) => setSupplierForm({ ...supplierForm, address: e.target.value })} rows={2} className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-2 text-sm text-gray-100" />
              </div>
              <div className="flex items-center gap-2">
                <input id="supplier-preferred" type="checkbox" checked={supplierForm.preferred === 1} onChange={(e) => setSupplierForm({ ...supplierForm, preferred: e.target.checked ? 1 : 0 })} className="w-4 h-4 accent-blue-500" />
                <label htmlFor="supplier-preferred" className="text-sm text-gray-700 dark:text-gray-300">Preferred Supplier</label>
              </div>
              <div className="flex justify-end gap-3 pt-4">
                <button onClick={() => setSupplierModalMode("list")} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-300">Cancel</button>
                <button onClick={supplierModalMode === "edit" ? handleSupplierUpdate : handleSupplierCreate} className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700">
                  {supplierModalMode === "edit" ? "Update" : "Create"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Supplier List Modal */}
      {supplierModalMode === "list" && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50" onClick={() => setSupplierModalMode("list")}>
          <div className="bg-[#1a1a2e] border border-gray-800 rounded-lg w-full max-w-2xl max-h-[90vh] overflow-hidden" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between p-4 border-b border-gray-800">
              <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-100">Suppliers</h3>
              <button onClick={() => setSupplierModalMode("list")} className="text-gray-600 dark:text-gray-400 hover:text-white text-xl p-1">×</button>
            </div>
            <div className="p-4 border-b border-gray-800 flex gap-2">
              <input value={supplierSearch} onChange={(e) => setSupplierSearch(e.target.value)} placeholder="Search suppliers..." className="flex-1 rounded bg-gray-700 border border-gray-600 px-3 py-2 text-sm text-gray-100" />
              <button onClick={() => openSupplierEdit()} className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-sm font-medium">+ Add Supplier</button>
            </div>
            <div className="max-h-[60vh] overflow-y-auto">
              {supplierLoading ? (
                <div className="flex items-center justify-center p-8"><div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500"></div></div>
              ) : suppliers.length === 0 ? (
                <div className="p-8 text-center text-gray-500">No suppliers found</div>
              ) : (
                <div className="divide-y divide-gray-800">
                  {suppliers.map((s) => (
                    <div key={s.id} className="p-4 flex items-center justify-between hover:bg-gray-800/50">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-gray-800 dark:text-gray-100 truncate">{s.name}</span>
                          {s.preferred ? <span className="px-2 py-0.5 text-xs bg-amber-500/20 text-amber-400 rounded">Preferred</span> : null}
                        </div>
                        <div className="text-xs text-gray-500 flex flex-wrap gap-4 mt-1">
                          {s.contact_name ? <span>Contact: {s.contact_name}</span> : null}
                          {s.contact_phone ? <span>Phone: {s.contact_phone}</span> : null}
                          {s.contact_email ? <span>Email: {s.contact_email}</span> : null}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {!s.preferred && <button onClick={() => handleSetPreferred(s.id)} className="px-3 py-1.5 text-xs bg-amber-500 hover:bg-amber-600 text-white rounded">Set Preferred</button>}
                        <button onClick={() => openSupplierEdit(s)} className="px-3 py-1.5 text-xs border border-gray-600 text-gray-300 hover:bg-gray-700 rounded">Edit</button>
                        <button onClick={() => handleSupplierDelete(s.id)} className="px-3 py-1.5 text-xs bg-red-500 hover:bg-red-600 text-white rounded">Delete</button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* PO Receive Modal */}
      {showReceiveModal && selected && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50" onClick={() => setShowReceiveModal(false)}>
          <div className="bg-[#1a1a2e] border border-gray-800 rounded-lg w-full max-w-2xl max-h-[90vh] overflow-hidden" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between p-4 border-b border-gray-800">
              <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-100">Receive PO — {selected.po_number}</h3>
              <button onClick={() => setShowReceiveModal(false)} className="text-gray-600 dark:text-gray-400 hover:text-white text-xl p-1">×</button>
            </div>
            <div className="p-4 max-h-[70vh] overflow-y-auto">
              <div className="space-y-4">
                {selected.items.map((item) => {
                  const data = receiveItems[item.id] || { received_qty: item.quantity, lot_number: "", expiry_date: "", mfg_date: "" };
                  return (
                    <div key={item.id} className="bg-[#0d0d20] border border-gray-800 rounded-lg p-4 space-y-3">
                      <div className="font-medium text-gray-800 dark:text-gray-100">{item.product_name}</div>
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                        <div>
                          <span className="block text-gray-500 mb-1">Expected Qty</span>
                          <span className="text-gray-800 dark:text-gray-200 font-medium">{item.quantity}</span>
                        </div>
                        <div>
                          <label className="block text-gray-500 mb-1" htmlFor="page-field-12">Received Qty *</label>
                          <input id="page-field-12" type="number" min="0" value={data.received_qty} onChange={(e) => setReceiveItems({ ...receiveItems, [item.id]: { ...data, received_qty: parseInt(e.target.value) || 0 } })} className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-2 text-sm text-gray-100" />
                        </div>
                        <div>
                          <label className="block text-gray-500 mb-1" htmlFor="page-field-13">Lot Number</label>
                          <input id="page-field-13" value={data.lot_number} onChange={(e) => setReceiveItems({ ...receiveItems, [item.id]: { ...data, lot_number: e.target.value } })} className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-2 text-sm text-gray-100" />
                        </div>
                        <div>
                          <label className="block text-gray-500 mb-1" htmlFor="page-field-14">Expiry Date</label>
                          <input id="page-field-14" type="date" value={data.expiry_date} onChange={(e) => setReceiveItems({ ...receiveItems, [item.id]: { ...data, expiry_date: e.target.value } })} className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-2 text-sm text-gray-100" />
                        </div>
                        <div className="sm:col-span-2">
                          <label className="block text-gray-500 mb-1" htmlFor="page-field-15">Mfg Date</label>
                          <input id="page-field-15" type="date" value={data.mfg_date} onChange={(e) => setReceiveItems({ ...receiveItems, [item.id]: { ...data, mfg_date: e.target.value } })} className="w-full rounded bg-gray-700 border border-gray-600 px-3 py-2 text-sm text-gray-100" />
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
            <div className="flex justify-end gap-3 p-4 border-t border-gray-800">
              <button onClick={() => setShowReceiveModal(false)} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-300">Cancel</button>
              <button onClick={handleReceive} className="px-4 py-2 text-sm font-medium text-white bg-green-600 rounded-md hover:bg-green-700">Receive Items</button>
            </div>
          </div>
        </div>
      )}
    </>
    </DashboardLayout>
  );
}
