"""`admissibility(claim)` and `apparent_admissibility(claim, confrontee, view)` (§19.5,
I-27, I-35) — the base-provenance half of the shared lattice function.

The architecture's full lattice needs two things this phase does not have: corroboration
(the collusion graph over `Secret`/`Rel`, §19.5, needs `Secret` — Phase 4) and the
planted/confrontee-knows-false divergence (needs `Evidence.authentic` — Phase 3 — and
`Claim`/`ResponsePlan` — Phase 4). What Phase 2 CAN and does compute deterministically,
purely from `KnowledgeStore`/`BeliefStore`, is the level implied by a grounding chain alone
(§6.2's comment table): walk `Provenance`/`Belief.grounds` and take the minimum, exactly as
I-27 prescribes, without the corroboration bump from L1 to L2. Phase 3/4 take `min` of this
result against their own corroboration/planted-evidence checks — this function is the base
case they build on, not a competing implementation.
"""
from __future__ import annotations

from .belief import BeliefStore
from .ids import BeliefId, KnowledgeEntryId
from .knowledge import KnowledgeEntry, KnowledgeStore
from .provenance import (
    Absence, AdmissibilityLevel, Background, Inferred, InvestigationTold, Participated, Read,
    Told, Witnessed, level_below,
)


def _level_of_entry(entry: KnowledgeEntry, knowledge: KnowledgeStore, beliefs: BeliefStore,
                     seen: frozenset[str]) -> AdmissibilityLevel:
    src = entry.source
    if isinstance(src, (Witnessed, Participated, Absence, Read, Background)):
        # §6.2's own comment table: "Witnessed / Participated / Absence / Read -> can
        # reach L2 if corroborated or presence-fixed" — L1 uncorroborated, all four alike.
        # `Background` is grouped with them (§19.5's L1 row lists it explicitly). NotAt
        # material stays admissible-but-weak (I-34), not inadmissible — V-5's own
        # absence-fragility report (§19.5) would have nothing to report on otherwise.
        # Corroboration promoting L1 to L2 is deferred (module docstring).
        return AdmissibilityLevel.L1
    if isinstance(src, InvestigationTold):
        return AdmissibilityLevel.L0  # I-27: always, and it poisons any chain containing it.
    if isinstance(src, Told):
        # I-27 reads the recorded chain, never a re-resolution. `grounding_entry_id` is the
        # teller's own entry that was actually relayed; searching for it instead (by
        # proposition, best reliability) can select a DIFFERENT entry than the one relayed
        # and so route around an `InvestigationTold` link that must poison the chain (AC-1).
        if src.grounding_entry_id is None:
            return AdmissibilityLevel.L0  # nothing grounds the teller's own claim
        teller_entry = knowledge.get(src.grounding_entry_id)
        if teller_entry is None:
            # A recorded edge that resolves to nothing is impossible provenance, not an
            # invitation to guess. (If the teller's entry is a runtime one, the caller must
            # pass the overlay view — `knowledge.with_overlay` — so it resolves here.)
            return AdmissibilityLevel.L0
        return level_below(admissibility_level(teller_entry.id, knowledge, beliefs, seen))
    if isinstance(src, Inferred):
        if not src.from_ids:
            return AdmissibilityLevel.L0
        return min(admissibility_level(fid, knowledge, beliefs, seen) for fid in src.from_ids)
    return AdmissibilityLevel.L0


def admissibility_level(entry_or_belief_id: KnowledgeEntryId | BeliefId, knowledge: KnowledgeStore,
                         beliefs: BeliefStore, _seen: frozenset[str] = frozenset()) -> AdmissibilityLevel:
    """Walks the grounding chain and takes the minimum (I-27). `_seen` guards a malformed
    (cyclic) grounding graph — the architecture assumes acyclic grounding; a cycle is
    itself "impossible provenance" and resolves to L0 rather than recursing forever."""
    if entry_or_belief_id in _seen:
        return AdmissibilityLevel.L0
    seen = _seen | {entry_or_belief_id}

    entry = knowledge.get(entry_or_belief_id)
    if entry is not None:
        return _level_of_entry(entry, knowledge, beliefs, seen)

    belief = beliefs.get(entry_or_belief_id)
    if belief is not None:
        if not belief.grounds:
            return AdmissibilityLevel.L1
        return min(admissibility_level(g, knowledge, beliefs, seen) for g in belief.grounds)

    raise KeyError(f"unknown grounding id: {entry_or_belief_id!r} (not in either store)")


def apparent_admissibility(entry_or_belief_id: KnowledgeEntryId | BeliefId, knowledge: KnowledgeStore,
                            beliefs: BeliefStore, confrontee=None, view=None) -> AdmissibilityLevel:
    """§11.2/I-35: at full strength this diverges from `admissibility_level` for planted
    evidence (full apparent level despite being inadmissible) and for claims the
    confrontee knows to be false (apparent 0 regardless of true level) — both need models
    Phase 2 does not build (`Evidence.authentic`, `Claim`/`ResponsePlan`). Until those
    exist this is exactly `admissibility_level`; `confrontee`/`view` are accepted so
    Phase 3/4 call sites do not need a signature change when the divergence is added."""
    return admissibility_level(entry_or_belief_id, knowledge, beliefs)
