"""Generation and validation (§18.3 stages 9-11, §19.1 V-0…V-8).

`generate(skeleton, seed)` = plan -> compile -> bounded distortion selection -> memory boosts
(I-39) -> `validate` -> seal. `validate(pkg)` runs the stages IN ORDER on the sealed package alone
and stops at the first failure, naming it: the seed study counts the funnel by that name.

The pipeline calls the solver; the solver never calls the pipeline or the planner
(`tests/solve/test_independence.py` checks the import graph).
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field, replace

from ..decision.cover_consistency import (
    MurderUniquenessCheck, check_cover_consistency, deliverable_accounts, derive_breaker_sets,
)
from ..decision.secrets import SecretStore
from ..evidence.contradiction import evidence_vs_evidence
from ..evidence.grounding import check_evidence_grounding
from ..evidence.model import EvidenceStore
from ..minds import accounts
from ..minds.knowledge import propagate_knowledge
from ..minds.soundness import check_knowledge_soundness
from ..solve import bots
from ..solve import fairness as fair
from ..solve import proof_material as pm
from ..solve.distort import derive_distortions, robustness
from ..solve.lattice import admissible
from ..solve.package import CasePackage, MemoryBoost, SealedCase, TimeShift
from ..solve.proof import build_proof, verify_proof
from ..solve.session import decision_context
from ..solve.solver import build_ctx, evaluate, judge, proof_core, robust_material, robust_trace
from ..world.facts import FactIndex
from ..world.physics import check_physics
from .compile import compile_draft
from .planner import plan
from .skeletons import SKELETONS, Skeleton

STAGES = ("planner", "V-0", "V-1", "V-2", "V-3", "V-4", "V-5", "V-6", "V-7")
DISTORTIONS_PER_WITNESS = {"easy": 1, "standard": 1, "hard": 2}   # §20.2 (bounded; 0 is also legal)


@dataclass
class Report:
    package: str
    failed_at: str | None = None
    problems: list = field(default_factory=list)
    stages: dict = field(default_factory=dict)      # stage -> {"ok": bool, "seconds": float, ...}
    proof: dict | None = None
    metrics: dict | None = None
    band_problems: list = field(default_factory=list)   # §20.2 knobs out of band (B-3)

    @property
    def ok(self) -> bool:
        return self.failed_at is None

    def to_json(self) -> dict:
        return {"package": self.package, "ok": self.ok, "failed_at": self.failed_at, "problems": self.problems,
                "stages": self.stages, "metrics": self.metrics}


def select_distortions(pkg: CasePackage, exclude: set[str], per_witness: int) -> tuple[TimeShift, ...]:
    """§18.3 stage 9: bounded, seeded assignment. Phase 2 would put a distortion on roughly half of
    every weak memory (30-60 per witness); the generator keeps at most `per_witness` of them per
    witness, ranked by a hash of (case, memory) so the pick is reproducible (I-6)."""
    by_actor: dict[str, list[TimeShift]] = {}
    for d in derive_distortions(pkg.case):
        if d.memory not in exclude and d.know_ids:
            by_actor.setdefault(d.actor, []).append(d)
    out: list[TimeShift] = []
    for actor in sorted(by_actor):
        ranked = sorted(by_actor[actor], key=lambda d: hashlib.sha256(f"{pkg.id}|{d.memory}".encode()).hexdigest())
        out += ranked[:per_witness]
    return tuple(sorted(out, key=lambda d: d.memory))


def _murder_layer0_tokens(pkg: CasePackage) -> set[str]:
    """The account tokens in any derived breaker set of the MURDER secret's layer 0 (ADR-24): the testimony the
    murderer's conviction-by-play rests on, which generation must make retrievable and undistorted."""
    murder = next((x for x in pkg.secrets if x.kind == "murder"), None)
    if murder is None or not pkg.accounts:
        return set()
    dctx = decision_context(pkg)
    dctx = replace(dctx, accounts=tuple(sorted(deliverable_accounts(list(pkg.secrets), dctx))))
    return {t for b in derive_breaker_sets(murder, 0, dctx) for t in b if t in pkg.accounts}


