"""The Vance House (§29.1). Three fixtures, transcribed into the production
`eidolon.world` model from their Phase 0.5 sources (Phase 1 deliverable, §30):

- `vance_v01_negative` / `vance_v02_negative` — hand-authored, from `spike/fixtures.py`.
  Negative fixtures by definition (§29.1): not unique under the admissibility lattice.
  Phase 1 only needs them to *construct* cleanly and to exercise `check_physics`/P-9
  (V-5 rejection is Phase 6's T-17).
- `vance_v03` — the solver-produced golden case, from `cases/vance_v03.json`.

Ticks are minutes after 21:00 (`t_investigation` = 120 = 23:00).
"""
from __future__ import annotations

from eidolon.world.case import Case
from eidolon.world.entities import Actor, Object
from eidolon.world.events import EffActorAt, EffActorState, EffTraceCreated, Event, Perceptibility
from eidolon.world.physics import Implication
from eidolon.world.propositions import Did, ObjectState, Rel
from eidolon.world.space import EXT, Location, PerceptionEdge, TravelEdge

T_INVESTIGATION = 120

LOCATIONS = {
    "Hall": Location(id="Hall", name="the hall"),
    "Study": Location(id="Study", name="the study", private=True),
    "Library": Location(id="Library", name="the library"),
    "Kitchen": Location(id="Kitchen", name="the kitchen"),
    "BackSteps": Location(id="BackSteps", name="the back steps"),
    "Gazebo": Location(id="Gazebo", name="the gazebo", exterior=True, entrances_visible=False),
    "Room": Location(id="Room", name="Margaret's room"),
    EXT: Location(id=EXT, name="outside", entrances_visible=False),
}

TRAVEL = (
    TravelEdge(a="Hall", b="Study", minutes=1),
    TravelEdge(a="Hall", b="Library", minutes=1),
    TravelEdge(a="Hall", b="Kitchen", minutes=1),
    TravelEdge(a="Hall", b="Room", minutes=1),
    TravelEdge(a="Kitchen", b="BackSteps", minutes=1),
    TravelEdge(a="BackSteps", b="Gazebo", minutes=3),
    TravelEdge(a="Gazebo", b=EXT, minutes=2),
    TravelEdge(a="Study", b="Gazebo", minutes=2),
)

# §29.1: "Gazebo -> Back Steps (sight 0.6 at night only for lit objects - a cigarette
# glow)". The v0.3 skeleton (`spike/gen.py::vance_skeleton`) omitted this edge and
# hand-injected its one resulting knowledge entry instead (a spike shortcut); Phase 1's
# perception model (§4.8 rule 8) derives it from the edge directly (T-30), so the edge
# belongs in the shared perception graph.
PERCEPTION = (
    PerceptionEdge(observer_at="BackSteps", perceives="Study", modality="sound", quality=0.7),
    PerceptionEdge(observer_at="Kitchen", perceives="Hall", modality="sight", quality=0.5),
    PerceptionEdge(observer_at="Hall", perceives="Study", modality="sound", quality=0.6),
    PerceptionEdge(observer_at="Gazebo", perceives="BackSteps", modality="sight", quality=0.6),
)

ACTORS = {
    "Harold": Actor(id="Harold", name="Harold Vance", role="victim", static_attrs={"sex": "M"}),
    "Elena": Actor(id="Elena", name="Elena Ruiz", role="witness", static_attrs={"sex": "F"}),
    "David": Actor(id="David", name="David Kessler", role="suspect", static_attrs={"sex": "M"}),
    "Margaret": Actor(id="Margaret", name="Margaret Vance", role="suspect", static_attrs={"sex": "F"}),
    "Robert": Actor(id="Robert", name="Robert Hale", role="suspect", static_attrs={"sex": "M"}),
}

OBJECTS = {
    "Glass1": Object(id="Glass1", name="a drinking glass", kind="glass", initial_location="Kitchen",
                      traceable=("fingerprint",)),
    "bookend": Object(id="bookend", name="a bronze bookend", kind="weapon", initial_location="Study"),
    "terrace_door": Object(id="terrace_door", name="the terrace door", kind="door", initial_location="Study"),
}

RELS = (Rel(a="Margaret", b="Robert", rel_kind="lover"),)


