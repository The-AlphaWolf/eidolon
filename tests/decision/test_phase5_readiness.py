"""Regression tests for the four Phase-5-readiness findings of the Phase 4 hostile review:

- I-3  the lexical guard was a deny-list and could not see an invented entity (§14.2(b));
- I-4  §14.2(e)'s leak check was a containment re-check; nothing audited the envelope (§21.2);
- I-5  the confession gate took no arguments, so one suspect's proof opened anyone's (I-21);
- N-2  a gate-open peel onto a confession layer carrying a `Solution` was rejected every turn.

Each docstring names the finding and the failure it reproduces; every test here failed on the
pre-fix code (verified by `tests/decision/mutation_check.py`'s `R-P5-*` reversions). Expected
values come from the architecture and hand-built fixtures. Do not weaken an assertion here to
make a change pass.
"""
from __future__ import annotations

import json
from dataclasses import replace

import pytest
from hypothesis import given, settings, strategies as st

from eidolon.decision import turn as turn_mod
from eidolon.decision.claims import Claim
from eidolon.decision.context import DecisionContext
from eidolon.decision.demo import build_demo_state
from eidolon.decision.digest import ConversationDigest, build_digest
from eidolon.decision.envelope import Envelope, EnvelopeClaim, PersonaSlot, build_envelope
from eidolon.decision.llm import Draft, Segment, TemplateLLM
from eidolon.decision.peel import evaluate_peel, layer_index
from eidolon.decision.query import Query
from eidolon.decision.secrets import CoverLayer, CoverStory, Deflection, Secret, SecretStore, Stakes
from eidolon.decision.solver import UniquenessResult
from eidolon.decision.strategy import DeliveryDirective, ResponsePlan, StrategyInput, _deflect
from eidolon.decision.turn import GameState, run_ask_turn
from eidolon.decision.validator import (
    _NON_ENTITY_WORDS, _name_index, audit_envelope, lexical_guard, validate_draft,
)
from eidolon.minds.character import Personality, initial_character_state
from eidolon.world.alias import Alias
from eidolon.world.entities import Actor
from eidolon.world.frozen import FrozenDict
from eidolon.world.propositions import At, Did, DidNot, Solution
from tests.decision.fixtures.vance_walkthrough import DAVID, ELENA, MARGARET, build_initial_state

# =====================================================================================
# I-3 — entity allow-list (§14.2(b))
# =====================================================================================

VANCE = build_initial_state()
LIB = Claim(id="c_lib", proposition=At(actor=DAVID, location="Library", interval=(5, 60)),
            sincerity="deceptive", source="plan")


def _lie_plan_env(claims=(LIB,)):
    plan = ResponsePlan(act="LIE", claims=claims, delivery=DeliveryDirective("composed"))
    return plan, build_envelope(plan, persona=PersonaSlot(), digest=ConversationDigest(character=DAVID, turns=0))


def _validate(draft, plan, env, state=VANCE, **kw):
    return validate_draft(draft, env, plan, DAVID, state.case, state.decision.statements, ctx=state.ctx(), **kw)


def _faithful(env, *extra: Segment, state=VANCE) -> Draft:
    return Draft(segments=TemplateLLM().generate(env, state.case, DAVID).segments + extra)


@pytest.mark.parametrize("kind", ["color", "assert", "question", "nonverbal"])
def test_i3_invented_entity_fails_in_every_segment_kind(kind):
    """I-3, the review's own repro: "I was with Mr Fothergill in the orangery at half past."
    (kind="color") produced NO violation — the guard only listed names the case contains, so a
    name it does not contain was invisible. Unknown names fail "in any segment kind" (§14.2(c))."""
    plan, env = _lie_plan_env()
    claim_ids = ("c_lib",) if kind == "assert" else ()
    seg = Segment(text="I was with Mr Fothergill in the orangery at half past.", claim_ids=claim_ids, kind=kind)
    violations = lexical_guard(Draft(segments=(seg,)), VANCE.case, frozenset({DAVID, "Library"}))
    assert any(v.startswith("UNKNOWN_ENTITY[0]") and "Fothergill" in v for v in violations)


