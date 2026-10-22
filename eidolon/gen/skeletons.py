"""Skeletons (§18.2): the crime MECHANICS and role slots; cast, schedule and evidence are the
planner's. v1 ships two. Both are blunt-force in a private room with one exterior access, so
the `EliminationStructure` (I-43) is declared identically; they differ in layout, cast size and
role mix (the difficulty knob `Suspects`, §20.2: easy = 4, standard = 5-6).

Layout rules every skeleton must satisfy (checked by `tests/gen/test_skeleton.py`):
  * the murder room is `private` (I-48) and never an intermediate node of a route;
  * an EXTERIOR access location exists, is NEVER a waypoint or a stay of any cast member, and is
    the only door between the house and `EXT` — that is what lets its containment device (a
    self-grounding L3 `Saw(nobody)` log, I-47) be canonically true (`FactIndex._tv_Saw`);
  * every non-exterior edge is a 1- or 2-minute edge so the planner's routes stay short.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..solve.package import MethodSpec
from ..world.entities import Object
from ..world.space import EXT, Location, PerceptionEdge, TravelEdge


@dataclass(frozen=True)
class Skeleton:
    id: str
    locations: tuple[Location, ...]
    travel: tuple[TravelEdge, ...]
    perception: tuple[PerceptionEdge, ...]
    murder_loc: str
    hub: str
    exterior: tuple[str, ...]
    roles: tuple[str, ...]                       # one per living cast slot ("housekeeper" | "guest")
    role_weights: dict
    secret_locs: tuple[str, ...]
    sleep_locs: tuple[str, ...]
    victim: tuple[str, str]                      # (name, sex)
    cast: tuple[tuple[str, str], ...]            # (name, sex) per living slot
    weapon: Object
    method: MethodSpec
    motive_menu: tuple[str, ...] = ("inheritance", "jealousy", "blackmail", "revenge")
    T: int = 120
    t_m_range: tuple[int, int] = (40, 90)
    sleep_after: int = 95
    p_pin: float = 0.35
    p_lover: float = 0.5
    p_meeting: float = 0.4
    difficulty: str = "standard"
    chain_depth: int = 0        # §20.2 "min discovery depth": how many prerequisite hops precede the proof core
    shared_alibi_log: bool = False
    """§20.2 `Proof-core size` knob (B-3). True: ONE room-level L3 log covers every innocent, so
    the deletion-minimal proof core is {time pin, containment, that log} — the easy band's 3-4.
    False: each innocent needs their own elimination and the core grows with the cast, which is
    what the standard band's 5-6 wants. Declared per skeleton, confirmed by V-6's band gate."""


def _loc(i, name, **kw):
    return Location(id=i, name=name, **kw)


STUDY_PARTY = Skeleton(
    id="study_party",
    locations=(_loc("Hall", "the hall"), _loc("Study", "the study", private=True), _loc("Library", "the library"),
               _loc("Kitchen", "the kitchen"), _loc("BackSteps", "the back steps"),
               _loc("Gazebo", "the gazebo", exterior=True, entrances_visible=False), _loc("Room", "the guest room"),
               _loc(EXT, "outside", entrances_visible=False)),
    travel=(TravelEdge(a="Hall", b="Study", minutes=1), TravelEdge(a="Hall", b="Library", minutes=1),
            TravelEdge(a="Hall", b="Kitchen", minutes=1), TravelEdge(a="Hall", b="Room", minutes=1),
            TravelEdge(a="Kitchen", b="BackSteps", minutes=1), TravelEdge(a="BackSteps", b="Gazebo", minutes=3),
            TravelEdge(a="Gazebo", b=EXT, minutes=2), TravelEdge(a="Study", b="Gazebo", minutes=2)),
    perception=(PerceptionEdge(observer_at="BackSteps", perceives="Study", modality="sound", quality=0.7),
                PerceptionEdge(observer_at="Kitchen", perceives="Hall", modality="sight", quality=0.5),
                PerceptionEdge(observer_at="Hall", perceives="Study", modality="sound", quality=0.6)),
    murder_loc="Study", hub="Hall", exterior=("Gazebo",),
    roles=("housekeeper", "guest", "guest", "guest"),
    role_weights={"housekeeper": {"Kitchen": 0.6, "Hall": 0.15, "BackSteps": 0.1, "Room": 0.15},
                  "guest": {"Hall": 0.3, "Library": 0.3, "Room": 0.2, "Kitchen": 0.1, "BackSteps": 0.1}},
    secret_locs=("BackSteps", "Room", "Library"), sleep_locs=("Room",),
    victim=("Harold", "M"),
    cast=(("Elena", "F"), ("David", "M"), ("Margaret", "F"), ("Robert", "M")),
    weapon=Object(id="Decanter", name="a crystal decanter", kind="weapon", initial_location="Study",
                  traceable=("fingerprint",)),
    method=MethodSpec(kind="blunt_force", weapon="Decanter"),
    difficulty="easy", shared_alibi_log=True,
)

MANOR_WING = Skeleton(
    id="manor_wing",
    locations=(_loc("Foyer", "the foyer"), _loc("Office", "the office", private=True), _loc("Parlor", "the parlor"),
               _loc("Kitchen", "the kitchen"), _loc("Conservatory", "the conservatory"),
               _loc("Terrace", "the terrace", exterior=True, entrances_visible=False),
               _loc("Suite", "the guest suite"), _loc(EXT, "outside", entrances_visible=False)),
    travel=(TravelEdge(a="Foyer", b="Office", minutes=1), TravelEdge(a="Foyer", b="Parlor", minutes=1),
            TravelEdge(a="Foyer", b="Kitchen", minutes=2), TravelEdge(a="Parlor", b="Conservatory", minutes=1),
            TravelEdge(a="Kitchen", b="Conservatory", minutes=1), TravelEdge(a="Foyer", b="Suite", minutes=1),
            TravelEdge(a="Conservatory", b="Terrace", minutes=2), TravelEdge(a="Office", b="Terrace", minutes=2),
            TravelEdge(a="Terrace", b=EXT, minutes=2)),
    perception=(PerceptionEdge(observer_at="Foyer", perceives="Office", modality="sound", quality=0.6),
                PerceptionEdge(observer_at="Kitchen", perceives="Conservatory", modality="sight", quality=0.5),
                PerceptionEdge(observer_at="Parlor", perceives="Foyer", modality="sight", quality=0.5),
                PerceptionEdge(observer_at="Conservatory", perceives="Office", modality="sound", quality=0.5)),
    murder_loc="Office", hub="Foyer", exterior=("Terrace",),
    roles=("housekeeper", "guest", "guest", "guest", "guest"),
    role_weights={"housekeeper": {"Kitchen": 0.5, "Foyer": 0.2, "Parlor": 0.15, "Suite": 0.15},
                  "guest": {"Foyer": 0.25, "Parlor": 0.3, "Conservatory": 0.2, "Suite": 0.15, "Kitchen": 0.1}},
    secret_locs=("Conservatory", "Suite", "Parlor"), sleep_locs=("Suite",),
    victim=("Alistair", "M"),
    cast=(("Beatrix", "F"), ("Cormac", "M"), ("Delphine", "F"), ("Emeric", "M"), ("Fiora", "F")),
    weapon=Object(id="Paperweight", name="a brass paperweight", kind="weapon", initial_location="Office",
                  traceable=("fingerprint",)),
    method=MethodSpec(kind="blunt_force", weapon="Paperweight"),
    chain_depth=3,
)

SKELETONS = {s.id: s for s in (STUDY_PARTY, MANOR_WING)}
