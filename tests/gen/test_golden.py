"""The golden set is MACHINE-GENERATED (`python -m eidolon.gen.golden`) and independently verified: each file is ONE sealed
bundle `{package, proof, report, bundle_seal}` (I-58) that loads ONLY through `load_sealed_case` — every seal matches, the
independent verifier accepts the proof, and the report records every stage OK at the architecture's FULL V-7 scale —
re-validates through every stage V-0..V-7, and regenerating from (skeleton, seed) reproduces the same seal byte for byte."""
import json
from pathlib import Path

import pytest

from eidolon.gen.golden import GOLDEN
from eidolon.gen.pipeline import generate, validate
from eidolon.solve.package import load_sealed_case
from eidolon.solve.proof import verify_proof

DIR = Path(__file__).resolve().parents[2] / "cases" / "generated"


@pytest.mark.parametrize("sk,seed", GOLDEN)
def test_golden_case_revalidates_and_its_proof_verifies_independently(sk, seed):
    c = load_sealed_case(str(DIR / f"{sk}_s{seed}.json"))
    pkg, proof = c.package, c.proof
    assert pkg.verify_seal() and pkg.seed == seed and pkg.skeleton_id == sk
    assert validate(pkg, bluffs=40, odd=40).ok
    assert verify_proof(pkg, proof) == []
    assert proof["unique"] and proof["survivors"] == [pkg.solution.murderer]
    assert proof["proof_core"] and all(x["level"] >= 2 for x in proof["constraints"])
    assert c.report["stages"]["V-7"]["scale"] == "full"


@pytest.mark.parametrize("sk,seed", GOLDEN[:2])
def test_golden_case_is_reproducible_from_its_seed(sk, seed):
    doc = json.loads((DIR / f"{sk}_s{seed}.json").read_text(encoding="utf-8"))
    assert generate(sk, seed, bluffs=40, odd=40).package.seal == doc["package"]["seal"]


def test_golden_set_has_meaningful_alternatives_and_negatives_derive_from_it():
    c = load_sealed_case(str(DIR / "manor_wing_s4.json"))
    pkg, proof = c.package, c.proof
    excluded = [X for X, e in proof["candidates"].items() if e["excluded"]]
    assert len(excluded) == len(pkg.case.living_actors()) - 1 and all(proof["candidates"][X]["core"] for X in excluded)
    assert proof["outsider"]["excluded"] and proof["outsider"]["blocked"]
    assert pkg.distortions and proof["robustness"]["failures"] == [] and proof["robustness"]["subsets_run"] >= 1
