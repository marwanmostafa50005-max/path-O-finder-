"""Initials sign-on gate — no analysis, queue, or disposition without an
identified operator (the dispensing-bench / DD-register discipline)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QLabel, QLineEdit, QPushButton,
                               QVBoxLayout)

from .. import APP_NAME, SLOGAN
from . import theme


class SignOnDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — sign on")
        self.setModal(True)
        self.setMinimumWidth(420)
        self.initials: str | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 32, 40, 32)
        lay.setSpacing(14)

        logo = QLabel()
        pix = QPixmap(str(theme.logo_path()))
        if not pix.isNull():
            logo.setPixmap(pix.scaledToWidth(280, Qt.TransformationMode.SmoothTransformation))
            logo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            lay.addWidget(logo)

        sub = QLabel(SLOGAN)
        sub.setObjectName("subtitle")
        sub.setWordWrap(True)
        sub.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(sub)

        prompt = QLabel("Enter your initials to begin. Every run is recorded "
                        "against these initials in the practice audit log.")
        prompt.setWordWrap(True)
        lay.addWidget(prompt)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText("e.g. MM")
        self.edit.setMaxLength(6)
        self.edit.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.edit.returnPressed.connect(self._accept)
        lay.addWidget(self.edit)

        self.error = QLabel("")
        self.error.setObjectName("subtitle")
        lay.addWidget(self.error)

        btn = QPushButton("Sign on")
        btn.clicked.connect(self._accept)
        btn.setDefault(True)
        lay.addWidget(btn)

    def _accept(self):
        text = self.edit.text().strip().upper()
        if len(text) < 2 or not text.isalpha():
            self.error.setText("Initials must be at least two letters.")
            return
        self.initials = text
        self.accept()
