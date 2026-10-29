"""Verbal pressure and composure (§11.2, I-16, I-29): DELIVERY-ONLY quantities, deliberately
kept out of every peel/slip/confession gate (`peel.py`/`strategy.py` never import this
module's outputs into those predicates — they read only `refutation_weight` and static
`Personality`).

The architecture gives the update rule as arithmetic on the deltas ("composure -=
0.4 x delta_verbal + 0.6 x delta_refutation_weight; composure += recovery(personality) on
calm turns") without pinning two numbers: the per-topic probing cap's bookkeeping unit, and
`recovery()`'s formula. Both are documented, smallest-deterministic choices below, in the
style already used throughout `minds/` for similarly under-specified constants (e.g.
`belief.OPPORTUNITY_MARGIN`, `memory.DECAY_TAU0/1`).
"""
from __future__ import annotations

from dataclasses import dataclass

from ..minds.character import VERBAL_PRESSURE_MAX
from ..minds.character import Personality
from ..minds.scale import BP_MAX

PROVISIONAL_ACCUSATION_BP = 1500
HOSTILE_TONE_BP = 500
REPEATED_PROBE_BP = 300
REPEATED_PROBE_TOPIC_CAP_BP = 2000  # "cap 2000/topic": probing alone may not push a topic's
                                     # contribution past this; tracked via `topics_probed[topic]`
                                     # (already an int count, §9) — capped once
                                     # `count * REPEATED_PROBE_BP` would exceed the ceiling.
DECAY_RATE = 0.05
CALM_THREAT_THRESHOLD = 0.3


@dataclass(frozen=True)
class PressureFeatures:
    """One turn's inputs to the verbal-pressure update — everything the strategy/turn runner
    already computed for other reasons (accusation, tone, topic, threat)."""
    provisional_accusation: bool = False
    hostile_tone: bool = False
    repeated_probe_of_protected_topic: bool = False
    topic_probe_count_before: int = 0
    threat: float = 0.0


def update_verbal_pressure(current_bp: int, features: PressureFeatures) -> int:
    delta = 0
    if features.provisional_accusation:
        delta += PROVISIONAL_ACCUSATION_BP
    if features.hostile_tone:
        delta += HOSTILE_TONE_BP
    if (features.repeated_probe_of_protected_topic
            and features.topic_probe_count_before * REPEATED_PROBE_BP < REPEATED_PROBE_TOPIC_CAP_BP):
        delta += REPEATED_PROBE_BP
    if delta > 0:
        return min(VERBAL_PRESSURE_MAX, current_bp + delta)
    if features.threat < CALM_THREAT_THRESHOLD:
        return round(current_bp * (1 - DECAY_RATE))
    return current_bp


def recovery_bp(personality: Personality) -> int:
    """A calm turn's composure recovery — scaled by `composure_base` so a naturally steady
    character recovers faster, matching how `Personality.composure_base` seeds
    `CharacterState.composure` in the first place (`minds/character.py::initial_character_state`)."""
    return round(300 * max(0.0, min(1.0, personality.composure_base)))


def update_composure(current_bp: int, *, delta_verbal_bp: int, delta_weight_bp: int,
                      personality: Personality, calm_turn: bool) -> int:
    """§11.2: "composure -= 0.4 x delta_verbal + 0.6 x delta_refutation_weight; composure +=
    recovery(personality) on calm turns". Both terms act on the SAME turn: a turn can both
    lose ground to fresh pressure/weight and be "calm" in the sense of carrying no hostile
    tone or accusation this turn (`calm_turn` is the caller's own `threat < 0.3` reading,
    passed in rather than recomputed here to keep this function a pure arithmetic step)."""
    delta = -(0.4 * delta_verbal_bp + 0.6 * delta_weight_bp)
    new = current_bp + round(delta)
    if calm_turn:
        new += recovery_bp(personality)
    return max(0, min(BP_MAX, new))
