"""RB-3 (Phase 6 re-audit): `verify_proof` accepted forged proofs. Each test here is one of the hostile
auditor's actual attacks (or the invariant it breaks) and must fail for the ARCHITECTURAL reason named in
its assertion — an independent re-derivation of the admissible material (I-57), not a shape check.

Recorded RED on the pre-fix tree: the same attacks run against the original `proof/1` verifier all
verified (wrong murderer, fake item, fairness 0, omitted constraint, forged robustness) and the malformed
documents crashed it with KeyError/AttributeError/TypeError.
"""
from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from eidolon.solve import proof_material as pm
from eidolon.solve.lattice import admissible
from eidolon.solve.package import SealedCase, SealRefusal, bundle_seal, load_sealed_case
from eidolon.solve.proof import verify_proof
from eidolon.solve.solver import build_ctx, robust_material
from eidolon.world.case import Case
from tests.solve.helpers import GOLDEN, golden, rebuild

BOTH = (("study_party", 4), ("manor_wing", 4))
ROOT = Path(__file__).resolve().parents[2] / "eidolon" / "solve"


def base(skel="study_party", seed=4):
    r = golden(skel, seed)
    return r.package, copy.deepcopy(r.report.proof)


def rejects(pkg, proof, needle: str) -> list[str]:
    bad = verify_proof(pkg, proof)
    assert bad, "a forged proof VERIFIED"
    assert any(needle in b for b in bad), (needle, bad)
    return bad


# ---------------------------------------------------------------------------- the honest proof
@pytest.mark.parametrize("skel,seed", GOLDEN)
def test_the_generator_s_own_proof_verifies_under_the_independent_derivation(skel, seed):
    p, proof = base(skel, seed)
    assert proof["schema"] == "eidolon.proof/2" and verify_proof(p, proof) == []
    assert proof["package_seal"] == p.seal and proof["fairness"] == p.fairness_level


@pytest.mark.parametrize("skel,seed", GOLDEN)
def test_differential_the_verifier_s_hard_set_equals_the_solvers_cell_for_cell(skel, seed):
    """§D.16: two implementations, one answer. A disagreement is a bug in one of them, never an alignment."""
    p, proof = base(skel, seed)
    ctx = build_ctx(p)
    mat, _c, _r = robust_material(ctx)
    lattice_hard = [c for c in admissible(ctx.case, ctx.store, mat, ctx.comps, ctx.victim) if c.level >= 2]
    dom, _pb, victim = pm.domain_problems(p.case)
    _cr, _rd, _tr, hard, _u = pm.fixpoint(p, dom, victim, p.fairness_level, pm.Oracle(p.case))
    a = set().union(*[pm.key_set(c) for c in lattice_hard])
    b = set().union(*[pm.key_set(c) for c in hard])
    assert a == b, (sorted(a - b, key=repr)[:3], sorted(b - a, key=repr)[:3])


