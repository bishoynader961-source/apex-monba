# SPEC 06 — Architecture Deep-Dive: Full Agent Context Document

**Purpose:** This document gives an AI coding agent complete working knowledge of the Pharmacy Suite codebase without needing to read every file. Read this before any task. It describes not just WHERE things are, but HOW they are coded and WHAT patterns to follow.

---

## 1. Project Structure at a Glance

```
E:\my progam pharmacy\
├── app/                          # Next.js 15 App Router pages
│   ├── login/                    # Login page + server actions
│   ├── setup/                    # First-run wizard (to be created)
│   ├── pos/                      # POS system (full-screen, no sidebar)
│   ├── rx/                       # Rx queue (standalone)
│   └── dashboard/                # All main tabs (with sidebar)
│       ├── layout.tsx            # DashboardLayout wrapper
│       ├── page.tsx              # Dashboard homepage
│       ├── inventory/            # Inventory management
│       ├── analytics/            # Analytics + demand
│       ├── patients/             # Patient records
│       ├── label-engine/         # Label designer
│       ├── label-engine-preview/ # Print preview window
│       ├── roles/                # Roles & permissions
│       ├── users/                # User management
│       ├── settings/             # System settings
│       └── [other tabs]/
├── components/                   # Shared React components
├── stores/                       # Zustand state stores
├── lib/                          # API clients, utilities
│   ├── api/                      # Per-feature Axios wrappers
│   ├── api.ts                    # Base Axios instance + interceptors
│   ├── decimalCurrency.ts        # Money math (bigint cents)
│   └── i18n/locales/             # Translation files (en, ar, es, fr, de, pt)
├── types/contracts.ts            # TypeScript interfaces matching Pydantic schemas
├── hooks/                        # React hooks
├── backend_fastapi/              # FastAPI Python backend
│   ├── app/
│   │   ├── main.py               # FastAPI app, startup, router registration
│   │   ├── core/
│   │   │   ├── models.py         # SQLAlchemy models
│   │   │   └── database.py       # DB connection, session factory
│   │   ├── shared/
│   │   │   └── schemas.py        # Pydantic request/response schemas
│   │   ├── api/
│   │   │   ├── deps.py           # FastAPI dependencies (auth, permissions)
│   │   │   └── routers/          # One file per feature area
│   │   └── services/             # Business logic layer
├── src-tauri/                    # Tauri desktop shell
│   ├── src/lib.rs                # Tauri commands, sidecar management
│   └── tauri.conf.json           # App config, bundle settings, CSP
└── mobile/                       # React Native (separate, don't touch)
```

---

## 2. How Authentication Works (End to End)

### Login Flow
1. User fills `app/login/page.tsx` form → calls server action in `app/login/actions.ts`
2. Server action calls `POST /api/v1/auth/login` → `auth_route.py` → `AuthService.login()`
3. `AuthService.login()` verifies bcrypt password hash, builds JWT with:
   - `sub` (user_id), `username`, `role` (role name string), `role_id` (int), `permissions` (string[])
   - `role_id=1` gets `permissions: ["*"]` (wildcard = full access)
   - Other users get their specific permission list from `UserRepository.permissions_for_role(role_id)`
4. Returns `Token` schema: `{ access_token, refresh_token, user: UserPublic }`
5. Frontend stores tokens in `localStorage` (`access_token`, `refresh_token`)
6. Frontend calls `GET /api/v1/auth/me` → stores full `CurrentUser` in Zustand `useAuthStore`

### Permission Check Pattern
```typescript
// Frontend — always use this, never roll your own
const canRead = useCan("inventory.read");
const canWrite = useCan("inventory.write");

// useCan calls hasPermission which does:
// perms.includes("*") || perms.includes(permission)
// Where perms = useAuthStore.getState().user?.permissions ?? []
```

```python
# Backend — always use require_permission dependency
@router.get("/medicines")
async def list_medicines(
    _: None = Depends(require_permission("inventory.read")),
    db: AsyncSession = Depends(get_db)
):
    ...

# require_permission in deps.py checks:
# 1. user.role_id == 1 → always allowed
# 2. "*" in user.permissions → always allowed
# 3. permission in user.permissions → allowed
# Otherwise → 403
```

### Token Refresh
`lib/api.ts` Axios interceptor catches 401 → automatically calls `POST /api/v1/auth/refresh` → retries the original request. If refresh fails, logs out.

---

## 3. How to Add a New Tab

