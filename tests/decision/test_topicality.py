"""RB-2 at the Phase 4 layer (ADR-25/26/27, I-54…I-56): topicality is a FOOTPRINT, never a wording; the speaker may not
voice what the solver withholds; retrieval is argmax; an innocent's concession terminal is not the murder gate.
Each test names the audit cause (C1…C11, design §A) it closes.
"""
from __future__ import annotations

import itertools
from dataclasses import replace

import pytest

from eidolon.decision.demo import DAVID, build_demo_state
from eidolon.decision.footprint import (
    Footprint, claim_covers, intersects, prop_footprint, secret_topical, unconceded_protected,
)
from eidolon.decision.claims import Claim
from eidolon.decision.peel import confession_gated
from eidolon.decision.query import EntityRef, Query, TimePhrase
from eidolon.decision.secrets import CoverLayer, CoverStory, Secret, SecretStore, Stakes
from eidolon.decision.speakable import speakable
from eidolon.decision.turn import query_cues, relevant_secret, retrieve_for_query, run_ask_turn
from eidolon.minds.belief import Belief, BeliefStore
from eidolon.minds.epistemic import EpistemicState
from eidolon.minds.memory import CueSet, Memory
from eidolon.world.propositions import At, Did, DidNot, Saw


def tp(a, b):
    return TimePhrase(text="t", interval=(a, b))


def narrowed_state(interval=(5, 6)):
    """The demo, but David's secret protects only `interval`, so footprints can miss it."""
    s = build_demo_state()
    old = s.secrets.for_owner(DAVID)[0]
    deny = Claim(id="c0", proposition=DidNot(actor=DAVID, action="touch", object="Knife", interval=interval),
                 sincerity="deceptive", source="plan")
    sec = old.model_copy(update={"protected": (deny.proposition,), "cover": CoverStory(layers=(
        CoverLayer(index=0, claims=(deny,), resolve=6000), old.cover.layers[1]))})
    return replace(s, secrets=SecretStore([sec])), sec


# ----------------------------------------------------------------------------------------- C1: footprint topicality
def test_the_len_owned_equals_one_fallback_is_gone_a_question_about_another_time_is_not_about_the_secret():
    s, sec = narrowed_state((5, 6))
    inside = Query(kind="did_you", time=tp(0, 10), raw="Were you there?")
    outside = Query(kind="did_you", time=tp(12, 20), raw="Were you there?")
    assert relevant_secret(DAVID, s.secrets, inside, None, s.evidence) is sec
    assert relevant_secret(DAVID, s.secrets, outside, None, s.evidence) is None


def test_a_question_about_somebody_else_is_not_about_my_secret():
    s, sec = narrowed_state((0, 20))
    q = Query(kind="did_they", subject=EntityRef(id="Harold", kind="actor"), predicate_hint="presence", raw="Harold?")
    assert relevant_secret(DAVID, s.secrets, q, None, s.evidence) is None
    own = Query(kind="did_you", raw="You?")
    assert relevant_secret(DAVID, s.secrets, own, None, s.evidence) is sec         # §29.2 turns 1-2: still the cover


def test_open_ended_and_smalltalk_questions_are_never_topical():
    s, sec = narrowed_state((0, 20))
    for kind in ("what", "why", "opinion", "hypothetical", "smalltalk", "narrative", "recall_detail"):
        assert relevant_secret(DAVID, s.secrets, Query(kind=kind, raw="..."), None, s.evidence) is None, kind


def test_topicality_never_reads_presuppositions_bluff_parity_6_5():
    s, sec = narrowed_state((5, 6))
    true_p, false_p = sec.protected[0], At(actor="Harold", location="Study", interval=(0, 20))
    for kind, loc, iv in itertools.product(("did_you", "where", "what", "did_they"), (None, "Hall"), ((0, 10), (12, 20))):
        base = dict(kind=kind, location=loc, time=tp(*iv), raw="x")
        a = secret_topical(sec, 0, Query(presupposes=(true_p,), **base), DAVID)
        b = secret_topical(sec, 0, Query(presupposes=(false_p,), **base), DAVID)
        c = secret_topical(sec, 0, Query(**base), DAVID)
        assert a == b == c, (kind, loc, iv)