def finalize(pkg: CasePackage) -> CasePackage:
    """Stages 9-10 of §18.3 on a compiled package: raise the memories behind proof-core testimony AND behind every
    account in the murderer's layer-0 breaker (I-39, ADR-24), then pick the bounded distortion set from what remains.
    §19.4 is applied literally: the boost climbs `BOOST_LADDER` until the REAL ENGINE delivers every target through an
    expressible question; if even the top rung does not, the package keeps the top rung and V-4 rejects it."""
    ctx = build_ctx(pkg)
    mat, _cracked, _ = robust_material(ctx)
    core = proof_core(ctx, mat)
    tokens = _murder_layer0_tokens(pkg)
    atoms = {c for c in (core or []) if c.startswith("S:")}
    targets = atoms | {a for t in tokens for a in accounts.atoms_of(pkg.case, t)}
    boosts: tuple = ()
    for level in fair.BOOST_LADDER:
        boosts = tuple(MemoryBoost(memory=m, actor=a, strength_bp=level) for m, a in fair.memory_boosts_for(pkg, targets))
        if not targets or fair.engine_retrieval(pkg.model_copy(update={"memory_boosts": boosts}), atoms, tokens)["ok"]:
            break
    boosts = fair.name_places(pkg, ctx, boosts, atoms, tokens)
    k = DISTORTIONS_PER_WITNESS[pkg.difficulty]
    shifted = pkg.model_copy(update={"memory_boosts": boosts})
    dist = select_distortions(shifted, {b.memory for b in boosts}, k)
    return pkg.model_copy(update={"memory_boosts": boosts, "distortions": dist}).sealed()


def _stage(rep: Report, name: str, fn) -> bool:
    t = time.perf_counter()
    ok, problems, extra = fn()
    rep.stages[name] = {"ok": ok, "seconds": round(time.perf_counter() - t, 3), **extra}
    if not ok:
        rep.failed_at, rep.problems = name, list(problems)
    return ok


