"""Canonical schema (build brief §5) and hand-rolled forward-only migrations.

All patient-identifying tables live inside the SQLCipher-encrypted DB.
audit_log is append-only: code-level guard (db/audit.py) plus SQLite triggers
that RAISE on UPDATE/DELETE.
"""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 1

_MIGRATION_1 = """
CREATE TABLE patients (
    patient_id          INTEGER PRIMARY KEY,
    source_patient_key  TEXT NOT NULL,
    family_name         TEXT,
    given_names         TEXT,
    dob                 TEXT,
    sex                 TEXT,
    created_at          TEXT NOT NULL,
    UNIQUE (source_patient_key)
);

CREATE TABLE messages (
    message_id          INTEGER PRIMARY KEY,
    source_adapter      TEXT NOT NULL,
    original_path       TEXT NOT NULL,
    file_type           TEXT NOT NULL,          -- hl7|hl7_batch|pit|pdf|unknown
    sha256              TEXT NOT NULL,
    received_at         TEXT NOT NULL,
    processed_at        TEXT,
    status              TEXT NOT NULL CHECK (status IN ('parsed','quarantined','duplicate')),
    quarantine_reason   TEXT,
    raw_blob            BLOB,
    hl7_msh_control_id  TEXT,
    UNIQUE (sha256, status)
);
CREATE INDEX idx_messages_control ON messages (hl7_msh_control_id);

CREATE TABLE orders (
    order_id            INTEGER PRIMARY KEY,
    message_id          INTEGER NOT NULL REFERENCES messages(message_id),
    obr_set_id          TEXT,
    filler_order_number TEXT,
    ordering_provider   TEXT,
    order_status        TEXT,
    collected_at        TEXT,
    reported_at         TEXT,
    panel_code          TEXT,
    panel_name          TEXT
);

CREATE TABLE results (
    result_id           INTEGER PRIMARY KEY,
    order_id            INTEGER NOT NULL REFERENCES orders(order_id),
    patient_id          INTEGER REFERENCES patients(patient_id),
    analyte_raw         TEXT NOT NULL,
    analyte_canonical   TEXT,
    loinc               TEXT,
    value_raw           TEXT,
    value_num           REAL,
    unit_raw            TEXT,
    unit_canonical      TEXT,
    ref_range_raw       TEXT,
    ref_low             REAL,
    ref_high            REAL,
    lab_abnormal_flag   TEXT,                   -- raw OBX-8, repetitions joined with '~'
    obx_value_type      TEXT,
    obx_result_status   TEXT,                   -- F|P|C|X…
    obx_sub_id          TEXT,
    obx_identifier      TEXT,                   -- raw OBX-3 for correction matching
    superseded_by       INTEGER REFERENCES results(result_id),
    extraction_tier     INTEGER NOT NULL CHECK (extraction_tier IN (1,2,3)),
    confidence          REAL,
    provenance_json     TEXT NOT NULL,
    coherence_status    TEXT NOT NULL DEFAULT 'ok' CHECK (coherence_status IN ('ok','conflict')),
    created_at          TEXT NOT NULL
);
CREATE INDEX idx_results_patient_analyte ON results (patient_id, analyte_canonical);

CREATE TABLE flags (
    flag_id             INTEGER PRIMARY KEY,
    result_id           INTEGER NOT NULL REFERENCES results(result_id),
    severity_tier       TEXT NOT NULL,          -- critical|high|borderline|check_yourself
    flag_reason         TEXT NOT NULL,
    is_check_yourself   INTEGER NOT NULL DEFAULT 0,
    grace_deadline      TEXT,
    overdue             INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL,
    UNIQUE (result_id)
);

CREATE TABLE dispositions (
    disposition_id      INTEGER PRIMARY KEY,
    flag_id             INTEGER NOT NULL REFERENCES flags(flag_id),
    operator_initials   TEXT NOT NULL,
    disposition_type    TEXT NOT NULL CHECK (disposition_type IN
        ('handled','watching','not-relevant','escalate','check-done')),
    closed_loop_mode_at_time TEXT NOT NULL,     -- e.g. 'inbox/strict'
    note                TEXT,
    created_at          TEXT NOT NULL
);

CREATE TABLE suppression_memory (
    supp_id             INTEGER PRIMARY KEY,
    patient_id          INTEGER REFERENCES patients(patient_id),
    analyte_canonical   TEXT,
    disposition_id      INTEGER NOT NULL REFERENCES dispositions(disposition_id),
    disposition_type    TEXT NOT NULL,
    scope               TEXT NOT NULL DEFAULT 'this_result',  -- this_result|patient_analyte
    expires_at          TEXT,
    created_by_initials TEXT NOT NULL,
    created_at          TEXT NOT NULL
);

CREATE TABLE runs (
    run_id              INTEGER PRIMARY KEY,
    operator_initials   TEXT NOT NULL,
    started_at          TEXT NOT NULL,
    finished_at         TEXT,
    messages_seen       INTEGER NOT NULL DEFAULT 0,
    flags_built         INTEGER NOT NULL DEFAULT 0,
    mode_settings_json  TEXT
);

CREATE TABLE audit_log (
    audit_id            INTEGER PRIMARY KEY,
    ts                  TEXT NOT NULL,
    actor_initials      TEXT NOT NULL,
    event_type          TEXT NOT NULL,
    entity              TEXT,
    entity_id           TEXT,
    before_json         TEXT,
    after_json          TEXT,
    hash_prev           TEXT NOT NULL,
    hash_self           TEXT NOT NULL
);

CREATE TRIGGER audit_log_no_update BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only: UPDATE forbidden');
END;

CREATE TRIGGER audit_log_no_delete BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only: DELETE forbidden');
END;

CREATE TABLE config_versions (
    cfg_id              INTEGER PRIMARY KEY,
    cfg_name            TEXT NOT NULL,          -- grace_matrix|citation_map|test_aliases|settings
    yaml_blob           TEXT NOT NULL,
    edited_by_initials  TEXT NOT NULL,
    created_at          TEXT NOT NULL
);

CREATE TABLE test_aliases (
    alias_id            INTEGER PRIMARY KEY,
    analyte_raw         TEXT NOT NULL,
    analyte_canonical   TEXT NOT NULL,
    loinc               TEXT,
    created_by_initials TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    UNIQUE (analyte_raw)
);

CREATE TABLE schema_version (version INTEGER NOT NULL);
"""

MIGRATIONS: dict[int, str] = {1: _MIGRATION_1}


def migrate(conn: sqlite3.Connection) -> None:
    """Apply all pending migrations (forward-only)."""
    cur = conn.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='schema_version'"
    )
    if cur.fetchone()[0] == 0:
        current = 0
    else:
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        current = row[0] if row else 0

    for version in sorted(MIGRATIONS):
        if version > current:
            conn.executescript(MIGRATIONS[version])
            conn.execute("DELETE FROM schema_version")
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
            conn.commit()
