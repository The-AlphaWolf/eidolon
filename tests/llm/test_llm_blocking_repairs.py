"""Regression guards for the three BLOCKING findings of the Phase 5 hostile review.

Each test names the finding it guards and reproduces the failure mode. Do not weaken an assertion
here to make a change pass — the same rule as `tests/decision/test_blocking_repairs.py` and
`tests/evidence/test_blocking_regressions.py`.

    F-1  the committed claim SEQUENCE came from model segment ordering, so two wordings of one
         plan recorded different `Statement.claims` (and, through `standing_claims_ordered`, a
         different digest once the five-claim budget truncates).
    F-2  `repair_feedback` expanded an entity id into its canonical display name, so a model that
         guessed a bare name learned both that the entity exists and what it is really called —
         an oracle, since an invented name was echoed back verbatim instead.
    F-3  `build_view` matched the player's raw line against the WHOLE case name index, so a player
         guessing an undiscovered real entity put that entity's name into the renderer's view.
"""
from __future__ import annotations

import inspect
import json
import re

import pytest

from eidolon.decision.digest import standing_claims_ordered
from eidolon.decision.query import EntityRef, Query
from eidolon.llm.fakes import REORDERINGS, ScriptedTransport, reordering
from eidolon.llm.render import LLMRenderer, ModelLLM, NameBook, permitted_ids, repair_feedback
from tests.llm.llm_helpers import (
    DAVID, MARGARET, WHERE, approve, ask, build_initial_state, draft_json, faithful, fingerprint, scripted,
)

VANCE = build_initial_state()

# Entities the Vance case really has but David's turn does not permit. The renderer is meant never
# to learn that any of these exist. (F-3's vector is the DISPLAY name, typed by the player.)
HIDDEN = [("hidden actor", "Margaret", "Margaret Vance"),
          ("hidden location", "Gazebo", "the gazebo"),
          ("hidden object", "bookend", "a bronze bookend")]
INVENTED = [("invented actor", "Mustard", "Colonel Mustard"),
            ("invented location", "Orangery", "the orangery"),
            ("invented object", "Candlestick", "a silver candlestick")]

# F-2's vector is the engine ID, written by the MODEL: an id-shaped capitalised token resolves to
# no surface form, so the allow-list refuses it and the old feedback expanded it into the display
# name. Each row picks a turn on which that entity is genuinely not permitted — David's turn
# carries the glass, so the hidden-object probe asks Margaret instead (her view is
# `['Margaret Vance', "Margaret's room"]`).
GUESS_HIDDEN = [("hidden actor", DAVID, "Margaret", "Margaret Vance"),
                ("hidden location", DAVID, "Gazebo", "the gazebo"),
                ("hidden object", MARGARET, "Glass1", "a drinking glass")]
GUESS_INVENTED = [("invented actor", DAVID, "Mustard", "Mustard"),
                  ("invented location", DAVID, "Orangery", "Orangery"),
                  ("invented object", MARGARET, "Candlestick", "Candlestick")]


def _render(gen, state=VANCE, who=DAVID, query=WHERE, **kw):
    t = ScriptedTransport(generate=[gen], verify=[approve] * 9, repeat_last=True)
    return ask(state, who, query, renderer=LLMRenderer(ModelLLM(t), **kw)), t


def _prompts(t, role="generate"):
    return [json.loads(q.user) for q in t.requests if q.role == role]


# =====================================================================================
# F-1 — the committed claim sequence is the plan's, never the draft's
# =====================================================================================
BASE = ask(VANCE, DAVID, WHERE)                      # the Phase 4 reference: two claims, LIE
PLAN_ORDER = [c.id for c in BASE.state.decision.statements.all()[-1].claims]


def test_f1_the_reordering_generators_are_genuinely_accepted():
    """Negative control. If these drafts fell back, every assertion below would be vacuous — the
    template would be speaking and the ordering question would never arise."""
    assert PLAN_ORDER == ["d_c0_kitchen", "d_c0_lib"]
    for shape in REORDERINGS:
        r, t = _render(reordering(shape))
        assert r.rejected is False and r.fallback is False, (shape, r.violations)
        assert r.render_audit[0].outcome == "accepted" and t.calls("generate") == 1
        # ...and the draft the engine accepted really did carry the claims in a different shape
        # from the plan's (`merged` says the same WORDS, one segment, ids reversed).
        draft = r.render_audit[0].attempts[0].draft
        assert [list(s.claim_ids) for s in draft.segments if s.kind == "assert"] != [[c] for c in PLAN_ORDER]


