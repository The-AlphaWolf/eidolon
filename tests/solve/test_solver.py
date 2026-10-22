"""V-5 on generated cases: canonical solution survives, everything else is excluded with a core
that the INDEPENDENT verifier re-checks; declared metadata is never read; order is irrelevant."""
import copy
import random

import pytest

from eidolon.solve.proof import verify_proof
from eidolon.solve.solver import evaluate, judge, proof_core
from tests.solve.helpers import GOLDEN, golden, pkg, shuffled, verdict


@pytest.mark.parametrize("skel,seed", GOLDEN)
def test_canonical_solution_is_the_lone_survivor_and_judged_correct(skel, seed):
    p = pkg(skel, seed)
    _, _, v = verdict(p)
    assert v.unique and v.survivors == [p.solution.murderer] and judge(p, v) == []
    assert v.outsider["excluded"] and len(v.time_bins) == 1


@pytest.mark.parametrize("skel,seed", GOLDEN)
def test_every_other_candidate_is_excluded_with_a_verified_core(skel, seed):
    r = golden(skel, seed)
    proof = r.report.proof
    assert set(proof["candidates"]) == set(r.package.case.living_actors())
    assert all(e["excluded"] and e["core"] for X, e in proof["candidates"].items() if X != r.package.solution.murderer)
    assert verify_proof(r.package, proof) == []


def test_proof_verifier_catches_tampering():
    r = golden("study_party", 4)
    good = r.report.proof
    # 1. a dropped constraint: the core cites something no longer in the proof
    bad = copy.deepcopy(good)
    victim = next(X for X, e in bad["candidates"].items() if e["excluded"])
    cid = bad["candidates"][victim]["core"][0]            # proof/2: a core is a list of constraint ids
    bad["constraints"] = [c for c in bad["constraints"] if c["id"] != cid]
    assert verify_proof(r.package, bad)
    # 2. a false constraint fails the truth audit
    bad = copy.deepcopy(good)
    c = next(c for c in bad["constraints"] if c["kind"] == "At")
    c["loc"] = next(loc for loc in r.package.case.locations if loc != c["loc"])
    # a FALSE constraint is no longer merely audited: the independent derivation never produces it, so it is rejected as
    # inadmissible (ADR-28); the truth audit over the derived set is pinned in test_rb3_verifier.py
    assert any("not admissible at the sealed fairness level" in m or "TRUTH AUDIT" in m for m in verify_proof(r.package, bad))
    # 3. a claim of uniqueness the checked facts do not support
    bad = copy.deepcopy(good)
    bad["candidates"][victim]["excluded"] = False
    bad["candidates"][victim]["times"] = [1]
    bad["survivors"] = sorted(bad["survivors"] + [victim])
    assert verify_proof(r.package, bad)
    # 4. a proof about another package
    assert verify_proof(golden("manor_wing", 4).package, good)


def test_exclusion_cores_are_small_and_minimal():
    r = golden("manor_wing", 4)
    for X, e in r.report.proof["candidates"].items():
        if e["excluded"]:
            assert 1 <= len(e["core"]) <= 3        # minimality itself is asserted by verify_proof(minimal=True)


def test_solver_never_reads_the_declared_solution_or_structure():
    p = pkg()
    base = verdict(p)[2].to_json()
    other = next(a for a in p.case.living_actors() if a != p.solution.murderer)
    lied = p.model_copy(update={"solution": p.solution.model_copy(update={
        "murderer": other, "alternatives": (), "critical_constraints": (), "load_bearing": ("nothing",)}),
        "structure": p.structure.model_copy(update={"alibi_window": 999})})
    assert verdict(lied)[2].to_json() == base            # the solver's answer is untouched...
    assert judge(lied, verdict(lied)[2])                  # ...and judge() now disagrees with the claim


def test_order_of_events_evidence_actors_and_secrets_is_irrelevant():
    p = pkg("manor_wing", 4)
    _, _, base = verdict(p)
    for s in range(3):
        _, _, v = verdict(shuffled(p, random.Random(s)))
        assert (v.survivors, v.unique, v.time_bins, v.outsider["excluded"], v.window) == \
               (base.survivors, base.unique, base.time_bins, base.outsider["excluded"], base.window)


def test_survivor_sets_are_deterministic_across_runs():
    p = pkg()
    assert verdict(p)[2].to_json() == verdict(p)[2].to_json()


def test_proof_core_is_1_minimal_and_sufficient():
    p = pkg("manor_wing", 4)
    ctx, mat, _ = verdict(p)
    core = proof_core(ctx, mat)
    assert evaluate(ctx, {k: mat[k] for k in core}).unique
    for i in core:
        assert not evaluate(ctx, {k: mat[k] for k in core if k != i}, want_cores=False).unique


def test_no_material_at_all_is_not_unique_and_not_a_solution():
    ctx, _, _ = verdict(pkg())
    v = evaluate(ctx, {})
    assert not v.unique and len(v.survivors) > 1
