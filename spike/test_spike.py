"""Phase 0.5 spike checks (pytest). Solver vs brute force; absence gating (T-2/T-3); corroboration
(T-4/T-5); feasible() on the cycle/triple (T-15); P-9 (T-16); negative fixtures (T-17/T-18);
the canonical world satisfies every admissible constraint; determinism.

    python -m pytest spike/test_spike.py -q
"""
from __future__ import annotations

import random

from spike.model import World, Actor, Loc, Seg, Prop, iv_minus, iv_shrink, check_physics
from spike.minds import (derive_knowledge, collusion_components, material_all, admissible, Know, Testimony,
                         Constraint)
from spike.minds import testimony_pool as layer0_pool  # (name must not start with `test`)
from spike.solve import _dp, feasible, contradiction, solve, cue_closure, robust_material
from spike.gen import toy_skeleton, vance_skeleton, plan, empty_world
from spike.fixtures import vance_world, cycle_claims, triple_claims
from spike.run_spike import evaluate, run_config, digest, MODES, PRIMARY, initial_named, skeleton


def tiny_world() -> World:
    w = World(actors={"x": Actor("x", "x", "living"), "y": Actor("y", "y", "living")},
              locs={"A": Loc("A", "A", True), "B": Loc("B", "B", True), "C": Loc("C", "C", False)},
              travel={("A", "B"): 1, ("B", "A"): 1, ("B", "C"): 1, ("C", "B"): 1, ("A", "C"): 3, ("C", "A"): 3},
              doors={}, perception=[], segments={}, events=[], t_inv=6, victim="", murderer="x", t_m=3, murder_loc="B",
              secrets={}, rels=[], evidence=[])
    return w


# ------------------------------------------------------------- basics
def test_intervals():
    assert iv_minus((0, 10), [(2, 4), (6, 8)]) == [(0, 2), (4, 6), (8, 10)]
    assert iv_shrink((0, 10), 2) == (2, 8) and iv_shrink((0, 4), 2) is None


def test_dijkstra_with_locked_door():
    w = tiny_world()
    assert w.travel_time("A", "C", 0) == 2  # via B
    w.doors[("B", "C")] = [(0, 5)]
    assert w.travel_time("A", "C", 0) == 3  # direct edge while the door is locked
    assert w.travel_time("A", "C", 5) == 2


def test_fact_index():
    w = tiny_world()
    w.segments = {"x": [Seg("A", 0, 3), Seg("B", 4, 6)], "y": [Seg("C", 0, 6)]}
    assert w.truth_value(Prop("At", "x", "A", (0, 3))) is True
    assert w.truth_value(Prop("At", "x", "A", (0, 4))) is False
    assert w.truth_value(Prop("NotAt", "x", "B", (0, 4))) is True
    assert w.truth_value(Prop("Did", "x", "B", (0, 6), ("touch", "o"))) is True


# ---------------------------------------------------- absence gating (I-34)
def test_absence_requires_awake_and_entrances(): # T-2, T-3
    w = tiny_world()
    w.segments = {"x": [Seg("A", 0, 6, attention=0.3)], "y": [Seg("C", 0, 6, attention=1.0)]}
    ks = derive_knowledge(w)
    assert not [k for k in ks if k.prop.kind in ("NotAt", "NoStranger")]  # asleep -> none; C has unwatched entrances -> none
    w.segments = {"x": [Seg("A", 0, 6, attention=1.0)], "y": [Seg("B", 0, 6, attention=1.0)]}
    ks = derive_knowledge(w)
    absent = [k for k in ks if k.who == "x" and k.prop.kind == "NotAt"]
    own = [k for k in ks if k.who == "x" and k.prop.kind == "At" and k.prop.actor == "x"][0]
    assert absent and all(k.reliability < own.reliability for k in absent)