def test_i3_invented_entity_never_reaches_the_player_or_the_ledger():
    """I-3: the draft is rejected as a RENDERER failure — the deterministic fallback speaks the
    valid plan (§14.3), so the invented name is neither shown nor committed."""
    plan, env = _lie_plan_env()
    draft = _faithful(env, Segment(text="Colonel Mustard can vouch for me.", kind="color"))
    result = _validate(draft, plan, env)
    assert any("UNKNOWN_ENTITY" in v and "Mustard" in v for v in result.violations)
    assert result.fallback is True and result.rejected is False
    assert "Mustard" not in result.text and result.claim_ids == ("c_lib",)


def test_i3_run_ask_turn_never_speaks_an_invented_entity(monkeypatch):
    """I-3 end to end: a renderer that invents a witness. Pre-fix the turn spoke it verbatim."""
    class Inventive(TemplateLLM):
        def generate(self, envelope, case, speaker):
            base = super().generate(envelope, case, speaker)
            return Draft(segments=base.segments + (Segment(text="Ask Lady Ashcombe, she saw me.", kind="color"),))

    monkeypatch.setattr(turn_mod, "TemplateLLM", Inventive)
    r = run_ask_turn(build_initial_state(), DAVID, Query(kind="where", raw="Where were you?"))
    assert r.rejected is False and r.text
    assert "Ashcombe" not in r.text


def test_i3_known_but_unpermitted_entity_still_fails():
    """Negative control: the allow-list is permitted ∩ resolvable, not merely resolvable. Harold
    is in the case but not in this envelope or the query."""
    plan, env = _lie_plan_env()
    result = _validate(_faithful(env, Segment(text="Harold Vance was upset.", kind="color")), plan, env)
    assert any("UNKNOWN_ENTITY" in v and "Harold" in v for v in result.violations)


def test_i3_alias_table_is_the_resolver():
    """§4.4/§14.2(c): names resolve through the case's `Alias` table. "Mr Kessler" resolves to David
    (the speaker) when the table says so, and is an unknown entity when it does not."""
    plan, env = _lie_plan_env()
    seg = Segment(text="Mr Kessler keeps to himself.", kind="color")
    aliased = VANCE.case.model_copy(update={"alias": Alias(names=FrozenDict({"mr kessler": DAVID}))})
    assert lexical_guard(Draft(segments=(seg,)), aliased, frozenset({DAVID})) == []
    assert any("Kessler" in v for v in lexical_guard(Draft(segments=(seg,)), VANCE.case, frozenset({DAVID})))
    # an alias that resolves to someone NOT permitted is not a free pass
    other = VANCE.case.model_copy(update={"alias": Alias(names=FrozenDict({"mr kessler": "Robert"}))})
    assert any("UNKNOWN_ENTITY" in v for v in lexical_guard(Draft(segments=(seg,)), other, frozenset({DAVID})))


def test_i3_faithful_template_output_passes_the_allow_list():
    """Negative control: nothing the engine's own renderer produces trips the guard — verbs are
    rendered lowercase ("I never use ..."), names come from the case table."""
    s = build_initial_state()
    d = s.secrets.for_owner(DAVID)[0]
    for layer in d.cover.layers:
        if not layer.claims:
            continue
        plan, env = _lie_plan_env(layer.claims)
        assert lexical_guard(_faithful(env, state=s), s.case, frozenset({DAVID})
                             | {e for c in layer.claims for e in _entities(c)}) == []


def _entities(c):
    from eidolon.world.propositions import entities
    a, l, o, amb = entities(c.proposition)
    return a | l | o | amb


_NAMES = frozenset(_name_index(VANCE.case))


@settings(max_examples=80, deadline=None)
@given(name=st.from_regex(r"[A-Z][a-z]{3,10}", fullmatch=True).filter(
           lambda n: n.lower() not in _NON_ENTITY_WORDS and not any(n.lower() in k for k in _NAMES)),
       kind=st.sampled_from(["assert", "color", "question", "nonverbal"]),
       template=st.sampled_from(["{} was there.", "I saw {} leave.", "Ask {}.", "Perhaps {} knows.", "(glances at {})"]))
