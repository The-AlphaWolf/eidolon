"""Cover-story consistency (V-3, §19.3) — the Phase 4 checker. Builds `CoverLayer.breaker_sets`
by enumeration (using TRUE admissibility, never apparent — I-35/§19.3) and checks the §10.2
consistency contract: EvidenceResponse coverage, innocent reachability, monotone `concedes`,
`Deflection.basis` grounding, `Slip.excuse` reachability, and joint feasibility (I-28).

**Scope, stated once.** V-3 formally runs at CASE GENERATION (Phase 6), over a fully
authored cast and an `EliminationStructure`. This module builds the checking PRIMITIVE —
breaker-set derivation over a candidate pool, and the five §19.3 checks — against whatever
cover stories and evidence/statement pool a caller supplies (a hand-authored fixture in
Phase 4's own tests, or Phase 6's generator later). It does not implement generation
(synthesizing a cover story until the contract holds is Phase 6's "cover synthesis"), and
check (i)'s uniqueness test uses `solver.unique()` — itself scoped to opportunity-uniqueness
only (see `solver.py`'s own docstring).
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from ..minds import accounts as acct
from ..minds.provenance import AdmissibilityLevel
from ..world.interval import overlaps
from ..world.feasibility import Claim as FeasClaim
from ..world.feasibility import feasible
from ..world.ids import LocationId
from .admissibility import claim_admissibility, evidence_admissibility
from .claims import Claim
from .context import DecisionContext
from .secrets import Ref, Secret
from .solver import AdmissibleClaim, FairnessLevel, unique
from .weight import refutation_weight

MAX_BREAKER_SET_SIZE = 4


@dataclass(frozen=True)
class V3Violation:
    check: str  # "i".."v"
    detail: str

    def __str__(self) -> str:
        return f"V-3({self.check}): {self.detail}"


def _context_for_subset(ctx: DecisionContext, subset: frozenset[Ref]) -> DecisionContext:
    """A breaker SET is the minimal DISCOVERED material that suffices (§13.3: "{E1 + S_wash}
    is a derived breaker set" — S_wash must be independently obtained, not assumed globally
    available). So `requires`/`unlocked()` must see exactly `subset` as known, never "the
    whole sealed pool" — treating everything as always-known would let any item's `requires`
    trivially unlock and collapse every breaker set to size 1, whatever the fixture."""
    from ..evidence.discovery import DiscoveryState
    known_evidence = frozenset(r for r in subset if ctx.evidence.get(r) is not None)
    known_statements = frozenset(r for r in subset if ctx.statements.get(r) is not None)
    known_accounts = frozenset(r for r in subset if r in ctx.accounts)
    return DecisionContext(case=ctx.case, knowledge=ctx.knowledge, beliefs=ctx.beliefs,
                            secrets=ctx.secrets, evidence=ctx.evidence, statements=ctx.statements,
                            epistemic=ctx.epistemic, accounts=ctx.accounts,
                            discovery=DiscoveryState(known_evidence=known_evidence, known_statements=known_statements,
                                                     known_accounts=known_accounts))


def _candidate_pool(secret: Secret, ctx: DecisionContext) -> frozenset[Ref]:
    """§19.3: "admissible material (evidence implications with `requires` respected;
    claims at level >= L1 by per-claim admissibility, never L0)"."""
    pool: set[Ref] = set()
    for ev in ctx.evidence.all():
        if evidence_admissibility(ev) >= AdmissibilityLevel.L1:
            pool.add(ev.id)
    knowledge = ctx.knowledge_with_overlay
    for st in ctx.statements.all():
        for c in st.claims:
            level = claim_admissibility(c, st.speaker, knowledge, ctx.beliefs, ctx.secrets, ctx.collusion)
            if level >= AdmissibilityLevel.L1:
                pool.add(st.id)
                break
    pool |= set(ctx.accounts)          # DELIVERABLE account tokens only (`deliverable_accounts`, I-54/I-60)
    return frozenset(pool)


def _protected_by_owner(secrets: list[Secret]) -> dict:
    out: dict = {}
    for s in secrets:
        out.setdefault(s.owner, []).extend(s.protected_intervals())
    return out


