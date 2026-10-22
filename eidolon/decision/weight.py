"""`refutation_weight` (§11.2) — the evidentiary half of the murderer's engine, and the one
function I-3/I-16/I-32/I-33/I-38 are all stated in terms of.

```
refutation_weight(presented, layer, confrontee, view) -> bp:
    groups = group_by_causal_support(presented)
    per_group = [max(...) for g in groups]      # I-32: max within a group
    return noisy_or(*per_group)                 # I-32: noisy_or only across groups
```

Two adapters unify evidence implications and statement claims into one shape
(`_WeighableItem`) so the aggregation loop is written once, per the pseudocode's own
`claims_of(item)` treating "evidence implications OR statement claims" alike.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..evidence.contradiction import _requires_closure  # the SAME closure `corroborates()` uses (I-37)
from ..evidence.contradiction import contradiction
from ..evidence.discovery import unlocked_implications
from ..evidence.model import combined_strength
from ..minds.provenance import AdmissibilityLevel
from ..minds.scale import bp
from ..world.ids import ActorId
from ..world.propositions import Proposition
from .admissibility import (
    claim_admissibility, claim_apparent_admissibility, evidence_admissibility,
    evidence_apparent_admissibility, provenance_origin,
)
from .context import DecisionContext
from .secrets import CoverLayer, Ref

# §19.5's admissibility -> weight table.
_ADM_WEIGHT = {AdmissibilityLevel.L0: 0.0, AdmissibilityLevel.L1: 0.3,
               AdmissibilityLevel.L2: 0.7, AdmissibilityLevel.L3: 1.0}


@dataclass(frozen=True)
class _WeighableItem:
    """One `claims_of(item)` entry: a proposition with a strength and an apparent
    admissibility, plus the event ids it causally rests on (for grouping) and whether it (or
    its containing item) has been retracted (I-38: retracted material weighs zero).

    `known_origin` is False when the item's source cannot be established (evidence with no
    `created_by`/`planted_by`; testimony whose grounding reaches no perception). Such an item
    can never be shown independent of anything, so it never compounds (I-15, I-37)."""
    proposition: Proposition
    strength: float             # combined_strength for evidence; 1.0 for a stated claim
    apparent_level: AdmissibilityLevel
    support: frozenset[str]
    retracted: bool
    known_origin: bool = True


def _origin_events(evidence) -> set[str]:
    direct = {e for e in (evidence.created_by, evidence.planted_by) if e is not None}
    return direct | {e for _, e in evidence.interacted}


def _evidence_support(evidence, ctx: DecisionContext) -> frozenset[str]:
    """Origin events plus the item's whole ancestry in the `requires` derivation graph: its own
    id, every id it transitively rests on, AND the origins of those ancestors — a required
    item's own creating events, a required statement's perceptual sources. Two items sharing
    any token are one causal group, so a derived item groups with its source, two items with a
    shared prerequisite group together, and so do two items meeting at a common event through
    testimony (I-37 clause 4, applied to aggregation)."""
    closure = _requires_closure(evidence, ctx.evidence)
    tokens = _origin_events(evidence) | {f"ref:{r}" for r in closure} | {f"ref:{evidence.id}"}
    knowledge = None
    for r in closure:
        ancestor = ctx.evidence.get(r)
        if ancestor is not None:
            tokens |= _origin_events(ancestor)
        statement = ctx.statements.get(r)
        if statement is not None:
            knowledge = knowledge or ctx.knowledge_with_overlay
            for c in statement.claims:
                tokens |= provenance_origin(c.grounding, knowledge, ctx.beliefs)[0]
    return frozenset(tokens)


def _items_for_ref(ref: Ref, ctx: DecisionContext, confrontee: ActorId,
                    player_material: frozenset[str], apparent: bool = True) -> list[_WeighableItem]:
    """`apparent=True` (the runtime default, §11.2) uses I-35's apparent-strength rule.
    `apparent=False` uses TRUE admissibility instead — what V-3's breaker-set derivation
    requires (§19.3: "using **true** admissibility") so a case is never authored to be
    "breakable" only by material that would not actually be admissible for the solver."""
    ev = ctx.evidence.get(ref)
    if ev is not None:
        known = player_material  # `unlocked()` reads the player's global discovered material
        level = (evidence_apparent_admissibility(ev, confrontee, ctx.beliefs, ctx.epistemic) if apparent
                 else evidence_admissibility(ev))
        support = _evidence_support(ev, ctx)
        known_origin = ev.created_by is not None or ev.planted_by is not None
        return [_WeighableItem(imp.proposition, combined_strength(ev, imp), level, support, False, known_origin)
                for imp in unlocked_implications(ev, known)]

    if ref in ctx.accounts:
        # V-3 only (ADR-23): the content of an account token is DERIVED from its speaker's own `Participated`
        # knowledge — exactly the claims a faithful delivery commits (I-50) — never a second authored copy.
        from ..minds import accounts as acct
        from .claims import Claim
        knowledge = ctx.knowledge_with_overlay
        speaker = acct.parse(ref)[1]
        out = []
        for i, e in enumerate(acct.entries_of(ctx.case, ctx.knowledge, ref)):
            c = Claim(id=f"acct:{ref}:{i}", proposition=e.proposition, sincerity="truthful", source="plan", grounding=(e.id,))
            level = (claim_apparent_admissibility(c, speaker, confrontee, knowledge, ctx.beliefs, ctx.secrets,
                                                   ctx.collusion, ctx.epistemic) if apparent
                     else claim_admissibility(c, speaker, knowledge, ctx.beliefs, ctx.secrets, ctx.collusion))
            events, perceptual = provenance_origin(c.grounding, knowledge, ctx.beliefs)
            out.append(_WeighableItem(c.proposition, 1.0, level, events | {f"ref:{ref}"}, False, perceptual))
        return out

    statement = ctx.statements.get(ref)
    if statement is not None:
        knowledge = ctx.knowledge_with_overlay
        out = []
        for c in statement.claims:
            level = (claim_apparent_admissibility(c, statement.speaker, confrontee, knowledge, ctx.beliefs,
                                                   ctx.secrets, ctx.collusion, ctx.epistemic) if apparent
                     else claim_admissibility(c, statement.speaker, knowledge, ctx.beliefs, ctx.secrets, ctx.collusion))
            events, perceptual = provenance_origin(c.grounding, knowledge, ctx.beliefs)
            out.append(_WeighableItem(c.proposition, 1.0, level, events | {f"ref:{statement.id}"},
                                      statement.retracted_by is not None, perceptual))
        return out
    return []


def group_by_causal_support(presented: frozenset[Ref], items_by_ref: dict[Ref, list[_WeighableItem]]) -> list[list[Ref]]:
    """§11.2: "items sharing any EventId in `support` share a group". Union-find over the
    presented refs by their items' support sets; a ref with empty support is its own
    singleton group (nothing to share)."""
    parent: dict[Ref, Ref] = {r: r for r in presented}

    def find(x: Ref) -> Ref:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: Ref, b: Ref) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    by_event: dict[str, list[Ref]] = {}
    for ref in presented:
        for item in items_by_ref.get(ref, []):
            for eid in item.support:
                by_event.setdefault(eid, []).append(ref)
    for refs in by_event.values():
        for r in refs[1:]:
            union(refs[0], r)

    groups: dict[Ref, list[Ref]] = {}
    for ref in presented:
        groups.setdefault(find(ref), []).append(ref)
    return list(groups.values())


def noisy_or(*probabilities: float) -> float:
    result = 0.0
    for p in probabilities:
        result = result + p - result * p
    return result


def refutation_weight(presented: frozenset[Ref], layer: CoverLayer, confrontee: ActorId,
                       ctx: DecisionContext, *, apparent: bool = True) -> int:
    """§11.2. Returns bp (0..10000). `view` (the pre-turn epistemic snapshot, §8.6) is
    `ctx` itself — callers build `ctx` from the pre-turn fold, never revise it mid-computation.

    `apparent=True` (default) is the RUNTIME reading (I-35): peel/slip react to what looks
    convincing. `apparent=False` is what `cover_consistency.py`'s V-3 breaker-set derivation
    uses instead (§19.3: "using true admissibility") — a case must never be authored to look
    breakable only by material that would not actually be admissible for the solver.
    """
    # `presented` is folded into the global material `requires` resolves against: an item
    # PRESENTED for the first time is, by that act, discovered — `DetectiveModelUpdate`
    # records it as known AFTER this turn commits (`turn.py`), but weight this turn must
    # already see it, or a first-time `Present` could never itself unlock anything.
    player_material = (ctx.discovery.known_evidence | ctx.discovery.known_statements | ctx.discovery.known_accounts
                       | frozenset(presented))
    items_by_ref = {ref: _items_for_ref(ref, ctx, confrontee, player_material, apparent) for ref in presented}
    groups = group_by_causal_support(frozenset(presented), items_by_ref)

    per_group: list[float] = []
    unknown_best = 0.0  # unknown-origin items: counted by `max` only, never compounded
    for group in groups:
        best = 0.0
        for ref in group:
            for item in items_by_ref.get(ref, []):
                if item.retracted:
                    continue
                sev = 0.0
                for c in layer.claims:
                    hit = contradiction(item.proposition, c.proposition, case=ctx.case)
                    if hit is not None:
                        sev = max(sev, hit.severity)
                adm = _ADM_WEIGHT[item.apparent_level]
                w = item.strength * sev * adm
                if item.known_origin:
                    best = max(best, w)
                else:
                    unknown_best = max(unknown_best, w)
        per_group.append(best)
    return bp(max(noisy_or(*per_group), unknown_best))
