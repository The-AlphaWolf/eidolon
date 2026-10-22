"""Discovery (§5.3, §17, V-4 §19.4): the player's access path to `Evidence`, and its
reachability. Discovery never manufactures evidence — it only flips visibility of items the
generation-time `EvidenceStore` already contains in full (the boundary's own line: "Discovery
must not create evidence out of thin air").

Scope note: §17's `GoTo`/`Search` player ACTIONS and their session-log wiring are a Phase 4
deliverable ("exploration actions", roadmap §30). This module owns the Phase 3 half — the
`DiscoverySpec`/`Prereq` model, whether a prerequisite is met, the `Discovery` event itself
(§5.3 names it explicitly as this phase's), and the V-4 reachability graph — and exposes
`DiscoveryState`'s other membership sets (`visited_locations`, `held_items`,
`known_statements`) as plain settable fields rather than inventing session-event kinds for
actions this phase does not implement; Phase 4 wires those to `GoTo`/`Take`/testimony events.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict

from ..minds.epistemic import EpistemicState
from ..minds.memory import RETRIEVE_STRONG, CueSet, Memory, score
from ..world.ids import EvidenceId
from ..world.propositions import Proposition
from .model import Evidence, EvidenceKind, EvidenceStore, Prereq


class DiscoveryState(BaseModel):
    """The per-game runtime overlay for what has been found — mirrors `EpistemicState`'s
    role (§6.3): the sealed `EvidenceStore` never mutates (I-4); this is the fold-derived
    record of what discovery has unlocked so far."""
    model_config = ConfigDict(frozen=True)

    known_evidence: frozenset[EvidenceId] = frozenset()
    known_statements: frozenset[str] = frozenset()
    known_accounts: frozenset[str] = frozenset()
    """ADR-24: account tokens (`<event>@<actor>`, `minds.accounts`) the player has HEARD — minted only by the
    stage-10 commit of a turn whose committed claim faithfully delivered the speaker's own `Participated`
    knowledge (I-50). Never seeded, never presentable (I-51)."""
    visited_locations: frozenset[str] = frozenset()
    held_items: frozenset[str] = frozenset()


class Discovery(BaseModel):
    """§5.3: "a SessionLog event `{evidence_id, turn, action, at}`"."""
    model_config = ConfigDict(frozen=True)

    kind: Literal["Discovery"] = "Discovery"
    evidence_id: EvidenceId
    turn: int
    action: Literal["Look", "Open", "Dust", "Read", "Search", "Ask"]
    at: str


def _prereq_met(p: Prereq, state: DiscoveryState) -> bool:
    if p.kind == "KnowsAbout":
        return p.ref in state.visited_locations
    if p.kind == "HasItem":
        return p.ref in state.held_items
    if p.kind == "StatementHeard":
        return p.ref in state.known_statements or p.ref in state.known_accounts
    if p.kind == "EvidenceFound":
        return p.ref in state.known_evidence
    return False  # unreachable: `Prereq.kind` is a closed Literal


def can_discover(evidence: Evidence, state: DiscoveryState) -> bool:
    """§5.1: "each unmet prerequisite yields a deterministic in-world hint" — this is the
    predicate that decision is made from; the hint text itself is a Phase 4/UI concern."""
    return all(_prereq_met(p, state) for p in evidence.discovery.prerequisites)


def unmet_prerequisites(evidence: Evidence, state: DiscoveryState) -> tuple[Prereq, ...]:
    """The `Prereq`s `can_discover` found unmet — what `decision.exploration`'s `Search`
    handler (§17) renders into the deterministic in-world hint text can_discover's own
    docstring defers to a later phase."""
    return tuple(p for p in evidence.discovery.prerequisites if not _prereq_met(p, state))


def apply_discovery(state: DiscoveryState, event: Discovery, store: EvidenceStore) -> DiscoveryState:
    """The Phase 3 slice of the I-22 fold: applies the recorded outcome only.

    Re-checking `can_discover` here is not "re-deriving a scored decision" (which I-22
    forbids) — it is the same structural-impossibility gate `knowledge.propagate_knowledge`
    applies to `Told` (I-8: a listener not present cannot have heard it). A `Discovery` row
    whose prerequisites were never met is impossible provenance, and replaying it must fail
    the same way loading a tampered log does (I-15: fail closed), not silently grant access.
    Re-discovering an already-known item is an explicit no-op (idempotent replay, I-5).

    The event's `action` and `at` are checked against the item's own `DiscoverySpec`, not
    just carried: §17 has `Search(target, method)` "match `DiscoverySpec`s at the target",
    so a row naming a different method or a different place did not describe a discovery
    this item admits. Unvalidated, both fields were decorative — a forensic trace gated on
    `Dust` at the knife could be folded in with `Look` at any address at all, which is
    DISCOVERABLE collapsed into DISCOVERED."""
    ev = store.get(event.evidence_id)
    if ev is None:
        raise ValueError(f"Discovery of unknown evidence id {event.evidence_id!r}")
    if event.evidence_id in state.known_evidence:
        return state
    if event.action != ev.discovery.action:
        raise ValueError(f"Discovery of {event.evidence_id!r} by {event.action!r}, but its "
                          f"DiscoverySpec requires {ev.discovery.action!r}")
    if event.at != ev.discovery.at:
        raise ValueError(f"Discovery of {event.evidence_id!r} at {event.at!r}, but it is "
                          f"found at {ev.discovery.at!r}")
    if not can_discover(ev, state):
        raise ValueError(f"Discovery of {event.evidence_id!r} attempted with unmet prerequisites")
    return state.model_copy(update={"known_evidence": state.known_evidence | {event.evidence_id}})


def check_discovery_state(state: DiscoveryState, store: EvidenceStore) -> list[str]:
    """Soundness of a `DiscoveryState` that was NOT produced by the fold.

    `apply_discovery` is the only path that validates, but a `DiscoveryState` is an ordinary
    pydantic model and can be constructed with any `known_evidence` at all — including ids
    no store contains. Every downstream reader (`unlocked_implications`,
    `project_for_player`, `_prereq_met`) trusts that set, so a forged one is a free pass to
    unlocked implications and player-visible text.

    Phase 2 answers exactly this question for hand-built knowledge with `minds.soundness`
    ("catching a `KnowledgeEntry` that was hand-constructed or corrupted... without
    re-deriving the whole model"); this is the same check one layer up. Returns the reasons
    the state could not have been reached by any legal discovery order — empty means sound.

    Order-independent by construction: a set is reachable iff repeatedly admitting every
    member whose prerequisites are already admitted exhausts it (the same fixpoint
    `reachability` uses), so no particular sequence has to be guessed.
    """
    problems = [f"unknown evidence id {i!r}" for i in sorted(state.known_evidence) if store.get(i) is None]
    admitted: frozenset[EvidenceId] = frozenset()
    pending = {i for i in state.known_evidence if store.get(i) is not None}
    while True:
        probe = state.model_copy(update={"known_evidence": admitted})
        newly = {i for i in pending if can_discover(store.get(i), probe)}
        if not newly:
            break
        admitted |= newly
        pending -= newly
    problems += [f"{i!r} is present with prerequisites no legal discovery order could have met"
                 for i in sorted(pending)]
    return problems


def unlocked_implications(evidence: Evidence, known_ids: frozenset[str]):
    """§5.1: an implication "only unlocks with" everything in its `requires`."""
    return [imp for imp in evidence.implications if all(r in known_ids for r in imp.requires)]


def held_material(state: DiscoveryState) -> frozenset[str]:
    """What an implication's `requires` is answered by: the evidence found, the statements and the accounts heard."""
    return state.known_evidence | state.known_statements | state.known_accounts


def unlocked_view(evidence: Evidence, state: DiscoveryState) -> Evidence:
    """§5.2: the item as the PLAYER may reason about it — only the implications they have unlocked. Every player-facing
    reader (the hypothesis board, the notebook's tensions, the form vocabulary) takes an item through this, because
    `Evidence.implications` also holds the locked ones, which name the answer (H8-B1)."""
    return evidence.model_copy(update={"implications": tuple(unlocked_implications(evidence, held_material(state)))})


class PlayerEvidenceView(BaseModel):
    """§5.2: "Player view vs engine view. The player sees `reveals_text`, kind, location,
    and implications they have unlocked. `authentic`, `planted_by`, `load_bearing`,
    `red_herring` are engine-only" — and, by the same logic, so are `supports`/`contradicts`
    (solver tags) and `known_to`/`interacted` (provenance bookkeeping)."""
    model_config = ConfigDict(frozen=True)

    id: EvidenceId
    kind: EvidenceKind
    location: str | None
    reveals_text: str
    unlocked: tuple[Proposition, ...]


def project_for_player(evidence: Evidence, state: DiscoveryState) -> PlayerEvidenceView | None:
    """§5.2's player view — or `None` when the player has not found this item.

    DISCOVERABLE, DISCOVERED and VISIBLE TO PLAYER are three different states, and the
    projection is the boundary between the last two. Hiding the engine-only FIELDS is only
    half of it: without the access gate, projecting an undiscovered item still handed back
    its `reveals_text`, kind and location — the whole point of concealing an item is that
    its description is not available before it is found.

    The unlock set comes from the same `DiscoveryState`, so what an implication needs
    (`requires`: other evidence, or a heard statement) is answered by what the player
    actually holds rather than by a caller-supplied bag of ids unrelated to any discovery.
    """
    if evidence.id not in state.known_evidence:
        return None
    known = state.known_evidence | state.known_statements | state.known_accounts
    return PlayerEvidenceView(
        id=evidence.id, kind=evidence.kind, location=evidence.location_at_investigation,
        reveals_text=evidence.discovery.reveals_text,
        unlocked=tuple(imp.proposition for imp in unlocked_implications(evidence, known)),
    )


def testimony_strongly_retrievable(memory: Memory, epistemic: EpistemicState, cues: CueSet) -> bool:
    """I-39's pass/fail core without the parser (`Query`/`Alias`/`TimeAnchor` enumeration is
    Phase 4/5): does retrieval on this cue set reach `RETRIEVE_STRONG`? V-4's full form
    enumerates every parser-expressible `Query` shape and requires at least one to pass;
    Phase 3 exposes the primitive those shapes will be checked against, reusing Phase 2's
    own retrieval scoring rather than re-deriving it."""
    return score(memory, epistemic, cues) >= RETRIEVE_STRONG


@dataclass(frozen=True)
class ReachabilityReport:
    """V-4 (§19.4). `depth` is the level-synchronous BFS depth over the prerequisite graph;
    `cued` is the I-47 subset of `reachable` whose full discovery PATH is cued — every
    prerequisite itself cued, and the location/cue of every hop already named by held
    material — and `cued_depth` is §19.4's "minimum cued discovery depth", the number the
    proof core is reported and banded on (§20.2). Both depths are a function of case content
    alone, never of `EvidenceStore` insertion order."""
    reachable: frozenset[EvidenceId]
    unreachable: frozenset[EvidenceId]
    depth: dict[EvidenceId, int]
    cued: frozenset[EvidenceId]
    cued_depth: dict[EvidenceId, int] = field(default_factory=dict)


def _names(ev: Evidence) -> set[str]:
    """The entities an item puts into the player's material once found — the spike's
    `Evidence.names` (`spike/model.py`, "entities the item names (cue graph, §19.4)"),
    expressed in the fields §5.1 actually carries: the item itself, where it was found,
    the object it concerns, and where that object sits."""
    return {n for n in (ev.id, ev.discovery.at, ev.object, ev.location_at_investigation)
            if n is not None}


def _cue_satisfied(ev: Evidence, named: frozenset[str]) -> bool:
    """§19.4: "every edge carries a `cue: Ref` — an item already in the player's material
    that names the target's entity or location". Two conditions, both from the spike's
    `cue_closure` (`it.at in named and all(x in named for x in it.discover_needs)`):
    the player must have been given the item's LOCATION by something they already hold, and
    the spec's own `cue`, when it names one, must likewise already be held. A syntactically
    valid `at` is not a cue — that is exactly the vance4C seed-5 failure I-47 exists for (a
    gate log at a gazebo no statement ever named)."""
    if ev.discovery.at not in named:
        return False
    return ev.discovery.cue is None or ev.discovery.cue in named


def reachability(store: EvidenceStore, initial_locations: Iterable[str] = (),
                  initial_items: Iterable[str] = (), initial_statements: Iterable[str] = ()) -> ReachabilityReport:
    """V-4 (§19.4): two level-synchronous closures over the discovery graph. Nodes are
    evidence items; edges are `DiscoverySpec.prerequisites` (an item can gate on another
    item, a location, an item in hand, or a heard statement). `initial_*` seed the starting
    material — §19.4's "start location, kit, all characters interrogable" ∪ "every exterior
    access location" (I-47) — the Actor/Kit models that supply those values belong to
    Phase 1/6; this function only takes the resulting ids.

    **Reachable** is the prerequisite closure: what a player who enumerates everything could
    in principle obtain. **Cued** is the strictly narrower closure of §19.4's "fully-cued
    path", ported from the Phase 0.5 spike's `cue_closure` (`spike/solve.py`), which passed
    the feasibility gate: an item is cued only when every prerequisite it rests on is
    ITSELF cued and its own location/cue is already named by held material, and only cued
    items contribute new names. Cueing is therefore a property of the whole path, never of
    one node — §19.4: "uncued reachability is reported but does not satisfy V-4".

    Both loops are **level-synchronous**: each pass computes its whole frontier against the
    previous level's state before applying any of it. Mutating the state mid-pass (the v1
    form) let an item satisfy a sibling's prerequisite within its own level, which made both
    `depth` and `cued` a function of `EvidenceStore` insertion order rather than of case
    content. Items are iterated in sorted id order so nothing else can reintroduce that.
    # ponytail: O(n^2) over evidence count per case (small — §13.2a's own case-scale note,
    # <= a few dozen items); a real priority-queue BFS is only worth it if case sizes grow.
    """
    items = sorted(store.all(), key=lambda e: e.id)
    seed = DiscoveryState(visited_locations=frozenset(initial_locations),
                           held_items=frozenset(initial_items),
                           known_statements=frozenset(initial_statements))

    def closure(cue_gated: bool) -> tuple[frozenset[EvidenceId], dict[EvidenceId, int]]:
        found: frozenset[EvidenceId] = frozenset()
        named = frozenset(initial_locations) | frozenset(initial_items) | frozenset(initial_statements)
        depth: dict[EvidenceId, int] = {}
        d = 0
        while True:
            state = seed.model_copy(update={"known_evidence": found})
            frontier = [e for e in items
                        if e.id not in found and can_discover(e, state)
                        and (not cue_gated or _cue_satisfied(e, named))]
            if not frontier:
                return found, depth
            found |= {e.id for e in frontier}
            depth.update({e.id: d for e in frontier})
            if cue_gated:
                named |= {n for e in frontier for n in _names(e)}
            d += 1

    reachable, depth = closure(cue_gated=False)
    cued, cued_depth = closure(cue_gated=True)
    all_ids = frozenset(e.id for e in items)
    return ReachabilityReport(reachable=reachable, unreachable=all_ids - reachable,
                               depth=depth, cued=cued, cued_depth=cued_depth)


def unreachable_load_bearing(store: EvidenceStore, report: ReachabilityReport) -> frozenset[EvidenceId]:
    """§19.4: "every node tagged `load_bearing`... must be reachable" — the critical-clue
    half of V-4. An empty result is what "critical clues have valid reachability paths"
    means operationally; a non-empty one names exactly which proof-core item is stranded."""
    return frozenset(e.id for e in store.all() if e.load_bearing) & report.unreachable


def uncued_load_bearing(store: EvidenceStore, report: ReachabilityReport) -> frozenset[EvidenceId]:
    """§19.4's second half, and the one V-4 actually gates on: "the proof core must be
    reachable along a **fully-cued path**; uncued reachability is reported but does not
    satisfy V-4". `cued ⊆ reachable`, so this is a superset of `unreachable_load_bearing`
    and the two are reported separately — stranded and merely-uncued are different defects
    with different repairs (add a path vs. add a cue)."""
    return frozenset(e.id for e in store.all() if e.load_bearing) - report.cued


def red_herring_refuter_reachable(evidence: Evidence, report: ReachabilityReport) -> bool | None:
    """§19.6: "its `refuter` must be reachable". Returns `None` when there is nothing to
    check (no `red_herring`) or the refuter is a `StatementId` the reachability graph (which
    only knows about `Evidence`) cannot speak to — a `bool` only for an `EvidenceId` refuter."""
    if evidence.red_herring is None:
        return None
    refuter = evidence.red_herring.refuter
    if refuter not in report.reachable and refuter not in report.unreachable:
        return None  # not an EvidenceId at all (a StatementId) — Phase 4's testimony reachability
    return refuter in report.reachable
