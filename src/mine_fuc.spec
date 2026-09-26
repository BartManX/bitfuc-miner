# -*- mode: python ; coding: utf-8 -*-
import os
import sys

root = SPECPATH
libname = "librandomx.dll" if sys.platform.startswith("win") else "librandomx.so"
libpath = os.path.join(root, libname)
if not os.path.isfile(libpath):
    raise SystemExit(f"Missing {libpath} for PyInstaller bundle")

a = Analysis(
    ["mine_fuc.py"],
    pathex=[],
    binaries=[(libpath, ".")],
    datas=[],
    hiddenimports=[],
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
    a.binaries,
    a.datas,
    [],
    name="mine_fuc",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
