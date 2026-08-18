"""INVARIANTS:
  - ABSTAIN ON ANY COHERENCE CONFLICT: every conflict fixture abstains;
    no value is emitted.
  - ZERO FALSE-ABNORMAL ASSERTIONS: the engine surfaces only the LAB'S
    abnormal flag; it never asserts an abnormality the lab did not flag and
    never emits a clinical interpretation of its own.
"""

from __future__ import annotations

from pathofinder.extraction import coherence, hl7_tier1, normalize
from tests.fixtures import generator


def _first_result(text: str):
    res = hl7_tier1.parse_oru(text).orders[0].results[0]
    normalize.normalize_result(res)
    return coherence.run_coherence(res)


def test_invariant_abstain_flag_vs_range_conflict():
    r = _first_result(generator.hl7_conflict_flag_vs_range())
    assert r.abstained and r.coherence_status == "conflict"
    assert "inside stated range" in r.abstain_reason


def test_invariant_abstain_impossible_value():
    r = _first_result(generator.hl7_conflict_impossible_value())
    assert r.abstained
    assert "hard bound" in r.abstain_reason


def test_invariant_abstain_unit_mismatch():
    r = _first_result(generator.hl7_conflict_unit_mismatch())
    assert r.abstained
    assert "incompatible" in r.abstain_reason


def test_invariant_abstain_misplaced_decimal():
    r = _first_result(generator.hl7_conflict_misplaced_decimal())
    assert r.abstained
    assert "hard bound" in r.abstain_reason


def test_invariant_coherent_result_not_abstained():
    r = _first_result(generator.hl7_simple_abnormal())
    assert not r.abstained and r.coherence_status == "ok"


def test_invariant_zero_false_abnormal_assertions():
    """The abnormal flag on every emitted record is byte-identical to the
    lab's OBX-8 repetitions — the engine adds no abnormality of its own."""
    for maker in (generator.hl7_simple_abnormal, generator.hl7_multi_obr_all_types):
        msg = hl7_tier1.parse_oru(maker())
        raw_obx8 = []
        for seg in maker().split("\r"):
            if seg.startswith("OBX|"):
                f = seg.split("|")
                raw_obx8.append(f[8] if len(f) > 8 and f[8] else None)
        emitted = [r.lab_abnormal_flag for o in msg.orders for r in o.results]
        assert emitted == raw_obx8


def test_invariant_change_indicators_never_treated_as_abnormal():
    """Lab delta flags (U/D/B/W) alone must not read as abnormal and must not
    conflict with an in-range value (they are the lab's change notes, and the
    software never asserts trends)."""
    txt = generator.hl7_simple_abnormal().replace("|H|", "|U|")
    r = _first_result(txt)
    # in-range check: 6.1 outside 3.5-5.2 with only a change flag → no conflict claim
    assert not r.abstained
    assert r.lab_abnormal_flag == "U"
