"""Filesystem locations: data directory (per-user), brand assets and bundled resources.

Windows-first: the data directory is ``%LOCALAPPDATA%\\SellAgent`` (same rule as the backend's
``sellagent_backend.config.default_data_dir``) so the desktop app and the backend child process agree.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    """Directory holding the executable (frozen) or the monorepo root (source checkout)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def bundle_root() -> Path:
    """PyInstaller one-dir internal folder (``_internal``) or the repo root in development."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", app_root()))
    return app_root()


def data_dir() -> Path:
    if env := os.environ.get("SELLAGENT_DATA_DIR"):
        return Path(env)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "SellAgent"
    return Path.home() / ".local" / "share" / "sellagent"


def resources_dir() -> Path:
    cands = [bundle_root() / "resources", Path(__file__).resolve().parents[1] / "resources"]
    for c in cands:
        if c.exists():
            return c
    return cands[-1]


def brand_dir() -> Path | None:
    cands = [bundle_root() / "packages" / "brand", app_root() / "packages" / "brand"]
    for c in cands:
        if (c / "qt" / "theme.qss").exists():
            return c
    return None


def theme_qss_path() -> Path | None:
    b = brand_dir()
    if b is not None:
        return b / "qt" / "theme.qss"
    r = resources_dir() / "theme.qss"
    return r if r.exists() else None


def logo_svg_path() -> Path | None:
    b = brand_dir()
    for c in ([b / "assets" / "fitron_mark.svg"] if b else []) + [resources_dir() / "fitron_mark.svg"]:
        if c.exists():
            return c
    return None


def app_icon_path() -> Path | None:
    for name in ("sellagent.ico", "icons/sellagent_256.png"):
        p = resources_dir() / name
        if p.exists():
            return p
    return None


def first_run_flag() -> Path:
    return data_dir() / "desktop_first_run_done"
