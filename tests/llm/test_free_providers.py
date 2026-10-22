"""Free model providers (`--provider gemini|openrouter|ollama`): an OpenAI-compatible `Transport` for play and development.
No network here: every test injects `post`. What is guarded: the wire request carries the prompt, the schema and nothing else (I-11);
every failure maps onto the provider errors the renderer already fails closed on; the key comes only from the environment; the
leak guard still runs in front of it; and the nightly never counts a free model as a live measurement."""
from __future__ import annotations

import json

import pytest

from eidolon.debug import nightly
from eidolon.llm.ingress import ModelParser
from eidolon.llm.provider import (
    CompletionRequest, FREE_PROVIDERS, GuardedTransport, OpenAICompatTransport, PromptLeak, ProviderError, ProviderRefusal,
    ProviderTimeout, free_transport,
)


def reply(content='{"kind": "ask", "query_kind": "meta"}', finish="stop", **extra):
    return {"choices": [{"message": {"content": content, **extra}, "finish_reason": finish}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7}}


class Post:
    def __init__(self, answer=None, exc=None):
        self.answer, self.exc, self.calls = answer if answer is not None else reply(), exc, []

    def __call__(self, url, body, headers, timeout_s):
        self.calls.append((url, body, headers, timeout_s))
        if self.exc is not None:
            raise self.exc
        return self.answer


REQ = CompletionRequest("parse", "system text", json.dumps({"player_text": "hello"}), {"type": "object", "properties": {}})


def test_the_wire_request_is_the_prompt_and_the_schema_and_nothing_else():
    post = Post()
    done = OpenAICompatTransport("https://x.test/v1/", model="m1", api_key="k", post=post).complete(REQ)
    url, body, headers, _ = post.calls[0]
    assert url == "https://x.test/v1/chat/completions" and headers == {"Authorization": "Bearer k"}
    assert set(body) == {"model", "max_tokens", "messages", "response_format"}            # no tools, no functions (I-11)
    assert body["messages"] == [{"role": "system", "content": "system text"}, {"role": "user", "content": REQ.user}]
    assert body["response_format"]["json_schema"]["schema"] == REQ.schema
    assert (done.text, done.stop_reason, done.input_tokens, done.output_tokens, done.model) == (
        '{"kind": "ask", "query_kind": "meta"}', "end_turn", 11, 7, "m1")


def test_no_key_no_authorization_header():
    post = Post()
    OpenAICompatTransport("http://localhost:11434/v1", model="llama", post=post).complete(REQ)
    assert post.calls[0][2] == {}


@pytest.mark.parametrize("answer,exc", [
    (reply(finish="content_filter"), ProviderRefusal),
    (reply(refusal="no"), ProviderRefusal),
    ({"error": {"message": "quota"}}, ProviderError),
    ({"choices": []}, ProviderError),
])
def test_refusals_and_bad_replies_are_provider_errors(answer, exc):
    with pytest.raises(exc):
        OpenAICompatTransport("u", model="m", post=Post(answer)).complete(REQ)


@pytest.mark.parametrize("raised,exc", [(TimeoutError(), ProviderTimeout), (OSError("refused"), ProviderError),
                                        (ValueError("bad json"), ProviderError)])
def test_transport_failures_fail_closed(raised, exc):
    with pytest.raises(exc):
        OpenAICompatTransport("u", model="m", post=Post(exc=raised)).complete(REQ)


def test_a_truncated_reply_is_reported_as_such_so_the_parser_refuses_it():
    done = OpenAICompatTransport("u", model="m", post=Post(reply(finish="length"))).complete(REQ)
    assert done.stop_reason == "max_tokens"


def test_the_key_comes_from_the_environment_only():
    t = free_transport("gemini", environ={"GEMINI_API_KEY": "abc"})
    assert t._key == "abc" and t._model == FREE_PROVIDERS["gemini"][2] and t._url.startswith("https://generativelanguage")
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        free_transport("gemini", environ={})
    with pytest.raises(ValueError, match="--model"):
        free_transport("openrouter", environ={"OPENROUTER_API_KEY": "x"})
    assert free_transport("ollama", "llama3.1", environ={})._key is None
    g = free_transport("groq", environ={"GROQ_API_KEY": "gk"})
    assert g._key == "gk" and g._url == "https://api.groq.com/openai/v1/chat/completions" and g._drop == ()
    h = free_transport("github", environ={"GITHUB_MODELS_TOKEN": "ghp"})
    assert h._key == "ghp" and h._url == "https://models.github.ai/inference/chat/completions"
    with pytest.raises(ValueError, match="GITHUB_MODELS_TOKEN"):
        free_transport("github", environ={"GITHUB_TOKEN": "a general token is not picked up"})
    with pytest.raises(ValueError):
        free_transport("anthropic", environ={})                                            # not a free provider


