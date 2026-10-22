"""The Phase 6 self-check questions as tests, plus the lattice rules they rest on, distortion-subset
robustness, and malformed input. (See docs/EIDOLON-PHASE-6-REPORT.md, "Final self-check".)"""
import random

import pytest

from eidolon.decision.secrets import SecretStore
from eidolon.evidence.model import EvidenceStore
from eidolon.gen.compile import compile_draft
from eidolon.gen.planner import plan
from eidolon.gen.skeletons import SKELETONS
from eidolon.solve.distort import apply_shifts, derive_distortions, robustness
from eidolon.solve import lattice
from eidolon.solve.lattice import admissible
from eidolon.solve.package import TimeShift
from eidolon.solve.solver import build_ctx, evaluate, judge, proof_core, robust_material
from eidolon.world.case import Case
from eidolon.world.propositions import Rel
from tests.solve.helpers import blind_everyone, drop_evidence, pkg, rebuild, verdict


# ---- Q1: secretly replace the intended murderer, keep the world consistent, rerun the solver ----
@pytest.mark.parametrize("skel", sorted(SKELETONS))
def test_Q1_replacing_the_murderer_is_rediscovered_not_assumed(skel):
    sk, seen = SKELETONS[skel], 0
    for seed in (4, 5):
        for who in [n for n, _ in sk.cast]:
            dr = plan(sk, seed, murderer=who)
            if dr.error:
                continue
            p = compile_draft(dr)
            try:
                _, _, v = verdict(p)
            except Exception:                        # a physically invalid swapped world cannot be folded
                continue
            seen += 1
            assert v.survivors == [who] or not v.unique          # the solver follows the WORLD...
            claimed = p.model_copy(update={"solution": p.solution.model_copy(update={"murderer": next(
                a for a in p.case.living_actors() if a != who)})})
            assert judge(claimed, v)                              # ...so a false claim is always caught
    assert seen >= 4


def test_Q1b_a_second_suspect_left_unexcluded_makes_the_case_non_unique():
    v = verdict(blind_everyone(pkg("manor_wing", 4)))[2]
    assert not v.unique and len(v.survivors) >= 2


# ---- Q2: reorder evidence/events/actors without changing semantics -> same result (test_solver.py) ----

# ---- Q3: remove a critical clue -> the loss of uniqueness is DETECTED ----
@pytest.mark.parametrize("skel,seed", [("study_party", 4), ("manor_wing", 4)])
def test_Q3_removing_any_proof_core_evidence_is_never_silent(skel, seed):
    p = pkg(skel, seed)
    ctx, mat, base = verdict(p)
    core = [i for i in proof_core(ctx, mat) if i.startswith("E_")]
    assert core
    for eid in core:
        q = drop_evidence(p, eid)
        ctx2, mat2, v = verdict(q)
        if v.unique:                                           # redundancy is allowed, but then it must be real
            assert eid not in proof_core(ctx2, mat2)
        else:
            assert v.reasons


def test_Q3b_the_containment_log_is_load_bearing_for_the_outsider():
    p = pkg("study_party", 4)
    gate = next(e.id for e in p.evidence if e.id.startswith("E_gate_"))
    assert verdict(p)[2].outsider["excluded"]
    assert not verdict(drop_evidence(p, gate))[2].outsider["excluded"]


# ---- Q4: a plausible case with two valid explanations is rejected (test_negative_fixtures.py N1/N10) ----

# ---- lattice rules --------------------------------------------------------------------------------
def test_protected_interval_testimony_is_withheld_until_cracked():
    p = pkg("manor_wing", 4)
    ctx = build_ctx(p)
    pool = lattice.testimony_pool(ctx.atoms, ctx.protected)
    from eidolon.world.interval import overlaps
    assert all(not any(overlaps(k.obs_iv, iv) for iv in ctx.protected.get(k.who, ())) for k in pool.values())
    assert len(lattice.testimony_pool(ctx.atoms, ctx.protected, frozenset(ctx.protected))) == len(ctx.atoms)


