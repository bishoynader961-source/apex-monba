# Pharmacy Suite Modernization & Feature Integration Plan

This document outlines the architecture, database schema, and implementation steps to execute the comprehensive codebase audit, design system enforcement, and integration of legacy Python features into the Next.js/FastAPI stack.

## User Review Required

> [!IMPORTANT]
> This is a massive multi-phase architectural overhaul. Please review the proposed database schema changes and the technology choices below before we begin execution.

## Decisions Made

1. **OCR Temporary Storage Strategy**: Images will be processed in-memory via `io.BytesIO` using FastAPI's `UploadFile` (SpooledTemporaryFile) to prevent disk clutter and ensure speed.
2. **Third-Party Medicine API Contract & Mocking**: We will mock the external API initially. The endpoint `POST /api/v1/drugs/evaluate` will accept `{ "ndc": "string", "drug_name": "string" }` and return `{ "status": "safe" | "warning" | "severe", "message": "...", "interactions": [...] }`.
3. **Label Printing Architecture**: A dedicated Next.js print-preview route will be built, styled with explicit `@media print` CSS rules for standard thermal label dimensions (e.g., 2x1 inches). Tauri's native window management will be used to print cleanly without browser artifacts.

## Phase 1: Visual Evaluation & Design System Enforcement

- **Audit & Standardization**: Unify the UI components to match a modern, dark-themed, highly polished aesthetic with neon accents (as seen in the current application screenshots).
- **Refactoring**: Standardize Tailwind CSS across all pages (`app/dashboard/*`, `app/pos/*`).
- **Codification**: 
  - [NEW] `DESIGN_SYSTEM.md` to document color hex codes, spacing rules, card containers, and typography.

## Phase 2: Role-Based Access Control (RBAC) & Permissions

- **Backend**:
  - [MODIFY] `backend_fastapi/app/api/deps.py` or equivalent: Create a robust FastAPI dependency/middleware that injects user roles and permissions into the Request context.
- **Frontend**:
  - [MODIFY] `lib/api/auth.ts` and `stores/authStore.ts`: Ensure auth state exposes specific permissions.
  - [MODIFY] Next.js components to conditionally render buttons (like "+ New Patient") and restrict routes based on `useAuthStore().hasPermission(...)`.

## Phase 3: Porting Legacy Python Features & OCR

- **OCR Pipeline**:
  - [NEW] `backend_fastapi/app/api/routers/ocr_route.py`: `POST /api/v1/ocr` endpoint utilizing `pytesseract` to parse uploaded images.
  - [NEW] `components/OcrUploadDropzone.tsx`: Drag-and-drop component for forms.
- **Excel Import/Export**:
  - [NEW] `backend_fastapi/app/api/routers/export_route.py`: Pandas/Openpyxl-powered endpoints for streaming `.xlsx` files.
  - [NEW] Frontend Zod schemas and bulk upload component for importing files.
- **Label Printing**:
  - [NEW] Next.js print-preview route using browser `@media print` CSS for standard thermal label sizes.

## Phase 4: Multi-PC LAN Network Configuration

- **FastAPI Server Binding**:
  - [MODIFY] `backend_fastapi/run_backend.py` (and equivalent Docker/Procfile scripts) to bind Uvicorn to `0.0.0.0` instead of `127.0.0.1`, allowing LAN access.

## Phase 5: Time-Filtered Sales Analytics Dashboard

- **Backend Aggregation**:
  - [NEW] `backend_fastapi/app/services/analytics_service.py`: SQL `GROUP BY` aggregations filtering by Day/Week/Month.
  - [MODIFY] `backend_fastapi/app/api/routers/analytics_route.py` to expose this.
- **Frontend Dashboard**:
  - [MODIFY] `app/dashboard/analytics/page.tsx`: Implement the Day/Week/Month toggle switch and top-selling data tables.

## Phase 6: Vendor Management Module

- **Database Schema**:
  - Add tables: `vendors`, `vendor_items`, `purchase_history`.
- **FastAPI Endpoints**:
  - [NEW] `backend_fastapi/app/api/routers/vendors_route.py`: CRUD endpoints + `/api/vendors/receive` for stock incrementing and audit logging.
- **Frontend Interface**:
  - [NEW] `app/dashboard/vendors/page.tsx`: Directory grid, searchable dropdowns, and restock dashboard.

## Phase 7: Third-Party Medicine API Proxy & Integration

- **Database Schema**:
  - Add table: `integrations` (id, provider_name, api_key encrypted, is_active).
- **FastAPI Proxy**:
  - [NEW] `backend_fastapi/app/api/routers/integrations_route.py`: `POST /api/v1/drugs/evaluate` proxying via `httpx` with caching.
- **Frontend Guardrails**:
  - [MODIFY] Drug input forms to include "Evaluate Drug" button.
  - [NEW] Red clinical warning modal and programmatically lock "Dispense" button on severe interaction.

## Verification Plan

### Automated Tests
- `pytest` for all new FastAPI endpoints (OCR, Vendors, Integrations, Analytics).
- `vitest` for new React components (OCR Dropzone, Evaluate Drug Modal).

### Manual Verification
- Start FastAPI bound to `0.0.0.0` and access it from another device on the LAN.
- Upload a sample prescription image and verify OCR JSON payload correctly auto-fills the frontend form.
- Apply RBAC rules and verify non-admin users cannot see administrative buttons.
