"""Brand theme: palette, bundled Poppins, and the application stylesheet.

Palette (build brief §12): Teal frame #0E7C7B / #41BDB4, Ink #243A3B,
Oxygen burgundy #7E1E2E→#B84452 (single bold accent), Deep panel #0E2A2B
(dark background), Paper #F7FAFA. Dark, calm, professional morning-queue UI;
burgundy used sparingly; large tap targets; keyboard-navigable.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFontDatabase

from .. import paths

TEAL = "#0E7C7B"
TEAL_LIGHT = "#41BDB4"
INK = "#243A3B"
BURGUNDY = "#7E1E2E"
BURGUNDY_LIGHT = "#B84452"
DEEP = "#0E2A2B"
DEEP_RAISED = "#123435"
DEEP_HOVER = "#17403f"
PAPER = "#F7FAFA"
TEXT = "#D9EAEA"
TEXT_DIM = "#8FB4B3"

SEVERITY_COLORS = {
    "critical": BURGUNDY_LIGHT,
    "high": "#D9A03C",
    "borderline": TEAL_LIGHT,
    "check_yourself": TEXT_DIM,
}


def load_fonts() -> str:
    """Register bundled Poppins; returns the family name to use."""
    fonts_dir = Path(paths.resources_dir() / "fonts")
    family = "Poppins"
    loaded = False
    for f in sorted(fonts_dir.glob("Poppins-*.ttf")):
        if QFontDatabase.addApplicationFont(str(f)) >= 0:
            loaded = True
    return family if loaded else "Sans Serif"


def logo_path() -> Path:
    return paths.resources_dir() / "brand" / "pathofinder_ui.png"


def stylesheet(font_family: str = "Poppins") -> str:
    return f"""
* {{ font-family: '{font_family}'; }}
QMainWindow, QDialog {{ background: {DEEP}; color: {TEXT}; }}
QWidget {{ background: transparent; color: {TEXT}; font-size: 14px; }}
QFrame#panel, QListWidget, QTreeWidget, QTableWidget, QPlainTextEdit, QTextEdit {{
    background: {DEEP_RAISED}; border: 1px solid {TEAL}; border-radius: 8px;
}}
QLabel#title {{ font-size: 22px; font-weight: 600; color: {TEAL_LIGHT}; }}
QLabel#subtitle {{ font-size: 13px; color: {TEXT_DIM}; }}
QLabel#severity-critical {{ color: {BURGUNDY_LIGHT}; font-weight: 700; }}
QLabel#severity-high {{ color: #D9A03C; font-weight: 600; }}
QLabel#severity-borderline {{ color: {TEAL_LIGHT}; }}
QLabel#severity-check_yourself {{ color: {TEXT_DIM}; font-style: italic; }}
QPushButton {{
    background: {TEAL}; color: {PAPER}; border: none; border-radius: 8px;
    padding: 12px 20px; font-size: 15px; font-weight: 600; min-height: 22px;
}}
QPushButton:hover {{ background: {TEAL_LIGHT}; color: {INK}; }}
QPushButton:focus {{ outline: 2px solid {TEAL_LIGHT}; }}
QPushButton:disabled {{ background: {DEEP_RAISED}; color: {TEXT_DIM}; }}
QPushButton#accent {{ background: {BURGUNDY}; }}
QPushButton#accent:hover {{ background: {BURGUNDY_LIGHT}; color: {PAPER}; }}
QPushButton#quiet {{ background: {DEEP_RAISED}; color: {TEXT}; border: 1px solid {TEAL}; }}
QLineEdit, QComboBox, QSpinBox {{
    background: {DEEP_RAISED}; color: {TEXT}; border: 1px solid {TEAL};
    border-radius: 6px; padding: 10px; font-size: 15px;
}}
QListWidget::item {{ padding: 10px; border-radius: 6px; }}
QListWidget::item:selected, QListWidget::item:hover {{ background: {DEEP_HOVER}; }}
QTabWidget::pane {{ border: 1px solid {TEAL}; border-radius: 8px; }}
QTabBar::tab {{
    background: {DEEP_RAISED}; color: {TEXT_DIM}; padding: 10px 18px;
    border-top-left-radius: 8px; border-top-right-radius: 8px; margin-right: 2px;
}}
QTabBar::tab:selected {{ background: {TEAL}; color: {PAPER}; }}
QHeaderView::section {{ background: {DEEP_RAISED}; color: {TEXT_DIM};
    border: none; padding: 8px; }}
QTableWidget {{ gridline-color: {TEAL}; }}
QScrollBar:vertical {{ background: {DEEP}; width: 12px; }}
QScrollBar::handle:vertical {{ background: {TEAL}; border-radius: 6px; min-height: 30px; }}
QToolTip {{ background: {INK}; color: {PAPER}; border: 1px solid {TEAL_LIGHT}; }}
"""
