"""§9 character state: `Personality` (static, generation-time), `Emotion`/`CharacterState`
(runtime, mutable only via named events, I-31), `DetectiveModel` (no telepathy, §11.3).

`CharacterState` is frozen; "mutation" is `.model_copy(update=...)` producing a new
instance, the same pattern `world/state.py`'s `WorldState` uses — folds never mutate in
place, which is what makes replay determinism (I-5) possible.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from ..world.ids import ActorId
from .scale import BP_MAX, Bp, bp

VERBAL_PRESSURE_MAX = BP_MAX  # bp cap (§11.2); the `Bp` annotation is what enforces it


class VoiceSpec(BaseModel):
    """§9: "public style (register, idiom, tics) — safe to give the LLM." `voice_register`
    rather than `register`: pydantic's `BaseModel` reserves that name (shadow warning)."""
    model_config = ConfigDict(frozen=True)

    voice_register: str = ""
    idiom: tuple[str, ...] = ()
    tics: tuple[str, ...] = ()


Weight = Annotated[float, Field(ge=0.0, le=1.0)]   # RR-N2: §15.4's margins over every other act assume weights in [0, 1]


class Personality(BaseModel):
    """Static weights from generation (§9) — plain `float`, not bp: I-17's bp requirement
    is for *runtime-mutable* state, and personality never changes after generation."""
    model_config = ConfigDict(frozen=True)

    composure_base: Weight
    volatility: Weight
    deference: Weight
    loyalty: dict[ActorId, Weight] = {}
    guile: Weight
    talkativeness: Weight
    self_preservation: Weight
    voice: VoiceSpec = VoiceSpec()


class Emotion(BaseModel):
    """Three dimensions only (§9) — a tone knob, not a psychology engine."""
    model_config = ConfigDict(frozen=True)

    anxiety: Bp = 0
    hostility: Bp = 0
    warmth: Bp = 0


class DetectiveModel(BaseModel):
    """§11.3. Updated only from interactions with THIS character — no telepathy term (the
    v0.2 `estimated_suspicion_of_me` cross-character-decay bug this fixes)."""
    model_config = ConfigDict(frozen=True)

    known_evidence: frozenset[str] = frozenset()
    heard_statements: frozenset[str] = frozenset()
    accusations: tuple[tuple[int, bool, ActorId], ...] = ()  # (turn_id, provisional, target)
    probed_topics: dict[str, int] = {}
    estimated_suspicion_of_me: Bp = 0
    contradictions_confronted: tuple[str, ...] = ()


class CharacterState(BaseModel):
    """§9. Every scalar is bp (I-17); every field is written by exactly one
    `SessionEventKind` (I-31, `events.py`/`fold.py`). `cover_layer` is deliberately NOT a
    field here — it is a derived, monotone function of the presented set (§9 comment,
    Phase 4's job); storing it would let it drift from what the weight function implies."""
    model_config = ConfigDict(frozen=True)

    actor: ActorId
    personality: Personality
    emotion: Emotion = Emotion()
    trust_detective: Bp = 5000
    suspicion_of_detective: Bp = 0
    suspicion: dict[ActorId, Bp] = {}
    verbal_pressure: dict[str, Bp] = {}  # SecretId (plain str id; `Secret` model is Phase 4) -> bp
    composure: Bp = 5000
    refuse_streak: int = 0
    detective_model: DetectiveModel = DetectiveModel()
    topics_probed: dict[str, int] = {}
    contradictions_caught: tuple[str, ...] = ()
    slips_used: frozenset[str] = frozenset()


def initial_character_state(actor: ActorId, personality: Personality) -> CharacterState:
    return CharacterState(actor=actor, personality=personality,
                           composure=bp(personality.composure_base))
