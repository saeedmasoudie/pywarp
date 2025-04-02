import asyncio
import atexit
import json
import os
import platform
import requests
import shutil
import subprocess
import sys
import threading
import traceback
import webbrowser
import resources_rc

from PySide6.QtCore import Qt, QThread, Signal, QEvent, QStandardPaths, QFile
from PySide6.QtGui import QFont, QPalette, QIcon, QAction, QColor
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QPushButton, QLabel, QFrame, QStackedWidget,
                               QGraphicsDropShadowEffect, QMessageBox, QSizePolicy, QSystemTrayIcon, QMenu, QComboBox,
                               QLineEdit, QGridLayout)


class WarpStatusHandler(QThread):
    status_signal = Signal(str)
    def __init__(self, loop=False):
        super().__init__()
        self.looping = loop
        self.last_status = None

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.monitor_status())

    async def monitor_status(self):
        while True:
            try:
                process = await asyncio.create_subprocess_exec(
                    'warp-cli', 'status',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                stdout, _ = await process.communicate()
                status = stdout.decode()

                if 'Connected' in status:
                    current_status = 'Connected'
                elif 'Disconnected' in status:
                    current_status = 'Disconnected'
                else:
                    data = status.split()
                    try:
                        reason_index = data.index("Reason:")
                        current_status = " ".join(data[reason_index + 1:]).lower()
                    except ValueError:
                        current_status = 'Fetching'

                if current_status != self.last_status:
                    self.last_status = current_status
                    self.status_signal.emit(current_status)

            except Exception as e:
                print(f"Error checking Warp status: {e}")
                self.status_signal.emit('Fetching')

            if not self.looping:
                break

            await asyncio.sleep(8)

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
                while not self.warp_connected:
                    await asyncio.sleep(2)

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
            await asyncio.sleep(15)


class SettingsHandler(QThread):
    settings_signal = Signal(dict)

    def __init__(self, loop=True):
        super().__init__()
        self.looping = loop

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.fetch_settings())

    async def fetch_settings(self):
        while True:
            settings = {}
            try:
                settings["mode"] = await self.get_mode()
                self.settings_signal.emit(settings)
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
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            stdout, _ = await process.communicate()
            for line in stdout.decode().splitlines():
                if "Mode:" in line:
                    return line.split(":")[1].strip()
        except Exception as e:
            print(f"Error fetching mode: {e}")
        return "Unknown"

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
            "connect": {
                "dark": "background-color: #222; border: 4px solid orange; color: orange;",
                "light": "background-color: #f0f2f5; border: 4px solid orange; color: orange;"
            },
            "on": {
                "dark": "background-color: #222; border: 4px solid green; color: green;",
                "light": "background-color: #f0f2f5; border: 4px solid green; color: green;"
            }
        }

        self.theme = "dark" if is_dark_mode else "light"

        # Power Button
        self.power_button = QPushButton("...", self)
        self.power_button.setGeometry(25, 25, 100, 100)
        self.power_button.setStyleSheet(self.button_styles["connect"][self.theme] + "border-radius: 50px; font-size: 24px;")
        self.power_button.setFont(QFont("Arial", 16, QFont.Bold))

        # Glow Effect
        self.glow_effect = QGraphicsDropShadowEffect()
        self.glow_effect.setBlurRadius(50)
        self.glow_effect.setColor(Qt.yellow)
        self.glow_effect.setOffset(0, 0)
        self.power_button.setGraphicsEffect(self.glow_effect)

        # Button Click Event
        self.power_button.clicked.connect(self.toggle_power)
        self.is_on = False

    def toggle_power(self):
        def toggle():
            self.power_button.setText("...")
            self.power_button.setStyleSheet(
                self.button_styles['connect'][self.theme] + "border-radius: 50px; font-size: 24px;")
            self.glow_effect.setColor(Qt.yellow)
            if self.is_on:
                subprocess.run(['warp-cli', 'disconnect'], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                self.toggled.emit('Disconnecting...')
            else:
                subprocess.run(['warp-cli', 'connect'], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                self.toggled.emit('Connecting...')

        threading.Thread(target=toggle, daemon=True).start()

    def update_button_state(self, is_on):
        states = {
            True: {"state": "on", "text": "ON", "color": QColor("green")},
            False: {"state": "off", "text": "OFF", "color": QColor("red")},
            "connect": {"state": "connect", "text": "...", "color": QColor("yellow")}
        }

        if isinstance(is_on, bool):
            selected_state = states[is_on]
            self.is_on = is_on
        else:
            selected_state = states["connect"]
            self.is_on = True

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

class SettingsPage(QWidget):
    def __init__(self, parent=None, warp_status_handler=None, settings_handler=None):
        super().__init__(parent)
        self.settings_handler = settings_handler
        self.warp_status_handler = warp_status_handler
        # Define writable path for local storage
        writable_path = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
        os.makedirs(writable_path, exist_ok=True)  # Ensure the directory exists
        self.local_storage_file = os.path.join(writable_path, "settings.json")

        if not os.path.exists(self.local_storage_file):
            self.copy_settings_file()

        self.current_status = "Disconnected"
        self.current_endpoint = ""
        self.current_dns_mode = ""

        self.load_local_settings()
        layout = QGridLayout(self)

        palette = QApplication.palette()
        is_dark_mode = palette.color(QPalette.Window).lightness() < 128
        fg_color = "#E0E0E0" if is_dark_mode else "#333"
        bg_color = "#1E1E1E" if is_dark_mode else "white"
        input_bg_color = "#333333" if is_dark_mode else "#f0f0f0"

        modes_label = QLabel("Modes:")
        modes_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {fg_color};")
        layout.addWidget(modes_label, 0, 0, 1, 2)

        self.modes_dropdown = QComboBox()
        self.modes_dropdown.addItems(["warp", "doh", "warp+doh", "dot", "warp+dot", "proxy", "tunnel_only"])
        self.style_dropdown(self.modes_dropdown, fg_color, input_bg_color)
        self.modes_dropdown.currentTextChanged.connect(self.set_mode)
        layout.addWidget(self.modes_dropdown, 1, 0, 1, 2)

        dns_label = QLabel("DNS Mode:")
        dns_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {fg_color};")
        layout.addWidget(dns_label, 2, 0, 1, 2)

        self.dns_dropdown = QComboBox()
        self.dns_dropdown.addItems(["off", "family-friendly", "malware"])
        self.dns_dropdown.setCurrentText(self.current_dns_mode)
        self.style_dropdown(self.dns_dropdown, fg_color, input_bg_color)
        self.dns_dropdown.currentTextChanged.connect(self.set_dns_mode)
        layout.addWidget(self.dns_dropdown, 3, 0, 1, 2)

        endpoint_label = QLabel("Custom Endpoint:")
        endpoint_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {fg_color};")
        layout.addWidget(endpoint_label, 4, 0)

        self.endpoint_input = QLineEdit()
        self.endpoint_input.setPlaceholderText("Enter endpoint")
        self.endpoint_input.setText(self.current_endpoint)
        self.endpoint_input.setStyleSheet(f"""
            background-color: {input_bg_color};
            color: {fg_color};
            border: 1px solid {fg_color};
            border-radius: 5px;
            padding: 5px;
        """)
        layout.addWidget(self.endpoint_input, 5, 0, 1, 2)

        endpoint_submit_button = QPushButton("Submit")
        endpoint_submit_button.setStyleSheet(f"""
            QPushButton {{
                background-color: #0078D4;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 5px 10px;
            }}
            QPushButton:hover {{
                background-color: #005A9E;
            }}
        """)
        endpoint_submit_button.clicked.connect(self.set_endpoint)
        layout.addWidget(endpoint_submit_button, 5, 2)

        endpoint_reset_button = QPushButton("Reset")
        endpoint_reset_button.setStyleSheet(f"""
            QPushButton {{
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 5px 10px;
            }}
            QPushButton:hover {{
                background-color: #c0392b;
            }}
        """)
        endpoint_reset_button.clicked.connect(self.reset_endpoint)
        layout.addWidget(endpoint_reset_button, 5, 3)

        self.setStyleSheet(f"background-color: {bg_color}; padding: 15px; border-radius: 8px;")
        self.setLayout(layout)

        if self.settings_handler:
            self.settings_handler.settings_signal.connect(self.update_inputs)

        if self.warp_status_handler:
            self.warp_status_handler.status_signal.connect(self.update_status)

    def copy_settings_file(self):
        resource_file = QFile(":/settings.json")
        if resource_file.open(QFile.ReadOnly | QFile.Text):
            with open(self.local_storage_file, "w") as file:
                file.write(resource_file.readAll().data().decode())
        else:
            print("Failed to open settings.json from resources.")

    def load_local_settings(self):
        if os.path.exists(self.local_storage_file):
            try:
                with open(self.local_storage_file, "r") as file:
                    data = json.load(file)
                    self.current_endpoint = data.get("endpoint", "")
                    self.current_dns_mode = data.get("dns_mode", "off")
            except Exception as e:
                print(f"Error loading settings: {e}")
        else:
            self.current_dns_mode = "off"

    def save_local_settings(self):
        data = {
            "endpoint": self.current_endpoint,
            "dns_mode": self.current_dns_mode
        }
        with open(self.local_storage_file, "w") as file:
            json.dump(data, file)

    def set_endpoint(self):
        endpoint = self.endpoint_input.text()
        if endpoint.strip():
            self.current_endpoint = endpoint
            self.save_local_settings()
            QMessageBox.information(self, "Endpoint Saved", f"Custom endpoint set to: {endpoint}")
        else:
            QMessageBox.warning(self, "Invalid Input", "Please enter a valid endpoint.")

    def reset_endpoint(self):
        self.current_endpoint = ""
        self.endpoint_input.clear()
        self.save_local_settings()
        QMessageBox.information(self, "Endpoint Reset", "Custom endpoint has been cleared.")

    def set_dns_mode(self):
        selected_dns = self.dns_dropdown.currentText()
        if selected_dns == "family-friendly":
            selected_dns = "full"
        self.current_dns_mode = selected_dns
        self.save_local_settings()
        QMessageBox.information(self, "DNS Mode Saved", f"DNS mode set to: {selected_dns}")
        subprocess.run(["warp-cli", "dns", "families", selected_dns], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)

    def set_mode(self):
        selected_mode = self.modes_dropdown.currentText()
        if selected_mode:
            subprocess.run(['warp-cli', 'mode', selected_mode], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            QMessageBox.information(self, "Mode Changed", f"Mode set to: {selected_mode}")

    def update_inputs(self, settings):
        self.modes_dropdown.setCurrentText(settings.get("mode", "Unknown"))

    def style_dropdown(self, dropdown, fg_color, bg_color):
        dropdown.setStyleSheet(f"""
            QComboBox {{
                background-color: {bg_color};
                color: {fg_color};
                border: 1px solid {fg_color};
                border-radius: 5px;
                padding: 5px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {bg_color};
                color: {fg_color};
                selection-background-color: #0078D4;
            }}
        """)

    def update_status(self, status):
        self.current_status = status
        self.endpoint_input.setDisabled(status == "Connected")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyWarp App")
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
        self.status_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.status_label.setStyleSheet("color: #fcb909; font-weight: bold;")
        self.ip_label = QLabel(f"IPv4: 0.0.0.0")
        self.ip_label.setFont(QFont("Segoe UI", 12))
        self.ip_label.setToolTip("This is your current public IP address.")
        self.protocol_label = QLabel(f"Protocol: ---")
        current_protocol = get_current_protocol()
        self.protocol_label.setText(
            f"Protocol: <span style='color: #0078D4; font-weight: bold;'>{current_protocol}</span>")
        self.version_label = QLabel("Version: 1.0.1")
        self.version_label.setText(
            f"Version: <span style='color: #0078D4; font-weight: bold;'>1.0.1</span>")

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
        stats_widget.setStyleSheet("""
            QLabel {
                font-family: 'Segoe UI';
                font-size: 12pt;
                font-weight: normal;
            }
        """)
        stats_layout = QVBoxLayout(stats_widget)

        self.endpoints_label = QLabel("Endpoints: --")
        self.handshake_label = QLabel("Last Handshake: --")
        self.sent_label = QLabel("Sent Data: --")
        self.received_label = QLabel("Received Data: --")
        self.latency_label = QLabel("Latency: --")
        self.loss_label = QLabel("Loss: --")

        stats_layout.addWidget(self.endpoints_label)
        stats_layout.addWidget(self.handshake_label)
        stats_layout.addWidget(self.sent_label)
        stats_layout.addWidget(self.received_label)
        stats_layout.addWidget(self.latency_label)
        stats_layout.addWidget(self.loss_label)

        self.stacked_widget.addWidget(stats_widget)

        self.settings_handler = SettingsHandler(loop=True)
        self.settings_handler.start()
        settings_widget = SettingsPage(settings_handler=self.settings_handler)
        self.stacked_widget.addWidget(settings_widget)

        for idx, btn_text in enumerate(["Network Stats", "Settings", "Protocol"]):
            btn = QPushButton(btn_text)
            btn.setMinimumHeight(40)
            if btn_text != "Protocol":
                btn.clicked.connect(lambda _, i=idx: self.stacked_widget.setCurrentIndex(i))
            else:
                btn.clicked.connect(self.set_protocol)
            self.buttons[btn_text] = btn
            button_layout.addWidget(btn)

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
        protocol, endpoints, handshake_time, sent, received, latency, loss = stats_list

        self.protocol_label.setText(f"Protocol: <span style='color: #0078D4; font-weight: bold;'>{protocol}</span>")
        handshake_value = int(handshake_time.replace('s', ''))
        endpoints_value = endpoints.split(',')
        ipv4 = endpoints_value[0]
        ipv6 = endpoints_value[1] if len(endpoints_value[1]) > 5 else 'not Available'
        self.endpoints_label.setText(f"IPv4 Endpoint: {ipv4}\nIPv6 Endpoint: {ipv6}")
        self.handshake_label.setText(f"Last Handshake: {format_handshake_time(handshake_value)}")
        if handshake_value < 1800:
            self.handshake_label.setStyleSheet("color: green; font-weight: bold;")
        elif handshake_value < 3600:
            self.handshake_label.setStyleSheet("color: orange; font-weight: bold;")
        else:
            self.handshake_label.setStyleSheet("color: red; font-weight: bold;")
        self.sent_label.setText(f"Sent Data: {sent}")
        self.received_label.setText(f"Received Data: {received}")

        latency_value = int(latency.replace('ms', ''))
        if latency_value < 100:
            latency_color = "green"
        elif latency_value < 200:
            latency_color = "orange"
        else:
            latency_color = "red"
        self.latency_label.setStyleSheet(f"color: {latency_color}; font-weight: bold;")
        self.latency_label.setText(f"Latency: {latency}")

        loss_value = float(loss.split(';')[0].replace("%", ""))
        if loss_value > 5:
            self.loss_label.setStyleSheet("color: red; font-weight: bold;")
            self.loss_label.setToolTip("High packet loss detected!")
        else:
            self.loss_label.setStyleSheet("color: green; font-weight: normal;")
        self.loss_label.setText(f"Loss: {loss_value}%")

    def update_status(self, is_connected):
        self.status_label.setText(f"Status: {is_connected}")
        if is_connected == 'Connected':
            ip = get_global_ip()
            self.status_text = is_connected
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
            is_connected = True
            self.ip_label.setText(
                f"IPv4: <span style='color: #0078D4; font-weight: bold;'>{ip}</span>")
        elif is_connected == 'Disconnected':
            ip = get_global_ip()
            self.status_text = is_connected
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
            is_connected = False
            self.ip_label.setText(
                f"IPv4: <span style='color: #0078D4; font-weight: bold;'>{ip}</span>")
        else:
            self.status_text = is_connected
            is_connected = 'Unknown'
            self.ip_label.setText(
                f"IPv4: <span style='color: #0078D4; font-weight: bold;'>fetching...</span>")
            self.status_label.setStyleSheet("color: orange; font-weight: bold;")
        self.toggle_switch.update_button_state(is_connected)

    def get_styles(self):
        if self.is_dark_mode:
            return """
                QMainWindow { background-color: #121212; }
                #statusFrame { background-color: #1E1E1E; border-radius: 12px; padding: 15px; }
                QPushButton { background-color: #34495e; color: white; padding: 12px; border-radius: 8px; }
                QPushButton:hover { background-color: #1abc9c; }
                QLabel { font-size: 15px; color: #E0E0E0; }
                QStackedWidget { background-color: #1E1E1E; border-radius: 12px; padding: 20px; }
            """
        else:
            return """
                QMainWindow { background-color: #f0f2f5; }
                #statusFrame { background-color: white; border-radius: 12px; padding: 15px; }
                QPushButton { background-color: #0078D4; color: white; padding: 12px; border-radius: 8px; }
                QPushButton:hover { background-color: #005A9E; }
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
            subprocess.run(['warp-cli', 'tunnel', 'protocol', 'set', protocol], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            QMessageBox.information(self, "Protocol Changed", f"Protocol successfully changed to {protocol}.")
            self.protocol_label.setText(
                f"Protocol: <span style='color: #0078D4; font-weight: bold;'>{protocol}</span>")
        except subprocess.CalledProcessError as e:
            error_message = f"Failed to set protocol: {str(e)}"
            QMessageBox.critical(self, "Error", error_message)


def format_handshake_time(seconds):
    hours, remainder = divmod(seconds, 3600)
    mins, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {mins}m {secs}s"
    elif mins:
        return f"{mins}m {secs}s"
    else:
        return f"{secs}s"


def get_global_ip():
    try:
        response = requests.get('https://api.ipify.org', params={'format': 'json'})
        return response.json().get('ip', 'Failed')
    except Exception as e:
        print(f"Failed to fetch global IP: {e}")
        return 'Failed'

def get_current_protocol():
    try:
        process = subprocess.Popen(['warp-cli', 'settings'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
        stdout, _ = process.communicate()
        output = stdout.decode()

        for line in output.splitlines():
            if "WARP tunnel protocol:" in line:
                return line.split(":")[1].strip()
        return "Unknown"
    except Exception as e:
        print(f"Error fetching current protocol: {e}")
        return "Error"

def is_warp_installed():
    return shutil.which('warp-cli') is not None

def get_os_download_url():
    base_url = "https://developers.cloudflare.com/cloudflare-one/connections/connect-devices/warp/download-warp/#"
    os_name = platform.system().lower()

    if os_name == "darwin":
        os_name = "macos"

    return f"{base_url}{os_name}"

def handle_exception(exc_type, exc_value, exc_traceback):
    error_dialog = QMessageBox()
    error_dialog.setIcon(QMessageBox.Critical)
    error_dialog.setWindowTitle("Application Error")
    error_dialog.setText("An unexpected error occurred!")
    error_dialog.setDetailedText("".join(traceback.format_exception(exc_type, exc_value, exc_traceback)))
    error_dialog.exec()

def disconnect_on_exit():
    try:
        subprocess.run(["warp-cli", "disconnect"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        print("Warp disconnected successfully.")
    except Exception as e:
        print(f"Failed to disconnect Warp: {e}")

if __name__ == "__main__":
    atexit.register(disconnect_on_exit)
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(":/logo.png"))
    sys.excepthook = handle_exception
    if not is_warp_installed():
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setWindowTitle("Warp Not Found")
        msg_box.setText("Warp Cloudflare is not installed on this system. Please install Warp to use this app.")
        download_button = msg_box.addButton("Download", QMessageBox.ActionRole)
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec()
        if msg_box.clickedButton() == download_button:
            webbrowser.open(get_os_download_url())
        sys.exit()
    app.setFont(QFont("Arial", 10))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())