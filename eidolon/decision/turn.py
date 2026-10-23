"""The turn runner (§12.1): wires stages 0-11 into one function per turn, using
`TemplateLLM` (§28.2) and every module this phase built. `GameState` is the full runtime
authoritative state Phase 4 owns on top of `minds`/`evidence`'s own stores.

Not built here (named so the scope is explicit, not implied): the LLM intent parser (stage 1
free-text -> `Query`, Phase 5's `AnthropicLLM` role) and grounding's name/time resolution
against a real `Alias`/`TimeAnchor` table (also Phase 5). `run_ask_turn` therefore takes an
ALREADY-GROUNDED `Query` — exactly the boundary `query.py`'s own docstring draws. Structured
actions (`Present`/`Accuse`/`GoTo`/`Search`) need no parser at all (I-26) and are handled
directly.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import Callable

from ..evidence.discovery import Discovery, DiscoveryState, apply_discovery, can_discover
from ..evidence.model import EvidenceStore
from ..minds import accounts as acct
from ..minds.belief import BeliefStore
from ..minds.character import CharacterState
from ..minds.epistemic import EpistemicState
from ..minds.events import ComposureChange, CoverStateDelta, DetectiveModelUpdate, MindsEvent, PressureChange
from ..minds.fold import apply_character
from ..minds.knowledge import KnowledgeStore
from ..minds.scale import BP_MAX
from ..evidence.contradiction import contradiction
from ..minds.memory import CueSet, Memory, _cues_for_prop, cue_overlap, retrieve, score
from ..world.case import Case
from ..world.ids import ActorId
from ..world.propositions import entities
from .claims import Claim, Statement
from .context import DecisionContext
from .digest import build_digest, evidence_labels
from .envelope import Envelope, PersonaSlot, build_envelope
from .voice import persona_voice
from .footprint import TOPIC_OF_HINT, on_topic, secret_topical
from .hypotheses import Hypothesis, evaluate_hypothesis
from .events import ClaimMade, ClaimRetracted, DecisionState, LayerPeel as LayerPeelEvent
from .events import Accusation, CaseSolved, HypothesisChanged, MetaAttemptLogged, TurnCommitted, apply_decision
from .exploration import AccountHeardEvent, ItemTaken, LocationVisited, StatementHeardEvent, apply_exploration, apply_heard
from .exploration import known_items, known_locations
from .exploration import search as exploration_search
from .llm import TemplateLLM
from .peel import (
    ConfessionCheck, claims_voiced_on_peel, evaluate_peel, layer_index, statements_to_retract,
    superseded_propositions,
)
from .pressure import PressureFeatures, update_composure, update_verbal_pressure
from .query import Query, normalize
from .secrets import Ref, Secret, SecretStore
from .speakable import speakable
from .strategy import StrategyInput, feature_terms, select_plan
from .validator import audit_envelope, validate_draft
from .weight import refutation_weight


@dataclass(frozen=True)
class GameState:
    case: Case
    knowledge: KnowledgeStore
    beliefs: BeliefStore
    memories: dict[ActorId, tuple[Memory, ...]]
    secrets: SecretStore
    evidence: EvidenceStore
    characters: dict[ActorId, CharacterState]
    epistemic: EpistemicState
    discovery: DiscoveryState
    decision: DecisionState
    seed: int = 0
    turn_counter: int = 0
    murderer: ActorId | None = None
    """The sealed proof's verified unique survivor (`solve.session.new_session` from a `SealedCase`; I-58/PI-7). Static and
    never hashed: what the verdict (`CaseSolved.correct`) is judged against, by the runner and again by the store."""

    def ctx(self) -> DecisionContext:
        return DecisionContext(case=self.case, knowledge=self.knowledge, beliefs=self.beliefs,
                                secrets=self.secrets, evidence=self.evidence, statements=self.decision.statements,
                                epistemic=self.epistemic, discovery=self.discovery)


@dataclass(frozen=True)
class TurnStages:
    """What stages 3-6 saw and scored, kept for the `TurnTrace` (§27.1). OBSERVATION ONLY: the turn writes it and never
    reads it, nothing in `events` depends on it, and replay (I-22) never sees it. Identifiers here are the engine's own
    (`llm`-free, `store`-free); `eidolon.trace` turns them into opaque handles before anything is persisted."""
    repetition: int = 0
    retrieval_band: str = "none"
    retrieved_claim: str | None = None
    memories: tuple = ()                 # ((memory id, score bp), ...) of the band the retrieval ranked
    standing_claims: int = 0
    known_topic: bool = False
    layer_reached: int = 0
    secret_id: str | None = None
    threat_bp: int = 0
    presented: bool = False
    contradicts_standing: bool = False
    peels: tuple = ()                    # ((secret id, from, to, weight bp, peeled, stonewalled), ...) for every owned secret
    candidates: tuple = ()               # ((act, (claim ids), utility bp, ((term, bp), ...)), ...)
    detective: tuple = (0, 0, 0)         # (evidence shown, statements heard, accusations) before this turn
    pressure_delta_bp: int = 0
    n_reveals: int = 0
    selected: tuple = ()                 # (act, (claim ids), secret id, layer index, retracts, delivery tone) of the chosen plan


@dataclass(frozen=True)
class TurnResult:
    """`rejected=True` is I-15's fail-closed outcome: `state` is the caller's state, untouched
    (turn counter included), `events` is empty and `text` is empty — no in-world text.
    `plan_act`, `violations`, `fallback`, `render_audit` and `stages` are ENGINE-side (trace) fields: a UI
    shows `llm.render.player_view(result)` only (I-12, §12.1 stage 11)."""
    state: GameState
    text: str
    plan_act: str
    events: tuple
    envelope: Envelope | None = None
    rejected: bool = False
    violations: tuple[str, ...] = ()
    fallback: bool = False
    render_audit: tuple = ()
    stages: TurnStages | None = None


@dataclass(frozen=True)
class RenderRequest:
    """Everything a renderer may use to turn a validated plan into text. The renderer never
    receives `GameState` and has no way to change it: it returns text + claim ids, and only
    `run_ask_turn` commits (stage 10)."""
    envelope: Envelope
    plan: object                    # ResponsePlan
    speaker: ActorId
    case: Case
    statements: object              # StatementStore
    ctx: DecisionContext
    allowed_entity_ids: frozenset[str]
    canary: str
    retracting: frozenset[str]


@dataclass(frozen=True)
class RenderOutcome:
    result: object                  # validator.ValidationResult
    audit: tuple = ()


Renderer = Callable[[RenderRequest], RenderOutcome]


def presented_tokens(presented_ref: Ref | None, statements) -> frozenset[str]:
    """What a presentation NAMES for the purpose of matching authored responses and breaker sets: the ref itself,
    plus — when it is a delivered statement — every account token that statement delivered (ADR-23/24)."""
    if presented_ref is None:
        return frozenset()
    st = statements.get(presented_ref) if statements is not None else None
    return frozenset({presented_ref}) | (frozenset(st.accounts) if st is not None else frozenset())


def relevant_secret(addressee: ActorId, secrets: SecretStore, query: Query,
                     presented_ref: Ref | None, evidence: EvidenceStore, statements=None,
                     layer_of: Callable[[Secret], int] = lambda s: 0,
                     presented_bears_on: Callable[[Secret], bool] = lambda s: False) -> Secret | None:
    """Which secret this question is ABOUT (ADR-26, I-55). A presented item (or the accounts a presented statement
    delivered) names the secret with a matching `EvidenceResponse`/breaker set. Otherwise a secret is topical iff the
    query's FOOTPRINT — who it asks about, where, when — intersects the footprint of one of its still-UNCONCEDED
    protected propositions. The old `len(owned) == 1` fallback made every whereabouts question "about" the
    speaker's secret (RB-2/C1) and is gone; wording, `predicate_hint` and `Query.presupposes` are never read."""
    owned = secrets.for_owner(addressee)
    if not owned:
        return None
    if presented_ref is not None:
        named = presented_tokens(presented_ref, statements)
        for s in owned:
            if any(r.evidence in named for r in s.evidence_responses):
                return s
            for layer in s.cover.layers:
                if any(named & bset for bset in layer.breaker_sets):
                    return s
        for s in owned:                  # an item that actually bears on a cover is "about" that cover, authored or not
            if presented_bears_on(s):
                return s
    for s in owned:
        if secret_topical(s, layer_of(s), query, addressee):
            return s
    return None


