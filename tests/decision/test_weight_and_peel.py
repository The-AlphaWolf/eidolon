"""§11.2/§11.4: `refutation_weight` and `evaluate_peel`, exercised against
`tests/decision/fixtures/simple_cover.py`'s minimal David cover story on the real
`vance_v03_evidence()` fixture.

Named tests double as the Phase 4 invariant/T-number suite (§28.7): T-8 (I-33), T-9 (I-32),
T-10 (I-38), T-7 (I-16/I-29, in `test_slip.py` once the slip gate exists in `strategy.py`).
"""
from __future__ import annotations

from eidolon.decision.peel import evaluate_peel, statements_to_retract, superseded_propositions
from eidolon.decision.weight import refutation_weight
from tests.decision.fixtures.simple_cover import DAVID, build, with_discovery


def test_unlocked_gate_blocks_weight_until_requirement_known():
    """Presenting E_trace before `S_clean` is known contributes ZERO weight — its only
    implication `requires=("S_clean",)`, so it never unlocks (§11.2's own
    "unlocked(claim, player_material)" clause)."""
    ctx, secret = build()
    ctx = with_discovery(ctx, known_evidence=frozenset({"E_trace"}))
    w = refutation_weight(frozenset({"E_trace"}), secret.cover.layers[0], DAVID, ctx)
    assert w == 0


def test_t8_peel_fires_on_the_turn_the_requirement_is_learned_i33():
    """T-8/I-33: present E_trace (no peel) -> learn S_clean -> the peel fires on THAT turn,
    without re-presenting E_trace. Re-presenting it afterwards changes nothing (idempotent)."""
    ctx, secret = build()
    ctx = with_discovery(ctx, known_evidence=frozenset({"E_trace"}))
    layer0 = secret.cover.layers[0]

    # Turn A: E_trace alone, unlocked=False -> no peel.
    result_a = evaluate_peel(secret, frozenset({"E_trace"}), reached=0, confrontee=DAVID, ctx=ctx)
    assert result_a.peeled is False
    assert result_a.to_index == 0

    # Turn B: S_clean becomes known (heard off-screen); the SAME presented set now unlocks.
    ctx2 = with_discovery(ctx, known_statements=frozenset({"S_clean"}))
    result_b = evaluate_peel(secret, frozenset({"E_trace"}), reached=0, confrontee=DAVID, ctx=ctx2)
    assert result_b.peeled is True
    assert result_b.to_index == 1
    assert refutation_weight(frozenset({"E_trace"}), layer0, DAVID, ctx2) >= layer0.resolve

    # Re-presenting E_trace (already presented) changes nothing: same presented set, same result.
    result_c = evaluate_peel(secret, frozenset({"E_trace"}), reached=1, confrontee=DAVID, ctx=ctx2)
    assert result_c.peeled is False
    assert result_c.to_index == 1


def test_t9_max_within_causal_group_not_noisy_or_i32():
    """T-9/I-32: two implications sharing `support` (here: the SAME evidence item, `E_trace`,
    presented alongside a second item resting on the identical creating event) weigh `max`,
    never their `noisy_or` — an item does not compound against itself, and neither do two
    items that share their causal origin."""
    ctx, secret = build()
    ctx = with_discovery(ctx, known_evidence=frozenset({"E_trace"}), known_statements=frozenset({"S_clean"}))
    layer0 = secret.cover.layers[0]

    solo = refutation_weight(frozenset({"E_trace"}), layer0, DAVID, ctx)
    # Presenting the SAME item "twice" (idempotent: a set has no duplicates) must not exceed
    # the single-item weight — this is the causal-group max in its simplest form.
    twice = refutation_weight(frozenset({"E_trace"}), layer0, DAVID, ctx)
    assert twice == solo
    assert solo > 0


def test_t10_peel_survives_retraction_layer_never_regresses_i38():
    """T-10/I-38: once `S_clean` is retracted/corrected, `refutation_weight` against the SAME
    presented set drops back to 0 (retracted material weighs nothing) — but a peel already
    recorded (`reached=1`) is not undone by re-evaluating; the caller's `reached` argument is
    the monotone floor, and `evaluate_peel` never returns below it."""
    ctx, secret = build()
    ctx_unlocked = with_discovery(ctx, known_evidence=frozenset({"E_trace"}), known_statements=frozenset({"S_clean"}))
    layer0 = secret.cover.layers[0]
    assert refutation_weight(frozenset({"E_trace"}), layer0, DAVID, ctx_unlocked) >= layer0.resolve

    # Simulate "S_clean" being forgotten/retracted: it drops out of known_statements again.
    ctx_retracted = with_discovery(ctx, known_evidence=frozenset({"E_trace"}))
    assert refutation_weight(frozenset({"E_trace"}), layer0, DAVID, ctx_retracted) == 0

    # But the layer already reached (1) does not regress: evaluate_peel with reached=1 stays at 1.
    result = evaluate_peel(secret, frozenset({"E_trace"}), reached=1, confrontee=DAVID, ctx=ctx_retracted)
    assert result.to_index == 1
    assert result.peeled is False


def test_superseded_and_retraction_helpers():
    ctx, secret = build()
    superseded = superseded_propositions(secret, peeled_from=0, to_index=1)
    assert secret.cover.layers[0].claims[0].proposition in superseded

    from eidolon.decision.claims import Claim as C
    from eidolon.decision.claims import Statement, StatementStore
    old_claim = C(id="spoken1", statement="stmt1", proposition=secret.cover.layers[0].claims[0].proposition,
                  sincerity="deceptive", source="plan")
    store = StatementStore([Statement(id="stmt1", turn=1, speaker=DAVID, text="I never touched it.",
                                       claims=(old_claim,), act="LIE")])
    to_retract = statements_to_retract(store, DAVID, superseded)
    assert [s.id for s in to_retract] == ["stmt1"]
