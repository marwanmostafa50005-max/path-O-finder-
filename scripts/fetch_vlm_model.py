#!/usr/bin/env python3
"""BUILD-TIME fetcher for the Tier-3 model (never runs in the shipped app).

Downloads the Apache-2.0 licensed Qwen2.5-VL-7B-Instruct GGUF (+ mmproj) for
bundling by the Windows build host, or for a practice to install into the
app's models folder. ONLY the 7B-Instruct variant is permitted: the 3B is
research-only and the 72B is MAU-capped (licence red lines).

Usage:
    python scripts/fetch_vlm_model.py --dest installer/vendor/llama/models
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

# Pinned quantisation of the Apache-2.0 7B-Instruct variant (GGUF conversion).
BASE = "https://huggingface.co/ggml-org/Qwen2.5-VL-7B-Instruct-GGUF/resolve/main"
FILES = [
    "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf",
    "mmproj-Qwen2.5-VL-7B-Instruct-f16.gguf",
]
FORBIDDEN_MARKERS = ("3B", "72B")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default="installer/vendor/llama/models")
    args = ap.parse_args()
    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)

    for name in FILES:
        assert not any(m in name for m in FORBIDDEN_MARKERS), \
            "licence red line: only the 7B-Instruct variant is permitted"
        target = dest / name
        if target.exists():
            print(f"already present: {target}")
            continue
        url = f"{BASE}/{name}"
        print(f"downloading {url} …")
        with urllib.request.urlopen(url) as resp, open(target, "wb") as out:
            h = hashlib.sha256()
            while chunk := resp.read(1 << 20):
                out.write(chunk)
                h.update(chunk)
        print(f"  sha256={h.hexdigest()}")
    print("Done. Record the hashes above in the build log.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
