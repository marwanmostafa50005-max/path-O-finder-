"""INVARIANT: the audit log is immutable and its hash chain verifies.

UPDATE/DELETE on audit_log must fail at the database level; the chain must
verify end-to-end and detect any tampering.
"""

from __future__ import annotations

import sqlite3

import pytest

from pathofinder.db import audit, connection

if connection.HAVE_SQLCIPHER:
    from sqlcipher3 import dbapi2 as _sqlcipher
    DB_ERRORS = (sqlite3.DatabaseError, _sqlcipher.DatabaseError)
else:
    DB_ERRORS = (sqlite3.DatabaseError,)


def _fill(conn):
    audit.append(conn, "MM", "run_started", entity="runs", entity_id=1, after={"mode": "inbox"})
    audit.append(conn, "MM", "disposition", entity="flags", entity_id=7,
                 after={"disposition_type": "handled"})
    audit.append(conn, "RN", "config_edited", entity="config_versions", entity_id=2,
                 before={"v": 1}, after={"v": 2})


def test_invariant_audit_update_forbidden(db):
    _fill(db.conn)
    with pytest.raises(DB_ERRORS, match="append-only"):
        db.conn.execute("UPDATE audit_log SET actor_initials='XX' WHERE audit_id=1")


def test_invariant_audit_delete_forbidden(db):
    _fill(db.conn)
    with pytest.raises(DB_ERRORS, match="append-only"):
        db.conn.execute("DELETE FROM audit_log")


def test_invariant_hash_chain_verifies(db):
    _fill(db.conn)
    ok, detail = audit.verify_chain(db.conn)
    assert ok, detail


def test_invariant_hash_chain_detects_tampering(db):
    _fill(db.conn)
    # Simulate an attacker editing the DB with triggers disabled/bypassed:
    db.conn.execute("DROP TRIGGER audit_log_no_update")
    db.conn.execute("UPDATE audit_log SET after_json='{\"mode\":\"recall\"}' WHERE audit_id=1")
    db.conn.commit()
    ok, detail = audit.verify_chain(db.conn)
    assert not ok
    assert "mismatch" in detail