# ADR-27: topics are PROPOSITION KINDS. Memories tag themselves with the kind of the proposition they hold
# (`minds.memory._cues_for_prop`), so a question's `predicate_hint` is mapped onto that closed vocabulary here —
# the one place cues are built — instead of leaving "presence" and "at" as two words for one topic (RB-2/C6).
_TOPIC_OF_HINT = TOPIC_OF_HINT                # one map (`footprint`), shared with the LIE gate (ADR-30)


def query_cues(query: Query) -> CueSet:
    ents = []
    for ref in (query.subject, query.object):
        if ref is not None:
            ents.append(ref.id)
    bucket = None
    if query.time is not None and query.time.interval is not None:
        bucket = f"b{query.time.interval[0] // 30}"
    hint = query.predicate_hint.strip().lower() if query.predicate_hint else None
    return CueSet(entities=tuple(ents), location=query.location, time_bucket=bucket,
                  topic_tags=(_TOPIC_OF_HINT.get(hint, hint),) if hint else ())


def has_knowledge_on_topic(knowledge: KnowledgeStore, character: ActorId, query: Query) -> bool:
    targets = {r.id for r in (query.subject, query.object) if r is not None}
    if query.location:
        targets.add(query.location)
    if not targets:
        return bool(knowledge.for_character(character))
    for entry in knowledge.for_character(character):
        a, l, o, amb = entities(entry.proposition)
        if targets & (a | l | o | amb):
            return True
    return False


