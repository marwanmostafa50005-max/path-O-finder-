"""Canonical extracted-record types with full provenance.

Abstention is first-class: an ExtractedResult either carries a value the
engine is confident in, or `abstained=True` with a reason — never a guess.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum


class Tier(int, Enum):
    HL7 = 1
    PDF_OCR = 2
    VLM = 3


@dataclass
class Provenance:
    """Where a value came from. Tier 1: segment/field path.
    Tier 2/3: page number + pixel bounding boxes."""
    tier: int
    segment_path: str | None = None            # e.g. "OBR[1]/OBX[3]-5"
    page: int | None = None                    # 1-based
    bboxes: list[tuple[float, float, float, float]] = field(default_factory=list)
    engine: str | None = None                  # "hl7apy" | "pdfplumber" | "tesseract" | "qwen2.5-vl-7b"

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))


@dataclass
class ExtractedResult:
    analyte_raw: str
    value_raw: str | None = None
    value_num: float | None = None
    unit_raw: str | None = None
    ref_range_raw: str | None = None
    ref_low: float | None = None
    ref_high: float | None = None
    lab_abnormal_flag: str | None = None       # raw OBX-8, repetitions joined '~'
    loinc: str | None = None
    obx_value_type: str | None = None
    obx_result_status: str | None = None       # F|P|C|X…
    obx_sub_id: str | None = None
    obx_identifier: str | None = None          # raw OBX-3 (correction matching)
    analyte_canonical: str | None = None
    unit_canonical: str | None = None
    extraction_tier: int = 1
    confidence: float = 1.0
    provenance: Provenance | None = None
    coherence_status: str = "ok"               # ok | conflict
    abstained: bool = False
    abstain_reason: str | None = None
    notes: list[str] = field(default_factory=list)

    def abstain(self, reason: str) -> "ExtractedResult":
        self.abstained = True
        self.coherence_status = "conflict"
        self.abstain_reason = reason
        return self

    def db_record(self) -> dict:
        """Row for the results table."""
        return {
            "analyte_raw": self.analyte_raw,
            "analyte_canonical": self.analyte_canonical,
            "loinc": self.loinc,
            "value_raw": self.value_raw,
            "value_num": self.value_num,
            "unit_raw": self.unit_raw,
            "unit_canonical": self.unit_canonical,
            "ref_range_raw": self.ref_range_raw,
            "ref_low": self.ref_low,
            "ref_high": self.ref_high,
            "lab_abnormal_flag": self.lab_abnormal_flag,
            "obx_value_type": self.obx_value_type,
            "obx_result_status": self.obx_result_status,
            "obx_sub_id": self.obx_sub_id,
            "obx_identifier": self.obx_identifier,
            "extraction_tier": self.extraction_tier,
            "confidence": self.confidence,
            "provenance_json": self.provenance.to_json() if self.provenance else "{}",
            "coherence_status": self.coherence_status,
        }


@dataclass
class PatientInfo:
    source_key: str
    family_name: str | None = None
    given_names: str | None = None
    dob: str | None = None
    sex: str | None = None


@dataclass
class OrderInfo:
    obr_set_id: str | None = None
    filler_order_number: str | None = None
    ordering_provider: str | None = None
    order_status: str | None = None
    collected_at: str | None = None
    reported_at: str | None = None
    panel_code: str | None = None
    panel_name: str | None = None
    results: list[ExtractedResult] = field(default_factory=list)
    embedded_documents: list[bytes] = field(default_factory=list)   # e.g. ED PDFs
    embedded_pit: list[str] = field(default_factory=list)


@dataclass
class ParsedMessage:
    control_id: str | None
    patient: PatientInfo | None
    orders: list[OrderInfo] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# HL7 table 0078 abnormal-flag knowledge (recognition only — the flag stays
# the LAB'S assertion; path-O-finder adds no clinical interpretation).
CRITICAL_FLAGS = {"LL", "HH", "LLL", "HHH", "AA"}
ABNORMAL_FLAGS = {"L", "H", "A", "<", ">", "POS", "DET", "RR"}
NORMAL_FLAGS = {"N", "NEG", "ND", "NR"}
# Change indicators are the lab's own delta notes — NEVER treated as a trend
# assertion by this software (TGA red line).
CHANGE_INDICATOR_FLAGS = {"U", "D", "B", "W"}
QUALITATIVE_FLAGS = {"POS", "NEG", "DET", "ND", "RR", "NR", "IND"}
