"""Windows suspend/resume notifications (WM_POWERBROADCAST).

Gives exact suspend/resume instants and immediate detection on wake-up.
Some machines (Modern Standby) do not send these events; the heartbeat-gap
detection in the timer remains as a fallback.
"""

from __future__ import annotations

import logging
import sys
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

log = logging.getLogger(__name__)

WM_POWERBROADCAST = 0x0218
PBT_APMSUSPEND = 0x0004
PBT_APMRESUMESUSPEND = 0x0007
PBT_APMRESUMEAUTOMATIC = 0x0012


class PowerMonitor(QObject):
    suspended = Signal()
    resumed = Signal()

    def handle(self, wparam: int) -> None:
        if wparam == PBT_APMSUSPEND:
            log.warning("Windows is suspending")
            self.suspended.emit()
        elif wparam in (PBT_APMRESUMEAUTOMATIC, PBT_APMRESUMESUSPEND):
            log.warning("Windows resumed (event 0x%x)", wparam)
            self.resumed.emit()


class _PowerEventFilter(QAbstractNativeEventFilter):
    def __init__(self, monitor: PowerMonitor) -> None:
        super().__init__()
        self.monitor = monitor

    def nativeEventFilter(self, event_type, message):  # noqa: N802 (Qt API)
        try:
            if bytes(event_type) == b"windows_generic_MSG":
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_POWERBROADCAST:
                    self.monitor.handle(int(msg.wParam))
        except Exception:  # never let a native callback raise
            log.exception("Power event filter failed")
        return False, 0


def install_power_monitor(app) -> PowerMonitor | None:
    """Install on the QApplication (Windows only). Keep the returned object alive."""
    if sys.platform != "win32":
        return None
    monitor = PowerMonitor(app)
    event_filter = _PowerEventFilter(monitor)
    app.installNativeEventFilter(event_filter)
    monitor._filter = event_filter  # keep a reference (GC would remove it)
    return monitor
