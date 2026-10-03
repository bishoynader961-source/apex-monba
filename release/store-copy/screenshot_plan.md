# Screenshot Plan — 8 Freemius store screenshots

Capture on Windows 10/11, light theme, 100% scaling (or 125% if text is small), PNG **≥1280×800**, using the demo dataset (`backend_fastapi/.venv/Scripts/python release/demo/load_demo.py`, login `demo`). Close dev tools; hide the OS taskbar if possible. Each shot = one screen, no popups over content.

| # | Screen | Demo data to show | Exact UI state to capture | Why it matters to a buyer |
|---|---|---|---|---|
| 1 | POS Sale Screen | Demo products, patient "Amir Hassan (demo)" | 3 items in the sale list with quantities + prices, running total visible, barcode field focused, "Cash" payment selected | The screen their cashiers live in all day — speed and clarity sell first |
| 2 | Inventory / Product List | All 20 demo products | Table with name, price, stock status, expiry columns; one row selected; search box with a partial name typed | Shows stock visibility at a glance — the core of pharmacy management |
| 3 | Expiry Alerts Dashboard | Demo products with expiry offsets 210–300 days | Dashboard/expiry view listing soon-expiring batches sorted by date, alert badges visible | Expired stock is money thrown away — this is the emotional "save me money" shot |
| 4 | Receipt / Invoice Print View | Receipt DEMO-TX0004 (2 items, Card) | Printed receipt preview with pharmacy name "Demo Pharmacy (Apex Software)", items, totals, payment method | Professional invoices = trust with their own customers |
| 5 | Users & Roles | demo owner + roles list (Administrator etc.) | Roles page with permission toggles for one role expanded | Owners fear cashiers messing with prices/data — show control |
| 6 | Reports / End-of-Day | 10 demo receipts over the last 13 days | EOD/report summary: sales count, total 2445.90, breakdown by payment method | "I can close the day in one screen" — daily-use reassurance |
| 7 | Backup & Restore | Any state | Settings → Backup: encrypted backup UI with recovery-key field visible (mask the key value) | Data-loss fear is the #1 objection — show the answer exists |
| 8 | Arabic RTL (POS or Inventory) | Same as #1 or #2 | Same screen with UI language = العربية (Settings → Language), layout fully right-to-left | Proves genuine Arabic/RTL support to the target market (also satisfies HUMAN_TODO §L4) |

**HUMAN_TODO:** capturing these is an owner step (§L4 in HUMAN_TODO.md) — PNG ≥1280×800, saved to `release/store-copy/screenshots/1-pos.png` … `8-arabic-rtl.png`.
