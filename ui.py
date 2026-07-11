import customtkinter as ctk
from tkinter import ttk, messagebox
import os
import json
from PIL import Image
import tempfile

import database
import barcode_logic

class PharmacyApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("Pharmacy Inventory System")
        self.geometry("1000x700")
        
        # Configure grid
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        # Create TabView
        self.tab_view = ctk.CTkTabview(self)
        self.tab_view.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        
        self.tab_view.configure(command=self.on_tab_change)
        
        self.tab_add = self.tab_view.add("Add Product")
        self.tab_inventory = self.tab_view.add("Inventory")
        self.tab_report = self.tab_view.add("Sales Report")
        self.tab_templates = self.tab_view.add("Templates")
        self.tab_settings = self.tab_view.add("Settings")
        
        self.templates_list = []
        
        self.setup_add_tab()
        self.setup_inventory_tab()
        self.setup_report_tab()
        self.setup_templates_tab()
        self.setup_settings_tab()
        
    def on_tab_change(self):
        current_tab = self.tab_view.get()
        if current_tab == "Add Product":
            self.refresh_add_tab_templates()
        elif current_tab == "Inventory":
            self.load_inventory()
        elif current_tab == "Sales Report":
            self.load_sales_report()
        elif current_tab == "Templates":
            self.load_templates_grid()
            
    # --- Add Product Tab ---
    def setup_add_tab(self):
        self.tab_add.grid_columnconfigure((0, 1), weight=1)
        
        title_label = ctk.CTkLabel(self.tab_add, text="Add New Product", font=ctk.CTkFont(size=24, weight="bold"))
        title_label.grid(row=0, column=0, columnspan=2, padx=20, pady=(20, 30))
        
        tpl_label = ctk.CTkLabel(self.tab_add, text="Use Template (Optional):", anchor="w")
        tpl_label.grid(row=1, column=0, padx=(100, 10), pady=10, sticky="w")
        
        self.template_var = ctk.StringVar(value="Select a template...")
        self.template_combo = ctk.CTkComboBox(self.tab_add, width=300, variable=self.template_var, command=self.on_template_selected)
        self.template_combo.grid(row=1, column=1, padx=(10, 100), pady=10, sticky="w")
        self.refresh_add_tab_templates()
        
        name_label = ctk.CTkLabel(self.tab_add, text="Product Name:", anchor="w")
        name_label.grid(row=2, column=0, padx=(100, 10), pady=10, sticky="w")
        self.name_entry = ctk.CTkEntry(self.tab_add, width=300)
        self.name_entry.grid(row=2, column=1, padx=(10, 100), pady=10, sticky="w")
        
        price_label = ctk.CTkLabel(self.tab_add, text="Price ($):", anchor="w")
        price_label.grid(row=3, column=0, padx=(100, 10), pady=10, sticky="w")
        self.price_entry = ctk.CTkEntry(self.tab_add, width=300)
        self.price_entry.grid(row=3, column=1, padx=(10, 100), pady=10, sticky="w")
        
        mfg_label = ctk.CTkLabel(self.tab_add, text="Manufacturer Barcode:", anchor="w")
        mfg_label.grid(row=4, column=0, padx=(100, 10), pady=10, sticky="w")
        self.mfg_entry = ctk.CTkEntry(self.tab_add, width=300, placeholder_text="Scan or type barcode")
        self.mfg_entry.grid(row=4, column=1, padx=(10, 100), pady=10, sticky="w")
        self.mfg_entry.bind("<Return>", self.save_product)
        
        save_btn = ctk.CTkButton(self.tab_add, text="Save & Generate Tag", command=self.save_product, height=40, font=ctk.CTkFont(size=16))
        save_btn.grid(row=5, column=0, columnspan=2, pady=40)
        
    def refresh_add_tab_templates(self):
        self.templates_list = database.get_templates()
        combo_values = ["Select a template..."] + [tpl[1] for tpl in self.templates_list]
        self.template_combo.configure(values=combo_values)
        
    def on_template_selected(self, choice):
        if choice == "Select a template...":
            return
        for tpl in self.templates_list:
            if tpl[1] == choice:
                self.name_entry.delete(0, 'end')
                self.name_entry.insert(0, tpl[1])
                self.price_entry.delete(0, 'end')
                self.price_entry.insert(0, str(tpl[2]))
                break
                
    def save_product(self, event=None):
        name = self.name_entry.get().strip()
        price_str = self.price_entry.get().strip()
        mfg_barcode = self.mfg_entry.get().strip()
        
        if not name or not price_str or not mfg_barcode:
            messagebox.showerror("Error", "All fields are required!")
            return
            
        try:
            price = float(price_str)
        except ValueError:
            messagebox.showerror("Error", "Price must be a valid number!")
            return
            
        internal_barcode = barcode_logic.generate_internal_barcode(mfg_barcode)
        
        try:
            database.add_product(name, price, mfg_barcode, internal_barcode)
            
            self.name_entry.delete(0, 'end')
            self.price_entry.delete(0, 'end')
            self.mfg_entry.delete(0, 'end')
            self.template_var.set("Select a template...")
            
            messagebox.showinfo("Success", "Product saved successfully! Opening Label Designer...")
            
            # Open Designer Popup
            designer = LabelDesignerPopup(self, name, price_str, internal_barcode)
            designer.grab_set()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save product:\n{str(e)}")

    # --- Inventory Tab ---
    def setup_inventory_tab(self):
        self.tab_inventory.grid_rowconfigure(1, weight=1)
        self.tab_inventory.grid_columnconfigure(0, weight=1)
        
        search_frame = ctk.CTkFrame(self.tab_inventory, fg_color="transparent")
        search_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        search_frame.grid_columnconfigure(0, weight=1)
        
        self.search_entry = ctk.CTkEntry(search_frame, placeholder_text="Search by name, mfg barcode, or internal barcode...")
        self.search_entry.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        self.search_entry.bind("<Return>", self.perform_search)
        
        search_btn = ctk.CTkButton(search_frame, text="Search", width=100, command=self.perform_search)
        search_btn.grid(row=0, column=1)
        
        clear_btn = ctk.CTkButton(search_frame, text="Clear", width=100, fg_color="gray", hover_color="darkgray", command=self.load_inventory)
        clear_btn.grid(row=0, column=2, padx=(10, 10))
        
        sell_btn = ctk.CTkButton(search_frame, text="Sell Item", width=100, fg_color="#c42b1c", hover_color="#9e2216", command=self.sell_product)
        sell_btn.grid(row=0, column=3, padx=(10, 0))
        
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview",
                        background="#2b2b2b",
                        foreground="white",
                        rowheight=25,
                        fieldbackground="#2b2b2b",
                        bordercolor="#343638",
                        borderwidth=0)
        style.map('Treeview', background=[('selected', '#1f538d')])
        style.configure("Treeview.Heading",
                        background="#565b5e",
                        foreground="white",
                        relief="flat")
        style.map("Treeview.Heading",
                  background=[('active', '#3484F0')])
                  
        columns = ("ID", "Name", "Price", "Mfg Barcode", "Internal Barcode", "Status")
        self.tree_inv = ttk.Treeview(self.tab_inventory, columns=columns, show="headings")
        
        for col in columns:
            self.tree_inv.heading(col, text=col)
            
        self.tree_inv.column("ID", width=50, anchor="center")
        self.tree_inv.column("Name", width=200, anchor="w")
        self.tree_inv.column("Price", width=70, anchor="center")
        self.tree_inv.column("Mfg Barcode", width=130, anchor="center")
        self.tree_inv.column("Internal Barcode", width=130, anchor="center")
        self.tree_inv.column("Status", width=100, anchor="center")
        
        self.tree_inv.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        
        scrollbar = ttk.Scrollbar(self.tab_inventory, orient="vertical", command=self.tree_inv.yview)
        self.tree_inv.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=1, column=1, sticky="ns", pady=(0, 10))
        
        self.load_inventory()

    def load_inventory(self):
        self.search_entry.delete(0, 'end')
        for item in self.tree_inv.get_children():
            self.tree_inv.delete(item)
            
        products = database.get_all_products()
        for prod in products:
            self.tree_inv.insert("", "end", values=(prod[0], prod[1], f"${prod[2]:.2f}", prod[3], prod[4], prod[5]))

    def perform_search(self, event=None):
        query = self.search_entry.get().strip()
        if not query:
            self.load_inventory()
            return
            
        exact_match = database.get_product_by_barcode(query)
        if exact_match and event:
            self.search_entry.delete(0, 'end')
            self.load_inventory()
            for item in self.tree_inv.get_children():
                if str(self.tree_inv.item(item, 'values')[0]) == str(exact_match[0]):
                    self.tree_inv.selection_set(item)
                    self.tree_inv.focus(item)
                    self.tree_inv.see(item)
                    return
            return

        for item in self.tree_inv.get_children():
            self.tree_inv.delete(item)
            
        products = database.search_products(query)
        for prod in products:
            self.tree_inv.insert("", "end", values=(prod[0], prod[1], f"${prod[2]:.2f}", prod[3], prod[4], prod[5]))

    def sell_product(self):
        selected = self.tree_inv.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select an item to sell.")
            return
            
        item = selected[0]
        values = self.tree_inv.item(item, 'values')
        mfg_code = values[3]
        
        try:
            database.mark_item_as_sold(mfg_code)
            self.load_inventory()
            messagebox.showinfo("Success", "Item marked as sold and moved to Sales Report.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to mark item as sold:\n{str(e)}")

    # --- Sales Report Tab ---
    def setup_report_tab(self):
        self.tab_report.grid_rowconfigure(1, weight=1)
        self.tab_report.grid_columnconfigure(0, weight=1)
        
        top_frame = ctk.CTkFrame(self.tab_report, fg_color="transparent")
        top_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        
        self.report_count_label = ctk.CTkLabel(top_frame, text="Total Items Sold: 0", font=ctk.CTkFont(size=16, weight="bold"))
        self.report_count_label.pack(side="left", padx=20)
        
        self.report_revenue_label = ctk.CTkLabel(top_frame, text="Total Revenue: $0.00", font=ctk.CTkFont(size=16, weight="bold"), text_color="#28a745")
        self.report_revenue_label.pack(side="left", padx=20)
        
        refund_btn = ctk.CTkButton(top_frame, text="Refund Item", fg_color="#ffc107", text_color="black", hover_color="#e0a800", command=self.refund_item)
        refund_btn.pack(side="right", padx=20)
        
        columns = ("ID", "Name", "Price", "Mfg Barcode", "Internal Barcode", "Timestamp")
        self.tree_report = ttk.Treeview(self.tab_report, columns=columns, show="headings")
        
        for col in columns:
            self.tree_report.heading(col, text=col)
            
        self.tree_report.column("ID", width=50, anchor="center")
        self.tree_report.column("Name", width=200, anchor="w")
        self.tree_report.column("Price", width=70, anchor="center")
        self.tree_report.column("Mfg Barcode", width=120, anchor="center")
        self.tree_report.column("Internal Barcode", width=120, anchor="center")
        self.tree_report.column("Timestamp", width=150, anchor="center")
        
        self.tree_report.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        
        scrollbar = ttk.Scrollbar(self.tab_report, orient="vertical", command=self.tree_report.yview)
        self.tree_report.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=1, column=1, sticky="ns", pady=(0, 10))
        
    def load_sales_report(self):
        for item in self.tree_report.get_children():
            self.tree_report.delete(item)
            
        sold_items = database.get_sold_items()
        
        total_count = len(sold_items)
        total_revenue = sum(item[2] for item in sold_items)
        
        self.report_count_label.configure(text=f"Total Items Sold: {total_count}")
        self.report_revenue_label.configure(text=f"Total Revenue: ${total_revenue:.2f}")
        
        for item in sold_items:
            self.tree_report.insert("", "end", values=(item[0], item[1], f"${item[2]:.2f}", item[3], item[4], item[5]))
            
    def refund_item(self):
        selected = self.tree_report.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select an item to refund.")
            return
            
        item = selected[0]
        sold_id = self.tree_report.item(item, 'values')[0]
        
        try:
            database.reverse_sale(sold_id)
            self.load_sales_report()
            messagebox.showinfo("Refunded", "Item successfully returned to inventory.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to refund item:\n{str(e)}")

    # --- Templates Tab ---
    def setup_templates_tab(self):
        self.tab_templates.grid_rowconfigure(1, weight=1)
        self.tab_templates.grid_columnconfigure(0, weight=1)
        
        add_frame = ctk.CTkFrame(self.tab_templates, fg_color="transparent")
        add_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        
        ctk.CTkLabel(add_frame, text="Name:").pack(side="left", padx=(0, 5))
        self.tpl_name_entry = ctk.CTkEntry(add_frame, width=200)
        self.tpl_name_entry.pack(side="left", padx=(0, 15))
        
        ctk.CTkLabel(add_frame, text="Price:").pack(side="left", padx=(0, 5))
        self.tpl_price_entry = ctk.CTkEntry(add_frame, width=100)
        self.tpl_price_entry.pack(side="left", padx=(0, 15))
        
        add_btn = ctk.CTkButton(add_frame, text="Add Template", command=self.add_template_gui)
        add_btn.pack(side="left")
        
        edit_btn = ctk.CTkButton(add_frame, text="Update Selected", fg_color="#28a745", hover_color="#218838", command=self.update_template_gui)
        edit_btn.pack(side="left", padx=10)
        
        del_btn = ctk.CTkButton(add_frame, text="Delete Selected", fg_color="#c42b1c", hover_color="#9e2216", command=self.delete_template_gui)
        del_btn.pack(side="right", padx=10)
        
        columns = ("ID", "Name", "Price")
        self.tree_tpl = ttk.Treeview(self.tab_templates, columns=columns, show="headings")
        
        for col in columns:
            self.tree_tpl.heading(col, text=col)
            
        self.tree_tpl.column("ID", width=50, anchor="center")
        self.tree_tpl.column("Name", width=400, anchor="w")
        self.tree_tpl.column("Price", width=100, anchor="center")
        
        self.tree_tpl.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        
        scrollbar = ttk.Scrollbar(self.tab_templates, orient="vertical", command=self.tree_tpl.yview)
        self.tree_tpl.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=1, column=1, sticky="ns", pady=(0, 10))
        
        self.tree_tpl.bind("<<TreeviewSelect>>", self.on_template_tree_select)
        
    def load_templates_grid(self):
        for item in self.tree_tpl.get_children():
            self.tree_tpl.delete(item)
            
        templates = database.get_templates()
        for tpl in templates:
            self.tree_tpl.insert("", "end", values=(tpl[0], tpl[1], f"${tpl[2]:.2f}"))

    def on_template_tree_select(self, event):
        selected = self.tree_tpl.selection()
        if not selected:
            return
        item = selected[0]
        values = self.tree_tpl.item(item, 'values')
        
        self.tpl_name_entry.delete(0, 'end')
        self.tpl_name_entry.insert(0, values[1])
        
        self.tpl_price_entry.delete(0, 'end')
        price = values[2].replace('$', '')
        self.tpl_price_entry.insert(0, price)

    def add_template_gui(self):
        name = self.tpl_name_entry.get().strip()
        price_str = self.tpl_price_entry.get().strip()
        
        if not name or not price_str:
            messagebox.showwarning("Warning", "Name and Price required.")
            return
            
        try:
            price = float(price_str)
        except ValueError:
            messagebox.showwarning("Warning", "Price must be a number.")
            return
            
        database.add_template(name, price)
        self.tpl_name_entry.delete(0, 'end')
        self.tpl_price_entry.delete(0, 'end')
        self.load_templates_grid()
        self.refresh_add_tab_templates()
        
    def update_template_gui(self):
        selected = self.tree_tpl.selection()
        if not selected:
            messagebox.showwarning("Warning", "Select a template to update.")
            return
            
        item = selected[0]
        tpl_id = self.tree_tpl.item(item, 'values')[0]
        
        name = self.tpl_name_entry.get().strip()
        price_str = self.tpl_price_entry.get().strip()
        
        if not name or not price_str:
            messagebox.showwarning("Warning", "Name and Price required.")
            return
            
        try:
            price = float(price_str)
        except ValueError:
            messagebox.showwarning("Warning", "Price must be a number.")
            return
            
        database.update_template(tpl_id, name, price)
        self.tpl_name_entry.delete(0, 'end')
        self.tpl_price_entry.delete(0, 'end')
        self.load_templates_grid()
        self.refresh_add_tab_templates()

    def delete_template_gui(self):
        selected = self.tree_tpl.selection()
        if not selected:
            return
            
        item = selected[0]
        tpl_id = self.tree_tpl.item(item, 'values')[0]
        database.delete_template(tpl_id)
        self.load_templates_grid()
        self.refresh_add_tab_templates()

    # --- Settings Tab ---
    def setup_settings_tab(self):
        self.tab_settings.grid_columnconfigure((0, 1), weight=1)
        
        title_label = ctk.CTkLabel(self.tab_settings, text="Application Settings", font=ctk.CTkFont(size=24, weight="bold"))
        title_label.grid(row=0, column=0, columnspan=3, padx=20, pady=(20, 30))
        
        config = barcode_logic.load_config()
        
        # Label Settings
        name_label = ctk.CTkLabel(self.tab_settings, text="Pharmacy Name:", anchor="w")
        name_label.grid(row=1, column=0, padx=(100, 10), pady=10, sticky="w")
        self.set_name_entry = ctk.CTkEntry(self.tab_settings, width=300)
        self.set_name_entry.insert(0, config.get("pharmacy_name", "My Pharmacy"))
        self.set_name_entry.grid(row=1, column=1, padx=(10, 100), pady=10, sticky="w")
        
        font_label = ctk.CTkLabel(self.tab_settings, text="Pharmacy Name Font Size:", anchor="w")
        font_label.grid(row=2, column=0, padx=(100, 10), pady=10, sticky="w")
        self.set_font_entry = ctk.CTkEntry(self.tab_settings, width=300)
        self.set_font_entry.insert(0, str(config.get("font_size", 20)))
        self.set_font_entry.grid(row=2, column=1, padx=(10, 100), pady=10, sticky="w")
        
        self.set_price_var = ctk.BooleanVar(value=config.get("include_price", True))
        self.set_price_check = ctk.CTkCheckBox(self.tab_settings, text="Include Price on Label", variable=self.set_price_var)
        self.set_price_check.grid(row=3, column=0, columnspan=3, pady=20)
        
        # Database Path
        db_label = ctk.CTkLabel(self.tab_settings, text="Database Path:", anchor="w")
        db_label.grid(row=4, column=0, padx=(100, 10), pady=10, sticky="w")
        self.set_db_entry = ctk.CTkEntry(self.tab_settings, width=300)
        self.set_db_entry.insert(0, config.get("db_path", "pharmacy.db"))
        self.set_db_entry.grid(row=4, column=1, padx=(10, 10), pady=10, sticky="w")
        
        browse_btn = ctk.CTkButton(self.tab_settings, text="Browse...", width=100, command=self.browse_db_path)
        browse_btn.grid(row=4, column=2, padx=(0, 100), sticky="w")
        
        save_btn = ctk.CTkButton(self.tab_settings, text="Save Settings", command=self.save_settings, height=40, font=ctk.CTkFont(size=16))
        save_btn.grid(row=5, column=0, columnspan=3, pady=20)
        
        backup_btn = ctk.CTkButton(self.tab_settings, text="Backup Database", command=self.backup_database_gui, height=40, font=ctk.CTkFont(size=16), fg_color="#17a2b8", hover_color="#138496")
        backup_btn.grid(row=6, column=0, columnspan=3, pady=10)
        
    def browse_db_path(self):
        folder = ctk.filedialog.askdirectory(title="Select Database Folder")
        if folder:
            db_path = os.path.join(folder, "pharmacy.db")
            self.set_db_entry.delete(0, 'end')
            self.set_db_entry.insert(0, db_path)
            
    def backup_database_gui(self):
        folder = ctk.filedialog.askdirectory(title="Select Backup Destination Folder")
        if folder:
            try:
                backup_path = database.backup_database(folder)
                messagebox.showinfo("Backup Success", f"Database successfully backed up to:\n{backup_path}")
            except Exception as e:
                messagebox.showerror("Backup Failed", str(e))
        
    def save_settings(self):
        new_name = self.set_name_entry.get().strip()
        new_font_str = self.set_font_entry.get().strip()
        include_price = self.set_price_var.get()
        new_db_path = self.set_db_entry.get().strip()
        
        if not new_name:
            messagebox.showerror("Error", "Pharmacy Name cannot be empty.")
            return
            
        try:
            new_font = int(new_font_str)
            if new_font <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "Font size must be a positive integer.")
            return
            
        new_config = {
            "pharmacy_name": new_name,
            "font_size": new_font,
            "include_price": include_price,
            "db_path": new_db_path or "pharmacy.db"
        }
        
        try:
            with open(barcode_logic.CONFIG_FILE, "w") as f:
                json.dump(new_config, f, indent=4)
                
            # Initialize DB at new path if it doesn't exist
            database.init_db()
            
            # Refresh all tabs to use the newly connected database
            self.load_inventory()
            self.load_sales_report()
            self.load_templates_grid()
            self.refresh_add_tab_templates()
            
            messagebox.showinfo("Success", "Settings saved successfully! Connected to database.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save config:\n{str(e)}")

