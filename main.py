import asyncio
import base64
import ipaddress
import json
import logging
import os
import platform
import re
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
import zipfile
import requests
import resources_rc
from types import SimpleNamespace
from pathlib import Path
from PySide6.QtNetwork import QLocalSocket, QLocalServer
from PySide6.QtCore import Qt, QThread, Signal, QEvent, QObject, QSettings, QTimer, QVariantAnimation, QEasingCurve, \
    QTranslator, QCoreApplication, QPropertyAnimation, QAbstractAnimation, QProcess, QSize
from PySide6.QtGui import QFont, QPalette, QIcon, QAction, QColor, QBrush, QActionGroup, QTextCursor, QPainter, QPen, \
    QPixmap
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QPushButton, QLabel, QFrame, QStackedWidget,
                               QGraphicsDropShadowEffect, QMessageBox, QSizePolicy, QSystemTrayIcon, QMenu, QComboBox,
                               QLineEdit, QGridLayout, QTableWidget, QAbstractItemView, QTableWidgetItem, QHeaderView,
                               QGroupBox, QDialog, QListWidget, QProgressDialog, QInputDialog, QCheckBox,
                               QTextEdit, QFontComboBox)

CURRENT_VERSION = "1.2.7"
GITHUB_VERSION_URL = "https://raw.githubusercontent.com/saeedmasoudie/pywarp/main/version.txt"
WARP_ASSETS = f"https://github.com/saeedmasoudie/pywarp/releases/download/v{CURRENT_VERSION}/warp_assets.zip"
SERVER_NAME = "PyWarpInstance"
server = QLocalServer()


# ------------------- Utilities ----------------------

def format_seconds_to_hms(seconds):
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02}:{m:02}:{s:02}"

def to_bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(v)

def get_current_protocol():
    try:
        process = run_warp_command('warp-cli', 'settings')

        if process.returncode != 0:
            return "Error"

        output = process.stdout
        for line in output.splitlines():
            if "WARP tunnel protocol:" in line:
                return line.split(":")[1].strip()
        return "Unknown"
    except Exception as e:
        logger.error(f"Error fetching current protocol: {e}")
        return "Error"

def handle_exception(exc_type, exc_value, exc_traceback):
    if exc_type is KeyboardInterrupt:
        sys.exit(0)

    error_dialog = QMessageBox()
    error_dialog.setIcon(QMessageBox.Critical)
    error_dialog.setWindowTitle(QCoreApplication.translate("MainWindow", "Application Error"))
    error_dialog.setText(QCoreApplication.translate("MainWindow", "An unexpected error occurred!"))
    error_dialog.setDetailedText("".join(
        traceback.format_exception(exc_type, exc_value, exc_traceback)))
    error_dialog.exec()

def safe_subprocess_args():
    if platform.system() == "Windows":
        return {"shell": False, "creationflags": subprocess.CREATE_NO_WINDOW}
    return {"shell": False}

def get_warp_cli_executable() -> str | None:
    system_path = shutil.which("warp-cli")
    if system_path:
        return system_path

    if platform.system() == "Windows":
        portable_path = Path(os.getenv("APPDATA", "")) / "pywarp" / "warp" / "warp-cli.exe"
    else:
        portable_path = Path.home() / ".pywarp" / "warp" / "warp-cli"

    if portable_path.exists():
        return str(portable_path)

    logger.warning("warp-cli executable not found in system PATH or portable directory.")
    return None

def run_warp_command(*args):
    warp_cli_path = get_warp_cli_executable()
    if not warp_cli_path:
        return SimpleNamespace(returncode=-1, stdout="", stderr="warp-cli executable not found")

    command = [warp_cli_path] + list(args[1:])

    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=30, **safe_subprocess_args()
        )
        return result
    except subprocess.TimeoutExpired:
        logger.error(f"Command timeout: {' '.join(args)}")
        return SimpleNamespace(returncode=-1, stdout="", stderr="timeout")
    except Exception as e:
        logger.error(f"Command failed: {' '.join(args)}: {e}")
        return SimpleNamespace(returncode=-1, stdout="", stderr=str(e))

def notify_update(update_type, latest_version, current_version):
    app = QApplication.instance()
    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Information)
    msg_box.setWindowTitle(app.translate("UpdateChecker", "Update Available"))
    manual_update_button = msg_box.addButton(app.translate("UpdateChecker", "Update"), QMessageBox.ActionRole)
    msg_box.addButton(app.translate("UpdateChecker", "Later"), QMessageBox.RejectRole)

    if update_type == "pywarp":
        msg_box.setText(
            app.translate("UpdateChecker", "A new version of PyWarp is available!\n\nLatest: {}\nCurrent: {}").format(
                latest_version, current_version))

    elif update_type == "warp_installed":
        msg_box.setText(
            app.translate("UpdateChecker", "A new version of WARP is available!\n\nLatest: {}\nCurrent: {}").format(
                latest_version, current_version))

    elif update_type == "warp_portable":
        msg_box.setText(
            app.translate("UpdateChecker",
                          "A new version of portable WARP is available!\n\nLatest: {}\nCurrent: {}").format(
                latest_version, current_version))
        auto_update_button = msg_box.addButton(app.translate("UpdateChecker", "Auto Update"), QMessageBox.AcceptRole)
        msg_box.setDefaultButton(auto_update_button)
        msg_box.removeButton(manual_update_button)

    msg_box.exec()
    clicked_button = msg_box.clickedButton()

    if clicked_button == manual_update_button:
        webbrowser.open("https://github.com/saeedmasoudie/pywarp/releases")
    elif 'auto_update_button' in locals() and clicked_button == auto_update_button:
        update_thread = threading.Thread(target=update_checker.perform_portable_warp_update, daemon=True)
        update_thread.start()

def handle_new_connection(main_window_class):
    client = server.nextPendingConnection()
    if client and client.waitForReadyRead(100):
        msg = client.readAll().data().decode()
        if msg == "SHOW" and main_window_class.instance:
            main_window_class.instance.showNormal()
            main_window_class.instance.raise_()
            main_window_class.instance.activateWindow()

def check_existing_instance(main_window_class=None):
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)

    if socket.waitForConnected(500):
        if "--restarting" in sys.argv:
            for _ in range(10):
                time.sleep(0.5)
                socket.connectToServer(SERVER_NAME)
                if not socket.waitForConnected(100):
                    logger.info("Graceful restart successful: old instance closed.")
                    return
            logger.warning("Restart failed: The previous instance did not close in time.")
            sys.exit(1)
        else:
            socket.write(b"SHOW")
            socket.flush()
            socket.waitForBytesWritten(100)
            logger.info("Another instance is running. Activating it instead of starting new.")
            sys.exit(0)
    else:
        if main_window_class:
            server.removeServer(SERVER_NAME)
            if not server.listen(SERVER_NAME):
                logger.error("Failed to start local server for single instance.")
            else:
                server.newConnection.connect(lambda: handle_new_connection(main_window_class))

def setup_logger():
    global LOG_PATH

    log_dir = os.path.join(os.path.expanduser("~"), ".pywarp")
    os.makedirs(log_dir, exist_ok=True)

    LOG_PATH = os.path.join(log_dir, "pywarp.log")

    logger = logging.getLogger("pywarp")
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        fh = logging.FileHandler(LOG_PATH, mode="a", encoding="utf-8")
        fh.setLevel(logging.DEBUG)

        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)

        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        fh.setFormatter(fmt)
        ch.setFormatter(fmt)

        logger.addHandler(fh)
        logger.addHandler(ch)

    return logger, LOG_PATH

def get_log_path():
    return LOG_PATH

def load_language(app, lang_code="en", settings_handler=None):
    if hasattr(app, "_translator") and app._translator:
        app.removeTranslator(app._translator)
        app._translator = None

    if lang_code == "en":
        if settings_handler:
            settings_handler.save_settings("language", lang_code)
        app.setLayoutDirection(Qt.LeftToRight)
        return None

    qm_resource_path = f":/translations/{lang_code}.qm"
    translator = QTranslator()
    if translator.load(qm_resource_path):
        app.installTranslator(translator)
        app._translator = translator
        if settings_handler:
            settings_handler.save_settings("language", lang_code)
        if lang_code in ["fa", "ar", "he", "ur"]:
            app.setLayoutDirection(Qt.RightToLeft)
        else:
            app.setLayoutDirection(Qt.LeftToRight)
        logger.info(f"Language switched to {lang_code}")
        return translator
    else:
        logger.warning(f"Failed to load translation file from resources for {lang_code}")
        return None

def load_saved_language(app, settings_handler):
    saved_lang = settings_handler.get("language", "en")
    return load_language(app, saved_lang, settings_handler)

def fetch_protocol():
    try:
        res = run_warp_command("warp-cli", "settings")
        if res and res.returncode == 0:
            out = res.stdout
            for line in out.splitlines():
                if "WARP tunnel protocol:" in line:
                    return line.split(":", 1)[1].strip()
            return "Unknown"
        return "Error"
    except Exception as e:
        logger.error(f"fetch_protocol failed: {e}")
        return "Error"

def run_in_worker(func, *args, parent=None, on_done=None, on_error=None, **kwargs):
    worker = GenericWorker(func, *args, parent=parent, **kwargs)
    if on_done:
        worker.finished_signal.connect(on_done)
    if on_error:
        worker.error_signal.connect(on_error)
    worker.start()
    return worker

# -----------------------------------------------------

class ThemeManager:
    @staticmethod
    def is_dark_mode():
        palette = QApplication.palette()
        return palette.color(QPalette.Window).lightness() < 128

    @staticmethod
    def apply(font_name="Segoe UI", font_size=13):
        app = QApplication.instance()
        if not app:
            return

        app.setFont(QFont(font_name, font_size))

        if ThemeManager.is_dark_mode():
            app.setStyleSheet(ThemeManager.dark_theme(font_name))
        else:
            app.setStyleSheet(ThemeManager.light_theme(font_name))

    @staticmethod
    def dark_theme(font_name):
        return """
        QWidget {{
            background-color: #0d1117;
            color: #f0f6fc;
            font-size: 13px;
            font-family: "{font_name}", "Segoe UI", "Arial", sans-serif;
        }}
        QMainWindow {{ background-color: #0d1117; }}
        QLabel {{ font-size: 14px; font-weight: 500; }}

        /* GroupBox */
        QGroupBox {{
            font-size: 16px;
            font-weight: 600;
            border: 1px solid #30363d;
            border-radius: 12px;
            padding: 12px;
            margin-top: 10px;
        }}
        QGroupBox::title {{ color: #58a6ff; left: 10px; padding: 0 5px; }}

        /* Buttons */
        QPushButton {{
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #238636, stop:1 #1f7a2e);
            color: white;
            border-radius: 8px;
            padding: 8px 16px;
            font-weight: 600;
            border: none;
        }}
        QPushButton:hover {{
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #2ea043, stop:1 #238636);
        }}
        QPushButton:pressed {{
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #1f7a2e, stop:1 #1a6928);
        }}

        /* Inputs */
        QComboBox, QLineEdit, QTextEdit, QSpinBox {{
            background-color: #21262d;
            color: #f0f6fc;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 6px 8px;
        }}
        QComboBox:hover, QLineEdit:hover, QTextEdit:hover, QSpinBox:hover {{
            border-color: #58a6ff;
        }}
        QComboBox::down-arrow {{
            image: none;
            border: 2px solid #f0f6fc;
            width: 6px; height: 6px;
            border-top: none; border-left: none;
            transform: rotate(45deg);
        }}

        /* Tables / Lists */
        QTableWidget, QListWidget {{
            background-color: #0d1117;
            alternate-background-color: #161b22;
            color: #f0f6fc;
            border: 1px solid #30363d;
            border-radius: 8px;
        }}
        QTableWidget::item, QListWidget::item {{
            padding: 6px;
            border-bottom: 1px solid #21262d;
        }}
        QListWidget::item:hover {{ background-color: #161b22; }}
        QListWidget::item:selected {{ background-color: #1f6feb; }}

        QHeaderView::section {{
            background: #21262d;
            color: #f0f6fc;
            font-weight: 600;
            padding: 8px;
            border: none;
            border-right: 1px solid #30363d;
        }}

        /* Dialogs & MessageBox */
        QDialog, QMessageBox {{
            background-color: #161b22;
            color: #f0f6fc;
            border: 1px solid #30363d;
            border-radius: 12px;
        }}
        QMessageBox QLabel {{
            background: transparent;
            color: white;
            font-size: 14px;
            border: none;
        }}
        QMessageBox QPushButton {{
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #238636, stop:1 #1f7a2e);
            color: white;
            border-radius: 6px;
            padding: 6px 14px;
            font-weight: 600;
        }}
        QMessageBox QPushButton:hover {{
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #2ea043, stop:1 #238636);
        }}
        QCheckBox {{
            background: transparent;
            color: white;
        }}
        QMenu {{
            background-color: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 6px;
        }}
        QMenu::item {{
            padding: 6px 20px;
            color: #f0f6fc;
            border-radius: 6px;
        }}
        QMenu::item:selected {{
            background-color: #238636;   /* hover effect */
            color: white;
        }}
        QMenu::separator {{
            height: 1px;
            background: #30363d;
            margin: 4px 0;
        }}
        """.format(font_name=font_name)

    @staticmethod
    def light_theme(font_name):
        return """
        QWidget {{
            background-color: #f4f6f8;
            color: #1a1f24;
            font-size: 13px;
            font-family: "{font_name}", "Segoe UI", "Arial", sans-serif;
        }}
        QMainWindow {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #f9fafb, stop:1 #f0f2f4);
        }}
        QLabel {{
            font-size: 14px;
            font-weight: 500;
            color: #1a1f24;
        }}
        QGroupBox {{
            font-size: 16px;
            font-weight: 600;
            border: 1px solid #d0d7de;
            border-radius: 12px;
            padding: 12px;
            margin-top: 10px;
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                        stop:0 #ffffff, stop:1 #f6f8fa);
        }}
        QGroupBox::title {{ color: #2563eb; left: 10px; padding: 0 5px; }}
        QPushButton {{
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                        stop:0 #3b82f6, stop:1 #2563eb);
            color: white;
            border-radius: 8px;
            padding: 8px 16px;
            font-weight: 600;
            border: none;
        }}
        QPushButton:hover {{
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                        stop:0 #60a5fa, stop:1 #3b82f6);
        }}
        QPushButton:pressed {{
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                        stop:0 #2563eb, stop:1 #1d4ed8);
        }}
        QComboBox, QLineEdit, QTextEdit, QSpinBox {{
            background-color: #ffffff;
            color: #1a1f24;
            border: 1px solid #d0d7de;
            border-radius: 6px;
            padding: 6px 8px;
        }}
        QComboBox:hover, QLineEdit:hover, QTextEdit:hover, QSpinBox:hover {{
            border-color: #2563eb;
            background-color: #f9fafb;
        }}
        QComboBox::down-arrow {{
            image: none;
            border: 2px solid #1a1f24;
            width: 6px; height: 6px;
            border-top: none; border-left: none;
            transform: rotate(45deg);
        }}
        QTableWidget, QListWidget {{
            background-color: #ffffff;
            alternate-background-color: #f3f4f6;
            color: #1a1f24;
            border: 1px solid #d0d7de;
            border-radius: 8px;
        }}
        QTableWidget::item, QListWidget::item {{
            padding: 6px;
            border-bottom: 1px solid #e5e7eb;
        }}
        QListWidget::item:hover {{ background-color: #f1f5f9; }}
        QListWidget::item:selected {{ background-color: #dbeafe; }}
        QHeaderView::section {{
            background: #f1f5f9;
            color: #1a1f24;
            font-weight: 600;
            padding: 8px;
            border: none;
            border-right: 1px solid #d0d7de;
        }}
        QDialog, QMessageBox {{
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                        stop:0 #ffffff, stop:1 #f3f4f6);
            color: #1a1f24;
            border: 1px solid #d0d7de;
            border-radius: 12px;
        }}
        QMessageBox QLabel {{
            background: transparent;
            color: black;
            font-size: 14px;
            border: none;
        }}
        QMessageBox QPushButton {{
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                        stop:0 #3b82f6, stop:1 #2563eb);
            color: white;
            border-radius: 6px;
            padding: 6px 14px;
            font-weight: 600;
        }}
        QMessageBox QPushButton:hover {{
            background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                        stop:0 #60a5fa, stop:1 #3b82f6);
        }}
        QCheckBox {{
            background: transparent;
            color: black;
        }}
        QMenu {{
            background-color: #ffffff;
            border: 1px solid #d0d7de;
            border-radius: 8px;
            padding: 6px;
        }}
        QMenu::item {{
            padding: 6px 20px;
            color: #24292f;
            border-radius: 6px;
        }}
        QMenu::item:selected {{
            background-color: #3b82f6;
            color: white;
        }}
        QMenu::separator {{
            height: 1px;
            background: #eaeef2;
            margin: 4px 0;
        }}
        """.format(font_name=font_name)

    @staticmethod
    def overlay_theme():
        if ThemeManager.is_dark_mode():
            return {
                "background": """
                        background: qlineargradient(
                            x1:0, y1:0, x2:0, y2:1,
                            stop:0 #0d1117, stop:1 #161b22
                        );
                        color: #f0f6fc;
                    """,
                "title": "color: #58a6ff; font-size: 22px; font-weight: bold; background: none;",
                "subtitle": "color: #8b949e; font-size: 14px; background: none;",
                "loading": "color: #c9d1d9; font-size: 13px; font-style: italic; background: none;",
                "logo": "background: none;",
                "spinner": "#00aaff"
            }
        else:
            return {
                "background": """
                        background: qlineargradient(
                            x1:0, y1:0, x2:0, y2:1,
                            stop:0 #f9fafb, stop:1 #f3f4f6
                        );
                        color: #1a1f24;
                    """,
                "title": "color: #2563eb; font-size: 22px; font-weight: bold;",
                "subtitle": "color: #4b5563; font-size: 14px;",
                "loading": "color: #374151; font-size: 13px; font-style: italic;",
                "logo": "background: none;",
                "spinner": "#2563eb"
            }

