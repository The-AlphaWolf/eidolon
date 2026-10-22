"""`DecisionContext`: the read-only bundle of stores every Phase 4 function needs to look
things up in. Not a new store — every field is a store some earlier phase (or this one)
already owns; this is only a named tuple of references, replacing what would otherwise be an
8-argument parameter list repeated across `weight.py`/`peel.py`/`strategy.py`/`validator.py`.

Building one is cheap (`CollusionGraph.build` is the only derived field) and it is never
mutated — a new turn's context is built fresh from the current fold, mirroring how
`CharacterView` (§12.1 stage 4) is described as built fresh per turn.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..evidence.discovery import DiscoveryState
from ..evidence.model import EvidenceStore
from ..minds.belief import BeliefStore
from ..minds.epistemic import EpistemicState
from ..minds.knowledge import KnowledgeStore, with_overlay
from ..world.case import Case
from .admissibility import CollusionGraph
from .claims import StatementStore
from .secrets import SecretStore


@dataclass(frozen=True)
class DecisionContext:
    case: Case
    knowledge: KnowledgeStore          # sealed store; use `.knowledge_with_overlay` for I-27 chains
    beliefs: BeliefStore
    secrets: SecretStore
    evidence: EvidenceStore
    statements: StatementStore
    epistemic: EpistemicState
    discovery: DiscoveryState
    accounts: tuple[str, ...] = ()
    """V-3's declared pool of DELIVERABLE account tokens (`CasePackage.accounts`, filtered by I-54). A runtime
    context leaves it empty: a token is never presentable there (I-51)."""

    @property
    def collusion(self) -> CollusionGraph:
        return CollusionGraph.build(self.secrets, self.case.rels)

    @property
    def knowledge_with_overlay(self) -> KnowledgeStore:
        """I-27/AC-1's admissibility walk must resolve chains through runtime
        `InvestigationTold` entries too (`knowledge.with_overlay`'s own docstring: "a chain
        that passes through a detective-supplied entry simply dead-ends... instead of the L0
        that poisons it"), so every admissibility call in this layer reads this view, never
        the bare sealed store."""
        return with_overlay(self.knowledge, self.epistemic)
