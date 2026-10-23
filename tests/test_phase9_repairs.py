"""Phase 9 repair — the guards for the three findings of `docs/EIDOLON-PHASE-9-HOSTILE-REVIEW.md` that §10 requires fixed.

* **H9-B1** — repeating a question told a lie from a truth: a LIE was restated unchanged however often it was asked, while a
  truthful or vague answer turned into `REPEAT_PRIOR` / `REFUSE`. §15.4: from the third identical question the speaker
  re-supplies its STANDING answer (`REPEAT_PRIOR`), from the sixth it refuses — for every act, so the escalation says nothing
  about sincerity (§22.3).
* **H9-I1** — the nightly job counted a parse that FAILED as a parse that classified, and judged a corpus pass the budget had cut
  short.
* **H9-I2** — the nightly audit claimed the stronger verifier (`claude-fable-5-1`, §24) and called the generation model.

Each test names its finding; none may be weakened to make a change pass. No network: the provider is the suite's SDK-shaped
stand-in (`FakeAnthropicClient`)."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from eidolon.debug import nightly
from eidolon.decision.query import Query
from eidolon.decision.turn import run_ask_turn, run_search_turn
from eidolon.llm.fakes import RepairingTransport
from eidolon.llm.provider import MODEL, AnthropicTransport, Completion, ProviderError, ProviderRefusal
from eidolon.solve.bots import held_names
from eidolon.solve.package import load_sealed_case
from eidolon.solve.queries import expressible_queries, public_names
from eidolon.solve.session import new_session
from tests.decision.fixtures.vance_walkthrough import DAVID, build_initial_state
from tests.llm.injection_corpus_v2 import ALL
from tests.p9_worlds import HALL, NORA, world_a
from tests.test_phase9_nightly import FakeAnthropicClient, ParserToo

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "cases" / "generated"
REPS = 8
# answers 3..8 to the same question (§15.4, §28.4 #2); REFUSE runs at most 2 turns in a row, then the standing answer (F-15)
ESCALATION = ["REPEAT_PRIOR"] * 3 + ["REFUSE"] * 2 + ["REPEAT_PRIOR"]


def ask_repeatedly(state, who, q, n=REPS, presented_ref=None):
    acts, claims = [], []
    for _ in range(n):
        r = run_ask_turn(state, who, q, presented_ref=presented_ref)
        assert not r.rejected, r.violations
        state = r.state
        acts.append(r.plan_act)
        claims.append(tuple(c.id for c in state.decision.statements.all()[-1].claims))
    return state, acts, claims


# ====================================================================== H9-B1
def test_H9_B1_a_lie_and_a_truth_escalate_identically_when_the_same_question_is_repeated():
    """§28.4 #2 for BOTH arms: "REPEAT_PRIOR after 2, escalation after 5, claims identical". Before the repair the liar answered
    LIE eight times out of eight (his memory retrieval is empty, so the old REPEAT_PRIOR had nothing to repeat, and REFUSE lost
    to LIE on utility): a deterministic sincerity tell."""
    _, truth_acts, truth_claims = ask_repeatedly(world_a(), NORA, HALL)
    _, lie_acts, lie_claims = ask_repeatedly(build_initial_state(), DAVID,
                                             Query(kind="where", raw="Where were you between ten and half past?"))
    assert truth_acts == ["TRUTH"] * 2 + ESCALATION, truth_acts
    assert lie_acts == ["LIE"] * 2 + ESCALATION, lie_acts
    for claims in (truth_claims, lie_claims):
        assert len({c for c in claims if c}) == 1, "the claims never change, whatever the act (§15.4: verbatim)"
        assert all(claims[i] for i in (0, 1, 2, 3, 4, 7)) and not any(claims[5:7]),             "REPEAT_PRIOR re-supplies the answer; REFUSE says nothing, and never more than twice running (F-15)"


def test_H9_B1_repeat_prior_never_resupplies_a_claim_a_peel_retracted():
    """§15.4: "the standing (non-retracted) claim is re-supplied verbatim — never a claim retracted by a peel". The liar is shown
    the knife print (his layer peels and the lie is retracted); asked the old question again twice more, he must not say the
    retracted lie as REPEAT_PRIOR."""
    from tests.p9_worlds import PRINTS, WHERE
    state = world_a()
    for _ in range(2):
        state = run_ask_turn(state, DAVID, WHERE).state
    lie_ids = {c.id for c in state.decision.statements.all()[-1].claims}
    state = run_ask_turn(state, DAVID, PRINTS, presented_ref="E_knife").state
    assert state.decision.layer_peels, "fixture: the knife print peels David's first layer"
    retracted = {s.id for s in state.decision.statements.all() if s.retracted_by is not None}
    assert retracted, "fixture: the peel retracted the lie"
    for _ in range(2):
        r = run_ask_turn(state, DAVID, WHERE)
        assert not r.rejected, r.violations
        state = r.state
        if r.plan_act == "REPEAT_PRIOR":
            assert not ({c.id for c in state.decision.statements.all()[-1].claims} & lie_ids)


def _demo_input(presented_ref, repeat_count):
    from eidolon.decision import demo
    from eidolon.decision.strategy import StrategyInput
    from eidolon.minds.character import initial_character_state
    from tests.p9_worlds import PERSONALITY
    secret = next(iter(demo.build_demo_state().secrets.for_owner(demo.DAVID)))
    return StrategyInput(query=Query(kind="challenge", raw="x"), character=demo.DAVID,
                         state=initial_character_state(demo.DAVID, PERSONALITY), secret=secret, layer_reached=0, peel=None,
                         presented_ref=presented_ref, retrieval="none", retrieved_claim=None, known_topic=True,
                         repeat_count=repeat_count, prior_claims=secret.cover.layers[0].claims)


def test_H9_B1_an_authored_evidence_response_is_never_swallowed_by_repetition():
    """The shown item has an authored response at this layer (`E_knife` -> DENY_EVIDENCE): however often the challenge is
    repeated, the speaker answers the item, never "as I said"."""
    from eidolon.decision.strategy import select_plan
    for n in (2, 3, 5, 7):
        assert select_plan(_demo_input("E_knife", n))[0].act == "DENY_EVIDENCE", n


def test_H9_B1_an_inert_shown_item_escalates_exactly_like_nothing_shown():
    """Re-review RR-B1: the preference was off for ANY shown item, so an item with no authored response switched the §15.4
    escalation off and a liar repeated his lie unchanged again. An inert item is no reason to stop escalating."""
    from eidolon.decision.strategy import select_plan
    for ref in (None, "E_unrelated"):
        assert select_plan(_demo_input(ref, 1))[0].act != "REPEAT_PRIOR"
        assert select_plan(_demo_input(ref, 2))[0].act == "REPEAT_PRIOR", ref
        assert select_plan(_demo_input(ref, 5))[0].act == "REFUSE", ref


def test_H9_B1_the_repetition_preferences_clear_the_ceiling_of_every_other_act():
    """The escalation must not depend on how a content act happens to score in one case: `REPEAT_PRIOR` (from the third ask) and
    `REFUSE` (from the sixth) must beat the CEILING of every other act's utility - every weighted term at its maximum."""
    from eidolon.decision import strategy as S
    from eidolon.decision.claims import Claim
    from eidolon.minds.character import initial_character_state
    from eidolon.world.propositions import At
    from tests.p9_worlds import PERSONALITY
    ceiling = S.W_SAFETY + S.W_CONSIST + S.W_PLAUS + S.W_PERSONA + S.W_EMOTION + S.W_GOAL
    talkative = PERSONALITY.model_copy(update={"talkativeness": 1.0})            # the lowest REFUSE persona fit
    claim = Claim(id="c", proposition=At(actor=DAVID, location="Kitchen", interval=(0, 10)), sincerity="deceptive", source="plan")
    inp = lambda n: S.StrategyInput(query=Query(kind="where", raw="x"), character=DAVID,                  # noqa: E731
                                    state=initial_character_state(DAVID, talkative), secret=None, layer_reached=0, peel=None,
                                    presented_ref=None, retrieval="none", retrieved_claim=None, known_topic=True, repeat_count=n,
                                    prior_claims=(claim,))
    rp = S._repeat_prior(inp(2))
    assert rp is not None and rp.claims == (claim,) and S.utility(rp, inp(2)) > ceiling
    assert S.utility(S._refuse(inp(5)), inp(5)) > max(ceiling, S.utility(rp, inp(5)))
    assert S._repeat_prior(inp(1)) is None and S._refuse(inp(4)) is None


