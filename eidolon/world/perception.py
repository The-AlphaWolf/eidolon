"""Perception model (§4.8): how observation facts are derived. Deterministic; the
thresholds are named constants here (not per-case data yet — no Phase 1 fixture tunes
them; a case-level override is a cheap follow-up once generation exists, Phase 6).

Produces `PerceptionFact` records — grounded observations with provenance and reliability.
This is deliberately *not* the `KnowledgeEntry`/`EpistemicState` of §6.2 (Phase 2, `minds/`):
Phase 1 owns the derivation that decides what a character could perceive; Phase 2 folds
these into the full knowledge/belief/memory layers. `minds/` will build on this module's
output rather than recomputing perception quality.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .case import Case
from .ids import ActorId, LocationId
from .interval import Interval, contains_tick, intersect, subtract, ticks
from .propositions import At, Did, Has, Heard, NotAt, ObjectAt, ObjectState, Proposition, Saw, State
from .state import _ordered, attention_at, death_ticks, loc_at, presence

# `Stay` is presence bookkeeping, not an action: rule 1 already emits the actor's own `At`
# for the same segment at reliability 1.0, and `Did(x, "Stay", I, L)` carries strictly less
# than that. Excluded from participation facts so the store gains no redundant rows (§4.7's
# extraction rules list `At` from presence and `Did` from event kinds as separate sources).
_PRESENCE_ONLY_KINDS = {"Stay"}

ATTENTION_PRESENT = 0.3   # §4.8 rule 4/6
ATTENTION_AWAKE = 0.7     # §4.8 rule 7 / I-34
PERCEIVE_THRESHOLD = 0.2  # §4.8 rule 5
IDENTIFY_THRESHOLD = 0.6  # §4.8 rule 5
ABSENCE_DISCOUNT = 0.8    # §4.8 rule 7
G_OWN = 2                 # granularity (minutes) of own-presence / co-presence claims
G_EVENT = 5               # granularity of routine-event sightings

PerceptionSource = Literal["Participated", "CoPresence", "Absence", "Witnessed"]


@dataclass(frozen=True)
class Absence:
    """§4.8 rule 7 payload, carried alongside the `NotAt` fact it grounds."""
    basis: Literal["continuous", "scan", "inference"]
    coverage: float
    entrances_covered: bool


@dataclass(frozen=True)
class PerceptionFact:
    """A grounded observation (world-level; not yet a character's `KnowledgeEntry`, §6.2)."""
    id: str
    observer: ActorId
    proposition: Proposition
    source: PerceptionSource
    reliability: float
    obs_location: LocationId
    obs_interval: Interval          # observer's presence segment during the observation (I-46 rule 9)
    provenance: tuple[str, ...] = ()  # perception-event ids (I-37 disjointness)
    granularity: int = G_OWN
    absence: Absence | None = None


def _runs(vals: list[tuple[int, object]]) -> list[tuple[int, int, object]]:
    """Merge consecutive ticks sharing a payload into maximal `(start, end, payload)` runs."""
    out: list[tuple[int, int, object]] = []
    for t, v in vals:
        if out and out[-1][1] == t and out[-1][2] == v:
            out[-1] = (out[-1][0], t + 1, v)
        else:
            out.append((t, t + 1, v))
    return out


def _perception_quality(case: Case, obs_loc: LocationId, target_loc: LocationId, modality: str) -> float:
    if obs_loc == target_loc:
        return 1.0
    best = 0.0
    for pe in case.perception_edges:
        if pe.observer_at == obs_loc and pe.perceives == target_loc and pe.modality == modality:
            best = max(best, pe.quality)
    return best


def _segment_containing(segs: list[tuple[Interval, LocationId]], t: int) -> Interval:
    for iv, _loc in segs:
        if contains_tick(iv, t):
            return iv
    return (t, t + 1)


_CACHE: list[tuple[Case, list]] = []   # newest last; holds the Case so `is` can never alias a freed one
_CACHE_SIZE = 8


def derive_perception(case: Case) -> list[PerceptionFact]:
    """Memoised `_derive_perception`. A `Case` is immutable after construction (I-4) and the
    derivation is a pure function of it (I-5, I-6), so a hit is exactly what a rerun would return;
    the cache exists because Phase 6 asks for the same case's perception ~25 times per candidate
    (`FactIndex`, knowledge, the solver's testimony atoms, distortions, retrieval)."""
    for c, facts in reversed(_CACHE):
        if c is case:
            return list(facts)
    facts = _derive_perception(case)
    _CACHE.append((case, facts))
    del _CACHE[:-_CACHE_SIZE]
    return list(facts)


def _derive_perception(case: Case) -> list[PerceptionFact]:
    """§4.8 rules 1-9 over the whole CaseLog. Deterministic; no case-level RNG (I-6)."""
    facts: list[PerceptionFact] = []
    n = 0

    def emit(observer, prop, source, reliability, obs_loc, obs_iv, provenance, granularity, absence=None):
        nonlocal n
        n += 1
        facts.append(PerceptionFact(f"P{n:04d}", observer, prop, source, round(reliability, 3),
                                     obs_loc, obs_iv, tuple(provenance), granularity, absence))

    # Who can perceive is decided by the CaseLog, not by `Actor.role`. An actor perceives
    # exactly while they are alive: up to their death tick (§4.9 P-4's own `alive=false`
    # marker) and not one tick past it. `case.living_actors()` answers a different question
    # — who is still interrogable at `t_investigation` — and using it here had two effects,
    # both wrong: the victim contributed no perception at all despite being alive for most
    # of the evening, and any OTHER actor killed mid-case would have kept witnessing (and
    # kept supplying absence alibis) from beyond the grave.
    #
    # `all_actors` can still be the *subject* of a co-presence/absence fact for the whole
    # log: a body in a room is as perceivable as a person in it.
    observers = sorted(a for a, act in case.actors.items() if act.role != "offstage")
    all_actors = sorted(case.actors)
    dead_at = death_ticks(case.events)
    horizon = case.t_investigation + 1

    def alive_until(a: ActorId) -> int:
        """First tick at which `a` no longer perceives anything."""
        return dead_at.get(a, horizon)

    segs = {a: presence(case.events, a) for a in all_actors}

    def obs_segment(a: ActorId, t: int) -> Interval:
        """The observer's presence segment backing an observation at `t` (I-46 rule 9),
        clipped at their death: the body stays in the room, the witness does not."""
        iv = _segment_containing(segs[a], t)
        return (iv[0], min(iv[1], alive_until(a)))

    # rules 1 (own presence) + 6 (co-presence) + 7 (absence, I-34)
    for a in observers:
        for i, (raw_iv, loc) in enumerate(segs[a]):
            # The observer only knows the part of their own presence segment they lived
            # through; the body's remaining presence is a fact about the room, not knowledge.
            iv = (raw_iv[0], min(raw_iv[1], alive_until(a)))
            if iv[1] <= iv[0]:
                continue
            ev_id = f"seg:{a}:{i}"
            att = attention_at(case.events, a, iv[0])
            emit(a, At(actor=a, location=loc, interval=iv), "Participated", 1.0, loc, iv, [ev_id], G_OWN)
            if att < ATTENTION_PRESENT:
                continue
            for x in all_actors:
                if x == a:
                    continue
                for xiv, xloc in segs[x]:
                    if xloc != loc:
                        continue
                    ov = intersect(iv, xiv)
                    if ov:
                        emit(a, At(actor=x, location=loc, interval=ov), "CoPresence", att, loc, iv, [ev_id], G_OWN)
            # §4.8.7 / I-34. Absence is the strictly stronger derivation: attention must hold
            # at ATTENTION_AWAKE *throughout* the claimed window, and the window is the
            # maximal sub-interval over which it actually did — not the whole segment by
            # extension. Sampling attention once at `iv[0]` (as an earlier version did) is
            # what made a character who dozed off after one minute a perfect absence witness
            # for the next hour, which is the v0.2 defect I-34 exists to prevent.
            if case.locations[loc].entrances_visible:
                awake = _runs([(t, attention_at(case.events, a, t)) for t in ticks(iv)])
                for run_start, run_end, run_att in awake:
                    if run_att < ATTENTION_AWAKE:
                        continue
                    covered = (run_start, run_end)
                    # coverage is 1.0 by construction: the claim is made over exactly the
                    # ticks that were watched, never widened past them.
                    r = run_att * 1.0 * ABSENCE_DISCOUNT
                    for x in all_actors:
                        if x == a:
                            continue
                        here = [xiv for xiv, xloc in segs[x] if xloc == loc]
                        for sub in subtract(covered, here):
                            ab = Absence(basis="continuous", coverage=1.0, entrances_covered=True)
                            emit(a, NotAt(actor=x, location=loc, interval=sub), "Absence", r,
                                 loc, iv, [ev_id], G_OWN, ab)

    # §4.8: "Participants of `e` receive `source=Participated, reliability=1.0` for the
    # event's own facts." The event's own facts are what §4.7's extraction rules read off it:
    # `Did` from the event kind, and `Has`/`ObjectAt`/`ObjectState`/`State` from its effects.
    # Effect-derived propositions are asserted over the single tick at which the effect has
    # landed (`world_at` applies an effect once `t_end <= t`), never extrapolated forward —
    # asserting a state beyond the tick the log establishes is exactly what I-30/P-9 forbids.
    for e in _ordered(case.events):
        if e.actor is None or e.kind in _PRESENCE_ONLY_KINDS:
            continue
        knowers = [a for a in ({e.actor} | set(e.participants))
                    if a in observers and e.interval[0] < alive_until(a)]
        if not knowers:
            continue
        after = (e.interval[1], e.interval[1] + 1)
        own_facts: list[Proposition] = []
        objects = e.objects or (None,)
        for obj in objects:
            own_facts.append(Did(actor=e.actor, action=e.kind, interval=e.interval,
                                  object=obj, location=e.location))
        for eff in e.effects:
            if eff.kind == "ObjectAt":
                own_facts.append(ObjectAt(object=eff.object, holder=eff.holder, interval=after))
                if eff.holder in case.actors:
                    own_facts.append(Has(actor=eff.holder, object=eff.object, interval=after))
            elif eff.kind == "ObjectState":
                own_facts.append(ObjectState(object=eff.object, attr=eff.attr, value=eff.value, interval=after))
            elif eff.kind == "ActorState":
                own_facts.append(State(actor=eff.actor, attr=eff.attr, value=eff.value, interval=after))
        for a in sorted(knowers):
            obs_iv = obs_segment(a, e.interval[0])
            for prop in own_facts:
                emit(a, prop, "Participated", 1.0, e.location, obs_iv, [e.id], G_OWN)

    # rules 2-5, 9 (event perception) + 8 (sustained identified observation via events)
    for e in case.events:
        if e.actor is None:
            continue
        for a in observers:
            if a == e.actor or a in e.participants:
                continue
            per_tick: list[tuple[int, tuple]] = []
            for t in ticks(e.interval):
                if t >= alive_until(a):
                    break
                la = loc_at(case.events, a, t)
                att = attention_at(case.events, a, t)
                if la is None or att < ATTENTION_PRESENT:
                    continue
                qs = e.perceptibility.sight * att if la == e.location else \
                    _perception_quality(case, la, e.location, "sight") * e.perceptibility.sight * att
                qh = e.perceptibility.sound * att if la == e.location else \
                    _perception_quality(case, la, e.location, "sound") * e.perceptibility.sound * att
                per_tick.append((t, (la, round(qs, 3), round(qh, 3))))
            for s, en, (la, qs, qh) in _runs(per_tick):
                run_iv = (s, en)
                obs_iv = obs_segment(a, s)  # I-46 rule 9: observer's presence segment
                pid = f"{e.id}@{a}"
                if qs >= PERCEIVE_THRESHOLD:
                    ident = qs >= IDENTIFY_THRESHOLD and e.perceptibility.identifies_actor
                    subject = e.actor if ident else "figure"
                    emit(a, Saw(observer=a, subject=subject, location=e.location, interval=run_iv, identified=ident),
                         "Witnessed", qs, la, obs_iv, [pid], G_EVENT)
                if qh >= PERCEIVE_THRESHOLD:
                    ident_actor = e.actor if (qh >= IDENTIFY_THRESHOLD and e.perceptibility.identifies_voice) else None
                    emit(a, Heard(observer=a, sound_kind=e.kind.lower(), from_location=e.location,
                                  interval=run_iv, identified_actor=ident_actor),
                         "Witnessed", qh, la, obs_iv, [pid], G_EVENT)

    # rule 8/9: sustained identified observation through a sight edge yields universal At,
    # otherwise an unidentified Saw("figure") — over runs of the *target's* presence, not
    # just event windows (covers Robert's ten-minute glow sighting of Elena, I-46).
    for a in observers:
        for x in all_actors:
            if x == a:
                continue
            per_tick = []
            for t in range(min(case.t_investigation, alive_until(a))):
                la = loc_at(case.events, a, t)
                lx = loc_at(case.events, x, t)
                att = attention_at(case.events, a, t)
                if la is None or lx is None or la == lx or att < ATTENTION_PRESENT:
                    continue
                q = _perception_quality(case, la, lx, "sight") * att
                if q >= PERCEIVE_THRESHOLD:
                    per_tick.append((t, (la, lx, round(q, 3))))
            for s, en, (la, lx, q) in _runs(per_tick):
                run_iv = (s, en)
                obs_iv = obs_segment(a, s)
                pid = f"see:{a}:{x}:{lx}:{s}"
                if q >= IDENTIFY_THRESHOLD:
                    emit(a, At(actor=x, location=lx, interval=run_iv), "Witnessed", q, la, obs_iv, [pid], G_OWN)
                else:
                    emit(a, Saw(observer=a, subject="figure", location=lx, interval=run_iv, identified=False),
                         "Witnessed", q, la, obs_iv, [pid], G_EVENT)
    return facts
