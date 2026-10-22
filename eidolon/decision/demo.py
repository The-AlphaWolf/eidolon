"""A minimal, self-contained playable `GameState` for `eidolon/cli.py`'s `play` command.

**Scope note.** The Phase 4 exit criterion asks for "`vance_v03` playable end-to-end with
TemplateLLM via CLI". `vance_v03` (`cases/vance_v03.json`) is the Phase 0.5/1 solver-selected
WORLD (locations, travel, the CaseLog) — it carries no `Secret`/`CoverStory` content, because
authoring those is Phase 6's "cover synthesis" deliverable (roadmap §30), not yet built. This
module demonstrates the same MECHANISM the exit criterion is checking — a real `Case`, a real
murder `Secret`/`CoverStory` with derived breaker sets, real `Evidence` with a `requires`
chain, driven through the full turn pipeline with `TemplateLLM` — using a small case built
directly here rather than importing `tests/` fixtures (production code does not depend on the
test tree) or a partial re-authoring of `vance_v03`'s own cast, which would just be a second,
incomplete copy of Phase 6's future work.
"""
from __future__ import annotations

from ..evidence.discovery import DiscoveryState
from ..evidence.model import DiscoverySpec, Evidence, EvidenceStore, Implication
from ..minds.belief import BeliefStore
from ..minds.character import Personality, initial_character_state
from ..minds.epistemic import EpistemicState
from ..minds.knowledge import KnowledgeStore
from ..world.case import Case
from ..world.entities import Actor, Object
from ..world.events import EffActorAt, EffTraceCreated, Event
from ..world.propositions import At, Did, DidNot
from ..world.space import Location
from .claims import Claim, StatementStore
from .events import DecisionState
from .secrets import CoverLayer, CoverStory, EvidenceResponse, Secret, SecretStore, Stakes
from .turn import GameState

DAVID, HAROLD = "David", "Harold"


def build_demo_state() -> GameState:
    locations = {
        "Hall": Location(id="Hall", name="the hall"),
        "Study": Location(id="Study", name="the study", private=True),
        "Kitchen": Location(id="Kitchen", name="the kitchen"),
    }
    actors = {
        HAROLD: Actor(id=HAROLD, name="Harold Vance", role="victim"),
        DAVID: Actor(id=DAVID, name="David Kessler", role="suspect"),
    }
    objects = {"Knife": Object(id="Knife", name="a kitchen knife", kind="weapon", initial_location="Kitchen")}
    events = (
        Event(id="stay:David:0", kind="Stay", interval=(0, 20), location="Kitchen", actor=DAVID,
              effects=(EffActorAt(actor=DAVID, location="Kitchen"),)),
        Event(id="stay:Harold:0", kind="Stay", interval=(0, 20), location="Study", actor=HAROLD,
              effects=(EffActorAt(actor=HAROLD, location="Study"),)),
        Event(id="wipe", kind="Clean", interval=(5, 6), location="Kitchen", actor=DAVID,
              objects=("Knife",), effects=(EffTraceCreated(object="Knife", trace_kind="fingerprint"),)),
    )
    case = Case(id="demo", t_investigation=20, actors=actors, locations=locations, objects=objects, events=events)

    denial = Claim(id="c0", proposition=DidNot(actor=DAVID, action="touch", object="Knife", interval=(0, 20)),
                    sincerity="deceptive", source="plan")
    concede = Claim(id="c1", proposition=Did(actor=DAVID, action="touch", object="Knife", location="Kitchen",
                                              interval=(5, 6)),
                     sincerity="deceptive", source="plan")
    secret = Secret(
        id="S_murder_demo", owner=DAVID, kind="murder", protected=(denial.proposition,),
        stakes=Stakes(legal=1.0),
        evidence_responses=(EvidenceResponse(evidence="E_knife", layer=0, act="DENY_EVIDENCE"),),
        cover=CoverStory(layers=(
            CoverLayer(index=0, claims=(denial,), resolve=6000, breaker_sets=(frozenset({"E_knife"}),)),
            CoverLayer(index=1, claims=(concede,), resolve=10000, terminal="stonewall"),
        )),
    )
    evidence = EvidenceStore([
        Evidence(id="E_knife", kind="Fingerprint", object="Knife", created_by="wipe", created_at=(5, 6),
                 reliability=0.9,
                 implications=(Implication(proposition=Did(actor=DAVID, action="touch", object="Knife",
                                                            location="Kitchen", interval=(0, 20)), strength=0.9),),
                 discovery=DiscoverySpec(action="Dust", at="Knife", cue="Knife")),
    ])

    return GameState(
        case=case, knowledge=KnowledgeStore(), beliefs=BeliefStore(), memories={DAVID: ()},
        secrets=SecretStore([secret]), evidence=evidence,
        characters={DAVID: initial_character_state(DAVID, Personality(
            composure_base=0.5, volatility=0.3, deference=0.5, guile=0.4,
            talkativeness=0.4, self_preservation=0.5))},
        epistemic=EpistemicState(), discovery=DiscoveryState(),
        decision=DecisionState(statements=StatementStore()), seed=1, turn_counter=0,
    )
