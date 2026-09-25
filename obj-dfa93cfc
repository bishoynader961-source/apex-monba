# SPEC 03 — Label Engine: Full Redesign & Button Fixes

**Architecture reference:** `app/dashboard/label-engine/page.tsx`, `app/dashboard/label-engine-preview/page.tsx`, `components/LabelCanvas.tsx`, `components/LabelPropertiesPanel.tsx`, `src-tauri/src/lib.rs` (Tauri IPC: `print_label`, `open_label_window`)

**Current state from screenshot:** Dark-themed canvas area with colorful toolbar buttons across the top (+Text, +Shape, +Barcode, +QR, Delete, Export PNG, Print, Save Tpl, Product ID, Save, Load, Open Standalone). Left panel shows "Templates" (empty). Right panel shows "Properties / No element selected." The canvas shows a blank white rectangle. The UI is functional but unpolished, visually noisy, and several buttons don't work.

---

## Part A — Visual Redesign

### A.1 — Overall Layout Restructure

Replace the current single horizontal toolbar with a professional three-panel layout:

```
┌─────────────────────────────────────────────────────────────────┐
│  HEADER BAR: Canvas size controls │ Template name │ Action buttons│
├──────────────┬──────────────────────────────┬───────────────────┤
│              │                              │                   │
│  LEFT PANEL  │       CANVAS AREA            │  RIGHT PANEL      │
│  (Elements   │   (white label, grid dots,   │  (Properties      │
│   & Templates│    zoom controls at bottom)  │   panel, context- │
│   library)   │                              │   sensitive)      │
│              │                              │                   │
└──────────────┴──────────────────────────────┴───────────────────┘
│  BOTTOM BAR: Zoom %, canvas dimensions, element count, status   │
└─────────────────────────────────────────────────────────────────┘
```

### A.2 — Left Panel: Element Palette + Templates

Replace the current "Templates" label with a proper left sidebar containing two tabs:

**Tab 1: Elements**
Vertical icon+label buttons for adding elements:
- 📝 Text
- ▭ Shape (rectangle/line)
- ▦ Barcode
- ⊞ QR Code
- 🖼 Image (new — allow embedding a small logo or image on the label)

Each button is a clean card with an icon and label, not a brightly colored pill. Style: white/light background, dark text, subtle hover shadow.

**Tab 2: Templates**
List of saved templates with thumbnail previews (render a small canvas preview of each template). Click a template to load it. "Save as Template" button at the bottom of this panel.

### A.3 — Top Header Bar

Replace the chaotic mixed-color pill buttons with a clean header:

**Left group (canvas controls):**
- W: [400] H: [300] (dimension inputs, same as now but styled cleanly)
- Zoom: [100%] dropdown or +/- buttons

**Center (template name):**
- Single text input: "Template name..." — clearly labeled

**Right group (actions, grouped by function):**
- [Save Template] [Load Template] — grouped together
- [Product ID: ___] [Save] [Load] — grouped together for product label operations
- Separator
- [Export PNG] [Print] [Open Preview] — grouped together for output
- Separator
- [🗑 Delete Selected] — destructive action, separated, shown only when element is selected

Remove the random colors from the element buttons. Use a consistent button style:
- Primary (blue): Save Template, Print
- Secondary (outline): Export PNG, Load Template
- Danger (red): Delete — only when element is selected

### A.4 — Canvas Area

- Light subtle dot-grid background so users can see the canvas boundary clearly
- Canvas (white label area) has a subtle drop shadow so it reads as a "paper" being designed
- Selected elements show resize handles (small squares at corners and edges)
- Hover shows a subtle blue outline to indicate the element is clickable
- Canvas zoom: scroll wheel to zoom, pinch on touch; zoom indicator bottom-left
- Click outside any element to deselect

### A.5 — Right Panel: Context-Sensitive Properties

When nothing selected: show a short help message ("Click an element to edit its properties") plus canvas properties (width, height, background color).

When Text selected:
- Content: multiline text input
- Font: dropdown (system fonts + monospace for barcodes)
- Size: number input
- Bold / Italic / Underline toggles
- Color picker
- Alignment (left/center/right)
- Position (X, Y) and Size (W, H) number inputs

When Shape selected:
- Fill color picker
- Border color + width
- Border radius (for rounded rectangles)
- Position and Size

When Barcode selected:
- Mode toggle: Manual | Auto-generate
- If Manual: Data text input
- If Auto-generate: Prefix, Separator, Number Type (Sequential/Random), Scope, Preview, Generate button
- Format dropdown: CODE128 (default), CODE39, EAN13, UPC
- Show text below barcode: checkbox
- Position and Size

When QR selected:
- Data input
- Error correction level (L/M/Q/H)
- Position and Size

