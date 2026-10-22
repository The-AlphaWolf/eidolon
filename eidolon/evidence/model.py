"""The evidence model (§5.1): the authoritative-but-partial artifact layer built ON TOP of
the canonical world (Phase 1, `eidolon.world`) and the epistemic layers (Phase 2,
`eidolon.minds`) — never a third source of truth (§5.2's own framing, and the boundary this
phase was given): an `Evidence` item CLAIMS a proposition via its `implications`; whether
the claim is TRUE is decided by the canonical `FactIndex` (`grounding.py`), and whether some
character has LEARNED of it is a `KnowledgeEntry`/`Belief` (Phase 2). Collapsing any of
these three is exactly what §5 forbids — this module only ever adds the claim layer.

Sealed at generation (I-4), the same discipline `Memory`/`Belief` use (Phase 2): nothing
here mutates after construction. `EvidenceStore` is the only mutable container, and even it
is only ever built fresh or extended, mirroring `KnowledgeStore`/`BeliefStore`.
"""
from __future__ import annotations

from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..world.frozen import Frozen, FrozenDict
from ..world.ids import ActorId, EventId, EvidenceId, ObjectId
from ..world.propositions import Interval, Proposition
from .ids import HypothesisTemplateId

EvidenceKind = Literal[
    "Fingerprint", "Bloodstain", "Document", "Object", "Footprint",
    "Witness", "Digital", "Timepiece",
]
"""§5.1's own list, closed the same way `EvidenceKind`'s sibling vocabularies are (§4.7,
ADR-22): the architecture's "…" is a prose ellipsis, not an open type; widening it is the
same ADR-level change extending `ActionKind`/`Proposition` would be."""

RequirementId = str
"""`EvidenceId | StatementId` per §5.1's `Implication.requires` — both are plain `str`
under the hood (`world/ids.py`, `evidence/ids.py`), so one alias covers the union without a
runtime tag; callers resolve which is which by looking the id up in the relevant store."""


class Implication(BaseModel):
    """§5.1. `strength` combines with `Evidence.reliability` (`combined_strength`, below) to
    feed the contradiction detector (§13.2) and, in later phases, refutation weight. `requires`
    is what P-9/I-30 (`grounding.check_temporal_grounding`) demands before the proposition's
    INTERVAL may be asserted — not a flavor list, a load-bearing dependency graph (§19.4)."""
    model_config = ConfigDict(frozen=True)

    proposition: Proposition
    strength: float = Field(default=1.0, ge=0.0, le=1.0)
    requires: tuple[RequirementId, ...] = ()


def combined_strength(evidence: "Evidence", implication: Implication) -> float:
    """§5.1: "Implications are propositions with strength... combined with Evidence.reliability"."""
    return evidence.reliability * implication.strength


# --- discovery ---------------------------------------------------------------
class Prereq(BaseModel):
    """A closed vocabulary of discovery prerequisites (§5.1's own comment: "KnowsAbout
    (location), HasItem(kit), StatementHeard(id), EvidenceFound(id)"). A tagged union rather
    than free text so `discovery.py`'s BFS can evaluate it without a parser (ADR-4's own
    reasoning, applied here)."""
    model_config = ConfigDict(frozen=True)

    kind: Literal["KnowsAbout", "HasItem", "StatementHeard", "EvidenceFound"]
    ref: str  # LocationId | ObjectId(kit) | StatementId | EvidenceId, per `kind`


class DiscoverySpec(BaseModel):
    """§5.1. `cue` is §19.4's "every edge carries a cue: Ref — an item already in the
    player's material that names the target's entity or location": `None` means the item
    needs no cue to be found (e.g. it sits in the open at the start location)."""
    model_config = ConfigDict(frozen=True)

    action: Literal["Look", "Open", "Dust", "Read", "Search", "Ask"]
    at: str  # LocationId | ObjectId
    prerequisites: tuple[Prereq, ...] = ()
    reveals_text: str = ""
    cue: str | None = None


class RedHerringSpec(BaseModel):
    """§5.2/§19.6: ordinary evidence tagged as existing to mislead. `refuter` must be
    reachable and, once found, produce a `Contradiction` with the misleading hypothesis
    (`contradiction.py`); the `misleads_toward` consistency check itself needs the solver
    (§19.6 first half) and is Phase 6's job."""
    model_config = ConfigDict(frozen=True)

    misleads_toward: HypothesisTemplateId
    refuter: RequirementId


class Evidence(BaseModel):
    """§5.1. Immutable after construction (I-4)."""
    model_config = ConfigDict(frozen=True)

    id: EvidenceId
    kind: EvidenceKind
    object: ObjectId | None = None
    location_at_investigation: str | None = None  # LocationId | ObjectId
    created_by: EventId | None = None              # None: creating event not pinned — the
                                                     # `requires` chain grounds it instead (§5.2)
    created_at: Interval | None = None
    authentic: bool = True
    planted_by: EventId | None = None
    reliability: float = Field(default=1.0, ge=0.0, le=1.0)
    implications: tuple[Implication, ...] = ()
    discovery: DiscoverySpec
    visibility: Literal["plain", "concealed", "forensic", "documentary"] = "plain"
    known_to: Frozen[ActorId, str] = Field(default_factory=FrozenDict)
    """-> KnowledgeEntryId (Phase 2 type; kept a plain str to avoid `world`/`evidence`
    naming a `minds` model, mirroring `CharacterState.verbal_pressure`'s own
    SecretId-as-str forward reference, §23.1).

    `Frozen`, not `dict`: pydantic's `frozen=True` blocks attribute REBINDING only, so a
    plain dict field stayed a live container and `evidence.known_to[actor] = forged`
    rewrote provenance on a sealed item (I-4). This is the same `world/frozen.py` guard
    `Case.actors`/`.locations`/`.objects` already use, for the same reason — reads,
    iteration, `==` and JSON round-tripping are unchanged."""
    interacted: tuple[tuple[ActorId, EventId], ...] = ()
    supports: tuple[HypothesisTemplateId, ...] = ()
    contradicts: tuple[HypothesisTemplateId, ...] = ()
    load_bearing: bool = False
    red_herring: RedHerringSpec | None = None


class EvidenceStore:
    """Mirrors `KnowledgeStore`/`BeliefStore` (Phase 2): built fresh or extended, never
    mutated in place once an item is added."""

    def __init__(self, items: Iterable[Evidence] = ()):
        self._by_id: dict[EvidenceId, Evidence] = {}
        self._by_object: dict[ObjectId, list[Evidence]] = {}
        for e in items:
            self.add(e)

    def add(self, evidence: Evidence) -> None:
        if evidence.id in self._by_id:
            raise ValueError(f"duplicate Evidence id: {evidence.id}")
        self._by_id[evidence.id] = evidence
        if evidence.object is not None:
            self._by_object.setdefault(evidence.object, []).append(evidence)

    def get(self, evidence_id: EvidenceId) -> Evidence | None:
        return self._by_id.get(evidence_id)

    def all(self) -> list[Evidence]:
        return list(self._by_id.values())

    def by_object(self, object_id: ObjectId) -> list[Evidence]:
        return list(self._by_object.get(object_id, []))