@dataclass(frozen=True)
class Retrieval:
    band: str
    claim: Claim | None
    memories: tuple = ()        # observation for the trace: ((memory id, score bp), ...) of the first band that ranked any


def _mem_tiebreak(memory_id: str) -> str:
    return hashlib.sha256(memory_id.encode()).hexdigest()


def retrieve_for_query(character: ActorId, memories: tuple[Memory, ...], beliefs: BeliefStore,
                        epistemic: EpistemicState, query: Query,
                        speakable_claim: Callable[[Claim], bool] = lambda c: True) -> Retrieval:
    """§8.4 retrieval as ARGMAX (ADR-27, RB-2/C8): within the strong band (else the weak one) the highest-scoring memory
    wins, ties broken by a hash of the memory id (I-6) — never list order — and within it the belief whose own cues
    overlap the query's most (ties by id), never `content[0]`. A claim the speaker may not voice (I-54) is skipped,
    so the next-best SPEAKABLE one is delivered; if none is, nothing is retrieved. A question that names a topic is
    answered only by a belief on that topic (`footprint.on_topic`, review NR-I3): "what did you hear?" is never answered with
    where the speaker was."""
    cues = query_cues(query)
    result = retrieve(list(memories), epistemic, cues)
    by_id = {m.id: m for m in memories}
    seen: tuple = ()
    for band, ids in (("strong", result.strong), ("weak", result.weak)):
        ranked = sorted((by_id[i] for i in ids if i in by_id and by_id[i].content),
                        key=lambda m: (-score(m, epistemic, cues), _mem_tiebreak(m.id)))
        if ranked and not seen:
            seen = tuple((m.id, round(score(m, epistemic, cues) * BP_MAX)) for m in ranked[:5])
        for mem in ranked:
            cands = [b for b in (beliefs.get(i) for i in mem.content) if b is not None]
            cands.sort(key=lambda b: (-cue_overlap(_cues_for_prop(b.proposition), cues), b.id))
            for belief in cands:
                if not on_topic(belief.proposition, query):     # review NR-I3: an honest answer stays on the asked topic
                    continue
                claim = Claim(id=f"ret:{belief.id}", proposition=belief.proposition,
                              sincerity="truthful" if belief.is_true else "sincere_false",
                              source="plan", grounding=belief.grounds or (mem.content[0],))
                if speakable_claim(claim):
                    return Retrieval(band=band, claim=claim, memories=seen)
    return Retrieval(band="none", claim=None, memories=seen)


def compute_threat(query: Query, presented_ref: Ref | None, secret: Secret | None) -> float:
    if presented_ref is not None:
        return 0.9
    if secret is not None:
        return 0.6
    return 0.1


def unheld_reason(state: GameState, ref: Ref) -> str | None:
    """I-51. `presented_ref` is an UNTRUSTED string (the CLI passes whatever follows `present `). It must be a
    package `EvidenceId` the player may legitimately hold, or a `StatementId` in the committed ledger. Account
    tokens (`event@actor`) are never presentable: they are minted by hearing, not typed."""
    ev = state.evidence.get(ref) if isinstance(ref, str) else None
    if ev is not None:
        if ref in state.discovery.known_evidence or can_discover(ev, state.discovery):
            return None
        return "UNHELD_PRESENTED_REF"
    if isinstance(ref, str) and state.decision.statements.get(ref) is not None:
        return None
    return "UNHELD_PRESENTED_REF"


CANARY = "EIDOLON-SESSION-CANARY"


