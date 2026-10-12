from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal


def find_warp_cli() -> str | None:
    executable = shutil.which("warp-cli")
    if executable:
        return executable

    if platform.system() == "Darwin":
        candidate = (
            "/Applications/Cloudflare WARP.app/Contents/Resources/warp-cli"
        )
        if os.path.isfile(candidate):
            return candidate
    return None


@dataclass(slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class _WorkerSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()


class _CommandWorker(QRunnable):
    def __init__(self, args: list[str], timeout: int):
        super().__init__()
        self.args = args
        self.timeout = timeout
        self.signals = _WorkerSignals()

    def run(self) -> None:
        try:
            executable = find_warp_cli()
            if not executable:
                raise RuntimeError("warp-cli was not found on this system.")

            completed = subprocess.run(
                [executable, *self.args],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW
                    if platform.system() == "Windows"
                    else 0
                ),
            )
            result = CommandResult(
                completed.returncode,
                completed.stdout.strip(),
                completed.stderr.strip(),
            )
            if completed.returncode == 0:
                self.signals.succeeded.emit(result)
            else:
                message = result.stderr or result.stdout or (
                    f"warp-cli exited with code {result.returncode}"
                )
                self.signals.failed.emit(message)
        except subprocess.TimeoutExpired:
            self.signals.failed.emit("The warp-cli command timed out.")
        except Exception as exc:
            self.signals.failed.emit(str(exc))
        finally:
            self.signals.finished.emit()


class _TaskWorker(QRunnable):
    def __init__(self, task: Callable[[], object]):
        super().__init__()
        self.task = task
        self.signals = _WorkerSignals()

    def run(self) -> None:
        try:
            self.signals.succeeded.emit(self.task())
        except Exception as exc:
            self.signals.failed.emit(str(exc))
        finally:
            self.signals.finished.emit()


class CommandRunner(QObject):
    """Runs warp-cli commands without blocking the QML render thread."""

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._pool = QThreadPool.globalInstance()
        self._active: set[_CommandWorker] = set()
        self._idle_callbacks: list[Callable[[], None]] = []

    def _worker_finished(self, worker: _CommandWorker) -> None:
        self._active.discard(worker)
        if self._active or not self._idle_callbacks:
            return
        callbacks, self._idle_callbacks = self._idle_callbacks, []
        for callback in callbacks:
            callback()

    def run_when_idle(self, callback: Callable[[], None]) -> None:
        """Run a callback after all currently queued work has settled."""
        if not self._active:
            QTimer.singleShot(0, callback)
            return
        self._idle_callbacks.append(callback)

    def run(
        self,
        args: list[str],
        on_success: Callable[[CommandResult], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_finished: Callable[[], None] | None = None,
        timeout: int = 20,
    ) -> None:
        worker = _CommandWorker(args, timeout)
        self._active.add(worker)
        if on_success:
            worker.signals.succeeded.connect(
                on_success, Qt.ConnectionType.QueuedConnection
            )
        if on_error:
            worker.signals.failed.connect(
                on_error, Qt.ConnectionType.QueuedConnection
            )
        if on_finished:
            worker.signals.finished.connect(
                on_finished, Qt.ConnectionType.QueuedConnection
            )
        worker.signals.finished.connect(
            lambda current=worker: self._worker_finished(current),
            Qt.ConnectionType.QueuedConnection,
        )
        self._pool.start(worker)

    def run_task(
        self,
        task: Callable[[], object],
        on_success: Callable[[object], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_finished: Callable[[], None] | None = None,
    ) -> None:
        worker = _TaskWorker(task)
        self._active.add(worker)
        if on_success:
            worker.signals.succeeded.connect(
                on_success, Qt.ConnectionType.QueuedConnection
            )
        if on_error:
            worker.signals.failed.connect(
                on_error, Qt.ConnectionType.QueuedConnection
            )
        if on_finished:
            worker.signals.finished.connect(
                on_finished, Qt.ConnectionType.QueuedConnection
            )
        worker.signals.finished.connect(
            lambda current=worker: self._worker_finished(current),
            Qt.ConnectionType.QueuedConnection,
        )
        self._pool.start(worker)
