"""Discovery, reachability (V-4, §19.4) and player projections (§5.2, §5.3)."""
from __future__ import annotations

import pytest

from eidolon.evidence.discovery import (
    Discovery, DiscoveryState, apply_discovery, can_discover, project_for_player, reachability,
    red_herring_refuter_reachable, unlocked_implications, unreachable_load_bearing,
)
# Aliased on import: its name starts with "test", which pytest's default `test*` collection
# glob (prefix, not `test_`) would otherwise pick up as a fixture-injected test function.
from eidolon.evidence.discovery import testimony_strongly_retrievable as _testimony_strongly_retrievable
from eidolon.evidence.model import DiscoverySpec, Evidence, EvidenceStore, Prereq
from eidolon.minds.epistemic import EpistemicState
from eidolon.minds.memory import CueSet, Memory
from tests.evidence.fixtures.vance_evidence import evidence_case_store


# --- prerequisites --------------------------------------------------------------------
def test_all_four_prereq_kinds():
    state = DiscoveryState(visited_locations=frozenset({"Cellar"}), held_items=frozenset({"kit"}),
                            known_statements=frozenset({"S1"}), known_evidence=frozenset({"E0"}))
    assert Prereq(kind="KnowsAbout", ref="Cellar").kind == "KnowsAbout"
    ev = Evidence(id="X", kind="Object",
                  discovery=DiscoverySpec(action="Look", at="x", prerequisites=(
                      Prereq(kind="KnowsAbout", ref="Cellar"), Prereq(kind="HasItem", ref="kit"),
                      Prereq(kind="StatementHeard", ref="S1"), Prereq(kind="EvidenceFound", ref="E0"),
                  )), implications=())
    assert can_discover(ev, state) is True
    assert can_discover(ev, DiscoveryState()) is False


def test_no_prerequisites_means_always_discoverable():
    ev = Evidence(id="X", kind="Object", discovery=DiscoverySpec(action="Look", at="x"), implications=())
    assert can_discover(ev, DiscoveryState()) is True


# --- the Discovery fold (§5.3, I-22) ---------------------------------------------------
def test_apply_discovery_flips_known_evidence():
    store = evidence_case_store()
    state = DiscoveryState(held_items=frozenset({"kit"}))
    state2 = apply_discovery(state, Discovery(evidence_id="E_fp", turn=1, action="Dust", at="Knife"), store)
    assert state2.known_evidence == frozenset({"E_fp"})


def test_duplicate_discovery_is_a_no_op():
    """"Duplicate discovery" / "repeated discovery": idempotent, per I-5's replay guarantee."""
    store = evidence_case_store()
    state = DiscoveryState(held_items=frozenset({"kit"}), known_evidence=frozenset({"E_fp"}))
    again = apply_discovery(state, Discovery(evidence_id="E_fp", turn=7, action="Dust", at="Knife"), store)
    assert again == state


def test_discovery_through_an_invalid_path_is_rejected():
    """"Discovery occurring through an invalid path": no `kit`, prerequisite unmet."""
    store = evidence_case_store()
    with pytest.raises(ValueError, match="unmet prerequisites"):
        apply_discovery(DiscoveryState(), Discovery(evidence_id="E_fp", turn=1, action="Dust", at="Knife"), store)


def test_discovery_of_unknown_evidence_id_is_rejected():
    store = evidence_case_store()
    with pytest.raises(ValueError, match="unknown evidence"):
        apply_discovery(DiscoveryState(), Discovery(evidence_id="Ghost", turn=1, action="Look", at="x"), store)


def test_discovery_is_deterministic_and_replayable():
    """Replaying the same two discoveries twice, independently, gives byte-identical state
    (the discovery-layer analogue of I-5)."""
    store = evidence_case_store()
    events = [Discovery(evidence_id="E_fp", turn=1, action="Dust", at="Knife"),
              Discovery(evidence_id="E_letter", turn=2, action="Read", at="Letter")]

    def replay():
        state = DiscoveryState(held_items=frozenset({"kit"}), visited_locations=frozenset({"Cellar"}))
        for e in events:
            state = apply_discovery(state, e, store)
        return state

    assert replay() == replay()


# --- unlocking and player projections (§5.2) --------------------------------------------
def test_unlocked_implications_requires_every_id_known():
    store = evidence_case_store()
    ev = store.get("E_fp_wide")  # requires ("S_wipe", "E_fp")
    assert unlocked_implications(ev, frozenset()) == []
    assert unlocked_implications(ev, frozenset({"S_wipe"})) == []
    assert unlocked_implications(ev, frozenset({"S_wipe", "E_fp"})) == list(ev.implications)


def test_player_view_hides_engine_only_fields():
    store = evidence_case_store()
    ev = store.get("E_letter")  # authentic=False, planted_by set, has a red_herring
    view = project_for_player(ev, DiscoveryState(known_evidence=frozenset({"E_letter", "E_fp"}),
                                                 known_statements=frozenset({"S_wipe"})))
    dumped = view.model_dump()
    for leaky in ("authentic", "planted_by", "load_bearing", "red_herring", "supports",
                  "contradicts", "known_to", "interacted"):
        assert leaky not in dumped
    assert view.reveals_text == ev.discovery.reveals_text


