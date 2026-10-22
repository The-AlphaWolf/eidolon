"""Joint feasibility — n-ary consistency (§13.2a, I-28, AC-2).

`contradiction(p, q)` is a *pairwise* function and a claim set can be pairwise consistent
yet jointly impossible (the transitive alibi cycle, §13.2a). `feasible()` propagates
presence/travel constraints over a whole claim set via reachability, not pairwise
comparison. Conditional travel edges (P-5) are treated as always-open here — §13.2a
describes presence/travel propagation only; door-gating is a separate physics rule.
"""
from __future__ import annotations

from dataclasses import dataclass

from .case import Case
from .interval import ticks
from .propositions import Proposition

LocTick = tuple[str, int]


@dataclass(frozen=True)
class Claim:
    """A minimal `(id, proposition)` pair — enough for §13.2a. The full `Claim` with
    modality/sincerity/grounding is a Phase 4 model; this is what it will feed through."""
    id: str
    proposition: Proposition


@dataclass(frozen=True)
class Feasibility:
    ok: bool
    core: tuple[str, ...] = ()  # minimal conflicting claim ids


def _actor_of(prop: Proposition) -> str | None:
    return getattr(prop, "actor", None) or getattr(prop, "observer", None)


def _location_of(prop: Proposition) -> str | None:
    return getattr(prop, "location", None) or getattr(prop, "from_location", None)


def _compile(case: Case, claims: list[Claim], actor: str):
    """Splits one actor's claims into `blocked` cells, `forced` tick->location placements,
    and `exist` existential (location,tick) sets. Returns `None` if two claims force
    contradictory placements at the same tick (trivially infeasible)."""
    blocked: set[LocTick] = set()
    forced: dict[int, str] = {}
    exist: list[set[LocTick]] = []
    for c in claims:
        p = c.proposition
        if _actor_of(p) != actor:
            continue
        if p.kind == "At":
            for t in ticks(p.interval):
                if forced.get(t, p.location) != p.location:
                    return None
                forced[t] = p.location
        elif p.kind == "NotAt":
            blocked |= {(p.location, t) for t in ticks(p.interval)}
        elif p.kind == "Moved":
            if forced.get(p.t, p.to_loc) != p.to_loc:
                return None
            forced[p.t] = p.to_loc
        elif p.kind == "Did" and p.location:
            exist.append({(p.location, t) for t in ticks(p.interval)})
        elif p.kind == "Saw" and p.identified:
            exist.append({(p.location, t) for t in ticks(p.interval)})
        elif p.kind == "Heard" and p.from_location:
            exist.append({(p.from_location, t) for t in ticks(p.interval)})
    return blocked, forced, exist


def _search(case: Case, T: int, starts: list[LocTick], blocked: set[LocTick],
            forced: dict[int, str], exist: list[set[LocTick]], goal: str | None = None):
    """Reachability over (location-or-transit, tick, existential-bitmask). Departing `L` at
    tick `t` allows arriving at a neighbour no earlier than `t + travel_time`; lingering in
    transit is allowed. `cur` maps each distinct (state, mask) reachable at `t` to its
    predecessor — two paths reaching the same location with different masks are different
    states and must not be collapsed (each mask records a different, possibly incompatible,
    subset of existentials satisfied so far). `goal`, if given, must be the location at the
    final tick. Returns `(ok, path)`; `path` is one `(location-or-"~", tick)` witness per
    tick (Phase 6: the solver's proofs carry it, and an independent checker re-validates it)."""
    full = (1 << len(exist)) - 1

    def mask(loc: str, t: int, m: int) -> int:
        for i, s in enumerate(exist):
            if (loc, t) in s:
                m |= 1 << i
        return m

    starts_at: dict[int, list[str]] = {}
    for loc, t0 in starts:
        starts_at.setdefault(t0, []).append(loc)

    layers: list[dict] = []
    cur: dict = {}
    for t in range(T):
        nxt: dict = {}
        if t > 0:
            for (state, m) in cur:
                if isinstance(state, tuple):  # ("~", dest, ticks remaining in transit)
                    _, dest, rem = state
                    if forced.get(t) is None:
                        nxt.setdefault((("~", dest, max(0, rem - 1)), m), (state, m))
                    if rem == 0 and (dest, t) not in blocked and forced.get(t) in (None, dest):
                        nxt.setdefault((dest, mask(dest, t, m)), (state, m))
                else:
                    loc = state
                    if (loc, t) not in blocked and forced.get(t) in (None, loc):
                        nxt.setdefault((loc, mask(loc, t, m)), (state, m))
                    for nb, minutes, _conditions in case.travel_graph.neighbours(loc):
                        if minutes == 1 and (nb, t) not in blocked and forced.get(t) in (None, nb):
                            nxt.setdefault((nb, mask(nb, t, m)), (state, m))
                        if forced.get(t) is None:
                            nxt.setdefault((("~", nb, max(0, minutes - 2)), m), (state, m))
        for loc in starts_at.get(t, []):
            if (loc, t) not in blocked and forced.get(t) in (None, loc):
                nxt.setdefault((loc, mask(loc, t, 0)), None)
        cur = nxt
        layers.append(cur)
        if not cur and t >= max(starts_at, default=0):
            return False, None
    for (state, m) in cur:
        if m == full and (goal is None or state == goal):
            path, t, key = [], T - 1, (state, m)
            while key is not None:
                path.append((key[0] if not isinstance(key[0], tuple) else "~", t))
                key = layers[t][key]
                t -= 1
            return True, path[::-1]
    return False, None


def _dp(case: Case, T: int, starts: list[LocTick], blocked: set[LocTick],
        forced: dict[int, str], exist: list[set[LocTick]]) -> bool:
    return _search(case, T, starts, blocked, forced, exist)[0]


def feasible_actor(case: Case, actor: str, claims: list[Claim]) -> bool:
    compiled = _compile(case, claims, actor)
    if compiled is None:
        return False
    blocked, forced, exist = compiled
    starts = [(loc, 0) for loc in case.locations]
    return _dp(case, case.t_investigation, starts, blocked, forced, exist)


def _actor_core(case: Case, actor: str, claims: list[Claim]) -> list[str]:
    """Deletion-minimal subset of this actor's claims that is already infeasible alone."""
    mine = [c for c in claims if _actor_of(c.proposition) == actor]
    keep = list(mine)
    for c in list(mine):
        trial = [x for x in keep if x is not c]
        if not feasible_actor(case, actor, trial):
            keep = trial
    return [c.id for c in keep]


def feasible(case: Case, claims: list[Claim]) -> Feasibility:
    """§13.2a: joint feasibility of a claim set under presence/travel propagation."""
    core: list[str] = []
    actors = sorted({_actor_of(c.proposition) for c in claims if _actor_of(c.proposition)})
    for a in actors:
        if not feasible_actor(case, a, claims):
            core += _actor_core(case, a, claims)
    return Feasibility(ok=not core, core=tuple(core))