def test_the_parser_works_over_it_and_the_leak_guard_still_stands_in_front():
    post = Post()
    action = ModelParser(OpenAICompatTransport("u", model="m", post=post)).parse("who are you really?", ["David"], "David")
    assert action is not None and len(post.calls) == 1
    guard = GuardedTransport(OpenAICompatTransport("u", model="m", post=post))
    guard.deny = frozenset({"SECRET_ID_7"})
    with pytest.raises(PromptLeak):
        guard.complete(CompletionRequest("parse", "mentions SECRET_ID_7", "{}", {}))
    assert len(post.calls) == 1, "a leaking prompt never reaches the free provider either"


class StubModel:
    """A free model that answers well, reached through the HTTP `post` seam; it records the model each call asked for."""

    def __init__(self):
        from tests.test_phase9_nightly import ParserToo
        self.stub, self.models = ParserToo(), []

    def __call__(self, url, body, headers, timeout_s):
        self.models.append((body["response_format"]["json_schema"]["name"], body["model"]))
        req = CompletionRequest(body["response_format"]["json_schema"]["name"], body["messages"][0]["content"],
                                body["messages"][1]["content"], body["response_format"]["json_schema"]["schema"])
        return reply(self.stub.complete(req).text)


def test_a_free_model_behind_an_injected_stand_in_is_never_counted_as_live(tmp_path):
    """ADR-31 makes a free-tier model a live measurement only on the REAL network path; a stand-in `post` is a script."""
    t = OpenAICompatTransport("u", model="gemini-test", post=StubModel(), provider="gemini")
    assert nightly.is_live(t) is False and nightly.is_live(nightly.BudgetedTransport(t, 5)) is False
    rep = nightly.run(tmp_path, transport=t, turns=12, audit_sample=12, corpus_turns_n=3, run_suites=False)
    assert rep["mode"] == "dry" and rep["model"] == "none"
    assert all(m["status"] == "UNMEASURED" for m in rep["metrics"] if m.get("source") != "human")
    assert nightly.exit_code(rep) == 3


def test_adr31_a_free_tier_model_on_the_network_is_a_live_measurement(tmp_path, monkeypatch):
    """The owner's decision (ADR-31): F-1 is closed by a free-tier model (e.g. Gemini). On the real HTTP path (`_http_post`,
    patched here so no network is used) the nightly judges PASS/FAIL, names the provider and model, audits on the provider's
    stronger free model, and paces the calls for the free tier."""
    from eidolon.llm import provider
    stub = StubModel()
    monkeypatch.setattr(provider, "_http_post", stub)
    t = free_transport("gemini", "gemini-flash-lite-latest", environ={"GEMINI_API_KEY": "k"})
    assert t.networked and nightly.is_live(t) and nightly.is_live(nightly.BudgetedTransport(t, 5))
    slept = []
    rep = nightly.run(tmp_path, transport=t, turns=12, audit_sample=12, corpus_turns_n=3, run_suites=False, pacer_sleep=slept.append)
    by = {m["id"]: m for m in rep["metrics"]}
    assert rep["mode"] == "live" and rep["provider"] == "gemini" and rep["model"] == "gemini-flash-lite-latest"
    assert by["N-1"]["status"] in ("PASS", "FAIL") and by["N-3"]["status"] in ("PASS", "FAIL"), by
    assert nightly.exit_code(rep) in (0, 1)
    audit = {m for role, m in stub.models if role == "verify"} - {"gemini-flash-lite-latest"}
    assert audit == {provider.FREE_AUDIT_MODELS["gemini"]}, stub.models[-5:]
    assert "gemini-flash-latest" in by["N-5"]["note"]
    assert rep["pacing"]["rpm"] == nightly.FREE_RPM and slept, "free-tier calls are paced"