def _colluding(p):
    innocents = [a for a in p.case.living_actors() if a != p.solution.murderer]
    rels = tuple(p.case.rels) + tuple(Rel(a=a, b=b, rel_kind="lover") for a, b in zip(innocents, innocents[1:]))
    case = Case(**{**{k: getattr(p.case, k) for k in Case.model_fields}, "rels": rels})
    return p.model_copy(update={"case": case}).sealed()


def test_collusion_destroys_corroboration_once_physical_pins_are_removed():
    """I-37: lovers do not corroborate each other. With every device log gone (so nothing FIXES a
    witness's presence, I-44) the alibis rest on independent corroboration alone — and chaining every
    innocent into one collusion component removes it."""
    p = pkg("study_party", 4)
    pins = [e.id for e in p.evidence if e.id.startswith(("E_alibi_", "E_secret_", "E_pin_"))]
    bare = drop_evidence(p, *pins)
    assert verdict(bare)[2].unique                                    # independent witnesses suffice...
    _, _, v = verdict(_colluding(bare))
    assert not v.unique and len(v.survivors) > 1                      # ...colluding ones do not


def test_physical_pins_keep_a_colluding_witness_admissible():
    """The other half of I-44: presence fixed by L3 material makes testimony L2 whoever the witness is."""
    _, _, v = verdict(_colluding(pkg("study_party", 4)))
    assert v.unique


def test_hard_fair_level_uses_strictly_fewer_constraints_than_standard():
    ctx, mat, _ = verdict(pkg("manor_wing", 4))
    cons = admissible(ctx.case, ctx.store, mat, ctx.comps, ctx.victim)
    assert sum(c.level >= 3 for c in cons) < sum(c.level >= 2 for c in cons)


def test_the_rejected_segment_reading_never_yields_fewer_constraints_than_tick_level():
    ctx, mat, _ = verdict(pkg("study_party", 4))
    tick = admissible(ctx.case, ctx.store, mat, ctx.comps, ctx.victim, "tick")
    seg = admissible(ctx.case, ctx.store, mat, ctx.comps, ctx.victim, "segment")
    assert sum(c.level >= 2 for c in seg) >= sum(c.level >= 2 for c in tick)


def test_duplicate_evidence_changes_nothing():
    p = pkg("study_party", 4)
    dup = [e.model_copy(update={"id": e.id + "_dup"}) for e in p.evidence if e.id == "E_watch"]
    q = rebuild(p, evidence=list(p.evidence) + dup)
    assert verdict(q)[2].survivors == verdict(p)[2].survivors and verdict(q)[2].unique


def test_missing_noncritical_material_keeps_uniqueness():
    p = pkg("manor_wing", 4)
    ctx, mat, _ = verdict(p)
    core = set(proof_core(ctx, mat))
    spare = [e.id for e in p.evidence if e.id not in core and e.id.startswith("E_pin_")]
    assert verdict(drop_evidence(p, *spare))[2].unique


# ---- distortion-subset robustness ------------------------------------------------------------------
def test_distortions_are_bounded_seeded_and_phase2_assigned():
    p = pkg("manor_wing", 4)
    derived = {d.memory: d for d in derive_distortions(p.case)}
    assert len(derived) > 20                                     # Phase 2 alone would distort dozens of memories
    assert 0 < len(p.distortions) <= len(p.case.living_actors())
    assert all(d.memory in derived and derived[d.memory].delta == d.delta for d in p.distortions)