def test_a_conceded_proposition_is_no_longer_topical_the_runtime_i45_counterpart():
    deny = Claim(id="d", proposition=DidNot(actor=DAVID, action="touch", object="Knife", interval=(0, 20)),
                 sincerity="deceptive", source="plan")
    truth = Did(actor=DAVID, action="touch", object="Knife", location="Kitchen", interval=(5, 6))
    sec = Secret(id="S", owner=DAVID, kind="theft", protected=(deny.proposition, truth), stakes=Stakes(),
                 cover=CoverStory(layers=(CoverLayer(index=0, claims=(deny,), resolve=6000),
                                          CoverLayer(index=1, concedes=(deny.proposition, truth), resolve=10000,
                                                     terminal="stonewall"))))
    assert unconceded_protected(sec, 0) == (deny.proposition, truth) and unconceded_protected(sec, 1) == ()
    assert secret_topical(sec, 0, Query(kind="did_you", raw="?"), DAVID)
    assert not secret_topical(sec, 1, Query(kind="did_you", raw="?"), DAVID)


def test_footprint_algebra():
    f = lambda a, loc=None, iv=None: Footprint(frozenset(a), loc, iv)
    assert intersects(f({"A"}), f({"A", "B"})) and not intersects(f({"A"}), f({"B"}))
    assert intersects(f({"A"}, None, (0, 10)), f({"A"}, None, (9, 12))) and not intersects(f({"A"}, None, (0, 10)), f({"A"}, None, (10, 12)))
    assert not intersects(f({"A"}, "X"), f({"A"}, "Y")) and intersects(f({"A"}, "X"), f({"A"}, None))
    assert not intersects(f(set()), f({"A"}))                                    # nobody asked about, no place: not topical
    assert intersects(f(set(), "X"), f({"A"}, "X")) and not intersects(f(set(), "X"), f({"A"}, None))
    # `At` carries no scene: where someone WAS is the content of the answer, not part of what is asked
    assert prop_footprint(At(actor="A", location="X", interval=(0, 5))).location is None
    assert prop_footprint(Did(actor="A", action="Attack", interval=(0, 1), location="X")).location == "X"


# ----------------------------------------------------------------------------------------- C2: LIE needs a covering claim
def test_lie_requires_a_deceptive_claim_covering_the_asked_proposition():
    s, sec = narrowed_state((5, 6))
    near = run_ask_turn(s, DAVID, Query(kind="did_you", time=tp(0, 10), raw="Were you there?"))
    far = run_ask_turn(s, DAVID, Query(kind="did_you", time=tp(12, 20), raw="Were you there?"))
    assert near.plan_act == "LIE" and far.plan_act != "LIE"
    deny = sec.cover.layers[0].claims[0]
    assert claim_covers(deny.proposition, Query(kind="did_you", time=tp(0, 10), raw=""), DAVID)
    assert not claim_covers(deny.proposition, Query(kind="did_you", time=tp(12, 20), raw=""), DAVID)


# ----------------------------------------------------------------------------------------- C11: speakable (I-54)
def test_a_claim_grounded_inside_an_unconceded_protected_interval_is_not_speakable_until_conceded():
    from tests.solve.helpers import loaded
    from eidolon.minds import accounts
    from eidolon.minds.knowledge import propagate_knowledge
    p = loaded("manor_wing", 4).package
    ks = propagate_knowledge(p.case)
    secrets = SecretStore(p.secrets)
    claim = lambda e: Claim(id="c", proposition=e.proposition, sincerity="truthful", source="plan", grounding=(e.id,))
    layer0 = lambda s: 0
    inside = lambda sec: [e for e in ks.for_character(sec.owner)
                          if (seg := accounts.observation_segment(p.case, ks, e.id)) is not None
                          and any(seg[0] < hi and lo < seg[1] for lo, hi in sec.protected_intervals())]
    # the murderer's excursion is never conceded for free: nothing grounded in it is ever speakable (I-45's runtime mirror)
    murder = next(s for s in p.secrets if s.kind == "murder")
    mine = inside(murder)
    assert mine, "the murderer must hold knowledge acquired inside their own protected interval"
    assert not any(speakable(claim(e), murder.owner, secrets, layer0, ks, p.case) for e in mine)
    last = lambda s: len(s.cover.layers) - 1
    assert not any(speakable(claim(e), murder.owner, secrets, last, ks, p.case) for e in mine
                   if e.proposition in murder.protected)
    # an innocent concedes what they hid: before the peel it is withheld, after it the same claim is speakable
    innocent = next(s for s in p.secrets if s.kind != "murder")
    own = inside(innocent)
    assert own
    assert not any(speakable(claim(e), innocent.owner, secrets, layer0, ks, p.case) for e in own)
    assert any(speakable(claim(e), innocent.owner, secrets, last, ks, p.case) for e in own),         "conceding the protected interval must release the knowledge acquired inside it"


def test_speakable_ignores_the_query_and_the_presupposition_by_construction():
    import inspect
    src = inspect.getsource(speakable)
    assert "presuppos" not in src and "query" not in src.lower().replace("queries", "")


