"""Interval algebra (§4.2, §4.9). Half-open `[start, end)` in ticks (integer minutes).

Ticks, not floats: I-17 bans floats from authoritative state, and half-open integer
intervals make "instantaneous" and "adjacent" unambiguous (no epsilon comparisons).
"""
from __future__ import annotations

Interval = tuple[int, int]


def valid(iv: Interval) -> bool:
    """Every event/claim interval must be non-empty: `t_end >= t_start + 1` (§4.2)."""
    return iv[1] > iv[0]


def length(iv: Interval) -> int:
    return max(0, iv[1] - iv[0])


def intersect(a: Interval, b: Interval) -> Interval | None:
    s, e = max(a[0], b[0]), min(a[1], b[1])
    return (s, e) if e > s else None


def overlaps(a: Interval, b: Interval) -> bool:
    return intersect(a, b) is not None


def contains(outer: Interval, inner: Interval) -> bool:
    return outer[0] <= inner[0] and inner[1] <= outer[1]


def contains_tick(iv: Interval, t: int) -> bool:
    return iv[0] <= t < iv[1]


def shrink(iv: Interval, granularity: int) -> Interval | None:
    """Testimony at granularity g: only the inner part is asserted (§13.2 granularity rule)."""
    s, e = iv[0] + granularity, iv[1] - granularity
    return (s, e) if e > s else None


def widen(iv: Interval, granularity: int, lo: int = 0, hi: int = 10**9) -> Interval:
    return (max(lo, iv[0] - granularity), min(hi, iv[1] + granularity))


def subtract(iv: Interval, cuts: list[Interval]) -> list[Interval]:
    """`iv` minus the union of `cuts`, as disjoint intervals, left to right."""
    out: list[Interval] = []
    s = iv[0]
    for c in sorted(cuts):
        if c[1] <= s or c[0] >= iv[1]:
            continue
        if c[0] > s:
            out.append((s, c[0]))
        s = max(s, c[1])
    if s < iv[1]:
        out.append((s, iv[1]))
    return out


def union(intervals: list[Interval]) -> list[Interval]:
    out: list[Interval] = []
    for s, e in sorted(intervals):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def ticks(iv: Interval) -> range:
    return range(iv[0], iv[1])
