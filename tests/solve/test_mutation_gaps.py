"""Tests added because the first Phase 6 mutation run let 20 of 48 mutants SURVIVE (see the report,
§Mutation). Each test below isolates ONE decision that had a redundant guard or no direct test:
the verifier's individual checks, the pipeline's individual stages, single lattice rules, the
bluff proxy on a case where it should fire, and time resolution."""
import copy


from eidolon.evidence.model import DiscoverySpec, Evidence, Implication
from eidolon.gen import pipeline
from eidolon.gen.pipeline import validate
from eidolon.solve import fairness as fair
from eidolon.solve.lattice import Know, admissible, claimed, material
from eidolon.solve.package import CanonicalSolution, CasePackage, EliminationStructure, MethodSpec
from eidolon.solve.proof import verify_proof
from eidolon.solve.solver import build_ctx, evaluate, robust_material
from eidolon.world.case import Case
from eidolon.world.entities import Actor
from eidolon.world.events import EffActorAt, Event
from eidolon.world.propositions import At, Did, Saw
from eidolon.world.space import Location
from tests.solve.helpers import drop_evidence, golden, pkg, rebuild, verdict
from tests.solve.test_bruteforce_case import tiny


# ---------------------------------------------------------------- the verifier, one check at a time
def base():
    r = golden("study_party", 4)
    return r.package, copy.deepcopy(r.report.proof)


def test_verifier_flags_a_core_with_a_redundant_constraint_V2():
    p, proof = base()
    X = next(x for x, e in proof["candidates"].items() if e["excluded"])
    in_core = set(proof["candidates"][X]["core"])                    # proof/2: a core is a list of constraint ids
    extra = next(c for c in proof["constraints"] if c["actor"] == X and c["id"] not in in_core)
    proof["candidates"][X]["core"].append(extra["id"])
    assert any("not deletion-minimal" in m for m in verify_proof(p, proof))


def test_verifier_flags_a_core_that_is_not_actually_infeasible_V3():
    """A core swapped for a constraint that does not exclude the candidate at all. "Harmless" is
    picked explicitly — a constraint whose interval misses the murder window — rather than "any
    other constraint about X", which since B-3's room log may itself be an exclusion."""
    p, proof = base()
    X = next(x for x, e in proof["candidates"].items() if e["excluded"])
    in_core = set(proof["candidates"][X]["core"])
    lo, hi = proof["window"]
    harmless = next(c for c in proof["constraints"]
                    if c["actor"] == X and c["id"] not in in_core and not (c["iv"][0] < hi and lo < c["iv"][1]))
    proof["candidates"][X]["core"] = [harmless["id"]]
    assert any("ORACLE finds a walk" in m for m in verify_proof(p, proof))


def test_verifier_re_derives_the_uniqueness_claim_V4():
    p, proof = base()
    proof["unique"] = False
    assert any("unique=False" in m for m in verify_proof(p, proof))
    from tests.solve.helpers import unalibied
    blind = unalibied(pkg("study_party", 4))
    ctx, mat, v = verdict(blind)
    from eidolon.solve.proof import build_proof
    from eidolon.solve.lattice import admissible as adm
    cons = adm(ctx.case, ctx.store, mat, ctx.comps, ctx.victim)
    forged = build_proof(blind, ctx, cons, v, cracked=frozenset(), rounds=0, core=None)
    assert verify_proof(blind, forged) == []                 # an honest non-unique proof verifies...
    forged["unique"] = True
    assert any("unique=True" in m for m in verify_proof(blind, forged))     # ...a lying one does not


def test_verifier_checks_the_package_seal_itself_V5():
    p, proof = base()
    tampered = p.model_copy(update={"seed": p.seed + 1})     # seal now stale; proof still names the OLD seal
    tampered_proof = {**proof, "package_seal": tampered.seal}        # so the proof agrees with the (stale) recorded seal
    assert any("seal does not verify" in m for m in verify_proof(tampered, tampered_proof))


def test_verifier_re_derives_the_outsider_verdict_V6():
    p, proof = base()
    proof["outsider"]["excluded"] = False
    assert any("outsider verdict disagrees" in m for m in verify_proof(p, proof))


