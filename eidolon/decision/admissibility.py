"""Claim-level admissibility (§19.5, I-27, I-35, I-37) — the piece `minds/admissibility.py`
and `evidence/contradiction.py` both explicitly deferred here: "the corroboration bump from
L1 to L2" and "the collusion graph over `Secret`/`Rel`, needs Secret — Phase 4".

Two functions per item kind, per I-35's table:

- `claim_admissibility` / `claim_apparent_admissibility` — testimony (a `Claim` inside a
  `Statement`). True admissibility never reaches L3 (§19.5/§6.2: L3 is a property of
  authentic physical evidence, never of a provenance walk).
- `evidence_admissibility` / `evidence_apparent_admissibility` — a presented `Evidence` item.
  True admissibility is L3 if authentic, L0 (never admissible for the solver) if not; apparent
  is full strength regardless of authenticity, because a planted item is by design
  indistinguishable from a genuine one to whoever it is shown (I-35) — UNLESS the confrontee
  actually knows better (see below), which takes priority over both the corroboration bump
  and the planted/apparent-full rule.

`confrontee_knows_false` is the one thing both apparent functions check first: "the
character-visible response to an inadmissible item is indistinguishable from the response to
an admissible item of equal apparent strength... UNLESS the confrontee sees through it" — a
confrontee who holds a belief contradicting the item's proposition at confidence >= 0.7
(§6.5's own bluff threshold, reused here for the same reason: this is the same
"does the character see through the premise" question, not a new one) reacts as if the item
weighed nothing, whatever it apparently is.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..evidence.model import Evidence
from ..minds.admissibility import admissibility_level as _grounding_level
from ..minds.belief import BeliefStore
from ..minds.epistemic import current_belief_confidence
from ..minds.knowledge import KnowledgeStore
from ..minds.provenance import (
    Absence, AdmissibilityLevel, Inferred, InvestigationTold, Participated, Read, Told, Witnessed,
)
from ..minds.scale import frac
from ..world.ids import ActorId
from ..world.propositions import Proposition
from .claims import Claim
from .secrets import SecretStore

CONFRONTEE_KNOWS_FALSE_THRESHOLD = 0.7  # §6.5's own bluff-parity threshold


@dataclass(frozen=True)
class CollusionGraph:
    """I-37's collusion graph over `{shared Secret, Rel, Secret.beneficiaries}`
    (`SecretStore.collusion_edges`), as connected components — "connectivity, not
    adjacency" (§19.5): A corroborating B and B corroborating C does not clear A and C when
    A and C are lovers, so membership is by COMPONENT, never by direct edge lookup."""
    edges: frozenset[frozenset[ActorId]]

    def connected(self, a: ActorId, b: ActorId) -> bool:
        if a == b:
            return True
        seen = {a}
        frontier = [a]
        while frontier:
            cur = frontier.pop()
            for edge in self.edges:
                if cur in edge:
                    for nxt in edge:
                        if nxt == b:
                            return True
                        if nxt not in seen:
                            seen.add(nxt)
                            frontier.append(nxt)
        return False

    @classmethod
    def build(cls, secrets: SecretStore, world_rels) -> "CollusionGraph":
        return cls(edges=frozenset(secrets.collusion_edges(world_rels)))


def confrontee_knows_false(proposition: Proposition, confrontee: ActorId,
                            beliefs: BeliefStore, epistemic=None,
                            threshold: float = CONFRONTEE_KNOWS_FALSE_THRESHOLD) -> bool:
    """§6.5's `contradicts_own_belief`, reused for I-35's apparent-weight override: does
    `confrontee` hold a belief CONTRADICTING `proposition` at confidence >= threshold? A
    belief about the exact same proposition with a different truth value never arises in
    this schema (propositions are structural, not signed), so "contradicting" here is the
    narrow, decidable form §6.5 actually needs: an `At`/`NotAt`/`Did`/`DidNot` pair, or the
    identical predicate applied to the same subject with a different value. Reuses
    `evidence.contradiction` would pull in an evidence-shaped dependency for a belief-only
    question; the two-line check below only needs the same rules `contradiction()` applies to
    presence/negation, so it inlines the ones relevant to bluffed propositions.
    """
    from ..world.interval import overlaps

    for b in beliefs.for_character(confrontee):
        conf = frac(current_belief_confidence(epistemic, b.id, b.confidence_0)) if epistemic else frac(b.confidence_0)
        if conf < threshold:
            continue
        p, q = b.proposition, proposition
        if p.kind == "At" and q.kind == "At" and p.actor == q.actor and p.location != q.location and overlaps(p.interval, q.interval):
            return True
        if {p.kind, q.kind} == {"At", "NotAt"}:
            at, nat = (p, q) if p.kind == "At" else (q, p)
            if at.actor == nat.actor and at.location == nat.location and overlaps(at.interval, nat.interval):
                return True
        # review I-7: two `Did`s of the same act are agreement at different granularity, never a contradiction - and an
        # agreeing belief never ends the scan (a contradicting one later in the store must still be seen)
        if {p.kind, q.kind} == {"Did", "DidNot"}:
            did, didnot = (p, q) if p.kind == "Did" else (q, p)
            if (did.actor == didnot.actor and did.action == didnot.action
                    and (didnot.object is None or didnot.object == did.object) and overlaps(did.interval, didnot.interval)):
                return True
    return False


def _chain_poisoned(grounding, knowledge: KnowledgeStore) -> bool:
    """I-27: "any chain containing InvestigationTold" poisons to L0, regardless of the
    `min` the ordinary walk would otherwise compute. `minds.admissibility` already applies
    this at each step of ITS OWN walk; this re-check exists because a claim's `grounding`
    tuple can name entries `minds.admissibility` never sees as a single chain (multiple
    top-level grounds, e.g. an `Inferred`-style claim over several entries) — this walks
    each named id's own source once, cheaply, without re-deriving `minds.admissibility`'s
    full recursive minimum."""
    for gid in grounding:
        entry = knowledge.get(gid)
        if entry is not None and isinstance(entry.source, InvestigationTold):
            return True
    return False


def provenance_origin(ids, knowledge: KnowledgeStore, beliefs: BeliefStore) -> tuple[frozenset[str], bool]:
    """The source identity I-37 compares: every event `ids` rest on, TRANSITIVELY — through
    `Told.grounding_entry_id`, `Inferred.from_ids` and `Belief.grounds` — plus whether any of it
    bottoms out in a perception (`Witnessed`/`Participated`/`Read`/`Absence`). An `Absence`
    entry has no event id, so it is named by its own entry id: two distinct observations never
    collide on it, and anything relaying it inherits the token.

    Fail closed (I-15): `Background`, `InvestigationTold` and dangling ids establish no origin,
    so a caller asking "is this an independent observation?" gets `False` for them."""
    events: set[str] = set()
    perceptual = False
    seen: set[str] = set()
    stack = list(ids)
    while stack:
        gid = stack.pop()
        if gid in seen:
            continue
        seen.add(gid)
        entry = knowledge.get(gid)
        if entry is None:
            belief = beliefs.get(gid)
            if belief is not None:
                stack.extend(belief.grounds)
            continue
        src = entry.source
        if isinstance(src, (Witnessed, Participated)):
            events.add(src.event_id)
            perceptual = True
        elif isinstance(src, Read):
            events.add(src.read_event_id)
            perceptual = True
        elif isinstance(src, Absence):
            events.add(f"absence:{entry.id}")
            perceptual = True
        elif isinstance(src, Told):
            events.add(src.speak_event_id)
            if src.grounding_entry_id is not None:
                stack.append(src.grounding_entry_id)
        elif isinstance(src, Inferred):
            stack.extend(src.from_ids)
    return frozenset(events), perceptual


def _corroborated(proposition: Proposition, speaker: ActorId, grounding: tuple[str, ...],
                   knowledge: KnowledgeStore, beliefs: BeliefStore, collusion: CollusionGraph) -> bool:
    """I-37: corroboration requires a DIFFERENT `KnowledgeEntry` with provenance disjoint from
    the claim's WHOLE grounding — every ground, walked transitively, however many there are —
    from a speaker in a different collusion component, whose own entry is an established
    perception at >= L1. One perception reached by two paths is one source."""
    own_events, _ = provenance_origin(grounding, knowledge, beliefs)
    for other_actor, other_entry in knowledge.knowers(proposition).items():
        if other_actor == speaker or collusion.connected(speaker, other_actor):
            continue
        if other_entry.id in grounding:
            continue
        other_events, other_perceptual = provenance_origin((other_entry.id,), knowledge, beliefs)
        if not other_perceptual or own_events & other_events:
            continue
        if _grounding_level(other_entry.id, knowledge, beliefs) >= AdmissibilityLevel.L1:
            return True
    return False


def claim_admissibility(claim: Claim, speaker: ActorId, knowledge: KnowledgeStore,
                         beliefs: BeliefStore, secrets: SecretStore,
                         collusion: CollusionGraph) -> AdmissibilityLevel:
    """§19.5's L0-L3 table, restricted to what a testimony `Claim` can reach (never L3)."""
    if secrets.is_protected_for(speaker, claim.proposition):
        return AdmissibilityLevel.L0  # "any suspect's claims about their own protected facts"
    if not claim.grounding:
        return AdmissibilityLevel.L0
    if _chain_poisoned(claim.grounding, knowledge):
        return AdmissibilityLevel.L0
    base = min(_grounding_level(gid, knowledge, beliefs) for gid in claim.grounding)
    if base == AdmissibilityLevel.L0:
        return AdmissibilityLevel.L0
    if base == AdmissibilityLevel.L1 and _corroborated(claim.proposition, speaker, claim.grounding,
                                                        knowledge, beliefs, collusion):
        return AdmissibilityLevel.L2
    return base


