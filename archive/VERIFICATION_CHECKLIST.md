# VERIFICATION_CHECKLIST

## Quality Gates for UI/UX
- [x] No overlapping text or squished columns in Treeviews.
- [x] CustomTkinter elements use designated Theme Colors (`#1a1a2e` / `#2d2d3a` card backgrounds).
- [x] Responsive resize: Grids (`grid_rowconfigure`, `grid_columnconfigure`) must be used for fluid layout.
- [x] Scrollable views adapt correctly to long lists (e.g. patients, products).

## Quality Gates for Code
- [x] No `// TODO` or `pass` placeholders left behind (except `except: pass` error suppression, matching existing rx modules).
- [x] Logs do not block the main thread (`AsyncUI` thread pool, `.after()` marshaling).
- [x] The `Simplicity First` principle is applied (no speculative programming).
- [x] Ensure backward compatibility with existing databases (sqlite3 fallback for all rx_db calls).

## Security & Reliability
- [x] Developer mode is authenticated only via secure `.pharmacy_dev.key` or Env Var.
- [x] `DEV-PASS` plain-text backdoor is completely removed.
- [x] External API network errors are gracefully handled or fail-fast logged (EPCS auth errors shown via messagebox + logged).

## EPCS Workflow Module — M89
- [x] Import smoke test: `ui_epcs_workflow` imports cleanly.
- [x] Strategy routing: US → USBillingStrategy, GB/DE → EUBillingStrategy, unknown → MockProvider.
- [x] Veterinarian prescriber handling: NPI → DEA → State License fallback.
- [x] Backend immutability: `rx_config.py`, `rx_database.py`, `rx_strategies.py`, `rx_db.py` not modified.
- [x] Zero regression: 99 tests pass (74 existing + 25 new).
- [x] main_app integration: nav icon, tab creation, on_tab_change hook all wired.
