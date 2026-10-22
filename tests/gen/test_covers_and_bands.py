"""Phase 6 BLOCKING repairs B-2 (cover synthesis / V-3) and B-3 (difficulty-band gating).

Same rule as the other blocker-regression files: each test names the audited failure it guards.
"""
import pytest

from eidolon.decision.cover_consistency import check_cover_consistency, derive_breaker_sets
from eidolon.evidence.discovery import unlocked_implications
from eidolon.gen.pipeline import MAX_BAND_ATTEMPTS, generate, generate_in_band, validate
from eidolon.gen.skeletons import SKELETONS
from eidolon.solve import fairness as fair
from eidolon.minds import accounts
from eidolon.solve.lattice import _resolve, admissible
from eidolon.solve.session import decision_context
from tests.solve.helpers import GOLDEN, REDUCED, golden, pkg, rebuild


# ================================================================== B-2: covers and the real V-3
@pytest.mark.parametrize("skel,seed", GOLDEN)
def test_B2_generated_cases_have_no_V3_violations_under_the_real_checker(skel, seed):
    """The audit ran Phase 4's own `check_cover_consistency` on a sealed case and got 3
    violations. The pipeline now runs it, so a sealed case has none."""
    p = pkg(skel, seed)
    assert check_cover_consistency(list(p.secrets), decision_context(p)) == []


@pytest.mark.parametrize("skel,seed", GOLDEN)
def test_B2_the_murderers_layer0_has_a_non_empty_derived_breaker_set(skel, seed):
    """The audited defect in one line: `derive_breaker_sets` returned `[]` for the murderer, so
    the murderer could never be peeled at all. It must now derive a set, and that set must be the
    trace (§20.1 item 6: refutable by physical evidence)."""
    p = pkg(skel, seed)
    ctx = decision_context(p)
    murder = next(s for s in p.secrets if s.kind == "murder")
    sets = derive_breaker_sets(murder, 0, ctx)
    assert sets, "the murderer's layer 0 has no breaker set"
    assert all("E_trace" in b for b in sets)


@pytest.mark.parametrize("skel,seed", GOLDEN)
def test_B2_every_breaker_item_has_an_evidence_response(skel, seed):
    p = pkg(skel, seed)
    ctx = decision_context(p)
    for s in p.secrets:
        for layer in s.cover.layers:
            if layer.terminal is not None:
                continue
            covered = {(r.evidence, r.layer) for r in s.evidence_responses}
            for bset in derive_breaker_sets(s, layer.index, ctx):
                for ref in bset:
                    assert (ref, layer.index) in covered, f"{s.id} layer {layer.index}: {ref}"


@pytest.mark.parametrize("skel,seed", GOLDEN)
def test_B2_breaker_items_are_reachable_through_phase3_discovery(skel, seed):
    r = golden(skel, seed)
    assert r.report.stages["V-4"]["ok"] and r.report.stages["V-4"]["breaker_refs"] > 0


def test_B2_the_requires_token_resolves_at_runtime_and_for_the_solver():
    """D-2's runtime half, which made the murderer's trace inert in play: `clean@<hk>` is a DECLARED account token
    (ADR-23) that Phase 3's unlock gate accepts once it has been HEARD (`known_accounts`) — while the solver's own
    `_resolve` matches the very same token against the speaker's `Participated` perception, through the one resolver."""
    p = pkg("study_party", 4)
    trace = next(e for e in p.evidence if e.id == "E_trace")
    token = trace.implications[0].requires[0]
    assert token in p.accounts and accounts.atoms_of(p.case, token)
    assert unlocked_implications(trace, frozenset()) == []            # locked with nothing held
    assert unlocked_implications(trace, frozenset({token}))           # unlocked once the account is held
    ctx, mat, _v = __import__("tests.solve.helpers", fromlist=["verdict"]).verdict(p)
    lvl = {c.item: c.level for c in admissible(p.case, ctx.store, mat, ctx.comps, ctx.victim)}
    assert _resolve(p.case, mat, (token,), lvl) is not None           # still resolvable by V-5


@pytest.mark.parametrize("skel,seed", GOLDEN)
def test_B2_layer_one_is_never_an_empty_dead_end(skel, seed):
    for s in pkg(skel, seed).secrets:
        for layer in s.cover.layers[1:]:
            assert layer.claims, f"{s.id} layer {layer.index} has no claims"
        assert s.cover.layers[-1].terminal is not None


