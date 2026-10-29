"""Phase 0.5 spike — solve slice.

feasible() (§13.2a, I-28) as a presence/travel DP; the V-5 solver (§19.5) as per-candidate
feasibility with deletion-minimal exclusion cores; outsider_excluded() as a reachability query
over (location, tick) cells (AC-9); proof-core extraction; the cued discovery closure (§19.4);
pairwise contradiction() (§13.2) for the n-ary fixture comparison.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .model import World, Prop, Evidence, EXT, Interval, iv_inter, ticks
from .minds import Constraint, admissible, material_all

BIN = 10  # time-bin width for "exactly one (murderer, method, time_bin)"


# ------------------------------------------------------------------ the DP
def _dp(w: World, T: int, starts: list[tuple[str, int]], blocked: set[tuple[str, int]],
        forced: dict[int, str], exist: list[set[tuple[str, int]]], goal: str | None = None):
    """Reachability over (state, tick, mask). Returns (ok, path) where path is a list of
    (loc|'~', tick) when ok. Movement: depart L at tick t, arrive L2 at tick >= t + d (lingering
    in transit is allowed; transit ticks may not be forced). Existential requirements are an
    unordered set (bitmask); `goal` (if given) must be the location at the final state."""
    full = (1 << len(exist)) - 1

    def mk(L, t, m):
        for i, s in enumerate(exist):
            if (L, t) in s:
                m |= 1 << i
        return m

    starts_at: dict[int, list[str]] = {}
    for L, t0 in starts:
        starts_at.setdefault(t0, []).append(L)
    layers: list[dict] = []
    cur: dict = {}
    for t in range(T):
        nxt: dict = {}
        if t > 0:
            for (st, m), _ in cur.items():
                if isinstance(st, tuple):  # ('~', dest, rem)
                    _, dest, rem = st
                    if forced.get(t) is None:
                        nxt.setdefault((("~", dest, max(0, rem - 1)), m), (st, m))
                    if rem == 0 and (dest, t) not in blocked and forced.get(t) in (None, dest):
                        nxt.setdefault((dest, mk(dest, t, m)), (st, m))
                else:
                    L = st
                    if (L, t) not in blocked and forced.get(t) in (None, L):
                        nxt.setdefault((L, mk(L, t, m)), (st, m))
                    for L2, d in w.neighbours(L):
                        if not w.edge_open(L, L2, t - 1):
                            continue
                        if d == 1 and (L2, t) not in blocked and forced.get(t) in (None, L2):
                            nxt.setdefault((L2, mk(L2, t, m)), (st, m))
                        if forced.get(t) is None:
                            nxt.setdefault((("~", L2, max(0, d - 2)), m), (st, m))
        for L in starts_at.get(t, []):
            if (L, t) not in blocked and forced.get(t) in (None, L):
                nxt.setdefault((L, mk(L, t, 0)), None)
        cur = nxt
        layers.append(cur)
        if not cur and t >= max(starts_at, default=0):
            return False, None
    for (st, m), _ in cur.items():
        if m == full and (goal is None or st == goal):
            path, t, key = [], T - 1, (st, m)
            while key is not None:
                path.append((key[0] if not isinstance(key[0], tuple) else "~", t))
                key = layers[t][key]
                t -= 1
            return True, path[::-1]
    return False, None


def _compile(cons: list[Constraint], actor: str):
    blocked, forced, exist = set(), {}, []
    for c in cons:
        p = c.prop
        if p.actor != actor:
            continue
        if p.kind == "At":
            for t in ticks(p.iv):
                if forced.get(t, p.loc) != p.loc:
                    return None  # two universal placements at once: trivially infeasible
                forced[t] = p.loc
        elif p.kind == "NotAt":
            blocked |= {(p.loc, t) for t in ticks(p.iv)}
        elif p.kind in ("Did", "Saw", "Heard") and p.actor:
            if p.kind == "Saw" and not p.extra[0]:
                continue
            exist.append({(p.loc, t) for t in ticks(p.iv)})
    return blocked, forced, exist


def _reach(w: World, T: int, blocked: set, forced: dict, reverse: bool = False, starts: list[str] | None = None) -> set[tuple[str, int]]:
    """Location-ticks on some valid walk from the start (or, reversed, to the end); no existential
    bookkeeping, so with existentials present it is a superset. Doors are ignored when reversed."""
    if reverse:
        blocked = {(L, T - 1 - t) for L, t in blocked}
        forced = {T - 1 - t: L for t, L in forced.items()}
    locs = starts if starts is not None else sorted(w.locs)
    seen: set[tuple[str, int]] = set()
    cur: set = set()
    for t in range(T):
        nxt: set = set()
        if t > 0:
            for st in cur:
                if isinstance(st, tuple):
                    _, dest, rem = st
                    if forced.get(t) is None:
                        nxt.add(("~", dest, max(0, rem - 1)))
                    if rem == 0 and (dest, t) not in blocked and forced.get(t) in (None, dest):
                        nxt.add(dest)
                else:
                    L = st
                    if (L, t) not in blocked and forced.get(t) in (None, L):
                        nxt.add(L)
                    for L2, d in w.neighbours(L):
                        if not reverse and not w.edge_open(L, L2, t - 1):
                            continue
                        if d == 1 and (L2, t) not in blocked and forced.get(t) in (None, L2):
                            nxt.add(L2)
                        if forced.get(t) is None:
                            nxt.add(("~", L2, max(0, d - 2)))
        else:
            for L in locs:
                if (L, 0) not in blocked and forced.get(0) in (None, L):
                    nxt.add(L)
                if reverse and forced.get(0) is None:
                    for r in range(3):
                        nxt.add(("~", L, r))
        cur = nxt
        for st in cur:
            if not isinstance(st, tuple):
                seen.add((st, T - 1 - t if reverse else t))
    return seen


def _survivor_times(w: World, X: str, hard: list[Constraint], window: Interval) -> tuple[list[int], bool]:
    """Ticks in `window` at which X can be in the murder room. Exact when <= 40 candidate ticks
    remain after forward/backward pruning; beyond that the (superset) pruning result is returned
    and flagged approximate — it then spans several bins and the case is not unique in time."""
    lo, hi = window
    blocked, forced, _ = _compile(hard, X)
    if hi - lo <= 40:
        cand = list(range(lo, hi))
    else:
        F = _reach(w, w.t_inv, blocked, forced)
        B = _reach(w, w.t_inv, blocked, forced, reverse=True)
        cand = [t for t in range(lo, hi) if (w.murder_loc, t) in F and (w.murder_loc, t) in B]
        if len(cand) > 40:
            return cand, True
    hyp = lambda t: Constraint("HYP", "HYP", Prop("At", X, w.murder_loc, (t, t + 1)), 3, ())
    return [t for t in cand if feasible_actor(w, X, hard, [hyp(t)])], False


def feasible_actor(w: World, actor: str, cons: list[Constraint], hyp: list[Constraint] = ()) -> bool:
    comp = _compile(list(cons) + list(hyp), actor)
    if comp is None:
        return False
    blocked, forced, exist = comp
    locs = sorted(w.locs)
    ok, _ = _dp(w, w.t_inv, [(L, 0) for L in locs], blocked, forced, exist)
    return ok


def actor_core(w: World, actor: str, cons: list[Constraint], hyp: list[Constraint]) -> list[Constraint]:
    """Deletion-minimal subset of `cons` that is infeasible together with `hyp`."""
    mine = [c for c in cons if c.prop.actor == actor]
    assert not feasible_actor(w, actor, mine, hyp)
    keep = list(mine)
    for c in list(mine):
        trial = [x for x in keep if x is not c]
        if not feasible_actor(w, actor, trial, hyp):
            keep = trial
    return keep


def feasible(w: World, claims: list[Constraint]) -> tuple[bool, list[Constraint]]:
    """§13.2a: joint feasibility of a claim set under presence/travel propagation."""
    core: list[Constraint] = []
    for a in sorted({c.prop.actor for c in claims if c.prop.actor}):
        if not feasible_actor(w, a, claims):
            core += actor_core(w, a, claims, [])
    return (not core), core


def contradiction(p: Prop, q: Prop, w: World) -> str | None:
    """Pairwise §13.2 rules (presence, negation, travel, existential-vs-universal). Used only to
    show what the pairwise detector misses relative to feasible()."""
    if p.actor != q.actor or not p.iv or not q.iv:
        return None
    if p.kind == "At" and q.kind == "At":
        if p.loc != q.loc and iv_inter(p.iv, q.iv):
            return "presence"
        if p.loc != q.loc:
            gap = max(q.iv[0] - (p.iv[1] - 1), p.iv[0] - (q.iv[1] - 1))
            tt = w.travel_time(p.loc, q.loc, 0)
            if tt is not None and gap < tt:
                return "travel"
    if {p.kind, q.kind} == {"At", "NotAt"} and p.loc == q.loc and iv_inter(p.iv, q.iv):
        return "negation"
    u, x = (p, q) if p.kind == "At" else (q, p)
    if u.kind == "At" and x.kind in ("Did", "Saw") and x.loc != u.loc and u.iv[0] <= x.iv[0] and x.iv[1] <= u.iv[1]:
        return "existential"
    return None


# ------------------------------------------------------------------ solver
@dataclass
class Verdict:
    fairness: int
    window: Interval
    candidates: dict[str, dict] = field(default_factory=dict)
    outsider: dict = field(default_factory=dict)
    survivors: list[str] = field(default_factory=list)
    time_bins: list[int] = field(default_factory=list)
    unique: bool = False
    reasons: list[str] = field(default_factory=list)
    n_constraints: dict[int, int] = field(default_factory=dict)

    def to_json(self):
        return {"fairness": self.fairness, "window": list(self.window), "unique": self.unique,
                "survivors": self.survivors, "time_bins": self.time_bins, "reasons": self.reasons,
                "n_constraints": {str(k): v for k, v in self.n_constraints.items()},
                "candidates": self.candidates, "outsider": self.outsider}


def outsider_path(w: World, cons: list[Constraint], window: Interval, fairness: int):
    """AC-9: a phantom enters from EXT at t=0, is in the murder room at some t in `window`,
    and is back at EXT by t_inv, through no cell excluded by admissible absence material."""
    if EXT not in w.locs:
        return None
    blocked = set()
    for c in cons:
        if c.level >= fairness and c.prop.kind == "NoStranger":
            blocked |= {(c.prop.loc, t) for t in ticks(c.prop.iv)}
    goal = {(w.murder_loc, t) for t in ticks(window)}
    reach_in = _reach(w, w.t_inv, blocked, {}, starts=[EXT]) & goal   # every murder-room cell the phantom can reach
    if not reach_in:
        return None
    # must exit afterwards: from ANY reachable goal cell, reach EXT by the end
    ok2, path2 = _dp(w, w.t_inv, sorted(reach_in), blocked, {}, [], goal=EXT)
    if not ok2:
        return None
    t_in = path2[0][1]
    ok1, path1 = _dp(w, w.t_inv, [(EXT, 0)], blocked, {}, [{(w.murder_loc, t_in)}])
    assert ok1
    pre = [(L, t) for L, t in path1 if t <= t_in]
    return pre + path2[1:]


def solve(w: World, cons: list[Constraint], fairness: int = 2, check_outsider: bool = True, want_cores: bool = True) -> Verdict:
    """V-5. `check_outsider=False` ASSUMES the outsider away (v0.2's authored exclusion) — a
    sensitivity setting only, never used for the gate. `want_cores=False` skips the deletion-minimal
    exclusion chains (used inside the proof-core loop, where only `unique` matters)."""
    hard = [c for c in cons if c.level >= fairness]
    v = Verdict(fairness, (0, w.t_inv))
    for c in cons:
        v.n_constraints[c.level] = v.n_constraints.get(c.level, 0) + 1
    # murder time window: L3 Died pins it; L2 Heard(struggle) windows narrow it
    lo, hi = 0, w.t_inv
    for c in hard:
        if c.prop.kind == "Died" and c.prop.loc == w.murder_loc:
            lo, hi = max(lo, c.prop.iv[0]), min(hi, c.prop.iv[1])
        if c.prop.kind == "Heard" and c.prop.loc == w.murder_loc and c.prop.extra[0] == "struggle":
            lo, hi = max(lo, c.prop.iv[0]), min(hi, c.prop.iv[1])
    if hi <= lo:
        v.reasons.append("admissible material is contradictory about the murder time")
        return v
    v.window = (lo, hi)
    voice =[c for c in hard if c.prop.kind == "Heard" and c.prop.loc == w.murder_loc and c.prop.extra[1]]
    for X in w.living():
        h = Constraint("HYP", "HYP", Prop("Did", X, w.murder_loc, (lo, hi), ("attack", w.victim)), 3, ())
        entry = {"excluded": False, "times": [], "core": []}
        bad_voice = [c for c in voice if w.actors[X].attrs.get("sex") != c.prop.extra[1]]
        if bad_voice:
            entry["excluded"] = True
            entry["core"] = [c.to_json() for c in bad_voice[:1]] + [{"id": "ATTR", "prop": f"(Attr {X} sex {w.actors[X].attrs.get('sex')})", "level": 3}]
        elif not feasible_actor(w, X, hard, [h]):
            entry["excluded"] = True
            if want_cores:
                entry["core"] = [c.to_json() for c in actor_core(w, X, hard, [h])] + [{"id": "HYP", "prop": str(h.prop), "level": 3}]
        else:
            entry["times"], entry["times_approx"] = _survivor_times(w, X, hard, (lo, hi))
            if not entry["times"]:
                entry["excluded"] = True
                entry["core"] = [{"id": "TIME", "prop": "no single tick in the window admits the candidate", "level": 3}]
        v.candidates[X] = entry
    v.survivors = [X for X, e in v.candidates.items() if not e["excluded"]]
    path = outsider_path(w, cons, (lo, hi), fairness) if check_outsider else None
    v.outsider = {"excluded": path is None, "path": path, "assumed": not check_outsider}
    v.time_bins = sorted({t // BIN for X in v.survivors for t in v.candidates[X]["times"]})
    if w.murderer not in v.survivors:
        v.reasons.append("SOLVER BUG: the true murderer is excluded by admissible material")
    if len(v.survivors) != 1:
        v.reasons.append(f"{len(v.survivors)} living candidates survive: {v.survivors}")
    if not v.outsider["excluded"]:
        v.reasons.append("outsider corridor open")
    if len(v.time_bins) > 1:
        v.reasons.append(f"murder time under-determined across bins {v.time_bins}")
    v.unique = (len(v.survivors) == 1 and v.survivors[0] == w.murderer and v.outsider["excluded"] and len(v.time_bins) == 1)
    return v


# ------------------------------------------------- layer-0 fixpoint (I-45)
def robust_material(w: World, know, comps: dict, fix: str, fairness: int = 2, check_outsider: bool = True):
    """§19.5 v0.4: round 0 withholds every secret-holder's protected-interval knowledge; an innocent
    excluded at the fairness level in round k has their non-murder secret treated as cracked in round
    k+1; iterate to the fixpoint. The murderer is never cracked. Returns (material, cracked, rounds)."""
    cracked: set[str] = set()
    rounds = 0
    while True:
        mat = material_all(w, know, "layer0_all", cracked)
        v = solve(w, admissible(w, mat, comps, fix), fairness, check_outsider, want_cores=False)
        new = {X for X, e in v.candidates.items() if e["excluded"] and X != w.murderer and X in w.secrets} - cracked
        if not new or rounds >= len(w.living()):
            return mat, cracked, rounds
        cracked |= new
        rounds += 1


# ------------------------------------------------------------- proof core
def proof_core(w: World, material: dict, comps: dict, fix: str, fairness: int = 2, check_outsider: bool = True) -> list[str] | None:
    """Deletion-minimal subset of material items preserving uniqueness (§19.5)."""
    uniq = lambda m: solve(w, admissible(w, m, comps, fix), fairness, check_outsider, want_cores=False).unique
    if not uniq(material):
        return None
    keep = dict(material)
    cons = admissible(w, keep, comps, fix)
    involved = {c.item for c in cons if c.level >= fairness} | {s for c in cons if c.level >= fairness for s in c.sources}
    involved = {i for i in involved if i in keep}
    trial = {k: v for k, v in keep.items() if k in involved}
    if uniq(trial):
        keep = trial
    for iid in sorted(keep):
        trial = {k: v for k, v in keep.items() if k != iid}
        if uniq(trial):
            keep = trial
    return sorted(keep)


# -------------------------------------------------------------- cue graph
def cue_closure(w: World, material: dict, initial_named: set[str]) -> dict[str, int]:
    """§19.4: BFS over items; an item is obtainable only when something already held names its
    target entity/location. Returns item -> cued depth."""
    named = set(initial_named)
    depth: dict[str, int] = {}
    d = 0
    while True:
        new = []
        for iid, it in sorted(material.items()):
            if iid in depth:
                continue
            if isinstance(it, Evidence):
                if it.at in named and all(x in named for x in it.discover_needs):
                    new.append((iid, set(it.names)))
            else:
                k = it.k
                ents = k.prop.entities()
                if k.who in named and (ents & named):
                    new.append((iid, ents | {k.obs_loc}))
        if not new:
            return depth
        d += 1
        for iid, names in new:
            depth[iid] = d
            named |= names
