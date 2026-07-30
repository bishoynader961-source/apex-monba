import customtkinter as ctk
from tkinter import ttk, messagebox

import database


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