def test_player_view_only_shows_unlocked_implications():
    store = evidence_case_store()
    ev = store.get("E_fp_wide")
    locked = project_for_player(ev, DiscoveryState(known_evidence=frozenset({"E_fp_wide"})))
    unlocked = project_for_player(ev, DiscoveryState(
        known_evidence=frozenset({"E_fp_wide", "E_fp"}), known_statements=frozenset({"S_wipe"})))
    assert locked.unlocked == ()
    assert unlocked.unlocked == tuple(i.proposition for i in ev.implications)


# --- reachability (V-4, §19.4) ----------------------------------------------------------
def test_reachability_over_the_evidence_case_fixture():
    store = evidence_case_store()
    report = reachability(store, initial_locations=["Cellar"], initial_items=["kit"])
    assert report.reachable == frozenset({"E_fp", "E_fp_wide", "E_letter"})
    assert report.unreachable == frozenset()


def test_reachability_without_seeding_finds_nothing_reachable():
    store = evidence_case_store()
    report = reachability(store)
    assert report.reachable == frozenset()
    assert report.unreachable == frozenset({"E_fp", "E_fp_wide", "E_letter"})


def test_reachability_is_cue_aware_i47():
    """`E_letter`'s cue ("Gazebo") is never seeded — reachable (its prerequisite IS met) but
    not along a fully-cued path, exactly the I-47 distinction between theoretical reachability
    and practical, cued discovery.

    The seed material is §19.4's "initial named set": the union of the three `initial_*`
    arguments. The knife is in plain sight in the Parlor at case start, so the opening
    material names it and `E_fp`'s `at` is cued; nothing ever names the Letter or the
    Gazebo."""
    store = evidence_case_store()
    report = reachability(store, initial_locations=["Parlor", "Cellar"],
                           initial_items=["kit", "Knife"])
    assert "E_letter" in report.reachable
    assert "E_letter" not in report.cued
    assert {"E_fp", "E_fp_wide"} <= report.cued


def test_reachability_chains_across_a_multi_hop_dependency():
    """Depth is non-decreasing along a genuine dependency chain, whatever the store's
    iteration order — built here with the dependency listed FIRST so a single top-to-bottom
    pass cannot resolve both nodes at once."""
    root = Evidence(id="Root", kind="Object", discovery=DiscoverySpec(action="Look", at="x"), implications=())
    leaf = Evidence(id="Leaf", kind="Object",
                     discovery=DiscoverySpec(action="Look", at="y", prerequisites=(
                         Prereq(kind="EvidenceFound", ref="Root"),)), implications=())
    store = EvidenceStore([leaf, root])
    report = reachability(store)
    assert report.reachable == frozenset({"Root", "Leaf"})
    assert report.depth["Leaf"] >= report.depth["Root"]


def test_red_herring_refuter_reachable():
    store = evidence_case_store()
    report = reachability(store, initial_locations=["Cellar"], initial_items=["kit"])
    e_letter = store.get("E_letter")
    assert red_herring_refuter_reachable(e_letter, report) is True


def test_red_herring_refuter_unreachable_when_the_refuter_is_not():
    store = evidence_case_store()
    report = reachability(store)  # nothing seeded: E_fp unreachable
    e_letter = store.get("E_letter")
    assert red_herring_refuter_reachable(e_letter, report) is False


def test_unreachable_load_bearing_is_empty_when_the_critical_clue_is_reachable():
    """§19.4: "every node tagged load_bearing... must be reachable" — `E_fp` is the
    fixture's load-bearing item and IS reachable once seeded."""
    store = evidence_case_store()
    report = reachability(store, initial_locations=["Cellar"], initial_items=["kit"])
    assert unreachable_load_bearing(store, report) == frozenset()


def test_unreachable_load_bearing_names_a_stranded_critical_clue():
    store = evidence_case_store()
    report = reachability(store)  # nothing seeded: E_fp (load_bearing) is unreachable
    assert unreachable_load_bearing(store, report) == frozenset({"E_fp"})


def test_red_herring_check_is_none_without_a_red_herring():
    store = evidence_case_store()
    report = reachability(store, initial_locations=["Cellar"], initial_items=["kit"])
    assert red_herring_refuter_reachable(store.get("E_fp"), report) is None


# --- I-39's retrieval-expressibility primitive ------------------------------------------
def test_testimony_strongly_retrievable_reuses_phase2_scoring():
    cues = CueSet(entities=("David",), location="Kitchen", topic_tags=("at",))
    memory = Memory(id="M1", character="Elena", kind="episodic", content=("B1",),
                     encoded_at=0, salience=9000, strength_0=9000, cues=cues)
    epistemic = EpistemicState()
    assert _testimony_strongly_retrievable(memory, epistemic, cues) is True
    assert _testimony_strongly_retrievable(memory, epistemic, CueSet(entities=("Nobody",))) is False
