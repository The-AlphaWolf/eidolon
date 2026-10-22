"""Basis-point conversion and the bp scalar type (I-17: every hashed runtime scalar is an
int in basis points, 0..10000; no float enters authoritative state). Shared by
belief/memory/character/epistemic — generation-time confidence/strength/salience are
computed as 0..1 floats per the architecture's own formulas (§6.4, §8.2) and stored as bp
at the model boundary.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import Field

BP_MAX = 10000

Bp = Annotated[int, Field(ge=0, le=BP_MAX)]
"""I-17's scalar: an int in `[0, BP_MAX]`, range-checked by pydantic at construction.

The annotation is the enforcement point, and it is deliberately on the MODELS rather than
in the fold: `apply_*` copies a payload's post-value with `model_copy(update=...)`, which
skips validation by design (I-22 — the fold applies, it does not re-derive). So a bp value
has to be rejected where it enters the system — constructing the `SessionEvent` that
carries it, or constructing the state directly — not clamped after the fact. Clamping is
what let a 999999 composure land as 10000 and a -5000 trust land as -5000 unnoticed.
"""


def bp(fraction: float) -> int:
    """0..1 float -> clamped 0..10000 int basis points."""
    return max(0, min(BP_MAX, round(fraction * BP_MAX)))


def frac(basis_points: int) -> float:
    return basis_points / BP_MAX