def _found_everything(name):
    state = new_session(load_sealed_case(CASES / f"{name}.json"), seed=7)
    for _ in range(4):
        for ev in sorted(state.evidence.all(), key=lambda e: e.id):
            if ev.id not in state.discovery.known_evidence:
                r = run_search_turn(state, ev.discovery.at, ev.discovery.action)
                if not r.rejected:
                    state = r.state
    return state


@pytest.mark.parametrize("name", ["study_party_s4", "manor_wing_s4"])
def test_H9_B1_a_repeat_bot_with_no_evidence_learns_nothing_about_sincerity(name):
    """The review's reproduction, as a test: every V-7 question, to every living character, asked again and again with nothing
    shown. Whatever the first answer's act - LIE, TRUTH, VAGUE - a claim-bearing answer must escalate the same way, so watching
    what repetition does tells the player nothing about whether the answer was a lie. (Before the repair: 0 of 250 lies changed,
    the other answers did.)"""
    state = _found_everything(name)
    names = held_names(state, public_names(state.case))
    seen = Counter()
    for who in sorted(state.case.living_actors()):
        for q in expressible_queries(state.case, who, names)[::2]:            # every other question keeps the run short
            state, acts, claims = ask_repeatedly(state, who, q, n=7)
            if not claims[0] or acts[0] in ("CONCESSION", "CONFESSION", "SLIP", "STONEWALL"):
                continue
            seen[acts[0]] += 1
            assert acts[2:] == ESCALATION[:5], (who, q.raw, acts)
            # every claim made for this question is the same claim (§28.4 #2), and the second answer is the first (F-14: the
            # tie-break is keyed on the question, so a weak memory's VAGUE/DONT_KNOW tie cannot flip on the second ask)
            assert len({c for c in claims if c}) == 1 and claims[1] == claims[0], (who, q.raw, claims)
    assert seen["LIE"] >= 10 and sum(v for k, v in seen.items() if k != "LIE") >= 10, seen


