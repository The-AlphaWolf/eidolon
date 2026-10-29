"""NR-I2 / NR-I4 (`docs/EIDOLON-FULL-REVIEW-2026-10-22.md`): a generated case gives the "heard" topic something true to answer, and
the murderer's cover also lies on the whereabouts topic (ADR-30 lets a lie answer only its own topic) - without adding a breaker
set, so the case's economics (V-3, the bands) are what they were."""
from __future__ import annotations

import pytest

from eidolon.decision.cover_consistency import derive_breaker_sets
from eidolon.decision.query import EntityRef, Query
from eidolon.decision.secrets import CoverLayer, CoverStory
from eidolon.decision.turn import run_ask_turn
from eidolon.solve.queries import BUCKET, time_phrase
from eidolon.solve.session import decision_context, new_session
from tests.solve.helpers import GOLDEN, loaded


@pytest.mark.parametrize("skel,seed", GOLDEN)
def test_NR_I2_every_innocent_heard_the_others_talking(skel, seed):
    sealed = loaded(skel, seed)
    st = new_session(sealed, seed=7)
    murderer = sealed.package.solution.murderer
    innocents = sorted(a for a in st.case.living_actors() if a != murderer)
    heard = {e.character for e in st.knowledge.all() if e.proposition.kind == "Heard" and e.character in innocents}
    assert len(heard) >= len(innocents) - 1, (innocents, heard)


@pytest.mark.parametrize("skel,seed", GOLDEN)
def test_NR_I2_what_did_you_hear_gets_a_true_answer(skel, seed):
    sealed = loaded(skel, seed)
    st = new_session(sealed, seed=7)
    chat = next(e for e in st.case.events if e.id == "chat")
    murderer = sealed.package.solution.murderer
    listener = sorted(a for a in st.case.living_actors() if a not in (murderer, chat.actor))[0]
    # recall is cue-driven (§8.4): a specific question - you, that room, that half hour, heard - not a bare "what did you hear?"
    q = Query(kind="did_you", subject=EntityRef(id=listener, kind="actor"), location=chat.location, predicate_hint="heard",
              raw="Did you hear anything in there around then?", time=time_phrase(chat.interval[0] // BUCKET))
    r = run_ask_turn(st, listener, q)
    assert not r.rejected and r.plan_act in ("TRUTH", "VAGUE"), r.plan_act
    said = r.state.decision.statements.all()[-1].claims
    assert said and all(c.proposition.kind == "Heard" for c in said), said


def _murder(p):
    return next(s for s in p.secrets if s.kind == "murder")


@pytest.mark.parametrize("skel,seed", GOLDEN)
def test_NR_I4_the_murderer_lies_about_where_they_were_and_the_lie_adds_no_breaker(skel, seed):
    p = loaded(skel, seed).package
    murder = _murder(p)
    layer0 = murder.cover.layers[0]
    alibi = [c for c in layer0.claims if c.proposition.kind == "At"]
    assert len(alibi) == 1 and alibi[0].sincerity == "deceptive"
    ctx = decision_context(p)
    without = murder.model_copy(update={"cover": CoverStory(layers=(CoverLayer(**{**layer0.model_dump(),
        "claims": tuple(c for c in layer0.claims if c.proposition.kind != "At")}),) + murder.cover.layers[1:])})
    assert derive_breaker_sets(murder, 0, ctx) == derive_breaker_sets(without, 0, ctx)


@pytest.mark.parametrize("skel,seed", GOLDEN)
def test_NR_I4_asked_where_they_were_the_murderer_lies_on_topic(skel, seed):
    sealed = loaded(skel, seed)
    st = new_session(sealed, seed=7)
    murderer = sealed.package.solution.murderer
    lie = next(c for c in _murder(sealed.package).cover.layers[0].claims if c.proposition.kind == "At")
    q = Query(kind="where", predicate_hint="at", raw="Where were you?", time=time_phrase(lie.proposition.interval[0] // BUCKET))
    r = run_ask_turn(st, murderer, q)
    assert not r.rejected and r.plan_act == "LIE", r.plan_act
    assert [c.id for c in r.state.decision.statements.all()[-1].claims] == [lie.id]

