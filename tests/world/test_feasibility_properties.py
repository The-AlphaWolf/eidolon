"""Property test (§28.3: "random claim sets -> `feasible()` agrees with a brute-force
presence/travel search", I-28). Cross-checks `feasibility.py`'s DP against an independent
gap/travel-time computation on the real Vance travel graph — a different code path from
`physics.py`'s P-2 (which checks events, not claims), so agreement is not a tautology.
"""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from eidolon.world.feasibility import Claim, feasible_actor
from eidolon.world.propositions import At
from tests.world.fixtures.vance import vance_v01_negative

_LOCS = ["Hall", "Study", "Library", "Kitchen", "BackSteps", "Room"]


@given(
    l1=st.sampled_from(_LOCS), l2=st.sampled_from(_LOCS),
    s1=st.integers(0, 40), len1=st.integers(1, 5), gap=st.integers(0, 6), len2=st.integers(1, 5),
)
@settings(max_examples=150, deadline=None)
def test_feasible_actor_agrees_with_independent_travel_gap_check(l1, l2, s1, len1, gap, len2):
    case, _ = vance_v01_negative()
    e1 = s1 + len1
    last_tick = e1 - 1
    s2 = last_tick + gap if l1 != l2 else e1  # same-location claims just need to not overlap
    e2 = s2 + len2
    claims = [Claim("A", At(actor="David", location=l1, interval=(s1, e1))),
              Claim("B", At(actor="David", location=l2, interval=(s2, e2)))]

    if l1 == l2:
        expected = True
    else:
        tt = case.travel_graph.travel_time(l1, l2, last_tick)
        expected = tt is not None and gap >= tt

    assert feasible_actor(case, "David", claims) == expected, (l1, l2, s1, e1, s2, e2, gap)
