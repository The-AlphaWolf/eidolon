"""Phase 0.5 spike runner: 20 seeds x {toy 3 suspects, toy 4 suspects, Vance layout} x 4 semantic
modes; negative fixtures; determinism; solver-produced golden case with exclusion chains.

    python -m spike.run_spike            # full run (writes spike/out/*.json, cases/*.json)
    python -m spike.run_spike --quick    # 5 seeds, primary config only
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

from .model import World, Evidence, check_physics
from .gen import toy_skeleton, vance_skeleton, plan, Skeleton
from .minds import derive_knowledge, collusion_components, material_all, admissible, Testimony
from .solve import solve, proof_core, cue_closure, feasible, contradiction, robust_material
from .fixtures import vance_world, cycle_claims, triple_claims

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "spike" / "out"
CASES = ROOT / "cases"
# withhold: layer0_fixpoint (I-45, v0.4 rule) | layer0_all (v0.3 literal, round 0 only) | murderer_only (all innocents cracked)
# fix:      tick (I-44, v0.4 rule) | segment (the reading §29.1 v0.3 practised; sensitivity only)
MODES = [("layer0_fixpoint", "tick"), ("layer0_all", "tick"), ("layer0_all", "segment"), ("murderer_only", "tick"), ("murderer_only", "segment")]
PRIMARY = ("layer0_fixpoint", "tick")
SEEDS = list(range(1, 21))
CONFIGS = [("toy3", "toy", 3, False), ("toy4", "toy", 4, False), ("vance4", "vance", 4, False),
           ("toy3C", "toy", 3, True), ("toy4C", "toy", 4, True), ("vance4C", "vance", 4, True)]  # C = R-B constructive planner
FAIRNESS = 2


def skeleton(kind: str) -> Skeleton:
    return toy_skeleton() if kind == "toy" else vance_skeleton()


def hhmm(t: int) -> str:
    return f"{21 + t // 60:02d}:{t % 60:02d}"


def evaluate(w: World, withhold: str, fix: str, extra_know=(), want_core: bool = True, check_outsider: bool = True) -> dict:
    out = {"seed": w.meta.get("seed"), "murderer": w.murderer, "t_m": w.t_m, "planner_error": w.meta.get("planner_error"),
           "physics": w.meta.get("physics", check_physics(w)), "mode": [withhold, fix], "outsider_checked": check_outsider}
    if out["planner_error"] or [v for v in out["physics"] if not v.startswith("P-9")]:
        out["stage"] = "V-1 planner/physics"
        return out
    know = derive_knowledge(w) + list(extra_know)
    comps = collusion_components(w)
    if withhold == "layer0_fixpoint":
        mat, cracked, rounds = robust_material(w, know, comps, fix, FAIRNESS, check_outsider)
        out["fixpoint"] = {"cracked": sorted(cracked), "rounds": rounds}
    else:
        mat = material_all(w, know, withhold)
    cons = admissible(w, mat, comps, fix)
    v = solve(w, cons, FAIRNESS, check_outsider)
    out.update({"n_knowledge": len(know), "n_items": len(mat), "n_testimony": sum(isinstance(i, Testimony) for i in mat.values()),
                "verdict": v.to_json(), "collusion": comps, "structure": w.meta.get("structure"),
                "opportunity_pin": any(c.level >= FAIRNESS and c.prop.kind == "Did" and c.prop.actor == w.murderer
                                       and c.prop.loc == w.murder_loc for c in cons)})
    if not v.unique:
        if w.murderer not in v.survivors:
            out["stage"] = "BUG"
        elif not v.outsider["excluded"] and len(v.survivors) == 1 and len(v.time_bins) <= 1:
            out["stage"] = "V-5 outsider only"
        elif len(v.survivors) > 1:
            out["stage"] = "V-5 multiple survivors"
        else:
            out["stage"] = "V-5 time under-determined"
        return out
    if not want_core:
        out["stage"] = "unique"
        return out
    core = proof_core(w, mat, comps, fix, FAIRNESS, check_outsider)
    initial = initial_named(w)
    depth = cue_closure(w, mat, initial)
    cued = all(i in depth for i in core)
    closure = {i: mat[i] for i in depth}
    closure_unique = solve(w, admissible(w, closure, comps, fix), FAIRNESS, check_outsider).unique
    frag = {}
    for X, e in v.candidates.items():
        if e["excluded"]:
            abs_cons = [c for c in e["core"] if c["prop"].startswith("(NotAt") or c["prop"].startswith("(NoStranger")]
            frag[X] = {"absence_constraints": len(abs_cons), "of": len(e["core"]) - 1,
                       "absence_sources": sorted({s for c in abs_cons for s in c.get("sources", [])})}
    out.update({"proof_core": core, "core_depths": {i: depth.get(i) for i in core}, "fully_cued": cued,
                "cued_depth": max(depth[i] for i in core) if cued and core else None,
                "cue_closure_unique": closure_unique, "n_cued_items": len(depth), "fragility": frag,
                "core_render": [render_item(mat[i], w) for i in core]})
    out["stage"] = "pass" if (cued and closure_unique) else ("V-4 proof core not fully cued" if not cued else "V-4 cue closure not unique")
    return out


def initial_named(w: World, with_exterior: bool = True) -> set[str]:
    """§19.4 initial named set: victim, body, murder room, cast, and (I-47, v0.4) every exterior access."""
    s = {w.victim, w.murder_loc, "body"} | set(w.living())
    if with_exterior:
        s |= {l for l, x in w.locs.items() if x.exterior}
    return s


def render_item(it, w: World) -> dict:
    if isinstance(it, Evidence):
        return {"id": it.id, "kind": it.kind, "at": it.at, "implications": [str(i.prop) + (f" requires {list(i.requires)}" if i.requires else "") for i in it.implications]}
    k = it.k
    return {"id": it.id, "speaker": k.who, "prop": str(k.prop), "source": k.source, "observed_from": k.obs_loc,
            "while": [hhmm(k.obs_iv[0]), hhmm(k.obs_iv[1])], "reliability": k.reliability, "granularity_min": k.g}


def run_config(name: str, kind: str, n: int, withhold: str, fix: str, seeds=SEEDS, want_core=True, check_outsider=True,
               construct: bool = False) -> list[dict]:
    rows = []
    for seed in seeds:
        w = plan(skeleton(kind), seed, n, construct)
        r = evaluate(w, withhold, fix, want_core=want_core, check_outsider=check_outsider)
        r.update({"config": name, "trace": w.meta.get("trace"), "watch": w.meta.get("watch"), "pins": w.meta.get("pins"),
                  "secret_kind": w.meta.get("secret_kind"), "lovers": w.meta.get("lovers"), "construct": construct})
        rows.append(r)
    return rows


def attempts_within(kind: str, n: int, withhold: str, fix: str, base_seeds=SEEDS, k_max: int = 20, construct: bool = False) -> list[int | None]:
    """Phase-6 style: reseed up to k_max times per base seed; first attempt index that passes."""
    out = []
    for b in base_seeds:
        hit = None
        for k in range(k_max):
            w = plan(skeleton(kind), b * 1000 + k, n, construct)
            r = evaluate(w, withhold, fix)
            if r["stage"] == "pass":
                hit = k
                break
        out.append(hit)
    return out


def digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def summarize(rows: list[dict]) -> dict:
    stages = {}
    for r in rows:
        stages[r["stage"]] = stages.get(r["stage"], 0) + 1
    uniq = [r for r in rows if "verdict" in r and r["verdict"]["unique"]]
    return {"n": len(rows), "planner_ok": sum(r["stage"] != "V-1 planner/physics" for r in rows),
            "unique_L2": len(uniq), "unique_and_fully_cued": sum(r.get("fully_cued", False) for r in rows),
            "pass": sum(r["stage"] == "pass" for r in rows), "stages": stages,
            "opportunity_pin": sum(bool(r.get("opportunity_pin")) for r in rows),
            "outsider_open": sum(1 for r in rows if "verdict" in r and not r["verdict"]["outsider"]["excluded"]),
            "mean_L2L3": round(sum(sum(v for k, v in r["verdict"]["n_constraints"].items() if k in ("2", "3")) for r in rows if "verdict" in r) / max(1, len([r for r in rows if "verdict" in r])), 1),
            "mean_core_size": round(sum(len(r["proof_core"]) for r in uniq if "proof_core" in r) / max(1, len([r for r in uniq if "proof_core" in r])), 1),
            "seeds_pass": [r["seed"] for r in rows if r["stage"] == "pass"]}


def golden_json(w: World, r: dict, extra_know=()) -> dict:
    know = derive_knowledge(w) + list(extra_know)
    mat = material_all(w, know, r["mode"][0])
    return {
        "name": r.get("name"), "skeleton": w.meta.get("skeleton"), "seed": w.meta.get("seed"), "mode": r["mode"],
        "produced_by": "spike/run_spike.py (solver-selected; not hand-authored)",
        "actors": {a: {"role": x.role, "attrs": x.attrs} for a, x in w.actors.items()},
        "locations": {l: {"entrances_visible": x.entrances_visible, "exterior": x.exterior} for l, x in w.locs.items()},
        "travel": sorted([f"{a}-{b}:{d}" for (a, b), d in w.travel.items() if a < b]),
        "perception": w.perception,
        "murder": {"murderer": w.murderer, "victim": w.victim, "t_m": w.t_m, "time": hhmm(w.t_m), "location": w.murder_loc},
        "timeline": {a: [f"{s.loc} {hhmm(s.s)}-{hhmm(s.e)}" + (" (asleep)" if s.attention < 0.7 else "") for s in segs]
                     for a, segs in w.segments.items()},
        "events": [f"{e.kind} {e.actor} @{e.loc} {hhmm(e.t)}-{hhmm(e.iv[1])} {list(e.objects)}" for e in w.events],
        "secrets": {a: {"kind": s.kind, "protected": [hhmm(s.iv[0]), hhmm(s.iv[1])], "shared_with": list(s.shared_with)} for a, s in w.secrets.items()},
        "relationships": w.rels,
        "evidence": [render_item(e, w) for e in w.evidence],
        "verdict": r["verdict"],
        "exclusion_chains": {X: e["core"] for X, e in r["verdict"]["candidates"].items() if e["excluded"]},
        "outsider": r["verdict"]["outsider"],
        "proof_core": r.get("core_render"), "proof_core_cued_depths": r.get("core_depths"),
        "fully_cued": r.get("fully_cued"), "cue_closure_unique": r.get("cue_closure_unique"),
        "absence_fragility": r.get("fragility"),
        "knowledge_size": len(know), "material_size": len(mat),
    }


def fixtures_report() -> dict:
    rep = {}
    for ver in ("v01", "v02"):
        w, extra = vance_world(ver)
        rep[f"vance_{ver}_negative"] = {"physics": check_physics(w), "modes": {}}
        for withhold, fix in MODES:
            r = evaluate(w, withhold, fix, extra_know=extra, want_core=False)
            rep[f"vance_{ver}_negative"]["modes"][f"{withhold}/{fix}"] = {
                "rejected": not r["verdict"]["unique"], "survivors": r["verdict"]["survivors"],
                "outsider_path": r["verdict"]["outsider"]["path"], "reasons": r["verdict"]["reasons"],
                "exclusions": {X: [c["prop"] for c in e["core"]] for X, e in r["verdict"]["candidates"].items() if e["excluded"]},
                "n_constraints": r["verdict"]["n_constraints"]}
    w, claims = cycle_claims()
    ok, core = feasible(w, claims)
    pair = [(a.id, b.id, contradiction(a.prop, b.prop, w)) for i, a in enumerate(claims) for b in claims[i + 1:] if contradiction(a.prop, b.prop, w)]
    rep["transitive_alibi_cycle"] = {"feasible": ok, "core": [c.id + " " + str(c.prop) for c in core], "pairwise_hits": pair}
    w, claims = triple_claims()
    ok, core = feasible(w, claims)
    pair = [(a.id, b.id, contradiction(a.prop, b.prop, w)) for i, a in enumerate(claims) for b in claims[i + 1:] if contradiction(a.prop, b.prop, w)]
    rep["pairwise_clean_triple"] = {"feasible": ok, "core": [c.id + " " + str(c.prop) for c in core], "pairwise_hits": pair}
    return rep


def main(quick: bool = False):
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    CASES.mkdir(parents=True, exist_ok=True)
    seeds = SEEDS[:5] if quick else SEEDS
    configs = CONFIGS[:1] if quick else CONFIGS
    modes = [PRIMARY] if quick else MODES
    results = {"seeds": seeds, "modes": [f"{a}/{b}" for a, b in modes], "configs": {}, "timing_s": {}}
    for name, kind, n, construct in configs:
        results["configs"][name] = {}
        for withhold, fix in modes:
            t1 = time.time()
            rows = run_config(name, kind, n, withhold, fix, seeds, construct=construct)
            results["configs"][name][f"{withhold}/{fix}"] = {"summary": summarize(rows), "rows": rows}
            results["timing_s"][f"{name}/{withhold}/{fix}"] = round(time.time() - t1, 1)
            print(f"{name:8s} {withhold:14s}/{fix:8s} {json.dumps(results['configs'][name][f'{withhold}/{fix}']['summary'])}", flush=True)
    # sensitivity: outsider ASSUMED excluded (v0.2's authored exclusion) — how much of the loss is AC-9?
    if not quick:
        for name, kind, n, construct in configs:
            if construct:
                continue
            rows = run_config(name, kind, n, *PRIMARY, seeds, check_outsider=False, construct=construct)
            results["configs"][name]["outsider_assumed/" + "/".join(PRIMARY)] = {"summary": summarize(rows), "rows": rows}
            print(f"{name:8s} outsider ASSUMED {json.dumps(summarize(rows))}", flush=True)
    # attempts-within-20 (Phase-6 criterion) for the toy config, search and constructive planners
    if not quick:
        for label, construct in (("search", False), ("construct", True)):  # v0.3 baseline vs v0.4 planner
            t1 = time.time()
            att = attempts_within("toy", 3, *PRIMARY, construct=construct)
            results[f"attempts_within_20_toy3_{label}"] = {
                "first_pass_index": att, "seeds_with_a_pass": sum(a is not None for a in att),
                "mean_attempts_when_found": round(sum(a + 1 for a in att if a is not None) / max(1, sum(a is not None for a in att)), 2)}
            results["timing_s"][f"attempts_{label}"] = round(time.time() - t1, 1)
            print(f"attempts ({label}):", json.dumps(results[f"attempts_within_20_toy3_{label}"]), flush=True)
    # negative fixtures
    results["fixtures"] = fixtures_report()
    # determinism: same process twice, and a fresh process, on the primary toy config (3 seeds)
    a = run_config("toy3", "toy", 3, *PRIMARY, seeds=seeds[:3])
    b = run_config("toy3", "toy", 3, *PRIMARY, seeds=seeds[:3])
    proc = subprocess.run([sys.executable, "-c",
                           "import json,sys; from spike.run_spike import run_config, digest, PRIMARY; "
                           f"print(digest(run_config('toy3','toy',3,*PRIMARY,seeds={seeds[:3]})))"],
                          cwd=ROOT, capture_output=True, text=True)
    results["determinism"] = {"in_process_equal": digest(a) == digest(b), "digest": digest(a),
                              "fresh_process_digest": proc.stdout.strip(), "fresh_process_equal": proc.stdout.strip() == digest(a),
                              "stderr": proc.stderr[-500:]}
    print("determinism:", json.dumps(results["determinism"]), flush=True)
    # golden cases: first passing seed of the v0.4 constructive planner under the primary mode (I-43, I-48).
    # (The v0.3 search planner found none in 120 Vance seeds on 2026-09-02; it is no longer consulted here.)
    goldens = {}
    for name, kind, n, fname in [("toy3", "toy", 3, "toy_v03"), ("vance4", "vance", 4, "vance_v03")]:
        if quick and name != "toy3":
            continue
        chosen, tried, how = None, 0, None
        for construct in (True,):
            pool = list(seeds)
            for seed in pool:
                tried += 1
                w = plan(skeleton(kind), seed, n, construct)
                r = evaluate(w, *PRIMARY)
                if r["stage"] == "pass":
                    chosen, how = (w, r), ("construct" if construct else "search")
                    break
            if chosen:
                break
        if chosen:
            w, r = chosen
            r["name"], r["mode"] = fname, list(PRIMARY)
            g = golden_json(w, r)
            g["search"] = {"seeds_tried": tried, "planner": how, "mode": list(PRIMARY)}
            g["produced_by"] += f" — {how} planner, seed {w.meta['seed']}"
            (CASES / f"{fname}.json").write_text(json.dumps(g, indent=1, default=str))
            goldens[fname] = {"seed": w.meta["seed"], "planner": how, "mode": list(PRIMARY), "seeds_tried": tried, "path": f"cases/{fname}.json"}
        else:
            goldens[fname] = {"seed": None, "seeds_tried": tried, "note": "no passing case found"}
    results["golden"] = goldens
    # gate line (T-27): constructive planner, primary mode, all three layouts
    results["gate"] = {name: results["configs"][name]["/".join(PRIMARY)]["summary"]["pass"]
                       for name, _, _, construct in configs if construct and name in results["configs"]}
    results["gate"]["criterion"] = ">= 30% per config (expected near 100%); fixtures rejected; verify clean; deterministic; owner sign-off required"
    print("GATE (v0.4 planner, primary mode, pass/20):", json.dumps(results["gate"]), flush=True)
    results["timing_s"]["total"] = round(time.time() - t0, 1)
    (OUT / ("results_quick.json" if quick else "results.json")).write_text(json.dumps(results, indent=1, default=str))
    print("golden:", json.dumps(goldens))
    print("total s:", results["timing_s"]["total"])
    return results


if __name__ == "__main__":
    main(quick="--quick" in sys.argv)
