from __future__ import annotations

import ipaddress
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import requests
from PySide6.QtCore import (
    Property,
    QProcess,
    QSettings,
    QTimer,
    QObject,
    Signal,
    Slot,
    QUrl,
)
from PySide6.QtGui import QDesktopServices

from .command_runner import CommandResult, CommandRunner, find_warp_cli
from .models import ObjectListModel


MODE_VALUES = (
    "warp",
    "doh",
    "warp+doh",
    "dot",
    "warp+dot",
    "proxy",
    "tunnel_only",
)
DNS_VALUES = ("off", "malware", "full")
PROTOCOL_VALUES = ("WireGuard", "MASQUE")
MASQUE_VALUES = ("auto", "h3-only", "h2-only", "h3-with-h2-fallback")
CURRENT_VERSION = "2.0.0"
CREATE_NO_WINDOW = 0x08000000


class AppController(QObject):
    stateChanged = Signal()
    settingsChanged = Signal()
    statsChanged = Signal()
    busyChanged = Signal()
    introChanged = Signal()
    autoSelectionChanged = Signal()
    accountChanged = Signal()
    updateStateChanged = Signal()
    navigationRequested = Signal(int)
    focusRequested = Signal(str)
    tourRequested = Signal()
    installStateChanged = Signal()
    toastRequested = Signal(str, str)
    shutdownReady = Signal()

    def __init__(self, log_path: Path, parent: QObject | None = None):
        super().__init__(parent)
        self._settings = QSettings("PyWarp", "App")
        self._runner = CommandRunner(self)
        self._log_path = log_path

        self._status = "Disconnected"
        self._reason = "Connect to create a private route through Cloudflare."
        self._reason_title = "Ready when you are"
        self._reason_code = ""
        self._status_buffer = ""
        self._last_status_update = 0.0
        self._busy = False
        self._connection_generation = 0
        self._connect_intent_deadline = 0.0
        self._cancel_requested = False
        self._shutdown_pending = False
        self._public_ip = "Detecting…"
        self._country_name = "Detecting location"
        self._country_code = ""
        self._country_flag = "—"
        self._mode = str(self._settings.value("mode", "warp"))
        self._dns_family = str(self._settings.value("dns_mode", "off"))
        self._protocol = self._normalize_protocol(
            self._settings.value("protocol", "WireGuard"),
            "WireGuard",
        )
        self._masque_option = str(
            self._settings.value("masque_option", "auto")
        )
        self._custom_endpoint = str(
            self._settings.value("custom_endpoint", "")
        )
        self._proxy_port = str(self._settings.value("proxy_port", "40000"))
        self._compact_mode = self._as_bool(
            self._settings.value("compact_mode", False)
        )
        self._theme = str(self._settings.value("theme", "system"))
        self._language = str(self._settings.value("language", "en"))
        if self._language not in ("en", "fa", "ru", "zh_CN"):
            self._language = "en"
        try:
            country_names_path = (
                Path(__file__).resolve().parent.parent
                / "assets"
                / "countries-fa.json"
            )
            self._persian_country_names = json.loads(
                country_names_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            self._persian_country_names = {}
        self._warp_installed = find_warp_cli() is not None
        self._warp_installing = False
        self._warp_install_message = ""
        self._platform_name = platform.system()
        self._intro_complete = self._as_bool(
            self._settings.value("qml_intro_complete", False)
        )
        self._dns_logging = self._as_bool(
            self._settings.value("dns_log_enabled", False)
        )
        self._auto_selecting = False
        self._auto_progress = 0
        self._auto_message = ""
        self._auto_profile = ""
        self._auto_test_index = 0
        self._auto_test_total = 8
        self._auto_index = 0
        self._auto_candidates: list[tuple[str, str | None, str]] = []
        self._auto_original: tuple[str, str, str, str, bool] | None = None
        self._auto_restore_pending = False
        self._auto_verify_deadline = 0.0
        self._auto_full_test = False
        self._auto_results: list[dict] = []
        saved_smart_results = self._load_json_setting(
            "smart_test_results", []
        )

        self._registration_loaded = False
        self._registered = False
        self._registration_busy = False
        self._account_type = ""
        self._license_key = ""
        self._device_id = ""
        self._organization = ""
        self._support_url = ""
        self._managed_account = False
        self._mode_switch_allowed = True
        self._registration_devices: list[dict] = []
        self._team_enroll_style = ""
        self._accept_tos_flag = False
        self._netbt_supported = False
        self._netbt_enabled = False
        self._relaxed_timeouts_supported = False
        self._relaxed_timeouts_enabled = False
        self._pmtud_supported = False
        self._pmtud_enabled = False
        self._doh_mss_clamp_supported = False
        self._doh_mss_clamp_enabled = False

        self._endpoint_history = self._load_list_setting("endpoint_history")
        self._rule_history = self._load_list_setting("rule_history")
        self._advanced_history = self._load_json_setting(
            "advanced_history", []
        )
        self._activity_items = self._load_json_setting(
            "activity_history", []
        )

        self._update_checking = False
        self._latest_pywarp_version = ""
        self._latest_warp_version = ""
        self._installed_warp_version = ""
        self._pywarp_update_available = False
        self._warp_update_available = False
        self._pywarp_release_url = (
            "https://github.com/saeedmasoudie/pywarp/releases"
        )
        self._update_error = ""
        self._pywarp_asset_url = ""
        self._pywarp_asset_name = ""
        self._update_downloading = False

        self._sent = "0 B"
        self._received = "0 B"
        self._latency = "—"
        self._loss = "—"
        self._endpoint_v4 = "—"
        self._endpoint_v6 = "—"
        self._handshake = "—"
        self._upload_rate = "0 B/s"
        self._download_rate = "0 B/s"
        self._last_bytes_sent: float | None = None
        self._last_bytes_received: float | None = None
        self._last_stats_at: float | None = None
        self._latency_history: list[float] = []
        self._stats_pending = False
        self._ip_pending = False
        self._last_updated = "Waiting for data"

        self._dns_logs = ObjectListModel(
            ("time", "recordType", "domain", "status", "duration", "answers"),
            max_items=300,
            parent=self,
        )
        self._app_logs = ObjectListModel(
            ("time", "date", "level", "category", "message", "detail"),
            max_items=500,
            parent=self,
        )
        self._exclusions = ObjectListModel(
            ("type", "value"),
            parent=self,
        )
        self._advanced_changes = ObjectListModel(
            ("time", "action", "kind", "value"),
            max_items=30,
            parent=self,
        )
        self._smart_results = ObjectListModel(
            (
                "profile",
                "protocol",
                "transport",
                "mode",
                "latency",
                "loss",
                "status",
                "working",
                "recommended",
            ),
            parent=self,
        )
        if isinstance(saved_smart_results, list):
            self._auto_results = [
                item for item in saved_smart_results
                if isinstance(item, dict)
            ]
            self._smart_results.replace(self._auto_results)
        if isinstance(self._activity_items, list):
            self._activity_items = [
                {
                    "time": str(item.get("time", "")),
                    "date": str(item.get("date", "")),
                    "level": str(item.get("level", "INFO")),
                    "category": str(item.get("category", "system")),
                    "message": str(item.get("message", "")),
                    "detail": str(item.get("detail", "")),
                }
                for item in self._activity_items
                if isinstance(item, dict)
            ]
            self._app_logs.replace(self._activity_items[-300:])
        if isinstance(self._advanced_history, list):
            self._advanced_changes.replace(self._advanced_history[-30:])
        self._append_event(
            "system",
            "PyWarp opened",
            f"Version {CURRENT_VERSION} started on {self._platform_name}.",
            "INFO",
        )

        self._status_process = QProcess(self)
        self._status_process.setProcessChannelMode(QProcess.MergedChannels)
        if (
            platform.system() == "Windows"
            and hasattr(
                self._status_process,
                "setCreateProcessArgumentsModifier",
            )
        ):
            self._status_process.setCreateProcessArgumentsModifier(
                self._hide_qprocess_window
            )
        self._status_process.readyReadStandardOutput.connect(
            self._read_status_stream
        )
        self._status_process.finished.connect(self._restart_status_stream)
        self._status_process.errorOccurred.connect(self._status_process_error)

        self._stats_timer = QTimer(self)
        self._stats_timer.setInterval(3_000)
        self._stats_timer.timeout.connect(self.refreshStats)
        self._stats_timer.start()

        self._status_watchdog = QTimer(self)
        self._status_watchdog.setInterval(8_000)
        self._status_watchdog.timeout.connect(self._check_status_stream)
        self._status_watchdog.start()

        self._ip_refresh_timer = QTimer(self)
        self._ip_refresh_timer.setInterval(30_000)
        self._ip_refresh_timer.timeout.connect(self.refreshPublicIp)
        self._ip_refresh_timer.start()

        QTimer.singleShot(0, self._start_status_stream)
        QTimer.singleShot(150, self.refreshStats)
        QTimer.singleShot(250, self.refreshPublicIp)
        QTimer.singleShot(350, self.refreshExclusions)
        QTimer.singleShot(450, self._detect_cli_capabilities)
        QTimer.singleShot(550, self.refreshRegistration)
        QTimer.singleShot(2_500, self.checkForUpdates)

    @staticmethod
    def _hide_qprocess_window(arguments) -> None:
        arguments.flags |= CREATE_NO_WINDOW

    @staticmethod
    def _as_bool(value) -> bool:
        if isinstance(value, str):
            return value.lower() in ("1", "true", "yes", "on")
        return bool(value)

    @staticmethod
    def _normalize_protocol(value, fallback: str) -> str:
        normalized = str(value or "").strip().lower()
        return {
            "wireguard": "WireGuard",
            "masque": "MASQUE",
        }.get(normalized, fallback)

    def _load_json_setting(self, key: str, default):
        raw = self._settings.value(key, "")
        if not raw:
            return default
        if isinstance(raw, (list, dict)):
            return raw
        try:
            return json.loads(str(raw))
        except (TypeError, json.JSONDecodeError):
            return default

    def _load_list_setting(self, key: str) -> list[str]:
        value = self._settings.value(key, [])
        if isinstance(value, list):
            return [str(item) for item in value]
        if not value:
            return []
        try:
            parsed = json.loads(str(value))
            return [str(item) for item in parsed] if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return [str(value)]

    @staticmethod
    def _format_bytes(value) -> str:
        try:
            size = float(value)
        except (TypeError, ValueError):
            return "0 B"
        units = ("B", "KB", "MB", "GB", "TB")
        index = 0
        while size >= 1024 and index < len(units) - 1:
            size /= 1024
            index += 1
        return f"{size:.2f} {units[index]}"

    def _set_busy(self, value: bool) -> None:
        if self._busy != value:
            self._busy = value
            self.busyChanged.emit()

    def _save_setting(self, key: str, value) -> None:
        self._settings.setValue(key, value)
        self._settings.sync()

    def _run(
        self,
        args: list[str],
        success=None,
        success_message: str = "",
        busy: bool = True,
        report_errors: bool = True,
        on_finished=None,
        error=None,
    ) -> None:
        if busy:
            self._set_busy(True)

        def done(result: CommandResult) -> None:
            if success:
                success(result)
            if success_message:
                self._append_event(
                    "settings",
                    success_message,
                    "The new setting was accepted by Cloudflare WARP.",
                    "INFO",
                )
                self.toastRequested.emit("success", success_message)

        def failed(message: str) -> None:
            if report_errors:
                self._append_event(
                    "error",
                    "WARP could not complete an action",
                    message.splitlines()[0],
                    "ERROR",
                )
            if error:
                error(message)
            if report_errors:
                self.toastRequested.emit("error", message.splitlines()[0])

        def command_finished() -> None:
            if busy:
                self._set_busy(False)
            if on_finished:
                on_finished()

        self._runner.run(
            args,
            on_success=done,
            on_error=failed,
            on_finished=command_finished,
        )

    def _start_status_stream(self) -> None:
        executable = find_warp_cli()
        if not executable:
            self._reason = "warp-cli was not found"
            self._status = "Unavailable"
            self.stateChanged.emit()
            return
        if self._status_process.state() != QProcess.NotRunning:
            return
        self._status_buffer = ""
        self._status_process.setProgram(executable)
        self._status_process.setArguments(["-l", "-j", "status"])
        self._status_process.start()

    def _restart_status_stream(self, *_args) -> None:
        self._consume_status_lines(flush=True)
        QTimer.singleShot(3_000, self._start_status_stream)

    def _status_process_error(self, _error) -> None:
        if self._status_process.state() == QProcess.NotRunning:
            QTimer.singleShot(3_000, self._start_status_stream)

    def _check_status_stream(self) -> None:
        if self._status_process.state() == QProcess.NotRunning:
            self._start_status_stream()

    def _read_status_stream(self) -> None:
        self._status_buffer += bytes(
            self._status_process.readAllStandardOutput()
        ).decode(
            errors="ignore"
        )
        self._consume_status_lines()

    def _consume_status_lines(self, flush: bool = False) -> None:
        lines = self._status_buffer.splitlines(keepends=True)
        self._status_buffer = ""
        for chunk in lines:
            complete = chunk.endswith(("\n", "\r"))
            line = chunk.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                if not complete and not flush:
                    self._status_buffer = line + self._status_buffer
                continue

            if "status" in event:
                old_status = self._status
                old_reason_code = self._reason_code
                raw_status = str(event.get("status", "Unknown"))
                status_map = {
                    "connected": "Connected",
                    "disconnected": "Disconnected",
                    "connecting": "Connecting",
                    "disconnecting": "Disconnecting",
                    "no network": "No Network",
                    "nonetwork": "No Network",
                    "failed": "Failed",
                }
                parsed_status = status_map.get(
                    raw_status.replace("_", " ").lower(), raw_status
                )
                raw_reason = event.get("reason", "")
                incoming_reason_code = (
                    str(next(iter(raw_reason), ""))
                    if isinstance(raw_reason, dict)
                    else str(raw_reason or "")
                )
                if (
                    parsed_status == "Disconnected"
                    and self._status == "Connecting"
                    and time.monotonic() < self._connect_intent_deadline
                    and incoming_reason_code != "Manual"
                ):
                    parsed_status = "Connecting"
                if self._cancel_requested and parsed_status == "Connected":
                    continue
                self._status = parsed_status
                if self._status in (
                    "Connected",
                    "Disconnected",
                    "Failed",
                    "No Network",
                ):
                    self._connect_intent_deadline = 0.0
                if self._status in (
                    "Disconnected",
                    "Failed",
                    "No Network",
                ):
                    self._cancel_requested = False
                reason = raw_reason
                if isinstance(reason, dict):
                    key, value = next(iter(reason.items()), ("", ""))
                    if isinstance(value, list):
                        value = value[0] if value else ""
                    self._reason_code = str(key)
                    self._reason_title, self._reason = self._friendly_reason(
                        str(key), str(value or ""), self._status
                    )
                else:
                    self._reason_code = str(reason or "")
                    self._reason_title, self._reason = self._friendly_reason(
                        self._reason_code, "", self._status
                    )
                if self._status == "Disconnected":
                    self._reason_code = ""
                    self._reason_title, self._reason = self._friendly_reason(
                        "", "", self._status
                    )
                self._last_status_update = time.monotonic()
                self._last_updated = time.strftime("Updated %H:%M:%S")
                if old_status != self._status and not self.connected:
                    self._reset_live_stats()
                if old_status != self._status:
                    if self._status == "Connected":
                        self._append_event(
                            "connection",
                            "Secure connection established",
                            (
                                f"Connected with {self._protocol} in "
                                f"{self._mode} mode."
                            ),
                            "SUCCESS",
                        )
                    elif self._status == "Disconnected":
                        self._append_event(
                            "connection",
                            "Connection closed",
                            self._reason
                            or "Traffic returned to the normal network route.",
                            "INFO",
                        )
                    elif self._status in ("Failed", "No Network"):
                        self._append_event(
                            "network",
                            self._reason_title,
                            self._reason,
                            "ERROR",
                        )
                elif (
                    self.connected
                    and self._reason_code != old_reason_code
                    and self._reason_code
                    in ("NetworkDegraded", "ConnectivityCheckFailed")
                ):
                    self._append_event(
                        "network",
                        self._reason_title,
                        self._reason,
                        "WARNING",
                    )
                self.stateChanged.emit()
                if self._status == "Connected":
                    self.refreshStats()
                    if old_status != self._status:
                        self.refreshPublicIp()
                elif (
                    old_status != self._status
                    and self._status in ("Disconnected", "Failed", "No Network")
                ):
                    QTimer.singleShot(900, self.refreshPublicIp)
            elif "dns_log" in event:
                self._append_dns_log(event["dns_log"])

    @staticmethod
    def _friendly_reason(
        code: str, value: str, status: str
    ) -> tuple[str, str]:
        if status == "Disconnected":
            return (
                "Ready to connect",
                "Your normal internet connection is active.",
            )
        reasons = {
            "PerformingHappyEyeballs": (
                "Finding the fastest route",
                "Comparing IPv4 and IPv6 paths to Cloudflare.",
            ),
            "EstablishingConnection": (
                "Reaching Cloudflare",
                f"Negotiating a secure session with {value}."
                if value
                else "Negotiating a secure session with the edge network.",
            ),
            "InitializingTunnelInterface": (
                "Creating the secure interface",
                "Preparing the encrypted network adapter.",
            ),
            "ConfiguringInitialFirewall": (
                "Securing local traffic",
                "Applying temporary firewall protection.",
            ),
            "SettingRoutes": (
                "Directing your traffic",
                "Installing the routes used by the WARP tunnel.",
            ),
            "ConfiguringFirewallRules": (
                "Applying protection rules",
                "Finalizing firewall policy for the tunnel.",
            ),
            "PerformingConnectivityChecks": (
                "Verifying the route",
                "Checking that internet traffic passes through WARP.",
            ),
            "ValidatingDnsConfiguration": (
                "Checking secure DNS",
                "Confirming that DNS is using the selected policy.",
            ),
            "CheckingNetwork": (
                "Checking your network",
                "Waiting for a usable local connection.",
            ),
            "InitializingSettings": (
                "Loading WARP settings",
                "Preparing your saved connection profile.",
            ),
            "SettingsChanged": (
                "Applying new settings",
                "Refreshing the tunnel with your latest configuration.",
            ),
            "Manual": (
                "Disconnected",
                "The secure tunnel was stopped manually.",
            ),
            "NetworkHealthy": (
                "Connection is healthy",
                "The encrypted route is operating normally.",
            ),
            "NoNetwork": (
                "No network available",
                "Connect to a network and PyWarp will try again.",
            ),
            "HappyEyeballsFailed": (
                "Could not reach Cloudflare",
                "IPv4 and IPv6 connection attempts both failed.",
            ),
            "ConfiguringForwardProxy": (
                "Starting the local proxy",
                "Preparing HTTP and SOCKS proxy listeners.",
            ),
            "ValidatingProxyConfiguration": (
                "Checking the local proxy",
                "Verifying that proxy traffic can reach Cloudflare.",
            ),
            "NetworkDegraded": (
                "Network quality is reduced",
                "WARP is connected, but the route may be unstable.",
            ),
            "ConnectivityCheckFailed": (
                "Route verification failed",
                "The tunnel started but internet access could not be verified.",
            ),
        }
        if code in reasons:
            return reasons[code]
        if status == "Connected":
            return (
                "Connection is protected",
                "Traffic is flowing through the encrypted WARP tunnel.",
            )
        if status == "Connecting":
            return (
                "Building a secure route",
                "WARP is negotiating the best available connection.",
            )
        if status == "Disconnecting":
            return (
                "Closing the secure route",
                "Restoring your normal network configuration.",
            )
        if status == "Disconnected":
            return (
                "Ready when you are",
                "Connect to create a private route through Cloudflare.",
            )
        readable = re.sub(r"(?<!^)(?=[A-Z])", " ", code).strip()
        return (
            readable or status,
            f"Cloudflare WARP reported: {readable}."
            if readable
            else "Waiting for an update from the WARP service.",
        )

    def _reset_live_stats(self) -> None:
        self._sent = "0 B"
        self._received = "0 B"
        self._latency = "—"
        self._loss = "—"
        self._endpoint_v4 = "—"
        self._endpoint_v6 = "—"
        self._handshake = "—"
        self._upload_rate = "0 B/s"
        self._download_rate = "0 B/s"
        self._last_bytes_sent = None
        self._last_bytes_received = None
        self._last_stats_at = None
        self._latency_history = []
        self.statsChanged.emit()

    def _append_dns_log(self, data: dict) -> None:
        query = data.get("query", [])
        record_type = str(query[0]) if len(query) > 0 else "?"
        domain = str(query[1]).rstrip(".") if len(query) > 1 else "Unknown"
        answers = []
        for answer in data.get("answers", []):
            if isinstance(answer, list) and answer:
                answers.append(str(answer[-1]))
        self._dns_logs.append(
            {
                "time": time.strftime("%H:%M:%S"),
                "recordType": record_type,
                "domain": domain,
                "status": str(data.get("status", "Unknown")),
                "duration": f"{data.get('duration_ms', 0)} ms",
                "answers": ", ".join(answers),
            }
        )

    def _append_event(
        self,
        category: str,
        message: str,
        detail: str = "",
        level: str = "INFO",
    ) -> None:
        item = {
            "time": time.strftime("%H:%M:%S"),
            "date": time.strftime("%Y-%m-%d"),
            "level": level,
            "category": category,
            "message": message,
            "detail": detail,
        }
        self._app_logs.append(item)
        if not isinstance(self._activity_items, list):
            self._activity_items = []
        self._activity_items = [*self._activity_items[-199:], item]
        self._save_setting(
            "activity_history",
            json.dumps(self._activity_items, ensure_ascii=False),
        )
        getattr(logging, level.lower(), logging.info)(
            "%s: %s — %s", category, message, detail
        )

    def recordCriticalError(self, message: str) -> None:
        self._append_event(
            "error",
            "Unexpected application error",
            message,
            "CRITICAL",
        )

    @Property(str, notify=stateChanged)
    def status(self) -> str:
        return self._status

    @Property(str, notify=stateChanged)
    def reason(self) -> str:
        return self._reason

    @Property(str, notify=stateChanged)
    def reasonTitle(self) -> str:
        return self._reason_title

    @Property(str, notify=stateChanged)
    def reasonCode(self) -> str:
        return self._reason_code

    @Property(bool, notify=stateChanged)
    def connected(self) -> bool:
        return self._status == "Connected"

    @Property(bool, notify=stateChanged)
    def connecting(self) -> bool:
        return self._status == "Connecting"

    @Property(bool, notify=stateChanged)
    def disconnecting(self) -> bool:
        return self._status == "Disconnecting"

    @Property(bool, notify=stateChanged)
    def transitioning(self) -> bool:
        return self._status in ("Connecting", "Disconnecting")

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    @Property(str, notify=stateChanged)
    def publicIp(self) -> str:
        return self._public_ip

    @Property(str, notify=stateChanged)
    def countryName(self) -> str:
        return self._country_name

    @Property(str, notify=stateChanged)
    def countryCode(self) -> str:
        return self._country_code

    @Property(str, notify=stateChanged)
    def countryFlag(self) -> str:
        return self._country_flag

    @Property(str, notify=stateChanged)
    def lastUpdated(self) -> str:
        return self._last_updated

    @Property(str, notify=settingsChanged)
    def mode(self) -> str:
        return self._mode

    @Property(str, notify=settingsChanged)
    def dnsFamily(self) -> str:
        return self._dns_family

    @Property(str, notify=settingsChanged)
    def protocol(self) -> str:
        return self._protocol

    @Property(str, notify=settingsChanged)
    def masqueOption(self) -> str:
        return self._masque_option

    @Property(str, notify=settingsChanged)
    def customEndpoint(self) -> str:
        return self._custom_endpoint

    @Property("QVariantList", notify=settingsChanged)
    def endpointHistory(self) -> list[str]:
        return self._endpoint_history

    @Property("QVariantList", notify=settingsChanged)
    def ruleHistory(self) -> list[str]:
        return self._rule_history

    @Property(str, notify=settingsChanged)
    def proxyPort(self) -> str:
        return self._proxy_port

    @Property(str, notify=settingsChanged)
    def theme(self) -> str:
        return self._theme

    @Property(bool, notify=settingsChanged)
    def compactMode(self) -> bool:
        return self._compact_mode

    @Property(str, notify=settingsChanged)
    def language(self) -> str:
        return self._language

    @Property(bool, notify=settingsChanged)
    def warpInstalled(self) -> bool:
        return self._warp_installed

    @Property(bool, notify=installStateChanged)
    def warpInstalling(self) -> bool:
        return self._warp_installing

    @Property(str, notify=installStateChanged)
    def warpInstallMessage(self) -> str:
        return self._warp_install_message

    @Property(str, constant=True)
    def platformName(self) -> str:
        return self._platform_name

    @Property(str, notify=settingsChanged)
    def installHint(self) -> str:
        if self._warp_installed:
            return "Cloudflare WARP CLI is installed and ready."
        if self._platform_name == "Linux":
            return (
                "Download the official Cloudflare package for your "
                "distribution, install it, then run warp-cli register."
            )
        if self._platform_name == "Darwin":
            return (
                "Install the official Cloudflare WARP application, then "
                "reopen PyWarp."
            )
        return (
            "Install Cloudflare WARP from the official download page, then "
            "reopen PyWarp."
        )

    @Property(bool, notify=settingsChanged)
    def dnsLogging(self) -> bool:
        return self._dns_logging

    @Property(bool, notify=introChanged)
    def introComplete(self) -> bool:
        return self._intro_complete

    @Property(bool, notify=autoSelectionChanged)
    def autoSelecting(self) -> bool:
        return self._auto_selecting

    @Property(int, notify=autoSelectionChanged)
    def autoProgress(self) -> int:
        return self._auto_progress

    @Property(str, notify=autoSelectionChanged)
    def autoMessage(self) -> str:
        return self._auto_message

    @Property(str, notify=autoSelectionChanged)
    def autoProfile(self) -> str:
        return self._auto_profile

    @Property(int, notify=autoSelectionChanged)
    def autoTestIndex(self) -> int:
        return self._auto_test_index

    @Property(int, notify=autoSelectionChanged)
    def autoTestTotal(self) -> int:
        return self._auto_test_total

    @Property(bool, notify=autoSelectionChanged)
    def autoFullTest(self) -> bool:
        return self._auto_full_test

    @Property(int, notify=autoSelectionChanged)
    def smartResultCount(self) -> int:
        return len(self._auto_results)

    @Property(QObject, constant=True)
    def smartResultModel(self) -> QObject:
        return self._smart_results

    @Property(bool, notify=accountChanged)
    def registrationLoaded(self) -> bool:
        return self._registration_loaded

    @Property(bool, notify=accountChanged)
    def registered(self) -> bool:
        return self._registered

    @Property(bool, notify=accountChanged)
    def registrationBusy(self) -> bool:
        return self._registration_busy

    @Property(str, notify=accountChanged)
    def accountType(self) -> str:
        return self._account_type

    @Property(str, notify=accountChanged)
    def licenseKey(self) -> str:
        return self._license_key

    @Property(str, notify=accountChanged)
    def deviceId(self) -> str:
        return self._device_id

    @Property(str, notify=accountChanged)
    def organization(self) -> str:
        return self._organization

    @Property(str, notify=accountChanged)
    def supportUrl(self) -> str:
        return self._support_url

    @Property(bool, notify=accountChanged)
    def managedAccount(self) -> bool:
        return self._managed_account

    @Property(bool, notify=accountChanged)
    def modeSwitchAllowed(self) -> bool:
        return self._mode_switch_allowed

    @Property("QVariantList", notify=accountChanged)
    def registrationDevices(self) -> list[dict]:
        return self._registration_devices

    @Property(bool, notify=accountChanged)
    def teamEnrollmentSupported(self) -> bool:
        return bool(self._team_enroll_style)

    @Property(bool, notify=accountChanged)
    def netbtSupported(self) -> bool:
        return self._netbt_supported

    @Property(bool, notify=accountChanged)
    def netbtEnabled(self) -> bool:
        return self._netbt_enabled

    @Property(bool, notify=accountChanged)
    def relaxedTimeoutsSupported(self) -> bool:
        return self._relaxed_timeouts_supported

    @Property(bool, notify=accountChanged)
    def relaxedTimeoutsEnabled(self) -> bool:
        return self._relaxed_timeouts_enabled

    @Property(bool, notify=accountChanged)
    def pmtudSupported(self) -> bool:
        return self._pmtud_supported

    @Property(bool, notify=accountChanged)
    def pmtudEnabled(self) -> bool:
        return self._pmtud_enabled

    @Property(bool, notify=accountChanged)
    def dohMssClampSupported(self) -> bool:
        return self._doh_mss_clamp_supported

    @Property(bool, notify=accountChanged)
    def dohMssClampEnabled(self) -> bool:
        return self._doh_mss_clamp_enabled

    @Property(str, notify=statsChanged)
    def sent(self) -> str:
        return self._sent

    @Property(str, notify=statsChanged)
    def received(self) -> str:
        return self._received

    @Property(str, notify=statsChanged)
    def latency(self) -> str:
        return self._latency

    @Property(str, notify=statsChanged)
    def loss(self) -> str:
        return self._loss

    @Property(str, notify=statsChanged)
    def endpointV4(self) -> str:
        return self._endpoint_v4

    @Property(str, notify=statsChanged)
    def endpointV6(self) -> str:
        return self._endpoint_v6

    @Property(str, notify=statsChanged)
    def handshake(self) -> str:
        return self._handshake

    @Property(str, notify=statsChanged)
    def uploadRate(self) -> str:
        return self._upload_rate

    @Property(str, notify=statsChanged)
    def downloadRate(self) -> str:
        return self._download_rate

    @Property("QVariantList", notify=statsChanged)
    def latencyHistory(self) -> list[float]:
        return self._latency_history

    @Property(QObject, constant=True)
    def dnsLogModel(self) -> QObject:
        return self._dns_logs

    @Property(QObject, constant=True)
    def appLogModel(self) -> QObject:
        return self._app_logs

    @Property(QObject, constant=True)
    def exclusionModel(self) -> QObject:
        return self._exclusions

    @Property(QObject, constant=True)
    def advancedHistoryModel(self) -> QObject:
        return self._advanced_changes

    @Property(str, constant=True)
    def currentVersion(self) -> str:
        return CURRENT_VERSION

    @Property(bool, notify=updateStateChanged)
    def updateChecking(self) -> bool:
        return self._update_checking

    @Property(str, notify=updateStateChanged)
    def latestPywarpVersion(self) -> str:
        return self._latest_pywarp_version

    @Property(str, notify=updateStateChanged)
    def latestWarpVersion(self) -> str:
        return self._latest_warp_version

    @Property(str, notify=updateStateChanged)
    def installedWarpVersion(self) -> str:
        return self._installed_warp_version

    @Property(bool, notify=updateStateChanged)
    def pywarpUpdateAvailable(self) -> bool:
        return self._pywarp_update_available

    @Property(bool, notify=updateStateChanged)
    def warpUpdateAvailable(self) -> bool:
        return self._warp_update_available

    @Property(str, notify=updateStateChanged)
    def updateError(self) -> str:
        return self._update_error

    @Property(bool, notify=updateStateChanged)
    def updateDownloading(self) -> bool:
        return self._update_downloading

    @Property(bool, notify=updateStateChanged)
    def canAutoUpdatePywarp(self) -> bool:
        return bool(self._pywarp_asset_url)

    @Property(str, notify=updateStateChanged)
    def pywarpAssetName(self) -> str:
        return self._pywarp_asset_name

    @Slot()
    def toggleConnection(self) -> None:
        if self._busy and not self.connecting:
            return
        self._connection_generation += 1
        generation = self._connection_generation
        previous_status = self._status
        previous_reason = self._reason
        previous_title = self._reason_title
        command = (
            "disconnect"
            if self._status in ("Connected", "Connecting")
            else "connect"
        )
        self._cancel_requested = (
            command == "disconnect" and previous_status == "Connecting"
        )
        self._connect_intent_deadline = (
            time.monotonic() + 45.0 if command == "connect" else 0.0
        )
        self._status = (
            "Disconnecting" if command == "disconnect" else "Connecting"
        )
        self._reason_title = (
            "Stopping the connection"
            if command == "disconnect"
            else "Starting a secure connection"
        )
        self._reason = (
            "Cancelling negotiation and restoring your normal route."
            if command == "disconnect" and previous_status == "Connecting"
            else "Restoring your normal network configuration."
            if command == "disconnect"
            else "Looking for the fastest route to Cloudflare."
        )
        self.stateChanged.emit()

        def rollback(message: str) -> None:
            if generation != self._connection_generation:
                return
            self._cancel_requested = False
            self._connect_intent_deadline = 0.0
            self._status = previous_status
            self._reason_title = previous_title
            self._reason = message.splitlines()[0] or previous_reason
            self.stateChanged.emit()
            self._append_event(
                "error",
                "Connection action failed",
                message.splitlines()[0],
                "ERROR",
            )
            self.toastRequested.emit("error", message.splitlines()[0])

        def success(_: CommandResult) -> None:
            if generation == self._connection_generation:
                QTimer.singleShot(8_000, self._resync_transition_status)

        self._run(
            [command],
            success=success,
            error=rollback,
            busy=False,
            report_errors=False,
        )

    @Slot(int)
    def navigateTo(self, page: int) -> None:
        self.navigationRequested.emit(page)

    @Slot(str)
    def navigateToSetting(self, kind: str) -> None:
        page = {
            "endpoint": 3,
            "compatibility": 3,
            "smart": 2,
        }.get(kind, 1)
        self.navigationRequested.emit(page)
        QTimer.singleShot(0, lambda: self.focusRequested.emit(kind))

    def _resync_transition_status(self) -> None:
        if self._status not in ("Connecting", "Disconnecting"):
            return
        if self._status_process.state() != QProcess.NotRunning:
            self._status_process.kill()
        else:
            self._start_status_stream()

    @Slot(str, str)
    def setMode(self, mode: str, proxy_port: str = "") -> None:
        if mode not in MODE_VALUES:
            self.toastRequested.emit("error", "Unsupported WARP mode.")
            return
        if mode == "proxy":
            try:
                port = int(proxy_port or self._proxy_port)
                if not 1 <= port <= 65535:
                    raise ValueError
            except ValueError:
                self.toastRequested.emit(
                    "error", "Proxy port must be between 1 and 65535."
                )
                return
            if self._protocol == "MASQUE" and self._masque_option == "h2-only":
                self.toastRequested.emit(
                    "error", "Proxy mode cannot use MASQUE HTTP/2 only."
                )
                return

            def proxy_saved() -> None:
                self._proxy_port = str(port)
                self._mode = mode
                self._save_setting("proxy_port", self._proxy_port)
                self._save_setting("mode", mode)
                self._set_busy(False)
                self.settingsChanged.emit()
                self.toastRequested.emit("success", "Proxy mode configured.")

            def proxy_failed(message: str) -> None:
                self._set_busy(False)
                self.toastRequested.emit("error", message.splitlines()[0])

            self._set_busy(True)
            self._run_command_chain(
                [
                    ["proxy", "port", str(port)],
                    ["mode", mode],
                ],
                on_complete=proxy_saved,
                on_error=proxy_failed,
            )
            return
        self._apply_mode(mode)

    def _apply_mode(self, mode: str) -> None:
        if mode == "proxy" and self._protocol == "MASQUE" and (
            self._masque_option == "h2-only"
        ):
            self.toastRequested.emit(
                "error", "Proxy mode cannot use MASQUE HTTP/2 only."
            )
            return

        def saved(_: CommandResult) -> None:
            self._mode = mode
            self._save_setting("mode", mode)
            self.settingsChanged.emit()

        self._run(
            ["mode", mode],
            success=saved,
            success_message=f"Mode changed to {mode}.",
        )

    @Slot(str)
    def setDnsFamily(self, family: str) -> None:
        aliases = {
            "Off (No DNS filtering)": "off",
            "Block Malware": "malware",
            "Block Adult Content": "full",
        }
        family = aliases.get(family, family)
        if family not in DNS_VALUES:
            self.toastRequested.emit("error", "Unsupported DNS family.")
            return

        def saved(_: CommandResult) -> None:
            self._dns_family = family
            self._save_setting("dns_mode", family)
            self.settingsChanged.emit()

        self._run(
            ["dns", "families", family],
            success=saved,
            success_message="DNS filtering updated.",
        )

    @Slot(str)
    def setProtocol(self, protocol: str) -> None:
        if protocol not in PROTOCOL_VALUES:
            self.toastRequested.emit("error", "Unsupported tunnel protocol.")
            return

        def saved(_: CommandResult) -> None:
            self._protocol = protocol
            self._save_setting("protocol", protocol)
            self.settingsChanged.emit()

        self._run(
            ["tunnel", "protocol", "set", protocol],
            success=saved,
            success_message=f"Protocol changed to {protocol}.",
        )

    @Slot(str)
    def setMasqueOption(self, option: str) -> None:
        if option not in MASQUE_VALUES:
            self.toastRequested.emit("error", "Unsupported MASQUE option.")
            return
        if option == "h2-only" and self._mode == "proxy":
            self.toastRequested.emit(
                "error", "HTTP/2 only is incompatible with Proxy mode."
            )
            return
        cli_value = (
            "h3-with-h2-fallback" if option == "auto" else option
        )

        def saved(_: CommandResult) -> None:
            self._masque_option = option
            self._save_setting("masque_option", option)
            self.settingsChanged.emit()

        self._run(
            ["tunnel", "masque-options", "set", cli_value],
            success=saved,
            success_message="MASQUE transport updated.",
        )

    @Slot(str)
    def setCustomEndpoint(self, endpoint: str) -> None:
        endpoint = endpoint.strip()
        if not endpoint:
            self.toastRequested.emit("error", "Enter an endpoint first.")
            return

        def saved(_: CommandResult) -> None:
            self._custom_endpoint = endpoint
            self._save_setting("custom_endpoint", endpoint)
            self._endpoint_history = [
                endpoint,
                *[item for item in self._endpoint_history if item != endpoint],
            ][:10]
            self._save_setting("endpoint_history", self._endpoint_history)
            self._record_advanced_change("Saved endpoint", "endpoint", endpoint)
            self.settingsChanged.emit()

        self._run(
            ["tunnel", "endpoint", "set", endpoint],
            success=saved,
            success_message="Custom endpoint saved.",
        )

    @Slot()
    def resetCustomEndpoint(self) -> None:
        def reset(_: CommandResult) -> None:
            self._custom_endpoint = ""
            self._save_setting("custom_endpoint", "")
            self._record_advanced_change(
                "Reset endpoint", "endpoint", "Cloudflare default"
            )
            self.settingsChanged.emit()

        self._run(
            ["tunnel", "endpoint", "reset"],
            success=reset,
            success_message="Endpoint reset.",
        )

    @Slot(str, str)
    def addExclusion(self, rule_type: str, value: str) -> None:
        rule_type = "host" if rule_type.lower() in ("host", "domain") else "ip"
        value = value.strip()
        if not self._valid_exclusion(rule_type, value):
            self.toastRequested.emit("error", "Enter a valid IP/CIDR or domain.")
            return
        def added(_: CommandResult) -> None:
            key = f"{rule_type}:{value}"
            self._rule_history = [
                key,
                *[item for item in self._rule_history if item != key],
            ][:12]
            self._save_setting("rule_history", self._rule_history)
            self._record_advanced_change(
                "Added bypass rule", rule_type, value
            )
            self.refreshExclusions()
            self.settingsChanged.emit()

        self._run(
            ["tunnel", rule_type, "add", value],
            success=added,
            success_message="Split-tunnel rule added.",
        )

    @Slot(str, str)
    def removeExclusion(self, rule_type: str, value: str) -> None:
        rule_type = "host" if rule_type.lower() in ("host", "domain") else "ip"
        def removed(_: CommandResult) -> None:
            self._record_advanced_change(
                "Removed bypass rule", rule_type, value
            )
            self.refreshExclusions()

        self._run(
            ["tunnel", rule_type, "remove", value],
            success=removed,
            success_message="Split-tunnel rule removed.",
        )

    @staticmethod
    def _valid_exclusion(rule_type: str, value: str) -> bool:
        if rule_type == "ip":
            try:
                ipaddress.ip_network(value, strict=False)
                return True
            except ValueError:
                return False
        return bool(
            re.fullmatch(
                r"(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}"
                r"[A-Za-z0-9])?\.)+[A-Za-z]{2,63}",
                value,
            )
        )

    @Slot()
    def resetExclusions(self) -> None:
        pending = {"count": 2}

        def finished(_: CommandResult) -> None:
            pending["count"] -= 1
            if pending["count"] == 0:
                self._record_advanced_change(
                    "Reset bypass rules", "all", "Manual rules cleared"
                )
                self.refreshExclusions()
                self.toastRequested.emit("success", "Manual exclusions reset.")

        self._run(["tunnel", "ip", "reset"], success=finished, busy=False)
        self._run(["tunnel", "host", "reset"], success=finished, busy=False)

    def _record_advanced_change(
        self, action: str, kind: str, value: str
    ) -> None:
        item = {
            "time": time.strftime("%H:%M"),
            "action": action,
            "kind": kind,
            "value": value,
        }
        self._advanced_changes.append(item)
        if not isinstance(self._advanced_history, list):
            self._advanced_history = []
        self._advanced_history = [*self._advanced_history[-29:], item]
        self._save_setting(
            "advanced_history",
            json.dumps(self._advanced_history, ensure_ascii=False),
        )

    def _run_command_chain(
        self,
        commands: list[list[str]],
        on_complete,
        on_error,
        should_continue=None,
        on_stopped=None,
    ) -> None:
        if should_continue is not None and not should_continue():
            if on_stopped:
                on_stopped()
            return
        if not commands:
            on_complete()
            return
        current, *remaining = commands
        self._runner.run(
            current,
            on_success=lambda _: self._run_command_chain(
                remaining,
                on_complete,
                on_error,
                should_continue,
                on_stopped,
            ),
            on_error=on_error,
        )

    @Slot()
    def startAutoSelection(self) -> None:
        self.startQuickSelection()

    def _start_smart_test(self, full_test: bool) -> None:
        if self._auto_selecting or self._busy:
            return
        if self._managed_account:
            self.toastRequested.emit(
                "error",
                "Smart route is unavailable for organization-managed profiles.",
            )
            return
        self._auto_full_test = full_test
        if full_test:
            self._auto_results = []
            self._smart_results.clear()
        self._auto_candidates = [
            ("MASQUE", "h3-with-h2-fallback", "warp"),
            ("MASQUE", "h3-only", "warp"),
            ("MASQUE", "h2-only", "warp"),
            ("WireGuard", None, "warp"),
            ("MASQUE", "h3-with-h2-fallback", "warp+doh"),
            ("MASQUE", "h3-only", "warp+doh"),
            ("MASQUE", "h2-only", "warp+doh"),
            ("WireGuard", None, "warp+doh"),
        ]
        self._auto_original = (
            self._protocol,
            self._masque_option,
            self._mode,
            self._custom_endpoint,
            self.connected,
        )
        self._auto_restore_pending = False
        self._auto_index = 0
        self._auto_test_index = 0
        self._auto_test_total = len(self._auto_candidates)
        self._auto_profile = (
            "Preparing full comparison"
            if full_test else "Preparing quick test"
        )
        self._auto_progress = 0
        self._auto_selecting = True
        self._set_busy(True)
        self._auto_message = (
            "Every profile will be measured for latency and packet loss."
            if full_test
            else "The first verified working profile will be selected."
        )
        self.autoSelectionChanged.emit()
        self._try_auto_candidate()

    @Slot()
    def startQuickSelection(self) -> None:
        self._start_smart_test(False)

    @Slot()
    def startFullSelection(self) -> None:
        self._start_smart_test(True)

    @Slot()
    def cancelAutoSelection(self) -> None:
        if not self._auto_selecting:
            return
        self._auto_selecting = False
        self._auto_message = "Selection cancelled."
        self.autoSelectionChanged.emit()
        self._restore_auto_original()

    def _disconnect_after_auto_cancel(self) -> None:
        self._restore_auto_original()

    def _try_auto_candidate(self) -> None:
        if not self._auto_selecting:
            return
        if self._auto_index >= len(self._auto_candidates):
            if self._auto_full_test:
                self._finish_full_smart_test()
            else:
                self._finish_auto_selection_failed()
            return

        protocol, masque, mode = self._auto_candidates[self._auto_index]
        self._auto_test_index = self._auto_index + 1
        self._auto_progress = int(
            (self._auto_index / len(self._auto_candidates)) * 100
        )
        transport = masque or "UDP"
        self._auto_profile = f"{protocol} · {transport} · {mode.upper()}"
        self._auto_message = (
            f"Testing {protocol} · {transport} · {mode.upper()}"
        )
        self.autoSelectionChanged.emit()

        commands = [
            ["disconnect"],
            ["tunnel", "protocol", "set", protocol],
            ["mode", mode],
        ]
        if masque:
            commands.append(["tunnel", "masque-options", "set", masque])
        commands.extend(
            [
                ["tunnel", "endpoint", "reset"],
                ["connect"],
            ]
        )
        self._run_command_chain(
            commands,
            on_complete=self._begin_auto_verification,
            on_error=self._smart_candidate_failed,
            should_continue=lambda: self._auto_selecting,
            on_stopped=self._disconnect_after_auto_cancel,
        )

    def _begin_auto_verification(self) -> None:
        self._auto_verify_deadline = time.monotonic() + 18
        self._poll_auto_connection()

    def _poll_auto_connection(self) -> None:
        if not self._auto_selecting:
            return
        if self.connected:
            self._verify_auto_candidate()
            return
        if time.monotonic() >= self._auto_verify_deadline:
            self._smart_candidate_failed("Connection timed out.")
            return
        QTimer.singleShot(600, self._poll_auto_connection)

    def _verify_auto_candidate(self) -> None:
        full_test = self._auto_full_test

        def verify() -> dict:
            attempts = 4 if full_test else 1
            samples: list[float] = []
            for _ in range(attempts):
                started = time.perf_counter()
                try:
                    response = requests.get(
                        "https://1.1.1.1/cdn-cgi/trace",
                        timeout=4,
                    )
                    response.raise_for_status()
                    samples.append(
                        (time.perf_counter() - started) * 1000
                    )
                except requests.RequestException:
                    pass
            if not samples:
                raise RuntimeError("No verification request succeeded.")
            return {
                "latency": round(sum(samples) / len(samples)),
                "loss": round(
                    ((attempts - len(samples)) / attempts) * 100, 1
                ),
            }

        self._runner.run_task(
            verify,
            on_success=self._smart_candidate_verified,
            on_error=self._smart_candidate_failed,
        )

    def _smart_result(
        self,
        working: bool,
        latency: int | None = None,
        loss: float | None = None,
        status: str = "",
    ) -> dict:
        protocol, masque, mode = self._auto_candidates[self._auto_index]
        transport = masque or "UDP"
        return {
            "profile": f"{protocol} · {transport} · {mode.upper()}",
            "protocol": protocol,
            "transport": transport,
            "mode": mode,
            "latency": f"{latency} ms" if latency is not None else "—",
            "loss": f"{loss:.1f}%" if loss is not None else "—",
            "latencyValue": latency if latency is not None else 999999,
            "lossValue": loss if loss is not None else 100.0,
            "status": status or ("Working" if working else "Failed"),
            "working": working,
            "recommended": False,
            "masque": masque or "",
        }

    def _publish_smart_results(self) -> None:
        ordered = sorted(
            self._auto_results,
            key=lambda item: (
                not bool(item.get("working")),
                float(item.get("lossValue", 100)),
                int(item.get("latencyValue", 999999)),
            ),
        )
        for index, item in enumerate(ordered):
            item["recommended"] = bool(
                index == 0 and item.get("working")
            )
        self._auto_results = ordered
        self._smart_results.replace(ordered)
        self._save_setting(
            "smart_test_results",
            json.dumps(ordered, ensure_ascii=False),
        )
        self.autoSelectionChanged.emit()

    def _smart_candidate_verified(self, result: object) -> None:
        if not self._auto_selecting:
            return
        if not self._auto_full_test:
            self._finish_auto_selection_success()
            return
        metrics = dict(result)
        self._auto_results.append(
            self._smart_result(
                True,
                int(metrics.get("latency", 0)),
                float(metrics.get("loss", 0)),
                "Verified",
            )
        )
        self._publish_smart_results()
        self._advance_auto_candidate()

    def _smart_candidate_failed(self, message: str) -> None:
        if not self._auto_selecting:
            return
        if self._auto_full_test:
            self._auto_results.append(
                self._smart_result(
                    False,
                    status=message.splitlines()[0] or "Failed",
                )
            )
            self._publish_smart_results()
        self._advance_auto_candidate()

    def _advance_auto_candidate(self) -> None:
        if not self._auto_selecting:
            return
        self._auto_index += 1
        QTimer.singleShot(250, self._try_auto_candidate)

    def _finish_auto_selection_success(self) -> None:
        if not self._auto_selecting:
            return
        protocol, masque, mode = self._auto_candidates[self._auto_index]
        self._protocol = protocol
        self._mode = mode
        self._save_setting("protocol", protocol)
        self._save_setting("mode", mode)
        if masque:
            self._masque_option = masque
            self._save_setting("masque_option", masque)
        self._custom_endpoint = ""
        self._save_setting("custom_endpoint", "")
        self._auto_progress = 100
        self._auto_test_index = self._auto_index + 1
        self._auto_profile = f"{protocol} · {mode.upper()}"
        self._auto_message = f"Selected {protocol} · {mode.upper()}"
        self._auto_selecting = False
        self._auto_original = None
        self._set_busy(False)
        self.settingsChanged.emit()
        self.autoSelectionChanged.emit()
        self.toastRequested.emit(
            "success", "First verified working profile selected."
        )

    def _finish_full_smart_test(self) -> None:
        self._auto_progress = 100
        self._auto_test_index = self._auto_test_total
        working = sum(
            1 for result in self._auto_results
            if result.get("working")
        )
        self._auto_profile = "Full comparison complete"
        self._auto_message = (
            f"{working} of {self._auto_test_total} profiles worked. "
            "Choose any verified result below."
        )
        self._auto_selecting = False
        self._publish_smart_results()
        self.toastRequested.emit(
            "success" if working else "error",
            "Full Smart Route comparison completed."
            if working
            else "Full comparison finished without a working profile.",
        )
        self._restore_auto_original()

    @Slot(int)
    def applySmartResult(self, index: int) -> None:
        if (
            self._auto_selecting
            or self._busy
            or not 0 <= index < len(self._auto_results)
        ):
            return
        result = self._auto_results[index]
        if not result.get("working"):
            return
        protocol = str(result.get("protocol", ""))
        mode = str(result.get("mode", ""))
        masque = str(result.get("masque", "")) or None
        if protocol not in PROTOCOL_VALUES or mode not in MODE_VALUES:
            return
        commands = [
            ["disconnect"],
            ["tunnel", "protocol", "set", protocol],
            ["mode", mode],
        ]
        if masque:
            commands.append(
                ["tunnel", "masque-options", "set", masque]
            )
        commands.extend(
            [["tunnel", "endpoint", "reset"], ["connect"]]
        )
        self._set_busy(True)

        def applied() -> None:
            self._protocol = protocol
            self._mode = mode
            self._masque_option = masque or self._masque_option
            self._custom_endpoint = ""
            self._save_setting("protocol", protocol)
            self._save_setting("mode", mode)
            if masque:
                self._save_setting("masque_option", masque)
            self._save_setting("custom_endpoint", "")
            self._set_busy(False)
            self.settingsChanged.emit()
            self.toastRequested.emit(
                "success",
                f"Applied {result.get('profile', 'Smart Route profile')}.",
            )

        def failed(message: str) -> None:
            self._set_busy(False)
            self.toastRequested.emit(
                "error", message.splitlines()[0]
            )

        self._run_command_chain(
            commands,
            on_complete=applied,
            on_error=failed,
        )

    def _finish_auto_selection_failed(self) -> None:
        self._auto_selecting = False
        self._auto_profile = "No verified profile"
        self._auto_message = "No working profile was found."
        self.autoSelectionChanged.emit()
        self.toastRequested.emit(
            "error", "No connection profile passed the network test."
        )
        self._restore_auto_original()

    def _restore_auto_original(self) -> None:
        original = self._auto_original
        if self._auto_restore_pending:
            return
        if not original:
            self._set_busy(False)
            return
        self._auto_restore_pending = True

        self._runner.run_when_idle(
            lambda saved=original: self._run_auto_restore(saved)
        )

    def _run_auto_restore(
        self, original: tuple[str, str, str, str, bool]
    ) -> None:
        protocol, masque, mode, endpoint, was_connected = original
        commands = [
            ["disconnect"],
            ["tunnel", "protocol", "set", protocol],
            ["mode", mode],
        ]
        if protocol == "MASQUE":
            commands.append(
                [
                    "tunnel",
                    "masque-options",
                    "set",
                    "h3-with-h2-fallback" if masque == "auto" else masque,
                ]
            )
        commands.append(
            ["tunnel", "endpoint", "set", endpoint]
            if endpoint
            else ["tunnel", "endpoint", "reset"]
        )
        if was_connected:
            commands.append(["connect"])

        def restored() -> None:
            self._auto_restore_pending = False
            self._auto_original = None
            self._set_busy(False)
            self.settingsChanged.emit()

        self._run_command_chain(
            commands,
            on_complete=restored,
            on_error=lambda _: restored(),
        )

    @Slot()
    def refreshExclusions(self) -> None:
        collected: dict[str, list[dict]] = {"ip": [], "host": []}
        pending = {"count": 2}

        def parsed(rule_type: str, result: CommandResult) -> None:
            try:
                data = json.loads(result.stdout)
                values = data if isinstance(data, list) else (
                    data.get("entries")
                    or data.get(rule_type)
                    or data.get("items")
                    or []
                )
                collected[rule_type] = [
                    {"type": rule_type, "value": str(value)}
                    for value in values
                ]
            except (json.JSONDecodeError, AttributeError):
                collected[rule_type] = []
            pending["count"] -= 1
            if pending["count"] == 0:
                self._exclusions.replace(
                    collected["ip"] + collected["host"]
                )

        for rule_type in ("ip", "host"):
            self._runner.run(
                ["-j", "tunnel", rule_type, "list"],
                on_success=lambda result, kind=rule_type: parsed(kind, result),
                on_error=lambda _: None,
            )

    @Slot(bool)
    def setDnsLogging(self, enabled: bool) -> None:
        command = "enable" if enabled else "disable"

        def saved(_: CommandResult) -> None:
            self._dns_logging = enabled
            self._save_setting("dns_log_enabled", enabled)
            self.settingsChanged.emit()

        self._run(
            ["dns", "log", command],
            success=saved,
            success_message=f"DNS logging {command}d.",
        )

    @Slot()
    def refreshStats(self) -> None:
        if not self.connected or self._stats_pending:
            return
        self._stats_pending = True

        def parsed(result: CommandResult) -> None:
            try:
                data = json.loads(result.stdout)
            except json.JSONDecodeError:
                return
            now = time.monotonic()
            self._protocol = self._normalize_protocol(
                data.get("protocol"),
                self._protocol,
            )
            self._endpoint_v4 = str(data.get("v4_endpoint", "—"))
            self._endpoint_v6 = str(data.get("v6_endpoint", "—"))
            sent = float(data.get("bytes_sent", 0) or 0)
            received = float(data.get("bytes_received", 0) or 0)
            self._sent = self._format_bytes(sent)
            self._received = self._format_bytes(received)
            latency = data.get("estimated_latency_ms")
            loss = data.get("estimated_loss")
            handshake = data.get("secs_since_last_handshake")
            self._latency = f"{latency} ms" if latency is not None else "—"
            if loss is not None and float(loss) >= 0:
                self._loss = f"{float(loss) * 100:.2f}%"
            else:
                self._loss = "—"
            self._handshake = f"{handshake}s ago" if handshake is not None else "—"
            if (
                self._last_stats_at is not None
                and self._last_bytes_sent is not None
                and self._last_bytes_received is not None
            ):
                elapsed = max(now - self._last_stats_at, 0.1)
                upload = max(0.0, sent - self._last_bytes_sent) / elapsed
                download = max(
                    0.0, received - self._last_bytes_received
                ) / elapsed
                self._upload_rate = f"{self._format_bytes(upload)}/s"
                self._download_rate = f"{self._format_bytes(download)}/s"
            self._last_stats_at = now
            self._last_bytes_sent = sent
            self._last_bytes_received = received
            if latency is not None:
                try:
                    self._latency_history = [
                        *self._latency_history[-29:],
                        float(latency),
                    ]
                except (TypeError, ValueError):
                    pass
            self._last_updated = time.strftime("Updated %H:%M:%S")
            self.statsChanged.emit()
            self.stateChanged.emit()
            self.settingsChanged.emit()

        def complete() -> None:
            self._stats_pending = False

        self._run(
            ["-j", "tunnel", "stats"],
            success=parsed,
            busy=False,
            report_errors=False,
            on_finished=complete,
        )

    @Slot()
    def refreshPublicIp(self) -> None:
        if self._ip_pending:
            return
        self._ip_pending = True
        requested_language = self._language
        proxy = None
        if self._mode == "proxy" and self.connected:
            address = f"socks5h://127.0.0.1:{self._proxy_port}"
            proxy = {"http": address, "https": address}

        def fetch() -> dict:
            session = requests.Session()
            session.trust_env = False
            try:
                trace = session.get(
                    "https://1.1.1.1/cdn-cgi/trace",
                    proxies=proxy,
                    timeout=8,
                )
                trace.raise_for_status()
                trace_data = dict(
                    line.split("=", 1)
                    for line in trace.text.splitlines()
                    if "=" in line
                )
                observed_ip = str(trace_data.get("ip", "")).strip()
            except requests.RequestException:
                ip_response = session.get(
                    "https://api.ipify.org",
                    params={"format": "json"},
                    proxies=proxy,
                    timeout=8,
                )
                ip_response.raise_for_status()
                observed_ip = str(ip_response.json().get("ip", "")).strip()
            ipaddress.ip_address(observed_ip)
            try:
                response = session.get(
                    f"https://ipwho.is/{observed_ip}",
                    params={
                        "lang": {
                            "fa": "en",
                            "zh_CN": "zh-CN",
                        }.get(requested_language, requested_language)
                    },
                    proxies=proxy,
                    timeout=8,
                )
                response.raise_for_status()
                data = response.json()
                if data.get("success") is False:
                    raise RuntimeError(
                        str(data.get("message", "Location unavailable"))
                    )
                country_code = str(
                    data.get("country_code", "")
                ).upper()
                country_name = str(
                    data.get("country", "Locating…")
                )
            except (requests.RequestException, RuntimeError, ValueError):
                country_code = ""
                country_name = "Locating…"
            if requested_language == "fa" and country_code:
                country_name = str(
                    self._persian_country_names.get(
                        country_code, country_name
                    )
                )
            return {
                "ip": observed_ip,
                "country": country_name,
                "code": country_code,
            }

        def has_cached_location() -> bool:
            try:
                ipaddress.ip_address(self._public_ip)
            except ValueError:
                return False
            return len(self._country_code) == 2

        def apply(result: object) -> None:
            data = dict(result)
            if (
                (self.transitioning or self._auto_selecting)
                and not data.get("code")
                and has_cached_location()
            ):
                self._last_updated = "Waiting for the route to respond"
                self.stateChanged.emit()
                return
            self._public_ip = data.get("ip", "Unavailable")
            self._country_name = data.get("country", "Unknown location")
            self._country_code = data.get("code", "")
            if len(self._country_code) == 2:
                self._country_flag = "".join(
                    chr(0x1F1E6 + ord(letter) - ord("A"))
                    for letter in self._country_code
                )
            else:
                self._country_flag = "—"
            self.stateChanged.emit()

        def unavailable(_: str) -> None:
            if self.transitioning or self._auto_selecting:
                if not has_cached_location():
                    self._public_ip = "Looking up…"
                    self._country_name = "Connecting…"
                    self._country_code = ""
                    self._country_flag = "—"
                self._last_updated = "Waiting for the route to respond"
                self.stateChanged.emit()
                return
            self._public_ip = "Unavailable"
            self._country_name = "Location unavailable"
            self._country_code = ""
            self._country_flag = "—"
            self.stateChanged.emit()

        def finished() -> None:
            self._ip_pending = False
            if requested_language != self._language:
                self.refreshPublicIp()

        self._runner.run_task(
            fetch,
            on_success=apply,
            on_error=unavailable,
            on_finished=finished,
        )

    @Slot()
    def refreshAppLogs(self) -> None:
        self._app_logs.replace(self._activity_items[-300:])

    def _detect_cli_capabilities(self) -> None:
        pending = {"count": 4}
        output = {
            "root": "",
            "registration": "",
            "tunnel": "",
            "debug": "",
        }

        def received(kind: str, result: CommandResult) -> None:
            output[kind] = result.stdout
            finished()

        def finished() -> None:
            pending["count"] -= 1
            if pending["count"]:
                return
            registration_help = output["registration"].lower()
            root_help = output["root"].lower()
            tunnel_help = output["tunnel"].lower()
            debug_help = output["debug"].lower()
            self._accept_tos_flag = "--accept-tos" in root_help
            if "organization" in registration_help:
                self._team_enroll_style = "registration"
            elif "teams-enroll" in root_help:
                self._team_enroll_style = "teams"
            self._netbt_supported = (
                self._platform_name == "Windows" and "netbt" in tunnel_help
            )
            self._relaxed_timeouts_supported = (
                "high-timeouts" in debug_help
            )
            self._pmtud_supported = "pmtud" in tunnel_help
            self._doh_mss_clamp_supported = (
                "doh-mss-clamp" in tunnel_help
            )
            self.accountChanged.emit()
            self.refreshCompatibilityOptions()

        for kind, args in (
            ("root", ["--help"]),
            ("registration", ["registration", "new", "--help"]),
            ("tunnel", ["tunnel", "--help"]),
            ("debug", ["debug", "--help"]),
        ):
            self._runner.run(
                args,
                on_success=lambda result, key=kind: received(key, result),
                on_error=lambda _, key=kind: finished(),
            )

    @Slot()
    def refreshRegistration(self) -> None:
        if self._registration_busy:
            return
        self._registration_busy = True
        self.accountChanged.emit()

        def registration_loaded(result: CommandResult) -> None:
            try:
                data = json.loads(result.stdout)
            except json.JSONDecodeError:
                data = {}
            account = data.get("account") or {}
            self._registered = bool(data)
            self._account_type = str(
                account.get("type") or data.get("type") or "Consumer"
            )
            self._license_key = str(account.get("license") or "")
            self._device_id = str(data.get("device_id") or "")
            account_managed = account.get("managed")
            self._managed_account = bool(
                account_managed
                if account_managed is not None
                else self._account_type.lower()
                in ("managed", "team", "teams", "organization")
            ) or bool(self._organization)

        def no_registration(_: str) -> None:
            self._registered = False
            self._account_type = ""
            self._license_key = ""
            self._device_id = ""
            self._organization = ""
            self._support_url = ""
            self._managed_account = False
            self._registration_devices = []

        def registration_finished() -> None:
            self._registration_loaded = True
            self._registration_busy = False
            self.accountChanged.emit()

        self._runner.run(
            ["-j", "registration", "show"],
            on_success=registration_loaded,
            on_error=no_registration,
            on_finished=registration_finished,
        )

        def devices_loaded(result: CommandResult) -> None:
            try:
                data = json.loads(result.stdout)
                devices = data if isinstance(data, list) else []
            except json.JSONDecodeError:
                devices = []
            self._registration_devices = [
                {
                    "model": str(device.get("model") or "Unknown"),
                    "os": str(device.get("os") or "Unknown"),
                    "active": bool(device.get("active")),
                }
                for device in devices
                if isinstance(device, dict)
            ]
            self.accountChanged.emit()

        self._runner.run(
            ["-j", "registration", "devices"],
            on_success=devices_loaded,
            on_error=lambda _: None,
        )

        def organization_loaded(result: CommandResult) -> None:
            value = result.stdout.strip().strip('"')
            if value.lower() in (
                "none",
                "null",
                "no organization",
                "no organization found",
            ):
                value = ""
            self._organization = value
            if value:
                self._managed_account = True
                self._account_type = "Zero Trust"
            self.accountChanged.emit()

        self._runner.run(
            ["registration", "organization"],
            on_success=organization_loaded,
            on_error=lambda _: None,
        )
        self._runner.run(
            ["settings", "support-url"],
            on_success=lambda result: self._set_support_url(result.stdout),
            on_error=lambda _: None,
        )
        self._runner.run(
            ["settings", "mode-switch-allowed"],
            on_success=lambda result: self._set_mode_switch_allowed(
                result.stdout
            ),
            on_error=lambda _: None,
        )

    def _set_support_url(self, value: str) -> None:
        self._support_url = value.strip()
        self.accountChanged.emit()

    def _set_mode_switch_allowed(self, value: str) -> None:
        self._mode_switch_allowed = value.strip().lower() == "true"
        self.accountChanged.emit()

    def _registration_complete(self, message: str) -> None:
        self._registration_busy = False
        self.toastRequested.emit("success", message)
        self.accountChanged.emit()
        QTimer.singleShot(900, self.refreshRegistration)

    def _registration_failed(self, message: str) -> None:
        self._registration_busy = False
        self.accountChanged.emit()
        self.toastRequested.emit("error", message.splitlines()[0])

    def _replace_registration(
        self,
        final_args: list[str],
        message: str,
        accept_after: bool = False,
    ) -> None:
        if self._registration_busy:
            return
        self._registration_busy = True
        self.accountChanged.emit()

        def enroll() -> None:
            def enrolled(_: CommandResult) -> None:
                if not accept_after:
                    self._registration_complete(message)
                    return
                self._runner.run(
                    ["accept-tos"],
                    on_success=lambda _: self._registration_complete(message),
                    on_error=self._registration_failed,
                )

            self._runner.run(
                final_args,
                on_success=enrolled,
                on_error=self._registration_failed,
                timeout=120,
            )

        def remove_existing() -> None:
            if not self._registered:
                enroll()
                return
            self._runner.run(
                ["registration", "delete"],
                on_success=lambda _: enroll(),
                on_error=self._registration_failed,
            )

        self._runner.run(
            ["disconnect"],
            on_success=lambda _: remove_existing(),
            on_error=lambda _: remove_existing(),
        )

    @Slot()
    def createConsumerRegistration(self) -> None:
        self._replace_registration(
            (
                ["--accept-tos", "registration", "new"]
                if self._accept_tos_flag
                else ["registration", "new"]
            ),
            "Personal WARP registration created.",
            accept_after=not self._accept_tos_flag,
        )

    @Slot(str)
    def enrollTeam(self, organization: str) -> None:
        organization = organization.strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,62}", organization):
            self.toastRequested.emit(
                "error", "Enter a valid Zero Trust organization name."
            )
            return
        if not self._team_enroll_style:
            self.toastRequested.emit(
                "error", "Team enrollment is not supported by this warp-cli."
            )
            return
        args = (
            (
                ["--accept-tos", "registration", "new", organization]
                if self._accept_tos_flag
                else ["registration", "new", organization]
            )
            if self._team_enroll_style == "registration"
            else ["teams-enroll", organization]
        )
        self._replace_registration(
            args, f"Enrollment started for {organization}."
        )

    @Slot()
    def deleteRegistration(self) -> None:
        if self._registration_busy:
            return
        self._registration_busy = True
        self.accountChanged.emit()

        def remove() -> None:
            self._runner.run(
                ["registration", "delete"],
                on_success=lambda _: self._registration_complete(
                    "WARP registration deleted."
                ),
                on_error=self._registration_failed,
            )

        self._runner.run(
            ["disconnect"],
            on_success=lambda _: remove(),
            on_error=lambda _: remove(),
        )

    @Slot(str)
    def setRegistrationLicense(self, key: str) -> None:
        key = key.strip()
        if not key:
            self.toastRequested.emit("error", "Enter a license key.")
            return
        self._registration_busy = True
        self.accountChanged.emit()
        self._runner.run(
            ["registration", "license", key],
            on_success=lambda _: self._registration_complete(
                "WARP license updated."
            ),
            on_error=self._registration_failed,
        )

    @Slot()
    def openTeamSupport(self) -> None:
        if self._support_url.startswith(("https://", "http://")):
            QDesktopServices.openUrl(QUrl(self._support_url))

    @Slot()
    def refreshNetbt(self) -> None:
        self.refreshCompatibilityOptions()

    @Slot()
    def refreshCompatibilityOptions(self) -> None:
        if not any(
            (
                self._netbt_supported,
                self._relaxed_timeouts_supported,
                self._pmtud_supported,
                self._doh_mss_clamp_supported,
            )
        ):
            return

        def loaded(result: CommandResult) -> None:
            patterns = (
                ("_netbt_enabled", r"NetBT[^\n:]*(?::|=)\s*(true|false)"),
                (
                    "_relaxed_timeouts_enabled",
                    r"(?:high|relaxed)[^\n]*(?:timeout)[^\n:]*(?::|=)\s*(true|false)",
                ),
                (
                    "_pmtud_enabled",
                    r"(?:enable[_ -]?)?pmtud[^\n:]*(?::|=)\s*(true|false)",
                ),
                (
                    "_doh_mss_clamp_enabled",
                    r"(?:doh)[^\n]*(?:mss)[^\n:]*(?::|=)\s*(true|false)",
                ),
            )
            for attribute, pattern in patterns:
                match = re.search(pattern, result.stdout, re.IGNORECASE)
                if match:
                    setattr(
                        self,
                        attribute,
                        match.group(1).lower() == "true",
                    )
            self.accountChanged.emit()

        self._runner.run(
            ["settings", "list"],
            on_success=loaded,
            on_error=lambda _: None,
        )

    @Slot(bool)
    def setNetbt(self, enabled: bool) -> None:
        if not self._netbt_supported:
            return

        def saved(_: CommandResult) -> None:
            self._netbt_enabled = enabled
            self.accountChanged.emit()

        self._run(
            ["tunnel", "netbt", "enable" if enabled else "disable"],
            success=saved,
            success_message=(
                "NetBIOS over TCP/IP enabled."
                if enabled
                else "NetBIOS over TCP/IP disabled."
            ),
        )

    @Slot()
    def resetNetbt(self) -> None:
        if not self._netbt_supported:
            return
        self._run(
            ["tunnel", "netbt", "reset"],
            success=lambda _: self.refreshNetbt(),
            success_message="NetBIOS setting restored to policy default.",
        )

    def _set_compatibility_option(
        self,
        supported: bool,
        args: list[str],
        attribute: str,
        enabled: bool,
        message: str,
    ) -> None:
        if not supported:
            return

        def saved(_: CommandResult) -> None:
            setattr(self, attribute, enabled)
            self.accountChanged.emit()

        self._run(args, success=saved, success_message=message)

    @Slot(bool)
    def setRelaxedTimeouts(self, enabled: bool) -> None:
        self._set_compatibility_option(
            self._relaxed_timeouts_supported,
            [
                "debug",
                "high-timeouts",
                "enable" if enabled else "disable",
            ],
            "_relaxed_timeouts_enabled",
            enabled,
            (
                "Relaxed connection timeouts enabled."
                if enabled
                else "Relaxed connection timeouts disabled."
            ),
        )

    @Slot()
    def resetRelaxedTimeouts(self) -> None:
        self._run(
            ["debug", "high-timeouts", "reset"],
            success=lambda _: self.refreshCompatibilityOptions(),
            success_message="Connection timeouts restored to default.",
        )

    @Slot(bool)
    def setPmtud(self, enabled: bool) -> None:
        self._set_compatibility_option(
            self._pmtud_supported,
            ["tunnel", "pmtud", "enable" if enabled else "disable"],
            "_pmtud_enabled",
            enabled,
            (
                "MASQUE path MTU discovery enabled."
                if enabled
                else "MASQUE path MTU discovery disabled."
            ),
        )

    @Slot()
    def resetPmtud(self) -> None:
        self._run(
            ["tunnel", "pmtud", "reset"],
            success=lambda _: self.refreshCompatibilityOptions(),
            success_message="Path MTU discovery restored to default.",
        )

    @Slot(bool)
    def setDohMssClamp(self, enabled: bool) -> None:
        self._set_compatibility_option(
            self._doh_mss_clamp_supported,
            [
                "tunnel",
                "doh-mss-clamp",
                "enable" if enabled else "disable",
            ],
            "_doh_mss_clamp_enabled",
            enabled,
            (
                "DoH MSS clamping enabled."
                if enabled
                else "DoH MSS clamping disabled."
            ),
        )

    @Slot()
    def resetDohMssClamp(self) -> None:
        self._run(
            ["tunnel", "doh-mss-clamp", "reset"],
            success=lambda _: self.refreshCompatibilityOptions(),
            success_message="DoH MSS clamping restored to default.",
        )

    @Slot(str)
    def setTheme(self, theme: str) -> None:
        if theme not in ("system", "dark", "light", "aurora"):
            return
        self._theme = theme
        self._save_setting("theme", theme)
        self.settingsChanged.emit()

    @Slot()
    def prepareToQuit(self) -> None:
        """Disconnect WARP before allowing the application to terminate."""
        if self._shutdown_pending:
            return
        self._shutdown_pending = True
        self._cancel_requested = True
        self._auto_selecting = False
        self._connection_generation += 1
        self._stats_timer.stop()
        self._status_watchdog.stop()
        self._ip_refresh_timer.stop()
        if self._status_process.state() != QProcess.NotRunning:
            self._status_process.finished.disconnect(self._restart_status_stream)
            self._status_process.kill()
        if self._status in ("Connected", "Connecting"):
            self._status = "Disconnecting"
            self.stateChanged.emit()
        self._runner.run_when_idle(self._disconnect_for_shutdown)

    def _disconnect_for_shutdown(self) -> None:
        self._runner.run(
            ["disconnect"],
            on_finished=self.shutdownReady.emit,
            timeout=10,
        )

    @Slot(bool)
    def setCompactMode(self, enabled: bool) -> None:
        self._compact_mode = enabled
        self._save_setting("compact_mode", enabled)
        self.settingsChanged.emit()

    @Slot()
    def toggleCompactMode(self) -> None:
        self.setCompactMode(not self._compact_mode)

    @Slot(str)
    def setLanguage(self, language: str) -> None:
        if language not in ("en", "fa", "ru", "zh_CN"):
            return
        self._language = language
        self._save_setting("language", language)
        self.settingsChanged.emit()
        self.refreshPublicIp()

    @Slot()
    def refreshWarpInstallation(self) -> None:
        self._warp_installed = find_warp_cli() is not None
        self.settingsChanged.emit()

    @staticmethod
    def _linux_os_release() -> dict[str, str]:
        values: dict[str, str] = {}
        try:
            for line in Path("/etc/os-release").read_text(
                encoding="utf-8"
            ).splitlines():
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key] = value.strip().strip("\"'")
        except OSError:
            pass
        return values

    @staticmethod
    def _run_installer_command(
        args: list[str], timeout: int = 900
    ) -> None:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if completed.returncode:
            message = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(
                message or f"Installer exited with code {completed.returncode}."
            )

    def _install_warp_linux_task(self) -> str:
        if platform.system() != "Linux":
            raise RuntimeError("Automatic installation is available on Linux only.")
        pkexec = shutil.which("pkexec")
        if not pkexec:
            raise RuntimeError(
                "PolicyKit (pkexec) is required for automatic installation."
            )
        package_manager = next(
            (
                name
                for name in ("apt-get", "dnf", "yum")
                if shutil.which(name)
            ),
            "",
        )
        if not package_manager:
            raise RuntimeError(
                "Supported package manager not found (apt, dnf, or yum)."
            )

        with tempfile.TemporaryDirectory(prefix="pywarp-install-") as temp:
            temp_path = Path(temp)
            script_path = temp_path / "install-warp.sh"
            if package_manager == "apt-get":
                release = self._linux_os_release()
                codename = release.get("VERSION_CODENAME", "")
                if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", codename):
                    raise RuntimeError(
                        "Could not determine a supported distribution codename."
                    )
                key_path = temp_path / "cloudflare-warp-key.gpg"
                response = requests.get(
                    "https://pkg.cloudflareclient.com/pubkey.gpg",
                    timeout=20,
                )
                response.raise_for_status()
                key_path.write_bytes(response.content)
                script = f"""#!/usr/bin/env bash
set -euo pipefail
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates gpg
install -d -m 0755 /usr/share/keyrings
gpg --batch --yes --dearmor -o /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg "$1"
printf '%s\\n' 'deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ {codename} main' > /etc/apt/sources.list.d/cloudflare-client.list
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y cloudflare-warp
"""
                script_path.write_text(script, encoding="utf-8")
                script_path.chmod(0o700)
                self._run_installer_command(
                    [pkexec, "bash", str(script_path), str(key_path)]
                )
            else:
                repo_path = temp_path / "cloudflare-warp.repo"
                response = requests.get(
                    "https://pkg.cloudflareclient.com/"
                    "cloudflare-warp-ascii.repo",
                    timeout=20,
                )
                response.raise_for_status()
                repo_path.write_bytes(response.content)
                script = f"""#!/usr/bin/env bash
set -euo pipefail
install -m 0644 "$1" /etc/yum.repos.d/cloudflare-warp.repo
{package_manager} install -y cloudflare-warp
"""
                script_path.write_text(script, encoding="utf-8")
                script_path.chmod(0o700)
                self._run_installer_command(
                    [pkexec, "bash", str(script_path), str(repo_path)]
                )

        executable = find_warp_cli()
        if not executable:
            raise RuntimeError(
                "Installation completed, but warp-cli was not found on PATH."
            )
        registration = subprocess.run(
            [executable, "--accept-tos", "registration", "new"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if registration.returncode:
            output = (registration.stdout + registration.stderr).lower()
            already_registered = "already" in output and "register" in output
            unsupported_flag = (
                "accept-tos" in output
                and any(word in output for word in ("unknown", "unexpected"))
            )
            if unsupported_flag:
                self._run_installer_command(
                    [executable, "registration", "new"], timeout=120
                )
                self._run_installer_command(
                    [executable, "accept-tos"], timeout=60
                )
            elif not already_registered:
                raise RuntimeError(
                    registration.stderr.strip()
                    or registration.stdout.strip()
                    or "WARP registration failed."
                )
        return "Cloudflare WARP was installed and registered successfully."

    @Slot()
    def installWarpLinux(self) -> None:
        if self._warp_installing:
            return
        if self._platform_name != "Linux":
            self.toastRequested.emit(
                "error", "Automatic installation is available on Linux only."
            )
            return
        self._warp_installing = True
        self._warp_install_message = (
            "Waiting for administrator approval and installing WARP…"
        )
        self.installStateChanged.emit()

        def installed(result: object) -> None:
            self._warp_installed = find_warp_cli() is not None
            self._warp_install_message = str(result)
            self.settingsChanged.emit()
            self.toastRequested.emit("success", str(result))
            if self._warp_installed:
                self._detect_cli_capabilities()
                self._start_status_stream()
                self.refreshRegistration()

        def failed(message: str) -> None:
            self._warp_installed = find_warp_cli() is not None
            self._warp_install_message = message.splitlines()[0]
            self.settingsChanged.emit()
            self.toastRequested.emit(
                "error", self._warp_install_message
            )

        def finished() -> None:
            self._warp_installing = False
            self.installStateChanged.emit()

        self._runner.run_task(
            self._install_warp_linux_task,
            on_success=installed,
            on_error=failed,
            on_finished=finished,
        )

    @Slot()
    def openWarpDownload(self) -> None:
        QDesktopServices.openUrl(
            QUrl(
                "https://developers.cloudflare.com/cloudflare-one/"
                "connections/connect-devices/warp/download-warp/"
            )
        )

    @Slot()
    def openWarpApplication(self) -> None:
        launched = False
        try:
            if self._platform_name == "Darwin":
                subprocess.Popen(
                    ["open", "-a", "Cloudflare WARP"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                launched = True
            elif self._platform_name == "Windows":
                candidates = [
                    Path(os.environ.get("ProgramFiles", ""))
                    / "Cloudflare"
                    / "Cloudflare WARP"
                    / "Cloudflare WARP.exe",
                    Path(os.environ.get("LOCALAPPDATA", ""))
                    / "Cloudflare"
                    / "Cloudflare WARP"
                    / "Cloudflare WARP.exe",
                ]
                executable = next(
                    (path for path in candidates if path.is_file()), None
                )
                if executable:
                    subprocess.Popen([str(executable)])
                    launched = True
            else:
                taskbar = shutil.which("warp-taskbar")
                if taskbar:
                    subprocess.Popen(
                        [taskbar],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    launched = True
                elif shutil.which("gtk-launch"):
                    for desktop_id in (
                        "com.cloudflare.Warp",
                        "cloudflare-warp",
                    ):
                        result = subprocess.run(
                            ["gtk-launch", desktop_id],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=3,
                            check=False,
                        )
                        if result.returncode == 0:
                            launched = True
                            break
        except (OSError, subprocess.SubprocessError):
            launched = False

        if launched:
            self._append_event(
                "update",
                "Opened Cloudflare WARP",
                "The official client will handle its own update.",
                "INFO",
            )
        else:
            self.toastRequested.emit(
                "error",
                "Could not open the WARP app. Opening official help instead.",
            )
            self.openWarpDownload()

    @Slot(str)
    def openExternalUrl(self, url: str) -> None:
        if url.startswith(("https://", "http://")):
            QDesktopServices.openUrl(QUrl(url))

    @staticmethod
    def _version_tuple(value: str) -> tuple[int, ...]:
        numbers = re.findall(r"\d+", value or "")
        return tuple(int(number) for number in numbers[:4])

    @staticmethod
    def _linux_codename() -> str:
        try:
            text = Path("/etc/os-release").read_text(
                encoding="utf-8", errors="ignore"
            )
            match = re.search(
                r"^VERSION_CODENAME=(.+)$", text, re.MULTILINE
            )
            if match:
                return match.group(1).strip().strip('"')
        except OSError:
            pass
        return "jammy"

    def _fetch_update_metadata(self) -> dict:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": f"PyWarp/{CURRENT_VERSION}",
        }
        github = requests.get(
            "https://api.github.com/repos/saeedmasoudie/pywarp/"
            "releases/latest",
            headers=headers,
            timeout=12,
        )
        github.raise_for_status()
        release = github.json()
        selected_asset = self._select_release_asset(
            list(release.get("assets", []))
        )

        architecture = {
            "x86_64": "amd64",
            "AMD64": "amd64",
            "aarch64": "arm64",
            "arm64": "arm64",
        }.get(platform.machine(), "amd64")
        codename = self._linux_codename()
        package_url = (
            "https://pkg.cloudflareclient.com/dists/"
            f"{codename}/main/binary-{architecture}/Packages"
        )
        package_response = requests.get(package_url, timeout=12)
        if package_response.status_code == 404:
            package_response = requests.get(
                "https://pkg.cloudflareclient.com/dists/"
                "jammy/main/binary-amd64/Packages",
                timeout=12,
            )
        package_response.raise_for_status()
        version_match = re.search(
            r"^Version:\s*(\S+)",
            package_response.text,
            re.MULTILINE,
        )

        installed = ""
        executable = find_warp_cli()
        if executable:
            try:
                result = subprocess.run(
                    [executable, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                    creationflags=(
                        subprocess.CREATE_NO_WINDOW
                        if platform.system() == "Windows"
                        else 0
                    ),
                )
                installed_match = re.search(
                    r"\d+(?:\.\d+){2,}", result.stdout + result.stderr
                )
                if installed_match:
                    installed = installed_match.group(0)
            except (OSError, subprocess.SubprocessError):
                pass

        return {
            "pywarp_version": str(release.get("tag_name", "")).lstrip("v"),
            "pywarp_url": str(
                release.get(
                    "html_url",
                    "https://github.com/saeedmasoudie/pywarp/releases",
                )
            ),
            "warp_version": version_match.group(1) if version_match else "",
            "installed_warp": installed,
            "asset_name": selected_asset.get("name", ""),
            "asset_url": selected_asset.get("browser_download_url", ""),
        }

    def _select_release_asset(self, assets: list[dict]) -> dict:
        machine = platform.machine().lower()
        names = [
            (
                str(asset.get("name", "")).lower(),
                asset,
            )
            for asset in assets
        ]
        preferences: list[str]
        if self._platform_name == "Linux":
            preferences = ["pywarp-installer.sh", "linux-x64", "linux"]
        elif self._platform_name == "Darwin":
            architecture = "arm64" if "arm" in machine else "intel"
            preferences = [f"macos-{architecture}", ".dmg"]
        elif self._platform_name == "Windows":
            preferences = ["windows-installer", "windows-x64"]
        else:
            preferences = []
        for preference in preferences:
            for name, asset in names:
                if preference in name:
                    return asset
        return {}

    @Slot()
    def checkForUpdates(self) -> None:
        if self._update_checking:
            return
        self._update_checking = True
        self._update_error = ""
        self.updateStateChanged.emit()

        def apply(result: object) -> None:
            data = dict(result)
            previous_pywarp_version = self._latest_pywarp_version
            previous_warp_version = self._latest_warp_version
            self._latest_pywarp_version = data.get("pywarp_version", "")
            self._latest_warp_version = data.get("warp_version", "")
            self._installed_warp_version = data.get("installed_warp", "")
            self._pywarp_release_url = data.get(
                "pywarp_url", self._pywarp_release_url
            )
            self._pywarp_asset_name = data.get("asset_name", "")
            self._pywarp_asset_url = data.get("asset_url", "")
            self._pywarp_update_available = bool(
                self._latest_pywarp_version
                and self._version_tuple(self._latest_pywarp_version)
                > self._version_tuple(CURRENT_VERSION)
            )
            self._warp_update_available = bool(
                self._latest_warp_version
                and self._installed_warp_version
                and self._version_tuple(self._latest_warp_version)
                > self._version_tuple(self._installed_warp_version)
            )
            if (
                self._pywarp_update_available
                and self._latest_pywarp_version != previous_pywarp_version
            ):
                self._append_event(
                    "update",
                    "PyWarp update available",
                    f"Version {self._latest_pywarp_version} is ready.",
                    "INFO",
                )
            if (
                self._warp_update_available
                and self._latest_warp_version != previous_warp_version
            ):
                self._append_event(
                    "update",
                    "Cloudflare WARP update available",
                    (
                        f"Installed {self._installed_warp_version}; "
                        f"latest {self._latest_warp_version}."
                    ),
                    "INFO",
                )
            self.updateStateChanged.emit()

        def failed(message: str) -> None:
            self._update_error = message.splitlines()[0]
            self.updateStateChanged.emit()

        def finished() -> None:
            self._update_checking = False
            self.updateStateChanged.emit()

        self._runner.run_task(
            self._fetch_update_metadata,
            on_success=apply,
            on_error=failed,
            on_finished=finished,
        )

    @Slot()
    def openPywarpUpdate(self) -> None:
        QDesktopServices.openUrl(QUrl(self._pywarp_release_url))

    @Slot()
    def installPywarpUpdate(self) -> None:
        if not self._pywarp_asset_url or self._update_downloading:
            self.openPywarpUpdate()
            return
        self._update_downloading = True
        self.updateStateChanged.emit()

        def download() -> str:
            downloads = Path.home() / "Downloads"
            downloads.mkdir(parents=True, exist_ok=True)
            destination = downloads / self._pywarp_asset_name
            with requests.get(
                self._pywarp_asset_url,
                stream=True,
                timeout=45,
                headers={"User-Agent": f"PyWarp/{CURRENT_VERSION}"},
            ) as response:
                response.raise_for_status()
                with destination.open("wb") as output:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            output.write(chunk)
            if destination.suffix == ".sh":
                destination.chmod(destination.stat().st_mode | 0o111)
            return str(destination)

        def launch(path_value: object) -> None:
            path = Path(str(path_value))
            launched = False
            try:
                if path.suffix == ".sh":
                    terminal = next(
                        (
                            shutil.which(name)
                            for name in (
                                "x-terminal-emulator",
                                "gnome-terminal",
                                "konsole",
                                "xfce4-terminal",
                            )
                            if shutil.which(name)
                        ),
                        None,
                    )
                    if terminal:
                        if Path(terminal).name == "gnome-terminal":
                            subprocess.Popen(
                                [terminal, "--", "bash", str(path)]
                            )
                        elif Path(terminal).name == "konsole":
                            subprocess.Popen(
                                [terminal, "-e", "bash", str(path)]
                            )
                        else:
                            subprocess.Popen(
                                [terminal, "-e", "bash", str(path)]
                            )
                        launched = True
                if not launched:
                    launched = QDesktopServices.openUrl(
                        QUrl.fromLocalFile(str(path))
                    )
            except OSError:
                launched = False
            self._append_event(
                "update",
                "PyWarp update downloaded",
                (
                    f"Installer saved to {path}."
                    if launched
                    else f"Open {path} to finish installation."
                ),
                "SUCCESS",
            )
            self.toastRequested.emit(
                "success",
                "Update downloaded. Follow the installer to finish.",
            )

        def failed(message: str) -> None:
            self._update_error = message.splitlines()[0]
            self.toastRequested.emit(
                "error", f"Update download failed: {self._update_error}"
            )

        def finished() -> None:
            self._update_downloading = False
            self.updateStateChanged.emit()

        self._runner.run_task(
            download,
            on_success=launch,
            on_error=failed,
            on_finished=finished,
        )

    @Slot()
    def completeIntro(self) -> None:
        self._intro_complete = True
        self._save_setting("qml_intro_complete", True)
        self.introChanged.emit()

    @Slot()
    def showIntro(self) -> None:
        self._intro_complete = False
        self.introChanged.emit()

    @Slot()
    def startTour(self) -> None:
        self.completeIntro()
        QTimer.singleShot(0, self.tourRequested.emit)

    @Slot()
    def clearDnsLogs(self) -> None:
        self._dns_logs.clear()

    @Slot()
    def clearAppLogs(self) -> None:
        self._activity_items = []
        self._save_setting("activity_history", "[]")
        self._app_logs.clear()
