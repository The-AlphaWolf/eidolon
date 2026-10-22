"""Memory architecture (§8): encoding, decay and distortion at generation (pure, deterministic
functions of the case — §8.1's "authored at generation... never sampled at runtime"), plus
retrieval at runtime (§8.4, also pure — the only runtime state it reads is the
`EpistemicState` overlay, never mutated in place).
"""
from __future__ import annotations

import hashlib
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..world.case import Case
from ..world.events import Event
from ..world.ids import ActorId, EventId
from ..world.interval import overlaps
from ..world.state import presence
from .belief import Belief
from .epistemic import EpistemicState, RecallRecord, current_memory_strength
from .ids import BeliefId, MemoryId
from .knowledge import KnowledgeStore
from .provenance import Participated, Told, Witnessed
from .scale import Bp, bp, frac

# §8.2 salience weights (fixed by the architecture's own formula).
SALIENCE_BASE = 0.2
W_NOVELTY, W_EMOTION, W_SELF = 0.3, 0.3, 0.2

# §8.3 decay time constants (minutes). Not given numerically by the architecture, only
# qualitatively ("gentle" over a case window of hours) — chosen so that at low salience a
# 2-hour-old memory (`vance_v03`'s `t_investigation` = 120) still retains roughly half its
# salience, and higher salience decays slower still.
DECAY_TAU0 = 200.0
DECAY_TAU1 = 175.0

RETRIEVE_STRONG = 0.55
RETRIEVE_WEAK = 0.30
REPETITION_STEP = 0.05
REPETITION_CAP = 1.3

# §8.2 "rare event kinds score higher" / "Attack, Argument, Die, personal relevance" — no
# numeric table is given; this is the documented, smallest deterministic reading. `Speak`
# stands in for "Argument" (the schema has no separate Argument kind, §4.5).
_NOVELTY = {"Attack": 1.0, "Die": 1.0, "Hide": 0.8, "Plant": 0.8, "Write": 0.4, "Clean": 0.4,
            "Speak": 0.3, "Meet": 0.3, "Take": 0.3, "Give": 0.3, "Read": 0.3, "Use": 0.2,
            "Observe": 0.2, "Environmental": 0.1, "Move": 0.05, "Stay": 0.05}
_EMOTION_CHARGE = {"Attack": 1.0, "Die": 1.0, "Speak": 0.5, "Hide": 0.5, "Plant": 0.5,
                    "Meet": 0.3, "Clean": 0.2, "Take": 0.2, "Give": 0.2, "Write": 0.2,
                    "Use": 0.1, "Read": 0.1, "Observe": 0.1, "Environmental": 0.1,
                    "Move": 0.05, "Stay": 0.05}
_DEFAULT_NOVELTY = 0.2
_DEFAULT_EMOTION = 0.2


class CueSet(BaseModel):
    model_config = ConfigDict(frozen=True)

    entities: tuple[str, ...] = ()
    location: str | None = None
    time_bucket: str | None = None
    topic_tags: tuple[str, ...] = ()
    sensory_tags: tuple[str, ...] = ()

    def tags(self) -> frozenset[str]:
        out = {f"entity:{e}" for e in self.entities}
        if self.location:
            out.add(f"location:{self.location}")
        if self.time_bucket:
            out.add(f"time:{self.time_bucket}")
        out |= {f"topic:{t}" for t in self.topic_tags}
        out |= {f"sensory:{t}" for t in self.sensory_tags}
        return frozenset(out)


class Distortion(BaseModel):
    model_config = ConfigDict(frozen=True)

    field: Literal["interval", "actor", "object", "location", "order"]
    true_value: object
    recalled_value: object
    cause: Literal["time_compression", "identity_confusion", "conflation", "suggestion", "gap_fill"]
    correctable_by: tuple[str, ...] = ()
    # ^ EvidenceId | StatementId, per the architecture. Left empty: neither model exists
    #   yet (Phase 3/4). The correction MECHANISM (§8.6) is implemented and tested against
    #   a hand-supplied item id; populating real, reachable ids is later phases' work.


class Memory(BaseModel):
    """§6.2. SEALED at generation (I-4) — runtime deltas live in `EpistemicState`."""
    model_config = ConfigDict(frozen=True)

    id: MemoryId
    character: ActorId
    kind: Literal["episodic", "semantic"]
    content: tuple[BeliefId, ...]
    episode: EventId | None = None
    encoded_at: int
    salience: Bp  # fixed at encoding
    strength_0: Bp  # retrievability AT SEAL, i.e. after generation-time decay (§6.2)
    emotion: str | None = None
    cues: CueSet
    distortions: tuple[Distortion, ...] = ()