def run_ask_turn(state: GameState, addressee: ActorId, query: Query, *,
                  presented_ref: Ref | None = None, hostile_tone: bool = False,
                  provisional_accusation: bool = False,
                  confession_check: ConfessionCheck | None = None,
                  renderer: Renderer | None = None) -> TurnResult:
    """One full turn addressed to `addressee` (§12.1 stages 3-11 collapsed into one call;
    stages 0-2 — ingress/parse/ground — are `llm.ingress`'s job). `confession_check` is the
    I-21 solver hook (Phase 6's V-5 solver wires it); absent, the confession gate stays closed.
    `renderer` is stage 8-9 (`llm.render.LLMRenderer`); absent, `TemplateLLM` renders. Whatever
    renders, everything above this line — act, claims, peels — was already decided."""
    if presented_ref is not None and (why := unheld_reason(state, presented_ref)):
        # I-51: only HELD material may be presented. A bare account token, an unknown id or an item whose
        # prerequisites the player has not met is a rejected turn with NO state change — never an exception.
        return TurnResult(state=state, text="", plan_act="", events=(), rejected=True, violations=(why,))
    ctx = state.ctx()
    char_state = state.characters[addressee]
    def layer_of(s: Secret) -> int:
        return layer_index(state.decision.layer_peels, addressee, s.id)

    topical = relevant_secret(addressee, state.secrets, query, presented_ref, state.evidence, state.decision.statements,
                              layer_of,
                              lambda s: presented_ref is not None and refutation_weight(
                                  frozenset({presented_ref}), s.cover.layers[layer_of(s)], addressee, ctx) > 0)

    detective_model = char_state.detective_model
    presented = detective_model.known_evidence | detective_model.heard_statements
    if presented_ref is not None:
        presented |= {presented_ref}

    is_meta = query.kind == "meta"
    is_coercion = query.kind == "coercion"

    # §11.4/I-3/I-33: the peel runs for EVERY secret the addressee owns, every turn, as a
    # function of the presented set alone. Which secret the question is "about" is a wording
    # heuristic (`relevant_secret`) and may pick the plan's CONTENT, never whether a cover moves.
    peels = [(s, evaluate_peel(s, presented, layer_index(state.decision.layer_peels, addressee, s.id),
                               addressee, ctx, confession_check))
             for s in state.secrets.for_owner(addressee)]
    peeled = tuple((s, p) for s, p in peels if p.peeled)
    secret = peeled[0][0] if peeled else topical
    peel_result = next((p for s, p in peels if secret is not None and s.id == secret.id), None)
    layer_reached = peel_result.from_index if peel_result is not None else 0

    retract_ids: list[str] = []
    for s, p in peeled:
        for old in statements_to_retract(state.decision.statements, addressee,
                                         superseded_propositions(s, p.from_index, p.to_index)):
            if old.id not in retract_ids:
                retract_ids.append(old.id)

    query_hash = normalize(query)
    repeat_count = sum(1 for s in state.decision.statements.for_speaker(addressee)
                        if s.query_hash == query_hash)
    # §15.4: what REPEAT_PRIOR re-supplies — the latest STANDING answer to this question (a peel's retraction removes it)
    prior = next((s for s in reversed(state.decision.statements.standing_for_speaker(addressee))
                  if s.query_hash == query_hash and s.claims), None)

    retrieval = retrieve_for_query(addressee, state.memories.get(addressee, ()), state.beliefs,
                                    state.epistemic, query,
                                    lambda c: speakable(c, addressee, state.secrets, layer_of, state.knowledge, state.case))
    standing = state.decision.statements.standing_claims(addressee)
    contradicts_standing = retrieval.claim is not None and any(
        contradiction(retrieval.claim.proposition, c.proposition, case=state.case) is not None for c in standing)
    known_topic = has_knowledge_on_topic(state.knowledge, addressee, query)
    threat = compute_threat(query, presented_ref, secret)

    inp = StrategyInput(query=query, character=addressee, state=char_state, secret=secret,
                         layer_reached=layer_reached, peel=peel_result, presented_ref=presented_ref,
                         retrieval=retrieval.band, retrieved_claim=retrieval.claim, known_topic=known_topic,
                         repeat_count=repeat_count, is_meta=is_meta, is_coercion=is_coercion, threat=threat,
                         seed=state.seed, turn_id=state.turn_counter, concessions=peeled,
                         presented_tokens=presented_tokens(presented_ref, state.decision.statements),
                         retrieved_contradicts_standing=contradicts_standing,
                         prior_claims=prior.claims if prior is not None else ())
    plan, scored = select_plan(inp)
    # §27.1: what the stages saw and scored, for the `TurnTrace`. Written here, read by nobody in this module.
    stages = TurnStages(
        repetition=repeat_count, retrieval_band=retrieval.band,
        retrieved_claim=retrieval.claim.id if retrieval.claim is not None else None, memories=retrieval.memories,
        standing_claims=len(standing), known_topic=known_topic, layer_reached=layer_reached,
        secret_id=secret.id if secret else None, threat_bp=round(threat * BP_MAX), presented=presented_ref is not None,
        contradicts_standing=contradicts_standing,
        peels=tuple((sec.id, p.from_index, p.to_index, p.weight_bp, p.peeled, p.stonewalled) for sec, p in peels),
        candidates=tuple((c.act, tuple(cl.id for cl in c.claims), round(u * BP_MAX),
                          tuple((k, round(v * BP_MAX)) for k, v in feature_terms(c, inp).items())) for c, u in scored),
        detective=(len(detective_model.known_evidence), len(detective_model.heard_statements),
                   len(detective_model.accusations)),
        n_reveals=len(plan.authorized_reveals),
        selected=(plan.act, tuple(c.id for c in plan.claims), plan.secret_id, plan.layer_index, plan.retracts,
                  plan.delivery.tone))

    # Every layer transition recorded this turn must be voiced by this turn's plan. Whatever
    # chose the plan, a turn that would move a cover without saying so commits nothing (I-15).
    if peeled:
        owed = {c.id for s, p in peeled for c in claims_voiced_on_peel(s.cover.layers[p.to_index])}
        if plan.act not in ("CONCESSION", "CONFESSION") or not owed <= {c.id for c in plan.claims}:
            return TurnResult(state=state, text="", plan_act=plan.act, events=(), rejected=True,
                              violations=("UNVOICED_LAYER_PEEL",), stages=stages)

    frame = secret.cover.layers[layer_reached].frame if secret else ()
    digest = build_digest(addressee, state.turn_counter, {}, detective_model, state.decision.statements,
                           [], current_topic=query.predicate_hint)
    persona = PersonaSlot(voice=persona_voice(char_state.personality.voice, addressee, state.seed))
    query_entities = {r.id for r in (query.subject, query.object) if r is not None}
    if query.location:
        query_entities.add(query.location)

    envelope = build_envelope(plan, persona=persona, digest=digest, frame=frame, query_text=query.raw,
                               digest_labels=evidence_labels(state.evidence, state.case, state.discovery.known_evidence))
    # §21.2: nothing reaches the renderer until every envelope field is traced to its one
    # permitted source. A leak here is the plan's fault, so the turn fails closed (I-15).
    leaks = audit_envelope(envelope, plan, frame, digest, addressee, ctx)
    if leaks:
        return TurnResult(state=state, text="", plan_act=plan.act, events=(), rejected=True,
                          violations=tuple(leaks), stages=stages)
    audit: tuple = ()
    if renderer is None:
        draft = TemplateLLM().generate(envelope, state.case, addressee)
        result = validate_draft(draft, envelope, plan, addressee, state.case, state.decision.statements,
                                 ctx=ctx, allowed_entity_ids=query_entities, canary=CANARY,
                                 retracting=frozenset(retract_ids))
    else:
        try:
            outcome = renderer(RenderRequest(envelope, plan, addressee, state.case, state.decision.statements, ctx,
                                              frozenset(query_entities), CANARY, frozenset(retract_ids)))
            result, audit = outcome.result, outcome.audit
        except Exception as exc:  # I-15: any renderer exception aborts the turn; nothing is committed
            return TurnResult(state=state, text="", plan_act=plan.act, events=(), envelope=envelope, rejected=True,
                              violations=(f"RENDERER_EXCEPTION:{type(exc).__name__}",), stages=stages)
    # F-7: the gate is the RESULT'S OWN semantics, not the single `rejected` flag. A combination
    # this pipeline cannot produce — above all `ok=False` with neither `rejected` nor `fallback`,
    # which the old gate silently committed — is a bug somewhere above, and a bug fails closed.
    if (malformed := result.integrity()) is not None:
        return TurnResult(state=state, text="", plan_act=plan.act, events=(), envelope=envelope,
                          rejected=True, violations=(f"RESULT_INTEGRITY:{malformed}",), render_audit=audit, stages=stages)
    if result.rejected:
        return TurnResult(state=state, text="", plan_act=plan.act, events=(), envelope=envelope,
                          rejected=True, violations=result.violations, render_audit=audit, stages=stages)
    if not result.committable:  # unreachable while the two checks above stand; the backstop is the point
        return TurnResult(state=state, text="", plan_act=plan.act, events=(), envelope=envelope,
                          rejected=True, violations=("RESULT_NOT_COMMITTABLE",), render_audit=audit, stages=stages)

    turn_id = state.turn_counter + 1
    statement_id = f"S{turn_id:05d}"
    # The ORDER is the plan's, never the draft's (F-1). `result.claim_ids` says WHICH of the plan's
    # claims were voiced — a set — and the renderer may merge, split or reorder segments freely; if
    # the sequence were read off the segments, two wordings of the same plan would record different
    # `Statement.claims` and a model would be deciding what the ledger looks like (I-2, I-22).
    voiced = set(result.claim_ids)
    committed_claims = tuple(
        c.model_copy(update={"statement": statement_id})
        for c in plan.claims if c.id in voiced
    )
    # I-50: tokens are minted HERE and nowhere else — by the claims this committed turn actually delivered.
    minted = tuple(sorted(frozenset().union(*[acct.tokens_satisfied(state.case, state.knowledge, c, addressee)
                                              for c in committed_claims]))) if committed_claims else ()
    statement = Statement(id=statement_id, turn=turn_id, speaker=addressee, text=result.text,
                           claims=committed_claims, act=plan.act, query_hash=query_hash, accounts=minted,
                           layer_scope=(secret.id, layer_reached) if (secret and frame) else None)

    events: list = [ClaimMade(statement=statement)]
    for s, p in peeled:
        events.append(LayerPeelEvent(character=addressee, secret_id=s.id,
                                      from_index=p.from_index, to_index=p.to_index))
    events += [ClaimRetracted(statement_id=sid, retracted_by=statement_id) for sid in retract_ids]

    if is_meta or is_coercion:
        events.append(MetaAttemptLogged(turn=turn_id, character=addressee,
                                          query_kind="coercion" if is_coercion else "meta"))
    if provisional_accusation:
        # §16.3/§11.3: said TO the addressee, so it is theirs to record (no telepathy). It feeds pressure and the digest only;
        # nothing above read it, so it can never move a cover (I-16).
        events.append(Accusation(turn=turn_id, target=addressee, provisional=True))

    # --- pressure / composure (delivery-only, I-16/I-29: never read above this line) -----
    secret_id_for_pressure = secret.id if secret else "none"
    old_pressure = char_state.verbal_pressure.get(secret_id_for_pressure, 0)
    features = PressureFeatures(provisional_accusation=provisional_accusation, hostile_tone=hostile_tone,
                                 repeated_probe_of_protected_topic=bool(secret) and threat > 0.3,
                                 topic_probe_count_before=char_state.topics_probed.get(query.predicate_hint or "", 0),
                                 threat=threat)
    new_pressure = update_verbal_pressure(old_pressure, features)
    weight_now = refutation_weight(presented, secret.cover.layers[layer_reached], addressee, ctx) if secret else 0
    new_composure = update_composure(char_state.composure, delta_verbal_bp=new_pressure - old_pressure,
                                      delta_weight_bp=weight_now, personality=char_state.personality,
                                      calm_turn=threat < 0.3 and not provisional_accusation and not hostile_tone)
    minds_events: list[MindsEvent] = []
    if secret is not None:
        minds_events.append(PressureChange(secret_id=secret.id, new_value_bp=new_pressure))
    minds_events.append(ComposureChange(new_composure_bp=new_composure))
    new_known_evidence = detective_model.known_evidence | ({presented_ref} if presented_ref and state.evidence.get(presented_ref) else set())
    new_heard = detective_model.heard_statements | ({presented_ref} if presented_ref and state.decision.statements.get(presented_ref) else set())
    new_accusations = detective_model.accusations + (((turn_id, True, addressee),) if provisional_accusation else ())
    if (new_known_evidence, new_heard, new_accusations) != (detective_model.known_evidence, detective_model.heard_statements,
                                                            detective_model.accusations):
        minds_events.append(DetectiveModelUpdate(new_model=detective_model.model_copy(
            update={"known_evidence": frozenset(new_known_evidence), "heard_statements": frozenset(new_heard),
                    "accusations": new_accusations})))
    new_topics = dict(char_state.topics_probed)
    if query.predicate_hint:
        new_topics[query.predicate_hint] = new_topics.get(query.predicate_hint, 0) + 1
    # §15.4 / F-15: REFUSE runs at most 2 turns in a row; any other act ends the run. Written only when it changes.
    streak = char_state.refuse_streak + 1 if plan.act == "REFUSE" else 0
    if query.predicate_hint or streak != char_state.refuse_streak:
        minds_events.append(CoverStateDelta(topics_probed=new_topics if query.predicate_hint else None,
                                            refuse_streak=streak if streak != char_state.refuse_streak else None))

    new_char_states = dict(state.characters)
    cs = char_state
    for ev in minds_events:
        cs = apply_character(cs, ev)
    new_char_states[addressee] = cs

    new_decision = state.decision
    for ev in events:
        new_decision = apply_decision(new_decision, ev)

    new_discovery = state.discovery
    discovered: list = []
    if presented_ref is not None and state.evidence.get(presented_ref) is not None and presented_ref not in state.discovery.known_evidence:
        found = Discovery(evidence_id=presented_ref, turn=turn_id,
                          action=state.evidence.get(presented_ref).discovery.action,
                          at=state.evidence.get(presented_ref).discovery.at)
        new_discovery = apply_discovery(new_discovery, found, state.evidence)
        discovered.append(found)

    # ADR-24: a committed statement is HEARD, and so is every account it delivered; the validating fold
    # refuses a row the ledger does not back, so a hearing can only come from a commit.
    heard = [StatementHeardEvent(statement_id=statement_id, turn=turn_id)]
    heard += [AccountHeardEvent(token=t, statement_id=statement_id, turn=turn_id) for t in minted]
    for row in heard:
        new_discovery = apply_heard(new_discovery, row, new_decision.statements)

    new_state = replace(state, characters=new_char_states, decision=new_decision, discovery=new_discovery,
                         turn_counter=turn_id)
    # §26: the returned rows ARE the turn's whole log (Phase 7 persists exactly these and replays them, I-22).
    # `TurnCommitted` brackets the group and names the character the bare minds rows belong to; `Discovery` precedes the
    # hearing rows because it was folded before them above (a `StatementHeard` prerequisite may depend on that order).
    rows = [TurnCommitted(turn=turn_id, character=addressee)] + events + discovered + heard + minds_events
    return TurnResult(state=new_state, text=result.text, plan_act=plan.act,
                       events=tuple(rows), envelope=envelope,
                       fallback=result.fallback, render_audit=audit,
                       stages=replace(stages, pressure_delta_bp=new_pressure - old_pressure))


