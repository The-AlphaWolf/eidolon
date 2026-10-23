"""No circular validation (the solver may not consume what the generator declares), and the
fairness / human-solvability layers (V-4, V-6, V-7 proxies) — separate from formal uniqueness."""
import ast
from pathlib import Path

import pytest

from eidolon.solve import fairness as fair
from eidolon.solve.solver import build_ctx, proof_core
from tests.solve.helpers import GOLDEN, edit_evidence, golden, pkg, rebuild, verdict

ROOT = Path(__file__).resolve().parents[2] / "eidolon"


def imports(path: Path) -> set[str]:
    out = set()
    for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(n, ast.ImportFrom):
            out.add(("." * n.level) + (n.module or ""))
        elif isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
    return out


def attr_uses(path: Path, attr: str) -> list[str]:
    """Names of enclosing functions in which `.attr` is read."""
    tree, hits = ast.parse(path.read_text(encoding="utf-8")), []
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        if any(isinstance(n, ast.Attribute) and n.attr == attr for n in ast.walk(fn)):
            hits.append(fn.name)
    return hits


def test_the_solver_package_never_imports_the_generator():
    for f in (ROOT / "solve").glob("*.py"):
        assert not any(m.endswith("gen") or ".gen." in m or m.startswith("..gen") for m in imports(f)), f.name


def test_lower_layers_never_import_solve_or_gen():
    for layer in ("world", "minds", "evidence", "decision", "llm"):
        for f in (ROOT / layer).glob("*.py"):
            bad = [m for m in imports(f) if m.lstrip(".").split(".")[0] in ("solve", "gen")]
            assert not bad, (f, bad)


def test_the_oracle_shares_no_code_with_the_solver_or_the_lattice():
    assert not [m for m in imports(ROOT / "solve" / "oracle.py") if "solver" in m or "lattice" in m]


def test_the_canonical_solution_is_read_in_exactly_one_place():
    for name in ("solver.py", "lattice.py", "fairness.py", "distort.py"):
        uses = attr_uses(ROOT / "solve" / name, "solution")
        assert uses == ([] if name != "solver.py" else ["judge"]), (name, uses)


def test_the_verifier_neither_calls_the_solver_nor_reads_the_solution():
    src = ROOT / "solve" / "proof.py"
    assert "solution" not in {n.attr for n in ast.walk(ast.parse(src.read_text(encoding="utf-8"))) if isinstance(n, ast.Attribute)}
    verify = next(n for n in ast.walk(ast.parse(src.read_text(encoding="utf-8"))) if isinstance(n, ast.FunctionDef) and n.name == "verify_proof")
    called = {n.func.id for n in ast.walk(verify) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert not called & {"solve", "evaluate", "robust_material", "proof_core", "feasible_actor", "actor_core"}


def test_declared_load_bearing_flags_are_not_premises():
    p = pkg("manor_wing", 4)
    scrambled = rebuild(p, evidence=[e.model_copy(update={"load_bearing": not e.load_bearing}) for e in p.evidence])
    assert verdict(scrambled)[2].to_json() == verdict(p)[2].to_json()


# ---- V-4: reachability along cued paths, and testimony that can be asked for -----------------------
@pytest.mark.parametrize("skel,seed", GOLDEN)
def test_v4_proof_core_is_on_a_fully_cued_path(skel, seed):
    r = golden(skel, seed)
    v4 = r.report.stages["V-4"]
    assert v4["ok"] and v4["cued_depth"] <= 5


def test_exterior_access_is_in_the_initial_named_set_I47():
    p = pkg("study_party", 4)
    ctx, mat, _ = verdict(p)
    assert set(e for e, x in p.case.locations.items() if x.exterior) <= fair.named_locations(ctx, mat)


def test_retrieval_expressibility_needs_the_generators_memory_boosts_I39():
    p = pkg("manor_wing", 4)
    ctx, mat, _ = verdict(p)
    core = proof_core(ctx, mat)
    assert any(c.startswith("S:") for c in core) and p.memory_boosts
    assert fair.retrieval_check(p, ctx, core)["ok"]
    # Engine-faithful I-39 (RB-2): the boost is load-bearing for the ACCOUNT behind the murderer's breaker — the
    # housekeeper's recollection of a cleaning is a weak memory — while this case's core atoms are retrievable without it.
    q = pkg("study_party", 4)
    assert fair.engine_retrieval(q, set(), set(q.accounts))["ok"]
    unboosted = q.model_copy(update={"memory_boosts": ()})
    r = fair.engine_retrieval(unboosted, set(), set(unboosted.accounts))
    assert not r["ok"] and r["problems"]                  # without the raise, no query makes her deliver it


def test_an_uncued_or_unreachable_proof_item_fails_v4():
    p = edit_evidence(pkg("manor_wing", 4), "E_watch", discovery=pkg("manor_wing", 4).evidence[1].discovery.model_copy(update={"cue": "never_held"}))
    ctx, mat, _ = verdict(p)
    assert not fair.v4_reachability(p, ctx, mat, proof_core(ctx, mat))["ok"]


# ---- V-6 / V-7 ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("skel,seed", GOLDEN)
def test_v6_fairness_contract_holds_and_the_bluff_proxy_does_not_converge(skel, seed):
    r = golden(skel, seed)
    c = r.report.stages["V-6"]["contract"]
    assert c and all(c.values()), c
    ctx = build_ctx(r.package)
    assert not fair.bluff_converges(ctx)                  # I-40 (material-level): nothing presented, nothing proven


def test_a_lie_without_any_admissible_breaker_is_a_fairness_failure():
    p = pkg("study_party", 4)
    ctx, mat, v = verdict(p)
    from eidolon.solve.lattice import admissible
    admissible(ctx.case, ctx.store, mat, ctx.comps, ctx.victim)
    no_trace = rebuild(p, evidence=[e for e in p.evidence if e.id != "E_trace"])
    ctx2, mat2, v2 = verdict(no_trace)
    cons2 = admissible(ctx2.case, ctx2.store, mat2, ctx2.comps, ctx2.victim)
    core2 = proof_core(ctx2, mat2)
    c = fair.contract(no_trace, ctx2, mat2, cons2, core2, v2, {"ok": True, "problems": []}, {"ok": True, "problems": []}, {"ok": True})
    ok, why = c["2_lies_breakable"]
    assert not ok and any("layer-0 lie" in w for w in why)        # the murderer's "I never touched it" is now unbreakable


def test_absence_fragility_report_is_reported_not_gated():
    f = golden("manor_wing", 4).report.metrics["fragility"]            # recomputed by V-6 from verified cores (ADR-28)
    assert f and all({"rests_on_absence", "absence_sources", "levels"} <= set(v) for v in f.values())


def test_bands_follow_the_section_20_2_table():
    assert (fair.band_of("suspects", 4), fair.band_of("suspects", 5), fair.band_of("suspects", 8)) == ("easy", "standard", "hard")
    assert fair.band_of("suspects", 3) is None and fair.band_of("proof_core", 6) == "standard"
    m = golden("study_party", 4).report.metrics
    assert m["suspects"] == 4 and m["bands"]["suspects"] == "easy" and m["red_herrings"] == 1
