"""INVARIANT: NO-NETWORK — the running application opens no outbound socket.

Every socket connect attempt is denied for the duration of a full pipeline
run over every fixture (loopback included: the core pipeline needs no socket
at all; the optional Tier-3 VLM, which talks to 127.0.0.1 only, is simply
absent/disabled — exactly the shipped graceful-disable posture).
"""

from __future__ import annotations

import shutil
import socket

import pytest

from pathofinder.pipeline import Pipeline
from pathofinder.presentation import queue
from tests.fixtures import generator


class _NetworkBlocked(AssertionError):
    pass


@pytest.fixture()
def deny_all_sockets(monkeypatch):
    def _blocked(*args, **kwargs):
        raise _NetworkBlocked("outbound network call attempted by the app")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked)


def test_invariant_full_run_opens_no_socket(tmp_path, data_dir, repo, deny_all_sockets):
    src = generator.write_all()
    feed = tmp_path / "feed"
    feed.mkdir()
    for f in src.iterdir():
        shutil.copy2(f, feed / f.name)

    report = Pipeline(repo).run("MM", watched_folder=feed)
    assert report.messages_parsed > 0 and report.flags_built > 0
    queue.build_queue(repo.open_flags())


def test_invariant_vlm_client_refuses_non_loopback():
    from pathofinder.extraction.vlm_tier3 import VlmClient
    with pytest.raises(ValueError):
        VlmClient("http://example.com:8078")
    VlmClient("http://127.0.0.1:8078")   # loopback allowed (local llama-server)
