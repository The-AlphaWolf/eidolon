"""Generation (§18): determinism across runs, PYTHONHASHSEED values and processes; structural validity
of what the planner emits; and the generation matrix (2 skeletons x seeds) with its funnel."""
import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from eidolon.evidence.grounding import check_evidence_grounding
from eidolon.evidence.model import EvidenceStore
from eidolon.gen import study
from eidolon.gen.compile import compile_draft
from eidolon.gen.pipeline import generate, validate, write_package
from eidolon.gen.planner import plan
from eidolon.gen.skeletons import SKELETONS
from eidolon.minds import accounts
from eidolon.solve.package import CasePackage, SealRefusal, load_sealed_case
from eidolon.solve.proof import verify_proof
from eidolon.world.facts import FactIndex
from eidolon.world.physics import check_physics
from tests.solve.helpers import GOLDEN, REDUCED, golden, loaded, pkg

ROOT = Path(__file__).resolve().parents[2]
SNIPPET = ("from eidolon.gen.planner import plan; from eidolon.gen.compile import compile_draft; "
           "from eidolon.gen.skeletons import SKELETONS; "
           "print(compile_draft(plan(SKELETONS['{sk}'], {seed})).seal)")


def seal_in_subprocess(sk: str, seed: int, hashseed: str) -> str:
    env = {**os.environ, "PYTHONHASHSEED": hashseed}
    r = subprocess.run([sys.executable, "-c", SNIPPET.format(sk=sk, seed=seed)], cwd=ROOT, env=env,
                       capture_output=True, text=True, check=True)
    return r.stdout.strip()


# ---- determinism ---------------------------------------------------------------------------------
@pytest.mark.parametrize("sk", sorted(SKELETONS))
def test_same_seed_same_sealed_package_in_process(sk):
    a, b = compile_draft(plan(SKELETONS[sk], 7)), compile_draft(plan(SKELETONS[sk], 7))
    assert a.seal == b.seal and a.model_dump_json() == b.model_dump_json()
    assert compile_draft(plan(SKELETONS[sk], 8)).seal != a.seal


@pytest.mark.parametrize("sk", sorted(SKELETONS))
def test_same_seed_same_package_across_processes_and_hashseeds(sk):
    seals = {seal_in_subprocess(sk, 7, hs) for hs in ("0", "1", "12345")}
    assert seals == {compile_draft(plan(SKELETONS[sk], 7)).seal}


def test_full_generation_including_distortions_and_boosts_is_process_independent():
    """`generate` adds the bounded distortion selection and the I-39 boosts on top of the plan."""
    code = ("from eidolon.gen.pipeline import generate; r = generate('study_party', 4, bluffs=40, odd=40); print(r.package.seal)")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env={**os.environ, "PYTHONHASHSEED": "777"},
                         capture_output=True, text=True, check=True).stdout.strip()
    assert out == pkg("study_party", 4).seal


def test_no_random_secrets_or_uuid_outside_gen():
    """I-6, checked statically over the whole package (not by convention)."""
    bad = []
    for f in (ROOT / "eidolon").rglob("*.py"):
        if "gen" in f.relative_to(ROOT / "eidolon").parts[:1]:
            continue
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            names = [a.name.split(".")[0] for a in getattr(node, "names", [])] if isinstance(node, ast.Import) else \
                    [node.module.split(".")[0]] if isinstance(node, ast.ImportFrom) and node.module and node.level == 0 else []
            bad += [f"{f.name}: import {n}" for n in names if n in ("random", "secrets", "uuid")]
    assert bad == []


