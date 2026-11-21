"""Recovery of a session left open by an unexpected shutdown.

On startup (single instance guaranteed), any active session is an orphan
from a previous run. The user chooses: continue it, finish it at the last
moment the app was known to be alive (last heartbeat), or at a given time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from worktrack.core.errors import NoActiveSessionError, ValidationError
from worktrack.core.models import EntryView, TimeEntry
from worktrack.core.timeutils import seconds_between
from worktrack.services.timer_service import TimerService

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecoveryInfo:
    view: EntryView
    started_at: datetime
    last_seen: datetime  # last heartbeat, or start if none was recorded
    now: datetime

    @property
    def seconds_to_last_seen(self) -> int:
        return max(0, seconds_between(self.started_at, self.last_seen))

    @property
    def seconds_to_now(self) -> int:
        return max(0, seconds_between(self.started_at, self.now))

    @property
    def unseen_seconds(self) -> int:
        """Time between the last heartbeat and now (the app was not running)."""
        return max(0, seconds_between(self.last_seen, self.now))


class RecoveryService:
    def __init__(self, timer: TimerService) -> None:
        self.timer = timer

    def check(self) -> RecoveryInfo | None:
        view = self.timer.get_active_view()
        if view is None:
            return None
        entry = view.entry
        now = self.timer.clock.now()
        last_seen = entry.last_heartbeat or entry.start_time
        last_seen = min(max(last_seen, entry.start_time), max(now, entry.start_time))
        info = RecoveryInfo(view=view, started_at=entry.start_time, last_seen=last_seen, now=now)
        log.warning(
            "Orphan active session found id=%s start=%s last_heartbeat=%s now=%s",
            entry.id, entry.start_time.isoformat(), last_seen.isoformat(), now.isoformat(),
        )
        return info

    def continue_session(self) -> TimeEntry:
        beat = self.timer.heartbeat()
        if beat is None:
            raise NoActiveSessionError()
        active = self.timer.get_active()
        log.info("Recovery: session id=%s continued (last beat %s)", active.id, beat.previous)
        return active

    def finish_at_last_seen(self) -> TimeEntry:
        info = self.check()
        if info is None:
            raise NoActiveSessionError()
        entry = self.timer.finish_active_at(info.last_seen, reason="recovery-last-seen")
        log.info("Recovery: session id=%s finished at last heartbeat %s", entry.id, info.last_seen)
        return entry

    def finish_at(self, end: datetime) -> TimeEntry:
        if end.tzinfo is None:
            raise ValidationError("Hora de fin inválida.")
        entry = self.timer.finish_active_at(end.replace(microsecond=0), reason="recovery-custom")
        log.info("Recovery: session id=%s finished at user time %s", entry.id, end.isoformat())
        return entry
