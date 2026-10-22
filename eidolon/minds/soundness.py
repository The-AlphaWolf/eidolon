"""Knowledge-soundness checker (V-2, roadmap §30 Phase 2 deliverable; I-8).

`propagate_knowledge` (`knowledge.py`) only ever emits sound entries by construction —
this checker exists for the other direction: catching a `KnowledgeEntry` that was hand-
constructed or corrupted (an adversarial/malformed input, or a future generator bug)
without re-deriving the whole perception model. It re-checks the cheap, load-bearing part
of I-8 — "at a time they were present" — against `world/state.py`'s own `presence`/`loc_at`,
independently of `perception.py`.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..world.case import Case
from ..world.state import loc_at
from .belief import BeliefStore
from .knowledge import KnowledgeStore
from .provenance import Absence, Background, Inferred, InvestigationTold, Participated, Read, Told, Witnessed


@dataclass(frozen=True)
class Violation:
    rule: str  # "V-2"
    detail: str

    def __str__(self) -> str:
        return f"{self.rule}: {self.detail}"


def _positioned_for(case: Case, character: str, at_tick: int, location: str | None) -> bool:
    """Could `character` plausibly have perceived `location` at `at_tick`: physically
    there, or with a perception edge reaching it from where they actually were."""
    if location is None:
        return True  # proposition carries no location to be positioned for (e.g. `Heard` w/o from_location)
    char_loc = loc_at(case.events, character, at_tick)
    if char_loc is None:
        return False
    if char_loc == location:
        return True
    return any(pe.observer_at == char_loc and pe.perceives == location for pe in case.perception_edges)


def check_knowledge_soundness(store: KnowledgeStore, case: Case,
                                beliefs: BeliefStore | None = None) -> list[Violation]:
    """I-8: every entry's provenance must terminate in something the character could
    actually perceive/participate in/be told, at a time they were present."""
    violations: list[Violation] = []
    events_by_id = {e.id: e for e in case.events}

    for entry in store.all():
        src = entry.source
        prop_loc = getattr(entry.proposition, "location", None) or getattr(entry.proposition, "from_location", None)

        if isinstance(src, Absence) and entry.proposition.kind != "NotAt":
            # I-34: Absence grounds NotAt ONLY.
            violations.append(Violation("V-2", f"{entry.id}: Absence provenance on a "
                                                 f"{entry.proposition.kind} proposition (Absence grounds NotAt only)"))
        elif isinstance(src, (Witnessed, Participated, Absence)):
            if not _positioned_for(case, entry.character, entry.acquired_at, prop_loc):
                violations.append(Violation("V-2", f"{entry.id}: {entry.character} was not positioned to "
                                                     f"acquire {entry.proposition} at t={entry.acquired_at}"))
        elif isinstance(src, Told):
            event = events_by_id.get(src.speak_event_id)
            if event is None:
                violations.append(Violation("V-2", f"{entry.id}: Told references unknown event {src.speak_event_id!r}"))
            elif entry.character != event.actor and entry.character not in event.participants:
                violations.append(Violation("V-2", f"{entry.id}: {entry.character} was not present at "
                                                     f"{src.speak_event_id} to be told this"))
            # I-27's chain has to resolve. A `grounding_entry_id` naming nothing is impossible
            # provenance; so is one naming an entry the teller does not actually hold. (For a
            # chain that runs through a runtime `InvestigationTold` entry, pass the overlay
            # view — `knowledge.with_overlay` — as `store`, or the edge dead-ends here.)
            if src.grounding_entry_id is not None:
                grounding = store.get(src.grounding_entry_id)
                if grounding is None:
                    violations.append(Violation("V-2", f"{entry.id}: Told grounding "
                                                         f"{src.grounding_entry_id!r} is not in the store"))
                elif grounding.character != src.by:
                    violations.append(Violation("V-2", f"{entry.id}: Told claims {src.by} as teller but its "
                                                         f"grounding {grounding.id} belongs to {grounding.character}"))
        elif isinstance(src, Read):
            if src.read_event_id not in events_by_id:
                violations.append(Violation("V-2", f"{entry.id}: Read references unknown event {src.read_event_id!r}"))
        elif isinstance(src, Inferred):
            for fid in src.from_ids:
                if store.get(fid) is None and (beliefs is None or beliefs.get(fid) is None):
                    violations.append(Violation("V-2", f"{entry.id}: Inferred references unknown grounding {fid!r}"))
        elif isinstance(src, (Background, InvestigationTold)):
            pass  # not event-grounded by definition (§6.2)

    return violations
