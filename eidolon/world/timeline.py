"""§4.10 Timeline query API — "used by every other subsystem".

§4.10 names seven entry points. Six are pure world queries and live here; the seventh,
`information_reach(proposition, t) -> {actor: KnowledgeEntry}`, returns a `minds/` model and
so lives on `minds.knowledge.KnowledgeStore` — §23.1's dependency direction is one-way
(`world <- minds`), and `world/` may not name a `KnowledgeEntry`.

Nothing here is a new derivation: every function is a projection of `state.presence`,
`space.TravelGraph` and `perception.derive_perception`, so a caller cannot get a different
answer from this module than from the model those three define.
"""
from __future__ import annotations

from typing import Literal

from .case import Case
from .events import Event
from .ids import ActorId, LocationId
from .interval import Interval, intersect, overlaps, subtract, ticks
from .perception import (
    ATTENTION_PRESENT, IDENTIFY_THRESHOLD, PERCEIVE_THRESHOLD, PerceptionFact,
    _perception_quality, derive_perception,
)
from .state import WorldState, attention_at, death_ticks, ordered_events, presence

Modality = Literal["sight", "sound", "participation"]


def who_was_at(case: Case, location: LocationId, interval: Interval) -> dict[ActorId, Interval]:
    """§4.10 `who_was_at(location, interval) -> {actor: Interval}`.

    The value is the actor's presence at `location` clipped to `interval`. `presence()`
    already merges touching same-location runs, so an actor with two entries in the window
    genuinely left and came back; only the EARLIEST such visit is reported, because the
    signature carries one interval per actor and hulling two visits would assert presence
    across the gap between them. Callers needing every visit read `presence()` directly.
    """
    out: dict[ActorId, Interval] = {}
    for actor in sorted(case.actors):
        for seg, loc in presence(case.events, actor):
            if loc != location:
                continue
            overlap = intersect(seg, interval)
            if overlap is not None:
                out[actor] = overlap
                break
    return out


def events_at(case: Case, location: LocationId, interval: Interval) -> list[Event]:
    """§4.10 `events_at(location, interval) -> [Event]`, in the CaseLog's canonical order."""
    return [e for e in ordered_events(case.events)
            if e.location == location and overlaps(e.interval, interval)]


def could_reach(case: Case, actor: ActorId, location: LocationId, by_t: int,
                 from_state: WorldState | None = None) -> bool:
    """§4.10 `could_reach(actor, location, by_t, from_state?) -> bool` — "travel + presence".

    Origin is `from_state` when supplied (its `t` is the departure tick), otherwise the
    actor's own last canonical placement at or before `by_t`. True iff the remaining time
    covers `travel_time` on the open graph at the departure tick. An actor with no placement
    at or before `by_t`, or with no open route, cannot reach it.

    Note what "last canonical placement" means when the actor is IN a segment spanning
    `by_t`: the origin tick is `by_t` itself, so the answer reduces to "are they already
    there" — which is the right answer, because §4.1's CaseLog says where they are and P-1
    says it is one place. The query earns its keep on the two cases that are not trivial:
    an actor in transit at `by_t` (the origin is the tick they left, and the edge cost
    decides), and a counterfactual `from_state` — which is how the cover-story planner asks
    "granting this claimed position, could they still have made it?".
    """
    if from_state is not None:
        origin_t, origin_loc = from_state.t, from_state.actor_at.get(actor)
    else:
        origin_t, origin_loc = None, None
        for seg, loc in presence(case.events, actor):
            if seg[0] > by_t:
                break
            origin_t, origin_loc = min(by_t, seg[1] - 1), loc
    if origin_loc is None or origin_t is None or origin_t > by_t:
        return False
    if origin_loc == location:
        return True
    minutes = case.travel_graph.travel_time(origin_loc, location, origin_t)
    return minutes is not None and by_t - origin_t >= minutes


def could_observe(case: Case, actor: ActorId, event: Event) -> tuple[bool, float, Modality | None]:
    """§4.10 `could_observe(actor, event) -> (bool, quality, modality)`, on §4.8's own rules
    and thresholds — the best modality over the ticks the actor was alive, placed and
    attentive during the event.

    A participant (the event's own actor, or one of `participants`) has first-hand access by
    §4.8 rule 1 regardless of how perceptible the event is to a bystander, and is reported at
    quality 1.0 under the `"participation"` modality, matching the `Participated` provenance
    `derive_perception` emits for them.
    """
    if actor == event.actor or actor in event.participants:
        return True, 1.0, "participation"
    death = death_ticks(case.events).get(actor)
    segs = presence(case.events, actor)
    best, best_modality = 0.0, None
    for t in ticks(event.interval):
        if death is not None and t >= death:
            break
        here = next((loc for seg, loc in segs if seg[0] <= t < seg[1]), None)
        if here is None:
            continue
        att = attention_at(case.events, actor, t)
        if att < ATTENTION_PRESENT:
            continue
        for modality, base in (("sight", event.perceptibility.sight),
                                ("sound", event.perceptibility.sound)):
            quality = base * att * (1.0 if here == event.location
                                    else _perception_quality(case, here, event.location, modality))
            if quality > best:
                best, best_modality = quality, modality
    return best >= PERCEIVE_THRESHOLD, round(best, 3), best_modality


def possible_window(case: Case, actor: ActorId, location: LocationId,
                     facts: list[PerceptionFact] | None = None) -> list[Interval]:
    """§4.10 `possible_window(actor, location) -> [Interval]` — "gaps where presence is
    unconstrained (used by cover-story planner: where a lie is *not* refuted)".

    §4.1 makes the CaseLog complete, so presence is never unconstrained in the canonical
    world; what the cover-story planner needs is where a claim of being at `location` is not
    refuted by SOMEONE ELSE'S perception. So a tick is excluded when another actor's §4.8
    fact either places `actor` at a different location (an identified sighting or a
    co-presence), or certifies `actor`'s absence FROM `location` (§4.8 rule 7 / I-34). The
    actor's own facts never constrain them — the whole point is that the truth is elsewhere.

    Travel feasibility is a separate question and a separate §4.10 entry point: a window this
    function returns still has to pass `could_reach`.

    `facts` lets a caller pass perception it already derived (`FactIndex(case).perception`);
    omitted, the model is re-derived per call, which is the dominant cost of this query.
    """
    refuted: list[Interval] = []
    for fact in (derive_perception(case) if facts is None else facts):
        if fact.observer == actor:
            continue
        prop = fact.proposition
        if prop.kind == "At" and prop.actor == actor and prop.location != location:
            refuted.append(prop.interval)
        elif prop.kind == "NotAt" and prop.actor == actor and prop.location == location:
            refuted.append(prop.interval)
        elif (prop.kind == "Saw" and prop.identified and prop.subject == actor
              and fact.reliability >= IDENTIFY_THRESHOLD and prop.location != location):
            refuted.append(prop.interval)
        elif prop.kind == "Did" and prop.actor == actor and prop.location not in (None, location):
            refuted.append(prop.interval)
    return subtract((0, case.t_investigation), refuted)
