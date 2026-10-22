"""Phase 0.5 spike — canonical world slice.

Throwaway-quality vertical slice of EIDOLON-ARCHITECTURE.md v0.3 §4 (world), just
enough to MEASURE generator yield. Stdlib only (dataclasses instead of pydantic).

Contents: interval algebra, closed proposition schema (subset), travel graph with
on-demand conditional Dijkstra (§4.3), presence/FactIndex (§4.6–4.7), physics
checker P-1/P-2/P-4 + P-9 (§4.9).
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field

Interval = tuple[int, int]  # half-open [s, e) in ticks (minutes)

EXT = "EXT"  # exterior pseudo-location (outsider entry/exit)


# ---------------------------------------------------------------- intervals
def iv_len(a: Interval) -> int:
    return max(0, a[1] - a[0])


def iv_inter(a: Interval, b: Interval) -> Interval | None:
    s, e = max(a[0], b[0]), min(a[1], b[1])
    return (s, e) if e > s else None


def iv_shrink(a: Interval, g: int) -> Interval | None:
    """Testimony at granularity g: only the inner part is asserted (§13.2 granularity rule)."""
    s, e = a[0] + g, a[1] - g
    return (s, e) if e > s else None


def iv_widen(a: Interval, g: int, lo: int = 0, hi: int = 10**9) -> Interval:
    return (max(lo, a[0] - g), min(hi, a[1] + g))


def iv_minus(a: Interval, cuts: list[Interval]) -> list[Interval]:
    """a minus the union of cuts, as disjoint intervals."""
    out, s = [], a[0]
    for c in sorted(cuts):
        if c[1] <= s or c[0] >= a[1]:
            continue
        if c[0] > s:
            out.append((s, c[0]))
        s = max(s, c[1])
    if s < a[1]:
        out.append((s, a[1]))
    return out


def iv_union(ivs: list[Interval]) -> list[Interval]:
    out: list[Interval] = []
    for s, e in sorted(ivs):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def ticks(a: Interval) -> range:
    return range(a[0], a[1])


# ------------------------------------------------------------- propositions
@dataclass(frozen=True, order=True)
class Prop:
    """Closed proposition schema, spike subset of §4.7.

    kind:
      At(actor, loc, iv)         universal presence (throughout iv)
      NotAt(actor, loc, iv)      universal absence
      Did(actor, loc, iv, (action, object))   existential: at some tick in iv actor was at loc doing action
      Saw(actor=subject, loc, iv, (identified,))  existential presence of an identified subject (observer = speaker)
      Heard(actor=identified_actor|None, loc=source, iv, (sound, voice_attr|None))
      Died(actor, loc, iv)       time pin of the attack
      NoStranger(None, loc, iv)  Saw(observer, "nobody", loc, iv): no unknown person in loc throughout iv
      Attr(actor, None, None, (attr, value))
      ObjectState(None, loc, iv, (object, attr, value))
    """
    kind: str
    actor: str | None
    loc: str | None
    iv: Interval | None
    extra: tuple = ()

    def entities(self) -> set[str]:
        s = {x for x in (self.actor, self.loc) if x}
        if self.kind == "Did":
            s.add(self.extra[1])
        if self.kind == "ObjectState":
            s.add(self.extra[0])
        return s

    def __str__(self) -> str:
        parts = [self.kind]
        if self.actor:
            parts.append(self.actor)
        if self.loc:
            parts.append(self.loc)
        if self.iv:
            parts.append(f"[{self.iv[0]},{self.iv[1]})")
        if self.extra:
            parts.append(repr(self.extra))
        return "(" + " ".join(parts) + ")"


# ------------------------------------------------------------------- world
@dataclass
class Actor:
    id: str
    name: str
    role: str  # victim | living
    attrs: dict[str, str] = field(default_factory=dict)  # e.g. sex


@dataclass
class Loc:
    id: str
    name: str
    entrances_visible: bool  # I-34: every entrance perceivable from inside
    exterior: bool = False  # reachable from EXT
    private: bool = False  # I-48: never transited en route; entered only as a destination


@dataclass
class Seg:
    """Maximal presence segment (I, L) of one actor; gaps between segments are transit."""
    loc: str
    s: int
    e: int
    attention: float = 1.0  # 1.0 awake/idle, 0.7 engaged, 0.3 asleep/drunk
    event_id: str = ""  # the Stay event grounding co-presence/absence knowledge

    @property
    def iv(self) -> Interval:
        return (self.s, self.e)


@dataclass
class Event:
    id: str
    kind: str  # Attack | Clean | Logged | Move | Speak
    actor: str
    loc: str
    t: int  # instantaneous events occupy [t, t+1); Logged spans [t, t_end)
    t_end: int | None = None
    objects: tuple[str, ...] = ()
    sight: float = 0.0
    sound: float = 0.0
    identifies_voice: bool = False
    participants: tuple[str, ...] = ()

    @property
    def iv(self) -> Interval:
        return (self.t, self.t_end if self.t_end is not None else self.t + 1)


@dataclass
class Implication:
    prop: Prop
    requires: tuple[str, ...] = ()  # item ids that must be held (P-9: they establish prop.iv)
    strength: float = 1.0


@dataclass
class Evidence:
    id: str
    kind: str
    at: str  # discovery location
    names: tuple[str, ...]  # entities the item names (cue graph, §19.4)
    implications: list[Implication]
    authentic: bool = True
    discover_needs: tuple[str, ...] = ()  # entities that must already be named (e.g. the object to dust)
    established_iv: Interval | None = None  # P-9: interval established by created_at alone


@dataclass
class Secret:
    owner: str
    iv: Interval  # protected interval: owner's presence during iv is protected
    kind: str
    shared_with: tuple[str, ...] = ()  # collusion edge (shared secret)


@dataclass
class World:
    actors: dict[str, Actor]
    locs: dict[str, Loc]
    travel: dict[tuple[str, str], int]  # symmetric edges (a,b)->minutes, stored both ways
    doors: dict[tuple[str, str], list[Interval]]  # edge -> intervals when LOCKED (condition)
    perception: list[tuple[str, str, str, float]]  # (observer_at, perceives, modality, quality)
    segments: dict[str, list[Seg]]
    events: list[Event]
    t_inv: int
    victim: str
    murderer: str
    t_m: int
    murder_loc: str
    secrets: dict[str, Secret]
    rels: list[tuple[str, str, str]]  # (a, b, kind)
    evidence: list[Evidence]
    meta: dict = field(default_factory=dict)

    # --- travel ------------------------------------------------------------
    def neighbours(self, a: str) -> list[tuple[str, int]]:
        adj = self.meta.get("_adj")
        if adj is None:
            adj = {}
            for (x, b), d in self.travel.items():
                adj.setdefault(x, []).append((b, d))
            adj = {x: sorted(v) for x, v in adj.items()}
            self.meta["_adj"] = adj
        return adj.get(a, [])

    def edge_open(self, a: str, b: str, t: int) -> bool:
        if not self.doors:
            return True
        key = (a, b) if (a, b) in self.doors else (b, a)
        return not any(s <= t < e for s, e in self.doors.get(key, []))

    def travel_time(self, a: str, b: str, t: int) -> int | None:
        """On-demand Dijkstra with edge conditions evaluated at traversal time (§4.3)."""
        if a == b:
            return 0
        dist = {a: t}
        pq = [(t, a)]
        while pq:
            d, u = heapq.heappop(pq)
            if u == b:
                return d - t
            if d > dist.get(u, 10**9):
                continue
            for v, w in self.neighbours(u):
                if not self.edge_open(u, v, d):
                    continue
                nd = d + w
                if nd < dist.get(v, 10**9):
                    dist[v] = nd
                    heapq.heappush(pq, (nd, v))
        return None

    def route(self, a: str, b: str, t: int) -> list[str] | None:
        """Node sequence of the shortest open route at time t (for the planner). Private rooms
        (I-48) are never intermediate nodes."""
        if a == b:
            return [a]
        dist, prev = {a: t}, {}
        pq = [(t, a)]
        while pq:
            d, u = heapq.heappop(pq)
            if u == b:
                path = [b]
                while path[-1] != a:
                    path.append(prev[path[-1]])
                return path[::-1]
            if d > dist.get(u, 10**9):
                continue
            if u != a and self.locs[u].private:
                continue  # may arrive at a private room only as the destination
            for v, w in self.neighbours(u):
                if not self.edge_open(u, v, d):
                    continue
                nd = d + w
                if nd < dist.get(v, 10**9):
                    dist[v], prev[v] = nd, u
                    heapq.heappush(pq, (nd, v))
        return None

    # --- presence / FactIndex (§4.6–4.7) ----------------------------------
    def living(self) -> list[str]:
        return [a for a, x in self.actors.items() if x.role == "living"]

    def loc_at(self, actor: str, t: int) -> str | None:
        for sg in self.segments.get(actor, []):
            if sg.s <= t < sg.e:
                return sg.loc
        return None

    def attention_at(self, actor: str, t: int) -> float:
        for sg in self.segments.get(actor, []):
            if sg.s <= t < sg.e:
                return sg.attention
        return 0.0

    def truth_value(self, p: Prop) -> bool | None:
        """FactIndex.truth_value by containment/overlap rules per predicate (§4.7)."""
        if p.kind == "At":
            return all(self.loc_at(p.actor, t) == p.loc for t in ticks(p.iv))
        if p.kind == "NotAt":
            return all(self.loc_at(p.actor, t) != p.loc for t in ticks(p.iv))
        if p.kind == "Did":
            return any(self.loc_at(p.actor, t) == p.loc for t in ticks(p.iv))
        if p.kind == "Saw":
            if p.actor is None:  # an unidentified figure: someone was there
                return any(self.loc_at(x, t) == p.loc for x in self.actors for t in ticks(p.iv))
            return any(self.loc_at(p.actor, t) == p.loc for t in ticks(p.iv))
        if p.kind == "Died":
            return p.actor == self.victim and p.loc == self.murder_loc and p.iv[0] <= self.t_m < p.iv[1]
        if p.kind == "NoStranger":
            return True  # the canonical world contains only the cast
        if p.kind == "Heard":
            kind = "Attack" if p.extra[0] == "struggle" else "Speak"
            evs = [e for e in self.events if e.kind == kind and e.loc == p.loc and iv_inter(e.iv, p.iv)]
            if not evs:
                return False
            if p.actor:
                return any(e.actor == p.actor for e in evs)
            if p.extra[1]:
                return any(self.actors[e.actor].attrs.get("sex") == p.extra[1] for e in evs)
            return True
        if p.kind == "Attr":
            return self.actors[p.actor].attrs.get(p.extra[0]) == p.extra[1]
        return None


# ------------------------------------------------------------------ physics
def check_physics(w: World) -> list[str]:
    """P-1 presence uniqueness, P-2 travel feasibility, P-4 attack co-location, P-9 temporal grounding."""
    v: list[str] = []
    for a, segs in w.segments.items():
        segs = sorted(segs, key=lambda s: s.s)
        for i, sg in enumerate(segs):
            if sg.e <= sg.s:
                v.append(f"P-0 empty segment {a} {sg}")
            if i:
                prev = segs[i - 1]
                if sg.s < prev.e:
                    v.append(f"P-1 {a} overlaps {prev.loc}[{prev.s},{prev.e}) / {sg.loc}[{sg.s},{sg.e})")
                    continue
                # half-open intervals: last tick in prev is prev.e-1; arrival tick >= (prev.e-1) + travel
                tt = w.travel_time(prev.loc, sg.loc, prev.e - 1)
                if tt is None or sg.s - (prev.e - 1) < tt:
                    v.append(f"P-2 {a} {prev.loc}->{sg.loc} gap {sg.s - (prev.e - 1)} < travel {tt}")
    if w.loc_at(w.murderer, w.t_m) != w.murder_loc or w.loc_at(w.victim, w.t_m) != w.murder_loc:
        v.append("P-4 attacker/victim not co-located at t_m")
    for ev in w.evidence:
        for imp in ev.implications:
            if imp.prop.iv and not imp.requires and ev.established_iv is not None:
                s, e = ev.established_iv
                if not (s <= imp.prop.iv[0] and imp.prop.iv[1] <= e):
                    v.append(f"P-9 {ev.id}: {imp.prop} spans more than established {ev.established_iv} with no requires")
    return v
