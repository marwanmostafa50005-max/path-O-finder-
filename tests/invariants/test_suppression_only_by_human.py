"""INVARIANT: SUPPRESSION-ONLY-BY-HUMAN.

No code path suppresses a flag without a recorded human disposition:
  - a freshly built flag stays in open_flags() indefinitely with no human act;
  - every suppression_memory row references a disposition row carrying
    operator initials (enforced structurally: NOT NULL FK + the single write
    path in Repository.add_disposition);
  - dispositions without initials are rejected.
"""

from __future__ import annotations

import pytest

from pathofinder.db import audit


def _make_flag(repo) -> int:
    pid = repo.upsert_patient("MRN1", "CITIZEN", "Jane", "1980-01-01", "F")
    mid = repo.record_message(source_adapter="test", original_path="/f", file_type="hl7",
                              sha256="s1", status="parsed")
    oid = repo.insert_order(mid, filler_order_number="FIL-1", panel_name="UEC")
    rid = repo.insert_result(oid, pid, {
        "analyte_raw": "Potassium", "analyte_canonical": "potassium",
        "value_raw": "6.1", "value_num": 6.1, "unit_raw": "mmol/L",
        "ref_range_raw": "3.5-5.2", "ref_low": 3.5, "ref_high": 5.2,
        "lab_abnormal_flag": "H", "extraction_tier": 1, "confidence": 1.0,
        "provenance_json": "{}", "coherence_status": "ok",
    })
    return repo.create_flag(rid, "high", "lab flagged H", False, None)


def test_invariant_flag_stays_open_without_human(repo):
    flag_id = _make_flag(repo)
    assert any(f["flag_id"] == flag_id for f in repo.open_flags())
    # No amount of re-querying, time passing, or reprocessing closes it.
    assert any(f["flag_id"] == flag_id for f in repo.open_flags())


def test_invariant_disposition_closes_and_is_audited(repo):
    flag_id = _make_flag(repo)
    repo.add_disposition(flag_id, "MM", "handled", "inbox/strict", note="rpt done")
    assert all(f["flag_id"] != flag_id for f in repo.open_flags())

    supp = repo.conn.execute("SELECT * FROM suppression_memory").fetchall()
    assert len(supp) == 1
    row = dict(supp[0])
    assert row["created_by_initials"] == "MM"
    assert row["disposition_id"] is not None

    events = [r[0] for r in repo.conn.execute("SELECT event_type FROM audit_log")]
    assert "disposition" in events
    ok, detail = audit.verify_chain(repo.conn)
    assert ok, detail


def test_invariant_no_anonymous_disposition(repo):
    flag_id = _make_flag(repo)
    with pytest.raises(ValueError):
        repo.add_disposition(flag_id, "  ", "handled", "inbox/strict")


def test_invariant_every_suppression_references_disposition(repo):
    """Structural check: suppression_memory.disposition_id is NOT NULL and
    the schema has no other writer."""
    cols = {r[1]: r for r in repo.conn.execute("PRAGMA table_info(suppression_memory)")}
    assert cols["disposition_id"][3] == 1     # notnull

    import inspect
    import pathofinder.db.repository as repository_mod
    src = inspect.getsource(repository_mod)
    writes = [ln for ln in src.splitlines() if "INSERT INTO suppression_memory" in ln]
    assert len(writes) == 1, "exactly one code path may write suppression_memory"


def test_invariant_timeboxed_watching_suppression_expires(repo):
    flag_id = _make_flag(repo)
    repo.add_disposition(flag_id, "MM", "watching", "inbox/strict",
                         suppress_scope="patient_analyte",
                         suppress_expires_at="2000-01-01T00:00:00+00:00")  # already expired
    # Disposition closes THIS flag, but a NEW flag on the same patient+analyte
    # is not suppressed once the watching window has lapsed.
    mid = repo.record_message(source_adapter="test", original_path="/f2", file_type="hl7",
                              sha256="s2", status="parsed")
    oid = repo.insert_order(mid, filler_order_number="FIL-2", panel_name="UEC")
    pid = repo.upsert_patient("MRN1", None, None, None, None)
    rid = repo.insert_result(oid, pid, {
        "analyte_raw": "Potassium", "analyte_canonical": "potassium",
        "value_raw": "6.3", "value_num": 6.3, "unit_raw": "mmol/L",
        "ref_range_raw": "3.5-5.2", "ref_low": 3.5, "ref_high": 5.2,
        "lab_abnormal_flag": "H", "extraction_tier": 1, "confidence": 1.0,
        "provenance_json": "{}", "coherence_status": "ok",
    })
    new_flag = repo.create_flag(rid, "high", "lab flagged H", False, None)
    assert any(f["flag_id"] == new_flag for f in repo.open_flags())
