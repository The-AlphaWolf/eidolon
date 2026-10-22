"""Derived world state (§4.6): `world_at(t)` and `presence(actor)`.

Never authored by hand, never the primary record: both are pure folds over the CaseLog
(§4.1). `t_investigation` is the tick at which play begins; the world is frozen there.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .events import Event
from .ids import ActorId, LocationId, ObjectId
from .interval import Interval, contains_tick

CaseLog = tuple[Event, ...]

ATTENTION_ATTR = "attention"
ATTENTION_DEFAULT = 1.0  # awake & idle (§4.8 rule 4), used when a Stay event states none


class WorldState(BaseModel):
    """§4.6. Frozen/hashable: replay determinism (I-5) needs equal states to hash equal."""
    model_config = ConfigDict(frozen=True)

    t: int
    actor_at: dict[ActorId, LocationId] = {}
    object_at: dict[ObjectId, LocationId | ActorId] = {}
    object_state: dict[ObjectId, dict[str, str]] = {}
    actor_state: dict[ActorId, dict[str, str]] = {}
    location_state: dict[LocationId, dict[str, str]] = {}


def ordered_events(events: CaseLog) -> list[Event]:
    """The CaseLog's canonical order (§4.1: the log is a *set* of events; every fold over it
    must impose the same order or the derivation is not a function of the case). Ordering is
    total — `(start, end, id)` — so two logs with equal content fold identically regardless
    of the order they were authored or serialized in."""
    return sorted(events, key=lambda e: (e.interval[0], e.interval[1], e.id))


_ordered = ordered_events  # internal alias, kept for readability at the fold sites


def world_at(events: CaseLog, t: int) -> WorldState:
    """Fold effects of events with `t_end <= t`, plus in-progress `ActorAt` for events
    spanning `t` (§4.6). Later events (by interval) override earlier ones for the same key."""
    actor_at: dict[ActorId, LocationId] = {}
    object_at: dict[ObjectId, LocationId | ActorId] = {}
    object_state: dict[ObjectId, dict[str, str]] = {}
    actor_state: dict[ActorId, dict[str, str]] = {}
    location_state: dict[LocationId, dict[str, str]] = {}

    for e in _ordered(events):
        done = e.interval[1] <= t
        spanning = contains_tick(e.interval, t)
        if not (done or spanning):
            continue
        for eff in e.effects:
            if eff.kind == "ActorAt":
                if done or spanning:
                    actor_at[eff.actor] = eff.location
            elif not done:
                continue
            elif eff.kind == "ObjectAt":
                object_at[eff.object] = eff.holder
            elif eff.kind == "ObjectState":
                object_state.setdefault(eff.object, {})[eff.attr] = eff.value
            elif eff.kind == "ActorState":
                actor_state.setdefault(eff.actor, {})[eff.attr] = eff.value
            # TraceCreated / InformationTransferred carry no WorldState-visible delta here;
            # they are read directly off the CaseLog by the evidence system (Phase 3).

    # `location_state` (door/light schedules, §4.3) has no Effect variant in the closed
    # union yet — no fixture needs one in Phase 1. Left empty rather than invented.
    return WorldState(t=t, actor_at=actor_at, object_at=object_at, object_state=object_state,
                       actor_state=actor_state, location_state=location_state)


def presence(events: CaseLog, actor: ActorId) -> list[tuple[Interval, LocationId]]:
    """`presence(actor) -> [(Interval, Location)]` (§4.6): maximal presence segments, derived
    from every event's `ActorAt` effect for this actor, merging touching same-location runs."""
    raw: list[tuple[Interval, LocationId]] = []
    for e in _ordered(events):
        for eff in e.effects:
            if eff.kind == "ActorAt" and eff.actor == actor:
                raw.append((e.interval, eff.location))
    raw.sort(key=lambda x: x[0][0])
    merged: list[tuple[Interval, LocationId]] = []
    for iv, loc in raw:
        if merged and merged[-1][1] == loc and merged[-1][0][1] == iv[0]:
            prev_iv, _ = merged[-1]
            merged[-1] = ((prev_iv[0], iv[1]), loc)
        else:
            merged.append((iv, loc))
    return merged


def death_ticks(events: CaseLog) -> dict[ActorId, int]:
    """First tick at which each actor is dead, derived from the CaseLog (§4.9 P-4: death is
    `ActorState(actor, "alive", "false")` — the closed schema has no "Died" predicate).

    Actors absent from the mapping never die in this case. This is the single authority on
    who is alive when: `Actor.role` is authored metadata about a character's narrative
    function, not a fact about the timeline, and reading eligibility off `role` is what let
    a corpse go on witnessing (§4.8) while a victim who was alive for two thirds of the
    evening perceived nothing at all.
    """
    dead: dict[ActorId, int] = {}
    for e in _ordered(events):
        for eff in e.effects:
            if eff.kind == "ActorState" and eff.attr == "alive" and eff.value == "false":
                dead[eff.actor] = min(dead.get(eff.actor, e.interval[0]), e.interval[0])
    return dead


def loc_at(events: CaseLog, actor: ActorId, t: int) -> LocationId | None:
    for iv, loc in presence(events, actor):
        if contains_tick(iv, t):
            return loc
    return None


def unlocated(events: CaseLog, actor: ActorId, t: int) -> bool:
    """True when the actor is at no location at `t` — in transit, or offstage.

    This is a *determination*, not missing information. §4.1: the CaseLog "contains every
    Event of the fiction from case epoch to `t_investigation`", so presence is total — a tick
    with no covering segment means the actor was in no room, either on a travel edge longer
    than one tick (§4.9 P-2 gives intermediate *nodes* a 1-tick presence; a direct 3-minute
    edge has no node to stand in) or not in the modelled world at all.

    It is what keeps `NotAt` over those ticks True rather than Unknown, per §4.7's rule that
    "`Unknown` arises only for `Incidental` and for attributes never defined".
    """
    return loc_at(events, actor, t) is None


def attention_at(events: CaseLog, actor: ActorId, t: int) -> float:
    """Attention level at `t` (§4.8 rule 4), read off the presence-defining event's own
    `ActorState(attention)` effect; unstated defaults to awake & idle (1.0)."""
    for e in _ordered(events):
        if not contains_tick(e.interval, t):
            continue
        has_actor_at = any(eff.kind == "ActorAt" and eff.actor == actor for eff in e.effects)
        if not has_actor_at:
            continue
        for eff in e.effects:
            if eff.kind == "ActorState" and eff.actor == actor and eff.attr == ATTENTION_ATTR:
                return float(eff.value)
        return ATTENTION_DEFAULT
    return 0.0  # actor not present anywhere at t
