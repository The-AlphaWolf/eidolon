"""The machine-readable proof of a V-5 verdict (`eidolon.proof/2`) and its INDEPENDENT verifier
(§19.5 "exclusion chains are machine-generated"; ADR-28).

A proof is a SET OF HINTS, not a premise. `build_proof` writes down what the solver concluded;
`verify_proof` takes none of it on faith. Every field is either re-derived from the sealed package
or absent — there is no "carried through" field (the audit's H7):

  0. strict parsing — a malformed document is a rejection, never an exception (I-15);
  1. the proof names THIS package (its seal) and the fairness level is the one the package sealed;
  2. the candidate domain is the PHYSICAL one (CaseLog presence, alive at `t_investigation`), and
     the authored role labels must agree with it (I-59);
  3. the admissible hard constraint set is re-derived from the package (`proof_material.derive`, an
     implementation that shares no code with the lattice or the solver) and must be SEMANTICALLY
     EQUAL to the proof's — item, level, sources, tick cells (I-57). A constraint naming an item the
     package does not have, at a level the material does not reach, or missing altogether, is rejected;
  4. every derived constraint is TRUE in the CaseLog (`Heard.actor` is the real attacker; a
     `NoStranger` is audited against its recorded observer);
  5. window, per-candidate exclusion cores (oracle-infeasible, deletion-minimal), the voice and time
     exclusions, survivors' feasible ticks, the outsider corridor and `unique` are recomputed;
  6. the I-45 fixpoint (`cracked`) is recomputed and each cracked actor's core must rest on material
     available in its own round;
  7. `proof_core` is re-derived: sufficient, with the same survivor, and 1-minimal;
  8. every subset of the relevant distortions is re-derived and must stay unique with the same
     survivor (more than 2**10 subsets is rejected, never sampled).

It imports nothing from `solver`, `lattice`, `distort`, `fairness` or `bots` — constants included.
It never reads `pkg.solution`.
"""
from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, ValidationError

from ..world.interval import ticks
from . import proof_material as pm
from .package import MAX_WINDOW, CasePackage

SCHEMA = "eidolon.proof/2"
_MAX_ROWS = 4000


# ------------------------------------------------------------------ the document
class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PConstraint(_Strict):
    id: StrictStr
    item: StrictStr
    kind: Literal["At", "NotAt", "Exist", "Died", "Heard", "NoStranger"]
    actor: StrictStr | None
    observer: StrictStr | None = None
    loc: StrictStr | None
    iv: list[StrictInt] = Field(min_length=2, max_length=2)
    level: StrictInt
    sources: list[StrictStr] = Field(max_length=64)


class VoiceCore(_Strict):
    kind: Literal["VOICE"]
    by: StrictStr


class TimeCore(_Strict):
    kind: Literal["TIME"]


class PCandidate(_Strict):
    excluded: StrictBool
    core: Union[list[StrictStr], VoiceCore, TimeCore]
    times: list[StrictInt] = Field(max_length=_MAX_ROWS)


class PCracked(_Strict):
    actor: StrictStr
    round: StrictInt
    core: list[StrictStr] = Field(max_length=_MAX_ROWS)


class POutsider(_Strict):
    excluded: StrictBool
    blocked: list[StrictStr] = Field(max_length=_MAX_ROWS)


class PRobustness(_Strict):
    subsets_run: StrictInt
    failures: list[dict] = Field(max_length=64)


class Proof2(_Strict):
    schema_: Literal["eidolon.proof/2"] = Field(alias="schema")
    package_seal: StrictStr
    fairness: StrictInt
    candidate_domain: list[StrictStr] = Field(max_length=256)
    cracked: list[PCracked] = Field(max_length=256)
    constraints: list[PConstraint] = Field(max_length=_MAX_ROWS)
    window: list[StrictInt] = Field(min_length=2, max_length=2)
    murder_loc: StrictStr | None
    candidates: dict[StrictStr, PCandidate] = Field(max_length=256)
    survivors: list[StrictStr] = Field(max_length=256)
    time_bins: list[StrictInt] = Field(max_length=_MAX_ROWS)
    outsider: POutsider
    unique: StrictBool
    proof_core: list[StrictStr] = Field(max_length=_MAX_ROWS)
    robustness: PRobustness

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