@dataclass(frozen=True)
class ExplorationTurnResult:
    state: GameState
    text: str
    discovered: str | None  # EvidenceId, if any
    events: tuple = ()      # the turn's whole log (§26), same contract as `TurnResult.events`
    rejected: bool = False  # I-15: an unknown place/item commits nothing — `state` is the caller's, `events` is empty
    violations: tuple[str, ...] = ()   # engine-side reason codes for a rejection (trace only, never shown, I-12)


def run_goto_turn(state: GameState, location: str) -> ExplorationTurnResult:
    """§17: "`GoTo(location)` is free but recorded"."""
    if location not in known_locations(state.case, state.evidence):
        return ExplorationTurnResult(state=state, text="", discovered=None, rejected=True)
    turn_id = state.turn_counter + 1
    row = LocationVisited(location=location, turn=turn_id)
    new_state = replace(state, discovery=apply_exploration(state.discovery, row), turn_counter=turn_id)
    return ExplorationTurnResult(state=new_state, text=f"You go to {location}.", discovered=None,
                                 events=(TurnCommitted(turn=turn_id), row))


def run_search_turn(state: GameState, target: str, action: str) -> ExplorationTurnResult:
    """§17: `Search(target, method)` — a discovery, or a deterministic in-world hint."""
    turn_id = state.turn_counter + 1
    result = exploration_search(state.evidence, state.discovery, target, action, turn_id, state.case)
    if result.discovery is None:
        return ExplorationTurnResult(state=replace(state, turn_counter=turn_id), text=result.hint, discovered=None,
                                     events=(TurnCommitted(turn=turn_id),))
    new_discovery = apply_discovery(state.discovery, result.discovery, state.evidence)
    ev = state.evidence.get(result.discovery.evidence_id)
    new_state = replace(state, discovery=new_discovery, turn_counter=turn_id)
    return ExplorationTurnResult(state=new_state, text=ev.discovery.reveals_text, discovered=ev.id,
                                 events=(TurnCommitted(turn=turn_id), result.discovery))