def validate(pkg: CasePackage, *, fairness: int | None = None, verify: bool = True,
             bluffs: int = bots.N_BLUFF, odd: int = bots.N_ADVERSARIAL) -> Report:
    """V-0…V-8. Stops at the first failing stage; `report.failed_at` names it. The fairness level is the one
    the package sealed (ADR-28); the keyword exists for the negative fixtures that ask a different question."""
    fairness = pkg.fairness_level if fairness is None else fairness
    rep = Report(pkg.id)
    case = pkg.case
    store = EvidenceStore(pkg.evidence)
    SecretStore(pkg.secrets)                      # refuses a duplicate secret id; the store itself is not needed
    state: dict = {}

    def v0():
        p = []
        if len({e.id for e in pkg.evidence}) != len(pkg.evidence):
            p.append("duplicate evidence ids")
        if not pkg.verify_seal():
            p.append("seal does not verify")
        p += pm.domain_problems(case)[1]            # I-59: the authored roles must agree with the CaseLog
        living = set(case.living_actors())
        for t in pkg.accounts:
            parsed = accounts.parse(t)
            if parsed is None or not accounts.atoms_of(case, t):
                p.append(f"account token {t!r} does not resolve to a Participated Did of its actor (ADR-23)")
            elif parsed[1] not in living:
                p.append(f"account token {t!r} names a dead or offstage actor")
        for s in pkg.secrets:
            if s.owner not in case.actors:
                p.append(f"{s.id}: unknown owner {s.owner}")
        for e in pkg.evidence:
            if e.red_herring and store.get(e.red_herring.refuter) is None:
                p.append(f"{e.id}: red-herring refuter {e.red_herring.refuter!r} does not exist")
        return not p, p, {}

    def v1():
        p = [str(x) for x in check_physics(case)]
        p += [str(x) for x in check_evidence_grounding(case, store, None, accounts.token_intervals(case))]
        evs = [e for e in pkg.evidence if e.authentic]
        for i, a in enumerate(evs):
            for b in evs[i + 1:]:
                p += [f"P-6 {c.a} vs {c.b}: {c.explanation}" for c in evidence_vs_evidence(a, b, case)]
        return not p, p, {}

    def v2():
        ks = propagate_knowledge(case)
        p = [str(x) for x in check_knowledge_soundness(ks, case)]
        derived = {d.memory: d for d in derive_distortions(case)}
        for d in pkg.distortions:
            if d.memory not in derived or derived[d.memory].delta != d.delta:
                p.append(f"distortion {d.memory} is not one Phase 2 would assign")
        per: dict[str, int] = {}
        for d in pkg.distortions:
            per[d.actor] = per.get(d.actor, 0) + 1
        if any(n > DISTORTIONS_PER_WITNESS[pkg.difficulty] for n in per.values()):
            p.append("more distortions per witness than the difficulty band allows")
        return not p, p, {"knowledge_entries": len(ks.all())}

    def v3():
        """§19.3, the real contract — breaker-set derivation over the sealed pool, `EvidenceResponse`
        coverage (ii), innocent reachability (iii), intra-layer consistency (iv), joint layer-0
        feasibility (v, I-28), and the murder pre-terminal uniqueness test (i). The grounding checks
        below it (protected facts true, layer-0 claims false) are Phase 6's own addition: V-3's
        contract assumes a cover that lies about something real, and nothing else checks that."""
        p, idx = [], FactIndex(case)
        for s in pkg.secrets:
            for prop in s.protected:
                if idx.truth_value(prop) is not True:
                    p.append(f"{s.id}: protected fact is not true in the CaseLog (a secret with nothing to hide): {prop}")
            for c in s.cover.layers[0].claims:
                if idx.truth_value(c.proposition) is not False:
                    p.append(f"{s.id}: layer-0 claim is not a lie in the canonical world")
        if p:
            return False, p, {"secrets": len(pkg.secrets)}
        dctx = decision_context(pkg)
        dctx = replace(dctx, accounts=tuple(sorted(deliverable_accounts(list(pkg.secrets), dctx))))
        sol = pkg.solution
        murder_check = MurderUniquenessCheck(murder_location=sol.location, murder_interval=sol.interval,
                                             candidates=tuple(sorted(case.living_actors())))
        p += [str(x) for x in check_cover_consistency(list(pkg.secrets), dctx, murder_check)]
        breakers = {(s.id, l.index): derive_breaker_sets(s, l.index, dctx)
                    for s in pkg.secrets for l in s.cover.layers if l.terminal is None}
        state["breakers"] = breakers
        # §20.1 item 6 in V-3's own terms. §19.3 check (iii) demands a breaker set for INNOCENTS;
        # nothing demanded one for the murderer, and the audit found generated cases whose
        # murderer had none at all — formally unique, conversationally unbreakable. V-6's
        # `2_lies_breakable` does not catch it: that asks whether some admissible implication
        # contradicts the lie, not whether any presentable subset reaches the layer's `resolve`.
        for s in pkg.secrets:
            if s.kind == "murder" and not breakers.get((s.id, 0)):
                p.append(f"{s.id}: the murderer's layer 0 has no derivable breaker set "
                         f"(§20.1 item 6: it must be refutable by physical evidence)")
        return not p, p, {"secrets": len(pkg.secrets),
                          "breaker_sets": sum(len(b) for b in breakers.values())}

    def v5():
        ctx = build_ctx(pkg)
        mat, cracked, rounds, trace = robust_trace(ctx, fairness)
        cons = admissible(case, ctx.store, mat, ctx.comps, ctx.victim)
        v = evaluate(ctx, mat, fairness)
        p = list(v.reasons) + judge(pkg, v)
        state.update(ctx=ctx, mat=mat, cons=cons, verdict=v, cracked=cracked, rounds=rounds)
        if p:
            return False, p, {"survivors": v.survivors, "unique": v.unique}
        core = proof_core(ctx, mat, fairness)
        frag = fair.fragility(v)
        rob = robustness(ctx, list(pkg.distortions), fairness, cracked, v.survivors)
        proof = build_proof(pkg, ctx, cons, v, cracked=cracked, rounds=rounds, core=core, robustness=rob, fragility=frag, trace=trace)
        bad = verify_proof(pkg, proof) if verify else []
        state.update(core=core, frag=frag, rob=rob, proof=proof)
        rep.proof = proof
        p = [f"proof does not verify: {b}" for b in bad]
        if not rob["ok"]:
            p.append(f"uniqueness fails for {rob['n_failures']} of {rob['subsets_run']} distortion subsets")
        return not p, p, {"survivors": v.survivors, "unique": v.unique, "rounds": rounds, "proof_core": len(core or []),
                          "distortion_subsets": rob["subsets_run"], "active_distortions": rob["n_active"]}

    def v4():
        ctx, mat, core = state["ctx"], state["mat"], state["core"]
        r = fair.v4_reachability(pkg, ctx, mat, core)
        rt = fair.retrieval_check(pkg, ctx, core, state.get("breakers", {}))
        br = fair.breakers_reachable(pkg, ctx, mat, state.get("breakers", {}))
        state.update(v4=r, retr=rt, breach=br)
        ok = r["ok"] and rt["ok"] and br["ok"]
        return ok, r["problems"] + rt["problems"] + br["problems"], {
            "cued_depth": r["cued_depth"], "retrieval_checked": rt["checked"], "breaker_refs": br["checked"]}

    def v6():
        c = fair.contract(pkg, state["ctx"], state["mat"], state["cons"], state["core"], state["verdict"],
                          state["v4"], state["retr"], state["rob"])
        bad = [f"{k}: {d}" for k, (ok, d) in c.items() if not ok]
        m = fair.metrics(pkg, state["ctx"], state["core"], state["v4"], state["rob"], state["frag"])
        rep.metrics = {**m, "fragility": state["frag"]}
        # §20.2: the band is a GATE. An out-of-band case is rejected here and `generate_in_band`
        # reseeds; it is never sealed with a difficulty it does not have (B-3).
        band_bad = fair.band_violations(pkg.difficulty, m)
        rep.band_problems = band_bad
        bad += [f"band: {b}" for b in band_bad]
        return not bad, bad, {"contract": {k: ok for k, (ok, _) in c.items()}, "bands": m["bands"],
                              "in_band": not band_bad}

    def v7():
        """§19.7 / I-53: the scripted bots drive the REAL engine at the architecture's full scale. A package seals only if
        the engine-faithful greedy and cue-following bots each reach a unique survivor equal to the canonical murderer
        within `N_MAX`/`N_CUE`, the murderer-peel bot breaks the murderer's layer 0 through real turns, the bluff bot
        does not converge (and parity holds), and the adversarial bot records zero peels and zero leaks. The canonical
        murderer is read HERE and nowhere else: the bots never see it."""
        res = bots.run_bots(pkg, names=("greedy", "cue_following", "murderer_peel", "bluff", "adversarial"),
                            bluffs=bluffs, odd=odd)
        murderer = pkg.solution.murderer
        p = []
        for name in ("greedy", "cue_following"):
            r = res[name]
            if r.survivors != [murderer] or not r.solved:
                p.append(f"{name} bot: survivors {r.survivors}, unique={r.solved} (canonical murderer {murderer})")
            elif not r.ok:
                p.append(f"{name} bot needed {r.actions} actions, over its budget")
        if not res["murderer_peel"].ok:
            p.append(f"murderer-peel bot never broke layer 0 through play (tried {res['murderer_peel'].detail.get('breaker_sets_tried')})")
        for name in ("bluff", "adversarial"):
            if not res[name].ok:
                p.append(f"{name} bot: {({k: v for k, v in res[name].detail.items() if k in ('converged', 'parity_ok', 'leaks', 'envelope_bounded')})}"
                         f" peels={res[name].peels}")
        full = bluffs == bots.N_BLUFF and odd == bots.N_ADVERSARIAL
        state["bots"] = res
        return not p, p, {"scale": "full" if full else "reduced", "bluffs_per_character": bluffs, "adversarial_per_character": odd,
                          "9_not_solvable_without_evidence": not res["bluff"].detail.get("converged", True),
                          "bots": {n: {"actions": r.actions, "ok": r.ok, "peels": r.peels, "rejected": r.rejected}
                                   for n, r in res.items()}}

    # V-5 runs before V-4/V-6 because both need the proof core; reported in stage order
    for name, fn in (("V-0", v0), ("V-1", v1), ("V-2", v2), ("V-3", v3), ("V-5", v5), ("V-4", v4), ("V-6", v6), ("V-7", v7)):
        if not _stage(rep, name, fn):
            return rep
    rep.stages["V-8"] = {"ok": True, "seal": pkg.seal}
    return rep


