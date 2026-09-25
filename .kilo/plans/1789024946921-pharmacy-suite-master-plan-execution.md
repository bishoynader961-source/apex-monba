# Pharmacy Suite Master Plan Execution — Implementation-Ready Plan

## Current State Analysis
The PROJECT_MAP.md indicates all 5 phases are "completed", but code review reveals several issues requiring fixes:

### Phase 2: Analytics Crash Resolution (CRITICAL — Runtime crashes)
**`.reduce()` calls missing optional chaining/initial values — will throw `TypeError: Cannot read properties of undefined (reading 'reduce')` when data is null/empty:**

1. `app/dashboard/analytics/page.tsx` lines 90-91: `data?.items.reduce` → `data?.items?.reduce`
2. `app/dashboard/analytics/demand/page.tsx` lines 119, 121, 122: `summary?.items.reduce` → `summary?.items?.reduce`
3. `app/patients/page.tsx` line 643: `history.reduce(...)` — already has initial value `0`, but `history` state is initialized as `[]` so this is actually safe. **No fix needed.**

### Phase 1: Button Accessibility (HIGH — Silent failures)
**Missing toast notifications on async button handlers:**
- Most pages don't use `useToast` hook
- Errors only set local `error` state, no user-visible feedback

### Phase 3, 4, 5: Already Implemented ✓
- Label Engine wired to Tauri IPC (`open_label_window`, `print_label`)
- Admin seeding (User ID 1, Role ID 1) with backend safeguards
- AuthConfirmModal for sensitive actions (edit user, toggle active, delete role, toggle permission)

---

## Exact Code Changes Required

### FIX 1: `app/dashboard/analytics/page.tsx` (lines 90-91)

**Current (BROKEN — crashes when `data` is null):**
```tsx
const totalRevenue = data?.items.reduce((s, i) => s + i.total_revenue, 0) ?? 0;
const totalUnits = data?.items.reduce((s, i) => s + i.total_quantity, 0) ?? 0;
```

**Fixed:**
```tsx
const totalRevenue = data?.items?.reduce((s, i) => s + i.total_revenue, 0) ?? 0;
const totalUnits = data?.items?.reduce((s, i) => s + i.total_quantity, 0) ?? 0;
```

---

### FIX 2: `app/dashboard/analytics/demand/page.tsx` (lines 118-125)

**Current (BROKEN — crashes when `summary` is null):**
```tsx
const totalQty =
  summary?.items.reduce((s, it) => s + it.total_quantity_demanded, 0) ?? 0;
const totalRevenue =
  summary?.items.reduce((s, it) => s + parseMoney(it.total_revenue), 0n) ?? 0n;
const topProduct = summary?.items.reduce<DemandAnalyticsItem | null>(
  (top, it) => (it.total_quantity_demanded > (top?.total_quantity_demanded ?? 0) ? it : top),
  null,
);
```

**Fixed:**
```tsx
const totalQty =
  summary?.items?.reduce((s, it) => s + it.total_quantity_demanded, 0) ?? 0;
const totalRevenue =
  summary?.items?.reduce((s, it) => s + parseMoney(it.total_revenue), 0n) ?? 0n;
const topProduct = summary?.items?.reduce<DemandAnalyticsItem | null>(
  (top, it) => (it.total_quantity_demanded > (top?.total_quantity_demanded ?? 0) ? it : top),
  null,
);
```

---

### FIX 3: `app/patients/page.tsx` (line 643) — **NO CHANGE NEEDED**
```tsx
const totalOutstanding = history.reduce((sum, h) => sum + Number(h.total_amount), 0);
```
This already has initial value `0` and `history` is initialized as `[]` via `useState<PatientHistoryEntry[]>([])`. Safe.

---

## Phase 1: Button Accessibility — Toast Integration Pattern

For each priority page, apply this pattern:

### Pattern: Add `useToast` and wrap async handlers

```tsx
// 1. Import
import { useToast } from "@/hooks/useToast";

// 2. In component body
const { toast } = useToast();

// 3. Wrap async handlers
const handleAction = async () => {
  try {
    await riskyOperation();
    toast({ title: "Success", message: "Operation completed", variant: "success" });
  } catch (err) {
    toast({ title: "Error", message: err instanceof Error ? err.message : "Failed", variant: "destructive" });
  }
};
```

### Priority Pages Requiring Toast Integration:

1. **`app/pos/page.tsx`** — `handleCheckout`, `handleSearchChange`, `flushQueue`
2. **`app/dashboard/inventory/page.tsx`** — `receiveBatch`, `adjustBatch`, `deleteMedicine`
3. **`app/dashboard/gift-cards/page.tsx`** — `activateCard`, `voidCard`, `loadCard`
4. **`app/dashboard/bulk-label-print/page.tsx`** — `generatePreview`, `handlePrint`, `handleDownloadAll`
5. **`app/patients/page.tsx`** — `handleValidate`, `handleBind`, `handleAddInsurance`

---

## Verification Commands

```bash
# TypeScript type check
npx tsc --noEmit

# ESLint
npm run lint

# Run tests (if available)
npm test

# Manual verification:
# 1. Navigate to /dashboard/analytics — should not crash when empty
# 2. Navigate to /dashboard/analytics/demand — should not crash when empty
# 3. Click buttons on POS page — should show toast on success/error
```

---

## Implementation Order

1. **Immediate (Phase 2):** Apply FIX 1 and FIX 2 — these are runtime crashes
2. **High Priority (Phase 1):** Add toast integration to 5 priority pages
3. **Verification:** Run typecheck, lint, and manual smoke test

---

## Notes

- All changes are minimal, surgical fixes — no refactoring
- Existing architecture, database structure, and UI layout preserved
- Phase 3, 4, 5 verified as complete — no changes needed