def _stays(actor: str, spec: list[tuple[str, int, int]]) -> list[Event]:
    return [
        Event(id=f"stay:{actor}:{i}", kind="Stay", interval=(s, e), location=loc, actor=actor,
              effects=(EffActorAt(actor=actor, location=loc),))
        for i, (loc, s, e) in enumerate(spec)
    ]


# --- v01/v02: hand-authored timeline (spike/fixtures.py::vance_world) -----------------
_TIMELINE_V01V02 = {
    "Harold": [("Hall", 0, 5), ("Study", 5, 120)],
    "Elena": [("Hall", 0, 5), ("Kitchen", 5, 65), ("BackSteps", 65, 75), ("Kitchen", 75, 94),
              ("Hall", 94, 95), ("Study", 95, 120)],
    "David": [("Hall", 0, 5), ("Library", 5, 64), ("Hall", 64, 65), ("Kitchen", 65, 67), ("Hall", 67, 68),
              ("Study", 68, 73), ("Hall", 73, 74), ("Kitchen", 74, 75), ("Hall", 75, 76), ("Library", 76, 120)],
    "Margaret": [("Hall", 0, 5), ("Room", 5, 51), ("Hall", 51, 52), ("Kitchen", 52, 53), ("BackSteps", 53, 54),
                 ("Gazebo", 56, 81), ("BackSteps", 83, 84), ("Kitchen", 84, 85), ("Hall", 85, 86), ("Room", 86, 120)],
    "Robert": [(EXT, 0, 53), ("Gazebo", 54, 81), (EXT, 82, 120)],
}


def _v01v02_events() -> tuple[Event, ...]:
    stays: list[Event] = []
    for actor, spec in _TIMELINE_V01V02.items():
        stays += _stays(actor, spec)
    action_events = (
        Event(id="alive0:Harold", kind="Environmental", interval=(0, 1), location="Hall",
              effects=(EffActorState(actor="Harold", attr="alive", value="true"),)),
        Event(id="argue", kind="Speak", interval=(68, 70), location="Study", actor="David",
              participants=("Harold",), perceptibility=Perceptibility(sight=1.0, sound=0.8, identifies_voice=True)),
        Event(id="attack", kind="Attack", interval=(70, 71), location="Study", actor="David",
              participants=("Harold",), objects=("bookend",),
              perceptibility=Perceptibility(sight=1.0, sound=0.8, identifies_voice=True)),
        Event(id="die", kind="Die", interval=(71, 72), location="Study", actor="Harold",
              effects=(EffActorState(actor="Harold", attr="alive", value="false"),)),
        Event(id="wash", kind="Clean", interval=(20, 21), location="Kitchen", actor="Elena",
              objects=("Glass1",), perceptibility=Perceptibility(sight=0.6, sound=0.2)),
        # E1 asserts David used the washed glass. The hand-authored v0.1/v0.2 timeline
        # carried the evidence but never logged the contact it implies, leaving E1 refuted
        # by the world it describes (P-0). David is in the Kitchen 22:05-22:07.
        Event(id="drink", kind="Use", interval=(65, 66), location="Kitchen", actor="David",
              objects=("Glass1",), perceptibility=Perceptibility(sight=0.5, sound=0.1)),
    )
    return tuple(stays) + action_events


def _base_evidence() -> list[tuple[str, Implication]]:
    return [
        ("E1", Implication(Did(actor="David", action="Use", object="Glass1", location="Kitchen",
                                interval=(20, 120)),
                            requires=("wash@Elena",))),
        # Same `Died` transcription as v03's E_watch: the occurrence, not an `alive` state
        # that only holds from the tick after the event completes.
        ("E4", Implication(Did(actor="Harold", action="Die", interval=(71, 72), location="Study"),
                            created_at=(71, 72))),
    ]


def vance_v01_negative() -> tuple[Case, list[tuple[str, Implication]]]:
    """§29.1: the v0.1 golden case. Lovers alibi each other (collusion); Elena
    uncorroborated. Not uniquely solvable (V-5 rejection is Phase 6's T-17)."""
    case = Case(id="vance_v01_negative", t_investigation=T_INVESTIGATION, actors=ACTORS,
                locations=LOCATIONS, objects=OBJECTS, travel_edges=TRAVEL, perception_edges=PERCEPTION,
                events=_v01v02_events(), rels=RELS)
    return case, _base_evidence()


