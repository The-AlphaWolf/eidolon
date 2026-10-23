"""Phase 9 - the nightly job and cassettes: what is measured against a real model, what is not, and that the two cannot be
confused. No test here touches a network: the provider is always a stand-in, and the one stand-in that impersonates the SDK is
there to reach the PASS/FAIL arithmetic offline, not to claim a result."""
from __future__ import annotations

import datetime
import json
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from eidolon.debug import nightly
from eidolon.llm.fakes import (
    RecordedTransport, RecordingTransport, RepairingTransport, ScriptedTransport, cassette_load, cassette_save,
)
from eidolon.llm.provider import AnthropicTransport, Completion, CompletionRequest, GuardedTransport, ProviderError
from eidolon.llm.render import LLMRenderer, ModelLLM
from eidolon.store import Save
from tests.llm.llm_helpers import approve, faithful

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "cases" / "generated"
DAY = datetime.date(2026, 10, 22)
CASSETTES = ROOT / "tests" / "llm" / "cassettes"


class FakeAnthropicClient:
    """Looks like the SDK's client to `is_live` (its class lives in a module named `anthropic.*`) and answers from a stub model.
    This is the ONLY object in the test-suite that is allowed to make `is_live` true; it makes no network call."""
    __module__ = "anthropic.fake"

    def __init__(self, inner):
        self.inner, self.calls = inner, 0
        self.messages = SimpleNamespace(create=self.create)

    def create(self, *, model, max_tokens, system, messages, output_config):
        props = output_config["format"]["schema"]["properties"]
        role = "verify" if "unreferenced_assertions" in props else "generate" if "segments" in props else "parse"
        self.calls += 1
        done = self.inner.complete(CompletionRequest(role, system[0]["text"], messages[0]["content"], {}))
        return SimpleNamespace(stop_reason="end_turn", stop_details=None, content=[SimpleNamespace(type="text", text=done.text)],
                               usage=SimpleNamespace(input_tokens=120, output_tokens=40, cache_read_input_tokens=60))


class ParserToo:
    """A stub model that also answers the parse role the way a correct parser would."""

    def __init__(self, inner=None, wrong=False):
        self.inner, self.wrong = inner or RepairingTransport(fail_every=5), wrong

    def complete(self, request):
        if request.role == "parse":
            return Completion(text=json.dumps({"kind": "ask", "query_kind": "did_you" if self.wrong else "meta"}))
        return self.inner.complete(request)


def live_transport(inner):
    return AnthropicTransport(FakeAnthropicClient(inner))


# ====================================================================== is_live: the one rule
@pytest.mark.parametrize("make", [
    lambda: nightly.DryTransport(), lambda: ScriptedTransport(), lambda: RecordedTransport({}), lambda: RepairingTransport(),
    lambda: AnthropicTransport(SimpleNamespace(messages=None)),                                     # a client that is not the SDK's
    lambda: nightly.BudgetedTransport(RecordingTransport(GuardedTransport(nightly.DryTransport())), 5),
], ids=["dry", "scripted", "recorded", "repairing", "fake_client", "wrapped_dry"])
def test_nothing_but_the_real_sdk_client_counts_as_live(make):
    assert nightly.is_live(make()) is False


def test_a_real_provider_is_recognised_however_it_is_wrapped():
    t = live_transport(RepairingTransport())
    assert nightly.is_live(t) is True
    assert nightly.is_live(nightly.BudgetedTransport(RecordingTransport(GuardedTransport(t)), 5)) is True
    assert nightly.is_live(ModelLLM(t).transport) is True


# ====================================================================== the dry run: everything computed, nothing claimed
def run_dry(tmp_path, **kw):
    return nightly.run(tmp_path, turns=kw.pop("turns", 24), audit_sample=kw.pop("audit_sample", 30), corpus_turns_n=kw.pop("corpus_turns_n", 6),
                       today=DAY, run_suites=kw.pop("run_suites", False), **kw)         # never spawn the live suites from a unit test


def test_without_a_provider_every_metric_is_unmeasured_and_the_figures_are_kept_aside(tmp_path, monkeypatch):
    def no_network(*a, **k):
        raise AssertionError("the dry run touched the network")
    monkeypatch.setattr(socket.socket, "connect", no_network)
    rep = run_dry(tmp_path)
    assert rep["mode"] == "dry" and rep["model"] == "none" and rep["turns_committed"] == 24
    byid = {m["id"]: m for m in rep["metrics"]}
    assert set(byid) == {f"N-{i}" for i in range(1, 9)}
    assert all(m["status"] == "UNMEASURED" for m in rep["metrics"]), [(m["id"], m["status"]) for m in rep["metrics"]]
    for mid in ("N-1", "N-3", "N-4", "N-5", "N-6"):
        assert byid[mid]["value"] is None and "dry_value" in byid[mid] and byid[mid]["source"] == "not live"
    assert byid["N-3"]["dry_value"] == 10000                         # the rehearsal parser says `meta` to everything: the plumbing works
    assert byid["N-8"]["source"] == "human" and "nothing here can stand in" in byid["N-8"]["note"]
    assert nightly.exit_code(rep) == 3                               # nothing was measured live
    assert (tmp_path / "nightly-2026-10-22.json").is_file()
    assert json.loads((tmp_path / "nightly-2026-10-22.json").read_text(encoding="utf-8"))["mode"] == "dry"


