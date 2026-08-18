"""Read-only audit log viewer with hash-chain verification."""

from __future__ import annotations

from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ..db import audit
from ..db.repository import Repository


class AuditView(QWidget):
    def __init__(self, repo: Repository, parent=None):
        super().__init__(parent)
        self.repo = repo
        lay = QVBoxLayout(self)

        header = QHBoxLayout()
        title = QLabel("Audit log (append-only, hash-chained)")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch(1)
        self.chain_status = QLabel("")
        self.chain_status.setObjectName("subtitle")
        header.addWidget(self.chain_status)
        verify = QPushButton("Verify chain")
        verify.setObjectName("quiet")
        verify.clicked.connect(self._verify)
        header.addWidget(verify)
        refresh = QPushButton("Refresh")
        refresh.setObjectName("quiet")
        refresh.clicked.connect(self.reload)
        header.addWidget(refresh)
        lay.addLayout(header)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["When (UTC)", "Who", "Event", "Entity", "Id", "Detail"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        lay.addWidget(self.table, 1)
        self.reload()

    def reload(self):
        self.table.setRowCount(0)
        rows = self.repo.conn.execute(
            "SELECT ts, actor_initials, event_type, entity, entity_id, after_json"
            " FROM audit_log ORDER BY audit_id DESC LIMIT 500").fetchall()
        for row in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c in range(6):
                self.table.setItem(r, c, QTableWidgetItem(str(row[c] or "")))

    def _verify(self):
        ok, detail = audit.verify_chain(self.repo.conn)
        self.chain_status.setText(
            "Chain intact ✔" if ok else f"CHAIN BROKEN: {detail}")