def vance_v02_negative() -> tuple[Case, list[tuple[str, Implication]]]:
    """§29.1: adds E9 (cigarette butts, physically grounded) and E10 (bolted terrace door,
    *not* temporally grounded — P-9/I-30 rejects it, T-16). Still not uniquely solvable
    (open corridor; V-5 rejection is Phase 6's T-17)."""
    # E9 is the cigarette-butt item, and it is v02-only — so are the object it names and the
    # event that grounds it. Neither existed before: E9 named an object the case did not
    # define and an act nobody performed, so the world refuted its own evidence (P-0).
    objects = dict(OBJECTS) | {
        "cigarettes": Object(id="cigarettes", name="cigarette butts", kind="litter",
                              initial_location="BackSteps", traceable=("dna",)),
    }
    smoke = Event(id="smoke", kind="Use", interval=(65, 66), location="BackSteps", actor="Elena",
                  objects=("cigarettes",), perceptibility=Perceptibility(sight=0.4, sound=0.0))
    case = Case(id="vance_v02_negative", t_investigation=T_INVESTIGATION, actors=ACTORS,
                locations=LOCATIONS, objects=objects, travel_edges=TRAVEL, perception_edges=PERCEPTION,
                events=_v01v02_events() + (smoke,), rels=RELS)
    evidence = _base_evidence() + [
        ("E9", Implication(Did(actor="Elena", action="Use", object="cigarettes", location="BackSteps",
                                interval=(0, 120)), created_at=(0, 120))),
        # E10 as authored (§29.1): observed at t_investigation only, asserted over the whole
        # evening with no `requires` — P-9 must reject this.
        ("E10", Implication(ObjectState(object="terrace_door", attr="bolted", value="true", interval=(0, 120)),
                             created_at=(120, 121))),
    ]
    return case, evidence


# --- v03: solver-produced golden case (cases/vance_v03.json) ------------------------
_TIMELINE_V03 = {
    "Harold": [("Hall", 0, 5), ("Study", 5, 120)],
    "Elena": [("Hall", 0, 5), ("Kitchen", 5, 9), ("Hall", 9, 10), ("Study", 10, 18), ("Hall", 18, 48),
              ("Kitchen", 48, 84), ("BackSteps", 84, 93), ("Kitchen", 93, 94), ("Hall", 94, 95), ("Room", 95, 120)],
    "David": [("Hall", 0, 5), ("Kitchen", 5, 34), ("BackSteps", 34, 35), ("Gazebo", 37, 59), ("BackSteps", 61, 72),
              ("Kitchen", 72, 73), ("Hall", 73, 74), ("Study", 74, 77), ("Hall", 77, 98), ("Room", 98, 120)],
    "Margaret": [("Hall", 0, 5), ("Library", 5, 23), ("Hall", 23, 24), ("Kitchen", 24, 25), ("BackSteps", 25, 51),
                 ("Kitchen", 51, 52), ("Hall", 52, 53), ("Library", 53, 67), ("Hall", 67, 68), ("Kitchen", 68, 84),
                 ("Hall", 84, 85), ("Room", 85, 112), ("Hall", 112, 120)],
    "Robert": [("Hall", 0, 5), ("Kitchen", 5, 6), ("BackSteps", 6, 7), ("Gazebo", 9, 15), ("BackSteps", 17, 18),
               ("Kitchen", 18, 19), ("Hall", 19, 20), ("Library", 20, 45), ("Hall", 45, 46), ("Kitchen", 46, 47),
               ("BackSteps", 47, 48), ("Gazebo", 50, 65), ("BackSteps", 67, 68), ("Kitchen", 68, 84), ("Hall", 84, 85),
               ("Room", 85, 115), ("Hall", 115, 116), ("Kitchen", 116, 117), ("BackSteps", 117, 120)],
}

_PERCEPTION_V03 = (
    PerceptionEdge(observer_at="BackSteps", perceives="Study", modality="sound", quality=0.7),
    PerceptionEdge(observer_at="Kitchen", perceives="Hall", modality="sight", quality=0.5),
    PerceptionEdge(observer_at="Hall", perceives="Study", modality="sound", quality=0.6),
)


