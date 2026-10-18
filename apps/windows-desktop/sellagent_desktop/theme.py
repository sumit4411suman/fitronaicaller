"""Apply the FITRON brand theme: the brand QSS is loaded VERBATIM, plus the Devanagari-capable font fallback list."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont, QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

from sellagent_desktop import paths

FONT_FAMILIES = ["Segoe UI", "Segoe UI Variable", "Noto Sans", "Noto Sans Devanagari", "Nirmala UI", "Mangal", "sans-serif"]
MIN_POINT_SIZE = 10  # ~13px at 96 dpi; accessibility floor

# Minimal additions for widget types the brand sheet does not mention. Only brand colours are used.
SUPPLEMENT_QSS = """
QLabel[role="pill"] { background-color: #F0EEE6; border: 1px solid #E6E2D6; border-radius: 10px; padding: 2px 8px; color: #6B665A; font-size: 11px; }
QLabel[role="pill-gold"] { background-color: #FFFFFF; border: 1px solid #D4AF37; border-radius: 10px; padding: 2px 8px; color: #B8962E; font-weight: 600; font-size: 11px; }
QLabel[role="state"] { color: #B8962E; font-size: 26px; font-weight: 800; letter-spacing: 1px; }
QLabel[role="pairing-code"] { color: #B8962E; font-size: 44px; font-weight: 800; letter-spacing: 8px; }
QLabel[role="agent-line"] { color: #1A1A1A; font-size: 16px; background-color: #FFFFFF; border: 2px solid #D4AF37; border-radius: 12px; padding: 12px; }
QLabel[role="avatar"] { background-color: #D4AF37; color: #0B0B0B; border-radius: 28px; font-size: 20px; font-weight: 800; min-width: 56px; max-width: 56px; min-height: 56px; max-height: 56px; }
QLabel[role="avatar-small"] { background-color: #D4AF37; color: #0B0B0B; border-radius: 16px; font-size: 12px; font-weight: 800; min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px; }
QLabel[role="greeting"] { color: #1A1A1A; font-size: 24px; font-weight: 800; }
QLabel[role="card-title"] { color: #1A1A1A; font-size: 14px; font-weight: 700; }
QTextEdit[invalid="true"], QPlainTextEdit[invalid="true"], QComboBox[invalid="true"], QDateTimeEdit[invalid="true"] { border: 2px solid #C62828; }
QFrame[role="danger-banner"] { background-color: #C62828; border-radius: 8px; }
QFrame[role="danger-banner"] QLabel { color: #FFFFFF; font-weight: 700; background: transparent; }
QFrame[role="card-dark"] QPushButton { background-color: #1C1C1C; color: #F5F0E1; border: 1px solid #2A2A2A; }
QFrame[role="card-dark"] QPushButton[role="primary"] { background-color: #D4AF37; color: #0B0B0B; border: none; }
QFrame[role="card-dark"] QLabel[role="caption"] { color: #B8B2A0; }
QFrame[role="card-dark"] QLabel[role="success"] { color: #4CAF50; }
QFrame[role="card-dark"] QLabel[role="danger"] { color: #E05252; }
QFrame[role="card-dark"] QLabel[role="warning"] { color: #E6A23C; }
QFrame#Header QLabel[role="caption"] { background: transparent; }
QFrame#Header QPushButton[role="danger"] { min-height: 30px; }
QPushButton[role="chip"] { background-color: #FFFFFF; color: #6B665A; border: 1px solid #E6E2D6; border-radius: 14px; padding: 4px 12px; }
QPushButton[role="chip"]:checked { background-color: #D4AF37; color: #0B0B0B; border-color: #D4AF37; font-weight: 700; }
QSplashScreen { background-color: #0B0B0B; }
QPushButton[role="success"]:disabled, QPushButton[role="danger"]:disabled, QPushButton[role="secondary"]:disabled { background-color: #F0EEE6; color: #A8A396; border: 1px solid #E6E2D6; }
QPushButton[role="quick"] { min-height: 44px; }
"""


def load_theme_text() -> str:
    p = paths.theme_qss_path()
    base = p.read_text(encoding="utf-8") if p else ""
    return base + "\n" + SUPPLEMENT_QSS


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")  # consistent base so the stylesheet renders identically on every Windows build
    app.setStyleSheet(load_theme_text())
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPointSize(MIN_POINT_SIZE)
    app.setFont(font)
    QFont.insertSubstitutions("Segoe UI", ["Nirmala UI", "Noto Sans Devanagari", "Mangal"])
    icon = app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)


def render_svg(path: Path, size: int) -> QPixmap:
    renderer = QSvgRenderer(str(path))
    img = QImage(QSize(size, size), QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    renderer.render(painter)
    painter.end()
    return QPixmap.fromImage(img)


def logo_pixmap(size: int = 64) -> QPixmap:
    p = paths.logo_svg_path()
    if p is None:
        return QPixmap()
    return render_svg(p, size)


def app_icon() -> QIcon:
    ip = paths.app_icon_path()
    if ip is not None:
        return QIcon(str(ip))
    icon = QIcon()
    for s in (16, 32, 48, 64, 128, 256):
        pm = logo_pixmap(s)
        if not pm.isNull():
            icon.addPixmap(pm)
    return icon
