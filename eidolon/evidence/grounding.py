"""Evidence grounding: the boundary that stops Evidence becoming a second source of truth.

Two independent checks, both re-using Phase 1's own `Violation` shape (`world.physics`) so a
caller can merge Phase 1/3 diagnostics into one report without a second type:

- **Creation grounding (P-6).** Every evidence item must trace to something the CaseLog
  actually contains — a `TraceCreated` effect for a forensic trace, a real object/event for
  everything else, and self-consistent `authentic`/`planted_by` flags. This is "evidence
  does not assert facts that cannot be grounded in canonical world state", checked at the
  artifact's ORIGIN rather than its implication.
- **Temporal grounding (P-9/I-30).** An implication whose proposition spans an interval may
  not claim more of that interval than its `requires` chain (plus the always-available
  "discovery observes state at t_investigation" anchor) actually establishes. Phase 1's
  `world.physics._p9` only ever checked the SHALLOW form — "some `requires` is present" —
  because it worked on the physics-only `Implication` stub and said so in its own docstring
  ("the full Evidence model... is Phase 3"). This module resolves the chain for real.

`to_physics_tuples` bridges the full model back to that Phase 1 stub so `check_physics`'s
P-0 (implication truth) and P-1..P-5 keep running unchanged — reuse, not a second engine.
"""
from __future__ import annotations

from ..minds.knowledge import KnowledgeStore
from ..world.case import Case
from ..world.facts import FactIndex
from ..world.ids import EvidenceId
from ..world.interval import contains
from ..world.physics import Implication as PhysicsImplication
from ..world.physics import Violation
from ..world.propositions import Interval, entities
from ..world.state import world_at
from .model import EvidenceStore, Implication

# Trace-bearing kinds: a `TraceCreated` effect is the physical warrant §5.2 requires ("a
# fingerprint exists because a Use(glass) event with a TraceCreated effect occurred"). Other
# kinds (Document, Object, Witness, Digital, Timepiece) may pre-exist or be authored without
# a trace effect — a document's existence needs no forensic act on it.
_TRACE_KINDS = frozenset({"Fingerprint", "Bloodstain", "Footprint"})


def check_reference_integrity(case: Case, store: EvidenceStore) -> list[Violation]:
    """P-6: every entity an implication NAMES must exist in the canonical world.

    Distinct from `check_world_truth` (P-0), which asks whether the world makes the
    proposition true. `truth_value` answers Unknown for anything the CaseLog does not
    settle — an attribute never defined, an object no event ever moved — and that Unknown is
    correct: the world genuinely has no opinion. But it is the same answer the world gives
    for an entity it has never heard of, so P-0 alone cannot tell "not settled" from
    "not real", and an implication naming a nonexistent actor, room or object passed the
    whole gate. `propositions.entities` walks the closed schema slot by slot instead
    (PRESENT IN WORLD, checked before GROUNDED).

    Applies to planted evidence too: a forged item is designed to be FALSE, never to be
    about things that do not exist (§5.2) — its `Plant` event had to handle real objects in
    a real room.
    """
    v: list[Violation] = []
    known_any = set(case.actors) | set(case.locations) | set(case.objects)
    for ev in store.all():
        for imp in ev.implications:
            actors, locations, objects, ambiguous = entities(imp.proposition)
            for name, pool, table in ((actors, case.actors, "actor"),
                                       (locations, case.locations, "location"),
                                       (objects, case.objects, "object")):
                for ref in sorted(name - set(pool)):
                    v.append(Violation("P-6", f"{ev.id}: implication names unknown {table} "
                                               f"{ref!r} ({imp.proposition.kind})"))
            for ref in sorted(ambiguous - known_any):
                v.append(Violation("P-6", f"{ev.id}: implication names unknown entity {ref!r} "
                                           f"({imp.proposition.kind})"))
    return v


