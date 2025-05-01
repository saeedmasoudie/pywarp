import asyncio
import atexit
import ipaddress
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import traceback
import webbrowser

from PySide6.QtNetwork import QLocalSocket, QLocalServer

import resources_rc
import requests
from PySide6.QtCore import Qt, QThread, Signal, QEvent, QStandardPaths, QObject
from PySide6.QtGui import QFont, QPalette, QIcon, QAction, QColor, QBrush
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QPushButton, QLabel, QFrame, QStackedWidget,
                               QGraphicsDropShadowEffect, QMessageBox, QSizePolicy, QSystemTrayIcon, QMenu, QComboBox,
                               QLineEdit, QGridLayout, QTableWidget, QAbstractItemView, QTableWidgetItem, QHeaderView,
                               QGroupBox, QSpacerItem, QDialog, QListWidget, QProgressDialog, QInputDialog)

GITHUB_VERSION_URL = "https://raw.githubusercontent.com/saeedmasoudie/pywarp/main/version.txt"
CURRENT_VERSION = "1.1.3"
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
            with requests.get(self.url, stream=True) as r:
                r.raise_for_status()
                total_length = int(r.headers.get('content-length', 0))
                downloaded = 0
                with open(local_filename, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if self._abort:
                            self.finished.emit(False, "")
                            return
                        f.write(chunk)
                        downloaded += len(chunk)
                        percent = int(downloaded * 100 / total_length)
                        self.progress.emit(percent)
            self.finished.emit(True, local_filename)
        except Exception:
            self.finished.emit(False, "")

class UpdateChecker(QObject):
    update_available = Signal(str)

    def check_for_update(self):
        latest_version = self.get_latest_version()
        if latest_version and latest_version != CURRENT_VERSION:
            self.update_available.emit(latest_version)

    def get_latest_version(self):
        try:
            response = requests.get(GITHUB_VERSION_URL, timeout=5)
            response.raise_for_status()
            latest_version = response.text.strip()

            if latest_version and latest_version.replace(".", "").isdigit():
                return latest_version
            else:
                print("Received invalid version format")
                return None
        except requests.exceptions.Timeout:
            print("Request timed out. Could not check for updates.")
        except requests.exceptions.RequestException as e:
            print(f"Network error: {e}")
        return None

class WarpStatusHandler(QThread):
    status_signal = Signal(str)

    def __init__(self, loop=True):
        super().__init__()
        self.looping = loop
        self.previous_status = None
        self.status_map = {
            "Connected": 8,
            "Disconnected": 8,
            "Connecting": 2
        }

    def run(self):
        asyncio.run(self.monitor_status())

    async def monitor_status(self):
        while self.looping:
            try:
                process = await asyncio.create_subprocess_exec(
                    'warp-cli', 'status',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    **safe_subprocess_args()
                )
                stdout, _ = await process.communicate()
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
        except ValueError:
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
        loop.run_until_complete(self.monitor_stats())

    async def monitor_stats(self):
        while True:
            if not self.warp_connected:
                print("Warp is disconnected. Waiting for connection...")
                self.stats_signal.emit([])
                while not self.warp_connected:
                    await asyncio.sleep(6)

            try:
                process = await asyncio.create_subprocess_exec(
                    'warp-cli', 'tunnel', 'stats',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                stdout, _ = await process.communicate()
                stats_output = stdout.decode().splitlines()

                if len(stats_output) < 6:
                    raise ValueError("Unexpected stats output format")

                protocol = stats_output[0].split(": ")[1].split(" ")[0]
                endpoints = stats_output[1].split(': ')[1]
                handshake_time = stats_output[2].split(': ')[1]
                sent = stats_output[3].split('; ')[0].split(':')[1].strip()
                received = stats_output[3].split('; ')[1].split(':')[1].strip()
                latency = stats_output[4].split(': ')[1]
                loss = stats_output[5].split(': ')[1]

                self.stats_signal.emit([protocol, endpoints, handshake_time, sent, received, latency, loss])

            except Exception as e:
                print(f"Error on getting stats: {e}")
            await asyncio.sleep(10)


class SettingsHandler(QThread):
    settings_signal = Signal(dict)

    def __init__(self, settings_file="settings.json", loop=True):
        super().__init__()
        self.looping = loop
        self.settings_file = settings_file
        self.settings = {}
        self.load_settings()

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.fetch_settings())

    async def fetch_settings(self):
        while True:
            try:
                self.settings["mode"] = await self.get_mode()
                self.settings_signal.emit(self.settings)

            except Exception as e:
                print(f"Error fetching settings: {e}")

            if not self.looping:
                break

            await asyncio.sleep(15)

    async def get_mode(self):
        try:
            process = await asyncio.create_subprocess_exec(
                "warp-cli", "settings",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **safe_subprocess_args()
            )
            stdout, _ = await process.communicate()
            for line in stdout.decode().splitlines():
                if "Mode:" in line:
                    return line.split(":")[1].strip()
        except Exception as e:
            print(f"Error fetching mode: {e}")
        return "Unknown"

    def load_settings(self):
        try:
            with open(self.settings_file, "r") as file:
                self.settings = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            self.settings = {}

    def save_settings(self):
        try:
            with open(self.settings_file, "w") as file:
                json.dump(self.settings, file, indent=4)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def get(self, key, default=None):
        return self.settings.get(key, default)

    def set(self, key, value):
        self.settings[key] = value
        self.save_settings()

class PowerButton(QWidget):
    toggled = Signal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(150, 150)
        palette = QApplication.palette()
        is_dark_mode = palette.color(QPalette.Window).lightness() < 128

        # Button styles
        self.button_styles = {
            "off": {
                "dark": "background-color: #222; border: 4px solid red; color: red;",
                "light": "background-color: #f0f2f5; border: 4px solid red; color: red;"
            },
            "unknown": {
                "dark": "background-color: #222; border: 4px solid orange; color: orange;",
                "light": "background-color: #f0f2f5; border: 4px solid orange; color: orange;"
            },
            "on": {
                "dark": "background-color: #222; border: 4px solid green; color: green;",
                "light": "background-color: #f0f2f5; border: 4px solid green; color: green;"
            }
        }

        self.theme = "dark" if is_dark_mode else "light"
        self.power_button = QPushButton("...", self)
        self.power_button.setGeometry(25, 25, 100, 100)
        self.power_button.setStyleSheet("")
        self.power_button.setFont(QFont("Arial", 16, QFont.Bold))
        self.glow_effect = QGraphicsDropShadowEffect()
        self.glow_effect.setBlurRadius(50)
        self.glow_effect.setColor(Qt.yellow)
        self.glow_effect.setOffset(0, 0)
        self.power_button.setGraphicsEffect(self.glow_effect)
        self.power_button.clicked.connect(self.toggle_power)
        self.state = 'disconnected'

    def toggle_power(self):
        if hasattr(self, '_toggle_lock') and self._toggle_lock:
            return
        self._toggle_lock = True

        def toggle():
            self.power_button.setDisabled(True)
            self.power_button.setText("...")
            self.power_button.setStyleSheet(
                self.button_styles['unknown'][self.theme] + "border-radius: 50px; font-size: 24px;")
            self.glow_effect.setColor(Qt.yellow)

            if self.state == "Disconnected":
                subprocess.run(['warp-cli', 'connect'], capture_output=True, **safe_subprocess_args())
                self.toggled.emit('Connecting')
            elif self.state == "Disconnecting" or self.state == "No Network":
                print(f"The action cannot be performed. (current state : {self.state})")
            else:
                subprocess.run(['warp-cli', 'disconnect'], capture_output=True, **safe_subprocess_args())
                self.toggled.emit('Disconnecting')

            self.power_button.setDisabled(False)
            self._toggle_lock = False

        threading.Thread(target=toggle, daemon=True).start()

    def update_button_state(self, state):
        states = {
            "Connected": {"state": "on", "text": "ON", "color": QColor("green")},
            "Disconnected": {"state": "off", "text": "OFF", "color": QColor("red")},
            "unknown": {"state": "unknown", "text": "...", "color": QColor("yellow")}
        }
        self.state = state
        selected_state = states.get(state, states["unknown"])

        self.power_button.setStyleSheet(
            self.button_styles[selected_state["state"]][self.theme] +
            "border-radius: 50px; font-size: 24px;"
        )
        self.power_button.setText(selected_state["text"])
        self.glow_effect.setColor(selected_state["color"])


class CustomTitleBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        palette = QApplication.palette()
        self.is_dark_mode = palette.color(QPalette.Window).lightness() < 128
        if self.is_dark_mode:
            self.background_color = "#34495e"
            self.background_color_hover = "#1abc9c"
        else:
            self.background_color = "#0078D4"
            self.background_color_hover = "#005A9E"

        title_layout = QHBoxLayout(self)
        title_layout.setContentsMargins(5, 0, 5, 0)

        self.icon_label = QLabel()
        self.icon_label.setPixmap(QIcon(":/logo.png").pixmap(35, 35))
        title_layout.addWidget(self.icon_label)
        self.app_name_label = QLabel("PyWarp")
        self.app_name_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-left: 5px;")
        title_layout.addWidget(self.app_name_label)

        # About Me
        self.about_button = QPushButton("About Me")
        self.about_button.setFixedHeight(30)
        self.about_button.setStyleSheet("""
            QPushButton {{
                background-color: {background_color};
                color: white;
                border: none;
                border-radius: 5px;
                padding: 5px 10px;
            }}
            QPushButton:hover {{
                background-color: {background_color_hover};
            }}
        """.format(background_color=self.background_color, background_color_hover=self.background_color_hover))
        self.about_button.clicked.connect(self.show_about)
        title_layout.addWidget(self.about_button)

        # Tutorials
        self.tutorials_button = QPushButton("Tutorials")
        self.tutorials_button.setFixedHeight(30)
        self.tutorials_button.setStyleSheet("""
            QPushButton {{
                background-color: {background_color};
                color: white;
                border: none;
                border-radius: 5px;
                padding: 5px 10px;
            }}
            QPushButton:hover {{
                background-color: {background_color_hover};
            }}
        """.format(background_color=self.background_color, background_color_hover=self.background_color_hover))
        self.tutorials_button.clicked.connect(self.show_tutorials)
        title_layout.addWidget(self.tutorials_button)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        title_layout.addWidget(spacer)

        # menu buttons
        self.minimize_button = QPushButton("-")
        self.style_button(self.minimize_button, f"background-color: {self.background_color};")
        self.minimize_button.clicked.connect(parent.showMinimized)
        title_layout.addWidget(self.minimize_button)

        self.maximize_button = QPushButton("□")
        self.style_button(self.maximize_button, f"background-color: {self.background_color};")
        self.maximize_button.clicked.connect(self.toggle_maximize_restore)
        title_layout.addWidget(self.maximize_button)

        self.close_button = QPushButton("×")
        self.style_button(self.close_button, "background-color: #e74c3c;")
        self.close_button.clicked.connect(self.confirm_close)
        title_layout.addWidget(self.close_button)

    def style_button(self, button, base_style):
        button.setFixedSize(30, 30)
        button.setStyleSheet(f"""
            {base_style}
            border-radius: 5px; color: white;
        """)
        button.setCursor(Qt.PointingHandCursor)
        button.installEventFilter(self)

    def toggle_maximize_restore(self):
        if self.parent().isMaximized():
            self.parent().showNormal()
        else:
            self.parent().showMaximized()

    def confirm_close(self):
        msg_box = QMessageBox(self.parent())
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setWindowTitle("Exit Confirmation")
        msg_box.setText("Do you want to close the app or hide it?")
        close_button = msg_box.addButton("Close", QMessageBox.AcceptRole)
        hide_button = msg_box.addButton("Hide", QMessageBox.RejectRole)
        msg_box.exec()
        if msg_box.clickedButton() == close_button:
            self.parent().close()
        elif msg_box.clickedButton() == hide_button:
            self.parent().hide()

    def show_about(self):
        about_dialog = QMessageBox(self)
        about_dialog.setWindowTitle("About Me")
        about_dialog.setText(
            "Hi, I'm Saeed/Eric, a Python developer passionate about creating efficient applications and constantly learning new things. "
            "You can explore my work on GitHub."
        )
        github_button = QPushButton("Visit GitHub")
        github_button.clicked.connect(lambda: webbrowser.open("https://github.com/saeedmasoudie"))
        about_dialog.addButton(github_button, QMessageBox.ActionRole)
        about_dialog.addButton("Close", QMessageBox.RejectRole)
        about_dialog.exec()

    def show_tutorials(self):
        title_color = "#1E90FF" if not self.is_dark_mode else "#87CEEB"
        text_color = "#333333" if not self.is_dark_mode else "#E0E0E0"
        warning_color = "#FF6347" if not self.is_dark_mode else "#FF4500"
        tutorials_dialog = QMessageBox(self)
        tutorials_dialog.setWindowTitle("PyWarp Tutorials")

        tutorials_dialog.setText(
            f"""
            <h2 style="color: {title_color}; text-align: center;">Welcome to PyWarp!</h2>
            <p style="font-size: 14px; color: {text_color};">This application allows you to manage Cloudflare Warp settings with ease. Here's how it works:</p>
            <ol style="font-size: 13px; color: {text_color};">
                <li><b>Modes:</b> Use the dropdown to select the Warp mode (e.g., warp, doh, proxy, etc.).</li>
                <li><b>DNS Mode:</b> Choose your preferred DNS filtering (off, family-friendly, or malware).</li>
                <li><b>Endpoint:</b> Set a custom endpoint for advanced configurations.</li>
                <li><b>Protocol:</b> You can choose your Protocol and try that connection.</li>
            </ol>
            <p style="font-size: 14px; color: {warning_color};"><b>⚠️ Important Warning:</b> Ensure Warp is disconnected before changing sensitive settings such as DNS mode or custom endpoint to avoid conflicts or errors.</p>
            <p style="text-align: center; font-size: 13px; color: {text_color};">Enjoy customizing your Warp experience!</p>
            """
        )
        tutorials_dialog.addButton("Close", QMessageBox.RejectRole)
        tutorials_dialog.exec()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            offset = event.globalPosition().toPoint() - self.drag_pos
            self.parent().move(self.parent().pos() + offset)
            self.drag_pos = event.globalPosition().toPoint()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Enter:
            obj.setStyleSheet("""
                background-color: {bg}; color: white; border-radius: 5px;
            """.format(bg=self.background_color_hover))
        elif event.type() == QEvent.Leave:
            if obj == self.minimize_button:
                obj.setStyleSheet(f"background-color: {self.background_color}; color: white; border-radius: 5px;")
            elif obj == self.maximize_button:
                obj.setStyleSheet(f"background-color: {self.background_color}; color: white; border-radius: 5px;")
            elif obj == self.close_button:
                obj.setStyleSheet("background-color: #e74c3c; color: white; border-radius: 5px;")
        return super().eventFilter(obj, event)


class ExclusionManager(QDialog):
    exclusions_updated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Exclusion")
        self.setFixedSize(300, 220)

        layout = QVBoxLayout(self)

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

    def is_valid_ip(self, value):
        try:
            ipaddress.ip_address(value)
            return True
        except ValueError:
            return False

    def is_valid_domain(self, value):
        return bool(re.match(r"^(?!-)[A-Za-z0-9-]+(\.[A-Za-z]{2,})+$", value))

    def add_item(self):
        value = self.input_field.text().strip()
        if not value:
            return

        exclusion_type = self.selector.currentText().lower()

        if exclusion_type == "ip" and not self.is_valid_ip(value):
            QMessageBox.warning(self, "Invalid Input", "Please enter a valid IP address.")
            return
        elif exclusion_type == "domain" and not self.is_valid_domain(value):
            QMessageBox.warning(self, "Invalid Input", "Please enter a valid domain name.")
            return

        cmd = ["warp-cli", "tunnel", "ip" if exclusion_type == "ip" else "host", "add", value]
        result = subprocess.run(cmd, capture_output=True, **safe_subprocess_args())

        if result.returncode == 0:
            self.exclusions_updated.emit()
            self.accept()
        else:
            QMessageBox.warning(self, "Error", f"Failed to add {exclusion_type}: {result.stderr.strip()}")


class AdvancedSettings(QDialog):
    def __init__(self, settings_handler, local_storage_file, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Advanced Settings")
        self.setStyleSheet(self.get_stylesheet())
        self.setFixedSize(460, 460)

        self.settings_handler = settings_handler
        self.storage_path = local_storage_file
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

        self.endpoint_input = QLineEdit()
        self.endpoint_input.setPlaceholderText("Set Custom Endpoint")
        self.endpoint_input.setText(self.current_endpoint)

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

    def update_list_view(self):
        self.item_list.clear()
        cmd = ["warp-cli", "tunnel", "ip", "list"]
        result_ip = subprocess.run(cmd, capture_output=True, text=True, **safe_subprocess_args())

        cmd = ["warp-cli", "tunnel", "host", "list"]
        result_host = subprocess.run(cmd, capture_output=True, text=True, **safe_subprocess_args())

        if result_ip.returncode == 0:
            lines = result_ip.stdout.strip().splitlines()
            for line in lines[1:]:
                self.item_list.addItem(f"IP: {line.strip()}")

        if result_host.returncode == 0:
            lines = result_host.stdout.strip().splitlines()
            for line in lines[1:]:
                self.item_list.addItem(f"Domain: {line.strip()}")

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
        value_cleaned = " ".join(item_text[1].split(" ")[:-2]).strip()
        current_exclusions = self.get_exclusion_list(mode)

        if any(value_cleaned in item for item in current_exclusions):
            cmd = ["warp-cli", "tunnel", "ip" if mode == "ip" else "host", "remove", value_cleaned]
            result = subprocess.run(cmd, capture_output=True, text=True, **safe_subprocess_args())

            if result.returncode == 0:
                self.update_list_view()
            else:
                QMessageBox.warning(self, "Error", f"Failed to remove {mode}: {result.stderr.strip()}")
        else:
            QMessageBox.warning(self, "Error", f"{value_cleaned} not found in exclusion list!")
            return


    def get_exclusion_list(self, mode):
        cmd = ["warp-cli", "tunnel", "ip" if mode == "ip" else "host", "list"]
        result = subprocess.run(cmd, capture_output=True, text=True, **safe_subprocess_args())

        if result.returncode == 0:
            lines = result.stdout.strip().splitlines()
            return [f"Domain: {line.strip()}" if mode == "domain" else f"IP: {line.strip()}" for line in lines[1:]]

        return []

    def reset_list(self):
        cmd = ["warp-cli", "tunnel", "ip", "reset"]
        subprocess.run(cmd, **safe_subprocess_args())

        cmd = ["warp-cli", "tunnel", "host", "reset"]
        subprocess.run(cmd, **safe_subprocess_args())
        self.update_list_view()

    def save_endpoint(self):
        endpoint = self.endpoint_input.text().strip()
        if not endpoint:
            return

        try:
            result = subprocess.run(
                ["warp-cli", "tunnel", "endpoint", "set", endpoint],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                **safe_subprocess_args()
            )

            stderr = result.stderr.decode("utf-8").strip()
            if result.returncode != 0:
                error_line = stderr.split("\n")[0]
                QMessageBox.warning(self, "Error", error_line)
                return

            self.settings_handler.set("custom_endpoint", endpoint)
            QMessageBox.information(self, "Saved", "Endpoint saved successfully.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"An exception occurred: {str(e)}")

    def reset_endpoint(self):
        subprocess.run(["warp-cli", "tunnel", "endpoint", "reset"], **safe_subprocess_args())
        self.settings_handler.set("custom_endpoint", "")
        self.endpoint_input.clear()
        QMessageBox.information(self, "Reset", "Endpoint reset successfully.")

    def get_stylesheet(self):
        palette = self.palette()
        is_dark_mode = palette.color(QPalette.Window).lightness() < 128
        fg_color = "#E0E0E0" if is_dark_mode else "#333"
        bg_color = "#1E1E1E" if is_dark_mode else "white"
        input_bg_color = "#333333" if is_dark_mode else "#f0f0f0"
        background_color = "#34495e" if is_dark_mode else "#0078D4"
        background_color_hover = "#1abc9c" if is_dark_mode else "#005A9E"

        return f"""
            QDialog {{
                background-color: {bg_color};
                color: {fg_color};
                border-radius: 5px;
            }}

            QGroupBox {{
                border: 1px solid {background_color};
                padding: 10px;
                font-weight: bold;
            }}
            
            QComboBox {{
                background-color: {input_bg_color};
                color: {fg_color};
                border: 1px solid #555;
                border-radius: 5px;
                padding: 5px;
            }}

            QListWidget {{
                background-color: {input_bg_color};
                color: {fg_color};
                border: 1px solid #555;
                font-size: 14px;
            }}

            QLineEdit {{
                background-color: {input_bg_color};
                color: {fg_color};
                border: 1px solid #777;
                padding: 6px;
            }}

            QPushButton {{
                background-color: {background_color};
                color: white;
                padding: 6px;
                border-radius: 4px;
            }}

            QPushButton:hover {{
                background-color: {background_color_hover};
            }}
        """


class SettingsPage(QWidget):
    def __init__(self, parent=None, warp_status_handler=None, settings_handler=None):
        super().__init__(parent)
        self.settings_handler = SettingsHandler()
        self.warp_status_handler = warp_status_handler

        writable_path = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
        os.makedirs(writable_path, exist_ok=True)
        self.local_storage_file = os.path.join(writable_path, "settings.json")

        if not os.path.exists(self.local_storage_file):
            self.copy_settings_file()

        self.current_status = "Disconnected"
        self.current_endpoint = ""
        self.current_dns_mode = ""
        self.current_mode = ""

        self.load_local_settings()
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
        self.dns_dropdown.addItems(["off", "Block Adult-Content", "Block malware"])
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
        dialog = AdvancedSettings(self.settings_handler, "settings.json", self)
        dialog.exec()

    def create_groupbox(self, title):
        groupbox = QGroupBox(title)
        groupbox.setStyleSheet(self.get_stylesheet())
        return groupbox

    def copy_settings_file(self):
        writable_path = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
        os.makedirs(writable_path, exist_ok=True)
        default_settings = {"endpoint": "", "dns_mode": "off", "mode": "warp"}
        with open(self.local_storage_file, "w") as file:
            json.dump(default_settings, file)

    def load_local_settings(self):
        if os.path.exists(self.local_storage_file):
            try:
                with open(self.local_storage_file, "r") as file:
                    data = json.load(file)
                    self.current_endpoint = data.get("endpoint", "")
                    self.current_dns_mode = data.get("dns_mode", "off")
                    self.current_mode = data.get("mode", "warp")
            except Exception as e:
                print(f"Error loading settings: {e}")
        else:
            self.current_dns_mode = "off"

    def save_local_settings(self):
        data = {"endpoint": self.current_endpoint, "dns_mode": self.current_dns_mode, "mode": self.current_mode}
        with open(self.local_storage_file, "w") as file:
            json.dump(data, file)

    def set_dns_mode(self):
        dns_dict = {
            "off": "off", "Block Adult-Content": "full", "Block malware": "malware"
        }
        selected_dns = self.dns_dropdown.currentText()
        cmd = subprocess.run(["warp-cli", "dns", "families", dns_dict.get(selected_dns, 'off')], **safe_subprocess_args())
        if cmd.returncode == 0:
            self.current_dns_mode = selected_dns
            self.save_local_settings()
            QMessageBox.information(self, "DNS Mode Saved", f"DNS mode set to: {selected_dns}")
        else:
            QMessageBox.warning(self, "Error", f"Failed to Set DNS Mode to {selected_dns}: {cmd.stderr.strip()}")

    def set_mode(self):
        selected_mode = self.modes_dropdown.currentText()

        if selected_mode == "proxy":
            port_str, ok = QInputDialog.getText(
                self,
                "Proxy Port Required",
                "Enter proxy port (1–65535):"
            )

            if not ok:
                self.modes_dropdown.setCurrentText(self.current_mode)
                return

            try:
                port = int(port_str)
                if not (1 <= port <= 65535):
                    raise ValueError
            except ValueError:
                QMessageBox.warning(self, "Invalid Port", "Please enter a valid port number between 1 and 65535.")
                self.modes_dropdown.setCurrentText(self.current_mode)
                return

            set_port_cmd = subprocess.run(
                ["warp-cli", "set-proxy-port", str(port)],
                **safe_subprocess_args()
            )
            if set_port_cmd.returncode != 0:
                QMessageBox.warning(
                    self,
                    "Port Set Failed",
                    f"Failed to set proxy port:\n{set_port_cmd.stderr.strip()}"
                )
                self.modes_dropdown.setCurrentText(self.current_mode)
                return

        cmd = subprocess.run(["warp-cli", "mode", selected_mode], **safe_subprocess_args())
        if cmd.returncode == 0:
            self.current_mode = selected_mode
            self.save_local_settings()
            QMessageBox.information(self, "Mode Changed", f"Mode set to: {selected_mode}")
        else:
            QMessageBox.warning(self, "Error", f"Failed to set mode to {selected_mode}:\n{cmd.stderr.strip()}")
            self.modes_dropdown.setCurrentText(self.current_mode)

    def get_stylesheet(self):
        palette = QApplication.palette()
        is_dark_mode = palette.color(QPalette.Window).lightness() < 128

        fg_color = "#E0E0E0" if is_dark_mode else "#333"
        bg_color = "#1E1E1E" if is_dark_mode else "white"
        input_bg_color = "#333333" if is_dark_mode else "#f0f0f0"
        button_bg = "#34495e" if is_dark_mode else "#0078D4"
        button_hover_bg = "#1abc9c" if is_dark_mode else "#005A9E"

        return f"""
            QWidget {{
                background-color: {bg_color};
                color: {fg_color};
                padding: 15px;
                border-radius: 8px;
            }}

            QGroupBox {{
                font-size: 18px;
                font-weight: bold;
                color: {fg_color};
                border: 1px solid {button_bg};
                border-radius: 8px;
                padding: 6px;
            }}

            QComboBox {{
                background-color: {input_bg_color};
                color: {fg_color};
                border: 1px solid {fg_color};
                border-radius: 5px;
                padding: 5px;
            }}

            QLineEdit {{
                background-color: {input_bg_color};
                color: {fg_color};
                border: 1px solid {fg_color};
                border-radius: 5px;
                padding: 5px;
            }}

            QPushButton {{
                background-color: {button_bg};
                color: white;
                border-radius: 5px;
                padding: 5px 10px;
                transition: 0.3s;
            }}

            QPushButton:hover {{
                background-color: {button_hover_bg};
            }}
        """


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyWarp")
        self.setWindowIcon(QIcon(":/logo.png"))
        self.setGeometry(100, 100, 400, 600)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.title_bar = CustomTitleBar(self)
        self.setMenuWidget(self.title_bar)
        self.setup_tray()
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)
        palette = QApplication.palette()
        self.is_dark_mode = palette.color(QPalette.Window).lightness() < 128

        status_frame = QFrame()
        status_frame.setObjectName("statusFrame")
        status_layout = QHBoxLayout(status_frame)
        status_layout.setSpacing(10)

        self.toggle_switch = PowerButton()
        self.toggle_switch.toggled.connect(self.update_status)

        status_layout.addWidget(self.toggle_switch)
        status_info = QVBoxLayout()
        status_info.setAlignment(Qt.AlignRight)

        self.status_label = QLabel("Status: Disconnected")
        self.status_label.setFont(QFont("Segoe UI", 12))
        self.ip_label = QLabel(f"IPv4: 0.0.0.0")
        self.ip_label.setFont(QFont("Segoe UI", 12))
        self.ip_label.setToolTip("This is your current public IP address.")
        self.protocol_label = QLabel(f"Protocol: ---")
        current_protocol = get_current_protocol()
        self.protocol_label.setText(
            f"Protocol: <span style='color: #0078D4; font-weight: bold;'>{current_protocol}</span>")
        self.version_label = QLabel(f"Version: {CURRENT_VERSION}")
        self.version_label.setText(
            f"Version: <span style='color: #0078D4; font-weight: bold;'>{CURRENT_VERSION}</span>")

        status_info.addWidget(self.status_label)
        status_info.addWidget(self.ip_label)
        status_info.addWidget(self.protocol_label)
        status_info.addWidget(self.version_label)

        status_layout.addLayout(status_info)
        main_layout.addWidget(status_frame)

        button_layout = QHBoxLayout()
        self.stacked_widget = QStackedWidget()
        self.buttons = {}

        stats_widget = QWidget()
        stats_layout = QVBoxLayout(stats_widget)

        self.stats_table = QTableWidget(8, 2)
        self.stats_table.setHorizontalHeaderLabels(["Metric", "Value"])
        self.stats_table.verticalHeader().setVisible(False)
        self.stats_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.stats_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.stats_table.setStyleSheet("""
            QTableWidget {
                font-family: 'Segoe UI';
                font-size: 12pt;
                font-weight: normal;
            }
        """)

        stats_labels = [
            "Protocol", "IPv4 Endpoint", "IPv6 Endpoint",
            "Last Handshake", "Sent Data", "Received Data", "Latency", "Loss"
        ]
        for i, label in enumerate(stats_labels):
            self.stats_table.setItem(i, 0, QTableWidgetItem(label))

        stats_layout.addWidget(self.stats_table)
        self.stacked_widget.addWidget(stats_widget)

        self.settings_handler = SettingsHandler(loop=True)
        self.settings_handler.start()
        settings_widget = SettingsPage(settings_handler=self.settings_handler)
        self.stacked_widget.addWidget(settings_widget)

        for idx, btn_text in enumerate(["Network Stats", "Settings", "Protocol"]):
            btn = QPushButton(btn_text)
            btn.setMinimumHeight(40)
            if btn_text != "Protocol":
                btn.clicked.connect(
                    lambda _, i=idx: (self.stacked_widget.setCurrentIndex(i), self.update_button_styles()))
            else:
                btn.clicked.connect(lambda _: (self.set_protocol(), self.update_button_styles()))
            self.buttons[btn_text] = btn
            button_layout.addWidget(btn)
        self.update_button_styles()

        main_layout.addLayout(button_layout)
        main_layout.addWidget(self.stacked_widget)

        # status checker
        self.status_checker = WarpStatusHandler(loop=True)
        self.status_checker.status_signal.connect(self.update_status)
        self.status_checker.start()

        # stats Checker
        self.stats_checker = WarpStatsHandler(self.status_checker, loop=True)
        self.stats_checker.stats_signal.connect(self.update_stats_display)
        self.stats_checker.start()

        self.setStyleSheet(self.get_styles())


    def setup_tray(self):
        self.tray_icon = QSystemTrayIcon(QIcon(":/logo.png"), self)
        self.tray_icon.setToolTip("PyWarp - Advanced Cloudflare Warp")
        tray_menu = QMenu(self)

        show_action = QAction("Show App", self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        tray_menu.addAction(exit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.tray_icon.show()

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.show()
            self.activateWindow()

    def update_stats_display(self, stats_list):
        if not stats_list:
            for row in range(8):
                self.stats_table.setItem(row, 1, QTableWidgetItem(""))
            return

        protocol, endpoints, handshake_time, sent, received, latency, loss = stats_list

        handshake_time_cleaned = handshake_time.replace('s', '')
        handshake_value = int(handshake_time_cleaned) if handshake_time_cleaned.isdigit() else 0
        formatted_handshake = format_handshake_time(handshake_value)
        handshake_item = QTableWidgetItem(formatted_handshake)
        if handshake_value < 1800:
            handshake_item.setForeground(QBrush(QColor("green")))
        elif handshake_value < 3600:
            handshake_item.setForeground(QBrush(QColor("orange")))
        else:
            handshake_item.setForeground(QBrush(QColor("red")))

        endpoints_value = endpoints.split(',')
        ipv4 = endpoints_value[0]
        ipv6 = endpoints_value[1] if len(endpoints_value) > 1 and len(endpoints_value[1]) > 5 else 'Not Available'

        latency_value = int(latency.replace("ms", "").strip())
        latency_item = QTableWidgetItem(f"{latency_value} ms")

        if latency_value < 100:
            latency_item.setForeground(QBrush(QColor("green")))
        elif latency_value < 200:
            latency_item.setForeground(QBrush(QColor("orange")))
        else:
            latency_item.setForeground(QBrush(QColor("red")))

        loss_value = float(loss.split(";")[0].replace("%", "").strip())
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

    def update_status(self, is_connected):
        if is_connected == 'Connected':
            self.status_label.setText("Status: <span style='color: green; font-weight: bold;'>Connected</span>")
            self.ip_label.setText("IPv4: <span style='color: #0078D4; font-weight: bold;'>Receiving...</span>")
            get_global_ip_async(lambda ip: self.ip_label.setText(
                f"IPv4: <span style='color: #0078D4; font-weight: bold;'>{ip}</span>"
            ))
        elif is_connected == 'Disconnected':
            self.status_label.setText("Status: <span style='color: red; font-weight: bold;'>Disconnected</span>")
            self.ip_label.setText("IPv4: <span style='color: #0078D4; font-weight: bold;'>Receiving...</span>")
            get_global_ip_async(lambda ip: self.ip_label.setText(
                f"IPv4: <span style='color: #0078D4; font-weight: bold;'>{ip}</span>"
            ))
        elif is_connected == 'Connecting':
            self.status_label.setText("Status: <span style='color: orange; font-weight: bold;'>Connecting...</span>")
            self.ip_label.setText("IPv4: <span style='color: #0078D4; font-weight: bold;'>Receiving...</span>")
        elif is_connected == 'Disconnecting':
            self.status_label.setText("Status: <span style='color: orange; font-weight: bold;'>Disconnecting...</span>")
            self.ip_label.setText("IPv4: <span style='color: #0078D4; font-weight: bold;'>Receiving...</span>")
        elif is_connected == 'No Network':
            self.status_label.setText("Status: <span style='color: orange; font-weight: bold;'>No Network</span>")
            self.ip_label.setText("IPv4: <span style='color: #0078D4; font-weight: bold;'>Not Available</span>")
            self.show_critical_error("Failed to Connect", "No active internet connection detected. Please check your network settings.")
        else:
            self.status_label.setText(f"Status: <span style='color: red; font-weight: bold;'>Network Error</span>")
            self.ip_label.setText("IPv4: <span style='color: #0078D4; font-weight: bold;'>Not Available</span>")
            self.show_critical_error("Failed to Connect", is_connected)
            is_connected = 'unknown'

        self.toggle_switch.update_button_state(is_connected)

    def show_critical_error(self, title, message):
        self.activateWindow()
        self.raise_()
        QMessageBox.critical(self, title, message)

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
                QMainWindow { background-color: #121212; }
                #statusFrame { background-color: #1E1E1E; border-radius: 12px; padding: 15px; }
                QPushButton { background-color: #34495e; color: white; padding: 12px; border-radius: 8px; }
                QPushButton:hover { background-color: #1abc9c; }
                QPushButton[active="true"] { background-color: #1abc9c; }
                QLabel { font-size: 15px; color: #E0E0E0; }
                QStackedWidget { background-color: #1E1E1E; border-radius: 12px; padding: 20px; }
            """
        else:
            return """
                QMainWindow { background-color: #f0f2f5; }
                #statusFrame { background-color: white; border-radius: 12px; padding: 15px; }
                QPushButton { background-color: #0078D4; color: white; padding: 12px; border-radius: 8px; }
                QPushButton:hover { background-color: #005A9E; }
                QPushButton[active="true"] { background-color: #005A9E; }
                QLabel { font-size: 15px; color: #333; }
                QStackedWidget { background-color: white; border-radius: 12px; padding: 20px; }
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
            message_bg_color="#222222" if self.is_dark_mode else "#FFFFFF"
        )
        dlg.setStyleSheet(base_styles + dialog_styles)

        custom_button1 = dlg.addButton("WireGuard", QMessageBox.ActionRole)
        custom_button2 = dlg.addButton("MASQUE", QMessageBox.ActionRole)
        cancel_button = dlg.addButton(QMessageBox.Cancel)
        dlg.exec()

        if dlg.clickedButton() == custom_button1:
            self.set_warp_protocol("WireGuard")
        elif dlg.clickedButton() == custom_button2:
            self.set_warp_protocol("MASQUE")
        elif dlg.clickedButton() == cancel_button:
            print("Operation canceled.")

    def set_warp_protocol(self, protocol):
        try:
            subprocess.run(['warp-cli', 'tunnel', 'protocol', 'set', protocol], check=True, **safe_subprocess_args())
            QMessageBox.information(self, "Protocol Changed", f"Protocol successfully changed to {protocol}.")
            self.protocol_label.setText(
                f"Protocol: <span style='color: #0078D4; font-weight: bold;'>{protocol}</span>")
        except subprocess.CalledProcessError as e:
            error_message = f"Failed to set protocol: {str(e)}"
            QMessageBox.critical(self, "Error", error_message)


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
                subprocess.run(["msiexec", "/i", file_path, "/quiet", "/norestart"], check=True)
            elif os_name == "Darwin":
                subprocess.run(["open", file_path], check=True)
            else:
                QMessageBox.critical(self.parent, "Unsupported", "Automatic install not supported for this OS.")
                sys.exit()

            self.register_and_activate_warp()

        except subprocess.CalledProcessError:
            QMessageBox.critical(self.parent, "Installation Failed", "Failed to install Warp.")
            self.show_install_prompt()

    def install_linux_package(self):
        msg_box = QMessageBox(self.parent)
        msg_box.setWindowTitle("Linux Installation")
        msg_box.setText(
            "Warp will be installed via your system's package manager.\n\nDo you want to proceed?"
        )
        install_button = msg_box.addButton("Install", QMessageBox.AcceptRole)
        cancel_button = msg_box.addButton(QMessageBox.Cancel)
        msg_box.exec()

        if msg_box.clickedButton() == install_button:
            try:
                package_manager = self.detect_linux_package_manager()
                if package_manager == "apt":
                    subprocess.run(["sudo", "apt", "update"], check=True)
                    subprocess.run([
                        "sudo", "apt", "install", "-y",
                        "curl", "gpg", "lsb-release", "apt-transport-https",
                        "ca-certificates", "sudo"
                    ], check=True)
                    subprocess.run([
                        "bash", "-c",
                        'curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | '
                        'gpg --dearmor --yes -o /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg'
                    ], check=True)
                    distro = subprocess.check_output(["lsb_release", "-cs"]).decode().strip()
                    subprocess.run([
                        "bash", "-c",
                        f'echo "deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] '
                        f'https://pkg.cloudflareclient.com/ {distro} main" | '
                        f'sudo tee /etc/apt/sources.list.d/cloudflare-client.list'
                    ], check=True)
                    subprocess.run(["sudo", "apt", "update"], check=True)
                    subprocess.run(["sudo", "apt", "install", "-y", "cloudflare-warp"], check=True)

                elif package_manager == "yum":
                    subprocess.run([
                        "bash", "-c",
                        'curl -fsSL https://pkg.cloudflareclient.com/cloudflare-warp-ascii.repo | '
                        'sudo tee /etc/yum.repos.d/cloudflare-warp.repo'
                    ], check=True)
                    subprocess.run(["sudo", "yum", "check-update"], check=True)
                    subprocess.run(["sudo", "yum", "install", "-y", "curl", "sudo", "coreutils"], check=True)
                    subprocess.run(["sudo", "yum", "check-update"], check=True)
                    subprocess.run(["sudo", "yum", "install", "-y", "cloudflare-warp"], check=True)

                else:
                    QMessageBox.critical(self.parent, "Unsupported", "Unsupported package manager for auto install.")
                    sys.exit()

                self.register_and_activate_warp()

            except subprocess.CalledProcessError as e:
                QMessageBox.critical(self.parent, "Installation Failed", f"An error occurred:\n{e}")
                self.show_install_prompt()
        else:
            sys.exit()

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
            subprocess.run(["warp-cli", "register"], check=True)
            QMessageBox.information(self.parent, "Warp Ready", "Warp has been registered successfully!")
        except subprocess.CalledProcessError:
            QMessageBox.critical(self.parent, "Warp Activation Failed", "Failed to register Warp.")

def format_handshake_time(seconds):
    hours, remainder = divmod(seconds, 3600)
    mins, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {mins}m {secs}s"
    elif mins:
        return f"{mins}m {secs}s"
    else:
        return f"{secs}s"

def get_global_ip_async(callback):
    def fetch_ip():
        try:
            response = requests.get('https://api.ipify.org', params={'format': 'json'}, timeout=5)
            ip = response.json().get('ip', 'Unavailable')
        except requests.RequestException as e:
            ip = 'Unavailable'
            print(f"Failed to fetch global IP: {e}")
        callback(ip)

    thread = threading.Thread(target=fetch_ip, daemon=True)
    thread.start()

def get_current_protocol():
    try:
        process = subprocess.Popen(['warp-cli', 'settings'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, **safe_subprocess_args())
        stdout, _ = process.communicate()
        output = stdout.decode()

        for line in output.splitlines():
            if "WARP tunnel protocol:" in line:
                return line.split(":")[1].strip()
        return "Unknown"
    except Exception as e:
        print(f"Error fetching current protocol: {e}")
        return "Error"

def handle_exception(exc_type, exc_value, exc_traceback):
    error_dialog = QMessageBox()
    error_dialog.setIcon(QMessageBox.Critical)
    error_dialog.setWindowTitle("Application Error")
    error_dialog.setText("An unexpected error occurred!")
    error_dialog.setDetailedText("".join(traceback.format_exception(exc_type, exc_value, exc_traceback)))
    error_dialog.exec()

def disconnect_on_exit():
    server.removeServer(SERVER_NAME)
    try:
        subprocess.run(["warp-cli", "disconnect"], capture_output=True, **safe_subprocess_args())
        print("Warp disconnected successfully.")
    except Exception as e:
        print(f"Failed to disconnect Warp: {e}")

def safe_subprocess_args():
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if platform.system() == "Windows" else {}

def notify_update(latest_version):
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
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if socket.waitForConnected(500):
        sys.exit(1)

if __name__ == "__main__":
    check_existing_instance()
    app = QApplication(sys.argv)
    server.listen(SERVER_NAME)
    atexit.register(disconnect_on_exit)
    app.setWindowIcon(QIcon(":/logo.png"))
    sys.excepthook = handle_exception

    installer = WarpInstaller(parent=None)
    if not installer.is_warp_installed():
        installer.show_install_prompt()
        if not installer.is_warp_installed():
            QMessageBox.critical(None, "Warp Installation Failed", "Warp could not be installed.\nExiting app.")
            sys.exit()

    app.setFont(QFont("Arial", 10))
    window = MainWindow()
    window.show()

    update_checker = UpdateChecker()
    update_checker.update_available.connect(notify_update)
    update_thread = threading.Thread(target=update_checker.check_for_update, daemon=True)
    update_thread.start()

    sys.exit(app.exec())
