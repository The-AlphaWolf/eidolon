"""§6.4 belief formation rules 1-5."""
from __future__ import annotations

from eidolon.minds.belief import (
    CLOSE_RELS, TRUST_CLOSE, TRUST_DEFAULT, form_beliefs, trust_between,
)
from eidolon.minds.knowledge import KnowledgeEntry, KnowledgeStore, propagate_knowledge
from eidolon.minds.provenance import Told, Witnessed
from eidolon.world.case import Case
from eidolon.world.entities import Actor
from eidolon.world.facts import FactIndex
from eidolon.world.propositions import At, Rel, Saw

ACTORS = {"A": Actor(id="A", name="A", role="suspect"), "B": Actor(id="B", name="B", role="suspect")}


def _case(rels=()):
    return Case(id="c", t_investigation=20, actors=ACTORS, locations={}, rels=rels)


def test_rule1_direct_belief_above_threshold():
    prop = At(actor="X", location="Hall", interval=(0, 5))
    store = KnowledgeStore()
    store.add(KnowledgeEntry(id="K1", character="A", proposition=prop,
                              source=Witnessed(event_id="e1", modality="sight", quality=0.9),
                              acquired_at=0, reliability=0.9, is_true=True))
    case = _case()
    result = form_beliefs("A", store, case, FactIndex(case))
    assert len(result.beliefs) == 1
    b = result.beliefs[0]
    assert b.proposition == prop and b.confidence_0 == 9000 and b.grounds == ("K1",)


def test_rule2_uncertain_unidentified_perception_forms_belief_in_unidentified_form():
    prop = Saw(observer="A", subject="figure", location="Hall", interval=(0, 5), identified=False)
    store = KnowledgeStore()
    store.add(KnowledgeEntry(id="K1", character="A", proposition=prop,
                              source=Witnessed(event_id="e1", modality="sight", quality=0.4),
                              acquired_at=0, reliability=0.4, is_true=True))
    case = _case()
    result = form_beliefs("A", store, case, FactIndex(case))
    assert len(result.beliefs) == 1
    assert result.beliefs[0].proposition == prop
    assert result.beliefs[0].confidence_0 == 4000


def test_below_uncertain_floor_and_non_perception_kinds_form_no_belief():
    """Reliability < 0.2, and a non-Saw/Heard kind sitting in the 0.2-0.6 band (no
    "unidentified form" for it to take): rule 1 and rule 2 both decline (documented
    scope — see `belief.py`'s module docstring)."""
    weak_saw = Saw(observer="A", subject="figure", location="Hall", interval=(0, 5), identified=False)
    weak_at = At(actor="X", location="Hall", interval=(0, 5))
    store = KnowledgeStore()
    store.add(KnowledgeEntry(id="K1", character="A", proposition=weak_saw,
                              source=Witnessed(event_id="e1", modality="sight", quality=0.1),
                              acquired_at=0, reliability=0.1, is_true=True))
    store.add(KnowledgeEntry(id="K2", character="A", proposition=weak_at,
                              source=Witnessed(event_id="e2", modality="co-presence", quality=0.4),
                              acquired_at=0, reliability=0.4, is_true=True))
    case = _case()
    result = form_beliefs("A", store, case, FactIndex(case))
    assert result.beliefs == ()


def test_rule3_told_forms_belief_scaled_by_trust_times_reliability():
    prop = At(actor="X", location="Hall", interval=(0, 5))
    store = KnowledgeStore()
    store.add(KnowledgeEntry(id="K1", character="A", proposition=prop,
                              source=Told(by="B", speak_event_id="talk", teller_sincere=True),
                              acquired_at=0, reliability=0.5, is_true=True))
    case = _case()  # no Rel(A,B) -> default trust
    result = form_beliefs("A", store, case, FactIndex(case))
    assert len(result.beliefs) == 1
    assert result.beliefs[0].confidence_0 == round(TRUST_DEFAULT * 0.5 * 10000)


def test_trust_between_close_relationship_vs_default():
    case = _case(rels=(Rel(a="A", b="B", rel_kind="lover"),))
    assert trust_between(case, "A", "B") == TRUST_CLOSE
    assert trust_between(case, "A", "C") == TRUST_DEFAULT
    assert "lover" in CLOSE_RELS