def build_proof(pkg: CasePackage, ctx, cons, verdict, *, cracked, rounds, core, robustness=None, fragility=None,
                trace=()) -> dict:
    """The solver's conclusion, written down. `fragility`/`rounds`/`reasons` are not part of the document:
    they are recomputed from verified material by V-6, never carried (ADR-28)."""
    hard = [c for c in cons if c.level >= verdict.fairness]
    cand = {}
    for x, e in sorted(verdict.candidates.items()):
        c0 = e["core"]
        out = dict(c0[0]) if c0 and c0[0].get("kind") in ("VOICE", "TIME") else [c["id"] for c in c0]
        cand[x] = {"excluded": e["excluded"], "core": out, "times": list(e["times"])}
    return {
        "schema": SCHEMA, "package_seal": pkg.seal, "fairness": verdict.fairness,
        "candidate_domain": sorted(verdict.candidates),
        "cracked": [dict(t) for t in trace],
        "constraints": [c.to_json() for c in hard],
        "window": list(verdict.window), "murder_loc": verdict.murder_loc,
        "candidates": cand, "survivors": list(verdict.survivors), "time_bins": list(verdict.time_bins),
        "outsider": {"excluded": verdict.outsider["excluded"],
                     "blocked": sorted(c.id for c in hard if c.kind == "NoStranger")},
        "unique": verdict.unique, "proof_core": list(core or []),
        "robustness": {"subsets_run": (robustness or {}).get("subsets_run", 0),
                       "failures": list((robustness or {}).get("failures", []))},
    }


# ------------------------------------------------------------------ the verifier
def _pc_key(c: PConstraint) -> set[tuple]:
    return pm.key_set(pm.DC(c.item, c.kind, c.actor, c.observer, c.loc, (c.iv[0], c.iv[1]), c.level, tuple(c.sources)))


def candidate_domain_complete(pkg: CasePackage, proof: dict) -> list[str]:
    """B-4, kept as its own entry point: a proof is a claim about a CANDIDATE SPACE, not about the rows
    it chose to print. The space is physical (I-59); the table must be exactly it."""
    dom, _p, _v = pm.domain_problems(pkg.case)
    expected = set(dom) | set(pkg.case.living_actors())
    table = proof.get("candidates") if isinstance(proof, dict) else None
    if not isinstance(table, dict):
        return ["proof has no candidate table"]
    got = set(table)
    bad: list[str] = []
    if missing := sorted(expected - got):
        bad.append(f"candidate table is incomplete: {missing} never tested")
    if extra := sorted(got - expected):
        bad.append(f"candidate table names actors outside the case's candidate domain: {extra}")
    survivors = proof.get("survivors", ())
    if isinstance(survivors, (list, tuple)) and (stray := sorted(set(map(str, survivors)) - expected)):
        bad.append(f"survivors name actors outside the candidate domain: {stray}")
    return bad


def verify_proof(pkg: CasePackage, proof: dict, *, minimal: bool = True) -> list[str]:
    """Empty list == the proof checks out. Each string names one failure. Never raises: any internal
    exception is itself a rejection (fail closed, I-15)."""
    try:
        return _verify(pkg, proof, minimal)
    except Exception as e:                                              # noqa: BLE001 — fail closed
        return [f"verifier error: {type(e).__name__}"]


def _parse(proof) -> tuple[Proof2 | None, list[str]]:
    if not isinstance(proof, dict):
        return None, ["malformed proof: not an object"]
    try:
        return Proof2.model_validate(proof), []
    except ValidationError as e:
        first = e.errors()[0]
        return None, [f"malformed proof: {'.'.join(map(str, first['loc']))}: {first['type']}"]