def test_i3_property_no_unresolvable_capitalised_name_passes(name, kind, template):
    """Property (I-3): any capitalised token that resolves to no case entity and is not a
    closed-class word fails the guard, whatever the segment kind and wherever it sits."""
    seg = Segment(text=template.format(name), kind=kind, claim_ids=("c_lib",) if kind == "assert" else ())
    assert any(name in v for v in lexical_guard(Draft(segments=(seg,)), VANCE.case, frozenset({DAVID})))


# =====================================================================================
# I-4 — §14.2(e) leak check and the envelope boundary (§21.2)
# =====================================================================================

MURDER_TRUTH = At(actor=DAVID, location="Study", interval=(71, 72))      # true in Vance; hidden
ROBERT_GAZEBO = At(actor="Robert", location="Gazebo", interval=(55, 80))  # true; only Robert's
MARGARET_PROTECTED = At(actor=MARGARET, location="Room", interval=(30, 90))  # Margaret's secret


def _claim(cid, prop, sincerity="truthful"):
    return Claim(id=cid, proposition=prop, sincerity=sincerity, source="plan")


def _check(plan, speaker, state=VANCE, frame=()):
    env = build_envelope(plan, persona=PersonaSlot(), digest=ConversationDigest(character=speaker, turns=0), frame=frame)
    draft = TemplateLLM().generate(env, state.case, speaker)
    return validate_draft(draft, env, plan, speaker, state.case, state.decision.statements, ctx=state.ctx())


def test_i4_hidden_canonical_truth_is_rejected():
    """I-4: Elena has no provenance for where David was when Harold died. Pre-fix, (e) checked
    only `Solution`, so a plan asserting the murder location/time committed."""
    result = _check(ResponsePlan(act="DEFLECT", claims=(_claim("x", MURDER_TRUTH),)), ELENA)
    assert "UNKNOWABLE_CLAIM:At" in result.violations
    assert result.rejected is True and result.claim_ids == ()


def test_i4_other_characters_private_knowledge_is_rejected():
    """I-4: Robert's whereabouts are Robert's knowledge; David has no entry for them."""
    result = _check(ResponsePlan(act="DEFLECT", claims=(_claim("x", ROBERT_GAZEBO),)), DAVID)
    assert "UNKNOWABLE_CLAIM:At" in result.violations and result.rejected is True


def test_i4_another_characters_protected_fact_is_rejected_even_when_false_and_authorized():
    """I-4, rule 3: a claim naming another character's PROTECTED fact without a knowledge entry
    — false here, so the unknowable rule does not fire; and listing it in `authorized_reveals`
    does not lift it (a plan may reveal its own speaker's secrets, never someone else's)."""
    leaky = _claim("x", MARGARET_PROTECTED, "deceptive")
    plan = ResponsePlan(act="SLIP", claims=(leaky,), authorized_reveals=(MARGARET_PROTECTED,))
    result = _check(plan, DAVID)
    assert "FOREIGN_PROTECTED:At" in result.violations and result.rejected is True


def test_i4_the_deflect_route_the_review_named():
    """I-4 via the review's route: `_deflect` carries `Deflection.claims` straight into the plan,
    and V-3 checks only the deflection's basis. The validator is where it must stop."""
    s = build_initial_state()
    d = s.secrets.for_owner(DAVID)[0].model_copy(update={"deflections": (
        Deflection(target="Robert", basis=(), claims=(_claim("dfl", ROBERT_GAZEBO),)),)})
    cand = _deflect(StrategyInput(query=Query(kind="where", raw="?"), character=DAVID, state=s.characters[DAVID],
                                  secret=d, layer_reached=0, peel=None, presented_ref=None, retrieval="none",
                                  retrieved_claim=None, known_topic=True))
    result = _check(ResponsePlan(act=cand.act, claims=cand.claims), DAVID, state=s)
    assert result.rejected is True and "UNKNOWABLE_CLAIM:At" in result.violations


