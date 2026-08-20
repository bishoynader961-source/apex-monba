# B8 — Restore 90% coverage gate (direct-await unit tests)

> **Date:** 2026-08-20
> **Scope:** Restore the backend coverage gate `fail_under = 90` and raise **measured** coverage to green by adding direct-await unit tests for the four async services whose bodies are under-reported by coverage.
> **Mode:** Implementation-ready — an execution-capable agent creates `backend_fastapi/tests/test_b8_coverage.py` and flips the gate.

---

## 1. Status (HEAD `5aa4329`)
- B7 `stack-smoke` CI job is present in `.github/workflows/ci.yml` (verified via `git show HEAD:.github/workflows/ci.yml`). Validation needs a push/PR (no local Docker).
- `backend_fastapi/pyproject.toml`: `fail_under = 0` (repo default), `pytest-cov` declared. `backend_fastapi/.coverage` is an untracked run artifact (dirty in `git status`).

## 2. Root-cause finding (drives the strategy)
Coverage.py **7.15.4** in this env does **not** trace async coroutine bodies driven through the `AsyncClient`/ASGI HTTP path, but **does** trace them under a **direct `await` inside the test coroutine**.
- Evidence: `tests/test_pos.py::test_checkout_success_and_tax` (HTTP) returns `201` with a marker inside `PosService.process_checkout`, yet coverage reports `pos_service.py` lines `108-230` (the whole body) missing. A direct-await probe (`await PosService(session).process_checkout(...)`) covers the same body (`pos_service.py` 54%, lines 110–187 hit).
- The full HTTP suite (131 passed) leaves `pos_service` 44%, `auth_service` 57%, `inventory_service` 62%, `sync_service` 57% — systematically under-reported.
- **Not** fixed by `concurrency = ["asyncio"]` (invalid choice → `ConfigError`); asyncio is auto-traced. `core = ctrace` / `COVERAGE_CORE=ctrace` also no-op.

**Decision:** add **direct-await unit tests** (use the existing `session` fixture = in-memory aiosqlite). They are traced. Existing HTTP tests remain as behavior/integration coverage; overlap is fine.

## 3. Goal
`python -m pytest -q` from `backend_fastapi/` exits `0` with the `fail_under = 90` gate enforced (Total ≥ 90 %).

## 4. Concrete test design — `backend_fastapi/tests/test_b8_coverage.py`

### Fixtures / imports (mirror `test_pos_hardening.py`)
```python
import os
import pytest
from decimal import Decimal
from app.core.models import (Product, InventoryExtended, SyncInventory, Role, Permission, RolePermission, User, Shift)
from app.core.repositories import UserRepository, BatchRepository, SyncRepository
from app.services.pos_service import PosService
from app.services.inventory_service import InventoryService
from app.services.sync_service import SyncService
from app.services.auth_service import AuthService
from app.shared import config as config_mod
from app.shared.security import (hash_password, set_pin_pepper, PinPepper, seal_lockout, get_pin_pepper)
from app.shared.schemas import (CheckoutRequest, CheckoutLineIn, CurrentUser, DrawerMovementCreate,
    ShiftOpenRequest, ShiftCloseRequest, RefundRequest, SyncPushEntry, UserCreate)
```
- Seed a role + grants helper (`pos.checkout`, `pos.drawer`, `inventory.reports`, `users.write`).
- Seed a user: `UserRepository(session).create("adminroot", "Admin", hash_password("Password123!@#"), role.id)`.
- PIN pepper (env backend):
  ```python
  os.environ["PHARMACY_PEPPER_KEY"] = "test-pepper-secret-0123456789"
  set_pin_pepper(PinPepper(backend="env", env_key="PHARMACY_PEPPER_KEY", path="pepper_test.bin"))
  yield
  set_pin_pepper(None)
  ```
