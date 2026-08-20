"""Tier 2 — deterministic PDF reading: native text layer first (pdfplumber,
with per-word bounding boxes), then confidence-gated Tesseract OCR over a
pypdfium2 rasterisation for scanned pages.

GOVERNING RULE: abstain when unsure. A value is only emitted when the line it
came from matches the strict result pattern AND (for OCR) every word on that
line meets the confidence gate (default 80). Anything else becomes a
check-yourself abstention carried by the caller.

Provenance for every value = page number + pixel bounding box(es).
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path

from .hl7_tier1 import parse_ref_range
from .records import ExtractedResult, Provenance, Tier

DEFAULT_OCR_CONFIDENCE_GATE = 80.0
OCR_DPI = 300

# NAME  VALUE  UNIT  RANGE  [FLAG]  — table-style report line
_RESULT_LINE = re.compile(
    r"^(?P<name>[A-Za-z][A-Za-z0-9 /%\-\+\.]{1,40}?)\s{1,}"
    r"(?P<value>[<>]?=?\d+(?:\.\d+)?)\s+"
    r"(?P<unit>[A-Za-z%][A-Za-z0-9/%\*\^\.]*)\s+"
    r"\(?\s*(?P<range>[<>]?=?\s*\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?)?)\s*\)?"
    r"(?:\s+(?P<flag>[A-Z]{1,3}|LOW|HIGH))?\s*$"
)

_FLAG_WORDS = {"LOW": "L", "HIGH": "H"}


@dataclass
class PageText:
    page: int                     # 1-based
    words: list[dict]             # {text, x0, top, x1, bottom, conf}
    source: str                   # "native" | "ocr"


def _lines_from_words(words: list[dict], y_tol: float = 3.0) -> list[list[dict]]:
    """Group words into visual lines by vertical MIDPOINT, with a tolerance
    proportional to glyph height. Grouping by word top breaks on proportional
    fonts: tokens with ascender/descender extremes (e.g. 'g/L') get taller
    boxes with different tops and split onto phantom lines, so a readable
    line silently fails the result pattern (recall loss, found via OCR
    fixtures rendered in the bundled proportional font)."""
    def _mid(w: dict) -> float:
        return (w["top"] + w["bottom"]) / 2

    def _h(w: dict) -> float:
        return max(1.0, w["bottom"] - w["top"])

    lines: list[dict] = []
    for w in sorted(words, key=lambda w: (_mid(w), w["x0"])):
        placed = False
        for line in lines:
            tol = max(y_tol, 0.6 * max(_h(w), line["h"]))
            if abs(line["mid"] - _mid(w)) <= tol:
                line["words"].append(w)
                n = len(line["words"])
                line["mid"] += (_mid(w) - line["mid"]) / n   # running mean
                line["h"] = max(line["h"], _h(w))
                placed = True
                break
        if not placed:
            lines.append({"words": [w], "mid": _mid(w), "h": _h(w)})
    for line in lines:
        line["words"].sort(key=lambda w: w["x0"])
    lines.sort(key=lambda l: l["mid"])
    return [line["words"] for line in lines]


def native_pages(pdf_bytes: bytes) -> list[PageText]:
    import pdfplumber
    pages: list[PageText] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            words = [
                {"text": w["text"], "x0": w["x0"], "top": w["top"],
                 "x1": w["x1"], "bottom": w["bottom"], "conf": 100.0}
                for w in page.extract_words()
            ]
            pages.append(PageText(page=i, words=words, source="native"))
    return pages


def _windows_install_candidates() -> list[Path]:
    """Conventional Windows install locations. The standard Tesseract
    installer (UB Mannheim) does NOT add tesseract.exe to PATH, so a
    practice that installed it manually would otherwise never be found."""
    import os
    roots: list[str] = []
    for env in ("ProgramFiles", "ProgramFiles(x86)"):
        val = os.environ.get(env)
        if val:
            roots.append(val)
    lad = os.environ.get("LOCALAPPDATA")
    if lad:
        roots.append(str(Path(lad) / "Programs"))
    return [Path(r) / "Tesseract-OCR" / "tesseract.exe" for r in roots]


def _tesseract_cmd() -> str | None:
    """Bundled engine first (PyInstaller vendor dir), then PATH, then the
    conventional Windows install locations."""
    import shutil
    import sys
    base = getattr(sys, "_MEIPASS", None)
    if base:
        for name in ("tesseract.exe", "tesseract"):
            cand = Path(base) / "vendor" / "tesseract" / name
            if cand.exists():
                return str(cand)
    which = shutil.which("tesseract")
    if which:
        return which
    if sys.platform == "win32":
        for cand in _windows_install_candidates():
            if cand.exists():
                return str(cand)
    return None


def tesseract_available() -> bool:
    return _tesseract_cmd() is not None


def ocr_pages(pdf_bytes: bytes) -> list[PageText]:
    import pypdfium2 as pdfium
    import pytesseract

    cmd = _tesseract_cmd()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd

    pages: list[PageText] = []
    doc = pdfium.PdfDocument(pdf_bytes)
    try:
        for i in range(len(doc)):
            bitmap = doc[i].render(scale=OCR_DPI / 72)
            pil = bitmap.to_pil()
            data = pytesseract.image_to_data(
                pil, output_type=pytesseract.Output.DICT, config="--psm 6")
            words = []
            for j, txt in enumerate(data["text"]):
                if not txt.strip():
                    continue
                conf = float(data["conf"][j])
                if conf < 0:
                    continue
                words.append({
                    "text": txt, "conf": conf,
                    "x0": float(data["left"][j]), "top": float(data["top"][j]),
                    "x1": float(data["left"][j] + data["width"][j]),
                    "bottom": float(data["top"][j] + data["height"][j]),
                })
            pages.append(PageText(page=i + 1, words=words, source="ocr"))
    finally:
        doc.close()
    return pages


@dataclass
class PdfExtraction:
    results: list[ExtractedResult]
    abstentions: list[str]        # reasons for lines that looked like results but failed gates
    used_ocr: bool
    text_found: bool


def extract_from_pdf(pdf_bytes: bytes,
                     ocr_confidence_gate: float = DEFAULT_OCR_CONFIDENCE_GATE,
                     y_tol: float = 6.0) -> PdfExtraction:
    pages = native_pages(pdf_bytes)
    used_ocr = False
    if sum(len(p.words) for p in pages) < 5:      # no usable text layer → scan
        if not tesseract_available():
            return PdfExtraction([], ["scanned PDF and Tesseract unavailable"], False, False)
        pages = ocr_pages(pdf_bytes)
        used_ocr = True

    results: list[ExtractedResult] = []
    abstentions: list[str] = []
    text_found = any(p.words for p in pages)

    for page in pages:
        for line_words in _lines_from_words(page.words, y_tol=y_tol):
            line_text = " ".join(w["text"] for w in line_words)
            m = _RESULT_LINE.match(line_text.strip())
            if not m:
                continue

            if page.source == "ocr":
                min_conf = min(w["conf"] for w in line_words)
                if min_conf < ocr_confidence_gate:
                    abstentions.append(
                        f"page {page.page}: OCR confidence {min_conf:.0f} below gate "
                        f"{ocr_confidence_gate:.0f} for line '{line_text[:60]}'")
                    continue
                confidence = min_conf / 100.0
            else:
                confidence = 0.95   # native text layer, deterministic pattern

            bboxes = [(w["x0"], w["top"], w["x1"], w["bottom"]) for w in line_words]
            flag = m.group("flag")
            flag = _FLAG_WORDS.get(flag, flag) if flag else None
            res = ExtractedResult(
                analyte_raw=m.group("name").strip(),
                value_raw=m.group("value"),
                unit_raw=m.group("unit"),
                ref_range_raw=m.group("range").strip(),
                lab_abnormal_flag=flag,
                extraction_tier=2,
                confidence=confidence,
                provenance=Provenance(
                    tier=Tier.PDF_OCR,
                    engine="tesseract" if page.source == "ocr" else "pdfplumber",
                    page=page.page, bboxes=bboxes),
            )
            try:
                res.value_num = float(m.group("value").lstrip("<>="))
            except ValueError:
                res.value_num = None
            res.ref_low, res.ref_high = parse_ref_range(res.ref_range_raw)
            results.append(res)

    return PdfExtraction(results, abstentions, used_ocr, text_found)
