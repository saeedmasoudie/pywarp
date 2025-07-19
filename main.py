import asyncio
import atexit
import ipaddress
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
from PySide6.QtNetwork import QLocalSocket, QLocalServer
from PySide6.QtCore import Qt, QThread, Signal, QEvent, QObject, QSettings, QTimer
from PySide6.QtGui import QFont, QPalette, QIcon, QAction, QColor, QBrush
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QPushButton, QLabel, QFrame, QStackedWidget,
                               QGraphicsDropShadowEffect, QMessageBox, QSizePolicy, QSystemTrayIcon, QMenu, QComboBox,
                               QLineEdit, QGridLayout, QTableWidget, QAbstractItemView, QTableWidgetItem, QHeaderView,
                               QGroupBox, QSpacerItem, QDialog, QListWidget, QProgressDialog, QInputDialog)

GITHUB_VERSION_URL = "https://raw.githubusercontent.com/saeedmasoudie/pywarp/main/version.txt"
CURRENT_VERSION = "1.1.8"
SERVER_NAME = "PyWarpInstance"
server = QLocalServer()

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
            print(f"Download error: {e}")
            self.finished.emit(False, "")


class UpdateChecker(QObject):
    update_available = Signal(str)

    def check_for_update(self):
        try:
            latest_version = self.get_latest_version()
            if latest_version and self.is_newer_version(latest_version, CURRENT_VERSION):
                self.update_available.emit(latest_version)
        except Exception as e:
            print(f"Update check failed: {e}")

    def get_latest_version(self):
        try:
            response = requests.get(GITHUB_VERSION_URL, timeout=10)
            response.raise_for_status()
            latest_version = response.text.strip()

            if latest_version and self.is_valid_version(latest_version):
                return latest_version
            else:
                print("Received invalid version format")
                return None
        except requests.exceptions.RequestException as e:
            print(f"Network error during update check: {e}")
            return None

    def is_valid_version(self, version):
        """Check if version string is valid (e.g., 1.1.5)"""
        return bool(re.match(r'^\d+\.\d+\.\d+$', version))

    def is_newer_version(self, latest, current):
        """Compare version strings"""
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
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.monitor_status())
        finally:
            loop.close()

    async def monitor_status(self):
        while self.looping:
            try:
                process = await asyncio.create_subprocess_exec(
                    'warp-cli',
                    'status',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    **safe_subprocess_args())
                stdout, stderr = await process.communicate()

                if process.returncode != 0:
                    print(f"warp-cli status error: {stderr.decode()}")
                    current_status = "Failed"
                else:
                    status = stdout.decode()
                    current_status = self.extract_status(status)

                timeout = self.status_map.get(current_status, 5)

                if current_status != self.previous_status:
                    self.status_signal.emit(current_status)
                    self.previous_status = current_status

            except Exception as e:
                print(f"Error checking Warp status: {e}")
                timeout = 10

            await asyncio.sleep(timeout)

    def extract_status(self, status):
        for key in self.status_map.keys():
            if key in status:
                return key
        return self.extract_status_reason(status)

    @staticmethod
    def extract_status_reason(status):
        data = status.split()
        try:
            reason_index = data.index("Reason:")
            reason_text = " ".join(data[reason_index + 1:])
            return 'No Network' if 'No Network' in reason_text else reason_text
        except (ValueError, IndexError):
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
                    print(f"Stats error: {stderr.decode()}")
                    self.stats_signal.emit([])
                    await asyncio.sleep(10)
                    continue

                stats_output = stdout.decode().splitlines()

                if len(stats_output) < 6:
                    print("Unexpected stats output format")
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
                    print(f"Error parsing stats: {e}")
                    self.stats_signal.emit([])

            except Exception as e:
                print(f"Error getting stats: {e}")
                self.stats_signal.emit([])

            await asyncio.sleep(10)


class SettingsHandler(QThread):
    settings_signal = Signal(dict)

    def __init__(self):
        super().__init__()
        self.settings = QSettings("PyWarp", "App")

    def run(self):
        self.settings_signal.emit(self.get_all_settings())

    def save_settings(self, key, value):
        self.settings.setValue(key, value)
        self.settings.sync()

    def get(self, key, default=None):
        return self.settings.value(key, default)

    def get_all_settings(self):
        return {
            "endpoint": self.get("endpoint", ""),
            "dns_mode": self.get("dns_mode", "off"),
            "mode": self.get("mode", "warp")
        }


