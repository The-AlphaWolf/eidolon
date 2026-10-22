"""`eidolon.world` — the canonical world model (Phase 1, docs/EIDOLON-ARCHITECTURE.md Part II).

Deterministic, authoritative, no LLM involved (§2.1). Every other subsystem (`minds/`,
`play/`, `gen/`, `solve/`) is built on top of this package and depends on it one-way
(§23.1: `world <- minds <- play <- api`).
"""
from .case import Case
from .facts import FactIndex
from .feasibility import Claim, Feasibility, feasible
from .physics import Implication, Violation, check_physics
from .propositions import Fact, Proposition
from .state import CaseLog, WorldState, death_ticks, presence, world_at
from .timeline import could_observe, could_reach, events_at, possible_window, who_was_at

__all__ = [
    "Case", "FactIndex", "Claim", "Feasibility", "feasible",
    "Implication", "Violation", "check_physics",
    "Fact", "Proposition", "CaseLog", "WorldState", "presence", "world_at",
    "death_ticks",
    # §4.10 timeline query API (the seventh entry point, `information_reach`, is
    # `minds.KnowledgeStore.information_reach` — see `world/timeline.py`).
    "who_was_at", "events_at", "could_reach", "could_observe", "possible_window",
]
