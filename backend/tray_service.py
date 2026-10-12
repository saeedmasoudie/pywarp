from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Property, Qt, Signal, Slot
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPixmap,
    QWindow,
)
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon


def _base_tray_icon(icon_path: Path | None = None) -> QIcon:
    if icon_path and icon_path.exists():
        icon = QIcon(str(icon_path))
        if not icon.isNull():
            return icon
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor("transparent"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    gradient = QLinearGradient(8, 8, 56, 56)
    gradient.setColorAt(0, QColor("#7C5CFC"))
    gradient.setColorAt(1, QColor("#22D3C5"))
    painter.setBrush(gradient)
    painter.setPen(QColor("transparent"))
    painter.drawRoundedRect(5, 5, 54, 54, 17, 17)
    font = QFont()
    font.setPixelSize(33)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("white"))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "P")
    painter.end()
    return QIcon(pixmap)


def create_tray_icon(base_icon: QIcon, status: str) -> QIcon:
    colors = {
        "Connected": QColor("#42D392"),
        "Connecting": QColor("#F5B942"),
        "Disconnecting": QColor("#F5B942"),
    }
    badge_color = colors.get(status, QColor("#FF657A"))
    icon = QIcon()
    for size in (16, 20, 24, 32, 48, 64):
        pixmap = base_icon.pixmap(size, size)
        if pixmap.isNull():
            continue
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        badge_size = max(6, round(size * 0.3))
        outline = max(1, round(size * 0.045))
        x = size - badge_size - outline
        y = size - badge_size - outline

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#0B1020"))
        painter.drawEllipse(
            x - outline,
            y - outline,
            badge_size + outline * 2,
            badge_size + outline * 2,
        )
        painter.setBrush(badge_color)
        painter.drawEllipse(x, y, badge_size, badge_size)

        highlight = QColor("#FFFFFF")
        highlight.setAlpha(150)
        painter.setBrush(highlight)
        highlight_size = max(1, round(badge_size * 0.22))
        painter.drawEllipse(
            x + round(badge_size * 0.2),
            y + round(badge_size * 0.18),
            highlight_size,
            highlight_size,
        )
        painter.end()
        icon.addPixmap(pixmap)
    return icon


