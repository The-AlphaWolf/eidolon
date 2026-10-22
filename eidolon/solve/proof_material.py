"""The verifier's OWN derivation of the admissible material (I-57, ADR-28).

`proof.verify_proof` must not take the proof's word for what is admissible, so it re-derives the
hard constraint set from the sealed package with an implementation that shares NO code with
`lattice.py` / `solver.py` / `distort.py` (nor any constant of theirs — `BIN`/`MAX_WINDOW` live in
`package.py`). It is written from the specification text (§19.5 L3/L2/L1 rules, I-27 requires-chain
minimum, I-37 independence, I-44 tick-level fixing, I-45 layer-0 withholding), with a deliberately
different shape from the lattice: tick SETS, not interval runs; a recursive requirement resolver, not a
level table. Where it and the lattice disagree on a real package one of them has a bug, and
`tests/solve/test_rb3_verifier.py::test_differential_*` finds it. What it does share is Phase 1-3
ground truth that is not "the solver": perception facts (`world.perception`), P-9
(`evidence.grounding.established_interval`), the account resolver (`minds.accounts`), the collusion
edge definition (`SecretStore.collusion_edges`) and `Secret.protected_intervals()`.

Nothing here reads `pkg.solution`, a `load_bearing` flag, or a `Secret.kind`.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations

from ..decision.secrets import SecretStore
from ..evidence.grounding import established_interval
from ..evidence.model import EvidenceStore
from ..minds import accounts
from ..world.interval import contains, intersect, shrink, ticks, widen
from ..world.perception import derive_perception
from ..world.space import EXT
from ..world.state import death_ticks, loc_at, presence
from .oracle import oracle_feasible
from .package import BIN, MAX_WINDOW, CasePackage, TimeShift

MAX_SUBSETS_LOG2 = 10          # more than 2**10 distortion subsets is rejected, never sampled


@dataclass(frozen=True)
class DC:
    """One derived constraint. `observer` is set only on `NoStranger`."""
    item: str
    kind: str
    actor: str | None
    observer: str | None
    loc: str | None
    iv: tuple[int, int]
    level: int
    sources: tuple[str, ...]


def key_set(dc) -> set[tuple]:
    """Semantic identity of a constraint, independent of how an interval was cut into runs: a
    universal `At`/`NotAt` is a set of (place, tick) cells; everything else is its own span."""
    iv = (int(dc.iv[0]), int(dc.iv[1]))
    src = tuple(dc.sources)
    if dc.kind in ("At", "NotAt"):
        return {(dc.item, dc.kind, dc.actor, dc.loc, t, int(dc.level), src) for t in ticks(iv)}
    return {(dc.item, dc.kind, dc.actor, dc.observer, dc.loc, iv, int(dc.level), src)}


# ------------------------------------------------------------------ the physical candidate domain (I-59)
def victims_by_log(case) -> list[str]:
    dead = death_ticks(case.events)
    return sorted(a for a in case.actors if dead.get(a, case.t_investigation + 1) <= case.t_investigation)


def domain_problems(case) -> tuple[list[str], list[str], str | None]:
    """(candidate domain, problems, victim). The domain is PHYSICAL: everyone the CaseLog places
    somewhere who is still alive at `t_investigation`, minus the victim. Authored `role` labels are
    checked against it, never trusted: an `offstage` relabel cannot hide a viable suspect."""
    T = case.t_investigation
    dead = death_ticks(case.events)
    log_victims = victims_by_log(case)
    labelled = sorted(a for a, x in case.actors.items() if x.role == "victim")
    problems: list[str] = []
    if len(log_victims) != 1 or labelled != log_victims:
        problems.append(f"victim labels {labelled} disagree with the CaseLog's deaths {log_victims}")
    victim = log_victims[0] if len(log_victims) == 1 else None
    dom = sorted(a for a in case.actors
                 if presence(case.events, a) and dead.get(a, T + 1) > T and a != victim)
    if dom != sorted(case.living_actors()):
        problems.append(f"authored roles disagree with the CaseLog: physical candidate domain {dom} "
                        f"!= case.living_actors() {sorted(case.living_actors())}")
    return dom, problems, victim


def murder_loc(case, victim: str | None) -> str | None:
    if victim is None:
        return None
    segs = presence(case.events, victim)
    return segs[-1][1] if segs else None


# ------------------------------------------------------------------ testimony atoms
@dataclass(frozen=True)
class Atom:
    id: str
    who: str
    prop: object
    events: tuple[str, ...]
    obs_loc: str
    obs_iv: tuple[int, int]
    g: int


def _atoms(case, alive: set[str], shifts: tuple[TimeShift, ...]) -> list[Atom]:
    delta: dict[str, int] = defaultdict(int)
    for s in shifts:
        for k in s.know_ids:
            delta[k] += s.delta
    T = case.t_investigation
    out: list[Atom] = []
    for pf in derive_perception(case):
        if pf.observer not in alive:
            continue
        aid, prop = f"S:{pf.id}", pf.proposition
        if aid in delta:
            a, b = prop.interval
            a2, b2 = max(0, a + delta[aid]), min(T, b + delta[aid])
            if b2 <= a2:
                continue                   # shifted wholly out of the window: no claim at all
            prop = prop.model_copy(update={"interval": (a2, b2)})
        out.append(Atom(aid, pf.observer, prop, pf.provenance, pf.obs_location, pf.obs_interval, pf.granularity))
    return out


def _claim_window(a: Atom, T: int):
    """§13.2: a universal claim asserts only the part of its span that its granularity vouches for; an
    existential claim's span is blurred outward by that granularity."""
    if a.prop.kind in ("At", "NotAt"):
        return shrink(a.prop.interval, a.g)
    return widen(a.prop.interval, a.g, 0, T)


