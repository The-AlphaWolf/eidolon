"""The seed study (§30 Phase 0.5 exit methodology, Phase 6 tests: "generation matrix — 2 skeletons ×
50 seeds"): attempt every seed ONCE, with no retry unless `retries` says so, and count the funnel by
validator stage. Low yield is reported, never hidden behind reseeding.

    python -m eidolon.gen.study --seeds 50            # both skeletons, 50 seeds each, no retry
    python -m eidolon.gen.study --seeds 50 --retries 3  # also report the bounded-retry yield
"""
from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor

from .pipeline import generate
from .skeletons import SKELETONS

# execution order of the funnel (V-5 runs before V-4/V-6: both need its proof core)
FUNNEL = (("planner_realised", "planner"), ("schema_valid", "V-0"), ("physically_valid", "V-1"),
          ("knowledge_sound", "V-2"), ("cover_valid", "V-3"), ("solver_unique", "V-5:unique"),
          ("proof_verified", "V-5:proof"), ("robust_to_distortions", "V-5:robust"),
          ("reachable_and_askable", "V-4"), ("fairness_valid", "V-6"), ("simulation_valid", "V-7"))


def _bucket(failed_at: str | None, problems: list) -> str | None:
    if failed_at != "V-5":
        return failed_at
    # the verifier re-runs the robustness sweep, so a distortion failure appears as a "proof does not verify" line too
    proof = [p for p in problems if "proof does not verify" in p and "stay uncorrected" not in p and "robustness" not in p]
    if proof:
        return "V-5:proof"
    if any("uniqueness fails" in p or "robustness" in p for p in problems):
        return "V-5:robust"
    return "V-5:unique"


def _one(args):
    sk, seed, retries, scale = args
    for r in range(retries + 1):
        s = seed if r == 0 else seed * 1000 + r
        res = generate(sk, s, **scale)
        if res.failed_at is None or res.failed_at not in ("planner", "V-1"):
            break
    return {"skeleton": sk, "seed": seed, "used_seed": s, "attempts": r + 1, "failed_at": _bucket(res.failed_at, res.problems),
            "problems": [p[:160] for p in res.problems[:2]], "seconds": round(res.seconds, 2),
            "package": res.package.seal if res.package and res.failed_at is None else None,
            "band": (res.report.metrics or {}).get("bands") if res.report else None,
            "metrics": res.report.metrics if res.report else None,
            "stage_seconds": {k: v.get("seconds") for k, v in (res.report.stages.items() if res.report else [])}}


def run(seeds: range, skeletons=None, retries: int = 0, workers: int | None = None, bluffs: int | None = None,
        odd: int | None = None) -> dict:
    """`bluffs`/`odd` default to the architecture's full V-7 scale; CI passes a reduced one (such cases cannot seal)."""
    skeletons = skeletons or sorted(SKELETONS)
    scale = {k: v for k, v in (('bluffs', bluffs), ('odd', odd)) if v is not None}
    jobs = [(sk, s, retries, scale) for sk in skeletons for s in seeds]
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers or max(1, (os.cpu_count() or 2) - 1)) as ex:
        rows = list(ex.map(_one, jobs, chunksize=1))
    out = {"seeds": [seeds.start, seeds.stop], "retries": retries, "wall_seconds": round(time.perf_counter() - t0, 1), "by_skeleton": {}}
    for sk in skeletons:
        mine = [r for r in rows if r["skeleton"] == sk]
        order = [k for _, k in FUNNEL]
        reached = {k: 0 for k in order}
        failed = {}
        for r in mine:
            idx = order.index(r["failed_at"]) if r["failed_at"] in order else len(order)
            for k in order[:idx]:
                reached[k] += 1
            if r["failed_at"]:
                failed[r["failed_at"]] = failed.get(r["failed_at"], 0) + 1
        n = len(mine)
        sealed = [r for r in mine if r["failed_at"] is None]
        in_band = [r for r in sealed if r["band"] and all(v == SKELETONS[sk].difficulty for v in r["band"].values() if v)]
        out["by_skeleton"][sk] = {
            "attempted": n, "sealed": len(sealed), "yield": round(len(sealed) / n, 3) if n else 0,
            "passed_stage": {name: reached[k] for name, k in FUNNEL}, "failed_at": failed,
            "in_band_of_sealed": len(in_band), "attempts_used": sum(r["attempts"] for r in mine),
            "seconds_mean": round(sum(r["seconds"] for r in mine) / n, 2) if n else 0,
            "example_failures": [{"seed": r["seed"], "stage": r["failed_at"], "why": r["problems"]}
                                 for r in mine if r["failed_at"]][:6]}
    out["rows"] = rows
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=50)
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--retries", type=int, default=0)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    res = run(range(a.start, a.start + a.seeds), retries=a.retries, workers=a.workers)
    slim = {k: v for k, v in res.items() if k != "rows"}
    print(json.dumps(slim, indent=1))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1)


if __name__ == "__main__":
    main()
