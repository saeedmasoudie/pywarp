from __future__ import annotations

import logging
import os
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import (
    QCoreApplication,
    QObject,
    QStandardPaths,
    QUrl,
    Signal,
)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from backend.app_controller import AppController
from backend.tray_service import TrayService


ROOT = Path(__file__).resolve().parent
INSTANCE_SERVER_NAME = "PyWarp-single-instance"


class SingleInstance(QObject):
    activateRequested = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._server = QLocalServer(self)
        self._server.setSocketOptions(
            QLocalServer.SocketOption.UserAccessOption
        )
        self._server.newConnection.connect(self._accept_connections)

    def acquire(self) -> bool:
        probe = QLocalSocket()
        probe.connectToServer(INSTANCE_SERVER_NAME)
        if probe.waitForConnected(300):
            probe.write(b"activate")
            probe.waitForBytesWritten(300)
            probe.disconnectFromServer()
            return False

        QLocalServer.removeServer(INSTANCE_SERVER_NAME)
        if self._server.listen(INSTANCE_SERVER_NAME):
            return True

        probe.connectToServer(INSTANCE_SERVER_NAME)
        if probe.waitForConnected(300):
            probe.write(b"activate")
            probe.waitForBytesWritten(300)
            probe.disconnectFromServer()
        return False

    def _accept_connections(self) -> None:
        while self._server.hasPendingConnections():
            connection = self._server.nextPendingConnection()
            if connection is not None:
                connection.disconnectFromServer()
                connection.deleteLater()
        self.activateRequested.emit()


def configure_windows_identity() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "PyWarp.PyWarp"
        )
    except (AttributeError, OSError):
        logging.warning("Could not set the Windows application identity.")


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
    configure_windows_identity()
    QCoreApplication.setOrganizationName("PyWarp")
    QCoreApplication.setApplicationName("PyWarp")
    QApplication.setDesktopFileName("pywarp")

    app = QApplication(sys.argv)
    app.setApplicationDisplayName("PyWarp")
    single_instance = SingleInstance(app)
    if not single_instance.acquire():
        return 0

    png_logo = ROOT / "assets" / "logo.png"
    logo_path = png_logo if png_logo.exists() else ROOT / "assets" / "logo.svg"
    app_icon = QIcon(str(logo_path))
    app.setWindowIcon(app_icon)

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
    window = engine.rootObjects()[0]
    window.setIcon(app_icon)

    def activate_window() -> None:
        window.showNormal()
        window.raise_()
        window.requestActivate()

    single_instance.activateRequested.connect(activate_window)
    tray_service.set_window(window)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
