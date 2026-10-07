# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [
    ("assets", "assets"),
    ("tools/httpx.exe", "tools"),
    ("tools/curl.exe", "tools"),
    ("tools/lib/fofa_api.py", "tools/lib"),
    ("tools/lib/domain_icp.py", "tools/lib"),
    ("config.example.json", "."),
]
binaries = []
hiddenimports = ["engine", "openpyxl"]
tmp = collect_all("openpyxl")
datas += tmp[0]
binaries += tmp[1]
hiddenimports += tmp[2]

a = Analysis(
    ["ui.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["numpy", "scipy", "pytest", "PIL", "PySide6", "PyQt5", "matplotlib", "pandas", "IPython"],
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
    name="TwinTitle",
    icon="assets/linshen.ico",
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