class PowerButton(QWidget):
    toggled = Signal(str)

    STATES = {
        "Connected": {"style": "on", "text": "ON", "color": QColor("green")},
        "Disconnected": {"style": "off", "text": "OFF", "color": QColor("red")},
        "Connecting": {"style": "unknown", "text": "...", "color": QColor("yellow")},
        "Disconnecting": {"style": "unknown", "text": "...", "color": QColor("yellow")},
        "No Network": {"style": "off", "text": "ERR", "color": QColor("red")},
        "unknown": {"style": "off", "text": "ERR", "color": QColor("red")}
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(150, 150)
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
                result = run_warp_command(*command)
                if not result or result.returncode != 0:
                    error = result.stderr.strip() if result else "Unknown error"
                    self.show_error_dialog("Command Error", f"Failed to run command: {error}")
            finally:
                self.reset_timer.stop()
                QTimer.singleShot(500, self.force_status_refresh)

        threading.Thread(target=toggle, daemon=True).start()

    def update_button_state(self, new_state):
        """Update button appearance based on Warp status"""
        self.state = new_state
        config = self.STATES.get(new_state, self.STATES["unknown"])

        if new_state in ["Connected", "Disconnected", "No Network"]:
            self._toggle_lock = False
            self.power_button.setDisabled(False)
        else:
            self._toggle_lock = True
            self.power_button.setDisabled(True)

        self.apply_style(config["style"], config["text"], config["color"])

    def apply_style(self, style_key, text, glow_color):
        """Apply visual style to button based on state"""
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
        """Handle async error events posted from threads"""
        if event.type() == QEvent.User:
            self.show_error_dialog("Warning", "No network detected. Please check your connection.")
        elif event.type() == QEvent.Type(QEvent.User + 1):
            self.show_error_dialog("Command Error", event.error_message)
        elif event.type() == QEvent.MaxUser:
            self.show_error_dialog("Error", "An unexpected error occurred. Please try again later.")

    def show_error_dialog(self, title, message):
        """Display error message box"""
        if self.current_error_box:
            self.current_error_box.close()

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning if title == "Warning" else QMessageBox.Critical)
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
        self.setWindowTitle("Add Exclusion")
        self.setFixedSize(320, 240)

        # Apply modern styling
        palette = self.palette()
        is_dark_mode = palette.color(QPalette.Window).lightness() < 128
        self.setStyleSheet(self.get_modern_style(is_dark_mode))

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        self.selector = QComboBox()
        self.selector.addItems(["IP", "Domain"])
        layout.addWidget(self.selector)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Enter IP or Domain")
        layout.addWidget(self.input_field)
        layout.addSpacing(10)

        self.submit_button = QPushButton("Add")
        self.submit_button.setMinimumHeight(40)
        self.submit_button.clicked.connect(self.add_item)
        layout.addWidget(self.submit_button, alignment=Qt.AlignCenter)

        self.setLayout(layout)

    def get_modern_style(self, is_dark_mode):
        if is_dark_mode:
            return """
                QDialog {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #0d1117, stop: 1 #161b22);
                    color: #f0f6fc;
                    border: 1px solid #30363d;
                    border-radius: 12px;
                }
                QComboBox, QLineEdit {
                    background-color: #21262d;
                    color: #f0f6fc;
                    border: 1px solid #30363d;
                    border-radius: 8px;
                    padding: 10px;
                    font-size: 14px;
                }
                QComboBox:hover, QLineEdit:hover {
                    border-color: #58a6ff;
                }
                QPushButton {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #238636, stop: 1 #1f7a2e);
                    color: white;
                    padding: 12px 20px;
                    border-radius: 8px;
                    border: none;
                    font-weight: 600;
                    font-size: 14px;
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
                QComboBox, QLineEdit {
                    background-color: #ffffff;
                    color: #24292f;
                    border: 1px solid #d1d9e0;
                    border-radius: 8px;
                    padding: 10px;
                    font-size: 14px;
                }
                QComboBox:hover, QLineEdit:hover {
                    border-color: #0969da;
                }
                QPushButton {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #2da44e, stop: 1 #238636);
                    color: white;
                    padding: 12px 20px;
                    border-radius: 8px;
                    border: none;
                    font-weight: 600;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #2c974b, stop: 1 #2da44e);
                }
            """

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

        if exclusion_type == "ip" and not self.is_valid_ip(value):
            QMessageBox.warning(self, "Invalid Input",
                                "Please enter a valid IP address.")
            return
        elif exclusion_type == "domain" and not self.is_valid_domain(value):
            QMessageBox.warning(self, "Invalid Input",
                                "Please enter a valid domain name.")
            return

        try:
            result = run_warp_command("warp-cli", "tunnel", "ip" if exclusion_type == "ip" else "host", "add", value)

            if result.returncode == 0:
                self.exclusions_updated.emit()
                self.accept()
            else:
                QMessageBox.warning(
                    self, "Error",
                    f"Failed to add {exclusion_type}: {result.stderr.strip()}")
        except subprocess.TimeoutExpired:
            QMessageBox.warning(self, "Error", "Command timed out")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Command failed: {e}")


