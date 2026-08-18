from __future__ import annotations

import pytest

from pathofinder.extraction import hl7_tier1, normalize
from pathofinder.ingestion import sniffer
from tests.fixtures import generator


def _parse(text: str):
    return hl7_tier1.parse_oru(text)


def test_simple_abnormal_parses_with_provenance():
    msg = _parse(generator.hl7_simple_abnormal())
    assert msg.control_id == "SYNTH-0001"
    assert msg.patient.family_name == "CITIZEN"
    (order,) = msg.orders
    k, na = order.results
    assert (k.analyte_raw, k.value_num, k.unit_raw) == ("Potassium", 6.1, "mmol/L")
    assert (k.ref_low, k.ref_high) == (3.5, 5.2)
    assert k.lab_abnormal_flag == "H"
    assert k.loinc == "2823-3"
    assert k.provenance.segment_path == "OBR[1]/OBX[1]-5"
    assert na.lab_abnormal_flag == "N"
    assert "haemolysed" in " ".join(na.notes)  # NTE attaches to preceding OBX


def test_all_obx_value_types_and_repeating_flags():
    msg = _parse(generator.hl7_multi_obr_all_types())
    assert len(msg.orders) == 2
    fbc, misc = msg.orders
    hb, wcc, plt_note = fbc.results
    assert hb.lab_abnormal_flag == "LL~A"          # repeating OBX-8 preserved
    assert wcc.obx_value_type == "SN"
    assert wcc.value_raw == "<0.5" and wcc.value_num == 0.5
    assert plt_note.obx_value_type == "ST"

    types = [r.obx_value_type for r in misc.results]
    assert types == ["TX", "FT", "CE", "CWE", "RP"]
    ce = misc.results[2]
    assert ce.value_raw == "Positive" and ce.lab_abnormal_flag == "POS~A"


def test_embedded_pdf_extracted():
    msg = _parse(generator.hl7_embedded_pdf())
    (order,) = msg.orders
    assert len(order.embedded_documents) == 1
    assert order.embedded_documents[0].startswith(b"%PDF-")


def test_embedded_pit_routed():
    msg = _parse(generator.hl7_with_embedded_pit())
    (order,) = msg.orders
    assert len(order.embedded_pit) == 1
    assert "POTASSIUM" in order.embedded_pit[0]


def test_preliminary_and_correction_statuses():
    prelim_txt, corr_txt = generator.hl7_preliminary_then_correction()
    prelim = _parse(prelim_txt).orders[0].results[0]
    corr = _parse(corr_txt).orders[0].results[0]
    assert prelim.obx_result_status == "P"
    assert corr.obx_result_status == "C"
    assert prelim.obx_identifier == corr.obx_identifier
    assert prelim.obx_sub_id == corr.obx_sub_id == "1"


def test_malformed_message_raises_parse_failure():
    with pytest.raises(hl7_tier1.ParseFailure):
        _parse(generator.hl7_malformed())


def test_nm_with_nonnumeric_value_abstains():
    bad = generator.hl7_simple_abnormal().replace("|6.1|", "|six point one|")
    res = _parse(bad).orders[0].results[0]
    assert res.abstained and res.coherence_status == "conflict"


def test_batch_messages_parse_individually():
    sr = sniffer.sniff(generator.hl7_batch().encode())
    parsed = [_parse(m) for m in sr.messages]
    assert [p.control_id for p in parsed] == ["SYNTH-0006", "SYNTH-0007"]


def test_ref_range_forms():
    f = hl7_tier1.parse_ref_range
    assert f("3.5-5.2") == (3.5, 5.2)
    assert f("< 5") == (None, 5.0)
    assert f("<=1.0") == (None, 1.0)
    assert f(">10") == (10.0, None)
    assert f("negative") == (None, None)


def test_normalisation_seed_and_local_aliases():
    msg = _parse(generator.hl7_simple_abnormal())
    k = normalize.normalize_result(msg.orders[0].results[0])
    assert k.analyte_canonical == "potassium"

    from pathofinder.extraction.records import ExtractedResult
    odd = ExtractedResult(analyte_raw="Kalium (serum)")
    normalize.normalize_result(odd)
    assert odd.analyte_canonical is None            # never guessed
    assert any("clinician review" in n for n in odd.notes)

    normalize.normalize_result(odd, local_aliases={"Kalium (serum)": ("potassium", "2823-3")})
    assert odd.analyte_canonical == "potassium"     # clinician alias wins