@pytest.mark.parametrize("shape", REORDERINGS)
def test_f1_committed_claim_order_is_the_plans_whatever_the_segment_order(shape):
    """F-1: reversed / rotated / merged-into-one-segment / split-with-an-interleaved-color all
    voice exactly the same claims. The ledger must not be able to tell them apart."""
    r, _ = _render(reordering(shape))
    committed = [c.id for c in r.state.decision.statements.all()[-1].claims]
    assert committed == PLAN_ORDER


@pytest.mark.parametrize("shape", REORDERINGS)
def test_f1_the_engine_fingerprint_is_identical_across_segment_shapes(shape):
    """The whole point of the renderer boundary: wording varies, decisions do not."""
    r, _ = _render(reordering(shape))
    assert fingerprint(r.state) == fingerprint(BASE.state)


def test_f1_every_shape_agrees_with_every_other_shape():
    states = {shape: fingerprint(_render(reordering(shape))[0].state) for shape in REORDERINGS}
    assert len(set(map(repr, states.values()))) == 1


def test_f1_standing_claims_ordered_is_stable_across_wordings():
    """`standing_claims_ordered` walks `Statement.claims` in order and truncates at
    STANDING_CLAIMS_BUDGET, so model-derived ordering would decide which claims reach the digest."""
    digests = set()
    for shape in REORDERINGS:
        state = VANCE
        for _ in range(4):                               # > the 5-claim budget after two turns
            state = _render(reordering(shape), state=state)[0].state
        digests.add(standing_claims_ordered(state.decision.statements, DAVID, None))
    reference = VANCE
    for _ in range(4):
        reference = ask(reference, DAVID, WHERE).state
    assert digests == {standing_claims_ordered(reference.decision.statements, DAVID, None)}


def test_f1_a_draft_that_drops_a_plan_claim_is_still_refused():
    """Adversarial negative: the commit path now filters the plan by what was voiced, so check that
    a model cannot use that filter to quietly drop a claim — the omission check fires first."""
    one_only = draft_json(("I never use a drinking glass.", ["d_c0_kitchen"], "assert"))
    r, t = _render(one_only)
    assert r.fallback is True and t.calls("verify") == 0
    assert any(v.startswith("PLAN_CLAIM_OMITTED") for v in r.render_audit[0].attempts[0].violations)
    assert [c.id for c in r.state.decision.statements.all()[-1].claims] == PLAN_ORDER


def test_f1_replay_of_the_recorded_events_reproduces_the_same_order():
    """I-22: the fold applies recorded outcomes. A reordered render must fold to the plan's order."""
    from eidolon.decision.events import ClaimMade, apply_decision
    r, _ = _render(reordering("reversed"))
    folded = VANCE.decision
    for ev in r.events:
        if isinstance(ev, ClaimMade):
            folded = apply_decision(folded, ev)
    assert [c.id for s in folded.statements.all() for c in s.claims] == PLAN_ORDER


# =====================================================================================
# F-2 — repair feedback reveals nothing about what exists or what it is called
# =====================================================================================
_SPOKEN = {DAVID: (("I never use a drinking glass.", ["d_c0_kitchen"], "assert"),
                   ("I was in the library from 00:05 until 02:00.", ["d_c0_lib"], "assert")),
           MARGARET: (("I was in Margaret's room from 00:30 until 01:30.", ["m_c0_room"], "assert"),)}


def _feedback_for(name: str, who=DAVID) -> list[str]:
    """One turn in which the model writes `<name> can vouch for me.` in a color segment. Returns
    the `revise` slot of the repair prompt, or `[]` if the draft raised no violation at all."""
    bad = draft_json(*_SPOKEN[who], (f"{name} can vouch for me.", [], "color"))
    r, t = _render(bad, who=who)
    prompts = _prompts(t)
    return prompts[1]["revise"] if len(prompts) > 1 else []


@pytest.mark.parametrize("label, who, entity_id, display", GUESS_HIDDEN)
def test_f2_a_guessed_hidden_entity_is_not_expanded_into_its_canonical_name(label, who, entity_id, display):
    """F-2's exact reproduction: the model writes a bare id-shaped token and used to get the full
    display name back ('Margaret' -> 'Margaret Vance', 'Glass1' -> 'a drinking glass')."""
    revise = _feedback_for(entity_id, who)
    assert revise, "the guess must actually violate, or this test proves nothing"
    blob = " ".join(revise)
    assert entity_id not in blob
    assert display not in blob and display.lower() not in blob.lower()


