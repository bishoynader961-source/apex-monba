# Plan: Receipt Print Preview & Thermal Receipt Generation

> **Source:** Gap analysis between `MASTER_CODING_PROMPT.md` (legacy spec) and baseline report `1788631762352-decoupled-stack-baseline.md`.
> **Mode:** Native Plan — this file is an implementation-ready spec for an execution-capable agent.

## 1. Gap Analysis Summary

### Legacy feature present in spec, missing from current app

| # | Legacy Feature | Current Status | Impact |
|---|---|---|---|
| 1 | `GET /api/v1/pos/receipts/{id}/print` (thermal text) | **MISSING** | POS page shows checkout result as raw JSON `<pre>` dump (line 735) — no receipt print capability |
| 2 | Reports module (`/reports/inventory-value`, `/expiry-forecast`, `/audit-log`) | **MISSING** | Only analytics + POS sales report exist |
| 3 | `/suppliers` frontend page | **MISSING** | API exists (`GET/POST /suppliers`) but no route |
| 4 | `/license` frontend page | **MISSING** | Only `LicenseGate` wrapper, no standalone page |
| 5 | `settings.import` endpoint | **MISSING** | Settings API has list/get/update only |
| 6 | `uiStore` (UI preferences store) | **MISSING** | Current app has `themeStore` only |
| 7 | BarcodeScanner **component** | Refactored into `useBarcodeScanner` hook | Already addressed — not a gap |
| 8 | Supplier/Patient **models** with `email`, `is_licensed` fields | **Different schema** | Current uses `username` + RBAC roles — design choice, not gap |

### Key observation
The current app is a **superset** of the legacy spec — it added patients, prescribers, insurance, POs, coupons, DDI checking, sync protocol, etc. The few genuine gaps are missing features that were in the original spec but not yet ported.

---

## 2. Selected Feature: Receipt Print Preview & Thermal Receipt Generation

**Rationale:** Highest business value (receipt printing is core to POS operations), has a clear existing UI issue to fix (raw JSON `<pre>` on POS page line 735), requires both a backend route and frontend component, and is fully self-contained (only depends on existing `Receipt` + `ReceiptItem` ORM models and `receipt_detail` service method).

**What we port from legacy:** `GET /api/v1/pos/receipts/{receipt_id}/print` — but **refactored**, not copy-pasted. Instead of returning bare text, the current app returns structured JSON with a `receipt_text` field (ESC/POS-ready) plus the same `ReceiptRead` shape (items, totals, patient/cashier) for a styled preview UI.

---

## 3. Backend Implementation Plan (FastAPI)

### 3.1 New Pydantic Schema (`app/schemas.py`)

Add `ReceiptPrintResponse`:

```python
class ReceiptPrintResponse(BaseModel):
    receipt_id: int
    receipt_number: str
    receipt_text: str              # ESC/POS / thermal plain-text layout
    printable_html: str            # browser-print HTML (styled preview)
    items: list[ReceiptItemRead]
    total_amount: Decimal
    payment_method: str
    timestamp: str
    cashier_attribution: Optional[str]
    patient_name: Optional[str]
```

> **Refactor note (not copy-paste):** Legacy returned only thermal text. We return both `receipt_text` (for physical thermal printers) and `printable_html` (for browser/CSS print preview) so the frontend can show a styled preview before printing.

### 3.2 New Route (`app/api/routers/pos_route.py`)

```python
@router.get("/receipts/{receipt_id}/print", response_model=ReceiptPrintResponse, status_code=status.HTTP_200_OK)
async def receipt_print(
    receipt_id: int,
    user: CurrentUser = Depends(require_permission("pos.checkout")),
    session: AsyncSession = Depends(get_session),
) -> ReceiptPrintResponse:
    """Return a receipt in thermal-print and browser-print formats (legacy G1 port)."""
    return await PosService(session).format_receipt_print(receipt_id)
```

### 3.3 New Service Method (`app/services/pos_service.py`)

Add `format_receipt_print(receipt_id: int) -> ReceiptPrintResponse`:

1. Call existing `self.receipt_detail(receipt_id)` to get the `ReceiptRead` (already returns items).
2. Load pharmacy settings via `SystemSetting` rows for `pharmacy_name`, `pharmacy_address`, `pharmacy_phone` (fallback to defaults if unset).
3. Build `receipt_text` as ESC/POS-compatible plain text:
   - Centered pharmacy header (name, address, phone)
   - Separator line (24–32 chars of dashes)
   - Receipt number + date + cashier
   - Line items: `name` left, `qty x price` right-aligned, `total` right-aligned
   - Separator
   - Subtotal, Tax, Total (right-aligned, currency formatted)
   - Payment method
   - Footer: "THANK YOU FOR YOUR BUSINESS"
   - Final newline for paper feed
