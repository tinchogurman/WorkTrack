"""Half-open time interval helpers ([start, end))."""

from __future__ import annotations

from datetime import datetime

Interval = tuple[datetime, datetime]


def overlap_seconds(a: Interval, b: Interval) -> int:
    start, end = max(a[0], b[0]), min(a[1], b[1])
    return max(0, int((end - start).total_seconds()))


def merge(intervals: list[Interval]) -> list[Interval]:
    """Sorted, non-overlapping union of the given intervals."""
    result: list[Interval] = []
    for start, end in sorted(i for i in intervals if i[1] > i[0]):
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], end))
        else:
            result.append((start, end))
    return result


def clipped_total(intervals: list[Interval], start: datetime, end: datetime) -> int:
    """Seconds of the union of `intervals` that fall inside [start, end)."""
    if end <= start:
        return 0
    return sum(overlap_seconds(i, (start, end)) for i in merge(intervals))


def subtract(start: datetime, end: datetime, intervals: list[Interval]) -> list[Interval]:
    """[start, end) minus the union of `intervals`, as sorted pieces."""
    pieces: list[Interval] = []
    cursor = start
    for s, e in merge(intervals):
        if e <= cursor or s >= end:
            continue
        if s > cursor:
            pieces.append((cursor, min(s, end)))
        cursor = max(cursor, e)
        if cursor >= end:
            break
    if cursor < end:
        pieces.append((cursor, end))
    return pieces
