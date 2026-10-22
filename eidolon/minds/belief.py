"""Belief formation (§6.4): generation-time, deterministic rules over `KnowledgeEntry`.

Belief != Knowledge (§6.1): a belief can be false, is confidence-weighted, and can be
revised. Nothing here writes back into `KnowledgeStore` or `Case` — beliefs are a pure
derivation, sealed at generation the same way `Memory` is (§6.3); runtime revision is the
`EpistemicState.belief_confidence` overlay (`epistemic.py`), never this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from pydantic import BaseModel, ConfigDict

from ..world.case import Case
from ..world.facts import FactIndex
from ..world.ids import ActorId
from ..world.interval import overlaps, widen
from ..world.propositions import Attitude, Proposition
from .ids import BeliefId, KnowledgeEntryId
from .knowledge import KnowledgeEntry, KnowledgeStore
from .provenance import Told
from .scale import Bp, bp

# §6.4 rule 1/2 thresholds
DIRECT_THRESHOLD = 0.6
UNCERTAIN_LOW = 0.2

# "near scene" margin for the opportunity inference rule (§6.4 rule 4), minutes each side
# of the death interval. Not specified numerically by the architecture; chosen so a
# character who was in the murder room shortly before/after death is flagged, matching
# the murderer's own excursion window shape used throughout §29.1's worked case.
OPPORTUNITY_MARGIN = 15

# §19.5's collusion-graph "close" relation kinds, reused as the trust heuristic's closeness
# test (§6.4 rule 3 needs `trust(A->B)`, which the architecture names but never defines a
# formula for — this is the documented, smallest deterministic choice: authored `Rel`
# closeness raises trust, everything else is neutral).
CLOSE_RELS = {"spouse", "lover", "sibling", "parent", "child", "employer", "partner", "accomplice"}
TRUST_CLOSE = 0.8
TRUST_DEFAULT = 0.5


class Belief(BaseModel):
    """§6.2. `confidence_0` is the SEALED initial confidence; current confidence at runtime
    is `EpistemicState.belief_confidence.get(id, confidence_0)` (§6.3, AC-4) — this model
    never changes after formation."""
    model_config = ConfigDict(frozen=True)

    id: BeliefId
    character: ActorId
    proposition: Proposition
    confidence_0: Bp
    grounds: tuple[KnowledgeEntryId | BeliefId, ...]
    formed_at: int
    is_true: bool  # engine-only, via FactIndex


class BeliefStore:
    def __init__(self, beliefs: Iterable[Belief] = ()):
        self._by_id: dict[str, Belief] = {}
        self._by_character: dict[ActorId, list[Belief]] = {}
        for b in beliefs:
            self.add(b)

    def add(self, belief: Belief) -> None:
        if belief.id in self._by_id:
            raise ValueError(f"duplicate Belief id: {belief.id}")
        self._by_id[belief.id] = belief
        self._by_character.setdefault(belief.character, []).append(belief)

    def get(self, belief_id: BeliefId) -> Belief | None:
        return self._by_id.get(belief_id)

    def for_character(self, character: ActorId) -> list[Belief]:
        return list(self._by_character.get(character, []))

    def belief_for(self, character: ActorId, proposition: Proposition) -> Belief | None:
        """§7.1 "do they believe it?" — may be absent, or a contradicting belief may exist
        (the caller compares `.proposition` itself; this returns the character's belief
        about the same *subject*, which for our closed schema is proposition equality)."""
        for b in self.for_character(character):
            if b.proposition == proposition:
                return b
        return None


def trust_between(case: Case, truster: ActorId, trusted: ActorId) -> float:
    """§6.4 rule 3 / §6.5 need `trust(A->B)`; no formula is given. Documented heuristic:
    an authored close `Rel` raises trust, otherwise neutral default."""
    for r in case.rels:
        if {r.a, r.b} == {truster, trusted} and r.rel_kind in CLOSE_RELS:
            return TRUST_CLOSE
    return TRUST_DEFAULT


@dataclass(frozen=True)
class BeliefFormationResult:
    beliefs: tuple[Belief, ...]
    suppressed: tuple[Belief, ...]  # rule 5: lower-confidence side of a resolved conflict


def _identity_key(prop: Proposition):
    """Narrow same-subject key for rule 5's conflict check — NOT the general contradiction
    detector (that is §13.2, Phase 3). Only covers the proposition kinds this module's
    rules 1-4 actually produce beliefs about."""
    if prop.kind == "At":
        return ("At", prop.actor)
    if prop.kind == "Saw":
        return ("Saw", prop.observer, prop.location)
    if prop.kind == "Heard":
        return ("Heard", prop.observer)
    if prop.kind == "Attitude":
        return ("Attitude", prop.a, prop.b, prop.attitude_kind)
    return (prop.kind,)


def _conflicts(a: Proposition, b: Proposition) -> bool:
    """Are these two propositions logically INCOMPATIBLE — not merely different?

    Rule 5 resolves contradictions; it must not suppress a belief that simply says something
    else. Two overlapping observations of the same actor in the same room, or of two
    different people in one room, are both perfectly satisfiable and are left alone. Only
    the incompatibilities this module's own rules 1-4 can actually produce are listed here;
    the general contradiction detector is §13.2 (Phase 3).
    """
    ia, ib = getattr(a, "interval", None), getattr(b, "interval", None)
    timed = ia is not None and ib is not None
    if timed and not overlaps(ia, ib):
        return False  # different times: never a conflict

    # An actor occupies one location at a time (§4.9 P-1). Same room = compatible, whatever
    # the intervals; different rooms over overlapping ticks = impossible.
    if a.kind == "At" and b.kind == "At" and a.actor == b.actor:
        return a.location != b.location
    # ...and being somewhere excludes being reported absent from it.
    if {a.kind, b.kind} == {"At", "NotAt"}:
        at, not_at = (a, b) if a.kind == "At" else (b, a)
        return at.actor == not_at.actor and at.location == not_at.location

    # Rule 2 forms an unidentified sighting and, optionally, an identified reading of the
    # SAME sighting. Those two compete. Two sightings of two different named people do not.
    if a.kind == "Saw" == b.kind and a.observer == b.observer and a.location == b.location:
        if a.subject == b.subject:
            return a.identified != b.identified
        return "figure" in (a.subject, b.subject)
    # Same sound, two different attributions of who made it.
    if a.kind == "Heard" == b.kind and a.observer == b.observer:
        return a.sound_kind == b.sound_kind and a.identified_actor != b.identified_actor

    # One attitude of one kind toward one person, at one strength.
    if a.kind == "Attitude" == b.kind:
        return (a.a, a.b, a.attitude_kind) == (b.a, b.b, b.attitude_kind) and a.intensity != b.intensity
    return False


InferenceRule = Callable[[ActorId, KnowledgeStore, Case], list[tuple[Proposition, float, tuple[str, ...], int]]]
# a rule returns (proposition, strength 0..1, grounding knowledge-entry ids, formed_at) tuples


def _rule_opportunity(character: ActorId, store: KnowledgeStore, case: Case):
    """§6.4 rule 4: `At(X, near scene) ∧ Died(V, scene, t) -> Suspect(X)` as
    `Attitude(self, X, "suspects", s)`. "Near scene" = present at the death location within
    `OPPORTUNITY_MARGIN` minutes of the death interval (documented reading — the
    architecture names the rule, not a distance/time formula)."""
    death = next((e for e in case.events if e.kind == "Die"), None)
    if death is None:
        return []
    window = widen(death.interval, OPPORTUNITY_MARGIN, lo=0, hi=case.t_investigation)
    out = []
    for entry in store.for_character(character):
        p = entry.proposition
        if p.kind != "At" or p.actor == character or p.location != death.location:
            continue
        if not overlaps(p.interval, window):
            continue
        out.append((Attitude(a=character, b=p.actor, attitude_kind="suspects", intensity=round(entry.reliability, 3)),
                     entry.reliability, (entry.id,), entry.acquired_at))
    return out


# Closed rule set (§6.4 rule 4: "≤ 12 rules in v1"). Only "opportunity" is specified
# precisely enough to implement without inventing formulas; "motive-from-relationship" and
# "consistency" are named but not formalised in the architecture, so they are not stubbed
# with guessed behaviour — this registry is where they are added once they are.
INFERENCE_RULES: dict[str, InferenceRule] = {"opportunity": _rule_opportunity}


def _identity_inference(entry: KnowledgeEntry, case: Case) -> tuple[Proposition, float, str] | None:
    """§6.4 rule 2's optional second clause: a known actor matching the perceived
    silhouette by margin >= 0.2 yields a second, identified belief. Not implementable
    without an observed-attribute payload on `Saw` — the closed proposition schema
    (§4.7) carries no such field, and adding one is an ADR-level change this phase does
    not make. Always returns None; the hook exists so a schema-extending phase can fill
    it in without changing `form_beliefs`'s call site."""
    return None


