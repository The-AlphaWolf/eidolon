"""`ConversationDigest` (§15.3): a deterministic, from-the-log summary — "because it is
derived from events, it is reproducible and never drifts. Same log => same digest bytes."

`standing_claims` truncation follows §15.3's own rule: "claims on the current topic first,
then by recency". Recency is statement order (`StatementStore.all()` already preserves
append/turn order); "current topic" match is a documented heuristic — a claim matches when
the query's topic string names an entity/location the claim's proposition mentions, or
equals its proposition kind lowercased (the same tag `memory.py`'s own `CueSet.topic_tags`
uses) — since Phase 4 has no separate `TopicId` taxonomy beyond that convention.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ..minds.character import DetectiveModel, Emotion
from ..world.ids import ActorId, EvidenceId
from ..world.propositions import entities
from .claims import ClaimId, StatementStore
from .ids import TopicId

STANDING_CLAIMS_BUDGET = 5
MOOD_TRAJECTORY_LIMIT = 5


class ConversationDigest(BaseModel):
    model_config = ConfigDict(frozen=True)

    character: ActorId
    turns: int
    topics: dict[TopicId, int] = {}
    evidence_presented: tuple[EvidenceId, ...] = ()
    accusations: int = 0
    contradictions_confronted: int = 0
    mood_trajectory: tuple[tuple[int, str], ...] = ()
    standing_claims: tuple[ClaimId, ...] = ()


def _dominant_emotion(emotion: Emotion) -> str:
    from ..minds.scale import frac
    dims = {"anxiety": frac(emotion.anxiety), "hostility": frac(emotion.hostility), "warmth": frac(emotion.warmth)}
    top = max(dims, key=lambda k: dims[k])
    return top if dims[top] > 0.15 else "neutral"


def inflection_points(mood_log: list[tuple[int, Emotion]], limit: int = MOOD_TRAJECTORY_LIMIT) -> tuple[tuple[int, str], ...]:
    """Turns where the dominant emotion CHANGED from the previous turn — "the last 5
    inflection points" (§15.3), not every turn's mood."""
    points: list[tuple[int, str]] = []
    last: str | None = None
    for turn, emotion in mood_log:
        label = _dominant_emotion(emotion)
        if label != last:
            points.append((turn, label))
            last = label
    return tuple(points[-limit:])


def _matches_topic(claim, topic: TopicId) -> bool:
    prop = claim.proposition
    if prop.kind.lower() == topic.lower():
        return True
    actors, locations, objects, ambiguous = entities(prop)
    return topic in actors | locations | objects | ambiguous


def standing_claims_ordered(statements: StatementStore, speaker: ActorId,
                             current_topic: TopicId | None, limit: int = STANDING_CLAIMS_BUDGET) -> tuple[ClaimId, ...]:
    recent_first = list(reversed(statements.standing_for_speaker(speaker)))
    on_topic: list[ClaimId] = []
    other: list[ClaimId] = []
    for s in recent_first:
        for c in s.claims:
            bucket = on_topic if (current_topic and _matches_topic(c, current_topic)) else other
            bucket.append(c.id)
    ordered = on_topic + other
    return tuple(ordered[:limit])


def evidence_labels(evidence, case, discovered) -> dict[str, str]:
    """Display-level names for the items the digest says were presented (F-11).

    §15.3 keeps `evidence_presented` as a list of `EvidenceId` — the structured digest is engine
    state and `audit_envelope` needs the ids to check them against `DiscoveryState` — but it only
    says the digest is "rendered to a short paragraph by templates", never that the RENDERED text
    must carry the id. An id is meaningless to a renderer, is exactly the sort of engine token
    `internal_token_violations` then has to police out of the reply, and is the one engine
    identifier that was still crossing the boundary.

    Only DISCOVERED items get a label, so an id that reached `evidence_presented` without being
    discovered renders as the generic placeholder rather than describing itself (I-15)."""
    out: dict[str, str] = {}
    for item in evidence.all():
        if item.id not in discovered:
            continue
        obj = case.objects[item.object].name if item.object and item.object in case.objects else None
        if item.kind == "Object" and obj:
            out[item.id] = obj
        elif obj:
            out[item.id] = f"the {item.kind.lower()} on {obj}"
        else:
            out[item.id] = f"the {item.kind.lower()}"
    return out


def build_digest(character: ActorId, turns: int, topics: dict[TopicId, int],
                  detective_model: DetectiveModel, statements: StatementStore,
                  mood_log: list[tuple[int, Emotion]], current_topic: TopicId | None = None,
                  accusations: int = 0) -> ConversationDigest:
    return ConversationDigest(
        character=character, turns=turns, topics=dict(topics),
        evidence_presented=tuple(sorted(detective_model.known_evidence)),
        accusations=accusations,
        contradictions_confronted=len(detective_model.contradictions_confronted),
        mood_trajectory=inflection_points(mood_log),
        standing_claims=standing_claims_ordered(statements, character, current_topic),
    )
