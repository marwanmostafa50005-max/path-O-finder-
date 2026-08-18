"""Why-flagged detail: value, lab range, lab OBX-8 flag, why-no-action
evidence, provenance viewer (segment/field for Tier 1; page + bounding-box
thumbnail for Tier 2/3), serial values (DISPLAY ONLY — no trend assertion),
pointer-only citation, and the one-tap disposition bar."""

from __future__ import annotations

import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QScrollArea,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from ..actionstate.dispositions import DEFAULT_SCOPE, watching_expiry
from ..db.repository import Repository
from ..guidelines.citations import CitationMap
from . import theme

DISPOSITION_BUTTONS = [
    ("Handled", "handled"),
    ("Watching", "watching"),
    ("Not relevant", "not-relevant"),
    ("Escalate", "escalate"),
    ("Check done", "check-done"),
]


class DetailView(QWidget):
    disposition_made = Signal()

    def __init__(self, repo: Repository, citation_map: CitationMap,
                 closed_loop_label: str, operator_initials: str, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.citation_map = citation_map
        self.closed_loop_label = closed_loop_label
        self.operator_initials = operator_initials
        self.flag: dict | None = None

        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        inner = QWidget()
        self.lay = QVBoxLayout(inner)
        self.lay.setSpacing(12)

        self.title = QLabel("Select a result from the queue")
        self.title.setObjectName("title")
        self.lay.addWidget(self.title)

        self.why_panel = QFrame()
        self.why_panel.setObjectName("panel")
        self.why_grid = QGridLayout(self.why_panel)
        self.lay.addWidget(self.why_panel)

        self.prov_label = QLabel("")
        self.prov_label.setWordWrap(True)
        self.lay.addWidget(self.prov_label)
        self.prov_image = QLabel()
        self.prov_image.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.lay.addWidget(self.prov_image)

        self.serial_title = QLabel("Serial values (display only — interpretation is yours)")
        self.serial_title.setObjectName("subtitle")
        self.lay.addWidget(self.serial_title)
        self.serial = QTableWidget(0, 4)
        self.serial.setHorizontalHeaderLabels(["When", "Value", "Lab range", "Lab flag"])
        self.serial.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.serial.setMaximumHeight(180)
        self.lay.addWidget(self.serial)

        self.citation = QLabel("")
        self.citation.setWordWrap(True)
        self.citation.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lay.addWidget(self.citation)

        note_row = QHBoxLayout()
        self.note = QLineEdit()
        self.note.setPlaceholderText("Optional note for the audit record…")
        note_row.addWidget(self.note)
        self.lay.addLayout(note_row)

        bar = QHBoxLayout()
        self.buttons: list[QPushButton] = []
        for label, dtype in DISPOSITION_BUTTONS:
            b = QPushButton(label)
            if dtype == "escalate":
                b.setObjectName("accent")
            b.clicked.connect(lambda _=False, d=dtype: self._dispose(d))
            b.setEnabled(False)
            bar.addWidget(b)
            self.buttons.append(b)
        self.lay.addLayout(bar)
        self.lay.addStretch(1)

        scroll.setWidget(inner)
        outer.addWidget(scroll)

    # -- population -------------------------------------------------------

    def show_flag(self, flag: dict) -> None:
        self.flag = flag
        analyte = flag.get("analyte_canonical") or flag.get("analyte_raw") or "?"
        self.title.setText(analyte)

        while self.why_grid.count():
            item = self.why_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        sev = flag.get("severity_tier", "")
        rows = [
            ("Value", f"{flag.get('value_raw') or '—'} {flag.get('unit_raw') or ''}".strip()),
            ("Lab reference range", flag.get("ref_range_raw") or "—"),
            ("Lab abnormal flag (OBX-8)", flag.get("lab_abnormal_flag") or "— (none sent)"),
            ("Why flagged", flag.get("flag_reason") or "—"),
            ("Why no action evidence",
             f"No {self.closed_loop_label} confirmation recorded for this result "
             f"— the loop is open until a clinician signs it off."),
            ("Extraction", f"Tier {flag.get('extraction_tier')} · "
                           f"confidence {flag.get('confidence'):.2f}" if flag.get('confidence') is not None else "—"),
            ("Reported", flag.get("reported_at") or "—"),
        ]
        for i, (k, v) in enumerate(rows):
            key = QLabel(k)
            key.setObjectName("subtitle")
            val = QLabel(str(v))
            val.setWordWrap(True)
            if k == "Why flagged":
                val.setObjectName(f"severity-{sev}")
            self.why_grid.addWidget(key, i, 0)
            self.why_grid.addWidget(val, i, 1)

        self._show_provenance(flag)
        self._show_serial(flag)
        self._show_citation(flag)
        for b in self.buttons:
            b.setEnabled(True)

    def _show_provenance(self, flag: dict) -> None:
        self.prov_image.clear()
        try:
            prov = json.loads(flag.get("provenance_json") or "{}")
        except json.JSONDecodeError:
            prov = {}
        if prov.get("segment_path"):
            self.prov_label.setText(
                f"Source: {prov.get('engine','')} — {prov['segment_path']} "
                f"(the exact HL7 field this value was read from)")
            return
        if prov.get("page") and prov.get("bboxes"):
            self.prov_label.setText(
                f"Source: {prov.get('engine','')} — page {prov['page']}, "
                f"highlighted region below")
            pix = self._render_bbox_thumbnail(flag, prov)
            if pix is not None:
                self.prov_image.setPixmap(pix)
            return
        self.prov_label.setText("Source: raw message retained in the encrypted store")

    def _render_bbox_thumbnail(self, flag: dict, prov: dict) -> QPixmap | None:
        row = self.repo.conn.execute(
            "SELECT m.raw_blob FROM results r JOIN orders o ON o.order_id=r.order_id"
            " JOIN messages m ON m.message_id=o.message_id WHERE r.result_id=?",
            (flag.get("result_id"),),
        ).fetchone()
        if not row or not row[0]:
            return None
        blob: bytes = row[0]
        if not blob.startswith(b"%PDF-"):
            return None
        try:
            import pypdfium2 as pdfium
            doc = pdfium.PdfDocument(blob)
            page_idx = int(prov["page"]) - 1
            engine = prov.get("engine", "")
            scale = (300 if engine == "tesseract" else 72) / 72
            page = doc[page_idx]
            pil = page.render(scale=scale).to_pil().convert("RGB")
            img = QImage(pil.tobytes(), pil.width, pil.height,
                         pil.width * 3, QImage.Format.Format_RGB888).copy()
            doc.close()
        except Exception:
            return None

        painter = QPainter(img)
        pen = QPen(QColor(theme.BURGUNDY_LIGHT))
        pen.setWidth(3)
        painter.setPen(pen)
        for bbox in prov.get("bboxes", []):
            x0, y0, x1, y1 = bbox
            painter.drawRect(int(x0) - 3, int(y0) - 3,
                             int(x1 - x0) + 6, int(y1 - y0) + 6)
        painter.end()
        return QPixmap.fromImage(img).scaledToWidth(
            640, Qt.TransformationMode.SmoothTransformation)

    def _show_serial(self, flag: dict) -> None:
        self.serial.setRowCount(0)
        pid, analyte = flag.get("patient_id"), flag.get("analyte_canonical")
        if not pid or not analyte:
            return
        for row in self.repo.serial_values(pid, analyte):
            r = self.serial.rowCount()
            self.serial.insertRow(r)
            for c, key in enumerate(("created_at", "value_raw", "ref_range_raw",
                                     "lab_abnormal_flag")):
                self.serial.setItem(r, c, QTableWidgetItem(str(row.get(key) or "—")))

    def _show_citation(self, flag: dict) -> None:
        c = self.citation_map.citation_for(flag)
        if c:
            self.citation.setText(f"Guideline pointer: {c.display}")
        else:
            self.citation.setText("")

    # -- disposition ------------------------------------------------------

    def _dispose(self, dtype: str) -> None:
        if not self.flag:
            return
        scope = DEFAULT_SCOPE.get(dtype, "this_result")
        expires = watching_expiry(3) if dtype == "watching" else None
        self.repo.add_disposition(
            int(self.flag["flag_id"]), self.operator_initials, dtype,
            self.closed_loop_label, note=self.note.text().strip() or None,
            suppress_scope=scope, suppress_expires_at=expires)
        self.note.clear()
        self.flag = None
        for b in self.buttons:
            b.setEnabled(False)
        self.title.setText("Recorded. Select the next result.")
        self.disposition_made.emit()
