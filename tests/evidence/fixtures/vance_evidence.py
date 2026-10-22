"""Phase 3 evidence fixtures.

Two independent cases:

- `vance_v03_evidence()` — the FULL `Evidence` model version of the §13.3 worked scenario
  ("a fingerprint proves he was there tonight... depends on knowing the glass was washed"),
  built on the unmodified `tests/world/fixtures/vance.py::vance_v03` golden case. Phase 1
  owns that fixture and it is never edited here — only read.
- `evidence_case()` — a small, self-contained case for scenarios `vance_v03` does not carry:
  a real `TraceCreated` effect (`vance_v03`'s own `attack` event has none), a `Plant` event,
  and a multi-step discovery-prerequisite chain with a deliberately uncued item (I-47).
"""
from __future__ import annotations

from eidolon.evidence.model import DiscoverySpec, Evidence, EvidenceStore, Implication, Prereq, RedHerringSpec
from eidolon.world.case import Case
from eidolon.world.entities import Actor, Object
from eidolon.world.events import EffActorAt, EffTraceCreated, Event
from eidolon.world.propositions import Did
from eidolon.world.space import Location
from tests.world.fixtures.vance import vance_v03


# --- vance_v03: the §13.3 worked scenario, as full Evidence -------------------------
def vance_v03_evidence():
    """`S_clean` stands in for "Elena's statement that she cleaned Glass1 at [12,13)" — the
    full `Statement` model is Phase 4 (`evidence/ids.py`'s own forward-reference note); its
    ESTABLISHED INTERVAL is simply the `clean` event's own interval, canonical CaseLog fact
    regardless of who later testifies to it."""
    case, _ = vance_v03()
    evidence = [
        Evidence(
            id="E_watch", kind="Timepiece", created_at=(76, 77),
            implications=(Implication(proposition=Did(actor="Harold", action="Die",
                                                        interval=(76, 77), location="Study")),),
            discovery=DiscoverySpec(action="Look", at="Study",
                                     reveals_text="The study clock stopped at 22:16."),
        ),
        Evidence(
            # `location_at_investigation` is left unset: `vance_v03`'s CaseLog never emits an
            # `ObjectAt` effect for Glass1 (it is used as the murder weapon but never
            # explicitly relocated), so its only canonical position is `Object.initial_location`
            # ("Kitchen") — asserting "Study" here would be exactly the kind of ungrounded
            # claim `grounding.check_creation_grounding` exists to catch.
            id="E_trace", kind="Fingerprint", object="Glass1",
            reliability=0.9,
            implications=(Implication(
                proposition=Did(actor="David", action="touch", object="Glass1",
                                 location="Study", interval=(12, 120)),
                strength=0.9, requires=("S_clean",)),),
            discovery=DiscoverySpec(action="Dust", at="Glass1",
                                     prerequisites=(Prereq(kind="HasItem", ref="kit"),),
                                     reveals_text="A print on the glass.", cue="Glass1"),
        ),
    ]
    statement_intervals = {"S_clean": (12, 13)}
    return case, evidence, statement_intervals


# --- a small, self-contained case for grounding/discovery/red-herring scenarios -----
T_INVESTIGATION = 20

LOCATIONS = {
    "Parlor": Location(id="Parlor", name="the parlor"),
    "Cellar": Location(id="Cellar", name="the cellar", private=True),
}
ACTORS = {
    "Ann": Actor(id="Ann", name="Ann", role="suspect"),
    "Bea": Actor(id="Bea", name="Bea", role="witness"),
}
OBJECTS = {
    "Knife": Object(id="Knife", name="a knife", kind="weapon", initial_location="Parlor",
                     traceable=("fingerprint",)),
    "Letter": Object(id="Letter", name="a letter", kind="document", initial_location="Cellar"),
}


def evidence_case() -> Case:
    events = (
        Event(id="stay:Ann:0", kind="Stay", interval=(0, 20), location="Parlor", actor="Ann",
              effects=(EffActorAt(actor="Ann", location="Parlor"),)),
        Event(id="stay:Bea:0", kind="Stay", interval=(0, 20), location="Cellar", actor="Bea",
              effects=(EffActorAt(actor="Bea", location="Cellar"),)),
        Event(id="grip", kind="Use", interval=(2, 3), location="Parlor", actor="Ann",
              objects=("Knife",), effects=(EffTraceCreated(object="Knife", trace_kind="fingerprint"),)),
        Event(id="wipe", kind="Clean", interval=(5, 6), location="Parlor", actor="Ann",
              objects=("Knife",)),
        # A second, real touch inside E_fp_wide's claimed window — the whole point of an
        # entailed `touch` implication (§5.2) is that forensics cannot tell WHICH handling
        # left the mark, so the wide claim must still name a genuine event somewhere in its
        # interval, exactly as `vance_v03`'s own E_trace resolves against the real `attack`.
        Event(id="fidget", kind="Use", interval=(15, 16), location="Parlor", actor="Ann",
              objects=("Knife",)),
        Event(id="plant", kind="Plant", interval=(8, 9), location="Cellar", actor="Ann",
              objects=("Letter",)),
    )
    return Case(id="evidence_case", t_investigation=T_INVESTIGATION, actors=ACTORS,
                locations=LOCATIONS, objects=OBJECTS, events=events)


STATEMENT_INTERVALS = {"S_wipe": (5, 6)}


def evidence_case_items() -> list[Evidence]:
    return [
        Evidence(
            id="E_fp", kind="Fingerprint", object="Knife", location_at_investigation="Parlor",
            created_by="grip", created_at=(2, 3), reliability=0.9, load_bearing=True,
            implications=(Implication(proposition=Did(actor="Ann", action="touch", object="Knife",
                                                        location="Parlor", interval=(2, 3)), strength=0.9),),
            discovery=DiscoverySpec(action="Dust", at="Knife",
                                     prerequisites=(Prereq(kind="HasItem", ref="kit"),),
                                     reveals_text="A partial print on the knife."),
        ),
        Evidence(
            id="E_fp_wide", kind="Fingerprint", object="Knife", location_at_investigation="Parlor",
            reliability=0.7,
            implications=(Implication(
                proposition=Did(actor="Ann", action="touch", object="Knife",
                                 location="Parlor", interval=(6, 20)), strength=0.7,
                requires=("S_wipe", "E_fp")),),
            discovery=DiscoverySpec(action="Dust", at="Knife",
                                     prerequisites=(Prereq(kind="EvidenceFound", ref="E_fp"),),
                                     reveals_text="A second, smudged print.", cue="E_fp"),
        ),
        Evidence(
            id="E_letter", kind="Document", object="Letter", location_at_investigation="Cellar",
            authentic=False, planted_by="plant", created_at=(8, 9),
            implications=(Implication(proposition=Did(actor="Bea", action="Write", object="Letter",
                                                        location="Cellar", interval=(8, 9))),),
            discovery=DiscoverySpec(action="Read", at="Letter",
                                     prerequisites=(Prereq(kind="KnowsAbout", ref="Cellar"),),
                                     reveals_text="A letter, seemingly in Bea's hand.",
                                     cue="Gazebo"),  # deliberately never seeded (I-47 uncued case)
            red_herring=RedHerringSpec(misleads_toward="H_bea_did_it", refuter="E_fp"),
        ),
    ]


def evidence_case_store() -> EvidenceStore:
    return EvidenceStore(evidence_case_items())
