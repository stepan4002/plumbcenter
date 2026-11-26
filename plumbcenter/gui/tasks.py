"""Background task runner using QThreadPool + QRunnable.

Ensures long-running operations (git clone/pull, venv setup, process actions,
provider connection tests, diagnostics) never block the Qt UI thread.
"""

from __future__ import annotations

import traceback
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


class TaskSignals(QObject):
    """Qt signals emitted by a background FunctionTask."""

    started = Signal()
    finished = Signal(object)
    error = Signal(str)
    done = Signal()


class FunctionTask(QRunnable):
    """Run an arbitrary Python callable on QThreadPool and emit Qt signals."""

    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = TaskSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        self._safe_emit(self.signals.started)
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).strip() or exc.__class__.__name__
            self._safe_emit(self.signals.error, msg)
        else:
            self._safe_emit(self.signals.finished, result)
        finally:
            self._safe_emit(self.signals.done)

    @staticmethod
    def _safe_emit(signal, *args: Any) -> None:
        try:
            signal.emit(*args)
        except RuntimeError:
            # Qt object / app shutting down while worker thread was finishing.
            pass


# Keep references to active TaskSignals objects until done so Python GC
# cannot collect them while QRunnable executes on a worker thread.
_ACTIVE_SIGNALS: set[TaskSignals] = set()


def run_in_background(
    fn: Callable[..., Any],
    *args: Any,
    on_success: Optional[Callable[[Any], None]] = None,
    on_error: Optional[Callable[[str], None]] = None,
    on_done: Optional[Callable[[], None]] = None,
    pool: Optional[QThreadPool] = None,
    **kwargs: Any,
) -> FunctionTask:
    """Submit `fn(*args, **kwargs)` to QThreadPool and wire callbacks safely."""
    task = FunctionTask(fn, *args, **kwargs)
    sig = task.signals
    _ACTIVE_SIGNALS.add(sig)

    if on_success is not None:
        sig.finished.connect(on_success)
    if on_error is not None:
        sig.error.connect(on_error)

    def _cleanup() -> None:
        _ACTIVE_SIGNALS.discard(sig)
        if on_done is not None:
            on_done()

    sig.done.connect(_cleanup)

    target_pool = pool or QThreadPool.globalInstance()
    target_pool.start(task)
    return task
