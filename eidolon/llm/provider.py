"""The provider boundary (ADR-12, I-11). A model call is `complete(request) -> Completion` and
nothing else: `CompletionRequest` has no field for tools, functions, MCP servers or network
switches, so no caller can add one. What comes back is text the caller must still parse and
validate. Only `GuardedTransport` reads engine vocabulary, and only to refuse to send it.
"""
from __future__ import annotations

import copy
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Literal, Protocol

from ..decision.validator import ENGINE_VOCAB, leaked_tokens

Role = Literal["parse", "generate", "verify"]
MODEL = "claude-opus-5"
# I-42: effort is a constant of the ROUTE. It is never computed from a plan, act or sincerity —
# a slower CONCESSION turn would be a timing channel (§12.3).
EFFORT: dict[Role, str] = {"parse": "low", "generate": "medium", "verify": "low"}


@dataclass(frozen=True)
class CompletionRequest:
    """`frozen=True` blocks attribute REBINDING only — a `dict` field on a frozen model is still a
    live container (I-4, the house rule `world/frozen.py` exists for). `schema` was a reference to
    a module-level constant, so a transport handed a request could rewrite `DRAFT_SCHEMA` for every
    later call in the process (F-5). Each request now owns a deep copy: a provider can scribble on
    its own request all it likes and the next request is built from the pristine constant."""
    role: Role
    system: str
    user: str
    schema: dict
    max_tokens: int = 8192

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema", copy.deepcopy(self.schema))

    @property
    def prompt_hash(self) -> str:
        return hashlib.sha256(f"{self.role}\n{self.system}\n{self.user}".encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Completion:
    text: str
    stop_reason: str = "end_turn"
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    model: str = ""


class ProviderError(Exception):
    """Any failure to obtain a completion. Fails the turn closed (I-15) unless the caller says
    otherwise."""


class ProviderTimeout(ProviderError):
    pass


class ProviderRefusal(ProviderError):
    """`stop_reason == "refusal"` (F-11). A renderer failure, not a plan failure."""


class Transport(Protocol):
    def complete(self, request: CompletionRequest) -> Completion: ...


class AnthropicTransport:
    """`Transport` over the Anthropic SDK: structured output (`output_config.format`), constant
    effort per route, a cacheable constant system block, refusal surfaced as an error. The SDK is
    an optional dependency (`pip install eidolon[llm]`), imported only when no client is injected.

    The default client is built with `max_retries=0`: every retry is the renderer's own bounded,
    audited retry, never an invisible one inside the SDK."""

    def __init__(self, client=None, *, model: str = MODEL, timeout_s: float = 30.0):
        if client is None:
            import anthropic  # ponytail: lazy; the core suite must not need the SDK or a key
            client = anthropic.Anthropic(max_retries=0, timeout=timeout_s)
        self._client, self._model = client, model

    def complete(self, request: CompletionRequest) -> Completion:
        try:
            resp = self._client.messages.create(
                model=self._model, max_tokens=request.max_tokens,
                system=[{"type": "text", "text": request.system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": request.user}],
                output_config={"effort": EFFORT[request.role],
                               "format": {"type": "json_schema", "schema": request.schema}},
            )
        except Exception as exc:  # SDK exceptions are classified by name so a fake client needs no SDK
            name = type(exc).__name__
            raise (ProviderTimeout if isinstance(exc, TimeoutError) or "Timeout" in name else ProviderError)(name) from exc
        if resp.stop_reason == "refusal":
            raise ProviderRefusal(getattr(getattr(resp, "stop_details", None), "category", None) or "refusal")
        usage = resp.usage
        return Completion(text=next((b.text for b in resp.content if b.type == "text"), ""),
                          stop_reason=resp.stop_reason or "end_turn",
                          input_tokens=getattr(usage, "input_tokens", 0),
                          output_tokens=getattr(usage, "output_tokens", 0),
                          cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
                          model=self._model)


FREE_PROVIDERS: dict[str, tuple[str, str | None, str | None]] = {
    # name: (OpenAI-compatible base URL, env var holding the key or None, default model or None = `--model` required)
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY", "gemini-flash-lite-latest"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", "openai/gpt-oss-120b"),      # JSON-schema output; the 20b misread questions
    "github": ("https://models.github.ai/inference", "GITHUB_MODELS_TOKEN", "openai/gpt-4.1-mini"),   # a fine-grained PAT, models:read
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", None),
    "ollama": ("http://localhost:11434/v1", None, None),
}


# ADR-31: the stronger model each free provider offers for the offline audit's verifier (§24's role, free tier); None = the
# provider has no clearly stronger free model, so the audit runs on the session's own and the report says so.
FREE_AUDIT_MODELS: dict[str, str | None] = {"gemini": "gemini-flash-latest", "groq": "openai/gpt-oss-120b", "github": "openai/gpt-4.1",
                                            "openrouter": None, "ollama": None}

# Gemini's OpenAI-compatible endpoint rejects some JSON-Schema keywords. Dropping them only loosens what the MODEL is told:
# every reply is still parsed strictly here (extra fields refused), so nothing becomes acceptable that was not before.
UNSUPPORTED_SCHEMA_KEYWORDS: dict[str, tuple[str, ...]] = {"gemini": ("additionalProperties",)}


def _without(schema, keywords: tuple[str, ...]):
    if isinstance(schema, dict):
        return {k: _without(v, keywords) for k, v in schema.items() if k not in keywords}
    if isinstance(schema, list):
        return [_without(v, keywords) for v in schema]
    return schema


def _http_post(url: str, body: dict, headers: dict, timeout_s: float) -> dict:
    import urllib.error
    import urllib.request
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 # Groq's firewall refuses urllib's default agent with a bare 403 (Cloudflare 1010)
                                 headers={"Content-Type": "application/json", "User-Agent": "eidolon/0.1", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            raw = r.read()
        try:
            return json.loads(raw)
        except ValueError as exc:           # e.g. a proxy or gateway answering in the provider's place
            raise ProviderError(f"non-JSON reply from {url}: {raw[:80]!r}") from exc
    except urllib.error.HTTPError as e:  # the provider's own explanation (never contains the key) - for the terminal
        try:
            doc = json.loads(e.read())
            doc = doc[0] if isinstance(doc, list) and doc else doc            # Gemini wraps its error in a list
            detail = doc.get("error", {}) if isinstance(doc, dict) else {}
            msg = str(detail.get("message", ""))[:300]
        except Exception:  # noqa: BLE001
            msg = ""
        raise ProviderError(f"HTTP {e.code}: {msg}") from e


class OpenAICompatTransport:
    """`Transport` over any OpenAI-compatible chat endpoint - the free ones in `FREE_PROVIDERS` (Gemini's free tier through
    AI Studio, OpenRouter's free models, a local Ollama). Same contract as `AnthropicTransport`: `complete(system, user,
    schema)` and nothing else (structured output via `response_format`, no tools), a refusal surfaced as `ProviderRefusal`,
    every other failure as `ProviderError`/`ProviderTimeout`. Stdlib HTTP only. For play and development: the nightly never
    counts it as live (`is_live`), because the Phase 9 criteria are defined for the configured Claude models."""

    def __init__(self, base_url: str, *, model: str, api_key: str | None = None, timeout_s: float = 60.0, post=None,
                 drop_keywords: tuple[str, ...] = (), provider: str = ""):
        self._base, self._url = base_url, base_url.rstrip("/") + "/chat/completions"
        self._model, self._key, self._timeout = model, api_key, timeout_s
        self._post, self._drop, self.provider = post, drop_keywords, provider

    def with_model(self, model: str) -> "OpenAICompatTransport":
        """The same endpoint, key and network path with another model (the audit's verifier, ADR-31)."""
        return OpenAICompatTransport(self._base, model=model, api_key=self._key, timeout_s=self._timeout, post=self._post,
                                     drop_keywords=self._drop, provider=self.provider)

    @property
    def networked(self) -> bool:
        """True when calls go over the real network (`_http_post`), not to an injected stand-in. Read at call time, so a test
        that patches `provider._http_post` exercises the live path without a network."""
        return self._post is None

    def complete(self, request: CompletionRequest) -> Completion:
        body = {"model": self._model, "max_tokens": request.max_tokens,
                "messages": [{"role": "system", "content": request.system}, {"role": "user", "content": request.user}],
                "response_format": {"type": "json_schema", "json_schema": {"name": request.role,
                                                                           "schema": _without(request.schema, self._drop)}}}
        headers = {"Authorization": f"Bearer {self._key}"} if self._key else {}
        try:
            doc = (self._post or _http_post)(self._url, body, headers, self._timeout)
        except Exception as exc:  # classified by name, like the SDK path, so a fake `post` needs no network
            name = type(exc).__name__
            import sys
            print(f"[eidolon] {self._model}: provider call failed: {exc}", file=sys.stderr)   # the operator's terminal, not the page
            if isinstance(exc, ProviderError):
                raise
            raise (ProviderTimeout if isinstance(exc, TimeoutError) or "timeout" in name.lower() else ProviderError)(name) from exc
        try:
            choice = doc["choices"][0]
            msg, finish = choice.get("message") or {}, choice.get("finish_reason")
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise ProviderError("BAD_RESPONSE") from exc
        if finish == "content_filter" or msg.get("refusal"):
            raise ProviderRefusal("refusal")
        usage = doc.get("usage") or {}
        return Completion(text=msg.get("content") or "",
                          stop_reason={"stop": "end_turn", "length": "max_tokens"}.get(finish, finish or "end_turn"),
                          input_tokens=usage.get("prompt_tokens", 0) or 0, output_tokens=usage.get("completion_tokens", 0) or 0,
                          model=self._model)


def free_transport(provider: str, model: str | None = None, *, environ=None) -> OpenAICompatTransport:
    """A transport for one of `FREE_PROVIDERS`, its key read from the environment (never from a command line or a file)."""
    import os
    env = os.environ if environ is None else environ
    if provider not in FREE_PROVIDERS:
        raise ValueError(f"unknown provider {provider!r}; choose one of {sorted(FREE_PROVIDERS)}")
    url, key_var, default = FREE_PROVIDERS[provider]
    model = model or default
    if not model:
        raise ValueError(f"--model is required for {provider}")
    key = env.get(key_var) if key_var else None
    if key_var and not key:
        raise ValueError(f"set {key_var} in your environment first")
    return OpenAICompatTransport(url, model=model, api_key=key, drop_keywords=UNSUPPORTED_SCHEMA_KEYWORDS.get(provider, ()),
                                 provider=provider)


class Paced:
    """Free-tier pacing for MEASUREMENT runs only (the nightly, the live suites) - never for play, where a retry would make the
    clock act-dependent (I-42). At most `rpm` calls per minute reach `inner`; a call refused for load (HTTP 429/503 - the free
    tier's "rate limited" / "high demand") is retried up to `retries` times after `backoff_s`, doubling. Every wait and retry is
    counted, so the report can say how the numbers were obtained."""

    def __init__(self, inner, rpm: float, *, retries: int = 4, backoff_s: float = 20.0, clock=time.monotonic, sleep=time.sleep):
        self.inner, self.rpm, self.retries, self.backoff_s = inner, rpm, retries, backoff_s
        self.clock, self.sleep = clock, sleep
        self.last: float | None = None
        self.waited_s = 0.0
        self.retried = 0

    def _wait(self, seconds: float) -> None:
        if seconds > 0:
            self.waited_s += seconds
            self.sleep(seconds)

    def complete(self, request: CompletionRequest) -> Completion:
        delay = self.backoff_s
        for attempt in range(self.retries + 1):
            if self.rpm > 0 and self.last is not None:
                self._wait(60.0 / self.rpm - (self.clock() - self.last))
            self.last = self.clock()
            try:
                return self.inner.complete(request)
            except ProviderRefusal:
                raise
            except ProviderError as exc:
                if attempt == self.retries or not any(code in str(exc) for code in ("HTTP 429", "HTTP 503")):
                    raise
                self.retried += 1
                self._wait(delay)
                delay *= 2
        raise ProviderError("UNREACHABLE")


@dataclass(frozen=True)
class LLMCallRecord:
    """§27.1 `LLMCallRecord`. Engine-side trace only; carries the prompt's hash, not the prompt."""
    role: str
    model: str
    effort: str
    prompt_hash: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    stop_reason: str = ""
    latency_ms: int = 0
    error: str = ""


class PromptLeak(Exception):
    """An engine identifier was found in a serialized prompt. That is the engine's bug, not the
    model's: the call is never made and the turn fails closed."""


class GuardedTransport:
    """The last checkpoint before a prompt leaves the process — it wraps EVERY route (generate,
    verify, parse). Player-typed text (`untrusted` JSON keys) is exempt: what the player typed
    is not something the engine leaked. Also keeps the call log the trace needs.

    ponytail: mutable `deny`, set per turn by the renderer; one guard per session, not thread-safe."""

    def __init__(self, inner: Transport, *, untrusted: frozenset[str] = frozenset({"player_query", "player_text"}),
                 clock=time.monotonic):
        self._inner, self._untrusted, self._clock = inner, untrusted, clock
        self.deny: frozenset[str] = frozenset()
        self.calls: list[LLMCallRecord] = []

    def drain(self) -> tuple[LLMCallRecord, ...]:
        out, self.calls = tuple(self.calls), []
        return out

    def _scan(self, request: CompletionRequest) -> list[str]:
        doc = json.loads(request.user)
        for key in self._untrusted:
            doc.pop(key, None)
        text = request.system + "\n" + json.dumps(doc, ensure_ascii=False)
        return leaked_tokens(text, self.deny) + [w for w in ENGINE_VOCAB if w in text.lower()]

    def complete(self, request: CompletionRequest) -> Completion:
        hits = self._scan(request)
        if hits:
            self.calls.append(LLMCallRecord(request.role, "", EFFORT[request.role], request.prompt_hash, error="PROMPT_LEAK"))
            raise PromptLeak(hits)
        start = self._clock()
        try:
            done = self._inner.complete(request)
        except Exception as exc:
            self.calls.append(LLMCallRecord(request.role, "", EFFORT[request.role], request.prompt_hash,
                                            latency_ms=int((self._clock() - start) * 1000), error=type(exc).__name__))
            raise
        self.calls.append(LLMCallRecord(request.role, done.model, EFFORT[request.role], request.prompt_hash,
                                        done.input_tokens, done.output_tokens, done.cache_read_tokens,
                                        done.stop_reason, int((self._clock() - start) * 1000)))
        return done