4. Build `printable_html` as a `<style scoped>` block with ReceiptRead data — browser print media query targets `@page { width: 80mm }`.
5. Return `ReceiptPrintResponse`.

**Key design decisions:**
- Money formatting uses `Decimal` with 2-place quantization (matches existing `parseMoney`/`formatMoney` frontend convention).
- No new DB tables required — reuses existing `receipts` + `receipt_items`.
- Settings lookup is best-effort: if `pharmacy_name` key is not in `system_settings`, use `"Pharmacy"` as fallback.

### 3.4 Schema Addition to `types/contracts.ts` (Frontend)

```typescript
export interface ReceiptItemRead {
  id: number;
  receipt_id: number;
  product_name: string;
  quantity: number;
  price_at_time: Money;
  internal_barcode: string;
  vendor: string;
  expiry_date: string;
}

export interface ReceiptPrintResponse {
  receipt_id: number;
  receipt_number: string;
  receipt_text: string;        // ESC/POS thermal text
  printable_html: string;      // browser-print HTML
  items: ReceiptItemRead[];
  total_amount: Money;
  payment_method: string;
  timestamp: string;
  cashier_attribution?: string | null;
  patient_name?: string | null;
}
```

### 3.5 API Client Function (`lib/api/pos.ts`)

```typescript
export async function getReceiptPrint(receiptId: number): Promise<ReceiptPrintResponse> {
  const { data } = await api.get<ReceiptPrintResponse>(`${BASE}/receipts/${receiptId}/print`);
  return data;
}
```

---

## 4. Frontend Component (Next.js React)

### 4.1 New Component: `components/ReceiptPrintPreview.tsx`

**Props:**
```typescript
interface ReceiptPrintPreviewProps {
  receiptId: number;
  open: boolean;
  onClose: () => void;
}
```

**Behavior:**
1. On `open`, fetch `getReceiptPrint(receiptId)` via the API client.
2. Display two tabs / switches:
   - **Preview tab**: Renders `printable_html` inside an iframe or `<div dangerouslySetInnerHTML>` for visual preview.
   - **Text tab**: Shows `receipt_text` in a `<pre>` with monospace font for thermal printer testing.
3. **Print button** → calls `window.print()` (CSS `@media print` hides non-preview elements; uses the printable HTML).
4. **Download .txt button** → Blob download of `receipt_text`.
5. Loading state: spinner using existing `LoadingSpinner` component.
6. Error state: red banner using `text-red-400` token.

**Design system compliance (DESIGN_SYSTEM.md §4, §5):**

| Element | Token | Purpose |
|---|---|---|
| Container | `bg-[#1a1a2e] border border-gray-800 rounded-lg shadow-xl` | Card surface (§4 Cards & Panels) |
| Header | `text-gray-100` | Primary text color (§2 Typography) |
| Subtitle | `text-gray-400` | Secondary text (§2) |
| Primary button | `px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-md font-medium transition-colors` | POS action (§4 Standard Buttons) |
| Secondary button | `px-4 py-2 border border-gray-700 text-gray-300 hover:bg-gray-800 rounded-md transition-colors` | Cancel/close (§4) |
| Tab toggle | `border-b border-gray-800` | Separator |
| Print area | `@media print { body * { visibility: hidden } #receipt-print-area * { visibility: visible } }` | Print isolation |

**No inline styles** — strict Tailwind-only (per DESIGN_SYSTEM.md §5 Implementation Rules).

### 4.2 POS Page Integration (`app/pos/page.tsx`)

**Replace** the JSON `<pre>` dump (lines 734–738) with the new `ReceiptPrintPreview` component:

```tsx
// After line 40 (imports), add:
import { ReceiptPrintPreview } from "@/components/ReceiptPrintPreview";

// Replace lines 734-738 (the <pre> JSON dump) with:
{result && (
  <div className="flex items-center gap-3 mt-4">
    <span className="text-sm text-gray-300">Receipt #{result.receipt_number} processed.</span>
    <button
      onClick={() => setShowPrintPreview(true)}
      className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded-md transition-colors"
    >
      Print Preview
    </button>
  </div>
)}
{showPrintPreview && result && (
  <ReceiptPrintPreview
    receiptId={result.receipt_id}
    open={showPrintPreview}
    onClose={() => setShowPrintPreview(false)}
  />
)}
```

