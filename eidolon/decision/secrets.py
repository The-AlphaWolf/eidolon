"""Secrets and the deception model (§10): `Secret`, `CoverStory`/`CoverLayer`,
`EvidenceResponse`, `Deflection`, `Slip`. Sealed at generation (I-4) — the same discipline
`Evidence`/`Belief`/`Memory` use; nothing here mutates after construction, and `SecretStore`
is only ever built fresh or extended.

**`FactId` deviation, documented once here.** §10.1/§10.2 type `Secret.protected` and
`CoverLayer.concedes` as `list[FactId]`, and `Slip.reveals` as a bare `FactId`. Phase 1 never
populated a `derive_facts()` fact-id catalog (`minds/knowledge.py`'s own docstring: "Phase 1
defines the `Fact` model but has no `derive_facts()` populating stable fact ids yet"), and
every store built since (`KnowledgeStore`, `BeliefStore`) indexes by `Proposition` equality
instead, never by a fact id. This module follows that established precedent rather than
inventing the missing catalog: `protected`/`concedes`/`Slip.reveals` are typed `Proposition`,
which is what every comparison against them (`is_protected`, `admissibility`'s L0 rule,
"never entail `Solution` unless CONFESSION") actually needs — proposition equality, or
`contradiction()`/`feasible()`, both of which already operate on `Proposition`, never on an
opaque id.
"""
from __future__ import annotations

from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..evidence.ids import StatementId
from ..minds.ids import KnowledgeEntryId
from ..world.ids import ActorId, EvidenceId
from ..world.propositions import Proposition
from .claims import Claim
from .ids import SecretId, SlipId, TopicId
from .speech_acts import SpeechAct

SecretKind = Literal[
    "murder", "affair", "theft", "debt", "protecting_other", "minor_infraction", "identity",
]

Ref = str  # EvidenceId | StatementId (§10.2's own alias, matching `evidence.model.RequirementId`)


class Stakes(BaseModel):
    """§10.1: "legal, social, protective (0..1 each)"."""
    model_config = ConfigDict(frozen=True)

    legal: float = Field(default=0.0, ge=0.0, le=1.0)
    social: float = Field(default=0.0, ge=0.0, le=1.0)
    protective: float = Field(default=0.0, ge=0.0, le=1.0)


class EvidenceResponse(BaseModel):
    """§10.2: "what to say when an item is presented at a layer"."""
    model_config = ConfigDict(frozen=True)

    evidence: Ref  # EvidenceId | StatementId
    layer: int
    act: SpeechAct
    claims: tuple[Claim, ...] = ()


class Deflection(BaseModel):
    model_config = ConfigDict(frozen=True)

    target: ActorId
    basis: tuple[KnowledgeEntryId, ...]  # I-8: the deflector must actually know the basis
    claims: tuple[Claim, ...] = ()
    cost: float = 0.0


class Slip(BaseModel):
    """§10.2/§11.7. `composure_max` was REMOVED in v0.3 (I-29): a slip is gated on
    refutation weight, topic and single-use only — never on any quantity `verbal_pressure`
    feeds (I-16)."""
    model_config = ConfigDict(frozen=True)

    id: SlipId
    reveals: Proposition  # see module docstring: FactId -> Proposition
    trigger_topic: TopicId
    min_weight_fraction: int = Field(ge=0, le=10000)  # bp of the current layer's resolve
    excuse: EvidenceResponse


class CoverLayer(BaseModel):
    """§10.2. `breaker_sets` are DERIVED by the validator/solver (§19.3), never hand-authored;
    stored here for audit and V-3's coverage checks. `resolve` is bp (I-17-adjacent: it is
    generation-time sealed content, compared directly against the bp `refutation_weight`
    result, so it is stored in the same unit rather than forcing a conversion at every
    comparison site)."""
    model_config = ConfigDict(frozen=True)

    index: int
    claims: tuple[Claim, ...] = ()
    concedes: tuple[Proposition, ...] = ()
    frame: tuple[Claim, ...] = ()
    resolve: int = Field(ge=0, le=10000)
    breaker_sets: tuple[frozenset[Ref], ...] = ()
    terminal: Literal[None, "confession", "stonewall"] = None


