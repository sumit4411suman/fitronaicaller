# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: SellAgent.exe (windowed desktop) + sellagent-backend.exe (no console window) in one folder.

Build:  python -m PyInstaller --noconfirm --clean scripts/sellagent.spec
Output: dist/SellAgent/  (portable folder; the Inno Setup script packages it)
"""

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent
sys.path[:0] = [str(ROOT / p) for p in ("services/local-backend", "services/ai-engine", "services/speech-engine", "services/knowledge-base", "packages/shared-protocol", "apps/windows-desktop")]

pathex = [str(ROOT / p) for p in ("services/local-backend", "services/ai-engine", "services/speech-engine", "services/knowledge-base", "packages/shared-protocol", "apps/windows-desktop")]

shared_datas = [
    (str(ROOT / "database" / "migrations"), "database/migrations"),
    (str(ROOT / "alembic.ini"), "."),
    (str(ROOT / "packages" / "brand" / "qt"), "packages/brand/qt"),
    (str(ROOT / "packages" / "brand" / "assets"), "packages/brand/assets"),
    (str(ROOT / "packages" / "brand" / "tokens.json"), "packages/brand"),
    (str(ROOT / "apps" / "windows-desktop" / "resources"), "resources"),
    (str(ROOT / "packages" / "shared-protocol" / "schema"), "packages/shared-protocol/schema"),
]
shared_datas += collect_data_files("alembic", includes=["templates/**/*", "script.py.mako"])

backend_hidden = (
    collect_submodules("sellagent_backend") + collect_submodules("sellagent_ai") + collect_submodules("sellagent_kb")
    + collect_submodules("sellagent_speech") + collect_submodules("sellagent_protocol")
    + ["uvicorn.logging", "uvicorn.loops.auto", "uvicorn.loops.asyncio", "uvicorn.protocols.http.auto", "uvicorn.protocols.http.h11_impl",
       "uvicorn.protocols.http.httptools_impl", "uvicorn.protocols.websockets.auto", "uvicorn.protocols.websockets.websockets_impl",
       "uvicorn.protocols.websockets.wsproto_impl", "uvicorn.lifespan.on", "uvicorn.lifespan.off", "sqlalchemy.dialects.sqlite",
       "alembic.runtime.migration", "phonenumbers", "openpyxl", "multipart", "python_multipart", "cryptography"]
)
desktop_hidden = collect_submodules("sellagent_desktop") + ["websockets", "websockets.asyncio.client", "httpx", "PySide6.QtSvg"]

block_cipher = None

backend_a = Analysis(
    [str(ROOT / "services" / "local-backend" / "sellagent_backend" / "main.py")],
    pathex=pathex, binaries=[], datas=shared_datas, hiddenimports=backend_hidden, hookspath=[], runtime_hooks=[],
    excludes=["PySide6", "shiboken6", "tkinter", "matplotlib", "torch"], cipher=block_cipher, noarchive=False,
)
desktop_a = Analysis(
    [str(ROOT / "apps" / "windows-desktop" / "sellagent_desktop" / "main.py")],
    pathex=pathex, binaries=[], datas=shared_datas, hiddenimports=desktop_hidden, hookspath=[], runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "torch", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.Qt3DCore"],
    cipher=block_cipher, noarchive=False,
)

MERGE((desktop_a, "SellAgent", "SellAgent"), (backend_a, "sellagent-backend", "sellagent-backend"))

ICON = str(ROOT / "apps" / "windows-desktop" / "resources" / "sellagent.ico")
if not os.path.exists(ICON):
    ICON = None

desktop_pyz = PYZ(desktop_a.pure, desktop_a.zipped_data, cipher=block_cipher)
desktop_exe = EXE(
    desktop_pyz, desktop_a.scripts, [], exclude_binaries=True, name="SellAgent", debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False, icon=ICON, version=None,
)
backend_pyz = PYZ(backend_a.pure, backend_a.zipped_data, cipher=block_cipher)
backend_exe = EXE(
    backend_pyz, backend_a.scripts, [], exclude_binaries=True, name="sellagent-backend", debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False, icon=ICON,  # console=False: no black window; stdout goes to <data>/logs/backend-child.log
)
coll = COLLECT(
    desktop_exe, desktop_a.binaries, desktop_a.zipfiles, desktop_a.datas,
    backend_exe, backend_a.binaries, backend_a.zipfiles, backend_a.datas,
    strip=False, upx=False, upx_exclude=[], name="SellAgent",
)
