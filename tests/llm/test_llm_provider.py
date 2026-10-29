"""The provider boundary (ADR-12, I-11, I-15) and the static rules that keep it a boundary: no tools,
constant effort, no invisible retries, cassettes, layering, no randomness (I-6)."""
from __future__ import annotations

import ast
import inspect
import pathlib
import re
import sys
from types import SimpleNamespace

import pytest

from eidolon.llm import provider
from eidolon.llm.fakes import (
    RecordedTransport, RecordingTransport, ScriptedTransport, cassette_dumps, cassette_loads,
)
from eidolon.llm.provider import (
    EFFORT, MODEL, AnthropicTransport, Completion, CompletionRequest, ProviderError, ProviderRefusal, ProviderTimeout,
    Transport,
)
from eidolon.llm.render import DRAFT_SCHEMA, ModelLLM, AnthropicLLM
from tests.llm.llm_helpers import DAVID, WHERE, approve, ask, build_initial_state, faithful, renderer, scripted

ROOT = pathlib.Path(__file__).resolve().parents[2] / "eidolon"


class FakeClient:
    """Duck-types `anthropic.Anthropic().messages.create`; records every kwarg it is given."""

    def __init__(self, resp=None, exc=None):
        self.kwargs = []
        self.messages = SimpleNamespace(create=self._create)
        self.resp = resp or SimpleNamespace(
            content=[SimpleNamespace(type="text", text='{"segments": []}')], stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=11, output_tokens=7, cache_read_input_tokens=5))
        self.exc = exc

    def _create(self, **kw):
        self.kwargs.append(kw)
        if self.exc:
            raise self.exc
        return self.resp


def _req(role="generate"):
    return CompletionRequest(role, "SYS", "{}", DRAFT_SCHEMA)


def test_request_sent_to_the_sdk_has_only_the_allowed_parameters():
    """I-11: no tools, tool_choice, functions, MCP servers, web/search or anything else a model call could grow."""
    c = FakeClient()
    AnthropicTransport(c).complete(_req())
    kw = c.kwargs[0]
    assert set(kw) == {"model", "max_tokens", "system", "messages", "output_config"}
    assert kw["model"] == MODEL == "claude-opus-5"
    assert kw["messages"] == [{"role": "user", "content": "{}"}]
    assert kw["system"] == [{"type": "text", "text": "SYS", "cache_control": {"type": "ephemeral"}}]
    assert kw["output_config"] == {"effort": "medium", "format": {"type": "json_schema", "schema": DRAFT_SCHEMA}}


@pytest.mark.parametrize("role, effort", [("parse", "low"), ("generate", "medium"), ("verify", "low")])
def test_effort_is_a_constant_of_the_route(role, effort):
    c = FakeClient()
    AnthropicTransport(c).complete(_req(role))
    assert c.kwargs[0]["output_config"]["effort"] == effort == EFFORT[role]


def test_transport_result_carries_text_and_usage():
    done = AnthropicTransport(FakeClient()).complete(_req())
    assert (done.text, done.stop_reason, done.input_tokens, done.output_tokens, done.cache_read_tokens, done.model) == (
        '{"segments": []}', "end_turn", 11, 7, 5, "claude-opus-5")


def test_refusal_is_a_provider_refusal_with_its_category():
    resp = SimpleNamespace(content=[], stop_reason="refusal", stop_details=SimpleNamespace(category="cyber"),
                           usage=SimpleNamespace(input_tokens=1, output_tokens=0))
    with pytest.raises(ProviderRefusal, match="cyber"):
        AnthropicTransport(FakeClient(resp)).complete(_req())


class APITimeoutError(Exception):
    pass


@pytest.mark.parametrize("exc, kind", [
    (TimeoutError("x"), ProviderTimeout), (APITimeoutError("x"), ProviderTimeout),
    (RuntimeError("boom"), ProviderError), (ConnectionError("x"), ProviderError),
])
def test_sdk_failures_are_classified(exc, kind):
    with pytest.raises(ProviderError) as e:
        AnthropicTransport(FakeClient(exc=exc)).complete(_req())
    assert type(e.value) is kind


def test_default_client_is_built_with_no_hidden_retries(monkeypatch):
    """Every retry must be the renderer's own — bounded and audited — never one inside the SDK."""
    seen = {}

    class Anthropic:
        def __init__(self, **kw):
            seen.update(kw)
            self.messages = SimpleNamespace(create=lambda **k: None)
    monkeypatch.setitem(sys.modules, "anthropic", SimpleNamespace(Anthropic=Anthropic))
    AnthropicTransport(timeout_s=12.0)
    assert seen == {"max_retries": 0, "timeout": 12.0}