@pytest.mark.parametrize("hidden_row, invented_row", list(zip(GUESS_HIDDEN, GUESS_INVENTED)),
                          ids=[r[0] for r in GUESS_HIDDEN])
def test_f2_hidden_and_invented_names_produce_byte_identical_feedback(hidden_row, invented_row):
    """The oracle, put the only way that isolates it: the SAME turn, the same segment, the same
    sentence — the one and only difference being whether the name the model guessed is a real
    entity of the case. Pre-fix, the hidden row came back carrying that entity's display name."""
    _, who, hidden_id, _ = hidden_row
    _, other_who, invented_id, _ = invented_row
    assert who == other_who
    hidden, invented = _feedback_for(hidden_id, who), _feedback_for(invented_id, who)
    assert hidden and invented, (hidden, invented)
    assert hidden == invented


def test_f2_the_feedback_line_says_nothing_but_the_segment():
    assert _feedback_for("Margaret", DAVID) == [
        "Segment 2: it names something that is not in names; remove that reference and keep everything else."]


def test_f2_the_segment_index_is_the_only_thing_that_varies_between_turns():
    """Margaret's turn has one asserting segment and David's has two, so the colour segment sits at
    a different index. Nothing else about the feedback may differ."""
    strip = lambda lines: [re.sub(r"Segment \d+", "Segment N", x) for x in lines]
    david = strip(_feedback_for("Margaret", DAVID))
    margaret = strip(_feedback_for("Glass1", MARGARET))
    assert david == margaret


def test_f2_a_permitted_entity_named_in_the_wrong_slot_also_reveals_nothing():
    """`the library` IS in this turn's view; naming it in a `color` segment is still a violation,
    and its feedback must not quote it either."""
    bad = draft_json(("I never use a drinking glass.", ["d_c0_kitchen"], "assert"),
                     ("I was in the library from 00:05 until 02:00.", ["d_c0_lib"], "assert"),
                     ("The library always felt cold.", [], "color"))
    r, t = _render(bad)
    assert r.fallback is True
    blob = " ".join(_prompts(t)[1]["revise"]).lower()
    assert "library" not in blob


def test_f2_no_display_name_of_any_case_entity_can_appear_in_feedback():
    """Sweep: guess every entity id in the case and confirm nothing of it comes back. A lowercase
    id ("bookend") trips no deterministic check at all and yields no feedback — the documented
    §14.2(b) residual, not a leak — so those rows simply have nothing to inspect."""
    case = VANCE.case
    names = {e.name for table in (case.actors, case.locations, case.objects) for e in table.values()}
    tested = 0
    for entity_id in list(case.actors) + list(case.locations) + list(case.objects):
        revise = _feedback_for(entity_id)
        if not revise:
            assert entity_id.islower(), entity_id     # only the lowercase-id residual may be silent
            continue
        tested += 1
        blob = " ".join(revise)
        assert entity_id not in blob
        assert not any(n in blob for n in names), (entity_id, blob)
    assert tested >= 14


def test_f2_repair_feedback_is_given_no_case_no_name_book_and_no_envelope():
    """Structural, not lexical: there is no parameter through which case data could arrive, so the
    boundary cannot be re-opened by a future caller passing one."""
    params = list(inspect.signature(repair_feedback).parameters)
    assert params == ["violations", "deny"]
    for banned in ("book", "case", "envelope", "names", "ctx"):
        assert banned not in params


def test_f2_feedback_is_a_function_of_the_violation_code_and_index_alone():
    """Same code, wildly different details -> the same line."""
    a = repair_feedback(("UNKNOWN_ENTITY[2]:['Margaret']",))
    b = repair_feedback(("UNKNOWN_ENTITY[2]:['Mustard', 'Colonel']",))
    c = repair_feedback(("UNKNOWN_ENTITY[2]:['Gazebo', 'bookend', 'Elena']",))
    assert a == b == c
    assert repair_feedback(("UNKNOWN_ENTITY[3]:['Margaret']",)) != a      # the index still varies


def test_f2_a_code_with_no_template_yields_no_feedback():
    assert repair_feedback(("REFUSAL_WITH_NO_TEMPLATE",)) == ()