# ----------------------------------------------------------------------------------------- C9 / I-56
def _secret(kind, terminal="confession", claims=()):
    c = Claim(id="x", proposition=DidNot(actor=DAVID, action="touch", object="Knife", interval=(0, 20)),
              sincerity="deceptive", source="plan")
    return Secret(id="S", owner=DAVID, kind=kind, protected=(c.proposition,), stakes=Stakes(),
                  cover=CoverStory(layers=(CoverLayer(index=0, claims=(c,), resolve=6000),
                                           CoverLayer(index=1, claims=tuple(claims), resolve=10000, terminal=terminal))))


def test_the_confession_gate_is_the_solutions_not_every_innocents():
    from eidolon.world.propositions import Solution
    sol = Claim(id="s", proposition=Solution(murderer=DAVID, method="blunt", motive_kind="debt", location="Study", interval=(5, 6)),
                sincerity="truthful", source="plan")
    plain = Claim(id="p", proposition=Did(actor=DAVID, action="touch", object="Knife", location="Kitchen", interval=(5, 6)),
                  sincerity="truthful", source="plan")
    assert confession_gated(_secret("murder", claims=(plain,)), _secret("murder", claims=(plain,)).cover.layers[1])
    assert confession_gated(_secret("protecting_other", claims=(sol,)), _secret("protecting_other", claims=(sol,)).cover.layers[1])
    assert not confession_gated(_secret("theft", claims=(plain,)), _secret("theft", claims=(plain,)).cover.layers[1])


def test_an_innocents_confession_terminal_peels_as_a_concession_on_every_golden():
    """manor_wing_s4's Delphine used to STONEWALL forever at a `confession` terminal the solver's I-45 fixpoint
    credits as cracked: the murder gate (I-21) was being applied to every secret."""
    from eidolon.solve import bots
    from eidolon.decision.cover_consistency import derive_breaker_sets, deliverable_accounts
    from eidolon.solve.session import decision_context, new_session
    from tests.solve.helpers import GOLDEN, loaded
    seen = 0
    for skel, seed in GOLDEN:
        p = loaded(skel, seed).package
        dctx = decision_context(p)
        dctx = replace(dctx, accounts=tuple(sorted(deliverable_accounts(list(p.secrets), dctx))))
        for sec in p.secrets:
            if sec.kind == "murder" or sec.cover.layers[-1].terminal != "confession":
                continue
            seen += 1
            st, peeled, *_rest, tried = bots.peel_secret(new_session(p), p, sec, derive_breaker_sets(sec, 0, dctx))
            assert peeled, (skel, seed, sec.id, tried)
            statements = st.decision.statements.for_speaker(sec.owner)
            assert any(s.act == "CONCESSION" for s in statements) and not any(s.act == "CONFESSION" for s in statements)
    assert seen, "no golden has an innocent with a confession terminal"


# ----------------------------------------------------------------------------------------- C10
def test_a_stonewalled_character_still_answers_questions_that_are_not_about_the_stonewalled_secret():
    from tests.decision.test_phase5_readiness import _gate, _state, ELENA
    s = _state()
    pushed = run_ask_turn(s, ELENA, Query(kind="did_you", raw="Your prints are on the knife."), presented_ref="E_knife",
                          confession_check=_gate([]))
    assert pushed.plan_act == "STONEWALL"
    later = run_ask_turn(pushed.state, ELENA, Query(kind="smalltalk", raw="Lovely garden."), confession_check=_gate([]))
    assert later.plan_act != "STONEWALL"


# ----------------------------------------------------------------------------------------- C8 / C6
def _mem(mid, strength, **cue):
    return Memory(id=mid, character=DAVID, kind="semantic", content=(f"B{mid}",), encoded_at=0, salience=strength,
                  strength_0=strength, cues=CueSet(**cue))


def test_retrieval_is_argmax_not_list_order_and_picks_the_best_matching_belief():
    cue = dict(entities=("Harold",), location="Hall", time_bucket="b0", topic_tags=("at",))
    weak_but_first = _mem("M1", 6000, **cue)
    strong = _mem("M2", 9000, **cue)
    beliefs = BeliefStore([
        Belief(id="BM1", character=DAVID, proposition=At(actor="Harold", location="Hall", interval=(0, 5)),
               confidence_0=9000, grounds=("K1",), formed_at=0, is_true=True),
        Belief(id="BM2", character=DAVID, proposition=At(actor="Harold", location="Hall", interval=(1, 6)),
               confidence_0=9000, grounds=("K2",), formed_at=0, is_true=True)])
    q = Query(kind="did_they", subject=EntityRef(id="Harold", kind="actor"), location="Hall", predicate_hint="presence",
              time=tp(0, 30), raw="Harold?")
    for order in itertools.permutations((weak_but_first, strong)):
        r = retrieve_for_query(DAVID, tuple(order), beliefs, EpistemicState(), q)
        assert r.band == "strong" and r.claim.id == "ret:BM2", [m.id for m in order]