class LabelDesignerPopup(ctk.CTkToplevel):
    def __init__(self, master, name: str, price: str, internal_barcode: str):
        super().__init__(master)
        
        self.title("Label Designer")
        self.geometry("800x500")
        self.internal_barcode = internal_barcode
        
        # Grid layout: 2 columns
        self.grid_columnconfigure(0, weight=2)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # Left Canvas
        self.canvas_frame = ctk.CTkFrame(self)
        self.canvas_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        
        self.image_label = ctk.CTkLabel(self.canvas_frame, text="")
        self.image_label.pack(expand=True, fill="both")
        
        # Right Controls
        self.controls_frame = ctk.CTkFrame(self)
        self.controls_frame.grid(row=0, column=1, sticky="nsew", padx=(0, 20), pady=20)
        
        ctk.CTkLabel(self.controls_frame, text="Design Overrides", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(10, 20))
        
        # Toggles
        self.show_name_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(self.controls_frame, text="Show Name", variable=self.show_name_var, command=self.update_preview).pack(anchor="w", padx=20, pady=5)
        
        self.show_price_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(self.controls_frame, text="Show Price", variable=self.show_price_var, command=self.update_preview).pack(anchor="w", padx=20, pady=5)
        
        self.show_expiry_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(self.controls_frame, text="Show Expiry", variable=self.show_expiry_var, command=self.update_preview).pack(anchor="w", padx=20, pady=5)
        
        self.show_barcode_text_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(self.controls_frame, text="Show Barcode Text", variable=self.show_barcode_text_var, command=self.update_preview).pack(anchor="w", padx=20, pady=5)
        
        # Edit Fields
        ctk.CTkLabel(self.controls_frame, text="Text Edits", font=ctk.CTkFont(weight="bold")).pack(pady=(20, 5))
        
        self.name_entry = ctk.CTkEntry(self.controls_frame, width=200)
        self.name_entry.insert(0, name)
        self.name_entry.pack(padx=20, pady=5)
        self.name_entry.bind("<KeyRelease>", lambda e: self.update_preview())
        
        self.price_entry = ctk.CTkEntry(self.controls_frame, width=200)
        self.price_entry.insert(0, f"${float(price):.2f}")
        self.price_entry.pack(padx=20, pady=5)
        self.price_entry.bind("<KeyRelease>", lambda e: self.update_preview())
        
        self.expiry_entry = ctk.CTkEntry(self.controls_frame, width=200)
        self.expiry_entry.insert(0, "Exp: ")
        self.expiry_entry.pack(padx=20, pady=5)
        self.expiry_entry.bind("<KeyRelease>", lambda e: self.update_preview())
        
        # Print Button
        print_btn = ctk.CTkButton(self.controls_frame, text="Print Label", command=self.print_label, height=40, font=ctk.CTkFont(size=16, weight="bold"))
        print_btn.pack(pady=30, padx=20, fill="x", side="bottom")
        
        self.current_img = None
        
        # Small delay to ensure the window is drawn before rendering preview
        self.after(100, self.update_preview)
        
    def update_preview(self):
        flags = {
            "show_name": self.show_name_var.get(),
            "show_price": self.show_price_var.get(),
            "show_expiry": self.show_expiry_var.get(),
            "show_barcode_text": self.show_barcode_text_var.get()
        }
        
        overrides = {
            "name": self.name_entry.get(),
            "price": self.price_entry.get(),
            "expiry": self.expiry_entry.get()
        }
        
        self.current_img = barcode_logic.generate_preview_image(flags, overrides, self.internal_barcode)
        
        # Convert to CTkImage
        ctk_img = ctk.CTkImage(light_image=self.current_img, dark_image=self.current_img, size=(self.current_img.width, self.current_img.height))
        self.image_label.configure(image=ctk_img)
        self.image_label.image = ctk_img

    def print_label(self):
        if not self.current_img:
            return
            
        try:
            # Save to temporary file and print
            temp_dir = tempfile.gettempdir()
            print_path = os.path.join(temp_dir, f"print_{self.internal_barcode}.png")
            self.current_img.save(print_path)
            
            # Send to default printer on Windows
            os.startfile(print_path, "print")
            
            self.destroy() # close after print
        except Exception as e:
            messagebox.showerror("Print Error", f"Failed to print:\n{str(e)}")
