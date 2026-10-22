"""§17: `GoTo`/`Search` wiring on top of Phase 3's discovery graph."""
from __future__ import annotations

from eidolon.decision.exploration import (
    ItemTaken, LocationVisited, apply_exploration, go_to, search,
)
from eidolon.evidence.discovery import DiscoveryState
from tests.evidence.fixtures.vance_evidence import evidence_case_items
from eidolon.evidence.model import EvidenceStore

STORE = EvidenceStore(evidence_case_items())


def test_go_to_records_visited_location():
    state = DiscoveryState()
    state = apply_exploration(state, go_to("Parlor", turn=1))
    assert "Parlor" in state.visited_locations
    # idempotent replay:
    state2 = apply_exploration(state, go_to("Parlor", turn=1))
    assert state2.visited_locations == state.visited_locations


def test_search_without_kit_yields_hint_not_discovery():
    state = DiscoveryState()
    result = search(STORE, state, target="Knife", action="Dust", turn=1)
    assert result.discovery is None
    assert result.hint == "You need something you do not have yet for that."      # `kit` is an engine ref, never shown (H8-I1)


def test_a_hint_names_a_place_or_an_object_by_its_display_name_and_nothing_else_by_id():
    from eidolon.evidence.model import DiscoverySpec, Evidence, Prereq
    from eidolon.world.case import Case
    from eidolon.world.entities import Actor, Object
    from eidolon.world.space import Location
    case = Case(id="c", t_investigation=10, actors={"x": Actor(id="x", name="X", role="suspect")},
                locations={"Cellar": Location(id="Cellar", name="the cellar")},
                objects={"Lamp": Object(id="Lamp", name="a brass lamp", kind="lamp", initial_location="Cellar")})
    item = lambda *p: EvidenceStore([Evidence(id="E_hidden", kind="Object", discovery=DiscoverySpec(  # noqa: E731
        action="Look", at="Cellar", prerequisites=tuple(Prereq(kind=k, ref=r) for k, r in p)))])
    said = lambda kind, ref, c=case: search(item((kind, ref)), DiscoveryState(), "Cellar", "Look", 1, c).hint      # noqa: E731
    assert said("KnowsAbout", "Cellar") == "You would need to know about the cellar first."
    assert said("HasItem", "Lamp") == "You need a brass lamp for that."
    assert said("KnowsAbout", "Vault_9") == "You would need to know more about this place first."     # not in the case: generic
    assert said("HasItem", "kit_7") == "You need something you do not have yet for that."
    assert said("StatementHeard", "S00042") == "Someone would have to tell you something first."
    assert said("EvidenceFound", "E_secret_Margaret") == "Something else would have to turn up first."
    assert "E_secret_Margaret" not in said("EvidenceFound", "E_secret_Margaret") and "S00042" not in said("StatementHeard", "S00042")


def test_search_with_kit_discovers():
    state = DiscoveryState(held_items=frozenset({"kit"}))
    result = search(STORE, state, target="Knife", action="Dust", turn=1)
    assert result.discovery is not None
    assert result.discovery.evidence_id == "E_fp"


def test_search_nothing_here():
    state = DiscoveryState()
    result = search(STORE, state, target="Parlor", action="Look", turn=1)
    assert result.discovery is None
    assert result.hint == "Nothing like that here."


def test_item_taken_wiring():
    state = apply_exploration(DiscoveryState(), ItemTaken(item="kit", turn=1))
    assert "kit" in state.held_items
