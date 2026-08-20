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


def _selfcheck() -> int:
    """Headless startup verification for the frozen build (--selfcheck).

    Run by build_windows.ps1 against the PyInstaller output: proves the
    bundled app can import its full stack, find its resources, and
    initialise Qt offscreen - so a packaging regression fails the BUILD,
    never a practice machine. Exit 0 = healthy."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    problems: list[str] = []

    res = paths.resources_dir()
    for rel in ("grace_matrix.yaml", "citation_map.yaml", "plausibility_bounds.yaml",
                "spia_aliases.yaml", "fonts/Poppins-Regular.ttf",
                "brand/pathofinder_ui.png", "brand/icon_1024.png"):
        if not (res / rel).exists():
            problems.append(f"missing bundled resource: {rel}")

    try:
        from .db import connection as _conn
        if not _conn.HAVE_SQLCIPHER:
            problems.append("sqlcipher3 not bundled - DB encryption unavailable")
    except Exception as e:  # pragma: no cover - frozen-build guard
        problems.append(f"db layer import failed: {e}")

    try:
        from . import pipeline as _pipeline  # noqa: F401  (pulls the whole engine stack)
    except Exception as e:  # pragma: no cover - frozen-build guard
        problems.append(f"pipeline import failed: {e}")

    try:
        qt_app = QApplication.instance() or QApplication(["selfcheck"])
        theme.load_fonts()
        del qt_app
    except Exception as e:  # pragma: no cover - frozen-build guard
        problems.append(f"Qt initialisation failed: {e}")

    if problems:
        print("SELFCHECK FAILED: " + "; ".join(problems))
        return 1
    print("SELFCHECK OK")
    return 0


def main() -> int:
    if "--selfcheck" in sys.argv:
        return _selfcheck()
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
