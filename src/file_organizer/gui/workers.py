"""Background execution so the window never freezes on large folders."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from PySide6.QtCore import QThread, Signal


class Worker(QThread):
    """Run ``task(progress, should_cancel)`` in a thread.

    ``progress(done, total, label)`` is throttled so thousands of files do
    not flood the event loop.
    """

    progress = Signal(int, int, str)
    succeeded = Signal(object)
    failed = Signal(object)

    def __init__(self, task: Callable[..., Any], parent=None) -> None:
        super().__init__(parent)
        self._task = task
        self._cancel = threading.Event()
        self._last_emit = 0.0

    def cancel(self) -> None:
        self._cancel.set()

    def _report(self, done: int, total: int, label: str = "") -> None:
        now = time.monotonic()
        if done >= total or now - self._last_emit >= 0.03:
            self._last_emit = now
            self.progress.emit(done, total, label)

    def run(self) -> None:
        try:
            result = self._task(self._report, self._cancel.is_set)
        except BaseException as error:  # reported to the UI thread
            self.failed.emit(error)
        else:
            self.succeeded.emit(result)
