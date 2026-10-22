"""Test doubles (§28.2): everything the core suite needs so that no test touches a network.

`ScriptedTransport`   raw model text, errors and timeouts per role — for schema abuse and provider faults
`RecordingTransport` / `RecordedTransport`   cassettes keyed by prompt hash
`MutantLLM`           wraps `TemplateLLM` and injects one violation class into an otherwise faithful draft
`reordering`          a FAITHFUL generator that varies only segment structure (F-1)
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Callable

from ..decision.llm import Draft, Segment, TemplateLLM
from ..world.propositions import entities
from .provider import Completion, CompletionRequest, ProviderError, Transport


class ScriptedTransport:
    """Answers each role from its own queue. An item is a string (the model's text), a
    `Completion`, an exception (raised), or a function of the request. `repeat_last` answers every
    call after the queue runs dry with its last item — a model that keeps doing the same wrong
    thing. `requests` records everything that was sent."""

    def __init__(self, generate=(), verify=(), parse=(), *, repeat_last: bool = False):
        self.queues = {"generate": list(generate), "verify": list(verify), "parse": list(parse)}
        self.last: dict[str, object] = {}
        self.repeat_last = repeat_last
        self.requests: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> Completion:
        self.requests.append(request)
        queue = self.queues[request.role]
        if queue:
            item = self.last[request.role] = queue.pop(0)
        elif self.repeat_last and request.role in self.last:
            item = self.last[request.role]
        else:
            raise ProviderError("SCRIPT_EXHAUSTED")
        if callable(item) and not isinstance(item, BaseException):
            item = item(request)
        if isinstance(item, BaseException):
            raise item
        return item if isinstance(item, Completion) else Completion(text=item, model="scripted")

    def calls(self, role: str) -> int:
        return sum(r.role == role for r in self.requests)


class RecordingTransport:
    """Wraps a live transport and stores every completion under its prompt hash."""

    def __init__(self, inner: Transport):
        self.inner, self.cassette = inner, {}

    def complete(self, request: CompletionRequest) -> Completion:
        done = self.cassette[request.prompt_hash] = self.inner.complete(request)
        return done


class RecordedTransport:
    """Replays a cassette. A prompt that was never recorded is a hard failure, so a changed
    prompt cannot silently pass against stale recordings."""

    def __init__(self, cassette: dict[str, Completion]):
        self.cassette = cassette

    def complete(self, request: CompletionRequest) -> Completion:
        try:
            return self.cassette[request.prompt_hash]
        except KeyError:
            raise ProviderError("CASSETTE_MISS") from None


def cassette_dumps(cassette: dict[str, Completion]) -> str:
    return json.dumps({h: dataclasses.asdict(c) for h, c in sorted(cassette.items())}, indent=1)


def cassette_loads(text: str) -> dict[str, Completion]:
    return {h: Completion(**c) for h, c in json.loads(text).items()}


CASSETTE_FORMAT = 1


def cassette_save(path, cassette: dict[str, Completion], *, source: str, model: str = "", script: dict | None = None, note: str = "") -> None:
    """A cassette FILE: the completions keyed by prompt hash, plus what they are evidence of. `source` is "live" only when
    the completions came from a real provider (`eidolon.debug.nightly` writes it, and only for an `AnthropicTransport`);
    a cassette recorded from any scripted model says "scripted" and is never counted as a real-model measurement. `script`
    names the deterministic session that produced it, so a replay can re-drive exactly that session."""
    if source not in ("live", "scripted"):
        raise ValueError("a cassette's source is 'live' or 'scripted'")
    doc = {"format": CASSETTE_FORMAT, "source": source, "model": model, "script": script or {}, "note": note,
           "completions": {h: dataclasses.asdict(c) for h, c in sorted(cassette.items())}}
    Path(path).write_text(json.dumps(doc, indent=1, sort_keys=True), encoding="utf-8")


def cassette_load(path) -> tuple[dict, dict[str, Completion]]:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if doc.get("format") != CASSETTE_FORMAT:
        raise ValueError(f"unknown cassette format {doc.get('format')!r}")
    meta = {k: doc[k] for k in ("source", "model", "script", "note")}
    return meta, {h: Completion(**c) for h, c in doc["completions"].items()}


# --- faithful generators that vary only the SHAPE of the reply (F-1) ----------------------
def reordering(shape: str = "reversed"):
    """A `ScriptedTransport` generate item: says exactly the claims it was given, in full, tagged
    correctly — and is therefore ACCEPTED — but arranges them differently from the envelope.

    `reversed` last claim first · `rotated` first claim moved to the end · `merged` every claim in
    one segment, ids reversed · `split` each claim's own segment, order reversed, with an untagged
    `color` segment between them.

    This is what a real model does and no other fake in this file does: the engine's recorded
    `Statement.claims` must not move when it happens."""
    def gen(request) -> str:
        claims = json.loads(request.user)["claims"]
        if not claims:
            return json.dumps({"segments": [{"text": "I really cannot say.", "claim_ids": [], "kind": "color"}]})
        seg = lambda text, ids: {"text": text, "claim_ids": ids, "kind": "assert"}
        if shape == "merged":
            out = [seg(" ".join(c["content"] for c in claims), [c["id"] for c in reversed(claims)])]
        else:
            order = {"reversed": list(reversed(claims)), "rotated": claims[1:] + claims[:1],
                     "split": list(reversed(claims))}[shape]
            out = [seg(c["content"], [c["id"]]) for c in order]
            if shape == "split":
                out.insert(1, {"text": "It was a long night.", "claim_ids": [], "kind": "color"})
        return json.dumps({"segments": out})
    return gen


REORDERINGS = ("reversed", "rotated", "merged", "split")


# --- MutantLLM ---------------------------------------------------------------------------
def _first_assert(draft: Draft) -> int:
    return next(i for i, s in enumerate(draft.segments) if s.kind == "assert")


def _replace(draft: Draft, i: int, **kw) -> Draft:
    segs = list(draft.segments)
    segs[i] = segs[i].model_copy(update=kw)
    return Draft(segments=tuple(segs))


def _add(draft: Draft, text: str, kind: str = "color", ids: tuple = ()) -> Draft:
    return Draft(segments=draft.segments + (Segment(text=text, claim_ids=ids, kind=kind),))


def _invert(draft: Draft) -> Draft:
    """Flip the polarity of every asserting segment: "I never X" -> "I did X", "I was in" -> "I was not in"."""
    flip = lambda t: t.replace("I never ", "I did ", 1) if "I never " in t else t.replace("I was in", "I was not in", 1)
    return Draft(segments=tuple(x.model_copy(update={"text": flip(x.text)}) if x.kind == "assert" else x for x in draft.segments))


def _outsider(case, envelope, speaker, table: str) -> str:
    """Display name of an entity the case has but this envelope does not carry."""
    used = {speaker}
    for c in envelope.allowed_claims:
        for group in entities(c.proposition):
            used |= group
    pool = getattr(case, table)
    return next(pool[i].name for i in sorted(pool) if i not in used)


# name -> (mutation, caught_by_deterministic_checks_alone). `False`: the draft is well-formed and
# in-slot, so only a semantic verifier (or the template path's re-render equality) can see it.
MUTATIONS: dict[str, tuple[Callable, bool]] = {
    "unknown_entity": (lambda d, e, c, s: _add(d, "Ask Lady Ashcombe, she saw me."), True),
    "known_unpermitted_entity": (lambda d, e, c, s: _add(d, f"{_outsider(c, e, s, 'actors')} was upset."), True),
    "protected_fact": (lambda d, e, c, s: _add(d, "It was me all along.", "assert", ("protected_fact",)), True),
    "out_of_envelope_time": (lambda d, e, c, s: _replace(d, _first_assert(d), text=d.segments[_first_assert(d)].text + " Then at 03:33 I left."), True),
    "meta_text": (lambda d, e, c, s: _add(d, "As an AI language model I cannot say."), True),
    "confession": (lambda d, e, c, s: _replace(d, _first_assert(d), text="I killed him."), True),
    "tense_negation_inversion": (lambda d, e, c, s: _invert(d), False),
    "untagged_assertion": (lambda d, e, c, s: _replace(d, _first_assert(d), claim_ids=()), True),
    "slot_mismatch": (lambda d, e, c, s: _replace(d, _first_assert(d), text=f"I was in {_outsider(c, e, s, 'locations')} the whole time."), True),
    "nonverbal_leak": (lambda d, e, c, s: _add(d, f"His eyes flick to {_outsider(c, e, s, 'objects')}.", "nonverbal"), True),
    "unreferenced_implicature": (lambda d, e, c, s: _add(d, "Some people simply cannot be trusted, can they?"), False),
    "assertion_mislabelled_color": (lambda d, e, c, s: _replace(d, _first_assert(d), kind="color", claim_ids=()), True),
    "color_names_location": (lambda d, e, c, s: _add(d, f"{_outsider(c, e, s, 'locations').capitalize()} always smelled of dust."), True),
    "color_names_time": (lambda d, e, c, s: _add(d, "It felt like 22:15 forever."), True),
    "claim_omitted": (lambda d, e, c, s: Draft(segments=()), True),
    "canary_leak": (lambda d, e, c, s: _add(d, "EIDOLON-SESSION-CANARY"), True),
    "sincerity_label": (lambda d, e, c, s: _add(d, "I am being deceptive about this."), True),
    "length_fingerprint": (lambda d, e, c, s: _add(d, "It has been such a long and wearying evening for everyone in this house. " * 6), True),
}


class MutantLLM:
    """`LLMPort` that injects ONE violation class into the faithful draft `TemplateLLM` would have
    written. Every class must be caught by `validate_draft`; those flagged `False` above need the
    verifier and are tested with a verifier oracle."""

    def __init__(self, mutation: str, base=None):
        self.mutation, self.base = mutation, base or TemplateLLM()

    def generate(self, envelope, case, speaker, feedback: tuple[str, ...] = ()) -> Draft:
        draft = self.base.generate(envelope, case, speaker)
        return MUTATIONS[self.mutation][0](draft, envelope, case, speaker)


# --- a model that fails the way real ones do, and repairs when told (T-25) -------------------------------------
_DEFECTS = (
    lambda segs, claims: segs + [{"text": "Colonel Mustard can vouch for me.", "claim_ids": [], "kind": "color"}],     # unknown entity
    lambda segs, claims: [dict(s, claim_ids=[]) if s["kind"] == "assert" else s for s in segs],                         # untagged assertion
    lambda segs, claims: [dict(s, text=s["text"] + " Then at 03:33 I left.") if s["kind"] == "assert" else s for s in segs],  # stray time
    lambda segs, claims: segs + [{"text": "EIDOLON-SESSION-CANARY", "claim_ids": [], "kind": "color"}],                # canary
    lambda segs, claims: segs + [{"text": "As an AI language model I cannot say.", "claim_ids": [], "kind": "color"}],  # meta text
)


class RepairingTransport:
    """A `Transport` that stands in for a model that is sometimes wrong and mends itself when told, which `TemplateLLM`
    cannot do (§30 Phase 9 exit: "the long-session fallback rate is measured with a *repairing* LLM stub").

    * Every `fail_every`-th request (by a hash of the prompt, so it is deterministic and independent of call order) is
      answered with a rotating defect first - an unknown name, an untagged assertion, a stray clock time, the canary, meta
      talk - and answered faithfully once the request carries repair feedback (`revise` non-empty).
    * `unrepairable_every` > 0 makes that share of requests defective even after feedback: those turns MUST end in the
      deterministic fallback, which is what lets a test prove the fallback-rate measurement can actually fail.
    * The wording varies (three styles), so the validator is not only ever shown the template's own phrasing.
    * `verify` agrees with the tagging; `parse` is not scripted (a test that needs a parser brings its own queue)."""

    def __init__(self, *, fail_every: int = 5, unrepairable_every: int = 0, latency=None):
        self.fail_every, self.unrepairable_every, self.latency = fail_every, unrepairable_every, latency
        self.requests: list[CompletionRequest] = []
        self.repaired = self.defective = 0

    def complete(self, request: CompletionRequest) -> Completion:
        self.requests.append(request)
        if request.role == "verify":
            doc = json.loads(request.user)
            return Completion(text=json.dumps({"unreferenced_assertions": [], "segments": [
                {"index": s["index"], "asserts_exactly": True, "extra_assertions": [], "modality": "actual"}
                for s in doc["segments"]]}), model="repairing-stub")
        if request.role != "generate":
            raise ProviderError("NOT_SCRIPTED")
        doc = json.loads(request.user)
        # keyed by the turn, not by the attempt: a retry (which carries `revise`) must draw the same die as the first try
        h = int(hashlib.sha256(json.dumps({k: v for k, v in doc.items() if k != "revise"}, sort_keys=True).encode()).hexdigest()[:12], 16)
        claims = doc["claims"]
        pre, post = [("Well, ", ""), ("", " That is all."), ("", "")][h % 3]
        segs = ([{"text": f"{pre}{c['content']}{post}", "claim_ids": [c["id"]], "kind": "assert"} for c in claims]
                or [{"text": "I really cannot say.", "claim_ids": [], "kind": "color"}])
        broken = (self.fail_every and not doc["revise"] and (h // 7) % self.fail_every == 0) or \
                 (self.unrepairable_every and (h // 11) % self.unrepairable_every == 0)
        if broken:
            self.defective += 1
            segs = _DEFECTS[(h // 13) % len(_DEFECTS)](segs, claims)
        elif doc["revise"]:
            self.repaired += 1
        if self.latency is not None:
            self.latency(request, doc)
        return Completion(text=json.dumps({"segments": segs}), model="repairing-stub")

    def calls(self, role: str) -> int:
        return sum(r.role == role for r in self.requests)