def _same_claim(p, q) -> bool:
    if p.kind != q.kind:
        return False
    if p.kind in ("At", "NotAt"):
        return (p.actor, p.location) == (q.actor, q.location)
    if p.kind == "Did":
        return (p.actor, p.location, p.action, p.object) == (q.actor, q.location, q.action, q.object)
    if p.kind == "Saw":
        return bool(p.identified and q.identified and p.subject == q.subject and p.location == q.location)
    if p.kind == "Heard":
        return (p.from_location, p.sound_kind, p.identified_actor) == (q.from_location, q.sound_kind, q.identified_actor)
    return False


def _maximal_runs(ts: set[int]) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    for t in sorted(ts):
        if runs and runs[-1][1] == t:
            runs[-1] = (runs[-1][0], t + 1)
        else:
            runs.append((t, t + 1))
    return runs


def _as_constraint(prop, item: str, level: int, sources: tuple[str, ...], victim: str | None, iv=None) -> DC | None:
    """The kinds the per-actor search can use; everything else (state, objects, relations,
    unidentified sightings) is dropped rather than approximated."""
    span = iv if iv is not None else getattr(prop, "interval", None)
    k = prop.kind
    if k in ("At", "NotAt"):
        return DC(item, k, prop.actor, None, prop.location, span, level, sources)
    if k == "Did":
        if prop.action == "Die" and prop.actor == victim and prop.location:
            return DC(item, "Died", prop.actor, None, prop.location, span, level, sources)
        return DC(item, "Exist", prop.actor, None, prop.location, span, level, sources) if prop.location else None
    if k == "Saw":
        if prop.subject == "nobody":
            return DC(item, "NoStranger", None, prop.observer, prop.location, span, level, sources)
        if prop.identified and prop.subject != "figure":
            return DC(item, "Exist", prop.subject, None, prop.location, span, level, sources)
        return None
    if k == "Heard":
        if prop.sound_kind == "attack" and prop.from_location:
            return DC(item, "Heard", prop.identified_actor, None, prop.from_location, span, level, sources)
        if prop.identified_actor and prop.from_location:
            return DC(item, "Exist", prop.identified_actor, None, prop.from_location, span, level, sources)
    return None


def protected_by_owner(pkg: CasePackage) -> dict[str, list[tuple[int, int]]]:
    out: dict[str, list] = defaultdict(list)
    for s in pkg.secrets:
        out[s.owner] += list(s.protected_intervals())
    return {o: v for o, v in out.items() if v}


def _components(pkg: CasePackage) -> dict[str, int]:
    adj: dict[str, set[str]] = {a: set() for a in pkg.case.actors}
    for edge in SecretStore(pkg.secrets).collusion_edges(pkg.case.rels):
        for a in edge:
            for b in edge:
                if a != b and a in adj and b in adj:
                    adj[a].add(b)
    comp: dict[str, int] = {}
    n = 0
    for a in sorted(adj):
        if a in comp:
            continue
        stack = [a]
        while stack:
            x = stack.pop()
            if x in comp:
                continue
            comp[x] = n
            stack.extend(adj[x] - set(comp))
        n += 1
    return comp


