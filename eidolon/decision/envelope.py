"""The envelope builder (§12.1 stage 7, §15.1) — the I-1 checkpoint. A PURE function of
`(plan, frame, persona, digest, recent exchange)`: every proposition the LLM could possibly
see is carried in a typed field of `Envelope`, so I-1 ("no LLM call context contains any
proposition outside the speaking character's speakable set") is provable by construction —
`props(envelope) <= speakable(plan, frame)` for ANY plan, not sampled from rendered prompt
text (§2.2's own wording for I-1).

`speakable(plan, frame)` is the plan's own claims/authorized reveals PLUS the layer's
pre-authored `frame` padding (§15.1's parity floor, I-18) — never arbitrary Background
knowledge the caller did not explicitly pass in, so there is exactly one place (`turn.py`)
that decides what padding a turn is allowed and this module only ever renders what it is
given, never reaches back into a store to fetch more.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ..minds.character import VoiceSpec
from ..world.propositions import Proposition
from .claims import Claim, ClaimId, Confidence, Modality
from .digest import ConversationDigest
from .strategy import DeliveryDirective, ResponsePlan

# §15.1's per-slot token budgets, kept as named constants (not enforced by measuring a real
# tokenizer here — Phase 5's job — but as a section-count/length sanity ceiling every plan
# must respect equally, which is what I-18/I-42's PARITY requirement actually needs: honest
# and deceptive plans render the same shape).
MAX_RECENT_EXCHANGE_TURNS = 6
MAX_RETRIEVED_STATEMENTS = 5


class PersonaSlot(BaseModel):
    model_config = ConfigDict(frozen=True)

    voice: VoiceSpec = VoiceSpec()
    public_facts: tuple[Proposition, ...] = ()


class EnvelopeClaim(BaseModel):
    """What the renderer may see of a claim: its id, content, modality and confidence.
    `sincerity`, `source` and `grounding` stay engine-side (§10.3: "Sincerity is an engine-side
    label ... never given to the LLM") — `sincerity="deceptive"` tells the model which claims
    are lies, `source="slip"` names the act, `grounding` names the knowledge behind a claim."""
    model_config = ConfigDict(frozen=True)

    id: ClaimId
    proposition: Proposition
    modality: Modality = "actual"
    confidence: Confidence = "certain"

    @classmethod
    def of(cls, claim: Claim) -> "EnvelopeClaim":
        return cls(id=claim.id, proposition=claim.proposition, modality=claim.modality,
                   confidence=claim.confidence)


class Envelope(BaseModel):
    """Every slot from §15.1's table, minus the ones that carry only rendered strings
    (persona prose, schema note) — those never carry a `Proposition` and so are outside
    `props()`'s concern entirely, which is the point: I-1 is about propositions, not tone."""
    model_config = ConfigDict(frozen=True)

    persona: PersonaSlot
    delivery: DeliveryDirective
    allowed_claims: tuple[EnvelopeClaim, ...] = ()
    authorized_reveals: tuple[Proposition, ...] = ()
    digest_text: str = ""
    retrieved_statements: tuple[str, ...] = ()  # rendered text only (§15.1 "verbatim" prior statements)
    recent_exchange: tuple[str, ...] = ()
    query_text: str = ""


def speakable(plan: ResponsePlan, frame: tuple[Claim, ...] = ()) -> frozenset[Proposition]:
    """Everything this plan is allowed to say: its own claims, authorized reveals (a `SLIP`/
    `CONCESSION`/`CONFESSION`'s specific fact ids, §14.2e), the persona's public facts, and
    the padding `frame` the caller explicitly supplies (never anything this function fetches
    on its own)."""
    return frozenset(
        {c.proposition for c in plan.claims} | set(plan.authorized_reveals) | {c.proposition for c in frame}
    )


def render_digest(digest: ConversationDigest, labels: dict[str, str] | None = None) -> str:
    """§15.3: "rendered to a short paragraph by templates" — deterministic, from the
    structured digest fields only.

    `labels` maps a discovered `EvidenceId` to its display name (`digest.evidence_labels`); an id
    with no label renders as "an item", never as itself (F-11). The default of no labels is
    therefore the most conservative rendering, not the leakiest."""
    labels = labels or {}
    parts = [f"{digest.turns} turn(s) so far."]
    if digest.evidence_presented:
        shown = [labels.get(e, "an item") for e in digest.evidence_presented]
        parts.append(f"Presented: {', '.join(shown)}.")
    if digest.accusations:
        parts.append(f"Accused {digest.accusations} time(s).")
    if digest.contradictions_confronted:
        parts.append(f"Confronted with {digest.contradictions_confronted} contradiction(s).")
    if digest.mood_trajectory:
        parts.append("Mood: " + " -> ".join(f"t{t}:{m}" for t, m in digest.mood_trajectory) + ".")
    return " ".join(parts)


def build_envelope(plan: ResponsePlan, *, persona: PersonaSlot, digest: ConversationDigest,
                    frame: tuple[Claim, ...] = (), retrieved_statements: tuple[str, ...] = (),
                    recent_exchange: tuple[str, ...] = (), query_text: str = "",
                    digest_labels: dict[str, str] | None = None) -> Envelope:
    """§15.1's slot caps are applied HERE (truncation, never expansion) so the property test
    can assert a fixed structural bound independent of any one call site."""
    return Envelope(
        persona=persona, delivery=plan.delivery,
        allowed_claims=tuple(EnvelopeClaim.of(c) for c in plan.claims + frame),
        authorized_reveals=plan.authorized_reveals, digest_text=render_digest(digest, digest_labels),
        retrieved_statements=retrieved_statements[:MAX_RETRIEVED_STATEMENTS],
        recent_exchange=recent_exchange[-MAX_RECENT_EXCHANGE_TURNS:], query_text=query_text,
    )


def props(envelope: Envelope) -> frozenset[Proposition]:
    """I-1's `props()`: every proposition reachable from the envelope's TYPED fields —
    never from `digest_text`/`retrieved_statements`/`recent_exchange`, which are rendered
    strings the property test correctly does not (and cannot) parse back into propositions;
    those strings are themselves built only from ALREADY-committed, already-validated prior
    statements (§15.2), so they carry nothing new."""
    return frozenset(
        {c.proposition for c in envelope.allowed_claims}
        | set(envelope.authorized_reveals)
        | set(envelope.persona.public_facts)
    )
