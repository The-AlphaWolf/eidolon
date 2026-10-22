"""`EpistemicState` (§6.3, AC-4): the per-game runtime overlay.

Nothing in the sealed generation-time stores (`KnowledgeStore`, `Belief`, `Memory`) mutates
during play (I-4). Runtime epistemic change lives here instead, written only by the four
event kinds named below (`events.py`), each carrying its post-value (I-22, I-31). Reading
an epistemic value is always `overlay.get(id, sealed_default)` — never recomputed.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from .ids import BeliefId, MemoryId
from .knowledge import KnowledgeEntry
from .scale import Bp


class RecallRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    turn_id: int
    cue_match_bp: Bp  # I-17: `RecallRecord` is hashed authoritative state (it lives in
                       # `EpistemicState`), so the cue-overlap score is stored in bp like every
                       # other runtime scalar. `memory.cue_overlap` still computes in 0..1.
    outcome: Literal["strong", "weak", "none"]


class Revision(BaseModel):
    model_config = ConfigDict(frozen=True)
    turn_id: int
    old_bp: Bp
    new_bp: Bp
    reason: str


def distortion_key(memory_id: MemoryId, field: str) -> str:
    """Composite string encoding of the architecture's `(MemoryId, field)` tuple key —
    plain dict keys stay JSON-round-trippable (pydantic's `dict[tuple, Any]` is not),
    matching how the rest of the world model keeps hashed state string-keyed (§4.6's
    `WorldState`, all plain-`str`-keyed dicts)."""
    return f"{memory_id}::{field}"


class EpistemicState(BaseModel):
    """Per game; folded from the SessionLog (§26); never part of the case content hash."""
    model_config = ConfigDict(frozen=True)

    memory_strength: dict[MemoryId, Bp] = {}
    recall_log: dict[MemoryId, tuple[RecallRecord, ...]] = {}
    belief_confidence: dict[BeliefId, Bp] = {}
    belief_revisions: dict[BeliefId, tuple[Revision, ...]] = {}
    distortion_corrections: dict[str, Any] = {}  # key: `distortion_key(memory_id, field)`
    added_knowledge: tuple[KnowledgeEntry, ...] = ()  # InvestigationTold entries; always L0


def current_memory_strength(state: EpistemicState, memory_id: MemoryId, sealed_strength_0: int) -> int:
    """`overlay.get(id, sealed_default)` (§6.3) — takes the id/default directly rather than
    a `Memory` object so this leaf module stays independent of `memory.py` (`memory.py`
    imports this module, not the reverse; `character.py` mirrors the same convention)."""
    return state.memory_strength.get(memory_id, sealed_strength_0)


def current_belief_confidence(state: EpistemicState, belief_id: BeliefId, sealed_confidence_0: int) -> int:
    return state.belief_confidence.get(belief_id, sealed_confidence_0)


def current_distortion_value(state: EpistemicState, memory_id: MemoryId, field: str, sealed_value: Any) -> Any:
    return state.distortion_corrections.get(distortion_key(memory_id, field), sealed_value)
