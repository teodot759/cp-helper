# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for C++ Helper.

From the repository root:

    pyinstaller packaging/cpp-helper.spec --noconfirm

Produces dist/CppHelper/ (onedir, windowed). One-dir starts faster and trips
fewer antivirus heuristics than one-file.

CPPJUDGE_NAME and CPPJUDGE_BRANDING can point at other values, which is how a
fork renames the bundle without touching this file.
"""

from pathlib import Path
import os

block_cipher = None
ROOT = Path(SPECPATH).resolve().parent

NAME = os.environ.get("CPPJUDGE_NAME", "CppHelper")
BRANDING = os.environ.get(
    "CPPJUDGE_BRANDING", str(ROOT / "cppjudge" / "resources" / "branding.json")
)

excludes = [
    "tkinter",
    "unittest",
    "pytest",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtUiTools",
    "PySide6.QtXml",
]

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "cppjudge" / "resources" / "icon.svg"), "cppjudge/resources"),
        (BRANDING, "cppjudge/resources"),
    ],
    hiddenimports=["psutil"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# The PySide6 hook collects every Qt plugin. Most of them pull in whole
# subsystems we never touch: the virtual keyboard plugin needs all of Qt Quick,
# the GTK3 platform theme needs a second copy of ICU (~31 MB), and the PDF image
# plugin needs QtPdf. Drop them and the transitive libraries they dragged in.
_DROP = (
    "PySide6/Qt/translations",
    "PySide6/Qt/qml",
    "PySide6/Qt/plugins/platformthemes",
    "PySide6/Qt/plugins/platforminputcontexts",
    "PySide6/Qt/plugins/imageformats/libqpdf",
    "PySide6/Qt/plugins/tls",
    "PySide6/Qt/plugins/networkinformation",
    "PySide6/Qt/plugins/generic",
    "libqt6network",
    "libcrypto",
    "libssl",
    "libbrotli",
    "libqt6quick",
    "libqt6qml",
    "libqt6virtualkeyboard",
    "libqt6pdf",
    "libqt6eglfs",
    "libqt6wlshell",
    "libgtk-3",
    "libgdk-3",
    "libatk",
    "libatspi",
    "libcairo",
    "libpango",
    "libgdk_pixbuf",
    "libtinysparql",
    "libicuuc.so.78",
    "libicui18n.so.78",
    "libicudata.so.78",
)


def _keep(entry):
    name = entry[0].replace("\\", "/").lower()
    return not any(token.lower() in name for token in _DROP)


a.binaries = [entry for entry in a.binaries if _keep(entry)]
a.datas = [entry for entry in a.datas if _keep(entry)]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=NAME,
)
