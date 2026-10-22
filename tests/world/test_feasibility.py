"""Joint feasibility (§13.2a, I-28). T-15 (transitive alibi cycle) and the pairwise-clean
travel triple — both pairwise-consistent, jointly impossible."""
from __future__ import annotations

from eidolon.world.feasibility import Claim, feasible, feasible_actor
from eidolon.world.propositions import At, Did, NotAt
from tests.world.fixtures.vance import vance_v01_negative

CYCLE = [
    Claim("A1", At(actor="David", location="Gazebo", interval=(60, 80))),
    Claim("A2", At(actor="Margaret", location="Gazebo", interval=(60, 80))),
    Claim("B1", At(actor="Margaret", location="Kitchen", interval=(65, 85))),
    Claim("B2", At(actor="Robert", location="Kitchen", interval=(65, 85))),
    Claim("C1", At(actor="Robert", location="Library", interval=(70, 90))),
    Claim("C2", At(actor="David", location="Library", interval=(70, 90))),
]

TRIPLE = [
    Claim("T1", Did(actor="David", action="Use", object="shelf", location="Library", interval=(60, 64))),
    Claim("T2", Did(actor="David", action="Use", object="tap", location="Kitchen", interval=(60, 64))),
    Claim("T3", Did(actor="David", action="Use", object="drawer", location="Room", interval=(60, 64))),
]


def test_T15_transitive_alibi_cycle_is_pairwise_clean_but_jointly_infeasible():
    case, _ = vance_v01_negative()
    # pairwise: no single pair of claims about the same actor conflicts directly
    for a in ("David", "Margaret", "Robert"):
        mine = [c for c in CYCLE if getattr(c.proposition, "actor", None) == a]
        assert len(mine) == 2
    result = feasible(case, CYCLE)
    assert not result.ok
    assert set(result.core) <= {c.id for c in CYCLE}
    assert result.core  # a minimal conflicting core is reported


def test_pairwise_clean_travel_triple_is_jointly_infeasible():
    """Three existential visits needing two hops each inside a 4-tick window."""
    case, _ = vance_v01_negative()
    result = feasible(case, TRIPLE)
    assert not result.ok
    assert set(result.core) == {"T1", "T2", "T3"}


def test_feasible_single_claim_is_trivially_ok():
    case, _ = vance_v01_negative()
    result = feasible(case, [Claim("X1", At(actor="David", location="Library", interval=(10, 20)))])
    assert result.ok
    assert result.core == ()


def test_feasible_actor_rejects_at_and_notat_on_same_cell():
    case, _ = vance_v01_negative()
    claims = [
        Claim("X1", At(actor="David", location="Library", interval=(10, 20))),
        Claim("X2", NotAt(actor="David", location="Library", interval=(15, 16))),
    ]
    assert not feasible_actor(case, "David", claims)
    result = feasible(case, claims)
    assert not result.ok
    assert set(result.core) == {"X1", "X2"}


def test_feasible_accepts_a_route_that_fits_the_window():
    """David can genuinely reach Kitchen from Library given enough time (contrast with
    the pairwise-clean triple's too-tight window)."""
    case, _ = vance_v01_negative()
    claims = [
        Claim("Y1", Did(actor="David", action="Use", object="shelf", location="Library", interval=(0, 4))),
        Claim("Y2", Did(actor="David", action="Use", object="tap", location="Kitchen", interval=(10, 14))),
    ]
    result = feasible(case, claims)
    assert result.ok