def check_creation_grounding(case: Case, store: EvidenceStore) -> list[Violation]:
    """P-6: every evidence item traces to something the CaseLog actually contains."""
    v: list[Violation] = []
    events_by_id = {e.id: e for e in case.events}
    world_now = world_at(case.events, case.t_investigation)
    traced_objects = {eff.object for e in case.events for eff in e.effects
                       if eff.kind == "TraceCreated"}

    for ev in store.all():
        if ev.object is not None and ev.object not in case.objects:
            v.append(Violation("P-6", f"{ev.id}: references unknown object {ev.object!r}"))
        if (ev.location_at_investigation is not None
                and ev.location_at_investigation not in case.locations
                and ev.location_at_investigation not in case.objects):
            v.append(Violation("P-6", f"{ev.id}: location_at_investigation "
                                       f"{ev.location_at_investigation!r} is neither a known "
                                       f"location nor object"))
        # §5.1 types `DiscoverySpec.at` as `LocationId | ObjectId`, and §17 has `Search`
        # match specs "at the target" — so `at` names a place in the world the player can
        # stand in or a thing they can handle. An `at` that resolves to neither is not a
        # discovery site at all, and V-4 would otherwise report the item reachable from an
        # address the world does not contain (the syntactically-valid-but-nonexistent case).
        if (ev.discovery.at not in case.locations and ev.discovery.at not in case.objects):
            v.append(Violation("P-6", f"{ev.id}: discovery.at {ev.discovery.at!r} is neither a "
                                       f"known location nor a known object"))
        if ev.object is not None and ev.location_at_investigation is not None:
            # `object_at` only has an entry once some event MOVES the object (an
            # `EffObjectAt` effect, §4.6); an object nobody ever touches is still placed —
            # at its authored `Object.initial_location` — so that is the fallback the world
            # actually commits to, not "no opinion".
            actual = world_now.object_at.get(ev.object, case.objects[ev.object].initial_location
                                              if ev.object in case.objects else None)
            if actual is not None and actual != ev.location_at_investigation:
                v.append(Violation("P-6", f"{ev.id}: location_at_investigation "
                                           f"{ev.location_at_investigation!r} != canonical "
                                           f"{actual!r} at t_investigation"))

        if ev.created_by is not None:
            event = events_by_id.get(ev.created_by)
            if event is None:
                v.append(Violation("P-6", f"{ev.id}: created_by references unknown event {ev.created_by!r}"))
            else:
                if event.interval[0] > case.t_investigation:
                    v.append(Violation("P-6", f"{ev.id}: created_by {event.id} occurs at "
                                               f"{event.interval} — after t_investigation "
                                               f"({case.t_investigation}), not yet discoverable"))
                if ev.object is not None and ev.object not in event.objects:
                    v.append(Violation("P-6", f"{ev.id}: creating event {event.id} does not "
                                               f"name object {ev.object!r}"))
                if ev.kind in _TRACE_KINDS and ev.object is not None:
                    has_trace = any(eff.kind == "TraceCreated" and eff.object == ev.object
                                     for eff in event.effects)
                    if not has_trace:
                        v.append(Violation("P-6", f"{ev.id}: no TraceCreated effect on "
                                                   f"{event.id} for {ev.object!r}"))
        elif ev.kind in _TRACE_KINDS and ev.object is not None and ev.object not in traced_objects:
            # §5.2: "the validator can verify that no evidence exists without a cause (P-6)".
            # Leaving `created_by` unset is legitimate — forensics under-determine WHICH
            # handling left a mark, which is exactly why `requires` exists (§5.1) — but it
            # cannot also excuse the item from having a cause at all, or the rule policed
            # only the items that volunteered one. The unpinned form is therefore the weaker
            # claim, not no claim: SOME event in the log must have marked this object.
            v.append(Violation("P-6", f"{ev.id}: {ev.kind} on {ev.object!r} with no "
                                       f"created_by and no TraceCreated effect anywhere in "
                                       f"the CaseLog (evidence without a cause)"))

        for actor, event_id in ev.interacted:
            event = events_by_id.get(event_id)
            if event is None:
                v.append(Violation("P-6", f"{ev.id}: interacted references unknown event {event_id!r}"))
            elif actor != event.actor and actor not in event.participants:
                v.append(Violation("P-6", f"{ev.id}: interacted claims {actor} at {event_id} "
                                           f"but they were not actor or participant"))

        if ev.authentic and ev.planted_by is not None:
            v.append(Violation("P-6", f"{ev.id}: authentic evidence must not carry planted_by "
                                       f"(authentic/planted_by are inconsistent)"))
        if not ev.authentic:
            if ev.planted_by is None:
                v.append(Violation("P-6", f"{ev.id}: planted evidence (authentic=False) needs planted_by"))
            else:
                plant_event = events_by_id.get(ev.planted_by)
                if plant_event is None:
                    v.append(Violation("P-6", f"{ev.id}: planted_by references unknown event {ev.planted_by!r}"))
                elif plant_event.kind != "Plant":
                    v.append(Violation("P-6", f"{ev.id}: planted_by {ev.planted_by!r} is a "
                                               f"{plant_event.kind} event, not Plant"))
    return v


