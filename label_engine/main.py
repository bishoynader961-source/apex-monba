import sys
import os
import tkinter as tk
from tkinter import filedialog
import logging
import customtkinter as ctk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from canvas_core import LabelCanvas, LabelElement, BarcodeElement, QRElement, ShapeElement
from properties_panel import PropertiesPanel
from export import save_label, load_label, export_to_png, print_label, FILE_TYPES, FILE_EXTENSION, PNG_FILE_TYPES

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_W = 400
DEFAULT_H = 300


class LabelEngineApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Label Design Engine")
        self.geometry("1100x650")
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self._build_menu()
        self._build_toolbar()
        self._build_canvas_area()
        self._build_properties_panel()

        logger.info("LabelEngineApp launched")

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
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 0))

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

    def _build_canvas_area(self):
        self.canvas_frame = ctk.CTkFrame(self)
        self.canvas_frame.grid(row=1, column=0, sticky="nsew", padx=(10, 0), pady=10)
        self.canvas_frame.grid_rowconfigure(0, weight=1)
        self.canvas_frame.grid_columnconfigure(0, weight=1)

        self.label_canvas = LabelCanvas(self.canvas_frame, DEFAULT_W, DEFAULT_H)
        self.label_canvas.frame.grid(row=0, column=0, sticky="nsew")

    def _build_properties_panel(self):
        self.props_panel = PropertiesPanel(self, self.label_canvas)
        self.props_panel.frame.grid(row=1, column=1, sticky="ns", padx=(0, 10), pady=10)

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
        filename = filedialog.asksaveasfilename(
            title="Save Label", filetypes=FILE_TYPES, defaultextension=FILE_EXTENSION
        )
        if filename:
            save_label(filename, self.label_canvas)

    def _load_file(self):
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


def main():
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    app = LabelEngineApp()
    app.mainloop()


if __name__ == "__main__":
    main()