# ------------------------------------------------------------------ the derivation
def derive(pkg: CasePackage, cracked, *, only: set[str] | None = None,
           shifts: tuple[TimeShift, ...] = ()) -> tuple[list[DC], dict]:
    """Every admissible constraint, at every level, for the material `pkg` allows. Returns
    `(constraints, universe)`; `universe` is `{item id: "evidence"|"testimony"}` for the material
    that was ON THE TABLE (after the layer-0 withholding). `only` restricts the table to those items
    (the proof-core re-derivation)."""
    case, T = pkg.case, pkg.case.t_investigation
    alive, _p, victim = domain_problems(case)
    alive = set(alive)
    store = EvidenceStore(pkg.evidence)
    token_iv = accounts.token_intervals(case)
    prot = protected_by_owner(pkg)
    comp = _components(pkg)

    pool: dict[str, Atom] = {}
    for a in _atoms(case, alive, tuple(shifts)):
        withheld = a.who not in cracked and any(a.obs_iv[0] < hi and lo < a.obs_iv[1] for lo, hi in prot.get(a.who, ()))
        if not withheld and (only is None or a.id in only):
            pool[a.id] = a
    evs = {e.id: e for e in pkg.evidence if only is None or e.id in only}
    universe = {i: "evidence" for i in evs} | {i: "testimony" for i in pool}

    out: list[DC] = []
    ev_levels: dict[str, int] = defaultdict(int)       # best level an evidence item reached
    at_cells: dict[tuple[str, str], set[int]] = defaultdict(set)    # (actor, place) -> ticks an L3 log fixes
    at_by: dict[tuple[str, str], set[str]] = defaultdict(set)

    def p9(imp, ev) -> bool:
        span = getattr(imp.proposition, "interval", None)
        return span is None or contains(established_interval(imp, store, T, token_iv, ev.created_at), span)

    # --- L3: authentic physical evidence that needs nothing
    for eid in sorted(evs):
        ev = evs[eid]
        if not ev.authentic:
            continue
        for imp in ev.implications:
            if imp.requires or not p9(imp, ev):
                continue
            dc = _as_constraint(imp.proposition, eid, 3, (eid,), victim)
            if dc is None:
                continue
            out.append(dc)
            ev_levels[eid] = 3
            if dc.kind == "At":
                at_cells[(dc.actor, dc.loc)] |= set(ticks(dc.iv))
                at_by[(dc.actor, dc.loc)].add(eid)

    # --- testimony: L2 when the speaker's presence is fixed tick by tick, or the claim is corroborated
    claim = {a.id: _claim_window(a, T) for a in pool.values()}
    by_other: dict[str, list[Atom]] = defaultdict(list)
    for a in pool.values():
        by_other[a.who].append(a)
    atom_levels: dict[str, int] = defaultdict(int)
    for k in sorted(pool.values(), key=lambda a: a.id):
        cw = claim[k.id]
        if cw is None:
            continue
        s = k.who
        fixed = {t for t in at_cells.get((s, k.obs_loc), ()) if k.obs_iv[0] <= t < k.obs_iv[1]}
        fixers = set(at_by.get((s, k.obs_loc), ())) if fixed else set()
        direct: set[int] = set()
        for who, others in by_other.items():
            if who == s or comp.get(who) == comp.get(s):
                continue
            for r in others:
                if set(r.events) & set(k.events) or claim[r.id] is None:
                    continue
                if r.prop.kind == "At" and r.prop.actor == s and r.prop.location == k.obs_loc:
                    ov = intersect(claim[r.id], k.obs_iv)
                    if ov:
                        fixed |= set(ticks(ov))
                        fixers.add(r.id)
                if _same_claim(k.prop, r.prop):
                    ov = intersect(claim[r.id], cw)
                    if ov:
                        direct |= set(ticks(ov))
                        fixers.add(r.id)
        src_hi = (s,) + tuple(sorted(fixers))
        window = set(ticks(cw))
        if k.prop.kind in ("At", "NotAt"):
            sure = window & (fixed | direct)
            pieces = [(run, 2, src_hi) for run in _maximal_runs(sure)] + \
                     [(run, 1, (s,)) for run in _maximal_runs(window - sure)]
        elif direct:
            pieces = [(_maximal_runs(direct)[0], 2, src_hi)]
        elif window <= fixed:
            pieces = [(cw, 2, src_hi)]
        else:
            pieces = [(cw, 1, src_hi)]
        for run, level, src in pieces:
            dc = _as_constraint(k.prop, k.id, level, src, victim, iv=run)
            if dc is not None:
                out.append(dc)
                atom_levels[k.id] = max(atom_levels[k.id], level)

    # --- implications that depend on other material: the weakest link bounds the level (I-27)
    memo: dict[str, list[DC]] = {}

    def conditional(eid: str) -> list[DC]:
        if eid in memo:
            return memo[eid]
        memo[eid] = []                                  # a requirement cycle resolves to nothing
        found: list[DC] = []
        ev = evs.get(eid)
        if ev is not None and ev.authentic:
            for imp in ev.implications:
                if not imp.requires:
                    continue
                levels, chosen, ok = [], [], True
                for r in imp.requires:
                    if r in evs:
                        lv = max([ev_levels[r]] + [d.level for d in conditional(r)])
                        levels.append(lv)
                        chosen.append(r)
                        continue
                    hits = [a for a in accounts.atoms_of(case, r) if a in pool]
                    if not hits:
                        ok = False
                        break
                    best = max(hits, key=lambda a: (atom_levels.get(a, 0), a))
                    levels.append(atom_levels.get(best, 0))
                    chosen.append(best)
                if not ok or not p9(imp, ev):
                    continue
                level = min([3] + levels)
                if level >= 1:
                    dc = _as_constraint(imp.proposition, eid, level, (eid,) + tuple(chosen), victim)
                    if dc is not None:
                        found.append(dc)
        memo[eid] = found
        return found

    for eid in sorted(evs):
        out += conditional(eid)
    return out, universe


