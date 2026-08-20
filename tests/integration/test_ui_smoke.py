"""UI smoke tests (offscreen). Verify the screens construct against a real
DB, the About page carries the EXACT two-part copy, sign-on gates initials,
and a disposition made through the detail view lands in the audit log."""

from __future__ import annotations

import os
import shutil

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from pathofinder.pipeline import Pipeline  # noqa: E402
from tests.fixtures import generator  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def loaded_repo(tmp_path, data_dir, repo):
    src = generator.write_all()
    feed = tmp_path / "feed"
    feed.mkdir()
    for f in src.iterdir():
        shutil.copy2(f, feed / f.name)
    Pipeline(repo).run("MM", watched_folder=feed)
    return repo


def test_about_page_exact_copy(qapp):
    from pathofinder.ui import about_view

    assert about_view.PHILOSOPHY.startswith(
        "I built path-O-finder because of a quiet problem I kept seeing at the coalface:")
    assert about_view.PHILOSOPHY.endswith(
        "Every result finds its path, and every path is one a clinician chose.")
    assert "nothing is ever marked 'handled' by the machine" in about_view.PHILOSOPHY
    assert about_view.FOUNDER.startswith(
        "Marwan Morsy, B.Pharm — AHPRA Reg. PHA0002761764.")
    assert about_view.FOUNDER.endswith(
        "the clinician who will validate it against real practice data.")
    assert "U.S. News & World" in about_view.FOUNDER

    view = about_view.AboutView()
    labels = [l.text() for l in view.findChildren(type(view), "")] or []
    from PySide6.QtWidgets import QLabel
    texts = [l.text() for l in view.findChildren(QLabel)]
    assert about_view.PHILOSOPHY in texts
    assert about_view.FOUNDER in texts


def test_signon_rejects_blank_and_accepts_initials(qapp):
    from pathofinder.ui.signon import SignOnDialog
    dlg = SignOnDialog()
    dlg.edit.setText(" ")
    dlg._accept()
    assert dlg.initials is None
    dlg.edit.setText("mm")
    dlg._accept()
    assert dlg.initials == "MM"


def test_main_window_queue_and_disposition(qapp, loaded_repo):
    from pathofinder.ui.main_window import MainWindow

    win = MainWindow(loaded_repo, "MM", encrypted=True)
    try:
        tree = win.queue_view.tree
        assert tree.topLevelItemCount() > 0

        # Select the first child flag and record a disposition through the UI.
        first_child = tree.topLevelItem(0).child(0)
        tree.setCurrentItem(first_child)
        assert win.detail_view.flag is not None
        open_before = len(loaded_repo.open_flags())
        win.detail_view._dispose("handled")
        assert len(loaded_repo.open_flags()) == open_before - 1

        events = [r[0] for r in loaded_repo.conn.execute(
            "SELECT event_type FROM audit_log")]
        assert "disposition" in events
    finally:
        win.scheduler.shutdown()


def test_app_selfcheck_passes(qapp, data_dir):
    """The same startup verification the Windows build runs against the
    frozen exe must pass from source too."""
    from pathofinder import app as app_mod
    assert app_mod._selfcheck() == 0


def test_settings_and_audit_views_construct(qapp, loaded_repo):
    from pathofinder.config.loader import ConfigStore
    from pathofinder.ui.audit_view import AuditView
    from pathofinder.ui.settings_view import SettingsView

    s = SettingsView(ConfigStore(loaded_repo), "MM")
    a = AuditView(loaded_repo)
    a._verify()
    assert "intact" in a.chain_status.text()
