# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = [('accounts', 'accounts'), ('accounts_config.json', '.'), ('ozon_accounts_config.json', '.'), ('ozon_auth.json', '.'), ('C:\\Users\\ASUS\\AppData\\Local\\ms-playwright\\chromium-1187', 'ms-playwright\\chromium-1187'), ('C:\\Users\\ASUS\\AppData\\Local\\ms-playwright\\ffmpeg-1011', 'ms-playwright\\ffmpeg-1011')]
datas += collect_data_files('playwright_stealth')


a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=datas,
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
    name='app',
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
    icon=['icon.ico'],
)