def form_beliefs(character: ActorId, store: KnowledgeStore, case: Case,
                  fact_index: FactIndex) -> BeliefFormationResult:
    """§6.4 rules 1-5 for one character. Deterministic; no RNG (I-6)."""
    candidates: list[Belief] = []
    counter = [0]

    def make(proposition: Proposition, confidence: float, grounds: tuple[str, ...], formed_at: int) -> Belief:
        counter[0] += 1
        return Belief(id=f"B{character}{counter[0]:04d}", character=character, proposition=proposition,
                      confidence_0=bp(confidence), grounds=grounds, formed_at=formed_at,
                      is_true=bool(fact_index.truth_value(proposition)))

    for entry in store.for_character(character):
        p = entry.proposition
        if isinstance(entry.source, Told):
            # rule 3: unconditional on any Told entry.
            trust = trust_between(case, character, entry.source.by)
            candidates.append(make(p, trust * entry.reliability, (entry.id,), entry.acquired_at))
            continue
        if entry.reliability >= DIRECT_THRESHOLD:
            # rule 1: direct.
            candidates.append(make(p, entry.reliability, (entry.id,), entry.acquired_at))
        elif UNCERTAIN_LOW <= entry.reliability < DIRECT_THRESHOLD and p.kind in ("Saw", "Heard"):
            # rule 2: uncertain perception, unidentified form.
            unidentified = getattr(p, "identified", None) is False or getattr(p, "identified_actor", "unset") is None
            if unidentified:
                candidates.append(make(p, entry.reliability, (entry.id,), entry.acquired_at))
                inferred = _identity_inference(entry, case)
                if inferred is not None:
                    ident_prop, conf, rule_id = inferred
                    candidates.append(make(ident_prop, conf, (entry.id,), entry.acquired_at))

    for rule in INFERENCE_RULES.values():
        for proposition, strength, grounds, formed_at in rule(character, store, case):
            candidates.append(make(proposition, strength, grounds, formed_at))

    # Rule 5: conflict resolution — "keep the higher-confidence one and record the loser as
    # a suppressed_belief". Conflict is not transitive (it needs overlapping intervals), so
    # evicting one incumbent per candidate could leave two beliefs that conflict with each
    # other but not with the winner. Confidence order is imposed FIRST — ties broken by id
    # so the pass is deterministic (I-6) and independent of store iteration order — then a
    # candidate is admitted only if it is compatible with everything already admitted. The
    # result is a consistent set by construction, at the highest confidences available.
    suppressed: list[Belief] = []
    kept: list[Belief] = []
    for c in sorted(candidates, key=lambda b: (-b.confidence_0, b.id)):
        if any(_conflicts(k.proposition, c.proposition) for k in kept):
            suppressed.append(c)
        else:
            kept.append(c)

    order = {b.id: i for i, b in enumerate(candidates)}  # report in formation order
    return BeliefFormationResult(beliefs=tuple(sorted(kept, key=lambda b: order[b.id])),
                                  suppressed=tuple(sorted(suppressed, key=lambda b: order[b.id])))