def test_retrieval_picks_the_belief_whose_cues_overlap_the_question_most():
    mem = Memory(id="M", character=DAVID, kind="episodic", content=("Bfar", "Bnear"), encoded_at=0, salience=10000,
                 strength_0=10000, cues=CueSet(entities=("Harold",), location="Hall", time_bucket="b0", topic_tags=("at",)))
    beliefs = BeliefStore([
        Belief(id="Bfar", character=DAVID, proposition=Saw(observer=DAVID, subject="figure", location="Kitchen",
                                                            interval=(40, 41), identified=False),
               confidence_0=9000, grounds=("K1",), formed_at=0, is_true=True),
        Belief(id="Bnear", character=DAVID, proposition=At(actor="Harold", location="Hall", interval=(0, 5)),
               confidence_0=9000, grounds=("K2",), formed_at=0, is_true=True)])
    q = Query(kind="did_they", subject=EntityRef(id="Harold", kind="actor"), location="Hall", predicate_hint="presence",
              time=tp(0, 30), raw="")
    assert retrieve_for_query(DAVID, (mem,), beliefs, EpistemicState(), q).claim.id == "ret:Bnear"   # not content[0]


def test_an_unspeakable_best_belief_is_skipped_for_the_next_best_speakable_one():
    cue = dict(entities=("Harold",), location="Hall", time_bucket="b0", topic_tags=("at",))
    beliefs = BeliefStore([
        Belief(id="Bsecret", character=DAVID, proposition=At(actor="Harold", location="Hall", interval=(0, 5)),
               confidence_0=9000, grounds=("K1",), formed_at=0, is_true=True),
        Belief(id="Bok", character=DAVID, proposition=At(actor="Harold", location="Hall", interval=(1, 6)),
               confidence_0=9000, grounds=("K2",), formed_at=0, is_true=True)])
    mems = (_mem("Bsecret".replace("B", "M"), 9000, **cue).model_copy(update={"content": ("Bsecret",)}),
            _mem("Mok", 8000, **cue).model_copy(update={"content": ("Bok",)}))
    q = Query(kind="did_they", subject=EntityRef(id="Harold", kind="actor"), location="Hall", predicate_hint="presence",
              time=tp(0, 30), raw="")
    r = retrieve_for_query(DAVID, mems, beliefs, EpistemicState(), q, lambda c: c.id != "ret:Bsecret")
    assert r.claim.id == "ret:Bok"
    none = retrieve_for_query(DAVID, mems, beliefs, EpistemicState(), q, lambda c: False)
    assert none.band == "none" and none.claim is None


def test_a_natural_presence_hint_reaches_the_at_topic():
    """C6: `predicate_hint="presence"` tagged the question `topic:presence`; memories tag `topic:at`. Jaccard could never
    reach `strong`."""
    cues = lambda h: query_cues(Query(kind="where", predicate_hint=h, raw="")).topic_tags
    assert cues("presence") == ("at",) and cues("Whereabouts") == ("at",) and cues("who") == ("at",)
    assert cues("heard") == ("heard",) and cues("did") == ("did",) and cues("clean") == ("did",)
    assert cues("saw") == ("saw",) and cues("kitchen") == ("kitchen",)             # unknown hints pass through unchanged
    assert query_cues(Query(kind="where", raw="")).topic_tags == ()


def test_lie_needs_a_claim_that_covers_even_when_the_secret_is_topical():
    """RB2-c: the secret protects (5,6) so a question about (4,10) is TOPICAL, but the cover claim only speaks to (0,3),
    so no claim covers the asked proposition and LIE is not a candidate (§10.3)."""
    from eidolon.decision.strategy import StrategyInput, _lie
    s = build_demo_state()
    deny = Claim(id="c0", proposition=DidNot(actor=DAVID, action="touch", object="Knife", interval=(0, 3)),
                 sincerity="deceptive", source="plan")
    sec = Secret(id="S", owner=DAVID, kind="theft", protected=(DidNot(actor=DAVID, action="touch", object="Knife", interval=(5, 6)),),
                 stakes=Stakes(), cover=CoverStory(layers=(CoverLayer(index=0, claims=(deny,), resolve=6000),
                                                          CoverLayer(index=1, resolve=10000, terminal="stonewall"))))
    mk = lambda iv: StrategyInput(query=Query(kind="did_you", time=tp(*iv), raw="?"), character=DAVID,
                                  state=s.characters[DAVID], secret=sec, layer_reached=0, peel=None, presented_ref=None,
                                  retrieval="none", retrieved_claim=None, known_topic=True)
    assert secret_topical(sec, 0, mk((4, 10)).query, DAVID)
    assert _lie(mk((4, 10))) is None
    assert _lie(mk((0, 2))) is not None