# ---------------------------------------------------------------- pipeline stages, one at a time
def test_G2_physics_alone_rejects_at_V1():
    p = pkg("study_party", 4)
    a = next(x for x in p.case.living_actors())
    seg = next(e for e in p.case.events if e.kind == "Stay" and e.actor == a)
    other = next(loc for loc in p.case.locations if loc not in (seg.location, "EXT"))
    clash = Event(id="clash", kind="Stay", interval=seg.interval, location=other, actor=a,
                  effects=(EffActorAt(actor=a, location=other),))
    q = rebuild(p, events=list(p.case.events) + [clash])       # two places at once: P-1 and nothing else
    assert validate(q).failed_at == "V-1"


def test_G3_the_solver_stage_judges_the_verdict_against_the_canonical_solution():
    p = pkg("study_party", 4)
    other = next(a for a in p.case.living_actors() if a != p.solution.murderer)
    lie = p.model_copy(update={"solution": p.solution.model_copy(update={"murderer": other})}).sealed()
    rep = validate(lie)
    assert rep.failed_at == "V-5" and any("survivor" in x for x in rep.problems)


def test_G4_the_pipeline_runs_the_independent_verifier(monkeypatch):
    real = pipeline.build_proof

    def corrupt(*a, **k):
        proof = real(*a, **k)
        proof["outsider"]["excluded"] = not proof["outsider"]["excluded"]
        return proof
    monkeypatch.setattr(pipeline, "build_proof", corrupt)
    rep = validate(pkg("study_party", 4))
    assert rep.failed_at == "V-5" and any("proof does not verify" in x for x in rep.problems)


# ---------------------------------------------------------------- single lattice rules
def two_witnesses(events_y, events_z):
    p = tiny()
    ctx = build_ctx(p)
    k = lambda i, who, ev: Know(i, who, At(actor="x", location="A", interval=(0, 8)), "CoPresence", ev, "A", (0, 8), 2)
    mat = {"k1": k("k1", "y", events_y), "k2": k("k2", "z", events_z)}
    comps = {"v": 0, "x": 1, "y": 2, "z": 3}                      # nobody colludes
    return [c for c in admissible(ctx.case, ctx.store, mat, comps, ctx.victim) if c.kind == "At" and c.actor == "x"]


def test_L2_corroboration_needs_disjoint_provenance():
    assert any(c.level == 2 for c in two_witnesses(("e1",), ("e2",)))          # two perceptions: one claim, corroborated
    assert not any(c.level == 2 for c in two_witnesses(("e1",), ("e1",)))      # one perception, two beliefs: still ONE source


def test_L8_a_universal_claim_only_asserts_its_inner_part_and_an_existential_one_widens():
    k = Know("k", "y", At(actor="x", location="A", interval=(10, 20)), "CoPresence", ("e",), "A", (10, 20), 2)
    assert claimed(k, 100) == (12, 18)
    kd = Know("k", "y", Did(actor="x", action="Use", location="A", interval=(10, 20)), "Participated", ("e",), "A", (10, 20), 2)
    assert claimed(kd, 100) == (8, 22)


def test_L9_a_requires_token_resolves_only_to_that_actors_own_account():
    p = tiny()
    ctx = build_ctx(p)

    def with_requires(token):
        ev = Evidence(id="E_req", kind="Digital", created_at=(4, 5), discovery=DiscoverySpec(action="Look", at="M"),
                      implications=(Implication(proposition=Did(actor="x", action="Attack", interval=(4, 5), location="M"),
                                                requires=(token,)),))
        mat = material([ev], {k.id: k for k in ctx.atoms})
        return [c for c in admissible(ctx.case, ctx.store, mat, ctx.comps, ctx.victim) if c.item == "E_req"]
    assert with_requires("attack@x")                     # x's own account of the attack exists
    assert not with_requires("attack@y")                 # y took no part in it: nothing resolves


def test_L4_an_authentic_implication_may_not_exceed_what_its_creation_establishes():
    p = pkg("study_party", 4)
    t0, t1 = p.solution.interval
    over = Evidence(id="E_over", kind="Digital", created_at=(t0, t1), discovery=DiscoverySpec(action="Look", at="Hall"),
                    implications=(Implication(proposition=Did(actor="x", action="Use", location="Hall", interval=(t0 - 10, t1))),))
    ctx = build_ctx(rebuild(p, evidence=list(p.evidence) + [over]))
    mat = material(list(ctx.store.all()), {})
    cons = admissible(ctx.case, ctx.store, mat, ctx.comps, ctx.victim)
    assert not [c for c in cons if c.item == "E_over"]                 # P-9 / I-30: not established, so not L3


