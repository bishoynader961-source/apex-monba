# Project Map

> Auto-generated from the codebase at `E:\my progam pharmacy`.
> Last scanned: 2026-07-12

## Directory Structure

```
my progam pharmacy/
├── main.py                 # Application entrypoint (pharmacy app)
├── ui.py                   # All GUI code (customtkinter)
├── database.py             # SQLite CRUD operations
├── barcode_logic.py        # Barcode/label generation + config loading
├── config.json             # Runtime settings (pharmacy name, font, DB path)
├── main.spec               # PyInstaller build spec
├── pharmacy.db             # SQLite database (runtime, auto-created)
├── labels/                 # Generated label PNG images
├── build/                  # PyInstaller build artifacts
├── dist/                   # PyInstaller output (main.exe)
├── label_engine/           # [NEW] Dynamic Label Design Engine
│   ├── main.py             #   App entry + File menu + toolbar + canvas area
│   ├── canvas_core.py      #   Element hierarchy + unified draw_elements() + drag/resize
│   ├── properties_panel.py #   Property editor sidebar (text/shape/barcode/QR)
│   └── export.py           #   JSON save/load + PNG export (300 DPI) + print support
├── venv/                   # Python virtual environment
├── AGENTS.md               # Agent instructions
├── PROJECT_MAP.md          # This file
└── .gitignore
```

## Source Files

### `main.py` — Entrypoint (22 lines)
- Sets customtkinter appearance (Dark mode, blue theme)
- Calls `database.init_db()` to create tables
- Calls `barcode_logic.init_labels_dir()` to ensure `labels/` exists
- Launches `PharmacyApp` main window

### `ui.py` — GUI Layer (641 lines)

**Classes:**

| Class | Purpose |
|---|---|
| `PharmacyApp(ctk.CTk)` | Main window with 5 tabs |
| `LabelDesignerPopup(ctk.CTkToplevel)` | Label preview/print popup |

**Tab breakdown:**

| Tab | Method | Purpose |
|---|---|---|
| Add Product | `setup_add_tab()` | Form: template dropdown, name, price, mfg barcode → saves + opens label designer |
| Inventory | `setup_inventory_tab()` | Treeview of all products, search, sell button |
| Sales Report | `setup_report_tab()` | Treeview of sold items, revenue totals, refund button |
| Templates | `setup_templates_tab()` | CRUD for reusable product templates |
| Settings | `setup_settings_tab()` | Pharmacy name, font size, price toggle, DB path, backup |

**Key methods:**

| Method | Line | Purpose |
|---|---|---|
| `save_product()` | `ui.py:103` | Validates form, generates internal barcode, saves to DB, opens label designer |
| `perform_search()` | `ui.py:206` | Exact barcode match → highlight; otherwise LIKE search |
| `sell_product()` | `ui.py:231` | Moves selected product to `sold_items` via `database.mark_item_as_sold()` |
| `refund_item()` | `ui.py:299` | Moves sold item back to products via `database.reverse_sale()` |
| `save_settings()` | `ui.py:497` | Writes config.json, reinitializes DB connection |
| `print_label()` | `ui.py:626` | Saves label PNG to temp, sends to Windows default printer via `os.startfile` |

### `database.py` — Data Layer (243 lines)

**Tables:**

#### `products`
| Column | Type | Constraints |
|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT |
| `name` | TEXT | NOT NULL |
| `price` | REAL | NOT NULL |
| `manufacturer_barcode` | TEXT | NOT NULL |
| `internal_unique_barcode` | TEXT | NOT NULL UNIQUE |
| `status` | TEXT | DEFAULT 'In Stock' |

#### `templates`
| Column | Type | Constraints |
|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT |
| `name` | TEXT | NOT NULL |
| `price` | REAL | NOT NULL |

#### `sold_items`
| Column | Type | Constraints |
|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT |
| `item_name` | TEXT | NOT NULL |
| `price` | REAL | NOT NULL |
| `manufacturer_barcode` | TEXT | NOT NULL |
| `internal_barcode` | TEXT | NOT NULL |
| `timestamp_of_sale` | TEXT | NOT NULL |

**Functions:**

