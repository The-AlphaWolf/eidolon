"""Phase 9 — §27.1 `TurnTrace`: the typed, bounded, redacted audit record of ONE turn (or of one attempt that committed
nothing), and the producer that builds it from what the real turn path already computed.

A trace is observation, never state (§27.1): it is written AFTER the commit transaction, best-effort, to `traces.db`, a
second file that never travels with a save and is never read by the player process (I-10, ADR-13). Nothing here is read by
the fold, so a missing, stale or forged trace cannot change a replay (I-22).

What the record holds, field by field against §27.1 (the report has the table):

* **Identifiers become opaque handles.** The architecture lists engine ids in the trace (beliefs, memories, claims, secrets);
  a file that holds them is a file that names the murder secret. `ref(seal, id)` is a 12-hex digest keyed by the case seal —
  the same device `game.handle` uses for evidence — so a debug process that opens the sealed case can resolve every handle
  (`resolver`), and the trace file alone resolves nothing. Entity ids (`David`, `Study`) are the names the player already
  sees; they stay.
* **Content becomes counts and hashes.** Propositions, the envelope, the prompt and the committed rows are NOT copied:
  each is reproducible from the save (a pure builder over the replayed pre-turn state) and every copy is another place a
  protected fact could leak. The envelope is its sha256 and its shape; the prompt is the `prompt_hash` §27.1 already asks for;
  the committed rows are their kinds and the log head they left.
* **Free text is scrubbed and clamped** (`scrub`): the canary, credential-shaped tokens and every engine id are replaced, and
  every string has a hard length. A leak the model attempted is a boolean (`canary_seen`), not the leaked text.
* **No float, no free-form container** (I-17): `strict` models, `extra="forbid"`, closed Literals, bounded tuples; scores are
  basis points. `MAX_TRACE_BYTES` bounds the whole record (checked on construction).
* **Failures are told apart**: a model refusal, a validation failure, a timeout, a transport error, a verifier failure, the
  deterministic fallback and a rejected game action are different members of `failures`, not one "error".

Layering: the top of the stack beside `game` (it reads `decision`, `llm` results and a `Save`; nothing below imports it, and
`store` imports nothing from here — the sink scrubs on its own).
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .decision.turn import CANARY

log = logging.getLogger("eidolon.trace")

TRACE_VERSION = 1
MAX_TRACE_BYTES = 64 * 1024
MAX_TEXT = 1200            # a draft's text; the player's raw line is capped by ingress at 1000
MAX_DIGEST = 600

# Prices are NOT guessed: with no entry for a model the cost is `None` and the SLO says UNMEASURED. Fill in
# `{model: (input, output, cache_read)}` in micro-USD per million tokens to turn cost on.
PRICES_PER_MTOK: dict[str, tuple[int, int, int]] = {}


# --------------------------------------------------------------------------------- the model
Int = Annotated[int, Field(strict=True, ge=0, le=2**31)]
SInt = Annotated[int, Field(strict=True, ge=-(2**31), le=2**31)]
Handle = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{12}$")]
Sha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Short = Annotated[str, StringConstraints(max_length=80)]
Name = Annotated[str, StringConstraints(max_length=48, pattern=r"^[A-Za-z0-9_. \-]+$")]
Code = Annotated[str, StringConstraints(max_length=96, pattern=r"^[A-Za-z0-9_\[\]:]+$")]

Kind = Literal["ask", "say", "goto", "search", "hypothesis", "withdraw", "accuse"]
Outcome = Literal["committed", "committed_fallback", "rejected", "refused_by_store", "clarify", "blocked"]
Failure = Literal["provider_refusal", "provider_timeout", "provider_error", "prompt_leak", "malformed_output",
                  "validation_failure", "verifier_failure", "renderer_exception", "plan_rejected", "rejected_action",
                  "store_refused", "deterministic_fallback", "clarify", "ingress_blocked", "parse_failed"]
COMMITTED = ("committed", "committed_fallback")
ACTION_REJECTIONS = frozenset({"CASE_CLOSED", "UNKNOWN_HYPOTHESIS", "BAD_HYPOTHESIS", "BAD_ACCUSATION", "UNHELD_CITATION",
                               "UNHELD_PRESENTED_REF", "OUTSIDE_CANDIDATE_DOMAIN"})


class _T(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class TraceIngress(_T):
    raw: Annotated[str, StringConstraints(max_length=1000)]
    raw_len: Int
    stripped: Annotated[tuple[Short, ...], Field(max_length=32)] = ()
    markers: Annotated[tuple[Short, ...], Field(max_length=8)] = ()
    blocked: Code | None = None
    escalated: bool = False


class TraceParsed(_T):
    kind: Short
    query_kind: Short | None = None
    tone: Short | None = None
    subject: Short | None = None
    object: Short | None = None
    location: Short | None = None
    predicate_hint: Short | None = None
    time_text: Short | None = None
    target: Short | None = None
    method: Short | None = None


class TraceGrounded(_T):
    outcome: Literal["asked", "explore", "clarify", "refused", "structured"]
    reason: Code | Literal[""] = ""
    query_kind: Short | None = None


class TraceMemory(_T):
    ref: Handle
    score_bp: Int


class TraceView(_T):
    retrieval_band: Literal["strong", "weak", "none"]
    retrieved: Handle | None = None
    memories: Annotated[tuple[TraceMemory, ...], Field(max_length=8)] = ()
    standing_claims: Int = 0
    known_topic: bool = False
    layer: Int = 0
    secret: Handle | None = None
    detective_evidence: Int = 0
    detective_statements: Int = 0
    detective_accusations: Int = 0


class TracePeel(_T):
    secret: Handle
    frm: Int
    to: Int
    weight_bp: Int
    peeled: bool
    stonewalled: bool


class TraceAssessment(_T):
    threat_bp: Int
    presented: bool
    contradicts_standing: bool
    pressure_delta_bp: SInt = 0
    peels: Annotated[tuple[TracePeel, ...], Field(max_length=8)] = ()


class TraceFeature(_T):
    name: Annotated[str, StringConstraints(max_length=16, pattern=r"^[a-z_]+$")]
    bp: SInt


class TraceCandidate(_T):
    act: Code
    claims: Annotated[tuple[Handle, ...], Field(max_length=8)] = ()
    utility_bp: SInt
    features: Annotated[tuple[TraceFeature, ...], Field(max_length=8)] = ()


class TracePlan(_T):
    act: Code
    claims: Annotated[tuple[Handle, ...], Field(max_length=8)] = ()
    secret: Handle | None = None
    layer: Int | None = None
    retracts: bool = False
    reveals: Int = 0
    tone: Short = ""


class TraceEnvelope(_T):
    sha: Sha
    sections: Int
    claims: Int
    reveals: Int
    digest_chars: Int
    query_chars: Int
    tokens: Int          # an ESTIMATE, ceil(chars / 4); the provider's own count is `llm_calls[].input_tokens`


class TraceAttempt(_T):
    n: Int
    outcome: Literal["accepted", "repair", "malformed", "refused", "rejected"]
    violations: Annotated[tuple[Code, ...], Field(max_length=16)] = ()
    text: Annotated[str, StringConstraints(max_length=MAX_TEXT)] = ""
    canary_seen: bool = False


class TraceCall(_T):
    role: Literal["parse", "generate", "verify"]
    model: Short = ""
    effort: Short = ""
    prompt_hash: Annotated[str, StringConstraints(max_length=16)]
    input_tokens: Int = 0
    output_tokens: Int = 0
    cache_read_tokens: Int = 0
    stop_reason: Short = ""
    latency_ms: Int = 0
    error: Code | Literal[""] = ""
    cost_micro_usd: Int | None = None


class TraceCommit(_T):
    events: Annotated[tuple[Code, ...], Field(max_length=64)]
    first_seq: Int
    last_seq: Int
    head_hash: Sha
    case: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{16}$")]


class TraceTimings(_T):
    run: Int = 0
    append: Int = 0
    render: Int = 0      # the sum of the model calls' own latencies


class TurnTrace(_T):
    version: Literal[1] = 1
    kind: Kind
    outcome: Outcome
    failures: Annotated[tuple[Failure, ...], Field(max_length=8)] = ()
    turn_id: Int | None = None
    game_id: Name
    character: Name | None = None
    renderer: Literal["template", "model", "none"] = "none"
    ingress: TraceIngress | None = None
    parsed: TraceParsed | None = None
    grounded: TraceGrounded | None = None
    repetition: Int = 0
    digest: Annotated[str, StringConstraints(max_length=MAX_DIGEST)] = ""
    view: TraceView | None = None
    assessment: TraceAssessment | None = None
    candidates: Annotated[tuple[TraceCandidate, ...], Field(max_length=32)] = ()
    selected: TracePlan | None = None
    envelope: TraceEnvelope | None = None
    drafts: Annotated[tuple[TraceAttempt, ...], Field(max_length=4)] = ()
    fallback_used: bool = False
    committed: TraceCommit | None = None
    llm_calls: Annotated[tuple[TraceCall, ...], Field(max_length=16)] = ()
    timings_ms: TraceTimings = TraceTimings()

    @model_validator(mode="after")
    def _coherent(self) -> "TurnTrace":
        done = self.outcome in COMMITTED
        if done != (self.turn_id is not None) or done != (self.committed is not None):
            raise ValueError("a committed trace has a turn id and a commit; an aborted one has neither")
        if self.fallback_used != (self.outcome == "committed_fallback"):
            raise ValueError("fallback_used and the outcome must agree")
        if len(self.model_dump_json()) > MAX_TRACE_BYTES:
            raise ValueError("trace over the size bound")
        return self


def to_row(t: TurnTrace) -> dict:
    """The plain dict `Save.write_trace` stores (canonicalised there)."""
    import json
    return json.loads(t.model_dump_json())


# --------------------------------------------------------------------------------- redaction
def ref(seal: str, ident: str) -> str:
    """An opaque, stable handle for an engine id: same case + id -> same handle, and nothing to read back from it."""
    return hashlib.sha256(f"{seal}|{ident}".encode()).hexdigest()[:12]


def engine_ids(state, extra=()) -> frozenset[str]:
    """Every identifier that is engine-only: what a trace may never carry verbatim. Secrets and their cover claims, slips and
    breaker tokens; ALL evidence ids; statements, their claims and account tokens; knowledge, belief and memory ids; plus
    `extra` (this turn's plan and candidate claim ids). Entity ids (people, rooms, objects) are NOT here — the player sees
    those names."""
    ids: set[str] = set(extra)
    for sec in state.secrets.all():
        ids.add(sec.id)
        ids.update(r.evidence for r in sec.evidence_responses)
        for slip in sec.slips:
            ids.add(slip.id)
        for layer in sec.cover.layers:
            ids.update(c.id for c in layer.claims)
            for bset in layer.breaker_sets:
                ids.update(bset)
    ids.update(e.id for e in state.evidence.all())
    for st in state.decision.statements.all():
        ids.add(st.id)
        ids.update(c.id for c in st.claims)
        ids.update(st.accounts)
    ids.update(state.discovery.known_accounts)
    ids.update(k.id for k in state.knowledge.all())
    for who in state.characters:
        ids.update(b.id for b in state.beliefs.for_character(who))
    for mems in state.memories.values():
        ids.update(m.id for m in mems)
    return frozenset(i for i in ids if i)


def resolver(save) -> dict[str, str]:
    """handle -> engine id, for the debug process, which holds the sealed case. (Plan claim ids that exist only inside one
    turn's envelope are not in the folded state; they stay handles.)"""
    seal = save.bundle.package.seal
    return {ref(seal, i): i for i in engine_ids(save.state)}


_TOKEN = re.compile(r"[\w@:.\-]+")
_CREDENTIAL = re.compile(r"sk-[A-Za-z0-9_\-]{16,}|Bearer\s+[A-Za-z0-9._\-]{16,}|(?i:api[_-]?key|token|secret)\s*[:=]\s*[A-Za-z0-9_.+/=\-]{8,}")
_CANARY_RE = re.compile(re.escape(CANARY), re.I)


def scrub(text: str, ids=frozenset(), limit: int = MAX_TEXT) -> str:
    """Canary, credential-shaped tokens and engine ids out; length clamped. Ordinary words are untouched."""
    text = _CREDENTIAL.sub("[secret]", _CANARY_RE.sub("[canary]", text))
    for token in {c for t in _TOKEN.findall(text) for c in (t, t.strip(".:-")) if c in ids}:
        text = re.sub(rf"(?<![\w@]){re.escape(token)}(?![\w@])", "[id]", text)
    return text[:limit]


_SAFE_SUBCODE = ("MALFORMED_OUTPUT", "VERIFIER_MALFORMED", "RENDERER_EXCEPTION", "PARSE_FAILED", "PARSE_EXCEPTION",
                 "RESULT_INTEGRITY", "STOP")


def safe_violation(v: str) -> str:
    """`UNKNOWN_ENTITY[2]:['Mr Fothergill']` -> `UNKNOWN_ENTITY[2]`. The detail of a violation is exactly the text the model
    wrote or the id it leaked; the code and the segment index say what failed."""
    m = re.match(r"([A-Z][A-Z_]*)(\[\d+\])?", v)
    if not m:
        return "UNKNOWN"
    out = m.group(0)
    if m.group(1) in _SAFE_SUBCODE and (sub := re.match(r":([A-Za-z_]{1,40})(?![\w:])", v[m.end():])):
        out += ":" + sub.group(1)
    return out[:96]


# --------------------------------------------------------------------------------- failures
def failures_of(audit, violations=(), extra=()) -> tuple[str, ...]:
    """Why a render did not go smoothly, as distinct facts, in a fixed order: transport and provider errors from the call log,
    then what each attempt turned out to be, then the render's own reason, then the fallback."""
    out: list[str] = list(extra)
    if audit is not None:
        for c in audit.calls:
            out.append({"": None, "ProviderTimeout": "provider_timeout", "ProviderRefusal": "provider_refusal",
                        "PromptLeak": "prompt_leak", "PROMPT_LEAK": "prompt_leak"}.get(c.error, "provider_error" if c.error else None) or "")
        for a in audit.attempts:
            out.append({"refused": "provider_refusal", "malformed": "malformed_output", "repair": "validation_failure",
                        "rejected": "plan_rejected"}.get(a.outcome, ""))
        reason = audit.reason
        if reason.startswith("VERIFIER_MALFORMED"):
            out.append("verifier_failure")
        elif reason.startswith("RENDERER_EXCEPTION"):
            out.append("renderer_exception")
        elif reason == "PLAN_LEVEL":
            out.append("plan_rejected")
        if audit.outcome == "fallback":
            out.append("deterministic_fallback")
    for v in violations:
        if v.startswith("RENDERER_EXCEPTION"):
            out.append("renderer_exception")
        elif v in ACTION_REJECTIONS or v.startswith("UNHELD"):
            out.append("rejected_action")           # the PLAYER asked for something the case does not allow
        elif audit is None or audit.outcome == "rejected":
            out.append("plan_rejected")             # the ENGINE's own gate refused (an unvoiced peel, a leak, an integrity failure)
    return tuple(dict.fromkeys(f for f in out if f))[:8]


# --------------------------------------------------------------------------------- the producer
@dataclass(frozen=True)
class Observed:
    """What stages 0-2 saw of a typed line, carried to the control that commits it. Absent for a structured control (no
    parser, I-26). `calls` are the parse-stage model calls, drained at the moment they happened so they cannot be charged to
    the next turn."""
    ingress: object | None = None          # llm.ingress.IngressResult
    action: object | None = None           # llm.ingress.PlayerAction
    grounded: str = "structured"
    reason: str = ""
    query_kind: str | None = None
    escalated: bool = False
    calls: tuple = ()


def envelope_sections(env) -> int:
    """How many of the envelope's slots are filled - counting only the ones the renderer is ever shown. `authorized_reveals`
    is an engine-side slot (`llm.render.build_view` has no field for it), so it is NOT a section the model, or anyone timing
    the model, can observe; it is recorded as `reveals`. I-42 / T-26 read this number."""
    persona = env.persona.public_facts or env.persona.voice.voice_register or env.persona.voice.idiom or env.persona.voice.tics
    return sum(bool(x) for x in (persona, env.delivery.tone or env.delivery.notes, env.allowed_claims, env.digest_text,
                                 env.retrieved_statements, env.recent_exchange, env.query_text))


def _call(c) -> TraceCall:
    price = PRICES_PER_MTOK.get(c.model)
    cost = None if price is None else (c.input_tokens * price[0] + c.output_tokens * price[1]
                                       + c.cache_read_tokens * price[2]) // 1_000_000
    return TraceCall(role=c.role, model=c.model[:80], effort=c.effort[:80], prompt_hash=c.prompt_hash[:16],
                     input_tokens=c.input_tokens, output_tokens=c.output_tokens, cache_read_tokens=c.cache_read_tokens,
                     stop_reason=c.stop_reason[:80], latency_ms=c.latency_ms, error=(c.error[:96] if c.error else ""),
                     cost_micro_usd=cost)


def _opt(x, n=80):
    return None if x is None else str(x)[:n]


def _ingress(o: Observed, ids) -> tuple:
    ing = o.ingress
    if ing is None:
        return None, None, TraceGrounded(outcome="structured")
    raw = "" if ing.blocked == "TOO_LONG" else scrub(ing.raw, ids, 1000)
    t_in = TraceIngress(raw=raw, raw_len=len(ing.raw), stripped=tuple(str(x)[:80] for x in ing.stripped[:32]),
                        markers=tuple(str(x)[:80] for x in ing.markers[:8]), blocked=ing.blocked, escalated=o.escalated)
    a = o.action
    t_parsed = None if a is None else TraceParsed(
        kind=a.kind, query_kind=_opt(a.query_kind), tone=_opt(a.tone), subject=_opt(scrub(a.subject or "", ids, 80) or None),
        object=_opt(scrub(a.object or "", ids, 80) or None), location=_opt(scrub(a.location or "", ids, 80) or None),
        predicate_hint=_opt(scrub(a.predicate_hint or "", ids, 80) or None), time_text=_opt(scrub(a.time_text or "", ids, 80) or None),
        target=_opt(scrub(a.target or "", ids, 80) or None), method=_opt(scrub(a.method or "", ids, 80) or None))
    return t_in, t_parsed, TraceGrounded(outcome=o.grounded, reason=o.reason[:96] if re.fullmatch(r"[A-Za-z0-9_\[\]:]*", o.reason) else "",
                                         query_kind=_opt(o.query_kind))


def build_turn_trace(save, res, *, kind: str, game_id: str, outcome: str, character: str | None = None,
                     observed: Observed | None = None, committed=None, run_ms: int = 0, append_ms: int = 0,
                     failures=()) -> TurnTrace:
    """One `TurnTrace` from a control's result. `res` is a `TurnResult` / `ExplorationTurnResult` (or `None` for a typed line
    that never reached a turn); `committed` is the store's `AppendResult` for a committed turn. Pure apart from reading
    `save` (its seal, its engine ids, its head)."""
    obs = observed or Observed()
    seal = save.bundle.package.seal
    stages = getattr(res, "stages", None)
    audits = getattr(res, "render_audit", ()) or ()
    audit = audits[0] if audits else None
    env = getattr(res, "envelope", None)
    extra = set()
    if stages is not None:
        extra |= {c for cand in stages.candidates for c in cand[1]} | set(stages.selected[1] if stages.selected else ())
        extra |= {stages.retrieved_claim} if stages.retrieved_claim else set()
    ids = engine_ids(save.state, extra)
    h = lambda i: ref(seal, i)                                                                # noqa: E731
    t_in, t_parsed, t_grounded = _ingress(obs, ids)

    view = assessment = selected = envelope = None
    candidates: tuple = ()
    repetition, digest = 0, ""
    if stages is not None:
        repetition = stages.repetition
        view = TraceView(retrieval_band=stages.retrieval_band, retrieved=h(stages.retrieved_claim) if stages.retrieved_claim else None,
                         memories=tuple(TraceMemory(ref=h(m), score_bp=min(s, 2**31)) for m, s in stages.memories),
                         standing_claims=stages.standing_claims, known_topic=stages.known_topic, layer=stages.layer_reached,
                         secret=h(stages.secret_id) if stages.secret_id else None, detective_evidence=stages.detective[0],
                         detective_statements=stages.detective[1], detective_accusations=stages.detective[2])
        assessment = TraceAssessment(
            threat_bp=stages.threat_bp, presented=stages.presented, contradicts_standing=stages.contradicts_standing,
            pressure_delta_bp=stages.pressure_delta_bp,
            peels=tuple(TracePeel(secret=h(s), frm=a, to=b, weight_bp=w, peeled=p, stonewalled=sw)
                        for s, a, b, w, p, sw in stages.peels[:8]))
        candidates = tuple(TraceCandidate(act=act, claims=tuple(h(c) for c in cl[:8]), utility_bp=u,
                                          features=tuple(TraceFeature(name=n, bp=v) for n, v in feats))
                           for act, cl, u, feats in stages.candidates[:32])
        if stages.selected:
            act, cl, sec, layer, retracts, tone = stages.selected
            selected = TracePlan(act=act, claims=tuple(h(c) for c in cl[:8]), secret=h(sec) if sec else None, layer=layer,
                                 retracts=retracts, reveals=stages.n_reveals, tone=scrub(tone, ids, 80))
    elif getattr(res, "plan_act", ""):
        selected = TracePlan(act=res.plan_act)
    if env is not None:
        dumped = env.model_dump_json()
        sections = envelope_sections(env)
        envelope = TraceEnvelope(sha=hashlib.sha256(dumped.encode()).hexdigest(), sections=sections,
                                 claims=len(env.allowed_claims), reveals=len(env.authorized_reveals),
                                 digest_chars=len(env.digest_text), query_chars=len(env.query_text),
                                 tokens=-(-len(dumped) // 4))
        digest = scrub(env.digest_text, ids, MAX_DIGEST)

    drafts: tuple = ()
    if audit is not None:
        att = []
        for a in audit.attempts[:4]:
            joined = " ".join(s.text for s in a.draft.segments) if a.draft is not None else ""
            att.append(TraceAttempt(n=a.attempt, outcome=a.outcome,
                                    violations=tuple(dict.fromkeys(safe_violation(v) for v in a.violations))[:16],
                                    text=scrub(joined, ids, MAX_TEXT), canary_seen=CANARY.lower() in joined.lower()))
        drafts = tuple(att)
    calls = tuple(_call(c) for c in (*obs.calls, *(audit.calls if audit is not None else ())))[:16]

    com = None
    if committed is not None and committed.ref is not None:
        com = TraceCommit(events=tuple(k[:96] for k in save.kinds_between(committed.ref.first_seq, committed.ref.last_seq))[:64],
                          first_seq=committed.ref.first_seq, last_seq=committed.ref.last_seq, head_hash=save.last_hash,
                          case=seal[:16])
    fb = bool(getattr(res, "fallback", False)) and outcome in COMMITTED
    outcome = "committed_fallback" if fb and outcome == "committed" else outcome
    renderer = "none" if (kind not in ("ask", "say") or res is None) else ("model" if audit is not None else "template")
    viol = tuple(getattr(res, "violations", ()) or ())
    fails = failures_of(audit, viol, tuple(failures))
    if outcome == "rejected" and not fails:
        fails = ("rejected_action",)                # a control refused with no reason code (an unknown place, an unknown item)
    return TurnTrace(
        kind=kind, outcome=outcome, failures=fails, turn_id=committed.ref.turn if com is not None else None, game_id=game_id,
        character=character, renderer=renderer, ingress=t_in, parsed=t_parsed, grounded=t_grounded, repetition=repetition,
        digest=digest, view=view, assessment=assessment, candidates=candidates, selected=selected, envelope=envelope,
        drafts=drafts, fallback_used=fb, committed=com, llm_calls=calls,
        timings_ms=TraceTimings(run=max(0, run_ms), append=max(0, append_ms), render=sum(c.latency_ms for c in calls)))
