"""Regression tests for Windows-specific divergences found by the
cross-platform audit (all runnable on Linux via simulation)."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from pathofinder.db import connection
from pathofinder.ingestion import watcher
from tests.fixtures import generator


# -- watcher: locked/in-flight files must not abort the scan pass ------------

def test_locked_file_skipped_and_retried_next_pass(tmp_path, repo, monkeypatch):
    """Windows sharing violations (secure-messaging client / AV holding a
    file) raise PermissionError from read_bytes. One locked file must not
    kill the pass, and the file must be retried once released."""
    watched = tmp_path / "feed"
    watched.mkdir()
    (watched / "a.hl7").write_bytes(generator.hl7_simple_abnormal().encode())
    locked = watched / "b.hl7"
    locked.write_bytes(generator.hl7_batch().encode())

    real_read = Path.read_bytes

    def flaky_read(self):
        if self.name == "b.hl7":
            raise PermissionError(32, "The process cannot access the file "
                                      "because it is being used by another process")
        return real_read(self)

    monkeypatch.setattr(Path, "read_bytes", flaky_read)
    skipped: list[str] = []
    out = watcher.scan_folder(watched, tmp_path / "inbox", repo, skipped=skipped)
    assert [f.original_path.name for f in out] == ["a.hl7"]
    assert len(skipped) == 1 and "b.hl7" in skipped[0] and "retry" in skipped[0]

    monkeypatch.setattr(Path, "read_bytes", real_read)   # file released
    repo.record_message(source_adapter="t", original_path="a", file_type="hl7",
                        sha256=out[0].sha256, status="parsed")
    retry = watcher.scan_folder(watched, tmp_path / "inbox", repo)
    names = {f.original_path.name: f for f in retry}
    assert not names["b.hl7"].duplicate            # picked up fresh, nothing lost
    assert names["a.hl7"].duplicate


def test_os_metadata_files_ignored(tmp_path, repo):
    watched = tmp_path / "feed"
    watched.mkdir()
    (watched / "a.hl7").write_bytes(generator.hl7_simple_abnormal().encode())
    for junk in ("desktop.ini", "Thumbs.db", "~$report.docx", ".DS_Store"):
        (watched / junk).write_bytes(b"shell metadata")
    out = watcher.scan_folder(watched, tmp_path / "inbox", repo)
    assert [f.original_path.name for f in out] == ["a.hl7"]


def test_inbox_copy_name_capped_for_max_path(tmp_path, repo):
    watched = tmp_path / "feed"
    watched.mkdir()
    long_name = "x" * 200 + ".hl7"
    (watched / long_name).write_bytes(generator.hl7_simple_abnormal().encode())
    out = watcher.scan_folder(watched, tmp_path / "inbox", repo)
    assert len(out[0].inbox_copy.name) <= 17 + watcher.MAX_COPY_NAME_STEM


# -- settings: Windows paths must survive YAML round-trip --------------------

def test_settings_yaml_roundtrips_windows_paths(repo):
    """A typed/pasted backslash path must save and load intact (the old
    hand-built double-quoted scalar treated backslash as a YAML escape)."""
    from ruamel.yaml import YAML

    from pathofinder.config.loader import ConfigStore

    store = ConfigStore(repo)
    win_path = r"C:\Users\reception\HLINK\ffprod"
    data = {
        "watched_folder": win_path, "source_adapter": "healthlink",
        "closed_loop_mode": "inbox", "closed_loop_strictness": "strict",
        "ocr_confidence_gate": 80, "vlm_enabled": "auto",
        "overnight_build_hour": 5,
    }
    buf = io.StringIO()
    YAML().dump(data, buf)                      # same serialiser the UI uses
    store.save("settings", buf.getvalue(), "MM")
    assert store.get("settings")["watched_folder"] == win_path

    unc = r"\\PRACTICE-SVR\feeds\inbound"
    data["watched_folder"] = unc
    buf = io.StringIO()
    YAML().dump(data, buf)
    store.save("settings", buf.getvalue(), "MM")
    assert store.get("settings")["watched_folder"] == unc


# -- DB key: machine-scope blob logic (DPAPI stubbed on Linux) ---------------

def test_machine_passphrase_blob_roundtrip_and_legacy_migration(tmp_path, monkeypatch):
    """The practice-wide DB uses a machine-scope DPAPI blob beside the DB so
    every local Windows account opens the same DB; a legacy per-user keyring
    passphrase migrates into the blob. DPAPI itself is stubbed reversibly."""
    monkeypatch.setattr(connection, "_dpapi",
                        lambda data, protect: bytes(b ^ 0x5A for b in data))

    db_path = tmp_path / "pathofinder.db"
    p1 = connection._windows_machine_passphrase(db_path)
    assert (tmp_path / "pathofinder.keyblob").exists()
    p2 = connection._windows_machine_passphrase(db_path)   # second account
    assert p1 == p2

    # Legacy migration: keyring value wins when no blob exists yet.
    blob2 = tmp_path / "other.db"
    import sys
    import types
    fake_keyring = types.SimpleNamespace(
        get_password=lambda *a: "legacy-pass", set_password=lambda *a: None)
    monkeypatch.setitem(sys.modules, "keyring", fake_keyring)
    assert connection._windows_machine_passphrase(blob2) == "legacy-pass"
    assert connection._windows_machine_passphrase(blob2) == "legacy-pass"


def test_serial_values_deterministic_on_timestamp_ties(repo):
    """Windows CPython <=3.12 has ~15.6ms clock granularity: results inserted
    in one pass share byte-identical created_at strings, and SQLite tie order
    is unspecified. The serial-values panel (display-only, clinician eyeballs
    trends) must still show newest-first via the result_id tie-breaker."""
    pid = repo.upsert_patient("MRN9", "TIE", "Case", "1970-01-01", "F")
    mid = repo.record_message(source_adapter="t", original_path="/t", file_type="hl7",
                              sha256="tie1", status="parsed")
    oid = repo.insert_order(mid, filler_order_number="FIL-T", panel_name="UEC")
    same_ts = "2026-08-20T01:02:03+00:00"          # identical, as on Windows
    for val in (5.1, 5.5, 6.1):                     # inserted oldest → newest
        repo.insert_result(oid, pid, {
            "analyte_raw": "Potassium", "analyte_canonical": "potassium",
            "value_raw": str(val), "value_num": val, "unit_raw": "mmol/L",
            "lab_abnormal_flag": "H", "extraction_tier": 1, "confidence": 1.0,
            "provenance_json": "{}", "coherence_status": "ok",
            "created_at": same_ts,
        })
    series = repo.serial_values(pid, "potassium")
    assert [r["value_num"] for r in series] == [6.1, 5.5, 5.1]  # newest first


def test_tesseract_probe_covers_windows_install_locations(monkeypatch, tmp_path):
    """The standard Windows Tesseract installer does not add itself to PATH;
    the probe must cover the conventional install roots."""
    from pathofinder.extraction import pdf_tier2
    monkeypatch.setenv("ProgramFiles", r"C:\Program Files")
    monkeypatch.setenv("ProgramFiles(x86)", r"C:\Program Files (x86)")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\x\AppData\Local")
    cands = [str(c) for c in pdf_tier2._windows_install_candidates()]
    assert any(c.startswith(r"C:\Program Files") and c.endswith("tesseract.exe")
               for c in cands)
    assert any("AppData" in c and "Programs" in c for c in cands)


def test_build_script_hard_gates_missing_ocr_bundle():
    """A vendor-less Windows build must FAIL, not warn-and-ship: the OCR tests
    are skip-gated, so nothing else in the chain would catch a build whose
    scanned-report tier is silently dead."""
    ps1 = (Path(__file__).resolve().parents[2] / "installer"
           / "build_windows.ps1").read_text(encoding="utf-8")
    assert "param([switch]$AllowNoOcr)" in ps1
    assert "throw" in ps1 and "vendor\\tesseract\\tesseract.exe missing" in ps1


def test_vlm_model_path_never_selects_mmproj(tmp_path, monkeypatch, data_dir):
    from pathofinder.extraction import vlm_tier3
    models = Path(data_dir) / "models"
    models.mkdir(parents=True)
    (models / "mmproj-Qwen2.5-VL-7B-Instruct-f16.gguf").write_bytes(b"x")
    assert vlm_tier3._model_path() is None      # companion alone is not a model
    (models / "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf").write_bytes(b"x")
    assert vlm_tier3._model_path().name == "Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf"
