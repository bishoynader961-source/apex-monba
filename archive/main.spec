# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas_req, binaries_req, hiddenimports_req = collect_all('requests')
datas_u3, binaries_u3, hiddenimports_u3 = collect_all('urllib3')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries_req + binaries_u3,
    datas=datas_req + datas_u3,
    hiddenimports=[
        'ssl',
        'http.client',
    ] + hiddenimports_req + hiddenimports_u3,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Dev config (must never ship)
        'dev_config',
        'dev_config.json',
        # Server-side scripts (must never ship)
        'license_server',
        'generate_key',
        'test_security',
        'wsgi',
        # Testing frameworks
        'pytest',
        '_pytest',
        'unittest',
        'tkinter.test',
        'test',
        'tests',
        'doctest',
        'pdb',
        'profile',
        'timeit',
        # Dev-only / unnecessary
        'dist_info',
        'pip',
        'setuptools',
        'pkg_resources',
        'wheel',
        'IPython',
        'ipykernel',
        'jupyter',
        'notebook',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='MyPharmacy',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
