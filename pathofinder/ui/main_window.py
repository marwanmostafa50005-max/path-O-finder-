"""Main window: queue · detail · settings · audit · about, gated by sign-on."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QHBoxLayout, QLabel, QMainWindow, QMessageBox,
                               QSplitter, QTabWidget, QWidget, QVBoxLayout)
from PySide6.QtCore import Qt

from .. import APP_NAME, __version__
from ..actionstate.closedloop import ClosedLoopSettings, Mode, Strictness
from ..config.loader import ConfigStore
from ..db.repository import Repository
from ..guidelines.citations import CitationMap
from ..pipeline import Pipeline
from ..presentation.scheduler import OvernightScheduler
from .about_view import AboutView
from .audit_view import AuditView
from .detail_view import DetailView
from .queue_view import QueueView
from .settings_view import SettingsView


class MainWindow(QMainWindow):
    def __init__(self, repo: Repository, operator_initials: str, encrypted: bool):
        super().__init__()
        self.repo = repo
        self.initials = operator_initials
        self.store = ConfigStore(repo)
        settings = self.store.get("settings")
        loop = ClosedLoopSettings(
            Mode(settings.get("closed_loop_mode", "inbox")),
            Strictness(settings.get("closed_loop_strictness", "strict")))

        self.setWindowTitle(f"{APP_NAME} v{__version__} — signed on: {operator_initials}")
        self.resize(1360, 860)

        tabs = QTabWidget()

        # -- queue + detail
        queue_page = QWidget()
        lay = QVBoxLayout(queue_page)
        if not encrypted:
            warn = QLabel("⚠ Database encryption unavailable in this build — "
                          "development mode only, do not use with patient data.")
            warn.setObjectName("severity-critical")
            lay.addWidget(warn)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.queue_view = QueueView()
        citation_map = CitationMap.from_yaml(self.store.get_yaml("citation_map"))
        self.detail_view = DetailView(repo, citation_map, loop.label, operator_initials)
        split.addWidget(self.queue_view)
        split.addWidget(self.detail_view)
        split.setSizes([620, 740])
        lay.addWidget(split)
        tabs.addTab(queue_page, "Morning queue")

        tabs.addTab(SettingsView(self.store, operator_initials), "Settings")
        self.audit_view = AuditView(repo)
        tabs.addTab(self.audit_view, "Audit log")
        tabs.addTab(AboutView(), "About")
        self.setCentralWidget(tabs)

        self.queue_view.flag_selected.connect(self.detail_view.show_flag)
        self.queue_view.build_now.connect(self.build_queue_now)
        self.detail_view.disposition_made.connect(self.refresh_queue)

        self.scheduler = OvernightScheduler(
            self._overnight_build, hour=int(settings.get("overnight_build_hour", 5)))
        self.scheduler.start()

        self.refresh_queue()

    # -- actions ----------------------------------------------------------

    def build_queue_now(self):
        try:
            pipe = Pipeline(self.repo, self.store)
            report = pipe.run(self.initials)
            self.refresh_queue()
            self.audit_view.reload()
            notes = ("\n".join(report.notes)) if report.notes else ""
            QMessageBox.information(
                self, "Run complete",
                f"Files seen: {report.files_seen}\n"
                f"Messages parsed: {report.messages_parsed}\n"
                f"Quarantined (check-yourself): {report.quarantined}\n"
                f"Duplicates skipped: {report.duplicates}\n"
                f"Flags built: {report.flags_built}\n"
                f"Corrections applied: {report.corrections_applied}\n{notes}")
        except Exception as e:
            QMessageBox.warning(self, "Run failed", str(e))

    def _overnight_build(self):
        # The scheduled build runs under the initials of the operator who
        # armed it (recorded in mode_settings); presentation still requires
        # a live sign-on next morning.
        try:
            Pipeline(self.repo, self.store).run(self.initials)
        except Exception:
            pass  # surfaced on next manual run; never crashes the UI thread

    def refresh_queue(self):
        self.queue_view.populate(self.repo.open_flags())

    def closeEvent(self, event):
        self.scheduler.shutdown()
        super().closeEvent(event)