def test_i4_negative_controls_own_knowledge_and_own_participation_pass():
    """Negative controls: Elena may say what she knows (her own entry), David may state his own
    whereabouts (participation), and a CONFESSION may carry its Solution."""
    elena = _check(ResponsePlan(act="TRUTH", claims=(VANCE.knowledge.get("K_kitchen_elena") and
                                                    _claim("k", VANCE.knowledge.get("K_kitchen_elena").proposition),)), ELENA)
    assert elena.ok is True
    assert _check(ResponsePlan(act="LIE", claims=(_claim("m", MURDER_TRUTH),)), DAVID).ok is True
    sol = Solution(murderer=DAVID, method="bookend", location="Study", interval=(70, 71), motive_kind="money")
    conf = ResponsePlan(act="CONFESSION", claims=(_claim("s", sol),), authorized_reveals=(sol,))
    assert _check(conf, DAVID).ok is True


def test_i4_sincerity_grounding_and_source_never_cross_the_boundary():
    """I-4 (envelope audit): the envelope handed every `Claim` field to the renderer, including
    `sincerity="deceptive"` — which claims are lies — and `source`/`grounding` (§10.3: "never
    given to the LLM"). The renderer now receives a projection with none of them."""
    plan, env = _lie_plan_env()
    dumped = json.dumps(env.model_dump(mode="json"))
    assert set(EnvelopeClaim.model_fields) == {"id", "proposition", "modality", "confidence"}
    for leaked in ("sincerity", "deceptive", "grounding", "source"):
        assert leaked not in dumped


def _audit(env, plan, digest, state=VANCE, speaker=DAVID, frame=()):
    return audit_envelope(env, plan, frame, digest, speaker, state.ctx())


def _clean(state=VANCE, speaker=DAVID):
    plan = ResponsePlan(act="LIE", claims=(LIB,), delivery=DeliveryDirective("composed"))
    digest = build_digest(speaker, 0, {}, state.characters[speaker].detective_model, state.decision.statements, [])
    return plan, digest, build_envelope(plan, persona=PersonaSlot(), digest=digest)


def test_i4_audit_accepts_what_the_turn_builds():
    """Negative control: an honestly built envelope passes the audit untouched."""
    plan, digest, env = _clean()
    assert _audit(env, plan, digest) == []


@pytest.mark.parametrize("field,value,code", [
    ("allowed_claims", lambda env: env.allowed_claims + (EnvelopeClaim.of(_claim("pad", ROBERT_GAZEBO)),),
     "ENVELOPE_CLAIMS_NOT_PLAN"),
    ("authorized_reveals", lambda env: (MURDER_TRUTH,), "ENVELOPE_REVEALS_NOT_PLAN"),
    ("persona", lambda env: PersonaSlot(public_facts=(ROBERT_GAZEBO,)), "UNKNOWABLE_CLAIM:At"),
    ("retrieved_statements", lambda env: ("I cleaned that glass just after eleven.",), "ENVELOPE_FOREIGN_TEXT"),
    ("recent_exchange", lambda env: ("Robert was in the gazebo all evening.",), "ENVELOPE_FOREIGN_TEXT"),
    ("digest_text", lambda env: env.digest_text + " Robert was in the gazebo.", "ENVELOPE_DIGEST_NOT_SPEAKERS"),
    ("delivery", lambda env: DeliveryDirective("composed", ("glances toward the study",)),
     "ENVELOPE_STYLE_CARRIES_CONTENT"),
])
def test_i4_every_envelope_field_rejects_deliberate_leakage(field, value, code):
    """I-4: one deliberate leak per envelope field — padding, reveals, public facts, another
    character's words in the retrieval/exchange slots, a doctored digest, content smuggled into
    a delivery note. `props()` never looked at four of these slots (review B-6)."""
    plan, digest, env = _clean()
    leaky = env.model_copy(update={field: value(env)})
    assert code in _audit(leaky, plan, digest)