# ------------------------------------------------ feasible() vs pairwise (T-15)
def test_feasible_rejects_cycle_and_pairwise_clean_triple():
    w, claims = cycle_claims()
    ok, core = feasible(w, claims)
    assert not ok and core
    w, claims = triple_claims()
    ok, core = feasible(w, claims)
    assert not ok and len(core) == 3
    for i, a in enumerate(claims):
        for b in claims[i + 1:]:
            assert contradiction(a.prop, b.prop, w) is None   # pairwise detector sees nothing
    assert feasible(w, claims[:2])[0] and feasible(w, claims[1:])[0] and feasible(w, [claims[0], claims[2]])[0]


# ------------------------------------------------------ DP vs brute force
def _brute(w: World, T, blocked, forced, exist):
    locs = sorted(w.locs)
    alphabet = locs + ["~"]

    def valid(seq):
        if seq[0] == "~":
            return False
        origin, depart = seq[0], 0
        for t in range(1, T):
            prev, cur = seq[t - 1], seq[t]
            if cur == "~":
                if prev != "~":
                    origin, depart = prev, t - 1
                continue
            if prev == "~":
                d = w.travel.get((origin, cur))
                if d is None or t - depart < d:
                    return False
            elif prev != cur and w.travel.get((prev, cur)) != 1:
                return False
        for t, L in forced.items():
            if seq[t] != L:
                return False
        if any((seq[t], t) in blocked for t in range(T) if seq[t] != "~"):
            return False
        return all(any((seq[t], t) in s for t in range(T)) for s in exist)

    def rec(seq):
        if len(seq) == T:
            return valid(seq)
        return any(rec(seq + [a]) for a in alphabet)
    return rec([])


def test_dp_matches_brute_force():
    w = tiny_world()
    rng = random.Random(7)
    T, locs = 6, sorted(w.locs)
    agree = 0
    for _ in range(250):
        blocked = {(rng.choice(locs), rng.randrange(T)) for _ in range(rng.randint(0, 5))}
        forced = {rng.randrange(T): rng.choice(locs) for _ in range(rng.randint(0, 2))}
        exist = [{(rng.choice(locs), t) for t in range(rng.randrange(T), T)} for _ in range(rng.randint(0, 2))]
        dp, _ = _dp(w, T, [(L, 0) for L in locs], blocked, forced, exist)
        assert dp == _brute(w, T, blocked, forced, exist), (blocked, forced, exist)
        agree += 1
    assert agree == 250


def test_solver_matches_brute_force_on_tiny_cases():
    """V-5 per-candidate exclusion == brute-force exclusion on tiny synthetic cases."""
    w = tiny_world()
    w.actors["v"] = Actor("v", "v", "victim")
    rng = random.Random(3)
    T, locs = 6, sorted(w.locs)
    for _ in range(120):
        cons = []
        for a in ("x", "y"):
            for i in range(rng.randint(0, 3)):
                kind = rng.choice(["At", "NotAt", "Did"])
                s = rng.randrange(T)
                e = rng.randint(s + 1, T)
                cons.append(Constraint(f"{a}{i}", f"{a}{i}", Prop(kind, a, rng.choice(locs), (s, e), ("touch", "o") if kind == "Did" else ()), 2, ()))
        cons.append(Constraint("W", "W", Prop("Died", "v", "B", (w.t_m, w.t_m + 1)), 3, ()))
        v = solve(w, cons, 2)
        for a in ("x", "y"):
            blocked, forced, exist = set(), {}, []
            bad = False
            for c in cons:
                if c.prop.actor != a:
                    continue
                if c.prop.kind == "At":
                    for t in range(*c.prop.iv):
                        if forced.get(t, c.prop.loc) != c.prop.loc:
                            bad = True
                        forced[t] = c.prop.loc
                elif c.prop.kind == "NotAt":
                    blocked |= {(c.prop.loc, t) for t in range(*c.prop.iv)}
                else:
                    exist.append({(c.prop.loc, t) for t in range(*c.prop.iv)})
            if forced.get(w.t_m, "B") != "B":
                bad = True
            forced[w.t_m] = "B"
            expect_excluded = bad or not _brute(w, T, blocked, forced, exist)
            assert v.candidates[a]["excluded"] == expect_excluded, (cons, a)