- `seed_product(session, name, price)` → `Product(name, price=Decimal(str(price)), internal_unique_barcode=f"INT-{name[:3].upper()}", vendor_name="Acme", expiry_date="2030-01-01")` + commit.
- `receive(session, name, lot, qty)` → `InventoryService(session).receive_batch(name, lot, "2030-01-01", qty, 1.0, "Acme")` + commit.

### A. `pos_service.py` (miss `60-61,108-230,245-259,272,281-311,322-345,357-409,413-429`)
- `test_skew_bad_timestamp` — `CheckoutRequest(client_timestamp="not-a-date")` → `process_checkout` (covers `_skew_seconds` ValueError 60-61).
- `test_checkout_success` — seed product+lot; `await PosService(session).process_checkout(CheckoutRequest(line_items=[CheckoutLineIn(product_name="P", quantity=2)], payment_method="Cash"), CurrentUser(id=1,username="adminroot",role="admin",permissions=["pos.checkout"]))`; assert `receipt_number`/`net_total`/`total_amount` (covers 108-226 + finally 227-230).
- `test_checkout_not_found` — unknown product → `NotFoundError` (109).
- `test_checkout_multi_terminal` — `monkeypatch.setattr(config_mod.settings, "multi_terminal", True)`; cover 188-204; to hit the `except`/`logger.warning` (204) `monkeypatch.setattr(SyncRepository, "append_outbox", make_async_raiser)`.
- `test_record_drawer_movement` — `DrawerMovementCreate(amount=Decimal("50"), reason="cash-in", cashier="adminroot")` → `record_drawer_movement` (245-259).
- `test_open_shift` — `ShiftOpenRequest(opening_float=Decimal("100"))` → `open_shift` (271-272).
- `test_close_shift_not_found` / `test_close_shift_already_closed` (raises `AppException` 409, 283-284) / `test_close_shift_success` (seed `open_shift` + a Cash `Receipt` + `paid_out` `DrawerMovement`, then `close_shift(ShiftCloseRequest(shift_id, counted_cash=Decimal("200")))`; assert `expected_cash`=`variance`) (281-318).
- `test_preview_shift_not_found` / `test_preview_shift_success` (322-350).
- `test_refund_not_found` (358-359) / `test_refund_already_refunded` (seed receipt+`Refund`, expect 409 360-368) / `test_refund_success` (seed a `Receipt` + `ReceiptItem`s, then `refund`; assert ledger reversal + restock) (370-409).
- `test_sales_report` — seed a Cash `Receipt` and a `Refund`; assert `gross_revenue`/`refund_total`/`net_revenue`/`by_payment_method` (411-435).

### B. `auth_service.py` (miss `48-49,59-81,96,101,103-105,110-126,134,137,156,161,169-173,177,183,210-253`)
- `test_parse_locked_until_invalid` — `AuthService._parse_locked_until("garbage")` → `None` (48-49).
- `test_authenticate_inactive` (59-60) / `test_authenticate_locked` (63-64) / `test_authenticate_wrong_pw_lockout` (5 fails → `locked_until` set, 66-73) / `test_authenticate_success` (75-81; assert `user.failed_attempts==0`).
- `test_refresh_wrong_type` (`decode_token` non-refresh → 401, 100-101) / `test_refresh_unknown_user` (103-105).
- `test_register_conflict` (110-112) / `test_register_weak_password` (e.g. `"short"` → `AppException` 116-131) / `test_register_success` (134-126; assert audit logged). Use `UserCreate(username="new", display_name="N", password="Password123!@#", role_id=role.id)`.
- `test_set_pin_unknown_user` (134) / `test_set_pin_no_pepper` (`set_pin_pepper(None)` then expect `UnauthorizedError`, 135-137).
- PIN (env pepper fixture): `test_pin_login_not_found_or_no_pin` (156) / `test_pin_login_no_pepper` (`set_pin_pepper(None)` → 161) / `test_pin_login_tampered` (after `set_pin`, overwrite `user.lockout_hmac=b"x"*32`, commit, expect `ForbiddenError`, 169-173) / `test_pin_login_locked` (set `pin_locked_until` future, 177) / `test_pin_login_wrong_then_lockout` (wrong PIN 5× → `UnauthorizedError`, 180-190) / `test_pin_login_success` (success → `Token`, 192-202).
- `test_approve_action_unknown` (210-211) / `test_approve_action_no_pepper` (214-215) / `test_approve_action_tampered` (221-225) / `test_approve_action_locked` (229) / `test_approve_action_wrong_pin` (233-242) / `test_approve_action_success` (`create_approval_token` returned, 252-253).

