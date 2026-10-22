"""Actors and objects (§4.4).

Everything mental (knowledge/belief/memory/secrets) lives in `minds/` (Phase 2), keyed by
ActorId. This module holds only the static shell.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from .frozen import Frozen, FrozenDict
from .ids import ActorId, LocationId, ObjectId

ActorRole = Literal["victim", "suspect", "witness", "offstage"]


class Actor(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: ActorId
    name: str
    role: ActorRole
    static_attrs: Frozen[str, str] = FrozenDict()


class Object(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: ObjectId
    name: str
    kind: str
    initial_location: LocationId | ActorId
    static_attrs: Frozen[str, str] = FrozenDict()
    traceable: tuple[str, ...] = ()