@dataclass
class Result:
    seed: int
    skeleton: str
    failed_at: str | None
    problems: list
    package: CasePackage | None
    report: Report | None
    seconds: float


def generate(skel: Skeleton | str, seed: int, *, difficulty: str | None = None, verify: bool = True,
             bluffs: int = bots.N_BLUFF, odd: int = bots.N_ADVERSARIAL) -> Result:
    """One attempt: no retry, no reseed. A failure is REPORTED with its stage and reasons."""
    skel = SKELETONS[skel] if isinstance(skel, str) else skel
    t0 = time.perf_counter()
    dr = plan(skel, seed)
    if dr.error:
        return Result(seed, skel.id, "planner", [dr.error], None, None, time.perf_counter() - t0)
    pkg = compile_draft(dr)
    if difficulty:
        pkg = pkg.model_copy(update={"difficulty": difficulty}).sealed()
    try:
        pkg = finalize(pkg)
    except Exception as e:                                   # physics-invalid worlds cannot be folded
        return Result(seed, skel.id, "V-1", [f"{type(e).__name__}: {str(e)[:200]}"], pkg, None, time.perf_counter() - t0)
    rep = validate(pkg, verify=verify, bluffs=bluffs, odd=odd)
    return Result(seed, skel.id, rep.failed_at, rep.problems, pkg, rep, time.perf_counter() - t0)


