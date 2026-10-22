"""Exploration and discovery (§17) — the Phase 4 half `evidence/discovery.py` names in its
own scope note: wiring `GoTo`/`Take`/testimony into session events, and `Search(target,
method)` matching a `DiscoverySpec` with a deterministic in-world hint on failure.

Discovery never manufactures evidence (§5.3's own boundary, still true here): `search()` only
ever flips visibility of an item the sealed `EvidenceStore` already contains, and a location
with nothing to find yields a plain "nothing here", never a new object.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..evidence.discovery import Discovery, DiscoveryState, can_discover, unmet_prerequisites
from ..evidence.model import EvidenceStore, Prereq


class LocationVisited(BaseModel):
    """§17: "`GoTo(location)` is free but recorded"."""
    model_config = ConfigDict(frozen=True)

    kind: Literal["LocationVisited"] = "LocationVisited"
    location: str
    turn: int


class ItemTaken(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["ItemTaken"] = "ItemTaken"
    item: str
    turn: int


class StatementHeardEvent(BaseModel):
    """Marks a statement as part of the player's global discovered material — heard either
    directly or quoted from another character (§5.1's `Prereq(kind="StatementHeard")`)."""
    model_config = ConfigDict(frozen=True)

    kind: Literal["StatementHeard"] = "StatementHeard"
    statement_id: str
    turn: int


class AccountHeardEvent(BaseModel):
    """ADR-24: the player heard `token` (`minds.accounts`) in the committed statement `statement_id`."""
    model_config = ConfigDict(frozen=True)

    kind: Literal["AccountHeard"] = "AccountHeard"
    token: str
    statement_id: str
    turn: int


ExplorationEvent = LocationVisited | ItemTaken | StatementHeardEvent


def apply_exploration(state: DiscoveryState, event: ExplorationEvent) -> DiscoveryState:
    """The Phase 4 fold for the three `DiscoveryState` fields Phase 3 left as "plain settable
    fields" pending this wiring (I-22: applies the recorded outcome only)."""
    if isinstance(event, LocationVisited):
        if event.location in state.visited_locations:
            return state
        return state.model_copy(update={"visited_locations": state.visited_locations | {event.location}})
    if isinstance(event, ItemTaken):
        if event.item in state.held_items:
            return state
        return state.model_copy(update={"held_items": state.held_items | {event.item}})
    if isinstance(event, StatementHeardEvent):
        # LEGACY, test-only: the hand-authored Phase 4 fixtures prime `known_statements` through this branch.
        # Nothing under `eidolon/` calls it (an AST test says so); production hearing is `apply_heard`.
        if event.statement_id in state.known_statements:
            return state
        return state.model_copy(update={"known_statements": state.known_statements | {event.statement_id}})
    return state


def apply_heard(state: DiscoveryState, event: StatementHeardEvent | AccountHeardEvent, statements) -> DiscoveryState:
    """The VALIDATING fold for hearing (I-50): a row the ledger does not back is refused, exactly as
    `apply_discovery` refuses a `Discovery` whose prerequisites were never met. The turn runner and replay
    use this and nothing else. `StatementHeard` needs a ledger statement; `AccountHeard` needs the ledger
    statement to LIST the token and to have been spoken by the token's own actor."""
    from ..minds.accounts import parse
    st = statements.get(event.statement_id)
    if st is None:
        raise ValueError(f"{event.kind} names statement {event.statement_id!r}, which is not in the ledger")
    if isinstance(event, StatementHeardEvent):
        return state if event.statement_id in state.known_statements else state.model_copy(
            update={"known_statements": state.known_statements | {event.statement_id}})
    parsed = parse(event.token)
    if parsed is None or parsed[1] != st.speaker:
        raise ValueError(f"AccountHeard {event.token!r}: not an account of {st.speaker!r}")
    if event.token not in st.accounts:
        raise ValueError(f"AccountHeard {event.token!r}: statement {st.id!r} does not deliver it")
    return state if event.token in state.known_accounts else state.model_copy(
        update={"known_accounts": state.known_accounts | {event.token}})


def check_heard_state(state: DiscoveryState, statements) -> list[str]:
    """Soundness of a `DiscoveryState` NOT produced by the fold (the hearing analogue of
    `evidence.discovery.check_discovery_state`): every heard statement must be in the ledger, and every heard account
    must be listed by a ledger statement of that token's own actor. Empty means the hearing could have happened."""
    from ..minds.accounts import parse
    problems = [f"known_statements names {i!r}, which is not in the ledger" for i in sorted(state.known_statements)
                if statements.get(i) is None]
    for t in sorted(state.known_accounts):
        parsed = parse(t)
        if parsed is None or not any(t in st.accounts and st.speaker == parsed[1] for st in statements.all()):
            problems.append(f"known_accounts names {t!r}, which no ledger statement by its actor delivered")
    return problems


def known_locations(case, evidence_store) -> frozenset[str]:
    """Where a player may go: the case's locations plus any place an item's `KnowsAbout` prerequisite names (I-15)."""
    return frozenset(case.locations) | {p.ref for e in evidence_store.all() for p in e.discovery.prerequisites
                                        if p.kind == "KnowsAbout"}


def known_items(case, evidence_store) -> frozenset[str]:
    """What a player may take: the case's objects plus any kit a `HasItem` prerequisite names."""
    return frozenset(case.objects) | {p.ref for e in evidence_store.all() for p in e.discovery.prerequisites
                                      if p.kind == "HasItem"}


def go_to(location: str, turn: int) -> LocationVisited:
    return LocationVisited(location=location, turn=turn)


def _hint(prereqs: tuple[Prereq, ...], case=None) -> str:
    """§5.1's deterministic in-world hint for the first unmet prerequisite. It names only what the player may already
    see: a place or an object by its display name, never an evidence, statement, account or kit id (§22.2 Storage — an id
    is what the engine thinks an item is, and naming an undiscovered one says it exists; H8-I1). A ref the case does not
    name gets the generic line."""
    p = prereqs[0]
    place = getattr(case, "locations", {}).get(p.ref) if p.kind == "KnowsAbout" else None
    kit = getattr(case, "objects", {}).get(p.ref) if p.kind == "HasItem" else None
    return {
        "KnowsAbout": f"You would need to know about {place.name} first." if place else "You would need to know more about this place first.",
        "HasItem": f"You need {kit.name} for that." if kit else "You need something you do not have yet for that.",
        "StatementHeard": "Someone would have to tell you something first.",
        "EvidenceFound": "Something else would have to turn up first.",
    }[p.kind]


@dataclass(frozen=True)
class SearchResult:
    discovery: Discovery | None
    hint: str


def search(store: EvidenceStore, state: DiscoveryState, target: str, action: str, turn: int, case=None) -> SearchResult:
    """§17: "`Search(target, method)` matches `DiscoverySpec`s at the target"; the first
    unmet prerequisite of the first matching, not-yet-found item yields the hint — matching
    `can_discover`'s own single predicate rather than aggregating every candidate's
    prerequisites into one message. `case` supplies the display names a hint may use (H8-I1)."""
    candidates = [e for e in store.all()
                  if e.discovery.at == target and e.discovery.action == action
                  and e.id not in state.known_evidence]
    if not candidates:
        return SearchResult(discovery=None, hint="Nothing like that here.")
    for ev in candidates:
        if can_discover(ev, state):
            return SearchResult(discovery=Discovery(evidence_id=ev.id, turn=turn, action=action, at=target),
                                 hint="")
    return SearchResult(discovery=None, hint=_hint(unmet_prerequisites(candidates[0], state), case))