| Function | Purpose |
|---|---|
| `get_db_path()` | Reads DB path from `config.json` via `barcode_logic.load_config()` |
| `init_db()` | Creates tables if missing, seeds default templates |
| `add_product()` | Inserts into `products` |
| `get_all_products()` | Returns all rows from `products` |
| `search_products(query)` | LIKE search on name, mfg barcode, internal barcode |
| `get_product_by_barcode(barcode)` | Exact match on either barcode column |
| `update_product_status()` | Updates `status` field by barcode |
| `mark_item_as_sold(barcode)` | Moves product → `sold_items` (delete + insert in one transaction) |
| `reverse_sale(sold_item_id)` | Moves sold item → `products` (delete + insert in one transaction) |
| `get_sold_items()` | Returns all `sold_items` ordered by timestamp DESC |
| `get_templates()` | Returns all templates ordered by name ASC |
| `add_template()` | Inserts into `templates` |
| `update_template()` | Updates template by id |
| `delete_template()` | Deletes template by id |
| `backup_database(dest_folder)` | Copies `pharmacy.db` with date suffix |

### `barcode_logic.py` — Barcode & Config (194 lines)

| Function | Purpose |
|---|---|
| `init_labels_dir()` | Creates `labels/` directory if missing |
| `load_config()` | Reads `config.json`, creates with defaults if missing |
| `generate_internal_barcode(mfg_barcode)` | Returns `<mfg>-<timestamp4><random2>` string |
| `create_label(price, internal_barcode)` | Renders full label PNG to `labels/` dir, returns path |
| `generate_preview_image(flags, overrides, internal_barcode)` | Returns PIL Image for live preview in LabelDesignerPopup |

**Constants:**
- `LABELS_DIR = "labels"`
- `CONFIG_FILE = "config.json"`

### `config.json` — Runtime Settings

```json
{
    "pharmacy_name": "My Pharmacy",   // Printed on labels
    "font_size": 20,                  // Label pharmacy name font size
    "include_price": true,            // Whether price appears on label
    "db_path": "pharmacy.db"          // SQLite database path
}
```

## Data Flow

```
User input (ui.py)
  → database.py (SQLite CRUD)
  → barcode_logic.py (label generation)
  → labels/ directory (PNG output)
  → os.startfile() (print on Windows)
```

## Dependencies

| Package | Used By | Purpose |
|---|---|---|
| `customtkinter` | `ui.py`, `main.py`, `label_engine/main.py` | GUI framework |
| `python-barcode` | `barcode_logic.py`, `label_engine/canvas_core.py` | Code128 barcode rendering |
| `Pillow` (PIL) | `barcode_logic.py`, `label_engine/canvas_core.py` | Label image composition + element rendering |
| `qrcode` | `label_engine/canvas_core.py` | QR code image generation |
| `tkinter` | `ui.py`, `label_engine/canvas_core.py` | Canvas, Treeview, messagebox (via stdlib) |

## Build & Run

```bash
# Run from source
python main.py

# Build standalone executable (Windows)
pyinstaller main.spec
# Output → dist/main.exe
```

## Notes (Pharmacy App)

- No API layer — this is a desktop GUI app, not a web service.
- No ORM — raw sqlite3 with manual connect/close per function.
- No test suite.
- No `requirements.txt` — dependencies must be installed manually.
- Font dependency: `arial.ttf` required for label rendering (Windows stdlib).
- Database schema migrations done via `ALTER TABLE` wrapped in try/except.

---

# Dynamic Label Design Engine

> Status: **M6 Complete** — PNG export (300 DPI) + Print support. Unified `draw_elements()` renderer. No regression.
> Last updated: 2026-07-12

## label_engine/ Directory Structure

```
label_engine/
├── main.py              # App entry, window setup, File menu, toolbar
├── canvas_core.py       # Element hierarchy + unified draw_elements() + drag/resize
├── properties_panel.py  # Property editor sidebar (text/shape/barcode/QR fields)
└── export.py            # JSON save/load + PNG export (300 DPI) + print support
```

## label_engine/ Tech Stack

| Component | Choice | Version |
|---|---|---|
| Language | Python | 3.12.7 |
| GUI | customtkinter | 6.0.0 |
| Imaging | Pillow | 12.3.0 |
| Barcode | python-barcode | 0.16.1 |
| QR Code | qrcode | 8.2 |

> Downgraded from Python 3.14 to 3.12.7 for Pillow pre-built wheel compatibility.

## label_engine/ Source Files

### `main.py` — App Entry (192 lines)

**Class: `LabelEngineApp(ctk.CTk)`**