def run_take_turn(state: GameState, item: str) -> ExplorationTurnResult:
    """§5.1's `Kit` item, or any other takeable object named by a discovered scene."""
    if item not in known_items(state.case, state.evidence):
        return ExplorationTurnResult(state=state, text="", discovered=None, rejected=True)
    turn_id = state.turn_counter + 1
    row = ItemTaken(item=item, turn=turn_id)
    new_state = replace(state, discovery=apply_exploration(state.discovery, row), turn_counter=turn_id)
    return ExplorationTurnResult(state=new_state, text=f"You take the {item}.", discovered=None,
                                 events=(TurnCommitted(turn=turn_id), row))


def _refused(state: GameState, why: str) -> ExplorationTurnResult:
    return ExplorationTurnResult(state=state, text="", discovered=None, rejected=True, violations=(why,))


def run_hypothesis_turn(state: GameState, propositions=(), confidence_bp: int = 5000, *, revise: str | None = None,
                        withdraw: str | None = None) -> ExplorationTurnResult:
    """§16.1: one board edit is one turn of its own — create (`revise=None`), revise (`revise=id`: new propositions and
    confidence, same creation turn) or withdraw (`withdraw=id`; terminal). The entry is evaluated against HELD material
    only, at commit (bookkeeping, never truth); `player_confidence` is the player's, carried on the basis-point grid. What
    the propositions may reference is the store's to refuse (one contract, I-15) — this shapes the turn."""
    turn = state.turn_counter + 1
    target = withdraw or revise
    old = next((h for h in state.decision.hypotheses if h.id == target), None) if target else None
    if state.decision.solved is not None:
        return _refused(state, "CASE_CLOSED")
    if target and (old is None or old.status == "withdrawn"):
        return _refused(state, "UNKNOWN_HYPOTHESIS")
    if withdraw:
        h = old.model_copy(update={"status": "withdrawn", "updated_turn": turn})
    else:
        if not propositions or not 0 <= confidence_bp <= BP_MAX:
            return _refused(state, "BAD_HYPOTHESIS")
        try:
            draft = Hypothesis(id=old.id if old else f"H{turn:05d}", propositions=tuple(propositions),
                               player_confidence=confidence_bp / BP_MAX, created_turn=old.created_turn if old else turn)
        except ValueError:
            return _refused(state, "BAD_HYPOTHESIS")
        h = evaluate_hypothesis(draft, state.evidence, state.decision.statements, state.discovery, turn)
    row = HypothesisChanged(hypothesis=h)
    return ExplorationTurnResult(state=replace(state, decision=apply_decision(state.decision, row), turn_counter=turn),
                                 text="", discovered=None, events=(TurnCommitted(turn=turn), row))


