"""Tier 3 — local vision-language model (Qwen2.5-VL-7B-Instruct, Apache-2.0),
served by a bundled llama.cpp llama-server bound to 127.0.0.1. LAST RESORT,
used only when Tiers 1–2 cannot read a page.

Hard constraints (TGA red line iii):
  - READING ONLY. The model reports characters it can point to. It is never
    asked for, and its output is never used as, interpretation, diagnosis,
    or advice.
  - JSON-constrained output (llama.cpp json_schema); non-conforming → discard.
  - Every value MUST carry a grounded bounding box; ungrounded → discard.
  - Multi-pass agreement: two passes with different framings must agree on
    value/unit/range within tolerance, else ABSTAIN.
  - Graceful disable when hardware can't run it: the app is fully functional
    with Tier 3 absent — unreadable items simply go to "check-yourself".

The server is only ever launched against 127.0.0.1 by this process; the
air-gap posture is unaffected (loopback only, no outbound sockets).
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from .hl7_tier1 import parse_ref_range
from .records import ExtractedResult, Provenance, Tier

MIN_RAM_GB = 12.0          # 7B Q4 GGUF + mmproj comfortably
NUMERIC_TOLERANCE = 0.0    # exact agreement required for numbers (strings compared verbatim)

JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "values": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "analyte": {"type": "string"},
                    "value": {"type": "string"},
                    "unit": {"type": "string"},
                    "reference_range": {"type": "string"},
                    "flag": {"type": "string"},
                    "bbox": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 4, "maxItems": 4,
                    },
                },
                "required": ["analyte", "value", "bbox"],
            },
        }
    },
    "required": ["values"],
}

PROMPT_PASS_1 = (
    "You are reading a pathology report image. Transcribe ONLY the test result "
    "lines you can literally see. For each: analyte name, value, unit, reference "
    "range, and the lab's flag if printed. Give the pixel bounding box "
    "[x0,y0,x1,y1] of the printed value. Do NOT interpret, diagnose, or advise. "
    "If you cannot read something clearly, omit it entirely."
)
PROMPT_PASS_2 = (
    "Look at this laboratory report image. List each measurement row exactly as "
    "printed (name, number, unit, range, printed flag) with the bounding box of "
    "the number. Transcription only — omit anything unclear. No commentary."
)


@dataclass
class HardwareStatus:
    capable: bool
    reason: str


def detect_hardware() -> HardwareStatus:
    """Conservative capability check: enough RAM and a llama-server binary."""
    try:
        import os
        page = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
        ram_gb = page / (1024 ** 3)
    except (ValueError, OSError, AttributeError):
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(stat)
            kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            ram_gb = stat.ullTotalPhys / (1024 ** 3)
        except Exception:
            return HardwareStatus(False, "cannot determine system RAM")

    if ram_gb < MIN_RAM_GB:
        return HardwareStatus(False, f"insufficient RAM ({ram_gb:.1f} GB < {MIN_RAM_GB} GB)")
    if not (shutil.which("llama-server") or _bundled_server_path()):
        return HardwareStatus(False, "llama-server binary not found")
    if not _model_path():
        return HardwareStatus(False, "Qwen2.5-VL-7B GGUF model not installed")
    return HardwareStatus(True, "ok")


def _bundled_server_path() -> Path | None:
    import sys
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parents[2]))
    for cand in (base / "vendor" / "llama" / "llama-server.exe",
                 base / "vendor" / "llama" / "llama-server"):
        if cand.exists():
            return cand
    return None


def _model_path() -> Path | None:
    """The main 7B GGUF, never the mmproj companion. Windows globbing is
    case-insensitive and sorts case-insensitively, so a single pattern also
    matches 'mmproj-Qwen2.5-VL-7B-...' and can sort it first — filter it out
    explicitly."""
    from .. import paths
    d = paths.data_dir() / "models"
    if d.exists():
        candidates = {f for f in d.glob("*.gguf")
                      if "qwen2.5-vl-7b" in f.name.lower()
                      and not f.name.lower().startswith("mmproj")}
        for f in sorted(candidates):
            return f
    return None


class VlmClient:
    """HTTP client for the local llama-server (127.0.0.1 only)."""

    def __init__(self, base_url: str = "http://127.0.0.1:8078"):
        if "127.0.0.1" not in base_url and "localhost" not in base_url:
            raise ValueError("Tier-3 VLM must be loopback-only (air-gap posture)")
        self.base_url = base_url.rstrip("/")

    def read_page(self, image_b64_png: str, prompt: str) -> dict | None:
        """One JSON-constrained transcription pass. Returns parsed JSON or None."""
        import urllib.request
        body = json.dumps({
            "temperature": 0,
            "json_schema": JSON_SCHEMA,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{image_b64_png}"}},
                ],
            }],
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions", data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                payload = json.loads(resp.read())
            content = payload["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            if not isinstance(parsed, dict) or "values" not in parsed:
                return None
            return parsed
        except Exception:
            return None


def _key(v: dict) -> str:
    return v.get("analyte", "").strip().lower()


def _agree(a: dict, b: dict) -> bool:
    """Two passes agree when value, unit and range match (numeric values must
    match exactly after parsing; strings compared case-insensitively)."""
    def norm_num(s: str) -> float | None:
        try:
            return float(str(s).strip().lstrip("<>="))
        except ValueError:
            return None

    va, vb = norm_num(a.get("value", "")), norm_num(b.get("value", ""))
    if va is not None and vb is not None:
        if abs(va - vb) > NUMERIC_TOLERANCE:
            return False
    elif str(a.get("value", "")).strip().lower() != str(b.get("value", "")).strip().lower():
        return False
    if str(a.get("unit", "")).strip().lower() != str(b.get("unit", "")).strip().lower():
        return False
    if str(a.get("reference_range", "")).strip() != str(b.get("reference_range", "")).strip():
        return False
    return True


def extract_with_vlm(client: VlmClient, image_b64_png: str, page: int) -> list[ExtractedResult]:
    """Two-pass grounded transcription. Discards ungrounded values; abstains
    (returns nothing for that analyte) on any cross-pass disagreement."""
    pass1 = client.read_page(image_b64_png, PROMPT_PASS_1)
    pass2 = client.read_page(image_b64_png, PROMPT_PASS_2)
    if pass1 is None or pass2 is None:
        return []

    by_key_2 = {_key(v): v for v in pass2.get("values", []) if _key(v)}
    out: list[ExtractedResult] = []
    for v in pass1.get("values", []):
        key = _key(v)
        if not key:
            continue
        bbox = v.get("bbox")
        if (not isinstance(bbox, list) or len(bbox) != 4
                or not all(isinstance(x, (int, float)) for x in bbox)):
            continue  # ungrounded → discard (never emit)
        other = by_key_2.get(key)
        if other is None or not _agree(v, other):
            continue  # cross-pass disagreement → abstain on this analyte
        other_bbox = other.get("bbox")
        if (not isinstance(other_bbox, list) or len(other_bbox) != 4):
            continue  # both passes must ground the value

        res = ExtractedResult(
            analyte_raw=v["analyte"].strip(),
            value_raw=str(v.get("value", "")).strip(),
            unit_raw=(v.get("unit") or "").strip() or None,
            ref_range_raw=(v.get("reference_range") or "").strip() or None,
            lab_abnormal_flag=(v.get("flag") or "").strip() or None,
            extraction_tier=3,
            confidence=0.75,   # capped: VLM reads never outrank deterministic tiers
            provenance=Provenance(tier=Tier.VLM, engine="qwen2.5-vl-7b-instruct",
                                  page=page, bboxes=[tuple(bbox)]),
        )
        try:
            res.value_num = float(res.value_raw.lstrip("<>="))
        except ValueError:
            res.value_num = None
        res.ref_low, res.ref_high = parse_ref_range(res.ref_range_raw)
        out.append(res)
    return out