| Method | Purpose |
|---|---|
| `__init__` | Window setup, grid layout, menu bar + toolbar + canvas + properties panel |
| `_build_menu` | File menu with Save (Ctrl+S), Load (Ctrl+O), Export PNG (Ctrl+E), Print (Ctrl+P), Exit |
| `_build_toolbar` | Canvas size inputs, Apply Size, + Text/Shape/Barcode/QR, Delete, Export PNG, Print buttons |
| `_build_canvas_area` | Frame container for LabelCanvas |
| `_build_properties_panel` | Creates PropertiesPanel sidebar wired to canvas |
| `_apply_canvas_size` | Reads W/H entries, calls `label_canvas.set_size()` |
| `_add_text_element` | Adds a sample text element to canvas |
| `_add_shape_element` | Adds a ShapeElement rectangle to canvas with default props |
| `_add_barcode_element` | Adds a Code128 barcode element with sample data |
| `_add_qr_element` | Adds a QR code element with sample URL |
| `_delete_selected` | Removes the currently selected element |
| `_save_file` | Opens Save dialog, calls `export.save_label()` |
| `_load_file` | Opens Load dialog, calls `export.load_label()` |
| `_export_png` | Opens Export PNG dialog, calls `export.export_to_png()` |
| `_print_label` | Calls `export.print_label()` → renders to temp PNG → os.startfile("print") |

**Constants:** `DEFAULT_W = 400`, `DEFAULT_H = 300`

### `canvas_core.py` — Canvas Engine (430 lines)

**Class Hierarchy:**

```
LabelElement (base dataclass)
├── BarcodeElement    — Code128 barcode rendering via python-barcode
├── QRElement         — QR code rendering via qrcode library
└── ShapeElement      — Rectangle, ellipse, rounded-rectangle with configurable fill/border
```

**`LabelElement` dataclass (base):**

| Field | Type | Default |
|---|---|---|
| `id` | str | `uuid.uuid4().hex[:8]` |
| `type` | str | `"text"` |
| `x` | int | `50` |
| `y` | int | `50` |
| `width` | int | `120` |
| `height` | int | `120` |
| `props` | dict | `{}` |

**`BarcodeElement(LabelElement)`:**
- Default width=200, height=80
- `props`: `data` (str), `show_text` (bool)

**`QRElement(LabelElement)`:**
- Default width=120, height=120
- `props`: `data` (str), `fill_color` (hex), `back_color` (hex)

**`ShapeElement(LabelElement)`:**
- Default width=120, height=120
- `props`: `shape` (rectangle|ellipse|rounded-rectangle), `fill_color` (hex), `border_color` (hex), `border_width` (int)

**Unified Renderer:**

`draw_elements(surface, elements, scale=1.0)` — Draws all elements onto either a `tkinter.Canvas` or a `PIL.Image`. Handles text, shapes (rectangle/ellipse/rounded-rectangle), barcodes, and QR codes. The `scale` parameter multiplies all coordinates and sizes for high-DPI export.

**Helper Functions:**

| Function | Purpose |
|---|---|
| `_rounded_rect_coords(x0, y0, x1, y1, r)` | Generates 52-point polygon path for smooth rounded corners |
| `_get_font(elem, scale)` | Resolves TrueType font with fallback chain (family → arial.ttf → default) |
| `_generate_barcode_img(elem)` | Returns PIL Image of Code128 barcode |
| `_generate_qr_img(elem)` | Returns PIL Image of QR code |

**`LabelCanvas` class:**

| Method | Purpose |
|---|---|
| `__init__(parent, width, height)` | Creates tkinter.Canvas, sets `_image_cache`, `on_select` callback |
| `set_size(width, height)` | Resizes canvas and redraws |
| `add_element(element)` | Appends element and redraws |
| `remove_element(element_id)` | Removes element by ID |
| `get_element(element_id)` | Returns element or None |
| `select(element_id)` | Sets selection, redraws, fires `on_select` callback |
| `clear()` | Removes all elements |
| `redraw()` | Clears canvas, calls `draw_elements()`, draws selection + resize handles |

**Dragging:** B1-Motion on selected element → updates x/y → redraw.
**Resizing:** 5 handles (SE, SW, NE, S, E) rendered as 6px squares. `_hit_handle()` detects cursor near a handle; B1-Motion adjusts width/height/min 30px.

**Callbacks:**
- `on_select(element | None)` — Fired when selection changes

### `properties_panel.py` — Property Editor Sidebar (175 lines)

**Class: `PropertiesPanel`**

