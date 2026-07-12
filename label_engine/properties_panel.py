import logging
import customtkinter as ctk

logger = logging.getLogger(__name__)

FONT_FAMILIES = ["Arial", "Helvetica", "Times New Roman", "Courier", "Verdana", "Georgia"]
SHAPE_TYPES = ["rectangle", "ellipse", "rounded-rectangle"]


class PropertiesPanel:
    def __init__(self, parent, label_canvas):
        self.label_canvas = label_canvas
        self.current_id: str | None = None
        self._updating = False

        self.frame = ctk.CTkFrame(parent, width=220)
        self.frame.grid_propagate(False)

        self.title = ctk.CTkLabel(
            self.frame, text="Properties", font=ctk.CTkFont(size=16, weight="bold")
        )
        self.title.pack(padx=10, pady=(10, 5), anchor="w")

        self.no_selection = ctk.CTkLabel(
            self.frame, text="No element selected", text_color="gray"
        )
        self.no_selection.pack(padx=10, pady=20)

        self.text_fields = ctk.CTkFrame(self.frame, fg_color="transparent")
        self._build_text_fields()

        self.shape_fields = ctk.CTkFrame(self.frame, fg_color="transparent")
        self._build_shape_fields()

        self.barcode_fields = ctk.CTkFrame(self.frame, fg_color="transparent")
        self._build_barcode_fields()

        self.qr_fields = ctk.CTkFrame(self.frame, fg_color="transparent")
        self._build_qr_fields()

        self._hide_all()

        self.label_canvas.on_select = self._on_selection_changed
        logger.info("PropertiesPanel created")

    def _make_labeled_entry(self, parent, label_text: str, attr_name: str, on_change=None):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=3)
        ctk.CTkLabel(row, text=label_text, width=50, anchor="w").pack(side="left")
        entry = ctk.CTkEntry(row, width=125)
        entry.pack(side="left", fill="x", expand=True)
        if on_change:
            entry.bind("<KeyRelease>", on_change)
        setattr(self, attr_name, entry)
        return entry

    def _make_combobox(self, parent, label_text: str, attr_name: str, values: list[str], on_change=None):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=3)
        ctk.CTkLabel(row, text=label_text, width=50, anchor="w").pack(side="left")
        var = ctk.StringVar(value=values[0] if values else "")
        combo = ctk.CTkComboBox(row, values=values, variable=var, width=125)
        combo.pack(side="left", fill="x", expand=True)
        if on_change:
            combo.bind("<<ComboboxSelected>>", on_change)
        setattr(self, attr_name, combo)
        return combo

    def _make_checkbox(self, parent, label_text: str, attr_name: str, on_change=None):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=3)
        var = ctk.BooleanVar(value=True)
        cb = ctk.CTkCheckBox(row, text=label_text, variable=var)
        cb.pack(side="left")
        if on_change:
            var.trace_add("write", lambda *_: on_change())
        setattr(self, attr_name, var)
        return var

    def _build_text_fields(self):
        self._field_text = self._make_labeled_entry(self.text_fields, "Text:", "entry_text", self._on_text_change)
        self._field_font = self._make_combobox(self.text_fields, "Font:", "combo_font", FONT_FAMILIES, self._on_text_change)
        self._field_size = self._make_labeled_entry(self.text_fields, "Size:", "entry_size", self._on_text_change)
        self._field_color = self._make_labeled_entry(self.text_fields, "Color:", "entry_color", self._on_text_change)

    def _build_shape_fields(self):
        self._field_shape_type = self._make_combobox(self.shape_fields, "Type:", "combo_shape_type", SHAPE_TYPES, self._on_shape_change)
        self._field_fill_color = self._make_labeled_entry(self.shape_fields, "Fill:", "entry_fill_color", self._on_shape_change)
        self._field_border_color = self._make_labeled_entry(self.shape_fields, "Border:", "entry_border_color", self._on_shape_change)
        self._field_border_width = self._make_labeled_entry(self.shape_fields, "Width:", "entry_border_width", self._on_shape_change)

    def _build_barcode_fields(self):
        self._field_bc_data = self._make_labeled_entry(self.barcode_fields, "Data:", "entry_bc_data", self._on_barcode_change)
        self._field_bc_text = self._make_checkbox(self.barcode_fields, "Show Text", "bc_show_text", self._on_barcode_change)

    def _build_qr_fields(self):
        self._field_qr_data = self._make_labeled_entry(self.qr_fields, "Data:", "entry_qr_data", self._on_qr_change)
        self._field_qr_fill = self._make_labeled_entry(self.qr_fields, "Fill:", "entry_qr_fill", self._on_qr_change)
        self._field_qr_back = self._make_labeled_entry(self.qr_fields, "Back:", "entry_qr_back", self._on_qr_change)

    def _hide_all(self):
        self.no_selection.pack_forget()
        self.text_fields.pack_forget()
        self.shape_fields.pack_forget()
        self.barcode_fields.pack_forget()
        self.qr_fields.pack_forget()

    def _show_no_selection(self):
        self._hide_all()
        self.no_selection.pack(padx=10, pady=20)

    def _on_selection_changed(self, element):
        self._updating = True
        self._hide_all()
        if not element:
            self.current_id = None
            self._show_no_selection()
            self._updating = False
            return

        self.current_id = element.id
        if element.type == "text":
            self._field_text.delete(0, "end")
            self._field_text.insert(0, element.props.get("text", ""))
            self._field_font.set(element.props.get("font", "Arial"))
            self._field_size.delete(0, "end")
            self._field_size.insert(0, str(element.props.get("font_size", 16)))
            self._field_color.delete(0, "end")
            self._field_color.insert(0, element.props.get("color", "#000000"))
            self.text_fields.pack(fill="x", pady=(5, 10))
        elif element.type == "shape":
            self._field_shape_type.set(element.props.get("shape", "rectangle"))
            self._field_fill_color.delete(0, "end")
            self._field_fill_color.insert(0, element.props.get("fill_color", "#cccccc"))
            self._field_border_color.delete(0, "end")
            self._field_border_color.insert(0, element.props.get("border_color", "#000000"))
            self._field_border_width.delete(0, "end")
            self._field_border_width.insert(0, str(element.props.get("border_width", 2)))
            self.shape_fields.pack(fill="x", pady=(5, 10))
        elif element.type == "barcode":
            self._field_bc_data.delete(0, "end")
            self._field_bc_data.insert(0, element.props.get("data", ""))
            self._field_bc_text.set(element.props.get("show_text", True))
            self.barcode_fields.pack(fill="x", pady=(5, 10))
        elif element.type == "qr":
            self._field_qr_data.delete(0, "end")
            self._field_qr_data.insert(0, element.props.get("data", ""))
            self._field_qr_fill.delete(0, "end")
            self._field_qr_fill.insert(0, element.props.get("fill_color", "#000000"))
            self._field_qr_back.delete(0, "end")
            self._field_qr_back.insert(0, element.props.get("back_color", "#ffffff"))
            self.qr_fields.pack(fill="x", pady=(5, 10))
        else:
            self.current_id = None
            self._show_no_selection()
        self._updating = False
        logger.info("Properties loaded for element %s (type=%s)", element.id, element.type)

    def _on_text_change(self, event=None):
        if self._updating or not self.current_id:
            return
        elem = self.label_canvas.get_element(self.current_id)
        if not elem or elem.type != "text":
            return
        elem.props["text"] = self._field_text.get().strip()
        elem.props["font"] = self._field_font.get().strip()
        try:
            elem.props["font_size"] = int(self._field_size.get().strip())
        except ValueError:
            pass
        color_val = self._field_color.get().strip()
        if color_val:
            elem.props["color"] = color_val
        self.label_canvas.redraw()

    def _on_shape_change(self, event=None):
        if self._updating or not self.current_id:
            return
        elem = self.label_canvas.get_element(self.current_id)
        if not elem or elem.type != "shape":
            return
        elem.props["shape"] = self._field_shape_type.get().strip()
        fill_val = self._field_fill_color.get().strip()
        if fill_val:
            elem.props["fill_color"] = fill_val
        border_val = self._field_border_color.get().strip()
        if border_val:
            elem.props["border_color"] = border_val
        try:
            elem.props["border_width"] = int(self._field_border_width.get().strip())
        except ValueError:
            pass
        self.label_canvas.redraw()

    def _on_barcode_change(self, event=None):
        if self._updating or not self.current_id:
            return
        elem = self.label_canvas.get_element(self.current_id)
        if not elem or elem.type != "barcode":
            return
        elem.props["data"] = self._field_bc_data.get().strip()
        elem.props["show_text"] = self._field_bc_text.get()
        self.label_canvas.redraw()

    def _on_qr_change(self, event=None):
        if self._updating or not self.current_id:
            return
        elem = self.label_canvas.get_element(self.current_id)
        if not elem or elem.type != "qr":
            return
        elem.props["data"] = self._field_qr_data.get().strip()
        elem.props["fill_color"] = self._field_qr_fill.get().strip()
        elem.props["back_color"] = self._field_qr_back.get().strip()
        self.label_canvas.redraw()