### A.6 — Bottom Status Bar

Thin bar at bottom:
- Left: "W: 400 H: 300 px" (canvas dimensions)
- Center: "3 elements" (element count)
- Right: "Zoom: 100%" | zoom in/out buttons

---

## Part B — Button Fixes

Each button must be traced from click → handler → output. Fix any that are broken.

### B.1 — +Text, +Shape, +Barcode, +QR (element creation)
These call `addElement()` in local state. Should work already — confirm each actually adds a visible element to the canvas.

### B.2 — Delete
Currently disabled when nothing is selected. Must:
- Be visually hidden (not just disabled) when nothing is selected
- Remove the selected element from canvas state when clicked
- If multiple selected (implement multi-select with Shift+click): remove all selected

### B.3 — Export PNG
Calls `canvas.toDataURL()`. Must:
- Render the canvas to a PNG blob
- Trigger a file download via Tauri `dialog.save()` (let user choose filename/location)
- If nothing on canvas: show a toast "Add elements before exporting"
- Currently may fail silently — add error handling with a visible error toast

### B.4 — Print
Calls `invoke("print_label", { image_data, canvas_width, canvas_height })` via Tauri IPC.
In `src-tauri/src/lib.rs`, the `print_label` command:
1. Writes image data (base64 PNG) to a temp file
2. Calls `ShellExecuteW` with `print` verb on that file
Add error handling: if `ShellExecuteW` fails, return the error code to the frontend and show a toast.

### B.5 — Save Tpl (Save Template)
Calls `POST /api/v1/label-templates` with `{ name, canvas_json }`.
Must:
- Require a non-empty template name — if input is empty, show inline validation error, don't submit
- Show a success toast with the template name on save
- Refresh the Templates panel after save so the new template appears immediately

### B.6 — Load Template
Opens a modal or uses the Templates panel. The selected template's `canvas_json` is parsed and loaded into the canvas state. Must show a confirmation if the canvas has unsaved changes.

### B.7 — Save/Load Product Label (Product ID + Save/Load buttons)
These associate a label template with a specific product in inventory.
- Product ID input: must accept a product barcode scan or manual entry
- Save: calls `PUT /api/v1/product-labels/{product_id}` with current canvas JSON
- Load: calls `GET /api/v1/product-labels/{product_id}` and loads the canvas

### B.8 — Open Standalone (now: Open Preview)
Rename this button to "Preview & Print" for clarity.
Opens the preview window (`app/dashboard/label-engine-preview/page.tsx`) via `invoke("open_label_window")`.
The preview window must:
1. Receive the current canvas state via Tauri event `label-preview-state`
2. Show a loading spinner until the event arrives (prevent blank canvas flash)
3. Render the label as it will look when printed
4. Show two options: "Print Single" and "Apply to Inventory Items"
5. If "Apply to Inventory Items": show a searchable dropdown of products, quantity field, "Save & Print" button

---

## Part C — New Features

### C.1 — Multi-select
Hold Shift and click multiple elements to select them. Selected elements all show handles. Group move by dragging any selected element.

### C.2 — Undo/Redo
Ctrl+Z / Ctrl+Y. Keep a history of up to 50 states. Show undo/redo buttons in the header bar.

### C.3 — Keyboard shortcuts
- Delete key: remove selected element
- Ctrl+D: duplicate selected element
- Arrow keys: nudge selected element 1px (Shift+Arrow: 10px)
- Ctrl+A: select all elements

### C.4 — Snap to grid
Optional toggle (default off). When on, elements snap to a configurable grid (default 5px) while dragging.

---

## Part D — Barcode Pattern Generation (already in codebase, verify and refine)

**Backend:** `GET /api/v1/barcodes/next-sequence?prefix=PHARMA-` and `POST /api/v1/barcodes/validate` exist.

**Verify these work:**
```bash
curl "http://127.0.0.1:8000/api/v1/barcodes/next-sequence?prefix=PHARMA-" \
  -H "Authorization: Bearer ADMIN_TOKEN"
# Expected: {"next": 1} (or next available number)
```

If they don't exist or return errors, implement them:
- `next-sequence`: count existing barcodes with that prefix, return count+1
- `validate`: check if a barcode value already exists in the Product table

---

## Build

After all parts are done, run `npm run build` to confirm no TypeScript errors, then:
```
cd "E:\my progam pharmacy"
npm run tauri build
```

Manual verification in the packaged app:
- Click each element type button — confirm element appears on canvas
- Click each element — confirm Properties panel shows correct fields
- Export PNG — confirm file downloads
- Print — confirm print dialog appears
- Save Template with a name — confirm it appears in Templates panel
- Open Preview — confirm preview window opens with the current canvas
