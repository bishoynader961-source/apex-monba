import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox
import os
import json
import tempfile
from datetime import datetime, date

import database
import barcode_logic

from label_engine.canvas_core import LabelCanvas, draw_elements
from label_engine.export import load_label, export_to_png, print_label, TEMPLATE_PATH

from ui_helpers import _extract_first_var, _extract_all_vars


class LabelDesignerPopup(ctk.CTkToplevel):
    def __init__(self, parent, name, price, barcode, expiry="", mfg="", *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self.title("Label Designer")
        self.geometry("800x500")
        self.product_name = name
        self.internal_barcode = barcode
        self.price = price
        self.product_expiry = expiry
        self.product_mfg = mfg

        self.grid_columnconfigure(0, weight=2)
        self.grid_columnconfigure(1, weight=1, minsize=300)
        self.grid_rowconfigure(0, weight=1)

        self.canvas_frame = ctk.CTkFrame(self)
        self.canvas_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

        self.v_scroll = tk.Scrollbar(self.canvas_frame, orient="vertical")
        self.h_scroll = tk.Scrollbar(self.canvas_frame, orient="horizontal")

        self.preview_canvas = tk.Canvas(
            self.canvas_frame, bg="white",
            xscrollcommand=self.h_scroll.set,
            yscrollcommand=self.v_scroll.set,
        )

        self.h_scroll.config(command=self.preview_canvas.xview)
        self.v_scroll.config(command=self.preview_canvas.yview)

        self.v_scroll.pack(side="right", fill="y")
        self.h_scroll.pack(side="bottom", fill="x")
        self.preview_canvas.pack(side="left", fill="both", expand=True)

        self.preview_canvas.bind("<MouseWheel>", self._on_canvas_mousewheel)
        self.preview_canvas.bind("<Shift-MouseWheel>", self._on_canvas_shift_mousewheel)

        self._label_canvas = LabelCanvas(self, 400, 300)
        self._label_canvas.var_context = {}

        self.controls_frame = ctk.CTkFrame(self)
        self.controls_frame.grid(row=0, column=1, sticky="nsew", padx=(0, 20), pady=20)

        self._dynamic_entries = {}
        self._build_controls(name, price, expiry)

        self.current_img = None

        def _safe_preview():
            if self.winfo_exists():
                self.update_preview()

        self.after(100, _safe_preview)

    def _build_controls(self, name, price, expiry):
        ctk.CTkLabel(self.controls_frame, text="Design Overrides", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(10, 10))

        template_loaded = False
        if os.path.exists(TEMPLATE_PATH):
            try:
                with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
                    template_data = json.load(f)
                template_loaded = True
            except Exception:
                template_loaded = False

        if template_loaded:
            self._label_canvas.clear()
            load_label(TEMPLATE_PATH, self._label_canvas)
            self._build_dynamic_fields(template_data)
        else:
            self._build_default_fields(name, price, expiry)

        print_btn = ctk.CTkButton(self.controls_frame, text="Quick Print", command=self.print_label, height=40, font=ctk.CTkFont(size=16, weight="bold"))
        print_btn.pack(pady=(10, 30), padx=20, fill="x", side="bottom")

        adv_btn = ctk.CTkButton(self.controls_frame, text="Open Label Designer", command=self.launch_m8_engine, height=40, fg_color="#1f538d", font=ctk.CTkFont(size=16, weight="bold"))
        adv_btn.pack(pady=(10, 0), padx=20, fill="x", side="bottom")

    def _build_dynamic_fields(self, template_data):
        scroll_frame = ctk.CTkScrollableFrame(self.controls_frame, fg_color="transparent")
        scroll_frame.pack(fill="both", expand=True, padx=5, pady=(0, 5))

        ctk.CTkLabel(scroll_frame, text="Template Fields", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=15, pady=(5, 10))

        defaults = {
            "NAME": self.product_name or "",
            "BARCODE": self.internal_barcode or "",
            "PHARMACY_NAME": "My Pharmacy",
            "PHARMACY_ADDRESS": "",
            "DRUG_NAME": "",
            "BATCH_NO": "",
            "MANUFACTURER": "",
            "QTY": "",
            "PRICE": self.app.currency.fmt(float(self._get_numeric_price())) if self._get_numeric_price() else self.app.currency.fmt(0),
            "EXPIRY": self.product_expiry or "",
            "MFG_DATE": self.product_mfg or "",
        }

        for elem_data in template_data.get("elements", []):
            if elem_data.get("type") != "text":
                continue
            elem_id = elem_data.get("id", "")
            props = elem_data.get("props", {})
            raw_text = props.get("text", "")

            label_text = raw_text.replace("{{", "").replace("}}", "")
            if len(label_text) > 30:
                label_text = label_text[:27] + "..."

            default_val = raw_text
            if raw_text in defaults:
                default_val = defaults[raw_text]
            else:
                var_match = _extract_first_var(raw_text)
                if var_match and var_match in defaults:
                    default_val = defaults[var_match]

            ctk.CTkLabel(scroll_frame, text=label_text, anchor="w", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=15, pady=(8, 2))
            entry = ctk.CTkEntry(scroll_frame, width=200)
            entry.insert(0, default_val)
            entry.pack(padx=15, pady=(0, 2), fill="x")
            entry.bind("<KeyRelease>", lambda e: self.update_preview())

            self._dynamic_entries[elem_id] = entry

    def _build_default_fields(self, name, price, expiry):
        ctk.CTkLabel(self.controls_frame, text="Text Edits", font=ctk.CTkFont(weight="bold")).pack(pady=(20, 5))

        self.name_entry = ctk.CTkEntry(self.controls_frame, width=200)
        self.name_entry.insert(0, name)
        self.name_entry.pack(padx=20, pady=5)
        self.name_entry.bind("<KeyRelease>", lambda e: self.update_preview())

        self.price_entry = ctk.CTkEntry(self.controls_frame, width=200)
        self.price_entry.insert(0, self.app.currency.fmt(float(price)) if price else self.app.currency.fmt(0))
        self.price_entry.pack(padx=20, pady=5)
        self.price_entry.bind("<KeyRelease>", lambda e: self.update_preview())

        self.expiry_entry = ctk.CTkEntry(self.controls_frame, width=200)
        self.expiry_entry.insert(0, expiry or "")
        self.expiry_entry.pack(padx=20, pady=5)
        self.expiry_entry.bind("<KeyRelease>", lambda e: self.update_preview())

        self.mfg_entry = ctk.CTkEntry(self.controls_frame, width=200)
        self.mfg_entry.insert(0, self.product_mfg or "")
        self.mfg_entry.pack(padx=20, pady=5)
        self.mfg_entry.bind("<KeyRelease>", lambda e: self.update_preview())

    def _get_numeric_price(self):
        try:
            return float(self.price)
        except (ValueError, TypeError):
            return None

    def launch_m8_engine(self):
        ctx = self._build_context()
        current_name = ctx.get("NAME", "")
        current_price = ctx.get("PRICE", "")
        current_expiry = ctx.get("EXPIRY", self.product_expiry)
        current_mfg = ctx.get("MFG_DATE", self.product_mfg)

        try:
            barcode_logic.open_label_engine(
                "NEW", self.internal_barcode, current_name, current_price,
                expiry=current_expiry, manufacture=current_mfg,
                show_name=True,
                show_price=True,
                show_expiry=True,
                show_barcode_text=True,
            )
        except Exception as e:
            messagebox.showerror("Error", f"Could not open Label Designer:\n{str(e)}")

    def _get_field_value(self, field, default=""):
        if hasattr(self, "name_entry") and field == "name":
            return self.name_entry.get()
        if hasattr(self, "price_entry") and field == "price":
            return self.price_entry.get()
        if hasattr(self, "expiry_entry") and field == "expiry":
            return self.expiry_entry.get()
        if hasattr(self, "mfg_entry") and field == "mfg":
            return self.mfg_entry.get()
        return default

    def update_preview(self):
        context = self._build_context()
        self._label_canvas.var_context = context

        self.preview_canvas.delete("all")
        draw_elements(self.preview_canvas, self._label_canvas.elements, scale=1.0, context=context)

        self.preview_canvas.config(scrollregion=self.preview_canvas.bbox("all"))
        self.preview_canvas.xview_moveto(0)
        self.preview_canvas.yview_moveto(0)

    def _build_context(self):
        if self._dynamic_entries:
            ctx = {}
            for elem_id, entry in self._dynamic_entries.items():
                elem = self._label_canvas.get_element(elem_id)
                if elem and elem.type == "text":
                    raw_text = elem.props.get("text", "")
                    for var_name in _extract_all_vars(raw_text):
                        ctx[var_name] = entry.get()
            ctx["BARCODE"] = self.internal_barcode
            return ctx
        else:
            ctx = {}
            if hasattr(self, "name_entry"):
                ctx["NAME"] = self.name_entry.get()
            if hasattr(self, "price_entry"):
                ctx["PRICE"] = self.price_entry.get()
            if hasattr(self, "expiry_entry"):
                ctx["EXPIRY"] = self.expiry_entry.get()
            if hasattr(self, "mfg_entry"):
                ctx["MFG_DATE"] = self.mfg_entry.get()
            ctx["BARCODE"] = self.internal_barcode
            return ctx

    def _on_canvas_mousewheel(self, event):
        self.preview_canvas.yview_scroll(-1 * (event.delta // 120), "units")

    def _on_canvas_shift_mousewheel(self, event):
        self.preview_canvas.xview_scroll(-1 * (event.delta // 120), "units")

    def print_label(self):
        try:
            self._label_canvas.var_context = self._build_context()
            temp_path = os.path.join(tempfile.gettempdir(), f"print_{self.internal_barcode}.png")
            export_to_png(temp_path, self._label_canvas)
            os.startfile(temp_path, "print")
            self.destroy()
        except Exception as e:
            messagebox.showerror("Print Error", f"Failed to print:\n{str(e)}")


class QuickReceiveModal(ctk.CTkToplevel):
    def __init__(self, parent, product_name: str, vendor_name: str, barcode: str):
        super().__init__(parent)
        self.title("Quick Receive Inventory")
        self.geometry("380x240")
        self.grab_set()

        self.parent = parent
        self.product_name = product_name
        self.vendor_name = vendor_name
        self.barcode = barcode

        ctk.CTkLabel(self, text=f"Receive {product_name} from {vendor_name}",
                      font=ctk.CTkFont(size=15, weight="bold"), wraplength=340
                      ).pack(padx=20, pady=(18, 12))

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="x", padx=20)
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form, text="Quantity:", anchor="w").grid(row=0, column=0, padx=(0, 8), pady=5, sticky="w")
        self.qty_entry = ctk.CTkEntry(form, placeholder_text="e.g. 10")
        self.qty_entry.grid(row=0, column=1, sticky="ew", pady=5)

        ctk.CTkLabel(form, text=i18n.t("total_cost"), anchor="w").grid(row=1, column=0, padx=(0, 8), pady=5, sticky="w")
        self.cost_entry = ctk.CTkEntry(form, placeholder_text="0.00")
        self.cost_entry.grid(row=1, column=1, sticky="ew", pady=5)
        self.cost_entry.insert(0, "0.00")

        self.qty_entry.focus_set()
        self.bind("<Return>", lambda e: self._submit())

        ctk.CTkButton(self, text="Submit", command=self._submit, height=36,
                       font=ctk.CTkFont(size=14)).pack(padx=20, pady=(10, 15), fill="x")

    def _submit(self):
        qty_str = self.qty_entry.get().strip()
        cost_str = self.cost_entry.get().strip()

        if not qty_str:
            messagebox.showwarning("Missing Quantity", "Please enter a quantity.", parent=self)
            return
        try:
            qty = int(qty_str)
            if qty <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid Quantity", "Quantity must be a positive whole number.", parent=self)
            return

        try:
            cost = float(cost_str) if cost_str else 0.0
        except ValueError:
            messagebox.showerror("Invalid Cost", "Cost must be a number.", parent=self)
            return

        existing = database.get_product_by_barcode(self.barcode)
        if not existing:
            messagebox.showerror("Error", f"Could not find product with barcode {self.barcode}.", parent=self)
            return

        _, tpl_name, tpl_price, tpl_mfg_barcode, _, _, tpl_expiry, tpl_mfg_date, _ = existing

        try:
            database.receive_inventory_atomically(
                self.vendor_name, self.product_name, date.today().isoformat(), qty, qty * tpl_price,
                tpl_price, tpl_mfg_barcode, tpl_expiry, tpl_mfg_date,
                barcode_logic.generate_internal_barcode
            )
        except Exception as e:
            messagebox.showerror("Transaction Failed",
                                 f"No inventory was saved.\n\n{str(e)}", parent=self)
            return

        parent = self.parent
        self.destroy()

        def _refresh():
            if parent.winfo_exists():
                parent.load_inventory()
                parent.load_receiving_log()

        parent.after(100, _refresh)
        messagebox.showinfo("Success",
                            f"Received {qty}x {self.product_name} from {self.vendor_name}.")


class BulkAddModal(ctk.CTkToplevel):
    def __init__(self, parent, name, price, mfg_barcode, expiry_date, manufacture_date, vendor_name):
        super().__init__(parent)
        self.title("Quick Receive (Bulk)")
        self.geometry("420x420")
        self.grab_set()

        self.parent = parent
        self.name = name
        self.price = price
        self.mfg_barcode = mfg_barcode
        self.expiry_date = expiry_date
        self.manufacture_date = manufacture_date
        self.vendor_name = vendor_name

        ctk.CTkLabel(self, text="Bulk Receive Product",
                      font=ctk.CTkFont(size=16, weight="bold")).pack(padx=20, pady=(16, 10))

        info_frame = ctk.CTkFrame(self, fg_color="#2a2a3e", corner_radius=8)
        info_frame.pack(fill="x", padx=20, pady=(0, 10))
        info_frame.grid_columnconfigure(1, weight=1)

        fields = [
            ("Name:", name),
            ("Price:", self.app.currency.fmt(price)),
            ("Vendor:", vendor_name),
            ("Mfg Barcode:", mfg_barcode or "\u2014"),
            ("Expiry:", expiry_date or "\u2014"),
            ("Mfg Date:", manufacture_date or "\u2014"),
        ]
        for i, (label, value) in enumerate(fields):
            ctk.CTkLabel(info_frame, text=label, font=ctk.CTkFont(size=12),
                         text_color="#8899aa", anchor="w").grid(row=i, column=0, padx=(12, 8), pady=3, sticky="w")
            ctk.CTkLabel(info_frame, text=value, font=ctk.CTkFont(size=12),
                         anchor="w").grid(row=i, column=1, padx=(0, 12), pady=3, sticky="w")

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="x", padx=20)
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form, text="Quantity:", anchor="w").grid(row=0, column=0, padx=(0, 8), pady=8, sticky="w")
        self.qty_entry = ctk.CTkEntry(form, placeholder_text="e.g. 50")
        self.qty_entry.grid(row=0, column=1, sticky="ew", pady=8)

        ctk.CTkLabel(form, text=i18n.t("total_wholesale_cost"), anchor="w").grid(row=1, column=0, padx=(0, 8), pady=8, sticky="w")
        self.cost_entry = ctk.CTkEntry(form, placeholder_text="e.g. 250.00")
        self.cost_entry.grid(row=1, column=1, sticky="ew", pady=8)
        self.cost_entry.insert(0, "0.00")

        self.qty_entry.focus_set()
        self.bind("<Return>", lambda e: self._submit())

        ctk.CTkButton(self, text="Add to Queue",
                      command=self._submit, height=40,
                      font=ctk.CTkFont(size=14, weight="bold"),
                      fg_color="#2563EB", hover_color="#1d4ed8"
                      ).pack(padx=20, pady=(14, 16), fill="x")

    def _submit(self):
        qty_str = self.qty_entry.get().strip()
        cost_str = self.cost_entry.get().strip()

        if not qty_str:
            messagebox.showwarning("Missing Quantity", "Please enter a quantity.", parent=self)
            return
        try:
            qty = int(qty_str)
            if qty <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid Quantity", "Quantity must be a positive whole number.", parent=self)
            return

        try:
            total_cost = float(cost_str) if cost_str else 0.0
        except ValueError:
            messagebox.showerror("Invalid Cost", "Total Cost must be a number.", parent=self)
            return

        vendor = self.vendor_name
        if vendor not in self.parent.receiving_session:
            self.parent.receiving_session[vendor] = {
                "total_quantity": 0,
                "vendor_asking_price": 0.0,
                "items": []
            }

        self.parent.receiving_session[vendor]["total_quantity"] += qty
        self.parent.receiving_session[vendor]["items"].append({
            "name": self.name,
            "qty": qty,
            "price": self.price,
            "cost": total_cost,
            "mfg_barcode": self.mfg_barcode,
            "internal_barcode": "",
            "mfg_date": self.manufacture_date or "",
            "exp_date": self.expiry_date or "",
            "date_received": datetime.now().strftime('%Y-%m-%d'),
        })

        parent = self.parent
        qty_ref = qty
        self.destroy()

        parent.name_entry.delete(0, 'end')
        parent.price_entry.delete(0, 'end')
        parent.mfg_entry.delete(0, 'end')
        parent.expiry_entry.delete(0, 'end')
        parent.mfg_date_entry.delete(0, 'end')
        parent.vendor_name_entry.delete(0, 'end')
        parent.template_var.set("Select a template...")

        parent.tab_view.set("Receive Inventory")
        parent.vendor_entry.delete(0, "end")
        parent.vendor_entry.insert(0, vendor)
        parent._refresh_po_treeview()
        parent.recv_status_label.configure(
            text=f"Queued {qty_ref}x {self.name} for {vendor}.",
            text_color="#007bff")

        def _clear_status():
            if parent.recv_status_label.winfo_exists():
                parent.recv_status_label.configure(text="")
        parent.recv_status_label.after(5000, _clear_status)
        messagebox.showinfo("Success", f"Queued {qty_ref}x {self.name} for {vendor} in Pending PO.")


class BulkLabelPrintDialog(ctk.CTkToplevel):
    def __init__(self, parent, boxes, batch_folder):
        super().__init__(parent)
        self.title(f"Bulk Label Printer \u2014 {len(boxes)} boxes pending")
        self.geometry("960x620")
        self.grab_set()

        self._parent = parent
        self._boxes = boxes
        self._save_dir = batch_folder
        self._current_img = None

        self.grid_columnconfigure(0, weight=3, minsize=420)
        self.grid_columnconfigure(1, weight=2, minsize=300)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=15, pady=(12, 0))

        ctk.CTkLabel(header, text="Save Path:",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#8899aa").pack(side="left")
        path_lbl = ctk.CTkLabel(header, text=batch_folder,
                     font=ctk.CTkFont(size=11),
                     text_color="#60a5fa", cursor="hand2")
        path_lbl.pack(side="left", padx=(6, 0))
        path_lbl.bind("<Button-1>", lambda e: self._copy_path())
        ctk.CTkLabel(header, text="(click to open folder)",
                     font=ctk.CTkFont(size=10),
                     text_color="#666").pack(side="left", padx=(6, 0))

        tree_frame = ctk.CTkFrame(self)
        tree_frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=10)

        cols = ("Name", "Vendor", "Barcode", "Price")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("#0", text="#")
        self.tree.column("#0", width=40, anchor="center")
        for c in cols:
            self.tree.heading(c, text=c)
        self.tree.column("Name", width=160, anchor="w")
        self.tree.column("Vendor", width=100, anchor="w")
        self.tree.column("Barcode", width=110, anchor="center")
        self.tree.column("Price", width=70, anchor="e")

        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=tree_scroll.set)
        tree_scroll.grid(row=0, column=1, sticky="ns")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        for idx, box in enumerate(self._boxes, 1):
            self.tree.insert("", "end", iid=str(idx - 1),
                             text=str(idx),
                             values=(box["name"], box["vendor"],
                                     box["barcode"], self.app.currency.fmt(box['price'])))
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        right = ctk.CTkFrame(self)
        right.grid(row=1, column=1, sticky="nsew", padx=(0, 15), pady=10)
        right.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(right, text="Label Controls",
                     font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, pady=(12, 5), padx=15, sticky="w")

        self.preview_canvas = tk.Canvas(right, bg="white", highlightthickness=0)
        self.preview_canvas.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 10))

        btn_col = ctk.CTkFrame(right, fg_color="transparent")
        btn_col.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 12))
        btn_col.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(btn_col, text="Open Label Designer",
                      fg_color="#1f538d", hover_color="#17406b",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      command=self._open_designer).grid(
            row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))

        ctk.CTkButton(btn_col, text="Export All PNG",
                      fg_color="#2563EB", hover_color="#1d4ed8",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      command=self._export_all).grid(
            row=1, column=0, sticky="ew", padx=(0, 3), pady=(0, 6))

        ctk.CTkButton(btn_col, text="Print All",
                      fg_color="#7c3aed", hover_color="#6d28d9",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      command=self._print_all).grid(
            row=1, column=1, sticky="ew", padx=(3, 0), pady=(0, 6))

        ctk.CTkButton(btn_col, text="Close", height=32,
                      fg_color="#6b7280", hover_color="#4b5563",
                      command=self.destroy).grid(
            row=3, column=0, columnspan=2, sticky="ew")

    def _on_select(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        box = self._boxes[idx]
        self._render_preview(box)

    def _render_preview(self, box):
        self.preview_canvas.delete("all")
        try:
            from label_engine.canvas_core import LabelCanvas
            from label_engine.export import load_template, export_to_png as _exp, TEMPLATE_PATH as _TP

            if not os.path.exists(_TP):
                self.preview_canvas.create_text(
                    10, 10, anchor="nw",
                    text="No label template found.\nDesign one in the Label Designer first.",
                    fill="#888", font=("Arial", 12))
                return

            lbl = LabelCanvas(None, 400, 300)
            load_template(lbl)
            lbl.var_context = {
                "NAME": box["name"],
                "PRICE": self.app.currency.fmt(box['price']) if box["price"] else self.app.currency.fmt(0),
                "BARCODE": box["barcode"],
                "EXPIRY": box.get("expiry", ""),
                "MFG_DATE": box.get("mfg_date", ""),
            }
            import tempfile as _tmp
            tmp = os.path.join(_tmp.gettempdir(), f"_preview_{box['barcode']}.png")
            _exp(tmp, lbl)

            from PIL import Image, ImageTk
            img = Image.open(tmp)
            cw = max(self.preview_canvas.winfo_width(), 200)
            ch = max(self.preview_canvas.winfo_height(), 150)
            scale = min(cw / img.width, ch / img.height)
            rw, rh = int(img.width * scale), int(img.height * scale)
            img = img.resize((rw, rh), Image.LANCZOS)
            self._current_img = ImageTk.PhotoImage(img)
            ox = (cw - rw) // 2
            oy = (ch - rh) // 2
            self.preview_canvas.create_image(ox, oy, anchor="nw", image=self._current_img)
            self.preview_canvas.config(scrollregion=self.preview_canvas.bbox("all"))
            img.close()
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception as e:
            self.preview_canvas.create_text(
                10, 10, anchor="nw",
                text=f"Preview error:\n{e}", fill="#f55", font=("Arial", 11))

    def _open_designer(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("No Selection", "Select a box from the list first.", parent=self)
            return
        box = self._boxes[int(sel[0])]
        LabelDesignerPopup(self, box["name"], f"{box['price']:.2f}",
                           box["barcode"], box.get("expiry", ""), box.get("mfg_date", ""))

    def _export_all(self):
        try:
            from label_engine.canvas_core import LabelCanvas
            from label_engine.export import load_template, export_to_png, TEMPLATE_PATH

            if not os.path.exists(TEMPLATE_PATH):
                messagebox.showinfo("No Template",
                    "No label template found. Design one in the Label Designer first.", parent=self)
                return

            lbl = LabelCanvas(None, 400, 300)
            load_template(lbl)

            for box in self._boxes:
                lbl.var_context = {
                    "NAME": box["name"],
                    "PRICE": self.app.currency.fmt(box['price']) if box["price"] else self.app.currency.fmt(0),
                    "BARCODE": box["barcode"],
                    "EXPIRY": box.get("expiry", ""),
                    "MFG_DATE": box.get("mfg_date", ""),
                }
                png_path = os.path.join(self._save_dir, f"{box['barcode']}.png")
                export_to_png(png_path, lbl)

            messagebox.showinfo("Export Complete",
                f"{len(self._boxes)} label(s) saved to:\n{self._save_dir}", parent=self)
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export labels:\n{str(e)}", parent=self)

    def _print_all(self):
        try:
            from label_engine.canvas_core import LabelCanvas
            from label_engine.export import load_template, export_to_png, print_label, TEMPLATE_PATH

            if not os.path.exists(TEMPLATE_PATH):
                messagebox.showinfo("No Template",
                    "No label template found. Design one in the Label Designer first.", parent=self)
                return

            lbl = LabelCanvas(None, 400, 300)
            load_template(lbl)

            for box in self._boxes:
                lbl.var_context = {
                    "NAME": box["name"],
                    "PRICE": self.app.currency.fmt(box['price']) if box["price"] else self.app.currency.fmt(0),
                    "BARCODE": box["barcode"],
                    "EXPIRY": box.get("expiry", ""),
                    "MFG_DATE": box.get("mfg_date", ""),
                }
                print_label(lbl)

            messagebox.showinfo("Print Sent",
                f"{len(self._boxes)} label(s) sent to printer.", parent=self)
        except Exception as e:
            messagebox.showerror("Print Error", f"Failed to print labels:\n{str(e)}", parent=self)

    def _copy_path(self):
        if os.path.isdir(self._save_dir):
            os.startfile(self._save_dir, "open")
        else:
            self.clipboard_clear()
            self.clipboard_append(self._save_dir)


class EditBatchDialog(ctk.CTkToplevel):
    def __init__(self, parent, row):
        super().__init__(parent)
        batch_id, name, price, mfg_barcode, int_barcode, status, expiry, mfg_date, vendor = row
        self.title(f"Edit Batch: {name}")
        self.geometry("460x620")
        self.grab_set()

        self.parent = parent
        self.batch_id = batch_id
        self.int_barcode = int_barcode
        self._original_vendor = vendor or "N/A"

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(15, 5))
        ctk.CTkLabel(header, text=f"Edit: {name}", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(header, text=f"Batch ID: {batch_id}  |  Internal: {int_barcode}",
                      text_color="gray").pack(anchor="w")

        sep = ctk.CTkFrame(self, height=1, fg_color="gray50")
        sep.pack(fill="x", padx=20, pady=(5, 10))

        form = ctk.CTkScrollableFrame(self, fg_color="transparent")
        form.pack(fill="both", expand=True, padx=20, pady=(0, 5))
        form.grid_columnconfigure(1, weight=1)

        fields = [
            ("Name:", "name_var", name),
            (i18n.t("price_label"), "price_var", f"{price:.2f}"),
            ("Mfg Barcode:", "mfg_barcode_var", mfg_barcode),
            ("Internal Barcode:", "int_barcode_var", int_barcode),
            ("Expiry Date:", "expiry_var", expiry or ""),
            ("Mfg Date:", "mfg_var", mfg_date or ""),
            ("Vendor:", "vendor_var", vendor or "N/A"),
        ]

        for i, (label, var_name, value) in enumerate(fields):
            ctk.CTkLabel(form, text=label, anchor="w").grid(row=i, column=0, padx=(0, 10), pady=5, sticky="w")
            var = ctk.StringVar(value=value)
            setattr(self, var_name, var)
            entry = ctk.CTkEntry(form, textvariable=var)
            entry.grid(row=i, column=1, sticky="ew", pady=5)
            if var_name == "int_barcode_var":
                entry.configure(state="disabled")
                ctk.CTkLabel(form, text="(Auto-Generated)", text_color="gray",
                             font=ctk.CTkFont(size=11)).grid(row=i, column=2, padx=(6, 0), pady=5, sticky="w")

        status_row = len(fields)
        ctk.CTkLabel(form, text="Status:", anchor="w").grid(row=status_row, column=0, padx=(0, 10), pady=5, sticky="w")
        self.status_var = ctk.StringVar(value=status or "In Stock")
        ctk.CTkSegmentedButton(form, values=["In Stock", "Sold"], variable=self.status_var
        ).grid(row=status_row, column=1, sticky="ew", pady=5)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(5, 15))

        ctk.CTkButton(btn_frame, text="Save Changes", command=self._save, height=38,
                       font=ctk.CTkFont(size=14)).pack(side="left", padx=(0, 10), fill="x", expand=True)
        ctk.CTkButton(btn_frame, text="Open Label Designer", command=self._open_label_engine, height=38,
                       fg_color="#1f538d", font=ctk.CTkFont(size=14)).pack(side="left", fill="x", expand=True)

    def _save(self):
        from datetime import datetime as _dt
        name = self.name_var.get().strip()
        price_str = self.price_var.get().strip()
        mfg_barcode = self.mfg_barcode_var.get().strip()
        expiry = self.expiry_var.get().strip()
        mfg = self.mfg_var.get().strip()
        status = self.status_var.get()
        vendor = self.vendor_var.get().strip() or "N/A"

        if not name:
            messagebox.showerror("Error", "Name is required.")
            return
        if not mfg_barcode:
            messagebox.showerror("Error", "Manufacturer barcode is required.")
            return

        try:
            price = float(price_str)
        except ValueError:
            messagebox.showerror("Error", "Price must be a valid number.")
            return

        if expiry and not self.parent._validate_date(expiry, "Expiry Date", allow_empty=True):
            return
        if mfg and not self.parent._validate_date(mfg, "Manufacture Date", allow_empty=True):
            return

        if expiry and mfg:
            try:
                exp_dt = _dt.strptime(expiry, "%Y-%m-%d")
                mfg_dt = _dt.strptime(mfg, "%Y-%m-%d")
                if mfg_dt >= exp_dt:
                    messagebox.showerror("Error", "Manufacture date must be before expiry date.")
                    return
            except ValueError:
                return

        try:
            database.update_product_full(
                self.batch_id, name, price, mfg_barcode, self.int_barcode,
                expiry, mfg, status, vendor
            )
            vendor_changed = (self._original_vendor in (None, '', 'N/A')
                              and vendor not in (None, '', 'N/A'))
            if vendor_changed:
                database.log_shipment(
                    vendor, name, _dt.now().strftime('%Y-%m-%d'),
                    1, price, self.int_barcode
                )
            parent = self.parent
            self.destroy()

            def _refresh():
                if parent.winfo_exists():
                    parent.load_inventory()
                    parent.load_receiving_log()

            parent.after(100, _refresh)
            if vendor_changed:
                QuickReceiveModal(parent, name, vendor, self.int_barcode)
            else:
                messagebox.showinfo("Success", "Batch updated successfully.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update batch:\n{str(e)}")

    def _open_label_engine(self):
        expiry = self.expiry_var.get().strip()
        mfg = self.mfg_var.get().strip()
        price = self.price_var.get().strip()
        name = self.name_var.get().strip()
        try:
            barcode_logic.open_label_engine(
                "NEW", self.int_barcode, name, price,
                expiry=expiry, manufacture=mfg
            )
        except Exception as e:
            messagebox.showerror("Error", f"Could not open Label Designer:\n{str(e)}")
