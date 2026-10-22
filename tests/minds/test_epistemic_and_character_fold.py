"""§6.3/§9 overlay fold: `apply_epistemic`/`apply_character` write POST-values only (I-22),
and every runtime-mutable field has a writing event kind (I-31, T-23)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from eidolon.minds.character import (
    VERBAL_PRESSURE_MAX, CharacterState, DetectiveModel, Emotion, Personality,
    initial_character_state,
)
from eidolon.minds.epistemic import EpistemicState, Revision
from eidolon.minds.events import (
    BeliefRevised, ComposureChange, CoverStateDelta, DetectiveModelUpdate, EmotionalDelta,
    KnowledgeAdded, MemoryCorrected, PressureChange, SuspicionShift, TrustChange,
)
from eidolon.minds.fold import apply_character, apply_epistemic, build_memory_recall_event
from eidolon.minds.knowledge import KnowledgeEntry
from eidolon.minds.memory import repetition_factor
from eidolon.minds.provenance import InvestigationTold, Witnessed
from eidolon.world.propositions import At

PERSONALITY = Personality(composure_base=0.7, volatility=0.3, deference=0.4, guile=0.2,
                           talkativeness=0.5, self_preservation=0.5)


def test_i31_every_characterstate_field_has_a_writing_event_kind():
    """T-23: enumerate `CharacterState` + `EpistemicState` fields; each is written by
    some `apply()`."""
    state = initial_character_state("A", PERSONALITY)
    events = [
        EmotionalDelta(new_emotion=Emotion(anxiety=100, hostility=200, warmth=300)),
        TrustChange(new_trust_detective=6000),
        SuspicionShift(target=None, new_value_bp=1500),
        SuspicionShift(target="B", new_value_bp=2500),
        PressureChange(secret_id="S1", new_value_bp=4000),
        ComposureChange(new_composure_bp=3000),
        CoverStateDelta(refuse_streak=1, topics_probed={"alibi": 2},
                         contradictions_caught=("C1",), slips_used=("Sl1",)),
        DetectiveModelUpdate(new_model=DetectiveModel(estimated_suspicion_of_me=800)),
    ]
    for ev in events:
        state = apply_character(state, ev)
    assert state.emotion == Emotion(anxiety=100, hostility=200, warmth=300)
    assert state.trust_detective == 6000
    assert state.suspicion_of_detective == 1500
    assert state.suspicion == {"B": 2500}
    assert state.verbal_pressure == {"S1": 4000}
    assert state.composure == 3000
    assert state.refuse_streak == 1
    assert state.topics_probed == {"alibi": 2}
    assert state.contradictions_caught == ("C1",)
    assert state.slips_used == frozenset({"Sl1"})
    assert state.detective_model.estimated_suspicion_of_me == 800
    # every field on the model was touched by the loop above (fails loudly if a new field
    # is added to CharacterState without a corresponding event kind, T-23's spirit).
    untouched = set(CharacterState.model_fields) - {"actor", "personality"}
    touched = {"emotion", "trust_detective", "suspicion_of_detective", "suspicion",
               "verbal_pressure", "composure", "refuse_streak", "detective_model",
               "topics_probed", "contradictions_caught", "slips_used"}
    assert untouched == touched


def test_pressure_change_is_bounded_by_verbal_pressure_max():
    """I-17 bp bounds. This used to assert that the fold CLAMPED 999999 down to the cap;
    the clamp has been replaced by a range check on the payload itself. Rejecting is the
    stronger rule and the I-22-consistent one: a fold that rewrites an out-of-range
    recorded outcome is no longer applying the recorded outcome."""
    with pytest.raises(ValidationError):
        PressureChange(secret_id="S1", new_value_bp=999999)
    state = initial_character_state("A", PERSONALITY)
    state = apply_character(state, PressureChange(secret_id="S1", new_value_bp=VERBAL_PRESSURE_MAX))
    assert state.verbal_pressure["S1"] == VERBAL_PRESSURE_MAX


def test_cover_state_delta_partial_update_leaves_other_fields_alone():
    state = initial_character_state("A", PERSONALITY)
    state = apply_character(state, CoverStateDelta(refuse_streak=2))
    assert state.refuse_streak == 2
    assert state.topics_probed == {}


def test_i31_every_epistemicstate_field_has_a_writing_event_kind():
    state = EpistemicState()
    entry = KnowledgeEntry(id="K1", character="A", proposition=At(actor="X", location="Hall", interval=(0, 5)),
                            source=InvestigationTold(by_detective_turn=2), acquired_at=0, reliability=0.5, is_true=False)
    events = [
        build_memory_recall_event("M1", turn_id=1, current_strength_bp=6000, cue_match=0.8, outcome="strong"),
        MemoryCorrected(memory_id="M1", field="interval", corrected_value=[10, 12], turn_id=2),
        BeliefRevised(belief_id="B1", new_confidence_bp=7000,
                      revision=Revision(turn_id=1, old_bp=5000, new_bp=7000, reason="detective showed E1")),
        KnowledgeAdded(entry=entry),
    ]
    for ev in events:
        state = apply_epistemic(state, ev)
    assert state.memory_strength == {"M1": 6000}
    assert len(state.recall_log["M1"]) == 1
    assert state.distortion_corrections == {"M1::interval": [10, 12]}
    assert state.belief_confidence == {"B1": 7000}
    assert len(state.belief_revisions["B1"]) == 1
    assert state.added_knowledge == (entry,)
    touched = {"memory_strength", "recall_log", "belief_confidence", "belief_revisions",
               "distortion_corrections", "added_knowledge"}
    assert set(EpistemicState.model_fields) == touched


def test_knowledge_added_rejects_non_investigation_told_provenance():
    """AC-1/I-27: this is the ONLY legal path into `added_knowledge` — enforcing it here
    (not just by convention) is what makes the grounding-propagation guarantee real."""
    bad_entry = KnowledgeEntry(id="K1", character="A", proposition=At(actor="X", location="Hall", interval=(0, 5)),
                                source=Witnessed(event_id="e1", modality="sight", quality=0.9),
                                acquired_at=0, reliability=0.9, is_true=True)
    with pytest.raises(ValueError):
        apply_epistemic(EpistemicState(), KnowledgeAdded(entry=bad_entry))


def test_repeated_application_of_the_same_event_is_idempotent_for_post_value_events():
    """Applying the same `MemoryRecall`/`ComposureChange` twice lands on the same state as
    applying it once — every payload here IS the post-value, not a delta, so replay of a
    duplicated log entry cannot double-count (I-22)."""
    state = EpistemicState()
    ev = build_memory_recall_event("M1", turn_id=1, current_strength_bp=5000, cue_match=0.6, outcome="weak")
    once = apply_epistemic(state, ev)
    twice = apply_epistemic(once, ev)
    assert once.memory_strength == twice.memory_strength

    # `recall_log` is append-shaped (§6.3), and appending is not idempotent by itself:
    # `memory.repetition_factor` is a function of exactly this length and feeds
    # `memory.score`, so a replayed duplicate row used to move retrieval (weak -> strong at
    # the boundary). The fold now appends only records it does not already hold, so the
    # whole state — not just `memory_strength` — is unchanged by a duplicated row.
    assert twice == once
    assert len(twice.recall_log["M1"]) == 1
    assert repetition_factor(twice.recall_log["M1"]) == repetition_factor(once.recall_log["M1"])

    cstate = initial_character_state("A", PERSONALITY)
    cev = ComposureChange(new_composure_bp=4000)
    c1 = apply_character(cstate, cev)
    c2 = apply_character(c1, cev)
    assert c1 == c2


def test_events_applied_in_unexpected_order_still_converge_on_last_write_wins():
    """I-22: the fold applies recorded outcomes only. Two `ComposureChange`s in either
    order leave `composure` at whichever was applied LAST — order-dependent by design
    (it is a log replay, not a commutative merge), so out-of-order application must not
    silently "average" or otherwise invent behaviour beyond last-write-wins."""
    state = initial_character_state("A", PERSONALITY)
    a, b = ComposureChange(new_composure_bp=3000), ComposureChange(new_composure_bp=7000)
    forward = apply_character(apply_character(state, a), b)
    backward = apply_character(apply_character(state, b), a)
    assert forward.composure == 7000
    assert backward.composure == 3000
    assert forward != backward  # order matters; the fold does not pretend otherwise


def test_apply_functions_ignore_event_kinds_they_do_not_own():
    """A mixed event stream can be folded through both without pre-splitting by kind."""
    estate = EpistemicState()
    cstate = initial_character_state("A", PERSONALITY)
    cev = ComposureChange(new_composure_bp=1000)
    assert apply_epistemic(estate, cev) == estate  # not an epistemic kind: no-op
    eev = MemoryCorrected(memory_id="M1", field="interval", corrected_value=[1, 2], turn_id=1)
    assert apply_character(cstate, eev) == cstate  # not a character kind: no-op


def test_t6_pre_turn_snapshot_unaffected_by_same_turns_revision_and_correction():
    """T-6 (§28.7)/§8.6's turn-ordering rule: "stage 5... reads ONLY that [pre-turn]
    snapshot... corrections and revisions take effect for the NEXT turn." A caller that
    took its snapshot before this turn's `BeliefRevised`+`MemoryCorrected` must still see
    the OLD values; a caller reading the post-turn state sees the new ones — one
    deterministic value each side, never a mix."""
    pre_turn = EpistemicState()
    revised = BeliefRevised(belief_id="B1", new_confidence_bp=8000,
                             revision=Revision(turn_id=5, old_bp=5000, new_bp=8000, reason="presented E1"))
    corrected = MemoryCorrected(memory_id="M1", field="interval", corrected_value=[70, 72], turn_id=5)

    # Both orders within the turn must agree (they touch disjoint overlay fields).
    forward = apply_epistemic(apply_epistemic(pre_turn, revised), corrected)
    backward = apply_epistemic(apply_epistemic(pre_turn, corrected), revised)
    assert forward == backward
    post_turn = forward

    # stage 5, evaluated against the snapshot taken BEFORE this turn, sees the old values:
    assert pre_turn.belief_confidence.get("B1", 5000) == 5000
    assert pre_turn.distortion_corrections.get("M1::interval", [70, 71]) == [70, 71]
    # ...while anything reading the post-turn state (the NEXT turn) sees the new ones:
    assert post_turn.belief_confidence["B1"] == 8000
    assert post_turn.distortion_corrections["M1::interval"] == [70, 72]
