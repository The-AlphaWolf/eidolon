"""§29.1/§29.2's "Vance House" walkthrough, built on the real `vance_v02_negative()` fixture
(`tests/world/fixtures/vance.py`, read-only per CLAUDE.md's house rules) plus its own base
evidence (E1, E4). `cases/vance_v02_negative.json` is explicitly the case the walkthrough's
turns illustrate (§29.1: "every turn in §29.2 remains a correct illustration of the
pipeline" even though the CASE itself is a negative solvability fixture) — David's murder
weapon here is the bookend (`objects=("bookend",)` on the `attack` event), matching §29.1's
prose exactly, unlike the production `vance_v03` (Glass1/fingerprint).

Covers David (murder secret, 3 layers matching §29.1's authored L0-L2), Elena (a weak,
distorted sighting plus a strong, corroborated kitchen-presence belief) and Margaret (an
affair secret, one layer, resolved by `E6`) using DIRECTLY-CONSTRUCTED `KnowledgeEntry`/
`Belief`/`Memory` objects with the numbers §29.1 states (reliability, confidence, retrieval
band) rather than running the full generation pipeline — the golden-trace test only needs
the DECISION-LEVEL outcome at each turn (act chosen, peel timing, pressure/meta handling),
never the exact prose (§21.2: language generation is deliberately kept out of decision
logic), so hand-built epistemic objects landing in the same bands generation would have
produced are enough.
"""
from __future__ import annotations

from eidolon.decision.claims import Claim, StatementStore
from eidolon.decision.events import DecisionState
from eidolon.decision.secrets import (
    CoverLayer, CoverStory, EvidenceResponse, Secret, SecretStore, Slip, Stakes,
)
from eidolon.decision.turn import GameState
from eidolon.evidence.discovery import DiscoveryState
from eidolon.evidence.model import DiscoverySpec, Evidence, EvidenceStore, Implication
from eidolon.minds.belief import Belief, BeliefStore
from eidolon.minds.character import Personality, initial_character_state
from eidolon.minds.epistemic import EpistemicState
from eidolon.minds.knowledge import KnowledgeEntry, KnowledgeStore
from eidolon.minds.memory import CueSet, Distortion, Memory
from eidolon.minds.provenance import Absence, Witnessed
from eidolon.minds.scale import bp
from eidolon.world.propositions import At, Did, DidNot, NotAt, ObjectState, Saw
from tests.world.fixtures.vance import vance_v02_negative

DAVID, ELENA, MARGARET, ROBERT = "David", "Elena", "Margaret", "Robert"


def _personality(**kw) -> Personality:
    base = dict(composure_base=0.45, volatility=0.3, deference=0.5, guile=0.4,
                talkativeness=0.4, self_preservation=0.5)
    base.update(kw)
    return Personality(**base)


