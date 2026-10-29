"""Memory distortions and the distortion-SUBSET robustness run (§8.7, §19.5).

Phase 2 (`minds.memory.encode_memories`) assigns `time_compression` distortions: a memory is
recalled shifted by 1-20 minutes. A player corrects some distortions and not others, so the
states actually played are the MIXED ones; §19.5 therefore requires uniqueness for every SUBSET
of uncorrected distortions, not only the all-distorted extreme.

Model: an UNCORRECTED distortion replaces each testimony atom grounded in the distorted memory by
the shifted claim (same speaker, same observation segment, interval moved by `delta`). The
lattice then treats it like any other testimony — it can lose its L2 status, or, worse, assert
something FALSE at L2 — and the solver must still return exactly the same lone survivor.

Bounded domain: subsets are enumerated over the RELEVANT distortions (atoms yielding a constraint at
any level, base or shifted); more than MAX_ACTIVE of them is reported `bounded` and fails closed.
"""
from __future__ import annotations

from dataclasses import replace
from itertools import combinations

from ..minds import accounts
from ..minds.belief import form_beliefs
from ..minds.knowledge import propagate_knowledge
from ..minds.memory import encode_memories
from ..world.case import Case
from ..world.facts import FactIndex
from .lattice import Know, admissible, material, testimony_pool
from .package import TimeShift
from .solver import Ctx, solve

MAX_ACTIVE = 10


def derive_distortions(case: Case) -> list[TimeShift]:
    """Every `time_compression` distortion Phase 2 would assign, resolved to the testimony atoms
    (`Know.id`) its memory is grounded in. Deterministic (I-6): a function of the case alone."""
    store = propagate_knowledge(case)
    idx = FactIndex(case)
    out: list[TimeShift] = []
    for actor in sorted(case.living_actors()):
        beliefs = form_beliefs(actor, store, case, idx).beliefs
        bmap = {b.id: b for b in beliefs}
        for m in encode_memories(actor, list(beliefs), store, case):
            for d in m.distortions:
                if d.field != "interval" or d.cause != "time_compression":
                    continue
                knows = tuple(sorted({a for bid in m.content for g in bmap[bid].grounds
                                      if (a := accounts.atom_of_entry(case, store, g)) is not None}))
                out.append(TimeShift(memory=m.id, actor=actor, delta=d.recalled_value[0] - d.true_value[0], know_ids=knows))
    return out


def apply_shifts(atoms, shifts: list[TimeShift], T: int) -> list[Know]:
    by_id: dict[str, int] = {}
    for s in shifts:
        for k in s.know_ids:
            by_id[k] = by_id.get(k, 0) + s.delta
    out: list[Know] = []
    for k in atoms:
        d = by_id.get(k.id)
        if d is None:
            out.append(k)
            continue
        a, b = k.prop.interval
        a2, b2 = max(0, a + d), min(T, b + d)
        if b2 <= a2:
            continue                       # shifted out of the investigation window: no claim
        out.append(replace(k, prop=k.prop.model_copy(update={"interval": (a2, b2)})))
    return out


def relevant(ctx: Ctx, shifts: list[TimeShift], fairness: int, cracked: frozenset) -> list[TimeShift]:
    """Distortions worth enumerating (ADR-28 / I-57): those whose atoms yield a constraint at ANY
    level, in the undistorted derivation or in the all-distorted one. A superset of "changes the
    hard set", so a distortion cannot hide behind a level it merely failed to reach on its own."""
    def items(subset):
        mat = material(ctx.store.all(), testimony_pool(apply_shifts(ctx.atoms, subset, ctx.case.t_investigation),
                                                       ctx.protected, cracked))
        return {c.item for c in admissible(ctx.case, ctx.store, mat, ctx.comps, ctx.victim)}
    seen = items([]) | items(shifts)
    return [s for s in shifts if set(s.know_ids) & seen]


def robustness(ctx: Ctx, shifts: list[TimeShift], fairness: int, cracked: frozenset,
               survivors: list[str]) -> dict:
    """Uniqueness (and the SAME survivor) must hold for every subset of uncorrected distortions.
    More than MAX_ACTIVE relevant distortions is reported unverifiable and FAILS CLOSED — never sampled."""
    T = ctx.case.t_investigation

    def run(subset: list[TimeShift]):
        atoms = apply_shifts(ctx.atoms, subset, T)
        mat = material(ctx.store.all(), testimony_pool(atoms, ctx.protected, cracked))
        cons = admissible(ctx.case, ctx.store, mat, ctx.comps, ctx.victim)
        return cons, solve(ctx, cons, fairness, want_cores=False)

    _, base_v = run([])
    active = relevant(ctx, shifts, fairness, cracked)
    if len(active) > MAX_ACTIVE:
        return {"n_distortions": len(shifts), "n_active": len(active), "subsets_run": 0, "bounded": True,
                "failures": [{"reasons": ["robustness unverifiable within bound"]}], "n_failures": 1, "ok": False,
                "baseline_unique": base_v.unique}
    subsets = [list(c) for r in range(len(active) + 1) for c in combinations(active, r)]
    failures = []
    for sub in subsets:
        _, v = run(sub)
        if not v.unique or v.survivors != survivors:
            failures.append({"uncorrected": [s.memory for s in sub], "survivors": v.survivors, "unique": v.unique,
                             "reasons": v.reasons})
    return {"n_distortions": len(shifts), "n_active": len(active), "subsets_run": len(subsets),
            "bounded": False, "failures": failures[:5], "n_failures": len(failures), "ok": not failures,
            "baseline_unique": base_v.unique}
