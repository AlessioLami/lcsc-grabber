# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for LCSC Grabber
Builds standalone executable for Windows
"""

import sys
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Get the project root directory
project_root = Path(SPECPATH)

# Collect all submodules
hiddenimports = collect_submodules('lcsc_grabber')
hiddenimports += [
    'wx',
    'wx._xml',
    'wx._html',
    'wx._adv',
    'wx._core',
    'wx._controls',
    'wx.glcanvas',
    'requests',
    'urllib3',
    'certifi',
    'charset_normalizer',
    'idna',
    'OpenGL',
    'OpenGL.GL',
    'OpenGL.GLU',
    'OpenGL.GLUT',
    'OpenGL.platform.win32',
    'numpy',
]

# Platform-specific settings
if sys.platform == 'win32':
    icon_file = str(project_root / 'resources' / 'icon.ico')
    exe_name = 'LCSC-Grabber'
else:
    icon_file = str(project_root / 'resources' / 'icon.png')
    exe_name = 'lcsc-grabber'

# Check if icon exists, use None if not
if not os.path.exists(icon_file):
    icon_file = None

a = Analysis(
    ['main.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        ('resources/icon.png', 'resources'),
        ('resources/metadata.json', 'resources'),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'pandas',
        'scipy',
        'PIL.ImageTk',
        'cv2',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=exe_name,
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
    icon=icon_file,
)