def _speakable_token(token: str, ctx: DecisionContext, protected: dict, conceded: set) -> bool:
    """I-54 for one token: the speaker has the knowledge, and none of its entries' observation segments overlaps
    a protected interval of the speaker's secret that has not yet been conceded (fail closed on a missing
    segment)."""
    parsed = acct.parse(token)
    entries = acct.entries_of(ctx.case, ctx.knowledge, token)
    if parsed is None or not entries:
        return False
    owner = parsed[1]
    for e in entries:
        seg = acct.observation_segment(ctx.case, ctx.knowledge, e.id)
        if seg is None:
            return False
        if owner not in conceded and any(overlaps(seg, iv) for iv in protected.get(owner, ())):
            return False
    return True


def deliverable_accounts(secrets: list[Secret], ctx: DecisionContext) -> frozenset[str]:
    """§C.3's availability fixpoint (mirrors I-45 over covers). Round 0: tokens whose entries avoid every
    UNCONCEDED protected interval. Round k+1: add the tokens of owners whose secret has a breaker set drawn from
    round-k material that lands on a conceding layer. The murder secret never contributes: it is never conceded
    for free (I-21), so a token only the murderer could deliver is never counted on."""
    protected = _protected_by_owner(secrets)
    declared = tuple(sorted(ctx.accounts))
    conceded: set = set()
    delivered = frozenset(t for t in declared if _speakable_token(t, ctx, protected, conceded))
    while True:
        sub = DecisionContext(case=ctx.case, knowledge=ctx.knowledge, beliefs=ctx.beliefs, secrets=ctx.secrets,
                              evidence=ctx.evidence, statements=ctx.statements, epistemic=ctx.epistemic,
                              discovery=ctx.discovery, accounts=tuple(sorted(delivered)))
        grew = {s.owner for s in secrets
                if s.kind != "murder" and s.owner not in conceded and len(s.cover.layers) > 1
                and derive_breaker_sets(s, 0, sub)}
        if not grew:
            return delivered
        conceded |= grew
        delivered = frozenset(t for t in declared if _speakable_token(t, ctx, protected, conceded))


def derive_breaker_sets(secret: Secret, layer_index: int, ctx: DecisionContext,
                         max_size: int = MAX_BREAKER_SET_SIZE) -> tuple[frozenset[Ref], ...]:
    """§19.3: minimal presentable subsets reaching `resolve(layer)`, using TRUE
    admissibility. Minimal = no proper subset already found also reaches it."""
    layer = secret.cover.layers[layer_index]
    pool = sorted(_candidate_pool(secret, ctx))
    found: list[frozenset[Ref]] = []

    def already_covered(subset: frozenset[Ref]) -> bool:
        return any(f <= subset for f in found)

    for size in range(1, max_size + 1):
        for combo in combinations(pool, size):
            subset = frozenset(combo)
            if already_covered(subset):
                continue
            subset_ctx = _context_for_subset(ctx, subset)
            w = refutation_weight(subset, layer, secret.owner, subset_ctx, apparent=False)
            if w >= layer.resolve:
                found.append(subset)
    return tuple(found)


def check_evidence_response_coverage(secret: Secret, layer_index: int,
                                      breaker_sets: tuple[frozenset[Ref], ...]) -> list[V3Violation]:
    """(ii): every item in any breaker set of `layer` has an authored `EvidenceResponse`."""
    covered = {(r.evidence, r.layer) for r in secret.evidence_responses}
    v: list[V3Violation] = []
    for bset in breaker_sets:
        for ref in bset:
            if (ref, layer_index) not in covered:
                v.append(V3Violation("ii", f"{secret.id} layer {layer_index}: no EvidenceResponse for {ref!r} "
                                             f"(appears in breaker set {sorted(bset)})"))
    return v


def check_innocent_reachability(secret: Secret, all_breaker_sets: dict[int, tuple[frozenset[Ref], ...]]) -> list[V3Violation]:
    """(iii): a non-murder secret needs at least one reachable breaker set SOMEWHERE in its
    cover, so a red herring / minor secret can resolve."""
    if secret.kind == "murder":
        return []
    if not any(all_breaker_sets.values()):
        return [V3Violation("iii", f"{secret.id} ({secret.kind}): no layer has any breaker set — unresolvable")]
    return []


