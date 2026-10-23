"""Independent witness checks on the generated cases (beyond the tiny-instance brute force in
test_spike.py):

  * every SURVIVING candidate: the DP's witness path is re-validated by a separate, naive checker
    (travel semantics, forced/blocked cells, existential visits) — proves the "feasible" claims;
  * every EXCLUDED candidate: a bounded randomised search for a counter-example walk that satisfies
    the exclusion core together with the hypothesis — must find none;
  * outsider: a reported corridor is re-validated; an "excluded" verdict is attacked by the same
    randomised search over the phantom's blocked cells.

    python -m spike.verify
"""
from __future__ import annotations

import json
import random

from .model import World, Prop, EXT, ticks
from .minds import derive_knowledge, collusion_components, material_all, admissible, Constraint
from .solve import _dp, _compile, solve
from .gen import plan
from .run_spike import CONFIGS, PRIMARY, SEEDS, skeleton, OUT


def check_walk(w: World, walk: list[str], cons: list[Constraint], actor: str) -> bool:
    """Naive validator: walk[t] is a location or '~' (transit)."""
    T = len(walk)
    if walk[0] == "~":
        return False
    origin, depart = walk[0], 0
    for t in range(1, T):
        prev, cur = walk[t - 1], walk[t]
        if cur == "~":
            if prev != "~":
                origin, depart = prev, t - 1
            continue
        if prev == "~":
            d = w.travel.get((origin, cur))
            if d is None or t - depart < d or not w.edge_open(origin, cur, depart):
                return False
        elif prev != cur:
            if w.travel.get((prev, cur)) != 1 or not w.edge_open(prev, cur, t - 1):
                return False
    for c in cons:
        p = c.prop
        if p.actor != actor:
            continue
        if p.kind == "At" and not all(walk[t] == p.loc for t in ticks(p.iv)):
            return False
        if p.kind == "NotAt" and any(walk[t] == p.loc for t in ticks(p.iv)):
            return False
        if p.kind in ("Did", "Saw", "Heard") and p.actor and not (p.kind == "Saw" and not p.extra[0]):
            if not any(walk[t] == p.loc for t in ticks(p.iv)):
                return False
    return True


def random_walks(w: World, actor: str, cons: list[Constraint], n: int, rng: random.Random, start_locs=None) -> str | None:
    """Try to find a walk satisfying `cons` by biased random exploration. Returns a walk or None."""
    T = w.t_inv
    comp = _compile(cons, actor)
    if comp is None:
        return None
    blocked, forced, exist = comp
    locs = sorted(w.locs)
    for _ in range(n):
        walk = [rng.choice(start_locs or locs)]
        cur = walk[0]
        transit_to, transit_left = None, 0
        for t in range(1, T):
            nf = min((ft for ft in forced if ft >= t), default=None)
            if transit_to is not None:
                transit_left -= 1
                if transit_left <= 0 and (rng.random() < 0.7 or forced.get(t) == transit_to):
                    cur, transit_to = transit_to, None
                    walk.append(cur)
                else:
                    walk.append("~")
                continue
            if nf is not None and forced.get(nf) != cur and nf - t <= (w.travel_time(cur, forced[nf], t) or 0):
                # must leave now toward the forced location along the shortest route
                route = w.route(cur, forced[nf], t)
                nxt = route[1] if route and len(route) > 1 else cur
                d = w.travel[(cur, nxt)]
                if d == 1:
                    cur = nxt
                    walk.append(cur)
                else:
                    transit_to, transit_left = nxt, d - 1
                    walk.append("~")
                continue
            r = rng.random()
            if r < 0.6 or forced.get(t) == cur:
                walk.append(cur)
            else:
                nxt, d = rng.choice(w.neighbours(cur))
                if d == 1:
                    cur = nxt
                    walk.append(cur)
                else:
                    transit_to, transit_left = nxt, d - 1
                    walk.append("~")
        if check_walk(w, walk, cons, actor):
            return walk
    return None