def _inert_item(state, who):
    """A held item with no authored response for `who` and zero refutation weight against every layer it owns."""
    from eidolon.decision.weight import refutation_weight
    secrets, ctx = list(state.secrets.for_owner(who)), state.ctx()
    return next(e for e in sorted(state.discovery.known_evidence)
                if not any(r.evidence == e for s in secrets for r in s.evidence_responses)
                and all(refutation_weight(frozenset({e}), layer, who, ctx) == 0 for s in secrets for layer in s.cover.layers))


@pytest.mark.parametrize("name", ["study_party_s4", "manor_wing_s4"])
def test_H9_B1_showing_an_inert_item_does_not_turn_repetition_back_into_a_sincerity_test(name):
    """Re-review RR-B1, through the shape the ask form builds when "Show them" is used (`kind="challenge"`, any held item): the
    repeat bot again, every ask showing an item that is inert for the addressee. Before this fix the repaired engine behaved
    exactly as the unrepaired one on this path - 50 of 50 lies unchanged over seven asks, the other answers escalating."""
    state = _found_everything(name)
    names = held_names(state, public_names(state.case))
    seen = Counter()
    for who in sorted(state.case.living_actors()):
        item = _inert_item(state, who)
        for q in expressible_queries(state.case, who, names):       # every question: ADR-30 left fewer (on-topic) lies to sample
            state, acts, claims = ask_repeatedly(state, who, q.model_copy(update={"kind": "challenge"}), n=7, presented_ref=item)
            if not claims[0] or acts[0] in ("CONCESSION", "CONFESSION", "SLIP", "STONEWALL"):
                continue
            seen[acts[0]] += 1
            assert acts[2:] == ESCALATION[:5], (who, q.raw, acts)
            assert len({c for c in claims if c}) == 1, (who, q.raw, claims)
    assert seen["LIE"] >= 3 and sum(v for k, v in seen.items() if k != "LIE") >= 3, seen


# ====================================================================== H9-I1 / H9-I2: the nightly job
CAT = {line: cat for cat, line, _ in ALL}


class Recorder(FakeAnthropicClient):
    """The SDK-shaped stand-in, also recording the model each call asked for, by role."""
    __module__ = "anthropic.fake"

    def __init__(self, inner):
        super().__init__(inner)
        self.log: list[tuple[str, str]] = []

    def create(self, *, model, **kw):
        props = kw["output_config"]["format"]["schema"]["properties"]
        self.log.append(("verify" if "unreferenced_assertions" in props else "generate" if "segments" in props else "parse", model))
        try:
            return super().create(model=model, **kw)
        except ProviderRefusal:                     # the SDK reports a refusal as a stop reason, not as an exception
            return SimpleNamespace(stop_reason="refusal", stop_details=None, content=[],
                                   usage=SimpleNamespace(input_tokens=120, output_tokens=0, cache_read_input_tokens=0))


class ParseFails:
    """Answers the parse role correctly for the `coercion` lines only; every other parse call fails with `exc`."""

    def __init__(self, exc):
        self.inner, self.exc = RepairingTransport(fail_every=5), exc

    def complete(self, request):
        if request.role == "parse":
            if CAT.get(json.loads(request.user)["player_text"]) == "coercion":
                return Completion(text=json.dumps({"kind": "ask", "query_kind": "coercion"}))
            raise self.exc
        return self.inner.complete(request)