def test_the_sdk_is_optional_and_imported_lazily(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", None)
    with pytest.raises(ImportError):
        AnthropicTransport()
    assert isinstance(AnthropicLLM(FakeClient()), ModelLLM)  # an injected client needs no SDK


def test_transport_protocol_exposes_only_complete():
    assert [n for n in vars(Transport) if not n.startswith("_")] == ["complete"]
    assert list(inspect.signature(Transport.complete).parameters) == ["self", "request"]
    assert list(inspect.signature(AnthropicTransport.complete).parameters) == ["self", "request"]


def test_max_tokens_stop_is_a_malformed_draft_not_a_partial_one():
    resp = SimpleNamespace(content=[SimpleNamespace(type="text", text='{"segments": [')], stop_reason="max_tokens",
                           usage=SimpleNamespace(input_tokens=1, output_tokens=8192))
    state = build_initial_state()
    r = ask(state, DAVID, WHERE, renderer=renderer(FakeClient(resp) and ScriptedTransport(
        generate=[Completion(text='{"segments": [', stop_reason="max_tokens")], verify=[approve], repeat_last=True)))
    audit = r.render_audit[0]
    assert audit.outcome == "fallback" and {a.outcome for a in audit.attempts} == {"malformed"}
    assert audit.attempts[0].violations == ("MALFORMED_OUTPUT:STOP_max_tokens",)


# ---- cassettes ----------------------------------------------------------------------------
def test_recorded_run_replays_identically_and_a_changed_prompt_is_a_hard_miss():
    state = build_initial_state()
    rec = RecordingTransport(scripted([faithful(1)], repeat_last=True))
    first = ask(state, DAVID, WHERE, renderer=renderer(rec))
    replay = ask(state, DAVID, WHERE, renderer=renderer(RecordedTransport(cassette_loads(cassette_dumps(rec.cassette)))))
    assert replay.text == first.text and replay.render_audit[0].outcome == "accepted"
    assert [c.prompt_hash for c in replay.render_audit[0].calls] == [c.prompt_hash for c in first.render_audit[0].calls]
    other = ask(state, DAVID, WHERE.model_copy(update={"raw": "A different question?"}),
                renderer=renderer(RecordedTransport(rec.cassette)))
    assert other.rejected and other.violations == ("PROVIDER_ERROR",) and other.state is state


def test_cassette_json_round_trip():
    c = {"abc": Completion(text="t", stop_reason="end_turn", input_tokens=3, output_tokens=4, cache_read_tokens=1, model="m")}
    assert cassette_loads(cassette_dumps(c)) == c


# ---- static rules over the package --------------------------------------------------------
def _imports(path: pathlib.Path) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf8"))):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            out.add(("." * node.level) + (node.module or ""))
    return out


def test_layering_decision_never_imports_llm_and_llm_never_imports_ui_or_debug():
    """§23.1: world <- minds <- evidence <- decision <- llm. Checked by test, not by convention."""
    for f in (ROOT / "decision").glob("*.py"):
        assert not any(i.startswith(("eidolon.llm", "..llm")) for i in _imports(f)), f  # `.llm` is decision.llm, the Phase 4 module
    for layer in ("world", "minds", "evidence"):
        for f in (ROOT / layer).glob("*.py"):
            assert not any("llm" in i.split(".") for i in _imports(f)), f
    for f in (ROOT / "llm").glob("*.py"):
        assert not any("debug" in i.split(".") for i in _imports(f)), f  # I-10


def test_no_randomness_or_uuid_anywhere_in_the_llm_package_i6():
    for f in (ROOT / "llm").glob("*.py"):
        assert not ({"random", "secrets", "uuid"} & {i.split(".")[0] for i in _imports(f)}), f
        assert "uuid4" not in f.read_text(encoding="utf8")


def test_the_sdk_is_never_imported_at_module_level():
    for f in (ROOT / "llm").glob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf8"))
        top = {a.name.split(".")[0] for n in tree.body if isinstance(n, ast.Import) for a in n.names}
        top |= {(n.module or "").split(".")[0] for n in tree.body if isinstance(n, ast.ImportFrom) and n.level == 0}
        assert "anthropic" not in top, f


def test_no_model_call_site_outside_the_transport():
    """I-11: the only place a request is built is `AnthropicTransport.complete`; nothing else names the SDK's call."""
    hits = [f.name for f in (ROOT / "llm").glob("*.py") if "messages.create" in f.read_text(encoding="utf8")]
    assert hits == ["provider.py"]
    src = inspect.getsource(provider.AnthropicTransport.complete)
    for banned in ("tools", "tool_choice", "mcp_servers", "web_search", "container", "betas", "thinking"):
        assert banned not in src


def test_time_is_only_read_where_a_clock_is_injected():
    """No wall-clock reads in the ingress or view code (deterministic, replayable)."""
    for name in ("ingress.py", "fakes.py"):
        assert not re.search(r"time\.(?:time|monotonic|sleep|perf_counter)", (ROOT / "llm" / name).read_text(encoding="utf8"))
