from __future__ import annotations

from pathlib import Path

import pytest

from pathofinder.ingestion import adapters, sniffer, watcher
from tests.fixtures import generator


@pytest.fixture(scope="session")
def fixtures() -> Path:
    return generator.write_all()


def _read(fixtures: Path, name: str) -> bytes:
    return (fixtures / name).read_bytes()


def test_sniff_hl7(fixtures):
    r = sniffer.sniff(_read(fixtures, "oru_simple_abnormal.hl7"))
    assert r.file_type == sniffer.FileType.HL7
    assert len(r.messages) == 1
    assert r.messages[0].startswith("MSH|")


def test_sniff_mllp_wrapped(fixtures):
    r = sniffer.sniff(_read(fixtures, "mllp_wrapped.hl7"))
    assert r.file_type == sniffer.FileType.HL7
    assert "SYNTH-0015" in r.messages[0]


def test_sniff_batch_splits_messages(fixtures):
    r = sniffer.sniff(_read(fixtures, "oru_batch.hl7"))
    assert r.file_type == sniffer.FileType.HL7_BATCH
    assert len(r.messages) == 2
    assert not r.truncated_batch


def test_sniff_truncated_batch_detected(fixtures):
    r = sniffer.sniff(_read(fixtures, "oru_batch_truncated.hl7"))
    assert r.file_type == sniffer.FileType.HL7_BATCH
    assert r.truncated_batch


def test_sniff_pit(fixtures):
    r = sniffer.sniff(_read(fixtures, "report_legacy.pit"))
    assert r.file_type == sniffer.FileType.PIT


def test_sniff_pdf_and_ignores_extension(fixtures, tmp_path):
    pdf = _read(fixtures, "report_native.pdf")
    disguised = tmp_path / "report.hl7"        # wrong extension on purpose
    disguised.write_bytes(pdf)
    assert sniffer.sniff(disguised.read_bytes()).file_type == sniffer.FileType.PDF


def test_sniff_unknown(fixtures):
    r = sniffer.sniff(_read(fixtures, "not_a_report.xyz"))
    assert r.file_type == sniffer.FileType.UNKNOWN


def test_watcher_copies_never_moves(fixtures, tmp_path, repo):
    watched = tmp_path / "feed"
    watched.mkdir()
    src = watched / "a.hl7"
    src.write_bytes(_read(fixtures, "oru_simple_abnormal.hl7"))
    before = sorted(p.name for p in watched.iterdir())

    out = watcher.scan_folder(watched, tmp_path / "inbox", repo)
    assert sorted(p.name for p in watched.iterdir()) == before  # source untouched
    assert len(out) == 1 and not out[0].duplicate
    assert out[0].inbox_copy.exists()


def test_invariant_idempotent_reprocessing(fixtures, tmp_path, repo):
    """INVARIANT: reprocessing the same feed never re-ingests the same file."""
    watched = tmp_path / "feed"
    watched.mkdir()
    (watched / "a.hl7").write_bytes(_read(fixtures, "oru_simple_abnormal.hl7"))

    first = watcher.scan_folder(watched, tmp_path / "inbox", repo)
    repo.record_message(source_adapter="test", original_path="a.hl7",
                        file_type="hl7", sha256=first[0].sha256, status="parsed")

    second = watcher.scan_folder(watched, tmp_path / "inbox", repo)
    third = watcher.scan_folder(watched, tmp_path / "inbox", repo)
    assert second[0].duplicate and third[0].duplicate
    n = repo.conn.execute(
        "SELECT count(*) FROM messages WHERE sha256=? AND status='duplicate'",
        (first[0].sha256,),
    ).fetchone()[0]
    assert n == 1  # duplicate marker recorded once, not per scan


def test_adapters_registry():
    for name in ("medical-objects", "healthlink", "argus", "referralnet", "generic"):
        a = adapters.get_adapter(name)
        assert a.name == name
        assert a.file_patterns()
    assert adapters.get_adapter("nonexistent").name == "generic"
