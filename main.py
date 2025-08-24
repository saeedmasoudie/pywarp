import asyncio
import atexit
import ipaddress
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import traceback
import webbrowser
import requests
import resources_rc
from pathlib import Path
from PySide6.QtNetwork import QLocalSocket, QLocalServer
from PySide6.QtCore import Qt, QThread, Signal, QEvent, QObject, QSettings, QTimer, QVariantAnimation, QEasingCurve, \
    QTranslator, QCoreApplication
from PySide6.QtGui import QFont, QPalette, QIcon, QAction, QColor, QBrush, QActionGroup, QTextCursor
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QPushButton, QLabel, QFrame, QStackedWidget,
                               QGraphicsDropShadowEffect, QMessageBox, QSizePolicy, QSystemTrayIcon, QMenu, QComboBox,
                               QLineEdit, QGridLayout, QTableWidget, QAbstractItemView, QTableWidgetItem, QHeaderView,
                               QGroupBox, QDialog, QListWidget, QProgressDialog, QInputDialog, QCheckBox,
                               QTextEdit, QFontComboBox)

CURRENT_VERSION = "1.2.1"
GITHUB_VERSION_URL = "https://raw.githubusercontent.com/saeedmasoudie/pywarp/main/version.txt"
WARP_CLI_URL = f"https://github.com/saeedmasoudie/pywarp/releases/download/v{CURRENT_VERSION}/warp-cli.exe"
WARP_SVC_URL = f"https://github.com/saeedmasoudie/pywarp/releases/download/v{CURRENT_VERSION}/warp-svc.exe"
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


class IpFetcher(QObject):
    ip_ready = Signal(str)

    def fetch_ip(self):
        try:
            response = requests.get('https://api.ipify.org',
                                    params={'format': 'json'},
                                    timeout=10)
            response.raise_for_status()
            ip = response.json().get('ip', self.tr('Unavailable'))
        except requests.RequestException as e:
            ip = self.tr('Unavailable')
            logger.error(f"Failed to fetch global IP: {e}")
        self.ip_ready.emit(ip)


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
    error_dialog.setWindowTitle(QCoreApplication.translate("handle_exception", "Application Error"))
    error_dialog.setText(QCoreApplication.translate("handle_exception", "An unexpected error occurred!"))
    error_dialog.setDetailedText("".join(
        traceback.format_exception(exc_type, exc_value, exc_traceback)))
    error_dialog.exec()


def disconnect_on_exit():
    server.removeServer(SERVER_NAME)
    try:
        run_warp_command("warp-cli", "disconnect")
        logger.info("PyWarp quit and Warp disconnected successfully.")
    except Exception as e:
        logger.error(f"Failed to disconnect Warp on PyWarp quit: {e}")


def safe_subprocess_args():
    if platform.system() == "Windows":
        return {"shell": False, "creationflags": subprocess.CREATE_NO_WINDOW}
    return {"shell": False}


def run_warp_command(*args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30, **safe_subprocess_args())
        return result
    except subprocess.TimeoutExpired:
        logger.error(f"Command timeout: {' '.join(args)}")
        return None
    except Exception as e:
        logger.error(f"Command failed: {' '.join(args)}: {e}")
        return None


def notify_update(update_type, latest_version, current_version):
    app = QApplication.instance()
    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Information)
    msg_box.setWindowTitle(app.translate("notify_update", "Update Available"))
    manual_update_button = msg_box.addButton(app.translate("notify_update", "Update"), QMessageBox.ActionRole)
    msg_box.addButton(app.translate("notify_update", "Later"), QMessageBox.RejectRole)

    if update_type == "pywarp":
        msg_box.setText(
            app.translate("notify_update", "A new version of PyWarp is available!\n\nLatest: {}\nCurrent: {}").format(
                latest_version, current_version))

    elif update_type == "warp_installed":
        msg_box.setText(
            app.translate("notify_update", "A new version of WARP is available!\n\nLatest: {}\nCurrent: {}").format(
                latest_version, current_version))

    elif update_type == "warp_portable":
        msg_box.setText(
            app.translate("notify_update",
                          "A new version of portable WARP is available!\n\nLatest: {}\nCurrent: {}").format(
                latest_version, current_version))
        auto_update_button = msg_box.addButton(app.translate("notify_update", "Auto Update"), QMessageBox.AcceptRole)
        msg_box.setDefaultButton(auto_update_button)
        msg_box.removeButton(manual_update_button)

    msg_box.exec()
    clicked_button = msg_box.clickedButton()

    if clicked_button == manual_update_button:
        webbrowser.open("https://github.com/saeedmasoudie/pywarp/releases")
    elif 'auto_update_button' in locals() and clicked_button == auto_update_button:
        update_thread = threading.Thread(target=update_checker.perform_portable_warp_update, daemon=True)
        update_thread.start()


