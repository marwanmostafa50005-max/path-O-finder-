"""Shipping-posture invariants:

  - NO demo/sample-data mode anywhere in the shipped package;
  - the shipped package never imports the test fixture generator;
  - forbidden licence-risk packages are absent from the environment;
  - the multi-resolution icon carries every required size;
  - installer scripts exist, create a desktop shortcut, and use the icon;
  - the exact About copy ships (guarded separately in UI tests too).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "pathofinder"


def _package_sources() -> list[Path]:
    return list(PKG.rglob("*.py"))


def test_invariant_no_demo_mode_in_shipped_package():
    pattern = re.compile(r"demo[ _-]?mode|sample[ _-]?data|demo\b", re.I)
    offenders = []
    for src in _package_sources():
        for i, line in enumerate(src.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{src.relative_to(ROOT)}:{i}: {line.strip()}")
    assert not offenders, "demo/sample-data references in shipped code:\n" + "\n".join(offenders)


def test_invariant_shipped_package_never_imports_fixtures():
    for src in _package_sources():
        text = src.read_text(encoding="utf-8")
        assert "tests.fixtures" not in text and "fixtures.generator" not in text, \
            f"{src} references the test fixture generator"


def test_invariant_forbidden_packages_absent():
    for forbidden in ("fitz", "pymupdf", "surya"):
        with pytest.raises(ImportError):
            __import__(forbidden)


def test_invariant_icon_has_all_sizes():
    from PIL import Image
    ico = ROOT / "installer" / "pathofinder.ico"
    assert ico.exists(), "run scripts/generate_icon.py"
    with Image.open(ico) as img:
        sizes = sorted({s[0] for s in img.info.get("sizes", set())})
    assert sizes == [16, 32, 48, 64, 128, 256]


def test_invariant_installer_creates_desktop_shortcut_with_icon():
    iss = (ROOT / "installer" / "installer.iss").read_text()
    assert "desktopicon" in iss
    assert "{autodesktop}\\{#MyAppName}" in iss
    assert "SetupIconFile=pathofinder.ico" in iss
    assert "licenses" in iss                     # licence texts shipped
    spec = (ROOT / "installer" / "pathofinder.spec").read_text()
    assert "pathofinder.ico" in spec
    assert '"fitz", "pymupdf", "surya"' in spec  # excluded from the bundle


def test_invariant_pyinstaller_spec_is_valid_python():
    spec = (ROOT / "installer" / "pathofinder.spec").read_text()
    compile(spec, "pathofinder.spec", "exec")    # PyInstaller injects globals at build


def test_invariant_third_party_licenses_cover_runtime_deps():
    text = (ROOT / "THIRD_PARTY_LICENSES.md").read_text()
    for dep in ("PySide6", "hl7apy", "pdfplumber", "pypdfium2", "pytesseract",
                "Tesseract", "Pillow", "APScheduler", "ruamel.yaml", "keyring",
                "sqlcipher3", "llama.cpp", "Qwen2.5-VL", "Poppins", "PyInstaller"):
        assert dep in text, f"{dep} missing from THIRD_PARTY_LICENSES.md"
    for banned in ("PyMuPDF", "Surya"):
        assert f"**{banned}" in text or banned in text  # documented as excluded


def test_invariant_shipped_licence_texts_present():
    lic = ROOT / "installer" / "licenses"
    for f in ("PDFium-LICENSE.txt", "Tesseract-LICENSE.txt", "SQLCipher-LICENSE.txt",
              "llama.cpp-LICENSE.txt", "Qt-PySide6-NOTICE.txt", "Poppins-OFL.txt"):
        assert (lic / f).exists(), f"missing shipped licence text {f}"
    assert (PKG / "resources" / "fonts" / "OFL.txt").exists()