def _verify(pkg: CasePackage, raw, minimal: bool) -> list[str]:
    P, bad = _parse(raw)
    if P is None:
        return bad
    case = pkg.case
    # 1. binding ------------------------------------------------------------------------------
    if not pkg.verify_seal():
        bad.append("package seal does not verify")
    if P.package_seal != pkg.seal:
        bad.append("proof is about a different package")
    if P.fairness != pkg.fairness_level:
        bad.append(f"proof claims fairness {P.fairness}, the sealed package says {pkg.fairness_level}")
    fairness = pkg.fairness_level
    # 2. candidate domain (I-59) --------------------------------------------------------------
    dom, dom_problems, victim = pm.domain_problems(case)
    bad += dom_problems
    if sorted(P.candidate_domain) != dom:
        bad.append(f"candidate_domain {sorted(P.candidate_domain)} is not the physical domain {dom}")
    if set(P.candidates) != set(dom):
        miss, extra = sorted(set(dom) - set(P.candidates)), sorted(set(P.candidates) - set(dom))
        if miss:
            bad.append(f"candidate table is incomplete: {miss} never tested")
        if extra:
            bad.append(f"candidate table names actors outside the case's candidate domain: {extra}")
    if stray := sorted(set(P.survivors) - set(dom)):
        bad.append(f"survivors name actors outside the candidate domain: {stray}")
    if victim is None:
        return bad
    mloc = pm.murder_loc(case, victim)
    if P.murder_loc != mloc:
        bad.append(f"murder_loc {P.murder_loc!r} is not where the CaseLog leaves the body ({mloc!r})")
    oracle = pm.Oracle(case)
    # 3. the material, re-derived (I-57) ------------------------------------------------------
    cracked, rounds, trace, hard, universe = pm.fixpoint(pkg, dom, victim, fairness, oracle)
    by_id: dict[str, PConstraint] = {}
    for c in P.constraints:
        if c.id in by_id:
            bad.append(f"duplicate constraint id {c.id!r}")
        by_id[c.id] = c
    for c in P.constraints:
        if c.item not in universe and not any(c.item == e.id for e in pkg.evidence):
            bad.append(f"{c.id}: item {c.item!r} is neither evidence in the package nor an obtainable testimony atom")
    derived: set[tuple] = set().union(*[pm.key_set(d) for d in hard]) if hard else set()
    claimed: set[tuple] = set().union(*[_pc_key(c) for c in P.constraints]) if P.constraints else set()
    for k in sorted(claimed - derived, key=repr)[:8]:
        bad.append(f"constraint not admissible at the sealed fairness level (or wrong item/level/sources): {k}")
    for k in sorted(derived - claimed, key=repr)[:8]:
        bad.append(f"proof is INCOMPLETE: admissible hard constraint omitted: {k}")
    # 4. truth audit over the derived set ------------------------------------------------------
    for d in hard:
        why = pm.truth_audit(case, victim, d)
        if why:
            bad.append(f"TRUTH AUDIT {d.item} {d.kind}@{d.loc}{list(d.iv)}: {why}")
    # 5. window, candidates, outsider, uniqueness ---------------------------------------------
    solved = pm.solve_independent(pkg, hard, dom, victim, oracle)
    if solved.contradictory:
        bad.append("admissible material is contradictory about the murder time")
        return bad
    if tuple(P.window) != solved.window:
        bad.append(f"window {tuple(P.window)} is not the intersection of the derived pins {solved.window}")
    if len(solved.voices) > 1:
        bad.append(f"the hard material names several voices {sorted(solved.voices)} (fail closed)")
    window = solved.window
    for x in dom:
        got, want = P.candidates.get(x), solved.candidates[x]
        if got is None:
            continue
        if got.excluded != want["excluded"]:
            bad.append(f"{x}: proof says excluded={got.excluded}, the independent solve says {want['excluded']}")
            continue
        if want["excluded"]:
            _check_exclusion(pkg, x, got, want, by_id, hard, window, mloc, solved, oracle, minimal, bad)
        else:
            if solved.too_wide:
                bad.append(f"{x}: murder window {window} exceeds {MAX_WINDOW} ticks — never approximated")
            elif got.times != want["times"]:
                bad.append(f"{x}: recorded times {got.times[:4]}… differ from the oracle's {want['times'][:4]}…")
            if got.core not in ([], ):
                bad.append(f"{x}: a survivor carries an exclusion core")
    if sorted(P.survivors) != solved.survivors:
        bad.append("recorded survivor list disagrees with the independent solve")
    blocked_ids = sorted(c.id for c in P.constraints if c.kind == "NoStranger")
    if sorted(P.outsider.blocked) != blocked_ids:
        bad.append("outsider.blocked does not list exactly the NoStranger constraints")
    if P.outsider.excluded == solved.corridor:
        bad.append(f"outsider verdict disagrees with the oracle (oracle finds a corridor: {solved.corridor})")
    if P.time_bins != solved.bins:
        bad.append("recorded time bins disagree with the survivors' times")
    unique = pm.is_unique(pkg, solved)
    if P.unique != unique:
        bad.append(f"unique={P.unique} but the checked facts give unique={unique}")
    # 6. the layer-0 fixpoint ------------------------------------------------------------------
    got_cracked = sorted((c.actor, c.round) for c in P.cracked)
    want_cracked = sorted((t["actor"], t["round"]) for t in trace)
    if got_cracked != want_cracked:
        bad.append(f"cracked set {got_cracked} is not the recomputed I-45 fixpoint {want_cracked}")
    else:
        by_actor = {c.actor: c for c in P.cracked}
        for t in trace:
            _check_cracked(t, by_actor[t["actor"]], mloc, oracle, bad)
    # 7/8. only a UNIQUE case carries a proof core and a robustness claim ------------------------
    if not unique:
        if P.proof_core or P.robustness.subsets_run or P.robustness.failures:
            bad.append("a case that is not unique carries a proof core or a robustness claim")
        return bad
    _check_core(pkg, P, cracked, universe, dom, victim, fairness, solved.survivors, oracle, minimal, bad)
    _check_robustness(pkg, P, cracked, dom, victim, fairness, solved.survivors, oracle, bad)
    return bad


def _hyp(mloc, window):
    return (mloc, (window[0], window[1]))


