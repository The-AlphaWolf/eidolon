"""Negative fixtures (Phase 6 brief). Part 1 re-runs the Phase 0.5 fixtures under the PRODUCTION
solver; part 2 derives ten Phase 6 negatives by editing generated packages. Every one must be
rejected, and rejected AT THE STAGE that owns the defect (§19.2) — a case failing for an unrelated
reason would prove nothing."""
import pytest

from eidolon.evidence.model import DiscoverySpec, Evidence, Implication, Prereq
from eidolon.gen.pipeline import validate
from eidolon.minds.knowledge import KnowledgeEntry, KnowledgeStore
from eidolon.minds.provenance import Witnessed
from eidolon.minds.soundness import check_knowledge_soundness
from eidolon.solve.oracle import oracle_feasible
from eidolon.solve.package import (
    CanonicalSolution, CasePackage, EliminationStructure, MethodSpec, TimeShift,
)
from eidolon.solve.solver import build_ctx, evaluate, judge, robust_material
from eidolon.world.feasibility import feasible
from eidolon.world.propositions import At
from tests.solve.helpers import blind_everyone, drop_evidence, edit_evidence, pkg, rebuild, unalibied, verdict
from tests.world.fixtures.vance import vance_v01_negative, vance_v02_negative, vance_v03


# ------------------------------------------------------------------ Phase 0.5 fixtures, re-run
def _phase1_package(case, imps) -> CasePackage:
    ev = tuple(Evidence(id=eid, kind="Timepiece", created_at=i.created_at,
                        implications=(Implication(proposition=i.proposition, requires=i.requires),),
                        discovery=DiscoverySpec(action="Look", at="Study")) for eid, i in imps)
    sol = CanonicalSolution(murderer="David", victim="Harold", method="blunt", weapon="Glass1", location="Study",
                            interval=(70, 71), murder_event="attack", motive_kind="x", approach=(68, 73))
    return CasePackage(id=case.id, skeleton_id="phase1", seed=0, case=case, evidence=ev, secrets=(),
                       method=MethodSpec(kind="blunt", weapon="Glass1"),
                       structure=EliminationStructure(alibi_window=0, secret_clearance=0, opportunity_pin=False), solution=sol)


@pytest.mark.parametrize("fixture", [vance_v01_negative, vance_v02_negative])
def test_vance_v01_and_v02_negatives_are_rejected_by_the_production_solver(fixture):
    """Collusion (lovers alibi each other) and the open corridor: same semantics as the spike."""
    p = _phase1_package(*fixture())
    ctx = build_ctx(p)
    mat, _, _ = robust_material(ctx)
    v = evaluate(ctx, mat)
    assert not v.unique
    assert len(v.survivors) > 1 and "outsider corridor open" in v.reasons


def test_vance_v03_as_shipped_in_phase_1_lacks_a_containment_device_so_is_not_declared_unique():
    """The Phase 1 fixture carries only E_watch/E_trace: David is the lone survivor but the corridor is
    open, and the solver refuses to call that unique — the same reading that made v02 fail."""
    p = _phase1_package(*vance_v03())
    _, _, v = verdict(p)
    assert v.survivors == ["David"] and not v.unique and "outsider corridor open" in v.reasons


def test_transitive_alibi_cycle_and_pairwise_clean_triple_are_infeasible_in_solver_and_oracle():
    from tests.world.test_feasibility import CYCLE, TRIPLE
    case, _ = vance_v01_negative()
    for claims in (CYCLE, TRIPLE):
        assert not feasible(case, claims).ok
        for a in {c.proposition.actor for c in claims}:
            mine = [c for c in claims if c.proposition.actor == a]
            forced, exist, blocked = {}, [], set()
            for c in mine:
                p = c.proposition
                if p.kind == "At":
                    forced.update({t: p.location for t in range(*p.interval)})
                else:
                    exist.append({(p.location, t) for t in range(*p.interval)})
            starts = [(loc, 0) for loc in case.locations]
            dp = feasible_actor_case(case, forced, exist, starts)
            assert dp == oracle_feasible(case, case.t_investigation, blocked, forced, exist, starts)


def feasible_actor_case(case, forced, exist, starts):
    from eidolon.world.feasibility import _search
    return _search(case, case.t_investigation, starts, set(), forced, exist)[0]


# ------------------------------------------------------------------ Phase 6 negatives
def stage(p: CasePackage) -> str | None:
    return validate(p).failed_at


def test_N1_multiple_valid_murderers_is_rejected_at_V5():
    p = unalibied(pkg("study_party", 4))
    _, _, v = verdict(p)
    assert len(v.survivors) > 1 and not v.unique
    assert stage(p) == "V-5"


def test_N2_impossible_murderer_is_rejected_by_physics_and_by_the_solver():
    p = pkg("study_party", 4)
    innocent = next(a for a in p.case.living_actors() if a != p.solution.murderer)
    ev = [e.model_copy(update={"actor": innocent}) if e.id == "attack" else e for e in p.case.events]
    assert stage(rebuild(p, events=ev)) == "V-1"                       # P-4: attacker not in the room
    # and the solver alone: naming the excluded innocent as the murderer contradicts its verdict
    v = verdict(p)[2]
    claimed = p.model_copy(update={"solution": p.solution.model_copy(update={"murderer": innocent})})
    assert any("survivor" in m for m in judge(claimed, v))
    assert v.candidates[innocent]["excluded"]


