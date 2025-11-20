"""
Setup script for creating macOS .app bundle using py2app
Usage: python setup.py py2app
"""
from setuptools import setup

APP = ['main.py']
DATA_FILES = [
    ('', ['icon.ico']),
]
OPTIONS = {
    'argv_emulation': False,
    'iconfile': 'icon.ico',
    'codesign_identity': '-',  # Disable code signing
    'plist': {
        'CFBundleName': 'Ninlab',
        'CFBundleDisplayName': 'Ninlab',
        'CFBundleGetInfoString': "Professional Photo Editor",
        'CFBundleIdentifier': "com.ninlab.app",
        'CFBundleVersion': "1.0.0",
        'CFBundleShortVersionString': "1.0.0",
        'NSHumanReadableCopyright': "Copyright © 2025",
        'NSHighResolutionCapable': True,
    },
    'packages': ['PySide6', 'numpy', 'PIL'],
    'includes': ['imaging', 'workers', 'ui_helpers', 'catalog', 'export_dialog', 'cropper'],
}

setup(
    name='Ninlab',
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
