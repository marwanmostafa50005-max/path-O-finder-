"""Morning queue — grouped per patient, ranked, check-yourself at bottom."""

from __future__ import annotations

import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from ..presentation import queue as queue_mod

SEVERITY_LABEL = {
    "critical": "CRITICAL (lab flag)",
    "high": "Abnormal (lab flag)",
    "borderline": "Outside stated range",
    "check_yourself": "Check yourself",
}


class QueueView(QWidget):
    flag_selected = Signal(dict)
    build_now = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)

        header = QHBoxLayout()
        title = QLabel("Morning queue")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch(1)
        self.count_label = QLabel("")
        self.count_label.setObjectName("subtitle")
        header.addWidget(self.count_label)
        btn = QPushButton("Build queue now")
        btn.setObjectName("quiet")
        btn.clicked.connect(self.build_now.emit)
        header.addWidget(btn)
        lay.addLayout(header)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Patient / result", "Severity", "Value", "Lab range", "Lab flag"])
        self.tree.setColumnWidth(0, 340)
        self.tree.setColumnWidth(1, 190)
        self.tree.itemSelectionChanged.connect(self._on_select)
        lay.addWidget(self.tree, 1)

        hint = QLabel("Items the engine could not read with certainty sit at the "
                      "bottom as “check yourself” — the system dropped "
                      "them to you for human eyes, it asserts nothing about them.")
        hint.setObjectName("subtitle")
        hint.setWordWrap(True)
        lay.addWidget(hint)

    def populate(self, open_flags: list[dict]) -> None:
        self.tree.clear()
        groups = queue_mod.build_queue(open_flags)
        n_flags = sum(len(g.flags) for g in groups)
        self.count_label.setText(f"{n_flags} open item(s) · {len(groups)} patient(s)")

        for g in groups:
            top = QTreeWidgetItem([f"{g.display_name}   (DOB {g.dob or '—'})", "", "", "", ""])
            top.setFlags(top.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.tree.addTopLevelItem(top)
            for f in g.flags:
                sev = f.get("severity_tier", "")
                value = f.get("value_raw") or "—"
                unit = f.get("unit_raw") or ""
                item = QTreeWidgetItem([
                    f.get("analyte_canonical") or f.get("analyte_raw") or "?",
                    SEVERITY_LABEL.get(sev, sev),
                    f"{value} {unit}".strip(),
                    f.get("ref_range_raw") or "—",
                    f.get("lab_abnormal_flag") or "—",
                ])
                item.setData(0, Qt.ItemDataRole.UserRole, json.dumps(f, default=str))
                top.addChild(item)
            top.setExpanded(True)

    def _on_select(self):
        items = self.tree.selectedItems()
        if not items:
            return
        payload = items[0].data(0, Qt.ItemDataRole.UserRole)
        if payload:
            self.flag_selected.emit(json.loads(payload))
