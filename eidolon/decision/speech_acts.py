"""The speech-act catalogue (§10.3): the strategic *form* of a turn's response, chosen by
the engine and never named to the LLM for deceptive acts (§10.3's own closing line). Kept as
a small, closed vocabulary — the same "closed schema, ADR to extend" discipline the
proposition schema and `ActionKind` already use (§4.7, ADR-22) — because `strategy.py`'s
candidate enumeration, `validator.py`'s CONCESSION/CORRECTION waiver and the static I-29
check all switch on these names.

Sincerity (`truthful | sincere_false | deceptive`) is a *label*, computed from what was
actually retrieved for the turn (§6.5's closing paragraph), not a fixed property of the act:
the table below records each act's *typical* sincerity for documentation, but callers should
derive the actual label from the claim's content, not from `SINCERITY_OF[act]` alone, for the
one act (`REINTERPRET`) the architecture itself marks "deceptive/truthful per content".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SpeechAct = Literal[
    "TRUTH", "VAGUE", "DONT_RECALL", "DONT_KNOW", "SINCERE_FALSE", "MISREMEMBERED",
    "OMISSION", "PARTIAL_TRUTH", "LIE", "MISLEADING_TRUE", "REINTERPRET", "DENY_EVIDENCE",
    "DEFLECT", "EVASION", "COUNTER_QUESTION", "SILENCE", "REFUSE", "REPEAT_PRIOR", "CLARIFY",
    "CORRECT_DETECTIVE", "OPINION", "HYPOTHETICAL", "CONCESSION", "CORRECTION", "SLIP",
    "CONFESSION", "STONEWALL", "ANGER", "ACCUSE_DETECTIVE", "INCIDENTAL",
]

Sincerity = Literal["truthful", "sincere_false", "deceptive"]


@dataclass(frozen=True)
class ActSpec:
    """One row of §10.3's table. `typical_sincerity` is `None` where the architecture says
    the label depends on content (`REINTERPRET`) or is not itself a sincerity claim
    (`COUNTER_QUESTION`, `CLARIFY`, acts with no propositional content)."""
    typical_sincerity: Sincerity | None
    committing: bool  # "claim committed" / case-affecting per the effect column


ACT_TABLE: dict[SpeechAct, ActSpec] = {
    "TRUTH": ActSpec("truthful", True),
    "VAGUE": ActSpec("truthful", True),
    "DONT_RECALL": ActSpec("truthful", False),
    "DONT_KNOW": ActSpec("truthful", False),
    "SINCERE_FALSE": ActSpec("sincere_false", True),
    "MISREMEMBERED": ActSpec("sincere_false", True),
    "OMISSION": ActSpec("deceptive", True),
    "PARTIAL_TRUTH": ActSpec("deceptive", True),
    "LIE": ActSpec("deceptive", True),
    "MISLEADING_TRUE": ActSpec("deceptive", True),
    "REINTERPRET": ActSpec(None, True),
    "DENY_EVIDENCE": ActSpec("deceptive", True),
    "DEFLECT": ActSpec("deceptive", True),  # "truthful content, deceptive intent" (§10.3)
    "EVASION": ActSpec("deceptive", False),
    "COUNTER_QUESTION": ActSpec(None, False),
    "SILENCE": ActSpec(None, False),
    "REFUSE": ActSpec(None, False),
    "REPEAT_PRIOR": ActSpec(None, True),  # "as prior" (§10.3) — inherits the prior claim's label
    "CLARIFY": ActSpec(None, False),
    "CORRECT_DETECTIVE": ActSpec("truthful", True),
    "OPINION": ActSpec("truthful", True),
    "HYPOTHETICAL": ActSpec(None, False),  # "not commitments" (§10.3)
    "CONCESSION": ActSpec(None, True),  # "mixed" per §10.3
    "CORRECTION": ActSpec("truthful", True),
    "SLIP": ActSpec("truthful", True),  # "truthful (unintended)"
    "CONFESSION": ActSpec("truthful", True),
    "STONEWALL": ActSpec(None, False),
    "ANGER": ActSpec(None, False),
    "ACCUSE_DETECTIVE": ActSpec(None, False),
    "INCIDENTAL": ActSpec(None, False),
}

# Acts §14.2(f) exempts from the consistency/contradiction gate: a plan that retracts its own
# prior claims is expected to contradict them (§13.3 step 6, §14.2(f)'s own text).
RETRACTION_EXEMPT_ACTS: frozenset[SpeechAct] = frozenset({"CONCESSION", "CORRECTION"})
