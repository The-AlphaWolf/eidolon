"""`FactIndex.truth_value` (§4.7): `Proposition -> True | False | Unknown(None)` by
containment/overlap rules per predicate. `Unknown` arises only for `Incidental` and for
attributes never defined (§4.7 note).

Presence predicates never return Unknown: the CaseLog is complete (§4.1), so an actor with
no covering presence segment at `t` is *determinately* in no room (`UNLOCATED`) rather than
unaccounted for. Object and attribute predicates still can — an attribute the case never
defines has no value to compare against, which is exactly the case §4.7 names.
"""
from __future__ import annotations

from typing import Iterable

from .actions import ENTAILED_ACTIONS, entailing_kinds
from .case import Case
from .interval import contains_tick, overlaps, ticks
from .perception import PerceptionFact, derive_perception
from .propositions import Proposition
from .state import loc_at, presence, world_at

# Sentinel placement: the actor is in no room at all (in transit, or offstage). Not a
# LocationId, so it compares unequal to every real location and satisfies every `NotAt`.
UNLOCATED = "\x00unlocated"

# `Did.action`/`DidNot.action` are the closed `ActionKind` vocabulary (§4.7, ADR-22), and
# `world/actions.py` owns the entailment from an action to the `EventKind`s that make it
# true. An action with no entailment row is not something the world says is FALSE — it is
# something the world cannot express at all, which is exactly §4.7's "attributes never
# defined" case for Unknown. `ActionKind` makes that unreachable through normal
# construction; the guard below stays because `model_construct`/`model_copy(update=…)`
# bypass validation, and because a future ADR could add a vocabulary member without adding
# its entailment. Reporting Unknown rather than False is what stops the gap from
# manufacturing refutations: P-0 would otherwise flag such an implication as contradicted by
# a world that has no opinion on it.


def _universal(values: Iterable[object | None], expected: object) -> bool | None:
    """True iff every value equals `expected`; False iff any value contradicts it; Unknown
    (None) iff some value is missing (a coverage gap) and the rest do not contradict."""
    gap = False
    for v in values:
        if v is None:
            gap = True
        elif v != expected:
            return False
    return None if gap else True


