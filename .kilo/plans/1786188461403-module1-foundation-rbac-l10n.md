# Module 1 — P0 Foundation: RBAC, Localization, Constants

**App root:** `archive/` · **Verified env:** Python 3.14.3, customtkinter **6.0.0**, SQLite
**Scope decision:** Delta-only. Module 1 is ~85% already implemented; this plan fixes two P0 startup crashes, closes the verified gaps, and closes Global Standards #1, #3, #4 with one proven consumer each.

---

## 0. Verified baseline — DO NOT re-implement

Confirmed present and correct by direct code inspection. Any implementation agent must **leave these alone**:

| Brief item | Location | Status |
|---|---|---|
| `auth_crypto.hash_secret` / `verify_secret` (scrypt N=2¹⁴/r=8/p=1, `salt‖digest`, `hmac.compare_digest`) | `archive/auth_crypto.py` (67 lines) | ✅ exactly as specified |
| `roles`/`users`/`permissions`/`role_permissions`/`system_settings` DDL + 2 indexes | `database.py:396–440` | ✅ |
| Permission catalog seed | `database.py:443–463` — **15** keys (brief said 12; superset kept) | ✅ |
| 4 seed roles + `role_permissions` map | `database.py:466–496` — `owner`/`manager`/`pharmacist`/`cashier` | ✅ |
| RBAC lookups under `@_db_fallback` | `database.py:518–850` (`get_roles`, `get_permissions`, `get_role_permissions`, `get_user_role_id`, `get_user_permissions`, `count_users`, `create_user`, `authenticate_user`, `user_has_pin`, `toggle_permission`) | ✅ + full `db.py` ORM parity |
| Master Owner override, encrypted | `owner_override_hash` (scrypt) + `owner_override_rotated`; `database.py:786–853`; forced rotation in `main_app.run_startup_gate:236`; `ui_admin_roles.open_admin_roles` requires `roles.manage` **and** override re-auth | ✅ |
| `set_kv`/`get_kv` on `system_settings` | `database.py:69–98` | ✅ |
| `LocalizationManager` | `localization_manager.py` — singleton, override→cache→OS locale→IP chain, `$`/`£`/`€`, Sales Tax/VAT/MwSt., `format_money`/`parse_money`, listeners, `_broadcasting` guard | ✅ |
| `"status_dashboard"` in all 6 locales | `en/de/es/fr/pt/ar.json` | ✅ (`_NAV_ICONS` untouched) |
| `"change_due"` key present in all 6 | — | ✅ key exists (values need translating — see T2) |
| `PAYMENT_CASH = "cash"` + refactored comparisons | `ui_pos_retail.py:73`, used at 329 / 931 / 937 / 1385; combobox still shows `i18n.t(key)` at 558/564 | ✅ |
| `COLOR_CARD_BG` in balance summary | `ui_pos_retail.py:484` | ✅ |
| Treeview headers localized + `apply_treeview_style` | `ui_pos_retail.py:436–441` | ✅ |
| `i18n.t('change_due')` at all 4 sites with `f"{...}: {...}"` | `ui_pos_retail.py:595 / 964 / 969 / 1362` | ✅ |
| `_patient_label` initial text `i18n.t("select_a_patient")`, `anchor="e"` | `ui_pos_retail.py:602–606` | ✅ |

---

## 1. Decisions

