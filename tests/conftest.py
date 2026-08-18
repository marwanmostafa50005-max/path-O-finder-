from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pathofinder.db import connection, schema  # noqa: E402
from pathofinder.db.repository import Repository  # noqa: E402


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