def claim_apparent_admissibility(claim: Claim, speaker: ActorId, confrontee: ActorId,
                                  knowledge: KnowledgeStore, beliefs: BeliefStore,
                                  secrets: SecretStore, collusion: CollusionGraph,
                                  epistemic=None) -> AdmissibilityLevel:
    """I-35: for testimony, apparent == true admissibility, except the confrontee-knows-false
    override (testimony has no "planted" analogue — that is an `Evidence`-only concept)."""
    if confrontee_knows_false(claim.proposition, confrontee, beliefs, epistemic):
        return AdmissibilityLevel.L0
    return claim_admissibility(claim, speaker, knowledge, beliefs, secrets, collusion)


def evidence_admissibility(evidence: Evidence) -> AdmissibilityLevel:
    """§19.5: authentic physical evidence is L3, hard; planted evidence is "never admissible
    for the solver" — L0, always, whatever it apparently looks like (I-35)."""
    return AdmissibilityLevel.L3 if evidence.authentic else AdmissibilityLevel.L0


def evidence_apparent_admissibility(evidence: Evidence, confrontee: ActorId,
                                     beliefs: BeliefStore, epistemic=None) -> AdmissibilityLevel:
    """I-35: full apparent strength regardless of authenticity — the character cannot tell a
    planted item apart from a genuine one — UNLESS this specific confrontee actually knows
    better (e.g. it was planted on/against them and they know they never touched the object),
    which zeroes the apparent response exactly as it does for testimony."""
    for imp in evidence.implications:
        if confrontee_knows_false(imp.proposition, confrontee, beliefs, epistemic):
            return AdmissibilityLevel.L0
    return AdmissibilityLevel.L3
