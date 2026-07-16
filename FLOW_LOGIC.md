# FLOW_LOGIC.md

## 1. Coordinate System
* **Origin (0,0):** Top-left corner of the printable label surface.
* **Safe Zone:** There is a hard-coded 15px left-margin requirement for all text elements to prevent edge-clipping.

## 2. Rendering Pipeline
Data travels: `Element Data` -> `canvas_core.py (Transformation)` -> `[Tkinter / PIL Output]`.
* **Margin Enforcement:** At the top of the `draw_elements` loop (line 219), `x0` is shifted by `TEXT_LEFT_MARGIN * scale` for ALL element types (text, shape, barcode, QR). No element can render closer than 15px to the left edge.
* **Coordinate Formula:** `x0 = elem.x * scale + TEXT_LEFT_MARGIN * scale`
* **Consistency:** Both Tkinter preview (`scale=1`) and PIL export (`scale=DPI/SCREEN_DPI`) share the same code path.

## 3. Key Constants
* `TEXT_LEFT_MARGIN = 15` (Do not change without updating this file).
* `RIGHT_PADDING = 20` (Do not change without updating this file).
* `MIN_FONT_SIZE = 8`

## 4. Constraint Rules
* **No Clipping:** No text element shall render at `x < 15`.
* **Consistency:** Tkinter preview and PIL export must use identical coordinate math.
## 5. Font Scaling Rule (NEW)
* **Goal:** Text must never clip on the right side.
* **Logic:** 1. Calculate `text_width` using current `font_size`.
    2. Define `max_available_width` = `label_width` - `TEXT_LEFT_MARGIN` - `RIGHT_PADDING`.
    3. If `text_width` > `max_available_width`:
        - Iteratively reduce `font_size` (min 8pt).
        - Re-calculate `text_width` until it fits OR minimum size is reached.
    4. **Consistency:** This scaling must occur *before* the final draw command for both Tkinter and PIL.

## 6. Debug Protocol — Diagnostic Rendering Logs
* **Purpose:** Verify coordinate math at runtime when clipping is reported.
* **Mechanism:** Temporarily add `print()` statements in `draw_elements()` before draw calls.
* **Output Format:** `[DRAW] text="<text>" original_x=<x> x0=<scaled_x> canvas_w=<width> scale=<factor>`
* **Usage:** Run the Label Engine app, reproduce the clipping, read the console output.
* **Status:** Removed (resolved). Re-add if new clipping issues arise.

## 7. Template System
* **Storage:** `label_template.json` in project root. Same format as label JSON: `{canvas_width, canvas_height, elements: [...]}`.
* **Write Path (Standalone Engine):** User designs label → clicks "Save Template" → `export.save_template(canvas)` → serializes canvas to `label_template.json`.
* **Read Path (Standalone Engine):** On startup without `--id`, `load_template(canvas)` auto-loads if file exists. Manual "Load Template" button also available.
* **Read Path (Popup):** `LabelDesignerPopup._build_controls()` reads `label_template.json` → parses text elements → creates a `CTkScrollableFrame` with one `CTkEntry` per text element → maps entry values to `var_context` via `{{VARIABLE}}` substitution.
* **Preview Rendering:** Popup uses `draw_elements(preview_canvas, elements, context=overrides)` directly on tk.Canvas — same code path as the standalone engine, ensuring pixel-perfect consistency.
* **Print/Export:** Popup uses `export_to_png(temp_path, label_canvas)` which renders to PIL Image at 300 DPI, then `os.startfile()` for Windows print.