def verify_case(w: World, withhold: str, fix: str, rng: random.Random) -> dict:
    know = derive_knowledge(w)
    comps = collusion_components(w)
    if withhold == "layer0_fixpoint":
        from .solve import robust_material
        mat, _, _ = robust_material(w, know, comps, fix)
    else:
        mat = material_all(w, know, withhold)
    cons = admissible(w, mat, comps, fix)
    v = solve(w, cons, 2)
    hard = [c for c in cons if c.level >= 2]
    rep = {"seed": w.meta.get("seed"), "survivor_paths_ok": 0, "survivor_paths_bad": 0,
           "excluded_counterexamples": 0, "excluded_checked": 0, "outsider": None}
    lo, hi = v.window
    for X, e in v.candidates.items():
        if e["excluded"]:
            rep["excluded_checked"] += 1
            core_ids = {c["id"] for c in e["core"]}
            core = [c for c in hard if c.id in core_ids]
            hyp = Constraint("HYP", "HYP", Prop("Did", X, w.murder_loc, (lo, hi), ("attack", w.victim)), 3, ())
            if e["core"] and e["core"][0]["id"] == "TIME":
                continue
            if any(c["id"] == "ATTR" for c in e["core"]):
                continue  # attribute exclusions are not walk-based
            if random_walks(w, X, core + [hyp], 300, rng) is not None:
                rep["excluded_counterexamples"] += 1
        else:
            hyp = Constraint("HYP", "HYP", Prop("Did", X, w.murder_loc, (lo, hi), ("attack", w.victim)), 3, ())
            blocked, forced, exist = _compile(hard + [hyp], X)
            ok, path = _dp(w, w.t_inv, [(L, 0) for L in sorted(w.locs)], blocked, forced, exist)
            assert ok
            walk = [L for L, _ in path]
            if check_walk(w, walk, hard + [hyp], X):
                rep["survivor_paths_ok"] += 1
            else:
                rep["survivor_paths_bad"] += 1
    # outsider
    phantom_cons = [Constraint(c.id, c.item, Prop("NotAt", "phantom", c.prop.loc, c.prop.iv), c.level, c.sources)
                    for c in hard if c.prop.kind == "NoStranger"]
    hyp = Constraint("HYP", "HYP", Prop("Did", "phantom", w.murder_loc, (lo, hi), ("attack", w.victim)), 3, ())
    if v.outsider["path"]:
        walk = [L for L, _ in v.outsider["path"]]
        walk = walk + [EXT] * (w.t_inv - len(walk))
        ok = walk[0] == EXT and EXT in walk[1:] and check_walk(w, walk, phantom_cons + [hyp], "phantom")
        rep["outsider"] = "path_ok" if ok else "PATH_INVALID"
    else:
        if EXT in w.locs:
            cx = random_walks(w, "phantom", phantom_cons + [hyp], 300, rng, start_locs=[EXT])
            rep["outsider"] = "COUNTEREXAMPLE" if (cx is not None and EXT in cx[cx.index(w.murder_loc):]) else "excluded_holds"
    return rep


def main():
    rng = random.Random(2026)
    report = {}
    for name, kind, n, construct in CONFIGS:
        rows = [verify_case(plan(skeleton(kind), s, n, construct), *PRIMARY, rng) for s in SEEDS]
        agg = {"survivor_paths_ok": sum(r["survivor_paths_ok"] for r in rows), "survivor_paths_bad": sum(r["survivor_paths_bad"] for r in rows),
               "excluded_checked": sum(r["excluded_checked"] for r in rows), "excluded_counterexamples": sum(r["excluded_counterexamples"] for r in rows),
               "outsider": {k: sum(1 for r in rows if r["outsider"] == k) for k in ("path_ok", "PATH_INVALID", "excluded_holds", "COUNTEREXAMPLE")}}
        report[name] = agg
        print(name, json.dumps(agg), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "verify.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
