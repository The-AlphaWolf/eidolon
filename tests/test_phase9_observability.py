"""Phase 9 - §27.4 offline audit and §27.5 SLOs, over synthetic populations (to pin every threshold) and over real played
sessions (to pin that a genuine game audits clean and measures sensibly)."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from eidolon import game
from eidolon.debug import audit, slo
from eidolon.decision.claims import Claim, Statement
from eidolon.decision.events import ClaimMade, apply_decision
from eidolon.decision.turn import CANARY
from eidolon.llm.fakes import ScriptedTransport
from eidolon.llm.render import LLMRenderer, ModelLLM
from eidolon.solve.bots import held_names
from eidolon.solve.queries import expressible_queries, public_names
from eidolon.store import Save
from eidolon.trace import TurnTrace
from eidolon.world.propositions import At, Solution
from tests.llm.llm_helpers import approve, faithful

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "cases" / "generated"


# ====================================================================== SLO thresholds, on synthetic traces
def trace(turn, *, renderer="model", outcome="committed", drafts=1, tokens=100, latency=10, peeled=False, presented=False,
          shown=0, kind="ask", failures=(), calls=None, cost=None, cache=0):
    d = dict(kind=kind, outcome=outcome, turn_id=turn, game_id="g", character="David", renderer=renderer, failures=failures,
             committed=dict(events=("TurnCommitted",), first_seq=turn, last_seq=turn, head_hash="a" * 64, case="b" * 16),
             fallback_used=outcome == "committed_fallback", timings_ms=dict(run=latency, append=1, render=latency),
             view=dict(retrieval_band="none", detective_evidence=shown), assessment=dict(
                 threat_bp=0, presented=presented, contradicts_standing=False,
                 peels=(dict(secret="a" * 12, frm=0, to=1, weight_bp=9000, peeled=peeled, stonewalled=False),)))
    if renderer == "model":
        d["drafts"] = tuple(dict(n=i, outcome="repair" if i < drafts - 1 else "accepted",
                                 violations=("UNKNOWN_ENTITY[0]",) if i < drafts - 1 else ()) for i in range(drafts))
        d["llm_calls"] = tuple(calls) if calls is not None else (dict(role="generate", model="m", effort="medium", prompt_hash="h",
                                                                  input_tokens=tokens, output_tokens=0, cache_read_tokens=cache,
                                                                  cost_micro_usd=cost),)
        d["envelope"] = dict(sha="c" * 64, sections=5, claims=1, reveals=0, digest_chars=1, query_chars=1, tokens=tokens)
    return TurnTrace.model_validate(d)


def by_name(ms):
    return {m.name: m for m in ms}


def test_an_empty_population_measures_nothing_and_says_so():
    m = by_name(slo.compute([], []))
    for name in ("fallback_rate_bp", "mean_drafts_per_turn_centi", "tokens_per_turn_flat", "turn_latency_ms"):
        assert m[name].status == "UNMEASURED" and m[name].value is None
    assert m["cache_read_ratio_bp"].status == "UNMEASURED" and m["cost_per_turn_micro_usd"].status == "UNMEASURED"
    assert m["peels_without_any_presented_breaker"].status == "PASS"           # nothing to violate, and zero is a true zero


@pytest.mark.parametrize("fallbacks, status", [(0, "PASS"), (1, "PASS"), (2, "FAIL"), (50, "FAIL")])
def test_the_fallback_rate_threshold_is_two_percent_exactly(fallbacks, status):
    ts = [trace(i + 1, outcome="committed_fallback" if i < fallbacks else "committed") for i in range(100)]
    m = by_name(slo.compute(ts, []))["fallback_rate_bp"]
    assert m.value == fallbacks * 100 and m.status == status


def test_mean_drafts_per_turn_threshold_is_exclusive_at_exactly_1_30():
    """9 two-draft turns in 30: a mean of exactly 1.30, and the target is "< 1.3"."""
    ts = [trace(i + 1, drafts=2 if i < 9 else 1) for i in range(30)]
    m = by_name(slo.compute(ts, []))["mean_drafts_per_turn_centi"]
    assert m.value == 130 and m.status == "FAIL"
    ts = [trace(i + 1, drafts=2 if i < 8 else 1) for i in range(30)]
    assert by_name(slo.compute(ts, []))["mean_drafts_per_turn_centi"].status == "PASS"


@pytest.mark.parametrize("drafts, status", [(1, "PASS"), (2, "FAIL")])
def test_mean_drafts_per_turn_threshold(drafts, status):
    ts = [trace(i + 1, drafts=drafts if i % 3 == 0 else 1) for i in range(30)]
    m = by_name(slo.compute(ts, []))["mean_drafts_per_turn_centi"]
    assert m.status == status
    assert (m.value < 130) is (status == "PASS")


def test_tokens_per_turn_must_be_flat_over_the_session():
    flat = [trace(i + 1, tokens=100 + (i % 3)) for i in range(30)]
    growing = [trace(i + 1, tokens=100 + 20 * i) for i in range(30)]
    assert by_name(slo.compute(flat, []))["tokens_per_turn_flat"].status == "PASS"
    assert by_name(slo.compute(growing, []))["tokens_per_turn_flat"].status == "FAIL"
    assert by_name(slo.compute(flat[:5], []))["tokens_per_turn_flat"].status == "UNMEASURED"


def test_latency_percentiles_cache_ratio_and_cost_are_reported_or_unmeasured_honestly():
    ts = [trace(i + 1, latency=10 * (i + 1), tokens=100, cache=50, cost=7) for i in range(20)]
    m = by_name(slo.compute(ts, []))
    assert m["turn_latency_ms"].value == {"p50": 110, "p95": 200}
    assert m["cache_read_ratio_bp"].value == 5000 and m["cost_per_turn_micro_usd"].value == 7
    assert by_name(slo.compute([trace(1, cost=None)], []))["cost_per_turn_micro_usd"].status == "UNMEASURED"


def test_a_peel_with_nothing_ever_presented_is_an_i3_violation_and_a_normal_peel_is_not():
    ok = [trace(1, peeled=True, presented=True), trace(2, peeled=True, presented=False, shown=1)]
    bad = ok + [trace(3, peeled=True, presented=False, shown=0)]
    assert by_name(slo.compute(ok, []))["peels_without_any_presented_breaker"].status == "PASS"
    m = by_name(slo.compute(bad, []))["peels_without_any_presented_breaker"]
    assert m.status == "FAIL" and m.value == 1 and "3" in m.note


def test_failures_are_counted_by_kind_and_clarify_rate_comes_from_typed_lines():
    ts = [trace(1, failures=("validation_failure",)), trace(2, failures=("deterministic_fallback", "provider_refusal"), outcome="committed_fallback"),
          trace(3, renderer="none", kind="say")]
    aborted = [TurnTrace.model_validate(dict(kind="say", outcome="clarify", game_id="g", failures=("clarify",))),
               TurnTrace.model_validate(dict(kind="ask", outcome="rejected", game_id="g", failures=("provider_timeout",)))]
    m = by_name(slo.compute(ts, aborted))
    assert m["failures_by_kind"].value == {"clarify": 1, "deterministic_fallback": 1, "provider_refusal": 1, "provider_timeout": 1,
                                           "validation_failure": 1}
    assert m["parser_clarify_rate_bp"].value == 5000 and m["outcomes"].value["rejected"] == 1


def test_rows_that_are_not_traces_are_counted_not_trusted():
    good = trace(1).model_dump_json()
    ts, bad = slo.parse_rows([(1, good), (2, '{"forged": true}'), (3, "not json")])
    assert len(ts) == 1 and bad == 2
    assert by_name(slo.compute(ts, [], unreadable=bad))["unreadable_trace_rows"].status == "FAIL"


def test_the_text_dashboard_carries_every_status_and_never_turns_unmeasured_into_a_number():
    text = slo.render_text(slo.compute([], []))
    assert "UNMEASURED" in text and "fallback_rate_bp" in text and "None" not in text.replace("null", "")
    assert text.count("UNMEASURED") >= 5


# ====================================================================== SLOs over a real played session
def play(tmp_path, name="study_party_s4", renderer=None, query_all=True):
    p = tmp_path / f"{name}.db"
    Save.create(p, CASES / f"{name}.json", seed=7).close()
    s = Save.open(p, writable=True)
    step = lambda c, *a, **k: c(s, f"{c.__name__}@{s.last_seq}", s.last_seq, *a, **k)            # noqa: E731
    for _ in range(4):
        for ev in sorted(s.state.evidence.all(), key=lambda e: e.id):
            if ev.id not in s.state.discovery.known_evidence:
                step(game.search, ev.discovery.at, ev.discovery.action)
    if query_all:
        for who in sorted(s.state.case.living_actors()):
            for q in expressible_queries(s.state.case, who, held_names(s.state, public_names(s.state.case))):
                step(game.ask, who, q, renderer=renderer)
    return s


@pytest.fixture(scope="module")
def played(tmp_path_factory):
    s = play(tmp_path_factory.mktemp("obs"))
    yield s
    s.close()


def test_a_real_session_has_a_trace_for_every_turn_and_measures_sensibly(played):
    ms = by_name(slo.from_save(played))
    assert ms["turns_committed"].value == played.state.turn_counter and ms["trace_gaps"].value == 0
    assert ms["peels_without_any_presented_breaker"].status == "PASS"
    assert ms["fallback_rate_bp"].status == "UNMEASURED", "a template session has no model turn: nothing to measure"
    assert "unreadable_trace_rows" not in ms


def test_a_model_session_measures_fallback_drafts_and_tokens(tmp_path):
    t = ScriptedTransport(generate=[faithful(1)], verify=[approve], repeat_last=True)
    s = play(tmp_path, renderer=LLMRenderer(ModelLLM(t)))
    ms = by_name(slo.from_save(s))
    assert ms["fallback_rate_bp"].status == "PASS" and ms["fallback_rate_bp"].value == 0
    assert ms["mean_drafts_per_turn_centi"].value == 100 and ms["tokens_per_turn_flat"].status in ("PASS", "UNMEASURED")
    assert ms["turn_latency_ms"].status == "REPORTED"
    s.close()


# ====================================================================== the audit
def test_a_genuine_session_audits_clean_on_two_cases(played, tmp_path):
    rep = audit.audit_save(played)
    assert rep.sampled == rep.statements >= 200 and rep.discrepancies == 0 and rep.status == "PASS"
    assert rep.rate_bp == 0 and rep.upper95_bp <= 150
    s2 = play(tmp_path, "manor_wing_s4")
    rep2 = audit.audit_save(s2)
    assert rep2.sampled >= 200 and rep2.discrepancies == 0 and rep2.status == "PASS"
    s2.close()


def forge(state, *, text, act="TRUTH", claims=(), speaker="Elena", n=99001):
    stmt = Statement(id=f"S{n:05d}", turn=n, speaker=speaker, text=text, act=act, claims=tuple(claims))
    return replace(state, decision=apply_decision(state.decision, ClaimMade(statement=stmt))), stmt


@pytest.fixture(scope="module")
def world(played):
    return played.state


LEAKS = {
    "meta_vocabulary": ("As an AI language model, I follow my instructions.", "TRUTH", "FORBIDDEN_VOCAB"),
    "canary": (f"My token is {CANARY}.", "TRUTH", "CANARY_LEAK"),
    "engine_vocabulary": ("My sincerity here is not in question.", "TRUTH", "INTERNAL_TOKEN_LEAK"),
    "an_act_name": ("That was a CONFESSION, I suppose.", "TRUTH", "INTERNAL_TOKEN_LEAK"),
    "an_invented_name": ("I was with Mr Fothergill all evening.", "TRUTH", "INVENTED_NAME"),
    "a_clock_time_no_claim_renders": ("I left at 03:33 sharp.", "TRUTH", "TIME_NOT_IN_CLAIMS"),
    "a_spelled_time": ("I left at half past three.", "TRUTH", "TIME_NOT_IN_CLAIMS"),
    "a_confession_outside_a_confession": ("I killed him, you know.", "TRUTH", "SELF_DISCLOSURE:confession"),
    "a_lie_tell": ("That was a lie, of course.", "TRUTH", "SELF_DISCLOSURE:lie_tell"),
}


@pytest.mark.parametrize("name", list(LEAKS))
def test_every_text_level_leak_class_is_found_with_the_full_deny_sets(world, name):
    text, act, code = LEAKS[name]
    state, stmt = forge(world, text=text, act=act)
    ids, names = audit.engine_ids(state), audit._name_index(state.case)
    hard, _ = audit.check_statement(state, stmt, ids=ids, names=names)
    assert any(h.startswith(code) for h in hard), (name, hard)


def test_an_id_the_runtime_would_not_have_denied_to_that_renderer_is_denied_by_the_audit(world):
    """The runtime denies the ids a renderer was GIVEN; the audit denies every one the session holds."""
    ev = sorted(e.id for e in world.evidence.all())[0]
    state, stmt = forge(world, text=f"Ask about {ev} if you doubt me.")
    hard, _ = audit.check_statement(state, stmt, ids=audit.engine_ids(state), names=audit._name_index(state.case))
    assert "INTERNAL_TOKEN_LEAK:1" in hard


def test_a_solution_claim_outside_a_confession_and_a_foreign_protected_fact_are_found(world):
    sol = Solution(murderer="David", method="knife", location="Study", interval=(10, 11), motive_kind="money")
    state, stmt = forge(world, text="It is what it is.", claims=(Claim(id="x1", proposition=sol, sincerity="truthful", source="plan"),))
    hard, _ = audit.check_statement(state, stmt, ids=audit.engine_ids(state), names=audit._name_index(state.case))
    assert "SOLUTION_OUTSIDE_CONFESSION" in hard and "SOLUTION_LEAK" in hard
    state, stmt = forge(world, text="It is what it is.", act="CONFESSION", claims=(Claim(id="x1", proposition=sol, sincerity="truthful", source="plan"),))
    ok, _ = audit.check_statement(state, stmt, ids=audit.engine_ids(state), names=audit._name_index(state.case))
    assert "SOLUTION_OUTSIDE_CONFESSION" not in ok and "SOLUTION_LEAK" not in ok


def test_the_speakers_own_never_conceded_protected_fact_in_plain_words_is_found(world):
    murder = next(s for s in world.secrets.all() if s.kind == "murder")
    prop = next(p for p in murder.protected if p.kind != "Said")
    from eidolon.decision.envelope import EnvelopeClaim
    from eidolon.decision.llm import render_claim
    said = render_claim(EnvelopeClaim(id="", proposition=prop), world.case)
    state, stmt = forge(world, text=said, speaker=murder.owner, act="TRUTH")
    hard, _ = audit.check_statement(state, stmt, ids=audit.engine_ids(state), names=audit._name_index(state.case))
    assert "PROTECTED_PHRASE" in hard
    state, stmt = forge(world, text=said, speaker=murder.owner, act="CONCESSION")                     # a concession may say it
    assert "PROTECTED_PHRASE" not in audit.check_statement(state, stmt, ids=audit.engine_ids(state), names=audit._name_index(state.case))[0]


def test_the_sample_is_deterministic_bounded_and_the_status_is_unmeasured_when_it_is_small(played):
    a = audit.audit_state(played.state, played.bundle.package.seal, sample=50, seed=3)
    b = audit.audit_state(played.state, played.bundle.package.seal, sample=50, seed=3)
    c = audit.audit_state(played.state, played.bundle.package.seal, sample=50, seed=4)
    assert a == b and a.sampled == 50 and a.statements == played.state.decision.statements.all().__len__()
    assert a.status == "UNMEASURED" and a.summary()["note"], "zero findings in 50 statements cannot show a rate below 0.5%"
    assert a.upper95_bp >= 500 and c.sampled == 50
    assert a.picked == b.picked and a.picked != c.picked and len(set(a.picked)) == 50, "a different seed samples different statements"
    assert a.picked != tuple(s.id for s in played.state.decision.statements.all())[:50], "and the sample is not just the first fifty"


def test_a_discrepancy_is_filed_as_a_stable_fixture(world, tmp_path):
    state, stmt = forge(world, text="I killed him, you know.")
    rep = audit.audit_state(state, "ab" * 16)
    assert rep.discrepancies == 1 and rep.sampled == 225 and rep.rate_bp == 44        # 1 of 225 is 0.44%: under the bound, and filed anyway
    files = audit.write_fixtures(rep, state, tmp_path / "fixtures")
    assert len(files) == rep.discrepancies
    doc = json.loads(files[0].read_text(encoding="utf-8"))
    assert doc["text"] == stmt.text and doc["violations"] and doc["case"] == rep.seal
    again = audit.write_fixtures(rep, state, tmp_path / "fixtures")
    assert [p.name for p in again] == [p.name for p in files] and again[0].read_text(encoding="utf-8") == files[0].read_text(encoding="utf-8")


def test_the_threshold_is_half_a_percent_on_a_sample_of_at_least_two_hundred():
    def rep(n, k):
        return audit.AuditReport(seal="s" * 16, sampled=n, statements=n, findings=tuple(audit.Finding(f"S{i}", "a", "TRUTH", ("X",)) for i in range(k)))
    assert rep(1000, 4).status == "PASS" and rep(1000, 5).status == "FAIL" and rep(199, 0).status == "UNMEASURED"
    assert rep(1000, 0).upper95_bp == 30


def test_a_stronger_verifier_is_a_port_and_can_only_add_findings(world):
    state, stmt = forge(world, text="I was in the library.", claims=(Claim(id="c9", proposition=At(actor="Elena", location="Library", interval=(0, 5)),
                                                                          sincerity="truthful", source="plan"),))
    t = ScriptedTransport(verify=[lambda r: json.dumps({"unreferenced_assertions": [], "segments": [
        {"index": 0, "asserts_exactly": False, "extra_assertions": [], "modality": "actual"}]})], repeat_last=True)
    hard, _ = audit.check_statement(state, stmt, ids=audit.engine_ids(state), names=audit._name_index(state.case),
                                    verifier=audit.model_verifier(t))
    assert any(h.startswith("VERIFIER:ASSERTS_NOT_EXACTLY") for h in hard) and t.calls("verify") == 1
    assert audit.audit_state(state, "s" * 32, sample=3, verifier=lambda s, st: []).verifier_used is True
    assert audit.audit_state(state, "s" * 32, sample=3).verifier_used is False


def test_a_verifier_that_cannot_be_reached_is_a_hole_in_the_audit_not_a_finding(world):
    def down(stmt, state):
        raise RuntimeError("provider down")
    rep = audit.audit_state(world, "s" * 32, verifier=down)
    assert rep.discrepancies == 0 and rep.verifier_errors == rep.sampled >= 200 and rep.status == "UNMEASURED"
    assert "unavailable" in rep.summary()["note"] and "provider down" not in json.dumps(rep.summary())
