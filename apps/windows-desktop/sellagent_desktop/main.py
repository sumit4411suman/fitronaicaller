"""Entry point: ``python -m sellagent_desktop.main`` or the frozen SellAgent.exe."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler

from sellagent_desktop import APP_NAME, APP_VERSION, paths


def _setup_logging() -> None:
    d = paths.data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        handlers.append(RotatingFileHandler(d / "desktop.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=handlers)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=f"{APP_NAME} desktop")
    ap.add_argument("--version", action="store_true")
    ap.add_argument("--no-wizard", action="store_true", help="skip the first-run wizard check")
    ap.add_argument("--backend-url", default=None, help="connect to a running backend instead of starting one")
    args = ap.parse_args(argv)
    if args.version:
        print(APP_VERSION)
        return 0
    if args.backend_url:
        os.environ["SELLAGENT_BACKEND_URL"] = args.backend_url
    _setup_logging()
    log = logging.getLogger("sellagent.desktop")
    os.environ.setdefault("QT_LOGGING_RULES", "qt.text.font.db=false")  # silence harmless font-table notices

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QMessageBox, QSplashScreen

    from sellagent_desktop.api_client import ApiClient, call_async
    from sellagent_desktop.backend_process import BackendProcess
    from sellagent_desktop.context import AppContext
    from sellagent_desktop.main_window import MainWindow
    from sellagent_desktop.screens.setup_wizard import SetupWizard, needs_first_run
    from sellagent_desktop.theme import apply_theme, logo_pixmap
    from sellagent_desktop.ws_client import WsClient

    QApplication.setApplicationName(APP_NAME)
    QApplication.setApplicationVersion(APP_VERSION)
    QApplication.setOrganizationName("FITRON")
    app = QApplication(sys.argv[:1])
    apply_theme(app)

    splash = QSplashScreen(logo_pixmap(220))
    splash.showMessage("Starting local backend…", Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter, Qt.GlobalColor.white)
    splash.show()
    app.processEvents()

    bp = BackendProcess()
    result: dict = {}

    def _start() -> None:
        try:
            result["url"] = bp.start()
        except Exception as exc:  # noqa: BLE001
            result["error"] = exc

    t = threading.Thread(target=_start, daemon=True)
    t.start()
    while t.is_alive():
        app.processEvents()
        t.join(0.05)
    splash.close()
    if "error" in result:
        err = result["error"]
        log.error("backend start failed: %s", err)
        box = QMessageBox(QMessageBox.Icon.Critical, f"{APP_NAME} cannot start", f"The local backend could not be started.\n\n{err}\n\nLog: {bp.log_path}")
        box.exec()
        return 1

    api = ApiClient(bp.base_url, bp.token or "")
    ws = WsClient(api.ws_url())
    ws.start()
    ctx = AppContext(api=api, ws=ws, data_dir=bp.data_dir, backend_url=bp.base_url, backend_owned=bp.owns_process)
    win = MainWindow(ctx)
    win.show()

    def _shutdown() -> None:
        ws.stop()
        bp.stop()
        api.close()

    app.aboutToQuit.connect(_shutdown)

    if not args.no_wizard and os.environ.get("SELLAGENT_DESKTOP_SKIP_WIZARD") != "1":
        def _check(settings: dict) -> None:
            ctx.settings_cache.update(settings.get("values", {}))
            if needs_first_run(ctx.settings_cache):
                SetupWizard(ctx, win).exec()

        call_async(lambda: api.get("/settings"), _check, lambda e: log.warning("first-run check failed: %s", e))

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