def test_f2_no_template_interpolates_anything_but_the_segment_index():
    """The structural statement of the repair, and the tripwire that keeps it true.

    Every template is a constant apart from `{i}`, an integer, so there is no substitution site
    through which a violation's detail — an id, a token the model wrote, an entity name — could
    re-enter the prompt. This is also WHY the pre-existing engine-vocabulary backstop in
    `repair_feedback` is now unreachable (mutation P5-22 is marked EQUIVALENT for exactly this
    reason): with no interpolation there is nothing for it to catch. Re-introduce a placeholder
    and this test fails and P5-22 stops being equivalent — either way it surfaces."""
    from eidolon.llm.render import _TEMPLATES
    placeholders = {f for t in _TEMPLATES.values() for f in re.findall(r"\{(\w*)\}", t)}
    assert placeholders == {"i"}


def test_f2_the_engine_vocabulary_backstop_has_nothing_left_to_catch():
    """Kept as a fail-closed backstop, and asserted dead: no rendered template trips it."""
    from eidolon.decision.speech_acts import ACT_TABLE
    from eidolon.decision.validator import ENGINE_VOCAB, leaked_tokens
    from eidolon.llm.render import _TEMPLATES
    deny = frozenset({s.id for s in VANCE.secrets.all()} | {e.id for e in VANCE.evidence.all()} | set(ACT_TABLE))
    for code, template in _TEMPLATES.items():
        line = template.format(i=7)
        assert not leaked_tokens(line, deny), (code, line)
        assert not [w for w in ENGINE_VOCAB if w in line.lower()], (code, line)


# =====================================================================================
# F-3 — the view's `names` is the validator's allow-list, not the whole case
# =====================================================================================
ROBERT = Query(kind="who", subject=EntityRef(id="Robert", kind="actor"), raw="Was Robert Hale with you?")


def test_f3_view_names_are_exactly_the_permitted_set():
    r, t = _render(faithful(0))
    assert _prompts(t)[0]["names"] == ["David Kessler", "a drinking glass", "the library"]


def test_f3_a_grounded_entity_the_player_named_is_still_offered():
    """The fix must not over-narrow: an entity the player legitimately grounded is permitted, so it
    belongs in `names` — that is the `allowed_entity_ids` half of the set."""
    r, t = _render(faithful(0), query=ROBERT)
    assert "Robert Hale" in _prompts(t)[0]["names"]


@pytest.mark.parametrize("label, entity_id, display", HIDDEN)
def test_f3_a_guessed_hidden_entity_never_enters_the_view(label, entity_id, display):
    guess = Query(kind="did_you", raw=f"Was it done in {display}?")
    r, t = _render(faithful(0), query=guess)
    prompt = _prompts(t)[0]
    assert display not in prompt["names"] and entity_id not in prompt["names"]
    blob = json.dumps({k: v for k, v in prompt.items() if k != "player_query"}, sort_keys=True)
    assert display not in blob and entity_id not in blob


@pytest.mark.parametrize("hidden_label, hidden_id, hidden_display", HIDDEN)
@pytest.mark.parametrize("inv_label, inv_id, inv_display", INVENTED)
def test_f3_hidden_real_and_invented_guesses_give_the_same_view(hidden_label, hidden_id, hidden_display,
                                                                 inv_label, inv_id, inv_display):
    """The existence oracle. Apart from the player's own words — which the player already typed —
    the two prompts must be identical."""
    def view_without_the_players_line(text):
        _, t = _render(faithful(0), query=Query(kind="did_you", raw=text))
        doc = _prompts(t)[0]
        doc.pop("player_query")
        return json.dumps(doc, sort_keys=True)
    assert view_without_the_players_line(f"Was it done in {hidden_display}?") == \
           view_without_the_players_line(f"Was it done in {inv_display}?")


def test_f3_the_whole_cast_is_not_reachable_from_the_name_book():
    """The port's own world is the permitted set, so there is no index to match against."""
    seen = {}

    class Spy:
        def generate(self, envelope, case, speaker, feedback=()):
            seen["book"] = case
            from eidolon.llm.provider import ProviderError
            raise ProviderError("stop")
    ask(VANCE, DAVID, Query(kind="did_you", raw="Was it done in the gazebo?"),
        renderer=LLMRenderer(Spy(), verify=lambda *a: []))
    book = seen["book"]
    assert isinstance(book, NameBook)
    # David's plan: `DidNot(touch, Glass1)` + `At(Library)`. The Kitchen is not an envelope entity,
    # the gazebo the player asked about is not permitted, and nothing else is reachable at all.
    assert set(book.actors) == {"David"}
    assert set(book.locations) == {"Library"}
    assert set(book.objects) == {"Glass1"}
    for hidden in ("Margaret", "Elena", "Harold", "Robert"):
        assert hidden not in book.actors
    assert "Gazebo" not in book.locations and "bookend" not in book.objects


