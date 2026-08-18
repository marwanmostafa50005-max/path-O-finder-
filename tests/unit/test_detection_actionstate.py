from __future__ import annotations

from datetime import datetime, timezone

import pytest

from pathofinder.actionstate import closedloop as cl
from pathofinder.detection import flags as flagmod
from pathofinder.detection import grace, severity
from pathofinder.extraction import coherence, hl7_tier1, normalize
from tests.fixtures import generator


def _result(text: str, idx: int = 0):
    res = hl7_tier1.parse_oru(text).orders[0].results[idx]
    normalize.normalize_result(res)
    return coherence.run_coherence(res)


def test_severity_from_lab_flags():
    high = _result(generator.hl7_simple_abnormal())
    tier, reason = severity.classify(high)
    assert tier == "high" and "lab flagged H" in reason

    crit = _result(generator.hl7_multi_obr_all_types())   # Hb LL~A
    tier, reason = severity.classify(crit)
    assert tier == "critical" and "LL" in reason

    normal = _result(generator.hl7_simple_abnormal(), idx=1)
    assert severity.classify(normal)[0] == "none"


def test_severity_no_flag_uses_range_display_only():
    txt = generator.hl7_simple_abnormal().replace("|H|", "||")
    r = _result(txt)
    tier, reason = severity.classify(r)
    assert tier == "borderline"
    assert "outside the lab's stated range" in reason   # never our judgement


def test_severity_abstained_is_check_yourself():
    r = _result(generator.hl7_conflict_impossible_value())
    assert severity.classify(r)[0] == "check_yourself"


def test_grace_matrix_defaults_and_overrides():
    m = grace.GraceMatrix.default()
    assert m.grace_hours("critical", None) == 24
    assert m.grace_hours("critical", "potassium") == 4     # per-analyte override
    assert m.grace_hours("high", "tsh") == 336
    assert m.grace_hours("high", "unknown_analyte") == 72


def test_grace_matrix_validation_rejects_bad_yaml():
    with pytest.raises(grace.GraceMatrixError):
        grace.parse_and_validate("defaults:\n  critical: {}\n")
    with pytest.raises(grace.GraceMatrixError):
        grace.parse_and_validate(
            "defaults:\n  critical: {grace_hours: -5}\n"
            "  high: {grace_hours: 1}\n  borderline: {grace_hours: 1}\n")


def test_flag_building_and_overdue():
    m = grace.GraceMatrix.default()
    r = _result(generator.hl7_simple_abnormal())
    now = datetime(2026, 8, 18, tzinfo=timezone.utc)
    flag = flagmod.build_flag(r, m, "20260810091500", now=now)
    assert flag["severity_tier"] == "high"
    assert not flag["is_check_yourself"]
    assert flag["overdue"]          # 72h grace long past by the 18th

    normal = _result(generator.hl7_simple_abnormal(), idx=1)
    assert flagmod.build_flag(normal, m, "20260810091500", now=now) is None


def test_check_yourself_flag_has_no_deadline():
    m = grace.GraceMatrix.default()
    r = _result(generator.hl7_conflict_unit_mismatch())
    flag = flagmod.build_flag(r, m, "20260810091500")
    assert flag["is_check_yourself"] and flag["grace_deadline"] is None


def test_closed_loop_strict_and_lenient():
    strict = cl.ClosedLoopSettings(cl.Mode.INBOX, cl.Strictness.STRICT)
    lenient = cl.ClosedLoopSettings(cl.Mode.INBOX, cl.Strictness.LENIENT)

    both = cl.LoopEvidence(inbox_actioned=True, recall_exists=True)
    one = cl.LoopEvidence(inbox_actioned=True, recall_exists=False)
    none = cl.LoopEvidence(inbox_actioned=False, recall_exists=False)
    unknown = cl.LoopEvidence()

    assert cl.is_closed(both, strict) == (True, "both conditions met")
    closed, why = cl.is_closed(one, strict)
    assert not closed and "recall" in why
    assert cl.is_closed(one, lenient)[0]
    assert not cl.is_closed(none, lenient)[0]
    assert not cl.is_closed(unknown, strict)[0]   # unknown never counts as closed
    assert not cl.is_closed(unknown, lenient)[0]