def check_breaker_accounts_deliverable(secret: Secret, layer_index: int,
                                        breaker_sets: tuple[frozenset[Ref], ...]) -> list[V3Violation]:
    """(vi) I-60: no breaker set of a secret contains an account by that secret's OWN owner — a cover is never
    broken by the owner's own word (the token is minted by THEIR delivery, which is exactly what their cover
    stops them giving). Deliverability under I-54 is enforced by the pool: only deliverable tokens are in it."""
    v: list[V3Violation] = []
    for bset in breaker_sets:
        for ref in sorted(bset):
            parsed = acct.parse(ref)
            if parsed is not None and parsed[1] == secret.owner:
                v.append(V3Violation("vi", f"{secret.id} layer {layer_index}: breaker set {sorted(bset)} rests on "
                                            f"{secret.owner}'s own account {ref!r} (I-60)"))
    return v


def check_monotone_concedes(secret: Secret) -> list[V3Violation]:
    """(iv), part 1: `concedes` is monotone across layers (I-20's authoring-time mirror)."""
    v: list[V3Violation] = []
    prior: frozenset = frozenset()
    for layer in secret.cover.layers:
        current = frozenset(layer.concedes)
        if not (prior <= current):
            v.append(V3Violation("iv", f"{secret.id} layer {layer.index}: concedes is not monotone "
                                        f"(lost {sorted(map(str, prior - current))})"))
        prior = current
    return v


def check_deflection_grounding(secret: Secret, ctx: DecisionContext) -> list[V3Violation]:
    """(iv), part 2: `Deflection.basis ⊆ owner knowledge` (I-8)."""
    v: list[V3Violation] = []
    knowledge = ctx.knowledge_with_overlay
    for d in secret.deflections:
        for kid in d.basis:
            entry = knowledge.get(kid)
            if entry is None or entry.character != secret.owner:
                v.append(V3Violation("iv", f"{secret.id}: Deflection.basis {kid!r} is not "
                                            f"{secret.owner}'s own knowledge"))
    return v


def check_slip_excuse_reachable(secret: Secret, ctx: DecisionContext) -> list[V3Violation]:
    """(iv), part 3: `Slip.excuse`'s refuter (the evidence/statement it responds to) must
    exist in the pool — "its refuter must be reachable"."""
    v: list[V3Violation] = []
    known = {e.id for e in ctx.evidence.all()} | {s.id for s in ctx.statements.all()} | \
        {f"slip:{s.id}" for s in secret.slips}
    for slip in secret.slips:
        if slip.excuse.evidence not in known:
            v.append(V3Violation("iv", f"{secret.id}: Slip {slip.id} excuse refers to unknown "
                                        f"{slip.excuse.evidence!r}"))
    return v


def check_joint_feasibility_layer0(secrets: list[Secret], ctx: DecisionContext) -> list[V3Violation]:
    """(v)'s baseline: `feasible(union of all characters' layer-0 claims)` (I-28). Full
    "every reachable combination of layer states" is Phase 6's job (combinatorial across
    the whole generated cast); this checks the one combination every case starts in."""
    claims = [FeasClaim(id=c.id, proposition=c.proposition)
              for s in secrets for c in s.cover.layers[0].claims]
    result = feasible(ctx.case, claims)
    if not result.ok:
        return [V3Violation("v", f"layer-0 claims are jointly infeasible; minimal conflicting core: {result.core}")]
    return []


@dataclass(frozen=True)
class MurderUniquenessCheck:
    murder_location: LocationId
    murder_interval: tuple[int, int]
    candidates: tuple[str, ...]
    fairness_level: FairnessLevel = "standard"


