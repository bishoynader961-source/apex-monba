# Project Map (High-Level Summary)

> **Status:** PRODUCTION-READY — Serialized Unit-Level Tracking Model

> **Source of Truth:** [`PROJECT_MAP.md`](PROJECT_MAP.md) — full architectural details, schema blueprints, and component impact analysis.

> **Last synced:** 2026-07-15

---

## Milestones

| Range | Milestone Group | Status |
|---|---|---|
| M1–M27 | Label Engine + Pharmacy Core | Complete |
| M28 | Vendor Traceability | Complete |
| M29 | Quick Receive Modal | Complete |
| M30 | Serialized Barcode Generation | Complete |
| M31 | Serialized Receiving Loop | Complete |
| M32 | Atomic Receiving (transactional) | Complete |
| M33 | Legacy Barcode Normalization | Complete |
| M34 | Vendor Prefix in Inventory Treeview | Complete |
| M35 | Purchase Order & Receiving Dashboard | Complete |
| M36 | Shipment History Bridge (Add Product + vendor-change edits log to receiving_log) | Complete |
| M37 | Shipment History Unit Cost Display (Cost column shows per-box unit cost) | Complete |
| M38 | Vendor-Filtered Combobox + Auto-Fill Expansion (Unit Price + Mfg Barcode) | Complete |
| M39 | Shipment History Cost Alignment (unit_cost matches products.price) | Complete |
| M40 | Price Cascade to Receiving Log (update_product_full cascades price to receiving_log.total_cost) | Complete |
| M41 | Vendor-Grouped Shipment History (hierarchical treeview grouped by vendor) | Complete |
| M42 | Click-to-Sort Date Column (click heading to sort chronologically within vendor groups) | Complete |
| M43 | Date Filter for Shipment History (date entry + Filter/Clear buttons) | Complete |
| M44 | Bulk Add from Add Product Tab (BulkAddModal — serialize N boxes in one click) | Complete |
| M45 | Bulk Print Tags + Save to Queue (BulkAddModal dual-path: direct save or queue; batch label printing) | Complete |

**All milestones M1–M35 verified and complete.**

---

## File Structure

### `database.py` — Schema Guard + Serialization Logic

- **Schema Guard:** `init_db()` creates all tables, runs `ALTER TABLE` migrations, validates column presence via `PRAGMA table_info` after migration.
- **Serialization:** `add_product()` inserts one serialized row per box. `receive_inventory_atomically()` wraps N product inserts + 1 receiving_log entry in a single `BEGIN/COMMIT/ROLLBACK` transaction.
- **Core queries:** `get_grouped_products()` uses `GROUP BY name` with `COUNT(*)` for box-level inventory display.
- **Cascade:** `update_product_full()` propagates vendor/name changes to `receiving_log` via `WHERE barcode = ?`.

### `migrate_data.py` — Migration Utility

- One-time script for normalizing pre-serialization barcodes to `{VND[:3]}-{UUID6}` format.
- Transaction-safe with rollback on error. Cascades updates to `receiving_log.barcode`.
- **Status:** Already executed. Database clean — 0 malformed barcodes remain.
- **Historical artifacts:** `receiving_log` entries 1 & 2 are pre-serialization orphans (no barcode link). Documented in `PROJECT_MAP.md` Known Orphans section. No further action required.

### `ui.py` — Serialized Inventory View

- **Inventory Tab:** Grouped Treeview (`GROUP BY name`) with double-click expand to individual box rows. Each child row = 1 physical box with unique barcode, expiry, and vendor prefix (e.g. `MED` from `MED-A3F9B2`) for instant vendor identification.
- **Receive Inventory Tab:** Purchase Order & Receiving Dashboard with 3-zone layout. Zone A (left, scrollable): input form + "Add to Queue" — items held in `self.receiving_session` in-memory. Product combobox filters by active vendor (`_on_vendor_change()`). Auto-fill section shows Mfg Date, Expiry Date, Unit Price, and Mfg Barcode from vendor-specific template. Zone B (top right): Pending PO Treeview (vendor-grouped). Zone C (bottom right): Commit panel with Invoice Total + "Commit Shipment" — calls `receive_inventory_atomically()` per vendor, then syncs Inventory + Receiving tabs. Vendor Payables lookup at bottom. Shipment History is vendor-grouped hierarchical treeview (M41) with per-box cost matching Inventory price (M39/M40).
- **Quick Receive Modal:** Appears when `EditBatchDialog` vendor changes from N/A to valid. Creates serialized rows via same atomic function.
- **Shipment History Bridge (M36):** `save_product()` and `EditBatchDialog._save()` now call `database.log_shipment()` to record entries in `receiving_log`, ensuring the Shipment History treeview reflects all product additions and vendor-change edits.
- **Sales/Report Tab:** Individual sold boxes with vendor traceability and date-based revenue queries.
- **Label Printing:** Each box gets a unique barcode label via `LabelDesignerPopup` → `label_engine`.

---

_No remaining TODO items. All planned features complete._

---

_This document is a high-level summary. Refer to [`PROJECT_MAP.md`](PROJECT_MAP.md) for full architectural details, schema blueprints, and system flow diagrams._