def live_run(tmp_path, inner, **kw):
    client = Recorder(inner)
    rep = nightly.run(tmp_path, transport=AnthropicTransport(client), turns=kw.pop("turns", 24), audit_sample=kw.pop("audit_sample", 30),
                      corpus_turns_n=kw.pop("corpus_turns_n", 6), run_suites=False, **kw)
    return rep, {m["id"]: m for m in rep["metrics"]}, client


def test_H9_I1_a_parser_that_refuses_hostile_lines_has_not_classified_them(tmp_path):
    """215 of 225 lines refused by the model: before the repair every refusal counted as an in-world `clarify` and N-3 read
    PASS 10000, exit 0. A refusal is the model's answer, and it is not "meta/coercion or what-do-you-mean": a miss."""
    rep, by, _ = live_run(tmp_path, ParseFails(ProviderRefusal("refused")))
    assert by["N-3"]["status"] == "FAIL" and by["N-3"]["value"] < 10000, by["N-3"]
    assert nightly.exit_code(rep) == 1


def test_H9_I1_a_provider_that_fails_during_the_parse_pass_leaves_the_classification_unmeasured(tmp_path):
    """A transport error is not a classification at all - neither a hit nor a miss: N-3 cannot be judged."""
    rep, by, _ = live_run(tmp_path, ParseFails(ProviderError("APIConnectionError")))
    assert by["N-3"]["status"] == "UNMEASURED" and by["N-3"]["value"] is None, by["N-3"]
    assert "provider" in by["N-3"]["note"]


@pytest.mark.parametrize("parsed", [100, 195])
def test_H9_I1_a_budget_that_runs_out_during_the_parse_pass_leaves_the_classification_unmeasured(tmp_path, parsed):
    """The budget was checked once, BEFORE the pass: running out after 195 lines read PASS (the unparsed 30 counted as hits),
    after 100 read FAIL (a budget event reported as the classifier's). Both are UNMEASURED."""
    _, _, probe = live_run(tmp_path / "probe", ParserToo())
    first_parse = next(i for i, (role, _) in enumerate(probe.log) if role == "parse")
    rep, by, client = live_run(tmp_path / "cut", ParserToo(), max_calls=first_parse + parsed)
    assert sum(role == "parse" for role, _ in client.log) == parsed and rep["budget_exhausted"] is True
    assert by["N-3"]["status"] == "UNMEASURED", by["N-3"]
    assert by["N-1"]["status"] == "PASS", "the session itself finished inside the budget and is still judged"


def test_H9_I1_a_budget_that_runs_out_during_the_corpus_sample_leaves_N4_unmeasured(tmp_path):
    """The same rule for the corpus-as-full-turns sample: a sample the budget cut short is not judged on what was left."""
    _, _, probe = live_run(tmp_path / "probe", ParserToo())
    first_parse = next(i for i, (role, _) in enumerate(probe.log) if role == "parse")
    rep, by, _ = live_run(tmp_path / "cut", ParserToo(), max_calls=first_parse + len(ALL) + 6)
    assert by["N-3"]["status"] == "PASS", "the parse pass itself was complete"
    assert by["N-4"]["status"] == "UNMEASURED" and by["N-4"]["dry_value"]["turns"] >= 1, by["N-4"]


def test_H9_I2_the_nightly_audit_runs_on_the_stronger_model_it_names(tmp_path):
    """§24/§27.4: the offline audit's verifier is `claude-fable-5-1`. Before the repair every call - session and audit - went to
    `claude-opus-5` while N-5's note said the stronger model was used."""
    rep, by, client = live_run(tmp_path, ParserToo())
    models = Counter(client.log)
    assert models[("verify", nightly.AUDIT_MODEL)] >= 1, models
    assert all(role == "verify" for role, model in client.log if model == nightly.AUDIT_MODEL), "only the audit uses it"
    assert {model for role, model in client.log if role in ("generate", "parse")} == {MODEL}
    assert nightly.AUDIT_MODEL in by["N-5"]["note"] and "verifier" in by["N-5"]["note"]


def test_H9_I2_a_run_without_a_stronger_verifier_does_not_say_it_had_one(tmp_path):
    """The note is read off the calls the audit actually made. A dry run's verifier is the rehearsal stub: no model is named."""
    rep = nightly.run(tmp_path, turns=12, audit_sample=12, corpus_turns_n=3, run_suites=False)
    note = {m["id"]: m for m in rep["metrics"]}["N-5"]["note"]
    assert nightly.AUDIT_MODEL not in note and MODEL not in note, note