class GenericWorker(QThread):
    finished_signal = Signal(object)
    error_signal = Signal(Exception)

    def __init__(self, func, *args, parent=None, auto_delete=True, **kwargs):
        super().__init__(parent)
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self._auto_delete = auto_delete

        if auto_delete:
            self.finished.connect(self.deleteLater)

    def run(self):
        try:
            result = self.func(*self.args, **self.kwargs)
            self.finished_signal.emit(result)
        except Exception as e:
            logger.exception("Worker error in %s", self.func)
            self.error_signal.emit(e)


class AsyncProcess(QObject):
    finished = Signal(int, str, str)
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._proc = QProcess(self)
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_timeout)

        self._proc.finished.connect(self._on_finished)
        self._proc.errorOccurred.connect(self._on_error)

    def run(self, program, args=None, timeout_ms=5000):
        if self.is_running():
            return False
        self._proc.setProgram(program)
        self._proc.setArguments(args or [])
        self._proc.start()
        if timeout_ms:
            self._timeout_timer.start(timeout_ms)
        return True

    def is_running(self):
        return self._proc.state() == QProcess.Running

    def _on_timeout(self):
        if self.is_running():
            self._proc.kill()
        self.error.emit("Timeout")

    def _on_finished(self, exit_code, exit_status):
        out = self._proc.readAllStandardOutput().data().decode()
        err = self._proc.readAllStandardError().data().decode()
        self._timeout_timer.stop()
        self.finished.emit(exit_code, out, err)

    def _on_error(self, proc_error):
        self._timeout_timer.stop()
        self.error.emit(str(proc_error))

class IpFetcher(QObject):
    ip_ready = Signal(str)

    def __init__(self, settings_handler=None, status_checker=None, parent=None):
        super().__init__(parent)
        self.settings_handler = settings_handler
        self.status_checker = status_checker
        self.is_connected = False
        self._worker = None
        self._retry_timer = QTimer(self)
        self._retry_timer.setSingleShot(True)
        self._retry_timer.timeout.connect(self.fetch_ip)

        if self.status_checker is not None:
            try:
                self.status_checker.status_signal.connect(self.update_status)
            except Exception:
                logger.debug("IpFetcher: status_checker provided but couldn't connect to status_signal")

    def update_status(self, status):
        self.is_connected = (status == "Connected")

    def fetch_ip(self):
        proxies = {}
        if self.settings_handler and getattr(self, "is_connected", False):
            mode = self.settings_handler.get("mode", "warp")
            if mode == "proxy":
                port = self.settings_handler.get("proxy_port", "40000")
                proxies = {
                    "http": f"socks5://127.0.0.1:{port}",
                    "https": f"socks5://127.0.0.1:{port}"
                }

        def do_request():
            try:
                try:
                    resp = requests.get("https://api.ipify.org", params={"format": "json"}, timeout=8, proxies=proxies)
                    resp.raise_for_status()
                    return resp.json().get("ip", "Unavailable")
                except Exception:
                    r = requests.get("https://1.1.1.1/cdn-cgi/trace", timeout=6, proxies=proxies)
                    for line in r.text.splitlines():
                        if line.startswith("ip="):
                            return line.split("=", 1)[1].strip()
                    return "Unavailable"
            except Exception as e:
                logger.debug("IpFetcher.do_request exception: %s", e)
                return "Unavailable"

        try:
            if self._worker and getattr(self._worker, "isRunning", None) and self._worker.isRunning():
                try:
                    self._worker.terminate()
                except Exception:
                    pass
        except Exception:
            pass

        self._worker = GenericWorker(do_request, parent=self)
        self._worker.finished_signal.connect(lambda ip: self.ip_ready.emit(str(ip)))
        self._worker.error_signal.connect(lambda e: (logger.error("IP fetch error: %s", e), self.ip_ready.emit("Unavailable")))
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()