# --------------------------------------------------- corroboration (T-4, T-5)
def _know(i, who, prop, events, obs_loc, obs_iv, g=0):
    return Know(i, who, prop, "CoPresence", tuple(events), obs_loc, obs_iv, 1.0, g, obs_iv[0])


def test_one_perception_cannot_self_corroborate_and_lover_chain_is_colluding():
    w = tiny_world()
    w.actors.update({"a": Actor("a", "a", "living"), "b": Actor("b", "b", "living"), "c": Actor("c", "c", "living")})
    w.segments = {a: [] for a in w.actors}
    # a claims x was in A during [0,6); b "corroborates" from the SAME provenance event -> not independent (T-4)
    ka = _know("ka", "a", Prop("At", "x", "A", (0, 6)), ["ev1"], "A", (0, 6))
    kb_same = _know("kb", "b", Prop("At", "x", "A", (0, 6)), ["ev1"], "A", (0, 6))
    mat = {"S:ka": Testimony("S:ka", ka), "S:kb": Testimony("S:kb", kb_same)}
    cons = admissible(w, mat, collusion_components(w), "tick")
    assert all(c.level == 1 for c in cons)
    # disjoint provenance, non-colluding -> L2
    kb = _know("kb", "b", Prop("At", "x", "A", (0, 6)), ["ev2"], "A", (0, 6))
    mat["S:kb"] = Testimony("S:kb", kb)
    cons = admissible(w, mat, collusion_components(w), "tick")
    assert any(c.level == 2 for c in cons)
    # T-5: a-b corroborate, b-c corroborate, a-c lovers -> a and c share a component; b too via a shared secret with c
    w.rels = [("a", "c", "lover")]
    from spike.model import Secret
    w.secrets = {"b": Secret("b", (50, 60), "affair", ("c",)), "c": Secret("c", (50, 60), "affair", ("b",))}
    comps = collusion_components(w)
    assert comps["a"] == comps["b"] == comps["c"]
    cons = admissible(w, mat, comps, "tick")
    assert all(c.level == 1 for c in cons)


# --------------------------------------------------- P-9 and negative fixtures
def test_negative_fixtures_rejected_in_every_mode():  # T-16, T-17, T-18
    for ver in ("v01", "v02"):
        w, extra = vance_world(ver)
        phys = check_physics(w)
        assert not [p for p in phys if not p.startswith("P-9")], phys
        if ver == "v02":
            assert any(p.startswith("P-9 E10") for p in phys)  # T-16: E10 has no temporal grounding
        for withhold, fix in MODES:
            r = evaluate(w, withhold, fix, extra_know=extra, want_core=False)
            v = r["verdict"]
            assert not v["unique"], (ver, withhold, fix, v["reasons"])
            assert "David" in v["survivors"]
            assert not v["outsider"]["excluded"] and v["outsider"]["path"]  # T-18: corridor reported
    w, extra = vance_world("v02")
    r = evaluate(w, "murderer_only", "segment", extra_know=extra, want_core=False)
    v = r["verdict"]
    assert set(v["survivors"]) == {"David", "Robert"}, v["survivors"]  # the hostile review's counter-model
    assert v["candidates"]["Margaret"]["excluded"] and v["candidates"]["Elena"]["excluded"]
    w, extra = vance_world("v01")
    r = evaluate(w, "murderer_only", "segment", extra_know=extra, want_core=False)
    assert "Margaret" in r["verdict"]["survivors"]  # lovers' alibi is colluding -> Margaret not excluded


# ------------------------------------------ the canonical world is a model
def test_canonical_world_satisfies_admissible_material_and_murderer_survives():
    for seed in range(1, 8):
        w = plan(toy_skeleton(), seed, 3)
        assert not w.meta.get("physics"), (seed, w.meta.get("physics"))
        know = derive_knowledge(w)
        assert all(w.truth_value(k.prop) is True for k in know if k.who != w.victim), seed
        for withhold, fix in MODES:
            cons = admissible(w, material_all(w, know, withhold), collusion_components(w), fix)
            assert all(w.truth_value(c.prop) is True for c in cons), seed
            v = solve(w, cons, 2)
            assert w.murderer in v.survivors, (seed, withhold, fix, v.reasons)
            hard = [c for c in cons if c.level >= 2]
            assert feasible(w, hard)[0]


