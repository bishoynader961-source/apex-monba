"""
ui_pos_terminal.py — POS Terminal module for PharmacyPro.

Provides:
  - PosTerminalFrame: CTkFrame with inventory search (Rx inventory_extended),
    cart management, tax/total calculation, 4 sale-type transactions, and
    recent-transaction logging.
  - setup_pos_terminal_tab(self): tab-setup function attached to PharmacyApp.
  - _refresh_pos_tab(self): refresh hook called on tab activation.

Integrates with:
  - rx_db.search_inventory / rx_db.get_all_inventory (inventory_extended table)
  - rx_db.update_inventory_on_hand (stock decrement on sale)
  - audit_log.log_action (transaction logging)
  - async_ui.AsyncUI (non-blocking search)
  - barcode_logic.load_config (tax_rate, pharmacy_name)
"""
import os
import sys
import sqlite3
import logging
from datetime import datetime

import customtkinter as ctk
from tkinter import ttk, messagebox

import i18n
import database
import barcode_logic
import audit_log
from ui_helpers import apply_treeview_style

try:
    from rx_db import (
        search_inventory as _rx_search_inventory,
        get_all_inventory as _rx_get_all_inventory,
        update_inventory_on_hand as _rx_update_inventory,
        HAS_SQLALCHEMY,
    )
except ImportError:
    _rx_search_inventory = None
    _rx_get_all_inventory = None
    _rx_update_inventory = None
    HAS_SQLALCHEMY = False

try:
    from async_ui import AsyncUI
except ImportError:
    AsyncUI = None

log = logging.getLogger("ui_pos_terminal")

_SALE_TYPES = ["Delivery", "OTC", "Rx OTC", "Loyalty"]


