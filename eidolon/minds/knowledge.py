"""KnowledgeEntry and its propagation from the canonical world (§6.2-6.3, §7.1, §4.8).

`propagate_knowledge(case)` is the deterministic fold Phase 1's `world/perception.py`
docstring points to: "`minds/` will build on this module's output rather than recomputing
perception quality." It never mutates `case` (I-4) and never touches `random` (I-6).
"""
from __future__ import annotations

from typing import Iterable

from pydantic import BaseModel, ConfigDict

from ..world.case import Case
from ..world.events import Event
from ..world.facts import FactIndex
from ..world.ids import ActorId
from ..world.perception import PerceptionFact, derive_perception
from ..world.physics import require_physics_valid
from ..world.state import death_ticks, ordered_events
from ..world.propositions import Proposition
from .ids import KnowledgeEntryId
from .provenance import Absence, Participated, Provenance, Told, Witnessed


class KnowledgeEntry(BaseModel):
    """§6.2. Immutable once produced — `KnowledgeStore` is the only mutable container, and
    even it is only ever built fresh or extended (I-4: the sealed case never changes)."""
    model_config = ConfigDict(frozen=True)

    id: KnowledgeEntryId
    character: ActorId
    proposition: Proposition
    source: Provenance
    acquired_at: int
    reliability: float
    is_true: bool  # engine-only, via FactIndex.truth_value (§6.2 types it as a bare `bool`).
                    # `False` therefore means REFUTED by the canonical world, never "not
                    # established": `propagate_knowledge` refuses to emit a non-`Told` entry
                    # whose truth is Unknown rather than folding the third value into this
                    # one. Only a `Told` proposition may be false here (§6.1/§6.2).


class KnowledgeStore:
    """Answers every §7.1 query reachable from knowledge alone (`knowers`, `entry.source`,
    `entry.acquired_at`, `entry.reliability`, `type(entry.source)`). `belief_for` and
    `retrievable` are answered by `belief.py`/`memory.py`, which are built on top of this.

    Keyed by `Proposition` rather than a `fact_id`: Phase 1 defines the `Fact` model
    (§4.7) but has no `derive_facts()` populating stable fact ids yet (only
    `FactIndex.truth_value`, which takes a `Proposition` directly) — indexing on the
    proposition itself is the query Phase 1 actually supports, and it is a strict subset
    of indexing by fact id once one exists (a documented Phase 2 scope decision)."""

    def __init__(self, entries: Iterable[KnowledgeEntry] = ()):
        self._by_id: dict[str, KnowledgeEntry] = {}
        self._by_character: dict[ActorId, list[KnowledgeEntry]] = {}
        for e in entries:
            self.add(e)

    def add(self, entry: KnowledgeEntry) -> None:
        if entry.id in self._by_id:
            raise ValueError(f"duplicate KnowledgeEntry id: {entry.id}")
        self._by_id[entry.id] = entry
        self._by_character.setdefault(entry.character, []).append(entry)

    def get(self, entry_id: KnowledgeEntryId) -> KnowledgeEntry | None:
        return self._by_id.get(entry_id)

    def all(self) -> list[KnowledgeEntry]:
        return list(self._by_id.values())

    def for_character(self, character: ActorId) -> list[KnowledgeEntry]:
        return list(self._by_character.get(character, []))

    def find(self, character: ActorId, proposition: Proposition) -> KnowledgeEntry | None:
        """The character's own entry for exactly this proposition, if any — highest
        reliability first (a character may acquire the same proposition twice)."""
        matches = [e for e in self.for_character(character) if e.proposition == proposition]
        return max(matches, key=lambda e: e.reliability) if matches else None

    def knowers(self, proposition: Proposition, by_t: int | None = None) -> dict[ActorId, KnowledgeEntry]:
        """§7.1 "who knows it?" — one (best) entry per character. `by_t` restricts to
        knowledge acquired at or before that tick."""
        out: dict[ActorId, KnowledgeEntry] = {}
        for e in self._by_id.values():
            if e.proposition != proposition:
                continue
            if by_t is not None and e.acquired_at > by_t:
                continue
            best = out.get(e.character)
            if best is None or e.reliability > best.reliability:
                out[e.character] = e
        return out

    def information_reach(self, proposition: Proposition, t: int) -> dict[ActorId, KnowledgeEntry]:
        """§4.10's `information_reach(proposition, t) -> {actor: KnowledgeEntry}` — "who
        could know p by t". It lives here rather than in `world/timeline.py` with the other
        six §4.10 queries because its return type is a `minds/` model and §23.1's dependency
        direction is one-way: `world/` may not name a `KnowledgeEntry`."""
        return self.knowers(proposition, by_t=t)


def _interval_start(prop: Proposition) -> int:
    iv = getattr(prop, "interval", None)
    if iv is not None:
        return iv[0]
    return getattr(prop, "t", 0)


def _provenance_from_perception_fact(pf: PerceptionFact) -> Provenance:
    event_id = pf.provenance[0] if pf.provenance else ""
    if pf.source == "Participated":
        return Participated(event_id=event_id)
    if pf.source == "CoPresence":
        return Witnessed(event_id=event_id, modality="co-presence", quality=pf.reliability)
    if pf.source == "Absence":
        assert pf.absence is not None
        return Absence(basis=pf.absence.basis, coverage=pf.absence.coverage,
                        entrances_covered=pf.absence.entrances_covered)
    modality = "sound" if pf.proposition.kind == "Heard" else "sight"
    return Witnessed(event_id=event_id, modality=modality, quality=pf.reliability)


