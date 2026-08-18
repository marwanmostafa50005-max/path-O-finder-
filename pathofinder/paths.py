"""Application data locations.

All persistent state lives under a single per-machine application data root:
Windows: %PROGRAMDATA%\\path-O-finder  (practice-wide, one DB per machine)
Other:   ~/.local/share/path-O-finder  (dev/CI)

Override with PATHOFINDER_DATA_DIR (used by tests).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    env = os.environ.get("PATHOFINDER_DATA_DIR")
    if env:
        root = Path(env)
    elif sys.platform == "win32":
        root = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "path-O-finder"
    else:
        root = Path.home() / ".local" / "share" / "path-O-finder"
    root.mkdir(parents=True, exist_ok=True)
    return root


def db_path() -> Path:
    return data_dir() / "pathofinder.db"


def inbox_dir() -> Path:
    d = data_dir() / "inbox_readonly"
    d.mkdir(parents=True, exist_ok=True)
    return d


def quarantine_dir() -> Path:
    d = data_dir() / "quarantine"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_dir() -> Path:
    d = data_dir() / "config"
    d.mkdir(parents=True, exist_ok=True)
    return d


def resources_dir() -> Path:
    """Bundled read-only resources (works from source and from PyInstaller)."""
    if getattr(sys, "_MEIPASS", None):  # PyInstaller onedir/onefile
        return Path(sys._MEIPASS) / "pathofinder" / "resources"  # type: ignore[attr-defined]
    return Path(__file__).parent / "resources"