# ---- structure of what the planner emits ----------------------------------------------------------
@pytest.mark.parametrize("skel,seed", GOLDEN)
def test_generated_case_is_structurally_valid(skel, seed):
    p = pkg(skel, seed)
    sk, case, sol = SKELETONS[skel], p.case, p.solution
    assert sum(a.role == "victim" for a in case.actors.values()) == 1                       # valid actor set
    assert {a for a in case.actors if case.actors[a].role != "victim"} == {n for n, _ in sk.cast}
    assert check_physics(case) == []                                                        # timeline + travel
    assert case.locations[sk.murder_loc].private                                            # I-48 murder room
    strangers = [e for e in case.events if e.kind == "Stay" and e.location in sk.exterior]
    assert strangers == []                                                                  # exterior never a stay
    inside = {e.actor for e in case.events if e.kind == "Stay" and e.location == sk.murder_loc}
    assert inside <= {sol.victim, sol.murderer, sol.opportunity_witness}                    # never transited
    attack = next(e for e in case.events if e.id == sol.murder_event)                       # valid murder event
    assert (attack.actor, attack.location, attack.interval, attack.objects) == (sol.murderer, sol.location, sol.interval, (sol.weapon,))
    assert attack.participants == (sol.victim,) and any(e.kind == "Die" and e.interval == sol.interval for e in case.events)
    assert sol.approach[0] <= sol.interval[0] < sol.approach[1]                             # opportunity
    assert check_evidence_grounding(case, EvidenceStore(p.evidence), None, accounts.token_intervals(case)) == []   # grounded
    idx = FactIndex(case)
    assert all(idx.truth_value(pr) is True for s in p.secrets for pr in s.protected)        # secrets have something to hide
    assert len([m for m in case.motives if m.actor in {a for a in case.actors}]) >= 2       # >= 2 plausible motives (§18.3.2)
    assert any(m.actor == sol.murderer for m in case.motives)
    assert {e.red_herring.refuter for e in p.evidence if e.red_herring} <= {e.id for e in p.evidence}


@pytest.mark.parametrize("skel,seed", GOLDEN)
def test_the_declared_elimination_structure_is_what_was_realised(skel, seed):
    """I-43: declared by the skeleton, realised by the planner — and CONFIRMED by the solver, not assumed."""
    p = pkg(skel, seed)
    inn = [a for a in p.case.living_actors() if a != p.solution.murderer]
    assert {a.candidate for a in p.solution.alternatives} == set(inn) | {"Outsider"}
    assert p.structure.opportunity_pin and p.solution.opportunity_witness in inn + [p.solution.murderer]
    assert golden(skel, seed).report.ok


@pytest.mark.parametrize("skel,seed", GOLDEN)
def test_package_serialization_round_trips_and_the_seal_survives(skel, seed):
    p = pkg(skel, seed)
    q = CasePackage.model_validate_json(p.model_dump_json())
    assert q.seal == p.seal and q.verify_seal() and q == p


def test_a_reduced_scale_case_cannot_be_persisted_and_the_committed_golden_loads_through_the_only_reader(tmp_path):
    """I-53/I-58: only a case whose V-7 ran at the architecture's FULL scale seals; `load_sealed_case` is the one reader."""
    r = golden("study_party", 4)                                  # V-7 at a reduced scale: valid, but cannot seal
    with pytest.raises(ValueError, match="full scale"):
        write_package(r, str(tmp_path / "case.json"))
    c = load_sealed_case(str(Path(ROOT / "cases" / "generated" / "study_party_s4.json")))
    assert validate(c.package, **REDUCED).ok and verify_proof(c.package, c.proof) == []


def test_a_seed_whose_structure_cannot_be_realised_is_reported_not_repaired():
    res = [generate("study_party", s, **REDUCED) for s in range(1, 3)]
    for r in res:
        assert r.failed_at is None or (r.failed_at == "planner" and r.problems and r.package is None)


# ---- the generation matrix (§30) ------------------------------------------------------------------
def test_generation_matrix_funnel_is_monotone_and_every_sealed_case_verifies():
    out = study.run(range(1, 7), **REDUCED)
    for sk, row in out["by_skeleton"].items():
        assert row["attempted"] == 6
        counts = list(row["passed_stage"].values())
        assert counts == sorted(counts, reverse=True)                     # a funnel only narrows
        assert row["yield"] >= 0.5, (sk, row["failed_at"], row["example_failures"])
        assert row["sealed"] == counts[-1]
    sealed = [r for r in out["rows"] if r["package"]]
    for sk in SKELETONS:                                   # the study's seal equals a fresh generation's, per skeleton
        r = next(r for r in sealed if r["skeleton"] == sk)
        assert generate(sk, r["seed"], **REDUCED).package.seal == r["package"]


# ---- CLI (`eidolon gen` / `eidolon validate`) -------------------------------------------------------
def test_cli_gen_then_validate_round_trip(tmp_path, capsys):
    from eidolon.cli import main
    out = tmp_path / "c.json"
    assert main(["gen", "--skeleton", "study_party", "--seed", "4", "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["proof"]["unique"] is True
    assert main(["validate", str(out)]) == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    doc["package"]["seed"] += 1                                    # tamper: the seal no longer verifies
    out.write_text(json.dumps(doc), encoding="utf-8")
    assert main(["validate", str(out)]) == 1
    with pytest.raises(SealRefusal):
        load_sealed_case(str(out))