def check_murder_confession_uniqueness(secret: Secret, pre_terminal_index: int, breaker_sets: tuple[frozenset[Ref], ...],
                                        ctx: DecisionContext, check: MurderUniquenessCheck) -> list[V3Violation]:
    """(i): for the murder secret's pre-terminal layer, EVERY breaker set must already
    establish solver uniqueness — "a confession is never cheaper than a proof" (I-21)."""
    if secret.kind != "murder":
        return []
    # I-21's own wording: "admissible(presented UNION player_hard_material)" — everything
    # else discoverable only ever HELPS uniqueness (more eliminating material), so the full
    # pool stands in for "hard material" here, unlike `derive_breaker_sets`'s per-subset
    # reading (where treating everything as known would collapse breaker-set SIZE).
    all_refs = frozenset(e.id for e in ctx.evidence.all()) | frozenset(s.id for s in ctx.statements.all())         | frozenset(ctx.accounts)
    ctx_all = _context_for_subset(ctx, all_refs)
    knowledge = ctx_all.knowledge_with_overlay
    v: list[V3Violation] = []
    for bset in breaker_sets:
        admissible: list[AdmissibleClaim] = []
        for ref in bset:
            ev = ctx_all.evidence.get(ref)
            if ev is not None:
                level = evidence_admissibility(ev)
                for imp in ev.implications:
                    actor = getattr(imp.proposition, "actor", None)
                    if actor:
                        admissible.append(AdmissibleClaim(actor=actor, proposition=imp.proposition, level=level))
                continue
            if ref in ctx_all.accounts:
                speaker = acct.parse(ref)[1]
                for e in acct.entries_of(ctx_all.case, ctx_all.knowledge, ref):
                    admissible.append(AdmissibleClaim(actor=speaker, proposition=e.proposition, level=claim_admissibility(
                        Claim(id=f"acct:{ref}", proposition=e.proposition, sincerity="truthful", source="plan",
                              grounding=(e.id,)), speaker, knowledge, ctx_all.beliefs, ctx_all.secrets, ctx_all.collusion)))
                continue
            st = ctx_all.statements.get(ref)
            if st is not None:
                for c in st.claims:
                    level = claim_admissibility(c, st.speaker, knowledge, ctx_all.beliefs, ctx_all.secrets, ctx_all.collusion)
                    admissible.append(AdmissibleClaim(actor=st.speaker, proposition=c.proposition, level=level))
        result = unique(check.candidates, check.murder_location, check.murder_interval, admissible,
                         ctx.case, check.fairness_level)
        if not result.unique:
            v.append(V3Violation("i", f"{secret.id} layer {pre_terminal_index}: breaker set {sorted(bset)} "
                                        f"does not establish uniqueness (survivors: {result.survivors})"))
    return v


def check_cover_consistency(secrets: list[Secret], ctx: DecisionContext,
                             murder_check: MurderUniquenessCheck | None = None) -> list[V3Violation]:
    """The full §19.3 gate over a cast of secrets."""
    violations: list[V3Violation] = []
    violations += check_joint_feasibility_layer0(secrets, ctx)
    if ctx.accounts:
        from dataclasses import replace
        ctx = replace(ctx, accounts=tuple(sorted(deliverable_accounts(secrets, ctx))))

    for secret in secrets:
        all_breaker_sets: dict[int, tuple[frozenset[Ref], ...]] = {}
        layers = secret.cover.layers
        for layer in layers:
            if layer.terminal is not None:
                continue
            bsets = derive_breaker_sets(secret, layer.index, ctx)
            all_breaker_sets[layer.index] = bsets
            violations += check_evidence_response_coverage(secret, layer.index, bsets)
            violations += check_breaker_accounts_deliverable(secret, layer.index, bsets)

            is_pre_terminal_confession = (layer.index + 1 < len(layers)
                                           and layers[layer.index + 1].terminal == "confession")
            if secret.kind == "murder" and murder_check is not None and is_pre_terminal_confession:
                violations += check_murder_confession_uniqueness(secret, layer.index, bsets, ctx, murder_check)
        violations += check_innocent_reachability(secret, all_breaker_sets)
        violations += check_monotone_concedes(secret)
        violations += check_deflection_grounding(secret, ctx)
        violations += check_slip_excuse_reachable(secret, ctx)
    return violations