def test_paced_spaces_calls_and_retries_only_what_the_provider_refused_for_load():
    from eidolon.llm.provider import Paced, ProviderError, ProviderRefusal
    now = [0.0]
    waits = []

    def sleep(s):
        waits.append(round(s, 3)); now[0] += s

    class Flaky:
        def __init__(self, errors): self.errors, self.calls = list(errors), 0
        def complete(self, req):
            self.calls += 1
            if self.errors:
                raise self.errors.pop(0)
            return "ok"

    p = Paced(Flaky([]), rpm=30, clock=lambda: now[0], sleep=sleep)
    p.complete(REQ); p.complete(REQ)
    assert waits == [2.0], "30 calls a minute is one every 2 s"
    p = Paced(Flaky([ProviderError("HTTP 429: quota"), ProviderError("HTTP 503: high demand")]), rpm=0, backoff_s=1,
              clock=lambda: now[0], sleep=sleep)
    assert p.complete(REQ) == "ok" and p.retried == 2
    for exc in (ProviderError("HTTP 401: bad key"), ProviderRefusal("refusal")):
        f = Flaky([exc])
        with pytest.raises(type(exc)):
            Paced(f, rpm=0, clock=lambda: now[0], sleep=sleep).complete(REQ)
        assert f.calls == 1, "only load refusals are retried"
    f = Flaky([ProviderError("HTTP 429")] * 9)
    with pytest.raises(ProviderError):
        Paced(f, rpm=0, retries=2, backoff_s=1, clock=lambda: now[0], sleep=sleep).complete(REQ)
    assert f.calls == 3


def test_the_cli_refuses_a_free_provider_without_its_key(monkeypatch):
    from eidolon import cli
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        cli._run_play(provider="gemini")


def test_gemini_is_not_sent_the_schema_keyword_it_rejects_and_extra_fields_are_still_refused_here():
    from eidolon.llm.ingress import ACTION_SCHEMA, parse_action
    from eidolon.llm.render import MalformedOutput
    post = Post()
    t = free_transport("gemini", environ={"GEMINI_API_KEY": "k"})
    t._post = post
    t.complete(CompletionRequest("parse", "s", "{}", ACTION_SCHEMA))
    assert "additionalProperties" not in json.dumps(post.calls[0][1]["response_format"])
    assert "additionalProperties" in json.dumps(ACTION_SCHEMA), "the constant itself is untouched"
    with pytest.raises((MalformedOutput, ValueError)):
        parse_action('{"kind": "ask", "query_kind": "meta", "smuggled": 1}')


@pytest.mark.parametrize("body", [b'{"error": {"message": "Unknown name additionalProperties"}}',
                                  b'[{"error": {"code": 400, "message": "Unknown name additionalProperties"}}]'])   # Gemini's list form
def test_an_http_error_carries_the_providers_explanation_but_not_the_key(monkeypatch, capsys, body):
    import io
    import urllib.error
    import urllib.request
    from eidolon.llm import provider

    def urlopen(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {},
                                     io.BytesIO(body))
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    t = OpenAICompatTransport("https://x.test/v1", model="m", api_key="SECRET-KEY-123", post=provider._http_post)
    with pytest.raises(ProviderError, match="HTTP 400: Unknown name additionalProperties"):
        t.complete(REQ)
    err = capsys.readouterr().err
    assert "HTTP 400" in err and "SECRET-KEY-123" not in err


def test_requests_carry_our_own_user_agent_because_groq_blocks_urllibs(monkeypatch):
    import urllib.request
    from eidolon.llm import provider
    seen = {}

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return json.dumps(reply()).encode()

    def urlopen(req, timeout):
        seen.update(req.headers)
        return Resp()
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    OpenAICompatTransport("https://x.test/v1", model="m", api_key="k", post=provider._http_post).complete(REQ)
    assert seen.get("User-agent") == "eidolon/0.1"


def test_a_non_json_reply_says_so(monkeypatch):
    import urllib.request
    from eidolon.llm import provider

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"OK"
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: Resp())
    with pytest.raises(ProviderError, match="non-JSON reply .* b'OK'"):
        OpenAICompatTransport("https://x.test/v1", model="m", post=provider._http_post).complete(REQ)


def test_the_verifier_is_told_that_words_about_the_speakers_own_memory_are_not_assertions():
    """Review NR-I1: with "a non-assert segment must assert nothing", a model could never voice a claimless act ("I can't
    remember") - every such turn cost three generations and the fallback, an act-correlated call pattern."""
    from eidolon.llm.render import SYSTEM_VERIFY
    assert "can't remember" in SYSTEM_VERIFY and "not assertions" in SYSTEM_VERIFY
    assert SYSTEM_VERIFY.rstrip().endswith("Reply with the JSON object only.")


def test_both_fallbacks_speak_the_same_line_for_a_plan_with_nothing_to_state():
    """Review NR-N9: `validator._fallback_text` said "..." while the renderer's template spoke the tone's line."""
    from eidolon.decision.llm import CLAIMLESS_LINES, claimless_line
    from eidolon.decision.strategy import DeliveryDirective, ResponsePlan
    from eidolon.decision.validator import _fallback_text
    plan = ResponsePlan(act="DONT_RECALL", delivery=DeliveryDirective("apologetic"))
    assert _fallback_text(plan, None) == claimless_line("apologetic") == CLAIMLESS_LINES["apologetic"]
    assert claimless_line("no such tone") == "I'd rather not say."