- **D1 — Permission catalog stays a superset.** Keep the existing 15 keys and add 2 (`backup.manage`, `settings.view`) → **17**. Reducing to the literal "12" would break `test_rbac.py` and the live gates in `ui_inventory_management.py`, `ui_report_tab.py`, `ui_enterprise_navigation.py`.
- **D2 — One role system.** The `Admin`/`User` `CTkSegmentedButton` in `ui_settings_tab.py:249–259` is security theater: in-memory only, defaults to `Admin`, never persisted, and only toggles three widget `state=` flags. It is **removed** and replaced with a read-only "Signed in as" label sourced from `auth_session` + `database.get_user_role_id`. The RBAC tables are the single source of truth for "User Role".
- **D3 — Gating is hide-in-nav + enforce-in-handler (defense in depth).** Handler gates are mandatory because `TabViewCompat.set()` can be invoked programmatically — `NavigationDrawer._on_banner_change_region` (`ui_navigation.py:280`) already does exactly that.
- **D4 — Region fields get one real consumer.** `LocalizationManager.get_field_visibility()` currently has **zero** callers and inconsistent key sets. Normalize it, add `field_label()`, add a reusable `RegionFieldSet`, and wire it into the patient add/edit dialog as proof-of-life. Modules 5/6 reuse it.
- **D5 — Tooltips get a re-localizing helper + Module-1-scope attachment.** `ui_tooltip.Tooltip` has zero call sites app-wide, never re-reads on language change, and has broken `destroy()` logic. Fix the primitive, add `attach_key()`, attach only to widgets Module 1 touches.
- **D6 — `database.py` and `db.py` must change in lockstep.** `@_db_fallback` delegates to `db.py` **first**. `db.py` has its own RBAC seed block at `db.py:560–650`. Seeding new permissions in `database.py` alone would silently no-op on SQLAlchemy-enabled installs.
- **D7 — i18n needs a real unregister path.** `i18n._LISTENERS` has no removal API (Risk #1 from review). Closures that guard on `winfo_exists()` only *hide* the leak; the callback object stays rooted forever. Add `i18n.unregister_listener(cb)` and use it in `Tooltip` and `RegionFieldSet` cleanup.
- **D8 — Cashiers get a trimmed Settings tab, not a wall of Access-Denied popups.** `settings.view` is granted to every role so the language selector stays reachable (D2), but the administrative controls (Save-all, Backup, Audit Log, email/PG/DB-path config) are grouped in an `admin_frame` whose visibility is gated by `settings.manage` at the widget level. Cashiers keep a lightweight Save for language/theme only. This is the fix for the "Settings Trap" review note — nav hiding (T6) plus handler gates (T5) plus local widget hiding (T5) is defense in depth.
- **D9 — Patient dialog stays fixed-size; the dynamic field block scrolls.** Wrapping `RegionFieldSet` in a `ctk.CTkScrollableFrame` removes the vertical-clipping risk without making the whole `520x520` dialog resizable (which would let users stretch it horizontally and produce ugly layout).

---

## 2. P0 — App does not launch (fix first, verify, then continue)

Both are hard crashes inside `PharmacyApp.__init__`. The previous "all tasks COMPLETE" claim in `.kilo/plans/1786177170941-*.md` was never validated by launching the app.

### T1a — `ui_patients_tab.py:52` — use before assignment (crashes FIRST)
`apply_treeview_style(self.tree_patients)` runs at line 52; `self.tree_patients` is not created until line 55. `PharmacyApp` never defines it earlier (`ui.py` only references it via `setup_patients_tab` at `ui.py:170`).
→ `AttributeError: 'PharmacyApp' object has no attribute 'tree_patients'`
**Fix:** delete line 52 and call `apply_treeview_style(self.tree_patients)` immediately after the `ttk.Treeview(...)` construction (after line 55, before the `heading(...)` calls).
**Verified:** this is the only inverted call site — all 23 other `apply_treeview_style` call sites assign the tree first.

### T1b — `ui_pos_retail.py:515` — `CTkLabel` missing required `master`
```python
self._subtotal_label = ctk.CTkLabel(            # ← no master
    text=f"{i18n.t('pos_subtotal')}: {self.app.currency.fmt(0)}", ...
)
```
CTk 6.0.0 signature is `CTkLabel(self, master: Any, ...)` — `master` is a required positional.
→ `TypeError` in `_build_balance_summary()` (L482) ← `EnterprisePosFrame.__init__` (L389) ← `setup_pos_retail_tab` (L1539) ← `main_app._patched_init` (L142).
**Fix:** pass `card` as the first positional argument, matching every sibling label in the same method.
**Verified:** the only missing-master CTk widget construction in `archive/`; `ctk.CTkLabel` is not monkey-patched anywhere.

### T1c — `ui_patients_tab.py:72` — scrollbar in the wrong grid row (same 3 lines)
Tree is `grid(row=2)`; its scrollbar is `grid(row=1, column=1)`. Fix to `row=2, column=1, sticky="ns"` while the file is open.

**Gate:** launch the app and reach the dashboard before starting T2. Nothing downstream is verifiable until this passes.

---

## 3. Tasks

### T2 — Locale corrections, all 6 files (`archive/locales/*.json`)
Do not modify `_NAV_ICONS`. After edits, **all 6 files must have identical key sets.**

**T2a — strip trailing colons** (fixes the `Change:: $0.00` class of bug):
| Key | Current | Target |
|---|---|---|
| `change` | `Change:` / `Wechselgeld:` / `Cambio:` / `Monnaie:` / `Troco:` / `المبلغ المتبقي:` | same minus the `:` |
| `patient_label` | `Patient:` in en/de/es/fr/pt, `المريض:` in ar | `Patient` / `Patient` / `Paciente` / `Patient` / `Paciente` / `المريض` |

`patient_label` is a **newly found second instance** of the same bug: `ui_pos_retail.py:908` does `f"{i18n.t('patient_label')}: {...}"` → renders **"Patient:: Jane Doe"**. Stripping the colon fixes it without touching the code.
`change` is now referenced from zero Python call sites (verified) — this edit is spec compliance + prevents regression.

**T2b — translate keys that are English placeholders in 5 locales:**
- `change_due` — currently `"Change Due"` in de/es/fr/pt/ar. Suggested: `Rückgeld` / `Cambio a devolver` / `Monnaie à rendre` / `Troco a devolver` / `المبلغ المستحق إرجاعه`.
- `select_a_patient` — currently `"Please select a patient."` everywhere. It is used **only** as a placeholder/label in `ui_pos_retail.py:603 / 653 / 657` (verified — no warning-dialog usage), so change en to `Select a patient` (no trailing period) and translate: `Patient auswählen` / `Seleccionar paciente` / `Sélectionner un patient` / `Selecionar paciente` / `اختر مريضاً`.

**T2c — close the 10-key drift.** `de/es/fr/pt` are each missing exactly these 10 keys that `en`/`ar` have, so the nav region indicator and region banner silently render English there:
`region_indicator`, `change_region`, `change_region_c`, `current_region`, `region_changed`, `region_changes_may_affect`, `region_banner_title`, `region_banner_msg`, `region_banner_dismiss`, `region_banner_change`.

**T2d — new keys required by T5–T8** (add to all 6, translated):
- `signed_in_as` — "Signed in as {user} ({role})"
- `permission_required` — "Requires the '{feature}' permission"
- Region field labels: `field_dea_number`, `field_npi`, `field_nhs_number`, `field_gphc_number`, `field_exemption_category`, `field_pzn_code`, `field_insurance_bin`, `field_insurance_pcn`, `field_scheme_pcn`, `field_group_number`
- Tooltip keys (`tip_` prefix): `tip_nav_settings`, `tip_nav_enterprise_settings`, `tip_nav_status_dashboard`, `tip_backup_database`, `tip_audit_log`, `tip_save_settings`, `tip_pos_payment_method`, `tip_pos_amount_tendered`, `tip_pos_tax_exempt`, `tip_pos_process_payment`, `tip_region_fields`

### T3 — `ui_pos_retail.py` localization polish
- **L1366** (`_on_checkout_done` reset) and **L1461** (`clear_all`): replace `self._patient_label.configure(text="—")` with `configure(text=i18n.t("select_a_patient"))`. These are the last two em-dash placeholders; the constructor path (L602–606) is already correct.
- **L908**: no code change needed once T2a strips the colon from `patient_label`; re-read it to confirm it renders `Patient: <name>`.
- Register the existing language-change hook pattern (`_on_payment_lang_change`, L568–576) for `_patient_label` and `_change_due_label` so a runtime language switch re-renders them.

### T4 — Extend the permission catalog (`database.py` **and** `db.py`)
- Append to `_RBAC_FEATURES` (`database.py:443–459` **and** the mirrored block in `db.py:~580–605`):
  - `("backup.manage", "Create and restore database backups")`
  - `("settings.view", "View application settings")`
- Update `_RBAC_ROLES` (`database.py:466–480` **and** `db.py:607–628`):
  - `owner` — already `{k for k, _ in _RBAC_FEATURES}`, picks both up automatically
  - `manager` — add `backup.manage`, `settings.view`
  - `pharmacist` — add `settings.view`
  - `cashier` — add `settings.view` (the language selector lives in Settings; cashiers must reach it) but **not** `settings.manage`, `backup.manage`, or `audit.view`
- Add `"backup.manage"` to `authz.SENSITIVE_FEATURES` (`authz.py:16–25`) so it inherits the PIN re-prompt.
- Seeding is `INSERT OR IGNORE` and `init_db()` runs on every startup (`main_app.py:258`), so existing databases pick the new rows up with no migration.

### T5 — Settings tab: remove the fake role control, gate the admin actions, trim the cashier view
`archive/ui_settings_tab.py` + `archive/ui.py`
- Delete `ui_settings_tab.py:249–259` (`role_label`, `self.role_segmented`, `self.user_role`, `self._update_role_controls()` call) and the now-dead `_on_role_change` (L419–421) / `_update_role_controls` (L424–434).
- Remove the corresponding imports/bindings: `ui.py:88` and `ui.py:618–619`. `self.user_role` has no other consumer (verified).
- Put a read-only label in that grid slot: `i18n.t("signed_in_as", user=..., role=...)` from `auth_session.current_user_id()` + `database.get_user_role_id()` + `database.get_roles()`.
- **Group the administrative controls into `admin_frame`** (a `ctk.CTkFrame` in `scroll`): `save_btn` (L287), `backup_btn` (L290), `audit_btn` (L293), the email/SMTP config block, the PostgreSQL/db-path block, and the signed-in label. The non-admin controls (pharmacy name/address/tax, language, theme, receipt header/footer, expiry threshold, ignore list) stay directly in `scroll` so cashiers still see them.
- After building the frame, set its visibility from the live session:
  ```python
  _admin = authz.check_permission(auth_session.current_user_id(), "settings.manage")
  admin_frame.grid(...) if _admin else admin_frame.grid_remove()
  ```
  Add `tip_settings_admin_only` to the frame explaining it is hidden without `settings.manage`.
- **Cashiers still need to persist language/theme.** Add a separate lightweight `save_btn_basic` (visible when `_admin` is False, i.e. only `settings.view`) that calls the same `save_settings` (whose own `settings.manage` guard is a no-op for these fields). This is the concrete fix for the "Cashier Settings Trap": a cashier sees only the general section + a basic Save, never the Backup/Audit/Email/DB-path buttons.
- Gate `_open_audit_log_viewer` (L448) — currently **completely ungated**:
  ```python
  if not authz.require_pin_for("audit.view", self):
      return
  AuditLogViewer(self)
  ```
  (Matches the existing gate in `ui_enterprise_navigation.py:40/56`.)
- Gate `backup_database_gui` (L437) — currently **completely ungated**: `require_pin_for("backup.manage", self)`, and on success `audit_log.log_action("backup.created", backup_path, user_pin=str(auth_session.current_user_id()))`.
- Gate `save_settings` (L640) with `authz.require_permission("settings.manage")` or an inline `require_pin_for` guard (defense in depth; the basic Save only touches language/theme fields).

### T6 — Navigation-level RBAC (`ui_navigation.py` + `main_app.py`)
- Add a module-level map in `ui_navigation.py`, keyed by **i18n key** (not display text) so it survives language switches:
  ```python
  NAV_PERMISSIONS = {
      "settings": "settings.view",
      "enterprise_settings": "settings.manage",
      "status_dashboard": "reports.view",
  }
  ```
- Add `NavigationDrawer.set_button_visible(name: str, visible: bool)` — `self._buttons[name]` is a `CTkButton` whose master is its `btn_frame`; toggle with `btn.master.grid_remove()` / `grid()`. No-op on unknown names.
- In `main_app._rbac_init`, after `run_startup_gate(self)` succeeds, resolve each key via `i18n.t(key)` and call `self.nav_drawer.set_button_visible(label, authz.check_permission(uid, feature))`. Re-apply after `ui_auth.force_relogin` (the `auth_session.start_session_timer` callback at `main_app.py:274`).
- Note: `create_navigation_system` builds **all** buttons from `_NAV_ICONS` eagerly at `ui.py:127`, independent of `tab_view.add()`, so gating must run after the login gate, not at drawer construction.
- Keep the T5 handler gates — hiding a nav button does not stop `tab_view.set()`.

### T7 — Tooltip foundation (`ui_tooltip.py` + `i18n.py`) — Global Standard #1
- **Add `i18n.unregister_listener(cb)`** to `archive/i18n.py` (Risk #1 from review). It removes `cb` from `_LISTENERS` by identity if present, so listeners can be torn down on widget `<Destroy>` instead of being rooted forever:
  ```python
  def unregister_listener(callback) -> None:
      global _LISTENERS
      _LISTENERS = [c for c in _LISTENERS if c is not callback]
  ```
  (`set_language` already iterates a snapshot, so removal during fire is safe.)
- Fix the broken `Tooltip.destroy()` (L67–72): `self._widget.unbind("<Enter>", self._widget.bind("<Enter>") and None)` is nonsense. Store the binding IDs returned by `bind(..., add="+")` in `__init__` and `unbind` them by ID. Also unregister the language listener here (see below).
- Add `Tooltip.refresh(text=None)` and `Tooltip.set_text(text)` (alias/refresh of `_text` + re-show), and:
  ```python
  def attach_key(widget, i18n_key: str) -> Tooltip:
      tip = Tooltip(widget, i18n.t(i18n_key))
      tip._i18n_key = i18n_key
      def _on_lang(_c):
          if widget.winfo_exists():
              tip.set_text(i18n.t(i18n_key))
      i18n.on_language_change(_on_lang)
      tip._on_lang = _on_lang            # keep a ref so we can unregister
      return tip
  ```
  In `Tooltip.destroy()`, call `i18n.unregister_listener(self._on_lang)` after unbinding the events. This replaces the pure `winfo_exists()`-guard approach (D7) and removes the closure from `i18n._LISTENERS` on teardown — no leak, no rapid-tab-switch race.
- Attach only to Module-1-touched widgets, using the `tip_*` keys from T2d: the three gated nav buttons, Settings `backup_btn` / `audit_btn` / `save_btn` / `admin_frame`, and the POS balance-card controls (`_payment_menu`, `_tendered_entry`, `_tax_exempt_check`, process-payment button).
- Convention to document for Modules 2–6: every attachable widget gets a `tip_<area>_<widget>` key in all 6 locales.

### T8 — Region-aware fields (`localization_manager.py` + new `ui_region_fields.py` + patient dialog) — Global Standard #4
- **Normalize `get_field_visibility()` (L365–387).** The three dicts do not share a key set today: `US` has `insurance_pcn` but no `scheme_pcn`; `GB` has `scheme_pcn` but no `insurance_pcn`; `DE` has neither `scheme_pcn` nor a US/GB-consistent shape. Any `vis["scheme_pcn"]` lookup `KeyError`s. Define one canonical tuple — `dea_number`, `npi`, `nhs_number`, `gphc_number`, `exemption_category`, `pzn_code`, `insurance_bin`, `insurance_pcn`, `scheme_pcn`, `group_number` — and return all 10 booleans for every region.
- Add `LocalizationManager.field_label(key) -> str` returning `i18n.t(f"field_{key}")`, and `visible_fields() -> tuple[str, ...]`.
- New `archive/ui_region_fields.py`:
  ```python
  class RegionFieldSet(ctk.CTkFrame):
      """Renders only the identifier fields valid for the active region.
      Registers with LocalizationManager and re-renders on region change."""
      def get_values(self) -> dict[str, str]: ...
      def set_values(self, data: dict[str, str]) -> None: ...
  ```
  Register via `lm.get_manager().register_listener(self._on_region)` and **unregister on `<Destroy>`** (`register_listener` fires the callback immediately, and `_listeners` is never pruned otherwise).
- **Wire one real consumer:** the patient add/edit dialog, `ui_patients_tab._open_patient_dialog` (L121–278). Insert the `RegionFieldSet` **wrapped in a `ctk.CTkScrollableFrame`** (D9 — prevents vertical clipping without making the `520x520` dialog resizable) between the Email row (row 5) and the "Custom Fields" header (row 6). Keep `geometry("520x520")` + `resizable(False, False)` (L124–125) unchanged. Persist through the existing `patient_fields` mechanism: merge `RegionFieldSet.get_values()` into `custom_fields` in `on_save` (L248–260) keyed by the **canonical field key**, not the localized label, so data survives a region or language switch. Load via `patient[5]` in the same pass that seeds `add_field_row`.
- `RegionFieldSet.__init__` registers with `lm.get_manager().register_listener(self._on_region)` and unregisters in `destroy()` via `lm.unregister_listener(self._on_region)` (mirrors the new `i18n.unregister_listener` pattern; `LocalizationManager._listeners` is never pruned otherwise). Add `unregister_listener` to `localization_manager.py` if missing (guard with `try`).
- Attach `tip_region_fields` explaining why the visible fields changed.

### T9 — Tests
- Extend `archive/test_rbac.py` with a **dual-backend parity** parametrization (review note #1 — the "Dual Database Sync Trap"). `@_db_fallback` prefers `db.py`, so a permission added to only one file silently no-ops on SQLAlchemy installs. Run the RBAC assertions under **both** backends by controlling `_HAS_DB`/`_db` via `monkeypatch` + importing/forcing `db` (or skipping the SQLAlchemy variant when `db.HAS_SQLALCHEMY` is False):
  - catalog is **17** keys; `backup.manage` and `settings.view` exist in the seeded catalog returned by `database.get_permissions()`;
  - `cashier` has `settings.view` but **not** `settings.manage` / `backup.manage` / `audit.view`;
  - `backup.manage ∈ authz.SENSITIVE_FEATURES`;
  - re-running `init_db()` on a pre-existing DB (temp copy) seeds the two new permissions (idempotent `INSERT OR IGNORE`).
  Assert the **same** expectations for both modes so T4's dual edit cannot drift.
- New `archive/test_module1_foundation.py`:
  - **Locale parity (concrete, automates T2c/T2d)** — load all 6 JSON files, compute `set(data.keys())` each, and `assert set(en.keys()) == set(lang.keys())` for every language; also assert `len({len(v.keys()) for v in files}) == 1`. Regresses any future key drift.
  - No value used with an appended `":"` in Python source ends with `:` (regression guard for `Change::` / `Patient::`): specifically `change` and `patient_label` have no trailing `:` in any locale.
  - `change_due` and `select_a_patient` differ from the English string in `de/es/fr/pt/ar`.
  - **Static crash guards:** no `ctk.CTk<Widget>(` call in `archive/*.py` opens with a keyword argument (catches T1b); every `apply_treeview_style(self.X)` line number is greater than the `self.X = ttk.Treeview` line number in the same file (catches T1a).
  - **i18n listener leak guard (review note #2):** `i18n.unregister_listener` exists; after `on_language_change(cb)` then `unregister_listener(cb)`, a language switch must not invoke `cb` (assert `cb` call count stays 0). This locks in D7.
  - `get_field_visibility()` returns an identical key set for `US`, `GB`, `DE`, with `dea_number`/`npi` true only for US, `nhs_number`/`gphc_number` only for GB, `pzn_code` only for DE.
  - `ui_settings_tab` source no longer contains `role_segmented` / `user_role`; `_open_audit_log_viewer` and `backup_database_gui` source contains a `require_pin_for` call; `admin_frame` (or `settings.manage` gate) is present so cashiers cannot see admin controls.
  - `NAV_PERMISSIONS` keys all exist in `_NAV_ICONS`, and all values exist in the seeded permission catalog.
- Run with the existing isolation fixture (`test_db_fixture.py` / `PHARMACY_DB_PATH`) so `archive/pharmacy.db` is never touched.

### T10 — Validation
1. `python -m pytest archive/test_rbac.py archive/test_module1_foundation.py -v` — all pass.
2. `python -m pytest archive/ -v` — no new failures vs. the recorded baseline (189/190; `test_native_accel.py::TestFuzzyMatchOne::test_best_match_found` is a known pre-existing failure).
3. **Launch `python archive/main_app.py`** — reaches the login gate, then the dashboard. This is the acceptance test for T1a/T1b and was never performed in the previous pass.
4. Open **Patients** → tree renders, scrollbar sits beside it → **Add Patient** → region-specific fields match the active region; save and reopen round-trips the values.
5. Open **POS Retail** → balance card renders → tender cash → label reads `Change Due: $0.00` (not `Change::`); select a patient → `Patient: <name>` (not `Patient::`); clear the cart → placeholder reads the localized "Select a patient" (no em dash).
6. Switch language to `de` → nav region indicator, banner, change-due, and patient placeholder are all German (validates T2b/T2c).
7. Switch region US → GB → DE in Enterprise Settings → the patient dialog's field set re-renders live (DEA/NPI → NHS/GPhC → PZN) and currency/tax terminology follows.
8. **RBAC:** sign in as `cashier` → `Enterprise Settings` and `Status Dashboard` nav buttons are hidden (T6); `Settings` is reachable but the `admin_frame` (Backup/Audit/Save-all/Email/DB-path) is **not shown** (T5/D8) and the only Save button is the lightweight language/theme one — verifying the "Settings Trap" is closed; the `Signed in as` label shows the real role. Sign in as `owner` → everything is reachable and `backup.created` appears in `audit_logs`.
9. Hover every widget touched in T7 → tooltip appears within ~420 ms and follows the language switch (validates D7: tooltip still updates, but `i18n._LISTENERS` no longer grows after closing dialogs — checked by the T9 leak assertion).
10. Rapidly open/close the patient dialog and switch language a few times → no `TclError` and the T9 listener-leak assertion passes (region + i18n listeners are unregistered on destroy).

---

## 4. Risks

1. **`database.py` / `db.py` drift.** `@_db_fallback` prefers `db.py`. Adding permissions to only one file silently no-ops on SQLAlchemy installs. Mitigation: T4 edits both; T9 asserts the seeded catalog through `database.get_permissions()` under **both** backends (review note #1), so a one-sided edit is caught.
2. **Locking a role out.** Granting `settings.view` to every role keeps the language selector reachable. If nav gating is misconfigured, an Owner could hide their own Enterprise Settings — recovery is `Ctrl+Shift+A` (`main_app.py:280`), which is bound independently of the drawer. Do not gate that shortcut.
3. **Listener leaks (review note #2).** Resolved structurally by D7: add `i18n.unregister_listener` and unregister in `Tooltip.destroy()` and `RegionFieldSet.destroy()`; add `localization_manager.unregister_listener` and unregister in `RegionFieldSet.destroy()`. T9 asserts a removed listener is no longer fired (proves no leak/race).
4. **Removing the legacy role toggle.** `_update_role_controls` currently disables `btn_sell` / `btn_print` / `btn_edit_batch`. After removal those buttons default to enabled — confirm they carry their own `require_permission` gates (`ui_inventory_tab.py:411–412` already does for edit/delete) or add them.
5. **Cashier Settings UX (review note: "Settings Trap").** Resolved by D8: administrative controls are grouped in `admin_frame` (T5) and hidden from `settings.view`-only users, plus a lightweight basic-Save for language/theme. Nav hiding (T6) and handler gates (T5) remain as defense in depth for programmatic `tab_view.set()` callers.
6. **Patient dialog vertical clipping (review note).** Resolved by D9: `RegionFieldSet` lives inside a `ctk.CTkScrollableFrame`; the `520x520` dialog stays non-resizable, so users cannot horizontally stretch it into an ugly layout.
7. **Non-Latin locales.** `ar.json` is RTL and already at key parity with `en`. New `tip_*` and `field_*` keys must be added there too or `i18n.t` falls back to English mid-sentence. The T9 locale-parity assertion will fail the build if any of the 6 files drifts.

---

## 5. Out of scope for Module 1

- Palette/spacing consolidation between `design_system.py` (`COLOR_BG`, `COLOR_PANEL`, …) and `ui_navigation.py` (`COLOR_SIDEBAR_BG`, `COLOR_CARD_BG`, …), and the absence of any `FONT_*` / `SPACING_*` constants → **Module 2**.
- Attaching tooltips to every remaining tab and button → **Modules 2–6** (Module 1 ships the helper, the `tip_*` convention, and the first attachments).
- Wiring `RegionFieldSet` into the Rx Processing prescriber panel and Enterprise Settings pharmacy identifiers → **Modules 5/6**.
- Drawer restructuring, section grouping, and nav ordering → **Module 4** (Module 1 only adds `set_button_visible` + `NAV_PERMISSIONS`).
- Any change to `_NAV_ICONS` (explicitly excluded by the brief).
- Regions beyond `US` / `GB` / `DE`.
