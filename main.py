import ast
import ipaddress
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import webbrowser
import zipfile
import requests
import psutil
import socket
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
                               QGroupBox, QDialog, QProgressDialog, QInputDialog, QCheckBox,
                               QTextEdit, QFontComboBox, QGraphicsOpacityEffect, QTextBrowser, QDialogButtonBox,
                               QTreeWidget, QTreeWidgetItem)

CURRENT_VERSION = "1.2.8"
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

def on_about_to_quit():
    if getattr(window, '_is_restarting', False):
        QProcess.startDetached(sys.executable, sys.argv)

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
        if self.settings_handler and self.is_connected:
            mode = self.settings_handler.get("mode", "warp")
            if mode == "proxy":
                port = self.settings_handler.get("proxy_port", "40000")
                proxies = {
                    "http": f"socks5://127.0.0.1:{port}",
                    "https": f"socks5://127.0.0.1:{port}"
                }

        def do_request():
            url = "https://ipwho.is/"
            try:
                resp = requests.get(url, timeout=8, proxies=proxies)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success", True):
                        return data.get("ip", "Unavailable")
                return "Unavailable"
            except Exception as e:
                logger.debug(f"IpFetcher.do_request exception: {e}")
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
        self._worker.error_signal.connect(
            lambda e: (logger.error(f"IP fetch error: {e}"), self.ip_ready.emit("Unavailable"))
        )
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def get_country_info(self, ip: str) -> dict:
        result = {
            "country": "Unknown",
            "country_code": "",
            "flag": "",
            "region": "",
            "city": ""
        }

        if not ip or ip.lower() == "unavailable":
            return result

        try:
            resp = requests.get(f"https://ipwho.is/{ip}", timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success", True):
                    country = data.get("country") or "Unknown"
                    code = data.get("country_code") or ""
                    region = data.get("region") or ""
                    city = data.get("city") or ""
                    flag = ""
                    if code:
                        try:
                            flag = chr(ord(code[0].upper()) + 127397) + chr(ord(code[1].upper()) + 127397)
                        except Exception:
                            pass
                    result.update({
                        "country": country,
                        "country_code": code,
                        "flag": flag,
                        "region": region,
                        "city": city
                    })
        except Exception as e:
            logger.debug(f"IpFetcher.get_country_info error: {e}")

        return result


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


class AppExcludeManager(QObject):
    exclusions_updated = Signal(list)
    DEFAULT_FILTER_IPS = [
        "127.0.0.1", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
        "169.254.0.0/16", "224.0.0.0/4", "240.0.0.0/4"
    ]
    KNOWN_APP_DOMAINS = {
        "Discord": ["*.discord.com", "*.discord.gg", "*.discordapp.com", "*.discordapp.net",
                    "*.discord.media", "*.discordcdn.com", "*.discordstatus.com"],
        "Steam": ["*.steampowered.com", "*.steamcommunity.com", "*.steamgames.com",
                  "*.steamusercontent.com", "*.steamcontent.com", "*.steamstatic.com",
                  "*.steamserver.net", "*.steam-chat.com", "*.valve.net", "*.akamaihd.net"],
        "Spotify": ["*.spotify.com", "*.pscdn.co", "*.scdn.co"],
        "Zoom": ["*.zoom.us", "zoom.us"],
        "Slack": ["*.slack.com", "*.slack-msgs.com", "*.slack-files.com", "*.slack-edge.com"],
        "EpicGamesLauncher": ["*.epicgames.com", "epicgames.com"],
        "Battle.net": ["*.blizzard.com", "*.battle.net"],
        "CS2": ["*.valve.net"],
        "Dota 2": ["*.valve.net"],
    }
    KNOWN_APP_IP_RANGES = {
        "Discord": ["162.159.128.0/17", "162.159.192.0/18", "104.16.0.0/12", "66.22.192.0/18"],
        "Steam": ["208.64.200.0/21", "208.64.0.0/11", "162.254.192.0/21", "155.133.224.0/19",
                  "146.66.152.0/22", "103.28.54.0/24", "103.10.124.0/24", "192.69.96.0/24",
                  "209.197.25.0/24"],
        "Spotify": ["35.186.224.0/19"],
        "Zoom": ["170.114.0.0/15"],
        "Slack": ["52.32.0.0/11"],
        "CS2": [],
        "Dota 2": [],
    }

    def __init__(self, settings_handler, parent=None, scan_interval_ms: int = 3000):
        super().__init__(parent)
        self.settings_handler = settings_handler
        self._scan_interval = scan_interval_ms
        self._timer = QTimer(self)
        self._timer.setInterval(scan_interval_ms)
        self._timer.timeout.connect(self.scan_processes)
        self._applied_apps = self._load_applied_apps()
        self.desired_app_set = self._load_applied_apps().copy()
        self._dns_cache = {}
        self._session_checked = {}
        self.saved_endpoints = self._load_saved_endpoints()
        self._applied_state = self._load_applied_state()
        self.known_endpoints = {}
        self._scan_lock = threading.Lock()
        self._is_shutting_down = False

    def toggle_desired_app(self, app_name, enable):
        if enable:
            self.desired_app_set.add(app_name)
        else:
            self.desired_app_set.discard(app_name)

    def _expand_known_domains(self, app_name):
        matches = []
        for key, domains in self.KNOWN_APP_DOMAINS.items():
            if key.lower() in app_name.lower():
                matches.extend(domains)
        return list(set(matches))

    def _expand_known_ip_ranges(self, app_name):
        matches = []
        for key, ranges in getattr(self, "KNOWN_APP_IP_RANGES", {}).items():
            if key.lower() in app_name.lower():
                matches.extend(ranges)
        return list(set(matches))

    def _load_saved(self):
        data = self.settings_handler.get("excluded_apps", {})
        if isinstance(data, str):
            try:
                data = ast.literal_eval(data)
            except Exception:
                data = {}
        return data if isinstance(data, dict) else {}

    def _save(self):
        try:
            self.settings_handler.save_settings("excluded_apps", self._saved)
        except Exception as e:
            logger.warning(f"Failed to save exclusions: {e}")

    def _load_saved_endpoints(self):
        data = self.settings_handler.get("app_endpoints", {})
        if isinstance(data, str):
            try:
                data = ast.literal_eval(data)
            except Exception:
                data = {}
        out = {}
        if isinstance(data, dict):
            for app, val in data.items():
                if isinstance(val, dict):
                    hosts = set(val.get("hosts", []))
                    ips = set(val.get("ips", []))
                else:
                    hosts = set()
                    ips = set()
                out[app] = {"hosts": hosts, "ips": ips}
        return out

    def _save_endpoints(self):
        try:
            serial = {}
            for app, val in self.saved_endpoints.items():
                serial[app] = {"hosts": sorted(list(val.get("hosts", set()))),
                               "ips": sorted(list(val.get("ips", set())))}
            self.settings_handler.save_settings("app_endpoints", serial)
        except Exception as e:
            logger.warning(f"Failed to save app_endpoints: {e}")

    def _load_applied_apps(self):
        data = self.settings_handler.get("app_applied_exclusions", [])
        if isinstance(data, str):
            try:
                data = ast.literal_eval(data)
            except Exception:
                data = []
        if not isinstance(data, list):
            data = []
        return set(data)

    def _save_applied_apps(self, applied_apps):
        try:
            self.settings_handler.save_settings("app_applied_exclusions", sorted(list(applied_apps)))
        except Exception as e:
            logger.warning(f"Failed to save applied app exclusions: {e}")

    def _load_applied_state(self):
        data = self.settings_handler.get("app_applied_endpoints", {})
        if isinstance(data, str):
            try:
                data = ast.literal_eval(data)
            except Exception:
                data = {}

        out = {"hosts": set(), "ips": set()}
        if isinstance(data, dict):
            out["hosts"] = set(data.get("hosts", []))
            out["ips"] = set(data.get("ips", []))
        return out

    def _save_applied_state(self):
        try:
            current_hosts = set()
            current_ips = set()
            for app, val in self.saved_endpoints.items():
                current_hosts.update(val.get("hosts", set()))
                current_ips.update(val.get("ips", set()))

            serial = {
                "hosts": sorted(list(current_hosts)),
                "ips": sorted(list(current_ips))
            }
            self.settings_handler.save_settings("app_applied_endpoints", serial)
            self._applied_state = {"hosts": current_hosts, "ips": current_ips}
        except Exception as e:
            logger.warning(f"Failed to save app_applied_endpoints: {e}")

    _helper_proc = None

    def _ensure_priv_helper(self):
        if self._helper_proc and self._helper_proc.poll() is None:
            return self._helper_proc

        helper_path = os.path.join(tempfile.gettempdir(), "pywarp_helper.py")
        if not os.path.exists(helper_path):
            with open(helper_path, "w") as f:
                f.write("""#!/usr/bin/env python3
                import sys, json, subprocess
                def main():
                    for line in sys.stdin:
                        try:
                            data = json.loads(line.strip())
                            cmd = data.get("cmd")
                            if not cmd or not isinstance(cmd, list):
                                print(json.dumps({"error": "invalid"})); sys.stdout.flush(); continue
                            res = subprocess.run(cmd, capture_output=True, text=True)
                            print(json.dumps({
                                "returncode": res.returncode,
                                "stdout": res.stdout.strip(),
                                "stderr": res.stderr.strip()
                            })); sys.stdout.flush()
                        except Exception as e:
                            print(json.dumps({"error": str(e)})); sys.stdout.flush()
                if __name__ == "__main__":
                    main()
                """)
            os.chmod(helper_path, 0o755)

        system = platform.system()
        try:
            if system == "Linux":
                cmd = ["pkexec", sys.executable, helper_path]
            elif system == "Darwin":
                cmd = ["osascript", "-e",
                       f'do shell script "{sys.executable} {helper_path}" with administrator privileges']
            else:
                return None
            self._helper_proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
            )
            return self._helper_proc
        except Exception as e:
            logger.error(f"Failed to start helper: {e}")
            return None

    class HelperResult:
        def __init__(self, returncode=1, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def _run_with_helper(self, cmd):
        proc = self._ensure_priv_helper()
        if not proc:
            try:
                res = subprocess.run(["sudo"] + cmd, capture_output=True, text=True)
                return self.HelperResult(res.returncode, res.stdout or "", res.stderr or "")
            except Exception as e:
                logger.error(f"Sudo fallback failed: {e}")
                return self.HelperResult(1, "", str(e))

        try:
            payload = json.dumps({"cmd": cmd}) + "\n"
            proc.stdin.write(payload)
            proc.stdin.flush()
            line = proc.stdout.readline().strip()
            if not line:
                raise RuntimeError("Empty response from helper")
            data = json.loads(line)
            return self.HelperResult(
                data.get("returncode", 1),
                data.get("stdout", "") or "",
                data.get("stderr", "") or ""
            )
        except Exception as e:
            logger.error(f"Helper communication failed: {e}")
            try:
                res = subprocess.run(["sudo"] + cmd, capture_output=True, text=True)
                return self.HelperResult(res.returncode, res.stdout or "", res.stderr or "")
            except Exception as e2:
                return self.HelperResult(1, "", f"{e} | fallback error: {e2}")

    def shutdown_helper(self):
        try:
            if self._helper_proc and self._helper_proc.poll() is None:
                self._helper_proc.terminate()
        except Exception:
            pass


    def _resolve_ip(self, host):
        try:
            ipaddress.ip_address(host)
            return host
        except Exception:
            try:
                if host in self._dns_cache:
                    return self._dns_cache[host]

                ip = socket.gethostbyname(host)
                self._dns_cache[host] = ip
                return ip
            except Exception:
                return None

    def mark_endpoint_saved(self, app_name, kind, value):
        app = self.saved_endpoints.setdefault(app_name, {"hosts": set(), "ips": set()})
        if kind == "host":
            app["hosts"].add(value)
            self.known_endpoints.setdefault(app_name, {"hosts": set(), "ips": set()})["hosts"].add(value)
        else:
            app["ips"].add(value)
            self.known_endpoints.setdefault(app_name, {"hosts": set(), "ips": set()})["ips"].add(value)
        self._save_endpoints()

    def unmark_endpoint_saved(self, app_name, kind, value):
        app = self.saved_endpoints.get(app_name)
        if app:
            if kind == "host":
                app["hosts"].discard(value)
            else:
                app["ips"].discard(value)
        self._save_endpoints()

    def _is_ip_valid_for_exclusion(self, ip_address):
        try:
            ip = ipaddress.ip_address(ip_address)
            return not (ip.is_private or ip.is_loopback or ip.is_multicast or ip.is_reserved or ip.is_link_local)
        except ValueError:
            return False

    def scan_processes(self):
        if self._is_shutting_down or not self._scan_lock.acquire(blocking=False):
            return

        def worker():
            try:
                current_process_data = {}
                for proc in psutil.process_iter(['pid', 'name', 'exe']):
                    try:
                        connections = proc.net_connections(kind='inet')

                        external_connections = []
                        for conn in connections:
                            if conn.raddr and conn.status != psutil.CONN_LISTEN:
                                remote_ip = conn.raddr.ip

                                if self._is_ip_valid_for_exclusion(remote_ip):
                                    value = remote_ip
                                    kind = "ip"

                                    if platform.system() == "Windows":
                                        remote_host = getattr(conn.raddr, 'host', remote_ip)
                                        if remote_host and remote_host != remote_ip:
                                            value = remote_host
                                            kind = "host"

                                    if value:
                                        external_connections.append((kind, value))

                        if external_connections:
                            name_key = proc.name() or (
                                proc.exe().split(os.sep)[-1] if proc.exe() else f"PID {proc.pid}")
                            current_process_data[name_key] = {
                                "pid": proc.pid,
                                "name": proc.name(),
                                "exe": proc.exe(),
                                "connections": list(set(external_connections))
                            }

                    except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
                        continue

                apps_for_ui = []

                for key, data in current_process_data.items():
                    app_entry = {
                        "key": key,
                        "pid": data["pid"],
                        "exe": data["exe"],
                        "saved": self.saved_endpoints.get(key, {"hosts": set(), "ips": set()}),
                        "known": self.known_endpoints.setdefault(key, {"hosts": set(), "ips": set()}),
                        "new": {"hosts": set(), "ips": set()}
                    }

                    for kind, value in data["connections"]:
                        value_set = "hosts" if kind == "host" else "ips"

                        is_saved = value in app_entry["saved"][value_set]
                        is_known = value in app_entry["known"][value_set]

                        if not is_saved and not is_known:
                            app_entry["new"][value_set].add(value)

                        app_entry["known"][value_set].add(value)

                    apps_for_ui.append(app_entry)

                if self.signalsBlocked():
                    return
                try:
                    self.exclusions_updated.emit(apps_for_ui)
                except RuntimeError:
                    pass

            finally:
                self._scan_lock.release()

        run_in_worker(
            worker,
            parent=self,
            on_error=lambda e: logger.error(f"Error during process scan: {e}")
        )

    def _get_current_warp_rules(self):
        current_hosts = set()
        current_ips = set()
        current_ranges = set()

        result_ip = run_warp_command("warp-cli", "-j", "tunnel", "ip", "list")
        if result_ip and result_ip.returncode == 0:
            try:
                data = json.loads(result_ip.stdout)
                for r in data.get("routes", []):
                    value = r.get("value", "")
                    if value:
                        if "/" in value:
                            if value.endswith("/32"):
                                current_ips.add(value.split("/")[0])
                            else:
                                current_ranges.add(value)
                        else:
                            current_ips.add(value)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode warp-cli tunnel ip list output: {e}")
            except Exception as e:
                logger.error(f"Error processing WARP IP list: {e}")

        result_host = run_warp_command("warp-cli", "-j", "tunnel", "host", "list")
        if result_host and result_host.returncode == 0:
            try:
                data = json.loads(result_host.stdout)
                host_list = data.get("routes", data.get("hosts", []))
                current_hosts.update([r.get("value", "") for r in host_list if isinstance(r, dict) and r.get("value")])
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode warp-cli tunnel host list output: {e}")
            except Exception as e:
                logger.error(f"Error processing WARP Host list: {e}")

        return current_hosts, current_ips, current_ranges

    def batch_apply_warp_rules(self):

        def worker_function():
            if getattr(self, "_is_shutting_down", False):
                logger.info("Batch apply aborted: shutting down")
                return False

            desired_hosts, desired_ips = set(), set()
            for app, data in self.saved_endpoints.items():
                desired_hosts.update(data.get("hosts", set()))
                desired_ips.update(data.get("ips", set()))

            previous_hosts = self._applied_state["hosts"]
            previous_ips = self._applied_state["ips"]

            to_add_ips = desired_ips - previous_ips
            to_remove_ips = previous_ips - desired_ips
            to_add_hosts = desired_hosts - previous_hosts
            to_remove_hosts = previous_hosts - desired_hosts

            current_warp_hosts, current_warp_ips, _ = self._get_current_warp_rules()
            to_add_ips.difference_update(current_warp_ips)
            to_add_hosts.difference_update(current_warp_hosts)
            to_remove_ips.intersection_update(current_warp_ips)
            to_remove_hosts.intersection_update(current_warp_hosts)

            changed = False

            for ip in to_add_ips:
                if getattr(self, "_is_shutting_down", False): return False
                res = run_warp_command("warp-cli", "tunnel", "ip", "add", ip)
                if res and res.returncode == 0:
                    changed = True
                else:
                    logger.error(f"Failed to add IP {ip}: {getattr(res, 'stderr', 'no result')}")

            for host in to_add_hosts:
                if getattr(self, "_is_shutting_down", False): return False
                res = run_warp_command("warp-cli", "tunnel", "host", "add", host)
                if res and res.returncode == 0:
                    changed = True
                else:
                    logger.error(f"Failed to add host {host}: {getattr(res, 'stderr', 'no result')}")

            for ip in to_remove_ips:
                if getattr(self, "_is_shutting_down", False): return False
                run_warp_command("warp-cli", "tunnel", "ip", "remove", ip)
                changed = True
            for host in to_remove_hosts:
                if getattr(self, "_is_shutting_down", False): return False
                run_warp_command("warp-cli", "tunnel", "host", "remove", host)
                changed = True

            if changed:
                self._save_applied_state()

            system = platform.system()

            desired_apps = self.desired_app_set
            previous_apps = self._applied_apps

            to_add_apps = desired_apps - previous_apps
            to_remove_apps = previous_apps - desired_apps

            for app_name in to_add_apps:
                if getattr(self, "_is_shutting_down", False): return False
                try:
                    for dom in self._expand_known_domains(app_name):
                        run_warp_command("warp-cli", "tunnel", "host", "add", dom)
                        logger.debug(f"Added known domain {dom} for {app_name}")

                    for cidr in self._expand_known_ip_ranges(app_name):
                        run_warp_command("warp-cli", "tunnel", "ip", "add", cidr)
                        logger.debug(f"Added known IP range {cidr} for {app_name}")

                    if system == "Windows":
                        self._apply_warp_exclusion(app_name)
                    elif system == "Linux":
                        self._set_linux_app_exclusion(app_name, enable=True)
                    elif system == "Darwin":
                        self._set_macos_app_exclusion(app_name, enable=True)

                    logger.info(f"Applied exclusion for {app_name}")

                except Exception as e:
                    logger.error(f"App exclusion failed for {app_name}: {e}")

            for app_name in to_remove_apps:
                if getattr(self, "_is_shutting_down", False): return False
                try:
                    for dom in self._expand_known_domains(app_name):
                        run_warp_command("warp-cli", "tunnel", "host", "remove", dom)
                        logger.debug(f"Removed known domain {dom} for {app_name}")

                    for cidr in self._expand_known_ip_ranges(app_name):
                        run_warp_command("warp-cli", "tunnel", "ip", "remove", cidr)
                        logger.debug(f"Removed known IP range {cidr} for {app_name}")

                    if system == "Windows":
                        self._remove_warp_exclusion(app_name)
                    elif system == "Linux":
                        self._set_linux_app_exclusion(app_name, enable=False)
                    elif system == "Darwin":
                        self._set_macos_app_exclusion(app_name, enable=False)
                    logger.info(f"Removed exclusion for {app_name}")
                except Exception as e:
                    logger.error(f"Failed to remove exclusion for {app_name}: {e}")

            self._save_applied_apps(desired_apps)
            self._applied_apps = desired_apps.copy()

            logger.info("✅ All pending exclusions applied successfully.")
            return True

        def on_done(_):
            self.scan_processes()

        run_in_worker(
            worker_function,
            parent=self,
            on_done=on_done,
            on_error=lambda e: logger.error(f"Batch WARP rule application failed: {e}")
        )

    def toggle_app_exclusion(self, app_name: str, enable: bool):
        try:
            if enable:
                self.desired_app_set.add(app_name)
            else:
                self.desired_app_set.discard(app_name)

            self._save_applied_apps(self.desired_app_set)

        except Exception as e:
            logger.error(f"toggle_app_exclusion({app_name}) failed: {e}")

    def _apply_warp_exclusion(self, app_name):
        app_data = self.saved_endpoints.get(app_name, {"hosts": set(), "ips": set()})
        for ip in app_data["ips"]:
            run_warp_command("warp-cli", "tunnel", "ip", "add", ip)
        for host in app_data["hosts"]:
            run_warp_command("warp-cli", "tunnel", "host", "add", host)
        logger.info(f"Applied WARP exclusion for {app_name}")

    def _remove_warp_exclusion(self, app_name):
        app_data = self.saved_endpoints.get(app_name, {"hosts": set(), "ips": set()})
        for ip in app_data["ips"]:
            run_warp_command("warp-cli", "tunnel", "ip", "remove", ip)
        for host in app_data["hosts"]:
            run_warp_command("warp-cli", "tunnel", "host", "remove", host)
        logger.info(f"Removed WARP exclusion for {app_name}")

    def _set_linux_app_exclusion(self, app_name, enable=True):
        try:
            for proc in psutil.process_iter(['name', 'uids']):
                if proc.info['name'] == app_name:
                    uid = proc.info['uids'].real
                    if enable:
                        self._run_with_helper(["ip", "rule", "add", "uidrange", f"{uid}-{uid}", "lookup", "main"])
                        self._run_with_helper([
                            "iptables", "-t", "mangle", "-A", "OUTPUT", "-m", "owner",
                            "--uid-owner", str(uid), "-j", "MARK", "--set-mark", "1"
                        ])
                        self._run_with_helper(["ip", "rule", "add", "fwmark", "1", "lookup", "main"])
                        logger.info(f"Excluded {app_name} (UID {uid}) from WARP routing")
                    else:
                        self._run_with_helper(["ip", "rule", "del", "uidrange", f"{uid}-{uid}", "lookup", "main"])
                        self._run_with_helper([
                            "iptables", "-t", "mangle", "-D", "OUTPUT", "-m", "owner",
                            "--uid-owner", str(uid), "-j", "MARK", "--set-mark", "1"
                        ])
                        logger.info(f"Removed Linux exclusion for {app_name}")
                    return
            logger.warning(f"App not found for exclusion: {app_name}")
        except Exception as e:
            logger.error(f"Linux exclusion failed for {app_name}: {e}")

    def _set_macos_app_exclusion(self, app_name, enable=True):
        pf_conf = "/tmp/pywarp_pf.conf"
        try:
            for proc in psutil.process_iter(['name', 'uids']):
                if proc.info['name'] == app_name:
                    uid = proc.info['uids'].real
                    pf_rule = f"block out quick on utun1 user {uid}\n"
                    if enable:
                        with open(pf_conf, "a") as f:
                            f.write(pf_rule)
                        self._run_with_helper(["pfctl", "-f", pf_conf])
                        self._run_with_helper(["pfctl", "-e"])
                        logger.info(f"Added pfctl exclusion for {app_name} (UID {uid})")
                    else:
                        if os.path.exists(pf_conf):
                            with open(pf_conf, "r") as f_read:
                                lines = [
                                    l for l in f_read
                                    if not l.strip().startswith("block out quick on utun1 user ")
                                ]
                            with open(pf_conf, "w") as f_write:
                                f_write.writelines(lines)
                        self._run_with_helper(["pfctl", "-f", pf_conf])
                        logger.info(f"Removed pfctl exclusion for {app_name}")
                    return
            logger.warning(f"macOS app not found: {app_name}")
        except Exception as e:
            logger.error(f"macOS exclusion failed for {app_name}: {e}")

    def validate_excluded_apps(self):
        try:
            current_hosts, current_ips, _ = self._get_current_warp_rules()
            logger.debug(f"Validating exclusions: {len(current_hosts)} hosts, {len(current_ips)} ips")

            removed_apps = set()
            removed_connections = []

            for app_name, endpoints in list(self.saved_endpoints.items()):
                hosts_to_remove = set()
                ips_to_remove = set()

                for h in endpoints.get("hosts", set()):
                    if h not in current_hosts:
                        hosts_to_remove.add(h)

                for ip in endpoints.get("ips", set()):
                    if ip not in current_ips:
                        ips_to_remove.add(ip)

                if hosts_to_remove or ips_to_remove:
                    endpoints["hosts"].difference_update(hosts_to_remove)
                    endpoints["ips"].difference_update(ips_to_remove)
                    removed_connections.extend(list(hosts_to_remove | ips_to_remove))
                    logger.debug(f"Removed invalid endpoints for {app_name}: {hosts_to_remove | ips_to_remove}")

                if app_name in self.desired_app_set:
                    if not endpoints["hosts"] and not endpoints["ips"]:
                        self.desired_app_set.discard(app_name)
                        removed_apps.add(app_name)
                        logger.debug(f"Unchecking app {app_name}: no valid endpoints left")

            self._save_endpoints()
            self._save_applied_apps(self.desired_app_set)

            if removed_apps or removed_connections:
                logger.info(
                    f"validate_excluded_apps: Removed {len(removed_apps)} apps and {len(removed_connections)} connections"
                )

            return {"apps": removed_apps, "connections": removed_connections}

        except Exception as e:
            logger.error(f"validate_excluded_apps failed: {e}")
            return {"apps": set(), "connections": []}


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
    status_signal = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._on_ready_read)
        self._process.errorOccurred.connect(self._on_process_error)
        self._process.finished.connect(self._on_process_finished)

        self._restart_timer = QTimer(self)
        self._restart_timer.setSingleShot(True)
        self._restart_timer.setInterval(5000)
        self._restart_timer.timeout.connect(self.start_listener)

        self._last_status = None
        self._last_reason = None

        QTimer.singleShot(0, self.start_listener)

    def start_listener(self):
        if self._process.state() == QProcess.Running:
            return

        warp_cli_path = get_warp_cli_executable()
        if not warp_cli_path:
            logger.error("warp-cli not found, cannot start status listener.")
            self.status_signal.emit("Failed", "warp-cli executable not found.")
            self._restart_timer.start()
            return

        self._process.setProgram(warp_cli_path)
        self._process.setArguments(["-l", "-j", "status"])
        self._process.start()
        logger.info("warp-cli JSON listener started")

    def stop_listener(self):
        self._restart_timer.stop()
        if self._process.state() == QProcess.Running:
            try:
                self._process.kill()
            except Exception as e:
                logger.debug(f"Error stopping listener: {e}")

    def _on_ready_read(self):
        try:
            data = self._process.readAllStandardOutput().data().decode(errors="ignore").strip()
        except Exception as e:
            logger.error(f"Error decoding warp-cli output: {e}")
            return

        for line in data.splitlines():
            line = line.strip()
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                logger.debug(f"WARP: Non-JSON line: {line}")
                continue

            if "status" in event:
                status = event.get("status", "")
                reason = event.get("reason", "")

                if isinstance(reason, dict):
                    key, value = next(iter(reason.items()))
                    if isinstance(value, list):
                        value = value[0] if value else ""
                    reason = self._translate_reason(key, value)
                elif isinstance(reason, str):
                    reason = self._translate_reason(reason)
                else:
                    reason = str(reason or "")

                self._emit_status(status, reason)

            elif "update" in event:
                update_type = event.get("update", "")
                self._emit_status("Update", update_type)

            else:
                logger.debug(f"WARP: Unknown event: {event}")

    def _translate_reason(self, key: str, value: str = "") -> str:

        mapping = {
            "PerformingHappyEyeballs": QCoreApplication.translate("WarpStatusHandler", "Trying to connect to Cloudflare"),
            "EstablishingConnection": QCoreApplication.translate("WarpStatusHandler", f"Connecting to {value}") if value else QCoreApplication.translate("WarpStatusHandler", "Connecting to Cloudflare"),
            "InitializingTunnelInterface": QCoreApplication.translate("WarpStatusHandler", "Setting up secure tunnel"),
            "ConfiguringInitialFirewall": QCoreApplication.translate("WarpStatusHandler", "Configuring firewall"),
            "SettingRoutes": QCoreApplication.translate("WarpStatusHandler", "Setting routes"),
            "ConfiguringFirewallRules": QCoreApplication.translate("WarpStatusHandler", "Applying firewall rules"),
            "PerformingConnectivityChecks": QCoreApplication.translate("WarpStatusHandler", "Checking connectivity"),
            "ValidatingDnsConfiguration": QCoreApplication.translate("WarpStatusHandler", "Validating DNS settings"),
            "CheckingNetwork": QCoreApplication.translate("WarpStatusHandler", "Checking network"),
            "InitializingSettings": QCoreApplication.translate("WarpStatusHandler", "Initializing settings"),
            "SettingsChanged": QCoreApplication.translate("WarpStatusHandler", "Settings changed"),
            "Manual": QCoreApplication.translate("WarpStatusHandler", "Disconnected manually"),
        }

        return mapping.get(key, key)

    def _emit_status(self, status: str, reason: str):
        if (status, reason) != (self._last_status, self._last_reason):
            self._last_status, self._last_reason = status, reason
            if status == 'Update':
                return
            if status == "Failed":
                logger.warning(f"WARP: {status} ({reason})")
            else:
                logger.debug(f"WARP: {status} ({reason})")
            self.status_signal.emit(status, reason)

    def _on_process_error(self, error):
        logger.warning(f"WARP listener process error: {error}")
        self.status_signal.emit("Failed", f"Listener error: {error}")
        self._restart_timer.start()

    def _on_process_finished(self, code, status):
        logger.warning(f"WARP listener exited unexpectedly (code {code}, status {status})")
        self.status_signal.emit("Failed", "warp-cli listener stopped unexpectedly.")
        self._restart_timer.start()


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

    @staticmethod
    def format_bytes(num_bytes):
        try:
            num_bytes = float(num_bytes)
        except (ValueError, TypeError):
            return "0 B"

        units = ["B", "KB", "MB", "GB", "TB"]
        size = num_bytes
        unit_index = 0

        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1

        return f"{size:.2f} {units[unit_index]}"

    def update_status(self, status: str, reason: str = ""):
        self.warp_connected = (status == "Connected")

    def check_stats(self):
        if not self.warp_connected:
            self.stats_signal.emit([])
            return
        if not self._stats_proc.is_running():
            warp_cli_path = get_warp_cli_executable()
            if warp_cli_path:
                self._stats_proc.run(warp_cli_path, ["-j", "tunnel", "stats"], timeout_ms=5000)
            else:
                self._on_stats_error("warp-cli not found")

    def _on_stats_finished(self, code: int, out: str, err: str):
        if code != 0:
            logger.error(f"WARP stats exited with code {code}: {err}")
            self.stats_signal.emit([])
            return

        try:
            data = json.loads(out)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse WARP stats JSON: {e}")
            self.stats_signal.emit([])
            return

        try:
            protocol = data.get("protocol", "Unknown")
            v4_endpoint = data.get("v4_endpoint", "N/A")
            v6_endpoint = data.get("v6_endpoint", "N/A")

            endpoints = f"{v4_endpoint},{v6_endpoint}"

            handshake_secs = data.get("secs_since_last_handshake")
            handshake_display = (
                f"{handshake_secs}s" if handshake_secs is not None else "—"
            )

            sent = data.get("bytes_sent", 0)
            received = data.get("bytes_received", 0)
            latency = data.get("estimated_latency_ms", None)
            loss = data.get("estimated_loss", None)

            sent_str = self.format_bytes(sent)
            recv_str = self.format_bytes(received)
            latency_str = f"{latency} ms" if latency is not None else "—"
            loss_value = (loss * 100) if loss is not None else 0.00

            self.stats_signal.emit([
                protocol,
                endpoints,
                handshake_display,
                sent_str,
                recv_str,
                latency_str,
                loss_value
            ])

        except Exception as e:
            logger.error(f"Error processing WARP stats JSON: {e}")
            self.stats_signal.emit([])

    def _on_stats_error(self, err_msg: str):
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

            QTimer.singleShot(3000, lambda: self.connecting_timer.stop())

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

        self.power_button.setDisabled(new_state == "No Network")

        self.apply_style(config["style"], config["text"])

    def toggle_power(self):
        self.power_button.setDisabled(True)

        def work():
            cmd = "connect" if self.state == "Disconnected" else "disconnect"
            return run_warp_command("warp-cli", cmd)

        def done(result):
            QTimer.singleShot(3000, lambda: self.power_button.setDisabled(False))
            if not result or result.returncode != 0:
                error = result.stderr.strip() if result else self.tr("Unknown error")
                self.command_error_signal.emit(self.tr("Command Error"), error)

        def fail(exc):
            self.command_error_signal.emit(self.tr("Command Error"), str(exc))
            QTimer.singleShot(3000, lambda: self.power_button.setDisabled(False))

        run_in_worker(work, parent=self, on_done=done, on_error=fail)

    def reset_button_state(self):
        if self._toggle_lock:
            self._toggle_lock = False
            self.power_button.setDisabled(False)

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


