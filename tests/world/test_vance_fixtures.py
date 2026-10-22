"""The Vance House golden case (§29.1, §30 Phase 1 exit criteria).

Cross-checks the production `vance_v03` transcription against `cases/vance_v03.json`
(the Phase 0.5 solver output) and demonstrates the required world-model behaviour end to
end: facts, perception, physics and feasibility together on one real case.
"""
from __future__ import annotations

from eidolon.world.facts import FactIndex
from eidolon.world.perception import derive_perception
from eidolon.world.physics import check_physics
from eidolon.world.propositions import At, Did, NotAt, Rel, State
from tests.world.fixtures.vance import vance_v01_negative, vance_v02_negative, vance_v03


def test_vance_v03_golden_facts():
    """Facts a solved case must expose (§29.1: murder = David attacks Harold in the Study
    at 22:16); each checked against the sealed CaseLog via `FactIndex.truth_value`."""
    case, _ = vance_v03()
    idx = FactIndex(case)

    golden_true = [
        At(actor="David", location="Study", interval=(76, 77)),
        At(actor="Harold", location="Study", interval=(76, 77)),
        Did(actor="David", action="Attack", target_actor="Harold", location="Study", interval=(76, 77)),
        # the `Die` event's own effect completes at its t_end (78); world_at is only
        # in-progress-aware for `ActorAt` (§4.6), so the state reads as changed from 78 on.
        State(actor="Harold", attr="alive", value="false", interval=(78, 79)),
        Did(actor="Elena", action="Clean", object="Glass1", location="Study", interval=(12, 13)),
        At(actor="Robert", location="Gazebo", interval=(50, 65)),
        At(actor="Margaret", location="Room", interval=(85, 112)),
        NotAt(actor="Elena", location="Study", interval=(76, 77)),  # she's in the Kitchen
        Rel(a="Margaret", b="Robert", rel_kind="lover"),
    ]
    golden_false = [
        State(actor="Harold", attr="alive", value="false", interval=(0, 76)),  # alive before the attack
        At(actor="David", location="Library", interval=(76, 77)),  # he's in the Study
        Did(actor="Margaret", action="Attack", target_actor="Harold", location="Study", interval=(76, 77)),
    ]
    for p in golden_true:
        assert idx.truth_value(p) is True, p
    for p in golden_false:
        assert idx.truth_value(p) is False, p


def test_vance_v03_matches_solver_selected_kitchen_corroboration():
    """Cross-check against `cases/vance_v03.json`'s proof core: Robert, Margaret and Elena
    mutually corroborate each other's Kitchen presence over [22:08, 22:24) = [68, 84)."""
    case, _ = vance_v03()
    facts = derive_perception(case)
    window = (68, 84)
    expected = {
        ("Margaret", "Robert"), ("Robert", "Elena"), ("Robert", "Margaret"),
    }
    got = {(f.observer, f.proposition.actor) for f in facts
           if f.proposition.kind == "At" and f.proposition.location == "Kitchen"
           and f.proposition.interval == window and f.source == "CoPresence"}
    assert expected <= got


def test_vance_v03_check_physics_clean():
    """Phase 1 exit criterion: `check_physics(vance_v03)` clean including P-9."""
    case, evidence = vance_v03()
    assert check_physics(case, evidence) == []


def test_vance_v03_no_route_transits_the_study():
    """T-33 / I-48: the Study is private; no route uses it as a waypoint."""
    g = vance_v03()[0].travel_graph
    destinations = [d for d in g.locations if d != "Study"]
    for dest in destinations:
        for origin in destinations:
            if origin == dest:
                continue
            route = g.route(origin, dest, 0)
            if route:
                assert "Study" not in route[1:-1], (origin, dest, route)


def test_negative_fixtures_construct_and_carry_the_documented_defect():
    """Phase 1 only needs to deliver these fixtures (§30); V-5 rejecting them is Phase 6's
    T-17. Here: v01 has no physics defect (its problem is collusion), v02's is P-9/E10."""
    v01, ev01 = vance_v01_negative()
    v02, ev02 = vance_v02_negative()
    assert check_physics(v01, ev01) == []
    v02_violations = check_physics(v02, ev02)
    assert len(v02_violations) == 1 and v02_violations[0].rule == "P-9"


def test_regression_phase_0_5_murder_facts_unchanged():
    """Pins the numbers Phase 0.5 signed off on (`cases/vance_v03.json`): murderer David,
    victim Harold, location Study, t_m=76 (22:16)."""
    case, _ = vance_v03()
    attacks = [e for e in case.events if e.kind == "Attack"]
    assert len(attacks) == 1
    attack = attacks[0]
    assert attack.actor == "David"
    assert attack.participants == ("Harold",)
    assert attack.location == "Study"
    assert attack.interval == (76, 77)
