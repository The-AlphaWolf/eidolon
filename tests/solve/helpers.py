"""Shared Phase 6 test helpers: cached generated packages and the world-editing transforms the
negative fixtures and self-checks are built from. Everything here EDITS a generated package; nothing
is hand-authored — the golden cases and their negatives come out of the generator."""
from __future__ import annotations

import functools
from pathlib import Path

from eidolon.gen.pipeline import generate
from eidolon.solve.package import CasePackage, load_sealed_case
from eidolon.solve.solver import build_ctx, evaluate, robust_material
from eidolon.world.case import Case
from eidolon.world.events import EffActorState

GOLDEN = (("study_party", 4), ("manor_wing", 4), ("study_party", 5), ("manor_wing", 6))


REDUCED = dict(bluffs=40, odd=40)       # tests run V-7's bluff/adversarial bots at a reduced scale; such a case cannot SEAL
                                         # (`load_sealed_case` refuses it) — the full scale is the committed goldens' job
GOLDEN_DIR = Path(__file__).resolve().parents[2] / "cases" / "generated"


@functools.cache
def loaded(skel: str, seed: int):
    """The committed golden, read through the ONLY reader: every seal, the independent proof verifier and the full-scale
    V-7 report must check out (I-58)."""
    return load_sealed_case(str(GOLDEN_DIR / f"{skel}_s{seed}.json"))


@functools.cache
def golden(skel: str, seed: int):
    res = generate(skel, seed, **REDUCED)
    assert res.failed_at is None, (skel, seed, res.failed_at, res.problems)
    return res


def pkg(skel: str = "study_party", seed: int = 4) -> CasePackage:
    return golden(skel, seed).package


def verdict(p: CasePackage, fairness: int = 2):
    ctx = build_ctx(p)
    mat, _cracked, _rounds = robust_material(ctx, fairness)
    return ctx, mat, evaluate(ctx, mat, fairness)


def rebuild(p: CasePackage, *, events=None, evidence=None, **fields) -> CasePackage:
    """A NEW sealed package with the given parts replaced (the Case is re-validated)."""
    case = p.case
    if events is not None:
        case = Case(**{**{k: getattr(case, k) for k in Case.model_fields}, "events": tuple(events)})
    upd = {"case": case, **fields}
    if evidence is not None:
        upd["evidence"] = tuple(evidence)
    return p.model_copy(update=upd).sealed()


def drop_evidence(p: CasePackage, *ids: str) -> CasePackage:
    return rebuild(p, evidence=[e for e in p.evidence if e.id not in ids])


def edit_evidence(p: CasePackage, eid: str, **upd) -> CasePackage:
    return rebuild(p, evidence=[e.model_copy(update=upd) if e.id == eid else e for e in p.evidence])


def blind_everyone(p: CasePackage) -> CasePackage:
    """Every stay is spent with attention 0.1 (< the 0.3 needed to perceive anything): nobody sees
    or hears anyone. The world is otherwise untouched."""
    out = []
    for e in p.case.events:
        if e.kind == "Stay" and e.actor:
            eff = tuple(x for x in e.effects if not (x.kind == "ActorState" and x.attr == "attention"))
            e = e.model_copy(update={"effects": eff + (EffActorState(actor=e.actor, attr="attention", value="0.1"),)})
        out.append(e)
    # the sealed distortions/boosts belonged to the ORIGINAL world's memories; they are meaningless against an edited
    # CaseLog. The declared account tokens are KEPT: what an account says is derived from the edited world's own
    # `Participated` knowledge (ADR-23), so nothing needs re-grounding after an edit.
    return rebuild(p, events=out, distortions=(), memory_boosts=())


def unalibied(p: CasePackage) -> CasePackage:
    """`blind_everyone` PLUS every L3 presence pin removed: nobody perceives anyone and no device
    places anyone, so nothing excludes anyone. This is what "a case with several possible
    murderers" needs now that a skeleton may carry a room-level alibi log (B-3) — blinding the
    cast alone no longer opens the case up, because the log is physical, not perceived."""
    pins = {e.id for e in p.evidence
            if e.id.startswith("E_alibi") or e.id.startswith("E_pin_") and e.id != "E_pin_clean"}
    q = drop_evidence(blind_everyone(p), *pins)
    # a herring whose refuter just went with the pins is a V-0 dangling reference, which would
    # stop the package before the stage this fixture exists to exercise
    return rebuild(q, evidence=[e.model_copy(update={"red_herring": None})
                                if e.red_herring and e.red_herring.refuter in pins else e
                                for e in q.evidence])


def shuffled(p: CasePackage, rng) -> CasePackage:
    """The same logical case with events, evidence, secrets and actor tables in another order."""
    ev = list(p.case.events)
    rng.shuffle(ev)
    evi = list(p.evidence)
    rng.shuffle(evi)
    sec = list(p.secrets)
    rng.shuffle(sec)
    keys = list(p.case.actors)
    rng.shuffle(keys)
    case = Case(**{**{k: getattr(p.case, k) for k in Case.model_fields}, "events": tuple(ev),
                   "actors": {k: p.case.actors[k] for k in keys}})
    return p.model_copy(update={"case": case, "evidence": tuple(evi), "secrets": tuple(sec)}).sealed()