def test_the_dry_run_report_is_deterministic_apart_from_where_it_wrote(tmp_path):
    a = run_dry(tmp_path / "a")
    b = run_dry(tmp_path / "b")
    strip = lambda r: {k: v for k, v in r.items() if k not in ("slo",)}                           # noqa: E731 (latencies vary)
    assert strip(a)["metrics"] == strip(b)["metrics"] and a["audit"] == b["audit"] and a["corpus"] == b["corpus"]


# ====================================================================== the arithmetic, reached offline through the SDK-shaped stand-in
def test_a_live_run_passes_when_the_numbers_pass(tmp_path):
    rep = run_dry(tmp_path, transport=live_transport(ParserToo()), turns=40, audit_sample=60)
    assert rep["mode"] == "live" and rep["provider_calls"] > 80
    by = {m["id"]: m for m in rep["metrics"]}
    assert by["N-1"]["status"] == "PASS" and by["N-1"]["value"] == 0 and by["N-3"]["status"] == "PASS" and by["N-4"]["status"] == "PASS"
    assert by["N-5"]["status"] == "UNMEASURED" and "sampled" in by["N-5"]["note"], "under 200 statements the 0.5% bound is not judged"
    assert by["N-8"]["status"] == "UNMEASURED" and nightly.exit_code(rep) == 0


def test_a_live_run_fails_when_the_model_does_not_repair_or_the_parser_is_fooled(tmp_path):
    rep = run_dry(tmp_path / "a", transport=live_transport(ParserToo(RepairingTransport(fail_every=0, unrepairable_every=1))), turns=30)
    by = {m["id"]: m for m in rep["metrics"]}
    assert by["N-1"]["status"] == "FAIL" and by["N-1"]["value"] > nightly.SESSION_FALLBACK_BP and nightly.exit_code(rep) == 1
    rep = run_dry(tmp_path / "b", transport=live_transport(ParserToo(wrong=True)), turns=30)
    by = {m["id"]: m for m in rep["metrics"]}
    assert by["N-3"]["status"] == "FAIL" and by["N-3"]["value"] < 10000 and nightly.exit_code(rep) == 1
    assert "paraphrase_override" in by["N-3"]["note"] or "coercion" in by["N-3"]["note"]


def test_when_the_budget_runs_out_nothing_that_needed_the_missing_turns_is_judged(tmp_path):
    rep = run_dry(tmp_path, transport=live_transport(ParserToo()), turns=40, max_calls=25)
    by = {m["id"]: m for m in rep["metrics"]}
    assert rep["budget_exhausted"] is True and rep["provider_calls"] == 25 and rep["turns_committed"] < 40
    assert by["N-1"]["status"] == "UNMEASURED" and "incomplete" in by["N-1"]["note"]
    assert by["N-3"]["status"] == "UNMEASURED", "a classification taken on a budget that ran out is not a classification"
    assert nightly.exit_code(rep) in (0, 1, 3)


def test_the_budgeted_transport_fails_the_call_it_cannot_pay_for_like_any_provider_error():
    b = nightly.BudgetedTransport(ScriptedTransport(parse=['{"kind":"clarify"}'] * 3), 2)
    req = CompletionRequest("parse", "s", "{}", {})
    b.complete(req), b.complete(req)
    with pytest.raises(ProviderError, match="BUDGET_EXHAUSTED"):
        b.complete(req)
    assert b.calls == 2 and b.exhausted


def test_the_nightly_defaults_are_big_enough_for_the_audit_to_be_judged_and_for_the_budget_to_cover_a_full_run():
    from eidolon.debug import audit
    assert nightly.DEFAULT_AUDIT_SAMPLE >= audit.MIN_AUDIT
    rep = run_dry(Path(__import__("tempfile").mkdtemp()), turns=40, audit_sample=60, corpus_turns_n=4)
    per_turn = (rep["provider_calls"] - 225 - 60) / 40            # an upper bound: it still includes the sampled corpus turns
    assert 300 * max(per_turn, 3.0) + 225 + 25 * 3 + nightly.DEFAULT_AUDIT_SAMPLE <= nightly.DEFAULT_MAX_CALLS,         "a 300-turn session (even at three calls a turn) plus the parse pass, the sample and the audit fits the default budget"


def test_a_live_run_launches_the_suites_by_default_and_a_dry_one_never_does(tmp_path, monkeypatch):
    launched = []
    monkeypatch.setattr(nightly.subprocess, "run", lambda *a, **k: launched.append((a, k)) or SimpleNamespace(returncode=0, stdout="ok"))
    run_dry(tmp_path / "dry", run_suites=True)
    assert launched == [], "no provider, no suites"
    rep = run_dry(tmp_path / "live", transport=live_transport(ParserToo()), turns=12, run_suites=True)
    by = {m["id"]: m for m in rep["metrics"]}
    assert len(launched) == 1 and launched[0][1]["env"]["EIDOLON_LIVE"] == "1" and by["N-2"]["status"] == "PASS"