def _grounding_events(ev) -> set[str]:
    """The CaseLog events an item's own existence traces to (§5.1's provenance fields)."""
    return {e for e in (ev.created_by, ev.planted_by) if e is not None} | {e for _, e in ev.interacted}


def _entry_event_ids(entry) -> set[str]:
    """Whichever event id this provenance variant carries (§6.2's closed union)."""
    return {getattr(entry.source, slot) for slot in ("event_id", "speak_event_id", "read_event_id")
            if getattr(entry.source, slot, None) is not None}


def check_known_to_soundness(store: EvidenceStore, knowledge: KnowledgeStore,
                              case: Case | None = None) -> list[Violation]:
    """§5.1's `known_to`: "characters aware it exists (pre-discovery)". Four checks.

    Referential (unchanged): the entry exists and belongs to the named actor. Then the two
    the audit found missing, both of which separate KNOWN BY CHARACTER from the mere fact
    that an id parses:

    - **The actor is real** and appears in the case at all.
    - **The entry is about THIS item.** Any entry of that actor's used to satisfy the field,
      so awareness was bound to a person rather than to a thing. A sound binding grounds in
      something the item itself traces to: the entry's provenance names one of the item's
      own events (`created_by`/`planted_by`/`interacted`), or its proposition names the
      item's object. Without this a `known_to` sealed at generation silently REBINDS to an
      unrelated proposition the moment knowledge ids shift — `propagate_knowledge` numbers
      entries positionally (`K%04d`), so inserting one event renumbers every later entry and
      the referential check alone would still pass.

    `case` is optional so the existing two-argument call keeps working; the actor check runs
    only when it is supplied.
    """
    v: list[Violation] = []
    for ev in store.all():
        grounding_events = _grounding_events(ev)
        for actor, entry_id in ev.known_to.items():
            if case is not None and actor not in case.actors:
                v.append(Violation("P-6", f"{ev.id}: known_to names unknown actor {actor!r}"))
            entry = knowledge.get(entry_id)
            if entry is None:
                v.append(Violation("P-6", f"{ev.id}: known_to[{actor}] references unknown "
                                           f"KnowledgeEntry {entry_id!r}"))
                continue
            if entry.character != actor:
                v.append(Violation("P-6", f"{ev.id}: known_to claims {actor} but "
                                           f"{entry_id} belongs to {entry.character}"))
                continue
            _, _, objects, ambiguous = entities(entry.proposition)
            about_object = ev.object is not None and ev.object in (objects | ambiguous)
            if not (about_object or (_entry_event_ids(entry) & grounding_events)):
                v.append(Violation("P-6", f"{ev.id}: known_to[{actor}] = {entry_id} is not "
                                           f"about this item — its provenance names none of "
                                           f"{sorted(grounding_events) or '[]'} and its "
                                           f"proposition does not name {ev.object!r}"))
    return v


def check_world_truth(case: Case, store: EvidenceStore) -> list[Violation]:
    """P-0, restricted to AUTHENTIC evidence: an authentic item's implication being refuted
    by the canonical world is an authoring error (`world.physics._implication_truth`'s own
    reasoning). A PLANTED item is deliberately world-false — that is what makes it
    misleading (§5.2) — so it is exempt here; `evidence_vs_evidence`/V-5 are where a planted
    item's tension with genuine material is judged, not this gate."""
    index = FactIndex(case)
    v: list[Violation] = []
    for ev in store.all():
        if not ev.authentic:
            continue
        for imp in ev.implications:
            if index.truth_value(imp.proposition) is False:
                v.append(Violation("P-0", f"{ev.id}: implication is contradicted by the "
                                           f"canonical world: {imp.proposition}"))
    return v