# ------------------------------------------------------------------ independent solving
def _compile(cons, actor: str):
    blocked, forced, exist = set(), {}, []
    for c in cons:
        if c.actor != actor:
            continue
        iv = (int(c.iv[0]), int(c.iv[1]))
        if c.kind == "At":
            for t in ticks(iv):
                if forced.get(t, c.loc) != c.loc:
                    return None
                forced[t] = c.loc
        elif c.kind == "NotAt":
            blocked |= {(c.loc, t) for t in ticks(iv)}
        elif c.kind in ("Exist", "Heard"):
            exist.append({(c.loc, t) for t in ticks(iv)})
    return blocked, forced, exist


class Oracle:
    """Feasibility questions answered by `oracle.oracle_feasible`, memoised on the actor's own
    constraint cells (a distortion subset only changes a few witnesses' atoms)."""

    def __init__(self, case):
        self.case, self.memo = case, {}

    def feasible(self, actor: str, cons, hyp) -> bool:
        mine = tuple(sorted((c.kind, c.loc, tuple(c.iv)) for c in cons if c.actor == actor))
        key = (actor, mine, hyp)
        if key not in self.memo:
            comp = _compile(list(cons) + [_Hyp(actor, *hyp)], actor)
            if comp is None:
                self.memo[key] = False
            else:
                blocked, forced, exist = comp
                starts = [(loc, 0) for loc in sorted(self.case.locations)]
                self.memo[key] = oracle_feasible(self.case, self.case.t_investigation, blocked, forced, exist, starts)
        return self.memo[key]

    def corridor(self, blocked_cells, loc, window) -> bool:
        if EXT not in self.case.locations:
            return False
        goal = {(loc, t) for t in ticks(window)}
        return oracle_feasible(self.case, self.case.t_investigation, blocked_cells, {}, [goal], [(EXT, 0)], goal=EXT)


@dataclass(frozen=True)
class _Hyp:
    actor: str
    loc: str
    iv: tuple[int, int]
    kind: str = "Exist"