# ---------------------------------------------------------------------------- H6/H5/H1: the wrong-murderer forgery
@pytest.mark.parametrize("skel,seed", BOTH)
def test_auditor_wrong_murderer_forgery_is_rejected(skel, seed):
    """Attack 7: drop the framed innocent's alibi, add `Heard(attack, actor=<innocent>)` with a made-up item,
    exclude everybody else by that 'voice'."""
    p, proof = base(skel, seed)
    murderer = p.solution.murderer
    framed = next(a for a, e in proof["candidates"].items() if a != murderer and e["excluded"])
    t_m = p.solution.interval[0]
    proof["constraints"] = [c for c in proof["constraints"] if c["actor"] != framed]
    proof["constraints"].append({"id": "FORGE", "item": "NO_SUCH_ITEM", "kind": "Heard", "actor": framed,
                                 "observer": None, "loc": proof["murder_loc"], "iv": [t_m, t_m + 1],
                                 "level": 3, "sources": []})
    for x, e in proof["candidates"].items():
        if x == framed:
            e.update(excluded=False, core=[], times=[t_m])
        else:
            e.update(excluded=True, core={"kind": "VOICE", "by": "FORGE"}, times=[])
    proof["survivors"], proof["time_bins"] = [framed], [t_m // 10]
    bad = rejects(p, proof, "neither evidence in the package nor an obtainable testimony atom")
    assert any("INCOMPLETE" in b for b in bad)              # and the innocent's real alibi is missing


def test_forged_heard_is_rejected_even_when_it_borrows_a_real_item_id():
    p, proof = base("manor_wing", 4)
    real_item = proof["constraints"][0]["item"]
    t_m = p.solution.interval[0]
    proof["constraints"].append({"id": "F2", "item": real_item, "kind": "Heard", "actor": p.solution.murderer,
                                 "observer": None, "loc": proof["murder_loc"], "iv": [t_m, t_m + 1],
                                 "level": 3, "sources": [real_item]})
    rejects(p, proof, "not admissible at the sealed fairness level")


@pytest.mark.parametrize("skel,seed", BOTH)
def test_omniscient_true_constraints_with_fabricated_items_are_rejected(skel, seed):
    """Every constraint TRUE (each candidate's real position), none of them derivable material."""
    p, proof = base(skel, seed)
    from eidolon.world.state import loc_at
    lo, hi = proof["window"]
    cons = []
    for i, a in enumerate(sorted(p.case.living_actors())):
        loc = loc_at(p.case.events, a, lo)
        cons.append({"id": f"G{i}", "item": "GOD_MODE", "kind": "At", "actor": a, "observer": None, "loc": loc,
                     "iv": [lo, lo + 1], "level": 3, "sources": ["GOD_MODE"]})
    proof["constraints"] = cons
    rejects(p, proof, "GOD_MODE")


def test_item_resolving_to_a_different_proposition_is_rejected():
    p, proof = base("manor_wing", 4)
    a, b = next((x, y) for x in proof["constraints"] for y in proof["constraints"] if x["item"] != y["item"])
    a["item"] = b["item"]                                   # a real item, but it does not say that
    rejects(p, proof, "not admissible at the sealed fairness level")


def test_heard_with_the_wrong_actor_fails_the_truth_audit():
    """H5 (X3-X5): the audit used to ignore `Heard.actor`, so ANY attacker's name passed."""
    p, _ = base("manor_wing", 4)
    _d, _pb, victim = pm.domain_problems(p.case)
    t_m = p.solution.interval[0]
    mk = lambda who: pm.DC("x", "Heard", who, None, p.solution.location, (t_m, t_m + 1), 3, ())
    innocent = next(a for a in p.case.living_actors() if a != p.solution.murderer)
    assert pm.truth_audit(p.case, victim, mk(p.solution.murderer)) is None
    assert "no attack" in pm.truth_audit(p.case, victim, mk(innocent))
    assert pm.truth_audit(p.case, victim, mk(None)) is None         # an unidentified sound only needs an attack


@pytest.mark.parametrize("skel,seed", BOTH)
def test_omitting_a_true_hard_constraint_is_rejected_as_incomplete(skel, seed):
    p, proof = base(skel, seed)
    for i in range(len(proof["constraints"])):
        q = copy.deepcopy(proof)
        gone = q["constraints"].pop(i)
        bad = verify_proof(p, q)
        assert any("INCOMPLETE" in b for b in bad), (gone["id"], bad[:2])


# ---------------------------------------------------------------------------- H4: fairness
@pytest.mark.parametrize("lowered", [0, 1, 3, -1])
def test_a_forged_fairness_level_is_rejected(lowered):
    p, proof = base()
    proof["fairness"] = lowered
    rejects(p, proof, "the sealed package says")


def test_fairness_is_sealed_with_the_package():
    p, _ = base()
    q = p.model_copy(update={"fairness_level": 3})
    assert q.content_hash() != p.content_hash()           # a different level is a different case


# ---------------------------------------------------------------------------- H7: proof_core / robustness / cracked
def test_forged_proof_core_is_rejected_nonexistent_insufficient_and_non_minimal():
    p, proof = base("manor_wing", 4)
    core = proof["proof_core"]
    q = copy.deepcopy(proof)
    q["proof_core"] = core + ["E_DOES_NOT_EXIST"]
    rejects(p, q, "not available material")
    q = copy.deepcopy(proof)
    q["proof_core"] = core[:-1]
    rejects(p, q, "INSUFFICIENT")
    spare = next(e.id for e in p.evidence if e.id not in core and e.authentic)
    q = copy.deepcopy(proof)
    q["proof_core"] = core + [spare]
    rejects(p, q, "not 1-minimal")
    q = copy.deepcopy(proof)
    q["proof_core"] = []
    rejects(p, q, "proof_core")


def test_forged_robustness_is_rejected():
    p, proof = base("manor_wing", 4)
    q = copy.deepcopy(proof)
    q["robustness"]["subsets_run"] += 7
    rejects(p, q, "robustness.subsets_run")
    q = copy.deepcopy(proof)
    q["robustness"]["failures"] = [{"uncorrected": ["M"]}]
    rejects(p, q, "robustness failures")
    q = copy.deepcopy(proof)
    q["robustness"] = {"subsets_run": 0, "failures": []}
    rejects(p, q, "robustness.subsets_run")


def test_forged_cracked_set_is_rejected():
    p, proof = base("manor_wing", 4)
    assert proof["cracked"], "the golden must exercise the I-45 fixpoint"
    q = copy.deepcopy(proof)
    q["cracked"] = q["cracked"][1:]
    rejects(p, q, "recomputed I-45 fixpoint")
    q = copy.deepcopy(proof)
    q["cracked"].append({"actor": p.solution.murderer, "round": 0, "core": []})
    rejects(p, q, "recomputed I-45 fixpoint")
    q = copy.deepcopy(proof)
    q["cracked"][0]["core"] = ["GOD_MODE"]
    rejects(p, q, "not available in round")


def test_survivor_times_and_window_tampering_is_rejected():
    """X6/X7: the survivor's times and the murder window used to be carried, not derived."""
    p, proof = base("manor_wing", 4)
    sv = proof["survivors"][0]
    q = copy.deepcopy(proof)
    q["candidates"][sv]["times"] = q["candidates"][sv]["times"] + [q["window"][1] + 3]
    rejects(p, q, "recorded times")
    q = copy.deepcopy(proof)
    q["window"] = [q["window"][0], q["window"][1] + 5]
    rejects(p, q, "window")
    q = copy.deepcopy(proof)
    q["time_bins"] = [99]
    rejects(p, q, "time bins")


def test_offstage_relabelled_viable_suspect_is_rejected():
    """I-59 / X1: a role relabel must not hide a suspect from the candidate domain."""
    p, proof = base("study_party", 4)
    victim_free = [a for a in p.case.living_actors() if a != p.solution.murderer]
    target = victim_free[0]
    actors = {k: (v.model_copy(update={"role": "offstage"}) if k == target else v) for k, v in p.case.actors.items()}
    case = Case(**{**{k: getattr(p.case, k) for k in Case.model_fields}, "actors": actors})
    q = rebuild(p, case=case) if False else p.model_copy(update={"case": case}).sealed()
    proof["package_seal"] = q.seal                       # the forger re-points the proof at the edited package
    bad = verify_proof(q, proof)
    assert any("authored roles disagree with the CaseLog" in b for b in bad), bad


def test_the_nostranger_audit_uses_the_recorded_observer():
    """N-4 / X21: the observer used to be hard-coded to the victim and dropped from the JSON."""
    p, proof = base("study_party", 4)
    ns = [c for c in proof["constraints"] if c["kind"] == "NoStranger"]
    assert ns and all(c["observer"] for c in ns)
    c = ns[0]
    _d, _pb, victim = pm.domain_problems(p.case)
    assert c["observer"] == victim
    dc = lambda obs: pm.DC("i", "NoStranger", None, obs, c["loc"], tuple(c["iv"]), 3, ())
    assert pm.truth_audit(p.case, victim, dc(victim)) is None
    assert "observer" in pm.truth_audit(p.case, victim, dc(None))
    # if the 'observer' is somebody who is not the only person absent, the audit changes its answer
    someone = next(a for a in p.case.living_actors())
    from eidolon.world.state import loc_at
    present = [a for a in p.case.actors if a != victim and any(loc_at(p.case.events, a, t) == c["loc"] for t in range(*c["iv"]))]
    assert pm.truth_audit(p.case, victim, dc(someone)) is None or present      # self-consistent either way
    q = copy.deepcopy(proof)
    next(x for x in q["constraints"] if x["kind"] == "NoStranger")["observer"] = someone
    rejects(p, q, "not admissible")


# ---------------------------------------------------------------------------- H8: malformed documents never raise
AUDITOR_JUNK = [{}, [], None, "x", 0, {"schema": "eidolon.proof/2"}, {"constraints": {}}]


@pytest.mark.parametrize("junk", AUDITOR_JUNK)
def test_the_auditors_malformed_documents_are_rejections_not_exceptions(junk):
    p, _ = base()
    bad = verify_proof(p, junk)
    assert bad and all(isinstance(b, str) for b in bad)


def test_structurally_corrupted_real_proofs_are_rejections_not_exceptions():
    p, proof = base()
    for mutate in (lambda d: d["candidates"].__setitem__(next(iter(d["candidates"])), {"excluded": True, "core": "x", "times": []}),
                   lambda d: d["constraints"][0].__setitem__("iv", "ab"),
                   lambda d: d["constraints"][0].__setitem__("iv", [1]),
                   lambda d: d["constraints"][0].__setitem__("level", True),
                   lambda d: d["constraints"][0].__setitem__("level", 2.5),
                   lambda d: d.__setitem__("constraints", [{}]),
                   lambda d: d.__setitem__("window", "xx"),
                   lambda d: d.__setitem__("unknown_field", 1),
                   lambda d: d.pop("robustness"),
                   lambda d: d.__setitem__("constraints", d["constraints"] * 3000)):
        q = copy.deepcopy(proof)
        mutate(q)
        bad = verify_proof(p, q)
        assert bad and all(isinstance(b, str) for b in bad)


_json = st.recursive(st.none() | st.booleans() | st.integers(-5, 400) | st.text(max_size=8),
                     lambda c: st.lists(c, max_size=4) | st.dictionaries(st.text(max_size=8), c, max_size=4), max_leaves=12)


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
@given(junk=_json)
def test_arbitrary_json_never_raises_and_never_verifies(junk):
    p, _ = base()
    assert verify_proof(p, junk) != []


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(key=st.sampled_from(["constraints", "candidates", "outsider", "cracked", "robustness", "window", "survivors",
                            "candidate_domain", "proof_core", "time_bins", "murder_loc", "fairness", "unique"]),
       junk=_json)
def test_a_real_proof_with_one_field_replaced_by_junk_never_raises(key, junk):
    p, proof = base()
    q = copy.deepcopy(proof)
    q[key] = junk
    out = verify_proof(p, q)
    assert isinstance(out, list)
    if q[key] != proof[key]:
        assert out != []


# ---------------------------------------------------------------------------- proof / package mismatch + the bundle
def test_a_proof_from_another_package_is_rejected():
    p, _ = base("study_party", 4)
    _p2, other = base("manor_wing", 4)
    rejects(p, other, "different package")


def _bundle(skel="study_party", seed=4, *, scale="full"):
    r = golden(skel, seed)
    rep = r.report.to_json()
    rep["stages"]["V-7"] = {**rep["stages"].get("V-7", {"ok": True}), "ok": True, "scale": scale}
    return r.package, copy.deepcopy(r.report.proof), rep


def _write(tmp_path, pkg, proof, rep, *, seal=None, name="c.json"):
    b = SealedCase.seal(pkg, proof, rep)
    doc = json.loads(b.model_dump_json())
    if seal is not None:
        doc["bundle_seal"] = seal
    f = tmp_path / name
    f.write_text(json.dumps(doc), encoding="utf-8")
    return str(f)


def test_a_sealed_bundle_loads_and_returns_the_verified_parts(tmp_path):
    pkg, proof, rep = _bundle()
    got = load_sealed_case(_write(tmp_path, pkg, proof, rep))
    assert got.package.seal == pkg.seal and got.bundle_seal == bundle_seal(pkg.seal, proof, rep)


def test_tampered_sealed_bundles_are_refused_swap_edit_resealed_forgery_and_reduced_scale(tmp_path):
    pkg, proof, rep = _bundle()
    # (a) a proof swapped in from another package
    _p2, other, _r2 = _bundle("manor_wing", 4)
    with pytest.raises(SealRefusal, match="different package"):
        load_sealed_case(_write(tmp_path, pkg, other, rep, name="a.json"))
    # (b) an edited proof, bundle seal NOT recomputed
    edited = copy.deepcopy(proof)
    edited["window"] = [edited["window"][0], edited["window"][1] + 1]
    good_seal = bundle_seal(pkg.seal, proof, rep)
    with pytest.raises(SealRefusal, match="bundle seal"):
        load_sealed_case(_write(tmp_path, pkg, edited, rep, seal=good_seal, name="b.json"))
    # (c) an edited proof, properly RESEALED: the seal is now valid and the proof is still a forgery
    with pytest.raises(SealRefusal, match="proof does not verify"):
        load_sealed_case(_write(tmp_path, pkg, edited, rep, name="c2.json"))
    # (d) an edited report (resealed): a forged green stage cannot be told from a real one unless its scale is
    pkg2, proof2, rep2 = _bundle(scale="reduced")
    with pytest.raises(SealRefusal, match="full scale"):
        load_sealed_case(_write(tmp_path, pkg2, proof2, rep2, name="d.json"))
    rep3 = copy.deepcopy(rep)
    rep3["stages"]["V-5"]["ok"] = False
    with pytest.raises(SealRefusal, match="every stage OK"):
        load_sealed_case(_write(tmp_path, pkg, proof, rep3, name="e.json"))
    # (e) a tampered package under the original proof
    forged_pkg = pkg.model_copy(update={"seed": pkg.seed + 1})
    with pytest.raises(SealRefusal, match="package seal"):
        load_sealed_case(_write(tmp_path, forged_pkg, proof, rep, name="f.json"))
    # (f) garbage and detached shapes
    (tmp_path / "g.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(SealRefusal):
        load_sealed_case(str(tmp_path / "g.json"))
    (tmp_path / "h.json").write_text(json.dumps({"package": {}, "proof": {}}), encoding="utf-8")
    with pytest.raises(SealRefusal):
        load_sealed_case(str(tmp_path / "h.json"))


# ---------------------------------------------------------------------------- independence (N-13)
def _imported_modules(path: Path) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for a in node.names:
                out.add((mod, a.name))
        elif isinstance(node, ast.Import):
            for a in node.names:
                out.add((a.name, ""))
    return out


@pytest.mark.parametrize("fname", ["proof.py", "proof_material.py"])
def test_the_verifier_imports_nothing_from_the_solver_side(fname):
    banned = {"solver", "lattice", "distort", "fairness", "bots"}
    for mod, name in _imported_modules(ROOT / fname):
        parts = set(mod.split(".")) | {name}
        assert not (parts & banned), f"{fname} imports {mod}.{name}"
    text = (ROOT / fname).read_text(encoding="utf-8")
    assert "BIN =" not in text and "MAX_WINDOW =" not in text           # constants come from package.py


def test_only_the_sanctioned_modules_touch_a_raw_proof_dict():
    """I-58: nothing but `solve/package.py`, `gen/pipeline.py` and `cli.py` reads `report.proof`/a proof file."""
    allowed = {"eidolon/solve/package.py", "eidolon/solve/proof.py", "eidolon/gen/pipeline.py", "eidolon/cli.py",
               "eidolon/solve/proof_material.py", "eidolon/gen/golden.py"}
    root = ROOT.parents[1]
    for f in (root / "eidolon").rglob("*.py"):
        rel = f.relative_to(root).as_posix()
        if rel in allowed:
            continue
        src = f.read_text(encoding="utf-8")
        assert ".proof[" not in src and "proof.json" not in src and "\"proof\"" not in src, rel


# ---------------------------------------------------------------------------- mutation-closing tests (RB3-b/i/j)
def test_a_forged_fairness_level_is_exactly_one_problem_it_never_re_derives_the_material_at_the_forged_level():
    """RB3-b: if the verifier read the level from the PROOF it would re-derive the (larger) L1 set at level 1 and
    report a pile of 'incomplete' constraints on top of the mismatch; reading it from the package gives exactly one."""
    p, proof = base()
    proof["fairness"] = 1
    bad = verify_proof(p, proof)
    assert len(bad) == 1 and "the sealed package says" in bad[0], bad


def test_a_voice_core_must_be_a_hard_heard_attack_at_the_murder_place_by_somebody_else():
    """RB3-i: the goldens carry no voice exclusion, so the check is driven directly with a core citing a constraint that
    is right in every respect except its KIND."""
    from eidolon.solve import proof as pr
    p, proof = base()
    mloc, (lo, hi) = proof["murder_loc"], proof["window"]
    others = [a for a in p.case.living_actors()]
    x, y = others[0], others[1]
    fake = pr.PConstraint(id="V", item="E_watch", kind="At", actor=y, loc=mloc, iv=[lo, hi], level=3, sources=[])
    ok = pr.PConstraint(id="V", item="E_watch", kind="Heard", actor=y, loc=mloc, iv=[lo, hi], level=3, sources=[])
    run = lambda c: _voice(pr, x, c, mloc, (lo, hi))
    assert run(fake), "a non-Heard constraint must not serve as a voice"
    assert run(ok) == []


def _voice(pr, x, c, mloc, window):
    bad: list = []
    pr._check_exclusion(None, x, pr.PCandidate(excluded=True, core=pr.VoiceCore(kind="VOICE", by="V"), times=[]),
                        {"how": "VOICE"}, {"V": c}, [], window, mloc, None, None, True, bad)
    return bad


def test_an_exception_inside_the_verifier_is_a_rejection_never_a_pass(monkeypatch):
    """RB3-j (fail closed, I-15)."""
    from eidolon.solve import proof as pr
    p, proof = base()

    def boom(*a, **k):
        raise RuntimeError("bug")
    monkeypatch.setattr(pr, "_verify", boom)
    assert verify_proof(p, proof) == ["verifier error: RuntimeError"]


def test_a_false_derived_constraint_is_reported_by_the_truth_audit(monkeypatch):
    """V1: the audit over the DERIVED hard set is wired into `verify_proof` — whatever it reports reaches the verdict."""
    p, proof = base()
    assert verify_proof(p, proof) == []
    monkeypatch.setattr(pm, "truth_audit", lambda case, victim, d: "forced")
    assert any(b.startswith("TRUTH AUDIT") and b.endswith("forced") for b in verify_proof(p, proof))


def test_a_distortion_that_matters_only_once_applied_is_still_relevant(monkeypatch):
    """B3: relevance is the union of the undistorted and the all-distorted derivations (ADR-28) — a shift whose atom yields a
    constraint only AFTER it is applied must not be dropped from the robustness sweep."""
    from types import SimpleNamespace as NS

    from eidolon.solve import distort
    from eidolon.solve.distort import TimeShift
    from eidolon.solve.lattice import Know
    from eidolon.world.propositions import At

    k = Know("S:1", "A", At(actor="A", location="L", interval=(10, 20)), "Participated", (), "L", (0, 50), 1)
    ctx = NS(atoms=[k], store=NS(all=lambda: []), case=NS(t_investigation=100), protected={}, comps={}, victim=None)
    monkeypatch.setattr(distort, "admissible", lambda case, store, mat, comps, victim: [
        NS(item=i) for i, x in mat.items() if getattr(x, "prop", None) is not None and x.prop.interval == (15, 25)])
    s = TimeShift(memory="M", actor="A", delta=5, know_ids=("S:1",))
    assert distort.relevant(ctx, [s], 2, frozenset()) == [s]
    assert distort.relevant(ctx, [], 2, frozenset()) == []