def run_accusation_turn(state: GameState, target: str, *, weapon: str | None = None, location: str | None = None,
                        interval: tuple[int, int] | None = None, motive_kind: str | None = None,
                        cited=()) -> ExplorationTurnResult:
    """§16.3 `Accuse(character, solution_form, final=True)`: a turn of its own, and the last one. `correct` is the WHO
    axis against the proof's verified survivor; without one there is nothing to judge against, so the turn is refused
    (I-15). Only HELD material may be cited — the support of an accusation is evidence the player legitimately acquired.
    The store re-checks every reference and the verdict; the five-axis score is the case report's (a projection)."""
    if state.decision.solved is not None or state.murderer is None:
        return _refused(state, "CASE_CLOSED")
    if target not in state.characters and target != "Outsider":
        return _refused(state, "OUTSIDE_CANDIDATE_DOMAIN")
    cited = tuple(sorted(set(cited)))
    if not set(cited) <= state.discovery.known_evidence | state.discovery.known_statements:
        return _refused(state, "UNHELD_CITATION")
    turn = state.turn_counter + 1
    try:
        acc = Accusation(turn=turn, target=target, provisional=False, weapon=weapon, location=location,
                         interval=interval, motive_kind=motive_kind, cited=cited)
    except ValueError:                                  # an empty or reversed window
        return _refused(state, "BAD_ACCUSATION")
    verdict = CaseSolved(turn=turn, correct=target == state.murderer)
    decision = apply_decision(apply_decision(state.decision, acc), verdict)
    return ExplorationTurnResult(state=replace(state, decision=decision, turn_counter=turn), text="", discovered=None,
                                 events=(TurnCommitted(turn=turn), acc, verdict))