@dataclass
class Solved:
    window: tuple[int, int]
    contradictory: bool
    candidates: dict            # X -> {"excluded", "how": VOICE|CONSTRAINTS|TIME|None, "times"}
    voices: set
    corridor: bool
    too_wide: bool

    @property
    def survivors(self) -> list[str]:
        return sorted(x for x, e in self.candidates.items() if not e["excluded"])

    @property
    def bins(self) -> list[int]:
        return sorted({t // BIN for x in self.survivors for t in self.candidates[x]["times"]})


def solve_independent(pkg: CasePackage, hard, dom: list[str], victim: str | None, oracle: Oracle) -> Solved:
    case, T = pkg.case, pkg.case.t_investigation
    mloc = murder_loc(case, victim)
    lo, hi = 0, T
    for c in hard:
        if c.kind in ("Died", "Heard") and c.loc == mloc:
            lo, hi = max(lo, c.iv[0]), min(hi, c.iv[1])
    if mloc is None or hi <= lo:
        return Solved((lo, hi), True, {}, set(), True, False)
    voices = {c.actor for c in hard if c.kind == "Heard" and c.loc == mloc and c.actor}
    cands: dict[str, dict] = {}
    too_wide = False
    for x in dom:
        if voices and x not in voices:
            cands[x] = {"excluded": True, "how": "VOICE", "times": []}
        elif not oracle.feasible(x, hard, (mloc, (lo, hi))):
            cands[x] = {"excluded": True, "how": "CONSTRAINTS", "times": []}
        elif hi - lo > MAX_WINDOW:
            too_wide = True
            cands[x] = {"excluded": False, "how": None, "times": []}
        else:
            times = [t for t in range(lo, hi) if oracle.feasible(x, hard, (mloc, (t, t + 1)))]
            cands[x] = ({"excluded": False, "how": None, "times": times} if times
                        else {"excluded": True, "how": "TIME", "times": []})
    blocked = {(c.loc, t) for c in hard if c.kind == "NoStranger" for t in ticks((c.iv[0], c.iv[1]))}
    return Solved((lo, hi), False, cands, voices, oracle.corridor(blocked, mloc, (lo, hi)), too_wide)


def is_unique(pkg: CasePackage, s: Solved) -> bool:
    accomplice = any(r.rel_kind == "accomplice" for r in pkg.case.rels)
    return bool(not s.contradictory and not s.too_wide and len(s.survivors) == 1 and not s.corridor
                and len(s.bins) == 1 and not pkg.method.admits and not accomplice)


# ------------------------------------------------------------------ the layer-0 fixpoint, re-derived
def fixpoint(pkg: CasePackage, dom, victim, fairness: int, oracle: Oracle):
    """I-45 recomputed: round 0 withholds every secret-holder's protected-interval knowledge; whoever
    the hard material EXCLUDES in round k has their secrets treated as cracked in round k+1.
    Returns `(cracked, rounds, trace, final_hard, final_universe)`."""
    owners = set(protected_by_owner(pkg))
    cracked: frozenset[str] = frozenset()
    rounds, trace = 0, []
    while True:
        cons, universe = derive(pkg, cracked)
        hard = [c for c in cons if c.level >= fairness]
        s = solve_independent(pkg, hard, dom, victim, oracle)
        new = frozenset(x for x, e in s.candidates.items() if e["excluded"] and x in owners) - cracked
        if not new or rounds >= len(dom):
            return cracked, rounds, trace, hard, universe
        for x in sorted(new):
            trace.append({"actor": x, "round": rounds, "how": s.candidates[x]["how"], "hard": hard,
                          "universe": universe, "window": s.window})
        cracked |= new
        rounds += 1


def relevant_distortions(pkg: CasePackage, cracked, base_cons, all_shift_cons) -> list[TimeShift]:
    seen = {c.item for c in base_cons} | {c.item for c in all_shift_cons}
    return [s for s in pkg.distortions if set(s.know_ids) & seen]


def distortion_subsets(relevant: list[TimeShift]):
    for r in range(len(relevant) + 1):
        for c in combinations(relevant, r):
            yield tuple(c)


# ------------------------------------------------------------------ the truth audit
def truth_audit(case, victim: str | None, c) -> str | None:
    """Is this admissible constraint TRUE in the canonical CaseLog? None if so, else why not."""
    ev, iv = case.events, (int(c.iv[0]), int(c.iv[1]))
    k = c.kind
    if k == "At":
        return None if all(loc_at(ev, c.actor, t) == c.loc for t in ticks(iv)) else "false At"
    if k == "NotAt":
        return None if all(loc_at(ev, c.actor, t) != c.loc for t in ticks(iv)) else "false NotAt"
    if k == "Exist":
        return None if any(loc_at(ev, c.actor, t) == c.loc for t in ticks(iv)) else "false existential"
    if k == "Died":
        d = death_ticks(ev).get(c.actor)
        return None if d is not None and iv[0] <= d < iv[1] else "false Died pin"
    if k == "Heard":
        hit = any(e.kind == "Attack" and e.location == c.loc and e.interval[0] < iv[1] and iv[0] < e.interval[1]
                  and (c.actor is None or e.actor == c.actor) for e in ev)
        return None if hit else "no attack (by that actor, if one is named) at that place and time"
    if k == "NoStranger":
        if c.observer is None:
            return "NoStranger names no observer"
        occupied = any(loc_at(ev, a, t) == c.loc for a in case.actors if a != c.observer for t in ticks(iv))
        return None if not occupied else "somebody other than the observer was in the 'empty' place"
    return f"unknown constraint kind {k!r}"
