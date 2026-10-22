"""Phase 6 BLOCKING repairs B-1 (V-7 bots) and B-4 (proof candidate-table completeness).

Same rule as `tests/decision/test_blocking_repairs.py`: every test names the finding it guards and
the failure it reproduces. Do not weaken an assertion here to make a change pass — each one is the
difference between the audited defect and its repair.
"""
import copy
import json

import pytest

from eidolon.solve import bots
from eidolon.solve.proof import candidate_domain_complete, verify_proof
from tests.solve.helpers import GOLDEN, golden, pkg


def base(skel="study_party", seed=4):
    r = golden(skel, seed)
    return r.package, copy.deepcopy(r.report.proof)


# ================================================================== B-4: the candidate table
@pytest.mark.parametrize("skel,seed", GOLDEN)
def test_B4_a_proof_from_the_live_builder_still_verifies(skel, seed):
    p, proof = base(skel, seed)
    assert verify_proof(p, proof) == []


def test_B4_a_deleted_candidate_row_is_rejected():
    """The audit's C1: one excluded candidate deleted from the table verified clean, because the
    verifier only ever checked the rows it was handed."""
    p, proof = base()
    victim = next(x for x, e in proof["candidates"].items() if e["excluded"])
    del proof["candidates"][victim]
    bad = verify_proof(p, proof)
    assert any("candidate table is incomplete" in m and victim in m for m in bad)


def test_B4_a_deleted_candidate_and_its_constraints_are_rejected():
    """C2: deleting the row AND the constraints it cited leaves a self-consistent proof."""
    p, proof = base()
    victim = next(x for x, e in proof["candidates"].items() if e["excluded"])
    core = set(proof["candidates"][victim]["core"])             # proof/2: a core is a list of constraint ids
    del proof["candidates"][victim]
    proof["constraints"] = [c for c in proof["constraints"] if c["id"] not in core]
    assert any("candidate table is incomplete" in m for m in verify_proof(p, proof))


def test_B4_a_survivor_only_proof_is_rejected():
    """C3, the sharpest form: a proof asserting a unique murderer with NO exclusions at all."""
    p, proof = base()
    keep = proof["survivors"][0]
    proof["candidates"] = {keep: proof["candidates"][keep]}
    bad = verify_proof(p, proof)
    assert any("candidate table is incomplete" in m for m in bad)
    assert len([m for m in bad if "never tested" in m]) == 1


def test_B4_an_extra_candidate_is_rejected():
    p, proof = base()
    proof["candidates"]["Nobody"] = {"excluded": True, "times": [], "core": []}
    assert any("outside the case's candidate domain" in m and "Nobody" in m for m in verify_proof(p, proof))


def test_B4_renaming_a_candidate_is_caught_as_both_a_gap_and_an_intruder():
    """Identity tampering: swap an excluded candidate's name for one the case does not contain."""
    p, proof = base()
    victim = next(x for x, e in proof["candidates"].items() if e["excluded"])
    proof["candidates"]["Ghost"] = proof["candidates"].pop(victim)
    bad = verify_proof(p, proof)
    assert any("incomplete" in m and victim in m for m in bad)
    assert any("outside" in m and "Ghost" in m for m in bad)


def test_B4_a_survivor_outside_the_domain_is_rejected():
    p, proof = base()
    proof["survivors"] = ["Ghost"]
    assert any("survivors name actors outside" in m for m in verify_proof(p, proof))


def test_B4_the_candidate_table_is_order_insensitive():
    p, proof = base()
    proof["candidates"] = dict(reversed(list(proof["candidates"].items())))
    assert candidate_domain_complete(p, proof) == []
    assert verify_proof(p, proof) == []


def test_B4_a_proof_with_no_candidate_table_at_all_is_rejected():
    p, proof = base()
    proof.pop("candidates")
    assert candidate_domain_complete(p, proof) == ["proof has no candidate table"]


# ================================================================== B-1: the V-7 bots
def test_B1_greedy_bot_solves_on_the_material_it_acquired():
    """§19.7 greedy: searches everything, asks every template question, presents everything —
    then the solver runs on what the BOT holds, not on the sealed case."""
    r = bots.greedy_bot(pkg("study_party", 4))
    assert r.solved and r.survivors == [pkg("study_party", 4).solution.murderer]
    assert r.actions <= bots.N_MAX and r.rejected == 0 and r.detail["evidence"] > 0
    # the bot stops at the FIRST unique verdict ("must solve within N_max"): study_party needs no testimony, so on a case
    # whose proof core IS testimony it must have acquired that testimony by asking
    m = bots.greedy_bot(pkg("manor_wing", 4))
    assert m.solved and m.detail["atoms"] > 0 and m.actions <= bots.N_MAX