def test_i4_digest_of_another_character_or_naming_undiscovered_evidence_is_rejected():
    """I-4: the digest must be THIS speaker's, and may name only items the player holds."""
    plan, digest, env = _clean()
    elena_digest = digest.model_copy(update={"character": ELENA})
    assert "ENVELOPE_DIGEST_NOT_SPEAKERS" in _audit(env, plan, elena_digest)
    undiscovered = digest.model_copy(update={"evidence_presented": ("E6",)})
    env2 = build_envelope(plan, persona=PersonaSlot(), digest=undiscovered)
    assert "ENVELOPE_UNDISCOVERED_EVIDENCE" in _audit(env2, plan, undiscovered)


def test_i4_an_unaudited_envelope_field_fails_closed():
    """I-4, structural: a field the audit has no rule for — here, an `Envelope` subclass carrying
    a solver verdict — fails the whole envelope rather than passing unexamined."""
    class Leaky(Envelope):
        survivors: tuple[str, ...] = (DAVID,)

    plan, digest, env = _clean()
    leaky = Leaky(**env.model_dump())
    assert _audit(leaky, plan, digest) == ["ENVELOPE_SCHEMA_UNAUDITED"]


def test_i4_run_ask_turn_audits_before_the_renderer_sees_anything(monkeypatch):
    """I-4 end to end: an envelope builder that pads the retrieval slot with Elena's words. The
    turn fails closed — state untouched, nothing shown — and the renderer is never called."""
    real = turn_mod.build_envelope
    monkeypatch.setattr(turn_mod, "build_envelope", lambda plan, **kw: real(
        plan, **{**kw, "retrieved_statements": ("Robert was in the gazebo all evening.",)}))
    calls = []
    monkeypatch.setattr(TemplateLLM, "generate", lambda self, *a: calls.append(a) or Draft())
    state = build_initial_state()
    r = run_ask_turn(state, DAVID, Query(kind="where", raw="Where were you?"))
    assert r.rejected is True and r.state is state and r.text == "" and r.envelope is None
    assert "ENVELOPE_FOREIGN_TEXT" in r.violations and calls == []


def test_i4_run_ask_turn_rejects_a_leaking_plan_whatever_produced_it(monkeypatch):
    """I-4 end to end: the strategy (or a future bug in it) proposes a hidden truth."""
    monkeypatch.setattr(turn_mod, "select_plan",
                        lambda inp: (ResponsePlan(act="DEFLECT", claims=(_claim("x", ROBERT_GAZEBO),)), []))
    state = build_initial_state()
    r = run_ask_turn(state, DAVID, Query(kind="where", raw="Where were you?"))
    assert r.rejected is True and r.state is state and "UNKNOWABLE_CLAIM:At" in r.violations


# =====================================================================================
# I-5 — confession gate identity binding (I-21)   and   N-2 — gate-open confession
# =====================================================================================

KNIFE_TOUCH = Did(actor=DAVID, action="touch", object="Knife", location="Kitchen", interval=(0, 20))
KNIFE_DENY = DidNot(actor=DAVID, action="touch", object="Knife", interval=(0, 20))
SOLUTION = Solution(murderer=DAVID, method="knife", location="Study", interval=(10, 11), motive_kind="money")


def _confession_secret(owner, sid, resolve=6000):
    deny = Claim(id=f"{sid}_deny", proposition=KNIFE_DENY, sincerity="deceptive", source="plan")
    admit = Claim(id=f"{sid}_admit", proposition=At(actor=owner, location="Kitchen", interval=(5, 6)),
                  sincerity="truthful", source="plan")
    sol = Claim(id=f"{sid}_sol", proposition=SOLUTION, sincerity="truthful", source="plan")
    return Secret(id=sid, owner=owner, kind="murder" if owner == DAVID else "protecting_other",
                  protected=(KNIFE_TOUCH,), stakes=Stakes(legal=1.0),
                  cover=CoverStory(layers=(CoverLayer(index=0, claims=(deny,), resolve=resolve),
                                           CoverLayer(index=1, claims=(admit, sol), resolve=10000,
                                                      terminal="confession"))))


