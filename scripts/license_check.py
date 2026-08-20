#!/usr/bin/env python3
"""Build-time licence gate for path-O-finder.

Fails (exit 1) if any installed dependency reports an AGPL / GPL / copyleft /
revenue-capped licence, or if a forbidden package is present at all.

Run inside the build venv:  python scripts/license_check.py
Requires: pip-licenses (dev dependency).
"""

from __future__ import annotations

import json
import subprocess
import sys

# Packages that must never appear, regardless of what licence they report.
FORBIDDEN_PACKAGES = {
    "pymupdf",          # AGPL-3.0 (Artifex dual licence)
    "fitz",
    "frontend",         # bogus package pulled by old fitz shim
    "surya-ocr",        # weights revenue-capped (AI-Pubs Open-RAIL-M)
    "surya",
}

# Licence substrings that fail the build. GPL is checked with carve-outs for
# LGPL (dynamic linking is permitted) and historical dual-licence strings.
FORBIDDEN_LICENSE_TOKENS = [
    "agpl",
    "affero",
    "sspl",
    "commons clause",
    "rail",            # Open-RAIL / BigScience RAIL variants
    "cc-by-nc",
    "noncommercial",
    "non-commercial",
]

# Packages allowed despite a "GPL" substring match, with the reason recorded.
GPL_ALLOWLIST = {
    "pyinstaller": "GPL with bundling exception — output not GPL-affected",
    "pyinstaller-hooks-contrib": "same PyInstaller exception",
    "pyside6": "LGPL-3.0, dynamically linked",
    "pyside6-addons": "LGPL-3.0, dynamically linked",
    "pyside6-essentials": "LGPL-3.0, dynamically linked",
    "shiboken6": "LGPL-3.0, dynamically linked",
    "chardet": "LGPL-2.1, dynamically linked (pure python import)",
}


def main() -> int:
    out = subprocess.run(
        [sys.executable, "-m", "piplicenses", "--format=json", "--with-system"],
        capture_output=True, check=True,
        encoding="utf-8", errors="replace",   # Windows locale default is cp1252
    ).stdout
    rows = json.loads(out)
    failures: list[str] = []

    for row in rows:
        name = row["Name"].lower()
        lic = (row.get("License") or "").lower()

        if name in FORBIDDEN_PACKAGES:
            failures.append(f"FORBIDDEN PACKAGE PRESENT: {row['Name']} ({row.get('License')})")
            continue

        for token in FORBIDDEN_LICENSE_TOKENS:
            if token in lic:
                failures.append(f"{row['Name']}: forbidden licence '{row.get('License')}'")
                break
        else:
            if "gpl" in lic and "lgpl" not in lic and name not in GPL_ALLOWLIST:
                failures.append(f"{row['Name']}: GPL-family licence '{row.get('License')}' not allow-listed")

    if failures:
        print("LICENCE CHECK FAILED:")
        for f in failures:
            print("  -", f)
        return 1

    print(f"Licence check passed: {len(rows)} packages, no AGPL/GPL/copyleft/revenue-capped deps.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