def test_L10_and_L6_a_requires_chain_is_bounded_by_its_statements_interval_and_by_its_weakest_link():
    p = pkg("study_party", 4)
    ctx, mat, _ = verdict(p)
    cons = admissible(ctx.case, ctx.store, mat, ctx.comps, ctx.victim)
    trace = [c for c in cons if c.item == "E_trace"]
    assert trace and max(c.level for c in trace) == 2                   # L6: min over the chain, never L3
    tr = next(e for e in p.evidence if e.id == "E_trace")
    imp = tr.implications[0]
    early = imp.model_copy(update={"proposition": imp.proposition.model_copy(update={"interval": (imp.proposition.interval[0] - 6, 120)})})
    q = rebuild(p, evidence=[e.model_copy(update={"implications": (early,)}) if e.id == "E_trace" else e for e in p.evidence])
    ctx2, mat2, _ = verdict(q)
    assert not [c for c in admissible(ctx2.case, ctx2.store, mat2, ctx2.comps, ctx2.victim) if c.item == "E_trace"]   # L10


# ---------------------------------------------------------------- outsider start, time resolution, bluff
def test_O3_a_partial_containment_log_still_excludes_an_outsider_who_could_not_have_entered():
    p = pkg("study_party", 4)
    t_m = p.solution.interval[0]
    gate = next(e for e in p.evidence if e.id.startswith("E_gate_"))
    ext = gate.implications[0].proposition.location
    partial = gate.model_copy(update={"created_at": (0, t_m), "implications": (Implication(proposition=Saw(
        observer=p.solution.victim, subject="nobody", location=ext, interval=(0, t_m), identified=False)),)})
    q = rebuild(p, evidence=[partial if e.id == gate.id else e for e in p.evidence])
    # the corridor was logged shut until the murder: nobody could have ENTERED (exiting later is not enough)
    assert verdict(q)[2].outsider["excluded"]


def test_S6_without_a_time_pin_the_survivors_times_are_resolved_tick_by_tick():
    p = drop_evidence(pkg("manor_wing", 4), "E_watch")
    _, _, v = verdict(p)
    assert v.window[1] - v.window[0] > 1 and len(v.candidates[p.solution.murderer]["times"]) > 1


def single_suspect(T):
    ev = [Event(id="sv", kind="Stay", interval=(0, T), location="M", actor="v", effects=(EffActorAt(actor="v", location="M"),)),
          Event(id="sx", kind="Stay", interval=(0, T), location="M", actor="x", effects=(EffActorAt(actor="x", location="M"),))]
    case = Case(id="one", t_investigation=T, actors={"v": Actor(id="v", name="v", role="victim"), "x": Actor(id="x", name="x", role="suspect")},
                locations={"M": Location(id="M", name="M", private=True)}, events=tuple(ev))
    sol = CanonicalSolution(murderer="x", victim="v", method="b", weapon="w", location="M", interval=(0, 1),
                            murder_event="e", motive_kind="m", approach=(0, T))
    return CasePackage(id="one", skeleton_id="t", seed=0, case=case, evidence=(), secrets=(), method=MethodSpec(kind="b", weapon="w"),
                       structure=EliminationStructure(alibi_window=0, secret_clearance=0, opportunity_pin=False), solution=sol)


def test_F4_the_bluff_proxy_fires_on_a_case_a_bluffer_could_solve():
    ctx = build_ctx(single_suspect(8))                     # one suspect, no exterior, one time bin: nothing left to prove
    assert fair.bluff_converges(ctx)
    assert not fair.bluff_converges(build_ctx(pkg("study_party", 4)))


def test_U2_one_survivor_in_several_time_bins_is_not_unique():
    ctx = build_ctx(single_suspect(30))
    mat, _, _ = robust_material(ctx)
    v = evaluate(ctx, mat)
    assert v.survivors == ["x"] and len(v.time_bins) > 1 and not v.unique and any("under-determined" in r for r in v.reasons)


def test_T2_a_window_wider_than_the_bound_is_reported_approximate_not_enumerated():
    ctx = build_ctx(single_suspect(60))
    v = evaluate(ctx, {})
    assert v.candidates["x"].get("times_approx") is True and not v.unique
