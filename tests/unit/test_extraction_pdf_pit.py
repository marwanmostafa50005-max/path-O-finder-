from __future__ import annotations

import pytest

from pathofinder.extraction import pdf_tier2, pit
from tests.fixtures import generator


def test_pit_standalone_extracts_flagged_result():
    results, report_lines = pit.parse_pit(generator.pit_standalone())
    by_name = {r.analyte_raw.upper(): r for r in results}
    assert "POTASSIUM" in by_name
    k = by_name["POTASSIUM"]
    assert (k.value_num, k.unit_raw, k.lab_abnormal_flag) == (6.1, "mmol/L", "H")
    assert (k.ref_low, k.ref_high) == (3.5, 5.2)
    assert k.extraction_tier == 2
    assert "line[" in k.provenance.segment_path
    assert any("good condition" in ln for ln in report_lines)


def test_pit_control_commands_stripped():
    results, _ = pit.parse_pit(generator.pit_standalone())
    assert all("~FG" not in (r.analyte_raw or "") for r in results)


def test_pdf_native_text_layer_with_bboxes():
    ext = pdf_tier2.extract_from_pdf(generator.pdf_native())
    assert not ext.used_ocr and ext.text_found
    by_name = {r.analyte_raw: r for r in ext.results}
    assert "Potassium" in by_name
    k = by_name["Potassium"]
    assert k.value_num == 6.1 and k.lab_abnormal_flag == "H"
    assert k.provenance.page == 1 and len(k.provenance.bboxes) >= 4
    assert k.provenance.engine == "pdfplumber"


@pytest.mark.skipif(not pdf_tier2.tesseract_available(), reason="tesseract not installed")
def test_pdf_scanned_ocr_path():
    ext = pdf_tier2.extract_from_pdf(generator.pdf_scanned("good"))
    assert ext.used_ocr
    names = {r.analyte_raw.lower() for r in ext.results}
    assert "haemoglobin" in names
    hb = next(r for r in ext.results if r.analyte_raw.lower() == "haemoglobin")
    assert hb.value_num == 72 and hb.provenance.engine == "tesseract"
    assert hb.confidence >= 0.80


@pytest.mark.skipif(not pdf_tier2.tesseract_available(), reason="tesseract not installed")
def test_invariant_low_quality_scan_abstains_below_gate():
    """INVARIANT: OCR below the confidence gate never emits a value."""
    ext = pdf_tier2.extract_from_pdf(generator.pdf_scanned("low"))
    assert ext.used_ocr
    assert ext.results == []          # nothing emitted from an unreadable scan
