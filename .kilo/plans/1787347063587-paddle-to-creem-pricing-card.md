# Plan: Migrate PricingCard.tsx from Paddle SDK to Creem Checkout + Build

**Status:** Phase 1 Complete — Phase 2 (Tauri signing) pending manual edit
**Date:** 2026-08-22
**Scope:** `components/PricingCard.tsx` Paddle→Creem migration + `.env.example` cleanup + `npm run build` + Tauri signing config

---

## 1. Context

### Migration state (already done in this repo)
- **Backend** (`backend_fastapi/`): Fully Creem — `POST /api/v1/checkout`, `POST /api/v1/webhook/creem`, `License` model.
- **`app/license/page.tsx`**: Already uses Creem via `initiateCheckout()` → redirect to `checkout_url`. Auth-gated via `useAuthStore.isAuthenticated()`.
- **`lib/api/license.ts`**: `initiateCheckout(payload)` posts to `/api/v1/license/checkout`, returns `CreemCheckoutResponse { checkout_id, checkout_url }`.
- **`types/contracts.ts`**: `CreemCheckoutRequest` / `CreemCheckoutResponse` interfaces exist.
- **`.env.example`**: Already documents Paddle vars as "legacy/optional and currently unused"; `NEXT_PUBLIC_API_BASE_URL` is set.

### What's NOT migrated yet
- **`components/PricingCard.tsx`** (rendered on `app/page.tsx` home page): Still loads the Paddle JS SDK from `https://cdn.paddle.com/paddle/v2/paddle.js`, initializes it with `NEXT_PUBLIC_PADDLE_CLIENT_TOKEN`, opens Paddle checkout with a hardcoded `PADDLE_PRICE_ID`, and displays "Secure payment via Paddle" (line 163).
- **`@paddle/paddle-js`** and **`@paddle/paddle-node-sdk`** in `package.json` are dead deps (never imported; the SDK is loaded via dynamic `<script>` tag). Not on import path of any source file.

### Auth consideration
`POST /api/v1/license/checkout` requires `get_current_user` (auth). The home page (`app/page.tsx`) is public. The migrated PricingCard must guard: if `!isAuthenticated()`, redirect to `/login` before calling `initiateCheckout`.

---

## 2. Verifiable Goals

1. `components/PricingCard.tsx` line 163 reads "Secure payment via Creem" (not Paddle).
2. PricingCard's Buy Now button calls `initiateCheckout()` (Creem) and redirects to `res.checkout_url` — no Paddle SDK script loaded or `window.Paddle` referenced.
3. `npx tsc --noEmit` exits 0 (no type errors from removed Paddle types / new imports).
4. `npm run build` exits 0 (12/12 pages compiled, standalone emitted).
5. `.env.example` no longer lists Paddle env vars as active (marked removed/legacy).

---

## 3. Changes

### 3.1 `components/PricingCard.tsx` — Replace Paddle SDK with Creem checkout

**Remove:**
- The `declare global { interface Window { Paddle: ... } }` block (lines 5–14).
- `const PADDLE_PRICE_ID = "pri_01kyweg4y7hjxvv4ppg33x422y"` (line 16).
- The `paddleReady` state variable and its `setPaddleReady` calls (lines 21, 40, 63, 141).
- The entire Paddle SDK `useEffect` block (lines 33–82): token check, `initPaddle()`, dynamic `<script>` injection, `window.Paddle.Initialize`.
- The Paddle checkout call `window.Paddle.Checkout.open(...)` (lines 100–102) and the `!window.Paddle` guard (line 85).

**Add:**
- `import { useAuthStore } from "@/stores/authStore";`
- `import { initiateCheckout } from "@/lib/api/license";`

**Rewrite `handleCheckout`:**
```typescript
const handleCheckout = useCallback(() => {
  const isAuthenticated = useAuthStore.getState().isAuthenticated;
  if (!isAuthenticated()) {
    router.push("/login");
    return;
  }
  setLoading(true);
  setError(null);

  checkoutTimeoutRef.current = setTimeout(() => {
    setLoading(false);
    setError("Checkout timed out. Please try again.");
    checkoutTimeoutRef.current = null;
  }, 10000);

  initiateCheckout({
    success_url: window.location.origin + "/license?activated=1",
    cancel_url: window.location.origin + "/license",
  })
    .then((res) => {
      if (checkoutTimeoutRef.current) {
        clearTimeout(checkoutTimeoutRef.current);
        checkoutTimeoutRef.current = null;
      }
      window.location.href = res.checkout_url;
    })
    .catch((err) => {
      if (checkoutTimeoutRef.current) {
        clearTimeout(checkoutTimeoutRef.current);
        checkoutTimeoutRef.current = null;
      }
      setError(err instanceof Error ? err.message : "Checkout failed");
      setLoading(false);
    });
}, []);
```