def test_B2_removing_the_murderers_breaker_is_rejected_by_V3():
    """The requested regression: take the murderer's breaker away and the case must not seal.
    Dropping the declared account leaves `E_trace` locked, so no subset reaches `resolve` any more."""
    p = pkg("study_party", 4)
    stripped = rebuild(p, accounts=())
    ctx = decision_context(stripped)
    murder = next(s for s in stripped.secrets if s.kind == "murder")
    assert derive_breaker_sets(murder, 0, ctx) == ()
    rep = validate(stripped)
    assert rep.failed_at == "V-3"
    assert any("no derivable breaker set" in x for x in rep.problems)
    # and the weak V-6 proxy would NOT have caught it — which is why V-3 has to
    assert fair.contract(*_v6_args(stripped))["2_lies_breakable"][0]


def test_B2_removing_an_evidence_response_is_rejected_by_V3():
    p = pkg("study_party", 4)
    secrets = tuple(s.model_copy(update={"evidence_responses": ()}) if s.kind != "murder" else s
                    for s in p.secrets)
    rep = validate(rebuild(p, secrets=secrets))
    assert rep.failed_at == "V-3"
    assert any("no EvidenceResponse" in x for x in rep.problems)


def test_B2_a_cover_that_lies_about_nothing_is_rejected():
    """V-3's own premise: a layer-0 claim that is TRUE in the CaseLog is not a cover."""
    p = pkg("study_party", 4)
    innocent = next(s for s in p.secrets if s.kind != "murder")
    truthful = innocent.cover.layers[0].model_copy(update={"claims": (innocent.cover.layers[1].claims[0],)})
    cover = innocent.cover.model_copy(update={"layers": (truthful,) + innocent.cover.layers[1:]})
    secrets = tuple(s.model_copy(update={"cover": cover}) if s.id == innocent.id else s for s in p.secrets)
    rep = validate(rebuild(p, secrets=secrets))
    assert rep.failed_at == "V-3" and any("not a lie" in x for x in rep.problems)


def test_B2_an_account_token_that_resolves_to_nothing_fails_closed():
    """I-27/ADR-23: a declared account that resolves to no `Participated` knowledge of its actor is a broken package,
    not weak testimony — and it must be REPORTED (V-0), never raise out of the validator."""
    p = pkg("study_party", 4)
    for bad in ("clean@Nobody", f"clean@{p.solution.victim}", "not-a-token", "stay:x:0@" + p.solution.murderer):
        rep = validate(rebuild(p, accounts=p.accounts + (bad,)))
        assert rep.failed_at == "V-0" and any("does not resolve" in x or "dead or offstage" in x for x in rep.problems), bad


def test_B2_an_unreachable_breaker_item_is_rejected_at_V4():
    """Mutation R13, and §20.1 item 2's own wording: a lie the player is expected to detect needs a
    REACHABLE breaker. Gate the innocent's revealing item behind a kit item no case contains and it
    is still derived as the breaker set — but nothing can ever get to it, so V-4 must reject."""
    from eidolon.evidence.model import Prereq
    p = pkg("study_party", 4)
    target = next(e for e in p.evidence if e.id.startswith("E_secret_"))
    gated = target.model_copy(update={"discovery": target.discovery.model_copy(
        update={"prerequisites": target.discovery.prerequisites + (Prereq(kind="HasItem", ref="no-such-item"),)})})
    q = rebuild(p, evidence=[gated if e.id == target.id else e for e in p.evidence])
    assert derive_breaker_sets(next(s for s in q.secrets if s.id == f"S_{target.id.split('_', 2)[2]}"),
                               0, decision_context(q)) == (frozenset({target.id}),)
    rep = validate(q)
    assert rep.failed_at == "V-4"
    assert any("is not on a fully-cued path" in x and target.id in x for x in rep.problems)


def test_B2_cover_synthesis_reads_no_solver_verdict():
    """Requirement 7: synthesis is compilation over the planner's world. `gen/compile.py` must
    not import the solver, and the covers must be identical whatever the solver later says."""
    import ast
    from pathlib import Path
    src = Path("eidolon/gen/compile.py").read_text(encoding="utf-8")
    mods = {(("." * n.level) + (n.module or "")) for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.ImportFrom)}
    assert not [m for m in mods if m.endswith("solver") or m.endswith("proof") or m.endswith("fairness")]
    assert "..solve.package" in mods                  # types only


def _v6_args(p):
    """The arguments V-6's `contract` takes, rebuilt for one package."""
    from eidolon.solve.lattice import admissible
    from eidolon.solve.solver import build_ctx, evaluate, proof_core, robust_material
    ctx = build_ctx(p)
    mat, _c, _r = robust_material(ctx)
    cons = admissible(p.case, ctx.store, mat, ctx.comps, ctx.victim)
    v = evaluate(ctx, mat)
    core = proof_core(ctx, mat)
    return (p, ctx, mat, cons, core, v, {"ok": True, "problems": []}, {"ok": True, "problems": []},
            {"ok": True, "failures": []})


