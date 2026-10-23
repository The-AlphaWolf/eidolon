"""The player hypothesis board (§16.1): player-authored propositions, evaluated by the
engine ONLY against material the player actually holds — never against truth. "The player is
the reasoner; the engine is the bookkeeper" (§16.1's own line).

`Lied`/`Planted` are the two hypothesis-only predicates §4.7 explicitly excludes from the
closed runtime `Proposition` schema ("Hypothesis-only predicates (player board; never
claims, never facts)") — they belong here, in the one layer that is allowed to model player
speculation about the game rather than the game's own facts.
"""
from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from ..evidence.contradiction import contradiction, evidence_implication_contradicts, evidence_vs_evidence
from ..evidence.discovery import DiscoveryState, held_material, unlocked_implications, unlocked_view
from ..evidence.ids import StatementId
from ..evidence.model import EvidenceStore
from ..world.ids import ActorId, EvidenceId
from ..world.propositions import Proposition, entities
from .claims import StatementStore
from .ids import HypothesisId
from .secrets import Ref

# "withdrawn" (Phase 8) is the player's removal: the entry stays in the log and in state, leaves the board, and is terminal —
# `evaluate_hypothesis` never produces it and the store refuses any edit of a withdrawn entry.
HypothesisStatus = Literal["open", "tension", "contradicted", "corroborated", "withdrawn"]


class Lied(BaseModel):
    """Player speculation: "I think `actor` lied in `statement`." Never a claim, never a fact
    — the engine can only tell the player whether their OTHER material is in tension with it."""
    model_config = ConfigDict(frozen=True)

    kind: Literal["Lied"] = "Lied"
    actor: ActorId
    statement: StatementId


class Planted(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["Planted"] = "Planted"
    evidence: EvidenceId


HypothesisProposition = Union[Proposition, Lied, Planted]


class Hypothesis(BaseModel):
    """§16.1. `support`/`against` are refs (`EvidenceId | StatementId`) into the player's OWN
    material; `player_confidence` is set by the player and never touched by
    `evaluate_hypothesis`."""
    model_config = ConfigDict(frozen=True)

    id: HypothesisId
    propositions: tuple[HypothesisProposition, ...] = Field(default_factory=tuple)
    player_confidence: float = 0.5
    support: tuple[Ref, ...] = ()
    against: tuple[Ref, ...] = ()
    status: HypothesisStatus = "open"
    created_turn: int = 0
    updated_turn: int = 0


def _shares_entity(prop: Proposition, other: Proposition) -> bool:
    a = set().union(*entities(prop))
    b = set().union(*entities(other))
    return bool(a & b)


def _evaluate_plain_proposition(prop: Proposition, evidence: EvidenceStore, statements: StatementStore,
                                 discovery: DiscoveryState) -> tuple[set[Ref], set[Ref]]:
    """Only UNLOCKED implications count (§5.2, H8-B1), and a contradiction needs `strength >= 0.5` (§13.2): a weaker one
    licenses no tension, and is not "consistent with" either."""
    support: set[Ref] = set()
    against: set[Ref] = set()
    known = held_material(discovery)
    for eid in discovery.known_evidence:
        ev = evidence.get(eid)
        if ev is None:
            continue
        for imp in unlocked_implications(ev, known):
            if not _shares_entity(imp.proposition, prop):
                continue
            if contradiction(imp.proposition, prop) is None:
                support.add(eid)
            elif evidence_implication_contradicts(imp, prop, imp_id=eid, other_id="hypothesis") is not None:
                against.add(eid)
    for sid in discovery.known_statements:
        st = statements.get(sid)
        if st is None:
            continue
        for c in st.claims:
            if not _shares_entity(c.proposition, prop):
                continue
            if contradiction(c.proposition, prop) is not None:
                against.add(sid)
            else:
                support.add(sid)
    return support, against


def _evaluate_lied(hp: Lied, evidence: EvidenceStore, statements: StatementStore,
                    discovery: DiscoveryState) -> tuple[set[Ref], set[Ref]]:
    """A `Lied(actor, statement)` hypothesis is CORROBORATED by the player's own material
    when the named statement's claims are in tension with something else the player holds
    (a discovered contradiction, §13.4's own "tension" framing) — the engine still never says
    which side is true."""
    statement = statements.get(hp.statement)
    if statement is None or statement.speaker != hp.actor:
        return set(), set()
    support: set[Ref] = set()
    known = held_material(discovery)
    for eid in discovery.known_evidence:
        ev = evidence.get(eid)
        if ev is None:
            continue
        for imp in unlocked_implications(ev, known):
            if any(contradiction(imp.proposition, c.proposition) is not None for c in statement.claims):
                support.add(eid)
    for sid in discovery.known_statements:
        other = statements.get(sid)
        if other is None or other.id == statement.id:
            continue
        if any(contradiction(oc.proposition, c.proposition) is not None
               for oc in other.claims for c in statement.claims):
            support.add(sid)
    return support, set()  # never "against": the player cannot disprove a lie accusation, only fail to support it


def _evaluate_planted(hp: Planted, evidence: EvidenceStore, discovery: DiscoveryState) -> tuple[set[Ref], set[Ref]]:
    """A `Planted(evidence)` hypothesis is corroborated by a discovered tension between this
    item and another authentic-looking one the player holds (§13.1's "planted-evidence
    tension" row) — never by the engine's own `authentic` flag, which the player never sees."""
    target = evidence.get(hp.evidence)
    if target is None:
        return set(), set()
    target = unlocked_view(target, discovery)
    support: set[Ref] = set()
    for eid in discovery.known_evidence:
        if eid == hp.evidence:
            continue
        other = evidence.get(eid)
        if other is not None and evidence_vs_evidence(target, unlocked_view(other, discovery)):
            support.add(eid)
    return support, set()


def evaluate_hypothesis(hypothesis: Hypothesis, evidence: EvidenceStore, statements: StatementStore,
                         discovery: DiscoveryState, turn: int) -> Hypothesis:
    """Recomputes `support`/`against`/`status` from the player's CURRENT material — pure and
    idempotent; calling it again with the same material returns an equal `Hypothesis` (the
    engine "never sets" `player_confidence`, and this never mutates it either)."""
    support: set[Ref] = set()
    against: set[Ref] = set()
    for prop in hypothesis.propositions:
        if isinstance(prop, Lied):
            s, a = _evaluate_lied(prop, evidence, statements, discovery)
        elif isinstance(prop, Planted):
            s, a = _evaluate_planted(prop, evidence, discovery)
        else:
            s, a = _evaluate_plain_proposition(prop, evidence, statements, discovery)
        support |= s
        against |= a

    if against and support:
        status: HypothesisStatus = "tension"
    elif against:
        status = "contradicted"
    elif support:
        status = "corroborated"
    else:
        status = "open"

    return hypothesis.model_copy(update={
        "support": tuple(sorted(support)), "against": tuple(sorted(against)),
        "status": status, "updated_turn": turn,
    })
