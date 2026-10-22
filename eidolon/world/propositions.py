"""The closed proposition schema (§4.7).

Every comparable thing in EIDOLON — facts, claims, evidence implications, hypotheses —
is one of these. The schema is closed by design (§4.7): extending it is an ADR-level
change, so this module holds the whole union and nothing outside it invents a new kind.

`Lied`/`Planted` (hypothesis-only) and `Cause`/`Knows` (generation-only metadata) are
explicitly *not* part of the runtime claim schema (§4.7 notes) and are not modelled here.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, AfterValidator

from .actions import ActionKind
from .ids import ActorId, LocationId, ObjectId
from .interval import Interval as _RawInterval
from .interval import valid as _iv_valid


def _check_interval(iv: _RawInterval) -> _RawInterval:
    if not _iv_valid(iv):
        raise ValueError(f"interval must be non-empty half-open [start, end): {iv}")
    return iv


Interval = Annotated[_RawInterval, AfterValidator(_check_interval)]


class _Prop(BaseModel):
    """Base for every proposition variant: immutable, hashable, structurally comparable."""
    model_config = ConfigDict(frozen=True)


# --- presence -----------------------------------------------------------------
class At(_Prop):
    kind: Literal["At"] = "At"
    actor: ActorId
    location: LocationId
    interval: Interval


class NotAt(_Prop):
    kind: Literal["NotAt"] = "NotAt"
    actor: ActorId
    location: LocationId
    interval: Interval


class Moved(_Prop):
    kind: Literal["Moved"] = "Moved"
    actor: ActorId
    from_loc: LocationId
    to_loc: LocationId
    t: int


# --- action ---------------------------------------------------------------
class Did(_Prop):
    """`action` is the closed `ActionKind` vocabulary (§4.7, ADR-22), not free text: an
    action names either an `EventKind` (assert that kind occurred) or an ENTAILED action
    such as `touch`, which several event kinds imply and forensic evidence cannot tell
    apart. `world/actions.py` owns the vocabulary and the entailment."""
    kind: Literal["Did"] = "Did"
    actor: ActorId
    action: ActionKind
    interval: Interval
    object: ObjectId | None = None
    target_actor: ActorId | None = None
    location: LocationId | None = None


class DidNot(_Prop):
    kind: Literal["DidNot"] = "DidNot"
    actor: ActorId
    action: ActionKind
    interval: Interval
    object: ObjectId | None = None
    target_actor: ActorId | None = None
    location: LocationId | None = None


# --- perception -------------------------------------------------------------
class Saw(_Prop):
    kind: Literal["Saw"] = "Saw"
    observer: ActorId
    subject: str  # ActorId | ObjectId | "figure" | "nobody"
    location: LocationId
    interval: Interval
    identified: bool


class Heard(_Prop):
    kind: Literal["Heard"] = "Heard"
    observer: ActorId
    sound_kind: str
    interval: Interval
    from_location: LocationId | None = None
    identified_actor: ActorId | None = None


# --- objects ------------------------------------------------------------
class Has(_Prop):
    kind: Literal["Has"] = "Has"
    actor: ActorId
    object: ObjectId
    interval: Interval


class ObjectAt(_Prop):
    kind: Literal["ObjectAt"] = "ObjectAt"
    object: ObjectId
    holder: LocationId | ActorId
    interval: Interval


class ObjectState(_Prop):
    kind: Literal["ObjectState"] = "ObjectState"
    object: ObjectId
    attr: str
    value: str
    interval: Interval


# --- attributes / static & time-bounded state -------------------------------
class Attr(_Prop):
    kind: Literal["Attr"] = "Attr"
    entity: str
    attr: str
    value: str


class State(_Prop):
    kind: Literal["State"] = "State"
    actor: ActorId
    attr: str
    value: str
    interval: Interval


# --- relationships / motive ---------------------------------------------------
class Rel(_Prop):
    kind: Literal["Rel"] = "Rel"
    a: ActorId
    b: ActorId
    rel_kind: str
    value: str | None = None


class Attitude(_Prop):
    kind: Literal["Attitude"] = "Attitude"
    a: ActorId
    b: ActorId
    attitude_kind: str
    intensity: float


class Motive(_Prop):
    kind: Literal["Motive"] = "Motive"
    actor: ActorId
    victim: ActorId
    motive_kind: str
    strength: float


# --- reported speech / solution / runtime-only -------------------------------
class Said(_Prop):
    kind: Literal["Said"] = "Said"
    speaker: ActorId
    listener: ActorId
    proposition: "Proposition"
    t: int


class Solution(_Prop):
    kind: Literal["Solution"] = "Solution"
    murderer: ActorId
    method: str
    location: LocationId
    interval: Interval
    motive_kind: str


class Incidental(_Prop):
    """Runtime-only soft claim (§14.4); never a canonical fact — `truth_value` is Unknown."""
    kind: Literal["Incidental"] = "Incidental"
    entity: str
    attr: str
    value: str


Proposition = Annotated[
    Union[
        At, NotAt, Moved, Did, DidNot, Saw, Heard, Has, ObjectAt, ObjectState,
        Attr, State, Rel, Attitude, Motive, Said, Solution, Incidental,
    ],
    Field(discriminator="kind"),
]

Said.model_rebuild()


_ACTOR_SLOTS = ("actor", "observer", "a", "b", "murderer", "victim", "target_actor",
                 "identified_actor", "speaker", "listener")
_LOCATION_SLOTS = ("location", "from_loc", "to_loc", "from_location")
_OBJECT_SLOTS = ("object",)


def entities(prop: Proposition) -> tuple[set[str], set[str], set[str], set[str]]:
    """The `(actors, locations, objects, ambiguous)` a proposition NAMES — the spike's own
    `Prop.entities()` (`spike/model.py`), split by slot kind so a caller can check each
    against the right `Case` table. `ambiguous` holds slots the schema itself types as a
    union (`ObjectAt.holder: LocationId | ActorId`, `Attr.entity`/`Incidental.entity: str`
    over actors and objects alike): the caller accepts them against any table.

    Referential integrity of a proposition is a different question from its truth value:
    `truth_value` answers "does the world make this true", and correctly returns Unknown for
    a predicate the CaseLog does not settle. A proposition naming an entity the world does
    not contain is not Unknown, it is unauthorable — and only a slot-level walk can tell
    the two apart (§4.7's closed schema is what makes the walk total).

    `Saw.subject` stays out entirely: §4.7 lets it be a non-entity literal ("figure",
    "nobody"), so it is not a reference to check. `Said.proposition` recurses.
    """
    actors: set[str] = set()
    locations: set[str] = set()
    objects: set[str] = set()
    ambiguous: set[str] = set()
    for slots, bucket in ((_ACTOR_SLOTS, actors), (_LOCATION_SLOTS, locations),
                           (_OBJECT_SLOTS, objects)):
        for slot in slots:
            value = getattr(prop, slot, None)
            if isinstance(value, str):
                bucket.add(value)
    if prop.kind == "ObjectAt":
        ambiguous.add(prop.holder)          # LocationId | ActorId
    if prop.kind in ("Attr", "Incidental"):
        ambiguous.add(prop.entity)           # actor or object (§4.7 `_tv_Attr` reads both)
    if prop.kind == "Said":
        inner = entities(prop.proposition)
        actors |= inner[0]
        locations |= inner[1]
        objects |= inner[2]
        ambiguous |= inner[3]
    return actors, locations, objects, ambiguous


class Fact(BaseModel):
    """`Fact = (fact_id, proposition, support, load_bearing)` (§4.7)."""
    model_config = ConfigDict(frozen=True)

    id: str
    proposition: Proposition
    support: tuple[str, ...] = ()
    load_bearing: bool = False