def vance_v03() -> tuple[Case, list[tuple[str, Implication]]]:
    """The shipping golden case (`cases/vance_v03.json`), solver-selected at the Phase 0.5
    gate. Murder: David attacks Harold in the Study, 22:16-22:17 (t=76-77)."""
    stays: list[Event] = []
    for actor, spec in _TIMELINE_V03.items():
        stays += _stays(actor, spec)
    action_events = (
        Event(id="alive0:Harold", kind="Environmental", interval=(0, 1), location="Hall",
              effects=(EffActorState(actor="Harold", attr="alive", value="true"),)),
        Event(id="argue", kind="Speak", interval=(74, 76), location="Study", actor="David",
              participants=("Harold",), perceptibility=Perceptibility(sight=1.0, sound=0.8, identifies_voice=True)),
        # `EffTraceCreated` on Glass1: §5.2 makes the trace a CONSEQUENCE of the handling
        # ("a fingerprint exists because a Use(glass) event with a TraceCreated effect
        # occurred"), and the validator's job is to verify "that every cause that *should*
        # create a trace did". `Glass1` is declared `traceable=("fingerprint",)` and David
        # handles it bare-handed here, so the effect was missing rather than absent by
        # design — without it the case declares a traceable murder weapon that no event ever
        # marks, and `E_trace`'s fingerprint has no cause anywhere in the CaseLog (P-6).
        # `E_trace` still leaves `created_by` unset: which handling left the mark is exactly
        # what forensics cannot pin down (§13.3), and that is what `requires` grounds.
        Event(id="attack", kind="Attack", interval=(76, 77), location="Study", actor="David",
              participants=("Harold",), objects=("Glass1",),
              effects=(EffTraceCreated(object="Glass1", trace_kind="fingerprint"),),
              perceptibility=Perceptibility(sight=1.0, sound=0.8, identifies_voice=True)),
        # `cases/vance_v03.json` records `t_m = 76` and the single event
        # `Attack David @Study 22:16-22:17`; the death is that moment, which is what its
        # `E_watch` implication `(Died Harold Study [76,77))` pins. An earlier transcription
        # of this fixture put the `Die` event at (77, 78), which made the golden case's own
        # time pin canonically false (P-0). Held at (76, 77) to match the source case.
        Event(id="die", kind="Die", interval=(76, 77), location="Study", actor="Harold",
              effects=(EffActorState(actor="Harold", attr="alive", value="false"),)),
        Event(id="clean", kind="Clean", interval=(12, 13), location="Study", actor="Elena",
              objects=("Glass1",), perceptibility=Perceptibility(sight=0.6, sound=0.2)),
    )
    case = Case(id="vance_v03", t_investigation=T_INVESTIGATION, actors=ACTORS,
                locations=LOCATIONS, objects=OBJECTS, travel_edges=TRAVEL, perception_edges=_PERCEPTION_V03,
                events=tuple(stays) + action_events, rels=RELS)
    evidence = [
        # `(Died Harold Study [76,77))`. The closed schema (§4.7) has no `Died` predicate —
        # §4.9 P-4 models death as the `Die` event kind — so the occurrence is transcribed as
        # `Did(Harold, "Die", ...)`, self-grounded by `created_at` (P-9 clean).
        ("E_watch", Implication(Did(actor="Harold", action="Die", interval=(76, 77), location="Study"),
                                 created_at=(76, 77))),
        # `(Did David Study [12,120) ('touch','Glass1')) requires ['clean@Elena']`, now
        # transcribed verbatim. ADR-22 defines `ActionKind` as `EventKind` plus the entailed
        # action `touch`, so the spike's deliberately-weak contact predicate is expressible
        # without naming the event kind that produced the contact — which is the point: a
        # trace says David handled the glass, not whether he drank from it or hit someone
        # with it. Earlier revisions of this fixture had to write `action="Attack"` here,
        # which over-claimed (it named the murder) and is what ADR-22 removes.
        ("E_trace", Implication(Did(actor="David", action="touch", object="Glass1",
                                     location="Study", interval=(12, 120)),
                                 requires=("clean@Elena",))),
    ]
    return case, evidence
