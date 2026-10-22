"""Negative fixtures required by the architecture (§29.1, §28.7 T-15/T-17/T-18).

vance_v01: the v0.1 golden case — lovers alibi each other (collusion), Elena uncorroborated.
vance_v02: the v0.2 golden case — E9/E10 added; Robert's corridor and the outsider stay open,
           E10 has no temporal grounding (P-9).
transitive cycle (T-15) and a pairwise-clean travel triple: inputs for feasible().

These are HAND-TRANSCRIBED from §29.1 (negative fixtures are hand-authored by definition).
Ticks are minutes after 21:00; 22:10 = 70; t_investigation = 120.
"""
from __future__ import annotations

from .model import Actor, Seg, Event, Evidence, Implication, Secret, Prop, EXT, World
from .minds import Know, Constraint
from .gen import vance_skeleton, empty_world


def _segs(a: str, spec: list[tuple[str, int, int]]) -> list[Seg]:
    return [Seg(loc, s, e, 1.0, f"stay:{a}:{i}") for i, (loc, s, e) in enumerate(spec)]


def vance_world(version: str) -> tuple[World, list[Know]]:
    assert version in ("v01", "v02")
    w = empty_world(vance_skeleton())
    w.meta.update({"hub": "Hall", "fixture": f"vance_{version}_negative", "seed": None})
    for nm, sex, role in [("Harold", "M", "victim"), ("David", "M", "living"), ("Margaret", "F", "living"),
                          ("Robert", "M", "living"), ("Elena", "F", "living")]:
        w.actors[nm] = Actor(nm, nm, role, {"sex": sex})
    w.victim, w.murderer, w.t_m = "Harold", "David", 70
    w.segments = {
        "Harold": _segs("Harold", [("Hall", 0, 5), ("Study", 5, 120)]),
        "Elena": _segs("Elena", [("Hall", 0, 5), ("Kitchen", 5, 65), ("BackSteps", 65, 75), ("Kitchen", 75, 94),
                                 ("Hall", 94, 95), ("Study", 95, 120)]),
        "David": _segs("David", [("Hall", 0, 5), ("Library", 5, 64), ("Hall", 64, 65), ("Kitchen", 65, 67), ("Hall", 67, 68),
                                 ("Study", 68, 73), ("Hall", 73, 74), ("Kitchen", 74, 75), ("Hall", 75, 76), ("Library", 76, 120)]),
        "Margaret": _segs("Margaret", [("Hall", 0, 5), ("Room", 5, 51), ("Hall", 51, 52), ("Kitchen", 52, 53), ("BackSteps", 53, 54),
                                       ("Gazebo", 56, 81), ("BackSteps", 83, 84), ("Kitchen", 84, 85), ("Hall", 85, 86), ("Room", 86, 120)]),
        "Robert": _segs("Robert", [(EXT, 0, 53), ("Gazebo", 54, 81), (EXT, 82, 120)]),
    }
    w.events = [
        Event("attack", "Attack", "David", "Study", 70, None, ("bookend",), sight=1.0, sound=0.8, identifies_voice=True),
        Event("argue", "Speak", "David", "Study", 68, 70, (), sight=1.0, sound=0.8, identifies_voice=True, participants=("Harold",)),
        Event("wash", "Clean", "Elena", "Kitchen", 20, None, ("Glass1",), sight=0.6, sound=0.2),
    ]
    w.secrets = {
        "David": Secret("David", (64, 76), "murder"),
        "Margaret": Secret("Margaret", (51, 86), "affair", ("Robert",)),
        "Robert": Secret("Robert", (54, 82), "affair", ("Margaret",)),
        "Elena": Secret("Elena", (65, 75), "minor_infraction"),
    }
    w.rels = [("Margaret", "Robert", "lover")]
    w.evidence = [
        Evidence("E_scene", "scene", "Study", ("Harold", "Study", "body", "bookend"), []),
        Evidence("E1", "fingerprint", "Kitchen", ("David", "Glass1", "Kitchen"),
                 [Implication(Prop("Did", "David", "Kitchen", (20, 120), ("touch", "Glass1")), requires=("wash@Elena",))],
                 discover_needs=("Glass1",)),
        Evidence("E2", "gloves", "Kitchen", ("gloves", "Kitchen"), []),
        Evidence("E4", "watch", "Study", ("Harold", "watch", "Study"),
                 [Implication(Prop("Died", "Harold", "Study", (70, 71)))], established_iv=(70, 71)),
        Evidence("E5", "shoes", "Room", ("Margaret", "Room", "shoes"), []),
        Evidence("E6", "letter", "Room", ("Robert", "Margaret", "Gazebo"), []),
        Evidence("E7", "ledger", "Study", ("David", "Harold", "ledger"), []),
    ]
    extra = []
    if version == "v01":
        # Robert sees a glow on the back steps: an unidentified figure (v0.1 had no E9)
        extra.append(Know("K_glow", "Robert", Prop("Saw", None, "BackSteps", (65, 75), (False,)), "Witnessed",
                          ("glow@Robert",), "Gazebo", (54, 81), 0.6, 5, 65))
    else:
        w.evidence += [
            Evidence("E9", "butts", "BackSteps", ("Elena", "BackSteps", "butts"),
                     [Implication(Prop("Did", "Elena", "BackSteps", (0, 120), ("smoke", "butts")))], established_iv=(0, 120)),
            # E10 as authored: bolted door observed at t_investigation, used to constrain the whole evening (P-9 violation)
            Evidence("E10", "door", "Study", ("terrace_door", "Study"),
                     [Implication(Prop("ObjectState", None, "Study", (0, 120), ("terrace_door", "bolted", "true")))],
                     established_iv=(120, 121)),
        ]
        # v0.2 grants that E9 + the glow identify the figure as Elena (§29.1): a continuous identified
        # observation, i.e. universal presence at own-presence granularity
        extra.append(Know("K_glow", "Robert", Prop("At", "Elena", "BackSteps", (65, 75)), "Witnessed",
                          ("glow@Robert",), "Gazebo", (54, 81), 0.6, 2, 65))
    return w, extra


def _c(i, kind, actor, loc, iv, extra=()):
    return Constraint(i, i, Prop(kind, actor, loc, iv, extra), 2, ())


def cycle_claims() -> tuple[World, list[Constraint]]:
    """§13.2a transitive alibi cycle: A with B in the Gazebo, B with C in the Kitchen, C with A in the Library."""
    w, _ = vance_world("v01")
    A, B, C = "David", "Margaret", "Robert"
    return w, [_c("A1", "At", A, "Gazebo", (60, 80)), _c("A2", "At", B, "Gazebo", (60, 80)),
               _c("B1", "At", B, "Kitchen", (65, 85)), _c("B2", "At", C, "Kitchen", (65, 85)),
               _c("C1", "At", C, "Library", (70, 90)), _c("C2", "At", A, "Library", (70, 90))]


def triple_claims() -> tuple[World, list[Constraint]]:
    """Pairwise-clean, jointly infeasible: three existential visits that need two hops each inside
    a 4-tick window (Library-Hall-Kitchen-Hall-Room needs ticks 60,62,64)."""
    w, _ = vance_world("v01")
    x = "David"
    return w, [_c("T1", "Did", x, "Library", (60, 64), ("visit", "shelf")),
               _c("T2", "Did", x, "Kitchen", (60, 64), ("visit", "tap")),
               _c("T3", "Did", x, "Room", (60, 64), ("visit", "drawer"))]