def test_constructive_planner_is_physical_and_declared_structure_is_realised():
    for seed in range(1, 11):
        w = plan(toy_skeleton(), seed, 3, construct=True)
        assert not w.meta.get("physics"), (seed, w.meta.get("physics"))
        loc, s, e = w.meta["alibi_window"]
        for a in w.living():
            if a != w.murderer:
                assert all(w.loc_at(a, t) == loc for t in range(s, e)), (seed, a)
        assert any(ev.kind == "gatelog" for ev in w.evidence)


def test_layer0_pool_withholds_protected_knowledge():
    w = plan(toy_skeleton(), 2, 3)
    know = derive_knowledge(w)
    pool = layer0_pool(w, know, "layer0_all")
    sec = w.secrets[w.murderer]
    assert not any(t.k.who == w.murderer and sec.iv[0] <= t.k.acquired_at < sec.iv[1] for t in pool.values())
    assert not any(t.k.who == w.victim for t in pool.values())


def test_determinism():
    a = run_config("toy3", "toy", 3, *PRIMARY, seeds=[1, 2, 3])
    b = run_config("toy3", "toy", 3, *PRIMARY, seeds=[1, 2, 3])
    assert digest(a) == digest(b)


# ------------------------------------------------------------ v0.4 named tests (T-27 … T-34)
def test_T27_constructive_planner_yield_gate():
    rows = run_config("toy3C", "toy", 3, *PRIMARY, seeds=list(range(1, 11)), construct=True)
    passes = sum(r["stage"] == "pass" for r in rows)
    assert passes >= 3, [r["stage"] for r in rows]            # >= 30 % is the gate line; expected near 100 %
    assert all(r["structure"] for r in rows)                   # the realised EliminationStructure is recorded


def test_T28_presence_fixing_is_tick_level():
    w, extra = vance_world("v02")
    know = derive_knowledge(w) + extra
    comps = collusion_components(w)
    mat = material_all(w, know, "murderer_only")

    def level(fix, sound):
        cons = admissible(w, mat, comps, fix)
        return max(c.level for c in cons if c.prop.kind == "Heard" and c.prop.extra[0] == sound and c.sources[0] == "Elena")
    # Elena is fixed on the back steps over [67,73) (Robert's At, shrunk by 2). The argument [68,70) widens to
    # [66,72): NOT covered -> L1 at tick level, L2 under the segment reading. The blow [70,71) widens to [68,73):
    # covered -> L2 under both.
    assert level("tick", "argument") == 1 and level("segment", "argument") == 2
    assert level("tick", "struggle") == 2 and level("segment", "struggle") == 2
    v = evaluate(w, "murderer_only", "tick", extra_know=extra, want_core=False)["verdict"]
    assert v["candidates"]["Elena"]["excluded"]                 # her own presence IS fixed over the murder tick