def _check_exclusion(pkg, x, got, want, by_id, hard, window, mloc, solved, oracle, minimal, bad):
    how, core = want["how"], got.core
    if how == "VOICE":
        if not isinstance(core, VoiceCore):
            bad.append(f"{x}: excluded by a voice but the proof gives no voice core")
            return
        c = by_id.get(core.by)
        if (c is None or c.kind != "Heard" or c.loc != mloc or not c.actor or c.actor == x
                or c.iv[0] >= window[1] or window[0] >= c.iv[1]):
            bad.append(f"{x}: voice core {core.by!r} is not a hard Heard(attack) at the murder place by somebody else")
    elif how == "TIME":
        if not isinstance(core, TimeCore):
            bad.append(f"{x}: time-excluded but the proof gives no TIME core")
    else:
        if not isinstance(core, list) or not core:
            bad.append(f"{x}: excluded by constraints but the proof cites none")
            return
        if any(i not in by_id for i in core):
            bad.append(f"{x}: core cites constraints not in the proof: {sorted(set(core) - set(by_id))}")
            return
        sub = [by_id[i] for i in core]
        if any(c.actor != x for c in sub):
            bad.append(f"{x}: core cites another actor's constraints")
            return
        if oracle.feasible(x, sub, _hyp(mloc, window)):
            bad.append(f"{x}: ORACLE finds a walk satisfying the 'infeasible' core")
        elif minimal:
            for c in sub:
                rest = [y for y in sub if y is not c]
                if not oracle.feasible(x, rest, _hyp(mloc, window)):
                    bad.append(f"{x}: core is not deletion-minimal ({c.id} is redundant)")


def _check_cracked(t, got, mloc, oracle, bad):
    x, how, universe, hard = t["actor"], t["how"], t["universe"], t["hard"]
    if got.round != t["round"]:
        bad.append(f"{x}: cracked in round {got.round}, recomputed round {t['round']}")
    if any(i not in universe for i in got.core):
        bad.append(f"{x}: cracked core uses material not available in round {t['round']}: "
                   f"{sorted(set(got.core) - set(universe))}")
        return
    if how == "CONSTRAINTS":
        mine = [d for d in hard if d.actor == x and d.item in set(got.core)]
        if oracle.feasible(x, mine, _hyp(mloc, t["window"])):
            bad.append(f"{x}: cracked core does not by itself exclude them in round {t['round']}")
    elif how == "VOICE":
        if not any(d.kind == "Heard" and d.loc == mloc and d.actor and d.actor != x and d.item in set(got.core)
                   for d in hard):
            bad.append(f"{x}: cracked-by-voice core does not contain the voice item")


def _check_core(pkg, P, cracked, universe, dom, victim, fairness, survivors, oracle, minimal, bad):
    core = list(P.proof_core)
    if len(set(core)) != len(core) or not core:
        bad.append("proof_core is empty or repeats an item")
        return
    if any(i not in universe for i in core):
        bad.append(f"proof_core names items that are not available material: {sorted(set(core) - set(universe))}")
        return

    def verdict(items):
        cons, _u = pm.derive(pkg, cracked, only=set(items))
        s = pm.solve_independent(pkg, [c for c in cons if c.level >= fairness], dom, victim, oracle)
        return s, pm.is_unique(pkg, s)

    s, uniq = verdict(core)
    if not uniq or s.survivors != survivors:
        bad.append("proof_core is INSUFFICIENT: re-derived from the core alone the case is not uniquely "
                   f"{survivors} (survivors {s.survivors})")
        return
    if minimal:
        for i in core:
            rest = [j for j in core if j != i]
            s2, u2 = verdict(rest)
            if u2:
                bad.append(f"proof_core is not 1-minimal: {i} is redundant")


def _check_robustness(pkg, P, cracked, dom, victim, fairness, survivors, oracle, bad):
    base, _u = pm.derive(pkg, cracked)
    shifted, _u2 = pm.derive(pkg, cracked, shifts=tuple(pkg.distortions))
    rel = pm.relevant_distortions(pkg, cracked, base, shifted)
    if len(rel) > pm.MAX_SUBSETS_LOG2:
        bad.append("robustness unverifiable within bound (more than 2**10 distortion subsets)")
        return
    n = 0
    for sub in pm.distortion_subsets(rel):
        n += 1
        cons, _u3 = pm.derive(pkg, cracked, shifts=sub)
        s = pm.solve_independent(pkg, [c for c in cons if c.level >= fairness], dom, victim, oracle)
        if not pm.is_unique(pkg, s) or s.survivors != survivors:
            bad.append(f"uniqueness fails when {[d.memory for d in sub]} stay uncorrected (survivors {s.survivors})")
    if P.robustness.subsets_run != n:
        bad.append(f"robustness.subsets_run={P.robustness.subsets_run}, the verifier ran {n}")
    if P.robustness.failures:
        bad.append("the proof itself records robustness failures")
