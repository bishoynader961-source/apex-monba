# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['E:\\my progam pharmacy\\archive\\main_app.py'],
    pathex=[],
    binaries=[('E:\\my progam pharmacy\\archive\\rust_crypto.pyd', '.'), ('E:\\my progam pharmacy\\archive\\hw_client.pyd', '.'), ('E:\\my progam pharmacy\\archive\\barcode_gen.pyd', '.')],
    datas=[('E:\\msys64\\mingw64\\lib\\python3.14\\site-packages\\customtkinter\\assets', 'customtkinter\\assets'), ('E:\\my progam pharmacy\\archive\\config.json', '.'), ('E:\\my progam pharmacy\\archive\\pharmacy.db', '.'), ('E:\\my progam pharmacy\\archive\\licenses.db', '.'), ('E:\\my progam pharmacy\\archive\\locales', 'locales')],
    hiddenimports=['customtkinter', 'requests', 'urllib3', 'ssl', 'http.client', 'database', 'barcode_logic', 'audit_log', 'backup', 'alert_engine', 'license_gate', 'updater', 'receipt_engine', 'path_utils', 'ui', 'ui_helpers', 'ui_modals', 'ui_add_tab', 'ui_inventory_tab', 'ui_expiring_tab', 'ui_dashboard_tab', 'ui_report_tab', 'ui_receive_tab', 'ui_checkout_tab', 'ui_templates_tab', 'ui_settings_tab', 'ui_patients_tab', 'excel_handler', 'pos_engine', 'receipt_template', 'smart_parser', 'auto_extract', 'i18n', 'db', 'barcode_listener', 'crypto_utils', 'async_ui', 'design_system', 'ocr_cascade', 'ocr_engine', 'hw_client', 'native_accel'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PharmacyPro_Enterprise',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PharmacyPro_Enterprise',
)
