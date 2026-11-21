# -*- mode: python ; coding: utf-8 -*-
# PyInstaller build configuration for WorkTrack (versioned on purpose: reproducible builds).
# Build with:  .\build.ps1   (or: .venv\Scripts\pyinstaller WorkTrack.spec --noconfirm --clean)
# Output: dist\WorkTrack\WorkTrack.exe  (one-folder, windowed, no console)

block_cipher = None

excludes = [
    # not used by WorkTrack; keeps the bundle smaller
    "tkinter", "matplotlib", "IPython", "jupyter", "notebook", "scipy", "numba",
    "pytest", "pytestqt", "_pytest", "setuptools", "pip",
    "OpenGL", "pyqtgraph.opengl", "pyqtgraph.examples", "pyqtgraph.jupyter",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
    "PySide6.QtMultimedia", "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtSql", "PySide6.QtNetwork",
]

a = Analysis(
    ["launcher.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WorkTrack",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon="assets/worktrack.ico",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="WorkTrack",
)
