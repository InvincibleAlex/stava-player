# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[('C:/ProgramData/miniconda/Library/bin/liblzma.dll', '.'), ('C:/ProgramData/miniconda/Library/bin/libbz2.dll', '.'), ('C:/ProgramData/miniconda/Library/bin/ffi.dll', '.'), ('C:/ProgramData/miniconda/Library/bin/libcrypto-3-x64.dll', '.'), ('C:/ProgramData/miniconda/Library/bin/sqlite3.dll', '.')],
    datas=[('icons', 'icons'), ('playlist', 'playlist'), ('player', 'player'), ('libs', 'libs')],
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
    name='Stava Player OneFile',
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
    icon=['icons\\Logo.ico'],
)
