#!/usr/bin/env python
"""Build the Windows desktop distribution.

Steps (each can be run alone with ``--only``):
  icons      rasterise packages/brand/assets/fitron_mark.svg into resources/icons/*.png + resources/sellagent.ico
  theme      copy packages/brand/qt/theme.qss and the SVG into apps/windows-desktop/resources (bundled fallback)
  pyinstaller run PyInstaller with scripts/sellagent.spec  -> dist/SellAgent/ (portable folder)
  installer  compile scripts/installer.iss with Inno Setup -> dist/SellAgent-Setup-<version>.exe

Run on Windows 11 with the project venv active:  python scripts/build_windows.py
"""

from __future__ import annotations

import argparse
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "apps" / "windows-desktop" / "resources"
BRAND = ROOT / "packages" / "brand"
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def _version() -> str:
    sys.path.insert(0, str(ROOT / "apps" / "windows-desktop"))
    from sellagent_desktop import APP_VERSION

    return APP_VERSION


def make_icons() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QBuffer, QIODevice, QSize, Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841
    svg = BRAND / "assets" / "fitron_mark.svg"
    out = RES / "icons"
    out.mkdir(parents=True, exist_ok=True)
    renderer = QSvgRenderer(str(svg))
    pngs: list[tuple[int, bytes]] = []
    for size in ICON_SIZES:
        img = QImage(QSize(size, size), QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(p)
        p.end()
        path = out / f"sellagent_{size}.png"
        img.save(str(path), "PNG")
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        pngs.append((size, bytes(buf.data())))
        print("wrote", path)
    # ICO container with PNG-compressed entries (supported since Windows Vista).
    ico = RES / "sellagent.ico"
    header = struct.pack("<HHH", 0, 1, len(pngs))
    offset = 6 + 16 * len(pngs)
    entries, blobs = b"", b""
    for size, data in pngs:
        entries += struct.pack("<BBBBHHII", size if size < 256 else 0, size if size < 256 else 0, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    ico.write_bytes(header + entries + blobs)
    print("wrote", ico)


def copy_theme() -> None:
    RES.mkdir(parents=True, exist_ok=True)
    for src, dst in ((BRAND / "qt" / "theme.qss", RES / "theme.qss"), (BRAND / "assets" / "fitron_mark.svg", RES / "fitron_mark.svg")):
        shutil.copyfile(src, dst)
        print("copied", src, "->", dst)


def run_pyinstaller() -> None:
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(ROOT / "scripts" / "sellagent.spec")]
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)


def run_installer() -> None:
    iscc = shutil.which("ISCC") or shutil.which("iscc")
    for cand in (r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe", r"C:\Program Files\Inno Setup 6\ISCC.exe"):
        if not iscc and Path(cand).exists():
            iscc = cand
    if not iscc:
        raise SystemExit("Inno Setup (ISCC.exe) not found. Install from https://jrsoftware.org/isinfo.php or `choco install innosetup`.")
    cmd = [iscc, f"/DAppVersion={_version()}", str(ROOT / "scripts" / "installer.iss")]
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["icons", "theme", "pyinstaller", "installer"], action="append")
    a = ap.parse_args()
    steps = a.only or ["icons", "theme", "pyinstaller", "installer"]
    for s in steps:
        {"icons": make_icons, "theme": copy_theme, "pyinstaller": run_pyinstaller, "installer": run_installer}[s]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
