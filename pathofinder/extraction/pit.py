"""PIT legacy-format parser (standalone files and embedded-in-OBX payloads).

PIT: variable-length lines, each starting with a 3-digit code + space.
Line codes ending in '9' are separators. '~' delimits embedded control
commands (e.g. ~FG02~ colour codes) which are stripped for reading but the
raw line is preserved in provenance notes.

PIT reports are semi-structured at best, so extraction here is conservative:
a line must match the strict result pattern (name, number, unit, (range),
optional flag) to yield a value; anything else stays as report text. If no
line can be read with confidence the whole report abstains (check-yourself).
"""

from __future__ import annotations

import re

from .records import ExtractedResult, Provenance, Tier
from .hl7_tier1 import parse_ref_range

_CONTROL = re.compile(r"~[A-Z]{2}\d{0,3}~?")
_LINE = re.compile(r"^(\d{3})[ ](.*)$")

# NAME  VALUE  UNIT  (RANGE)  [FLAG]
_RESULT = re.compile(
    r"^(?P<name>[A-Za-z][A-Za-z0-9 /%\-\+\.]{1,40}?)\s{2,}"
    r"(?P<value>[<>]?=?\s*\d+(?:\.\d+)?)\s+"
    r"(?P<unit>[A-Za-z%][A-Za-z0-9/%\*\^\.]*)\s+"
    r"\((?P<range>[^)]+)\)"
    r"(?:\s+(?P<flag>[A-Z]{1,3}))?\s*$"
)


def parse_pit(text: str, source_note: str = "pit") -> tuple[list[ExtractedResult], list[str]]:
    """Returns (results, report_lines). Unreadable result-looking lines abstain."""
    results: list[ExtractedResult] = []
    report_lines: list[str] = []

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        m = _LINE.match(raw_line.rstrip())
        if not m:
            if raw_line.strip():
                report_lines.append(raw_line.strip())
            continue
        code, body = m.group(1), m.group(2)
        if code.endswith("9"):
            continue  # separator line
        cleaned = _CONTROL.sub("", body).strip()
        if not cleaned:
            continue

        rm = _RESULT.match(cleaned)
        if rm:
            value_str = rm.group("value").replace(" ", "")
            prov = Provenance(tier=Tier.PDF_OCR, engine="pit",
                              segment_path=f"{source_note}:line[{lineno}]")
            res = ExtractedResult(
                analyte_raw=rm.group("name").strip(),
                value_raw=value_str,
                unit_raw=rm.group("unit"),
                ref_range_raw=rm.group("range").strip(),
                lab_abnormal_flag=rm.group("flag"),
                extraction_tier=2,
                confidence=0.9,   # deterministic pattern, but legacy format
                provenance=prov,
            )
            try:
                res.value_num = float(value_str.lstrip("<>="))
            except ValueError:
                res.value_num = None
            res.ref_low, res.ref_high = parse_ref_range(res.ref_range_raw)
            results.append(res)
        else:
            report_lines.append(cleaned)

    return results, report_lines