def show_update_result(message):
    QMessageBox.information(None, QCoreApplication.translate("show_update_result", "Update Status"), message)


def check_existing_instance():
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if socket.waitForConnected(500):
        logger.info("Tried to double run the application: closed before start")
        sys.exit(1)


def get_log_path():
    if sys.platform.startswith("win"):
        base = os.getenv("APPDATA", Path.home())
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Logs"
    else:
        base = Path.home() / ".config"

    log_dir = Path(base) / "PyWarp"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "pywarp.log"


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
        logger.info("Language switched to English")
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

def restart_app():
    python = sys.executable
    os.execl(python, python, *sys.argv)
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

        /* GroupBox */
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

        /* Buttons */
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

        /* Inputs */
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

        /* Tables / Lists */
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

        /* Dialogs & MessageBox */
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
            background-color: #3b82f6;   /* hover effect */
            color: white;
        }}
        QMenu::separator {{
            height: 1px;
            background: #eaeef2;
            margin: 4px 0;
        }}
        """.format(font_name=font_name)


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


class WarpDownloadThread(QThread):
    progress = Signal(int)
    finished = Signal(bool, str)

    def __init__(self, url):
        super().__init__()
        self.url = url
        self._abort = False

    def abort(self):
        self._abort = True

    def run(self):
        try:
            local_filename = self.url.split('/')[-1]
            with requests.get(self.url, stream=True, timeout=30) as r:
                r.raise_for_status()
                total_length = int(r.headers.get('content-length', 0))
                downloaded = 0
                with open(local_filename, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if self._abort:
                            self.finished.emit(False, "")
                            return
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_length > 0:
                                percent = int(downloaded * 100 / total_length)
                                self.progress.emit(percent)
            self.finished.emit(True, local_filename)
        except Exception as e:
            logger.error(f"Download error: {e}")
            self.finished.emit(False, "")


class UpdateChecker(QObject):
    update_available = Signal(str, str, str)
    update_finished = Signal(str)

    def __init__(self, installer, parent=None):
        super().__init__(parent)
        if not installer:
            raise ValueError("UpdateChecker requires a valid WarpInstaller instance.")
        self.installer = installer

    def check_for_update(self):
        try:
            versions = self._get_latest_versions()
            if not versions:
                logger.error("Could not retrieve latest version info.")
                return

            latest_pywarp = versions.get("pywarp")
            if latest_pywarp and self._is_newer_version(latest_pywarp, CURRENT_VERSION):
                self.update_available.emit("pywarp", latest_pywarp, CURRENT_VERSION)

            latest_warp = versions.get("warp")
            local_warp_version, _, is_portable = self.get_warp_info()

            if latest_warp and local_warp_version and self._is_newer_version(latest_warp, local_warp_version):
                update_type = "warp_portable" if is_portable else "warp_installed"
                self.update_available.emit(update_type, latest_warp, local_warp_version)

        except Exception as e:
            logger.error(f"Update check failed: {e}")

    def _get_latest_versions(self):
        try:
            response = requests.get(GITHUB_VERSION_URL, timeout=10)
            response.raise_for_status()
            lines = response.text.strip().splitlines()
            return {k.strip(): v.strip() for k, v in (line.split("=", 1) for line in lines if "=" in line)}
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during update check: {e}")
            return None

    def get_warp_info(self):
        try:
            warp_cli_path, _ = self.installer._portable_paths()
            if warp_cli_path.exists():
                out = subprocess.check_output(
                    [str(warp_cli_path), "--version"],
                    text=True,
                    **safe_subprocess_args()
                )
                version = out.strip().split()[-1]
                return version, warp_cli_path, True
        except (IOError, subprocess.SubprocessError):
            pass

        try:
            if shutil.which("warp-cli"):
                out = subprocess.check_output(["warp-cli", "--version"], text=True, **safe_subprocess_args())
                version = out.strip().split()[-1]
                return version, Path(shutil.which("warp-cli")), False
        except (IOError, subprocess.SubprocessError):
            pass

        return None, None, False

    def perform_portable_warp_update(self):
        try:
            cli_path, svc_path = self.installer._portable_paths()
            cli_temp_path = cli_path.with_suffix(".exe.tmp")
            svc_temp_path = svc_path.with_suffix(".exe.tmp")

            logger.info("Downloading latest warp-cli.exe...")
            cli_response = requests.get(WARP_CLI_URL, timeout=60)
            cli_response.raise_for_status()
            with open(cli_temp_path, "wb") as f:
                f.write(cli_response.content)

            logger.info("Downloading latest warp-svc.exe...")
            svc_response = requests.get(WARP_SVC_URL, timeout=60)
            svc_response.raise_for_status()
            with open(svc_temp_path, "wb") as f:
                f.write(svc_response.content)

            shutil.move(cli_temp_path, cli_path)
            shutil.move(svc_temp_path, svc_path)

            logger.info("Portable WARP update successful!")
            self.update_finished.emit(self.tr("✅ Portable WARP has been successfully updated!"))

        except Exception as e:
            logger.error(f"Portable WARP update failed: {e}")
            self.update_finished.emit(self.tr("❌ Update failed: {}").format(e))

    def _is_newer_version(self, latest, current):
        try:
            from packaging import version
            return version.parse(latest) > version.parse(current)
        except (ImportError, TypeError):
            latest_parts = [int(x) for x in latest.split('.')]
            current_parts = [int(x) for x in current.split('.')]
            return latest_parts > current_parts


class WarpStatusHandler(QThread):
    status_signal = Signal(str)

    def __init__(self, loop=True):
        super().__init__()
        self.looping = loop
        self.previous_status = None
        self.status_map = {"Connected": 8, "Disconnected": 8, "Connecting": 2}

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.monitor_status())
        finally:
            loop.close()

    async def monitor_status(self):
        connecting_count = 0
        while self.looping:
            try:
                process = await asyncio.create_subprocess_exec(
                    'warp-cli', 'status',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    **safe_subprocess_args()
                )
                stdout, stderr = await process.communicate()

                if process.returncode != 0:
                    logger.error(f"warp-cli status error: {stderr.decode()}")
                    current_status = "Failed"
                else:
                    status = stdout.decode()
                    current_status = self.extract_status(status)

                timeout = self.status_map.get(current_status, 5)

                if current_status == "Connecting":
                    connecting_count += 1
                    if connecting_count * timeout >= 15:
                        self.previous_status = None
                        connecting_count = 0
                else:
                    connecting_count = 0

                if self.previous_status != current_status:
                    self.status_signal.emit(current_status)
                    self.previous_status = current_status

            except Exception as e:
                logger.error(f"Error checking Warp status: {e}")
                timeout = 10

            await asyncio.sleep(timeout)

    def extract_status(self, status):
        for key in self.status_map.keys():
            if key in status:
                return key
        return self.extract_status_reason(status)

    @staticmethod
    def extract_status_reason(status):
        match = re.search(r"Reason:\s*(.*)", status)
        if match:
            reason_text = match.group(1).strip()
            return 'No Network' if 'No Network' in reason_text else reason_text
        return "Failed"


class WarpStatsHandler(QThread):
    stats_signal = Signal(list)

    def __init__(self, status_handler, loop=True):
        super().__init__()
        self.looping = loop
        self.status_handler = status_handler
        self.status_handler.status_signal.connect(self.update_status)
        self.warp_connected = False

    def update_status(self, status):
        self.warp_connected = (status == "Connected")

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.monitor_stats())
        finally:
            loop.close()

    async def monitor_stats(self):
        while self.looping:
            if not self.warp_connected:
                self.stats_signal.emit([])
                await asyncio.sleep(6)
                continue

            try:
                process = await asyncio.create_subprocess_exec(
                    'warp-cli',
                    'tunnel',
                    'stats',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    **safe_subprocess_args())
                stdout, stderr = await process.communicate()

                if process.returncode != 0:
                    logger.error(f"Stats error: {stderr.decode()}")
                    self.stats_signal.emit([])
                    await asyncio.sleep(10)
                    continue

                stats_output = stdout.decode().splitlines()

                if len(stats_output) < 6:
                    logger.error("Unexpected stats output format")
                    self.stats_signal.emit([])
                    await asyncio.sleep(30)
                    continue

                try:
                    protocol = stats_output[0].split(": ")[1].split(" ")[0]
                    endpoints = stats_output[1].split(': ')[1]
                    handshake_time = stats_output[2].split(': ')[1]
                    data_line = stats_output[3].split('; ')
                    sent = data_line[0].split(':')[1].strip()
                    received = data_line[1].split(':')[1].strip()
                    latency = stats_output[4].split(': ')[1]
                    loss = stats_output[5].split(': ')[1]

                    self.stats_signal.emit([
                        protocol, endpoints, handshake_time, sent, received,
                        latency, loss
                    ])
                except (IndexError, ValueError) as e:
                    logger.error(f"Error parsing stats: {e}")
                    self.stats_signal.emit([])

            except Exception as e:
                logger.error(f"Error getting stats: {e}")
                self.stats_signal.emit([])

            await asyncio.sleep(10)


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
            "silent_mode": self.get("silent_mode", False)
        }


class PowerButton(QWidget):
    toggled = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(150, 150)

        self.STATES = {
            "Connected": {"style": "on", "text": self.tr("ON"), "color": QColor("green")},
            "Disconnected": {"style": "off", "text": self.tr("OFF"), "color": QColor("red")},
            "Connecting": {"style": "unknown", "text": "...", "color": QColor("yellow")},
            "Disconnecting": {"style": "unknown", "text": "...", "color": QColor("yellow")},
            "No Network": {"style": "off", "text": self.tr("ERR"), "color": QColor("red")},
            "unknown": {"style": "off", "text": self.tr("ERR"), "color": QColor("red")}
        }

        self.current_error_box = None
        self.state = 'Disconnected'
        self._toggle_lock = False

        palette = QApplication.palette()
        is_dark_mode = palette.color(QPalette.Window).lightness() < 128
        self.theme = "dark" if is_dark_mode else "light"

        # Button styles
        self.button_styles = {
            "off": {
                "dark": """
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #0d1117, stop: 1 #161b22);
                    border: 3px solid #f85149; 
                    color: #f85149;
                    font-weight: 700;
                """,
                "light": """
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #ffffff, stop: 1 #f6f8fa);
                    border: 3px solid #d1242f; 
                    color: #d1242f;
                    font-weight: 700;
                """
            },
            "unknown": {
                "dark": """
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #0d1117, stop: 1 #161b22);
                    border: 3px solid #f0883e; 
                    color: #f0883e;
                    font-weight: 700;
                """,
                "light": """
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #ffffff, stop: 1 #f6f8fa);
                    border: 3px solid #d15704; 
                    color: #d15704;
                    font-weight: 700;
                """
            },
            "on": {
                "dark": """
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #0d1117, stop: 1 #161b22);
                    border: 3px solid #3fb950; 
                    color: #3fb950;
                    font-weight: 700;
                """,
                "light": """
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #ffffff, stop: 1 #f6f8fa);
                    border: 3px solid #2da44e; 
                    color: #2da44e;
                    font-weight: 700;
                """
            }
        }

        self.power_button = QPushButton("...", self)
        self.power_button.setGeometry(25, 25, 100, 100)
        self.power_button.setStyleSheet("border-radius: 50px; font-size: 24px;")
        self.power_button.setFont(QFont("Arial", 16, QFont.Bold))

        self.glow_effect = QGraphicsDropShadowEffect()
        self.glow_effect.setBlurRadius(50)
        self.glow_effect.setColor(Qt.yellow)
        self.glow_effect.setOffset(0, 0)
        self.power_button.setGraphicsEffect(self.glow_effect)

        self.power_button.clicked.connect(self.toggle_power)

        self.reset_timer = QTimer(self)
        self.reset_timer.setSingleShot(True)
        self.reset_timer.timeout.connect(self.reset_button_state)

    def toggle_power(self):
        if self._toggle_lock:
            return
        self._toggle_lock = True
        self.power_button.setDisabled(True)
        self.apply_style("unknown", "...", QColor("yellow"))

        def toggle():
            try:
                self.reset_timer.start(15000)
                command = ["warp-cli", "connect"] if self.state == "Disconnected" else ["warp-cli", "disconnect"]
                self.toggled.emit("Connecting") if command != ["warp-cli", "disconnect"] else self.toggled.emit(
                    "Disconnected")
                result = run_warp_command(*command)
                if not result or result.returncode != 0:
                    error = result.stderr.strip() if result else self.tr("Unknown error")
                    self.show_error_dialog(self.tr("Command Error"), self.tr("Failed to run command: {}").format(error))
            finally:
                self.reset_timer.stop()
                QTimer.singleShot(500, self.force_status_refresh)

        threading.Thread(target=toggle, daemon=True).start()

    def update_button_state(self, new_state):
        self.state = new_state
        config = self.STATES.get(new_state, self.STATES["unknown"])

        if new_state in ["Connected", "Disconnected", "Connecting"]:
            self._toggle_lock = False
            self.power_button.setDisabled(False)
        else:
            self._toggle_lock = True
            self.power_button.setDisabled(True)

        self.apply_style(config["style"], config["text"], config["color"])

    def apply_style(self, style_key, text, glow_color):
        stylesheet = self.button_styles.get(style_key, {}).get(self.theme, "")
        self.power_button.setStyleSheet(stylesheet + "border-radius: 50px; font-size: 24px;")
        self.power_button.setText(text)
        self.glow_effect.setColor(glow_color)
        self.power_button.update()
        self.update()

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

        if exclusion_type == self.tr("ip").lower() and not self.is_valid_ip(value):
            QMessageBox.warning(self, self.tr("Invalid Input"),
                                self.tr("Please enter a valid IP address."))
            return
        elif exclusion_type == self.tr("domain").lower() and not self.is_valid_domain(value):
            QMessageBox.warning(self, self.tr("Invalid Input"),
                                self.tr("Please enter a valid domain name."))
            return

        try:
            command_type = "ip" if exclusion_type == self.tr("ip").lower() else "host"
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
        self.setFixedSize(460, 460)

        self.settings_handler = settings_handler
        self.current_endpoint = self.settings_handler.get("custom_endpoint", "")

        # Exclude IP/Domain
        exclusion_group = QGroupBox(self.tr("Exclude IP/Domain"))
        exclusion_layout = QVBoxLayout()

        self.item_list = QListWidget()
        self.item_list.setMinimumHeight(150)
        self.item_list.setMaximumHeight(150)
        self.item_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
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
        self.endpoint_input.setMinimumWidth(250)

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

        # Coming Soon
        coming_soon_group = QGroupBox(self.tr("App Excludes"))
        coming_soon_layout = QVBoxLayout()
        coming_soon_layout.addWidget(QLabel(self.tr("Coming Soon...")))
        coming_soon_group.setLayout(coming_soon_layout)

        layout = QVBoxLayout()
        layout.addWidget(exclusion_group)
        layout.addWidget(endpoint_group)
        layout.addWidget(coming_soon_group)
        self.setLayout(layout)
        self.update_list_view()

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
            command_mode = "ip" if mode == self.tr("ip").lower() else "host"
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

    def get_stylesheet(self):
        palette = self.palette()
        is_dark_mode = palette.color(QPalette.Window).lightness() < 128

        if is_dark_mode:
            return """
                QDialog {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #0d1117, stop: 1 #161b22);
                    color: #f0f6fc;
                    border: 1px solid #30363d;
                    border-radius: 12px;
                }
                QGroupBox {
                    border: 1px solid #30363d;
                    border-radius: 8px;
                    padding: 12px;
                    font-weight: 600;
                    font-size: 14px;
                    color: #58a6ff;
                    margin-top: 8px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px 0 5px;
                }
                QComboBox, QLineEdit {
                    background-color: #21262d;
                    color: #f0f6fc;
                    border: 1px solid #30363d;
                    border-radius: 6px;
                    padding: 8px;
                    font-size: 13px;
                }
                QComboBox:hover, QLineEdit:hover {
                    border-color: #58a6ff;
                }
                QListWidget {
                    background-color: #0d1117;
                    color: #f0f6fc;
                    border: 1px solid #30363d;
                    border-radius: 6px;
                    font-size: 13px;
                }
                QListWidget::item {
                    padding: 6px;
                    border-bottom: 1px solid #21262d;
                }
                QListWidget::item:hover {
                    background-color: #161b22;
                }
                QListWidget::item:selected {
                    background-color: #1f6feb;
                }
                QPushButton {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #238636, stop: 1 #1f7a2e);
                    color: white;
                    padding: 8px 12px;
                    border-radius: 6px;
                    border: none;
                    font-weight: 600;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #2ea043, stop: 1 #238636);
                }
            """
        else:
            return """
                QDialog {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #ffffff, stop: 1 #f6f8fa);
                    color: #24292f;
                    border: 1px solid #d1d9e0;
                    border-radius: 12px;
                }
                QGroupBox {
                    border: 1px solid #d1d9e0;
                    border-radius: 8px;
                    padding: 12px;
                    font-weight: 600;
                    font-size: 14px;
                    color: #0969da;
                    margin-top: 8px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px 0 5px;
                }
                QComboBox, QLineEdit {
                    background-color: #ffffff;
                    color: #24292f;
                    border: 1px solid #d1d9e0;
                    border-radius: 6px;
                    padding: 8px;
                    font-size: 13px;
                }
                QComboBox:hover, QLineEdit:hover {
                    border-color: #0969da;
                }
                QListWidget {
                    background-color: #ffffff;
                    color: #24292f;
                    border: 1px solid #d1d9e0;
                    border-radius: 6px;
                    font-size: 13px;
                }
                QListWidget::item {
                    padding: 6px;
                    border-bottom: 1px solid #eaeef2;
                }
                QListWidget::item:hover {
                    background-color: #f6f8fa;
                }
                QListWidget::item:selected {
                    background-color: #dbeafe;
                }
                QPushButton {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #2da44e, stop: 1 #238636);
                    color: white;
                    padding: 8px 12px;
                    border-radius: 6px;
                    border: none;
                    font-weight: 600;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #2c974b, stop: 1 #2da44e);
                }
            """


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
            "proxy": self.tr("Sets up a local proxy (manual port needed). Apps can use it via localhost."),
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
        restart_app()

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

    def set_mode(self):
        selected_mode = self.modes_dropdown.currentText()

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
            except ValueError:
                QMessageBox.warning(
                    self, self.tr("Invalid Port"),
                    self.tr("Please enter a valid port number between 1 and 65535.")
                )
                self.modes_dropdown.setCurrentText(self.current_mode)
                return

            try:
                set_port_cmd = run_warp_command("warp-cli", "proxy", "port", str(port))
                if set_port_cmd.returncode != 0:
                    QMessageBox.warning(
                        self, self.tr("Port Set Failed"),
                        self.tr("Failed to set proxy port:\n{}").format(set_port_cmd.stderr.strip())
                    )
                    logger.error(f"Failed to set proxy port: {set_port_cmd.stderr.strip()}")
                    self.modes_dropdown.setCurrentText(self.current_mode)
                    return

                self.settings_handler.save_settings("proxy_port", str(port))
                logger.info(f"Proxy Port set to: {port}")

            except Exception as e:
                QMessageBox.warning(self, self.tr("Error"), self.tr("Command failed: {}").format(e))
                logger.error(f"Failed to set proxy port: {e}")
                self.modes_dropdown.setCurrentText(self.current_mode)
                return

        try:
            cmd = run_warp_command("warp-cli", "mode", selected_mode)
            if cmd.returncode == 0:
                self.current_mode = selected_mode
                self.settings_handler.save_settings("mode", selected_mode)

                main_window = self.window()
                if isinstance(main_window, MainWindow):
                    for action in main_window.modes_group.actions():
                        if action.text() == selected_mode:
                            action.setChecked(True)

                    if selected_mode == "proxy":
                        port = self.settings_handler.get("proxy_port", "40000")
                        main_window.info_label.setText(
                            self.tr(
                                "Proxy running on 127.0.0.1:<span style='color: #0078D4; font-weight: bold;'>{}</span>").format(
                                port)
                        )
                        main_window.info_label.show()
                    else:
                        main_window.info_label.hide()
                logger.info(f"Successfully set mode to {selected_mode}")
                QMessageBox.information(self, self.tr("Mode Changed"), self.tr("Mode set to: {}").format(selected_mode))
            else:
                logger.error(f"Failed to set mode to {selected_mode} : {cmd.stderr.strip()}")
                QMessageBox.warning(
                    self, self.tr("Error"),
                    self.tr("Failed to set mode to {}:\n{}").format(selected_mode, cmd.stderr.strip())
                )
                self.modes_dropdown.setCurrentText(self.current_mode)
        except Exception as e:
            QMessageBox.warning(self, self.tr("Error"), self.tr("Command failed: {}").format(e))
            self.modes_dropdown.setCurrentText(self.current_mode)


class MainWindow(QMainWindow):
    def __init__(self, settings_handler=None):
        super().__init__()
        self.settings_handler = settings_handler or SettingsHandler()
        if settings_handler is None:
            self.settings_handler.start()
        self.setWindowTitle(self.tr("PyWarp {}").format(CURRENT_VERSION))

        self.color_icon = QIcon(":/logo.png")
        self.gray_icon = QIcon(":/logo_gray.png")

        font_name = self.settings_handler.get("font_family", QApplication.font().family())
        ThemeManager.apply(str(font_name))

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

        current_protocol = get_current_protocol()

        self.status_label = QLabel(self.tr("Status: Disconnected"))
        self.status_label.setFont(QFont("Segoe UI", 12))

        self.ip_label = QLabel(self.tr("IPv4: 0.0.0.0"))
        self.ip_label.setFont(QFont("Segoe UI", 12))
        self.ip_label.setToolTip(self.tr("This is your current public IP address."))

        self.protocol_label = QLabel(
            self.tr("Protocol: <span style='color: #0078D4; font-weight: bold;'>{}</span>").format(current_protocol))

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
        self.info_label.hide()
        main_layout.addWidget(self.info_label)

        main_layout.addWidget(self.stacked_widget)

        # Status checker
        self.status_checker = WarpStatusHandler(loop=True)
        self.status_checker.status_signal.connect(self.update_status)
        self.status_checker.start()

        # Stats checker
        self.stats_checker = WarpStatsHandler(self.status_checker, loop=True)
        self.stats_checker.stats_signal.connect(self.update_stats_display)
        self.stats_checker.start()

    def closeEvent(self, event):
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setWindowTitle(self.tr("Exit Confirmation"))
        msg_box.setText(self.tr("Do you want to close the app or hide it?"))
        close_button = msg_box.addButton(self.tr("Close"), QMessageBox.AcceptRole)
        hide_button = msg_box.addButton(self.tr("Hide"), QMessageBox.RejectRole)
        msg_box.exec()

        if msg_box.clickedButton() == close_button:
            event.accept()
        elif msg_box.clickedButton() == hide_button:
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
        exit_action.triggered.connect(self.close)
        tray_menu.addAction(exit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.tray_icon.show()

    def on_tray_icon_activated(self, reason):
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

    def update_status(self, status):
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

        self.status_label.setText(status_messages.get(status,
                                                      self.tr(
                                                          "Status: <span style='color: red; font-weight: bold;'>Network Error</span>")))

        if status in ['Connected', 'Disconnected']:
            self.ip_label.setText(self.tr("IPv4: <span style='color: #0078D4; font-weight: bold;'>Receiving...</span>"))
            self.ip_fetcher_thread = QThread()
            self.ip_fetcher = IpFetcher()
            self.ip_fetcher.moveToThread(self.ip_fetcher_thread)

            self.ip_fetcher_thread.started.connect(self.ip_fetcher.fetch_ip)
            self.ip_fetcher.ip_ready.connect(self.update_ip_label)
            self.ip_fetcher.ip_ready.connect(self.ip_fetcher_thread.quit)
            self.ip_fetcher.ip_ready.connect(self.ip_fetcher.deleteLater)
            self.ip_fetcher_thread.finished.connect(self.ip_fetcher_thread.deleteLater)

            self.ip_fetcher_thread.start()
        elif status in ['Connecting', 'Disconnecting']:
            self.ip_label.setText(self.tr("IPv4: <span style='color: #0078D4; font-weight: bold;'>Receiving...</span>"))
        else:
            self.ip_label.setText(
                self.tr("IPv4: <span style='color: #0078D4; font-weight: bold;'>Not Available</span>"))
            if status == 'No Network':
                self.show_critical_error(
                    self.tr("Failed to Connect"),
                    self.tr("No active internet connection detected. Please check your network settings."))
            else:
                self.show_critical_error(self.tr("Failed to Connect"), status)

        self.toggle_switch.update_button_state(status)

    def update_ip_label(self, ip):
        self.ip_label.setText(self.tr("IPv4: <span style='color: #0078D4; font-weight: bold;'>{}</span>").format(ip))

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
        # Helper for translation in this non-QObject class
        return QCoreApplication.translate("WarpInstaller", text)

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

        auto_install_button = msg_box.addButton(self.tr("Auto Install"), QMessageBox.AcceptRole)
        manual_button = msg_box.addButton(self.tr("Manual Install"), QMessageBox.ActionRole)
        retry_button = msg_box.addButton(self.tr("Retry Check"), QMessageBox.DestructiveRole)
        cancel_button = msg_box.addButton(QMessageBox.Cancel)
        msg_box.exec()

        clicked = msg_box.clickedButton()
        if clicked == auto_install_button:
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
            self.install_windows_portable()
            return

        if self.download_url is None:
            self.install_linux_package()
            return

        self.download_thread = WarpDownloadThread(self.download_url)
        self.progress_dialog = QProgressDialog(self.tr("Downloading WARP..."), self.tr("Cancel"), 0, 100, self.parent)
        self.progress_dialog.setWindowTitle(self.tr("Downloading WARP"))
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.canceled.connect(self.download_thread.abort)
        self.download_thread.progress.connect(self.progress_dialog.setValue)
        self.download_thread.finished.connect(self.on_download_finished)
        self.download_thread.start()
        self.progress_dialog.exec()

    def install_windows_portable(self):
        try:
            base_url = "https://github.com/saeedmasoudie/pywarp/releases/latest/download/"
            for binary in ["warp-cli.exe", "warp-svc.exe"]:
                url = base_url + binary
                r = requests.get(url, stream=True, timeout=90)
                r.raise_for_status()
                with open(self.appdata_dir / binary, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

            self._ensure_warp_svc_running_windows()
            self.register_and_activate_warp()

        except Exception as e:
            QMessageBox.critical(self.parent, self.tr("Warp Install Failed"),
                                 self.tr("Could not setup portable WARP binaries:\n{}").format(e))
            self._fallback_windows_prompt()

    def _fallback_windows_prompt(self):
        if self.download_url:
            self.download_thread = WarpDownloadThread(self.download_url)
            self.progress_dialog = QProgressDialog(self.tr("Downloading WARP (MSI fallback)..."), self.tr("Cancel"), 0,
                                                   100, self.parent)
            self.progress_dialog.setWindowTitle(self.tr("Downloading WARP"))
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.canceled.connect(self.download_thread.abort)
            self.download_thread.progress.connect(self.progress_dialog.setValue)
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
                try:
                    subprocess.Popen([str(warp_svc)],
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL,
                                     **safe_subprocess_args())
                except Exception as e:
                    QMessageBox.critical(self.parent, self.tr("Warp Error"),
                                         self.tr("Failed to start warp-svc: {}").format(e))
                    raise

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
        msg_box.setText(self.tr("WARP will be installed via your system's package manager.\n\nDo you want to proceed?"))
        install_button = msg_box.addButton(self.tr("Install"), QMessageBox.AcceptRole)
        cancel_button = msg_box.addButton(QMessageBox.Cancel)
        msg_box.exec()

        if msg_box.clickedButton() != install_button:
            sys.exit()

        try:
            pm = self.detect_linux_package_manager()
            if pm == "apt":
                self.install_with_apt()
            elif pm in ("yum", "dnf"):
                self.install_with_yum_dnf(pm)
            else:
                QMessageBox.critical(self.parent, self.tr("Unsupported"),
                                     self.tr("Unsupported package manager for auto install."))
                sys.exit()
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
                cmd = [str(warp_cli), "register"]
            else:
                cmd = ["warp-cli", "register"]

            subprocess.run(cmd, check=True, timeout=60)
            QMessageBox.information(self.parent, self.tr("Warp Ready"),
                                    self.tr("WARP has been registered successfully!"))
        except subprocess.CalledProcessError as e:
            QMessageBox.critical(self.parent, self.tr("Warp Activation Failed"),
                                 self.tr("Failed to register WARP: {}").format(e))
        except Exception as e:
            QMessageBox.critical(self.parent, self.tr("Warp Activation Failed"),
                                 self.tr("Registration error: {}").format(e))


if __name__ == "__main__":
    check_existing_instance()
    app = QApplication(sys.argv)
    server.listen(SERVER_NAME)
    atexit.register(disconnect_on_exit)

    logger, log_path = setup_logger()

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

    window = MainWindow(settings_handler=settings_handler)
    window.show()

    update_checker = UpdateChecker(installer=installer)
    update_checker.update_available.connect(notify_update)
    update_thread = threading.Thread(target=update_checker.check_for_update, daemon=True)
    update_thread.start()
    sys.exit(app.exec())
