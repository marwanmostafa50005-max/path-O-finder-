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


def _dpapi(data: bytes, protect: bool) -> bytes:
    """Windows DPAPI with CRYPTPROTECT_LOCAL_MACHINE: the blob can be
    unprotected by ANY account on THIS machine (and no other machine)."""
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_byte))]

    crypt32 = ctypes.windll.crypt32          # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32        # type: ignore[attr-defined]
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    blob_out = DATA_BLOB()
    flags = 0x1 | 0x4                        # UI_FORBIDDEN | LOCAL_MACHINE
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    if not fn(ctypes.byref(blob_in), None, None, None, None, flags,
              ctypes.byref(blob_out)):
        raise OSError("DPAPI operation failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _windows_machine_passphrase(db_path: Path) -> str:
    """Machine-scope key management for the practice-wide DB.

    The DB lives in %PROGRAMDATA% (one DB per machine), so a per-USER
    credential-locker entry cannot work: the second Windows account at the
    practice would mint a fresh passphrase and be locked out. Instead the
    passphrase is wrapped with machine-scope DPAPI and stored beside the DB;
    every local account can unwrap it, no other machine can. A legacy
    per-user keyring entry (earlier builds) is migrated in-place."""
    blob_path = db_path.with_suffix(".keyblob")
    if blob_path.exists():
        return _dpapi(blob_path.read_bytes(), protect=False).decode("utf-8")

    legacy = None
    try:
        import keyring
        legacy = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
    except Exception:
        pass
    passphrase = legacy or secrets.token_urlsafe(32)
    blob_path.parent.mkdir(parents=True, exist_ok=True)
    blob_path.write_bytes(_dpapi(passphrase.encode("utf-8"), protect=True))
    return passphrase


def _get_or_create_passphrase(db_path: Path) -> str:
    """DB passphrase, created on first run. Windows: machine-scope DPAPI blob
    beside the DB (see _windows_machine_passphrase). Elsewhere (dev/CI): the
    per-user OS credential store via keyring."""
    import sys
    if sys.platform == "win32":
        return _windows_machine_passphrase(db_path)

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
        key = passphrase if passphrase is not None else _get_or_create_passphrase(path)
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
