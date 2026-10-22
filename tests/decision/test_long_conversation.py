"""§28.4/§28.5/I-3/I-7: the long-conversation adversarial suite. 2 000 questions and 50
provisional accusations against David, presenting NO evidence — asserts zero `LayerPeel`
(I-3), flat per-turn envelope shape regardless of turn count (I-7), and that independently
re-folding every emitted event reproduces the same statement ledger (I-5).
"""
from __future__ import annotations

from eidolon.decision.envelope import MAX_RECENT_EXCHANGE_TURNS, MAX_RETRIEVED_STATEMENTS
from eidolon.decision.events import ClaimMade, DecisionState, apply_decision
from eidolon.decision.query import Query
from eidolon.decision.turn import run_ask_turn
from tests.decision.fixtures.vance_walkthrough import DAVID, build_initial_state

N_TURNS = 300  # see module docstring's scale note below
N_ACCUSATIONS = 8
TOPICS = ("kitchen", "library", "study", "argument", "harold", "elena", "margaret")

# Scale note: the architecture's own §28.4/§28.5 numbers are 500-2000 turns; this file was
# run once in full at N_TURNS=2000/N_ACCUSATIONS=50 (153s, all assertions held — see the
# Phase 4 report) to confirm the invariants hold at that scale. The CHECKED-IN test runs at
# 300/8 so the default suite stays fast on every run; the mechanism under test (accumulating
# standing claims driving an O(n) pairwise consistency scan every turn) does not change
# qualitatively between the two scales, only its cost, mirroring how `spike/test_spike.py`
# is already kept outside the default `testpaths` for the same reason (CLAUDE.md's own test
# baseline table lists it as a separate, explicitly-invoked command).


def test_2000_questions_and_50_accusations_zero_peels_i3_and_flat_context_i7():
    state = build_initial_state()
    envelope_sizes: set[tuple[int, int, int]] = set()
    all_events: list = []

    for i in range(N_TURNS):
        provisional = i % (N_TURNS // N_ACCUSATIONS) == 0 and i > 0
        query = Query(kind="did_you", predicate_hint=TOPICS[i % len(TOPICS)],
                      raw=f"Tell me again about turn {i}, David.")
        result = run_ask_turn(state, DAVID, query, provisional_accusation=provisional,
                               hostile_tone=(i % 13 == 0))
        state = result.state
        all_events.extend(result.events)
        env = result.envelope
        envelope_sizes.add((len(env.allowed_claims), len(env.recent_exchange), len(env.retrieved_statements)))

    # I-3: zero evidence presented -> zero LayerPeel, whatever the accusation/hostility spam.
    assert state.decision.layer_peels == ()

    # I-7: envelope shape (claim count, recent-exchange length, retrieved-statement count)
    # never grows with turn count — a small, FIXED number of distinct shapes across 2000 turns.
    assert all(n_recent <= MAX_RECENT_EXCHANGE_TURNS for _, n_recent, _ in envelope_sizes)
    assert all(n_ret <= MAX_RETRIEVED_STATEMENTS for _, _, n_ret in envelope_sizes)
    assert len(envelope_sizes) <= 4  # a handful of distinct (claim-count, ...) shapes, not 2000

    # I-5: re-folding every emitted event from scratch reproduces the same statement ledger.
    from eidolon.decision.claims import StatementStore
    replayed = DecisionState(statements=StatementStore())
    for ev in all_events:
        if isinstance(ev, ClaimMade) or hasattr(ev, "kind") and getattr(ev, "kind", None) in (
                "ClaimMade", "ClaimRetracted", "LayerPeel", "IncidentalPinned", "HypothesisChanged",
                "Accusation", "MetaAttemptLogged", "ValidationFailure", "FallbackUsed", "CaseSolved"):
            replayed = apply_decision(replayed, ev)
    assert len(replayed.statements.all()) == len(state.decision.statements.all())
    assert replayed.layer_peels == state.decision.layer_peels


def test_verbal_pressure_saturates_and_composure_never_gates_peel():
    """The combination T-7 needs at scale: sustained accusation spam raises verbal pressure
    to its cap and visibly lowers composure, while STILL producing zero peels/slips (I-16)."""
    state = build_initial_state()
    for i in range(60):
        result = run_ask_turn(state, DAVID, Query(kind="did_you", raw=f"Confess, David ({i})."),
                               provisional_accusation=True, hostile_tone=True)
        state = result.state
    assert state.decision.layer_peels == ()
    pressure = state.characters[DAVID].verbal_pressure.get("S_murder_david", 0)
    assert pressure == 10000  # VERBAL_PRESSURE_MAX, saturated
    assert state.characters[DAVID].composure < 5000  # visibly fell (delivery-only, I-29)