def _state(resolve=6000) -> GameState:
    """The demo world plus Elena, who covers for David ("he never touched the knife"). E_knife
    weighs 0.9 x 0.9 x 1.0 = 8100 bp against both covers' layer 0."""
    base = build_demo_state()
    case = base.case.model_copy(update={"actors": FrozenDict({**base.case.actors,
                                                              ELENA: Actor(id=ELENA, name="Elena Ruiz", role="suspect")})})
    chars = {**base.characters, ELENA: initial_character_state(ELENA, Personality(
        composure_base=0.5, volatility=0.3, deference=0.5, guile=0.4, talkativeness=0.4, self_preservation=0.5))}
    return replace(base, case=case, characters=chars, memories={DAVID: (), ELENA: ()},
                   secrets=SecretStore([_confession_secret(DAVID, "S_d", resolve), _confession_secret(ELENA, "S_e", resolve)]))


def _gate(survivors, unique=True):
    calls = []

    def check(actor, secret, presented, ctx):
        calls.append((actor, secret.id, presented, ctx))
        return UniquenessResult(unique=unique, survivors=tuple(survivors))
    check.calls = calls
    return check


def _peel(state, owner, gate, presented=frozenset({"E_knife"}), reached=0, secret=None):
    secret = secret or state.secrets.for_owner(owner)[0]
    return evaluate_peel(secret, presented, reached, owner, state.ctx(), gate)


def test_i5_one_suspects_proof_does_not_open_anothers_confession():
    """I-5, the review's repro: `ConfessionCheck = Callable[[], bool]` could not say whose
    confession a proof licenses — a proof that only David survives opened Elena's gate too. The
    same verdict now opens David's terminal layer and stonewalls Elena at hers."""
    s = _state()
    only_david = _gate([DAVID])
    assert (_peel(s, DAVID, only_david).to_index, _peel(s, DAVID, only_david).stonewalled) == (1, False)
    elena = _peel(s, ELENA, only_david)
    assert (elena.to_index, elena.peeled, elena.stonewalled) == (0, False, True)


def test_i5_the_gate_is_bound_to_the_confessing_owner_of_the_secret():
    """I-5, wrong context: a verdict naming Elena cannot open DAVID's secret when Elena is the
    one addressed — the secret must be the confessor's own. The solver is not even consulted."""
    s = _state()
    gate = _gate([ELENA])
    wrong = _peel(s, ELENA, gate, secret=s.secrets.get("S_d"))
    assert wrong.stonewalled is True and wrong.to_index == 0 and gate.calls == []


@pytest.mark.parametrize("verdict", [
    UniquenessResult(unique=False, survivors=(DAVID, ELENA)),
    UniquenessResult(unique=True, survivors=(DAVID, ELENA)),   # malformed: "unique" with two
    UniquenessResult(unique=True, survivors=()),
    True,                                                       # the old bare-bool interface
    None,
])
def test_i5_anything_but_a_unique_verdict_naming_the_confessor_stays_closed(verdict):
    s = _state()
    r = _peel(s, DAVID, lambda actor, secret, presented, ctx: verdict)
    assert (r.to_index, r.stonewalled) == (0, True)


def test_i5_the_gate_reads_this_turns_presented_set_and_context():
    """I-5, relevant decision state: the checker is asked about THIS turn — the confessor, their
    secret, the presented set and the turn's context — so a proof needing an item not presented
    this turn does not open the gate."""
    s = _state()
    seen = []

    def needs_proof(actor, secret, presented, ctx):
        seen.append((actor, secret.id, presented, ctx))
        return UniquenessResult(unique="E_proof" in presented, survivors=(DAVID,))

    assert _peel(s, DAVID, needs_proof).stonewalled is True
    assert _peel(s, DAVID, needs_proof, presented=frozenset({"E_knife", "E_proof"})).to_index == 1
    assert [(a, sid, p) for a, sid, p, _ in seen] == [
        (DAVID, "S_d", frozenset({"E_knife"})), (DAVID, "S_d", frozenset({"E_knife", "E_proof"}))]
    assert all(isinstance(c, DecisionContext) for *_, c in seen)


