from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QStandardPaths, QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from backend.app_controller import AppController
from backend.tray_service import TrayService


ROOT = Path(__file__).resolve().parent


def configure_logging() -> Path:
    native_data_dir = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppLocalDataLocation
    )
    data_dir = (
        Path(native_data_dir)
        if native_data_dir
        else Path.home() / ".pywarp"
    )
    data_dir.mkdir(parents=True, exist_ok=True)
    log_path = data_dir / "pywarp.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return log_path


def main() -> int:
    QCoreApplication.setOrganizationName("PyWarp")
    QCoreApplication.setApplicationName("PyWarp")
    QApplication.setDesktopFileName("pywarp")

    app = QApplication(sys.argv)
    app.setApplicationDisplayName("PyWarp")
    png_logo = ROOT / "assets" / "logo.png"
    logo_path = png_logo if png_logo.exists() else ROOT / "assets" / "logo.svg"
    app.setWindowIcon(QIcon(str(logo_path)))

    controller = AppController(configure_logging())

    def handle_exception(exc_type, exc_value, tb) -> None:
        if exc_type is KeyboardInterrupt:
            return
        message = "".join(
            traceback.format_exception(exc_type, exc_value, tb)
        )
        logging.critical(message)
        controller.recordCriticalError(str(exc_value))

    sys.excepthook = handle_exception
    tray_service = TrayService(controller, logo_path)
    app.setQuitOnLastWindowClosed(not tray_service.available)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("AppController", controller)
    engine.rootContext().setContextProperty("TrayService", tray_service)
    engine.load(QUrl.fromLocalFile(str(ROOT / "qml" / "Main.qml")))
    if not engine.rootObjects():
        return 1
    tray_service.set_window(engine.rootObjects()[0])
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