# ===================================================================== ADR-30: a lie answers only its own topic
def _lie_input(prop_kind_claim, hint):
    from eidolon.decision.strategy import StrategyInput
    from eidolon.minds.character import Personality, initial_character_state
    lie = Claim(id="c0", proposition=prop_kind_claim, sincerity="deceptive", source="plan")
    sec = Secret(id="S1", owner=DAVID, kind="murder", protected=(lie.proposition,), stakes=Stakes(legal=1.0),
                 cover=CoverStory(layers=(CoverLayer(index=0, claims=(lie,), resolve=6000),
                                          CoverLayer(index=1, claims=(), resolve=10000, terminal="stonewall"))))
    st = initial_character_state(DAVID, Personality(composure_base=0.5, volatility=0.3, deference=0.5, guile=0.3,
                                                    talkativeness=0.5, self_preservation=0.5))
    q = Query(kind="did_they", subject=EntityRef(id=DAVID, kind="actor"), predicate_hint=hint, raw="?")
    return StrategyInput(query=q, character=DAVID, state=st, secret=sec, layer_reached=0, peel=None, presented_ref=None,
                         retrieval="none", retrieved_claim=None, known_topic=True)


DENY = DidNot(actor=DAVID, action="touch", object="Knife", interval=(0, 20))
ALIBI = At(actor=DAVID, location="Kitchen", interval=(0, 20))


@pytest.mark.parametrize("claim,hint,lies", [
    (DENY, "heard", False),           # "what did you hear?" is not answered with a deed denial (the reported defect)
    (DENY, "presence", False),        # nor "where were you?"
    (DENY, "did", True),              # "what did you do?" is
    (ALIBI, "presence", True),        # an alibi answers a whereabouts question
    (ALIBI, "heard", False),          # and not a hearing one
    (DENY, None, True),               # a question that names no topic: unchanged (any covering lie)
    (DENY, "bluff7", True),           # an unknown hint names no topic: the bluff bot's parity is untouched
])
def test_adr30_a_lie_answers_only_a_question_on_its_own_topic(claim, hint, lies):
    from eidolon.decision.strategy import select_plan
    plan, scored = select_plan(_lie_input(claim, hint))
    assert ("LIE" in {c.act for c, _ in scored}) is lies, (hint, [c.act for c, _ in scored])
    assert (plan.act == "LIE") is lies


def test_adr30_off_topic_the_murderer_does_not_lie_and_says_nothing_he_protects():
    """Through the real turn on a sealed case: the murderer's layer 0 lies on two topics (a deed denial and, since NR-I4,
    where he was). Asked what he HEARD he neither lies nor voices anything protected or observed in his protected window
    (speakable); asked where he was or what he did, he tells only that topic's lie."""
    from pathlib import Path
    from eidolon.solve.package import load_sealed_case
    from eidolon.solve.session import new_session
    root = Path(__file__).resolve().parents[2]
    st = new_session(load_sealed_case(str(root / "cases" / "generated" / "study_party_s4.json")), seed=7)
    murder = next(s for s in st.secrets.all() if s.kind == "murder")
    who = murder.owner
    lies = {c.proposition.kind: c.id for c in murder.cover.layers[0].claims}
    assert set(lies) == {"DidNot", "At"}, "fixture: a deed denial and a whereabouts lie"
    r = run_ask_turn(st, who, Query(kind="what", subject=EntityRef(id=who, kind="actor"), predicate_hint="heard", raw="?"))
    assert not r.rejected and r.plan_act != "LIE", r.plan_act
    said = {c.proposition for c in r.state.decision.statements.all()[-1].claims}
    assert not said & set(murder.protected)
    for hint, kind in (("presence", "At"), ("did", "DidNot")):
        r = run_ask_turn(st, who, Query(kind="what", subject=EntityRef(id=who, kind="actor"), predicate_hint=hint, raw="?"))
        assert r.plan_act == "LIE", (hint, r.plan_act)
        assert [c.id for c in r.state.decision.statements.all()[-1].claims] == [lies[kind]], hint
