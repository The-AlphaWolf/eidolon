"""V-5: solvability and uniqueness (§19.5) — the deterministic constraint solver.

**Question answered.** Given only the material a detective could legally obtain under the
fairness level (`standard` = L3 ∪ L2, `hard-fair` = L3 alone), which `(murderer, time_bin)`
explanations remain possible?

**Search.** For each candidate the question is a per-actor reachability problem over
(location, tick), solved exactly by the production layered DP (`world.feasibility._search`);
deletion-minimal exclusion cores come from greedy re-solves. The domain is bounded and
enumerated, so the answer is exact within it — there is no heuristic anywhere.

**Bounded domain (what "unique" means here).**
  candidates : every interrogable non-victim actor  +  the Outsider as a REACHABILITY query
  location   : the body's location (skeletons here have one murder room)
  time       : the pinned window; if the admissible material leaves > MAX_WINDOW ticks the case is
               reported NOT unique ("no time pin"), never approximated
  methods    : one per skeleton (`MethodSpec`); `Accident`/`Suicide` (if a method admits them) and
               accomplice pairs are NOT modelled and FAIL CLOSED (I-15): the verdict is not unique.

**Sound vs complete.** SOUND: a verdict `unique=True` means every other candidate has a
deletion-minimal core that is infeasible under the DP AND under the independent oracle
(`proof.verify`), the outsider corridor is closed, and the survivor's own canonical presence
satisfies every admissible constraint. COMPLETE only over the bounded domain above: outside it
(accomplices, accident, > MAX_WINDOW) the solver answers "not unique", so it may reject a case a
richer model could prove unique, never the reverse.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from ..decision.secrets import SecretStore
from ..evidence.model import EvidenceStore
from ..world.case import Case
from ..world.feasibility import _search
from ..world.interval import Interval, intersect, ticks
from ..world.space import EXT
from ..world.state import presence
from .lattice import (
    Constraint, Item, Know, admissible, components, know_atoms, material, protected_intervals,
    testimony_pool,
)
from .package import BIN, MAX_WINDOW, CasePackage

LocTick = tuple[str, int]


@dataclass(frozen=True)
class Ctx:
    """Everything the solver reads from a package — and nothing else."""
    case: Case
    store: EvidenceStore
    secrets: SecretStore
    victim: str | None
    murder_loc: str | None
    atoms: tuple[Know, ...]
    protected: dict
    comps: dict
    admits: tuple[str, ...]
    accomplice: bool
    problems: tuple[str, ...]


def build_ctx(pkg: CasePackage) -> Ctx:
    case = pkg.case
    victims = sorted(a for a, x in case.actors.items() if x.role == "victim")
    problems: list[str] = []
    victim = victims[0] if len(victims) == 1 else None
    if len(victims) != 1:
        problems.append(f"expected exactly one victim, found {victims}")
    murder_loc = None
    if victim:
        segs = presence(case.events, victim)
        murder_loc = segs[-1][1] if segs else None
        if murder_loc is None:
            problems.append("the victim has no presence: the body has no location")
    secrets = SecretStore(pkg.secrets)
    return Ctx(case, EvidenceStore(pkg.evidence), secrets, victim, murder_loc, tuple(know_atoms(case)),
               protected_intervals(secrets), components(case, secrets), tuple(pkg.method.admits),
               any(r.rel_kind == "accomplice" for r in case.rels), tuple(problems))


# ------------------------------------------------------------------ per-actor feasibility
def compile_actor(cons: Iterable[Constraint], actor: str):
    """One actor's constraints as (blocked cells, forced tick->loc, existential cell sets), or
    None when two universal placements clash at a tick (trivially infeasible)."""
    blocked: set[LocTick] = set()
    forced: dict[int, str] = {}
    exist: list[set[LocTick]] = []
    for c in cons:
        if c.actor != actor:
            continue
        if c.kind == "At":
            for t in ticks(c.iv):
                if forced.get(t, c.loc) != c.loc:
                    return None
                forced[t] = c.loc
        elif c.kind == "NotAt":
            blocked |= {(c.loc, t) for t in ticks(c.iv)}
        elif c.kind in ("Exist", "Heard"):
            exist.append({(c.loc, t) for t in ticks(c.iv)})
    return blocked, forced, exist


def feasible_actor(ctx: Ctx, actor: str, cons: Iterable[Constraint], hyp: Iterable[Constraint] = ()):
    comp = compile_actor(list(cons) + list(hyp), actor)
    if comp is None:
        return False, None
    blocked, forced, exist = comp
    starts = [(L, 0) for L in sorted(ctx.case.locations)]
    return _search(ctx.case, ctx.case.t_investigation, starts, blocked, forced, exist)


def actor_core(ctx: Ctx, actor: str, cons: list[Constraint], hyp: list[Constraint]) -> list[Constraint]:
    """Deletion-minimal subset of `cons` that is infeasible together with `hyp`."""
    keep = [c for c in cons if c.actor == actor]
    assert not feasible_actor(ctx, actor, keep, hyp)[0]
    for c in list(keep):
        trial = [x for x in keep if x is not c]
        if not feasible_actor(ctx, actor, trial, hyp)[0]:
            keep = trial
    return keep


# ------------------------------------------------------------------ verdict
@dataclass
class Verdict:
    fairness: int
    window: Interval
    murder_loc: str | None
    candidates: dict = field(default_factory=dict)
    outsider: dict = field(default_factory=dict)
    survivors: list = field(default_factory=list)
    time_bins: list = field(default_factory=list)
    unique: bool = False
    reasons: list = field(default_factory=list)
    n_constraints: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {"fairness": self.fairness, "window": list(self.window), "murder_loc": self.murder_loc,
                "unique": self.unique, "survivors": self.survivors, "time_bins": self.time_bins,
                "reasons": self.reasons, "n_constraints": {str(k): v for k, v in sorted(self.n_constraints.items())},
                "candidates": self.candidates, "outsider": self.outsider}


def murder_window(ctx: Ctx, hard: list[Constraint]) -> Interval:
    lo, hi = 0, ctx.case.t_investigation
    for c in hard:
        if c.kind in ("Died", "Heard") and c.loc == ctx.murder_loc:
            lo, hi = max(lo, c.iv[0]), min(hi, c.iv[1])
    return lo, hi


def outsider_path(ctx: Ctx, hard: list[Constraint], window: Interval):
    """AC-9: a phantom starts at EXT, is in the murder room at some tick of `window`, and is
    back at EXT at the end, through no cell that admissible containment material blocks."""
    if EXT not in ctx.case.locations:
        return None
    blocked = {(c.loc, t) for c in hard if c.kind == "NoStranger" for t in ticks(c.iv)}
    goal = {(ctx.murder_loc, t) for t in ticks(window)}
    ok, path = _search(ctx.case, ctx.case.t_investigation, [(EXT, 0)], blocked, {}, [goal], goal=EXT)
    return path if ok else None


def outsider_blocked(hard: list[Constraint]) -> set[LocTick]:
    return {(c.loc, t) for c in hard if c.kind == "NoStranger" for t in ticks(c.iv)}


def solve(ctx: Ctx, cons: list[Constraint], fairness: int = 2, want_cores: bool = True) -> Verdict:
    """V-5 over an already-derived constraint list. Takes no `CanonicalSolution`: whether the
    survivor IS the intended murderer is `judge()`'s job, after the fact."""
    hard = [c for c in cons if c.level >= fairness]
    v = Verdict(fairness, (0, ctx.case.t_investigation), ctx.murder_loc)
    for c in cons:
        v.n_constraints[c.level] = v.n_constraints.get(c.level, 0) + 1
    v.reasons += list(ctx.problems)
    if ctx.victim is None or ctx.murder_loc is None:
        return v
    lo, hi = murder_window(ctx, hard)
    if hi <= lo:
        v.reasons.append("admissible material is contradictory about the murder time")
        return v
    v.window = (lo, hi)
    voices = {c.actor for c in hard if c.kind == "Heard" and c.loc == ctx.murder_loc and c.actor}
    for X in sorted(ctx.case.living_actors()):
        hyp = [Constraint("HYP", "HYP", "Exist", X, ctx.murder_loc, (lo, hi), 3)]
        entry: dict = {"excluded": False, "times": [], "core": []}
        if voices and X not in voices:
            bad = [c for c in hard if c.kind == "Heard" and c.loc == ctx.murder_loc and c.actor and c.actor != X][:1]
            entry.update(excluded=True, core=[{"kind": "VOICE", "by": c.id} for c in bad])
        elif not feasible_actor(ctx, X, hard, hyp)[0]:
            entry["excluded"] = True
            if want_cores:
                entry["core"] = [c.to_json() for c in actor_core(ctx, X, hard, hyp)]
        elif hi - lo > MAX_WINDOW:
            entry["times"] = list(range(lo, hi))
            entry["times_approx"] = True
        else:
            for t in range(lo, hi):
                h = [Constraint("HYP", "HYP", "Exist", X, ctx.murder_loc, (t, t + 1), 3)]
                if feasible_actor(ctx, X, hard, h)[0]:
                    entry["times"].append(t)
            if not entry["times"]:
                entry["excluded"] = True
                entry["core"] = [{"kind": "TIME"}]      # no single tick of the window admits the candidate
        v.candidates[X] = entry
    v.survivors = [X for X, e in v.candidates.items() if not e["excluded"]]
    path = outsider_path(ctx, hard, (lo, hi))
    v.outsider = {"excluded": path is None, "path": path,
                  "blocked": [[c.loc, list(c.iv), c.item] for c in hard if c.kind == "NoStranger"]}
    v.time_bins = sorted({t // BIN for X in v.survivors for t in v.candidates[X]["times"]})
    if len(v.survivors) != 1:
        v.reasons.append(f"{len(v.survivors)} living candidates survive: {v.survivors}")
    if not v.outsider["excluded"]:
        v.reasons.append("outsider corridor open")
    if len(v.time_bins) > 1:
        v.reasons.append(f"murder time under-determined across bins {v.time_bins}")
    for cls in ctx.admits:
        v.reasons.append(f"method admits {cls}, but no exclusion material for it is modelled (fail closed, I-15)")
    if ctx.accomplice:
        v.reasons.append("an accomplice relation is declared: pair candidates are not modelled (fail closed, I-15)")
    v.unique = (len(v.survivors) == 1 and v.outsider["excluded"] and len(v.time_bins) == 1
                and not ctx.admits and not ctx.accomplice)
    return v


def judge(pkg: CasePackage, v: Verdict) -> list[str]:
    """Compare a verdict with the generator's claim. The ONLY place `pkg.solution` is read."""
    sol, out = pkg.solution, []
    if v.survivors != [sol.murderer]:
        out.append(f"survivor {v.survivors} != canonical murderer {sol.murderer}")
    if v.murder_loc != sol.location:
        out.append(f"murder location {v.murder_loc} != canonical {sol.location}")
    if v.time_bins and sol.interval[0] // BIN not in v.time_bins:
        out.append(f"canonical murder time {sol.interval} is outside the surviving bins {v.time_bins}")
    return out


# ------------------------------------------------------------------ I-45 layer-0 fixpoint
def robust_trace(ctx: Ctx, fairness: int = 2):
    """§19.5 (I-45): round 0 withholds every secret-holder's protected-interval knowledge; an
    innocent excluded at the fairness level in round k has their secrets treated as cracked in
    round k+1; iterate to the fixpoint (monotone, <= |living| rounds). The murderer is never
    excluded, so never cracked — without the solver being told who it is.

    Returns `(material, cracked, rounds, trace)`; `trace` is one `{actor, round, core}` per cracked
    actor — the round whose material excluded them and the ITEMS that exclusion rests on, which the
    independent verifier re-checks against its own derivation of that round (I-57)."""
    cracked: frozenset[str] = frozenset()
    rounds = 0
    trace: list[dict] = []
    while True:
        mat = material(ctx.store.all(), testimony_pool(ctx.atoms, ctx.protected, cracked))
        cons = admissible(ctx.case, ctx.store, mat, ctx.comps, ctx.victim)
        v = solve(ctx, cons, fairness, want_cores=False)
        new = frozenset(X for X, e in v.candidates.items()
                        if e["excluded"] and X in ctx.protected) - cracked
        if not new or rounds >= len(ctx.case.living_actors()):
            return mat, cracked, rounds, trace
        vc = solve(ctx, cons, fairness, want_cores=True)
        by_id = {c.id: c for c in cons}
        for X in sorted(new):
            items: set[str] = set()
            for c in vc.candidates[X]["core"]:
                if c.get("kind") == "VOICE":
                    items.add(by_id[c["by"]].item)
                elif "item" in c:
                    items.add(c["item"])
            trace.append({"actor": X, "round": rounds, "core": sorted(items)})
        cracked |= new
        rounds += 1


def robust_material(ctx: Ctx, fairness: int = 2):
    mat, cracked, rounds, _trace = robust_trace(ctx, fairness)
    return mat, cracked, rounds


def evaluate(ctx: Ctx, mat: dict[str, Item], fairness: int = 2, want_cores: bool = True) -> Verdict:
    return solve(ctx, admissible(ctx.case, ctx.store, mat, ctx.comps, ctx.victim), fairness, want_cores)


# ------------------------------------------------------------------ proof core
def proof_core(ctx: Ctx, mat: dict[str, Item], fairness: int = 2) -> list[str] | None:
    """Deletion-minimal subset of the material that preserves uniqueness (§19.5)."""
    def uniq(m):
        return evaluate(ctx, m, fairness, want_cores=False).unique
    if not uniq(mat):
        return None
    cons = admissible(ctx.case, ctx.store, mat, ctx.comps, ctx.victim)
    involved = {c.item for c in cons if c.level >= fairness} | {s for c in cons if c.level >= fairness for s in c.sources}
    keep = {k: v for k, v in mat.items() if k in involved}
    if not uniq(keep):
        keep = dict(mat)
    # chunked deletion (delta debugging): drop halves, quarters, ... then singles, so the result is
    # 1-minimal (no single item can go) but the run count is ~k log n, not n
    ids = sorted(keep)
    size = max(1, len(ids) // 2)
    while True:
        i = 0
        while i < len(ids):
            trial_ids = ids[:i] + ids[i + size:]
            if uniq({k: keep[k] for k in trial_ids}):
                ids = trial_ids
            else:
                i += size
        if size == 1:
            break
        size = max(1, size // 2)
    return sorted(ids)