class SOCKS5ChainedProxyServer:

    def __init__(self, settings_handler, forward_port=41000):
        self.settings_handler = settings_handler
        self.forward_port = int(forward_port or 41000)
        self._thread = None
        self._loop = None
        self._server = None
        self._stopping = threading.Event()

    def _get_external(self):
        raw = self.settings_handler.get("external_proxy", "")
        try:
            external = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            external = {}
        return external or {}

    def _get_warp_port(self):
        wp = self.settings_handler.get("proxy_port", "40000")
        try:
            return int(wp)
        except Exception:
            return 40000

    def check_external_proxy(self, timeout=5):
        external = self._get_external()
        if not external.get("host") or not external.get("port"):
            logger.warning("[ChainedProxy] No external proxy configured.")
            return False

        warp_port = self._get_warp_port()
        try:
            with socket.create_connection(("127.0.0.1", warp_port), timeout=timeout) as s:
                s.settimeout(timeout)
                s.sendall(b"\x05\x01\x00")
                resp = s.recv(2)
                if len(resp) < 2 or resp[1] == 0xFF:
                    logger.warning("[ChainedProxy] WARP proxy handshake failed.")
                    return False

                host = external["host"]
                port = int(external["port"])
                if self._is_valid_ipv4(host):
                    addr = socket.inet_aton(host)
                    req = b"\x05\x01\x00\x01" + addr + struct.pack(">H", port)
                else:
                    host_b = host.encode("idna")
                    req = b"\x05\x01\x00\x03" + bytes([len(host_b)]) + host_b + struct.pack(">H", port)

                s.sendall(req)
                rep = s.recv(4)
                if len(rep) < 4 or rep[1] != 0x00:
                    logger.warning(f"[ChainedProxy] External proxy {host}:{port} is unreachable via WARP.")
                    return False

                logger.info(f"[ChainedProxy] External proxy {host}:{port} check succeeded.")
                return True
        except Exception as e:
            logger.error(f"[ChainedProxy] External proxy check failed: {e}")
            return False

    def check_local_proxy(self, timeout=2):
        try:
            with socket.create_connection(("127.0.0.1", self.forward_port), timeout=timeout) as s:
                s.settimeout(timeout)
                s.sendall(b"\x05\x01\x00")
                resp = s.recv(2)
                ok = len(resp) == 2 and resp[0] == 0x05
                if ok:
                    logger.info(f"[ChainedProxy] Local SOCKS5 proxy is listening on 127.0.0.1:{self.forward_port}")
                else:
                    logger.warning(f"[ChainedProxy] Local proxy check failed on 127.0.0.1:{self.forward_port}")
                return ok
        except Exception:
            logger.error(f"[ChainedProxy] Local proxy not responding on 127.0.0.1:{self.forward_port}")
            return False

    def start_background(self):
        if self._thread and self._thread.is_alive():
            return
        self._stopping.clear()
        self._thread = threading.Thread(target=self._run_loop_thread, daemon=True)
        self._thread.start()

    def _run_loop_thread(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            coro = asyncio.start_server(self._handle_client_async, "127.0.0.1", self.forward_port)
            self._server = loop.run_until_complete(coro)
            addr = self._server.sockets[0].getsockname()
            logger.info(f"[ChainedProxy] SOCKS5 server listening on {addr}")
            try:
                loop.run_forever()
            finally:
                self._server.close()
                loop.run_until_complete(self._server.wait_closed())
                loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception as e:
            logger.error(f"[ChainedProxy] Server thread exception: {e}")
        finally:
            try:
                asyncio.set_event_loop(None)
            except Exception:
                pass
            self._loop = None
            self._server = None

    def stop(self):
        if self._loop:
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
                logger.info("[ChainedProxy] Server stopped.")
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def _is_valid_ipv4(self, v):
        try:
            socket.inet_aton(v)
            return True
        except Exception:
            return False

    async def _handle_client_async(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        peer = writer.get_extra_info("peername")
        logger.info(f"[ChainedProxy] New client {peer} connected.")

        try:
            data = await reader.readexactly(2)
            ver, nmethods = data[0], data[1]
            if ver != 5:
                writer.close()
                await writer.wait_closed()
                return
            await reader.readexactly(nmethods)
            writer.write(b"\x05\x00")
            await writer.drain()

            hdr = await reader.readexactly(4)
            if len(hdr) < 4 or hdr[1] != 1:
                writer.write(b"\x05\x07\x00\x01" + b"\x00"*6)
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return

            atyp = hdr[3]
            if atyp == 1:
                addr = await reader.readexactly(4)
                dest_host = socket.inet_ntoa(addr)
            elif atyp == 3:
                l = (await reader.readexactly(1))[0]
                dest_host = (await reader.readexactly(l)).decode("idna")
            elif atyp == 4:
                addr = await reader.readexactly(16)
                dest_host = socket.inet_ntop(socket.AF_INET6, addr)
            else:
                writer.close()
                await writer.wait_closed()
                return
            dest_port = struct.unpack(">H", await reader.readexactly(2))[0]

            external = self._get_external()
            if not external.get("host") or not external.get("port"):
                writer.write(b"\x05\x01\x00\x01" + b"\x00"*6)
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                logger.warning(f"[ChainedProxy] No external proxy configured. Closing client {peer}.")
                return

            warp_port = self._get_warp_port()
            try:
                warp_reader, warp_writer = await asyncio.open_connection("127.0.0.1", warp_port)
            except Exception:
                writer.write(b"\x05\x05\x00\x01" + b"\x00"*6)
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                logger.error(f"[ChainedProxy] Could not connect to WARP proxy on port {warp_port}.")
                return

            warp_writer.write(b"\x05\x01\x00")
            await warp_writer.drain()
            resp = await warp_reader.read(2)
            if len(resp) < 2 or resp[1] == 0xFF:
                await self._close_streams(warp_reader, warp_writer)
                writer.write(b"\x05\x05\x00\x01" + b"\x00"*6)
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                logger.error("[ChainedProxy] WARP SOCKS5 handshake refused methods.")
                return

            ext_host, ext_port = external["host"], int(external["port"])
            if self._is_valid_ipv4(ext_host):
                req = b"\x05\x01\x00\x01" + socket.inet_aton(ext_host) + struct.pack(">H", ext_port)
            else:
                hb = ext_host.encode("idna")
                req = b"\x05\x01\x00\x03" + bytes([len(hb)]) + hb + struct.pack(">H", ext_port)
            warp_writer.write(req)
            await warp_writer.drain()

            rep = await warp_reader.read(4)
            if len(rep) < 4 or rep[1] != 0x00:
                await self._close_streams(warp_reader, warp_writer)
                writer.write(b"\x05\x05\x00\x01" + b"\x00"*6)
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                logger.error(f"[ChainedProxy] WARP could not connect to external proxy {ext_host}:{ext_port}")
                return

            atyp = rep[3]
            if atyp == 1:
                await warp_reader.readexactly(6)
            elif atyp == 3:
                l = (await warp_reader.readexactly(1))[0]
                await warp_reader.readexactly(l + 2)
            elif atyp == 4:
                await warp_reader.readexactly(18)

            ext_type = (external.get("type") or "socks5").lower()
            user = external.get("user") or ""
            pwd = external.get("pass") or ""
            ok = False
            try:
                if ext_type in ("socks5", "socks5h"):
                    ok = await self._external_socks5_connect_async(warp_reader, warp_writer, dest_host, dest_port, user, pwd)
                elif ext_type in ("socks4", "socks4a"):
                    ok = await self._external_socks4_connect_async(warp_reader, warp_writer, dest_host, dest_port, user)
                elif ext_type in ("http", "https"):
                    ok = await self._external_http_connect_async(warp_reader, warp_writer, dest_host, dest_port, user, pwd)
            except Exception as e:
                logger.error(f"[ChainedProxy] Error during external proxy handshake: {e}")
                ok = False

            if not ok:
                await self._close_streams(warp_reader, warp_writer)
                writer.write(b"\x05\x05\x00\x01" + b"\x00"*6)
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                logger.warning(f"[ChainedProxy] External proxy {ext_type} connect failed for {dest_host}:{dest_port}")
                return

            writer.write(b"\x05\x00\x00\x01" + b"\x00"*6)
            await writer.drain()
            logger.info(f"[ChainedProxy] Proxy chain established: client {peer} -> {dest_host}:{dest_port} via {ext_type}://{ext_host}:{ext_port}")

            async def pipe(reader_src, writer_dst):
                try:
                    while True:
                        data = await reader_src.read(4096)
                        if not data:
                            break
                        writer_dst.write(data)
                        await writer_dst.drain()
                except Exception:
                    pass
                finally:
                    try:
                        writer_dst.close()
                    except Exception:
                        pass

            task1 = asyncio.create_task(pipe(reader, warp_writer))
            task2 = asyncio.create_task(pipe(warp_reader, writer))

            pending = {task1, task2}
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)

            for task in pending:
                task.cancel()

            logger.info(f"[ChainedProxy] Client {peer} disconnected.")

        except Exception as e:
            logger.error(f"[ChainedProxy] Exception for client {peer}: {e}")
            try:
                writer.close()
            except Exception:
                pass

    async def _close_streams(self, r, w):
        try:
            w.close()
            await w.wait_closed()
        except Exception:
            pass

    async def _external_socks5_connect_async(self, reader, writer, dest_host, dest_port, username, password):
        try:
            if username:
                writer.write(b"\x05\x02\x02\x00")
            else:
                writer.write(b"\x05\x01\x00")
            await writer.drain()
            resp = await reader.readexactly(2)
            if resp[1] == 0xFF:
                logger.error("[ChainedProxy] External SOCKS5 server refused all methods.")
                return False
            if resp[1] == 0x02:
                ub, pb = username.encode(), password.encode()
                auth_msg = b"\x01" + bytes([len(ub)]) + ub + bytes([len(pb)]) + pb
                writer.write(auth_msg)
                await writer.drain()
                arep = await reader.readexactly(2)
                if arep[1] != 0x00:
                    logger.error("[ChainedProxy] SOCKS5 authentication failed.")
                    return False

            if self._is_valid_ipv4(dest_host):
                req = b"\x05\x01\x00\x01" + socket.inet_aton(dest_host) + struct.pack(">H", dest_port)
            else:
                hb = dest_host.encode("idna")
                req = b"\x05\x01\x00\x03" + bytes([len(hb)]) + hb + struct.pack(">H", dest_port)
            writer.write(req)
            await writer.drain()

            rep = await reader.readexactly(4)
            if rep[1] != 0x00:
                logger.error(f"[ChainedProxy] SOCKS5 CONNECT to {dest_host}:{dest_port} failed (REP={rep[1]}).")
                return False

            atyp = rep[3]
            if atyp == 1:
                await reader.readexactly(6)
            elif atyp == 3:
                l = (await reader.readexactly(1))[0]
                await reader.readexactly(l + 2)
            elif atyp == 4:
                await reader.readexactly(18)

            logger.info(f"[ChainedProxy] SOCKS5 CONNECT to {dest_host}:{dest_port} successful.")
            return True
        except Exception as e:
            logger.error(f"[ChainedProxy] SOCKS5 handshake exception: {e}")
            return False

    async def _external_socks4_connect_async(self, reader, writer, dest_host, dest_port, user):
        try:
            if self._is_valid_ipv4(dest_host):
                ipb = socket.inet_aton(dest_host)
                header = b"\x04\x01" + struct.pack(">H", dest_port) + ipb
                header += (user.encode() if user else b"") + b"\x00"
            else:
                header = b"\x04\x01" + struct.pack(">H", dest_port) + b"\x00\x00\x00\x01"
                header += (user.encode() if user else b"") + b"\x00"
                header += dest_host.encode("idna") + b"\x00"

            writer.write(header)
            await writer.drain()
            resp = await reader.readexactly(8)
            ok = resp[1] == 0x5A
            if ok:
                logger.info(f"[ChainedProxy] SOCKS4 CONNECT to {dest_host}:{dest_port} successful.")
            else:
                logger.error(f"[ChainedProxy] SOCKS4 CONNECT to {dest_host}:{dest_port} failed.")
            return ok
        except Exception as e:
            logger.error(f"[ChainedProxy] SOCKS4 handshake exception: {e}")
            return False

    async def _external_http_connect_async(self, reader, writer, dest_host, dest_port, user, password):
        try:
            auth_hdr = b""
            if user:
                creds = f"{user}:{password}".encode("utf-8")
                auth_hdr = b"Proxy-Authorization: Basic " + base64.b64encode(creds) + b"\r\n"

            req = (
                b"CONNECT " + dest_host.encode("idna") + b":" + str(dest_port).encode() + b" HTTP/1.1\r\n"
                + b"Host: " + dest_host.encode("idna") + b":" + str(dest_port).encode() + b"\r\n"
                + auth_hdr
                + b"Proxy-Connection: Keep-Alive\r\n\r\n"
            )
            writer.write(req)
            await writer.drain()

            buffer = b""
            while True:
                chunk = await reader.read(4096)
                if not chunk:
                    break
                buffer += chunk
                if b"\r\n\r\n" in buffer or b"\n\n" in buffer:
                    break

            first_line = buffer.splitlines()[0] if buffer.splitlines() else b""
            if b"200" in first_line:
                logger.info(f"[ChainedProxy] HTTP CONNECT to {dest_host}:{dest_port} successful.")
                return True

            logger.error(f"[ChainedProxy] HTTP CONNECT to {dest_host}:{dest_port} failed: {first_line.decode(errors='ignore')}")
            return False
        except Exception as e:
            logger.error(f"[ChainedProxy] HTTP CONNECT exception: {e}")
            return False


class LogsWindow(QDialog):
    def __init__(self, parent=None, log_path=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Application Logs"))
        self.resize(720, 520)

        self.log_path = log_path
        self.logger = logging.getLogger("pywarp")

        layout = QVBoxLayout(self)

        self.text_edit = QTextEdit(self)
        self.text_edit.setReadOnly(True)
        self.text_edit.setLineWrapMode(QTextEdit.NoWrap)
        layout.addWidget(self.text_edit)

        btn_row = QHBoxLayout()
        self.refresh_btn = QPushButton(self.tr("Refresh"))
        self.clear_btn   = QPushButton(self.tr("Clear Logs"))
        btn_row.addStretch(1)
        btn_row.addWidget(self.refresh_btn)
        btn_row.addWidget(self.clear_btn)
        layout.addLayout(btn_row)

        self.refresh_btn.clicked.connect(self.load_logs)
        self.clear_btn.clicked.connect(self.clear_logs)
        self.load_logs()

    def load_logs(self):
        if not self.log_path or not os.path.exists(self.log_path):
            self.text_edit.setPlainText(self.tr("No logs found."))
            return
        try:
            with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                self.text_edit.setPlainText(f.read())
            cursor = self.text_edit.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.text_edit.setTextCursor(cursor)
        except Exception as e:
            self.text_edit.setPlainText(self.tr("Failed to read log file:\n{}").format(e))

    def clear_logs(self):
        if not self.log_path:
            QMessageBox.warning(self, self.tr("Error"), self.tr("Log path not set."))
            return

        reply = QMessageBox.question(
            self,
            self.tr("Confirm"),
            self.tr("Clear the log file? This cannot be undone."),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        try:
            for h in self.logger.handlers:
                try: h.flush()
                except Exception: pass

            with open(self.log_path, "w", encoding="utf-8") as f:
                f.write("")

            self.text_edit.clear()
            self.text_edit.setPlainText(self.tr("Logs cleared."))
        except Exception as e:
            QMessageBox.critical(self, self.tr("Error"), self.tr("Failed to clear logs:\n{}").format(e))


class DownloadWorker(GenericWorker):
    progress = Signal(int)
    finished = Signal(bool, str)

    def __init__(self, url, parent=None):
        self.url = url
        self._abort = False
        super().__init__(self._download, parent=parent)

        self.finished_signal.connect(self._on_generic_finished)
        self.error_signal.connect(self._on_error)
        self.finished.connect(self.deleteLater)

    def abort(self):
        self._abort = True

    def _download(self):
        try:
            local_filename = self.url.split('/')[-1] or "downloaded.file"
            with requests.get(self.url, stream=True, timeout=30) as r:
                r.raise_for_status()
                total_length = int(r.headers.get('content-length', 0) or 0)
                downloaded = 0
                with open(local_filename, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if self._abort:
                            return False, ""
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_length > 0:
                                percent = int(downloaded * 100 / total_length)
                                self.progress.emit(percent)
            return True, local_filename
        except Exception as e:
            logger.exception("DownloadWorker error")
            return False, ""

    def _on_generic_finished(self, result):
        try:
            success, filename = result
        except Exception:
            success, filename = False, ""
        self.finished.emit(bool(success), str(filename))

    def _on_error(self, exc):
        logger.exception("DownloadWorker caught error in GenericWorker: %s", exc)
        self.finished.emit(False, "")


class UpdateChecker(QObject):
    update_available = Signal(str, str, str)
    update_finished = Signal(str)

    def __init__(self, installer, parent=None):
        super().__init__(parent)
        if not installer:
            raise ValueError("UpdateChecker requires a valid WarpInstaller instance.")
        self.installer = installer
        self._workers = []

    def start_check(self, delay_ms=3000):
        """Start update check after window is shown (delayed)."""
        QTimer.singleShot(delay_ms, self._run_check_for_update)

    def perform_portable_warp_update(self):
        worker = run_in_worker(self._portable_update_task,
                               parent=self,
                               on_done=lambda _: self._on_worker_done(worker),
                               on_error=self._on_worker_error)
        self._workers.append(worker)

    def _run_check_for_update(self):
        worker = run_in_worker(self._check_for_update_task,
                               parent=self,
                               on_done=lambda _: self._on_worker_done(worker),
                               on_error=self._on_worker_error)
        self._workers.append(worker)

    def _check_for_update_task(self):
        """Worker task: fetch versions and compare."""
        versions = self._get_latest_versions()
        if not versions:
            return

        latest_pywarp = versions.get("pywarp")
        if latest_pywarp and self._is_newer_version(latest_pywarp, CURRENT_VERSION):
            self.update_available.emit("pywarp", latest_pywarp, CURRENT_VERSION)

        latest_warp = versions.get("warp")
        local_version, _, is_portable = self.get_warp_info()
        if latest_warp and local_version and self._is_newer_version(latest_warp, local_version):
            update_type = "warp_portable" if is_portable else "warp_installed"
            self.update_available.emit(update_type, latest_warp, local_version)

    def _get_latest_versions(self):
        """Fetch version file from GitHub and parse it into a dict."""
        try:
            r = requests.get(GITHUB_VERSION_URL, timeout=10)
            r.raise_for_status()
            lines = r.text.strip().splitlines()
            if not lines:
                return None

            versions = {"pywarp": lines[0].strip()}
            for line in lines[1:]:
                if "=" in line:
                    key, val = line.split("=", 1)
                    versions[key.strip()] = val.strip()
            return versions
        except Exception:
            logger.exception("Failed to fetch latest versions")
            return None

    def get_warp_info(self):
        warp_cli_path_str = get_warp_cli_executable()

        if not warp_cli_path_str:
            return None, None, False

        try:
            version = subprocess.check_output(
                [warp_cli_path_str, "--version"],
                text=True,
                **safe_subprocess_args()
            ).strip().split()[-1]

            warp_cli_path = Path(warp_cli_path_str)
            is_portable = "pywarp" in warp_cli_path.parts

            return version, warp_cli_path, is_portable

        except Exception as e:
            logger.error(f"Failed to get warp version from '{warp_cli_path_str}': {e}")
            return None, None, False

    def _portable_update_task(self):
        zip_path = self.installer.appdata_dir / "warp_assets.zip"

        progress = QProgressDialog(
            self.tr("Updating portable WARP..."),
            self.tr("Cancel"), 0, 100, self.parent()
        )
        progress.setWindowTitle(self.tr("Updating"))
        progress.setWindowModality(Qt.WindowModal)
        progress.setValue(0)

        with requests.get(WARP_ASSETS, stream=True, timeout=120) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(zip_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        progress.setValue(int(downloaded * 100 / total))
                    if progress.wasCanceled():
                        zip_path.unlink(missing_ok=True)
                        self.update_finished.emit(self.tr("Update canceled by user."))
                        return

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(self.installer.appdata_dir)
        zip_path.unlink(missing_ok=True)

        logger.info("Portable WARP update successful")
        self.update_finished.emit(self.tr("Portable WARP has been successfully updated!"))

    def _is_newer_version(self, latest, current):
        def parse(v):
            return [int(x) for x in re.findall(r"\d+", v)]
        return parse(latest) > parse(current)

    def _on_worker_done(self, worker):
        if worker in self._workers:
            self._workers.remove(worker)
        worker.deleteLater()

    def _on_worker_error(self, exc, worker):
        logger.error(f"Worker error: {exc}")
        self.update_finished.emit(self.tr("Update failed: {}").format(exc))
        if worker in self._workers:
            self._workers.remove(worker)


class WarpStatusHandler(QObject):
    status_signal = Signal(str)

    def __init__(self, parent=None, interval=5000):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.check_status)
        self._status_proc = AsyncProcess(self)
        self._status_proc.finished.connect(self._on_status_finished)
        self._status_proc.error.connect(self._on_status_error)
        self.status_map = {
            "Connected": 8000,
            "Disconnected": 8000,
            "Connecting": 2000,
            "Failed": 5000,
        }
        self._timer.start(interval)

    def check_status(self):
        if not self._status_proc.is_running():
            warp_cli_path = get_warp_cli_executable()
            if warp_cli_path:
                self._status_proc.run(warp_cli_path, ["status"], timeout_ms=5000)
            else:
                self._on_status_error("warp-cli not found")

    def _on_status_finished(self, code, out, err):
        if code != 0:
            self.status_signal.emit("Failed")
            self._timer.start(self.status_map["Failed"])
            return

        status = self.extract_status(out)
        self.status_signal.emit(status)
        self._timer.start(self.status_map.get(status, 5000))

    def _on_status_error(self, err_msg):
        logger.error(f"warp-cli status error: {err_msg}")
        self.status_signal.emit("Failed")
        self._timer.start(self.status_map["Failed"])

    def extract_status(self, text: str) -> str:
        for line in text.splitlines():
            if "Status update:" in line:
                return line.split(":", 1)[1].strip()
        return "Unknown"


class WarpStatsHandler(QObject):
    stats_signal = Signal(list)

    def __init__(self, status_handler, parent=None, interval=10000):
        super().__init__(parent)
        self.warp_connected = False
        status_handler.status_signal.connect(self.update_status)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.check_stats)
        self._stats_proc = AsyncProcess(self)
        self._stats_proc.finished.connect(self._on_stats_finished)
        self._stats_proc.error.connect(self._on_stats_error)
        self._timer.start(interval)

    def update_status(self, status):
        self.warp_connected = (status == "Connected")

    def check_stats(self):
        if not self.warp_connected:
            self.stats_signal.emit([])
            return
        if not self._stats_proc.is_running():
            warp_cli_path = get_warp_cli_executable()
            if warp_cli_path:
                self._stats_proc.run(warp_cli_path, ["tunnel", "stats"], timeout_ms=5000)
            else:
                self._on_stats_error("warp-cli not found")

    def _on_stats_finished(self, code, out, err):
        if code != 0:
            logger.error(err)
            self.stats_signal.emit([])
            return

        stats_output = out.splitlines()
        if len(stats_output) < 6:
            logger.error("Unexpected stats output format")
            self.stats_signal.emit([])
            return

        try:
            protocol = stats_output[0].split(": ")[1].split(" ")[0]
            endpoints = stats_output[1].split(": ")[1]
            handshake_time = stats_output[2].split(": ")[1]
            data_line = stats_output[3].split("; ")
            sent = data_line[0].split(":")[1].strip()
            received = data_line[1].split(":")[1].strip()
            latency = stats_output[4].split(": ")[1]
            loss = stats_output[5].split(": ")[1]

            self.stats_signal.emit([
                protocol, endpoints, handshake_time, sent, received, latency, loss
            ])
        except (IndexError, ValueError) as e:
            logger.error(f"Error parsing stats: {e}")
            self.stats_signal.emit([])

    def _on_stats_error(self, err_msg):
        logger.error(err_msg)
        self.stats_signal.emit([])

    def stop(self):
        self._timer.stop()


class SettingsHandler(QThread):
    settings_signal = Signal(dict)
    mode_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.settings = QSettings("PyWarp", "App")

    def run(self):
        self.settings_signal.emit(self.get_all_settings())

    def save_settings(self, key, value):
        self.settings.setValue(key, value)
        self.settings.sync()
        if key == "mode":
            self.mode_changed.emit(value)

    def get(self, key, default=None):
        value = self.settings.value(key, default)
        if isinstance(default, bool):
            return to_bool(value)
        return value

    def get_all_settings(self):
        return {
            "endpoint": self.get("endpoint", ""),
            "dns_mode": self.get("dns_mode", "off"),
            "mode": self.get("mode", "warp"),
            "silent_mode": self.get("silent_mode", False),
            "close_behavior": self.get("close_behavior", "ask")
        }


class SpinnerWidget(QWidget):
    def __init__(self, parent=None, lines=12, radius=18, line_length=10,
                 line_width=4, interval=80, color=None):
        super().__init__(parent)
        self._lines = lines
        self._radius = radius
        self._line_length = line_length
        self._line_width = line_width
        self._angle = 0
        self._color = QColor(0, 120, 212) if color is None else QColor(color)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._timer.start(interval)

        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setMinimumSize(self.sizeHint())

    def sizeHint(self):
        size = (self._radius + self._line_length + self._line_width) * 2
        return QSize(size, size)

    def setColor(self, color):
        self._color = QColor(color)
        self.update()

    def _rotate(self):
        self._angle = (self._angle + 360 / self._lines) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        center = self.rect().center()
        painter.translate(center.x(), center.y())

        step = 360.0 / self._lines
        for i in range(self._lines):
            painter.save()
            painter.rotate(self._angle + i * step)
            alpha = int(255 * ((i + 1) / self._lines))
            c = QColor(self._color)
            c.setAlpha(alpha)
            pen = QPen(c, self._line_width, Qt.SolidLine, Qt.RoundCap)
            painter.setPen(pen)
            painter.drawLine(0, -self._radius, 0, -self._radius + self._line_length)
            painter.restore()

    def stop(self):
        if self._timer.isActive():
            self._timer.stop()

    def start(self):
        if not self._timer.isActive():
            self._timer.start()

class LoadingOverlay(QWidget):
    def __init__(self, parent, icon_path=":/logo.png"):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.StrongFocus)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        self.logo_label = QLabel(self)
        pixmap = QPixmap(icon_path)
        if not pixmap.isNull():
            self.logo_label.setPixmap(pixmap.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        layout.addWidget(self.logo_label, alignment=Qt.AlignCenter)

        self.title_label = QLabel("PyWarp", self)
        layout.addWidget(self.title_label, alignment=Qt.AlignCenter)

        self.subtitle_label = QLabel(self.tr("Cloudflare Warp GUI"), self)
        layout.addWidget(self.subtitle_label, alignment=Qt.AlignCenter)

        self.spinner = SpinnerWidget(self)
        layout.addWidget(self.spinner, alignment=Qt.AlignCenter)

        self.loading_label = QLabel("", self)
        layout.addWidget(self.loading_label, alignment=Qt.AlignCenter)

        self.loading_texts = [
            self.tr("Checking Warp service..."),
            self.tr("Making sure Warp is ready..."),
            self.tr("Preparing UI..."),
            self.tr("Syncing settings..."),
            self.tr("Starting engines..."),
            self.tr("Almost ready...")
        ]
        self.current_index = 0

        self.text_timer = QTimer(self)
        self.text_timer.timeout.connect(self._update_text)

        self.setVisible(False)
        if parent:
            self.setGeometry(parent.rect())
            self.raise_()

        self.apply_theme()

    def apply_theme(self):
        theme = ThemeManager.overlay_theme()
        self.setStyleSheet(theme["background"])
        self.title_label.setStyleSheet(theme["title"])
        self.subtitle_label.setStyleSheet(theme["subtitle"])
        self.loading_label.setStyleSheet(theme["loading"])
        self.logo_label.setStyleSheet(theme['logo'])
        self.spinner.setColor(theme["spinner"])

    def _update_text(self):
        if self.current_index < len(self.loading_texts):
            self.loading_label.setText(self.loading_texts[self.current_index])
            self.current_index += 1

        if self.current_index >= len(self.loading_texts):
            self.text_timer.stop()

    def show(self):
        if self.parent():
            self.setGeometry(self.parent().rect())
        super().show()
        self.raise_()
        self.spinner.start()
        self.current_index = 0
        self.text_timer.start(1200)
        self._update_text()

    def hide(self):
        self.spinner.stop()
        self.text_timer.stop()
        super().hide()


class PowerButton(QWidget):
    toggled = Signal(str)
    command_error_signal = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(150, 150)

        self.STATES = {
            "Connected": {"style": "on", "text": self.tr("ON")},
            "Disconnected": {"style": "off", "text": self.tr("OFF")},
            "Connecting": {"style": "unknown", "text": "..."},
            "Disconnecting": {"style": "unknown", "text": "..."},
            "No Network": {"style": "off", "text": self.tr("ERR")},
            "unknown": {"style": "unknown", "text": self.tr("ERR")}
        }

        self.state = "Disconnected"
        self._toggle_lock = False
        self.current_error_box = None

        palette = QApplication.palette()
        is_dark_mode = palette.color(QPalette.Window).lightness() < 128
        self.theme = "dark" if is_dark_mode else "light"

        self.button_styles = {
            "off": {"dark": {"border": "#f85149", "text": "#f85149"},
                    "light": {"border": "#d1242f", "text": "#d1242f"}},
            "unknown": {"dark": {"border": "#f0883e", "text": "#f0883e"},
                        "light": {"border": "#f97316", "text": "#f97316"}},
            "on": {"dark": {"border": "#3fb950", "text": "#3fb950"}, "light": {"border": "#2da44e", "text": "#2da44e"}}
        }

        self.gradient_colors = {
            "off": ("#fdecea", "#f9d6d0") if self.theme == "light" else ("#2b1010", "#1a0707"),
            "unknown": ("#fff4e6", "#ffe6cc") if self.theme == "light" else ("#3a2110", "#1f1208"),
            "on": ("#e6f5ea", "#d1efd4") if self.theme == "light" else ("#1b2a1f", "#0f1b12")
        }

        self.power_button = QPushButton("...", self)
        self.power_button.setGeometry(25, 25, 100, 100)
        self.power_button.setFont(QFont("Arial", 20, QFont.Bold))
        self.power_button.setStyleSheet("border-radius: 50px; font-size: 24px;")

        self.glow_effect = QGraphicsDropShadowEffect()
        self.glow_effect.setBlurRadius(50)
        self.glow_effect.setOffset(0, 0)
        self.power_button.setGraphicsEffect(self.glow_effect)

        self.connecting_dots = 0
        self.connecting_timer = QTimer()
        self.connecting_timer.setInterval(500)
        self.connecting_timer.timeout.connect(self.update_dots)

        self.glow_animation = QPropertyAnimation(self.glow_effect, b"blurRadius")
        self.glow_animation.setStartValue(20)
        self.glow_animation.setEndValue(50)
        self.glow_animation.setDuration(800)
        self.glow_animation.setLoopCount(-1)

        self.glow_color_anim = QVariantAnimation()
        self.glow_color_anim.setStartValue(QColor("#f97316"))
        self.glow_color_anim.setEndValue(QColor("#ffb347"))
        self.glow_color_anim.setDuration(800)
        self.glow_color_anim.setLoopCount(-1)
        self.glow_color_anim.valueChanged.connect(self.update_glow_color)

        self.power_button.clicked.connect(self.toggle_power)
        self.command_error_signal.connect(self.show_error_dialog)

    def update_dots(self):
        self.connecting_dots = (self.connecting_dots + 1) % 4
        self.power_button.setText("." * self.connecting_dots)

    def get_glow_color(self, style_key):
        color = self.button_styles.get(style_key, {}).get(self.theme, {}).get("text", "#999999")
        qcolor = QColor(color)
        qcolor.setAlpha(200 if style_key == "unknown" else 255)
        return qcolor

    def update_glow_color(self, color):
        if isinstance(color, QColor):
            color.setAlpha(200)
            self.glow_effect.setColor(color)

    def apply_style(self, style_key, text):
        border_color = self.button_styles.get(style_key, {}).get(self.theme, {}).get("border", "#999999")
        text_color = self.button_styles.get(style_key, {}).get(self.theme, {}).get("text", "#999999")
        bg_start, bg_end = self.gradient_colors.get(style_key, ("#ffffff", "#f6f8fa"))

        self.power_button.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                        stop:0 {bg_start}, stop:1 {bg_end});
            border: 4px solid {border_color};
            color: {text_color};
            font-weight: 700;
            border-radius: 50px;
            font-size: 24px;
        """)

        if style_key == "unknown" and text == "...":
            if not self.connecting_timer.isActive():
                self.connecting_timer.start()
            if self.glow_animation.state() != QAbstractAnimation.Running:
                self.glow_animation.start()
            if self.glow_color_anim.state() != QAbstractAnimation.Running:
                self.glow_color_anim.start()
        else:
            self.connecting_timer.stop()
            self.glow_animation.stop()
            self.glow_color_anim.stop()
            self.glow_effect.setBlurRadius(50 if style_key != "unknown" else 30)
            self.glow_effect.setColor(self.get_glow_color(style_key))
            self.power_button.setText(text)

    def update_button_state(self, new_state):
        self.state = new_state
        config = self.STATES.get(new_state, self.STATES["unknown"])

        if new_state in ["Connected", "Disconnected", "Connecting"]:
            self.power_button.setDisabled(False)
        else:
            self.power_button.setDisabled(True)

        self.apply_style(config["style"], config["text"])

    def toggle_power(self):
        if self.state == "Connecting":
            def work():
                return run_warp_command("warp-cli", "disconnect")

            def done(result):
                self.toggled.emit("Disconnecting")
                if not result or result.returncode != 0:
                    error = result.stderr.strip() if result else self.tr("Unknown error")
                    self.command_error_signal.emit(
                        self.tr("Command Error"),
                        self.tr("Failed to run command: {}").format(error)
                    )
                QTimer.singleShot(500, self.force_status_refresh)

            def fail(exc):
                logger.error(f"Disconnect command failed: {exc}")
                self.command_error_signal.emit(
                    self.tr("Command Error"),
                    self.tr("Exception while disconnecting: {}").format(exc)
                )
                QTimer.singleShot(500, self.force_status_refresh)

            self._cancel_worker = run_in_worker(work, parent=self,
                                                on_done=done,
                                                on_error=fail)
            return

        self.power_button.setDisabled(True)
        self.apply_style("unknown", "...")

        def work():
            if self.state == "Disconnected":
                return "Connecting", run_warp_command("warp-cli", "connect")
            else:
                return "Disconnecting", run_warp_command("warp-cli", "disconnect")

        def done(result):
            phase, cmd_result = result
            self.toggled.emit(phase)
            if not cmd_result or cmd_result.returncode != 0:
                error = cmd_result.stderr.strip() if cmd_result else self.tr("Unknown error")
                self.command_error_signal.emit(
                    self.tr("Command Error"),
                    self.tr("Failed to run command: {}").format(error)
                )
            QTimer.singleShot(500, self.force_status_refresh)

        def fail(exc):
            logger.error(f"Toggle command failed: {exc}")
            self.command_error_signal.emit(
                self.tr("Command Error"),
                self.tr("Exception while toggling power: {}").format(exc)
            )
            QTimer.singleShot(500, self.force_status_refresh)

        self._toggle_worker = run_in_worker(work, parent=self,
                                            on_done=done,
                                            on_error=fail)

    def reset_button_state(self):
        if self._toggle_lock:
            self._toggle_lock = False
            self.power_button.setDisabled(False)
            self.force_status_refresh()

    def force_status_refresh(self):
        self.toggled.emit("ForceRefresh")

    def customEvent(self, event):
        if event.type() == QEvent.User:
            self.show_error_dialog(self.tr("Warning"), self.tr("No network detected. Please check your connection."))
        elif event.type() == QEvent.Type(QEvent.User + 1):
            self.show_error_dialog(self.tr("Command Error"), event.error_message)
        elif event.type() == QEvent.MaxUser:
            self.show_error_dialog(self.tr("Error"), self.tr("An unexpected error occurred. Please try again later."))

    def show_error_dialog(self, title, message):
        if self.current_error_box:
            self.current_error_box.close()
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning if title == self.tr("Warning") else QMessageBox.Critical)
        box.setWindowTitle(title)
        box.setText(message)
        box.setAttribute(Qt.WA_DeleteOnClose)
        box.finished.connect(self._on_error_dialog_closed)
        self.current_error_box = box
        box.show()

    def _on_error_dialog_closed(self):
        self.current_error_box = None
        QTimer.singleShot(500, self.force_status_refresh)


class ExclusionManager(QDialog):
    exclusions_updated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Add Exclusion"))
        self.setFixedSize(320, 240)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        self.selector = QComboBox()
        self.selector.addItems([self.tr("IP"), self.tr("Domain")])
        layout.addWidget(self.selector)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText(self.tr("Enter IP or Domain"))
        layout.addWidget(self.input_field)
        layout.addSpacing(10)

        self.submit_button = QPushButton(self.tr("Add"))
        self.submit_button.setMinimumHeight(40)
        self.submit_button.clicked.connect(self.add_item)
        layout.addWidget(self.submit_button, alignment=Qt.AlignCenter)

        self.setLayout(layout)

    def is_valid_ip(self, value):
        try:
            ipaddress.ip_address(value)
            return True
        except ValueError:
            return False

    def is_valid_domain(self, value):
        return bool(re.match(r'^((?!-)[A-Za-z0-9-]{1,63}(?<!-)\.)+[A-Za-z]{2,63}$', value))

    def add_item(self):
        value = self.input_field.text().strip()
        if not value:
            return

        exclusion_type = self.selector.currentText().lower()

        ip_keyword = self.tr("ip").lower()
        domain_keyword = self.tr("domain").lower()

        if exclusion_type == ip_keyword and not self.is_valid_ip(value):
            QMessageBox.warning(self, self.tr("Invalid Input"),
                                self.tr("Please enter a valid IP address."))
            return
        elif exclusion_type == domain_keyword and not self.is_valid_domain(value):
            QMessageBox.warning(self, self.tr("Invalid Input"),
                                self.tr("Please enter a valid domain name."))
            return

        try:
            command_type = "ip" if exclusion_type == ip_keyword else "host"
            result = run_warp_command("warp-cli", "tunnel", command_type, "add", value)

            if result.returncode == 0:
                self.exclusions_updated.emit()
                self.accept()
            else:
                QMessageBox.warning(
                    self, self.tr("Error"),
                    self.tr("Failed to add {}: {}").format(exclusion_type, result.stderr.strip()))
        except subprocess.TimeoutExpired:
            QMessageBox.warning(self, self.tr("Error"), self.tr("Command timed out"))
        except Exception as e:
            QMessageBox.warning(self, self.tr("Error"), self.tr("Command failed: {}").format(e))


class AdvancedSettings(QDialog):

    def __init__(self, settings_handler, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Advanced Settings"))
        self.resize(800, 600)

        self.settings_handler = settings_handler
        self.current_endpoint = self.settings_handler.get("custom_endpoint", "")

        # Exclude IP/Domain
        exclusion_group = QGroupBox(self.tr("Exclude IP/Domain"))
        exclusion_layout = QVBoxLayout()

        self.item_list = QListWidget()
        self.item_list.setMinimumHeight(180)
        self.item_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        exclusion_layout.addWidget(self.item_list)

        button_layout = QHBoxLayout()
        self.reset_button = QPushButton(self.tr("Reset"))
        self.reset_button.clicked.connect(self.reset_list)

        self.add_button = QPushButton("+")
        self.add_button.clicked.connect(self.open_exclusion_manager)

        self.remove_button = QPushButton("-")
        self.remove_button.clicked.connect(self.remove_item)

        button_layout.addWidget(self.reset_button)
        button_layout.addStretch()
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.remove_button)

        exclusion_layout.addLayout(button_layout)
        exclusion_group.setLayout(exclusion_layout)

        # Custom Endpoint
        endpoint_group = QGroupBox(self.tr("Custom Endpoint"))
        endpoint_layout = QHBoxLayout()

        self.endpoint_input = QComboBox()
        self.endpoint_input.setEditable(True)
        self.endpoint_input.setInsertPolicy(QComboBox.InsertAtTop)
        self.endpoint_input.setMinimumWidth(200)

        self.load_endpoint_history()
        self.endpoint_input.setPlaceholderText(self.tr("Set Custom Endpoint"))
        self.endpoint_input.setCurrentText(self.current_endpoint)

        self.endpoint_save_button = QPushButton(self.tr("Save"))
        self.endpoint_save_button.clicked.connect(self.save_endpoint)

        self.endpoint_reset_button = QPushButton(self.tr("Reset"))
        self.endpoint_reset_button.clicked.connect(self.reset_endpoint)

        endpoint_layout.addWidget(self.endpoint_input)
        endpoint_layout.addWidget(self.endpoint_save_button)
        endpoint_layout.addWidget(self.endpoint_reset_button)
        endpoint_group.setLayout(endpoint_layout)

        # MASQUE Options
        masque_group = QGroupBox(self.tr("MASQUE Options"))
        masque_layout = QHBoxLayout()

        self.masque_input = QComboBox()
        self.masque_input.setMinimumWidth(200)

        options = [
            ("h3-only", self.tr("Use only HTTP/3 (fastest, best for modern networks)")),
            ("h2-only", self.tr("Force HTTP/2 (may help in restrictive networks)")),
            ("h3-with-h2-fallback", self.tr("Use HTTP/3, fallback to HTTP/2 if needed")),
        ]

        for value, desc in options:
            self.masque_input.addItem(value, value)
            idx = self.masque_input.count() - 1
            self.masque_input.setItemData(idx, desc, Qt.ToolTipRole)

        current_masque = self.settings_handler.get("masque_option", "")
        if current_masque:
            index = self.masque_input.findData(current_masque)
            if index != -1:
                self.masque_input.setCurrentIndex(index)

        self.masque_set_button = QPushButton(self.tr("Set"))
        self.masque_set_button.clicked.connect(self.save_masque_option)

        self.masque_reset_button = QPushButton(self.tr("Reset"))
        self.masque_reset_button.clicked.connect(self.reset_masque_option)

        masque_layout.addWidget(self.masque_input)
        masque_layout.addWidget(self.masque_set_button)
        masque_layout.addWidget(self.masque_reset_button)
        masque_group.setLayout(masque_layout)

        # App Excludes (coming soon)
        coming_soon_group = QGroupBox(self.tr("App Excludes"))
        coming_soon_layout = QVBoxLayout()
        coming_soon_layout.addWidget(QLabel(self.tr("Coming Soon...")))
        coming_soon_group.setLayout(coming_soon_layout)

        # Proxy Chain
        proxy_group = QGroupBox(self.tr("Proxy Chain"))
        proxy_layout = QVBoxLayout()

        row1 = QHBoxLayout()
        self.proxy_host = QLineEdit()
        self.proxy_host.setPlaceholderText(self.tr("Host"))
        self.proxy_host.setMinimumWidth(140)

        self.proxy_port = QLineEdit()
        self.proxy_port.setPlaceholderText(self.tr("Port"))
        self.proxy_port.setMaximumWidth(80)

        self.proxy_type = QComboBox()
        self.proxy_type.addItems(["socks5", "socks4", "http"])
        self.proxy_type.setMaximumWidth(100)

        self.proxy_user = QLineEdit()
        self.proxy_user.setPlaceholderText(self.tr("User (optional)"))
        self.proxy_user.setMaximumWidth(120)

        self.proxy_pass = QLineEdit()
        self.proxy_pass.setPlaceholderText(self.tr("Pass (optional)"))
        self.proxy_pass.setEchoMode(QLineEdit.Password)
        self.proxy_pass.setMaximumWidth(120)

        row1.addWidget(QLabel(self.tr("Host:")))
        row1.addWidget(self.proxy_host)
        row1.addWidget(QLabel(self.tr("Port:")))
        row1.addWidget(self.proxy_port)
        row1.addWidget(QLabel(self.tr("Type:")))
        row1.addWidget(self.proxy_type)
        row1.addWidget(QLabel(self.tr("User:")))
        row1.addWidget(self.proxy_user)
        row1.addWidget(QLabel(self.tr("Pass:")))
        row1.addWidget(self.proxy_pass)

        proxy_layout.addLayout(row1)

        row2 = QHBoxLayout()

        self.proxy_local_forward_port = QLineEdit()
        self.proxy_local_forward_port.setPlaceholderText(self.tr("Local forward port (optional)"))
        self.proxy_local_forward_port.setMaximumWidth(160)
        self.proxy_save_btn = QPushButton(self.tr("Save Proxy"))

        row2.addWidget(QLabel(self.tr("Forward Port:")))
        row2.addWidget(self.proxy_local_forward_port)
        row2.addStretch()
        row2.addWidget(self.proxy_save_btn)

        proxy_layout.addLayout(row2)

        proxy_group.setLayout(proxy_layout)

        grid = QGridLayout()
        grid.addWidget(exclusion_group, 0, 0)
        grid.addWidget(coming_soon_group, 0, 1)
        grid.addWidget(endpoint_group, 1, 0)
        grid.addWidget(masque_group, 1, 1)
        grid.addWidget(proxy_group, 2, 0, 1, 2)

        self.setLayout(grid)
        self.update_list_view()

        self.proxy_save_btn.clicked.connect(self._save_proxy_settings)
        self._load_proxy_settings()

    def _load_proxy_settings(self):
        raw = self.settings_handler.get("external_proxy", "")
        proxy = {}
        if isinstance(raw, str) and raw:
            try:
                proxy = json.loads(raw)
            except Exception:
                proxy = {}
        elif isinstance(raw, dict):
            proxy = raw

        self.proxy_host.setText(proxy.get("host", ""))
        self.proxy_port.setText(str(proxy.get("port", "")) if proxy.get("port", "") != "" else "")
        self.proxy_user.setText(proxy.get("user", ""))
        self.proxy_pass.setText(proxy.get("pass", ""))
        ptype = proxy.get("type", "socks5")
        idx = self.proxy_type.findText(ptype)
        if idx != -1:
            self.proxy_type.setCurrentIndex(idx)
        else:
            if self.proxy_type.count():
                self.proxy_type.setCurrentIndex(0)

        self.proxy_local_forward_port.setText(str(self.settings_handler.get("proxy_chain_local_forward_port", "")))

    def _save_proxy_settings(self):
        host = self.proxy_host.text().strip()
        port_text = self.proxy_port.text().strip()

        if not host or not port_text:
            QMessageBox.warning(self, self.tr("Error"), self.tr("Host and port are required for the external proxy."))
            return

        try:
            port = int(port_text)
            if not (1 <= port <= 65535):
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, self.tr("Error"), self.tr("Port must be a number between 1 and 65535."))
            return

        local_port_text = self.proxy_local_forward_port.text().strip()
        try:
            if local_port_text:
                forward_port = int(local_port_text)
                if not (1 <= forward_port <= 65535):
                    raise ValueError
            else:
                forward_port = 41000
        except ValueError:
            QMessageBox.warning(self, self.tr("Error"),
                                self.tr("Local forward port must be a number between 1 and 65535."))
            return

        warp_port = self.settings_handler.get("proxy_port", "40000")
        try:
            warp_port_int = int(warp_port)
        except Exception:
            warp_port_int = 40000

        if forward_port == warp_port_int:
            QMessageBox.warning(self, self.tr("Error"),
                                self.tr("Forward port must not be the same as the WARP local proxy port."))
            return

        if forward_port <= 40000:
            QMessageBox.warning(self, self.tr("Error"), self.tr("Forward port must be larger than 40000 (e.g. 41000)."))
            return

        proxy_dict = {
            "host": host,
            "port": port,
            "user": self.proxy_user.text().strip() or "",
            "pass": self.proxy_pass.text() or "",
            "type": self.proxy_type.currentText() or "socks5"
        }

        try:
            self.settings_handler.save_settings("external_proxy", json.dumps(proxy_dict))
            self.settings_handler.save_settings("proxy_chain_local_forward_port", str(forward_port))
            QMessageBox.information(self, self.tr("Saved"), self.tr("External proxy saved."))
        except Exception as e:
            QMessageBox.warning(self, self.tr("Error"), self.tr("Failed to save proxy settings: {}").format(e))

    def save_masque_option(self):
        option = self.masque_input.currentData()
        if not option:
            return
        try:
            result = run_warp_command("warp-cli", "tunnel", "masque-options", "set", option)
            if result.returncode != 0:
                error_line = result.stderr.strip().split("\n")[0]
                QMessageBox.warning(self, self.tr("Error"), error_line)
                return
            self.settings_handler.save_settings("masque_option", option)
            QMessageBox.information(self, self.tr("Saved"),
                                    self.tr("MASQUE option set to {}.").format(option))
        except Exception as e:
            QMessageBox.warning(self, self.tr("Error"),
                                self.tr("An exception occurred: {}").format(str(e)))

    def reset_masque_option(self):
        try:
            result = run_warp_command("warp-cli", "tunnel", "masque-options", "reset")
            if result.returncode != 0:
                error_line = result.stderr.strip().split("\n")[0]
                QMessageBox.warning(self, self.tr("Error"), error_line)
                return
            self.settings_handler.save_settings("masque_option", "")
            self.masque_input.setCurrentIndex(-1)
            QMessageBox.information(self, self.tr("Reset"),
                                    self.tr("MASQUE option reset successfully."))
        except Exception as e:
            QMessageBox.warning(self, self.tr("Error"),
                                self.tr("Reset failed: {}").format(e))

    def open_exclusion_manager(self):
        exclusion_manager = ExclusionManager(self)
        exclusion_manager.exclusions_updated.connect(self.update_list_view)
        exclusion_manager.exec()

    def load_endpoint_history(self):
        history = self.settings_handler.get("endpoint_history")
        if isinstance(history, str):
            try:
                import ast
                history = ast.literal_eval(history)
            except Exception:
                history = []
        if not isinstance(history, list):
            history = []

        if history:
            self.endpoint_input.addItems(history)
        if self.current_endpoint and self.current_endpoint not in history:
            self.endpoint_input.insertItem(0, self.current_endpoint)

    def save_endpoint_history(self, endpoint):
        history = self.settings_handler.get("endpoint_history", [])
        if not isinstance(history, list):
            history = []

        if endpoint in history:
            history.remove(endpoint)
        history.insert(0, endpoint)
        history = history[:5]

        self.settings_handler.save_settings("endpoint_history", history)
        self.endpoint_input.clear()
        self.endpoint_input.addItems(history)
        self.endpoint_input.setCurrentText(endpoint)

    def update_list_view(self):
        self.item_list.clear()

        # Get IP exclusions
        try:
            result_ip = run_warp_command("warp-cli", "tunnel", "ip", "list")
            if result_ip.returncode == 0:
                lines = result_ip.stdout.strip().splitlines()
                for line in lines[1:]:
                    ip_value = line.strip().split()[0] if line.strip() else ""
                    if ip_value:
                        self.item_list.addItem(self.tr("IP: {}").format(ip_value))
        except Exception as e:
            logger.error(f"Error getting IP list: {e}")

        # Get host exclusions
        try:
            result_host = run_warp_command("warp-cli", "tunnel", "host", "list")
            if result_host.returncode == 0:
                lines = result_host.stdout.strip().splitlines()
                for line in lines[1:]:
                    host_value = line.strip().split()[0] if line.strip() else ""
                    if host_value:
                        self.item_list.addItem(self.tr("Domain: {}").format(host_value))
        except Exception as e:
            logger.error(f"Error getting host list: {e}")

    def remove_item(self):
        item = self.item_list.currentItem()
        if not item:
            QMessageBox.warning(self, self.tr("Error"), self.tr("No item selected!"))
            return

        item_text = item.text().split(": ", 1)
        if len(item_text) != 2:
            QMessageBox.warning(self, self.tr("Error"), self.tr("Invalid entry format!"))
            return

        mode = item_text[0].lower().strip()
        value_from_list = item_text[1].strip()
        value_cleaned = value_from_list.split('/')[0]

        try:
            ip_keyword = self.tr("ip").lower()
            command_mode = "ip" if mode == ip_keyword else "host"
            result = run_warp_command("warp-cli", "tunnel", command_mode, "remove", value_cleaned)

            if result.returncode == 0:
                self.update_list_view()
            else:
                QMessageBox.warning(
                    self, self.tr("Error"),
                    self.tr("Failed to remove {}:\n\n{}").format(mode, result.stderr.strip()))
        except Exception as e:
            QMessageBox.warning(self, self.tr("Error"), self.tr("Command failed: {}").format(e))

    def reset_list(self):
        try:
            run_warp_command("warp-cli", "tunnel", "ip", "reset")
            run_warp_command("warp-cli", "tunnel", "host", "reset")
            self.update_list_view()
        except Exception as e:
            QMessageBox.warning(self, self.tr("Error"), self.tr("Reset failed: {}").format(e))

    def save_endpoint(self):
        endpoint = self.endpoint_input.currentText().strip()
        if not endpoint:
            return

        try:
            result = run_warp_command("warp-cli", "tunnel", "endpoint", "set", endpoint)

            if result.returncode != 0:
                error_line = result.stderr.strip().split("\n")[0]
                QMessageBox.warning(self, self.tr("Error"), error_line)
                return

            self.settings_handler.save_settings("custom_endpoint", endpoint)
            self.save_endpoint_history(endpoint)
            QMessageBox.information(self, self.tr("Saved"), self.tr("Endpoint saved successfully."))
        except Exception as e:
            QMessageBox.warning(self, self.tr("Error"), self.tr("An exception occurred: {}").format(str(e)))

    def reset_endpoint(self):
        try:
            run_warp_command("warp-cli", "tunnel", "endpoint", "reset")
            self.settings_handler.save_settings("custom_endpoint", "")
            self.endpoint_input.clear()
            QMessageBox.information(self, self.tr("Reset"), self.tr("Endpoint reset successfully."))
        except Exception as e:
            QMessageBox.warning(self, self.tr("Error"), self.tr("Reset failed: {}").format(e))


class SettingsPage(QWidget):
    def __init__(self, parent=None, warp_status_handler=None, settings_handler=None):
        super().__init__(parent)
        self.settings_handler = settings_handler
        self.warp_status_handler = warp_status_handler

        self.current_status = "Disconnected"
        self.current_dns_mode = self.settings_handler.get("dns_mode", "off")
        self.current_mode = self.settings_handler.get("mode", "warp")
        self.current_lang = self.settings_handler.get("language", "en")
        self.current_font = self.settings_handler.get("font_family", QApplication.font().family())

        main_layout = QVBoxLayout(self)
        grid = QGridLayout()

        # Modes Section
        modes_group = self.create_groupbox(self.tr("Modes"))
        modes_layout = QVBoxLayout()
        self.modes_dropdown = QComboBox()

        modes_with_tooltips = {
            "warp": self.tr("Full VPN tunnel via Cloudflare. Encrypts all traffic."),
            "doh": self.tr("Only DNS over HTTPS (DoH). DNS is secure; rest of traffic is unencrypted."),
            "warp+doh": self.tr("VPN tunnel + DNS over HTTPS. Full encryption + secure DNS."),
            "dot": self.tr("Only DNS over TLS (DoT). Secure DNS, no VPN tunnel."),
            "warp+dot": self.tr("VPN tunnel + DNS over TLS. Full encryption + secure DNS."),
            "proxy": self.tr("Sets up a local WARP proxy (manual port needed). Apps can use it via localhost."),
            "chained_proxy": self.tr(
                "Starts a local proxy that chains WARP with your configured external proxy."
            ),
            "tunnel_only": self.tr("Tunnel is created but not used unless manually routed.")
        }

        for mode, tooltip in modes_with_tooltips.items():
            self.modes_dropdown.addItem(mode)
            index = self.modes_dropdown.findText(mode)
            self.modes_dropdown.setItemData(index, tooltip, Qt.ToolTipRole)

        self.modes_dropdown.setCurrentText(self.current_mode)
        self.modes_dropdown.currentTextChanged.connect(self.set_mode)
        modes_layout.addWidget(self.modes_dropdown)
        modes_group.setLayout(modes_layout)

        # DNS Section
        dns_group = self.create_groupbox(self.tr("DNS Settings"))
        dns_layout = QVBoxLayout()
        self.dns_dropdown = QComboBox()
        self.dns_dropdown.addItems([
            self.tr("Off (No DNS filtering)"),
            self.tr("Block Adult Content"),
            self.tr("Block Malware")
        ])
        self.dns_dropdown.setCurrentText(self.current_dns_mode)
        self.dns_dropdown.currentTextChanged.connect(self.set_dns_mode)
        dns_layout.addWidget(self.dns_dropdown)
        dns_group.setLayout(dns_layout)

        # Language Section
        language_group = self.create_groupbox(self.tr("Language"))
        language_layout = QVBoxLayout()
        self.language_dropdown = QComboBox()
        self.language_dropdown.addItem("English", "en")
        self.language_dropdown.addItem("فارسی", "fa")
        # self.language_dropdown.addItem("Russian", "ru")
        # self.language_dropdown.addItem("Chinese", "de")

        index = self.language_dropdown.findData(self.current_lang)
        if index >= 0:
            self.language_dropdown.setCurrentIndex(index)

        self.language_dropdown.currentIndexChanged.connect(self.change_language)
        language_layout.addWidget(self.language_dropdown)
        language_group.setLayout(language_layout)

        # Fonts Section
        font_group = self.create_groupbox(self.tr("Fonts"))
        font_layout = QVBoxLayout()
        self.font_dropdown = QFontComboBox()
        self.font_dropdown.setCurrentFont(QFont(self.current_font))
        self.font_dropdown.currentFontChanged.connect(self.change_font)
        font_layout.addWidget(self.font_dropdown)
        font_group.setLayout(font_layout)

        # Put 4 groups in a 2x2 grid
        grid.addWidget(modes_group, 0, 0)
        grid.addWidget(dns_group, 0, 1)
        grid.addWidget(language_group, 1, 0)
        grid.addWidget(font_group, 1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        main_layout.addLayout(grid)

        # More Options Section (Logs + Advanced in one row)
        more_group = self.create_groupbox(self.tr("More Options"))
        more_layout = QHBoxLayout()
        logs_button = QPushButton(self.tr("View Logs"))
        logs_button.clicked.connect(self.open_logs_window)
        advanced_settings_button = QPushButton(self.tr("Advanced Settings"))
        advanced_settings_button.clicked.connect(self.open_advanced_settings)
        more_layout.addWidget(logs_button)
        more_layout.addWidget(advanced_settings_button)
        more_group.setLayout(more_layout)
        main_layout.addWidget(more_group)

        self.setLayout(main_layout)

    def change_language(self):
        lang_code = self.language_dropdown.currentData()
        app = QApplication.instance()
        load_language(app, lang_code, self.settings_handler)

        reply = QMessageBox.question(
            self,
            self.tr("Language Change"),
            self.tr("Language will apply after restart. Restart now?"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply == QMessageBox.Yes:
            main_win = self.window()
            if hasattr(main_win, "restart_app"):
                main_win.restart_app()

    def change_font(self, font: QFont):
        font_family = font.family()
        self.settings_handler.save_settings("font_family", font_family)
        ThemeManager.apply(font_family)

    def open_logs_window(self):
        dialog = LogsWindow(self, get_log_path())
        dialog.exec()

    def update_mode_dropdown(self, new_mode):
        self.modes_dropdown.blockSignals(True)
        self.modes_dropdown.setCurrentText(new_mode)
        self.modes_dropdown.blockSignals(False)

    def open_advanced_settings(self):
        dialog = AdvancedSettings(self.settings_handler, self)
        dialog.exec()

    def create_groupbox(self, title):
        groupbox = QGroupBox(title)
        return groupbox

    def set_dns_mode(self):
        dns_dict = {
            self.tr("Off (No DNS filtering)"): "off",
            self.tr("Block Adult Content"): "full",
            self.tr("Block Malware"): "malware"
        }
        selected_dns = self.dns_dropdown.currentText()
        self.dns_dropdown.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)

        try:
            cmd = run_warp_command("warp-cli", "dns", "families", dns_dict.get(selected_dns, 'off'))
            if cmd.returncode == 0:
                self.current_dns_mode = selected_dns
                self.settings_handler.save_settings("dns_mode", selected_dns)
                QMessageBox.information(self, self.tr("DNS Mode Saved"),
                                        self.tr("DNS mode set to: {}").format(selected_dns))
                logger.info(f"DNS mode set to: {selected_dns}")
            else:
                QMessageBox.warning(self, self.tr("Error"),
                                    self.tr("Failed to Set DNS Mode to {}: {}").format(selected_dns,
                                                                                       cmd.stderr.strip()))
                logger.error(f"Failed to Set DNS Mode to {selected_dns} : {cmd.stderr.strip()}")
                self.dns_dropdown.setCurrentText(self.current_dns_mode)
        except Exception as e:
            QMessageBox.warning(self, self.tr("Error"), self.tr("Command failed: {}").format(e))
            self.dns_dropdown.setCurrentText(self.current_dns_mode)
        finally:
            self.dns_dropdown.setEnabled(True)
            QApplication.restoreOverrideCursor()

    def _wait_for_warp_connected(self, timeout=20):
        start = time.time()
        while time.time() - start < timeout:
            status_cmd = run_warp_command("warp-cli", "status")
            if status_cmd.returncode == 0 and "Connected" in status_cmd.stdout:
                return True
            time.sleep(2)
        return False

    def set_mode(self):
        selected_mode = self.modes_dropdown.currentText()
        port_to_set = None

        if hasattr(self, "chained_proxy") and self.chained_proxy:
            try:
                self.chained_proxy.stop()
                logger.info("[ChainedProxy] Previous chained proxy stopped.")
            except Exception as e:
                logger.warning(f"[ChainedProxy] Failed to stop previous server: {e}")
            self.chained_proxy = None

        # Normal WARP proxy setup
        if selected_mode == "proxy":
            saved_port = self.settings_handler.get("proxy_port", "40000")
            port_str, ok = QInputDialog.getText(
                self,
                self.tr("Proxy Port Required"),
                self.tr("Enter proxy port (1–65535):"),
                text=str(saved_port)
            )
            if not ok:
                self.modes_dropdown.setCurrentText(self.current_mode)
                return

            try:
                port = int(port_str)
                if not (1 <= port <= 65535):
                    raise ValueError
                port_to_set = port
            except ValueError:
                QMessageBox.warning(
                    self, self.tr("Invalid Port"),
                    self.tr("Please enter a valid port number between 1 and 65535.")
                )
                self.modes_dropdown.setCurrentText(self.current_mode)
                return

        # Chained Proxy setup
        if selected_mode == "chained_proxy":
            raw = self.settings_handler.get("external_proxy", "")
            try:
                external = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                external = {}

            if not external or not external.get("host") or not external.get("port"):
                QMessageBox.warning(
                    self, self.tr("Missing Proxy"),
                    self.tr(
                        "You must configure an external proxy in Advanced Settings before using Chained Proxy mode.")
                )
                self.modes_dropdown.setCurrentText(self.current_mode)
                return

            saved_port = self.settings_handler.get("proxy_port", "40000")
            port_str, ok = QInputDialog.getText(
                self,
                self.tr("Warp Proxy Port Required"),
                self.tr("Enter local WARP proxy port (1–65535):"),
                text=str(saved_port)
            )
            if not ok:
                self.modes_dropdown.setCurrentText(self.current_mode)
                return

            try:
                port = int(port_str)
                if not (1 <= port <= 65535):
                    raise ValueError
                port_to_set = port
            except ValueError:
                QMessageBox.warning(
                    self, self.tr("Invalid Port"),
                    self.tr("Please enter a valid port number between 1 and 65535.")
                )
                self.modes_dropdown.setCurrentText(self.current_mode)
                return

        progress_dialog = QProgressDialog(self)
        progress_dialog.setWindowTitle(self.tr("Setting Mode"))
        progress_dialog.setLabelText(self.tr("Applying new mode... Please wait."))
        progress_dialog.setWindowModality(Qt.WindowModal)
        progress_dialog.setRange(0, 0)
        progress_dialog.setCancelButton(None)
        self.modes_dropdown.setEnabled(False)

        def task():
            if selected_mode in ("proxy", "chained_proxy") and port_to_set:
                set_port_cmd = run_warp_command("warp-cli", "proxy", "port", str(port_to_set))
                if set_port_cmd.returncode != 0:
                    raise RuntimeError(f"Failed to set proxy port:\n{set_port_cmd.stderr.strip()}")
                self.settings_handler.save_settings("proxy_port", str(port_to_set))

            if selected_mode == "chained_proxy":
                cmd = run_warp_command("warp-cli", "mode", "proxy")
                if cmd.returncode != 0:
                    raise RuntimeError(f"Failed to set WARP into proxy mode:\n{cmd.stderr.strip()}")

                status_cmd = run_warp_command("warp-cli", "status")
                if status_cmd.returncode == 0 and "Disconnected" in status_cmd.stdout:
                    logger.info("[ChainedProxy] WARP is disconnected. Attempting auto-connect...")
                    connect_cmd = run_warp_command("warp-cli", "connect")
                    if connect_cmd.returncode != 0:
                        raise RuntimeError(f"Failed to auto-connect WARP:\n{connect_cmd.stderr.strip()}")

                if not self._wait_for_warp_connected(timeout=20):
                    raise RuntimeError(
                        "WARP did not reach 'Connected' state in time. Please check your connection and retry.")

                forward_port = self.settings_handler.get("proxy_chain_local_forward_port", "41000")
                try:
                    forward_port = int(forward_port)
                except ValueError:
                    forward_port = 41000

                if forward_port == port_to_set:
                    raise RuntimeError("Chained proxy forward port cannot be the same as WARP proxy port.")

                proxy_checker = SOCKS5ChainedProxyServer(self.settings_handler, forward_port)
                if not proxy_checker.check_external_proxy():
                    run_warp_command("warp-cli", "mode", "proxy")
                    self.settings_handler.save_settings("mode", "proxy")
                    raise RuntimeError("External proxy check failed. Reverted to proxy mode.")

                return ("chained_proxy", forward_port)
            else:
                cmd = run_warp_command("warp-cli", "mode", selected_mode)
                if cmd.returncode != 0:
                    raise RuntimeError(f"Failed to set mode to {selected_mode}:\n{cmd.stderr.strip()}")
                return selected_mode

        def on_finished(result):
            progress_dialog.close()
            self.modes_dropdown.setEnabled(True)

            if isinstance(result, tuple):
                successful_mode, forward_port = result
            else:
                successful_mode, forward_port = result, None

            self.current_mode = successful_mode
            self.settings_handler.save_settings("mode", successful_mode)

            main_window = self.window()
            if isinstance(main_window, MainWindow):
                for action in main_window.modes_group.actions():
                    if action.text() == successful_mode:
                        action.setChecked(True)

                if successful_mode == "proxy":
                    warp_port = self.settings_handler.get("proxy_port", "40000")
                    main_window.info_label.setText(
                        self.tr(
                            "WARP proxy running on 127.0.0.1:<span style='color: #0078D4; font-weight: bold;'>{}</span>").format(
                            warp_port)
                    )
                    main_window.info_label.show()

                elif successful_mode == "chained_proxy":
                    self.chained_proxy = SOCKS5ChainedProxyServer(self.settings_handler, forward_port)
                    self.chained_proxy.start_background()

                    if not self.chained_proxy.check_local_proxy():
                        self.chained_proxy.stop()
                        run_warp_command("warp-cli", "mode", "proxy")
                        self.settings_handler.save_settings("mode", "proxy")
                        self.modes_dropdown.setCurrentText("proxy")
                        QMessageBox.warning(
                            self, self.tr("Chained Proxy"),
                            self.tr("Chained proxy server failed to start. Reverted to proxy mode.")
                        )
                        main_window.info_label.hide()
                        return

                    main_window.info_label.setText(
                        self.tr(
                            "Chained proxy (SOCKS5) running on 127.0.0.1:<span style='color: #0078D4; font-weight: bold;'>{}</span>").format(
                            forward_port)
                    )
                    main_window.info_label.show()
                else:
                    main_window.info_label.hide()

            logger.info(f"Successfully set mode to {successful_mode}")
            QMessageBox.information(self, self.tr("Mode Changed"),
                                    self.tr("Mode set to: {}").format(successful_mode))

        def on_error(exc):
            progress_dialog.close()
            self.modes_dropdown.setEnabled(True)
            logger.error(f"Error setting mode: {exc}")
            QMessageBox.warning(self, self.tr("Error"), str(exc))
            self.modes_dropdown.setCurrentText(self.current_mode)

        self._worker = run_in_worker(task, parent=self,
                                     on_done=on_finished,
                                     on_error=on_error)
        progress_dialog.show()


class MainWindow(QMainWindow):
    instance = None
    def __init__(self, settings_handler=None):
        super().__init__()
        MainWindow.instance = self
        self.force_exit = False
        self.settings_handler = settings_handler or SettingsHandler()
        if settings_handler is None:
            self.settings_handler.start()
        self.setWindowTitle(self.tr("PyWarp {}").format(CURRENT_VERSION))

        self.color_icon = QIcon(":/logo.png")
        self.gray_icon = QIcon(":/logo_gray.png")

        font_name = self.settings_handler.get("font_family", QApplication.font().family())
        ThemeManager.apply(str(font_name))
        self._last_ui_status = None

        try:
            self.setWindowIcon(self.color_icon)
        except:
            self.setWindowIcon(QIcon())

        self.setGeometry(100, 100, 400, 480)
        self.setWindowFlags(Qt.Window)
        self.current_error_box = None
        self.setMinimumSize(360, 600)
        self.setMaximumSize(450, 750)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # Status frame
        status_frame = QFrame()
        status_frame.setObjectName("statusFrame")
        status_layout = QHBoxLayout(status_frame)
        status_layout.setSpacing(8)
        status_layout.setContentsMargins(12, 12, 12, 12)

        self.toggle_switch = PowerButton()
        self.toggle_switch.toggled.connect(self.handle_toggle_signal)
        status_layout.addWidget(self.toggle_switch)

        status_info = QVBoxLayout()
        status_info.setAlignment(Qt.AlignRight)

        self.status_label = QLabel(self.tr("Status: Disconnected"))
        self.status_label.setFont(QFont("Segoe UI", 12))

        self.ip_label = QLabel(
            self.tr("IPv4: <span style='color: #0078D4; font-weight: bold;'>Detecting...</span>")
        )

        self.ip_label.setFont(QFont("Segoe UI", 12))
        self.ip_label.setToolTip(self.tr("This is your current public IP address."))

        self.protocol_label = QLabel(self.tr("Protocol: <span style='color: #0078D4; font-weight: bold;'>Detecting...</span>"))

        self.source_label = QLabel(
            self.tr("Source: <a href='https://github.com/saeedmasoudie/pywarp' "
                    "style='color: #0078D4; font-weight: bold; text-decoration: none;'>"
                    "GitHub</a>"))
        self.source_label.setTextFormat(Qt.RichText)
        self.source_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.source_label.setOpenExternalLinks(True)
        self.source_label.setToolTip(self.tr("Click here to visit the app's source code on GitHub"))

        status_info.addWidget(self.status_label)
        status_info.addWidget(self.ip_label)
        status_info.addWidget(self.protocol_label)
        status_info.addWidget(self.source_label)

        status_layout.addLayout(status_info)
        main_layout.addWidget(status_frame)

        # Button layout
        button_layout = QHBoxLayout()
        self.stacked_widget = QStackedWidget()
        self.buttons = {}

        # Stats widget
        stats_widget = QWidget()
        stats_layout = QVBoxLayout(stats_widget)

        self.stats_table = QTableWidget(8, 2)
        self.stats_table.setHorizontalHeaderLabels([self.tr("Metric"), self.tr("Value")])
        self.stats_table.verticalHeader().setVisible(False)
        self.stats_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.stats_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.stats_table.setMaximumHeight(280)
        self.stats_table.setMinimumHeight(240)
        self.stats_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.stats_table.setFocusPolicy(Qt.NoFocus)
        self.stats_table.setMouseTracking(False)

        stats_labels = [
            self.tr("Protocol"), self.tr("IPv4 Endpoint"), self.tr("IPv6 Endpoint"), self.tr("Last Handshake"),
            self.tr("Sent Data"), self.tr("Received Data"), self.tr("Latency"), self.tr("Loss")
        ]
        for i, label in enumerate(stats_labels):
            self.stats_table.setItem(i, 0, QTableWidgetItem(label))

        stats_layout.addWidget(self.stats_table)
        self.stacked_widget.addWidget(stats_widget)

        # Settings
        settings_widget = SettingsPage(settings_handler=self.settings_handler)
        self.stacked_widget.addWidget(settings_widget)
        self.silent_mode = to_bool(self.settings_handler.get("silent_mode", False))

        self.setup_tray()

        # Buttons
        btn_texts = [self.tr("Network Stats"), self.tr("Settings"), self.tr("Protocol")]
        for idx, btn_text in enumerate(btn_texts):
            btn = QPushButton(btn_text)
            btn.setMinimumHeight(32)
            if btn_text != self.tr("Protocol"):
                btn.clicked.connect(lambda _, i=idx: (
                    self.stacked_widget.setCurrentIndex(i),
                    self.update_button_styles()))
            else:
                btn.clicked.connect(lambda _: (
                    self.set_protocol(),
                    self.update_button_styles()))
            self.buttons[btn_text] = btn
            button_layout.addWidget(btn)

        self.update_button_styles()

        main_layout.addLayout(button_layout)

        self.info_label = QLabel("")
        self.info_label.setAlignment(Qt.AlignCenter)
        current_mode = self.settings_handler.get("mode", "warp")
        if current_mode == "proxy":
            port = self.settings_handler.get("proxy_port", "40000")
            self.info_label.setText(
                self.tr(
                    "Proxy running on 127.0.0.1:<span style='color: #0078D4; font-weight: bold;'>{}</span>").format(
                    port)
            )
        elif current_mode == "chained_proxy":
            port = self.settings_handler.get("proxy_chain_local_forward_port", "41000")
            self.info_label.setText(
                self.tr(
                    "Chained proxy (SOCKS5) running on 127.0.0.1<span style='color: #0078D4; font-weight: bold;'>{}</span>").format(
                    port)
            )
        else:
            self.info_label.hide()

        main_layout.addWidget(self.info_label)
        main_layout.addWidget(self.stacked_widget)

        self._ready_checks = {"status": False, "protocol": False, "ip": False}

        self.loading_overlay = LoadingOverlay(self)
        self.loading_overlay.show()
        self._loading_fallback_timer = QTimer(self)
        self._loading_fallback_timer.setSingleShot(True)
        self._loading_fallback_timer.timeout.connect(self._force_ready)
        self._loading_fallback_timer.start(10000)

        QTimer.singleShot(200, self._start_background_tasks)

    def _start_background_tasks(self):
        QTimer.singleShot(1000, lambda: run_in_worker(
            fetch_protocol,
            parent=self,
            on_done=self._on_protocol_ready,
            on_error=lambda e: self._on_protocol_ready("Error")
        ))

        try:
            self.status_checker = WarpStatusHandler(parent=self)
            self.status_checker.status_signal.connect(self._on_status_ready)
        except Exception:
            logger.exception("Status checker failed")

        try:
            self.stats_checker = WarpStatsHandler(self.status_checker, parent=self)
            self.stats_checker.stats_signal.connect(self.update_stats_display)
        except Exception:
            logger.exception("Stats checker failed")

        try:
            self.ip_fetcher = IpFetcher(self.settings_handler, self.status_checker, parent=self)
            self.ip_fetcher.ip_ready.connect(self._on_ip_ready)
            self.ip_fetcher.fetch_ip()
        except Exception:
            logger.exception("IP fetcher failed")

    def restart_app(self):
        self.force_exit = True
        QApplication.quit()
        QProcess.startDetached(sys.executable, sys.argv + ["--restarting"])

    def _on_protocol_ready(self, protocol):
        self.protocol_label.setText(
            self.tr("Protocol: <span style='color: #0078D4; font-weight: bold;'>{}</span>").format(protocol)
        )
        self._ready_checks["protocol"] = True
        self._check_ready()

    def _on_ip_ready(self, ip):
        self.ip_label.setText(self.tr("IPv4: <span style='color: #0078D4; font-weight: bold;'>{}</span>").format(ip))
        self._ready_checks["ip"] = True
        self._check_ready()

    def _on_status_ready(self, status):
        self.update_status(status)
        self._ready_checks["status"] = True
        self._check_ready()

    def _check_ready(self):
        if all(self._ready_checks.values()):
            try:
                if hasattr(self, "_loading_fallback_timer"):
                    self._loading_fallback_timer.stop()
            except Exception:
                pass
            if hasattr(self, "loading_overlay") and self.loading_overlay:
                self.loading_overlay.hide()
                self.loading_overlay.deleteLater()
                self.loading_overlay = None

    def _force_ready(self):
        logger.warning("Loading overlay fallback: forcing UI ready state.")
        for k in list(self._ready_checks.keys()):
            self._ready_checks[k] = True
        self._check_ready()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "loading_overlay") and self.loading_overlay:
            self.loading_overlay.setGeometry(self.rect())

    def closeEvent(self, event):
        if getattr(self, "force_exit", False):
            try:
                if hasattr(self, "_protocol_worker"):
                    self._protocol_worker.quit()
                    self._protocol_worker.wait(2000)

                run_warp_command("warp-cli", "disconnect")
                logger.info("PyWarp quit and Warp disconnected successfully.")
                server.removeServer(SERVER_NAME)

            except Exception as e:
                logger.error("Error during shutdown: %s", e)

            event.accept()
            QApplication.quit()
            return

        behavior = self.settings_handler.get("close_behavior", "ask")

        if behavior == "hide":
            event.ignore()
            self.hide()
            return
        elif behavior == "close":
            chosen = "close"
        else:
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Question)
            msg_box.setWindowTitle(self.tr("Exit Confirmation"))
            msg_box.setText(self.tr("Do you want to close the app or hide it?"))

            close_button = msg_box.addButton(self.tr("Close"), QMessageBox.AcceptRole)
            hide_button = msg_box.addButton(self.tr("Hide"), QMessageBox.RejectRole)
            remember_box = QCheckBox(self.tr("Remember my choice"))
            msg_box.setCheckBox(remember_box)
            msg_box.exec()

            chosen = "close" if msg_box.clickedButton() == close_button else "hide"
            if remember_box.isChecked():
                self.settings_handler.save_settings("close_behavior", chosen)
                self.update_close_behavior_menu(chosen)

        if chosen == "close":
            try:
                if hasattr(self, "_protocol_worker"):
                    self._protocol_worker.quit()
                    self._protocol_worker.wait(2000)

                run_warp_command("warp-cli", "disconnect")
                logger.info("PyWarp quit and Warp disconnected successfully.")
                server.removeServer(SERVER_NAME)

            except Exception as e:
                logger.error("Error during shutdown: %s", e)

            event.accept()
            QApplication.quit()
        else:
            event.ignore()
            self.hide()

    def show_about(self):
        about_dialog = QMessageBox(self)
        about_dialog.setWindowTitle(self.tr("About Me"))
        about_dialog.setText(
            self.tr(
                "Hi, I'm Saeed/Eric, a Python developer passionate about creating efficient applications and constantly learning new things. "
                "You can explore my work on GitHub."))
        github_button = QPushButton(self.tr("Visit GitHub"))
        github_button.clicked.connect(
            lambda: webbrowser.open("https://github.com/saeedmasoudie"))
        about_dialog.addButton(github_button, QMessageBox.ActionRole)
        about_dialog.addButton(self.tr("Close"), QMessageBox.RejectRole)
        about_dialog.exec()

    def show_tutorials(self):
        tutorials_dialog = QMessageBox(self)
        tutorials_dialog.setWindowTitle(self.tr("PyWarp Tutorials"))
        tutorials_dialog.setText(
            self.tr("<h2>Welcome to PyWarp!</h2>"
                    "<p>This application allows you to manage Cloudflare Warp settings with ease.</p>"
                    "<ul>"
                    "<li><b>Modes:</b> Select Warp mode (warp, doh, proxy, etc.).</li>"
                    "<li><b>DNS Mode:</b> Choose filtering (off, family-friendly, or malware).</li>"
                    "<li><b>Endpoint:</b> Set a custom endpoint for advanced configurations.</li>"
                    "<li><b>Protocol:</b> Choose your connection protocol.</li>"
                    "</ul>"
                    "<p><b>⚠️ Important Warning:</b> Disconnect Warp before changing DNS mode or custom endpoint.</p>"))
        tutorials_dialog.addButton(self.tr("Close"), QMessageBox.RejectRole)
        tutorials_dialog.exec()

    def setup_tray(self):
        try:
            self.tray_icon = QSystemTrayIcon(self.gray_icon, self)
        except:
            self.tray_icon = QSystemTrayIcon(QIcon(), self)

        self.tray_icon.setToolTip(self.tr("PyWarp - CloudFlare Warp GUI"))
        tray_menu = QMenu(self)
        show_action = QAction(self.tr("Show App"), self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)
        tray_menu.addSeparator()

        # Connect/Disconnect Action
        self.toggle_connection_action = QAction(self.tr("Connect"), self)
        self.toggle_connection_action.triggered.connect(self.toggle_connection_from_tray)
        tray_menu.addAction(self.toggle_connection_action)

        # Silent Mode Action
        self.silent_mode_action = QAction(self.tr("Silent Mode"), self, checkable=True)
        self.silent_mode_action.setChecked(bool(self.silent_mode))
        self.silent_mode_action.toggled.connect(self.toggle_silent_mode)
        tray_menu.addAction(self.silent_mode_action)

        # Close Behavior submenu
        close_behavior_menu = QMenu(self.tr("On Close"), self)
        self.close_behavior_actions = {}
        for option, label in [("ask", self.tr("Ask Every Time")),
                              ("hide", self.tr("Always Hide")),
                              ("close", self.tr("Always Close"))]:
            action = QAction(label, self, checkable=True)
            action.setChecked(self.settings_handler.get("close_behavior", "ask") == option)
            action.triggered.connect(lambda checked, opt=option: self.set_close_behavior(opt))
            close_behavior_menu.addAction(action)
            self.close_behavior_actions[option] = action

        tray_menu.addMenu(close_behavior_menu)

        # Modes Submenu
        modes_menu = QMenu(self.tr("Set Mode"), self)
        self.modes_group = QActionGroup(self)
        self.modes_group.setExclusive(True)
        modes_list = ["warp", "doh", "warp+doh", "dot", "warp+dot", "proxy", "tunnel_only"]
        current_mode = self.settings_handler.get("mode", "warp")

        for mode in modes_list:
            action = QAction(mode, self, checkable=True)
            action.setChecked(mode == current_mode)
            action.triggered.connect(lambda checked, m=mode: self.set_warp_mode(m))
            self.modes_group.addAction(action)
            modes_menu.addAction(action)

        tray_menu.addMenu(modes_menu)
        tray_menu.addSeparator()

        help_menu = tray_menu.addMenu(self.tr("Help"))

        about_action = QAction(self.tr("About Me"), self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

        tutorials_action = QAction(self.tr("Tutorials"), self)
        tutorials_action.triggered.connect(self.show_tutorials)
        help_menu.addAction(tutorials_action)

        exit_action = QAction(self.tr("Exit"), self)
        exit_action.triggered.connect(self.close_app_tray)
        tray_menu.addAction(exit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.tray_icon.show()

    def close_app_tray(self):
        self.force_exit = True
        self.close()

    def set_close_behavior(self, option):
        self.settings_handler.save_settings("close_behavior", option)
        self.update_close_behavior_menu(option)

    def update_close_behavior_menu(self, selected_option):
        for option, action in self.close_behavior_actions.items():
            action.setChecked(option == selected_option)

    def on_tray_icon_activated(self, reason: object) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.showNormal()
            self.raise_()
            self.activateWindow()

    def toggle_connection_from_tray(self):
        self.toggle_switch.power_button.click()

    def toggle_silent_mode(self, checked: bool):
        self.silent_mode = bool(checked)
        self.settings_handler.save_settings("silent_mode", self.silent_mode)

    def set_warp_mode(self, selected_mode):
        settings_widget = self.stacked_widget.widget(1)
        if not isinstance(settings_widget, SettingsPage):
            return

        settings_widget.modes_dropdown.blockSignals(True)
        settings_widget.modes_dropdown.setCurrentText(selected_mode)
        settings_widget.modes_dropdown.blockSignals(False)

        settings_widget.set_mode()

    def parse_with_unit(self, value: str):
        match = re.match(r"([\d.]+)\s*([A-Za-z]*)", value.strip())
        if match:
            num = float(match.group(1))
            unit = " " + match.group(2) if match.group(2) else ""
            return num, unit
        return 0.0, ""

    def animate_number(self, row, col, start_value, end_value, suffix="", color_func=None, decimals=2,
                       format_func=None):
        animation = QVariantAnimation(self)
        animation.setStartValue(start_value)
        animation.setEndValue(end_value)
        animation.setDuration(5000)
        animation.setEasingCurve(QEasingCurve.OutCubic)

        def on_value_changed(value):
            if format_func:
                text = format_func(value)
            elif decimals > 0:
                text = f"{value:.{decimals}f}{suffix}"
            else:
                text = f"{int(value)}{suffix}"

            item = QTableWidgetItem(text)
            if color_func:
                item.setForeground(QBrush(QColor(color_func(value))))
            self.stats_table.setItem(row, col, item)

        animation.valueChanged.connect(on_value_changed)
        animation.start()

        if not hasattr(self, "_animations"):
            self._animations = []
        self._animations.append(animation)
        animation.finished.connect(lambda: self._animations.remove(animation))

    def update_stats_display(self, stats_list):
        if hasattr(self, "_animations"):
            for anim in self._animations[:]:
                anim.stop()
            self._animations.clear()

        if not stats_list:
            for row in range(8):
                self.stats_table.setItem(row, 1, QTableWidgetItem(""))
            return

        try:
            protocol, endpoints, handshake_time, sent, received, latency, loss = stats_list

            # --- Protocol & Endpoints ---
            self.stats_table.setItem(0, 1, QTableWidgetItem(protocol))
            endpoints_value = endpoints.split(',')
            ipv4 = endpoints_value[0] if endpoints_value else self.tr('Not Available')
            ipv6 = endpoints_value[1] if len(endpoints_value) > 1 and len(endpoints_value[1]) > 5 else self.tr(
                'Not Available')
            self.stats_table.setItem(1, 1, QTableWidgetItem(ipv4))
            self.stats_table.setItem(2, 1, QTableWidgetItem(ipv6))

            # --- Handshake ---
            handshake_time_cleaned = handshake_time.replace('s', '')
            handshake_value = int(handshake_time_cleaned) if handshake_time_cleaned.isdigit() else 0

            def handshake_color(val):
                if val < 1800:
                    return "green"
                elif val < 3600:
                    return "orange"
                return "red"

            prev_handshake = getattr(self, "_prev_handshake", 0)
            self.animate_number(
                3, 1,
                prev_handshake,
                handshake_value,
                suffix="",
                color_func=handshake_color,
                decimals=0,
                format_func=format_seconds_to_hms
            )
            self._prev_handshake = handshake_value

            # --- Sent ---
            sent_value, sent_unit = self.parse_with_unit(sent)
            prev_sent = getattr(self, "_prev_sent", 0.0)
            self.animate_number(4, 1, prev_sent, sent_value, sent_unit, None, decimals=2)
            self._prev_sent = sent_value

            # --- Received ---
            received_value, recv_unit = self.parse_with_unit(received)
            prev_received = getattr(self, "_prev_received", 0.0)
            self.animate_number(5, 1, prev_received, received_value, recv_unit, None, decimals=2)
            self._prev_received = received_value

            # --- Latency ---
            latency_value = int(latency.replace("ms", "").strip()) if latency.replace("ms", "").strip().isdigit() else 0

            def latency_color(val):
                if val < 100:
                    return "green"
                elif val < 200:
                    return "orange"
                return "red"

            prev_latency = getattr(self, "_prev_latency", 0)
            self.animate_number(6, 1, prev_latency, latency_value, " ms", latency_color, decimals=0)
            self._prev_latency = latency_value

            # --- Loss ---
            loss_parts = loss.split(";")[0].replace("%", "").strip()
            try:
                loss_value = float(loss_parts)
            except ValueError:
                loss_value = 0.0

            def loss_color(val):
                if val < 1:
                    return "green"
                elif val < 5:
                    return "orange"
                return "red"

            prev_loss = getattr(self, "_prev_loss", 0.0)
            self.animate_number(7, 1, prev_loss, loss_value, "%", loss_color, decimals=2)
            self._prev_loss = loss_value

        except Exception as e:
            logger.error(f"Error updating stats display: {e}")

    def handle_toggle_signal(self, signal):
        if signal == 'ForceRefresh':
            self.force_status_check()
        else:
            self.update_status(signal)

    def force_status_check(self):
        """Force an immediate status check"""

        def check_status():
            try:
                process = run_warp_command('warp-cli', 'status')

                if process.returncode != 0:
                    current_status = "Disconnected"
                else:
                    status_output = process.stdout
                    if "Connected" in status_output:
                        current_status = "Connected"
                    elif "Disconnected" in status_output:
                        current_status = "Disconnected"
                    elif "Connecting" in status_output:
                        current_status = "Connecting"
                    else:
                        current_status = "Disconnected"

                # Update UI in main thread
                QTimer.singleShot(0, lambda: self.update_status(current_status))

            except Exception as e:
                logger.error(f"Error in force status check: {e}")
                QTimer.singleShot(0, lambda: self.update_status("Disconnected"))

        threading.Thread(target=check_status, daemon=True).start()

    def on_warp_status_changed(self, status):
        if status in ["Connected", "Disconnected"]:
            self.ip_label.setText(self.tr("IPv4: <span style='color: #0078D4; font-weight: bold;'>Receiving...</span>"))
            if hasattr(self, "ip_fetcher") and self.ip_fetcher is not None:
                QTimer.singleShot(2000, self.ip_fetcher.fetch_ip)
            else:
                try:
                    self.ip_fetcher = IpFetcher(self.settings_handler, self.status_checker, parent=self)
                    self.ip_fetcher.ip_ready.connect(self._on_ip_ready)
                    QTimer.singleShot(2000, self.ip_fetcher.fetch_ip)
                except Exception as e:
                    logger.error("Failed to lazy-create ip_fetcher: %s", e)
        elif status in ["Failed", "No Network"]:
            self.ip_label.setText(self.tr("IPv4: <span style='color: #0078D4; font-weight: bold;'>Unavailable</span>"))
        else:
            self.ip_label.setText(self.tr("IPv4: <span style='color: #0078D4; font-weight: bold;'>Receiving...</span>"))

    def update_ip_label(self, ip):
        self.ip_label.setText(
            self.tr("IPv4: <span style='color: #0078D4; font-weight: bold;'>{}</span>").format(ip)
        )

    def update_status(self, status):
        if self._last_ui_status == status:
            return

        self._last_ui_status = status
        self.on_warp_status_changed(status)

        if status == 'Connected':
            self.tray_icon.setIcon(self.color_icon)
            self.toggle_connection_action.setText(self.tr("Disconnect"))

        else:
            self.tray_icon.setIcon(self.gray_icon)
            self.toggle_connection_action.setText(self.tr("Connect"))

        status_messages = {
            'Connected': self.tr("Status: <span style='color: green; font-weight: bold;'>Connected</span>"),
            'Disconnected': self.tr("Status: <span style='color: red; font-weight: bold;'>Disconnected</span>"),
            'Connecting': self.tr("Status: <span style='color: orange; font-weight: bold;'>Connecting...</span>"),
            'Disconnecting': self.tr("Status: <span style='color: orange; font-weight: bold;'>Disconnecting...</span>"),
            'No Network': self.tr("Status: <span style='color: red; font-weight: bold;'>No Network</span>")
        }
        self.status_label.setText(
            status_messages.get(
                status,
                self.tr("Status: <span style='color: red; font-weight: bold;'>Network Error</span>")
            )
        )

        self.toggle_switch.update_button_state(status)

    def show_critical_error(self, title, message):
        if self.silent_mode:
            logger.error(f"{title}: {message}")
            return
        else:
            self.activateWindow()
            self.raise_()
            QTimer.singleShot(100, lambda: self.show_non_blocking_error(title, message))

    def show_non_blocking_error(self, title, message):
        if self.current_error_box is not None:
            try:
                self.current_error_box.close()
            except Exception:
                pass
            self.current_error_box = None

        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setAttribute(Qt.WA_DeleteOnClose)

        checkbox = QCheckBox(self.tr("Don't show error messages again"))
        checkbox.setStyleSheet("QCheckBox { margin-top: 12px; margin-left: 4px; }")
        msg_box.setCheckBox(checkbox)

        def on_close():
            self.current_error_box = None
            QTimer.singleShot(500, self.force_status_check)
            if checkbox.isChecked():
                self.silent_mode = True
                self.settings_handler.save_settings("silent_mode", True)

        msg_box.finished.connect(on_close)
        self.current_error_box = msg_box
        msg_box.show()

    def update_button_styles(self):
        current_index = self.stacked_widget.currentIndex()
        for idx, (text, btn) in enumerate(self.buttons.items()):
            is_active = idx == current_index
            btn.setProperty("active", is_active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def set_protocol(self):
        dlg = QMessageBox(self)
        dlg.setWindowTitle(self.tr("Change The Protocol"))
        dlg.setText(self.tr("Which protocol do you want to use?"))
        dlg.setIcon(QMessageBox.Question)

        custom_button1 = dlg.addButton("WireGuard", QMessageBox.ActionRole)
        custom_button2 = dlg.addButton("MASQUE", QMessageBox.ActionRole)
        cancel_button = dlg.addButton(QMessageBox.Cancel)
        dlg.exec()

        if dlg.clickedButton() == custom_button1:
            self.set_warp_protocol("WireGuard")
        elif dlg.clickedButton() == custom_button2:
            self.set_warp_protocol("MASQUE")

    def set_warp_protocol(self, protocol):
        try:
            result = run_warp_command('warp-cli', 'tunnel', 'protocol', 'set', protocol)
            if result.returncode == 0:
                QMessageBox.information(
                    self, self.tr("Protocol Changed"),
                    self.tr("Protocol successfully changed to {}.").format(protocol))
                logger.info(f"Protocol successfully changed to {protocol}")
                self.protocol_label.setText(
                    self.tr("Protocol: <span style='color: #0078D4; font-weight: bold;'>{}</span>").format(protocol))
            else:
                QMessageBox.critical(self, self.tr("Error"),
                                     self.tr("Failed to set protocol: {}").format(result.stderr))
        except Exception as e:
            QMessageBox.critical(self, self.tr("Error"), self.tr("Failed to set protocol: {}").format(str(e)))


class WarpInstaller:
    def __init__(self, parent=None):
        self.parent = parent
        self.download_url = self.get_os_download_link()
        self.appdata_dir = Path(os.getenv("APPDATA") or Path.home() / ".pywarp") / "warp"
        self.appdata_dir.mkdir(parents=True, exist_ok=True)

    def tr(self, text):
        return QCoreApplication.translate(self.__class__.__name__, text)

    def is_warp_installed(self):
        os_name = platform.system()
        if os_name == "Windows":
            if shutil.which("warp-cli"):
                return True

            warp_cli, warp_svc = self._portable_paths()
            if warp_cli.exists() and warp_svc.exists():
                if not self._is_warp_svc_running_windows():
                    self._ensure_warp_svc_running_windows()
                return True
            return False

        return shutil.which("warp-cli") is not None

    def get_os_download_link(self):
        os_name = platform.system()
        if os_name == "Windows":
            return "https://package.cloudflareclient.com/latest/Cloudflare_WARP_Release-x64.msi"
        elif os_name == "Darwin":
            return "https://package.cloudflareclient.com/latest/Cloudflare_WARP.dmg"
        else:
            return None

    def get_manual_download_page(self):
        return "https://developers.cloudflare.com/cloudflare-one/connections/connect-devices/warp/download-warp/"

    def show_install_prompt(self):
        msg_box = QMessageBox(self.parent)
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setWindowTitle(self.tr("Warp Not Found"))
        msg_box.setText(self.tr("Cloudflare WARP is not installed.\n\nDo you want to install it automatically?"))

        portable_button = None
        if platform.system() == "Windows":
            portable_button = msg_box.addButton(self.tr("Portable Install"), QMessageBox.ActionRole)

        auto_install_button = msg_box.addButton(self.tr("Auto Install"), QMessageBox.AcceptRole)
        manual_button = msg_box.addButton(self.tr("Manual Install"), QMessageBox.ActionRole)
        retry_button = msg_box.addButton(self.tr("Retry Check"), QMessageBox.DestructiveRole)
        cancel_button = msg_box.addButton(QMessageBox.Cancel)
        msg_box.exec()

        clicked = msg_box.clickedButton()
        if clicked == portable_button:
            self.install_windows_portable_zip()
        elif clicked == auto_install_button:
            self.start_auto_install()
        elif clicked == manual_button:
            webbrowser.open(self.get_manual_download_page())
            sys.exit()
        elif clicked == retry_button:
            self.retry_install_check()
        else:
            sys.exit()

    def start_auto_install(self):
        os_name = platform.system()
        if os_name == "Windows":
            self.install_windows_portable_zip()
            return

        if self.download_url is None:
            self.install_linux_package()
            return

        self.download_thread = DownloadWorker(self.download_url, parent=self)
        self.progress_dialog = QProgressDialog(
            self.tr("Downloading WARP..."),
            self.tr("Cancel"),
            0, 100,
            self.parent
        )
        self.progress_dialog.setWindowTitle(self.tr("Downloading WARP"))
        self.progress_dialog.setWindowModality(Qt.WindowModal)

        self.download_thread.progress.connect(self.progress_dialog.setValue)
        self.progress_dialog.canceled.connect(self.download_thread.abort)
        self.download_thread.finished.connect(self.on_download_finished)

        self.download_thread.start()
        self.progress_dialog.exec()

    def install_windows_portable_zip(self):
        try:
            zip_path = self.appdata_dir / "warp_assets.zip"

            progress = QProgressDialog(
                self.tr("Downloading portable WARP..."),
                self.tr("Cancel"), 0, 100, self.parent
            )
            progress.setWindowTitle(self.tr("Downloading"))
            progress.setWindowModality(Qt.WindowModal)
            progress.setValue(0)

            with requests.get(WARP_ASSETS, stream=True, timeout=120) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length", 0))
                downloaded = 0
                with open(zip_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total:
                                progress.setValue(int(downloaded * 100 / total))
                            if progress.wasCanceled():
                                r.close()
                                zip_path.unlink(missing_ok=True)
                                return

            progress.setValue(100)
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(self.appdata_dir)

            zip_path.unlink(missing_ok=True)

            self._ensure_warp_svc_running_windows()
            self.register_and_activate_warp()

        except Exception as e:
            QMessageBox.critical(
                self.parent, self.tr("Warp Install Failed"),
                self.tr("Could not setup portable WARP from ZIP:\n{}").format(e)
            )
            self._fallback_windows_prompt()

    def _fallback_windows_prompt(self):
        if self.download_url:
            self.download_thread = DownloadWorker(self.download_url, parent=self)
            self.progress_dialog = QProgressDialog(
                self.tr("Downloading WARP (MSI fallback)..."),
                self.tr("Cancel"),
                0, 100,
                self.parent
            )
            self.progress_dialog.setWindowTitle(self.tr("Downloading WARP"))
            self.progress_dialog.setWindowModality(Qt.WindowModal)

            self.download_thread.progress.connect(self.progress_dialog.setValue)
            self.progress_dialog.canceled.connect(self.download_thread.abort)
            self.download_thread.finished.connect(self.on_download_finished)

            self.download_thread.start()
            self.progress_dialog.exec()
        else:
            self.show_install_prompt()

    def _portable_paths(self):
        return (self.appdata_dir / "warp-cli.exe", self.appdata_dir / "warp-svc.exe")

    def _is_warp_svc_running_windows(self):
        try:
            out = subprocess.check_output(["tasklist"], text=True, **safe_subprocess_args())
            return "warp-svc.exe" in out
        except Exception:
            return False

    def _ensure_warp_svc_running_windows(self):
        if not self._is_warp_svc_running_windows():
            _, warp_svc = self._portable_paths()
            if warp_svc.exists():
                subprocess.Popen([str(warp_svc)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 **safe_subprocess_args())
                for _ in range(5):
                    time.sleep(1)
                    if self._is_warp_svc_running_windows():
                        return
                raise RuntimeError("warp-svc failed to start")

    def on_download_finished(self, success, file_path):
        self.progress_dialog.close()
        if success:
            self.install_downloaded_file(file_path)
        else:
            QMessageBox.critical(self.parent, self.tr("Download Failed"), self.tr("Failed to download WARP installer."))
            self.show_install_prompt()

    def install_downloaded_file(self, file_path):
        try:
            os_name = platform.system()
            if os_name == "Windows":
                subprocess.run(["msiexec", "/i", file_path, "/quiet", "/norestart"],
                               check=True, timeout=600, **safe_subprocess_args())
            elif os_name == "Darwin":
                subprocess.run(["open", file_path], check=True, timeout=60)
            else:
                QMessageBox.critical(self.parent, self.tr("Unsupported"),
                                     self.tr("Automatic install not supported for this OS."))
                sys.exit()
            self.register_and_activate_warp()
        except subprocess.CalledProcessError as e:
            QMessageBox.critical(self.parent, self.tr("Installation Failed"),
                                 self.tr("Failed to install WARP: {}").format(e))
            self.show_install_prompt()
        except Exception as e:
            QMessageBox.critical(self.parent, self.tr("Installation Failed"),
                                 self.tr("Installation error: {}").format(e))
            self.show_install_prompt()

    def install_linux_package(self):
        msg_box = QMessageBox(self.parent)
        msg_box.setWindowTitle(self.tr("Linux Installation"))
        msg_box.setText(self.tr(
            "Automatic installation is only partially supported on Linux.\n\n"
            "For most reliable results, please follow the official Cloudflare guide:\n"
            "https://developers.cloudflare.com/cloudflare-one/connections/connect-devices/warp/download-warp/\n\n"
            "Do you want PyWarp to try installing via your package manager?"
        ))
        install_button = msg_box.addButton(self.tr("Try Auto Install"), QMessageBox.AcceptRole)
        manual_button = msg_box.addButton(self.tr("Open Manual Guide"), QMessageBox.ActionRole)
        cancel_button = msg_box.addButton(QMessageBox.Cancel)
        msg_box.exec()

        clicked = msg_box.clickedButton()
        if clicked == manual_button:
            webbrowser.open(self.get_manual_download_page())
            return
        if clicked != install_button:
            sys.exit()

        try:
            pm = self.detect_linux_package_manager()
            if pm == "apt":
                self.install_with_apt()
            elif pm in ("yum", "dnf"):
                self.install_with_yum_dnf(pm)
            else:
                QMessageBox.warning(self.parent, self.tr("Unsupported"),
                                    self.tr("Your package manager is not supported for auto-install.\n"
                                            "Please use the manual guide instead."))
                webbrowser.open(self.get_manual_download_page())
                return

            self.register_and_activate_warp()

        except subprocess.CalledProcessError as e:
            QMessageBox.critical(self.parent, self.tr("Installation Failed"),
                                 self.tr("An error occurred:\n{}").format(e))
            self.show_install_prompt()
        except Exception as e:
            QMessageBox.critical(self.parent, self.tr("Installation Failed"),
                                 self.tr("Installation error: {}").format(e))
            self.show_install_prompt()

    def install_with_apt(self):
        commands = [
            ["sudo", "apt", "update"],
            ["sudo", "apt", "install", "-y", "curl", "gpg", "lsb-release", "apt-transport-https", "ca-certificates",
             "sudo"],
            ["bash", "-c",
             'curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | gpg --dearmor --yes -o /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg'],
        ]
        for cmd in commands:
            subprocess.run(cmd, check=True, timeout=300)

        distro = subprocess.check_output(["lsb_release", "-cs"], timeout=60, text=True,
                                         **safe_subprocess_args()).strip()
        repo_cmd = [
            "bash", "-c",
            f'echo "deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] '
            f'https://pkg.cloudflareclient.com/ {distro} main" | '
            f'sudo tee /etc/apt/sources.list.d/cloudflare-client.list'
        ]
        subprocess.run(repo_cmd, check=True, timeout=60)
        subprocess.run(["sudo", "apt", "update"], check=True, timeout=300)
        subprocess.run(["sudo", "apt", "install", "-y", "cloudflare-warp"], check=True, timeout=300)

    def install_with_yum_dnf(self, pm):
        repo_cmd = ["bash", "-c",
                    'curl -fsSL https://pkg.cloudflareclient.com/cloudflare-warp-ascii.repo | '
                    'sudo tee /etc/yum.repos.d/cloudflare-warp.repo']
        subprocess.run(repo_cmd, check=True, timeout=120)
        subprocess.run(["sudo", pm, "check-update"], check=False, timeout=300)
        subprocess.run(["sudo", pm, "install", "-y", "curl", "sudo", "coreutils"], check=True, timeout=300)
        subprocess.run(["sudo", pm, "check-update"], check=False, timeout=300)
        subprocess.run(["sudo", pm, "install", "-y", "cloudflare-warp"], check=True, timeout=600)

    def detect_linux_package_manager(self):
        if shutil.which("apt"):
            return "apt"
        if shutil.which("dnf"):
            return "dnf"
        if shutil.which("yum"):
            return "yum"
        if shutil.which("pacman"):
            return "pacman"
        return None

    def retry_install_check(self):
        if self.is_warp_installed():
            QMessageBox.information(self.parent, self.tr("Warp Found"), self.tr("WARP is now installed!"))
        else:
            self.show_install_prompt()

    def register_and_activate_warp(self):
        try:
            os_name = platform.system()
            if os_name == "Windows" and not shutil.which("warp-cli"):
                warp_cli, _ = self._portable_paths()
                cmd_register = [str(warp_cli), "register"]
                cmd_tos = [str(warp_cli), "accept-tos"]
            else:
                cmd_register = ["warp-cli", "register"]
                cmd_tos = ["warp-cli", "accept-tos"]

            subprocess.run(cmd_register, check=True, timeout=60)
            subprocess.run(cmd_tos, check=True, timeout=60)

            QMessageBox.information(self.parent, self.tr("Warp Ready"),
                                    self.tr("WARP has been registered and TOS accepted successfully!"))

        except subprocess.CalledProcessError as e:
            QMessageBox.critical(self.parent, self.tr("Warp Activation Failed"),
                                 self.tr("Failed to activate WARP: {}").format(e))
        except Exception as e:
            QMessageBox.critical(self.parent, self.tr("Warp Activation Failed"),
                                 self.tr("Activation error: {}").format(e))


if __name__ == "__main__":
    logger, log_path = setup_logger()

    check_existing_instance()
    app = QApplication(sys.argv)
    server.listen(SERVER_NAME)

    translator = QTranslator()
    app._translator = translator

    settings_handler = SettingsHandler()
    settings_handler.start()
    load_saved_language(app, settings_handler)

    try:
        app.setWindowIcon(QIcon(":/logo.png"))
    except:
        app.setWindowIcon(QIcon())

    sys.excepthook = handle_exception
    installer = WarpInstaller(parent=None)
    if not installer.is_warp_installed():
        installer.show_install_prompt()
        if not installer.is_warp_installed():
            QMessageBox.critical(
                None,
                app.translate("__main__", "Warp Installation Failed"),
                app.translate("__main__", "Warp could not be installed.\nExiting app.")
            )
            sys.exit()

    if platform.system() == "Windows" and not shutil.which("warp-cli"):
        try:
            installer._ensure_warp_svc_running_windows()
        except Exception as e:
            QMessageBox.critical(
                None,
                app.translate("__main__", "Warp Service Error"),
                app.translate("__main__", "Portable Warp service failed to start:\n{}").format(e)
            )
            sys.exit(1)

    window = MainWindow(settings_handler=settings_handler)
    window.show()

    update_checker = UpdateChecker(installer=installer)
    update_checker.update_available.connect(notify_update)
    update_checker.start_check(delay_ms=3000)

    window._update_checker = update_checker

    sys.exit(app.exec())