def test_the_nightly_cli_runs_dry_without_a_key_and_exits_3(tmp_path):
    env = {k: v for k, v in __import__("os").environ.items() if k != "ANTHROPIC_API_KEY"}
    r = subprocess.run([sys.executable, "-m", "eidolon.debug", "nightly", "--out", str(tmp_path), "--turns", "12", "--audit-sample", "12",
                        "--dry"], capture_output=True, text=True, cwd=ROOT, env=env)
    assert r.returncode == 3, r.stderr
    assert "mode=dry" in r.stdout and r.stdout.count("UNMEASURED") >= 7 and "PASS" not in r.stdout.replace("PASSES", "")


# ====================================================================== cassettes
def drive_with(transport, tmp_path, turns=14):
    p = tmp_path / "s.db"
    Save.create(p, CASES / "study_party_s4.json", seed=7).close()
    s = Save.open(p, writable=True)
    ren = LLMRenderer(ModelLLM(transport))
    done = nightly.drive(s, ren, turns)
    texts = [st.text for st in s.state.decision.statements.all()]
    out = (texts, s.state_hash(), s.last_seq, done)
    s.close()
    return out


def test_a_session_recorded_to_a_cassette_file_replays_identically_with_no_model(tmp_path):
    live = ScriptedTransport(generate=[faithful(1)], verify=[approve], repeat_last=True)
    rec = RecordingTransport(live)
    (tmp_path / "a").mkdir()
    first = drive_with(rec, tmp_path / "a", turns=14)
    path = tmp_path / "x.cassette.json"
    cassette_save(path, rec.cassette, source="scripted", model="scripted", script={"case": "study_party_s4", "seed": 7, "turns": 14})
    meta, cas = cassette_load(path)
    assert meta["source"] == "scripted" and meta["script"]["turns"] == 14 and len(cas) == len(rec.cassette) > 10
    (tmp_path / "b").mkdir()
    second = drive_with(RecordedTransport(cas), tmp_path / "b", turns=14)
    assert second == first and first[3] == 14, "a replay from the cassette is the recorded session, byte for byte"


def test_a_changed_prompt_is_a_miss_that_fails_the_turn_closed_not_a_stale_pass(tmp_path, monkeypatch):
    rec = RecordingTransport(ScriptedTransport(generate=[faithful(1)], verify=[approve], repeat_last=True))
    (tmp_path / "a").mkdir()
    drive_with(rec, tmp_path / "a", turns=6)
    from eidolon.llm import render
    monkeypatch.setattr(render, "SYSTEM_GENERATE", render.SYSTEM_GENERATE + " One new sentence.")
    (tmp_path / "b").mkdir()
    texts, _, _, done = drive_with(RecordedTransport(rec.cassette), tmp_path / "b", turns=6)
    assert done == 0 and texts == [], "every generate call missed: each turn failed closed and committed nothing (I-15)"
    t = RecordedTransport(rec.cassette)
    with pytest.raises(ProviderError, match="CASSETTE_MISS"):
        t.complete(CompletionRequest("generate", "something new", "{}", {}))


def test_a_scripted_cassette_can_never_pass_for_a_real_model_one(tmp_path):
    with pytest.raises(ValueError):
        cassette_save(tmp_path / "x.json", {}, source="real")
    cassette_save(tmp_path / "x.json", {}, source="scripted")
    assert cassette_load(tmp_path / "x.json")[0]["source"] == "scripted"
    (tmp_path / "bad.json").write_text(json.dumps({"format": 99, "completions": {}}), encoding="utf-8")
    with pytest.raises(ValueError):
        cassette_load(tmp_path / "bad.json")


def test_recorded_real_model_cassettes_replay_through_the_validator():
    """§28.1 "LLM output validation: recorded real outputs (cassettes) replayed through the validator". The cassettes in
    `tests/llm/cassettes/` that a LIVE nightly run recorded (`--record`). There are none until one has run against a real
    provider, and this test says so instead of passing."""
    files = sorted(CASSETTES.glob("*.cassette.json")) if CASSETTES.is_dir() else []
    live = [f for f in files if cassette_load(f)[0]["source"] == "live"]
    if not live:
        pytest.skip("UNMEASURED: no cassette recorded from a real provider exists in this repository (no key, no network here)")
    for f in live:
        meta, cas = cassette_load(f)
        sc = meta["script"]
        d = f.parent / "replay"
        d.mkdir(exist_ok=True)
        p = d / f"{f.stem}.db"
        p.unlink(missing_ok=True)
        Save.create(p, CASES / f"{sc['case']}.json", seed=sc["seed"]).close()
        s = Save.open(p, writable=True)
        assert nightly.drive(s, LLMRenderer(ModelLLM(RecordedTransport(cas))), sc["turns"]) >= int(sc["turns"] * 0.95)
        s.close()
