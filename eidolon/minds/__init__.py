"""`eidolon.minds` — character cognition (Phase 2, docs/EIDOLON-ARCHITECTURE.md Part III).

Truth (`eidolon.world`) stays authoritative; everything here is per-character access,
belief and memory built ON TOP of it (§23.1: `world <- minds <- play <- api`, one-way).
Nothing in this package mutates a `Case` or a `FactIndex.truth_value` result.
"""
from .admissibility import admissibility_level, apparent_admissibility
from .belief import Belief, BeliefFormationResult, BeliefStore, form_beliefs, trust_between
from .character import (
    CharacterState, DetectiveModel, Emotion, Personality, VoiceSpec, initial_character_state,
)
from .epistemic import EpistemicState, RecallRecord, Revision, current_belief_confidence, current_memory_strength
from .events import MindsEvent
from .fold import apply_character, apply_epistemic, build_memory_recall_event
from .knowledge import KnowledgeEntry, KnowledgeStore, propagate_knowledge, with_overlay
from .memory import CueSet, Distortion, Memory, RetrievalResult, encode_memories, retrieve
from .provenance import AdmissibilityLevel, Provenance
from .soundness import Violation, check_knowledge_soundness

__all__ = [
    "admissibility_level", "apparent_admissibility",
    "Belief", "BeliefFormationResult", "BeliefStore", "form_beliefs", "trust_between",
    "CharacterState", "DetectiveModel", "Emotion", "Personality", "VoiceSpec", "initial_character_state",
    "EpistemicState", "RecallRecord", "Revision", "current_belief_confidence", "current_memory_strength",
    "MindsEvent",
    "apply_character", "apply_epistemic", "build_memory_recall_event",
    "KnowledgeEntry", "KnowledgeStore", "propagate_knowledge", "with_overlay",
    "CueSet", "Distortion", "Memory", "RetrievalResult", "encode_memories", "retrieve",
    "AdmissibilityLevel", "Provenance",
    "Violation", "check_knowledge_soundness",
]
