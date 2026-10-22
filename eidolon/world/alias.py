"""Alias and TimeAnchor tables (§4.2, §4.7 notes): name <-> ID and tick <-> phrase resolution.

Grounding names to IDs is a parser-time concern (Phase 5); this module only holds the
lookup tables and the deterministic tick->phrase renderer so a case can carry them (I-8:
"every actor/location/object slot is an ID... resolved against the case Alias table").
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .frozen import Frozen, FrozenDict


class Alias(BaseModel):
    """Maps every surface name/nickname for an entity to its canonical ID."""
    model_config = ConfigDict(frozen=True)

    names: Frozen[str, str] = FrozenDict()  # surface form (lowercased) -> entity id

    def resolve(self, name: str) -> str | None:
        return self.names.get(name.strip().lower())


class TimeAnchor(BaseModel):
    """A named wall-clock moment used only for rendering (§4.2 `epoch_wallclock`)."""
    model_config = ConfigDict(frozen=True)

    epoch_wallclock: str  # e.g. "2026-09-02T21:00"


def render_time(t: int, granularity: int = 0) -> str:
    """Deterministic tick -> phrase (§4.2). `t` is minutes since epoch; `granularity` widens
    the rendering to a vague window (e.g. "around ten") instead of a sharp clock time."""
    def clock(minute: int) -> str:
        hh, mm = divmod(minute, 60)
        return f"{hh % 24:02d}:{mm:02d}"

    if granularity <= 0:
        return clock(t)
    lo, hi = t - granularity, t + granularity
    return f"between {clock(lo)} and {clock(hi)}"