def memory_granularity(strength_bp: int) -> int:
    """§8.3: coarser time granularity for weaker memories ("around ten" without a distortion)."""
    s = frac(strength_bp)
    if s > 0.7:
        return 5
    if s > 0.4:
        return 15
    return 30


def _det_unit(*parts: str) -> float:
    """Deterministic 0..1 pseudo-random value from a hash of `parts` (I-6: `random` is
    banned outside `gen/`, which does not exist yet; this is the same
    `hash(case_seed, ...)` tie-break pattern the architecture prescribes elsewhere,
    applied to distortion assignment so it stays "seeded" — i.e. reproducible per
    case/memory — without importing a banned RNG)."""
    h = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _decay(delta_t: int, salience_frac: float) -> float:
    return math.exp(-max(0, delta_t) / (DECAY_TAU0 + DECAY_TAU1 * salience_frac))


def _anchor_event_id(belief: Belief, store: KnowledgeStore) -> str | None:
    """The real `Event.id` this belief's grounding traces to, if any. `Witnessed.event_id`
    is sometimes a real event-perception pid (`"<EventId>@<observer>"`, §4.8) and sometimes
    a perception-module synthetic segment id (`"seg:..."`/`"see:..."`, own-presence or
    co-presence) — only the former names a discrete episode; the `@`-split is a no-op on
    the synthetic form, which correctly then fails the `events_by_id` lookup in
    `encode_memories` and falls back to a semantic memory."""
    if not belief.grounds:
        return None
    entry = store.get(belief.grounds[0])
    if entry is None:
        return None
    src = entry.source
    if isinstance(src, Witnessed):
        return src.event_id.split("@", 1)[0]
    if isinstance(src, Participated):
        return src.event_id
    if isinstance(src, Told):
        return src.speak_event_id
    return None


def _self_relevance(character: ActorId, event: Event | None, case: Case) -> float:
    if event is None:
        return 1.0  # presence-anchored memory (own/co-presence): the character was there
    if event.actor == character or character in event.participants:
        return 1.0
    for iv, loc in presence(case.events, character):
        if loc == event.location and overlaps(iv, event.interval):
            return 0.6
    return 0.3


def _entities_of(prop) -> tuple[str, ...]:
    ids: list[str] = []
    for field in ("actor", "observer", "a", "b", "target_actor", "murderer"):
        v = getattr(prop, field, None)
        if isinstance(v, str):
            ids.append(v)
    subject = getattr(prop, "subject", None)
    if isinstance(subject, str) and subject not in ("figure", "nobody"):
        ids.append(subject)
    return tuple(dict.fromkeys(ids))


def _cues_for_prop(prop) -> CueSet:
    loc = getattr(prop, "location", None) or getattr(prop, "from_location", None)
    iv = getattr(prop, "interval", None)
    bucket = f"b{iv[0] // 30}" if iv else None
    return CueSet(entities=_entities_of(prop), location=loc, time_bucket=bucket, topic_tags=(prop.kind.lower(),))


def _merge_cues(beliefs: list[Belief]) -> CueSet:
    entities: set[str] = set()
    locs: set[str] = set()
    buckets: set[str] = set()
    topics: set[str] = set()
    for b in beliefs:
        c = _cues_for_prop(b.proposition)
        entities |= set(c.entities)
        if c.location:
            locs.add(c.location)
        if c.time_bucket:
            buckets.add(c.time_bucket)
        topics |= set(c.topic_tags)
    return CueSet(entities=tuple(sorted(entities)), location=next(iter(locs)) if len(locs) == 1 else None,
                  time_bucket=next(iter(buckets)) if len(buckets) == 1 else None, topic_tags=tuple(sorted(topics)))


def _assign_distortions(case: Case, memory_id: MemoryId, strength_frac: float, beliefs: list[Belief]) -> tuple[Distortion, ...]:
    """§8.7, `time_compression` only (documented scope: see module docstring and the
    completion report — `identity_confusion`/`gap_fill` need data the closed schema does
    not carry; `conflation`/`suggestion` need multi-memory context this per-memory
    function does not have). "At most one distortion per memory" (§8.7 global limit)."""
    if not (strength_frac < 0.6):
        return ()
    b = beliefs[0]
    iv = getattr(b.proposition, "interval", None)
    if iv is None:
        return ()
    roll = _det_unit(case.id, memory_id, "time_compression")
    if roll >= 0.5:  # deterministic per-memory coin flip: half of eligible memories distort
        return ()
    shift = 1 + round(_det_unit(case.id, memory_id, "shift") * 19)  # 1..20 minutes
    direction = 1 if _det_unit(case.id, memory_id, "direction") >= 0.5 else -1
    recalled = (iv[0] + shift * direction, iv[1] + shift * direction)
    return (Distortion(field="interval", true_value=list(iv), recalled_value=list(recalled),
                        cause="time_compression"),)


