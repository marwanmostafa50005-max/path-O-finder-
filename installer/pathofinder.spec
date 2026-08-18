# PyInstaller spec for path-O-finder (Windows x64 build host).
# Build:  pyinstaller installer/pathofinder.spec --noconfirm
# (run from the repo root, inside the build venv)

import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent

datas = [
    (str(ROOT / "pathofinder" / "resources"), "pathofinder/resources"),
]

# Bundled Tesseract engine + traineddata (place under installer/vendor/tesseract
# on the build host — see build_windows.ps1). Bundled llama-server likewise.
vendor = ROOT / "installer" / "vendor"
binaries = []
if (vendor / "tesseract").exists():
    datas.append((str(vendor / "tesseract"), "vendor/tesseract"))
if (vendor / "llama").exists():
    datas.append((str(vendor / "llama"), "vendor/llama"))

a = Analysis(
    [str(ROOT / "pathofinder" / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        "sqlcipher3", "keyring.backends.Windows",
        "apscheduler.triggers.cron",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Licence hygiene + size: never bundle these.
        "fitz", "pymupdf", "surya", "tkinter", "matplotlib", "numpy.f2py",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="path-O-finder",
    icon=str(ROOT / "installer" / "pathofinder.ico"),
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="path-O-finder",
)
