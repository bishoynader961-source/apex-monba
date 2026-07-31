import sys
import os
import argparse
import tkinter as tk
from tkinter import ttk, filedialog
import logging
import customtkinter as ctk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from canvas_core import LabelCanvas, LabelElement, BarcodeElement, QRElement, ShapeElement, resolve_variables
from properties_panel import PropertiesPanel
from export import (
    save_label, load_label, export_to_png, print_label,
    save_label_by_id, load_label_by_id,
    save_template, load_template,
    FILE_TYPES, FILE_EXTENSION, PNG_FILE_TYPES,
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_W = 400
DEFAULT_H = 300


def _parse_args():
    parser = argparse.ArgumentParser(description="Dynamic Label Design Engine")
    parser.add_argument("--id", dest="product_id", default=None, help="Product ID for context-aware label editing")
    parser.add_argument("--barcode", dest="barcode_value", default=None, help="Barcode value to pre-fill on new labels")
    parser.add_argument("--name", dest="product_name", default=None, help="Product name to pre-fill on new labels")
    parser.add_argument("--price", dest="product_price", default=None, help="Product price to pre-fill on new labels")
    parser.add_argument("--expiry", dest="product_expiry", default=None, help="Expiry date to pre-fill on new labels")
    parser.add_argument("--manufacture", dest="product_manufacture", default=None, help="Manufacture date to pre-fill on new labels")
    parser.add_argument("--show-name", dest="show_name", default="True", help="Whether to show the name element (True/False)")
    parser.add_argument("--show-price", dest="show_price", default="True", help="Whether to show the price element (True/False)")
    parser.add_argument("--show-expiry", dest="show_expiry", default="True", help="Whether to show the expiry element (True/False)")
    parser.add_argument("--show-barcode-text", dest="show_barcode_text", default="True", help="Whether to show barcode text (True/False)")
    return parser.parse_args()


class LabelEngineApp(ctk.CTk):
    def __init__(self, product_id: str | None = None, barcode_value: str | None = None,
                 product_name: str | None = None, product_price: str | None = None,
                 product_expiry: str | None = None, product_manufacture: str | None = None,
                 show_name: bool = True, show_price: bool = True,
                 show_expiry: bool = True, show_barcode_text: bool = True):
        super().__init__()
        self.product_id = product_id
        self.barcode_value = barcode_value
        self.product_name = product_name
        self.product_price = product_price
        self.product_expiry = product_expiry
        self.product_manufacture = product_manufacture
        self.show_name = show_name
        self.show_price = show_price
        self.show_expiry = show_expiry
        self.show_barcode_text = show_barcode_text

        title = "Label Design Engine"
        if self.product_id:
            title += f" — Product: {self.product_id}"
        self.title(title)
        self.geometry("1200x700")

        self._build_menu()
        self._build_toolbar()
        self._build_main_pane()
        self._load_product_context()

        logger.info("LabelEngineApp launched (product_id=%s)", self.product_id)
        self.after(500, self.verify_layout_geometry)

    def _build_menu(self):
        self.menu_bar = tk.Menu(self)
        self.config(menu=self.menu_bar)

        file_menu = tk.Menu(self.menu_bar, tearoff=0)
        file_menu.add_command(label="Save", accelerator="Ctrl+S", command=self._save_file)
        file_menu.add_command(label="Load", accelerator="Ctrl+O", command=self._load_file)
        file_menu.add_separator()
        file_menu.add_command(label="Export PNG", accelerator="Ctrl+E", command=self._export_png)
        file_menu.add_command(label="Print", accelerator="Ctrl+P", command=self._print_label)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        self.menu_bar.add_cascade(label="File", menu=file_menu)

        self.bind("<Control-s>", lambda e: self._save_file())
        self.bind("<Control-o>", lambda e: self._load_file())
        self.bind("<Control-e>", lambda e: self._export_png())
        self.bind("<Control-p>", lambda e: self._print_label())

    def _build_toolbar(self):
        toolbar = ctk.CTkFrame(self, height=50)
        toolbar.pack(side="top", fill="x", padx=10, pady=(10, 0))

        ctk.CTkLabel(toolbar, text="W:").grid(row=0, column=0, padx=(10, 2), pady=8)
        self.entry_w = ctk.CTkEntry(toolbar, width=60)
        self.entry_w.insert(0, str(DEFAULT_W))
        self.entry_w.grid(row=0, column=1, padx=2, pady=8)

        ctk.CTkLabel(toolbar, text="H:").grid(row=0, column=2, padx=(10, 2), pady=8)
        self.entry_h = ctk.CTkEntry(toolbar, width=60)
        self.entry_h.insert(0, str(DEFAULT_H))
        self.entry_h.grid(row=0, column=3, padx=2, pady=8)

        ctk.CTkButton(
            toolbar, text="Apply Size", width=90, command=self._apply_canvas_size
        ).grid(row=0, column=4, padx=(10, 0), pady=8)

        sep = ctk.CTkLabel(toolbar, text="|", text_color="gray")
        sep.grid(row=0, column=5, padx=8, pady=8)

        ctk.CTkButton(
            toolbar, text="+ Text", width=65, fg_color="#28a745", hover_color="#218838",
            command=self._add_text_element,
        ).grid(row=0, column=6, padx=3, pady=8)

        ctk.CTkButton(
            toolbar, text="+ Shape", width=65, fg_color="#17a2b8", hover_color="#138496",
            command=self._add_shape_element,
        ).grid(row=0, column=7, padx=3, pady=8)

        ctk.CTkButton(
            toolbar, text="+ Barcode", width=75, fg_color="#6f42c1", hover_color="#5a32a3",
            command=self._add_barcode_element,
        ).grid(row=0, column=8, padx=3, pady=8)

        ctk.CTkButton(
            toolbar, text="+ QR", width=60, fg_color="#fd7e14", hover_color="#e8590c",
            command=self._add_qr_element,
        ).grid(row=0, column=9, padx=3, pady=8)

        ctk.CTkButton(
            toolbar, text="Delete", width=65, fg_color="#c42b1c", hover_color="#9e2216",
            command=self._delete_selected,
        ).grid(row=0, column=10, padx=(10, 3), pady=8)

        sep2 = ctk.CTkLabel(toolbar, text="|", text_color="gray")
        sep2.grid(row=0, column=11, padx=4, pady=8)

        ctk.CTkButton(
            toolbar, text="Export PNG", width=80, fg_color="#20c997", hover_color="#12b886",
            command=self._export_png,
        ).grid(row=0, column=12, padx=3, pady=8)

        ctk.CTkButton(
            toolbar, text="Print", width=55, fg_color="#6c757d", hover_color="#5a6268",
            command=self._print_label,
        ).grid(row=0, column=13, padx=(3, 10), pady=8)

        sep3 = ctk.CTkLabel(toolbar, text="|", text_color="gray")
        sep3.grid(row=0, column=14, padx=4, pady=8)

        ctk.CTkButton(
            toolbar, text="Save Template", width=100, fg_color="#e83e8c", hover_color="#d63384",
            command=self._save_template,
        ).grid(row=0, column=15, padx=3, pady=8)

        ctk.CTkButton(
            toolbar, text="Load Template", width=100, fg_color="#e83e8c", hover_color="#d63384",
            command=self._load_template,
        ).grid(row=0, column=16, padx=(3, 10), pady=8)

    def _build_main_pane(self):
        self.main_pane = ttk.PanedWindow(self, orient="horizontal")
        self.main_pane.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        self.canvas_frame = ctk.CTkFrame(self.main_pane, width=800, fg_color="#1e1e1e")
        self.canvas_frame.pack_propagate(False)

        self.label_canvas = LabelCanvas(self.canvas_frame, DEFAULT_W, DEFAULT_H)
        self.label_canvas.frame.pack(expand=True)
        self.main_pane.add(self.canvas_frame, weight=1)

        self.props_panel = PropertiesPanel(self.main_pane, self.label_canvas)
        self.main_pane.add(self.props_panel.frame, weight=0)

    def verify_layout_geometry(self):
        self.update_idletasks()
        win_w = self.winfo_width()
        win_h = self.winfo_height()
        pp_w = self.props_panel.frame.winfo_width()
        cf_w = self.canvas_frame.winfo_width()
        total = cf_w + pp_w
        min_panel = 300

        print("\n===== LAYOUT GEOMETRY AUDIT =====")
        print(f"  Window size:    {win_w}x{win_h}")
        print(f"  Canvas frame:   {cf_w}px")
        print(f"  Properties:     {pp_w}px")
        print(f"  Pane total:     {total}px (window={win_w})")

        failure = False
        if pp_w < min_panel:
            print(f"  LAYOUT FAILURE: Properties panel ({pp_w}px) below minimum ({min_panel}px) — UI IS CRUSHED OR CLIPPED")
            failure = True
        if total > win_w + 10:
            print(f"  LAYOUT FAILURE: Panes ({total}px) exceed window ({win_w}px) — UI IS CLIPPED OFF-SCREEN")
            failure = True
        if cf_w < 200:
            print(f"  LAYOUT FAILURE: Canvas frame ({cf_w}px) too narrow — UI IS CRUSHED")
            failure = True

        if not failure:
            print("  RESULT: OK — all dimensions within tolerance")
        print("=================================\n")

        logger.info("Layout audit: window=%d, canvas=%d, panel=%d, total=%d, failure=%s",
                     win_w, cf_w, pp_w, total, failure)

    def _load_product_context(self):
        ctx = {}
        if self.barcode_value:
            ctx["BARCODE"] = self.barcode_value
        if self.product_name:
            ctx["NAME"] = self.product_name
        if self.product_price:
            ctx["PRICE"] = self.product_price
        if self.product_expiry:
            ctx["EXPIRY"] = self.product_expiry
        if self.product_manufacture:
            ctx["MFG_DATE"] = self.product_manufacture
        self.label_canvas.var_context = ctx

        if self.product_id and self.product_id != "NEW":
            loaded = load_label_by_id(self.product_id, self.label_canvas)
            if loaded:
                logger.info("Loaded existing label for product %s", self.product_id)
                return

        if load_template(self.label_canvas):
            for elem in self.label_canvas.elements:
                if "text" in elem.props:
                    elem.props["text"] = resolve_variables(elem.props["text"], ctx)
                if "data" in elem.props:
                    elem.props["data"] = resolve_variables(elem.props["data"], ctx)
            self.label_canvas.redraw()
            self.entry_w.delete(0, "end")
            self.entry_w.insert(0, str(self.label_canvas.width))
            self.entry_h.delete(0, "end")
            self.entry_h.insert(0, str(self.label_canvas.height))
            logger.info("Loaded template as layout source")
            for elem in self.label_canvas.elements:
                logger.info("  element id=%s type=%s x=%d y=%d text=%r",
                            elem.id, elem.type, elem.x, elem.y,
                            elem.props.get("text", elem.props.get("data", "")))
            return

        y_offset = 30
        gap = 8
        if self.barcode_value:
            elem = BarcodeElement(x=50, y=y_offset, props={"data": self.barcode_value, "show_text": self.show_barcode_text})
            self.label_canvas.add_element(elem)
            y_offset += 90 + gap
            logger.info("Created barcode element for product %s at (50, %d)", self.product_id, y_offset - 90 - gap)
        if self.product_name and self.show_name:
            elem = LabelElement(type="text", x=50, y=y_offset, width=280, height=40,
                props={"text": self.product_name, "font": "Arial", "font_size": 16, "color": "#000000"})
            self.label_canvas.add_element(elem)
            y_offset += 40 + gap
            logger.info("Created name element at (50, %d): %s", y_offset - 40 - gap, self.product_name)
        if self.product_price and self.show_price:
            elem = LabelElement(type="text", x=50, y=y_offset, width=150, height=32,
                props={"text": self.product_price, "font": "Arial", "font_size": 14, "color": "#000000"})
            self.label_canvas.add_element(elem)
            y_offset += 32 + gap
            logger.info("Created price element at (50, %d): %s", y_offset - 32 - gap, self.product_price)
        if self.product_expiry and self.show_expiry:
            elem = LabelElement(type="text", x=50, y=y_offset, width=200, height=28,
                props={"text": f"Exp: {self.product_expiry}", "font": "Arial", "font_size": 11, "color": "#666666"})
            self.label_canvas.add_element(elem)
            y_offset += 28 + gap
            logger.info("Created expiry element at (50, %d): %s", y_offset - 28 - gap, self.product_expiry)
        if self.product_manufacture:
            elem = LabelElement(type="text", x=50, y=y_offset, width=200, height=28,
                props={"text": f"Mfg: {self.product_manufacture}", "font": "Arial", "font_size": 11, "color": "#666666"})
            self.label_canvas.add_element(elem)
            logger.info("Created manufacture element at (50, %d): %s", y_offset, self.product_manufacture)

    def _apply_canvas_size(self):
        try:
            w = int(self.entry_w.get().strip())
            h = int(self.entry_h.get().strip())
        except ValueError:
            logger.error("Invalid canvas size input")
            return
        if w < 50 or h < 50:
            logger.warning("Minimum canvas size is 50x50")
            return
        self.label_canvas.set_size(w, h)

    def _add_text_element(self):
        elem = LabelElement(
            type="text", x=50, y=50, width=150, height=40,
            props={"text": "Sample Text", "font": "Arial", "font_size": 16, "color": "#000000"},
        )
        self.label_canvas.add_element(elem)

    def _add_shape_element(self):
        elem = ShapeElement(x=100, y=100, props={"shape": "rectangle"})
        self.label_canvas.add_element(elem)

    def _add_barcode_element(self):
        elem = BarcodeElement(x=50, y=50, props={"data": "SAMPLE-12345", "show_text": True})
        self.label_canvas.add_element(elem)

    def _add_qr_element(self):
        elem = QRElement(x=50, y=50, props={"data": "https://example.com"})
        self.label_canvas.add_element(elem)

    def _delete_selected(self):
        if self.label_canvas.selected_id:
            self.label_canvas.remove_element(self.label_canvas.selected_id)

    def _save_file(self):
        if self.product_id and self.product_id != "NEW":
            save_label_by_id(self.product_id, self.label_canvas)
        else:
            filename = filedialog.asksaveasfilename(
                title="Save Label", filetypes=FILE_TYPES, defaultextension=FILE_EXTENSION
            )
            if filename:
                save_label(filename, self.label_canvas)

    def _load_file(self):
        if self.product_id and self.product_id != "NEW":
            load_label_by_id(self.product_id, self.label_canvas)
        else:
            filename = filedialog.askopenfilename(
                title="Load Label", filetypes=FILE_TYPES
            )
            if filename:
                load_label(filename, self.label_canvas)

    def _export_png(self):
        filename = filedialog.asksaveasfilename(
            title="Export PNG", filetypes=PNG_FILE_TYPES, defaultextension=".png"
        )
        if filename:
            export_to_png(filename, self.label_canvas)

    def _print_label(self):
        print_label(self.label_canvas)

    def _save_template(self):
        if save_template(self.label_canvas):
            logger.info("Template saved")
        else:
            logger.error("Template save failed")

    def _load_template(self):
        if load_template(self.label_canvas):
            self.entry_w.delete(0, "end")
            self.entry_w.insert(0, str(self.label_canvas.width))
            self.entry_h.delete(0, "end")
            self.entry_h.insert(0, str(self.label_canvas.height))
            logger.info("Template loaded")
        else:
            logger.info("No template found")


def main():
    args = _parse_args()
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    app = LabelEngineApp(
        product_id=args.product_id,
        barcode_value=args.barcode_value,
        product_name=args.product_name,
        product_price=args.product_price,
        product_expiry=args.product_expiry,
        product_manufacture=args.product_manufacture,
        show_name=args.show_name == "True",
        show_price=args.show_price == "True",
        show_expiry=args.show_expiry == "True",
        show_barcode_text=args.show_barcode_text == "True",
    )
    app.mainloop()


if __name__ == "__main__":
    main()