| Field | Purpose |
|---|---|
| `label_canvas` | Reference to the `LabelCanvas` instance |
| `current_id` | ID of the currently inspected element |
| `_updating` | Lock to prevent recursive updates during programmatic field changes |

**UI Element Groups:**

| Group | Shown For | Fields |
|---|---|---|
| `text_fields` | `type == "text"` | Text entry, Font dropdown, Size entry, Color hex entry |
| `shape_fields` | `type == "shape"` | Shape type dropdown, Fill Color hex, Border Color hex, Border Width int |
| `barcode_fields` | `type == "barcode"` | Data entry, Show Text checkbox |
| `qr_fields` | `type == "qr"` | Data entry, Fill Color hex, Back Color hex |
| `no_selection` | No element selected | "No element selected" label |

**Methods:**

| Method | Purpose |
|---|---|
| `__init__(parent, label_canvas)` | Builds all field groups, registers `on_select` callback |
| `_on_selection_changed(element)` | Dispatches to correct field group by `element.type`, populates fields |
| `_on_text_change(event)` | Writes text fields back to element.props, triggers redraw |
| `_on_shape_change(event)` | Writes shape fields back to element.props, triggers redraw |
| `_on_barcode_change(event)` | Writes barcode fields back to element.props, triggers redraw |
| `_on_qr_change(event)` | Writes QR fields back to element.props, triggers redraw |

**Constants:** `FONT_FAMILIES` — 6 standard font names, `SHAPE_TYPES` — rectangle, ellipse, rounded-rectangle

### `export.py` — Export & I/O (82 lines)

**Functions:**

| Function | Purpose |
|---|---|
| `save_label(filename, canvas)` | Serializes canvas to JSON via `to_dict()`. Returns bool. |
| `load_label(filename, canvas)` | Deserializes JSON, restores canvas via `from_dict()`. Returns bool. |
| `export_to_png(filename, canvas)` | Renders to PIL Image at 300 DPI via `draw_elements()`, saves as PNG. Returns bool. |
| `print_label(canvas)` | Exports to temp PNG, invokes Windows print dialog via `os.startfile(path, "print")`. Returns bool. |

**Serialization format:**
```json
{
  "canvas_width": 500,
  "canvas_height": 400,
  "elements": [
    {"id": "...", "type": "text", "x": 50, "y": 50, "width": 200, "height": 40, "props": {...}},
    {"id": "...", "type": "barcode", "x": 50, "y": 120, "width": 200, "height": 80, "props": {...}},
    {"id": "...", "type": "qr", "x": 300, "y": 50, "width": 120, "height": 120, "props": {...}},
    {"id": "...", "type": "shape", "x": 300, "y": 200, "width": 100, "height": 80, "props": {...}}
  ]
}
```

**Constants:**
- `FILE_EXTENSION = ".json"`, `FILE_TYPES`, `PNG_FILE_TYPES`
- `DPI = 300`, `SCREEN_DPI = 96` (scale factor = 3.125x for print-quality rendering)

## label_engine/ System Flow

```
main.py (LabelEngineApp)
  → File menu (Ctrl+S / Ctrl+O / Ctrl+E / Ctrl+P)
    → export.py
      → save_label / load_label (JSON serialization via to_dict/from_dict)
      → export_to_png (PIL Image @ 300 DPI via draw_elements)
      → print_label (temp PNG → os.startfile("print"))
  → canvas_core.py (LabelCanvas)
    → draw_elements(surface, elements, scale) — unified renderer
      → tkinter.Canvas (on-screen rendering)
      → PIL.Image (PNG export rendering)
    → LabelElement / BarcodeElement / QRElement / ShapeElement
    → _image_cache (PIL PhotoImage lifecycle for on-screen)
    → on_select callback → properties_panel.py
  → properties_panel.py (PropertiesPanel)
    → reads element type → shows correct field group
    → reads element.props → populates fields
    → field edits → writes element.props → canvas.redraw()
```

## ORPHANS & PENDING

_All milestones complete. No pending items._

| Item | Milestone | Status |
|---|---|---|
| Text elements | M1/M2 | Done |
| Shape elements | M4 | Done |
| Barcode elements | M3 | Done |
| QR code elements | M3 | Done |
| Drag & resize | M3 | Done |
| Properties panel | M2-M4 | Done |
| JSON save/load | M5 | Done |
| PNG export (300 DPI) | M6 | Done |
| Print support | M6 | Done |
