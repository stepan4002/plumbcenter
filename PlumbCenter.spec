# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = ['keyring.backends.Windows']
hiddenimports += collect_submodules('plumbcenter')
tmp_ret = collect_all('PySide6')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['C:\\Users\\nikos\\Desktop\\work\\07 Tools and Automations\\plumbnote OPEN SOUSRCE REPOS\\plumbcenter\\.worktrees\\exe\\packaging\\launch_gui.py'],
    pathex=['C:\\Users\\nikos\\Desktop\\work\\07 Tools and Automations\\plumbnote OPEN SOUSRCE REPOS\\plumbcenter\\.worktrees\\exe'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    name='PlumbCenter',
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
    version='C:\\Users\\nikos\\Desktop\\work\\07 Tools and Automations\\plumbnote OPEN SOUSRCE REPOS\\plumbcenter\\.worktrees\\exe\\packaging\\version_info.txt',
    icon=['C:\\Users\\nikos\\Desktop\\work\\07 Tools and Automations\\plumbnote OPEN SOUSRCE REPOS\\plumbcenter\\.worktrees\\exe\\assets\\plumbcenter.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PlumbCenter',
)
