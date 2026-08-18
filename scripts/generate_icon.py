#!/usr/bin/env python3
"""Generate the multi-resolution Windows icon from brand/icon_1024.png.

Produces installer/pathofinder.ico containing 16/32/48/64/128/256 px frames.
Run from the repo root:  python scripts/generate_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "brand" / "icon_1024.png"
DEST = ROOT / "installer" / "pathofinder.ico"
SIZES = [16, 32, 48, 64, 128, 256]


def main() -> None:
    img = Image.open(SRC).convert("RGBA")
    DEST.parent.mkdir(parents=True, exist_ok=True)
    img.save(DEST, format="ICO", sizes=[(s, s) for s in SIZES])

    # Verify every frame landed in the file.
    from PIL import IcoImagePlugin  # noqa: F401
    with Image.open(DEST) as ico:
        frames = sorted({s[0] for s in ico.info.get("sizes", set())})
    assert frames == SIZES, f"ico frames {frames} != {SIZES}"
    print(f"wrote {DEST} with sizes {frames}")


if __name__ == "__main__":
    main()