class FactIndex:
    """Built once per `Case`; derivations (presence, perception) are computed eagerly since
    Phase 1 case sizes are small (§13.2a: <= 8 actors, <= 20 locations, <= 720 ticks)."""

    def __init__(self, case: Case):
        self.case = case
        self.perception: list[PerceptionFact] = derive_perception(case)

    # ------------------------------------------------------------------ dispatch
    def truth_value(self, prop: Proposition) -> bool | None:
        method = getattr(self, f"_tv_{prop.kind}", None)
        if method is None:
            return None
        return method(prop)

    # ------------------------------------------------------------------ presence
    def _placement(self, actor, t):
        """Where `actor` is at `t`: a LocationId, or `UNLOCATED` (in no room at all).

        Never None: the CaseLog is complete (§4.1), so presence is total and `UNLOCATED` is
        a definite placement (`state.unlocated`) that contradicts any `At` and satisfies any
        `NotAt`. Presence therefore contributes no Unknown, matching §4.7's rule that Unknown
        arises only for `Incidental` and for attributes never defined.
        """
        loc = loc_at(self.case.events, actor, t)
        return loc if loc is not None else UNLOCATED

    def _tv_At(self, p) -> bool | None:
        vals = [self._placement(p.actor, t) for t in ticks(p.interval)]
        return _universal(vals, p.location)

    def _tv_NotAt(self, p) -> bool | None:
        return all(self._placement(p.actor, t) != p.location for t in ticks(p.interval))

    def _tv_Moved(self, p) -> bool | None:
        segs = presence(self.case.events, p.actor)
        if not segs:
            return None
        for (i1, l1), (i2, l2) in zip(segs, segs[1:]):
            if l1 == p.from_loc and l2 == p.to_loc and i1[1] - 1 <= p.t <= i2[0]:
                return True
        return False

    # ------------------------------------------------------------------ action
    def _matching_events(self, actor, kinds, interval, object=None, target_actor=None, location=None):
        """Events by `actor` whose kind is one of `kinds` and whose slots match. `kinds` is a
        SET, not a single kind: an entailed action like `touch` is made true by any of several
        event kinds (§4.7, `actions.ACTION_ENTAILED_BY`)."""
        for e in self.case.events:
            if e.actor != actor or e.kind not in kinds:
                continue
            if not overlaps(e.interval, interval):
                continue
            if object is not None and object not in e.objects:
                continue
            if location is not None and e.location != location:
                continue
            if target_actor is not None and target_actor not in e.participants:
                continue
            yield e

    def _tv_Did(self, p) -> bool | None:
        kinds = entailing_kinds(p.action)
        if kinds is None:
            return None  # no entailment rule: Unknown, not refuted (see the note above)
        matches = self._matching_events(p.actor, kinds, p.interval, p.object, p.target_actor, p.location)
        if p.action in ENTAILED_ACTIONS and p.object is None:
            # `Did(a, "touch", object=None)` asks whether the actor handled ANY object, so the
            # matched event has to name one. Without this a bare-handed `Attack` — which
            # carries no `objects` — would satisfy a claim about object contact.
            matches = (e for e in matches if e.objects)
        return next(matches, None) is not None

    def _tv_DidNot(self, p) -> bool | None:
        did = self._tv_Did(p)
        return None if did is None else not did

    # ------------------------------------------------------------------ perception
    def _tv_Saw(self, p) -> bool | None:
        if p.subject == "nobody":
            # "I saw no one there" is a claim about the room's occupancy over the interval,
            # not about the cast list. It is False the moment any other actor is placed in
            # `p.location` during `p.interval` (§4.7: containment/overlap rules per
            # predicate) — never a blanket True, which would make every "the room was empty"
            # alibi canonically sound regardless of who was standing in it.
            return not any(self._placement(actor, t) == p.location
                            for t in ticks(p.interval)
                            for actor in self.case.actors if actor != p.observer)
        for f in self.perception:
            if f.proposition.kind != "Saw" or f.observer != p.observer or f.proposition.location != p.location:
                continue
            if not overlaps(f.proposition.interval, p.interval):
                continue
            if f.proposition.subject == p.subject and f.proposition.identified == p.identified:
                return True
        return False

    def _tv_Heard(self, p) -> bool | None:
        for f in self.perception:
            if f.proposition.kind != "Heard" or f.observer != p.observer:
                continue
            if f.proposition.from_location != p.from_location or f.proposition.sound_kind != p.sound_kind:
                continue
            if not overlaps(f.proposition.interval, p.interval):
                continue
            if f.proposition.identified_actor == p.identified_actor:
                return True
        return False

    # ------------------------------------------------------------------ objects
    def _tv_Has(self, p) -> bool | None:
        vals = [self.case_object_holder(p.object, t) for t in ticks(p.interval)]
        return _universal(vals, p.actor)

    def _tv_ObjectAt(self, p) -> bool | None:
        vals = [self.case_object_holder(p.object, t) for t in ticks(p.interval)]
        return _universal(vals, p.holder)

    def _tv_ObjectState(self, p) -> bool | None:
        vals = [world_at(self.case.events, t).object_state.get(p.object, {}).get(p.attr) for t in ticks(p.interval)]
        return _universal(vals, p.value)

    def case_object_holder(self, object_id, t):
        """Where `object_id` is at `t`: its last `EffObjectAt` holder, else its authored
        `Object.initial_location`.

        `world_at().object_at` only gains an entry once some event MOVES the object (§4.6),
        but an object nobody ever touches is still PLACED — at `Object.initial_location` —
        so "no entry" is not "the world has no opinion". Without the fallback every
        `Has`/`ObjectAt` claim about an unmoved object resolved to Unknown, and P-0 could
        not refute an evidence implication that put the murder weapon in the wrong room.

        This is the one authority on the question. `evidence.grounding` applied the same
        fallback to `Evidence.location_at_investigation` while `FactIndex` did not, which
        left the same question answered two different ways in two modules.
        """
        moved = world_at(self.case.events, t).object_at.get(object_id)
        if moved is not None:
            return moved
        obj = self.case.objects.get(object_id)
        return obj.initial_location if obj is not None else None

    # ------------------------------------------------------------------ attributes / state
    def _tv_Attr(self, p) -> bool | None:
        actor = self.case.actors.get(p.entity)
        obj = self.case.objects.get(p.entity)
        attrs = actor.static_attrs if actor else (obj.static_attrs if obj else None)
        if attrs is None or p.attr not in attrs:
            return None
        return attrs[p.attr] == p.value

    def _tv_State(self, p) -> bool | None:
        vals = [world_at(self.case.events, t).actor_state.get(p.actor, {}).get(p.attr) for t in ticks(p.interval)]
        return _universal(vals, p.value)

    # ------------------------------------------------------------------ authored graphs
    def _tv_Rel(self, p) -> bool | None:
        for r in self.case.rels:
            if r.rel_kind != p.rel_kind:
                continue
            if {r.a, r.b} == {p.a, p.b}:
                return p.value is None or r.value == p.value
        return False

    def _tv_Attitude(self, p) -> bool | None:
        for r in self.case.attitudes:
            if r.a == p.a and r.b == p.b and r.attitude_kind == p.attitude_kind:
                return r.intensity == p.intensity
        return False

    def _tv_Motive(self, p) -> bool | None:
        for r in self.case.motives:
            if r.actor == p.actor and r.victim == p.victim and r.motive_kind == p.motive_kind:
                return r.strength == p.strength
        return False

    # ------------------------------------------------------------------ reported speech
    def _tv_Said(self, p) -> bool | None:
        for e in self.case.events:
            if not contains_tick(e.interval, p.t) and e.interval[0] != p.t:
                continue
            for eff in e.effects:
                if eff.kind == "InformationTransferred" and eff.from_actor == p.speaker and eff.to_actor == p.listener:
                    if p.proposition in eff.propositions:
                        return True
        return False

    # ------------------------------------------------------------------ solution / runtime-only
    def _tv_Solution(self, p) -> bool | None:
        """Light derivation: an `Attack` by `p.murderer` on the victim at `p.location`
        overlapping `p.interval`. `motive_kind` is cross-checked only if a matching `Motive`
        fact was authored — the full solution-scoring rule (§16.3) belongs to Phase 4/6."""
        for e in self.case.events:
            if e.kind == "Attack" and e.actor == p.murderer and e.location == p.location and overlaps(e.interval, p.interval):
                for r in self.case.motives:
                    if r.actor == p.murderer and r.motive_kind != p.motive_kind:
                        return False
                return True
        return False

    def _tv_Incidental(self, p) -> bool | None:
        return None  # runtime-only soft claim; never a canonical fact (§4.7, §14.4)