# ====================================================================== re-review RR-I1: the H9-I1 rule on the sibling metrics
class CorpusSampleFails(ParserToo):
    """The 225-line parse pass is answered; then every corpus-sample parse but the first gets no answer from the transport."""

    def __init__(self, exc=None):
        super().__init__()
        self.parses, self.exc = 0, exc or ProviderError("APIConnectionError")

    def complete(self, request):
        if request.role == "parse":
            self.parses += 1
            if self.parses > len(ALL) + 1:
                raise self.exc
        return super().complete(request)


class GenerateOutage(ParserToo):
    """The generate route stops answering after `n` calls: the scripted session is cut short."""

    def __init__(self, n):
        super().__init__()
        self.n, self.calls = n, 0

    def complete(self, request):
        if request.role == "generate":
            self.calls += 1
            if self.calls > self.n:
                raise ProviderError("APIStatusError")
        return super().complete(request)


def test_RR_I1_a_corpus_sample_the_provider_did_not_answer_is_not_judged(tmp_path):
    """Before: 24 of 25 sample lines got no answer at the transport, the one that did was contained, and N-4 read PASS, exit 0."""
    rep, by, _ = live_run(tmp_path, CorpusSampleFails(), corpus_turns_n=25)
    assert by["N-3"]["status"] == "PASS", "the parse pass itself was answered"
    assert by["N-4"]["status"] == "UNMEASURED", by["N-4"]
    assert "no answer" in by["N-4"]["note"] and rep["corpus"]["sample"]["unanswered_calls"] >= 1


def test_RR_I1_a_refusal_during_the_corpus_sample_is_an_answer_and_is_still_judged(tmp_path):
    """A refusal is the model's answer (the line is contained: nothing runs), not a missing measurement."""
    rep, by, _ = live_run(tmp_path, CorpusSampleFails(ProviderRefusal("refused")), corpus_turns_n=25)
    assert rep["corpus"]["sample"]["unanswered_calls"] == 0
    assert by["N-4"]["status"] == "PASS", by["N-4"]


def test_RR_I1_a_session_an_outage_cut_short_does_not_judge_its_session_metrics(tmp_path):
    """Before: the generate route went down after 40 calls, 31 of 60 turns committed, and N-6/N-7 read PASS, exit 0 (after 12
    calls N-6 read FAIL). Like N-1, they describe the whole scripted session and are judged only on a complete one."""
    rep, by, _ = live_run(tmp_path, GenerateOutage(40), turns=60)
    assert rep["turns_committed"] < 60
    for mid in ("N-1", "N-6", "N-7"):
        assert by[mid]["status"] == "UNMEASURED", by[mid]


# ====================================================================== F-14 / F-15
@pytest.mark.parametrize("name", ["study_party_s4", "manor_wing_s4"])
def test_F14_asking_the_same_question_twice_gets_the_same_answer_whatever_it_was(name):
    """F-14 (R9-1): the tie-break hashed the turn, so a weak memory's VAGUE and DONT_KNOW - equal on utility - could swap on the
    second ask, and a changed second answer certified the first as "not a lie" (3 of 281 VAGUE, 14 of 109 DONT_KNOW). Keyed on
    (seed, speaker, question) the same question breaks the same tie the same way. Every V-7 question, claimless answers included."""
    state = _found_everything(name)
    names = held_names(state, public_names(state.case))
    seen = Counter()
    for who in sorted(state.case.living_actors()):
        for q in expressible_queries(state.case, who, names):
            state, acts, claims = ask_repeatedly(state, who, q, n=2)
            if acts[0] in ("CONCESSION", "CONFESSION", "SLIP", "STONEWALL"):
                continue
            seen[acts[0]] += 1
            assert (acts[1], claims[1]) == (acts[0], claims[0]), (who, q.raw, acts, claims)
    assert seen["VAGUE"] + seen["DONT_KNOW"] >= 10, seen


def test_F15_refuse_runs_at_most_two_turns_then_the_standing_answer_returns():
    """F-15 (R9-2): `refuse_streak` had no producer, so a character refused for ever from the sixth identical question. §11.2/§15.4:
    REFUSE is capped at 2 consecutive turns, after which terse acts resume - the same for a liar and a truthful witness."""
    state = build_initial_state()
    q = Query(kind="where", raw="Where were you between ten and half past?")
    state, acts, claims = ask_repeatedly(state, DAVID, q, n=11)
    assert acts[5:] == ["REFUSE", "REFUSE", "REPEAT_PRIOR", "REFUSE", "REFUSE", "REPEAT_PRIOR"], acts
    assert state.characters[DAVID].refuse_streak == 0