Add `const [showPrintPreview, setShowPrintPreview] = useState(false);` to the component body.

### 4.3 CSS Print Stylesheet

Add to `app/globals.css` (or create `styles/print.css` imported in layout):

```css
@media print {
  body * { visibility: hidden; }
  .receipt-print-content * { visibility: visible; }
  .receipt-print-content { position: static; margin: 0; padding: 0; }
}
```

---

## 5. Data Flow

```
POS checkout → CheckoutResult (receipt_id)
  → "Print Preview" button → getReceiptPrint(receipt_id)
    → FastAPI: GET /api/v1/pos/receipts/{id}/print
      → PosService.format_receipt_print()
        → receipt_detail() returns ReceiptRead w/ items
        → SystemSetting lookup for pharmacy info
      → ReceiptPrintResponse { receipt_text, printable_html, items, ... }
    → ReceiptPrintPreview component
      → Tabs: "Browser Preview" | "Thermal Text"
      → "Print" → window.print() (styled)
      → "Download .txt" → Blob download of receipt_text
```

---

## 6. Files to Create / Modify

| File | Action | Description |
|---|---|---|
| `backend_fastapi/app/schemas.py` | **Modify** | Add `ReceiptPrintResponse` schema |
| `backend_fastapi/app/services/pos_service.py` | **Modify** | Add `format_receipt_print()` method |
| `backend_fastapi/app/api/routers/pos_route.py` | **Modify** | Add `GET /receipts/{id}/print` route |
| `backend_fastapi/app/core/models.py` | Read-only | Confirm `Receipt` + `ReceiptItem` ORM fields |
| `types/contracts.ts` | **Modify** | Add `ReceiptPrintResponse` + `ReceiptItemRead` interfaces |
| `lib/api/pos.ts` | **Modify** | Add `getReceiptPrint()` function |
| `components/ReceiptPrintPreview.tsx` | **Create** | New component (Preview + Thermal text tabs, Print, Download) |
| `app/pos/page.tsx` | **Modify** | Replace JSON `<pre>` dump with `ReceiptPrintPreview` invocation |
| `app/globals.css` | **Modify** | Add `@media print` CSS rules |

---

## 7. Verification Criteria

**Backend:**
- `GET /api/v1/pos/receipts/{id}/print` with valid receipt → 200, returns `ReceiptPrintResponse` JSON with non-empty `receipt_text` and `printable_html`
- Invalid receipt_id → 404 `NotFoundError`
- Unauthenticated → 401
- Wrong permissions → 403
- `receipt_text` contains pharmacy name, receipt number, at least 1 item line, total amount
- `printable_html` contains `<table>` or `<div>` with item rows + total
- Pydantic schema validates with `response_model=ReceiptPrintResponse`
- `mypy --strict app/services/pos_service.py` clean
- `ruff check backend_fastapi/app` clean

**Frontend:**
- `ReceiptPrintPreview` opens from POS page after checkout
- "Browser Preview" tab renders the HTML receipt
- "Thermal Text" tab renders plain text
- "Print" button triggers `window.print()` with only the receipt visible
- "Download .txt" downloads a file with the thermal text
- Loading spinner shows during fetch
- Error message appears on API failure
- No inline styles used (all Tailwind utility classes)
- `npx tsc --noEmit` passes

**Integration:**
- Checkout → click Print Preview → see formatted preview → print
- No regression in existing `ReceiptHistoryPanel`, `ReceiptRead`, or `CheckoutResult` flows

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| `receipt_text` format won't match the target thermal printer | Return plain ASCII text with standard 32-char line width; let the consumer (browser print or printer driver) handle actual ESC/POS commands. The endpoint returns text, not raw ESC/POS bytes — printer-specific init/cut codes can be a v2 enhancement. |
| Pharmacy settings key doesn't exist | Fallback to `"Pharmacy"` name, empty address/phone — documented in service code comment |
| `printable_html` security (XSS via patient/product names) | Sanitize via `bleach.clean()` before embedding into HTML — only allow safe tags (`<div>`, `<table>`, `<td>`, `<tr>`, `<span>`, `<br>`) |
| Print CSS conflicts with existing layout | Use isolated `#receipt-print-area` div with scoped styles; `@media print` hides all other elements via global rule in `globals.css` |
| `ReceiptItemRead` not yet exported from `types/contracts.ts` | Add it if missing (confirmed it exists at lines 297-306 in contracts.ts) |
