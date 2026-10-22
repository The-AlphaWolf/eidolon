"""§16.1: the player hypothesis board is evaluated only against player-held material, never
truth."""
from __future__ import annotations

from eidolon.decision.claims import Claim, Statement, StatementStore
from eidolon.decision.hypotheses import Hypothesis, Lied, evaluate_hypothesis
from eidolon.evidence.discovery import DiscoveryState
from eidolon.evidence.model import DiscoverySpec, Evidence, EvidenceStore, Implication
from eidolon.world.propositions import At, Did, DidNot


def test_open_hypothesis_with_no_material():
    hyp = Hypothesis(id="H1", propositions=(At(actor="David", location="Study", interval=(10, 20)),))
    result = evaluate_hypothesis(hyp, EvidenceStore(), StatementStore(), DiscoveryState(), turn=1)
    assert result.status == "open"
    assert result.support == () and result.against == ()


def test_corroborated_when_discovered_evidence_agrees():
    prop = At(actor="David", location="Study", interval=(10, 20))
    ev = Evidence(id="E1", kind="Witness", implications=(Implication(proposition=prop),),
                  discovery=DiscoverySpec(action="Ask", at="Study"))
    store = EvidenceStore([ev])
    discovery = DiscoveryState(known_evidence=frozenset({"E1"}))
    hyp = Hypothesis(id="H1", propositions=(prop,))
    result = evaluate_hypothesis(hyp, store, StatementStore(), discovery, turn=2)
    assert result.status == "corroborated"
    assert result.support == ("E1",)


def test_contradicted_when_discovered_evidence_disagrees():
    hyp_prop = At(actor="David", location="Study", interval=(10, 20))
    contradicting = At(actor="David", location="Kitchen", interval=(10, 20))
    ev = Evidence(id="E1", kind="Witness", implications=(Implication(proposition=contradicting),),
                  discovery=DiscoverySpec(action="Ask", at="Kitchen"))
    store = EvidenceStore([ev])
    discovery = DiscoveryState(known_evidence=frozenset({"E1"}))
    hyp = Hypothesis(id="H1", propositions=(hyp_prop,))
    result = evaluate_hypothesis(hyp, store, StatementStore(), discovery, turn=2)
    assert result.status == "contradicted"


def test_lied_hypothesis_supported_by_a_visible_tension():
    claim = Claim(id="c1", proposition=DidNot(actor="David", action="touch", object="Glass1", interval=(0, 120)),
                  sincerity="deceptive", source="plan")
    stmt = Statement(id="S1", turn=1, speaker="David", text="I never touched it.", claims=(claim,), act="LIE")
    statements = StatementStore([stmt])
    ev = Evidence(id="E1", kind="Fingerprint", object="Glass1",
                  implications=(Implication(proposition=Did(actor="David", action="touch", object="Glass1",
                                                              interval=(0, 120))),),
                  discovery=DiscoverySpec(action="Dust", at="Glass1"))
    evidence = EvidenceStore([ev])
    discovery = DiscoveryState(known_evidence=frozenset({"E1"}), known_statements=frozenset({"S1"}))
    hyp = Hypothesis(id="H1", propositions=(Lied(actor="David", statement="S1"),))
    result = evaluate_hypothesis(hyp, evidence, statements, discovery, turn=3)
    assert result.status == "corroborated"
    assert result.support == ("E1",)


# ---- H8-B1 (Phase 8 hostile review): the board reads only what the player has UNLOCKED (§5.2, §16.1) -------------------------
def _item(eid, prop, *, requires=(), strength=1.0):
    return Evidence(id=eid, kind="Witness", implications=(Implication(proposition=prop, requires=requires, strength=strength),),
                    discovery=DiscoverySpec(action="Look", at="Study"))


def _board(items, discovery, *propositions):
    hyp = Hypothesis(id="H1", propositions=propositions)
    return evaluate_hypothesis(hyp, EvidenceStore(items), StatementStore(), discovery, turn=2)


STUDY = At(actor="David", location="Study", interval=(10, 20))
KITCHEN = At(actor="David", location="Kitchen", interval=(10, 20))