def test_N3_unreachable_proof_is_rejected_at_V4_though_formally_unique():
    p = edit_evidence(pkg("study_party", 4), "E_watch", discovery=DiscoverySpec(
        action="Look", at="Study", prerequisites=(Prereq(kind="EvidenceFound", ref="E_ghost"),)))
    assert verdict(p)[2].unique                                          # FORMAL solvability intact
    assert stage(p) == "V-4"                                             # HUMAN solvability is not


def test_N4_ambiguous_timeline_is_not_unique():
    p = drop_evidence(blind_everyone(pkg("study_party", 4)), "E_watch")
    v = verdict(p)[2]
    assert not v.unique and v.window[1] - v.window[0] > 1


def test_N4b_dropping_only_the_time_pin_loses_uniqueness_or_keeps_it_by_other_material_never_silently():
    p = drop_evidence(pkg("manor_wing", 4), "E_watch")
    v = verdict(p)[2]
    assert v.window[1] - v.window[0] > 1                                 # the pin was doing real work
    if not v.unique:
        assert v.reasons                                                  # loss of uniqueness is REPORTED


def test_N5_unsupported_uniqueness_claim_fails_closed():
    p = pkg("study_party", 4)
    p = p.model_copy(update={"method": MethodSpec(kind="blunt_force", weapon="Decanter", admits=("Accident",))}).sealed()
    v = verdict(p)[2]
    assert not v.unique and any("fail closed" in r for r in v.reasons)
    assert stage(p) == "V-5"


def test_N6_hidden_critical_clue_uncued_is_rejected_at_V4():
    p = edit_evidence(pkg("study_party", 4), "E_watch", discovery=DiscoverySpec(action="Look", at="Study", cue="something_never_held"))
    assert stage(p) == "V-4"


def test_N7_impossible_knowledge_path_is_rejected():
    p = pkg("study_party", 4)
    a, b = sorted(p.case.living_actors())[:2]
    ghost = KnowledgeEntry(id="K_ghost", character=a, proposition=At(actor=b, location="Gazebo", interval=(10, 20)),
                           source=Witnessed(event_id="nowhere", modality="sight", quality=0.9), acquired_at=10,
                           reliability=0.9, is_true=False)
    assert check_knowledge_soundness(KnowledgeStore([ghost]), p.case)     # V-2 catches a hand-built entry
    bad = p.model_copy(update={"distortions": (TimeShift(memory="Mnobody0001", actor=a, delta=5, know_ids=("S:P0001",)),)}).sealed()
    assert stage(bad) == "V-2"                                            # and a distortion Phase 2 would never assign


def test_N8_contradictory_evidence_is_rejected_at_V1():
    p = pkg("study_party", 4)
    M, (t0, t1) = p.solution.murderer, p.solution.interval
    lie = Evidence(id="E_bad", kind="Digital", created_at=(t0, t1), implications=(Implication(
        proposition=At(actor=M, location="Hall", interval=(t0, t1))),), discovery=DiscoverySpec(action="Look", at="Hall"))
    assert stage(rebuild(p, evidence=list(p.evidence) + [lie])) == "V-1"


def test_N9_planted_evidence_is_never_admissible_and_treating_it_as_authentic_is_caught():
    p = pkg("study_party", 4)
    M, (t0, t1) = p.solution.murderer, p.solution.interval
    fake = dict(id="E_fake", kind="Digital", created_at=(t0 - 3, t1 + 3), discovery=DiscoverySpec(action="Look", at="Hall"),
                implications=(Implication(proposition=At(actor=M, location="Hall", interval=(t0 - 3, t1 + 3))),))
    planted = rebuild(p, evidence=list(p.evidence) + [Evidence(**fake, authentic=False, planted_by="plant")])
    base = verdict(p)[2]
    assert verdict(planted)[2].to_json() == base.to_json()               # a planted alibi for the murderer: ignored (L0)
    mislabelled = rebuild(p, evidence=list(p.evidence) + [Evidence(**fake)])   # the same item, authentic=True
    assert stage(mislabelled) == "V-1"                                   # P-0: the canonical world refutes it
    ctx, mat, _ = verdict(mislabelled)
    assert verdict(mislabelled)[2].to_json() != base.to_json()           # and it would have changed the verdict


def test_N10_an_alternative_the_generator_says_it_excluded_is_still_open_when_the_material_is_gone():
    p = pkg("study_party", 4)
    assert any(a.candidate == "Outsider" and a.material for a in p.solution.alternatives)   # declared as excluded…
    gone = drop_evidence(p, *(a for alt in p.solution.alternatives if alt.candidate == "Outsider" for a in alt.material))
    v = verdict(gone)[2]
    assert not v.outsider["excluded"] and not v.unique                    # …but the solver derives it open
    assert "outsider corridor open" in v.reasons


def test_no_valid_murderer_is_rejected():
    """Every candidate excluded: contradictory alibis leave no survivor at all."""
    p = pkg("study_party", 4)
    ctx, mat, v = verdict(p)
    pin = Evidence(id="E_pin_wrong", kind="Digital", created_at=(0, 120), implications=(Implication(
        proposition=At(actor=p.solution.murderer, location="Hall", interval=(60, 100))),),
        discovery=DiscoverySpec(action="Look", at="Hall"))
    q = rebuild(p, evidence=list(p.evidence) + [pin])
    _, _, v2 = verdict(q)
    assert p.solution.murderer not in v2.survivors                        # a (false) pin excludes the real murderer
    assert not v2.unique or judge(q, v2)                                  # and the case is rejected either way
    assert stage(q) == "V-1"