def build_initial_state() -> GameState:
    case, _base_evidence = vance_v02_negative()

    # --- David's murder secret (§29.1 "David's cover") ---------------------------------
    l0_deny = Claim(id="d_c0_kitchen", proposition=DidNot(actor=DAVID, action="Use", object="Glass1",
                                                            interval=(0, 120)),
                     sincerity="deceptive", source="plan")
    l0_deny2 = Claim(id="d_c0_lib", proposition=At(actor=DAVID, location="Library", interval=(5, 120)),
                      sincerity="deceptive", source="plan")
    l1_concede = Claim(id="d_c1_water", proposition=At(actor=DAVID, location="Kitchen", interval=(30, 35)),
                        sincerity="deceptive", source="plan")
    l2_concede = Claim(id="d_c2_ill", proposition=At(actor=DAVID, location="Kitchen", interval=(72, 75)),
                        sincerity="deceptive", source="plan")
    l2_deny_argument = Claim(id="d_c2_noarg", proposition=DidNot(actor=DAVID, action="Speak", target_actor="Harold",
                                                                   interval=(68, 70)),
                              sincerity="deceptive", source="plan")
    slip = Slip(id="slip_bookend", reveals=ObjectState(object="bookend", attr="position", value="floor_by_desk",
                                                          interval=(71, 120)),
                trigger_topic="study", min_weight_fraction=5000,
                excuse=EvidenceResponse(evidence="slip:slip_bookend", layer=2, act="REINTERPRET"))
    david_secret = Secret(
        id="S_murder_david", owner=DAVID, kind="murder",
        protected=(l0_deny.proposition, l0_deny2.proposition),
        stakes=Stakes(legal=1.0), slips=(slip,),
        evidence_responses=(EvidenceResponse(evidence="E1", layer=0, act="DENY_EVIDENCE"),
                             EvidenceResponse(evidence="wash@Elena", layer=0, act="DENY_EVIDENCE"),
                             EvidenceResponse(evidence="S_elena_kitchen", layer=1, act="REINTERPRET")),
        cover=CoverStory(layers=(
            CoverLayer(index=0, claims=(l0_deny, l0_deny2), resolve=6000,
                       breaker_sets=(frozenset({"E1", "wash@Elena"}),)),
            CoverLayer(index=1, claims=(l1_concede,), resolve=6000,
                       breaker_sets=(frozenset({"S_elena_kitchen"}),)),
            CoverLayer(index=2, claims=(l2_concede, l2_deny_argument), resolve=8500),
            CoverLayer(index=3, claims=(), resolve=10000, terminal="stonewall"),
        )),
    )

    # --- Elena: a weak, distorted sighting + a strong kitchen-presence belief ----------
    # `subject="figure"`/`identified=False` throughout: even her "I took it for Mr. Kessler"
    # remark hedges (§29.2 turn 3's own validation note keeps BOTH her claims
    # `identified=False`), and it is what keeps the retrieved content genuinely
    # unidentified — §8.4's own rule for a `weak` band ("no identity claims").
    figure_prop = Saw(observer=ELENA, subject="figure", location="Hall", interval=(0, 120), identified=False)
    k_figure = KnowledgeEntry(id="K_figure", character=ELENA, proposition=figure_prop,
                               source=Witnessed(event_id="see:figure", modality="sight", quality=0.5),
                               acquired_at=95, reliability=0.5, is_true=True)
    b_figure = Belief(id="B_figure", character=ELENA, proposition=figure_prop, confidence_0=bp(0.5),
                       grounds=("K_figure",), formed_at=95, is_true=True)
    m_figure = Memory(id="M_figure", character=ELENA, kind="episodic", content=("B_figure",),
                       episode=None, encoded_at=95, salience=bp(0.5), strength_0=bp(0.5),
                       cues=CueSet(entities=(), location="Hall", time_bucket="b3", topic_tags=("saw",)),
                       distortions=(Distortion(field="interval", true_value=[95, 96], recalled_value=[60, 61],
                                                 cause="time_compression"),))

    # Elena's continuous kitchen presence licenses an ABSENCE-derived claim about DAVID
    # (§4.8.7/I-34: `Absence` grounds `NotAt` only) — "nobody came in" while she was there,
    # which is what actually CONTRADICTS David's L1 water-glass claim (a same-actor,
    # same-location, overlapping-interval `At`/`NotAt` pair, §13.2's negation rule).
    # Robert's independent, non-colluding sighting corroborates the SAME proposition
    # (I-37's corroboration bump, tested in isolation in `test_admissibility.py`) — a
    # documented simplification of I-44's full tick-level presence-fixing derivation
    # (Phase 1's own perception-model machinery), sufficient for this test's DECISION-level
    # purpose (does the weight cross `resolve` and peel).
    not_at_prop = NotAt(actor=DAVID, location="Kitchen", interval=(5, 65))
    k_kitchen = KnowledgeEntry(id="K_kitchen_elena", character=ELENA, proposition=not_at_prop,
                                source=Absence(basis="continuous", coverage=1.0, entrances_covered=True),
                                acquired_at=5, reliability=0.9, is_true=True)
    k_kitchen_robert = KnowledgeEntry(id="K_kitchen_robert", character=ROBERT, proposition=not_at_prop,
                                       source=Witnessed(event_id="glow:robert", modality="sight", quality=0.6),
                                       acquired_at=54, reliability=0.6, is_true=True)

    # --- Margaret: affair secret, resolved by E6 (§29.1 turn 9) -------------------------
    m_deny = Claim(id="m_c0_room", proposition=At(actor=MARGARET, location="Room", interval=(30, 90)),
                    sincerity="deceptive", source="plan")
    m_concede = Claim(id="m_c1_gazebo", proposition=At(actor=MARGARET, location="Gazebo", interval=(55, 80)),
                       sincerity="truthful", source="plan")
    margaret_secret = Secret(
        id="S_affair_margaret", owner=MARGARET, kind="affair", protected=(m_deny.proposition,),
        stakes=Stakes(social=0.6, legal=0.0),
        evidence_responses=(EvidenceResponse(evidence="E6", layer=0, act="DENY_EVIDENCE"),),
        cover=CoverStory(layers=(
            CoverLayer(index=0, claims=(m_deny,), resolve=5000, breaker_sets=(frozenset({"E6"}),)),
            CoverLayer(index=1, claims=(m_concede,), resolve=10000, terminal="stonewall"),
        )),
    )

    evidence = EvidenceStore([
        Evidence(id="E1", kind="Fingerprint", object="Glass1", reliability=0.9,
                 implications=(Implication(proposition=Did(actor=DAVID, action="Use", object="Glass1",
                                                            location="Kitchen", interval=(20, 120)),
                                            strength=0.9, requires=("wash@Elena",)),),
                 discovery=DiscoverySpec(action="Dust", at="Kitchen", cue="Kitchen")),
        Evidence(id="E4", kind="Timepiece",
                 implications=(Implication(proposition=Did(actor="Harold", action="Die", interval=(71, 72),
                                                            location="Study"), created_at=(71, 72)),),
                 discovery=DiscoverySpec(action="Look", at="Study")),
        Evidence(id="E6", kind="Document",
                 implications=(Implication(proposition=At(actor=MARGARET, location="Gazebo", interval=(55, 80)),
                                            strength=0.9),),
                 discovery=DiscoverySpec(action="Open", at="Room")),
    ])

    characters = {
        DAVID: initial_character_state(DAVID, _personality(guile=0.5)),
        ELENA: initial_character_state(ELENA, _personality(deference=0.7, guile=0.1)),
        MARGARET: initial_character_state(MARGARET, _personality(composure_base=0.5, guile=0.2)),
    }

    return GameState(
        case=case, knowledge=KnowledgeStore([k_figure, k_kitchen, k_kitchen_robert]),
        beliefs=BeliefStore([b_figure]),
        memories={ELENA: (m_figure,), DAVID: (), MARGARET: ()},
        secrets=SecretStore([david_secret, margaret_secret]), evidence=evidence,
        characters=characters, epistemic=EpistemicState(), discovery=DiscoveryState(),
        decision=DecisionState(statements=StatementStore()),
        seed=1, turn_counter=0,
    )


def elena_kitchen_statement_claim() -> Claim:
    """Exposed so the golden-trace test can commit Elena's kitchen statement directly
    (§29.2 turn 6's own note: "obtained off-screen at a prior turn")."""
    return Claim(id="c_elena_kitchen", statement="S_elena_kitchen",
                 proposition=NotAt(actor=DAVID, location="Kitchen", interval=(5, 65)),
                 sincerity="truthful", source="plan", grounding=("K_kitchen_elena",))
