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
QWizard, QWizardPage { background-color: #0B0B0B; }
QListWidget::item:selected, QTreeView::item:selected { background-color: #8A7124; color: #F5F0E1; }
QToolButton { background-color: #1C1C1C; color: #F5F0E1; border: 1px solid #2A2A2A; border-radius: 6px; padding: 4px 8px; }
QToolButton:hover { border-color: #D4AF37; }
QCalendarWidget QWidget { background-color: #141414; color: #F5F0E1; alternate-background-color: #1C1C1C; }
QCalendarWidget QAbstractItemView:enabled { selection-background-color: #D4AF37; selection-color: #0B0B0B; }
QLabel[role="pill"] { background-color: #1C1C1C; border: 1px solid #2A2A2A; border-radius: 10px; padding: 2px 8px; color: #B8B2A0; }
QLabel[role="pill-gold"] { background-color: #1C1C1C; border: 1px solid #D4AF37; border-radius: 10px; padding: 2px 8px; color: #D4AF37; font-weight: 600; }
QLabel[role="state"] { color: #D4AF37; font-size: 28px; font-weight: 700; letter-spacing: 1px; }
QLabel[role="pairing-code"] { color: #D4AF37; font-size: 44px; font-weight: 700; letter-spacing: 8px; }
QLabel[role="agent-line"] { color: #F5F0E1; font-size: 16px; background-color: #141414; border: 1px solid #D4AF37; border-radius: 10px; padding: 12px; }
QTextEdit[invalid="true"], QPlainTextEdit[invalid="true"], QComboBox[invalid="true"], QDateTimeEdit[invalid="true"] { border-color: #E05252; }
QFrame[role="danger-banner"] { background-color: #C62828; border-radius: 8px; }
QFrame[role="danger-banner"] QLabel { color: #FFFFFF; font-weight: 700; background: transparent; }
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
