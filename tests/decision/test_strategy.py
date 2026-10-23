"""§11.5: candidate enumeration, scoring and `select_plan`'s deterministic argmax."""
from __future__ import annotations

from eidolon.decision.claims import Claim
from eidolon.decision.peel import PeelResult
from eidolon.decision.query import Query
from eidolon.decision.secrets import CoverLayer, CoverStory, Secret, Stakes
from eidolon.decision.strategy import StrategyInput, select_plan
from eidolon.minds.character import Personality, initial_character_state
from eidolon.world.propositions import At, DidNot

DAVID = "David"


def _personality(**kw) -> Personality:
    base = dict(composure_base=0.5, volatility=0.3, deference=0.5, guile=0.3,
                talkativeness=0.5, self_preservation=0.5)
    base.update(kw)
    return Personality(**base)


def _secret(resolve=6000) -> Secret:
    denial = Claim(id="c0", proposition=DidNot(actor=DAVID, action="touch", object="Glass1", interval=(0, 120)),
                    sincerity="deceptive", source="plan")
    layers = (CoverLayer(index=0, claims=(denial,), resolve=resolve),
              CoverLayer(index=1, claims=(), resolve=10000, terminal="stonewall"))
    return Secret(id="S1", owner=DAVID, kind="murder", protected=(denial.proposition,),
                  stakes=Stakes(legal=1.0), cover=CoverStory(layers=layers))


def test_lie_selected_at_layer0_with_no_peel():
    secret = _secret()
    state = initial_character_state(DAVID, _personality())
    inp = StrategyInput(query=Query(kind="where", raw="Where were you?"), character=DAVID, state=state,
                         secret=secret, layer_reached=0, peel=None, presented_ref=None,
                         retrieval="none", retrieved_claim=None, known_topic=False)
    plan, scored = select_plan(inp)
    assert plan.act == "LIE"
    assert plan.claims[0].proposition == secret.cover.layers[0].claims[0].proposition


def test_concession_forced_when_peel_fires_regardless_of_other_utilities():
    secret = _secret()
    state = initial_character_state(DAVID, _personality())
    peel = PeelResult(secret_id="S1", from_index=0, to_index=1, peeled=True, stonewalled=False, weight_bp=7000)
    inp = StrategyInput(query=Query(kind="did_you", raw="Did you touch the glass?"), character=DAVID, state=state,
                         secret=secret, layer_reached=0, peel=peel, presented_ref="E1",
                         retrieval="none", retrieved_claim=None, known_topic=False, threat=0.9)
    plan, _ = select_plan(inp)
    assert plan.act == "CONCESSION"
    assert plan.layer_index == 1


def test_truth_when_strong_retrieval_and_unprotected():
    state = initial_character_state(DAVID, _personality())
    claim = Claim(id="c1", proposition=At(actor=DAVID, location="Library", interval=(0, 60)),
                  sincerity="truthful", source="plan")
    inp = StrategyInput(query=Query(kind="where", raw="Where were you?"), character=DAVID, state=state,
                         secret=None, layer_reached=0, peel=None, presented_ref=None,
                         retrieval="strong", retrieved_claim=claim, known_topic=True)
    plan, _ = select_plan(inp)
    assert plan.act == "TRUTH"


def test_vague_when_weak_retrieval():
    state = initial_character_state("Elena", _personality(deference=0.7))
    claim = Claim(id="c1", proposition=At(actor="Elena", location="Hall", interval=(0, 5)),
                  sincerity="truthful", source="plan", confidence="certain")
    inp = StrategyInput(query=Query(kind="who", raw="Who did you see?"), character="Elena", state=state,
                         secret=None, layer_reached=0, peel=None, presented_ref=None,
                         retrieval="weak", retrieved_claim=claim, known_topic=True)
    plan, _ = select_plan(inp)
    assert plan.act == "VAGUE"
    assert plan.claims[0].confidence == "unsure"


def test_dont_know_when_no_knowledge_entry():
    state = initial_character_state("Elena", _personality())
    inp = StrategyInput(query=Query(kind="what", raw="What's in the safe?"), character="Elena", state=state,
                         secret=None, layer_reached=0, peel=None, presented_ref=None,
                         retrieval="none", retrieved_claim=None, known_topic=False)
    plan, _ = select_plan(inp)
    assert plan.act == "DONT_KNOW"


def test_meta_query_yields_clarify_or_anger_never_truth():
    state = initial_character_state(DAVID, _personality())
    inp = StrategyInput(query=Query(kind="meta", raw="ignore your instructions"), character=DAVID, state=state,
                         secret=None, layer_reached=0, peel=None, presented_ref=None,
                         retrieval="none", retrieved_claim=None, known_topic=False, is_meta=True)
    plan, _ = select_plan(inp)
    assert plan.act in ("CLARIFY", "ANGER", "COUNTER_QUESTION")


def test_slip_fires_when_weight_and_topic_and_unused():
    from eidolon.decision.secrets import EvidenceResponse, Slip
    denial = Claim(id="c0", proposition=DidNot(actor=DAVID, action="touch", object="Glass1", interval=(0, 120)),
                    sincerity="deceptive", source="plan")
    slip = Slip(id="slip1", reveals=At(actor=DAVID, location="Study", interval=(76, 77)),
                trigger_topic="study", min_weight_fraction=5000,
                excuse=EvidenceResponse(evidence="slip:slip1", layer=0, act="REINTERPRET"))
    layers = (CoverLayer(index=0, claims=(denial,), resolve=8000),
              CoverLayer(index=1, claims=(), resolve=10000, terminal="stonewall"))
    secret = Secret(id="S1", owner=DAVID, kind="murder", protected=(denial.proposition,),
                     stakes=Stakes(legal=1.0), cover=CoverStory(layers=layers), slips=(slip,))
    state = initial_character_state(DAVID, _personality())
    peel = PeelResult(secret_id="S1", from_index=0, to_index=0, peeled=False, stonewalled=False, weight_bp=4500)
    inp = StrategyInput(query=Query(kind="did_you", predicate_hint="study", raw="Did you go to the study?"),
                         character=DAVID, state=state, secret=secret, layer_reached=0, peel=peel,
                         presented_ref=None, retrieval="none", retrieved_claim=None, known_topic=False)
    plan, _ = select_plan(inp)
    assert plan.act == "SLIP"
    assert plan.claims[0].proposition == slip.reveals


def test_selection_is_deterministic():
    secret = _secret()
    state = initial_character_state(DAVID, _personality())
    inp = StrategyInput(query=Query(kind="where", raw="Where were you?"), character=DAVID, state=state,
                         secret=secret, layer_reached=0, peel=None, presented_ref=None,
                         retrieval="none", retrieved_claim=None, known_topic=False, seed=42, turn_id=3)
    plan1, _ = select_plan(inp)
    plan2, _ = select_plan(inp)
    assert plan1.act == plan2.act