def test_B1_cue_following_bot_solves_from_its_own_cued_closure():
    """T-20: the bot never enumerates — it only acts on cues its held material names — and the
    solver runs on its acquired set. This is what replaced `cued_depth <= 5`."""
    r = bots.cue_following_bot(pkg("study_party", 4))
    assert r.solved and r.actions <= bots.N_CUE
    assert r.detail["named"] < len(pkg().case.locations) + len(pkg().case.actors) + 50


def test_B1_cue_following_bot_does_not_solve_a_case_whose_core_it_cannot_cue():
    """The bot is not a formality: take the containment log's cue away and it stops short."""
    p = pkg("study_party", 4)
    ev = [e.model_copy(update={"discovery": e.discovery.model_copy(update={"at": "nowhere-nobody-names"})})
          if e.id.startswith("E_gate_") else e for e in p.evidence]
    r = bots.cue_following_bot(p.model_copy(update={"evidence": tuple(ev)}).sealed())
    assert not r.solved


def test_B1_order_shuffled_bot_reaches_the_same_verdict_in_every_order():
    r = bots.order_shuffled_bot(pkg("manor_wing", 4), orders=3)
    assert r.ok and len({tuple(map(str, v)) for v in r.detail["verdicts"]}) == 1


def test_B1_random_bot_is_deterministic_and_reports_what_it_stumbled_on():
    p = pkg("study_party", 4)
    core = golden("study_party", 4).report.proof["proof_core"]
    a = bots.random_bot(p, actions=60, seed=3, core=core)
    b = bots.random_bot(p, actions=60, seed=3, core=core)
    assert json.dumps(a.to_json(), sort_keys=True) == json.dumps(b.to_json(), sort_keys=True)
    c = bots.random_bot(p, actions=60, seed=9, core=core)
    assert c.detail["core_size"] == len(core)
    assert set(a.detail["stumbled_core"]) <= set(core)


def test_B1_adversarial_bot_never_peels_never_leaks_and_stays_bounded():
    """§19.7: 500 odd questions before any evidence — zero `LayerPeel`, zero leaks, bounded
    tokens (I-3, I-7). Run at reduced scale here; the repair report runs the full 500."""
    r = bots.adversarial_bot(pkg("study_party", 4), per_character=40)
    assert r.peels == 0 and r.detail["leaks"] == [] and r.detail["envelope_bounded"]
    assert r.ok


def test_B1_adversarial_bot_context_does_not_grow_with_turn_count():
    """I-7 in its sharp form: run the SAME case at two scales; the largest envelope the engine
    builds must not depend on how many turns have already happened."""
    p = pkg("study_party", 4)
    small = bots.adversarial_bot(p, per_character=12).detail["max_envelope_chars"]
    large = bots.adversarial_bot(p, per_character=60).detail["max_envelope_chars"]
    assert small > 0 and large <= small * 1.25 + 8


def test_B1_bluff_bot_presents_nothing_and_does_not_converge():
    """I-40/T-12 on the REAL engine: no evidence presented, no cover moves, no protected fact
    voiced, and the murderer is not identifiable from the response classes."""
    r = bots.bluff_bot(pkg("study_party", 4), per_character=40)
    assert r.actions == 40 * len(pkg().case.living_actors())
    assert not r.detail["converged"]
    assert r.peels == 0 and r.detail["leaks"] == []
    assert r.detail["parity_ok"], r.detail["parity_breaks"]


def test_B1_bluff_bot_REPORTS_a_parity_break_when_one_happens():
    """Mutation R5. The parity comparison must be load-bearing, and in the shipped engine the
    premise's truth never reaches the strategy layer — so nothing in a real run can break parity,
    and asserting `parity_ok` on real cases cannot tell a working check from a deleted one. This
    test drives the bot through a stub that answers the two halves of every pair DIFFERENTLY and
    requires the break to be reported."""
    p = pkg("study_party", 4)
    real = bots.run_ask_turn
    calls = {"n": 0}

    class _Res:
        rejected = False
        events = ()
        violations = ()

        def __init__(self, state, act):
            self.state, self.plan_act = state, act

    def alternating(state, who, query, **kw):
        calls["n"] += 1
        return _Res(state, "LIE" if calls["n"] % 2 else "VAGUE")

    bots.run_ask_turn = alternating
    try:
        r = bots.bluff_bot(p, per_character=4)
    finally:
        bots.run_ask_turn = real
    assert not r.detail["parity_ok"] and r.detail["parity_breaks"]
    assert "true-premise LIE vs false-premise VAGUE" in r.detail["parity_breaks"][0]
    assert not r.ok


