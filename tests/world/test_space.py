from eidolon.world.space import Condition, Location, TravelEdge, TravelGraph


def _graph(private_study=True):
    locs = {
        "Hall": Location(id="Hall", name="Hall"),
        "Study": Location(id="Study", name="Study", private=private_study),
        "Kitchen": Location(id="Kitchen", name="Kitchen"),
    }
    edges = [
        TravelEdge(a="Hall", b="Study", minutes=1),
        TravelEdge(a="Hall", b="Kitchen", minutes=1),
        TravelEdge(a="Study", b="Kitchen", minutes=1),  # shortcut through the private room
    ]
    return TravelGraph(locs, edges)


def test_travel_time_symmetric_and_on_demand():
    g = _graph()
    assert g.travel_time("Hall", "Kitchen", 0) == 1
    assert g.travel_time("Kitchen", "Hall", 0) == 1
    assert g.travel_time("Hall", "Hall", 0) == 0
    assert g.travel_time("Nowhere", "Hall", 0) is None


def test_route_never_transits_a_private_room_but_may_end_there():
    """I-48 / T-33: the Study-Kitchen edge makes Study the shortest Hall<->Kitchen
    waypoint, but a private room may only be a destination."""
    g = _graph(private_study=True)
    assert g.route("Hall", "Kitchen", 0) == ["Hall", "Kitchen"]
    assert "Study" not in g.route("Hall", "Kitchen", 0)
    assert g.route("Hall", "Study", 0) == ["Hall", "Study"]  # destination is fine


def test_route_uses_private_room_as_waypoint_only_when_not_marked_private():
    g = _graph(private_study=False)
    # both are length-2 paths; either is an acceptable shortest route once Study isn't private
    assert g.travel_time("Hall", "Kitchen", 0) == 1  # the direct edge still wins on distance


def test_conditional_edge_gates_travel():
    locs = {"Hall": Location(id="Hall", name="Hall"), "Study": Location(id="Study", name="Study")}
    door = Condition(kind="DoorUnlocked", args=("study_door",))
    edges = [TravelEdge(a="Hall", b="Study", minutes=1, conditions=(door,))]
    g = TravelGraph(locs, edges)

    def locked_until_5(c: Condition, t: int) -> bool:
        return t >= 5

    assert g.travel_time("Hall", "Study", 0, locked_until_5) is None  # door still locked at t=0
    assert g.travel_time("Hall", "Study", 5, locked_until_5) == 1