class ExclusionManager(QDialog):
    exclusions_updated = Signal()

    DEFAULT_IPS = {
        "10.0.0.0/8", "100.64.0.0/10", "169.254.0.0/16",
        "172.16.0.0/12", "192.0.0.0/24", "192.168.0.0/16",
        "224.0.0.0/24", "240.0.0.0/4", "239.255.255.250/32",
        "255.255.255.255/32", "fe80::/10", "fd00::/8",
        "ff01::/16", "ff02::/16", "ff03::/16", "ff04::/16",
        "ff05::/16", "fc00::/7", "17.249.0.0/16", "17.252.0.0/16",
        "17.57.144.0/22", "17.188.128.0/18", "17.188.20.0/23",
        "2620:149:a44::/48", "2403:300:a42::/48",
        "2403:300:a51::/48", "2a01:b740:a42::/48"
    }

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

    @staticmethod
    def is_valid_ip(value):
        try:
            ipaddress.ip_address(value)
            return True
        except ValueError:
            return False

    @staticmethod
    def is_valid_domain(value):
        return bool(re.match(r"^((?!-)[A-Za-z0-9-]{1,63}(?<!-)\.)+[A-Za-z]{2,63}$", value))

    def add_item(self):
        value = self.input_field.text().strip()
        if not value:
            return

        exclusion_type = self.selector.currentText().lower()
        is_ip_mode = exclusion_type == self.tr("ip").lower()

        if is_ip_mode and not self.is_valid_ip(value):
            QMessageBox.warning(self, self.tr("Invalid Input"), self.tr("Please enter a valid IP address."))
            return
        if not is_ip_mode and not self.is_valid_domain(value):
            QMessageBox.warning(self, self.tr("Invalid Input"), self.tr("Please enter a valid domain name."))
            return
        if is_ip_mode and value in self.DEFAULT_IPS:
            QMessageBox.warning(self, self.tr("Error"), self.tr("Cannot add a default IP to exclusions."))
            return

        try:
            cmd = "ip" if is_ip_mode else "host"
            result = run_warp_command("warp-cli", "tunnel", cmd, "add", value)
            if result.returncode == 0:
                self.exclusions_updated.emit()
                self.accept()
            else:
                QMessageBox.warning(self, self.tr("Error"),
                                    self.tr("Failed to add {}: {}").format(exclusion_type, result.stderr.strip()))
        except subprocess.TimeoutExpired:
            QMessageBox.warning(self, self.tr("Error"), self.tr("Command timed out"))
        except Exception as e:
            QMessageBox.warning(self, self.tr("Error"), f"Command failed: {e}")

    @classmethod
    def filter_default_ips(cls, ip_list):
        return [ip for ip in ip_list if ip not in cls.DEFAULT_IPS]


