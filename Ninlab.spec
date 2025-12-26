from PyInstaller.utils.hooks import collect_submodules
import os

# Collect all hidden imports
hidden_imports = [
    'imaging', 'workers', 'ui_helpers', 'catalog', 'export_dialog', 
    'cropper', 'curve_widget', 'histogram_widget', 'library_view', 
    'cache_manager', 'rawpy', 'exifread'
]
hidden_imports += collect_submodules('scipy')

# Collect data files
datas = [
    ('icon.ico', '.'),
    ('cb_checked.png', '.'),
    ('cb_unchecked.png', '.'),
]

# Add exiftool if it exists
if os.path.exists('exiftool.exe'):
    datas.append(('exiftool.exe', '.'))

# Add Rust extension if it exists
if os.path.exists('ninlab_core_rs'):
    datas.append(('ninlab_core_rs', 'ninlab_core_rs'))

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
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
    name='Ninlab',
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
    icon=['icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='NinlabApp',
)
app = BUNDLE(
    coll,
    name='Ninlab.app',
    icon='icon.ico',
    bundle_identifier=None,
)
