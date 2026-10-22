"""The closed provenance schema (§6.2) and admissibility levels (§19.5, I-27).

Every `KnowledgeEntry` carries one of these. The union is closed by design, same rule as
the proposition schema (§4.7): extending it is an ADR-level change.

Admissibility levels themselves (`AdmissibilityLevel`) live here rather than in a later
`solve/` package because I-27 states admissibility is "a property of provenance" — the
level a piece of grounding can reach is intrinsic to what kind of grounding it is, before
any corroboration or claim-wrapping is considered. The actual walk over a store (needs
`KnowledgeStore`/`BeliefStore`) is `admissibility.admissibility_level` to avoid a cycle.
"""
from __future__ import annotations

from enum import IntEnum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from ..world.ids import ActorId, EventId, ObjectId
from .ids import BeliefId, KnowledgeEntryId


class AdmissibilityLevel(IntEnum):
    """§19.5's L0..L3 lattice. `L3` (authentic physical evidence) is never produced by a
    provenance walk alone — it is a property of `Evidence.Implication` (Phase 3) — so this
    module's own walk (§ `admissibility.py`) only ever returns L0..L2."""
    L0 = 0
    L1 = 1
    L2 = 2
    L3 = 3


def level_below(level: AdmissibilityLevel) -> AdmissibilityLevel:
    """Told is "at most the teller's own level, one step down" (§6.2 comment)."""
    return AdmissibilityLevel(max(AdmissibilityLevel.L0, level - 1))


class _Prov(BaseModel):
    model_config = ConfigDict(frozen=True)


class Witnessed(_Prov):
    """Direct perception: an event, co-presence, or sustained sighting (§4.8 rules 1-9)."""
    kind: Literal["Witnessed"] = "Witnessed"
    event_id: EventId  # a real Event.id, or a perception-module synthetic id (§4.8; both
                        # are auditable back to the CaseLog — see `test_perception.py`'s
                        # `test_every_perception_fact_is_auditable_to_the_caselog`)
    modality: Literal["sight", "sound", "co-presence"]
    quality: float


class Participated(_Prov):
    kind: Literal["Participated"] = "Participated"
    event_id: EventId


class Absence(_Prov):
    """§4.8.7 / I-34: grounds `NotAt` ONLY. Never emitted for a positive proposition."""
    kind: Literal["Absence"] = "Absence"
    basis: Literal["continuous", "scan", "inference"]
    coverage: float
    entrances_covered: bool


class Told(_Prov):
    kind: Literal["Told"] = "Told"
    by: ActorId
    speak_event_id: EventId
    teller_sincere: bool
    grounding_entry_id: KnowledgeEntryId | None = None
    # ^ The teller's OWN entry that this hearsay descends from. I-27 computes admissibility
    # "from that claim's `grounding` chain" — so the chain has to be a recorded edge, not a
    # lookup. Re-resolving the teller's entry by searching their store lets the walk pick a
    # *different* entry than the one actually relayed (the highest-reliability one), which
    # is precisely how a poisoned `InvestigationTold` chain launders itself into a clean
    # level once corroboration promotes L1 to L2 (AC-1).
    #
    # `None` means "the teller had no entry to relay" — an ungrounded assertion, which
    # `admissibility.py` floors at L0. It never means "look it up".


class Read(_Prov):
    kind: Literal["Read"] = "Read"
    document_object_id: ObjectId
    read_event_id: EventId


class Inferred(_Prov):
    """§6.4 rule 4. `from_ids` names the field `from` in the architecture prose; renamed
    here only because `from` is a Python reserved word — no semantic change."""
    kind: Literal["Inferred"] = "Inferred"
    from_ids: tuple[Union[KnowledgeEntryId, BeliefId], ...]
    rule_id: str


class Background(_Prov):
    kind: Literal["Background"] = "Background"
    background_kind: Literal["relationship", "habit", "layout", "common_knowledge"]


class InvestigationTold(_Prov):
    """Runtime-only (§6.5): the detective told/showed the character something this session.
    ALWAYS L0 (I-27), and poisons any chain containing it."""
    kind: Literal["InvestigationTold"] = "InvestigationTold"
    by_detective_turn: int  # turn_id


Provenance = Annotated[
    Union[Witnessed, Participated, Absence, Told, Read, Inferred, Background, InvestigationTold],
    Field(discriminator="kind"),
]