def test_i5_run_ask_turn_cross_character():
    """I-5 end to end, through the only public entry point: the same David-naming gate lets
    David's cover reach its confession layer and holds Elena's."""
    s = _state()
    gate = _gate([DAVID])
    q = Query(kind="did_you", raw="Your prints are on the knife.")
    elena = run_ask_turn(s, ELENA, q, presented_ref="E_knife", confession_check=gate)
    assert elena.rejected is False and elena.plan_act == "STONEWALL"
    assert layer_index(elena.state.decision.layer_peels, ELENA, "S_e") == 0
    david = run_ask_turn(s, DAVID, q, presented_ref="E_knife", confession_check=gate)
    assert layer_index(david.state.decision.layer_peels, DAVID, "S_d") == 1
    # control: a verdict naming Elena opens hers
    opened = run_ask_turn(s, ELENA, q, presented_ref="E_knife", confession_check=_gate([ELENA]))
    assert layer_index(opened.state.decision.layer_peels, ELENA, "S_e") == 1


def _committed(result):
    return [c for s in result.state.decision.statements.all() if s.turn == result.state.turn_counter for c in s.claims]


def test_n2_gate_open_is_not_itself_a_confession():
    """N-2 (1/3): an open gate is never by itself a CONFESSION. With nothing that reaches the last
    denial's `resolve` — nothing presented, or too little — a CLOSED gate (no proof) moves nothing.
    ADR-32 (2026-10-22): an OPEN gate there is a proof, and a proof breaks the last denial before a
    gated confession — the landing is still voiced as CONCESSION and commits no Solution (§14.2(e));
    only a character already standing on the confession layer confesses. (Before ADR-32 this test
    asserted that the gate was never consulted short of the confession layer; that is what
    ADR-32 changes, and why a murderer could never confess in a generated case.)"""
    for s, presented in ((_state(), None), (_state(resolve=9000), "E_knife")):
        q = Query(kind="did_you", raw="Did you do it?")
        closed = run_ask_turn(s, DAVID, q, presented_ref=presented, confession_check=_gate([DAVID], unique=False))
        assert closed.rejected is False and closed.plan_act not in ("CONFESSION", "CONCESSION", "STONEWALL")
        assert closed.state.decision.layer_peels == ()
        opened = run_ask_turn(s, DAVID, q, presented_ref=presented, confession_check=_gate([DAVID]))
        assert opened.rejected is False and opened.plan_act == "CONCESSION"
        assert [(p.from_index, p.to_index) for p in opened.state.decision.layer_peels] == [(0, 1)]
        for r in (closed, opened):
            assert not any(c.proposition.kind == "Solution" for c in _committed(r))


def test_n2_landing_on_the_confession_layer_is_a_concession_and_commits():
    """N-2 (2/3), the finding: with the gate open, the peel lands on the confession layer. §11.4
    voices every peel as CONCESSION ("if i > peeled_from: plan.act = CONCESSION"), and §14.2(e)
    allows a Solution only under CONFESSION — so pre-fix the concession carried the layer's
    Solution, was rejected, recorded nothing, and re-fired identically on every later turn. Now
    the landing commits as CONCESSION, records the peel, and says everything but the Solution."""
    s = _state()
    r = run_ask_turn(s, DAVID, Query(kind="did_you", raw="Your prints are on the knife."),
                     presented_ref="E_knife", confession_check=_gate([DAVID]))
    assert r.rejected is False and r.plan_act == "CONCESSION"
    assert [(p.from_index, p.to_index) for p in r.state.decision.layer_peels] == [(0, 1)]
    assert [c.id for c in _committed(r)] == ["S_d_admit"]
    assert "solution" not in r.text.lower()


