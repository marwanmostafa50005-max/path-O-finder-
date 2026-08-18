from __future__ import annotations

import pytest

from pathofinder.db import audit, connection, schema


def test_schema_creates_all_tables(db):
    tables = {
        r[0] for r in db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    expected = {"patients", "messages", "orders", "results", "flags",
                "dispositions", "suppression_memory", "runs", "audit_log",
                "config_versions", "test_aliases", "schema_version"}
    assert expected <= tables


def test_migrate_is_idempotent(db):
    schema.migrate(db.conn)  # second call must not fail or duplicate
    assert db.conn.execute("SELECT version FROM schema_version").fetchone()[0] == schema.SCHEMA_VERSION


@pytest.mark.skipif(not connection.HAVE_SQLCIPHER, reason="sqlcipher3 not installed")
def test_db_file_is_encrypted_at_rest(tmp_path):
    handle = connection.connect(tmp_path / "enc.db", passphrase="pp")
    schema.migrate(handle.conn)
    marker = "SENTINEL-PATIENT-KEY-0123456789"
    handle.conn.execute(
        "INSERT INTO patients (source_patient_key, created_at) VALUES (?, 'now')", (marker,)
    )
    handle.conn.commit()
    handle.conn.close()
    raw = (tmp_path / "enc.db").read_bytes()
    # Plain SQLite files start with this magic; SQLCipher files must not.
    assert not raw.startswith(b"SQLite format 3")
    assert marker.encode() not in raw


@pytest.mark.skipif(not connection.HAVE_SQLCIPHER, reason="sqlcipher3 not installed")
def test_wrong_passphrase_rejected(tmp_path):
    h = connection.connect(tmp_path / "enc.db", passphrase="right")
    schema.migrate(h.conn)
    h.conn.close()
    with pytest.raises(Exception):
        connection.connect(tmp_path / "enc.db", passphrase="wrong")


def test_plain_sqlite_refused_without_escape_hatch(tmp_path, monkeypatch):
    monkeypatch.delenv("PATHOFINDER_ALLOW_PLAIN_SQLITE", raising=False)
    monkeypatch.setattr(connection, "HAVE_SQLCIPHER", False)
    with pytest.raises(connection.EncryptionUnavailableError):
        connection.connect(tmp_path / "x.db")


def test_repository_idempotency_and_patient_upsert(repo):
    pid1 = repo.upsert_patient("SRC1", "CITIZEN", "Jane", "1980-01-01", "F")
    pid2 = repo.upsert_patient("SRC1", "CITIZEN", "Jane", "1980-01-01", "F")
    assert pid1 == pid2
    assert not repo.message_seen("abc123")
    repo.record_message(source_adapter="generic", original_path="/x", file_type="hl7",
                        sha256="abc123", status="parsed", control_id="MSG001")
    assert repo.message_seen("abc123")
    assert repo.message_seen("otherhash", control_id="MSG001")