class AdvancedSettings(QDialog):
    def __init__(self, settings_handler, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Advanced Settings"))
        self.resize(900, 560)

        self.settings_handler = settings_handler
        self.current_endpoint = self.settings_handler.get("custom_endpoint", "")

        self.app_exclude_manager = AppExcludeManager(self.settings_handler, self, scan_interval_ms=10000)
        self.app_exclude_manager.exclusions_updated.connect(self.populate_app_list)

        # Exclude IP / Domain Table
        exclusion_group = QGroupBox(self.tr("Exclude IP / Domain"))
        exclusion_layout = QVBoxLayout()
        self.exclude_table = QTableWidget()
        self.exclude_table.setColumnCount(2)
        self.exclude_table.setHorizontalHeaderLabels([self.tr("Type"), self.tr("Value")])
        self.exclude_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.exclude_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.exclude_table.horizontalHeader().setStretchLastSection(True)
        self.exclude_table.verticalHeader().setVisible(False)
        self.exclude_table.setAlternatingRowColors(True)
        exclusion_layout.addWidget(self.exclude_table)

        btn_grid = QGridLayout()
        self.btn_add = QPushButton(self.tr("Add"))
        self.btn_remove = QPushButton(self.tr("Remove"))
        self.btn_reset = QPushButton(self.tr("Reset List"))
        for b in (self.btn_add, self.btn_remove, self.btn_reset):
            b.setMinimumHeight(32)
        btn_grid.addWidget(self.btn_add, 0, 0)
        btn_grid.addWidget(self.btn_remove, 0, 1)
        btn_grid.addWidget(self.btn_reset, 0, 2)
        exclusion_layout.addLayout(btn_grid)
        exclusion_group.setLayout(exclusion_layout)

        self.btn_add.clicked.connect(self.open_exclusion_manager)
        self.btn_remove.clicked.connect(self.remove_item)
        self.btn_reset.clicked.connect(self.reset_list)

        # App Exclusion List
        app_group = QGroupBox(self.tr("Active Applications (Exclude from WARP)"))
        app_layout = QVBoxLayout()

        self.app_tree = QTreeWidget()
        self.app_tree.setColumnCount(2)
        self.app_tree.setHeaderLabels([self.tr("Application / Endpoint"), self.tr("PID")])
        self.app_tree.setRootIsDecorated(True)
        self.app_tree.setAnimated(True)
        self.app_tree.setIndentation(25)
        self.app_tree.setAlternatingRowColors(True)
        self.app_tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.app_tree.itemChanged.connect(self._on_app_item_changed)
        self.app_tree.itemExpanded.connect(lambda _item=None: self._save_expanded_apps())
        self.app_tree.itemCollapsed.connect(lambda _item=None: self._save_expanded_apps())

        self.app_tree.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.app_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.app_tree.header().setSectionResizeMode(1, QHeaderView.Interactive)
        self.app_tree.header().resizeSection(1, 90)

        self.select_all_checkbox = QCheckBox(self.tr("Select All"))
        self.select_all_checkbox.setChecked(False)
        self.select_all_checkbox.stateChanged.connect(self._on_select_all_toggled)

        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(15, 0, 0, 0)
        header_layout.setSpacing(5)
        header_layout.addWidget(self.select_all_checkbox)
        header_layout.addStretch(1)

        self.app_tree.header().setIndexWidget(self.app_tree.header().model().index(0, 0), header_widget)
        app_layout.addWidget(self.app_tree)

        btn_row = QHBoxLayout()
        self.btn_refresh_apps = QPushButton(self.tr("Refresh Now"))
        self.btn_refresh_apps.clicked.connect(self.manual_refresh_apps)

        self.btn_apply_pending = QPushButton(self.tr("Apply Pending Changes to WARP"))
        self.btn_apply_pending.setStyleSheet("")
        self.btn_apply_pending.clicked.connect(self.apply_pending_changes)

        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_refresh_apps)
        btn_row.addWidget(self.btn_apply_pending)
        app_layout.addLayout(btn_row)

        app_group.setLayout(app_layout)

        # Custom Endpoint & MASQUE
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
        self.endpoint_reset_button = QPushButton(self.tr("Reset"))
        self.endpoint_save_button.clicked.connect(self.save_endpoint)
        self.endpoint_reset_button.clicked.connect(self.reset_endpoint)
        endpoint_layout.addWidget(self.endpoint_input)
        endpoint_layout.addWidget(self.endpoint_save_button)
        endpoint_layout.addWidget(self.endpoint_reset_button)
        endpoint_group.setLayout(endpoint_layout)

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
        self.masque_reset_button = QPushButton(self.tr("Reset"))
        self.masque_set_button.clicked.connect(self.save_masque_option)
        self.masque_reset_button.clicked.connect(self.reset_masque_option)
        masque_layout.addWidget(self.masque_input)
        masque_layout.addWidget(self.masque_set_button)
        masque_layout.addWidget(self.masque_reset_button)
        masque_group.setLayout(masque_layout)

        # Layout
        grid = QGridLayout()
        grid.addWidget(exclusion_group, 0, 0)
        grid.addWidget(app_group, 0, 1)
        grid.addWidget(endpoint_group, 1, 0)
        grid.addWidget(masque_group, 1, 1)
        self.setLayout(grid)

        # initial data
        self.update_exclude_table()
        QTimer.singleShot(1500, self.app_exclude_manager._timer.start)
        QTimer.singleShot(250, self.app_exclude_manager.scan_processes)

    def closeEvent(self, event):
        try:
            try:
                self._save_expanded_apps()
            except Exception:
                pass

            if hasattr(self.app_exclude_manager, "_timer"):
                self.app_exclude_manager._is_shutting_down = True
                try:
                    self.app_exclude_manager._timer.stop()
                    self.app_exclude_manager._timer.timeout.disconnect()
                except Exception:
                    pass

            try:
                self.app_exclude_manager.blockSignals(True)
                self.app_exclude_manager.exclusions_updated.disconnect(self.populate_app_list)
            except Exception:
                pass

            try:
                self.app_exclude_manager.shutdown_helper()
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Error during AdvancedSettings close cleanup: {e}")
        super().closeEvent(event)

    def populate_app_list(self, apps):
        try:
            self.app_tree.blockSignals(True)
        except Exception:
            pass
        expanded_apps = self._load_expanded_apps()

        for i in range(self.app_tree.topLevelItemCount()):
            item = self.app_tree.topLevelItem(i)
            if item.isExpanded():
                expanded_apps.add(item.text(0))
        self.app_tree.clear()

        excluded_apps = self.app_exclude_manager.desired_app_set

        for app in sorted(apps, key=lambda a: a.get("key", "").lower()):
            name = app.get("key")
            pid = app.get("pid", -1)
            exe = app.get("exe", "") or ""
            top = QTreeWidgetItem([name, str(pid)])
            top.setFlags(top.flags() | Qt.ItemIsUserCheckable)

            top.setCheckState(0, Qt.Checked if name in excluded_apps else Qt.Unchecked)
            top.setData(0, Qt.UserRole, ("app", name))

            def add_child(label, kind, value, checked=False, color=None):
                child = QTreeWidgetItem([label, ""])
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                child.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
                child.setData(0, Qt.UserRole, ("endpoint", name, kind, value))
                if color:
                    brush = QBrush(QColor(*color))
                    for i in range(2):
                        child.setBackground(i, brush)
                top.addChild(child)

            for h in app.get("saved", {}).get("hosts", []):
                add_child(h, "host", h, checked=True, color=(200, 255, 200, 60))
            for ip in app.get("saved", {}).get("ips", []):
                add_child(ip, "ip", ip, checked=True, color=(200, 255, 200, 60))

            for h in app.get("known", {}).get("hosts", []):
                if h in app.get("saved", {}).get("hosts", []):
                    continue
                add_child(h, "host", h, checked=False)
            for ip in app.get("known", {}).get("ips", []):
                if ip in app.get("saved", {}).get("ips", []):
                    continue
                add_child(ip, "ip", ip, checked=False)

            for h in app.get("new", {}).get("hosts", []):
                if h in app.get("known", {}).get("hosts", []):
                    continue
                add_child(h, "host", h, checked=False, color=(255, 165, 69, 80))
            for ip in app.get("new", {}).get("ips", []):
                if ip in app.get("known", {}).get("ips", []):
                    continue
                add_child(ip, "ip", ip, checked=False, color=(255, 165, 69, 80))

            self.app_tree.addTopLevelItem(top)

            if name in expanded_apps:
                top.setExpanded(True)
            else:
                top.setExpanded(False)

            if name in excluded_apps:
                for i in range(top.childCount()):
                    brush = QBrush(QColor(200, 255, 200, 60))
                    for col in range(2):
                        top.child(i).setBackground(col, brush)

        try:
            self.app_tree.blockSignals(False)
        except Exception:
            pass

    def _save_expanded_apps(self):
        try:
            expanded = []
            for i in range(self.app_tree.topLevelItemCount()):
                item = self.app_tree.topLevelItem(i)
                if item.isExpanded():
                    expanded.append(item.text(0))
            self.settings_handler.save_settings("expanded_apps", expanded)
            logger.debug(f"Saved expanded_apps: {expanded}")
        except Exception as e:
            logger.exception(f"_save_expanded_apps failed: {e}")

    def _load_expanded_apps(self):
        expanded = self.settings_handler.get("expanded_apps", [])
        if isinstance(expanded, str):
            try:
                expanded = ast.literal_eval(expanded)
            except Exception:
                try:
                    expanded = json.loads(expanded)
                except Exception:
                    expanded = []
        if not isinstance(expanded, list):
            expanded = []
        return set(expanded)

    def _on_select_all_toggled(self, state):
        if self.app_tree.signalsBlocked():
            return

        checked = state == Qt.Checked

        try:
            self.app_tree.blockSignals(True)

            for i in range(self.app_tree.topLevelItemCount()):
                top_item = self.app_tree.topLevelItem(i)

                for j in range(top_item.childCount()):
                    child_item = top_item.child(j)

                    role = child_item.data(0, Qt.UserRole)
                    if role and role[0] == "endpoint":
                        child_item.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)

                        _, app_name, kind, value = role
                        if checked:
                            self.app_exclude_manager.mark_endpoint_saved(app_name, kind, value)
                        else:
                            self.app_exclude_manager.unmark_endpoint_saved(app_name, kind, value)

                        if checked:
                            brush = QBrush(QColor(200, 255, 200, 60))
                        else:
                            brush = QBrush()

                        for col in range(2):
                            child_item.setBackground(col, brush)

            self.app_tree.blockSignals(False)
            self.btn_apply_pending.setStyleSheet("background-color: #ffd700; color: black; font-weight: bold;")

        except Exception as e:
            logger.error(f"Error in _on_select_all_toggled: {e}")
            self.app_tree.blockSignals(False)

    def _on_app_item_changed(self, item, column):
        if self.app_tree.signalsBlocked():
            return

        role = item.data(0, Qt.UserRole)
        if not role:
            return

        if role[0] == "app":
            app_name = role[1]
            checked = item.checkState(0) == Qt.Checked

            # toggle all child endpoints
            for i in range(item.childCount()):
                child = item.child(i)
                child.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)

                role_child = child.data(0, Qt.UserRole)
                if not role_child or role_child[0] != "endpoint":
                    continue
                _, app_child, kind, value = role_child
                if checked:
                    self.app_exclude_manager.mark_endpoint_saved(app_child, kind, value)
                else:
                    self.app_exclude_manager.unmark_endpoint_saved(app_child, kind, value)

            self.app_exclude_manager.toggle_desired_app(app_name, checked)

            brush = QBrush(QColor(200, 255, 200, 60)) if checked else QBrush()
            for i in range(item.childCount()):
                for col in range(2):
                    item.child(i).setBackground(col, brush)

            self.btn_apply_pending.setStyleSheet("background-color: #ffd700; color: black; font-weight: bold;")
            return

        if role[0] != "endpoint":
            return

        _, app_name, kind, value = role
        checked = item.checkState(0) == Qt.Checked

        try:
            if hasattr(self.app_exclude_manager, "_timer"):
                self.app_exclude_manager._timer.stop()
        except Exception:
            pass

        try:
            if checked:
                self.app_exclude_manager.mark_endpoint_saved(app_name, kind, value)
                brush = QBrush(QColor(200, 255, 200, 60))
                for i in range(2):
                    item.setBackground(i, brush)
            else:
                self.app_exclude_manager.unmark_endpoint_saved(app_name, kind, value)
                for i in range(2):
                    item.setBackground(i, QBrush())

            self.btn_apply_pending.setStyleSheet("background-color: #ffd700; color: black; font-weight: bold;")

        finally:
            try:
                if hasattr(self.app_exclude_manager, "_timer"):
                    self.app_exclude_manager._timer.start()
            except Exception:
                pass

    def manual_refresh_apps(self):
        try:
            self.app_exclude_manager.scan_processes()
        except Exception as e:
            logger.debug("manual refresh failed: %s", e)

    def apply_pending_changes(self):
        resp = QMessageBox.question(
            self,
            self.tr("Apply Exclusions"),
            self.tr("Applying these network exclusions will cause WARP to reconnect. Continue?"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            return

        try:
            self.app_exclude_manager.batch_apply_warp_rules()
            self.btn_apply_pending.setStyleSheet("")

        except Exception as e:
            logger.exception("apply_pending_changes failed")
            QMessageBox.warning(self, self.tr("Error"), str(e))

    def update_exclude_table(self):
        self.exclude_table.setRowCount(0)
        result_ip = run_warp_command("warp-cli", "-j", "tunnel", "ip", "list")
        if result_ip and result_ip.returncode == 0 and result_ip.stdout.strip():
            try:
                data = json.loads(result_ip.stdout)
                ips = [r.get("value", "") for r in data.get("routes", [])]
                for ip in ExclusionManager.filter_default_ips(ips):
                    self._add_exclude_row("IP", ip)
            except json.JSONDecodeError:
                pass

        result_host = run_warp_command("warp-cli", "-j", "tunnel", "host", "list")
        if result_host and result_host.returncode == 0 and result_host.stdout.strip():
            try:
                data = json.loads(result_host.stdout)
                for host in data.get("hosts", []):
                    self._add_exclude_row("Domain", host.get("value", ""))
            except json.JSONDecodeError:
                pass

    def _add_exclude_row(self, type_name, value):
        row = self.exclude_table.rowCount()
        self.exclude_table.insertRow(row)
        self.exclude_table.setItem(row, 0, QTableWidgetItem(type_name))
        self.exclude_table.setItem(row, 1, QTableWidgetItem(value))

    def open_exclusion_manager(self):
        exclusion_manager = ExclusionManager(self)
        exclusion_manager.exclusions_updated.connect(self.update_exclude_table)
        exclusion_manager.exec()

    def remove_item(self):
        row = self.exclude_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, self.tr("Error"), self.tr("No row selected."))
            return
        mode = self.exclude_table.item(row, 0).text().lower()
        value = self.exclude_table.item(row, 1).text().strip()
        command_mode = "ip" if mode == "ip" else "host"
        result = run_warp_command("warp-cli", "tunnel", command_mode, "remove", value)
        if result and result.returncode == 0:
            self.update_exclude_table()
        else:
            QMessageBox.warning(self, self.tr("Error"),
                                result.stderr.strip() if result else self.tr("Unknown error"))

    def reset_list(self):
        run_warp_command("warp-cli", "tunnel", "ip", "reset")
        run_warp_command("warp-cli", "tunnel", "host", "reset")
        self.update_exclude_table()

        result = self.app_exclude_manager.validate_excluded_apps()
        removed_apps = result["apps"]
        removed_conns = result["connections"]

        # Update UI
        self.populate_app_list([])

        if removed_apps or removed_conns:
            msg = ""
            if removed_apps:
                msg += "Apps unchecked:\n" + "\n".join(sorted(removed_apps)) + "\n\n"
            if removed_conns:
                msg += "Connections removed:\n" + "\n".join(sorted(removed_conns))
            QMessageBox.information(
                self,
                self.tr("Exclusions Updated"),
                self.tr(msg.strip())
            )

    def load_endpoint_history(self):
        history = self.settings_handler.get("endpoint_history", [])
        if isinstance(history, str):
            try:
                history = ast.literal_eval(history)
            except Exception:
                history = []
        if not isinstance(history, list):
            history = []
        if history:
            self.endpoint_input.addItems(history)
        if self.current_endpoint and self.current_endpoint not in history:
            self.endpoint_input.insertItem(0, self.current_endpoint)

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
            QMessageBox.information(self, self.tr("Saved"), self.tr("Endpoint saved successfully."))
        except Exception as e:
            QMessageBox.warning(self, self.tr("Error"), str(e))

    def reset_endpoint(self):
        try:
            run_warp_command("warp-cli", "tunnel", "endpoint", "reset")
            self.settings_handler.save_settings("custom_endpoint", "")
            self.endpoint_input.clear()
            QMessageBox.information(self, self.tr("Reset"), self.tr("Endpoint reset successfully."))
        except Exception as e:
            QMessageBox.warning(self, self.tr("Error"), str(e))

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
            QMessageBox.warning(self, self.tr("Error"), str(e))

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
            QMessageBox.warning(self, self.tr("Error"), str(e))


class SettingsPage(QWidget):
    def __init__(self, parent=None, warp_status_handler=None, settings_handler=None):
        super().__init__(parent)
        self.settings_handler = settings_handler
        self.warp_status_handler = warp_status_handler

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

        grid.addWidget(modes_group, 0, 0)
        grid.addWidget(dns_group, 0, 1)
        grid.addWidget(language_group, 1, 0)
        grid.addWidget(font_group, 1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        main_layout.addLayout(grid)

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

    def open_advanced_settings(self):
        dialog = AdvancedSettings(self.settings_handler, self)
        dialog.exec()

    def create_groupbox(self, title):
        return QGroupBox(title)

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
            else:
                QMessageBox.warning(self, self.tr("Error"),
                                    self.tr("Failed to Set DNS Mode to {}: {}").format(selected_dns,
                                                                                       cmd.stderr.strip()))
                self.dns_dropdown.setCurrentText(self.current_dns_mode)
        except Exception as e:
            QMessageBox.warning(self, self.tr("Error"), f"Command failed: {e}")
            self.dns_dropdown.setCurrentText(self.current_dns_mode)
        finally:
            self.dns_dropdown.setEnabled(True)
            QApplication.restoreOverrideCursor()

    def set_mode(self):
        selected_mode = self.modes_dropdown.currentText()
        port_to_set = None

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
                    self,
                    self.tr("Invalid Port"),
                    self.tr("Please enter a valid port number between 1 and 65535.")
                )
                self.modes_dropdown.setCurrentText(self.current_mode)
                return

        def task():
            if selected_mode == "proxy" and port_to_set:
                set_port_cmd = run_warp_command("warp-cli", "proxy", "port", str(port_to_set))
                if set_port_cmd.returncode != 0:
                    raise RuntimeError(f"Failed to set proxy port:\n{set_port_cmd.stderr.strip()}")
                self.settings_handler.save_settings("proxy_port", str(port_to_set))

            cmd = run_warp_command("warp-cli", "mode", selected_mode)
            if cmd.returncode != 0:
                raise RuntimeError(f"Failed to set mode to {selected_mode}:\n{cmd.stderr.strip()}")
            return selected_mode

        def on_finished(result):
            self.modes_dropdown.setEnabled(True)
            self.current_mode = result
            self.settings_handler.save_settings("mode", result)
            QMessageBox.information(self, self.tr("Mode Changed"),
                                    self.tr("Mode set to: {}").format(result))

        def on_error(exc):
            self.modes_dropdown.setEnabled(True)
            QMessageBox.warning(self, self.tr("Error"), str(exc))
            self.modes_dropdown.setCurrentText(self.current_mode)

        self._worker = run_in_worker(task, parent=self, on_done=on_finished, on_error=on_error)


class MainWindow(QMainWindow):
    instance = None
    def __init__(self, settings_handler=None):
        super().__init__()
        MainWindow.instance = self
        self._is_restarting = False
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
        self.toggle_switch.toggled.connect(self.update_status)
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

        self.reason_label = QLabel("")
        self.reason_label.setFont(QFont("Segoe UI", 10))
        self.reason_label.setAlignment(Qt.AlignCenter)
        self.reason_label.setWordWrap(True)
        self.reason_label.setVisible(False)
        self.reason_label.setStyleSheet("""
            QLabel {
                background-color: rgba(255, 166, 0, 40%);
                color: #ffb347;
                border-radius: 8px;
                padding: 6px 10px;
                font-weight: 500;
            }
        """)
        self.reason_opacity = QGraphicsOpacityEffect()
        self.reason_label.setGraphicsEffect(self.reason_opacity)
        self.reason_fade = QPropertyAnimation(self.reason_opacity, b"opacity", self)
        self.reason_fade.setDuration(400)
        self.reason_fade.setEasingCurve(QEasingCurve.InOutQuad)
        main_layout.addWidget(self.reason_label)

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
        self.stats_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.stats_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

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
            self.status_checker.status_signal.connect(self._on_status_ready_with_reason)
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
        logger.info("Restart requested by user.")
        self._is_restarting = True
        self.force_exit = True
        self.close()

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

    def _on_status_ready_with_reason(self, status: str, reason: str):
        self.update_status(status)
        current_mode = self.settings_handler.get("mode", "warp")
        show_proxy_banner = current_mode == "proxy" and status == "Connected"
        is_error_state = status not in ("Connected", "Disconnected")

        if reason:
            display_reason = reason
            proxy_text = ""
        elif show_proxy_banner:
            port = self.settings_handler.get("proxy_port", "40000")
            proxy_text = self.tr(f"WARP proxy running on 127.0.0.1:<b>{port}</b>")
            display_reason = ""
        else:
            display_reason = status
            proxy_text = ""

        persist = is_error_state or show_proxy_banner

        self._update_reason_color(status, proxy_active=show_proxy_banner)
        self._update_reason_label(reason=display_reason, proxy_text=proxy_text, persist=persist)
        self._ready_checks["status"] = True
        self._check_ready()

    def _update_reason_label(self, reason: str = "", proxy_text: str = "", persist: bool = False):
        if not hasattr(self, "_reason_hide_timer"):
            self._reason_hide_timer = QTimer(self)
            self._reason_hide_timer.setSingleShot(True)
            self._reason_hide_timer.timeout.connect(self._hide_reason_label)

        self._last_persist = persist
        display_text = proxy_text or reason or getattr(self, "_last_reason_text", "")

        if not display_text:
            self._last_persist = False
            self._reason_hide_timer.stop()
            self._hide_reason_label()
            return

        if persist:
            self._reason_hide_timer.stop()
            if hasattr(self, "_reason_fade_animation"):
                self._reason_fade_animation.stop()
            self.reason_label.setVisible(True)
            self.reason_opacity.setOpacity(1.0)
            self._last_reason_text = display_text
            self.reason_label.setText(display_text)
            return

        if getattr(self, "_last_reason_text", "") != display_text:
            self._last_reason_text = display_text
            self.reason_label.setText(display_text)
            self.reason_label.setVisible(True)

            if hasattr(self, "_reason_fade_animation"):
                self._reason_fade_animation.stop()

            self.reason_opacity.setOpacity(0.0)
            fade = QPropertyAnimation(self.reason_opacity, b"opacity", self)
            fade.setStartValue(0.0)
            fade.setEndValue(1.0)
            fade.setDuration(350)
            fade.setEasingCurve(QEasingCurve.OutCubic)
            fade.start()
            self._reason_fade_animation = fade

        self._reason_hide_timer.start(3000)

    def _hide_reason_label(self):
        if getattr(self, "_last_persist", False):
            return
        if not self.reason_label.isVisible():
            return

        self._disconnect_fade_finished()
        self.reason_fade.stop()
        self.reason_fade.setStartValue(1.0)
        self.reason_fade.setEndValue(0.0)
        self.reason_fade.setDuration(300)
        self.reason_fade.start()
        self.reason_fade.finished.connect(lambda: self.reason_label.setVisible(False))

    def _update_reason_color(self, status: str = "", proxy_active: bool = False):
        if not hasattr(self, "reason_label"):
            return

        if proxy_active:
            color = "rgba(88, 166, 255, 35%)"
            text_color = "#58a6ff"
        elif status in ("Connecting", "Disconnecting"):
            color = "rgba(255, 166, 0, 40%)"
            text_color = "#ffb347"
        elif status == "Connected":
            color = "rgba(63, 185, 80, 35%)"
            text_color = "#3fb950"
        elif status in ("Failed", "Disconnected", "No Network"):
            color = "rgba(248, 81, 73, 40%)"
            text_color = "#f85149"
        else:
            color = "rgba(128,128,128,30%)"
            text_color = "#cccccc"

        self.reason_label.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                color: {text_color};
                border-radius: 8px;
                padding: 6px 10px;
                font-weight: 500;
            }}
        """)

    def _disconnect_fade_finished(self):
        try:
            if self.reason_fade.receivers(self.reason_fade.finished) > 0:
                self.reason_fade.finished.disconnect()
        except (TypeError, RuntimeError):
            pass

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
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("PyWarp Tutorials"))
        dialog.resize(700, 600)

        layout = QVBoxLayout(dialog)

        text_browser = QTextBrowser()
        text_browser.setOpenExternalLinks(True)
        text_browser.setStyleSheet("""
            QTextBrowser {
                font-size: 13px;
                line-height: 1.4em;
                padding: 10px;
                background-color: #1e1e1e;
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 8px;
            }
            h2, h3 {
                color: #00bfa5;
                margin-top: 15px;
            }
            ul { margin-left: 20px; }
            li { margin-bottom: 4px; }
            b { color: #ffd54f; }
        """)

        tutorial_html = self.tr(
            "<h2>Welcome to PyWarp!</h2>"
            "<p>PyWarp is a powerful GUI built around the official Cloudflare WARP service, "
            "allowing you to easily control and monitor your WARP connection.</p>"

            "<h3>Getting Started</h3>"
            "<p>You must have the official <b>Cloudflare WARP</b> client installed, "
            "as PyWarp depends on its services to function. "
            "If you cannot install it, PyWarp also offers a bundled package that works without the official client.</p>"

            "<h3>Main Interface</h3>"
            "<p>On the main page, you’ll find:</p>"
            "<ul>"
            "<li><b>Power Button:</b> Turn WARP on or off.</li>"
            "<li><b>Status Labels:</b> Show connection status, IP address, protocol, and source link.</li>"
            "<li><b>Network Stats:</b> Opens the real-time connection statistics page.</li>"
            "<li><b>Settings:</b> Opens the configuration panel.</li>"
            "<li><b>Protocol Switch:</b> Instantly toggle between <b>WireGuard</b> and <b>MASQUE</b> protocols.</li>"
            "</ul>"

            "<h3>Network Stats</h3>"
            "<p>View your live network data including traffic, latency, handshake time, and packet loss.</p>"

            "<h3>Settings</h3>"
            "<p>In the settings page, you can change the WARP operating mode:</p>"
            "<ul>"
            "<li><b>warp:</b> Full VPN tunnel via Cloudflare. Encrypts all traffic.</li>"
            "<li><b>doh:</b> DNS over HTTPS only (secure DNS, no VPN tunnel).</li>"
            "<li><b>warp+doh:</b> VPN + DoH for full encryption and secure DNS.</li>"
            "<li><b>dot:</b> DNS over TLS only.</li>"
            "<li><b>warp+dot:</b> VPN + DoT for full encryption with secure DNS.</li>"
            "<li><b>proxy:</b> Creates a local WARP proxy on localhost (for manual app routing).</li>"
            "<li><b>tunnel_only:</b> Creates a tunnel but does not route traffic automatically.</li>"
            "</ul>"

            "<h3>DNS & Language</h3>"
            "<p>Choose your preferred DNS filtering level:</p>"
            "<ul>"
            "<li><b>No Filter:</b> Standard DNS without filtering.</li>"
            "<li><b>Adult Content Filter:</b> Blocks adult websites.</li>"
            "<li><b>Malware & Ads Filter:</b> Blocks malicious sites and ads.</li>"
            "</ul>"
            "<p>You can also change the application’s <b>language</b> and <b>font</b> here.</p>"

            "<h3>Advanced Settings</h3>"
            "<p>Under Advanced Settings, you’ll find several powerful tools:</p>"
            "<ul>"
            "<li><b>Exclude IP/Domain:</b> Exclude specific IP ranges or domains from WARP tunneling.</li>"
            "<li><b>Exclude Apps:</b> (Coming Soon) Choose which apps bypass WARP.</li>"
            "<li><b>Custom Endpoint:</b> Connect through custom Cloudflare endpoints (last 5 are saved for reuse).</li>"
            "<li><b>MASQUE Options:</b> Change MASQUE protocol behavior:</li>"
            "<ul>"
            "<li><b>h3-only:</b> Use only HTTP/3 (fastest, best for modern networks).</li>"
            "<li><b>h2-only:</b> Force HTTP/2 (can help in restricted environments).</li>"
            "<li><b>h3-with-h2-fallback:</b> Use HTTP/3 with automatic fallback to HTTP/2.</li>"
            "</ul>"
            "</ul>"

            "<p>Enjoy full control over Cloudflare WARP — simply, safely, and visually with PyWarp.</p>"
        )

        text_browser.setHtml(tutorial_html)
        layout.addWidget(text_browser)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        dialog.exec()

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
            def loss_color(val):
                if val < 1:
                    return "green"
                elif val < 5:
                    return "orange"
                return "red"

            prev_loss = getattr(self, "_prev_loss", 0.00)
            self.animate_number(7, 1, prev_loss, loss, "%", loss_color, decimals=2)
            self._prev_loss = loss

        except Exception as e:
            logger.error(f"Error updating stats display: {e}")

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

    app.aboutToQuit.connect(on_about_to_quit)

    update_checker = UpdateChecker(installer=installer)
    update_checker.update_available.connect(notify_update)
    update_checker.start_check(delay_ms=3000)

    window._update_checker = update_checker

    sys.exit(app.exec())