**State simplification:**
- Remove `paddleReady` state. Keep `loading`, `error`, `testingMode`, `mountedRef`, `checkoutTimeoutRef`.
- `buttonDisabled = loading || (!testingMode && !paddleReady)` → `loading` (drop the `paddleReady` guard since there's no async SDK to wait on).

**Testing mode:**
- Currently triggered by `!NEXT_PUBLIC_PADDLE_CLIENT_TOKEN`. Since Creem checkout is backend-driven (no frontend token), testing mode should trigger when `NEXT_PUBLIC_API_BASE_URL` is unset or localhost dev without backend. Keep the existing semantics: when the API base URL is the default dev value and no auth token exists, fall back to the `/portal` link. Concretely: set `testingMode = !process.env.NEXT_PUBLIC_API_BASE_URL` (in dev, the env var may be absent → testing mode link to `/portal`).
- Update testing-mode button text: keep "Buy Now — $50 one-time".
- Update the footer text:
  - Testing mode: "Sandbox checkout — no real charges" (unchanged — still accurate).
  - Production: "Secure payment via Creem" (changed from Paddle).

**Text change (line 163):**
```
"testingMode ? "Sandbox checkout — no real charges" : "Secure payment via Creem""
```

**Add `router` import** (`useRouter` from `next/navigation`) for the `/login` redirect — same pattern already used in `app/license/page.tsx`.

### 3.2 `.env.example` — Remove Paddle env vars

Replace the Paddle block (lines 10–15):
```
# Paddle client vars referenced by components/PricingCard.tsx.
# NOTE: Payments are processed via Creem (Merchant of Record) on the backend.
# These Paddle vars are legacy/optional and currently unused — left for reference.
NEXT_PUBLIC_PADDLE_CLIENT_TOKEN=
NEXT_PUBLIC_PADDLE_ENVIRONMENT=production
NEXT_PUBLIC_PADDLE_PRICE_ID=
```
With a comment noting Paddle is fully retired:
```
# Payments are processed via Creem (Merchant of Record) on the backend
# (FastAPI POST /api/v1/license/checkout). No frontend payment SDK env vars needed.
# Legacy Paddle vars (NEXT_PUBLIC_PADDLE_CLIENT_TOKEN, etc.) have been removed.
```

### 3.3 `package.json` — Optional cleanup (flag, not required for build)

`@paddle/paddle-js` and `@paddle/paddle-node-sdk` are not imported by any source file. They can be removed from `package.json` dependencies as a follow-up. **Out of scope unless it blocks the build.** (Build should succeed with dead deps present.)

---

## 4. Execution Steps (for implementation agent)

1. Edit `components/PricingCard.tsx` per §3.1 (remove Paddle, add Creem checkout + auth guard).
2. Edit `.env.example` per §3.2 (remove Paddle vars).
3. Run `npx tsc --noEmit` — must exit 0.
4. Run `npm run build` (`next build && node scripts/prepare-standalone.mjs`) — must exit 0, 12/12 pages.
5. Verify `.next/standalone/server.js` exists and bundles are in place.

---

## 5. Validation

- **Text:** `grep -rn "Secure payment via Creem" components/PricingCard.tsx` → match found.
- **No Paddle:** `grep -n "Paddle\|paddle\|PADDLE" components/PricingCard.tsx` → zero matches.
- **Types:** `npx tsc --noEmit` → exit 0.
- **Build:** `npm run build` → exit 0; confirm `.next/standalone/` tree exists.
- **No regression:** `app/license/page.tsx` still works (unchanged, already Creem).

---

## 6. Risks

- **Auth on home page:** PricingCard's Buy Now now redirects unauthenticated users to `/login`. This is a UX change from the old Paddle inline checkout (which didn't require auth). Acceptable and consistent with `app/license/page.tsx`.
- **Testing mode detection:** The condition shifts from "no Paddle token" to "no API base URL". In production the API URL is always set, so testing mode won't trigger. In local dev without `.env.local`, the axios default (`http://localhost:8000`) means testing mode is off → the button calls the API and shows an error if the backend is down. This is acceptable; the "Download App" `/portal` link remains as a fallback.

---

## 7. Phase 1 Execution (COMPLETED)

The following were completed and verified:

| Step | Result |
|---|---|
| `components/PricingCard.tsx` rewritten (Paddle removed, Creem checkout + auth guard added, text → "Secure payment via Creem") | ✅ Done |
| `.env.example` Paddle vars removed | ✅ Done |
| `app/page.tsx` comment updated (Paddle → Creem) | ✅ Done |
| `npx tsc --noEmit` | ✅ 0 errors |
| `npm run build` (`next build && node scripts/prepare-standalone.mjs`) | ✅ Compiled, 15/15 routes, standalone emitted |
| `PROJECT_MAP.md` + `VERIFICATION_CHECKLIST.md` updated | ✅ Done |

### Remaining validation
- `grep "Secure payment via Creem" components/PricingCard.tsx` → ✅ match found
- `grep -i "paddle" components/PricingCard.tsx` → ✅ zero matches
- `.next/standalone/server.js` + `.next/standalone/.next/static` + `.next/standalone/public` → ✅ present

---

## 8. Phase 2 — Tauri Signing Config (COMPLETED — 2026-08-22)

**Problem:** Tauri build fails at the final step:
```
Signing ...\src-tauri\target\release\app.exe with a custom signing command
failed to bundle project: failed to run cmd
```

**Fix:** Removed the `signCommand` from `src-tauri/tauri.conf.json` (it was the only property in the `"bundle"."windows"` object):

**File:** `src-tauri/tauri.conf.json` lines 34–36

**Before:**
```json
    "windows": {
      "signCommand": "cmd /c src-tauri/sign.cmd %1"
    },
```

**After:** (deleted — `"windows"` object removed entirely from `"bundle"`)

The `"windows"` object had no other properties, so removing the whole block keeps the JSON valid. Verified: `ConvertFrom-Json` confirms the file is valid JSON, and `signCommand`/`sign.cmd` no longer appear anywhere in the file. `tauri build` now produces unsigned installers without invoking any signing command.