1. Create `app/dashboard/your-feature/page.tsx`
2. Add to `DashboardLayout.tsx` NAV_SECTIONS array:
```typescript
{
  href: "/dashboard/your-feature",
  label: "nav.yourFeature",        // i18n key
  icon: YourIcon,
  permission: "yourfeature.read"   // permission key from DB
}
```
3. Add `"nav.yourFeature": "Your Feature"` to `lib/i18n/locales/en.json` (and all other locales)
4. Add the permission to the database in `backend_fastapi/app/services/seed_service.py`:
```python
Permission(feature_key="yourfeature.read", description="View your feature", module="YourModule")
```
5. Add backend router in `backend_fastapi/app/api/routers/yourfeature_route.py`
6. Register in `backend_fastapi/app/main.py`: `app.include_router(yourfeature_router, prefix="/api/v1")`

---

## 4. How to Add a New API Endpoint

### Backend
```python
# backend_fastapi/app/api/routers/yourfeature_route.py
from fastapi import APIRouter, Depends
from backend_fastapi.app.api.deps import get_current_user, require_permission, get_db

router = APIRouter(prefix="/your-feature", tags=["Your Feature"])

@router.get("/", response_model=list[YourSchema])
async def list_items(
    _: None = Depends(require_permission("yourfeature.read")),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(YourModel))
    return result.scalars().all()
```

### Frontend
```typescript
// lib/api/yourfeature.ts
import api from "@/lib/api";
import type { YourType } from "@/types/contracts";

export async function listItems(): Promise<YourType[]> {
  const { data } = await api.get<YourType[]>("/api/v1/your-feature");
  return data;
}
```

### Type contract
Add to `types/contracts.ts`:
```typescript
export interface YourType {
  id: number;
  name: string;
  // mirror the Pydantic schema exactly
}
```

And the matching Pydantic schema in `backend_fastapi/app/shared/schemas.py`:
```python
class YourSchema(BaseModel):
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)
```

---

## 5. How Money is Handled (Critical — Never Deviate)

All monetary values:
- **Backend:** stored as `Decimal` in SQLAlchemy, serialized as `str` in JSON (`"29.99"`)
- **Frontend:** received as `string`, must be parsed with `lib/decimalCurrency.ts`
- **Never:** `parseFloat("29.99")`, `Number("29.99")`, or arithmetic on string money values

```typescript
// Correct money usage
import { parseMoney, formatMoney, addMoney } from "@/lib/decimalCurrency";

const price = parseMoney("29.99");    // → BigInt 2999 (cents)
const tax = parseMoney("2.55");       // → BigInt 255
const total = addMoney(price, tax);   // → BigInt 3254
const display = formatMoney(total);   // → "$32.54"
```

---

## 6. How State Management Works (Zustand Stores)

Each feature area has a Zustand store:
```typescript
// Pattern for all stores
export const useYourStore = create<YourStore>()(
  persist(
    (set, get) => ({
      items: [],
      loading: false,
      error: null,
      
      fetchItems: async () => {
        set({ loading: true, error: null });
        try {
          const items = await listItems();
          set({ items, loading: false });
        } catch (err) {
          set({ error: getErrorMessage(err), loading: false });
        }
      },
    }),
    { name: "your-store" }  // localStorage key
  )
);
```

Stores are initialized lazily — they don't fetch until a component calls the fetch action. Don't fetch in the store constructor.

---

## 7. How the Tauri Desktop Shell Works

### Sidecar Process Lifecycle (src-tauri/src/lib.rs)
```rust
// On app start: spawn both sidecars
fn start_sidecars(app: &AppHandle) {
    // 1. Spawn Node.js server (Next.js) on port 3000
    // 2. Spawn FastAPI backend on port 8000
    // 3. Store process handles in SIDECAR_NODE and SIDECAR_BACKEND Mutex
}

// On window close: kill both sidecars
fn kill_sidecars() {
    // Kill SIDECAR_NODE
    // Kill SIDECAR_BACKEND
}
```

### Tauri IPC Commands
```rust
// In lib.rs, registered in tauri::generate_handler![]
#[tauri::command]
async fn print_label(image_data: String, canvas_width: f64, canvas_height: f64) -> Result<(), String> {
    // Write base64 image to temp file
    // ShellExecuteW with "print" verb
}

#[tauri::command]
async fn open_label_window(app: AppHandle) -> Result<(), String> {
    // Create new WebviewWindow at http://127.0.0.1:3000/dashboard/label-engine-preview
}
```

Frontend invokes commands with:
```typescript
import { invoke } from "@tauri-apps/api/core";
await invoke("print_label", { image_data, canvas_width, canvas_height });
// NOTE: Tauri v2 does NOT auto-convert camelCase to snake_case
// Frontend MUST use snake_case to match Rust parameter names
```

