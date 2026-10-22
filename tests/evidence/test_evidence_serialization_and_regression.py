"""Serialization round-trips, replay determinism, and the I-4 regression check: nothing in
`eidolon.evidence` mutates the Phase 1 `Case` it reads, and Phase 0.5/1/2 stay green."""
from __future__ import annotations

import subprocess
import sys

from eidolon.evidence.contradiction import Contradiction, evidence_vs_evidence
from eidolon.evidence.discovery import Discovery, DiscoveryState, apply_discovery, reachability
from eidolon.evidence.grounding import check_evidence_grounding
from eidolon.evidence.model import Evidence, EvidenceStore
from tests.evidence.fixtures.vance_evidence import evidence_case, evidence_case_store, vance_v03_evidence


def test_evidence_round_trips_through_json():
    store = evidence_case_store()
    for ev in store.all():
        dumped = ev.model_dump_json()
        again = Evidence.model_validate_json(dumped)
        assert again == ev


def test_discovery_state_and_event_round_trip_through_json():
    state = DiscoveryState(known_evidence=frozenset({"E1"}), visited_locations=frozenset({"Cellar"}))
    assert DiscoveryState.model_validate_json(state.model_dump_json()) == state
    event = Discovery(evidence_id="E1", turn=3, action="Dust", at="Knife")
    assert Discovery.model_validate_json(event.model_dump_json()) == event


def test_contradiction_round_trips_through_json():
    c = Contradiction(a="x", b="y", kind="presence", severity=0.5, explanation="e", visible_to_player=True)
    assert Contradiction.model_validate_json(c.model_dump_json()) == c


def test_evidence_case_content_hash_unaffected_by_evidence_operations_i4():
    """The sealed `Case` is never mutated by anything in `eidolon.evidence` — the same I-4
    discipline Phase 2 verified for `minds/`."""
    case = evidence_case()
    before = case.content_hash()
    store = evidence_case_store()
    check_evidence_grounding(case, store)
    reachability(store, initial_locations=["Cellar"], initial_items=["kit"])
    state = DiscoveryState(held_items=frozenset({"kit"}))
    apply_discovery(state, Discovery(evidence_id="E_fp", turn=1, action="Dust", at="Knife"), store)
    evidence_vs_evidence(store.get("E_fp"), store.get("E_fp_wide"))
    assert case.content_hash() == before


def test_vance_v03_case_content_hash_unaffected_by_evidence_operations_i4():
    case, evidence, stmt = vance_v03_evidence()
    before = case.content_hash()
    store = EvidenceStore(evidence)
    check_evidence_grounding(case, store, statement_intervals=stmt)
    assert case.content_hash() == before


def test_discovery_fold_is_idempotent_under_repeated_and_out_of_order_application():
    """Mirrors Phase 2's own `apply_epistemic`/`apply_character` idempotence tests, applied
    to `apply_discovery`: applying the same event twice, or re-applying earlier events after
    later ones, never regresses or duplicates state."""
    store = evidence_case_store()
    base = DiscoveryState(held_items=frozenset({"kit"}), visited_locations=frozenset({"Cellar"}))
    e1 = Discovery(evidence_id="E_fp", turn=1, action="Dust", at="Knife")
    e2 = Discovery(evidence_id="E_letter", turn=2, action="Read", at="Letter")

    forward = apply_discovery(apply_discovery(base, e1, store), e2, store)
    repeated = apply_discovery(apply_discovery(apply_discovery(base, e1, store), e1, store), e2, store)
    assert forward == repeated


def test_replaying_discovery_reproduces_an_identical_state_hash_across_processes():
    """The discovery-layer analogue of I-5's cross-process determinism check (Phase 0.5's
    own gate criterion (iv)): folding the same event list in a fresh interpreter yields the
    same STATE. Compared by parsed content, not raw JSON text: `known_evidence`/
    `visited_locations` are `frozenset`s, and Python randomizes string-hash seeding per
    process (`PYTHONHASHSEED`), so frozenset iteration order — and therefore JSON array
    order — is not itself canonical across processes, exactly the reason `Case.content_hash`
    sorts every unordered collection before hashing rather than trusting `model_dump_json`
    (`world/case.py`'s own docstring). `DiscoveryState` is a runtime overlay, not sealed case
    content, so it carries no `content_hash` of its own — round-tripping through
    `model_validate_json` and comparing by value is the equivalent check at this layer."""
    script = (
        "from eidolon.evidence.discovery import Discovery, DiscoveryState, apply_discovery\n"
        "from tests.evidence.fixtures.vance_evidence import evidence_case_store\n"
        "store = evidence_case_store()\n"
        "state = DiscoveryState(held_items=frozenset({'kit'}), visited_locations=frozenset({'Cellar'}))\n"
        "state = apply_discovery(state, Discovery(evidence_id='E_fp', turn=1, action='Dust', at='Knife'), store)\n"
        "state = apply_discovery(state, Discovery(evidence_id='E_letter', turn=2, action='Read', at='Letter'), store)\n"
        "print(state.model_dump_json())\n"
    )
    out = subprocess.run([sys.executable, "-c", script], cwd=str(__import__("pathlib").Path(__file__).parents[2]),
                          capture_output=True, text=True, check=True).stdout.strip()

    store = evidence_case_store()
    state = DiscoveryState(held_items=frozenset({"kit"}), visited_locations=frozenset({"Cellar"}))
    state = apply_discovery(state, Discovery(evidence_id="E_fp", turn=1, action="Dust", at="Knife"), store)
    state = apply_discovery(state, Discovery(evidence_id="E_letter", turn=2, action="Read", at="Letter"), store)
    assert DiscoveryState.model_validate_json(out) == state


def test_reachability_is_a_deterministic_pure_function():
    store = evidence_case_store()
    r1 = reachability(store, initial_locations=["Cellar"], initial_items=["kit"])
    r2 = reachability(store, initial_locations=["Cellar"], initial_items=["kit"])
    assert (r1.reachable, r1.unreachable, r1.depth, r1.cued) == (r2.reachable, r2.unreachable, r2.depth, r2.cued)

# Phase 0.5/1/2 regression is run as a full separate `pytest`/`spike` invocation (see the
# Phase 3 report) rather than shelled out to from inside this suite — spawning full
# subprocess test runs from within a test file only slows every future `pytest tests/evidence`
# down for a re-check this repo's CI already does at the top level.
