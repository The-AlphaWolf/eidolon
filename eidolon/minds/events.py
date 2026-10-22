"""The Phase 2 slice of the `SessionEventKind` catalogue (§25, I-31): every kind that
writes a runtime-mutable `EpistemicState` or `CharacterState` field. Each payload carries
its POST-value (I-22: "the fold applies recorded outcomes only... never re-runs... weights")
— `fold.py`'s `apply_*` functions never recompute a decay curve, a repetition factor or an
emotion delta; they only copy the payload's value into the state.

The full `SessionLog`/hash-chain/store machinery (§26) is Phase 7 — this module only owns
the event *shapes* Phase 2's own fields need, matching how `world/events.py` owns `Effect`
shapes without owning persistence either.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from ..world.ids import ActorId
from .character import DetectiveModel, Emotion
from .epistemic import RecallRecord, Revision
from .ids import BeliefId, MemoryId
from .knowledge import KnowledgeEntry
from .scale import Bp


class _MindsEvent(BaseModel):
    model_config = ConfigDict(frozen=True)


# --- EpistemicState-writing (§6.3) -------------------------------------------------
class MemoryRecall(_MindsEvent):
    """§8.5. `new_strength_bp` is the post-value of `memory_strength[memory_id]` — per the
    architecture's own text, strengthening is *only* the appended `RecallRecord` raising
    the next `repetition_factor`; no separate strength-bump formula is given, so the
    post-value equals the pre-value unless a caller has a documented reason to raise it."""
    kind: Literal["MemoryRecall"] = "MemoryRecall"
    memory_id: MemoryId
    turn_id: int
    new_strength_bp: Bp
    record: RecallRecord


class MemoryCorrected(_MindsEvent):
    """§8.6: fires only when the detective presents an item in `Distortion.correctable_by`
    to a character with `trust(character->detective) >= 0.4`. The sealed
    `Distortion.recalled_value` is never touched; only the overlay is written."""
    kind: Literal["MemoryCorrected"] = "MemoryCorrected"
    memory_id: MemoryId
    field: str
    corrected_value: Any
    turn_id: int


class BeliefRevised(_MindsEvent):
    kind: Literal["BeliefRevised"] = "BeliefRevised"
    belief_id: BeliefId
    new_confidence_bp: Bp
    revision: Revision


class KnowledgeAdded(_MindsEvent):
    """§6.5: detective-supplied information. `entry.source` MUST be `InvestigationTold` —
    this is what makes the grounding-propagation rule (AC-1, I-27) hold: anything reached
    through this event is L0 forever, in every mouth it passes through."""
    kind: Literal["KnowledgeAdded"] = "KnowledgeAdded"
    entry: KnowledgeEntry


# --- CharacterState-writing (§9) ----------------------------------------------------
class EmotionalDelta(_MindsEvent):
    kind: Literal["EmotionalDelta"] = "EmotionalDelta"
    new_emotion: Emotion


class TrustChange(_MindsEvent):
    kind: Literal["TrustChange"] = "TrustChange"
    new_trust_detective: Bp


class SuspicionShift(_MindsEvent):
    kind: Literal["SuspicionShift"] = "SuspicionShift"
    target: ActorId | None = None  # None => `suspicion_of_detective`
    new_value_bp: Bp


class PressureChange(_MindsEvent):
    kind: Literal["PressureChange"] = "PressureChange"
    secret_id: str
    new_value_bp: Bp  # bounded by VERBAL_PRESSURE_MAX == BP_MAX (I-17)


class ComposureChange(_MindsEvent):
    kind: Literal["ComposureChange"] = "ComposureChange"
    new_composure_bp: Bp


class CoverStateDelta(_MindsEvent):
    """Bundles the small bookkeeping fields (§9) that change together on a turn; any
    subset may be `None` (unchanged)."""
    kind: Literal["CoverStateDelta"] = "CoverStateDelta"
    refuse_streak: int | None = None
    topics_probed: dict[str, int] | None = None
    contradictions_caught: tuple[str, ...] | None = None
    slips_used: tuple[str, ...] | None = None


class DetectiveModelUpdate(_MindsEvent):
    kind: Literal["DetectiveModelUpdate"] = "DetectiveModelUpdate"
    new_model: DetectiveModel


MindsEvent = Annotated[
    Union[MemoryRecall, MemoryCorrected, BeliefRevised, KnowledgeAdded,
          EmotionalDelta, TrustChange, SuspicionShift, PressureChange,
          ComposureChange, CoverStateDelta, DetectiveModelUpdate],
    Field(discriminator="kind"),
]

EPISTEMIC_KINDS = {"MemoryRecall", "MemoryCorrected", "BeliefRevised", "KnowledgeAdded"}
CHARACTER_KINDS = {"EmotionalDelta", "TrustChange", "SuspicionShift", "PressureChange",
                    "ComposureChange", "CoverStateDelta", "DetectiveModelUpdate"}
