"""Database connection management.

Production posture: SQLite encrypted at rest with SQLCipher (AES-256) via the
self-contained sqlcipher3 binary wheel. The key is derived from an
operator-set passphrase captured at first run and stored in the OS credential
store (Windows DPAPI via `keyring`) — never hard-coded, never written to disk
in clear.

Development/CI escape hatch: if the sqlcipher3 wheel is unavailable the app
refuses to start unless PATHOFINDER_ALLOW_PLAIN_SQLITE=1 is set, in which case
plain sqlite3 is used and the connection is marked `encrypted=False` so the UI
can surface it. The shipped Windows build always carries sqlcipher3.
"""

from __future__ import annotations

import os
import secrets
import sqlite3
from dataclasses import dataclass
from pathlib import Path

KEYRING_SERVICE = "path-O-finder"
KEYRING_USER = "db-passphrase"

try:  # preferred: SQLCipher wheel
    from sqlcipher3 import dbapi2 as sqlcipher_dbapi2  # type: ignore
    HAVE_SQLCIPHER = True
except ImportError:
    sqlcipher_dbapi2 = None
    HAVE_SQLCIPHER = False


class EncryptionUnavailableError(RuntimeError):
    """Raised when SQLCipher is missing and the plain-sqlite escape is not set."""


@dataclass
class DBHandle:
    conn: sqlite3.Connection
    encrypted: bool
    path: Path


def _get_or_create_passphrase() -> str:
    """Fetch the DB passphrase from the OS credential store, creating one on
    first run. On Windows, keyring uses the DPAPI-backed Credential Locker."""
    import keyring

    stored = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
    if stored:
        return stored
    passphrase = secrets.token_urlsafe(32)
    keyring.set_password(KEYRING_SERVICE, KEYRING_USER, passphrase)
    return passphrase


def connect(path: Path, passphrase: str | None = None) -> DBHandle:
    """Open (creating if needed) the practice database.

    Uses SQLCipher when available; otherwise honours the dev escape hatch.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    if HAVE_SQLCIPHER:
        key = passphrase if passphrase is not None else _get_or_create_passphrase()
        conn = sqlcipher_dbapi2.connect(str(path))
        # Parameterised PRAGMA is not supported; escape quotes in the key.
        conn.execute(f"PRAGMA key = '{key.replace(chr(39), chr(39)*2)}'")
        conn.execute("PRAGMA cipher_page_size = 4096")
        # Verify the key actually opens the DB (raises on wrong key).
        conn.execute("SELECT count(*) FROM sqlite_master")
        encrypted = True
    else:
        if os.environ.get("PATHOFINDER_ALLOW_PLAIN_SQLITE") != "1":
            raise EncryptionUnavailableError(
                "SQLCipher (sqlcipher3) is not installed. Refusing to store "
                "patient data unencrypted. Install the 'sqlcipher' extra, or "
                "set PATHOFINDER_ALLOW_PLAIN_SQLITE=1 for development only."
            )
        conn = sqlite3.connect(str(path))
        encrypted = False

    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    if encrypted:
        conn.row_factory = sqlcipher_dbapi2.Row  # type: ignore[union-attr]
    else:
        conn.row_factory = sqlite3.Row
    return DBHandle(conn=conn, encrypted=encrypted, path=path)