def test_n2_the_confession_comes_from_the_confession_layer_and_stays_gated():
    """N-2 (3/3): standing on the confession layer with the gate still open, the character
    confesses — CONFESSION, Solution committed. If the proof is lost (retraction), the layer
    holds (I-38) but the confession does not happen (I-21): STONEWALL."""
    s = _state()
    q = Query(kind="did_you", raw="Well?")
    landed = run_ask_turn(s, DAVID, Query(kind="did_you", raw="Prints."), presented_ref="E_knife",
                          confession_check=_gate([DAVID])).state
    gate = _gate([DAVID])
    confessed = run_ask_turn(landed, DAVID, q, confession_check=gate)
    assert confessed.rejected is False and confessed.plan_act == "CONFESSION"
    assert SOLUTION in [c.proposition for c in _committed(confessed)]
    assert [a for a, *_ in gate.calls] == [DAVID]

    lost = run_ask_turn(landed, DAVID, q, confession_check=_gate([DAVID], unique=False))
    assert lost.plan_act == "STONEWALL"
    assert layer_index(lost.state.decision.layer_peels, DAVID, "S_d") == 1
    assert not any(c.proposition.kind == "Solution" for c in _committed(lost))


# =====================================================================================
# Found by the fresh audit of this repair (A-3 .. A-7): holes in the first version of the fix
# =====================================================================================

@pytest.mark.parametrize("text,name", [
    ("Will saw me leave.", "Will"),                 # A-3: a modal that is also a given name
    ("May knows where I was.", "May"),
    ("Émile was there.", "Émile"),                  # A-4: non-ASCII capitals were invisible
    ("I saw ÖLAF in the hall.", "ÖLAF"),
    ("Harold Vanceworth called.", "Vanceworth"),    # A-5: masked as "harold vance" + "worth"
])
def test_audit_invented_names_the_first_allow_list_missed(text, name):
    violations = lexical_guard(Draft(segments=(Segment(text=text, kind="color"),)), VANCE.case, frozenset({DAVID}))
    assert any("UNKNOWN_ENTITY" in v and name in v for v in violations)


def test_audit_a6_said_does_not_launder_a_hidden_fact():
    """A-6: `Said(speaker=David, ...)` is first-person for David, so the first version exempted
    it outright — and with it the reported content: Robert's whereabouts, or Margaret's secret."""
    from eidolon.world.propositions import Said
    for inner, code in ((ROBERT_GAZEBO, "UNKNOWABLE_CLAIM:At"), (MARGARET_PROTECTED, "FOREIGN_PROTECTED:At")):
        said = Said(speaker=DAVID, listener=ELENA, proposition=inner, t=60)
        assert code in _check(ResponsePlan(act="LIE", claims=(_claim("x", said, "deceptive"),)), DAVID).violations
    own = Said(speaker=DAVID, listener=ELENA, proposition=LIB.proposition, t=60)   # control: his own alibi
    assert _check(ResponsePlan(act="LIE", claims=(_claim("x", own, "deceptive"),)), DAVID).ok is True


def test_audit_a7_a_negated_claim_is_checked_as_the_negation_it_asserts():
    """A-7: "Robert was NOT in the house" asserts ¬At(Robert, Room) — true, and Robert's alone to
    know. The first version tested the bare proposition (false) and let it through. The same
    claim asserted positively is a lie about Robert, not a leak (control)."""
    robert_room = At(actor="Robert", location="Room", interval=(55, 80))
    negated = Claim(id="x", proposition=robert_room, modality="negated", sincerity="truthful", source="plan")
    assert "UNKNOWABLE_CLAIM:At" in _check(ResponsePlan(act="DEFLECT", claims=(negated,)), DAVID).violations
    assert _check(ResponsePlan(act="DEFLECT", claims=(_claim("x", robert_room, "deceptive"),)), DAVID).ok is True


def test_audit_style_may_name_what_the_envelope_already_carries():
    """Negative control for the style rule: §10.3's own delivery example names a person. A note
    naming an entity the claims already carry is style; one naming anything else is content."""
    plan, digest, env = _clean()
    assert _audit(env.model_copy(update={"delivery": DeliveryDirective("composed", ("glances at the library",))}),
                  plan, digest) == []