class PosTerminalFrame(ctk.CTkFrame):
    """POS terminal frame: search Rx inventory, build cart, process sale."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self.cart = []          # list of dicts: {ndc, name, strength, awp, qty}
        self._tx_counter = 0

        self._build_ui()
        self._load_recent_transactions()

    # ── UI Construction ──

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)

        # Title
        title = ctk.CTkLabel(
            self, text=i18n.t("pos_terminal"),
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        title.grid(row=0, column=0, sticky="w", padx=20, pady=(20, 5))

        subtitle = ctk.CTkLabel(
            self, text=i18n.t("pos_terminal_subtitle"),
            font=ctk.CTkFont(size=12), text_color="#94a3b8",
        )
        subtitle.grid(row=1, column=0, sticky="w", padx=20, pady=(0, 20))

        # Top row: Sale Type selector + Search
        top_row = ctk.CTkFrame(self, fg_color="transparent")
        top_row.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 10))
        top_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            top_row, text=i18n.t("sale_type"),
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))

        self.sale_type_var = ctk.StringVar(value=_SALE_TYPES[1])  # default: OTC
        self.sale_type_seg = ctk.CTkSegmentedButton(
            top_row, values=_SALE_TYPES, variable=self.sale_type_var,
        )
        self.sale_type_seg.grid(row=0, column=1, sticky="w")

        # Search row (right side)
        search_sub = ctk.CTkFrame(top_row, fg_color="transparent")
        search_sub.grid(row=0, column=2, sticky="e")

        self.search_var = ctk.StringVar()
        self.search_entry = ctk.CTkEntry(
            search_sub, width=260, textvariable=self.search_var,
            placeholder_text=i18n.t("pos_search_placeholder"),
        )
        self.search_entry.grid(row=0, column=0, sticky="w")
        self.search_entry.bind("<Return>", self._on_search)

        ctk.CTkButton(
            search_sub, text=i18n.t("search"), width=80,
            fg_color="#3B82F6", hover_color="#2563EB",
            command=self._on_search,
        ).grid(row=0, column=1, padx=(6, 0))

        # Main content area: left (search results + cart) / right (summary + payment)
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=3, column=0, sticky="nsew", padx=20, pady=(0, 10))
        content.grid_columnconfigure(0, weight=2)
        content.grid_columnconfigure(1, weight=1)
        content.grid_rowconfigure(0, weight=1)

        self._build_left_panel(content)
        self._build_right_panel(content)

        # Transaction log
        self._build_transaction_log(self, row=4)


    def _build_left_panel(self, parent):
        """Left panel: search results (top, scrollable) + cart (bottom)."""
        left = ctk.CTkFrame(parent, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.grid_rowconfigure(0, weight=1)
        left.grid_rowconfigure(1, weight=0)
        left.grid_columnconfigure(0, weight=1)

        # ── Search Results ──
        results_card = ctk.CTkFrame(left, fg_color="#2d2d3a", corner_radius=10)
        results_card.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        results_card.grid_columnconfigure(0, weight=1)
        results_card.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            results_card, text=i18n.t("search_inventory"),
            font=ctk.CTkFont(size=14, weight="bold"), text_color="#ffffff",
        ).grid(row=0, column=0, padx=16, pady=(12, 8), sticky="w")

        result_columns = ("NDC", "Drug Name", "Strength", "Form", "AWP", "On Hand")
        self.tree_results = ttk.Treeview(
            results_card, columns=result_columns, show="headings", height=8,
        )
        apply_treeview_style(self.tree_results)
        for col in result_columns:
            self.tree_results.heading(col, text=col)
        self.tree_results.column("NDC", width=100, anchor="w")
        self.tree_results.column("Drug Name", width=170, anchor="w")
        self.tree_results.column("Strength", width=80, anchor="center")
        self.tree_results.column("Form", width=80, anchor="center")
        self.tree_results.column("AWP", width=70, anchor="e")
        self.tree_results.column("On Hand", width=70, anchor="center")
        self.tree_results.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))

        res_scroll = ttk.Scrollbar(results_card, orient="vertical", command=self.tree_results.yview)
        self.tree_results.configure(yscrollcommand=res_scroll.set)
        res_scroll.grid(row=1, column=1, sticky="ns", padx=(0, 12), pady=(0, 12))

        self.tree_results.bind("<Double-1>", self._on_result_double_click)

        # ── Cart ──
        cart_card = ctk.CTkFrame(left, fg_color="#2d2d3a", corner_radius=10)
        cart_card.grid(row=1, column=0, sticky="ew", pady=(0, 0))
        cart_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            cart_card, text=i18n.t("cart_pos"),
            font=ctk.CTkFont(size=14, weight="bold"), text_color="#ffffff",
        ).grid(row=0, column=0, padx=16, pady=(12, 8), sticky="w")

        cart_columns = ("Item", "NDC", "Qty", "AWP", "Line Total")
        self.tree_cart = ttk.Treeview(
            cart_card, columns=cart_columns, show="headings", height=6,
        )
        apply_treeview_style(self.tree_cart)
        for col in cart_columns:
            self.tree_cart.heading(col, text=col)
        self.tree_cart.column("Item", width=170, anchor="w")
        self.tree_cart.column("NDC", width=100, anchor="w")
        self.tree_cart.column("Qty", width=50, anchor="center")
        self.tree_cart.column("AWP", width=70, anchor="e")
        self.tree_cart.column("Line Total", width=80, anchor="e")
        self.tree_cart.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))

        # Cart controls
        cart_btn_row = ctk.CTkFrame(cart_card, fg_color="transparent")
        cart_btn_row.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))
        cart_btn_row.grid_columnconfigure((0, 1, 2, 3), weight=0)

        ctk.CTkButton(
            cart_btn_row, text="+1", width=60,
            fg_color="#3B82F6", hover_color="#2563EB",
            command=lambda: self._on_cart_qty(+1),
        ).grid(row=0, column=0, padx=(0, 4))
        ctk.CTkButton(
            cart_btn_row, text="-1", width=60,
            fg_color="#6c757d", hover_color="#5a6268",
            command=lambda: self._on_cart_qty(-1),
        ).grid(row=0, column=1, padx=(0, 4))
        ctk.CTkButton(
            cart_btn_row, text="Remove", width=80,
            fg_color="#EF4444", hover_color="#DC2626",
            command=self._on_cart_remove,
        ).grid(row=0, column=2, padx=(0, 4))
        ctk.CTkButton(
            cart_btn_row, text="Clear Cart", width=90,
            fg_color="#6c757d", hover_color="#5a6268",
            command=self._on_cart_clear,
        ).grid(row=0, column=3, padx=(0, 0))


    def _build_right_panel(self, parent):
        """Right panel: order summary, payment, complete button."""
        right = ctk.CTkFrame(parent, fg_color="#2d2d3a", corner_radius=10)
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(5, weight=1)

        # ── Order Summary ──
        ctk.CTkLabel(
            right, text="Order Summary",
            font=ctk.CTkFont(size=16, weight="bold"), text_color="#ffffff",
        ).grid(row=0, column=0, padx=20, pady=(16, 12), sticky="w")

        self.summary_subtotal_label = self._summary_row(right, i18n.t("pos_subtotal"), 1)
        self.summary_tax_label = self._summary_row(right, self.app.currency.tax_term(), 2)
        self.summary_total_label = self._summary_row(right, i18n.t("pos_total"), 3, bold=True)
        self.summary_items_label = self._summary_row(right, i18n.t("pos_items"), 4)

        # ── Payment Section ──
        ctk.CTkLabel(
            right, text="Payment",
            font=ctk.CTkFont(size=14, weight="bold"), text_color="#ffffff",
        ).grid(row=5, column=0, padx=20, pady=(20, 8), sticky="w")

        # Payment method
        self.payment_var = ctk.StringVar(value="Cash")
        payment_seg = ctk.CTkSegmentedButton(
            right, values=["Cash", "Card", "Insurance"],
            variable=self.payment_var,
        )
        payment_seg.grid(row=6, column=0, padx=20, pady=(0, 12), sticky="ew")

        # Amount tendered
        self.tendered_var = ctk.StringVar(value="0.00")
        self.tendered_entry = ctk.CTkEntry(
            right, width=160, textvariable=self.tendered_var,
        )
        self.tendered_entry.grid(row=7, column=0, padx=20, pady=(0, 6), sticky="w")
        ctk.CTkLabel(right, text="Amount Tendered", font=ctk.CTkFont(size=11), text_color="#a0a0a0").grid(
            row=8, column=0, padx=20, pady=(0, 0), sticky="w"
        )

        self.change_label = ctk.CTkLabel(
            right, text=i18n.t("change_due") + ": " + self.app.currency.fmt(0),
            font=ctk.CTkFont(size=16, weight="bold"), text_color="#10B981",
        )
        self.change_label.grid(row=9, column=0, padx=20, pady=(12, 8), sticky="w")

        # Complete transaction button
        self.complete_btn = ctk.CTkButton(
            right, text=i18n.t("complete_transaction"), height=46,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color="#10B981", hover_color="#059669",
            command=self._on_complete_transaction,
        )
        self.complete_btn.grid(row=10, column=0, padx=20, pady=(8, 16), sticky="ew")


    def _summary_row(self, parent, label_text, row, bold=False):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=20, pady=4)
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            frame, text=label_text, font=ctk.CTkFont(size=12),
            text_color="#a0a0a0",
        ).grid(row=0, column=0, sticky="w")

        val = ctk.CTkLabel(
            frame, text=self.app.currency.fmt(0),
            font=ctk.CTkFont(size=14, weight="bold") if bold else ctk.CTkFont(size=14),
            text_color="#ffffff" if bold else "#e0e0e0",
        )
        val.grid(row=0, column=1, sticky="e")
        return val


    def _build_transaction_log(self, parent, row):
        """Recent transactions Treeview at the bottom."""
        card = ctk.CTkFrame(parent, fg_color="#1a1a2e", corner_radius=10)
        card.grid(row=row, column=0, sticky="nsew", padx=20, pady=(0, 20))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            card, text=i18n.t("transaction_log"),
            font=ctk.CTkFont(size=14, weight="bold"), text_color="#ffffff",
        ).grid(row=0, column=0, padx=16, pady=(12, 4), sticky="w")

        tx_columns = ("Timestamp", "Type", "NDC", "Item", "Qty", "Total")
        self.tree_tx = ttk.Treeview(card, columns=tx_columns, show="headings", height=8)
        apply_treeview_style(self.tree_tx)
        for col in tx_columns:
            self.tree_tx.heading(col, text=col)
        self.tree_tx.column("Timestamp", width=130, anchor="w")
        self.tree_tx.column("Type", width=70, anchor="center")
        self.tree_tx.column("NDC", width=100, anchor="w")
        self.tree_tx.column("Item", width=170, anchor="w")
        self.tree_tx.column("Qty", width=50, anchor="center")
        self.tree_tx.column("Total", width=70, anchor="e")
        self.tree_tx.grid(row=1, column=0, sticky="nsew", padx=16, pady=(4, 12))

        tx_scroll = ttk.Scrollbar(card, orient="vertical", command=self.tree_tx.yview)
        self.tree_tx.configure(yscrollcommand=tx_scroll.set)
        tx_scroll.grid(row=1, column=1, sticky="ns", padx=(0, 12), pady=(4, 12))

        self.tree_tx.tag_configure("even", background="#2b2b2b", foreground="#ffffff")
        self.tree_tx.tag_configure("odd", background="#1e1e1e", foreground="#ffffff")


    # ── Inventory Search ──

    def _on_search(self, event=None):
        """Search Rx inventory asynchronously."""
        query = self.search_var.get().strip()
        if not query:
            self._load_all_inventory()
            return

        for item in self.tree_results.get_children():
            self.tree_results.delete(item)

        if AsyncUI is not None:
            AsyncUI.get().run(
                func=self._do_search,
                callback=self._on_search_done,
                args=(query,),
            )
        else:
            results = self._do_search(query)
            self._on_search_done(results, None)


    def _do_search(self, query):
        """Perform the inventory search (runs in background thread)."""
        if _rx_search_inventory is not None:
            try:
                return _rx_search_inventory(query)
            except Exception as e:
                log.warning("rx_db.search_inventory failed: %s, falling back to sqlite3", e)

        # Fallback: direct sqlite3 query on inventory_extended
        db_path = database.get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        like = f"%{query}%"
        try:
            cursor.execute("""
                SELECT id, ndc_code, drug_name, strength, dosage_form, ndc_formatted,
                       awp, mac, lot_number, expiration_date, on_hand, supplier, regional_metadata
                FROM inventory_extended
                WHERE ndc_code LIKE ?
                   OR drug_name LIKE ?
                   OR ndc_formatted LIKE ?
                ORDER BY drug_name ASC
            """, (like, like, like))
            return cursor.fetchall()
        finally:
            conn.close()


    def _on_search_done(self, results, error=None):
        """Callback to populate search results Treeview (runs on main thread)."""
        for item in self.tree_results.get_children():
            self.tree_results.delete(item)

        if error:
            messagebox.showwarning("Search Error", str(error), parent=self)
            return

        if not results:
            messagebox.showinfo("No Results", i18n.t("no_inventory_found"), parent=self)
            return

        for idx, row in enumerate(results):
            tag = "even" if idx % 2 == 0 else "odd"
            ndc = row[1] if len(row) > 1 else ""
            name = row[2] if len(row) > 2 else ""
            strength = row[3] if len(row) > 3 else ""
            form = row[4] if len(row) > 4 else ""
            awp = row[6] if len(row) > 6 else 0.0
            on_hand = row[10] if len(row) > 10 else 0

            self.tree_results.insert("", "end", values=(
                ndc, name, strength, form, self.app.currency.fmt(awp), on_hand
            ), tags=(tag,))


    def _load_all_inventory(self):
        """Load all inventory items."""
        if _rx_get_all_inventory is not None:
            try:
                rows = _rx_get_all_inventory()
            except Exception:
                rows = []
        else:
            rows = []

        for item in self.tree_results.get_children():
            self.tree_results.delete(item)

        for idx, row in enumerate(rows):
            tag = "even" if idx % 2 == 0 else "odd"
            self.tree_results.insert("", "end", values=(
                row[1], row[2], row[3], row[4], self.app.currency.fmt(row[6]), row[10]
            ), tags=(tag,))


    def _on_result_double_click(self, event=None):
        """Add selected search result to cart."""
        selected = self.tree_results.selection()
        if not selected:
            return
        values = self.tree_results.item(selected[0], "values")
        ndc, name, strength, form, awp_str, on_hand = values
        awp = self.app.currency.parse(awp_str or "0")

        for item in self.cart:
            if item["ndc"] == ndc:
                if item["qty"] < int(on_hand or 0):
                    item["qty"] += 1
                break
        else:
            self.cart.append({
                "ndc": ndc,
                "name": name,
                "strength": strength,
                "form": form,
                "awp": awp,
                "qty": 1,
            })

        self._refresh_cart()


    # ── Cart Management ──

    def _on_cart_qty(self, delta):
        """Adjust quantity of selected cart item by delta."""
        selected = self.tree_cart.selection()
        if not selected:
            return
        idx = self.tree_cart.index(selected[0])
        if 0 <= idx < len(self.cart):
            self.cart[idx]["qty"] = max(1, self.cart[idx]["qty"] + delta)
            self._refresh_cart()


    def _on_cart_remove(self):
        selected = self.tree_cart.selection()
        if not selected:
            return
        for iid in reversed([self.tree_cart.index(s) for s in selected]):
            if 0 <= iid < len(self.cart):
                self.cart.pop(iid)
        self._refresh_cart()


    def _on_cart_clear(self):
        self.cart.clear()
        self._refresh_cart()


    def _refresh_cart(self):
        """Repopulate the cart Treeview and recalculate totals."""
        for item in self.tree_cart.get_children():
            self.tree_cart.delete(item)

        for idx, entry in enumerate(self.cart):
            tag = "even" if idx % 2 == 0 else "odd"
            line_total = entry["awp"] * entry["qty"]
            self.tree_cart.insert("", "end", values=(
                entry["name"],
                entry["ndc"],
                entry["qty"],
                self.app.currency.fmt(entry['awp']),
                self.app.currency.fmt(line_total),
            ), tags=(tag,))

        self._calculate_totals()


    def _calculate_totals(self):
        """Calculate subtotal, tax, total, and change due."""
        config = barcode_logic.load_config()
        tax_rate = config.get("tax_rate", 0.0)

        subtotal = sum(e["awp"] * e["qty"] for e in self.cart)
        tax = subtotal * tax_rate
        total = subtotal + tax
        total_qty = sum(e["qty"] for e in self.cart)

        self.summary_subtotal_label.configure(text=self.app.currency.fmt(subtotal))
        self.summary_tax_label.configure(text=self.app.currency.fmt(tax))
        self.summary_total_label.configure(text=self.app.currency.fmt(total))
        self.summary_items_label.configure(
            text=i18n.t("pos_items_count", count=total_qty)
        )

        # Recalculate change
        self._update_change()


    def _update_change(self):
        """Recalculate change due based on tendered amount."""
        try:
            tendered = float(self.tendered_var.get())
        except (ValueError, TypeError):
            tendered = 0.0

        total_str = self.summary_total_label.cget("text")
        try:
            total = self.app.currency.parse(total_str)
        except (ValueError, TypeError):
            total = 0.0

        change = tendered - total
        if change < 0:
            change = 0.0
        self.change_label.configure(
            text=f"Change Due: {self.app.currency.fmt(change)}",
            text_color="#10B981" if change >= 0 else "#EF4444",
        )


    def _on_tendered_change(self, event=None):
        self._update_change()


    # ── Transaction Processing ──

    def _on_complete_transaction(self):
        """Process the sale: update inventory, log transaction, clear cart."""
        if not self.cart:
            messagebox.showwarning("Empty Cart", "Add items before completing a sale.", parent=self)
            return

        try:
            tendered = float(self.tendered_var.get())
        except (ValueError, TypeError):
            messagebox.showwarning("Invalid Amount", "Please enter a valid tendered amount.", parent=self)
            return

        total_str = self.summary_total_label.cget("text")
        try:
            total = self.app.currency.parse(total_str)
        except (ValueError, TypeError):
            total = 0.0

        if tendered < total:
            if not messagebox.askyesno(
                "Insufficient Tender",
                f"Tendered ({self.app.currency.fmt(tendered)}) is less than total ({self.app.currency.fmt(total)}).\nProceed anyway?",
                parent=self,
            ):
                return

        sale_type = self.sale_type_var.get()

        tx_id = None
        try:
            # Decrement inventory for each cart item
            for item in self.cart:
                new_on_hand = max(0, item["qty"])
                current = self._get_current_on_hand(item["ndc"])
                updated = max(0, current - item["qty"])
                if _rx_update_inventory is not None:
                    try:
                        _rx_update_inventory(item["ndc"], updated)
                    except Exception as e:
                        log.warning("Failed to update inventory for %s: %s", item["ndc"], e)
                else:
                    self._fallback_update_on_hand(item["ndc"], updated)

            # Create receipt in the standard database (for transaction log)
            conn = sqlite3.connect(database.get_db_path())
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO receipts (timestamp, total_amount, payment_method)
                VALUES (?, ?, ?)
            """, (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                total,
                f"{sale_type} / {self.payment_var.get()}",
            ))
            conn.commit()
            tx_id = cursor.lastrowid
            conn.close()

            # Log the transaction
            audit_log.log_action(
                "POS_SALE",
                f"Tx#{tx_id} | Type: {sale_type} | Items: {len(self.cart)} | "
                f"{i18n.t('pos_total')}: {self.app.currency.fmt(total)} | Method: {self.payment_var.get()}",
            )

            # Add to transaction log Treeview
            self._add_transaction_row(tx_id, sale_type, total)

            messagebox.showinfo(
                "Transaction Complete",
                f"{i18n.t('pos_total')}: {self.app.currency.fmt(total)}\nPayment: {self.payment_var.get()}",
                parent=self,
            )

            # Reset state
            self.cart.clear()
            self.tendered_var.set("0.00")
            self._refresh_cart()
            self._refresh_results_on_hand()

        except Exception as e:
            log.error("POS transaction error: %s", e)
            messagebox.showerror("Error", f"Transaction failed:\n{e}", parent=self)


    def _get_current_on_hand(self, ndc_code):
        """Check current on_hand for an NDC code."""
        if _rx_get_all_inventory is not None:
            try:
                rows = _rx_get_all_inventory()
                for row in rows:
                    if row[1] == ndc_code:  # ndc_code is column index 1
                        return row[10]  # on_hand is index 10
            except Exception:
                pass
        # Fallback: sqlite3
        db_path = database.get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT on_hand FROM inventory_extended WHERE ndc_code = ?",
                (ndc_code,),
            )
            result = cursor.fetchone()
            return result[0] if result else 0
        finally:
            conn.close()


    def _fallback_update_on_hand(self, ndc_code, new_on_hand):
        """Direct sqlite3 update when rx_db is unavailable."""
        db_path = database.get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE inventory_extended SET on_hand = ? WHERE ndc_code = ?",
                (new_on_hand, ndc_code),
            )
            conn.commit()
        finally:
            conn.close()


    def _add_transaction_row(self, tx_id, sale_type, total):
        """Add a transaction entry to the log Treeview."""
        now = datetime.now().strftime("%H:%M:%S")
        idx = len(self.tree_tx.get_children())
        tag = "even" if idx % 2 == 0 else "odd"
        self.tree_tx.insert("", "end", values=(
            now, sale_type, "", "", "", self.app.currency.fmt(total)
        ), tags=(tag,))


    def _refresh_results_on_hand(self):
        """Refresh the on-hand column in search results after a sale."""
        query = self.search_var.get().strip()
        self._on_search(None)


    # ── Transaction History ──

    def _load_recent_transactions(self):
        """Load recent transactions from the receipts table."""
        try:
            conn = sqlite3.connect(database.get_db_path())
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, timestamp, total_amount, payment_method
                FROM receipts ORDER BY id DESC LIMIT 20
            """)
            rows = cursor.fetchall()
            conn.close()

            for item in self.tree_tx.get_children():
                self.tree_tx.delete(item)

            for idx, row in enumerate(rows):
                tag = "even" if idx % 2 == 0 else "odd"
                self.tree_tx.insert("", "end", values=(
                    row[1] or "",
                    row[3] or "",
                    "", "", "",
                    self.app.currency.fmt(row[2]) if row[2] else self.app.currency.fmt(0),
                ), tags=(tag,))
        except Exception as e:
            log.warning("Failed to load recent transactions: %s", e)


    # ── Lifecycle ──

    def refresh(self):
        """Refresh the entire frame — called on tab switch."""
        self._calculate_totals()
        self._load_recent_transactions()


def setup_pos_terminal_tab(self):
    """Create the POS Terminal tab inside PharmacyApp."""
    pos_frame = PosTerminalFrame(
        self.tab_pos,
        fg_color="transparent",
    )
    pos_frame.pack(fill="both", expand=True, padx=4, pady=4)

    pos_frame.tendered_entry.bind("<KeyRelease>", pos_frame._on_tendered_change)
    pos_frame._load_all_inventory()
    pos_frame._calculate_totals()
    pos_frame._load_recent_transactions()
    self.pos_terminal_frame = pos_frame


def _refresh_pos_tab(self):
    """Refresh hook called when the POS Terminal tab is activated."""
    if hasattr(self, "pos_terminal_frame"):
        self.pos_terminal_frame.refresh()
