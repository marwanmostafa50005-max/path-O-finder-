"""Immutable, hash-chained audit log.

Every run, flag, disposition, quarantine and config change is appended here.
Each row stores hash_self = SHA-256(hash_prev + canonical JSON of the row's
content), so any tampering (even via external tooling) is detectable by
verify_chain(). SQLite triggers additionally forbid UPDATE/DELETE.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone

GENESIS_HASH = "0" * 64


def _canonical(ts: str, actor: str, event_type: str, entity: str | None,
               entity_id: str | None, before_json: str | None,
               after_json: str | None) -> str:
    return json.dumps(
        [ts, actor, event_type, entity, entity_id, before_json, after_json],
        separators=(",", ":"), ensure_ascii=False,
    )


def append(conn: sqlite3.Connection, actor_initials: str, event_type: str,
           entity: str | None = None, entity_id: str | int | None = None,
           before: object = None, after: object = None) -> int:
    """Append one audit event; returns audit_id. Commits."""
    ts = datetime.now(timezone.utc).isoformat()
    before_json = json.dumps(before, sort_keys=True, ensure_ascii=False) if before is not None else None
    after_json = json.dumps(after, sort_keys=True, ensure_ascii=False) if after is not None else None
    eid = str(entity_id) if entity_id is not None else None

    row = conn.execute(
        "SELECT hash_self FROM audit_log ORDER BY audit_id DESC LIMIT 1"
    ).fetchone()
    hash_prev = row[0] if row else GENESIS_HASH

    payload = _canonical(ts, actor_initials, event_type, entity, eid, before_json, after_json)
    hash_self = hashlib.sha256((hash_prev + payload).encode("utf-8")).hexdigest()

    cur = conn.execute(
        "INSERT INTO audit_log (ts, actor_initials, event_type, entity, entity_id,"
        " before_json, after_json, hash_prev, hash_self)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (ts, actor_initials, event_type, entity, eid, before_json, after_json,
         hash_prev, hash_self),
    )
    conn.commit()
    return cur.lastrowid


def verify_chain(conn: sqlite3.Connection) -> tuple[bool, str]:
    """Recompute the whole chain. Returns (ok, detail)."""
    prev = GENESIS_HASH
    for row in conn.execute(
        "SELECT audit_id, ts, actor_initials, event_type, entity, entity_id,"
        " before_json, after_json, hash_prev, hash_self"
        " FROM audit_log ORDER BY audit_id"
    ):
        (audit_id, ts, actor, event_type, entity, entity_id,
         before_json, after_json, hash_prev, hash_self) = row
        if hash_prev != prev:
            return False, f"audit_id {audit_id}: broken link (hash_prev mismatch)"
        payload = _canonical(ts, actor, event_type, entity, entity_id, before_json, after_json)
        expected = hashlib.sha256((hash_prev + payload).encode("utf-8")).hexdigest()
        if expected != hash_self:
            return False, f"audit_id {audit_id}: content hash mismatch"
        prev = hash_self
    return True, "chain intact"
