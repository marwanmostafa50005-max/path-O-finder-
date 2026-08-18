"""path-O-finder application entry point (initials-gated, offline)."""

from __future__ import annotations

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from . import APP_NAME, paths
from .db import connection, schema
from .db.repository import Repository
from .ui import theme
from .ui.main_window import MainWindow
from .ui.signon import SignOnDialog


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    family = theme.load_fonts()
    app.setStyleSheet(theme.stylesheet(family))
    icon_path = paths.resources_dir() / "brand" / "icon_1024.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    try:
        handle = connection.connect(paths.db_path())
    except connection.EncryptionUnavailableError as e:
        QMessageBox.critical(None, APP_NAME, str(e))
        return 2
    schema.migrate(handle.conn)
    repo = Repository(handle.conn)

    gate = SignOnDialog()
    if gate.exec() != QDialog.DialogCode.Accepted or not gate.initials:
        return 0

    window = MainWindow(repo, gate.initials, encrypted=handle.encrypted)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