def encode_memories(character: ActorId, beliefs: list[Belief], store: KnowledgeStore, case: Case) -> list[Memory]:
    """§8.2-8.3: one memory per event-anchored cluster of beliefs (episodic), one memory
    per remaining belief (semantic — co-presence/absence/inferred/told beliefs have no
    single discrete episode). Every belief ends up in exactly one memory: nothing formed
    in `belief.py` is silently unretrievable."""
    events_by_id = {e.id: e for e in case.events}
    groups: dict[str, list[Belief]] = {}
    singles: list[Belief] = []
    for b in beliefs:
        anchor = _anchor_event_id(b, store)
        if anchor is not None and anchor in events_by_id:
            groups.setdefault(anchor, []).append(b)
        else:
            singles.append(b)

    memories: list[Memory] = []
    counter = [0]

    def build(event: Event | None, blist: list[Belief], kind: Literal["episodic", "semantic"]) -> None:
        counter[0] += 1
        mem_id = f"M{character}{counter[0]:04d}"
        novelty = _NOVELTY.get(event.kind, _DEFAULT_NOVELTY) if event else _DEFAULT_NOVELTY
        charge = _EMOTION_CHARGE.get(event.kind, _DEFAULT_EMOTION) if event else _DEFAULT_EMOTION
        relevance = _self_relevance(character, event, case)
        salience_frac = max(0.0, min(1.0, SALIENCE_BASE + W_NOVELTY * novelty + W_EMOTION * charge + W_SELF * relevance))
        encoded_at = min(b.formed_at for b in blist)
        strength_frac = max(0.0, min(1.0, salience_frac * _decay(case.t_investigation - encoded_at, salience_frac)))
        memories.append(Memory(
            id=mem_id, character=character, kind=kind, content=tuple(b.id for b in blist),
            episode=event.id if (kind == "episodic" and event) else None, encoded_at=encoded_at,
            salience=bp(salience_frac), strength_0=bp(strength_frac), cues=_merge_cues(blist),
            distortions=_assign_distortions(case, mem_id, strength_frac, blist),
        ))

    for event_id, blist in groups.items():
        build(events_by_id[event_id], blist, "episodic")
    for b in singles:
        build(None, [b], "semantic")
    return memories


def cue_overlap(a: CueSet, b: CueSet) -> float:
    """Jaccard over entities/location/time-bucket/topic (§8.4)."""
    ta, tb = a.tags(), b.tags()
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def repetition_factor(records: tuple[RecallRecord, ...]) -> float:
    return min(REPETITION_CAP, 1.0 + REPETITION_STEP * len(records))


def emotional_boost(memory: Memory, current_emotion_tag: str | None) -> float:
    return 1.0 if memory.emotion is not None and memory.emotion == current_emotion_tag else 0.0


def score(memory: Memory, epistemic: EpistemicState, cues: CueSet, current_emotion_tag: str | None = None) -> float:
    strength = frac(current_memory_strength(epistemic, memory.id, memory.strength_0))
    records = epistemic.recall_log.get(memory.id, ())
    return strength * cue_overlap(memory.cues, cues) * (1 + 0.3 * emotional_boost(memory, current_emotion_tag)) * repetition_factor(records)


class RetrievalResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    strong: tuple[MemoryId, ...] = ()
    weak: tuple[MemoryId, ...] = ()


def retrieve(memories: list[Memory], epistemic: EpistemicState, cues: CueSet,
             current_emotion_tag: str | None = None) -> RetrievalResult:
    """§8.4, pure: a function of `(memory store, cues, recall_log)` only."""
    strong, weak = [], []
    for m in memories:
        s = score(m, epistemic, cues, current_emotion_tag)
        if s >= RETRIEVE_STRONG:
            strong.append(m.id)
        elif s >= RETRIEVE_WEAK:
            weak.append(m.id)
    return RetrievalResult(strong=tuple(strong), weak=tuple(weak))
