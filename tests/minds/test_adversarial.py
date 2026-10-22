"""The specific adversarial cases named in the Phase 2 brief, beyond what
`test_soundness.py`/`test_epistemic_and_character_fold.py` already cover (wrong location,
insufficient co-presence, impossible provenance, repeated/out-of-order event application)."""
from __future__ import annotations

from eidolon.minds.belief import form_beliefs
from eidolon.minds.epistemic import EpistemicState, Revision
from eidolon.minds.events import BeliefRevised
from eidolon.minds.fold import apply_epistemic
from eidolon.minds.knowledge import KnowledgeEntry, propagate_knowledge
from eidolon.minds.provenance import Told
from eidolon.minds.memory import encode_memories
from eidolon.world.facts import FactIndex
from eidolon.world.propositions import At
from eidolon.world.state import loc_at
from tests.world.fixtures.vance import vance_v01_negative, vance_v03


def test_belief_never_promoted_to_canonical_fact():
    """Forming beliefs (including FALSE ones — Told from an ungrounded teller, or a
    contradicted rule-5 loser) never touches the canonical `Case`/`FactIndex`. The world
    stays authoritative regardless of what any character believes (§6.1: Truth != Belief)."""
    case, _ = vance_v03()
    before_hash = case.content_hash()
    fi = FactIndex(case)
    truth_before = {p: fi.truth_value(p) for p in [At(actor="David", location="Study", interval=(76, 77))]}
    store = propagate_knowledge(case)
    for actor in case.living_actors():
        form_beliefs(actor, store, case, fi)  # discard results; only the side effects matter here
    assert case.content_hash() == before_hash  # I-4: sealed case never mutates
    truth_after = {p: fi.truth_value(p) for p in truth_before}
    assert truth_after == truth_before


def test_a_confidently_held_false_belief_is_still_marked_false():
    """A `Belief` can hold a false proposition with real confidence — its existence as a
    `Belief`, and the confidence attached to it, never make `is_true` True.

    The oracle is the fixture's own timeline, NOT `FactIndex`. An earlier version asserted
    `b.is_true == bool(fi.truth_value(b.proposition))`, which restates the implementation's
    own expression verbatim and so passes for any behaviour that expression produces —
    including the `Unknown`-collapses-to-`False` bug it was supposed to guard against.
    """
    case, _ = vance_v01_negative()
    lie = At(actor="David", location="Gazebo", interval=(70, 71))
    assert loc_at(case.events, "David", 70) == "Study", "fixture precondition: David is in the Study"

    store = propagate_knowledge(case)
    store.add(KnowledgeEntry(
        id="K_rumor", character="Elena", proposition=lie,
        source=Told(by="Margaret", speak_event_id="argue", teller_sincere=False,
                     grounding_entry_id=None),
        acquired_at=90, reliability=0.9, is_true=False))

    beliefs = form_beliefs("Elena", store, case, FactIndex(case)).beliefs
    rumor = next(b for b in beliefs if b.proposition == lie)
    assert rumor.confidence_0 > 0, "the belief is genuinely held"
    assert rumor.is_true is False, "and is still false — David was in the Study"


def test_beliefs_track_the_world_not_the_confidence_attached_to_them():
    """Across the whole cast: a belief's truth flag agrees with where the CaseLog actually
    put people, computed independently of `FactIndex`."""
    case, _ = vance_v01_negative()
    store, fi = propagate_knowledge(case), FactIndex(case)
    checked = 0
    for actor in case.living_actors():
        for b in form_beliefs(actor, store, case, fi).beliefs:
            p = b.proposition
            if p.kind != "At":
                continue
            actually_there = all(loc_at(case.events, p.actor, t) == p.location
                                 for t in range(*p.interval))
            assert b.is_true is actually_there, (actor, p)
            checked += 1
    assert checked > 20, f"only {checked} At-beliefs exercised"


def test_memory_never_bundles_a_belief_the_character_could_not_have_formed():
    """Every belief a memory's `content` cites must belong to that SAME character — a
    memory can never surface content "borrowed" from someone else's mind (which would be
    exactly "impossible knowledge" leaking through the memory layer)."""
    case, _ = vance_v03()
    store = propagate_knowledge(case)
    fi = FactIndex(case)
    for actor in case.living_actors():
        result = form_beliefs(actor, store, case, fi)
        by_id = {b.id: b for b in result.beliefs}
        for m in encode_memories(actor, list(result.beliefs), store, case):
            assert m.character == actor
            for bid in m.content:
                assert by_id[bid].character == actor  # KeyError itself would mean a leak


def test_no_character_ever_receives_a_knowledge_entry_about_something_only_another_actor_could_perceive():
    """Structural check across the whole cast: every entry's `character` field is the
    actual observer that `propagate_knowledge`/`derive_perception` assigned it to — no
    entry is ever cross-attributed. (A regression guard on the store's own bookkeeping,
    complementing V-2's per-entry soundness check.)"""
    case, _ = vance_v03()
    store = propagate_knowledge(case)
    for character in case.living_actors():
        for entry in store.for_character(character):
            assert entry.character == character


def test_contradictory_epistemic_updates_do_not_corrupt_state_last_write_wins():
    """Two `BeliefRevised` events for the same belief, in immediate succession, with
    opposite-direction confidence changes: the fold does not average, reject, or crash —
    it applies both in order and the log keeps a full audit trail of both."""
    state = EpistemicState()
    up = BeliefRevised(belief_id="B1", new_confidence_bp=9000,
                        revision=Revision(turn_id=1, old_bp=5000, new_bp=9000, reason="corroborated"))
    down = BeliefRevised(belief_id="B1", new_confidence_bp=1000,
                          revision=Revision(turn_id=2, old_bp=9000, new_bp=1000, reason="contradicted"))
    state = apply_epistemic(state, up)
    state = apply_epistemic(state, down)
    assert state.belief_confidence["B1"] == 1000  # last write wins, matches I-22's replay contract
    assert [r.reason for r in state.belief_revisions["B1"]] == ["corroborated", "contradicted"]  # full trail kept


def test_case_and_fact_index_are_unaffected_by_any_amount_of_epistemic_churn():
    """Hammering `EpistemicState` with many contradictory revisions never has anywhere to
    reach back into `Case`/`FactIndex` — there is no code path from `apply_epistemic` to
    either, by construction (module dependency direction, §23.1)."""
    case, _ = vance_v03()
    before = case.content_hash()
    state = EpistemicState()
    for i in range(50):
        state = apply_epistemic(state, BeliefRevised(
            belief_id="B1", new_confidence_bp=(i * 137) % 10000,
            revision=Revision(turn_id=i, old_bp=0, new_bp=(i * 137) % 10000, reason=f"turn {i}")))
    assert case.content_hash() == before