@dataclass
class BandResult:
    """The outcome of §20.2's loop: the in-band case, or an actionable account of why not."""
    result: Result
    attempts: int
    seeds: list
    rejections: list                 # (seed, stage, reason) per failed attempt
    in_band: bool

    @property
    def ok(self) -> bool:
        return self.in_band and self.result.failed_at is None

    def to_json(self) -> dict:
        return {"attempts": self.attempts, "seeds": self.seeds, "in_band": self.in_band,
                "rejections": self.rejections,
                "seal": self.result.package.seal if self.ok and self.result.package else None}


MAX_BAND_ATTEMPTS = 20               # §20.2: "max 20 attempts; then report"


def band_seed(seed: int, attempt: int) -> int:
    """A derived seed per attempt (§18.3 stage 3's "retried with a derived seed"), deterministic."""
    return seed if attempt == 0 else int(hashlib.sha256(f"band|{seed}|{attempt}".encode()).hexdigest()[:8], 16)


def generate_in_band(skel: Skeleton | str, seed: int, *, max_attempts: int = MAX_BAND_ATTEMPTS,
                     verify: bool = True, bluffs: int = bots.N_BLUFF, odd: int = bots.N_ADVERSARIAL) -> BandResult:
    """§20.2: "Generation loops until V-6 metrics fall in band (max 20 attempts; then report)."

    Only V-6 BAND failures are retried. Everything else keeps its own rule: a planner or physics
    failure is reported as before, and a V-5 failure on a realised structure is a skeleton defect
    that must never be reseeded away (I-43) — so the loop stops on it and says so. The last
    attempt's report is returned either way, and `rejections` names every attempt's reason, so a
    skeleton that can never reach its band produces an actionable report rather than a silent seal.
    """
    skel = SKELETONS[skel] if isinstance(skel, str) else skel
    rejections: list = []
    seeds: list = []
    last: Result | None = None
    for attempt in range(max_attempts):
        s = band_seed(seed, attempt)
        seeds.append(s)
        last = generate(skel, s, verify=verify, bluffs=bluffs, odd=odd)
        band_bad = last.report.band_problems if last.report else []
        if last.failed_at is None:
            return BandResult(last, attempt + 1, seeds, rejections, True)
        rejections.append({"seed": s, "stage": last.failed_at, "problems": [p[:160] for p in last.problems[:2]]})
        if not (last.failed_at == "V-6" and band_bad):
            break                    # not a band problem: report it, never reseed it away (I-43)
    return BandResult(last, len(seeds), seeds, rejections, False)


def write_package(res: "Result", path: str) -> None:
    """ONE sealed bundle: the package, its proof and the validation report, bound by `bundle_seal`
    (I-58). Refuses a case that did not seal — there is no detached-proof file format."""
    import json
    if res.failed_at is not None or res.package is None or res.report is None or res.report.proof is None:
        raise ValueError(f"refusing to persist an unsealed case (failed at {res.failed_at})")
    if res.report.stages.get("V-7", {}).get("scale") != "full":
        raise ValueError("refusing to persist a case whose V-7 did not run at the architecture's full scale")
    bundle = SealedCase.seal(res.package, res.report.proof, res.report.to_json())
    with open(path, "w", encoding="utf-8") as f:
        json.dump(json.loads(bundle.model_dump_json()), f, indent=1, sort_keys=True)
