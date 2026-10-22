"""Events and their effects (§4.5). The CaseLog is a list of these; everything else in the
canonical world is a pure derivation over them (§4.1)."""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from .actions import EventKind
from .ids import ActorId, EventId, LocationId, ObjectId
from .propositions import Interval, Proposition

__all__ = ["EventKind", "Perceptibility", "Effect", "Event", "EffActorAt", "EffObjectAt",
           "EffObjectState", "EffActorState", "EffTraceCreated", "EffInformationTransferred"]


class Perceptibility(BaseModel):
    model_config = ConfigDict(frozen=True)

    sight: float = 0.0     # 0 = invisible, 1 = unmistakable if in line of sight
    sound: float = 0.0     # 0 = silent, 1 = a shout
    identifies_actor: bool = True
    identifies_voice: bool = True


class _Effect(BaseModel):
    model_config = ConfigDict(frozen=True)


class EffActorAt(_Effect):
    kind: Literal["ActorAt"] = "ActorAt"
    actor: ActorId
    location: LocationId


class EffObjectAt(_Effect):
    kind: Literal["ObjectAt"] = "ObjectAt"
    object: ObjectId
    holder: LocationId | ActorId


class EffObjectState(_Effect):
    kind: Literal["ObjectState"] = "ObjectState"
    object: ObjectId
    attr: str
    value: str


class EffActorState(_Effect):
    kind: Literal["ActorState"] = "ActorState"
    actor: ActorId
    attr: str
    value: str


class EffTraceCreated(_Effect):
    """A forensic trace on an object (§5, P-6). Full `Evidence` promotion is Phase 3; this is
    only the physics-checkable delta: which object now carries which kind of trace."""
    kind: Literal["TraceCreated"] = "TraceCreated"
    object: ObjectId
    trace_kind: str


class EffInformationTransferred(_Effect):
    kind: Literal["InformationTransferred"] = "InformationTransferred"
    from_actor: ActorId
    to_actor: ActorId
    propositions: tuple[Proposition, ...] = ()


Effect = Annotated[
    Union[
        EffActorAt, EffObjectAt, EffObjectState, EffActorState,
        EffTraceCreated, EffInformationTransferred,
    ],
    Field(discriminator="kind"),
]


class Event(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: EventId
    kind: EventKind
    interval: Interval
    location: LocationId
    actor: ActorId | None = None          # primary agent (None for environmental)
    participants: tuple[ActorId, ...] = ()  # co-present agents in the event itself
    objects: tuple[ObjectId, ...] = ()
    effects: tuple[Effect, ...] = ()
    perceptibility: Perceptibility = Perceptibility()
    causes: tuple[EventId, ...] = ()
    intent: str | None = None             # hidden rationale, generation-only metadata
    load_bearing: bool = False            # part of the proof core / solution path
