"""Suspected interruptions during a running session (spec 3.1).

Detection:
- heartbeat gap: two consecutive heartbeats more than GAP_THRESHOLD apart
  (the process was frozen: sleep, hibernation, VM pause...);
- Windows power events (suspend -> resume) give exact bounds and refine a
  pending heartbeat-gap detection of the same interval.

Nothing is discounted automatically. The user keeps the time, discounts the
detected interval, or adjusts the range to discount. Worked time is always
elapsed time minus the discounted ranges.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta

from worktrack.core.clock import Clock
from worktrack.core.errors import NotFoundError, ValidationError
from worktrack.core.intervals import clipped_total, overlap_seconds
from worktrack.core.models import Interruption, TimeEntry
from worktrack.core.timeutils import format_hms, format_local_datetime, seconds_between
from worktrack.db.connection import transaction
from worktrack.db.errors import integrity_errors
from worktrack.repositories.entries import EntryRepository
from worktrack.repositories.interruptions import InterruptionRepository

log = logging.getLogger(__name__)

GAP_THRESHOLD = timedelta(minutes=5)


def describe(interruption: Interruption) -> str:
    return (
        f"{format_local_datetime(interruption.start_time)} – {format_local_datetime(interruption.end_time)}"
        f" ({format_hms(interruption.seconds)})"
    )


class InterruptionService:
    def __init__(self, conn: sqlite3.Connection, clock: Clock) -> None:
        self.conn = conn
        self.clock = clock
        self.repo = InterruptionRepository(conn)
        self.entries = EntryRepository(conn)

    # --- detection ---------------------------------------------------------
    def check_heartbeat(self, previous: datetime | None, current: datetime) -> Interruption | None:
        if previous is None or current - previous < GAP_THRESHOLD:
            return None
        return self._record(previous, current, "heartbeat_gap")

    def record_power_gap(self, suspended_at: datetime, resumed_at: datetime) -> Interruption | None:
        if resumed_at - suspended_at < GAP_THRESHOLD:
            log.info("Short suspend ignored (%ss)", seconds_between(suspended_at, resumed_at))
            return None
        return self._record(suspended_at, resumed_at, "power_event")

    def _record(self, start: datetime, end: datetime, source: str) -> Interruption | None:
        with integrity_errors(), transaction(self.conn):
            active = self.entries.get_active()
            if active is None:
                return None
            start = max(start, active.start_time)
            end = min(end, self.clock.now())
            if end - start < GAP_THRESHOLD:
                return None
            for existing in self.repo.list_for_entry(active.id):
                if overlap_seconds((existing.start_time, existing.end_time), (start, end)) > 0:
                    if source == "power_event" and existing.source == "heartbeat_gap" and existing.is_pending:
                        self.repo.update_bounds(existing.id, start, end, source)
                        log.warning(
                            "Interruption id=%s refined by power events: %s -> %s",
                            existing.id, start.isoformat(), end.isoformat(),
                        )
                        return self.repo.get(existing.id)
                    return None  # already known
            new_id = self.repo.insert(active.id, start, end, source, self.clock.now())
        found = self.repo.get(new_id)
        log.warning(
            "Interruption detected id=%s entry=%s source=%s %s -> %s (%ss)",
            found.id, found.entry_id, source, start.isoformat(), end.isoformat(), found.seconds,
        )
        return found

    # --- queries -----------------------------------------------------------
    def list_for_entry(self, entry_id: int) -> list[Interruption]:
        return self.repo.list_for_entry(entry_id)

    def pending_for_entry(self, entry_id: int) -> list[Interruption]:
        return [i for i in self.repo.list_for_entry(entry_id) if i.is_pending]

    def discounts(self, entry_id: int) -> list[tuple[datetime, datetime]]:
        return self.repo.discounts_for_entries([entry_id]).get(entry_id, [])

    # --- decisions ---------------------------------------------------------
    def keep(self, interruption_id: int) -> Interruption:
        return self._resolve(interruption_id, "kept", None)

    def discount(self, interruption_id: int) -> Interruption:
        item = self._get(interruption_id)
        return self._resolve(interruption_id, "discounted", (item.start_time, item.end_time))

    def adjust(self, interruption_id: int, start: datetime, end: datetime) -> Interruption:
        """Discount a user-chosen range (manual correction)."""
        if start.tzinfo is None or end.tzinfo is None:
            raise ValidationError("Fecha u hora inválida.")
        return self._resolve(interruption_id, "adjusted", (start.replace(microsecond=0), end.replace(microsecond=0)))

    def _get(self, interruption_id: int) -> Interruption:
        item = self.repo.get(interruption_id)
        if item is None:
            raise NotFoundError("La interrupción ya no existe.")
        return item

    def _resolve(
        self, interruption_id: int, status: str, discount: tuple[datetime, datetime] | None
    ) -> Interruption:
        with integrity_errors(), transaction(self.conn):
            item = self._get(interruption_id)
            entry = self.entries.get(item.entry_id)
            if discount is not None:
                self._check_discount(entry, item, discount)
            self.repo.resolve(interruption_id, status, discount, self.clock.now())
            if entry.end_time is not None:
                self._recompute_duration(entry)
        log.info(
            "Interruption id=%s entry=%s resolved: %s%s",
            interruption_id, item.entry_id, status,
            f" ({discount[0].isoformat()} -> {discount[1].isoformat()})" if discount else "",
        )
        return self.repo.get(interruption_id)

    def _check_discount(self, entry: TimeEntry, item: Interruption, discount: tuple[datetime, datetime]) -> None:
        start, end = discount
        if end <= start:
            raise ValidationError("El fin del tramo a descontar debe ser posterior al inicio.")
        limit = entry.end_time or self.clock.now()
        if start < entry.start_time or end > limit:
            raise ValidationError("El tramo a descontar debe estar dentro de la sesión.")
        others = [
            i.discounted_interval for i in self.repo.list_for_entry(entry.id)
            if i.id != item.id and i.discounted_interval
        ]
        if any(overlap_seconds(o, discount) for o in others):
            raise ValidationError("El tramo se superpone con otro tramo ya descontado.")

    def _recompute_duration(self, entry: TimeEntry) -> None:
        elapsed = seconds_between(entry.start_time, entry.end_time)
        discounted = clipped_total(self.discounts(entry.id), entry.start_time, entry.end_time)
        self.entries.finish(entry.id, entry.end_time, max(0, elapsed - discounted))