### C. `inventory_service.py` (miss `78,83,87,94,115,120-125,136-144,160,183-219,223-225,234-242`)
- `test_fifo_recalled` (seed lot + `recalled=1` via SQL/raw `update`, expect `RecalledLotError`, 78) / `test_fifo_expired` (expiry in past → `ExpiredLotError`, 83) / `test_fifo_missing` (`available==0` → `MissingLotError`, 87) / `test_fifo_oversell` (sellable < qty → `OverSellError`, 94).
- `test_return_stock_zero` (`quantity<=0` returns, 115) / `test_return_stock_new_lot` (no lots → adds `InventoryExtended`, 120-125) / `test_return_stock_existing` (adds to lot).
- `test_low_stock_override` (`threshold_override`, 136-144).
- `test_expiring_soon` (seed `InventoryExtended` with near expiry → `BatchRead`, 160).
- `test_stock_levels` (seed products + inventory + expiring batches; assert `is_low_stock`, 183-219).
- `test_get_batch_not_found` (223-225) / `test_adjust_batch_negative` (`BatchUpdate(on_hand=-1)` → `ValidationError`, 228-231) / `test_adjust_batch_not_found` (233-235) / `test_adjust_batch_ok` (236-242).

### D. `sync_service.py` (miss `38-57,69,71-78,84,89-91`)
- `test_sync_push_dedup_and_oversell` — two `SyncPushEntry`s (first accepted+applies deltas, second deduped); an over-sell entry clamps to 0 and inserts a `Discrepancy` (38-57). `payload={"items":[{"product_name":"P","quantity":1}]}`.
- `test_sync_apply_deltas_skip_empty` (item with `quantity<=0` skipped, 69) / `test_sync_apply_deltas_oversell` (`on_hand<qty` → clamp 0 + over=True, 71-77) / normal decrement (76-77).
- `test_sync_list_discrepancies` (84) / `test_sync_resolve_not_found` (`resolve_discrepancy(999)` → `NotFoundError`, 89-91).

## 5. Affected files
| File | Change |
|------|--------|
| `.gitignore` | add `backend_fastapi/.coverage` (already intended) |
| `backend_fastapi/pyproject.toml` | `[tool.coverage.report] fail_under = 0` → `90` (**apply AFTER tests green**) |
| `backend_fastapi/tests/test_b8_coverage.py` | **NEW** — direct-await unit tests (T4) |

## 6. Validation gate
1. `git` clean of `backend_fastapi/.coverage` after `.gitignore` (run `pytest` regenerates it but it's ignored).
2. With `fail_under` still `0`, run `python -m pytest tests/test_b8_coverage.py -q --cov=app --cov-report=term-missing`; confirm `pos/inventory/auth/sync` each largely covered and **TOTAL ≥ 90 %**.
3. Set `fail_under = 90`. Run `python -m pytest -q` → exits `0` (no `Coverage failure`).

## 7. Risks / notes
- Do **not** use `concurrency = ["asyncio"]` (invalid). Don't chase coverage-core fixes; direct-await is the verified fix.
- Keep the existing `test_pos.py` / `test_pos_hardening.py` / `test_auth*.py` / `test_inventory.py` / `test_sync.py` — they cover behavior even though their async bodies aren't counted.
- B7 `stack-smoke`: validate only via push/PR (no Docker locally).
- `PROJECT_MAP.md`/`FLOW_LOGIC.md` absent in repo root; if added later, note this coverage-strategy change (direct-await tests because HTTP-async bodies are under-counted by coverage 7.15.4 here).
