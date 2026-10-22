"""The Phase 2 fold (I-22, I-31): `apply_epistemic`/`apply_character` copy an event's
post-value into state and nothing else — no decay curve, weight, or repetition factor is
recomputed here. Each function only reacts to the event kinds it owns (`events.py`'s
`EPISTEMIC_KINDS`/`CHARACTER_KINDS`) and passes every other kind through unchanged, so a
mixed event stream can be folded through both without the caller pre-splitting it.

Three `EpistemicState` fields are APPEND-shaped rather than replace-shaped — `recall_log`,
`belief_revisions` and `added_knowledge` (§6.3 gives each event "its post-value and the
appended record"). Appending is not idempotent, and I-5 requires that "replaying the
SessionLog reproduces identical state hashes"; I-13 treats a duplicated row as
corruption. So the fold appends only what is not already there: applying the same event
twice is a no-op, while two genuinely different records (different turn, different
outcome, different revision) both land. Without this, one duplicated `MemoryRecall` row
raises `memory.repetition_factor` and can flip a retrieval from weak to strong.
"""
from __future__ import annotations

from .character import CharacterState
from .epistemic import EpistemicState, RecallRecord, distortion_key
from .events import (
    BeliefRevised, ComposureChange, CoverStateDelta, DetectiveModelUpdate, EmotionalDelta,
    KnowledgeAdded, MemoryCorrected, MemoryRecall, MindsEvent, PressureChange, SuspicionShift,
    TrustChange,
)
from .ids import MemoryId
from .provenance import InvestigationTold
from .scale import bp


def _append_once(existing: tuple, record) -> tuple:
    """Append `record` unless an equal one is already recorded (see module docstring).
    Equality is the only identity the fold has: §26's `SessionEvent` envelope (`seq`,
    `action_id`) is Phase 7, and the payload is what I-41 hashes anyway."""
    return existing if record in existing else existing + (record,)


def apply_epistemic(state: EpistemicState, event: MindsEvent) -> EpistemicState:
    if isinstance(event, MemoryRecall):
        log = _append_once(state.recall_log.get(event.memory_id, ()), event.record)
        return state.model_copy(update={
            "memory_strength": {**state.memory_strength, event.memory_id: event.new_strength_bp},
            "recall_log": {**state.recall_log, event.memory_id: log},
        })
    if isinstance(event, MemoryCorrected):
        key = distortion_key(event.memory_id, event.field)
        return state.model_copy(update={
            "distortion_corrections": {**state.distortion_corrections, key: event.corrected_value},
        })
    if isinstance(event, BeliefRevised):
        revs = _append_once(state.belief_revisions.get(event.belief_id, ()), event.revision)
        return state.model_copy(update={
            "belief_confidence": {**state.belief_confidence, event.belief_id: event.new_confidence_bp},
            "belief_revisions": {**state.belief_revisions, event.belief_id: revs},
        })
    if isinstance(event, KnowledgeAdded):
        if not isinstance(event.entry.source, InvestigationTold):
            # I-27/AC-1: this is the ONLY legal provenance for a detective-supplied entry.
            raise ValueError(f"KnowledgeAdded entry {event.entry.id} must carry InvestigationTold "
                              f"provenance, got {event.entry.source.kind!r}")
        clash = next((e for e in state.added_knowledge if e.id == event.entry.id), None)
        if clash is not None:
            if clash != event.entry:
                # Same id, different content: two different entries cannot share an id
                # (`KnowledgeStore.add`'s own contract). Fail closed (I-15) rather than
                # letting `with_overlay` silently keep whichever it saw first.
                raise ValueError(f"KnowledgeAdded id {event.entry.id} already added with "
                                  f"different content")
            return state  # duplicated row: already applied
        return state.model_copy(update={"added_knowledge": state.added_knowledge + (event.entry,)})
    return state


def apply_character(state: CharacterState, event: MindsEvent) -> CharacterState:
    if isinstance(event, EmotionalDelta):
        return state.model_copy(update={"emotion": event.new_emotion})
    if isinstance(event, TrustChange):
        return state.model_copy(update={"trust_detective": event.new_trust_detective})
    if isinstance(event, SuspicionShift):
        if event.target is None:
            return state.model_copy(update={"suspicion_of_detective": event.new_value_bp})
        return state.model_copy(update={"suspicion": {**state.suspicion, event.target: event.new_value_bp}})
    if isinstance(event, PressureChange):
        # No clamp here: `PressureChange.new_value_bp` is a `Bp`, range-checked when the
        # event is constructed (I-17). Clamping in the fold would silently rewrite an
        # out-of-range recorded outcome, which is exactly what I-22 forbids.
        return state.model_copy(update={"verbal_pressure": {**state.verbal_pressure, event.secret_id: event.new_value_bp}})
    if isinstance(event, ComposureChange):
        return state.model_copy(update={"composure": event.new_composure_bp})
    if isinstance(event, CoverStateDelta):
        update: dict = {}
        if event.refuse_streak is not None:
            update["refuse_streak"] = event.refuse_streak
        if event.topics_probed is not None:
            update["topics_probed"] = event.topics_probed
        if event.contradictions_caught is not None:
            update["contradictions_caught"] = event.contradictions_caught
        if event.slips_used is not None:
            update["slips_used"] = frozenset(event.slips_used)
        return state.model_copy(update=update) if update else state
    if isinstance(event, DetectiveModelUpdate):
        return state.model_copy(update={"detective_model": event.new_model})
    return state


def build_memory_recall_event(memory_id: MemoryId, turn_id: int, current_strength_bp: int,
                               cue_match: float, outcome: str) -> MemoryRecall:
    """Convenience constructor (§8.5): the post-value carried is the pre-value — see
    `MemoryRecall`'s docstring for why no separate strengthening formula is applied here."""
    record = RecallRecord(turn_id=turn_id, cue_match_bp=bp(cue_match), outcome=outcome)  # type: ignore[arg-type]
    return MemoryRecall(memory_id=memory_id, turn_id=turn_id, new_strength_bp=current_strength_bp, record=record)
