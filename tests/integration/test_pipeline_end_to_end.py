from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pathofinder.config.loader import ConfigStore
from pathofinder.pipeline import Pipeline
from pathofinder.presentation import queue
from tests.fixtures import generator


@pytest.fixture()
def feed(tmp_path, data_dir) -> Path:
    """A watched folder populated with the full fixture spread."""
    src = generator.write_all()
    folder = tmp_path / "feed"
    folder.mkdir()
    for f in src.iterdir():
        shutil.copy2(f, folder / f.name)
    return folder


def test_end_to_end_run(feed, repo):
    pipe = Pipeline(repo)
    report = pipe.run("MM", watched_folder=feed)

    assert report.files_seen == 19
    assert report.messages_parsed > 0
    assert report.quarantined >= 3       # malformed, truncated batch, junk file
    assert report.flags_built > 0
    assert report.corrections_applied == 1

    # NEVER-DROP invariant at pipeline level: every non-duplicate file is
    # accounted for as parsed or quarantined.
    n_msgs = repo.conn.execute(
        "SELECT count(DISTINCT sha256) FROM messages WHERE status IN ('parsed','quarantined')"
    ).fetchone()[0]
    # batch files add per-message rows beyond their file-level marker row
    assert n_msgs >= report.files_seen - report.duplicates

    # Run is initials-gated and recorded.
    run = dict(repo.conn.execute("SELECT * FROM runs").fetchone())
    assert run["operator_initials"] == "MM" and run["finished_at"]


def test_invariant_never_drop(feed, repo):
    """INVARIANT: every input file ends up parsed OR quarantined — nothing
    silently lost."""
    Pipeline(repo).run("MM", watched_folder=feed)
    statuses = {}
    for src in feed.iterdir():
        raw = src.read_bytes()
        import hashlib
        digest = hashlib.sha256(raw).hexdigest()
        row = repo.conn.execute(
            "SELECT status FROM messages WHERE sha256=? AND status IN ('parsed','quarantined')",
            (digest,),
        ).fetchone()
        statuses[src.name] = row[0] if row else None
    missing = [n for n, s in statuses.items() if s is None]
    assert not missing, f"files silently dropped: {missing}"


def test_invariant_idempotent_rerun_no_duplicate_flags(feed, repo):
    """INVARIANT: reprocessing the same feed produces no duplicate flags."""
    pipe = Pipeline(repo)
    first = pipe.run("MM", watched_folder=feed)
    flags_after_first = repo.conn.execute("SELECT count(*) FROM flags").fetchone()[0]

    second = Pipeline(repo).run("MM", watched_folder=feed)
    flags_after_second = repo.conn.execute("SELECT count(*) FROM flags").fetchone()[0]

    assert second.duplicates == first.files_seen
    assert second.flags_built == 0
    assert flags_after_second == flags_after_first


def test_invariant_correction_supersedes_and_preserves_original(feed, repo):
    """INVARIANT: OBX-11=C supersedes the prior value and preserves the
    original in the audit trail."""
    Pipeline(repo).run("MM", watched_folder=feed)

    rows = repo.conn.execute(
        "SELECT value_num, obx_result_status, superseded_by FROM results"
        " WHERE analyte_canonical='potassium' AND value_num IN (5.9, 4.9)"
        " ORDER BY value_num DESC"
    ).fetchall()
    by_status = {r[1]: r for r in rows}
    assert by_status["P"][2] is not None      # preliminary superseded…
    assert by_status["C"][2] is None          # …by the correction

    audits = repo.conn.execute(
        "SELECT before_json FROM audit_log WHERE event_type='result_corrected'"
    ).fetchall()
    assert len(audits) == 1 and "5.9" in audits[0][0]

    # Superseded result's flag never reaches the queue.
    open_ids = {f["result_id"] for f in repo.open_flags()}
    superseded_id = repo.conn.execute(
        "SELECT result_id FROM results WHERE superseded_by IS NOT NULL"
    ).fetchone()[0]
    assert superseded_id not in open_ids


def test_queue_contents_after_run(feed, repo):
    Pipeline(repo).run("MM", watched_folder=feed)
    groups = queue.build_queue(repo.open_flags())
    assert groups

    # Confident abnormals present, and every conflict fixture surfaced as
    # check-yourself at the bottom.
    all_flags = [f for g in groups for f in g.flags]
    tiers = {f["severity_tier"] for f in all_flags}
    assert "critical" in tiers or "high" in tiers
    check_items = [f for f in all_flags if f["is_check_yourself"]]
    assert len(check_items) >= 4              # 4 coherence-conflict fixtures

    scores = [f["_score"] for f in all_flags]
    confident_min = min((f["_score"] for f in all_flags if not f["is_check_yourself"]),
                        default=None)
    check_max = max((f["_score"] for f in check_items), default=None)
    if confident_min is not None and check_max is not None:
        assert check_max < confident_min

    # Quarantined files surface as check-yourself queue entries via messages
    # table (UI shows them from quarantine view); flags for parsed conflicts
    # already verified above.


def test_grace_matrix_config_version_used(feed, repo):
    """An edited grace matrix (stored via ConfigStore) drives the next run."""
    store = ConfigStore(repo)
    edited = store.get_yaml("grace_matrix").replace(
        "critical:   { grace_hours: 24 }", "critical:   { grace_hours: 1 }")
    store.save("grace_matrix", edited, "MM")

    pipe = Pipeline(repo)
    assert pipe.matrix.grace_hours("critical", None) == 1
