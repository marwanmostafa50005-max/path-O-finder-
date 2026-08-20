from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pathofinder.db import connection, schema  # noqa: E402
from pathofinder.db.repository import Repository  # noqa: E402

# ---------------------------------------------------------------------------
# Windows mount-point hardening can make os.path.realpath() raise
# OSError WinError 448 ("untrusted mount point") while pytest sweeps its temp
# root for dead symlinks at session finish - AFTER every test has already
# passed - which turns a green run into a red exit code. Temp-dir hygiene
# must never fail the suite: wrap the sweep to swallow OSError. tmpdir.py
# imports the function by name, so both references are patched. No-ops
# harmlessly if a future pytest renames these internals.
try:
    import _pytest.pathlib as _pytest_pathlib  # noqa: E402
    import _pytest.tmpdir as _pytest_tmpdir  # noqa: E402

    def _safe_cleanup_dead_symlinks(root, _orig=_pytest_pathlib.cleanup_dead_symlinks):
        try:
            _orig(root)
        except OSError:
            pass

    _pytest_pathlib.cleanup_dead_symlinks = _safe_cleanup_dead_symlinks
    _pytest_tmpdir.cleanup_dead_symlinks = _safe_cleanup_dead_symlinks
except (ImportError, AttributeError):  # pragma: no cover - future pytest
    pass


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PATHOFINDER_DATA_DIR", str(tmp_path / "appdata"))
    return tmp_path / "appdata"


@pytest.fixture()
def db(tmp_path):
    """A real (SQLCipher-encrypted when available) DB with schema applied.
    Passphrase passed explicitly so tests never touch the OS keyring."""
    if connection.HAVE_SQLCIPHER:
        handle = connection.connect(tmp_path / "test.db", passphrase="test-passphrase")
    else:
        os.environ["PATHOFINDER_ALLOW_PLAIN_SQLITE"] = "1"
        handle = connection.connect(tmp_path / "test.db")
    schema.migrate(handle.conn)
    yield handle
    handle.conn.close()


@pytest.fixture()
def repo(db):
    return Repository(db.conn)