# ================================================================== B-3: the band is a gate
@pytest.mark.parametrize("skel,seed", GOLDEN)
def test_B3_every_sealed_case_is_in_its_declared_band(skel, seed):
    r = golden(skel, seed)
    assert r.report.metrics["bands"] == {k: r.package.difficulty for k in fair.BANDS}
    assert r.report.band_problems == []
    assert r.report.stages["V-6"]["in_band"]


def test_B3_an_out_of_band_case_cannot_seal():
    """The audited defect: 50 of 97 sealed cases were out of band because V-6 only REPORTED the
    band. Relabelling an easy case "hard" must now be rejected, with the numbers in the reason."""
    p = pkg("study_party", 4)
    rep = validate(p.model_copy(update={"difficulty": "hard"}).sealed())
    assert rep.failed_at == "V-6"
    assert any("band: suspects=4" in x for x in rep.problems)
    assert any("proof_core=3" in x for x in rep.problems)


def test_B3_band_violations_names_every_knob_that_misses():
    m = {"suspects": 4, "red_herrings": 1, "proof_core": 3, "min_depth": 0,
         "bands": {"suspects": "easy", "red_herrings": "easy", "proof_core": "easy", "min_depth": "easy"}}
    assert fair.band_violations("easy", m) == []
    assert len(fair.band_violations("standard", m)) == 4
    m2 = {**m, "proof_core": 12, "bands": {**m["bands"], "proof_core": None}}
    assert any("in no band" in x for x in fair.band_violations("easy", m2))


def test_B3_study_party_reaches_the_easy_proof_core_band_by_construction():
    """The audit established the old `study_party` could never reach 3-4. The retune (one
    room-level alibi log, §20.2's proof-core knob) is what changed that — remove it and the
    core grows straight back out of band."""
    assert SKELETONS["study_party"].shared_alibi_log
    r = golden("study_party", 4)
    assert r.report.metrics["proof_core"] in (3, 4)
    plain = SKELETONS["study_party"].__class__(**{**SKELETONS["study_party"].__dict__,
                                                  "shared_alibi_log": False})
    out = generate(plain, 4, **REDUCED)
    assert out.failed_at == "V-6" and any("proof_core" in x for x in out.problems)


def test_B3_generate_in_band_reports_attempts_and_seeds():
    band = generate_in_band("study_party", 4, **REDUCED)
    assert band.ok and band.in_band and band.attempts == 1
    assert band.seeds == [4] and band.rejections == []
    assert band.result.report.metrics["bands"]["proof_core"] == "easy"


def test_B3_the_band_loop_reseeds_and_stops_at_twenty():
    """§20.2: "max 20 attempts; then report". A skeleton whose band it cannot reach must produce
    an actionable report, never a silent seal."""
    hard = SKELETONS["study_party"].__class__(**{**SKELETONS["study_party"].__dict__,
                                                 "difficulty": "hard"})
    band = generate_in_band(hard, 4, max_attempts=3, **REDUCED)
    assert not band.ok and band.attempts == 3 and len(band.seeds) == 3
    assert len(set(band.seeds)) == 3                      # each attempt a DIFFERENT derived seed
    assert all(r["stage"] == "V-6" for r in band.rejections)
    assert MAX_BAND_ATTEMPTS == 20


def test_B3_the_loop_never_reseeds_a_non_band_failure():
    """I-43: a V-5 failure on a realised structure is a skeleton defect, reported, never retried."""
    from tests.solve.helpers import drop_evidence
    import eidolon.gen.pipeline as pipe
    broken = drop_evidence(pkg("study_party", 4), "E_watch")
    calls = []

    def fake_generate(skel, seed, **kw):
        calls.append(seed)
        return pipe.Result(seed, "study_party", "V-5", ["2 living candidates survive"], broken, None, 0.0)

    real, pipe.generate = pipe.generate, fake_generate
    try:
        band = pipe.generate_in_band("study_party", 4, max_attempts=20)
    finally:
        pipe.generate = real
    assert len(calls) == 1 and not band.ok and band.rejections[0]["stage"] == "V-5"


def test_B3_cli_gen_runs_the_band_loop():
    from eidolon.cli import main
    assert main(["gen", "--skeleton", "study_party", "--seed", "4", "--bluffs", "40", "--odd", "40"]) == 0