def established_interval(imp: Implication, store: EvidenceStore, t_investigation: int,
                          statement_intervals: dict[str, Interval] | None = None,
                          self_created_at: Interval | None = None) -> Interval:
    """I-30's `established_interval(requires ∪ {created_at})`, plus the anchor P-9's own
    prose always grants: "discovery observes state at t_investigation", so a bare item with
    no `requires` and no `created_at` is still grounded — at exactly the single tick of
    discovery, never wider. This is why an ungrounded claim like E10 (§29.1, "a bolted door
    observed at t_investigation with no requires") is rejected but never crashes: the
    returned interval is always valid, just too narrow to contain a wide claim.

    Each entry in `requires` contributes the interval IT establishes: another `Evidence`'s
    own `created_at` (its creation moment — e.g. "washed at 21:20" bounds when a print could
    first have been left), or — for a `StatementId` the `Statement` model does not exist yet
    to supply (Phase 4 forward reference, same pattern as `Distortion.correctable_by`) — a
    caller-supplied entry in `statement_intervals`. The result is the convex hull (earliest
    start, latest end) of every resolved contribution: a hull, not a literal set union, is
    what makes "clean at [12,13) + discovery at [120,121)" establish the single connected
    window [12,121) that the architecture's own E1 example needs (§13.3, §29.1).
    """
    stmt = statement_intervals or {}
    parts: list[Interval] = [(t_investigation, t_investigation + 1)]
    if self_created_at is not None:
        parts.append(self_created_at)
    for req in imp.requires:
        req_ev = store.get(req)
        if req_ev is not None:
            if req_ev.created_at is not None:
                parts.append(req_ev.created_at)
        elif req in stmt:
            parts.append(stmt[req])
    return (min(p[0] for p in parts), max(p[1] for p in parts))


def check_temporal_grounding(case: Case, store: EvidenceStore,
                              statement_intervals: dict[str, Interval] | None = None) -> list[Violation]:
    """The DEEP P-9/I-30 check (see module docstring): resolves every `requires` reference
    for real, instead of Phase 1's "any non-empty `requires` passes" stub."""
    v: list[Violation] = []
    for ev in store.all():
        for imp in ev.implications:
            # Referential integrity of `requires` is checked for EVERY implication, not only
            # the interval-bearing ones. This loop used to sit below the `interval is None`
            # guard, so an implication over an interval-free proposition (`Attr`, `Rel`,
            # `Motive`, `Moved`, `Incidental`) could name a `requires` id that resolves to
            # nothing at all and pass clean — forged provenance, and a permanently
            # unlockable implication (`unlocked_implications` gates on the same ids).
            for req in imp.requires:
                if store.get(req) is None and req not in (statement_intervals or {}):
                    v.append(Violation("P-9", f"{ev.id}: requires unresolved reference {req!r} "
                                               f"(forged or dangling provenance)"))
            interval = getattr(imp.proposition, "interval", None)
            if interval is None:
                continue
            hull = established_interval(imp, store, case.t_investigation, statement_intervals, ev.created_at)
            if not contains(hull, interval):
                v.append(Violation("P-9", f"{ev.id}: implication spans {interval}, which "
                                           f"exceeds established {hull} (I-30)"))
    return v


def check_evidence_grounding(case: Case, store: EvidenceStore, knowledge: KnowledgeStore | None = None,
                              statement_intervals: dict[str, Interval] | None = None) -> list[Violation]:
    """The full Phase 3 grounding gate: P-6 (creation), P-0 restricted to authentic items,
    and the deep P-9. `knowledge` is optional — omit it to skip the `known_to` check when no
    `KnowledgeStore` is at hand (e.g. a case with no characters wired up yet)."""
    v = check_reference_integrity(case, store)
    v += check_creation_grounding(case, store)
    v += check_world_truth(case, store)
    v += check_temporal_grounding(case, store, statement_intervals)
    if knowledge is not None:
        v += check_known_to_soundness(store, knowledge, case)
    return v


def to_physics_tuples(store: EvidenceStore) -> list[tuple[EvidenceId, PhysicsImplication]]:
    """Bridges the full model back to `world.physics.Implication` so `check_physics`'s
    P-0/P-1..P-5 (and its own shallow P-9) keep running unchanged over the same data — reuse
    of tested Phase 1 machinery rather than a second implementation of the same rules."""
    out: list[tuple[EvidenceId, PhysicsImplication]] = []
    for ev in store.all():
        for imp in ev.implications:
            out.append((ev.id, PhysicsImplication(imp.proposition, requires=imp.requires,
                                                    created_at=ev.created_at)))
    return out