def test_T29_layer0_fixpoint():
    # Literal vance_v02: Robert's glow sighting is acquired inside HIS protected interval and Robert is never
    # excluded (corridor), so round 0 is already the fixpoint and all four survive.
    w, extra = vance_world("v02")
    know = derive_knowledge(w) + extra
    comps = collusion_components(w)
    mat, cracked, rounds = robust_material(w, know, comps, "tick")
    assert cracked == set() and rounds == 0
    assert len(solve(w, admissible(w, mat, comps, "tick"), 2).survivors) == 4
    # The mechanism firing: a constructive 4-living toy case where one innocent X is given a secret over the
    # alibi window. Round 0 withholds X's own knowledge, but the two other innocents fix each other and their
    # co-presence claims about X are L2, so X is excluded; round 1 cracks X's secret (cracked={X}, rounds=1);
    # the case stays unique at the fixpoint.
    from spike.model import Secret
    w = plan(toy_skeleton(), 1, 4, construct=True)
    X = next(a for a in w.living() if a != w.murderer and a not in w.secrets)
    w.secrets[X] = Secret(X, (w.t_m - 8, w.t_m + 8), "solo")
    know = derive_knowledge(w)
    comps = collusion_components(w)
    r0 = solve(w, admissible(w, material_all(w, know, "layer0_all"), comps, "tick"), 2)
    assert r0.candidates[X]["excluded"]
    assert not any(t.k.who == X and w.t_m - 8 <= t.k.acquired_at < w.t_m + 8 for t in material_all(w, know, "layer0_all").values() if hasattr(t, "k"))
    mat, cracked, rounds = robust_material(w, know, comps, "tick")
    assert X in cracked and rounds == 1   # the red herring, also excluded, is cracked in the same round
    assert any(t.k.who == X and w.t_m - 8 <= t.k.acquired_at < w.t_m + 8 for t in mat.values() if hasattr(t, "k"))
    assert solve(w, admissible(w, mat, comps, "tick"), 2).unique


def test_T30_sustained_identified_sighting_grounds_universal_At():
    w = tiny_world()
    w.perception = [("A", "B", "sight", 0.7)]
    w.segments = {"x": [Seg("A", 0, 6)], "y": [Seg("B", 1, 5)]}
    ks = derive_knowledge(w)
    at = [k for k in ks if k.who == "x" and k.prop.kind == "At" and k.prop.actor == "y"]
    assert at and at[0].prop.iv == (1, 5) and at[0].source == "Witnessed" and at[0].g == 2
    assert not [k for k in ks if k.who == "x" and k.prop.kind == "Saw"]
    w2, _ = vance_world("v02")
    heard = [k for k in derive_knowledge(w2) if k.who == "Elena" and k.prop.kind == "Heard"]
    assert heard and all(k.obs_iv == (65, 75) for k in heard)   # observer's presence segment, not the perception run


def test_T31_P2_half_open_correction():
    w = tiny_world()
    p2 = lambda: [p for p in check_physics(w) if p.startswith("P-2")]
    w.segments = {"x": [Seg("A", 0, 5), Seg("B", 5, 8)]}          # last tick in A is 4; B at 5 = 4 + travel(1): valid
    assert not p2()
    w.segments = {"x": [Seg("A", 0, 5), Seg("C", 6, 8)]}          # A->C needs 2 (via B): 4 + 2 = 6: valid
    assert not p2()
    w.segments = {"x": [Seg("A", 0, 5), Seg("C", 5, 8)]}          # arrives one tick early
    assert p2()
    wv, _ = vance_world("v02")
    assert not [p for p in check_physics(wv) if p.startswith("P-2")]   # §29.1 timetable passes


def test_T32_containment_device_must_be_cued():
    w = plan(vance_skeleton(), 5, 4, construct=True)
    know = derive_knowledge(w)
    mat = material_all(w, know, "layer0_all")
    with_ext = cue_closure(w, mat, initial_named(w, True))
    without = cue_closure(w, mat, initial_named(w, False))
    assert "E_gate_Gazebo" in with_ext and "E_gate_Gazebo" not in without


def test_T33_routes_never_transit_private_rooms():
    wv = empty_world(vance_skeleton())
    assert "Study" not in wv.route("Hall", "Gazebo", 0)[1:-1]
    for kind, n in (("toy", 3), ("vance", 4)):
        for seed in range(1, 21):
            w = plan(skeleton(kind), seed, n, construct=True)
            assert not w.meta.get("physics"), (kind, seed)
            for a, segs in w.segments.items():
                assert not any(s.loc == w.murder_loc and s.event_id.startswith("hop:") for s in segs), (kind, seed, a)


def test_T34_opportunity_pin_by_construction():
    for seed in range(1, 11):
        w = plan(toy_skeleton(), seed, 3, construct=True)
        r = evaluate(w, *PRIMARY, want_core=False)
        assert r["opportunity_pin"], seed                      # the trace's `requires` witness is presence-fixed