class TrayService(QObject):
    availableChanged = Signal()
    quitConfirmationRequested = Signal()

    def __init__(
        self,
        controller,
        icon_path: Path | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._controller = controller
        self._window = None
        self._force_quit = False
        self._available = QSystemTrayIcon.isSystemTrayAvailable()
        self._tray: QSystemTrayIcon | None = None
        self._menu: QMenu | None = None
        self._toggle_action: QAction | None = None
        self._show_action: QAction | None = None
        self._quit_action: QAction | None = None
        self._status_action: QAction | None = None
        self._telemetry_action: QAction | None = None
        self._base_icon = _base_tray_icon(icon_path)
        self._icon_status = ""
        controller.shutdownReady.connect(self._finish_quit)

        if not self._available:
            return

        self._tray = QSystemTrayIcon(
            create_tray_icon(self._base_icon, controller.status),
            self,
        )
        self._tray.setToolTip("PyWarp")

        menu = QMenu()
        self._menu = menu
        menu.setObjectName("pywarpTrayMenu")
        menu.setStyleSheet(
            """
            QMenu#pywarpTrayMenu {
                background: #111827;
                color: #F5F7FC;
                border: 1px solid #2B3850;
                border-radius: 10px;
                padding: 5px;
                font-size: 11px;
            }
            QMenu#pywarpTrayMenu::item {
                min-width: 168px;
                padding: 7px 12px;
                margin: 1px;
                border-radius: 6px;
            }
            QMenu#pywarpTrayMenu::item:selected {
                background: #25324A;
            }
            QMenu#pywarpTrayMenu::item:disabled {
                color: #8C9BB2;
                font-weight: 600;
            }
            QMenu#pywarpTrayMenu::separator {
                height: 1px;
                background: #2B3850;
                margin: 5px 8px;
            }
            """
        )
        self._status_action = QAction("PYWARP", menu)
        self._status_action.setEnabled(False)
        menu.addAction(self._status_action)
        self._telemetry_action = QAction("Ping —  ·  Loss —", menu)
        self._telemetry_action.setEnabled(False)
        menu.addAction(self._telemetry_action)
        menu.addSeparator()

        show_action = QAction("Open PyWarp", menu)
        self._show_action = show_action
        show_action.triggered.connect(self.showWindow)
        menu.addAction(show_action)

        self._toggle_action = QAction("Connect", menu)
        self._toggle_action.triggered.connect(controller.toggleConnection)
        menu.addAction(self._toggle_action)

        menu.addSeparator()
        quit_action = QAction("Quit", menu)
        self._quit_action = quit_action
        quit_action.triggered.connect(self.quitApplication)
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)
        controller.stateChanged.connect(self._sync_state)
        controller.settingsChanged.connect(self._sync_state)
        controller.statsChanged.connect(self._sync_state)
        self._sync_state()
        self._tray.show()

    @Property(bool, notify=availableChanged)
    def available(self) -> bool:
        return self._available

    @Property(bool)
    def forceQuit(self) -> bool:
        return self._force_quit

    def set_window(self, window) -> None:
        self._window = window

    def _sync_state(self) -> None:
        if not self._toggle_action:
            return
        status = self._controller.status
        if self._tray and status != self._icon_status:
            self._tray.setIcon(create_tray_icon(self._base_icon, status))
            self._icon_status = status
        labels = {
            "en": {
                "open": "Open PyWarp",
                "connect": "Connect",
                "cancel": "Cancel connection",
                "disconnect": "Disconnect",
                "quit": "Quit",
                "ping": "Ping",
                "loss": "Loss",
                "statuses": {
                    "Connected": "Connected",
                    "Disconnected": "Disconnected",
                    "Connecting": "Connecting",
                    "Disconnecting": "Disconnecting",
                    "No Network": "No network",
                    "Failed": "Failed",
                    "Unavailable": "Unavailable",
                },
            },
            "fa": {
                "open": "باز کردن PyWarp",
                "connect": "اتصال",
                "cancel": "لغو اتصال",
                "disconnect": "قطع اتصال",
                "quit": "خروج",
                "ping": "پینگ",
                "loss": "اتلاف",
                "statuses": {
                    "Connected": "متصل",
                    "Disconnected": "قطع",
                    "Connecting": "در حال اتصال",
                    "Disconnecting": "در حال قطع",
                    "No Network": "بدون شبکه",
                    "Failed": "ناموفق",
                    "Unavailable": "در دسترس نیست",
                },
            },
            "ru": {
                "open": "Открыть PyWarp",
                "connect": "Подключить",
                "cancel": "Отменить подключение",
                "disconnect": "Отключить",
                "quit": "Выйти",
                "ping": "Пинг",
                "loss": "Потери",
                "statuses": {
                    "Connected": "Подключено",
                    "Disconnected": "Отключено",
                    "Connecting": "Подключение",
                    "Disconnecting": "Отключение",
                    "No Network": "Нет сети",
                    "Failed": "Ошибка",
                    "Unavailable": "Недоступно",
                },
            },
            "zh_CN": {
                "open": "打开 PyWarp",
                "connect": "连接",
                "cancel": "取消连接",
                "disconnect": "断开连接",
                "quit": "退出",
                "ping": "延迟",
                "loss": "丢包",
                "statuses": {
                    "Connected": "已连接",
                    "Disconnected": "已断开",
                    "Connecting": "正在连接",
                    "Disconnecting": "正在断开",
                    "No Network": "无网络",
                    "Failed": "连接失败",
                    "Unavailable": "不可用",
                },
            },
        }.get(self._controller.language, {})
        if self._menu:
            self._menu.setLayoutDirection(
                Qt.RightToLeft
                if self._controller.language == "fa"
                else Qt.LeftToRight
            )
        if self._show_action:
            self._show_action.setText(labels.get("open", "Open PyWarp"))
        if self._quit_action:
            self._quit_action.setText(labels.get("quit", "Quit"))
        status_label = labels.get("statuses", {}).get(status, status)
        self._status_action.setText(f"PYWARP  ·  {status_label}")
        if self._telemetry_action:
            self._telemetry_action.setText(
                f"{labels.get('ping', 'Ping')} {self._controller.latency}"
                f"  ·  {labels.get('loss', 'Loss')} {self._controller.loss}"
            )
        if status == "Connecting":
            self._toggle_action.setText(
                labels.get("cancel", "Cancel connection")
            )
        elif status in ("Connected", "Disconnecting"):
            self._toggle_action.setText(
                labels.get("disconnect", "Disconnect")
            )
        else:
            self._toggle_action.setText(labels.get("connect", "Connect"))
        self._toggle_action.setEnabled(status != "Disconnecting")
        if self._tray:
            self._tray.setToolTip(f"PyWarp — {status_label}")

    def _on_activated(self, reason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            if (
                self._window
                and self._window.isVisible()
                and self._window.isActive()
            ):
                self._window.showMinimized()
            else:
                self.showWindow()

    @Slot()
    def showWindow(self) -> None:
        if not self._window:
            return
        if self._window.visibility() == QWindow.Visibility.Minimized:
            self._window.showNormal()
        else:
            self._window.show()
        self._window.raise_()
        self._window.requestActivate()

    @Slot()
    def hideWindow(self) -> None:
        if self._window:
            self._window.hide()

    @Slot()
    def quitApplication(self) -> None:
        self.showWindow()
        self.quitConfirmationRequested.emit()

    @Slot()
    def confirmQuit(self) -> None:
        if self._force_quit:
            return
        if self._quit_action:
            self._quit_action.setEnabled(False)
        if self._toggle_action:
            self._toggle_action.setEnabled(False)
        self._controller.prepareToQuit()

    @Slot()
    def _finish_quit(self) -> None:
        self._force_quit = True
        if self._tray:
            self._tray.hide()
        app = QApplication.instance()
        if app:
            app.quit()
