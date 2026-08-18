from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from pathofinder.config.loader import ConfigStore
from pathofinder.guidelines import citations
from pathofinder.presentation import queue

NOW = datetime(2026, 8, 18, 8, 0, tzinfo=timezone.utc)


def _flag(**kw) -> dict:
    base = {
        "flag_id": 1, "patient_id": 1, "family_name": "CITIZEN", "given_names": "Jane",
        "dob": "1980-01-01", "severity_tier": "high", "is_check_yourself": 0,
        "confidence": 1.0, "coherence_status": "ok", "analyte_canonical": "potassium",
        "grace_deadline": (NOW + timedelta(hours=24)).isoformat(),
        "result_created_at": (NOW - timedelta(hours=12)).isoformat(),
    }
    base.update(kw)
    return base


def test_ranking_severity_and_elapsed():
    crit_fresh = _flag(flag_id=1, severity_tier="critical")
    high_old = _flag(flag_id=2, severity_tier="high",
                     result_created_at=(NOW - timedelta(days=14)).isoformat())
    border = _flag(flag_id=3, severity_tier="borderline")
    scores = {f["flag_id"]: queue.score_flag(f, NOW) for f in (crit_fresh, high_old, border)}
    assert scores[1] > scores[2] > scores[3]


def test_invariant_check_yourself_always_sinks():
    """INVARIANT: an abstained/low-confidence item NEVER outranks a
    confidently-read abnormal — regardless of severity or age."""
    confident_borderline = _flag(flag_id=1, severity_tier="borderline")
    abstained_critical = _flag(flag_id=2, severity_tier="check_yourself",
                               is_check_yourself=1, confidence=1.0,
                               coherence_status="conflict",
                               result_created_at=(NOW - timedelta(days=400)).isoformat())
    low_conf = _flag(flag_id=3, confidence=0.4)
    s1 = queue.score_flag(confident_borderline, NOW)
    s2 = queue.score_flag(abstained_critical, NOW)
    s3 = queue.score_flag(low_conf, NOW)
    assert s1 > s2 and s1 > s3
    assert s2 < 0 and s3 < 0


def test_queue_groups_per_patient_and_orders():
    flags = [
        _flag(flag_id=1, patient_id=1, severity_tier="borderline"),
        _flag(flag_id=2, patient_id=2, severity_tier="critical", family_name="FAKEMAN"),
        _flag(flag_id=3, patient_id=2, severity_tier="high", family_name="FAKEMAN"),
        _flag(flag_id=4, patient_id=3, severity_tier="check_yourself",
              is_check_yourself=1, family_name="TESTPERSON"),
    ]
    groups = queue.build_queue(flags, NOW)
    assert [g.patient_id for g in groups] == [2, 1, 3]     # check-yourself group last
    assert [f["flag_id"] for f in groups[0].flags] == [2, 3]


def test_citation_only_for_high_confidence_abnormal():
    cmap = citations.CitationMap.default()
    hit = cmap.citation_for(_flag(analyte_canonical="tsh"))
    assert hit is not None
    assert "RACGP" in hit.publisher and "10th edition" in hit.display

    assert cmap.citation_for(_flag(is_check_yourself=1)) is None
    assert cmap.citation_for(_flag(confidence=0.5)) is None
    assert cmap.citation_for(_flag(coherence_status="conflict")) is None
    assert cmap.citation_for(_flag(analyte_canonical="sodium")) is None  # unmapped → nothing


def test_citation_map_validation():
    with pytest.raises(citations.CitationMapError):
        citations.parse_and_validate("entries:\n  - concept: x\n")   # missing fields
    good = citations.load_default_yaml()
    assert citations.parse_and_validate(good)["review_cadence_days"] == 180


def test_citation_review_cadence():
    cmap = citations.CitationMap.default()
    assert not cmap.review_due(NOW, now=NOW + timedelta(days=10))
    assert cmap.review_due(NOW, now=NOW + timedelta(days=181))


def test_config_store_versions_and_rejects_invalid(repo):
    store = ConfigStore(repo)
    assert "DRAFT" in store.get_yaml("grace_matrix")        # seeded from resources

    edited = store.get_yaml("grace_matrix").replace("grace_hours: 24", "grace_hours: 12")
    store.save("grace_matrix", edited, "MM")
    assert "grace_hours: 12" in store.get_yaml("grace_matrix")

    with pytest.raises(Exception):
        store.save("grace_matrix", "defaults: {}", "MM")    # invalid → rejected
    assert "grace_hours: 12" in store.get_yaml("grace_matrix")  # live config untouched

    versions = repo.conn.execute(
        "SELECT count(*) FROM config_versions WHERE cfg_name='grace_matrix'"
    ).fetchone()[0]
    assert versions == 1
    events = [r[0] for r in repo.conn.execute("SELECT event_type FROM audit_log")]
    assert "config_edited" in events


def test_settings_validation(repo):
    store = ConfigStore(repo)
    s = store.get("settings")
    assert s["closed_loop_mode"] == "inbox"
    with pytest.raises(ValueError):
        store.save("settings", "closed_loop_mode: magic\nclosed_loop_strictness: strict\nocr_confidence_gate: 80\nvlm_enabled: auto\n", "MM")
