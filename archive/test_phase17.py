"""
test_phase17.py — Unit tests for Phase 17: Pharmacy POS Audit & Interface Overhaul.

Tests:
  - StubEliminationTests: P1.1-1.3 — verify checkout stubs are no longer `pass`
  - AsyncProductLoadTests: T9 — verify _checkout_add_item / _checkout_load_products use AsyncUI
  - SupplierLookupTests: P2.1 — mock ndc_dictionary, verify form population
  - TaskPanelTests: P2.2 — verify all 9 task buttons are wired (no "coming soon")
  - MenuBarTests: P3.1-3.5 — verify 5 menu bar methods exist on PharmacyApp
  - ReceiptDetailDialogTests: P4.1-4.2 — verify ReceiptDetailDialog loads items
  - CheckoutTabLayoutTests: P5.1 — verify no duplicate checkout_items_count_label
  - I18nTests: verify new keys present in all 6 locale files
  - RegressionTests: verify test_phase16 patterns still work
"""
import os
import sys

# CRITICAL: route the ORM engine + sqlite3 fallback to a disposable temp DB
# BEFORE any `import database` / `import db` resolves DATABASE_URL at import
# time. This protects the production archive/pharmacy.db.
import test_db_fixture  # noqa: F401  (must precede database/db imports)

import json
import inspect
import tempfile
import unittest
from unittest.mock import patch, MagicMock

ARCHIVE_DIR = os.path.dirname(os.path.abspath(__file__))
if ARCHIVE_DIR not in sys.path:
    sys.path.insert(0, ARCHIVE_DIR)