class AdvancedSettings(QDialog):

    def __init__(self, settings_handler, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Advanced Settings")
        self.setStyleSheet(self.get_stylesheet())
        self.setFixedSize(460, 460)

        self.settings_handler = settings_handler
        self.current_endpoint = self.settings_handler.get("custom_endpoint", "")

        # Exclude IP/Domain
        exclusion_group = QGroupBox("Exclude IP/Domain")
        exclusion_layout = QVBoxLayout()

        self.item_list = QListWidget()
        self.item_list.setMinimumHeight(150)
        self.item_list.setMaximumHeight(150)
        self.item_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        exclusion_layout.addWidget(self.item_list)

        button_layout = QHBoxLayout()
        self.reset_button = QPushButton("Reset")
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
        endpoint_group = QGroupBox("Custom Endpoint")
        endpoint_layout = QHBoxLayout()

        self.endpoint_input = QComboBox()
        self.endpoint_input.setEditable(True)
        self.endpoint_input.setInsertPolicy(QComboBox.InsertAtTop)
        self.endpoint_input.setMinimumWidth(250)

        self.load_endpoint_history()
        self.endpoint_input.setPlaceholderText("Set Custom Endpoint")
        self.endpoint_input.setCurrentText(self.current_endpoint)

        self.endpoint_save_button = QPushButton("Save")
        self.endpoint_save_button.clicked.connect(self.save_endpoint)

        self.endpoint_reset_button = QPushButton("Reset")
        self.endpoint_reset_button.clicked.connect(self.reset_endpoint)

        endpoint_layout.addWidget(self.endpoint_input)
        endpoint_layout.addWidget(self.endpoint_save_button)
        endpoint_layout.addWidget(self.endpoint_reset_button)
        endpoint_group.setLayout(endpoint_layout)

        # Coming Soon
        coming_soon_group = QGroupBox("App Excludes")
        coming_soon_layout = QVBoxLayout()
        coming_soon_layout.addWidget(QLabel("Coming Soon..."))
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
                        self.item_list.addItem(f"IP: {ip_value}")
        except Exception as e:
            print(f"Error getting IP list: {e}")

        # Get host exclusions
        try:
            result_host = run_warp_command("warp-cli", "tunnel", "host", "list")
            if result_host.returncode == 0:
                lines = result_host.stdout.strip().splitlines()
                for line in lines[1:]:
                    host_value = line.strip().split()[0] if line.strip() else ""
                    if host_value:
                        self.item_list.addItem(f"Domain: {host_value}")
        except Exception as e:
            print(f"Error getting host list: {e}")

    def remove_item(self):
        item = self.item_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Error", "No item selected!")
            return

        item_text = item.text().split(": ", 1)
        if len(item_text) != 2:
            QMessageBox.warning(self, "Error", "Invalid entry format!")
            return

        mode = item_text[0].lower().strip()
        value_from_list = item_text[1].strip()
        value_cleaned = value_from_list.split('/')[0]

        try:
            result = run_warp_command("warp-cli", "tunnel", "ip" if mode == "ip" else "host", "remove", value_cleaned)

            if result.returncode == 0:
                self.update_list_view()
            else:
                QMessageBox.warning(
                    self, "Error",
                    f"Failed to remove {mode}:\n\n{result.stderr.strip()}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Command failed: {e}")

    def reset_list(self):
        try:
            run_warp_command("warp-cli", "tunnel", "ip", "reset")
            run_warp_command("warp-cli", "tunnel", "host", "reset")
            self.update_list_view()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Reset failed: {e}")

    def save_endpoint(self):
        endpoint = self.endpoint_input.currentText().strip()
        if not endpoint:
            return

        try:
            result = run_warp_command("warp-cli", "tunnel", "endpoint", "set", endpoint)

            if result.returncode != 0:
                error_line = result.stderr.strip().split("\n")[0]
                QMessageBox.warning(self, "Error", error_line)
                return

            self.settings_handler.save_settings("custom_endpoint", endpoint)
            self.save_endpoint_history(endpoint)
            QMessageBox.information(self, "Saved", "Endpoint saved successfully.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"An exception occurred: {str(e)}")

    def reset_endpoint(self):
        try:
            run_warp_command("warp-cli", "tunnel", "endpoint", "reset")
            self.settings_handler.save_settings("custom_endpoint", "")
            self.endpoint_input.clear()
            QMessageBox.information(self, "Reset", "Endpoint reset successfully.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Reset failed: {e}")

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

        main_layout = QVBoxLayout(self)

        # Modes Section
        modes_group = self.create_groupbox("Modes")
        modes_layout = QGridLayout()
        self.modes_dropdown = QComboBox()
        modes_with_tooltips = {
            "warp": "Full VPN tunnel via Cloudflare. Encrypts all traffic.",
            "doh": "Only DNS over HTTPS (DoH). DNS is secure; rest of traffic is unencrypted.",
            "warp+doh": "VPN tunnel + DNS over HTTPS. Full encryption + secure DNS.",
            "dot": "Only DNS over TLS (DoT). Secure DNS, no VPN tunnel.",
            "warp+dot": "VPN tunnel + DNS over TLS. Full encryption + secure DNS.",
            "proxy": "Sets up a local proxy (manual port needed). Apps can use it via localhost.",
            "tunnel_only": "Tunnel is created but not used unless manually routed."
        }

        for mode, tooltip in modes_with_tooltips.items():
            self.modes_dropdown.addItem(mode)
            index = self.modes_dropdown.findText(mode)
            self.modes_dropdown.setItemData(index, tooltip, Qt.ToolTipRole)

        self.modes_dropdown.setCurrentText(self.current_mode)
        self.modes_dropdown.currentTextChanged.connect(self.set_mode)
        modes_layout.addWidget(self.modes_dropdown, 1, 0, 1, 2)
        modes_layout.addItem(QSpacerItem(10, 15), 0, 0)
        modes_group.setLayout(modes_layout)
        main_layout.addWidget(modes_group)

        # DNS Section
        dns_group = self.create_groupbox("DNS Settings")
        dns_layout = QGridLayout()
        self.dns_dropdown = QComboBox()
        self.dns_dropdown.addItem("Off (No DNS filtering)")
        self.dns_dropdown.addItem("Block Adult Content")
        self.dns_dropdown.addItem("Block Malware")
        self.dns_dropdown.setCurrentText(self.current_dns_mode)
        self.dns_dropdown.currentTextChanged.connect(self.set_dns_mode)
        dns_layout.addWidget(self.dns_dropdown, 1, 0, 1, 2)
        dns_layout.addItem(QSpacerItem(10, 15), 0, 0)
        dns_group.setLayout(dns_layout)
        main_layout.addWidget(dns_group)

        # Advanced Settings Section
        advanced_group = self.create_groupbox("Advanced Settings")
        advanced_layout = QGridLayout()
        advanced_settings_button = QPushButton("Configure Advanced Settings")
        advanced_settings_button.setStyleSheet(self.get_stylesheet())
        advanced_settings_button.clicked.connect(self.open_advanced_settings)
        advanced_layout.addWidget(advanced_settings_button, 1, 2)
        advanced_layout.addItem(QSpacerItem(10, 15), 0, 0)
        advanced_group.setLayout(advanced_layout)
        main_layout.addWidget(advanced_group)

        self.setLayout(main_layout)
        self.setStyleSheet(self.get_stylesheet())

    def open_advanced_settings(self):
        dialog = AdvancedSettings(self.settings_handler, self)
        dialog.exec()

    def create_groupbox(self, title):
        groupbox = QGroupBox(title)
        groupbox.setStyleSheet(self.get_stylesheet())
        return groupbox

    def set_dns_mode(self):
        dns_dict = {
            "off": "off",
            "Block Adult-Content": "full",
            "Block malware": "malware"
        }
        selected_dns = self.dns_dropdown.currentText()

        try:
            cmd = run_warp_command("warp-cli", "dns", "families", dns_dict.get(selected_dns, 'off'))

            if cmd.returncode == 0:
                self.current_dns_mode = selected_dns
                self.settings_handler.save_settings("dns_mode", selected_dns)
                QMessageBox.information(self, "DNS Mode Saved",
                                        f"DNS mode set to: {selected_dns}")
            else:
                QMessageBox.warning(
                    self, "Error",
                    f"Failed to Set DNS Mode to {selected_dns}: {cmd.stderr.strip()}")
                self.dns_dropdown.setCurrentText(self.current_dns_mode)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Command failed: {e}")
            self.dns_dropdown.setCurrentText(self.current_dns_mode)

    def set_mode(self):
        selected_mode = self.modes_dropdown.currentText()

        if selected_mode == "proxy":
            port_str, ok = QInputDialog.getText(self, "Proxy Port Required",
                                                "Enter proxy port (1–65535):")
            if not ok:
                self.modes_dropdown.setCurrentText(self.current_mode)
                return

            try:
                port = int(port_str)
                if not (1 <= port <= 65535):
                    raise ValueError
            except ValueError:
                QMessageBox.warning(
                    self, "Invalid Port",
                    "Please enter a valid port number between 1 and 65535.")
                self.modes_dropdown.setCurrentText(self.current_mode)
                return

            try:
                set_port_cmd = run_warp_command("warp-cli", "proxy", "port", str(port))
                if set_port_cmd.returncode != 0:
                    QMessageBox.warning(
                        self, "Port Set Failed",
                        f"Failed to set proxy port:\n{set_port_cmd.stderr.strip()}")
                    self.modes_dropdown.setCurrentText(self.current_mode)
                    return
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Command failed: {e}")
                self.modes_dropdown.setCurrentText(self.current_mode)
                return

        try:
            cmd = run_warp_command("warp-cli", "mode", selected_mode)
            if cmd.returncode == 0:
                self.current_mode = selected_mode
                self.settings_handler.save_settings("mode", selected_mode)
                QMessageBox.information(self, "Mode Changed",f"Mode set to: {selected_mode}")
            else:
                QMessageBox.warning(
                    self, "Error",
                    f"Failed to set mode to {selected_mode}:\n{cmd.stderr.strip()}")
                self.modes_dropdown.setCurrentText(self.current_mode)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Command failed: {e}")
            self.modes_dropdown.setCurrentText(self.current_mode)

    def get_stylesheet(self):
        palette = QApplication.palette()
        is_dark_mode = palette.color(QPalette.Window).lightness() < 128

        if is_dark_mode:
            return """
                QWidget {
                    background-color: transparent;
                    color: #f0f6fc;
                    font-size: 13px;
                }
                QGroupBox {
                    font-size: 16px;
                    font-weight: 600;
                    color: #f0f6fc;
                    border: 1px solid #30363d;
                    border-radius: 12px;
                    padding: 12px;
                    margin-top: 10px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px 0 5px;
                    color: #58a6ff;
                }
                QComboBox {
                    background-color: #21262d;
                    color: #f0f6fc;
                    border: 1px solid #30363d;
                    border-radius: 8px;
                    padding: 8px 12px;
                    min-height: 20px;
                }
                QComboBox:hover {
                    border-color: #58a6ff;
                }
                QComboBox::drop-down {
                    border: none;
                    width: 20px;
                }
                QComboBox::down-arrow {
                    image: none;
                    border: 2px solid #f0f6fc;
                    width: 6px;
                    height: 6px;
                    border-top: none;
                    border-left: none;
                    transform: rotate(45deg);
                }
                QPushButton {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #238636, stop: 1 #1f7a2e);
                    color: white;
                    border-radius: 8px;
                    padding: 10px 16px;
                    font-weight: 600;
                    border: none;
                }
                QPushButton:hover {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #2ea043, stop: 1 #238636);
                }
                QPushButton:pressed {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #1f7a2e, stop: 1 #1a6928);
                }
            """
        else:
            return """
                QWidget {
                    background-color: transparent;
                    color: #24292f;
                    font-size: 13px;
                }
                QGroupBox {
                    font-size: 16px;
                    font-weight: 600;
                    color: #24292f;
                    border: 1px solid #d1d9e0;
                    border-radius: 12px;
                    padding: 12px;
                    margin-top: 10px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px 0 5px;
                    color: #0969da;
                }
                QComboBox {
                    background-color: #ffffff;
                    color: #24292f;
                    border: 1px solid #d1d9e0;
                    border-radius: 8px;
                    padding: 8px 12px;
                    min-height: 20px;
                }
                QComboBox:hover {
                    border-color: #0969da;
                }
                QComboBox::drop-down {
                    border: none;
                    width: 20px;
                }
                QComboBox::down-arrow {
                    image: none;
                    border: 2px solid #24292f;
                    width: 6px;
                    height: 6px;
                    border-top: none;
                    border-left: none;
                    transform: rotate(45deg);
                }
                QPushButton {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #2da44e, stop: 1 #238636);
                    color: white;
                    border-radius: 8px;
                    padding: 10px 16px;
                    font-weight: 600;
                    border: none;
                }
                QPushButton:hover {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #2c974b, stop: 1 #2da44e);
                }
                QPushButton:pressed {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #238636, stop: 1 #1f7a2e);
                }
            """


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"PyWarp {CURRENT_VERSION}")

        try:
            self.setWindowIcon(QIcon(":/logo.png"))
        except:
            self.setWindowIcon(QIcon())

        self.setGeometry(100, 100, 400, 480)
        self.setWindowFlags(Qt.Window)
        self.current_error_box = None

        self.setup_tray()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        palette = QApplication.palette()
        self.is_dark_mode = palette.color(QPalette.Window).lightness() < 128

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

        self.status_label = QLabel("Status: Disconnected")
        self.status_label.setFont(QFont("Segoe UI", 12))

        self.ip_label = QLabel("IPv4: 0.0.0.0")
        self.ip_label.setFont(QFont("Segoe UI", 12))
        self.ip_label.setToolTip("This is your current public IP address.")

        self.protocol_label = QLabel(
            f"Protocol: <span style='color: #0078D4; font-weight: bold;'>{current_protocol}</span>")

        self.source_label = QLabel(
            "Source: <a href='https://github.com/saeedmasoudie/pywarp' "
            "style='color: #0078D4; font-weight: bold; text-decoration: none;'>"
            "GitHub</a>")
        self.source_label.setTextFormat(Qt.RichText)
        self.source_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.source_label.setOpenExternalLinks(True)
        self.source_label.setToolTip("Click here to visit the app's source code on GitHub")

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
        self.stats_table.setHorizontalHeaderLabels(["Metric", "Value"])
        self.stats_table.verticalHeader().setVisible(False)
        self.stats_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.stats_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.stats_table.setMaximumHeight(280)
        self.stats_table.setMinimumHeight(240)
        self.stats_table.setStyleSheet("""
            QTableWidget {
                font-family: 'Segoe UI';
                font-size: 12pt;
                font-weight: normal;
            }
        """)

        stats_labels = [
            "Protocol", "IPv4 Endpoint", "IPv6 Endpoint", "Last Handshake",
            "Sent Data", "Received Data", "Latency", "Loss"
        ]
        for i, label in enumerate(stats_labels):
            self.stats_table.setItem(i, 0, QTableWidgetItem(label))

        stats_layout.addWidget(self.stats_table)
        self.stacked_widget.addWidget(stats_widget)

        # Settings
        self.settings_handler = SettingsHandler()
        self.settings_handler.start()
        settings_widget = SettingsPage(settings_handler=self.settings_handler)
        self.stacked_widget.addWidget(settings_widget)

        # Buttons
        for idx, btn_text in enumerate(["Network Stats", "Settings", "Protocol"]):
            btn = QPushButton(btn_text)
            btn.setMinimumHeight(32)
            if btn_text != "Protocol":
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

        # Status checker
        self.status_checker = WarpStatusHandler(loop=True)
        self.status_checker.status_signal.connect(self.update_status)
        self.status_checker.start()

        # Stats checker
        self.stats_checker = WarpStatsHandler(self.status_checker, loop=True)
        self.stats_checker.stats_signal.connect(self.update_stats_display)
        self.stats_checker.start()

        self.setStyleSheet(self.get_styles())

    def closeEvent(self, event):
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setWindowTitle("Exit Confirmation")
        msg_box.setText("Do you want to close the app or hide it?")
        close_button = msg_box.addButton("Close", QMessageBox.AcceptRole)
        hide_button = msg_box.addButton("Hide", QMessageBox.RejectRole)
        msg_box.exec()

        if msg_box.clickedButton() == close_button:
            event.accept()
        elif msg_box.clickedButton() == hide_button:
            event.ignore()
            self.hide()

    def show_about(self):
        about_dialog = QMessageBox(self)
        about_dialog.setWindowTitle("About Me")
        about_dialog.setText(
            "Hi, I'm Saeed/Eric, a Python developer passionate about creating efficient applications and constantly learning new things. "
            "You can explore my work on GitHub.")
        github_button = QPushButton("Visit GitHub")
        github_button.clicked.connect(
            lambda: webbrowser.open("https://github.com/saeedmasoudie"))
        about_dialog.addButton(github_button, QMessageBox.ActionRole)
        about_dialog.addButton("Close", QMessageBox.RejectRole)
        about_dialog.exec()

    def show_tutorials(self):
        tutorials_dialog = QMessageBox(self)
        tutorials_dialog.setWindowTitle("PyWarp Tutorials")
        tutorials_dialog.setText(
            "<h2>Welcome to PyWarp!</h2>"
            "<p>This application allows you to manage Cloudflare Warp settings with ease.</p>"
            "<ul>"
            "<li><b>Modes:</b> Select Warp mode (warp, doh, proxy, etc.).</li>"
            "<li><b>DNS Mode:</b> Choose filtering (off, family-friendly, or malware).</li>"
            "<li><b>Endpoint:</b> Set a custom endpoint for advanced configurations.</li>"
            "<li><b>Protocol:</b> Choose your connection protocol.</li>"
            "</ul>"
            "<p><b>⚠️ Important Warning:</b> Disconnect Warp before changing DNS mode or custom endpoint.</p>")
        tutorials_dialog.addButton("Close", QMessageBox.RejectRole)
        tutorials_dialog.exec()

    def setup_tray(self):
        try:
            self.tray_icon = QSystemTrayIcon(QIcon(":/logo.png"), self)
        except:
            self.tray_icon = QSystemTrayIcon(QIcon(), self)

        self.tray_icon.setToolTip("PyWarp - CloudFlare Warp GUI")
        tray_menu = QMenu(self)

        show_action = QAction("Show App", self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)

        help_menu = tray_menu.addMenu("Help")

        about_action = QAction("About Me", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

        tutorials_action = QAction("Tutorials", self)
        tutorials_action.triggered.connect(self.show_tutorials)
        help_menu.addAction(tutorials_action)

        exit_action = QAction("Exit", self)
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

    def update_stats_display(self, stats_list):
        if len(stats_list) != 7:
            return

        if not stats_list:
            for row in range(8):
                self.stats_table.setItem(row, 1, QTableWidgetItem(""))
            return

        try:
            protocol, endpoints, handshake_time, sent, received, latency, loss = stats_list

            # Process handshake time
            handshake_time_cleaned = handshake_time.replace('s', '')
            handshake_value = int(handshake_time_cleaned) if handshake_time_cleaned.isdigit() else 0
            formatted_handshake = format_handshake_time(handshake_value)
            handshake_item = QTableWidgetItem(formatted_handshake)

            # Color code handshake time
            if handshake_value < 1800:
                handshake_item.setForeground(QBrush(QColor("green")))
            elif handshake_value < 3600:
                handshake_item.setForeground(QBrush(QColor("orange")))
            else:
                handshake_item.setForeground(QBrush(QColor("red")))

            # Process endpoints
            endpoints_value = endpoints.split(',')
            ipv4 = endpoints_value[0] if endpoints_value else 'Not Available'
            ipv6 = endpoints_value[1] if len(endpoints_value) > 1 and len(endpoints_value[1]) > 5 else 'Not Available'

            # Process latency
            latency_value = int(latency.replace("ms", "").strip()) if latency.replace("ms", "").strip().isdigit() else 0
            latency_item = QTableWidgetItem(f"{latency_value} ms")

            if latency_value < 100:
                latency_item.setForeground(QBrush(QColor("green")))
            elif latency_value < 200:
                latency_item.setForeground(QBrush(QColor("orange")))
            else:
                latency_item.setForeground(QBrush(QColor("red")))

            # Process loss
            loss_parts = loss.split(";")[0].replace("%", "").strip()
            loss_value = float(loss_parts) if loss_parts.replace(".", "").isdigit() else 0.0
            loss_item = QTableWidgetItem(f"{loss_value}%")

            if loss_value < 1:
                loss_item.setForeground(QBrush(QColor("green")))
            elif loss_value < 5:
                loss_item.setForeground(QBrush(QColor("orange")))
            else:
                loss_item.setForeground(QBrush(QColor("red")))

            # Update table values
            self.stats_table.setItem(0, 1, QTableWidgetItem(protocol))
            self.stats_table.setItem(1, 1, QTableWidgetItem(ipv4))
            self.stats_table.setItem(2, 1, QTableWidgetItem(ipv6))
            self.stats_table.setItem(3, 1, handshake_item)
            self.stats_table.setItem(4, 1, QTableWidgetItem(sent))
            self.stats_table.setItem(5, 1, QTableWidgetItem(received))
            self.stats_table.setItem(6, 1, latency_item)
            self.stats_table.setItem(7, 1, loss_item)

        except Exception as e:
            print(f"Error updating stats display: {e}")

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
                print(f"Error in force status check: {e}")
                QTimer.singleShot(0, lambda: self.update_status("Disconnected"))

        threading.Thread(target=check_status, daemon=True).start()

    def update_status(self, status):
        status_messages = {
            'Connected': "Status: <span style='color: green; font-weight: bold;'>Connected</span>",
            'Disconnected': "Status: <span style='color: red; font-weight: bold;'>Disconnected</span>",
            'Connecting': "Status: <span style='color: orange; font-weight: bold;'>Connecting...</span>",
            'Disconnecting': "Status: <span style='color: orange; font-weight: bold;'>Disconnecting...</span>",
            'No Network': "Status: <span style='color: red; font-weight: bold;'>No Network</span>"
        }

        self.status_label.setText(status_messages.get(status,
                                                      f"Status: <span style='color: red; font-weight: bold;'>Network Error</span>"))

        if status in ['Connected', 'Disconnected']:
            self.ip_label.setText("IPv4: <span style='color: #0078D4; font-weight: bold;'>Receiving...</span>")
            get_global_ip_async(lambda ip: self.ip_label.setText(
                f"IPv4: <span style='color: #0078D4; font-weight: bold;'>{ip}</span>"))
        elif status in ['Connecting', 'Disconnecting']:
            self.ip_label.setText("IPv4: <span style='color: #0078D4; font-weight: bold;'>Receiving...</span>")
        else:
            self.ip_label.setText("IPv4: <span style='color: #0078D4; font-weight: bold;'>Not Available</span>")
            if status == 'No Network':
                self.show_critical_error(
                    "Failed to Connect",
                    "No active internet connection detected. Please check your network settings.")
            else:
                self.show_critical_error("Failed to Connect", status)

        self.toggle_switch.update_button_state(status)

    def show_critical_error(self, title, message):
        """Show critical error dialog without blocking UI updates"""
        self.activateWindow()
        self.raise_()

        # Use timer to ensure status updates are processed first
        QTimer.singleShot(100, lambda: self.show_non_blocking_error(title, message))

    def show_non_blocking_error(self, title, message):
        # Close old box if still open
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

        # Clear reference after it’s closed to avoid double-deletion
        def on_close():
            self.current_error_box = None
            QTimer.singleShot(500, self.force_status_check)

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

    def get_styles(self):
        if self.is_dark_mode:
            return """
                QMainWindow { 
                    background-color: #0d1117; 
                    color: #f0f6fc;
                }
                #statusFrame { 
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #161b22, stop: 1 #0d1117);
                    border: 1px solid #30363d;
                    border-radius: 12px; 
                    padding: 12px;
                    margin: 3px;
                }
                QPushButton { 
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #238636, stop: 1 #1f7a2e);
                    color: white; 
                    padding: 10px 16px; 
                    border-radius: 8px; 
                    border: none;
                    font-weight: 600;
                    font-size: 13px;
                    min-height: 14px;
                }
                QPushButton:hover { 
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #2ea043, stop: 1 #238636);
                    transform: translateY(-1px);
                }
                QPushButton:pressed {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #1f7a2e, stop: 1 #1a6928);
                }
                QPushButton[active="true"] { 
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #2ea043, stop: 1 #238636);
                    border: 2px solid #58a6ff;
                }
                QLabel { 
                    font-size: 14px; 
                    color: #f0f6fc; 
                    font-weight: 500;
                }
                QStackedWidget { 
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #161b22, stop: 1 #0d1117);
                    border: 1px solid #30363d;
                    border-radius: 12px; 
                    padding: 16px;
                    margin: 3px;
                }
                QTableWidget {
                    background-color: #0d1117;
                    alternate-background-color: #161b22;
                    color: #f0f6fc;
                    gridline-color: #30363d;
                    border: 1px solid #30363d;
                    border-radius: 8px;
                }
                QTableWidget::item {
                    padding: 8px;
                    border-bottom: 1px solid #21262d;
                }
                QHeaderView::section {
                    background: #21262d;
                    color: #f0f6fc;
                    font-weight: 600;
                    padding: 10px;
                    border: none;
                    border-right: 1px solid #30363d;
                }
            """
        else:
            return """
                QMainWindow { 
                    background-color: #fafbfc; 
                    color: #24292f;
                }
                #statusFrame { 
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #ffffff, stop: 1 #f6f8fa);
                    border: 1px solid #d1d9e0;
                    border-radius: 12px; 
                    padding: 12px;
                    margin: 3px;
                }
                QPushButton { 
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #2da44e, stop: 1 #238636);
                    color: white; 
                    padding: 10px 16px; 
                    border-radius: 8px; 
                    border: none;
                    font-weight: 600;
                    font-size: 13px;
                    min-height: 14px;
                }
                QPushButton:hover { 
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #2c974b, stop: 1 #2da44e);
                    transform: translateY(-1px);
                }
                QPushButton:pressed {
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #238636, stop: 1 #1f7a2e);
                }
                QPushButton[active="true"] { 
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #2c974b, stop: 1 #2da44e);
                    border: 2px solid #0969da;
                }
                QLabel { 
                    font-size: 14px; 
                    color: #24292f; 
                    font-weight: 500;
                }
                QStackedWidget { 
                    background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                        stop: 0 #ffffff, stop: 1 #f6f8fa);
                    border: 1px solid #d1d9e0;
                    border-radius: 12px; 
                    padding: 16px;
                    margin: 3px;
                }
                QTableWidget {
                    background-color: #ffffff;
                    alternate-background-color: #f6f8fa;
                    color: #24292f;
                    gridline-color: #d1d9e0;
                    border: 1px solid #d1d9e0;
                    border-radius: 8px;
                }
                QTableWidget::item {
                    padding: 8px;
                    border-bottom: 1px solid #eaeef2;
                }
                QHeaderView::section {
                    background: #f6f8fa;
                    color: #24292f;
                    font-weight: 600;
                    padding: 10px;
                    border: none;
                    border-right: 1px solid #d1d9e0;
                }
            """

    def set_protocol(self):
        dlg = QMessageBox(self)
        dlg.setWindowTitle("Change The Protocol")
        dlg.setText("Which protocol do you want to use?")
        dlg.setIcon(QMessageBox.Question)

        base_styles = self.get_styles()
        dialog_styles = """
                QLabel {{
                    color: {label_color};
                    font-family: Segoe UI;
                    font-size: 14px;
                }}
                QMessageBox {{
                    background-color: {message_bg_color};
                }}
            """.format(
            label_color="white" if self.is_dark_mode else "black",
            message_bg_color="#222222" if self.is_dark_mode else "#FFFFFF")
        dlg.setStyleSheet(base_styles + dialog_styles)

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
                    self, "Protocol Changed",
                    f"Protocol successfully changed to {protocol}.")
                self.protocol_label.setText(
                    f"Protocol: <span style='color: #0078D4; font-weight: bold;'>{protocol}</span>")
            else:
                QMessageBox.critical(self, "Error", f"Failed to set protocol: {result.stderr}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to set protocol: {str(e)}")


class WarpInstaller:

    def __init__(self, parent=None):
        self.parent = parent
        self.download_url = self.get_os_download_link()

    def is_warp_installed(self):
        return shutil.which('warp-cli') is not None

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
        msg_box.setWindowTitle("Warp Not Found")
        msg_box.setText("Warp Cloudflare is not installed.\n\nDo you want to install it automatically?")

        auto_install_button = msg_box.addButton("Auto Install", QMessageBox.AcceptRole)
        manual_button = msg_box.addButton("Manual Install", QMessageBox.ActionRole)
        retry_button = msg_box.addButton("Retry Check", QMessageBox.DestructiveRole)
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
        if self.download_url is None:
            self.install_linux_package()
        else:
            self.download_thread = WarpDownloadThread(self.download_url)
            self.progress_dialog = QProgressDialog("Downloading Warp...", "Cancel", 0, 100, self.parent)
            self.progress_dialog.setWindowTitle("Downloading Warp")
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.canceled.connect(self.download_thread.abort)

            self.download_thread.progress.connect(self.progress_dialog.setValue)
            self.download_thread.finished.connect(self.on_download_finished)
            self.download_thread.start()
            self.progress_dialog.exec()

    def on_download_finished(self, success, file_path):
        self.progress_dialog.close()
        if success:
            self.install_downloaded_file(file_path)
        else:
            QMessageBox.critical(self.parent, "Download Failed", "Failed to download Warp installer.")
            self.show_install_prompt()

    def install_downloaded_file(self, file_path):
        try:
            os_name = platform.system()
            if os_name == "Windows":
                run_warp_command("msiexec", "/i", file_path, "/quiet", "/norestart")
            elif os_name == "Darwin":
                run_warp_command("open", file_path)
            else:
                QMessageBox.critical(self.parent, "Unsupported","Automatic install not supported for this OS.")
                sys.exit()

            self.register_and_activate_warp()

        except subprocess.CalledProcessError as e:
            QMessageBox.critical(self.parent, "Installation Failed", f"Failed to install Warp: {e}")
            self.show_install_prompt()
        except Exception as e:
            QMessageBox.critical(self.parent, "Installation Failed", f"Installation error: {e}")
            self.show_install_prompt()

    def install_linux_package(self):
        msg_box = QMessageBox(self.parent)
        msg_box.setWindowTitle("Linux Installation")
        msg_box.setText("Warp will be installed via your system's package manager.\n\nDo you want to proceed?")
        install_button = msg_box.addButton("Install", QMessageBox.AcceptRole)
        cancel_button = msg_box.addButton(QMessageBox.Cancel)
        msg_box.exec()

        if msg_box.clickedButton() == install_button:
            try:
                package_manager = self.detect_linux_package_manager()
                if package_manager == "apt":
                    self.install_with_apt()
                elif package_manager in ["yum", "dnf"]:
                    self.install_with_yum()
                else:
                    QMessageBox.critical(self.parent, "Unsupported",
                                         "Unsupported package manager for auto install.")
                    sys.exit()

                self.register_and_activate_warp()

            except subprocess.CalledProcessError as e:
                QMessageBox.critical(self.parent, "Installation Failed", f"An error occurred:\n{e}")
                self.show_install_prompt()
            except Exception as e:
                QMessageBox.critical(self.parent, "Installation Failed", f"Installation error: {e}")
                self.show_install_prompt()
        else:
            sys.exit()

    def install_with_apt(self):
        commands = [
            ["sudo", "apt", "update"],
            ["sudo", "apt", "install", "-y", "curl", "gpg", "lsb-release", "apt-transport-https", "ca-certificates", "sudo"],
            ["bash", "-c", 'curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | gpg --dearmor --yes -o /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg'],
        ]

        for cmd in commands:
            subprocess.run(cmd, check=True, timeout=300)

        # Get distro
        distro = subprocess.check_output(["lsb_release", "-cs"], timeout=60).decode().strip()

        # Add repository
        repo_cmd = [
            "bash", "-c",
            f'echo "deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] '
            f'https://pkg.cloudflareclient.com/ {distro} main" | '
            f'sudo tee /etc/apt/sources.list.d/cloudflare-client.list'
        ]
        subprocess.run(repo_cmd, check=True, timeout=60)

        # Install
        subprocess.run(["sudo", "apt", "update"], check=True, timeout=300)
        subprocess.run(["sudo", "apt", "install", "-y", "cloudflare-warp"], check=True, timeout=300)

    def install_with_yum(self):
        commands = [
            ["bash", "-c", 'curl -fsSL https://pkg.cloudflareclient.com/cloudflare-warp-ascii.repo | sudo tee /etc/yum.repos.d/cloudflare-warp.repo'],
            ["sudo", "yum", "check-update"],
            ["sudo", "yum", "install", "-y", "curl", "sudo", "coreutils"],
            ["sudo", "yum", "check-update"],
            ["sudo", "yum", "install", "-y", "cloudflare-warp"]
        ]

        for cmd in commands:
            subprocess.run(cmd, check=True, timeout=300)

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
            QMessageBox.information(self.parent, "Warp Found", "Warp is now installed!")
        else:
            self.show_install_prompt()

    def register_and_activate_warp(self):
        try:
            subprocess.run(["warp-cli", "register"], check=True, timeout=60)
            QMessageBox.information(self.parent, "Warp Ready", "Warp has been registered successfully!")
        except subprocess.CalledProcessError as e:
            QMessageBox.critical(self.parent, "Warp Activation Failed", f"Failed to register Warp: {e}")
        except Exception as e:
            QMessageBox.critical(self.parent, "Warp Activation Failed", f"Registration error: {e}")


def format_handshake_time(seconds):
    """Format handshake time in a readable format"""
    hours, remainder = divmod(seconds, 3600)
    mins, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {mins}m {secs}s"
    elif mins:
        return f"{mins}m {secs}s"
    else:
        return f"{secs}s"


def get_global_ip_async(callback):
    """Fetch global IP address asynchronously"""
    def fetch_ip():
        try:
            response = requests.get('https://api.ipify.org',
                                    params={'format': 'json'},
                                    timeout=10)
            response.raise_for_status()
            ip = response.json().get('ip', 'Unavailable')
        except requests.RequestException as e:
            ip = 'Unavailable'
            print(f"Failed to fetch global IP: {e}")
        callback(ip)

    thread = threading.Thread(target=fetch_ip, daemon=True)
    thread.start()


def get_current_protocol():
    """Get current Warp protocol"""
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
        print(f"Error fetching current protocol: {e}")
        return "Error"


def handle_exception(exc_type, exc_value, exc_traceback):
    """Global exception handler"""
    if exc_type is KeyboardInterrupt:
        sys.exit(0)

    error_dialog = QMessageBox()
    error_dialog.setIcon(QMessageBox.Critical)
    error_dialog.setWindowTitle("Application Error")
    error_dialog.setText("An unexpected error occurred!")
    error_dialog.setDetailedText("".join(
        traceback.format_exception(exc_type, exc_value, exc_traceback)))
    error_dialog.exec()


def disconnect_on_exit():
    """Clean shutdown function"""
    server.removeServer(SERVER_NAME)
    try:
        run_warp_command("warp-cli", "disconnect")
        print("Warp disconnected successfully.")
    except Exception as e:
        print(f"Failed to disconnect Warp: {e}")


def safe_subprocess_args():
    return {"shell": False, "creationflags": subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0}

def run_warp_command(*args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30, **safe_subprocess_args())
        return result
    except subprocess.TimeoutExpired:
        print(f"Command timeout: {' '.join(args)}")
        return None
    except Exception as e:
        print(f"Command failed: {' '.join(args)}: {e}")
        return None

def notify_update(latest_version):
    """Show update notification"""
    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Information)
    msg_box.setWindowTitle("Update Available")
    msg_box.setText(f"A new version ({latest_version}) is available! Please update.")
    update_button = msg_box.addButton("Update", QMessageBox.ActionRole)
    msg_box.setStandardButtons(QMessageBox.Ok)
    msg_box.exec()

    if msg_box.clickedButton() == update_button:
        webbrowser.open("https://github.com/saeedmasoudie/pywarp/releases")


def check_existing_instance():
    """Check if another instance is already running"""
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if socket.waitForConnected(500):
        print("Another instance is already running")
        sys.exit(1)


if __name__ == "__main__":
    # Check for existing instance
    check_existing_instance()

    # Create application
    app = QApplication(sys.argv)
    server.listen(SERVER_NAME)
    atexit.register(disconnect_on_exit)

    # Set default icon
    try:
        app.setWindowIcon(QIcon(":/logo.png"))
    except:
        app.setWindowIcon(QIcon())

    # Set exception handler
    sys.excepthook = handle_exception

    # Check for Warp installation
    installer = WarpInstaller(parent=None)
    if not installer.is_warp_installed():
        installer.show_install_prompt()
        if not installer.is_warp_installed():
            QMessageBox.critical(None, "Warp Installation Failed",
                                 "Warp could not be installed.\nExiting app.")
            sys.exit()

    # Set application properties
    app.setFont(QFont("Arial", 10))

    # Create main window
    window = MainWindow()
    window.show()

    # Start update checker
    update_checker = UpdateChecker()
    update_checker.update_available.connect(notify_update)
    update_thread = threading.Thread(target=update_checker.check_for_update, daemon=True)
    update_thread.start()

    # Run application
    sys.exit(app.exec())