def test_f3_the_alias_table_is_filtered_to_the_permitted_set_too():
    """An alias is a name index entry like any other: an alias of a hidden entity would re-open the
    match the fix closes."""
    import dataclasses as dc
    from eidolon.world.alias import Alias
    from eidolon.world.frozen import FrozenDict
    aliased = dc.replace(VANCE, case=VANCE.case.model_copy(update={
        "alias": Alias(names=FrozenDict({"mr vance": "Harold", "the summerhouse": "Gazebo", "davey": "David"}))}))
    seen = {}

    class Spy:
        def generate(self, envelope, case, speaker, feedback=()):
            seen["book"] = case
            from eidolon.llm.provider import ProviderError
            raise ProviderError("stop")
    ask(aliased, DAVID, Query(kind="did_you", raw="Was it the summerhouse, or Mr Vance?"),
        renderer=LLMRenderer(Spy(), verify=lambda *a: []))
    assert dict(seen["book"].alias.names) == {"davey": "David"}


def test_f3_a_name_book_cannot_be_built_over_the_whole_case():
    """Structural: `permitted` is required, so there is no accidental unrestricted book."""
    with pytest.raises(TypeError):
        NameBook.of(VANCE.case)
    assert list(inspect.signature(NameBook.of).parameters) == ["case", "permitted"]
    assert inspect.signature(NameBook.of).parameters["permitted"].default is inspect.Parameter.empty


def test_f3_permitted_ids_equals_the_validators_own_allow_list():
    """The two sets must be defined together or they will drift apart: `validate_draft` allows
    `allowed_entity_ids | envelope entities | {speaker}` and the view must offer no more."""
    from eidolon.world.propositions import entities
    seen = {}

    class Spy:
        def generate(self, envelope, case, speaker, feedback=()):
            seen["book"] = case
            from eidolon.llm.provider import ProviderError
            raise ProviderError("stop")
    captured = {}
    real = LLMRenderer.__call__

    def capture(self, req):
        captured["req"] = req
        return real(self, req)
    try:
        LLMRenderer.__call__ = capture
        ask(VANCE, DAVID, ROBERT, renderer=LLMRenderer(Spy(), verify=lambda *a: []))
    finally:
        LLMRenderer.__call__ = real
    req = captured["req"]
    validator_allows = set(req.allowed_entity_ids) | {req.speaker}
    for c in req.envelope.allowed_claims:
        validator_allows |= set().union(*entities(c.proposition))
    assert permitted_ids(req) >= validator_allows
    book = seen["book"]
    assert set(book.actors) | set(book.locations) | set(book.objects) <= permitted_ids(req)


def test_f3_an_unresolvable_envelope_entity_still_fails_closed():
    """The narrowed book must not turn a genuinely unauthorable envelope into a silent success."""
    from eidolon.decision.claims import Claim
    from eidolon.decision.digest import ConversationDigest
    from eidolon.decision.envelope import PersonaSlot, build_envelope
    from eidolon.decision.strategy import DeliveryDirective, ResponsePlan
    from eidolon.decision.turn import CANARY, RenderRequest
    from eidolon.world.propositions import At
    ghost = ResponsePlan(act="LIE", claims=(Claim(id="c1", proposition=At(actor="David", location="Ghost", interval=(5, 60)),
                                                  sincerity="deceptive", source="plan"),),
                         delivery=DeliveryDirective("composed"))
    env = build_envelope(ghost, persona=PersonaSlot(), digest=ConversationDigest(character="David", turns=0), query_text="?")
    req = RenderRequest(env, ghost, "David", VANCE.case, VANCE.decision.statements, VANCE.ctx(),
                        frozenset(), CANARY, frozenset())
    t = scripted([faithful(0)])
    out = LLMRenderer(ModelLLM(t))(req)
    assert out.result.rejected and out.result.violations == ("RENDERER_EXCEPTION:ViewError",)
    assert t.requests == []
