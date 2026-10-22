"""`solver.unique` (I-21's opportunity-uniqueness primitive) and `pressure.py`'s verbal
pressure / composure update rules (§11.2), incl. I-16's own combination test (T-7)."""
from __future__ import annotations

from eidolon.decision.pressure import PressureFeatures, update_composure, update_verbal_pressure
from eidolon.decision.solver import AdmissibleClaim, unique
from eidolon.minds.character import Personality
from eidolon.minds.provenance import AdmissibilityLevel
from eidolon.world.propositions import At
from tests.world.fixtures.vance import vance_v03

CASE, _ = vance_v03()


def test_unique_excludes_infeasible_candidates():
    # Robert has no admissible material placing him anywhere in vance_v03 (he is not even a
    # character in this layout — use David/Margaret instead). Pin David at the murder scene
    # via an admissible claim that is jointly infeasible with his own OTHER admissible claim
    # placing him elsewhere at the same time.
    murder_loc, murder_iv = "Study", (76, 77)
    admissible = [
        AdmissibleClaim(actor="Margaret", proposition=At(actor="Margaret", location="Library", interval=(70, 80)),
                         level=AdmissibilityLevel.L3),
    ]
    result = unique(["David", "Margaret"], murder_loc, murder_iv, admissible, CASE)
    # Margaret is excluded (Library at t=76 is infeasible with being in the Study at 76-77
    # given no travel time); David has no admissible material at all, so nothing excludes him.
    assert result.unique is True
    assert result.survivors == ("David",)


def test_unique_false_when_multiple_survive():
    result = unique(["David", "Margaret"], "Study", (76, 77), [], CASE)
    assert result.unique is False
    assert set(result.survivors) == {"David", "Margaret"}


def test_t7_pressure_spam_does_not_move_composure_gate_i16():
    """T-7: composure is a function of verbal_pressure (§11.2), so 50 accusations alone must
    never be read by a peel/slip/confession predicate. This test only checks the arithmetic
    module in isolation: composure falls with pressure, but nothing in `peel.py`/slip logic
    ever consumes `CharacterState.composure` — a static/signature fact checked separately in
    `test_static_i29.py`."""
    pressure = 0
    for _ in range(50):
        pressure = update_verbal_pressure(pressure, PressureFeatures(provisional_accusation=True))
    assert pressure == 10000  # capped (VERBAL_PRESSURE_MAX)

    personality = Personality(composure_base=0.5, volatility=0.3, deference=0.5, guile=0.3,
                               talkativeness=0.5, self_preservation=0.5)
    composure = 5000
    composure = update_composure(composure, delta_verbal_bp=10000, delta_weight_bp=0,
                                  personality=personality, calm_turn=False)
    assert composure < 5000  # pressure spam DOES move composure (delivery-only)...
    # ...but composure is never an argument to refutation_weight/evaluate_peel/slip logic —
    # verified structurally in test_static_i29.py.


def test_verbal_pressure_decays_on_calm_turns():
    p = update_verbal_pressure(4000, PressureFeatures(threat=0.0))
    assert p == 3800  # 5% decay, no accusation/hostility/probe
