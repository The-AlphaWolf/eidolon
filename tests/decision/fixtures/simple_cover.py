"""A minimal, self-contained cover story built on Phase 3's own `vance_v03_evidence()`
fixture (`tests/evidence/fixtures/vance_evidence.py`) — read, never edited (Phase 1/3 own
those fixtures per CLAUDE.md's house rules).

Mirrors §13.3's worked scenario structurally (a fingerprint whose interval only tightens once
a washing/cleaning statement is heard) using the actual `E_trace`/`S_clean` shapes Phase 3
shipped, rather than re-authoring a new evidence set: `E_trace`'s single implication has
`requires=("S_clean",)`, so presenting it before `S_clean` is known does not unlock it at all
(weight 0) and presenting it after does (§11.2's "unlocked(claim, player_material)" gate) —
which is exactly what T-8 (I-33) needs to exercise.
"""
from __future__ import annotations

from eidolon.decision.claims import Claim, Statement, StatementStore
from eidolon.decision.context import DecisionContext
from eidolon.decision.secrets import CoverLayer, CoverStory, Secret, SecretStore, Stakes
from eidolon.evidence.discovery import DiscoveryState
from eidolon.evidence.model import EvidenceStore
from eidolon.minds.belief import BeliefStore
from eidolon.minds.epistemic import EpistemicState
from eidolon.minds.knowledge import KnowledgeStore
from eidolon.minds.knowledge import KnowledgeEntry
from eidolon.minds.provenance import Witnessed
from eidolon.world.propositions import At, Did, DidNot
from tests.evidence.fixtures.vance_evidence import vance_v03_evidence

DAVID = "David"
ELENA = "Elena"


def build() -> tuple[DecisionContext, Secret]:
    case, evidence, statement_intervals = vance_v03_evidence()
    evidence_store = EvidenceStore(evidence)

    denial = Claim(id="C_L0_deny", proposition=DidNot(actor=DAVID, action="touch", object="Glass1",
                                                        interval=(0, 120)),
                    sincerity="deceptive", source="plan")
    concession = Claim(id="C_L1_concede", proposition=Did(actor=DAVID, action="touch", object="Glass1",
                                                            location="Study", interval=(60, 61)),
                        sincerity="deceptive", source="plan")
    layers = (
        CoverLayer(index=0, claims=(denial,), resolve=6000, breaker_sets=(frozenset({"E_trace"}),)),
        CoverLayer(index=1, claims=(concession,), resolve=10000, terminal="stonewall"),
    )
    secret = Secret(id="S_murder_david", owner=DAVID, kind="murder", protected=(denial.proposition,),
                     stakes=Stakes(legal=1.0), cover=CoverStory(layers=layers))

    # Elena's own statement that she cleaned Glass1 at [12,13) — real `KnowledgeEntry` +
    # `Statement`, not just the bare `statement_intervals` placeholder Phase 3 used (its own
    # docstring: "the full Statement model is Phase 4"), so `cover_consistency.py`'s
    # candidate-pool enumeration can actually find and combine it with `E_trace`.
    k_clean = KnowledgeEntry(id="K_clean", character=ELENA,
                              proposition=At(actor=ELENA, location="Study", interval=(12, 13)),
                              source=Witnessed(event_id="clean", modality="sight", quality=0.9),
                              acquired_at=12, reliability=0.9, is_true=True)
    knowledge = KnowledgeStore([k_clean])
    s_clean_claim = Claim(id="c_clean", statement="S_clean", proposition=k_clean.proposition,
                           sincerity="truthful", source="plan", grounding=("K_clean",))
    statements = StatementStore([Statement(id="S_clean", turn=0, speaker=ELENA,
                                            text="I cleaned that glass just after eleven.",
                                            claims=(s_clean_claim,), act="TRUTH")])

    ctx = DecisionContext(
        case=case, knowledge=knowledge, beliefs=BeliefStore(),
        secrets=SecretStore([secret]), evidence=evidence_store, statements=statements,
        epistemic=EpistemicState(), discovery=DiscoveryState(),
    )
    return ctx, secret


def with_discovery(ctx: DecisionContext, *, known_evidence: frozenset[str] = frozenset(),
                    known_statements: frozenset[str] = frozenset()) -> DecisionContext:
    return DecisionContext(case=ctx.case, knowledge=ctx.knowledge, beliefs=ctx.beliefs,
                            secrets=ctx.secrets, evidence=ctx.evidence, statements=ctx.statements,
                            epistemic=ctx.epistemic,
                            discovery=ctx.discovery.model_copy(update={
                                "known_evidence": ctx.discovery.known_evidence | known_evidence,
                                "known_statements": ctx.discovery.known_statements | known_statements,
                            }))