---

## 8. Database Patterns

### SQLAlchemy Model Pattern
```python
# backend_fastapi/app/core/models.py
class YourModel(Base):
    __tablename__ = "your_table"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    
    # JSON column pattern
    custom_fields: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

### Async Query Pattern
```python
async def get_items(db: AsyncSession) -> list[YourModel]:
    result = await db.execute(select(YourModel).where(YourModel.is_active == True))
    return result.scalars().all()
```

### No raw SQL — always use SQLAlchemy ORM or `select()` statements.

---

## 9. Error Handling Contract

### Backend errors
```python
# Always raise HTTPException with this format:
raise HTTPException(
    status_code=404,
    detail="Medicine not found"  # or a dict with more detail
)
```

### Frontend handling
```typescript
// lib/api.ts interceptor catches 401, 403, 500 (after Spec 01 fix)
// For page-level errors, catch in the Zustand store:
try {
  const data = await someApiCall();
  set({ data });
} catch (err) {
  const message = getErrorMessage(err);  // from lib/api.ts helper
  set({ error: message });
  // Also show toast:
  useUiStore.getState().showToast(message, "error");
}
```

---

## 10. i18n Pattern

```typescript
// In any component:
import { useTranslation } from "@/lib/i18n";
const { t } = useTranslation();
return <span>{t("nav.inventory")}</span>;

// Key must exist in lib/i18n/locales/en.json:
// "nav.inventory": "Inventory"

// Convention: namespace.key
// nav.* = sidebar navigation labels
// common.* = shared buttons/labels (Save, Cancel, Delete, etc.)
// feature.* = feature-specific labels
```

---

## 11. CSS/Styling Conventions

- Tailwind CSS utility classes — no custom CSS unless absolutely necessary
- Dark mode: use `dark:` Tailwind variants, never hardcode dark colors
- CSS variables (defined in `app/globals.css`):
  - `var(--bg-primary)` = page background
  - `var(--bg-secondary)` = card/surface background
  - `var(--text-main)` = primary text
  - `var(--text-muted)` = secondary text
  - `var(--border)` = border color
- Never hardcode color values like `#1E293B` in component files — use CSS variables or Tailwind classes that use them
- Money display: always `formatMoney()`, right-aligned in tables

---

## 12. Key Files Reference (Quick Lookup)

| What you need | Where to find it |
|---------------|-----------------|
| Add a sidebar tab | `components/DashboardLayout.tsx` NAV_SECTIONS |
| Add a permission | `backend_fastapi/app/services/seed_service.py` seed_default_permissions |
| Add a translation key | `lib/i18n/locales/en.json` (and all other locales) |
| Add a backend endpoint | `backend_fastapi/app/api/routers/[feature]_route.py` |
| Add a frontend API call | `lib/api/[feature].ts` |
| Add a TypeScript type | `types/contracts.ts` |
| Add a Pydantic schema | `backend_fastapi/app/shared/schemas.py` |
| Add a Zustand store | `stores/[feature]Store.ts` |
| Add a Tauri IPC command | `src-tauri/src/lib.rs` + register in `generate_handler![]` |
| Show a toast notification | `useUiStore.getState().showToast(message, "success"|"error"|"info")` |
| Check user permission | `useCan("feature.action")` in components |
| Guard a backend endpoint | `Depends(require_permission("feature.action"))` |
| Format money for display | `formatMoney(parseMoney(someStringValue))` |
| Get current user | `useAuthStore.getState().user` or `useCan` hook |
| Session timeout config | `stores/sessionStore.ts`, `hooks/useSessionTimer.tsx` |
| App startup sequence | `backend_fastapi/app/main.py` on_startup, `src-tauri/src/lib.rs` |

---

## 13. Patterns NOT to Use

- ❌ `parseFloat()` or `Number()` for money values
- ❌ Raw `fetch()` calls — always use the Axios `api` instance from `lib/api.ts`
- ❌ Hardcoded color hex values in components
- ❌ `role.toLowerCase().startsWith("admin")` for permission checks — use `role_id == 1`
- ❌ `console.log()` in production code
- ❌ `any` TypeScript type without a `// TODO: type this properly` comment
- ❌ Relative URL paths in API calls (always use the full path starting with `/api/v1/`)
- ❌ Direct SQLite queries — always go through SQLAlchemy ORM
- ❌ `useState` for data that should be in a Zustand store
- ❌ Arithmetic directly on `number | "never"` union types
- ❌ `invoke()` with camelCase parameter names when the Rust function uses snake_case