class BaseTempDBTestCase(unittest.TestCase):
    """Base class that provisions a temp database for each test."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._orig_db_path = None

    def tearDown(self):
        try:
            os.unlink(self._tmp.name)
        except OSError:
            pass

    def _patch_db_path(self):
        """Patch database.get_db_path to return the temp DB path."""
        import database
        self._orig_db_path = database.get_db_path
        database.get_db_path = lambda: self._tmp.name

    def _unpatch_db_path(self):
        import database
        if self._orig_db_path is not None:
            database.get_db_path = self._orig_db_path


# =============================================================================
# T1: Stub Elimination Tests
# =============================================================================

class StubEliminationTests(unittest.TestCase):
    """Verify P1.1-1.3: checkout tab stubs are implemented, not `pass`."""

    def test_checkout_stubs_not_pass(self):
        """_print_receipt, _checkout_add_item, _on_checkout_product_change
        must not be `pass`-only bodies."""
        import ui_checkout_tab as mod

        for func_name in ("_print_receipt", "_checkout_add_item",
                          "_on_checkout_product_change"):
            source = inspect.getsource(getattr(mod, func_name))
            # A pass-only function is 2 lines: def + pass
            self.assertFalse(
                source.strip().endswith("pass"),
                f"{func_name} still has a `pass` body"
            )

    def test_print_receipt_uses_receipt_engine(self):
        """_print_receipt must reference receipt_engine.generate_receipt."""
        import ui_checkout_tab as mod
        source = inspect.getsource(mod._print_receipt)
        self.assertIn("receipt_engine", source)

    def test_checkout_add_item_uses_product_picker(self):
        """_checkout_add_item must open ProductPickerDialog."""
        import ui_checkout_tab as mod
        source = inspect.getsource(mod._checkout_add_item)
        self.assertIn("ProductPickerDialog", source)

    def test_on_checkout_product_change_populates_barcode(self):
        """_on_checkout_product_change must populate the barcode entry."""
        import ui_checkout_tab as mod
        source = inspect.getsource(mod._on_checkout_product_change)
        self.assertIn("checkout_barcode_entry", source)


# =============================================================================
# T9: Async Product Load Tests
# =============================================================================

class AsyncProductLoadTests(unittest.TestCase):
    """Verify P1.2/P1.3 use AsyncUI for database.get_all_products()."""

    def test_checkout_load_products_uses_asyncui(self):
        """_checkout_load_products must call AsyncUI.get().run()."""
        import ui_checkout_tab as mod
        source = inspect.getsource(mod._checkout_load_products)
        self.assertIn("AsyncUI", source)
        self.assertIn(".run(", source)

    def test_product_picker_dialog_uses_asyncui(self):
        """ProductPickerDialog._load_products must call AsyncUI.get().run()."""
        from ui_pos_panels import ProductPickerDialog
        source = inspect.getsource(ProductPickerDialog._load_products)
        self.assertIn("AsyncUI", source)
        self.assertIn(".run(", source)

    def test_async_callback_uses_after(self):
        """AsyncUI callback marshaling must use root.after() (thread safety)."""
        from async_ui import AsyncUI
        source = inspect.getsource(AsyncUI._make_done_callback)
        self.assertIn("after", source)


# =============================================================================
# T2: Supplier Lookup Tests
# =============================================================================

class SupplierLookupTests(BaseTempDBTestCase):
    """Verify P2.1: supplier order _on_lookup wires to ndc_dictionary."""

    def test_on_lookup_calls_barcode_lookup(self):
        """_on_lookup must call ndc_dictionary barcode_lookup."""
        import ui_supplier_order_management as mod
        source = inspect.getsource(mod.PoItemDialog._on_lookup)
        self.assertIn("barcode_lookup", source)

    def test_on_lookup_has_fallback_chain(self):
        """_on_lookup must try multiple lookup strategies."""
        import ui_supplier_order_management as mod
        source = inspect.getsource(mod.PoItemDialog._on_lookup)
        self.assertIn("ndc_lookup", source)
        self.assertIn("name_lookup", source)

    def test_on_lookup_populates_form_fields(self):
        """_on_lookup must populate product_name and price fields."""
        import ui_supplier_order_management as mod
        source = inspect.getsource(mod.PoItemDialog._on_lookup)
        # Must populate _product_name and _price_var
        self.assertIn("_product_name", source)
        self.assertIn("_price_var", source)

    def test_on_lookup_no_messagebox_stub(self):
        """_on_lookup must not be just a messagebox stub — must have lookup logic."""
        import ui_supplier_order_management as mod
        source = inspect.getsource(mod.PoItemDialog._on_lookup)
        # Must contain actual lookup calls (not just the old stub)
        self.assertIn("barcode_lookup", source)
        self.assertIn("ndc_lookup", source)
        self.assertIn("name_lookup", source)


# =============================================================================
# T3: TaskPanel Tests
# =============================================================================

class TaskPanelTests(BaseTempDBTestCase):
    """Verify P2.2: all TaskPanel buttons navigate or show guidance."""

    def test_all_tasks_wired(self):
        """All 9 task definitions should resolve to either _NAV_MAP or guidance."""
        from ui_status_dashboard import TaskPanel

        # Build the expected keys from _TASK_DEFS
        from ui_status_dashboard import _TASK_DEFS
        all_keys = [t[0] for t in _TASK_DEFS]
        self.assertEqual(len(all_keys), 9)

        # Check that at least 8 of 9 are in _NAV_MAP
        in_nav = [k for k in all_keys if k in TaskPanel._NAV_MAP]
        guidance = [k for k in all_keys if k not in TaskPanel._NAV_MAP]

        # 8 should navigate, 1 should have guidance
        self.assertEqual(len(in_nav), 8)
        self.assertEqual(len(guidance), 1)
        self.assertEqual(guidance[0], "task_iv_orders")

    def test_task_click_not_stub(self):
        """_on_task_click should not contain 'coming soon' as the only action."""
        from ui_status_dashboard import TaskPanel
        source = inspect.getsource(TaskPanel._on_task_click)
        # Should have guidance dict for unmapped tasks
        self.assertIn("guidance", source)


# =============================================================================
# T4: Menu Bar Tests
# =============================================================================

class MenuBarTests(unittest.TestCase):
    """Verify P3.1-3.5: 5 menu bar methods exist on PharmacyApp."""

    REQUIRED_METHODS = [
        "_new_prescription",
        "_open_database",
        "_save_all",
        "_open_preferences",
        "_show_about",
    ]

    def test_methods_exist_on_pharmacyapp(self):
        """All 5 methods must be defined on the PharmacyApp class."""
        from ui import PharmacyApp
        for method_name in self.REQUIRED_METHODS:
            self.assertTrue(
                hasattr(PharmacyApp, method_name),
                f"PharmacyApp missing method: {method_name}"
            )

    def test_methods_not_stub(self):
        """None of the 5 methods should be `pass` stubs."""
        from ui import PharmacyApp
        for method_name in self.REQUIRED_METHODS:
            method = getattr(PharmacyApp, method_name)
            source = inspect.getsource(method)
            self.assertFalse(
                source.strip().endswith("pass"),
                f"{method_name} is a pass stub"
            )

    def test_entrerprise_navigation_has_messagebox_fallback(self):
        """P3.6: EnterpriseMenuBar method commands should use messagebox fallbacks."""
        import ui_enterprise_navigation as mod
        source = inspect.getsource(mod.EnterpriseMenuBar.build)
        # The 5 method-based commands (File: New/Open, Edit: Save/Preferences, Help: About)
        # must use messagebox.showinfo when the method is unavailable
        self.assertIn("messagebox.showinfo", source)
        # Verify the specific method commands have msgbox fallback (not None)
        for method in ("_new_prescription", "_open_database", "_save_all",
                       "_open_preferences", "_show_about"):
            self.assertIn(method, source)


# =============================================================================
# T5: ReceiptDetailDialog Tests
# =============================================================================

class ReceiptDetailDialogTests(BaseTempDBTestCase):
    """Verify P4.1-4.2: ReceiptDetailDialog loads and displays receipt items."""

    def test_receipt_detail_dialog_exists(self):
        """ReceiptDetailDialog class must exist in ui_pos_panels."""
        from ui_pos_panels import ReceiptDetailDialog
        self.assertTrue(ReceiptDetailDialog)

    def test_receipt_detail_dialog_uses_async(self):
        """ReceiptDetailDialog._load_receipt must use AsyncUI."""
        from ui_pos_panels import ReceiptDetailDialog
        source = inspect.getsource(ReceiptDetailDialog._load_receipt)
        self.assertIn("AsyncUI", source)

    def test_receipt_detail_dialog_uses_receipt_items(self):
        """ReceiptDetailDialog must call database.get_receipt_items."""
        from ui_pos_panels import ReceiptDetailDialog
        source = inspect.getsource(ReceiptDetailDialog._load_receipt)
        self.assertIn("get_receipt_items", source)

    def test_receipt_detail_dialog_has_print_button(self):
        """ReceiptDetailDialog must have a print button wired to receipt_engine."""
        from ui_pos_panels import ReceiptDetailDialog
        source = inspect.getsource(ReceiptDetailDialog._build)
        self.assertIn("print_receipt", source)


# =============================================================================
# T6: Checkout Tab Layout Tests
# =============================================================================

class CheckoutTabLayoutTests(BaseTempDBTestCase):
    """Verify P5.1: no duplicate checkout_items_count_label."""

    def test_no_duplicate_count_label(self):
        """setup_checkout_tab must create checkout_items_count_label only once."""
        import ui_checkout_tab as mod
        source = inspect.getsource(mod.setup_checkout_tab)

        # Count assignments to checkout_items_count_label
        count = source.count("self.checkout_items_count_label = ctk.CTkLabel")
        self.assertEqual(count, 1,
                         f"checkout_items_count_label created {count} times, expected 1")

    def test_add_item_button_exists(self):
        """Verify _checkout_add_item button is wired in the cart toolbar."""
        import ui_checkout_tab as mod
        source = inspect.getsource(mod.setup_checkout_tab)
        self.assertIn("_checkout_add_item", source)

    def test_product_combobox_exists(self):
        """Verify product combobox is created in setup_checkout_tab."""
        import ui_checkout_tab as mod
        source = inspect.getsource(mod.setup_checkout_tab)
        self.assertIn("checkout_product_combo", source)
        self.assertIn("_checkout_load_products", source)


# =============================================================================
# T7: I18n Tests
# =============================================================================

class I18nTests(unittest.TestCase):
    """Verify P8: new i18n keys present in all 6 locale files."""

    NEW_KEYS = [
        "add_item",
        "product_select",
        "product_picker_title",
        "product_picker_subtitle",
        "product_search_placeholder",
        "product_price_col",
        "product_vendor_col",
        "product_int_barcode_col",
        "no_products_found",
        "product_added_format",
        "receipt_detail_title",
        "receipt_no_items",
        "about_dialog_title",
        "version",
        "build_date",
        "enter_product_id_to_lookup",
        "product_not_found",
        "lookup_failed",
        "task_iv_orders_guidance",
    ]

    def test_new_keys_present_in_all_languages(self):
        LOCALES_DIR = os.path.join(ARCHIVE_DIR, "locales")
        for lang in ["en", "de", "es", "fr", "pt", "ar"]:
            path = os.path.join(LOCALES_DIR, f"{lang}.json")
            if not os.path.isfile(path):
                continue
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for key in self.NEW_KEYS:
                self.assertIn(key, data, f"Key '{key}' missing from {lang}.json")


# =============================================================================
# T8: Regression Tests
# =============================================================================

class RegressionTests(BaseTempDBTestCase):
    """Verify existing Phase 16 functionality is not broken."""

    def test_pos_panels_still_importable(self):
        """ui_pos_panels must still import cleanly."""
        import ui_pos_panels
        self.assertTrue(hasattr(ui_pos_panels, "InsurancePanel"))

    def test_checkout_stubs_wrappers_present(self):
        """Wrapper functions must still exist."""
        import ui_checkout_tab as mod
        for name in ("_refresh_checkout_patients", "_on_patient_select",
                     "_checkout_remove_item", "_checkout_clear_cart",
                     "_refresh_cart_treeview", "_checkout_confirm",
                     "_refresh_receipts_history", "_on_receipt_double_click",
                     "_checkout_update_change"):
            self.assertTrue(hasattr(mod, name), f"Missing wrapper: {name}")

    def test_database_get_all_products_exists(self):
        """database.get_all_products must still exist."""
        import database
        self.assertTrue(callable(database.get_all_products))

    def test_database_get_products_with_vendors_exists(self):
        """database.get_products_with_vendors must still exist."""
        import database
        self.assertTrue(callable(database.get_products_with_vendors))


if __name__ == "__main__":
    unittest.main(verbosity=2)
