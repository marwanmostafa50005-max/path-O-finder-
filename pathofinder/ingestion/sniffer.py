"""File-type sniffing for inbound feed files. Extensions are never trusted.

Recognised shapes:
  - HL7 v2 pipe message  — starts with "MSH|^~\\&|" (possibly MLLP-framed:
    0x0B ... 0x1C 0x0D)
  - HL7 batch            — FHS/BHS envelope; BTS/FTS trailers must be present,
    otherwise the batch is TRUNCATED and must quarantine
  - PIT legacy           — variable-length lines each beginning with a 3-digit
    code + space; line codes ending in '9' are separators
  - PDF                  — %PDF- magic
Anything else → UNKNOWN (quarantine downstream; never silently dropped).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

MLLP_START = b"\x0b"
MLLP_END = b"\x1c"


class FileType(str, Enum):
    HL7 = "hl7"
    HL7_BATCH = "hl7_batch"
    PIT = "pit"
    PDF = "pdf"
    UNKNOWN = "unknown"


@dataclass
class SniffResult:
    file_type: FileType
    messages: list[str] = field(default_factory=list)   # individual HL7 messages
    truncated_batch: bool = False
    notes: list[str] = field(default_factory=list)


_PIT_LINE = re.compile(rb"^\d{3} ")


def strip_mllp(data: bytes) -> bytes:
    if data.startswith(MLLP_START):
        data = data[1:]
        end = data.rfind(MLLP_END)
        if end != -1:
            data = data[:end]
    return data


def _normalise_newlines(text: str) -> str:
    return text.replace("\r\n", "\r").replace("\n", "\r")


def split_batch(text: str) -> tuple[list[str], bool, list[str]]:
    """Split an FHS/BHS…BTS/FTS batch into messages.

    Returns (messages, truncated, notes). HL7AU permits a single batch file
    carrying many messages; BTS/FTS absence ⇒ possible truncation.
    """
    lines = [ln for ln in _normalise_newlines(text).split("\r") if ln.strip()]
    has_fhs = any(ln.startswith("FHS") for ln in lines)
    has_bhs = any(ln.startswith("BHS") for ln in lines)
    has_bts = any(ln.startswith("BTS") for ln in lines)
    has_fts = any(ln.startswith("FTS") for ln in lines)

    truncated = (has_bhs and not has_bts) or (has_fhs and not has_fts)
    notes = []
    if truncated:
        notes.append("batch missing BTS/FTS trailer — possible truncation")

    messages: list[str] = []
    current: list[str] = []
    for ln in lines:
        seg = ln[:3]
        if seg in ("FHS", "BHS", "BTS", "FTS"):
            continue
        if seg == "MSH":
            if current:
                messages.append("\r".join(current))
            current = [ln]
        elif current:
            current.append(ln)
        else:
            notes.append(f"segment before first MSH: {seg}")
    if current:
        messages.append("\r".join(current))
    return messages, truncated, notes


def looks_like_pit(data: bytes) -> bool:
    lines = [ln for ln in data.replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n") if ln.strip()]
    if len(lines) < 2:
        return False
    matching = sum(1 for ln in lines[:20] if _PIT_LINE.match(ln))
    return matching >= max(2, int(0.8 * min(len(lines), 20)))


def sniff(data: bytes) -> SniffResult:
    if data.startswith(b"%PDF-"):
        return SniffResult(FileType.PDF)

    payload = strip_mllp(data)

    head = payload.lstrip()[:8]
    if head.startswith(b"MSH|^~\\&") :
        try:
            text = payload.decode("utf-8", errors="replace")
        except Exception:
            return SniffResult(FileType.UNKNOWN, notes=["undecodable HL7 bytes"])
        return SniffResult(FileType.HL7, messages=[_normalise_newlines(text).strip("\r")])

    if head.startswith(b"FHS") or head.startswith(b"BHS"):
        text = payload.decode("utf-8", errors="replace")
        messages, truncated, notes = split_batch(text)
        return SniffResult(FileType.HL7_BATCH, messages=messages,
                           truncated_batch=truncated, notes=notes)

    if looks_like_pit(payload):
        return SniffResult(FileType.PIT)

    return SniffResult(FileType.UNKNOWN, notes=["unrecognised file shape"])
