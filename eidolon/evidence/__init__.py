"""`eidolon.evidence` — the evidence/discovery layer (Phase 3, docs/EIDOLON-ARCHITECTURE.md
§5, §13.2, §17, §19.4).

Built on top of `eidolon.world` (Phase 1) and `eidolon.minds` (Phase 2); never mutates
either (§23.1: `world <- minds <- evidence <- ...`, one-way). Evidence is never an
independent source of truth — `grounding.py` is the boundary that enforces it.
"""
from .contradiction import (
    Contradiction, ContradictionKind, contradiction, corroborates,
    evidence_implication_contradicts, evidence_vs_evidence,
)
from .discovery import (
    Discovery, DiscoveryState, PlayerEvidenceView, ReachabilityReport,
    apply_discovery, can_discover, check_discovery_state, project_for_player, reachability,
    red_herring_refuter_reachable, testimony_strongly_retrievable, uncued_load_bearing,
    unlocked_implications, unreachable_load_bearing,
)
from .grounding import (
    check_creation_grounding, check_evidence_grounding, check_known_to_soundness,
    check_reference_integrity, check_temporal_grounding, check_world_truth,
    established_interval, to_physics_tuples,
)
from .ids import HypothesisTemplateId, StatementId
from .model import (
    DiscoverySpec, Evidence, EvidenceKind, EvidenceStore, Implication, Prereq,
    RedHerringSpec, RequirementId, combined_strength,
)

__all__ = [
    "Contradiction", "ContradictionKind", "contradiction", "corroborates",
    "evidence_implication_contradicts", "evidence_vs_evidence",
    "Discovery", "DiscoveryState", "PlayerEvidenceView", "ReachabilityReport",
    "apply_discovery", "can_discover", "check_discovery_state", "project_for_player", "reachability",
    "red_herring_refuter_reachable", "testimony_strongly_retrievable", "uncued_load_bearing",
    "unlocked_implications", "unreachable_load_bearing",
    "check_creation_grounding", "check_evidence_grounding", "check_known_to_soundness",
    "check_reference_integrity", "check_temporal_grounding", "check_world_truth",
    "established_interval", "to_physics_tuples",
    "HypothesisTemplateId", "StatementId",
    "DiscoverySpec", "Evidence", "EvidenceKind", "EvidenceStore", "Implication", "Prereq",
    "RedHerringSpec", "RequirementId", "combined_strength",
]
