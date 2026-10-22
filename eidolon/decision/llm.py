"""The `LLMPort` seam (ADR-12, §28.2) and `TemplateLLM` — "a deterministic renderer of
envelope -> utterance + faithful claims. Enables the entire pipeline without a model."

Phase 4 builds only `TemplateLLM`; `RecordedLLM`/`MutantLLM`/`AnthropicLLM` live in
`eidolon.llm` (Phase 5). `TemplateLLM` is enough to drive every Phase 4 test (the golden trace, the
2 000-turn bot, I-1/I-3) because it is faithful by construction — every segment it emits is
tagged with exactly the claim it renders, so `validator.py`'s deterministic checks are
exercised for real while the "verifier" role is satisfied by construction rather than by a
second model call.
"""
from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from ..world.alias import render_time
from ..world.case import Case
from ..world.ids import ActorId
from .claims import Claim, ClaimId
from .envelope import Envelope, EnvelopeClaim

SegmentKind = Literal["assert", "color", "question", "nonverbal"]


class Segment(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    claim_ids: tuple[ClaimId, ...] = ()
    kind: SegmentKind = "assert"


class Draft(BaseModel):
    model_config = ConfigDict(frozen=True)

    segments: tuple[Segment, ...] = ()


class LLMPort(Protocol):
    """The generator seam (§28.2). `feedback` is the repair loop's violation phrasing (§14.3),
    passed only on a regeneration; a port that ignores it is still correct."""
    def generate(self, envelope: Envelope, case: Case, speaker: ActorId,
                 feedback: tuple[str, ...] = ()) -> Draft: ...


def _name(case: Case, entity_id: str) -> str:
    if entity_id in case.actors:
        return case.actors[entity_id].name
    if entity_id in case.locations:
        return case.locations[entity_id].name
    if entity_id in case.objects:
        return case.objects[entity_id].name
    return entity_id


def render_claim(claim: Claim | EnvelopeClaim, case: Case) -> str:
    """§14.3's own template-family idea ('"I was in the {location} from {t1} until {t2}."'),
    generalised to the proposition kinds Phase 4's fixtures exercise. Deliberately dull —
    the fallback repair render in a real turn runner IS exactly this dull on purpose
    (§14.3); `TemplateLLM` simply always speaks this way."""
    p = claim.proposition
    neg = "" if claim.modality != "negated" else "not "
    if p.kind == "At":
        t1, t2 = render_time(p.interval[0]), render_time(p.interval[1])
        return f"I was {neg}in {_name(case, p.location)} from {t1} until {t2}."
    if p.kind == "NotAt":
        t1, t2 = render_time(p.interval[0]), render_time(p.interval[1])
        return f"I was not in {_name(case, p.location)} from {t1} until {t2}."
    if p.kind == "Did":
        t1 = render_time(p.interval[0])
        # `Object.name` fixtures already carry their own article ("a drinking glass", "the
        # terrace door") — prefixing another one here is what produced "the a kitchen knife".
        obj = f" {_name(case, p.object)}" if p.object else ""
        return f"I did {p.action.lower()}{obj} around {t1}."  # a verb, not a name (§14.2(b))
    if p.kind == "DidNot":
        obj = f" {_name(case, p.object)}" if p.object else ""
        return f"I never {p.action.lower()}{obj}."
    if p.kind == "Saw":
        t1 = render_time(p.interval[0])
        who = _name(case, p.subject) if p.identified else "someone"
        return f"I saw {who} in {_name(case, p.location)} around {t1}."
    if p.kind == "Heard":
        return f"I heard {p.sound_kind}."
    if p.kind == "Attitude":
        return f"I {p.attitude_kind} {_name(case, p.b)}."
    return f"({p.kind.lower()} noted.)"


class TemplateLLM:
    """§28.2. One segment per allowed claim, tagged with exactly that claim's id — faithful
    by construction, so it can never itself produce an `UNTAGGED_ASSERTION` or
    `SLOT_MISMATCH`; those classes are exercised by hand-built adversarial `Draft`s in the
    validator tests instead (mirroring how a real `MutantLLM` would inject them, without
    needing that Phase 5 model)."""

    def generate(self, envelope: Envelope, case: Case, speaker: ActorId,
                 feedback: tuple[str, ...] = ()) -> Draft:
        segments = tuple(
            Segment(text=render_claim(c, case), claim_ids=(c.id,), kind="assert")
            for c in envelope.allowed_claims
        )
        if not segments:   # a claimless act still says something in character - no fact, only the tone the plan already chose
            text = CLAIMLESS_LINES.get(envelope.delivery.tone, "I'd rather not say.")
            segments = (Segment(text=text, claim_ids=(), kind="question" if text.endswith("?") else "color"),)
        return Draft(segments=segments)


# What a claimless reply sounds like, keyed by the plan's delivery tone (which already carries the act, F-4). No names, places,
# times or facts - each line passes every check a model's colour segment must pass. Was "...", whatever the act.
CLAIMLESS_LINES = {
    "apologetic": "I'm sorry. I honestly can't remember.",
    "puzzled": "I'm afraid I wouldn't know.",
    "shrugs": "I couldn't tell you.",
    "clipped": "I've answered that already.",
    "changes the subject": "Must we go over all this again?",
    "turns it back": "Why do you ask me that?",
    "baffled": "I'm sorry, I don't follow.",
    "indignant": "I don't care for your tone.",
    "thoughtful": "I'd rather not guess.",
    "imagines": "I couldn't say what might have happened.",
    "resolute; gives no ground": "I have nothing more to say.",
    "weary": "I've told you all I can.",
}