class CoverStory(BaseModel):
    model_config = ConfigDict(frozen=True)

    layers: tuple[CoverLayer, ...]

    def layer(self, index: int) -> CoverLayer:
        return self.layers[index]


class Secret(BaseModel):
    """§10.1. "Every suspect has at least one non-murder secret" is a generation-time
    authoring contract (§18), not something this model enforces by construction — the same
    boundary `Evidence`/`Belief` draw between "what the type allows" and "what the case
    author is required to provide"."""
    model_config = ConfigDict(frozen=True)

    id: SecretId
    owner: ActorId
    kind: SecretKind
    protected: tuple[Proposition, ...]
    stakes: Stakes
    beneficiaries: tuple[ActorId, ...] = ()
    cover: CoverStory
    evidence_responses: tuple[EvidenceResponse, ...] = ()
    deflections: tuple[Deflection, ...] = ()
    slips: tuple[Slip, ...] = ()
    misleading_truths: tuple[Claim, ...] = ()

    def is_protected(self, proposition: Proposition) -> bool:
        return proposition in self.protected

    def protected_intervals(self) -> tuple[tuple[int, int], ...]:
        """The spans of this secret's protected propositions — the ONE definition of "inside the
        speaker's protected interval" (ADR-26, I-54). The solver's layer-0 withholding (I-45), the
        runtime speakability gate and the independent verifier all read this, never their own copy."""
        return tuple(iv for p in self.protected if (iv := getattr(p, "interval", None)) is not None)


class SecretStore:
    """Mirrors `EvidenceStore`: built fresh or extended, never mutated in place (I-4)."""

    def __init__(self, secrets: Iterable[Secret] = ()):
        self._by_id: dict[SecretId, Secret] = {}
        self._by_owner: dict[ActorId, list[Secret]] = {}
        for s in secrets:
            self.add(s)

    def add(self, secret: Secret) -> None:
        if secret.id in self._by_id:
            raise ValueError(f"duplicate Secret id: {secret.id}")
        self._by_id[secret.id] = secret
        self._by_owner.setdefault(secret.owner, []).append(secret)

    def get(self, secret_id: SecretId) -> Secret | None:
        return self._by_id.get(secret_id)

    def all(self) -> list[Secret]:
        return list(self._by_id.values())

    def for_owner(self, owner: ActorId) -> list[Secret]:
        return list(self._by_owner.get(owner, []))

    def owner_of(self, secret_id: SecretId) -> ActorId | None:
        s = self._by_id.get(secret_id)
        return s.owner if s else None

    def is_protected_for(self, owner: ActorId, proposition: Proposition) -> bool:
        """Is `proposition` a protected fact of ANY of `owner`'s secrets — §19.5's L0 row
        ("any suspect's claims about their own protected facts")."""
        return any(s.is_protected(proposition) for s in self.for_owner(owner))

    def collusion_edges(self, world_rels: Iterable) -> set[frozenset[ActorId]]:
        """I-37's collusion graph edges: "a shared `Secret`, a `Rel` in {spouse, lover,
        sibling, accomplice, employer_of_dependent}, and membership in another's
        `Secret.beneficiaries`" (§19.5). Returns unordered actor pairs; `admissibility.py`
        turns this into connected components. `world_rels` is `Case.rels` (`world.Rel`
        tuples) — kept a parameter rather than importing `world.case.Case` here to avoid a
        needless dependency on the whole case object for one field.
        """
        close_kinds = {"spouse", "lover", "sibling", "accomplice", "employer_of_dependent"}
        edges: set[frozenset[ActorId]] = set()
        # Shared secret: every pair of DISTINCT owners of secrets that name each other as
        # beneficiaries, or co-owners is not modelled (Secret.owner is singular) — so "shared
        # Secret" here means one owner's secret whose beneficiaries include another actor;
        # that is exactly the `beneficiaries` clause below, kept together to avoid double
        # counting the same authored relationship as two different edge kinds.
        for s in self._by_id.values():
            for b in s.beneficiaries:
                if b != s.owner:
                    edges.add(frozenset({s.owner, b}))
        for rel in world_rels:
            if getattr(rel, "rel_kind", None) in close_kinds:
                edges.add(frozenset({rel.a, rel.b}))
        return edges