def _told_present(event: Event, listener: ActorId, dead_at: dict[ActorId, int]) -> bool:
    """I-8: a `Told` entry needs the listener present at the speak event AND alive to hear
    it — otherwise they could not have heard it (P-7's spirit, §4.9 P-4). Structurally
    prevents impossible provenance rather than authoring it and catching it later.

    Perception is gated on death in `world/perception.py`; `Told` is the other way
    information reaches a character, so it takes the same gate. Without it a corpse listed
    as a `participant` of a later `Speak` event still acquired what was said."""
    if listener != event.actor and listener not in event.participants:
        return False
    return event.interval[0] < dead_at.get(listener, event.interval[0] + 1)


def propagate_knowledge(case: Case) -> KnowledgeStore:
    """§6.3's first two arrows: CaseLog -> Facts -> KnowledgeEntries. Perception (co-presence,
    absence, event/sustained sighting) comes straight from `world/perception.py`; `Told`
    comes from `InformationTransferred` effects on events the listener actually attended.

    `Read` and `Background` provenance types exist (`provenance.py`) but are not
    auto-derived here: `Read` would need a document-content model Phase 1's `Object` does
    not carry (no field holds "what the document says"), and `Background` has no
    generation rule in the architecture (§6.2 lists it as a kind, not a derivation). Both
    are out of Phase 2's named deliverables ("Told/Read provenance" — the roadmap does not
    ask for a document model), so they are typed but not populated, rather than guessed.
    """
    require_physics_valid(case)  # the world <- minds gate (§23.1): every derivation below
                                  # reads `presence`/`loc_at` and assumes P-1 holds.
    fact_index = FactIndex(case)
    store = KnowledgeStore()
    counter = [0]

    def emit(character: ActorId, proposition: Proposition, source: Provenance,
              acquired_at: int, reliability: float) -> KnowledgeEntry:
        truth = fact_index.truth_value(proposition)
        if truth is None and not isinstance(source, Told):
            # §6.1: knowledge "can be false? No — it is access, not content"; the one
            # exception §6.2 names is a `Told` proposition from a lying teller. Everything
            # else here is derived FROM the CaseLog, so the CaseLog must be able to settle
            # it. An Unknown means the derivation asserted something the world does not
            # establish — a generator bug, and silently writing `is_true=False` would file
            # it as a *refuted* fact. Fail closed (I-15) instead of collapsing the third
            # value away.
            raise ValueError(
                f"{character}: {source.kind} provenance derived a proposition the canonical "
                f"world does not settle (truth_value is Unknown): {proposition}")
        counter[0] += 1
        entry = KnowledgeEntry(
            id=f"K{counter[0]:04d}", character=character, proposition=proposition,
            source=source, acquired_at=acquired_at, reliability=reliability,
            is_true=bool(truth),
        )
        store.add(entry)
        return entry

    for pf in derive_perception(case):
        emit(pf.observer, pf.proposition, _provenance_from_perception_fact(pf),
             _interval_start(pf.proposition), pf.reliability)

    # `ordered_events`, not `case.events`: the CaseLog is a set (§4.1) and a `Told` chain is
    # resolved against knowledge accumulated so far, so folding it in authoring order made
    # what a character knows depend on tuple order. Two logs with equal content must fold to
    # equal stores (I-5).
    dead_at = death_ticks(case.events)
    for event in ordered_events(case.events):
        for eff in event.effects:
            if eff.kind != "InformationTransferred":
                continue
            if not _told_present(event, eff.to_actor, dead_at):
                continue  # listener wasn't there to hear it (I-8) — no entry emitted
            for prop in eff.propositions:
                teller_entry = store.find(eff.from_actor, prop)
                reliability = teller_entry.reliability if teller_entry else 0.0
                sincere = teller_entry is not None
                emit(eff.to_actor, prop,
                     Told(by=eff.from_actor, speak_event_id=event.id, teller_sincere=sincere,
                          grounding_entry_id=teller_entry.id if teller_entry else None),
                     event.interval[0], reliability)

    return store


def with_overlay(store: KnowledgeStore, epistemic) -> KnowledgeStore:
    """The sealed store plus this game's runtime `InvestigationTold` entries (§6.5), as a
    read-only derived view — the same relationship `world_at` has to the CaseLog.

    §6.3 keeps runtime-acquired knowledge in `EpistemicState.added_knowledge` so the sealed
    case never mutates (I-4). But every provenance query — the admissibility walk (I-27), V-2
    soundness, §7.2's speakable set — has to resolve ids across BOTH containers, or a chain
    that passes through a detective-supplied entry simply dead-ends and reports a clean level
    instead of the L0 that poisons it (AC-1). Building the union here keeps one authority per
    container and adds no third one: nothing is copied back into the sealed store.
    """
    merged = KnowledgeStore(store.all())
    for entry in epistemic.added_knowledge:
        if merged.get(entry.id) is None:
            merged.add(entry)
    return merged
