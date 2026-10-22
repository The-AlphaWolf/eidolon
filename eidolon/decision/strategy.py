"""Candidate enumeration and scoring (§11.5) and `ResponsePlan` (§25/§12.1 stage 6).

`select_plan` is a pure function of `StrategyInput` — everything it needs (retrieval band,
threat, the query, the relevant secret/layer, this turn's peel result) is assembled by
`turn.py` from the `minds`/`evidence` layers before this module is called, so `strategy.py`
itself never touches a `KnowledgeStore`/`Memory` directly. This keeps the scorer testable in
isolation and keeps the layering rule (`decision` reads `minds`/`evidence`, never the other
way) honest even inside one phase.

Each act's precondition is one small function per §10.3's table, run in a fixed order and
scored; `argmax` breaks ties with `hash(seed, turn_id, candidate.act)` (I-6). Some utility
terms are necessarily simplified relative to §11.5's full list (`plausibility`/`persona_fit`
in particular use one concrete, documented signal each rather than a further sub-model) —
the shape of the scorer (seven weighted terms, a repetition penalty, deterministic argmax) is
exact; the richness of any one term is a content-tuning knob, not an invariant.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ..minds.character import CharacterState
from ..world.ids import ActorId
from ..world.propositions import Proposition
from .claims import Claim
from .footprint import claim_covers, on_topic
from .ids import SecretId
from .peel import PeelResult, claims_voiced_on_peel, confession_gated
from .query import Query
from .secrets import Ref, Secret
from .speech_acts import SpeechAct

RetrievalBand = Literal["strong", "weak", "none"]


@dataclass(frozen=True)
class DeliveryDirective:
    """§14.1 stage 7's "delivery directives" — public register/tone, given to the LLM verbatim
    (§21: it "sees *content* ... and *delivery*"). Never carries a proposition.

    It DOES carry the act (F-4). Each builder below attaches a constant string and the map is
    injective, so a renderer reading `delivery_tone` knows whether it is voicing a LIE or a TRUTH.
    The architecture treats this as intended — §33's F-1 row calls delivery directives "themselves
    designed tells" and ADR-8 accepts that "guilty behaviour must be authored as directives/slips
    (a feature: controllable)" — and I-42's observable-parity list covers latency, effort, envelope
    SECTION COUNT and length band, not the content of this string.

    ponytail: what is still owed is §33's mitigation, that the directives be AUTHORED per character
    ("honest characters get delivery directives too"). These are shared constants, which is what
    makes the map trivially invertible; authoring them is Phase 6 content work, not a code change
    here. Pinned by `test_the_act_is_recoverable_from_delivery_tone_and_that_is_the_intended_residual`."""
    tone: str = ""
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class StrategyInput:
    query: Query
    character: ActorId
    state: CharacterState
    secret: Secret | None              # the secret this query/topic is relevant to, if any
    layer_reached: int                 # derived current layer index for `secret`
    peel: PeelResult | None            # this turn's peel.evaluate_peel() result for `secret`
    presented_ref: Ref | None
    retrieval: RetrievalBand
    retrieved_claim: Claim | None      # the belief/memory content at that retrieval band
    known_topic: bool                  # does the character have ANY knowledge entry on topic?
    repeat_count: int = 0
    is_meta: bool = False
    is_coercion: bool = False
    threat: float = 0.0
    seed: int = 0
    turn_id: int = 0
    detective_knows_claim: bool = False  # DetectiveModel already holds this exact fact (plausibility)
    concessions: tuple = ()              # (Secret, PeelResult) for EVERY secret that peeled this turn
    presented_tokens: frozenset = frozenset()   # the presented ref plus the account tokens a presented statement delivered
    retrieved_contradicts_standing: bool = False   # the retrieved claim contradicts the speaker's own standing ledger claims
    prior_claims: tuple[Claim, ...] = ()  # §15.4: the speaker's STANDING (non-retracted) answer to this same question


@dataclass(frozen=True)
class Candidate:
    act: SpeechAct
    claims: tuple[Claim, ...] = ()
    exposes_protected: bool = False
    contradicts_own_standing: bool = False
    authorized_reveals: tuple[Proposition, ...] = ()
    retracts: bool = False  # True for CONCESSION/CORRECTION: exempt from the consistency cost
    delivery: DeliveryDirective = field(default_factory=DeliveryDirective)
    target: ActorId | None = None


class ResponsePlan:
    """§25/§12.1 stage 6's output. A plain object (not pydantic) because `Claim`s inside it
    may carry `statement=None` (not yet committed) — `turn.py` binds them to a real
    `StatementId` only once validated (§14) and ready to commit (stage 10)."""

    __slots__ = ("act", "claims", "authorized_reveals", "delivery", "secret_id", "layer_index",
                 "retracts", "target")

    def __init__(self, act: SpeechAct, claims: tuple[Claim, ...] = (),
                 authorized_reveals: tuple[Proposition, ...] = (),
                 delivery: DeliveryDirective = DeliveryDirective(),
                 secret_id: SecretId | None = None, layer_index: int | None = None,
                 retracts: bool = False, target: ActorId | None = None):
        self.act = act
        self.claims = claims
        self.authorized_reveals = authorized_reveals
        self.delivery = delivery
        self.secret_id = secret_id
        self.layer_index = layer_index
        self.retracts = retracts
        self.target = target

    def __repr__(self) -> str:
        return f"ResponsePlan(act={self.act!r}, claims={[c.id for c in self.claims]!r})"


# --- per-act candidate builders (§10.3) ----------------------------------------------
def _concession(inp: StrategyInput) -> Candidate | None:
    """Voices every layer the evidence moved this turn — all of them, since each recorded
    `LayerPeel` must be spoken (§11.4: "plan.act = CONCESSION; plan.claims = layers[i].claims")."""
    pairs = inp.concessions or (
        ((inp.secret, inp.peel),) if inp.secret is not None and inp.peel is not None and inp.peel.peeled else ())
    if not pairs:
        return None
    claims = tuple(dict.fromkeys(c for s, p in pairs for c in claims_voiced_on_peel(s.cover.layers[p.to_index])))
    return Candidate(act="CONCESSION", claims=claims, retracts=True,
                      delivery=DeliveryDirective("caught, minimizing"))


def _stonewall(inp: StrategyInput) -> Candidate | None:
    if inp.peel is not None and inp.peel.stonewalled:
        return Candidate(act="STONEWALL", delivery=DeliveryDirective("resolute; gives no ground"))
    return None


def _confession(inp: StrategyInput) -> Candidate | None:
    if inp.secret is None:
        return None
    layer = inp.secret.cover.layers[inp.layer_reached]
    if layer.terminal == "confession" and not confession_gated(inp.secret, layer):
        return None            # I-56: an ungated terminal is a concession, voiced by the peel — never a CONFESSION act
    if layer.terminal == "confession" and inp.peel is not None and not inp.peel.stonewalled:
        return Candidate(act="CONFESSION", claims=layer.claims,
                          authorized_reveals=tuple(c.proposition for c in layer.claims),
                          delivery=DeliveryDirective("resigned"))
    return None


def _lie(inp: StrategyInput) -> Candidate | None:
    if inp.secret is None:
        return None
    layer = inp.secret.cover.layers[inp.layer_reached]
    # §10.3: LIE needs "a claim covering the asked proposition" (ADR-26/I-55) — a DECEPTIVE claim whose footprint
    # meets the query's. A question about 21:40 gets no "I was in the Library 22:00-22:20".
    # ADR-30: and on the question's own TOPIC - "what did you hear?" is never answered with a denial of a deed.
    if not any(c.sincerity == "deceptive" and claim_covers(c.proposition, inp.query, inp.character)
               and on_topic(c.proposition, inp.query) for c in layer.claims):
        return None
    return Candidate(act="LIE", claims=layer.claims, exposes_protected=False,
                      delivery=DeliveryDirective("composed"))


def _deny_evidence_or_reinterpret(inp: StrategyInput) -> Candidate | None:
    if inp.secret is None or inp.presented_ref is None:
        return None
    resp = next((r for r in inp.secret.evidence_responses
                 if r.evidence in (inp.presented_tokens or {inp.presented_ref}) and r.layer == inp.layer_reached), None)
    if resp is None:
        return None
    return Candidate(act=resp.act, claims=resp.claims, delivery=DeliveryDirective("explains it away"))


def _deflect(inp: StrategyInput) -> Candidate | None:
    if inp.secret is None:
        return None
    for d in inp.secret.deflections:
        return Candidate(act="DEFLECT", claims=d.claims, target=d.target,
                          delivery=DeliveryDirective("redirects"))
    return None


def _slip(inp: StrategyInput) -> Candidate | None:
    if inp.secret is None:
        return None
    layer = inp.secret.cover.layers[inp.layer_reached]
    for slip in inp.secret.slips:
        if slip.id in inp.state.slips_used:
            continue
        topic_matches = inp.query.predicate_hint == slip.trigger_topic or (
            inp.query.subject is not None and inp.query.subject.id == slip.trigger_topic)
        if not topic_matches:
            continue
        if inp.peel is None:
            continue
        min_weight = round(slip.min_weight_fraction * layer.resolve / 10000)
        if inp.peel.weight_bp >= min_weight:
            claim = Claim(id=f"slip:{slip.id}", proposition=slip.reveals, sincerity="truthful", source="slip")
            return Candidate(act="SLIP", claims=(claim,), authorized_reveals=(slip.reveals,),
                              delivery=DeliveryDirective("rattled; over-explains"))
    return None


def _truth(inp: StrategyInput) -> Candidate | None:
    if inp.retrieval != "strong" or inp.retrieved_claim is None:
        return None
    if inp.secret is not None and inp.secret.is_protected(inp.retrieved_claim.proposition):
        return None
    return Candidate(act="TRUTH", claims=(inp.retrieved_claim,), delivery=DeliveryDirective("relaxed"),
                      contradicts_own_standing=inp.retrieved_contradicts_standing)


def _vague(inp: StrategyInput) -> Candidate | None:
    if inp.retrieval != "weak" or inp.retrieved_claim is None:
        return None
    hedged = inp.retrieved_claim.model_copy(update={"confidence": "unsure"})
    return Candidate(act="VAGUE", claims=(hedged,), delivery=DeliveryDirective("eager but unsure"))


def _dont_recall(inp: StrategyInput) -> Candidate | None:
    if inp.retrieval == "none" and inp.known_topic:
        return Candidate(act="DONT_RECALL", delivery=DeliveryDirective("apologetic"))
    return None


def _dont_know(inp: StrategyInput) -> Candidate | None:
    if not inp.known_topic:
        return Candidate(act="DONT_KNOW", delivery=DeliveryDirective("puzzled"))
    return None


def _repeat_prior(inp: StrategyInput) -> Candidate | None:
    """§15.4: the STANDING answer, re-supplied verbatim — whatever act produced it. Built from the ledger, never from this
    turn's retrieval: a liar's retrieval is empty, and keying on it made "as I said" a thing only honest answers did (H9-B1)."""
    if inp.repeat_count >= 2 and inp.prior_claims:
        return Candidate(act="REPEAT_PRIOR", claims=inp.prior_claims, delivery=DeliveryDirective("weary"))
    return None


def _refuse(inp: StrategyInput) -> Candidate | None:
    if inp.repeat_count >= 5 and inp.state.refuse_streak < 2:
        return Candidate(act="REFUSE", delivery=DeliveryDirective("clipped"))
    return None


def _evasion(inp: StrategyInput) -> Candidate | None:
    if inp.threat > 0.4:
        return Candidate(act="EVASION", delivery=DeliveryDirective("changes the subject"))
    return None


def _counter_question(inp: StrategyInput) -> Candidate | None:
    return Candidate(act="COUNTER_QUESTION", delivery=DeliveryDirective("turns it back"))


def _clarify(inp: StrategyInput) -> Candidate | None:
    if inp.is_meta or inp.is_coercion:
        return Candidate(act="CLARIFY", delivery=DeliveryDirective("baffled"))
    return None


def _anger(inp: StrategyInput) -> Candidate | None:
    if inp.is_meta or inp.is_coercion:
        return Candidate(act="ANGER", delivery=DeliveryDirective("indignant"))
    return None


def _opinion(inp: StrategyInput) -> Candidate | None:
    if inp.query.kind == "opinion":
        return Candidate(act="OPINION", delivery=DeliveryDirective("thoughtful"))
    return None


def _hypothetical(inp: StrategyInput) -> Candidate | None:
    if inp.query.kind == "hypothetical":
        return Candidate(act="HYPOTHETICAL", delivery=DeliveryDirective("imagines"))
    return None


def _correct_detective(inp: StrategyInput) -> Candidate | None:
    if inp.query.presupposes and inp.retrieved_claim is not None:
        return Candidate(act="CORRECT_DETECTIVE", claims=(inp.retrieved_claim,),
                          delivery=DeliveryDirective("politely corrects"))
    return None


CANDIDATE_BUILDERS = (
    _confession, _stonewall, _concession, _slip, _deny_evidence_or_reinterpret,
    _clarify, _anger, _correct_detective, _opinion, _hypothetical, _refuse, _repeat_prior,
    _lie, _deflect, _truth, _vague, _dont_recall, _dont_know, _evasion, _counter_question,
)


# --- scoring (§11.5) -----------------------------------------------------------------
W_SAFETY, W_CONSIST, W_PLAUS, W_PERSONA, W_EMOTION, W_GOAL, W_REPEAT = 1.0, 0.6, 0.4, 0.3, 0.3, 0.4, 0.5


def _exposure(c: Candidate) -> float:
    return 1.0 if c.exposes_protected else 0.0


def _contradiction_cost(c: Candidate, inp: StrategyInput) -> float:
    if c.retracts:
        return 0.0
    return 1.0 if c.contradicts_own_standing else 0.0


def _plausibility(c: Candidate, inp: StrategyInput) -> float:
    """One concrete signal (§11.5 names the term, not a formula): does the DETECTIVE already
    appear to know something this act would contradict? A `LIE`/`DENY_EVIDENCE` the detective
    can already see through is less plausible to keep using."""
    if c.act in ("LIE", "DENY_EVIDENCE") and inp.detective_knows_claim:
        return 0.2
    return 1.0


def _persona_fit(c: Candidate, inp: StrategyInput) -> float:
    guile = inp.state.personality.guile
    talk = inp.state.personality.talkativeness
    if c.act == "MISLEADING_TRUE":
        return guile
    if c.act in ("EVASION", "DONT_RECALL", "REFUSE"):
        return 1.0 - talk
    return 0.5


def _emotion_fit(c: Candidate, inp: StrategyInput) -> float:
    from ..minds.scale import frac
    anxiety, hostility = frac(inp.state.emotion.anxiety), frac(inp.state.emotion.hostility)
    if c.act in ("ANGER", "COUNTER_QUESTION"):
        return hostility
    if c.act == "EVASION":
        return anxiety
    return 0.3


def _goal_fit(c: Candidate, inp: StrategyInput) -> float:
    if c.act == "DEFLECT":
        return inp.state.personality.self_preservation
    if c.act in ("LIE", "CONCESSION", "STONEWALL", "DENY_EVIDENCE"):
        return 0.5
    return 0.4


REPEAT_PRIOR_PREFERENCE = 1.4
REFUSE_PREFERENCE = 2.0


def _repetition_penalty(c: Candidate, inp: StrategyInput) -> float:
    """§15.4 / §28.4 #2: `REPEAT_PRIOR` "becomes a high-utility candidate" from the third identical question and `REFUSE`
    from the sixth — for EVERY content act, or the escalation tells a lie from a truth (§22.3, H9-B1). A negative penalty is
    a preference; the margins are structural: any other act scores at most 3.00 (every term at its maximum), `REPEAT_PRIOR`
    scores 2.40 + 0.70 and `REFUSE` at least 2.25 + 1.00. Off only while an AUTHORED response to the shown item is in play
    (`DENY_EVIDENCE`/`REINTERPRET`): that must not be swallowed by "as I said". Keying on "anything shown" let an inert item
    switch the escalation off and repetition tell a lie from a truth again (re-review RR-B1). Peels are forced, never gated."""
    if inp.presented_ref is None or _deny_evidence_or_reinterpret(inp) is None:
        if c.act == "REFUSE" and inp.repeat_count >= 5:
            return -REFUSE_PREFERENCE
        if c.act == "REPEAT_PRIOR" and inp.repeat_count >= 2:
            return -REPEAT_PRIOR_PREFERENCE
    if c.act == "EVASION" and inp.repeat_count >= 3:
        return 0.6
    return 0.0


def utility(c: Candidate, inp: StrategyInput) -> float:
    return (W_SAFETY * (1 - _exposure(c))
            + W_CONSIST * (1 - _contradiction_cost(c, inp))
            + W_PLAUS * _plausibility(c, inp)
            + W_PERSONA * _persona_fit(c, inp)
            + W_EMOTION * _emotion_fit(c, inp)
            + W_GOAL * _goal_fit(c, inp)
            - W_REPEAT * _repetition_penalty(c, inp))


def feature_terms(c: Candidate, inp: StrategyInput) -> dict[str, float]:
    """`utility`'s seven weighted terms, by name (§27.1 `feature_breakdown`). Observation only: nothing selects with it, so
    a reading of the trace can never disagree with `utility` about which candidate won — `utility` stays the one scorer."""
    return {"safety": W_SAFETY * (1 - _exposure(c)), "consist": W_CONSIST * (1 - _contradiction_cost(c, inp)),
            "plaus": W_PLAUS * _plausibility(c, inp), "persona": W_PERSONA * _persona_fit(c, inp),
            "emotion": W_EMOTION * _emotion_fit(c, inp), "goal": W_GOAL * _goal_fit(c, inp),
            "repeat": -W_REPEAT * _repetition_penalty(c, inp)}


def _tie_break(seed: int, turn_id: int, act: SpeechAct) -> int:
    import hashlib
    return int(hashlib.sha256(f"{seed}:{turn_id}:{act}".encode()).hexdigest(), 16)


_META_ACTS = frozenset({"CLARIFY", "ANGER", "COUNTER_QUESTION"})


def enumerate_candidates(inp: StrategyInput) -> list[Candidate]:
    """§22.2: "meta -> in-world CLARIFY/COUNTER_QUESTION/ANGER per personality; coercion ->
    same" — turn 7's own worked example lists exactly `{COUNTER_QUESTION, CLARIFY}` as the
    candidates, not the character's ordinary content acts alongside them. A `meta`/`coercion`
    query is therefore restricted to that set outright, never merely down-weighted: the
    generator "does not know [the fact the query fishes for]" regardless of which of these
    three fires, and content acts (`LIE`/`TRUTH`/...) answering a meta probe would leak
    exactly the register-consistency tell §22.3 warns about.

    The restriction narrows what a character says ABOUT the question; it never hides a layer
    transition the presented evidence already caused. `CONFESSION`/`CONCESSION` voice recorded
    state, so they stay candidates whatever the query kind (a meta-flagged turn must not move
    the cover silently)."""
    if inp.is_meta or inp.is_coercion:
        voiced = [c for c in (_confession(inp), _concession(inp)) if c is not None]
        return voiced + [c for c in (_clarify(inp), _anger(inp), _counter_question(inp)) if c is not None]
    out = []
    for builder in CANDIDATE_BUILDERS:
        c = builder(inp)
        if c is not None:
            out.append(c)
    if not out:
        out.append(Candidate(act="DONT_KNOW", delivery=DeliveryDirective("shrugs")))
    return out


def select_plan(inp: StrategyInput) -> tuple[ResponsePlan, list[tuple[Candidate, float]]]:
    """Deterministic argmax with hash tie-break (I-6). Priority acts (`CONFESSION`/
    `STONEWALL`/`CONCESSION`/`SLIP`) are still scored through the SAME utility function —
    they simply tend to dominate because their preconditions are rare and decisive — so no
    special-cased "if peeled, always concession" branch is needed; §11.4 already only offers
    them as candidates when their precondition genuinely fires."""
    candidates = enumerate_candidates(inp)
    scored = [(c, utility(c, inp)) for c in candidates]
    # A peel/confession/stonewall/slip precondition firing is not merely "one option among
    # many" (§11.4: "if i > peeled_from: ... plan.act = CONCESSION" is an unconditional
    # assignment, not a candidate to be outvoted by e.g. a higher-utility EVASION) — these
    # four preconditions are gated on structural facts (I-3/I-16) that must always win once
    # true, so they are selected directly rather than through utility comparison.
    # CONCESSION outranks STONEWALL: a peel that stops short of an ungated confession is still
    # a peel ("i -= 1 ... if i > peeled_from: plan.act = CONCESSION", §11.4) and must be voiced;
    # STONEWALL records nothing, so it only speaks when nothing moved.
    for forced_act in ("CONFESSION", "CONCESSION", "STONEWALL", "SLIP"):
        forced = next((c for c in candidates if c.act == forced_act), None)
        if forced is not None:
            plan = ResponsePlan(act=forced.act, claims=forced.claims,
                                 authorized_reveals=forced.authorized_reveals, delivery=forced.delivery,
                                 secret_id=inp.secret.id if inp.secret else None,
                                 layer_index=inp.peel.to_index if inp.peel else inp.layer_reached,
                                 retracts=forced.retracts, target=forced.target)
            return plan, scored

    best = max(scored, key=lambda pair: (pair[1], _tie_break(inp.seed, inp.turn_id, pair[0].act)))
    c = best[0]
    plan = ResponsePlan(act=c.act, claims=c.claims, authorized_reveals=c.authorized_reveals,
                         delivery=c.delivery, secret_id=inp.secret.id if inp.secret else None,
                         layer_index=inp.layer_reached, retracts=c.retracts, target=c.target)
    return plan, scored
