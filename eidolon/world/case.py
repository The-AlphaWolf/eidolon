"""The canonical Case: the sealed bundle every other subsystem reads (§4.1, §23.1).

Phase 1 builds only the world-model slice of the full `Case` package (§1.2) — actors,
locations, objects, the CaseLog, travel/perception graphs, aliases. Secrets, evidence
discovery, cover stories etc. are later phases' fields and are not modelled here.
"""
from __future__ import annotations

import hashlib
import json
from functools import cached_property

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .alias import Alias, TimeAnchor
from .entities import Actor, Object
from .events import Event
from .frozen import Frozen, FrozenDict
from .ids import ActorId, LocationId, ObjectId
from .propositions import Attitude, Motive, Rel
from .space import Location, PerceptionEdge, TravelEdge, TravelGraph
from .state import death_ticks, ordered_events


class Case(BaseModel):
    """Immutable after construction (I-4): a `Case` is built once from generation output and
    never mutated at runtime. Referential integrity is checked at construction time — an
    event naming an unknown actor/location/object is rejected immediately, not discovered
    later by a validator pass."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    id: str
    t_investigation: int
    actors: Frozen[ActorId, Actor] = Field(default_factory=FrozenDict)
    locations: Frozen[LocationId, Location] = Field(default_factory=FrozenDict)
    objects: Frozen[ObjectId, Object] = Field(default_factory=FrozenDict)
    travel_edges: tuple[TravelEdge, ...] = ()
    perception_edges: tuple[PerceptionEdge, ...] = ()
    events: tuple[Event, ...] = ()
    rels: tuple[Rel, ...] = ()
    attitudes: tuple[Attitude, ...] = ()
    motives: tuple[Motive, ...] = ()
    alias: Alias = Field(default_factory=Alias)
    time_anchor: TimeAnchor | None = None

    @model_validator(mode="after")
    def _check_references(self) -> "Case":
        errors: list[str] = []
        actor_ids, loc_ids, obj_ids = set(self.actors), set(self.locations), set(self.objects)
        for e in self.events:
            if e.location not in loc_ids:
                errors.append(f"{e.id}: unknown location {e.location!r}")
            if e.actor is not None and e.actor not in actor_ids:
                errors.append(f"{e.id}: unknown actor {e.actor!r}")
            for p in e.participants:
                if p not in actor_ids:
                    errors.append(f"{e.id}: unknown participant {p!r}")
            for o in e.objects:
                if o not in obj_ids:
                    errors.append(f"{e.id}: unknown object {o!r}")
            for eff in e.effects:
                for fid, ids in (
                    ("actor", (getattr(eff, "actor", None),)),
                    ("location", (getattr(eff, "location", None),)),
                    ("object", (getattr(eff, "object", None),)),
                ):
                    for v in ids:
                        if v is None:
                            continue
                        pool = {"actor": actor_ids, "location": loc_ids, "object": obj_ids}[fid]
                        if v not in pool and v not in loc_ids and v not in actor_ids:
                            errors.append(f"{e.id}: effect references unknown {fid} {v!r}")
        for te in self.travel_edges:
            if te.a not in loc_ids or te.b not in loc_ids:
                errors.append(f"travel edge references unknown location: {te.a!r}/{te.b!r}")
        for pe in self.perception_edges:
            if pe.observer_at not in loc_ids or pe.perceives not in loc_ids:
                errors.append(f"perception edge references unknown location: {pe.observer_at!r}/{pe.perceives!r}")
        if errors:
            raise ValueError("Case has dangling references:\n" + "\n".join(errors))
        return self

    @cached_property
    def travel_graph(self) -> TravelGraph:
        return TravelGraph(self.locations, list(self.travel_edges))

    def living_actors(self) -> list[ActorId]:
        """Actors who can still be interrogated at `t_investigation`: not offstage, and not
        dead by the CaseLog. The authored `role` filter is kept as well — dropping it would
        widen the pool on a case whose victim has no `Die` event — but the log is what
        actually decides, so a suspect or witness killed mid-evening is now excluded too."""
        dead = death_ticks(self.events)
        return [a for a, act in self.actors.items()
                if act.role not in ("victim", "offstage")
                and dead.get(a, self.t_investigation + 1) > self.t_investigation]

    def content_hash(self) -> str:
        """I-4: content hash of the sealed case, for load-time tamper detection (full
        seal/store machinery is Phase 7 — this is the hash half of that contract).

        The hash is over a CANONICAL rendering, not over `model_dump_json`. Two cases with
        identical content must hash identically or the "verified on load" half of I-4 is a
        coin flip on how the case was built: `model_dump_json` preserves dict insertion
        order and tuple order, and neither is semantic here. §4.1 says the CaseLog is a
        *set* of events (`ordered_events` is its canonical order, the same one every fold
        already imposes for I-5), and the graph/attitude/motive tuples are likewise
        unordered collections. Mapping keys are sorted; every unordered tuple field is
        sorted by its own canonical JSON.

        `alias` stays excluded: it is a rendering table (§4.11), not case content.
        """
        def canonical(value) -> str:
            return json.dumps(value, sort_keys=True, separators=(",", ":"))

        payload = self.model_dump(mode="json", exclude={"alias"})
        payload["events"] = [e.model_dump(mode="json") for e in ordered_events(self.events)]
        for field in ("travel_edges", "perception_edges", "rels", "attitudes", "motives"):
            payload[field] = sorted(payload[field], key=canonical)
        return hashlib.sha256(canonical(payload).encode()).hexdigest()
