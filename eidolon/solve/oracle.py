"""Independent checkers for the solver's feasibility questions (§19.5 "a brute-force checker
cross-validates the solver").

`world.feasibility._search` answers "can one actor satisfy this claim set?" with a layered
per-tick DP over (location-or-transit, mask). Everything here answers the SAME question with a
different algorithm, so agreement is evidence and disagreement is a bug in one of them:

* `oracle_feasible`   — depth-first search over (location, tick, mask) with ARRIVAL JUMPS: a move
  along an edge of `d` minutes lands at any tick >= t+d, the ticks in between being unlocated.
  No transit-state machine, no layers.
* `check_walk`        — a naive validator of one concrete per-tick walk (used on the solver's
  witness paths and on the phantom's corridor).
* `brute_feasible`    — exhaustive enumeration of EVERY walk (tiny instances only): the ground
  truth both of the above are tested against.

None of them imports `solver.py` or `lattice.py` (they take blocked/forced/exist cell sets).
"""
from __future__ import annotations

from itertools import product

from ..world.case import Case

LocTick = tuple[str, int]


def _mk(exist: list[set[LocTick]], loc: str, t: int, m: int) -> int:
    for i, s in enumerate(exist):
        if (loc, t) in s:
            m |= 1 << i
    return m


def oracle_feasible(case: Case, T: int, blocked: set[LocTick], forced: dict[int, str],
                    exist: list[set[LocTick]], starts: list[LocTick], goal: str | None = None) -> bool:
    edges = {loc: [(nb, minutes) for nb, minutes, _c in case.travel_graph.neighbours(loc)]
             for loc in case.locations}
    full = (1 << len(exist)) - 1

    def ok(loc: str, t: int) -> bool:
        return (loc, t) not in blocked and forced.get(t) in (None, loc)

    def tail_ok(loc: str, t: int) -> bool:
        """After the last visit the actor may stay put or drift in transit to the final tick —
        the layered DP accepts an unlocated final state when there is no `goal`."""
        for k in range(t, T):                # stay put through tick k, drift in transit after it
            if k > t and not ok(loc, k):
                return False
            if all(forced.get(x) is None for x in range(k + 1, T)):
                return True
        return False

    stack: list[tuple[str, int, int]] = []
    seen: set[tuple[str, int, int]] = set()
    for loc, t0 in starts:
        if t0 < T and ok(loc, t0):
            st = (loc, t0, _mk(exist, loc, t0, 0))
            if st not in seen:
                seen.add(st)
                stack.append(st)
    while stack:
        loc, t, m = stack.pop()
        if goal is None:
            if m == full and tail_ok(loc, t):
                return True
        elif t == T - 1 and m == full and loc == goal:
            return True
        nxt: list[tuple[str, int]] = []
        if t + 1 < T and ok(loc, t + 1):
            nxt.append((loc, t + 1))
        for nb, d in edges.get(loc, ()):
            if any(forced.get(x) is not None for x in range(t + 1, min(T, t + d))):
                continue                     # a forced tick cannot be spent in transit
            t2 = t + d
            while t2 < T:
                if ok(nb, t2):
                    nxt.append((nb, t2))
                if forced.get(t2) is not None:
                    break                    # lingering further would spend a forced tick in transit
                t2 += 1
        for l2, t2 in nxt:
            st = (l2, t2, _mk(exist, l2, t2, m))
            if st not in seen:
                seen.add(st)
                stack.append(st)
    return False


def check_walk(case: Case, walk: list[str], blocked: set[LocTick], forced: dict[int, str],
               exist: list[set[LocTick]], goal: str | None = None) -> bool:
    """Validate one concrete walk: `walk[t]` is a location or "~" (in transit). Movement is
    checked hop by hop against the travel graph; constraints against the cell sets."""
    T = len(walk)
    if not T or walk[0] == "~":
        return False
    tg = case.travel_graph
    origin, depart = walk[0], 0
    for t in range(1, T):
        prev, cur = walk[t - 1], walk[t]
        if cur == "~":
            if prev != "~":
                origin, depart = prev, t - 1
            continue
        if prev == "~":
            d = dict((nb, m) for nb, m, _c in tg.neighbours(origin)).get(cur)
            if d is None or t - depart < d:
                return False
        elif prev != cur:
            d = dict((nb, m) for nb, m, _c in tg.neighbours(prev)).get(cur)
            if d != 1:
                return False
    for t, loc in enumerate(walk):
        if loc == "~":
            if forced.get(t) is not None:
                return False
        else:
            if (loc, t) in blocked or forced.get(t) not in (None, loc):
                return False
    for s in exist:
        if not any(walk[t] == loc for loc, t in s if t < T):
            return False
    return goal is None or walk[-1] == goal


def brute_feasible(case: Case, T: int, blocked: set[LocTick], forced: dict[int, str],
                   exist: list[set[LocTick]], starts: list[LocTick], goal: str | None = None) -> bool:
    """Enumerate every per-tick assignment over {locations, "~"}. Exponential: tiny cases only."""
    locs = sorted(case.locations) + ["~"]
    start_set = {t: [] for t in range(T)}
    for loc, t0 in starts:
        start_set.setdefault(t0, []).append(loc)
    for walk in product(locs, repeat=T):
        if (walk[0], 0) not in set(starts):
            continue
        if check_walk(case, list(walk), blocked, forced, exist, goal):
            return True
    return False
