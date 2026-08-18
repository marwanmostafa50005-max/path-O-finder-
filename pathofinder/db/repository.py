"""Typed data-access layer over the encrypted DB.

Every mutating operation that matters clinically writes an audit event.
Suppression rows are ONLY ever created from an explicit human disposition —
see add_disposition(); there is deliberately no other write path.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from . import audit


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Repository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # -- patients ---------------------------------------------------------

    def upsert_patient(self, source_patient_key: str, family_name: str | None,
                       given_names: str | None, dob: str | None, sex: str | None) -> int:
        row = self.conn.execute(
            "SELECT patient_id FROM patients WHERE source_patient_key=?",
            (source_patient_key,),
        ).fetchone()
        if row:
            return row[0]
        cur = self.conn.execute(
            "INSERT INTO patients (source_patient_key, family_name, given_names,"
            " dob, sex, created_at) VALUES (?,?,?,?,?,?)",
            (source_patient_key, family_name, given_names, dob, sex, _now()),
        )
        self.conn.commit()
        return cur.lastrowid

    # -- messages (idempotency) ------------------------------------------

    def message_seen(self, sha256: str, control_id: str | None = None) -> bool:
        if self.conn.execute(
            "SELECT 1 FROM messages WHERE sha256=? AND status IN ('parsed','quarantined')",
            (sha256,),
        ).fetchone():
            return True
        if control_id:
            return self.conn.execute(
                "SELECT 1 FROM messages WHERE hl7_msh_control_id=? AND status='parsed'",
                (control_id,),
            ).fetchone() is not None
        return False

    def record_message(self, *, source_adapter: str, original_path: str,
                       file_type: str, sha256: str, status: str,
                       raw_blob: bytes | None = None,
                       control_id: str | None = None,
                       quarantine_reason: str | None = None) -> int:
        verb = "INSERT OR IGNORE" if status == "duplicate" else "INSERT"
        cur = self.conn.execute(
            f"{verb} INTO messages (source_adapter, original_path, file_type, sha256,"
            " received_at, processed_at, status, quarantine_reason, raw_blob,"
            " hl7_msh_control_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (source_adapter, original_path, file_type, sha256, _now(),
             _now() if status != "quarantined" else None, status,
             quarantine_reason, raw_blob, control_id),
        )
        self.conn.commit()
        return cur.lastrowid

    # -- orders / results -------------------------------------------------

    def insert_order(self, message_id: int, **fields: Any) -> int:
        cols = ["message_id"] + list(fields.keys())
        vals = [message_id] + list(fields.values())
        cur = self.conn.execute(
            f"INSERT INTO orders ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            vals,
        )
        self.conn.commit()
        return cur.lastrowid

    def insert_result(self, order_id: int, patient_id: int | None, record: dict) -> int:
        fields = dict(record)
        fields["order_id"] = order_id
        fields["patient_id"] = patient_id
        fields.setdefault("created_at", _now())
        cols = list(fields.keys())
        cur = self.conn.execute(
            f"INSERT INTO results ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            [fields[c] for c in cols],
        )
        self.conn.commit()
        return cur.lastrowid

    def find_result_for_correction(self, filler_order_number: str | None,
                                   obx_identifier: str | None,
                                   obx_sub_id: str | None) -> int | None:
        """Locate the prior (non-superseded) result an OBX-11=C corrects,
        matched via filler order number + OBX-3 + OBX-4 sub-id."""
        if not obx_identifier:
            return None
        row = self.conn.execute(
            "SELECT r.result_id FROM results r JOIN orders o ON o.order_id=r.order_id"
            " WHERE o.filler_order_number IS ? AND r.obx_identifier IS ?"
            " AND r.obx_sub_id IS ? AND r.superseded_by IS NULL"
            " ORDER BY r.result_id DESC LIMIT 1",
            (filler_order_number, obx_identifier, obx_sub_id),
        ).fetchone()
        return row[0] if row else None

    def supersede_result(self, old_result_id: int, new_result_id: int,
                         actor_initials: str = "SYSTEM-FEED") -> None:
        before = self.get_result(old_result_id)
        self.conn.execute(
            "UPDATE results SET superseded_by=? WHERE result_id=?",
            (new_result_id, old_result_id),
        )
        self.conn.commit()
        audit.append(self.conn, actor_initials, "result_corrected",
                     entity="results", entity_id=old_result_id,
                     before=before, after={"superseded_by": new_result_id})

    def get_result(self, result_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM results WHERE result_id=?", (result_id,)
        ).fetchone()
        return dict(row) if row else None

    def serial_values(self, patient_id: int, analyte_canonical: str, limit: int = 12) -> list[dict]:
        """Prior values of one analyte for one patient — for DISPLAY ONLY.
        The software never computes or asserts a trend (TGA red line)."""
        rows = self.conn.execute(
            "SELECT result_id, value_raw, value_num, unit_raw, ref_range_raw,"
            " lab_abnormal_flag, created_at FROM results"
            " WHERE patient_id=? AND analyte_canonical=? AND superseded_by IS NULL"
            " ORDER BY created_at DESC LIMIT ?",
            (patient_id, analyte_canonical, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- flags ------------------------------------------------------------

    def create_flag(self, result_id: int, severity_tier: str, flag_reason: str,
                    is_check_yourself: bool, grace_deadline: str | None) -> int:
        existing = self.conn.execute(
            "SELECT flag_id FROM flags WHERE result_id=?", (result_id,)
        ).fetchone()
        if existing:
            return existing[0]
        cur = self.conn.execute(
            "INSERT INTO flags (result_id, severity_tier, flag_reason,"
            " is_check_yourself, grace_deadline, created_at) VALUES (?,?,?,?,?,?)",
            (result_id, severity_tier, flag_reason, int(is_check_yourself),
             grace_deadline, _now()),
        )
        self.conn.commit()
        return cur.lastrowid

    def open_flags(self) -> list[dict]:
        """Flags with no disposition and no active suppression."""
        rows = self.conn.execute(
            """
            SELECT f.*, r.patient_id, r.analyte_raw, r.analyte_canonical, r.value_raw,
                   r.value_num, r.unit_raw, r.ref_range_raw, r.lab_abnormal_flag,
                   r.extraction_tier, r.confidence, r.provenance_json, r.coherence_status,
                   r.obx_result_status, r.created_at AS result_created_at,
                   p.family_name, p.given_names, p.dob, p.sex, o.panel_name, o.reported_at
            FROM flags f
            JOIN results r ON r.result_id = f.result_id
            LEFT JOIN patients p ON p.patient_id = r.patient_id
            JOIN orders o ON o.order_id = r.order_id
            WHERE r.superseded_by IS NULL
              AND NOT EXISTS (SELECT 1 FROM dispositions d WHERE d.flag_id = f.flag_id)
              AND NOT EXISTS (
                    SELECT 1 FROM suppression_memory s
                    WHERE s.scope = 'patient_analyte'
                      AND s.patient_id = r.patient_id
                      AND s.analyte_canonical = r.analyte_canonical
                      AND (s.expires_at IS NULL OR s.expires_at > ?)
              )
            ORDER BY f.flag_id
            """,
            (_now(),),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- dispositions & suppression (the ONLY suppression write path) -----

    def add_disposition(self, flag_id: int, operator_initials: str,
                        disposition_type: str, closed_loop_mode: str,
                        note: str | None = None,
                        suppress_scope: str = "this_result",
                        suppress_expires_at: str | None = None) -> int:
        """Record an explicit human disposition; the software then remembers it
        (suppression_memory). Suppression is ALWAYS the memory of this human
        act — there is no other code path that writes suppression_memory."""
        if not operator_initials or not operator_initials.strip():
            raise ValueError("A disposition requires operator initials — no anonymous sign-off.")
        cur = self.conn.execute(
            "INSERT INTO dispositions (flag_id, operator_initials, disposition_type,"
            " closed_loop_mode_at_time, note, created_at) VALUES (?,?,?,?,?,?)",
            (flag_id, operator_initials, disposition_type, closed_loop_mode,
             note, _now()),
        )
        disposition_id = cur.lastrowid

        row = self.conn.execute(
            "SELECT r.patient_id, r.analyte_canonical FROM flags f"
            " JOIN results r ON r.result_id=f.result_id WHERE f.flag_id=?",
            (flag_id,),
        ).fetchone()
        patient_id, analyte = (row[0], row[1]) if row else (None, None)

        self.conn.execute(
            "INSERT INTO suppression_memory (patient_id, analyte_canonical,"
            " disposition_id, disposition_type, scope, expires_at,"
            " created_by_initials, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (patient_id, analyte, disposition_id, disposition_type,
             suppress_scope, suppress_expires_at, operator_initials, _now()),
        )
        self.conn.commit()
        audit.append(self.conn, operator_initials, "disposition",
                     entity="flags", entity_id=flag_id,
                     after={"disposition_type": disposition_type, "note": note,
                            "scope": suppress_scope, "expires_at": suppress_expires_at,
                            "closed_loop_mode": closed_loop_mode})
        return disposition_id

    # -- runs -------------------------------------------------------------

    def start_run(self, operator_initials: str, mode_settings: dict) -> int:
        if not operator_initials or not operator_initials.strip():
            raise ValueError("Initials sign-on is required before any analysis run.")
        cur = self.conn.execute(
            "INSERT INTO runs (operator_initials, started_at, mode_settings_json)"
            " VALUES (?,?,?)",
            (operator_initials, _now(), json.dumps(mode_settings, sort_keys=True)),
        )
        self.conn.commit()
        run_id = cur.lastrowid
        audit.append(self.conn, operator_initials, "run_started",
                     entity="runs", entity_id=run_id, after=mode_settings)
        return run_id

    def finish_run(self, run_id: int, messages_seen: int, flags_built: int) -> None:
        self.conn.execute(
            "UPDATE runs SET finished_at=?, messages_seen=?, flags_built=?"
            " WHERE run_id=?",
            (_now(), messages_seen, flags_built, run_id),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT operator_initials FROM runs WHERE run_id=?", (run_id,)
        ).fetchone()
        audit.append(self.conn, row[0] if row else "?", "run_finished",
                     entity="runs", entity_id=run_id,
                     after={"messages_seen": messages_seen, "flags_built": flags_built})

    # -- config versions --------------------------------------------------

    def save_config(self, cfg_name: str, yaml_blob: str, initials: str) -> int:
        prev = self.load_config(cfg_name)
        cur = self.conn.execute(
            "INSERT INTO config_versions (cfg_name, yaml_blob, edited_by_initials,"
            " created_at) VALUES (?,?,?,?)",
            (cfg_name, yaml_blob, initials, _now()),
        )
        self.conn.commit()
        audit.append(self.conn, initials, "config_edited", entity="config_versions",
                     entity_id=cur.lastrowid,
                     before={"cfg_name": cfg_name, "yaml": prev},
                     after={"cfg_name": cfg_name, "yaml": yaml_blob})
        return cur.lastrowid

    def load_config(self, cfg_name: str) -> str | None:
        row = self.conn.execute(
            "SELECT yaml_blob FROM config_versions WHERE cfg_name=?"
            " ORDER BY cfg_id DESC LIMIT 1",
            (cfg_name,),
        ).fetchone()
        return row[0] if row else None

    # -- aliases ----------------------------------------------------------

    def add_alias(self, analyte_raw: str, analyte_canonical: str,
                  loinc: str | None, initials: str) -> int:
        cur = self.conn.execute(
            "INSERT OR REPLACE INTO test_aliases (analyte_raw, analyte_canonical,"
            " loinc, created_by_initials, created_at) VALUES (?,?,?,?,?)",
            (analyte_raw, analyte_canonical, loinc, initials, _now()),
        )
        self.conn.commit()
        audit.append(self.conn, initials, "alias_edited", entity="test_aliases",
                     entity_id=cur.lastrowid,
                     after={"raw": analyte_raw, "canonical": analyte_canonical, "loinc": loinc})
        return cur.lastrowid

    def aliases(self) -> dict[str, tuple[str, str | None]]:
        return {
            r[0]: (r[1], r[2])
            for r in self.conn.execute(
                "SELECT analyte_raw, analyte_canonical, loinc FROM test_aliases"
            )
        }
