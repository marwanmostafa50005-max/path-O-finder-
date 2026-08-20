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


# OS shell metadata that appears in Windows folders but is never lab data.
# Skipped by exact name/prefix only — anything else unrecognised still goes
# to quarantine, never silently dropped.
OS_METADATA_NAMES = {"desktop.ini", "thumbs.db", ".ds_store"}
OS_METADATA_PREFIXES = ("~$",)

# Keep inbox copy names comfortably inside Windows' default MAX_PATH (260).
MAX_COPY_NAME_STEM = 80


def _is_os_metadata(name: str) -> bool:
    lower = name.lower()
    return lower in OS_METADATA_NAMES or any(lower.startswith(p) for p in OS_METADATA_PREFIXES)


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def scan_folder(watched: Path, inbox: Path, repo: Repository,
                patterns: tuple[str, ...] = ("*",),
                skipped: list[str] | None = None) -> list[IngestedFile]:
    """One scan pass over the watched folder. Returns every file found this
    pass, each either new (to be parsed/quarantined) or marked duplicate.
    Never writes to, moves, or deletes anything under `watched`.

    A file the OS refuses to read this pass (Windows sharing violation while
    the secure-messaging client or antivirus still holds it) is SKIPPED, not
    fatal: nothing about it is recorded, so the next scan retries it —
    never-drop holds across passes. Skips are reported via `skipped`."""
    ingested: list[IngestedFile] = []
    seen_paths: set[Path] = set()
    for pattern in patterns:
        for src in sorted(watched.glob(pattern)):
            if not src.is_file() or src in seen_paths:
                continue
            seen_paths.add(src)
            if _is_os_metadata(src.name):
                continue  # Windows shell noise, never feed content
            try:
                raw = src.read_bytes()
            except OSError as e:
                if skipped is not None:
                    skipped.append(f"{src.name}: unreadable this pass ({e}); will retry")
                continue
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
            dest = inbox / f"{digest[:16]}_{src.name[:MAX_COPY_NAME_STEM]}"
            try:
                if not dest.exists():
                    shutil.copy2(src, dest)  # copy, never move
            except OSError as e:
                if skipped is not None:
                    skipped.append(f"{src.name}: copy failed this pass ({e}); will retry")
                continue

            ingested.append(IngestedFile(src, dest, digest, sniffer.sniff(raw), raw))
    return ingested
