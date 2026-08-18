"""Settings: watched folder, closed-loop mode + strictness, grace-matrix /
citation-map YAML editors (validated + versioned + audited), alias table
editor, VLM status. Every save requires the signed-on operator's initials
(carried from sign-on)."""

from __future__ import annotations

from PySide6.QtWidgets import (QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
                               QPushButton, QSpinBox, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout,
                               QWidget)

from ..config.loader import ConfigStore
from ..extraction import vlm_tier3


class YamlEditorTab(QWidget):
    def __init__(self, store: ConfigStore, cfg_name: str, initials: str,
                 description: str, parent=None):
        super().__init__(parent)
        self.store = store
        self.cfg_name = cfg_name
        self.initials = initials
        lay = QVBoxLayout(self)
        desc = QLabel(description)
        desc.setWordWrap(True)
        desc.setObjectName("subtitle")
        lay.addWidget(desc)
        self.editor = QPlainTextEdit()
        self.editor.setPlainText(store.get_yaml(cfg_name))
        lay.addWidget(self.editor, 1)
        row = QHBoxLayout()
        self.status = QLabel("")
        self.status.setObjectName("subtitle")
        row.addWidget(self.status)
        row.addStretch(1)
        save = QPushButton("Validate && save new version")
        save.clicked.connect(self._save)
        row.addWidget(save)
        lay.addLayout(row)

    def _save(self):
        try:
            self.store.save(self.cfg_name, self.editor.toPlainText(), self.initials)
            self.status.setText("Saved as a new audited version.")
        except Exception as e:
            QMessageBox.warning(self, "Not saved",
                                f"Validation failed — the live config is unchanged.\n\n{e}")


class AliasTab(QWidget):
    def __init__(self, store: ConfigStore, initials: str, parent=None):
        super().__init__(parent)
        self.store = store
        self.initials = initials
        lay = QVBoxLayout(self)
        desc = QLabel("Local test-name aliases layered over the RCPA SPIA seed. "
                      "Raw lab names mapped here route to the right analyte "
                      "concept; unmapped names are never guessed.")
        desc.setWordWrap(True)
        desc.setObjectName("subtitle")
        lay.addWidget(desc)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Raw name (from lab)", "Canonical analyte", "LOINC"])
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        add = QPushButton("Add row")
        add.clicked.connect(lambda: self.table.insertRow(self.table.rowCount()))
        row.addWidget(add)
        row.addStretch(1)
        save = QPushButton("Save aliases")
        save.clicked.connect(self._save)
        row.addWidget(save)
        lay.addLayout(row)
        self._load()

    def _load(self):
        self.table.setRowCount(0)
        for raw, (canonical, loinc) in sorted(self.store.repo.aliases().items()):
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(raw))
            self.table.setItem(r, 1, QTableWidgetItem(canonical))
            self.table.setItem(r, 2, QTableWidgetItem(loinc or ""))

    def _save(self):
        for r in range(self.table.rowCount()):
            raw = self.table.item(r, 0)
            canonical = self.table.item(r, 1)
            if raw and canonical and raw.text().strip() and canonical.text().strip():
                loinc_item = self.table.item(r, 2)
                self.store.repo.add_alias(
                    raw.text().strip(), canonical.text().strip(),
                    (loinc_item.text().strip() if loinc_item else "") or None,
                    self.initials)
        self._load()


class SettingsView(QWidget):
    def __init__(self, store: ConfigStore, initials: str, parent=None):
        super().__init__(parent)
        self.store = store
        self.initials = initials

        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs)

        # -- practice tab
        practice = QWidget()
        form = QFormLayout(practice)
        s = store.get("settings")

        folder_row = QHBoxLayout()
        self.folder = QLineEdit(s.get("watched_folder") or "")
        browse = QPushButton("Browse…")
        browse.setObjectName("quiet")
        browse.clicked.connect(self._browse)
        folder_row.addWidget(self.folder)
        folder_row.addWidget(browse)
        form.addRow("Watched feed folder (read-only copy source)", folder_row)

        self.adapter = QComboBox()
        self.adapter.addItems(["generic", "medical-objects", "healthlink", "argus", "referralnet"])
        self.adapter.setCurrentText(s.get("source_adapter", "generic"))
        form.addRow("Secure-messaging adapter", self.adapter)

        self.mode = QComboBox()
        self.mode.addItems(["inbox", "recall"])
        self.mode.setCurrentText(s.get("closed_loop_mode", "inbox"))
        form.addRow("Closed-loop mode", self.mode)

        self.strictness = QComboBox()
        self.strictness.addItems(["strict", "lenient"])
        self.strictness.setCurrentText(s.get("closed_loop_strictness", "strict"))
        form.addRow("Strictness (strict = both inbox AND recall)", self.strictness)

        self.gate = QSpinBox()
        self.gate.setRange(0, 100)
        self.gate.setValue(int(s.get("ocr_confidence_gate", 80)))
        form.addRow("OCR confidence gate (below → check-yourself)", self.gate)

        self.vlm = QComboBox()
        self.vlm.addItems(["auto", "on", "off"])
        self.vlm.setCurrentText(s.get("vlm_enabled", "auto"))
        hw = vlm_tier3.detect_hardware()
        form.addRow("Tier-3 local vision model", self.vlm)
        vlm_status = QLabel(("Hardware capable — model ready." if hw.capable
                             else f"Disabled gracefully: {hw.reason}. The app is fully "
                                  f"functional without it; unreadable pages go to check-yourself."))
        vlm_status.setObjectName("subtitle")
        vlm_status.setWordWrap(True)
        form.addRow("", vlm_status)

        self.hour = QSpinBox()
        self.hour.setRange(0, 23)
        self.hour.setValue(int(s.get("overnight_build_hour", 5)))
        form.addRow("Overnight queue build hour", self.hour)

        save = QPushButton("Save practice settings")
        save.clicked.connect(self._save_settings)
        form.addRow("", save)
        tabs.addTab(practice, "Practice")

        tabs.addTab(YamlEditorTab(
            store, "grace_matrix", initials,
            "Grace matrix — how long each severity may sit before it is overdue. "
            "DRAFT defaults ship for clinician review; every save is a new audited version."),
            "Grace matrix")
        tabs.addTab(YamlEditorTab(
            store, "citation_map", initials,
            "Citation map — pointer-only guideline references (name, publisher, "
            "edition, section, URL as text). No guideline body text, no dose, no "
            "patient-specific tailoring. Re-verify editions on the review cadence."),
            "Citation map")
        tabs.addTab(AliasTab(store, initials), "Test aliases")

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Choose the feed folder")
        if d:
            self.folder.setText(d)

    def _save_settings(self):
        yaml_text = (
            f'watched_folder: "{self.folder.text().strip()}"\n'
            f"source_adapter: {self.adapter.currentText()}\n"
            f"closed_loop_mode: {self.mode.currentText()}\n"
            f"closed_loop_strictness: {self.strictness.currentText()}\n"
            f"ocr_confidence_gate: {self.gate.value()}\n"
            f"vlm_enabled: {self.vlm.currentText()}\n"
            f"overnight_build_hour: {self.hour.value()}\n"
        )
        try:
            self.store.save("settings", yaml_text, self.initials)
            QMessageBox.information(self, "Saved", "Practice settings saved (audited).")
        except Exception as e:
            QMessageBox.warning(self, "Not saved", str(e))
