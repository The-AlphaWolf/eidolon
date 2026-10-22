"""Space: locations, travel and perception graphs (§4.3).

`travel_time`/`route` run on-demand Dijkstra (hand-rolled, no `networkx` — ADR/§4.3: at
case scale, ≤ 20 nodes, a cached all-pairs matrix would be wrong under time-conditional
edges like a locked door). Edge conditions are evaluated by a caller-supplied predicate so
this module stays independent of `WorldState` (§23.1 dependency direction).
"""
from __future__ import annotations

import heapq
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict

from .frozen import Frozen, FrozenDict
from .ids import LocationId

EXT: LocationId = "EXT"  # exterior pseudo-location: outsider entry/exit (AC-9)


class Location(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: LocationId
    name: str
    zone: str = ""
    private: bool = False       # I-48: never an intermediate node on a route
    exterior: bool = False      # reachable from EXT
    entrances: tuple[LocationId, ...] = ()  # load-bearing for absence knowledge (§4.3, I-34)
    entrances_visible: bool = True  # every entrance perceivable from inside (§4.3 comment,
                                     # §4.8.7); the boolean the Phase 0.5 spike validated —
                                     # a per-entrance PerceptionEdge model is not specified.
    attributes: Frozen[str, str] = FrozenDict()


class Condition(BaseModel):
    """A named gate on a `TravelEdge`/`PerceptionEdge` (§4.3: `DoorUnlocked`, `HasKey`, …).

    The architecture leaves `Condition` as a sketch (named examples, no closed schema); this
    is the minimal tagged form that lets `check_physics` P-5 evaluate real gates without
    inventing a second condition language.
    """
    model_config = ConfigDict(frozen=True)

    kind: Literal["DoorUnlocked", "DoorOpen", "HasKey", "LightOn", "Night"]
    args: tuple[str, ...] = ()


ConditionCheck = Callable[[Condition, int], bool]


def always_open(_c: Condition, _t: int) -> bool:
    return True


class TravelEdge(BaseModel):
    model_config = ConfigDict(frozen=True)

    a: LocationId
    b: LocationId
    minutes: int
    directed: bool = False
    conditions: tuple[Condition, ...] = ()


class PerceptionEdge(BaseModel):
    model_config = ConfigDict(frozen=True)

    observer_at: LocationId
    perceives: LocationId
    modality: Literal["sight", "sound"]
    quality: float  # 0..1 base reliability
    conditions: tuple[Condition, ...] = ()


class TravelGraph:
    """Adjacency + on-demand conditional Dijkstra over a fixed set of `TravelEdge`s."""

    def __init__(self, locations: dict[LocationId, Location], edges: list[TravelEdge]):
        self.locations = locations
        self.edges = edges
        adj: dict[LocationId, list[tuple[LocationId, int, tuple[Condition, ...]]]] = {}
        for e in edges:
            adj.setdefault(e.a, []).append((e.b, e.minutes, e.conditions))
            if not e.directed:
                adj.setdefault(e.b, []).append((e.a, e.minutes, e.conditions))
        self._adj = {a: sorted(v) for a, v in adj.items()}

    def neighbours(self, a: LocationId) -> list[tuple[LocationId, int, tuple[Condition, ...]]]:
        return self._adj.get(a, [])

    def _edge_open(self, conditions: tuple[Condition, ...], t: int, check: ConditionCheck) -> bool:
        return all(check(c, t) for c in conditions)

    def travel_time(self, a: LocationId, b: LocationId, t: int, check: ConditionCheck = always_open) -> int | None:
        """Minutes to travel `a` -> `b`, departing no earlier than `t`, conditions evaluated
        at each edge's traversal tick (§4.3)."""
        if a == b:
            return 0
        dist: dict[LocationId, int] = {a: t}
        pq: list[tuple[int, LocationId]] = [(t, a)]
        while pq:
            d, u = heapq.heappop(pq)
            if u == b:
                return d - t
            if d > dist.get(u, 10**9):
                continue
            for v, w, conditions in self.neighbours(u):
                if not self._edge_open(conditions, d, check):
                    continue
                nd = d + w
                if nd < dist.get(v, 10**9):
                    dist[v] = nd
                    heapq.heappush(pq, (nd, v))
        return None

    def route(self, a: LocationId, b: LocationId, t: int, check: ConditionCheck = always_open) -> list[LocationId] | None:
        """Shortest open node path `a` -> `b` at time `t`. Private rooms (I-48) are excluded
        as intermediate nodes — a private room may only be the destination."""
        if a == b:
            return [a]
        dist: dict[LocationId, int] = {a: t}
        prev: dict[LocationId, LocationId] = {}
        pq: list[tuple[int, LocationId]] = [(t, a)]
        while pq:
            d, u = heapq.heappop(pq)
            if u == b:
                path = [b]
                while path[-1] != a:
                    path.append(prev[path[-1]])
                return path[::-1]
            if d > dist.get(u, 10**9):
                continue
            if u != a and self.locations[u].private:
                continue  # arrive at a private room only as the destination
            for v, w, conditions in self.neighbours(u):
                if not self._edge_open(conditions, d, check):
                    continue
                nd = d + w
                if nd < dist.get(v, 10**9):
                    dist[v], prev[v] = nd, u
                    heapq.heappush(pq, (nd, v))
        return None
