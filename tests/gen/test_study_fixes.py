"""Seed-study rejection clusters repaired at the planner / compile / boost level (never by relaxing a gate)."""
import pytest

from eidolon.gen.planner import plan
from eidolon.gen.skeletons import SKELETONS
from eidolon.gen.pipeline import generate
from eidolon.gen.study import _bucket
from eidolon.solve.queries import BUCKET
from tests.solve.helpers import REDUCED, pkg


def test_robustness_failures_are_bucketed_as_robustness_not_as_a_proof_defect():
    robust = ["proof does not verify: uniqueness fails when ['M1'] stay uncorrected (survivors [])",
              "proof does not verify: the proof itself records robustness failures",
              "uniqueness fails for 4 of 8 distortion subsets"]
    assert _bucket("V-5", robust) == "V-5:robust"
    assert _bucket("V-5", ["proof does not verify: window differs"] + robust) == "V-5:proof"


@pytest.mark.parametrize("sk", sorted(SKELETONS))
def test_the_housekeepers_secret_never_shares_a_time_bucket_with_the_cleaning(sk):
    """V-4/I-55: `clean@hk` is asked for by time bucket; a bucket that overlaps hk's own protected interval draws a LIE."""
    checked = 0
    for seed in range(1, 40):
        dr = plan(SKELETONS[sk], seed)
        sec = dr.secrets.get(dr.meta.get("hk"))
        if dr.error or sec is None:
            continue
        b0 = (dr.meta["t_c"] + 2) // BUCKET * BUCKET
        assert sec["iv"][0] >= b0 + BUCKET or sec["iv"][1] <= b0, (sk, seed)
        checked += 1
    assert checked > 5


@pytest.mark.parametrize("sk,seed", [("manor_wing", 4), ("study_party", 4)])
def test_a_red_herring_target_has_no_device_pin_of_its_own(sk, seed):
    """§19.6/V-6: a pin would exclude the target without the refuter, so the herring would mislead no one."""
    p = pkg(sk, seed)
    ids = {e.id for e in p.evidence}
    herrings = [e.id.removeprefix("E_secret_") for e in p.evidence if e.red_herring]
    assert herrings and not any(f"E_pin_{a}" in ids for a in herrings)
    assert any(i.startswith("E_pin_") and i != "E_pin_clean" for i in ids) or sk == "study_party"


@pytest.mark.parametrize("sk,seed", [("study_party", 3), ("study_party", 20), ("manor_wing", 3), ("study_party", 36), ("manor_wing", 19), ("manor_wing", 26)])
def test_seeds_the_study_rejected_now_seal(sk, seed):
    """study_party 3: V-7 cue bot never named the alibi room; study_party 20: clean@ shadowed by a LIE; manor_wing 3: V-6
    herring excluded by its own pin; study_party 36: the naming atoms were re-verified with a later, larger name set;
    manor_wing 19/26: hk's secret did not fit at the drawn length once the cleaning bucket was kept clear."""
    assert generate(sk, seed, **REDUCED).failed_at is None


@pytest.mark.parametrize("seed", [19, 26])
def test_the_planner_places_a_housekeepers_secret_that_only_fits_shorter(seed):
    assert plan(SKELETONS["manor_wing"], seed).error is None
