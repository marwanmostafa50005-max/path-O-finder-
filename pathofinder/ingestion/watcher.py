"""Watched-folder ingestion: copy-only, sha256, idempotent.

The secure-messaging client (Medical-Objects / HealthLink / Argus / ReferralNet)
writes each inbound message into a practice-local folder. path-O-finder watches
a READ-ONLY COPY of that folder:

  - files are COPIED into the internal inbox working area, never moved;
  - the source folder is never written to, and no HL7 ACK is ever produced;
  - a file whose sha256 was already processed is recorded as status=duplicate
    and skipped, so reprocessing the same feed can never create duplicate flags.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

from ..db.repository import Repository
from . import sniffer


@dataclass
class IngestedFile:
    original_path: Path
    inbox_copy: Path
    sha256: str
    sniff: sniffer.SniffResult
    raw: bytes
    duplicate: bool = False


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def scan_folder(watched: Path, inbox: Path, repo: Repository,
                patterns: tuple[str, ...] = ("*",)) -> list[IngestedFile]:
    """One scan pass over the watched folder. Returns every file found this
    pass, each either new (to be parsed/quarantined) or marked duplicate.
    Never writes to, moves, or deletes anything under `watched`."""
    ingested: list[IngestedFile] = []
    seen_paths: set[Path] = set()
    for pattern in patterns:
        for src in sorted(watched.glob(pattern)):
            if not src.is_file() or src in seen_paths:
                continue
            seen_paths.add(src)
            raw = src.read_bytes()
            digest = sha256_of(raw)

            if repo.message_seen(digest):
                repo.record_message(
                    source_adapter="watcher", original_path=str(src),
                    file_type="duplicate-skip", sha256=digest, status="duplicate",
                )
                ingested.append(IngestedFile(src, Path(), digest,
                                             sniffer.SniffResult(sniffer.FileType.UNKNOWN),
                                             raw, duplicate=True))
                continue

            inbox.mkdir(parents=True, exist_ok=True)
            dest = inbox / f"{digest[:16]}_{src.name}"
            if not dest.exists():
                shutil.copy2(src, dest)  # copy, never move

            ingested.append(IngestedFile(src, dest, digest, sniffer.sniff(raw), raw))
    return ingested