def test_a_locked_implication_is_neither_for_nor_against_a_plain_theory_until_its_requirement_is_held():
    held = DiscoveryState(known_evidence=frozenset({"E1"}))
    for token, field in (("clean@Elena", "known_accounts"), ("S9", "known_statements"), ("E9", "known_evidence")):
        locked = _item("E1", KITCHEN, requires=(token,))
        assert _board([locked], held, STUDY).status == "open"                      # held, but its implication is not the player's yet
        board = _board([locked], held.model_copy(update={field: getattr(held, field) | {token}}), STUDY)
        assert (board.status, board.against) == ("contradicted", ("E1",))          # the requirement held: it speaks
    agreeing = _item("E2", STUDY, requires=("E9",))
    assert _board([agreeing], DiscoveryState(known_evidence=frozenset({"E2"})), STUDY).status == "open"
    assert _board([agreeing], DiscoveryState(known_evidence=frozenset({"E2", "E9"})), STUDY).support == ("E2",)


def test_a_contradiction_weaker_than_half_licenses_no_tension_and_is_not_support_either():
    """§13.2: `strength >= 0.5` is the floor `evidence_implication_contradicts` applies; the board must apply the same."""
    d = DiscoveryState(known_evidence=frozenset({"E1"}))
    weak, edge = _item("E1", KITCHEN, strength=0.49), _item("E1", KITCHEN, strength=0.5)
    assert _board([weak], d, STUDY).status == "open"
    assert _board([edge], d, STUDY).status == "contradicted"
    assert _board([_item("E1", STUDY, strength=0.1)], d, STUDY).status == "corroborated"      # agreement needs no floor


def test_a_lied_theory_is_not_corroborated_by_a_locked_implication():
    claim = Claim(id="c1", proposition=DidNot(actor="David", action="touch", object="Glass1", interval=(0, 120)),
                  sincerity="deceptive", source="plan")
    statements = StatementStore([Statement(id="S1", turn=1, speaker="David", text="I never touched it.", claims=(claim,), act="LIE")])
    ev = _item("E1", Did(actor="David", action="touch", object="Glass1", interval=(0, 120)), requires=("clean@Elena",))
    hyp = Hypothesis(id="H1", propositions=(Lied(actor="David", statement="S1"),))
    base = DiscoveryState(known_evidence=frozenset({"E1"}), known_statements=frozenset({"S1"}))
    assert evaluate_hypothesis(hyp, EvidenceStore([ev]), statements, base, turn=3).status == "open"
    heard = base.model_copy(update={"known_accounts": frozenset({"clean@Elena"})})
    assert evaluate_hypothesis(hyp, EvidenceStore([ev]), statements, heard, turn=3).support == ("E1",)


def test_a_planted_theory_is_not_corroborated_by_a_tension_that_rests_on_a_locked_implication():
    """The theory's own item (`target`) and the item it is compared with (`other`) are each read through the unlock: the
    locked implication may be on either side of the pair, whichever of the two the player calls planted."""
    from eidolon.decision.hypotheses import Planted
    both = DiscoveryState(known_evidence=frozenset({"E1", "E2"}))
    heard = both.model_copy(update={"known_accounts": frozenset({"clean@Elena"})})
    for locked_id in ("E1", "E2"):
        items = [_item("E1", STUDY, requires=("clean@Elena",) if locked_id == "E1" else ()),
                 _item("E2", KITCHEN, requires=("clean@Elena",) if locked_id == "E2" else ())]
        for planted_id in ("E1", "E2"):
            hyp = Hypothesis(id="H1", propositions=(Planted(evidence=planted_id),))
            case = f"locked {locked_id}, planted {planted_id}"
            assert evaluate_hypothesis(hyp, EvidenceStore(items), StatementStore(), both, turn=2).status == "open", case
            board = evaluate_hypothesis(hyp, EvidenceStore(items), StatementStore(), heard, turn=2)
            assert (board.status, board.support) == ("corroborated", ({"E1": "E2", "E2": "E1"}[planted_id],)), case
