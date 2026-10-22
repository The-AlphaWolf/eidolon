"""Small decision-level worlds for the Phase 9 suites (T-25, T-26, §28.4). Built from the demo state plus the same derivation
the sealed-case loader uses (`propagate_knowledge` -> `form_beliefs` -> `encode_memories`), so every act class below comes out of
the REAL strategy, not out of a hand-written plan:

    LIE         David, asked where he was, with his cover intact
    TRUTH       Nora, whose memory of her own evening is strong
    CONCESSION  David, shown the knife print (his first layer peels)
    CONFESSION  David again, one turn later, with the solver gate OPEN (I-21) - in the world whose terminal layer confesses
"""
from __future__ import annotations

from dataclasses import replace

from eidolon.decision.demo import DAVID, build_demo_state
from eidolon.decision.query import EntityRef, Query
from eidolon.decision.secrets import SecretStore
from eidolon.decision.solver import UniquenessResult
from eidolon.minds.belief import BeliefStore, form_beliefs
from eidolon.minds.character import Personality, initial_character_state
from eidolon.minds.knowledge import propagate_knowledge
from eidolon.minds.memory import encode_memories
from eidolon.world.entities import Actor
from eidolon.world.events import EffActorAt, Event
from eidolon.world.facts import FactIndex
from eidolon.world.frozen import FrozenDict
from tests.decision.test_phase5_readiness import _confession_secret

NORA = "Nora"
GATE = lambda actor, secret, presented, ctx: UniquenessResult(unique=True, survivors=(DAVID,))      # noqa: E731
PERSONALITY = Personality(composure_base=0.5, volatility=0.3, deference=0.5, guile=0.4, talkativeness=0.4, self_preservation=0.5)


def world_a():
    """David (lies, then concedes at the knife print) and Nora (a strong, true memory of the hall)."""
    base = build_demo_state()
    case = base.case.model_copy(update={
        "actors": FrozenDict({**base.case.actors, NORA: Actor(id=NORA, name="Nora Pell", role="suspect")}),
        "events": base.case.events + (Event(id="stay:Nora:0", kind="Stay", interval=(0, 20), location="Hall", actor=NORA,
                                            effects=(EffActorAt(actor=NORA, location="Hall"),)),)})
    knowledge, idx = propagate_knowledge(case), FactIndex(case)
    beliefs, mems = [], {}
    for actor in sorted(case.living_actors()):
        own = form_beliefs(actor, knowledge, case, idx).beliefs
        beliefs += list(own)
        mems[actor] = tuple(m.model_copy(update={"strength_0": 9000}) for m in encode_memories(actor, list(own), knowledge, case))
    chars = {**base.characters, NORA: initial_character_state(NORA, PERSONALITY)}
    return replace(base, case=case, knowledge=knowledge, beliefs=BeliefStore(beliefs), memories=mems, characters=chars)


def world_b():
    """The same world with a murder cover whose terminal layer confesses - gated by the solver (I-21/I-56)."""
    a = world_a()
    return replace(a, secrets=SecretStore([_confession_secret(DAVID, "S_d")]))


WHERE = Query(kind="where", raw="Where were you?")
HALL = Query(kind="where", subject=EntityRef(id=NORA, kind="actor"), location="Hall", predicate_hint="presence",
             raw="Were you in the hall?")
PRINTS = Query(kind="challenge", raw="Your prints are on the knife.")
