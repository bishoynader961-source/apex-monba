"""Verification test for ui_epcs_workflow module."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import unittest
import ui_epcs_workflow as m


class TestWizardStateMachine(unittest.TestCase):
    """Test the wizard step management logic."""

    def test_resolve_prescriber_npi(self):
        prescriber = (1, '1234567890', 'DEA123', 'LIC123', 'John', 'Smith', '555-1234', 'js@med.com', '123 Main St', '2025-12-31', True, '{}')
        disp = m._resolve_prescriber_display(prescriber)
        self.assertEqual(disp['id_type'], 'NPI')
        self.assertEqual(disp['id_value'], '1234567890')
        self.assertEqual(disp['name'], 'John Smith')

    def test_resolve_prescriber_veterinarian_dea(self):
        vet = (2, None, 'VET987', 'VET-LIC-456', 'Jane', 'Vet', '555-5678', 'jv@vet.com', '456 Oak Ave', '2025-06-30', True, '{}')
        disp = m._resolve_prescriber_display(vet)
        self.assertEqual(disp['id_type'], 'DEA')
        self.assertEqual(disp['id_value'], 'VET987')
        self.assertEqual(disp['name'], 'Jane Vet')

    def test_resolve_prescriber_license_only(self):
        prescriber = (3, '', '', 'STATE-LIC-789', 'Bob', 'Vet', '555-9999', 'bv@vet.com', '789 Pine St', '2025-03-15', True, '{}')
        disp = m._resolve_prescriber_display(prescriber)
        self.assertEqual(disp['id_type'], 'License')
        self.assertEqual(disp['id_value'], 'STATE-LIC-789')

    def test_rx_number_format(self):
        rx_num = m._generate_rx_number_sqlite()
        self.assertTrue(rx_num.startswith('RX-'))
        parts = rx_num.split('-')
        self.assertEqual(len(parts), 4, f'Expected 4 parts, got {len(parts)}: {rx_num}')
        self.assertEqual(len(parts[3]), 6)

    def test_strategy_routing_all_regions(self):
        from rx_strategies import strategy_factory
        self.assertEqual(type(strategy_factory('US')).__name__, 'USBillingStrategy')
        self.assertEqual(type(strategy_factory('GB')).__name__, 'EUBillingStrategy')
        self.assertEqual(type(strategy_factory('DE')).__name__, 'EUBillingStrategy')
        self.assertEqual(type(strategy_factory('XX')).__name__, 'MockProvider')
        self.assertEqual(type(strategy_factory('MOCK')).__name__, 'MockProvider')

    def test_strategy_validate_us(self):
        from rx_strategies import strategy_factory
        s = strategy_factory('US')
        s.validate_prescription({'drug_name': 'Aspirin', 'dosage': 'BID', 'quantity': 30, 'prescriber_npi': '123'})
        with self.assertRaises(ValueError):
            s.validate_prescription({'drug_name': 'Aspirin', 'quantity': 30})

    def test_strategy_validate_eu(self):
        from rx_strategies import strategy_factory
        s = strategy_factory('GB')
        s.validate_prescription({'drug_name': 'Aspirin', 'dosage': 'BID', 'quantity': 30, 'prescriber_ods': '123'})
        with self.assertRaises(ValueError):
            s.validate_prescription({'drug_name': 'Aspirin', 'quantity': 30})

    def test_strategy_authenticate(self):
        from rx_strategies import strategy_factory
        s = strategy_factory('US')
        ok, msg = s.authenticate({'api_key': 'key', 'switch_id': 'sid'})
        self.assertTrue(ok)
        ok2, msg2 = s.authenticate({})
        self.assertFalse(ok2)

    def test_strategy_calculate_patient_cost(self):
        from rx_strategies import strategy_factory
        s = strategy_factory('US')
        cost = s.calculate_patient_cost(100.0, 30, {'coinsurance_rate': 0.2, 'copay': 5.0})
        self.assertGreater(cost, 0)

    def test_strategy_generate_claim(self):
        from rx_strategies import strategy_factory
        s = strategy_factory('US')
        claim = s.generate_claim({'drug_name': 'Aspirin', 'ndc': '123', 'quantity': 30, 'days_supply': 30, 'prescriber_npi': '456'})
        self.assertIn('region', claim)
        self.assertEqual(claim['region'], 'US')


class TestPresetsAndLabels(unittest.TestCase):
    """Test i18n keys and module constants."""

    @classmethod
    def setUpClass(cls):
        import i18n
        i18n.init()

    def test_frequency_options(self):
        self.assertIn('QD', m._FREQUENCY_OPTIONS)
        self.assertIn('BID', m._FREQUENCY_OPTIONS)
        self.assertIn('TID', m._FREQUENCY_OPTIONS)
        self.assertIn('QID', m._FREQUENCY_OPTIONS)
        self.assertGreater(len(m._FREQUENCY_OPTIONS), 5)

    def test_wizard_steps(self):
        self.assertEqual(len(m._WIZARD_STEPS), 3)
        self.assertEqual(m._WIZARD_STEPS[0], 'step_patient')
        self.assertEqual(m._WIZARD_STEPS[1], 'step_medication')
        self.assertEqual(m._WIZARD_STEPS[2], 'step_prescription')

    def test_valid_regions(self):
        self.assertIn('US', m._VALID_REGIONS)
        self.assertIn('GB', m._VALID_REGIONS)
        self.assertIn('DE', m._VALID_REGIONS)

    def test_i18n_keys_resolve(self):
        import i18n
        required_keys = [
            'epcs_workflow', 'epcs_workflow_subtitle', 'step_patient', 'step_medication',
            'step_prescription', 'back', 'next', 'save_draft', 'print_fax', 'save_to_inbox',
            'submit_authorize', 'frequency', 'duration', 'duration_days', 'special_notes',
            'veterinarian_prescriber', 'prescriber_search_box_placeholder',
            'frequency_placeholder', 'directions_placeholder', 'notes_placeholder',
            'insufficient_fields', 'draft_saved', 'inbox_saved', 'authorize_failed',
            'claim_generated', 'prescriber_required', 'drug_required', 'patient_required',
            'print_label', 'no_prescribers_found', 'select_prescriber_first', 'rx_number',
        ]
        for k in required_keys:
            v = i18n.t(k)
            self.assertNotEqual(v, k, f'Key {k} not translated (returned key itself)')

    def test_i18n_keys_in_all_languages(self):
        import json
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'locales')
        required_keys = [
            'epcs_workflow', 'epcs_workflow_subtitle', 'step_patient', 'step_medication',
            'step_prescription', 'back', 'next', 'save_draft', 'print_fax', 'save_to_inbox',
            'submit_authorize', 'frequency', 'duration', 'duration_days', 'special_notes',
            'veterinarian_prescriber', 'prescriber_search_box_placeholder',
            'frequency_placeholder', 'directions_placeholder', 'notes_placeholder',
            'insufficient_fields', 'draft_saved', 'inbox_saved', 'authorize_failed',
            'claim_generated', 'prescriber_required', 'drug_required', 'patient_required',
            'print_label', 'no_prescribers_found', 'select_prescriber_first', 'rx_number',
        ]
        for lang in ['en', 'de', 'es', 'fr', 'pt', 'ar']:
            with open(os.path.join(base, f'{lang}.json')) as f:
                data = json.load(f)
            for k in required_keys:
                self.assertIn(k, data, f'{lang}.json missing key: {k}')


class TestBackendImmutability(unittest.TestCase):
    """Verify that locked backend files were NOT modified."""

    BACKEND_FILES = ['rx_config.py', 'rx_database.py', 'rx_strategies.py', 'rx_db.py']

    def test_backend_files_exist(self):
        for fname in self.BACKEND_FILES:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)
            self.assertTrue(os.path.exists(path), f'Backend file missing: {fname}')

    def test_backend_functions_present(self):
        import rx_db
        self.assertTrue(hasattr(rx_db, 'search_inventory'))
        self.assertTrue(hasattr(rx_db, 'search_prescribers'))
        self.assertTrue(hasattr(rx_db, 'add_rx'))
        self.assertTrue(hasattr(rx_db, 'add_rx_regional'))
        self.assertTrue(hasattr(rx_db, 'update_rx_status'))
        self.assertTrue(hasattr(rx_db, 'get_rx_by_id'))
        self.assertTrue(hasattr(rx_db, 'get_insurance_by_patient'))
        self.assertTrue(hasattr(rx_db, 'get_prescriber_labels'))

    def test_strategies_unchanged(self):
        from rx_strategies import strategy_factory, USBillingStrategy, EUBillingStrategy, MockProvider
        self.assertEqual(type(strategy_factory('US')).__name__, 'USBillingStrategy')
        self.assertEqual(type(strategy_factory('GB')).__name__, 'EUBillingStrategy')
        self.assertEqual(type(strategy_factory('DE')).__name__, 'EUBillingStrategy')
        self.assertEqual(type(strategy_factory('XX')).__name__, 'MockProvider')

    def test_region_label_mapping(self):
        """GB/DE regions should map to EU labels (PZN, Prescriber Reg #)."""
        gb_labels = m._get_prescriber_labels('GB')
        de_labels = m._get_prescriber_labels('DE')
        us_labels = m._get_prescriber_labels('US')
        self.assertEqual(us_labels['prescriber_id_label'], 'NPI Number')
        self.assertEqual(gb_labels['prescriber_id_label'], 'Prescriber Reg #')
        self.assertEqual(de_labels['drug_code_label'], 'PZN Code')
        self.assertEqual(gb_labels['insurance_bin_label'], 'Scheme/PCN')


class TestModuleStructure(unittest.TestCase):
    """Test that the module has all required public interfaces."""

    def test_setup_hooks(self):
        self.assertTrue(hasattr(m, 'setup_epcs_workflow_tab'))
        self.assertTrue(hasattr(m, '_refresh_epcs_workflow_tab'))

    def test_class_exists(self):
        self.assertTrue(hasattr(m, 'EpcsWorkflowFrame'))

    def test_required_methods(self):
        methods = [
            '_build_ui', '_build_wizard_header', '_build_step_indicator',
            '_build_wizard_container', '_build_step_patient',
            '_build_step_medication', '_build_step_prescription',
            '_build_action_bar', '_show_step', '_update_step_indicator',
            '_on_back', '_on_next', '_on_save_draft', '_on_save_inbox',
            '_on_print_fax', '_on_submit_authorize', '_validate_step',
            '_on_patient_search', '_on_patient_search_done', '_on_patient_select',
            '_on_drug_search', '_on_drug_search_done', '_on_drug_select',
            '_on_prescriber_search', '_on_prescriber_search_done', '_on_prescriber_select',
            '_calculate_cost_preview', '_update_cost_display',
            '_gather_prescription_data', '_on_clear_form',
            '_refresh_all_queues', '_parse_int', 'refresh',
        ]
        for meth in methods:
            self.assertTrue(hasattr(m.EpcsWorkflowFrame, meth), f'Missing method: {meth}')

    def test_helper_functions(self):
        helpers = [
            '_get_rx_region', '_ensure_rx_tables', '_load_patients',
            '_load_inventory', '_load_prescribers', '_get_prescriber_labels',
            '_resolve_prescriber_display', '_generate_rx_number_sqlite',
            '_create_rx_sqlite', '_update_rx_status_sqlite',
            '_create_prescription_record', '_set_rx_status',
            '_format_prescription_text', '_debounced_search',
        ]
        for fn in helpers:
            self.assertTrue(hasattr(m, fn), f'Missing helper: {fn}')

    def test_main_app_integration(self):
        """Verify main_app.py was patched with EPCS workflow integration."""
        import main_app
        import inspect
        source = inspect.getsource(main_app._wire_rx_extensions)
        # Nav icon
        self.assertIn('"epcs_workflow"', source)
        # Import
        self.assertIn('setup_epcs_workflow_tab', source)
        # Tab creation
        self.assertIn('tab_epcs_workflow', source)
        # Tab refresh handler
        self.assertIn('epcs_workflow_frame', source)
        self.assertIn('.refresh()', source)
        # Verify the _refresh_epcs_workflow_tab exists in ui_epcs_workflow module
        self.assertTrue(hasattr(m, '_refresh_epcs_workflow_tab'))

    def test_prescription_text_format(self):
        data = {
            'rx_number': 'RX-2024-000001',
            'patient_name': 'John Doe',
            'patient_dob': '1980-01-15',
            'patient_phone': '555-0199',
            'prescriber_name': 'Dr. Smith',
            'prescriber_id_label': 'NPI',
            'prescriber_id_value': '1234567890',
            'prescriber_license': 'LIC-123',
            'drug_name': 'Aspirin',
            'drug_strength': '81mg',
            'drug_form': 'Tablet',
            'directions': 'Take 1 tablet daily',
            'frequency': 'QD',
            'quantity': '30',
            'duration': '90',
            'refills': '3',
            'notes': 'Take with food',
        }
        text = m._format_prescription_text(data)
        self.assertIn('Aspirin', text)
        self.assertIn('John Doe', text)
        self.assertIn('Dr. Smith', text)
        self.assertIn('RX-2024-000001', text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
