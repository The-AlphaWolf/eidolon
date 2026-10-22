"""The `Query` type (§12.2): stage 1's output for free-text `Ask` actions. `Present`,
`Accuse` and `Hypothesize` are structured UI actions that enter at stage 3 and never carry a
`Query` (I-26, ADR-16) — they are modelled in `turn.py`, not here.

Phase 4 does not build the intent parser (that is an LLM call, Phase 5's `AnthropicLLM` role,
§12.3) or grounding's name/time resolution against a real `Alias`/`TimeAnchor` table
(generation-time content, Phase 6). What it needs and builds is the `Query` shape itself and
`normalize()` (§15.4's repetition hash), since both the strategy engine and the digest are
Phase 4 deliverables that consume them. `TemplateLLM`/tests construct `Query` directly,
mirroring how `TemplateLLM` in §28.2 stands in for the whole parser role without a model.
"""
from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..world.ids import ActorId, LocationId
from ..world.propositions import Proposition
from .ids import TopicId

QueryKind = Literal[
    "where", "when", "who", "what", "why", "did_you", "did_they", "relationship",
    "opinion", "hypothetical", "narrative", "recall_detail", "challenge", "smalltalk",
    "meta", "coercion",
]

Tone = Literal["neutral", "hostile", "sympathetic", "sarcastic"]


class TimePhrase(BaseModel):
    """A player-facing time expression already resolved to a tick interval and a topic-bucket
    granularity by grounding (stage 2) — the phrase text is kept only for the digest/notebook,
    never re-parsed downstream."""
    model_config = ConfigDict(frozen=True)

    text: str
    interval: tuple[int, int] | None = None


class EntityRef(BaseModel):
    """A grounded reference (stage 2 output): an id the case actually contains. Ungrounded
    names never reach this far — stage 2 emits `Clarify` instead (§12.1)."""
    model_config = ConfigDict(frozen=True)

    id: str
    kind: Literal["actor", "location", "object"]


class Query(BaseModel):
    """§12.2. `presupposes` matters most: a loaded question is handled as an implicit
    `Present` of a proposition with **zero** evidential weight (§12.2, I-25) — never a
    breaker, never knowledge, and never `contributes weight` (I-16)."""
    model_config = ConfigDict(frozen=True)

    kind: QueryKind
    subject: EntityRef | None = None
    predicate_hint: str | None = None
    object: EntityRef | None = None
    location: LocationId | None = None
    time: TimePhrase | None = None
    presupposes: tuple[Proposition, ...] = ()
    tone: Tone = "neutral"
    quoted_statement: str | None = None  # StatementId, resolved against the ledger at stage 2
    raw: str = ""


def normalize(query: Query) -> str:
    """§15.4: `(kind, subject_id, predicate_hint canonical form, object_id, location_id,
    time bucket) -> hash`. Paraphrases converge on the same hash via the parser (grounding
    already maps synonyms to the same `predicate_hint`/ids before this runs); this function
    only does the tuple-to-hash half."""
    time_bucket = None
    if query.time is not None and query.time.interval is not None:
        time_bucket = query.time.interval[0] // 30  # §8.3's own 30-minute coarse bucket
    key = (query.kind, query.subject.id if query.subject else None,
           (query.predicate_hint or "").strip().lower() or None,
           query.object.id if query.object else None, query.location, time_bucket)
    return hashlib.sha256(repr(key).encode()).hexdigest()[:16]