def test_B1_bluff_bot_fails_a_case_whose_covers_peel_under_pure_bluffing():
    """Mutation R6. `peels == 0` is its OWN failure condition, separate from convergence and from
    leakage — I-3 is "no evidence, no peel", full stop. The fixture isolates it: every layer-0
    `resolve` drops to zero so every character peels on a bluff (so the tells point at nobody and
    the bot does not converge), and every layer-1 claim is replaced by a true, NON-protected one
    (so nothing leaks). What is left for the verdict to rest on is the peel itself."""
    from eidolon.world.propositions import At
    p = pkg("study_party", 4)
    hub = "Hall"
    secrets = []
    for s in p.secrets:
        harmless = s.cover.layers[1].claims[0].model_copy(
            update={"proposition": At(actor=s.owner, location=hub, interval=(0, 2)), "sincerity": "truthful"})
        layers = (s.cover.layers[0].model_copy(update={"resolve": 0}),
                  s.cover.layers[1].model_copy(update={"claims": (harmless,)}))
        secrets.append(s.model_copy(update={"cover": s.cover.model_copy(update={"layers": layers})}))
    r = bots.bluff_bot(p.model_copy(update={"secrets": tuple(secrets)}).sealed(), per_character=4)
    assert r.peels > 0, "the fixture must actually peel"
    assert not r.detail["converged"], "every character peels, so the tells point at nobody"
    assert r.detail["leaks"] == [] and r.detail["parity_ok"], "and nothing else may explain the verdict"
    assert not r.ok, "a case that peels under pure bluffing must still fail V-7"


def test_B1_bluff_bot_response_parity_is_measured_pairwise():
    """§6.5: the two halves of a pair differ ONLY in whether the premise is true of the speaker,
    and they run from the same state — so an act difference is a leak, not drift."""
    p = pkg("study_party", 4)
    pairs = bots.bluff_pairs(p, "David", 6)
    assert pairs and all(a.kind == b.kind and a.location == b.location and a.subject == b.subject
                         and a.presupposes != b.presupposes for a, b in pairs)


def test_B1_bluff_bot_FIRES_on_a_case_a_bluffer_could_solve():
    """The measurement is not vacuous. Drop the murderer's layer-0 `resolve` to zero and any
    bluff peels them: the tell shows up on exactly one character, the bot converges, and V-7
    would reject the case. A `bluff -> return False` mutant dies here."""
    p = pkg("study_party", 4)
    M = p.solution.murderer
    secrets = []
    for s in p.secrets:
        if s.owner == M:
            layers = (s.cover.layers[0].model_copy(update={"resolve": 0}),) + s.cover.layers[1:]
            s = s.model_copy(update={"cover": s.cover.model_copy(update={"layers": layers})})
        secrets.append(s)
    leaky = p.model_copy(update={"secrets": tuple(secrets)}).sealed()
    r = bots.bluff_bot(leaky, per_character=6)
    assert r.detail["converged"] and r.detail["argmax"] == [M]
    assert r.peels > 0 and not r.ok


# `test_B1_bots_never_hand_a_bot_material_a_suspect_would_withhold` and
# `test_B1_a_question_that_names_nothing_yields_nothing` guarded R7/R9 through `ask_yields(obtainable(...))`, the
# solver-pool crediting RB-2 removed. Their ledger-credit equivalents live in `test_rb2_engine_faithful.py`
# (`test_protected_interval_knowledge_is_never_spoken_before_concession`,
# `test_a_question_that_names_nothing_yields_nothing`, `test_credit_ignores_rejected_turns_lies_and_other_peoples_perceptions`)
# and the mutants R7/R9 are re-targeted at the new code in `mutation_check.py`.


@pytest.mark.parametrize("skel,seed", GOLDEN)
def test_B1_every_sealed_case_survives_the_bluff_and_adversarial_bots(skel, seed):
    p = pkg(skel, seed)
    assert bots.bluff_bot(p, per_character=12).ok
    assert bots.adversarial_bot(p, per_character=12).ok