def test_robustness_enumerates_every_subset_of_active_distortions_and_can_fail():
    p = pkg("study_party", 4)
    ctx, mat, v = verdict(p)
    _, cracked, _ = robust_material(ctx)
    ok = robustness(ctx, list(p.distortions), 2, cracked, v.survivors)
    assert ok["ok"] and ok["subsets_run"] == 2 ** ok["n_active"]
    # (a) the failure PATH: an expectation the verdict cannot meet is reported per subset, with reasons
    some = [TimeShift(memory=f"M{k.id}", actor=k.who, delta=60, know_ids=(k.id,)) for k in ctx.atoms[:3]]
    r = robustness(ctx, some, 2, cracked, ["Nobody"])
    assert not r["ok"] and r["n_failures"] == r["subsets_run"] and r["failures"][0]["survivors"] != ["Nobody"]
    # (a2) an active distortion is DETECTED, its subsets enumerated, and a subset that breaks the case REPORTED:
    # on the small case, z's account of y is what corroborates y's alibi — distort it and y is no longer excluded
    from tests.solve.test_bruteforce_case import tiny
    tctx = build_ctx(tiny())
    z_on_y = [k for k in tctx.atoms if k.who == "z" and k.prop.kind == "At" and k.prop.actor == "y"]
    assert z_on_y
    r3 = robustness(tctx, [TimeShift(memory=f"M{k.id}", actor="z", delta=60, know_ids=(k.id,)) for k in z_on_y], 2,
                    frozenset(), ["x"])
    assert r3["n_active"] >= 1 and r3["subsets_run"] == 2 ** r3["n_active"] and not r3["ok"] and r3["n_failures"] >= 1
    # (a3) REDUNDANT sources: with w also vouching for y, neither z's nor w's distortion matters alone — the
    # activity only shows JOINTLY, and only the leave-one-out test (against the all-distorted extreme) finds it
    rctx = build_ctx(tiny(extra_witness=True))
    both = [k for k in rctx.atoms if k.who in ("z", "w") and k.prop.kind == "At" and k.prop.actor == "y"]
    assert {k.who for k in both} == {"z", "w"}
    r4 = robustness(rctx, [TimeShift(memory=f"M{k.id}", actor=k.who, delta=60, know_ids=(k.id,)) for k in both], 2,
                    frozenset(), ["x"])
    assert r4["n_active"] == 2 and not r4["ok"] and r4["n_failures"] >= 1
    # (b) the failure MECHANISM: distort every testimony far outside the window and uniqueness is really lost
    ctx2, _, _ = verdict(drop_evidence(p, *[e.id for e in p.evidence if e.id.startswith(("E_alibi_", "E_secret_", "E_pin_"))]))
    everything = [TimeShift(memory=f"M{k.id}", actor=k.who, delta=60, know_ids=(k.id,)) for k in ctx2.atoms]
    atoms = apply_shifts(ctx2.atoms, everything, 120)
    from eidolon.solve.lattice import material, testimony_pool
    v2 = evaluate(ctx2, material(ctx2.store.all(), testimony_pool(atoms, ctx2.protected, cracked)))
    assert not v2.unique


def test_apply_shifts_moves_only_the_named_atoms_and_drops_atoms_shifted_out_of_range():
    ctx, *_ = verdict(pkg("study_party", 4))
    a = ctx.atoms[10]
    out = apply_shifts(ctx.atoms, [TimeShift(memory="m", actor=a.who, delta=7, know_ids=(a.id,))], 120)
    moved = next(k for k in out if k.id == a.id)
    assert moved.prop.interval[0] == min(120, a.prop.interval[0] + 7) or moved.prop.interval[0] == a.prop.interval[0] + 7
    assert [k for k in out if k.id != a.id] == [k for k in ctx.atoms if k.id != a.id]
    gone = apply_shifts(ctx.atoms, [TimeShift(memory="m", actor=a.who, delta=500, know_ids=(a.id,))], 120)
    assert a.id not in {k.id for k in gone}


# ---- malformed input ---------------------------------------------------------------------------------
def test_malformed_cases_are_rejected_at_construction_or_reported_never_crash():
    p = pkg()
    with pytest.raises(ValueError):                              # dangling reference: refused by Case itself
        Case(**{**{k: getattr(p.case, k) for k in Case.model_fields}, "events": p.case.events + (
            p.case.events[0].model_copy(update={"id": "x", "location": "Nowhere"}),)})
    no_victim = Case(**{**{k: getattr(p.case, k) for k in Case.model_fields}, "actors": {
        a: x.model_copy(update={"role": "suspect"}) for a, x in p.case.actors.items()}})
    v = verdict(p.model_copy(update={"case": no_victim}).sealed())[2]
    assert not v.unique and any("victim" in r for r in v.reasons)


def test_a_tampered_package_fails_its_seal():
    p = pkg()
    assert p.verify_seal()
    bad = p.model_copy(update={"seed": p.seed + 1})
    assert not bad.verify_seal()
