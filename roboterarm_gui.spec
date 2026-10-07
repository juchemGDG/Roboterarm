# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules
from pathlib import Path
import sys

project_root = Path(SPECPATH)

block_cipher = None


added_files = [
    (str(project_root / "README.md"), "."),
]

for child in (project_root / "assets").glob("logo.png"):
    added_files.append((str(child), "assets"))

for child in (project_root / "esp32_bridge").iterdir():
    if child.is_file():
        added_files.append((str(child), "esp32_bridge"))


a = Analysis(
    ['roboterarm_gui.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=added_files,
    hiddenimports=collect_submodules('mpremote') + collect_submodules('serial'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RoboterarmSteuerung',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(project_root / 'assets' / 'icon.ico') if sys.platform == 'win32' else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='RoboterarmSteuerung',
)
app = BUNDLE(
    coll,
    name='RoboterarmSteuerung.app',
    icon=str(project_root / 'assets' / 'icon.icns'),
    bundle_identifier='de.schule.roboterarm',
)
