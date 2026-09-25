# Pharmacy Suite - Master Architecture Blueprint

## 1. System Overview
*   **Frontend:** React, Next.js (Standalone), Zustand, Tailwind CSS
*   **Backend:** FastAPI, Python, SQLAlchemy
*   **Database:** SQLite
*   **Desktop Shell:** Tauri (Windows targeted)

## 2. Feature Map & Code Pointers
*(AI Agent: Map out the existing codebase here. For each feature below, specify the exact React component, Zustand store, FastAPI router, and SQLAlchemy model responsible for it. Keep it brief.)*

*   **Authentication & Roles:** (e.g., `app/login/page.tsx`, `stores/authStore.ts`, `api/routes/auth.py`, `models/user.py`)
*   **Inventory & POS:** 
*   **Prescription/RX Queue:** 
*   **Label Engine:** 
*   **Settings & Session:** 

## 3. Global Refinement Strategy
*(AI Agent: List the strict rules for code modification during this phase)*
1.  **Strict Type Safety:** All TypeScript interfaces must match Pydantic schemas exactly.
2.  **Error Boundaries:** All React routes must be wrapped in error boundaries to prevent white screens.
3.  **API Consistency:** All frontend API calls must handle 401, 403, and 500 status codes gracefully with user-facing toast notifications.
4.  **No Dead Code:** Remove unused variables, imports, and console.logs.