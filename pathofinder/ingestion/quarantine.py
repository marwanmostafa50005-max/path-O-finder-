"""Quarantine-on-parse-failure.

Anything that cannot be parsed with confidence is recorded (raw bytes retained
inside the encrypted DB), copied to the quarantine folder, audited, and later
surfaced as a "check-yourself" item. NOTHING is ever silently dropped.
"""

from __future__ import annotations

from pathlib import Path

from ..db import audit
from ..db.repository import Repository


def quarantine(repo: Repository, *, source_adapter: str, original_path: str,
               file_type: str, sha256: str, raw: bytes, reason: str,
               quarantine_folder: Path | None = None,
               actor_initials: str = "SYSTEM-FEED") -> int:
    message_id = repo.record_message(
        source_adapter=source_adapter, original_path=original_path,
        file_type=file_type, sha256=sha256, status="quarantined",
        raw_blob=raw, quarantine_reason=reason,
    )
    if quarantine_folder is not None:
        quarantine_folder.mkdir(parents=True, exist_ok=True)
        (quarantine_folder / f"{sha256[:16]}.bin").write_bytes(raw)
    audit.append(repo.conn, actor_initials, "quarantined",
                 entity="messages", entity_id=message_id,
                 after={"reason": reason, "original_path": original_path,
                        "file_type": file_type})
    return message_id