def test_rule4_opportunity_inference_flags_actor_near_scene_at_death():
    """§6.4 rule 4: `At(X, near scene) ∧ Died(V, scene, t) -> Attitude(self, X, "suspects")`.
    Exercised on a small hand-built case where the rule is guaranteed to fire: A was in the
    Study around the death window and B was not."""
    from eidolon.world.events import EffActorAt, EffActorState, Event
    from eidolon.world.space import Location

    actors = {"V": Actor(id="V", name="V", role="victim"), "A": Actor(id="A", name="A", role="suspect"),
              "B": Actor(id="B", name="B", role="suspect"), "Self": Actor(id="Self", name="Self", role="suspect")}
    locations = {"Study": Location(id="Study", name="Study"), "Kitchen": Location(id="Kitchen", name="Kitchen")}
    events = (
        # `Self` co-witnesses A's Study presence directly (no perception edges exist in
        # this tiny case, so co-presence is the only route to knowledge of another room).
        Event(id="a_at_study", kind="Stay", interval=(5, 12), location="Study", actor="A",
              effects=(EffActorAt(actor="A", location="Study"),)),
        Event(id="self_at_study", kind="Stay", interval=(5, 12), location="Study", actor="Self",
              effects=(EffActorAt(actor="Self", location="Study"),)),
        Event(id="b_at_kitchen", kind="Stay", interval=(0, 20), location="Kitchen", actor="B",
              effects=(EffActorAt(actor="B", location="Kitchen"),)),
        Event(id="v_at_study", kind="Stay", interval=(0, 10), location="Study", actor="V",
              effects=(EffActorAt(actor="V", location="Study"),)),
        Event(id="die", kind="Die", interval=(10, 11), location="Study", actor="V",
              effects=(EffActorState(actor="V", attr="alive", value="false"),)),
    )
    case = Case(id="d", t_investigation=20, actors=actors, locations=locations, events=events)
    store = propagate_knowledge(case)
    result = form_beliefs("Self", store, case, FactIndex(case))
    suspects = [b for b in result.beliefs if b.proposition.kind == "Attitude" and b.proposition.attitude_kind == "suspects"]
    targets = {b.proposition.b for b in suspects}
    assert "A" in targets  # in the Study within the margin of the death window
    assert "B" not in targets  # in the Kitchen throughout, not near the scene
    a_belief = next(b for b in suspects if b.proposition.b == "A")
    assert a_belief.proposition.a == "Self" and a_belief.grounds


def test_rule5_conflict_resolution_keeps_higher_confidence():
    prop_true = At(actor="A", location="Hall", interval=(0, 5))
    prop_false = At(actor="A", location="Kitchen", interval=(2, 4))  # same actor, overlapping, different location
    store = KnowledgeStore()
    store.add(KnowledgeEntry(id="K_weak", character="A", proposition=prop_false,
                              source=Witnessed(event_id="e1", modality="co-presence", quality=0.6),
                              acquired_at=0, reliability=0.6, is_true=False))
    store.add(KnowledgeEntry(id="K_strong", character="A", proposition=prop_true,
                              source=Witnessed(event_id="e2", modality="co-presence", quality=0.9),
                              acquired_at=0, reliability=0.9, is_true=True))
    case = _case()
    result = form_beliefs("A", store, case, FactIndex(case))
    assert len(result.beliefs) == 1
    assert result.beliefs[0].proposition == prop_true
    assert len(result.suppressed) == 1
    assert result.suppressed[0].proposition == prop_false


def test_belief_store_belief_for_and_duplicate_rejection():
    import pytest
    from eidolon.minds.belief import Belief, BeliefStore
    prop = At(actor="X", location="Hall", interval=(0, 5))
    bs = BeliefStore()
    b = Belief(id="B1", character="A", proposition=prop, confidence_0=9000, grounds=("K1",),
               formed_at=0, is_true=True)
    bs.add(b)
    assert bs.belief_for("A", prop) is b
    assert bs.belief_for("A", At(actor="Y", location="Hall", interval=(0, 5))) is None
    with pytest.raises(ValueError):
        bs.add(b)
