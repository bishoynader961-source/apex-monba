# Plan: M98 — Post-M97 Review Resolution, Commit, and Next Clinical Milestone

**Status:** Planning
**Date:** 2026-08-26
**Predecessor:** M97 (Clinical / Patient Management Layer) — implementation complete, all gates green, **uncommitted**

---

## 1. Current State (reconciled)

### Implemented (M97 — uncommitted working tree)
- **Backend:** 6 new models (`Patient`, `InsurancePlan`, `MembersGroup`, `SigCode`, `PriceCode`, `Dispense`, `DispenseItem`), `client_tx_id` on `Receipt`/`Dispense` (LAN idempotency #11), schema v6→7 migration, `PRAGMA foreign_keys=ON` in `_configure_pragmas` (Concern 10), `isolation_level="IMMEDIATE"` on write engine (T1.5), 6 new services (`patient_service`, `insurance_service`, `dictionary_service`, `dispense_service`, `receipt_engine`, `backup`), 6 new routers (patients, insurance, dictionaries, dispense, members, admin), `seed_clinical_defaults()`, offline docs support.
- **Frontend:** `app/patients/` 7-tab page, `lib/api/{patients,insurance,dictionaries,dispense}.ts`, `stores/patientStore.ts`, `hooks/usePatients.ts`, extended `types/contracts.ts`, POS dispense integration in `app/pos/page.tsx`.
- **Tests:** 8 new test files (test_patients, test_insurance, test_dictionaries, test_dispense, test_receipt_engine, test_backup, test_patient_service, test_seed_clinical, test_docs_offline, test_license_file_import).
- **Verification:** 327 passed, 1 skipped, 90.33% coverage · `mypy --strict` 0 · `tsc --noEmit` 0 · `next build` 16/16 · `vitest` 33/33.

### Code review triggered
- The `suggest` tool initiated a review of uncommitted changes. Results may or may not have surfaced. In-progress or pending review findings are addressed in §3.

### Pending action items (from PROJECT_MAP.md)
- **npm audit:** 3 high-severity advisories (next → transitive postcss/sharp).
- **PROJECT_MAP.md §1–7:** still describes the legacy Tkinter app; modernization pass outstanding.
- **Creem live validation:** production env keys not yet supplied.

---

## 2. Immediate Priority: Resolve & Commit M97

### T1 — Fix: `write_audit` placement in `dispense_service.py`
- **Finding:** `write_audit()` at line 196 is called **outside** the `async with self.session.begin():` block. Per `audit_log.py` docstring: "the audit call is the final write before the outer commit, so this composes cleanly." The intent is for the audit row to commit **atomically** with the dispense/receipt/sold-item rows.
- **Impact:** If `AuditRepository.log` (which commits internally) fails after the dispense transaction commits, the dispense is persisted but its audit row is lost — breaking the hash chain's completeness for that event.
- **Fix:** Move the `await write_audit(...)` call **inside** the `async with self.session.begin():` block, after `logger.info("dispense_created", ...)` and before the context manager exits. The `audit_log.py` docstring explicitly says this composition is safe on SQLite (savepoint release keeps outer txn open).
- **File:** `backend_fastapi/app/services/dispense_service.py:196`

### T2 — Verify: repository `commit()` pattern
- **Finding:** New repositories (`PatientRepository.create`, `InsuranceRepository.create/update`, `MembersGroupRepository.create/update/delete`, etc.) call `await self.session.commit()` directly rather than using `async with session.begin():`.
- **Assessment:** This is consistent with the existing `LicenseRepository.create()` pattern (which also calls `session.commit()` directly). It's a valid pattern for **standalone** CRUD operations. However, the `DispenseRepository.create()` method is never called directly — `DispenseService` manages its own transaction. This inconsistency is low-risk but worth flagging in review.
- **Decision:** No change needed — the pattern matches existing codebase conventions. Document for review.

### T3 — Commit M97
- Stage: `git add` all modified tracked files + new untracked files (backend routers, services, tests; frontend components, API services, store, hooks, contracts, patients page, pos page changes).
- **Exclude:** `tsconfig.tsbuildinfo`, `package-lock.json` (auto-generated; verify before staging).
- Commit message: `feat(clinical): add patient management layer, insurance, dispensing, dictionaries, backups (M97)`
- Do **not** commit `.env` files or `pharmacy.db` (already gitignored).

### T4 — Verification re-run (post-fix)
```
cd backend_fastapi
".venv-312\Scripts\python.exe" -m pytest -q            # ≥90% coverage, 0 failures
".venv-312\Scripts\python.exe" -m mypy app --strict     # 0 errors

cd ..
npx tsc --noEmit                                        # 0 errors
npx next build                                          # 16/16 routes
npx vitest run                                          # 33/33
```

---

## 3. Short-Term: npm Audit Remediation (M98-A)

### Context
3 high-severity advisories in `next` (transitive `postcss` + `sharp`). `npm audit fix` may bump the Next major version.

### Tasks
1. **a — Investigate:** Run `npm audit` to confirm current advisories and affected packages.
2. **b — Fix postcss:** `postcss` is a direct Tailwind dependency. Pin `postcss@latest` (v8.4.31+ patches the advisory) and `autoprefixer@latest`. This is a minor/pin bump — no major version change needed.
3. **c — Fix sharp:** `sharp` is used by Next.js image optimization. Either (i) upgrade `sharp` to the latest patched version, or (ii) add `sharp` as an explicit dev dependency at the patched version, or (iii) disable image optimization (`images.unoptimized = true` in next.config.ts if no custom image optimization is used).
4. **d — Verify frontend still green:** `tsc`, `next build`, `vitest run` — no regressions.

### Risk
- `postcss`/`autoprefixer` bump could affect Tailwind class generation — verify build output is unchanged.
- `sharp` upgrade or disabling image optimization — check if any `next/image` usage in the codebase would be affected.

---

## 4. Medium-Term: Next Clinical Feature (M98-B or M99)

### Proposed: M98-B — Clinical Decision Support (Allergy Alert Banners)

**Rationale:** M97 added `patient_allergies` (free-text/tag field) to `patients` specifically so "future allergy-alert banners need no further migration." This is the natural next clinical safety feature.

### Tasks
1. **B1 — Schema:** Add `allergy_alerts` computed field via the patients API (parse the free-text `patient_allergies` into structured tags on the backend, return in `PatientRead`).
2. **B2 — Backend service:** `app/services/drug_db.py` — a local drug-name → ingredient mapping table (seeded with ~500 common drugs). Used for basic DDI screening (e.g., "warfarin" + "ibuprofen" → high bleed risk).
3. **B3 — Dispense guard:** In `DispenseService.process_dispense`, check the patient's `patient_allergies` against the dispensed drug's active ingredients. If a match, set `flags` on the `DispenseRead` response (e.g., `allergy_flags: ["Patient has documented allergy to Aspirin"]`). Do **not** block the dispense — surface as a yellow warning banner for pharmacist override (clinical review is the pharmacist's call).
4. **B4 — POS integration:** In `app/pos/page.tsx`, when the dispense response includes `allergy_flags`, render a yellow alert banner above the cart with the flag text + an "Override (requires reason)" checkbox. Log the override reason via audit.
5. **B5 — Patient page:** In `app/patients/page.tsx` General tab, surface allergy tags as colored badges next to `patient_allergies`.
6. **B6 — Tests:** Backend: `test_clinical_cds.py` (allergy match, no-match, DDI warning, override logging). Frontend: `vitest` component test for the alert banner.

### Out of scope
- Full RxNorm/FDALabel API integration (would require an external API key + rate limiting). Use a local seed table instead.
- Prescription management (`prescriptions` table) — still deferred per M97 scope.

**Decision needed before implementation:** Is the local drug→ingredient mapping table (B2) the right approach, or should we integrate against an existing internal DB (e.g., `inventory_extended` already has drug names)?

---

## 5. Documentation Sync

- Update `PROJECT_MAP.md`:
  - Mark M97 as **committed** (after T3).
  - Update §1–7 to reflect the FastAPI + Next.js + Tauri stack (currently describes legacy Tkinter).
  - Add M98-A (npm audit) and M98-B (CDS) entries to [ORPHANS & PENDING].
- Update `FLOW_LOGIC.md` §17 with any changes from the `write_audit` fix.
- Update `CHANGELOG.md` with M97 + M98-A status.

---

## 6. Task Order

| Step | Description | Tool required |
|---|---|---|
| T1 | Fix `write_audit` placement in `dispense_service.py` | Implementation agent |
| T2 | Verify repository commit pattern (no change) | Review done |
| T3 | Commit M97 | Implementation agent |
| T4 | Re-run all verification gates | Implementation agent |
| T-a | Run `npm audit`, identify fix strategy | Implementation agent |
| T-b | Apply postcss/sharp fixes | Implementation agent |
| T-c | Re-run frontend gates | Implementation agent |
| B1-B6 | Implement Clinical Decision Support (M98-B) | Implementation agent |
| Docs | Sync PROJECT_MAP.md, FLOW_LOGIC.md, CHANGELOG.md | Implementation agent |

## 7. Validation Gates

- **M97 commit:** `git show --stat HEAD` lists all expected files; `pytest` 327+ passed; `tsc` 0 errors.
- **npm audit clean:** `npm audit` shows 0 high-severity advisories (or all advisories are in optional/non-prod deps with `--audit-level=moderate` clean).
- **CDS:** `test_clinical_cds.py` passes; dispense response includes `allergy_flags` when patient allergy matches drug name.
