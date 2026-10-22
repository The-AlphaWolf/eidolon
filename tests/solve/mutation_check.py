"""Controlled mutation verification for Phase 6 (docs/EIDOLON-PHASE-6-REPORT.md). From the repo root:

    python -m tests.solve.mutation_check                # every mutant against tests/solve + tests/gen
    python -m tests.solve.mutation_check quick         # the fast subset, against tests/solve only

Same protocol as `tests.decision.mutation_check`: each mutation is a list of exact
`(relpath, old, new)` replacements, `old` must occur EXACTLY once (a mutation can never silently
no-op), it is applied to a fresh copy of the repo, and it is KILLED iff the selected tests fail.
The unmutated baseline must be green first. Results: KILLED / SURVIVED / EQUIVALENT / ERROR.
A survivor that is not listed in EQUIVALENT is a gap in the suite and is reported as UNEXPECTED —
the harness exits non-zero. Nothing here claims the set is strong because every mutant died: the
mutants were chosen to attack the specific decisions listed in the Phase 6 brief.
"""
import os, re, shutil, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
S, G, W = "eidolon/solve/", "eidolon/gen/", "eidolon/world/"
TIMEOUT = int(os.environ.get("MUT_TIMEOUT", "1500"))     # seconds per mutant (baseline takes ~4 min)

M = {
  # ---------------- uniqueness condition ----------------
  "U1 unique ignores the outsider corridor": [(S+"solver.py", 'v.unique = (len(v.survivors) == 1 and v.outsider["excluded"] and len(v.time_bins) == 1', 'v.unique = (len(v.survivors) == 1 and len(v.time_bins) == 1')],
  "U2 unique ignores time under-determination": [(S+"solver.py", 'and v.outsider["excluded"] and len(v.time_bins) == 1', 'and v.outsider["excluded"]')],
  "U3 unique accepts >= 1 survivor": [(S+"solver.py", 'v.unique = (len(v.survivors) == 1 and', 'v.unique = (len(v.survivors) >= 1 and')],
  "U4 unique ignores fail-closed classes (accident/accomplice)": [(S+"solver.py", "                and not ctx.admits and not ctx.accomplice)", "                )")],
  # ---------------- survivor calculation / candidate enumeration ----------------
  "S1 excluded candidates still count as survivors": [(S+"solver.py", 'v.survivors = [X for X, e in v.candidates.items() if not e["excluded"]]', 'v.survivors = [X for X, e in v.candidates.items()]')],
  "S2 per-candidate feasibility never excludes": [(S+"solver.py", "        elif not feasible_actor(ctx, X, hard, hyp)[0]:", "        elif False:")],
  "S3 hypothesis is tested at the wrong location": [(S+"solver.py", 'hyp = [Constraint("HYP", "HYP", "Exist", X, ctx.murder_loc, (lo, hi), 3)]', 'hyp = [Constraint("HYP", "HYP", "Exist", X, sorted(ctx.case.locations)[0], (lo, hi), 3)]')],
  "S4 the last living candidate is never enumerated": [(S+"solver.py", "    for X in sorted(ctx.case.living_actors()):\n        hyp =", "    for X in sorted(ctx.case.living_actors())[:-1]:\n        hyp =")],
  "S5 the layer-0 fixpoint never cracks an innocent": [(S+"solver.py", 'if e["excluded"] and X in ctx.protected) - cracked', 'if False and X in ctx.protected) - cracked')],
  "S6 time is never resolved tick by tick": [(S+"solver.py", "            for t in range(lo, hi):\n                h = [Constraint", "            for t in range(lo, lo + 1):\n                h = [Constraint")],
  # ---------------- timeline / time pin ----------------
  "T1 the Died pin does not narrow the murder window": [(S+"solver.py", 'if c.kind in ("Died", "Heard") and c.loc == ctx.murder_loc:\n            lo, hi = max', 'if c.kind in ("Heard",) and c.loc == ctx.murder_loc:\n            lo, hi = max')],
  "T2 a wide window is approximated instead of reported": [(S+"solver.py", "        elif hi - lo > MAX_WINDOW:", "        elif False:")],
  # ---------------- outsider / containment / reachability ----------------
  "O1 containment blocks are ignored by the phantom": [(S+"solver.py", '    blocked = {(c.loc, t) for c in hard if c.kind == "NoStranger" for t in ticks(c.iv)}\n    goal =', '    blocked = set()\n    goal =')],
  "O2 the phantom need not exit": [(S+"solver.py", "{}, [goal], goal=EXT)", "{}, [goal], goal=None)")],
  "O3 the phantom may start inside the house": [(S+"solver.py", "[(EXT, 0)], blocked, {}, [goal]", "[(L, 0) for L in ctx.case.locations], blocked, {}, [goal]")],
  # ---------------- DP / travel / oracle ----------------
  "P1 travel is one minute faster than the graph says": [(W+"feasibility.py", 'nxt.setdefault((("~", nb, max(0, minutes - 2)), m), (state, m))', 'nxt.setdefault((("~", nb, max(0, minutes - 3)), m), (state, m))')],
  "P2 the oracle lets an edge be crossed one tick early": [(S+"oracle.py", "            t2 = t + d\n            while t2 < T:", "            t2 = t + d - 1\n            while t2 < T:")],
  # ---------------- lattice: evidence support, provenance, collusion ----------------
  "L1 collusion is ignored when corroborating": [(S+"lattice.py", "return a.who != b.who and comps.get(a.who) != comps.get(b.who) and not (set(a.events) & set(b.events))", "return a.who != b.who and not (set(a.events) & set(b.events))")],
  "L2 provenance need not be disjoint": [(S+"lattice.py", "comps.get(a.who) != comps.get(b.who) and not (set(a.events) & set(b.events))", "comps.get(a.who) != comps.get(b.who)")],
  "L3 planted evidence is admissible": [(S+"lattice.py", "        if not ev.authentic:\n            continue\n        for j, imp in enumerate(ev.implications):\n            if imp.requires:\n                continue\n            iv =", "        for j, imp in enumerate(ev.implications):\n            if imp.requires:\n                continue\n            iv =")],
  "L4 P-9 temporal grounding is not enforced for L3": [(S+"lattice.py", '            if iv is not None and not contains(established_interval(imp, store, T, stmt, ev.created_at), iv):\n                continue\n            c = _as_constraint(imp.proposition, f"{ev.id}#{j}", ev.id, L3,', '            c = _as_constraint(imp.proposition, f"{ev.id}#{j}", ev.id, L3,')],
  "L5 protected-interval testimony is not withheld": [(S+"lattice.py", "if k.who not in cracked and any(overlaps(k.obs_iv, iv) for iv in protected.get(k.who, ())):", "if False:")],
  "L6 a requires chain is as strong as its evidence, not its weakest link": [(S+"lattice.py", "level = min([L3] + [lvl[i] for i in req])", "level = L3")],
  "L7 one fixed tick fixes the whole segment (the rejected reading)": [(S+"lattice.py", 'if fix == "segment" and fixed:', 'if fixed:')],
  "L8 testimony granularity is ignored": [(S+"lattice.py", "        return shrink(k.prop.interval, k.g)", "        return k.prop.interval")],
  "L9 `requires` resolves to any testimony, not the actor's own account": [(S+"lattice.py", "            hits = [a for a in accounts.atoms_of(case, r) if a in mat]", "            hits = [i for i, it in mat.items() if isinstance(it, Know)]")],
  "L10 a statement establishes the wrong interval": [("eidolon/minds/accounts.py", "    return {format_token(ev, actor): by_id[ev].interval", "    return {format_token(ev, actor): (0, 1)")],
  # ---------------- proof + independent verification ----------------
  "V1 the verifier's truth audit is off": [(S+"proof.py", "        why = pm.truth_audit(case, victim, d)\n        if why:", "        why = None\n        if why:")],
  "V2 the verifier does not check deletion-minimality": [(S+"proof.py", "        elif minimal:", "        elif False:")],
  "V3 the verifier does not re-check exclusion cores": [(S+"proof.py", "        if oracle.feasible(x, sub, _hyp(mloc, window)):", "        if False:")],
  "V4 the verifier does not re-derive uniqueness": [(S+"proof.py", "    if P.unique != unique:", "    if False:")],
  "V5 the verifier does not check the seal": [(S+"proof.py", "    if not pkg.verify_seal():\n        bad.append(\"package seal does not verify\")", "    if False:\n        bad.append(\"package seal does not verify\")")],
  "V6 the verifier does not re-derive the outsider verdict": [(S+"proof.py", "    if P.outsider.excluded == solved.corridor:", "    if False:")],
  "V7 judge() accepts any survivor": [(S+"solver.py", "    if v.survivors != [sol.murderer]:", "    if False:")],
  "V8 the proof core is not minimal": [(S+"solver.py", "        if size == 1:\n            break", "        if size >= 1:\n            break")],
  # ---------------- robustness to distortions ----------------
  "B1 distortion subsets are never checked": [(S+"distort.py", "        if not v.unique or v.survivors != survivors:", "        if False:")],
  "B2 no distortion is ever relevant": [(S+"distort.py", "    return [s for s in shifts if set(s.know_ids) & seen]", "    return []")],
  "B3 only the undistorted derivation decides relevance": [(S+"distort.py", "    seen = items([]) | items(shifts)", "    seen = items([])")],
  # ---------------- generation: determinism, stages ----------------
  "D1 the planner is not seeded": [(G+"planner.py", "    rng = random.Random(seed)\n    dr = Draft(skel, seed)", "    rng = random.Random()\n    dr = Draft(skel, seed)")],
  "D2 the planner iterates a set (hash-order dependent)": [(G+"planner.py", "    for a in sorted({M, rng.choice(sorted(others))}):", "    for a in {M, rng.choice(sorted(others))}:")],
  "D3 the distortion pick is not reproducible": [(G+"pipeline.py", 'key=lambda d: hashlib.sha256(f"{pkg.id}|{d.memory}".encode()).hexdigest())', "key=lambda d: id(d))")],
  "G1 validation never records a failing stage": [(G+"pipeline.py", "        rep.failed_at, rep.problems = name, list(problems)", "        pass")],
  "G2 the physics stage is skipped": [(G+"pipeline.py", "        p = [str(x) for x in check_physics(case)]\n        p += [str(x) for x in check_evidence_grounding", "        p = []\n        p += [str(x) for x in check_evidence_grounding")],
  "G3 the solver stage does not judge the verdict against the canonical solution": [(G+"pipeline.py", "        p = list(v.reasons) + judge(pkg, v)", "        p = list(v.reasons)")],
  "G4 the verifier is not run on the proof": [(G+"pipeline.py", "        bad = verify_proof(pkg, proof) if verify else []", "        bad = []")],
  # ---------------- fairness ----------------
  "F1 proof-core items need not be on a cued path": [(S+"fairness.py", '    bad += [f"proof-core item {i} is not on a fully-cued path" for i in core_ev if i not in rep.cued]\n    bad += [f"load-bearing item {i} unreachable" for i in declared if i in rep.unreachable]\n    bad += [f"load-bearing item {i} reachable only uncued" for i in declared if i in rep.reachable and i not in rep.cued]', "    pass")],
  "F4 bluffing may converge": [(S+"fairness.py", "    return evaluate(ctx, {}, fairness, want_cores=False).unique", "    return False")],
  "F2 deliverability is never required (I-39)": [(S+"fairness.py", "        if not found:\n            bad.append(", "        if False:\n            bad.append(")],
  "F3 lies need no breaker": [(S+"fairness.py", "        if not broken:\n            breaks.append", "        if False:\n            breaks.append")],
  # ---------------- blocker repairs (B-1 bots, B-2 covers/V-3, B-3 band gate, B-4 proof domain) ----
  "R4 (B-1) the bluff bot never converges": [(S+"bots.py", "    converged = argmax == [pkg.solution.murderer] and best > 0", "    converged = False")],
  "R5 (B-1) the bluff bot ignores response parity": [(S+"bots.py", '            if outcomes[0][0] != outcomes[1][0]:', "            if False:")],
  "R6 (B-1) the bluff bot ignores layer peels": [(S+"bots.py", '{"ok": not converged and peels == 0 and not leaked and not parity_breaks,', '{"ok": not converged and not leaked and not parity_breaks,')],
  "R7 (B-1) a bot is handed material it never acquired": [(S+"bots.py", "    return evaluate(ctx, credited_material(state), want_cores=False)", "    from .lattice import know_atoms, material\n    return evaluate(ctx, material(ctx.store.all(), {k.id: k for k in know_atoms(ctx.case)}), want_cores=False)")],
  "R8 (B-1) the cue-following bot ignores cues": [(S+"bots.py", "            if (ev.discovery.cue or ev.discovery.at) not in named:     # uncued: a cue-follower never tries it\n                continue", "            if False:\n                continue")],
  "R9 (B-1) somebody else's perception is credited to the speaker": [(S+"bots.py", "                if pf is None or pf.observer != st.speaker:", "                if pf is None:")],
  "R10 (B-2) V-3's real contract is not run": [(G+"pipeline.py", "        p += [str(x) for x in check_cover_consistency(list(pkg.secrets), dctx, murder_check)]", "        p += []")],
  "R11 (B-2) the murderer needs no breaker set": [(G+"pipeline.py", '            if s.kind == "murder" and not breakers.get((s.id, 0)):', "            if False:")],
  "R12 (B-2) a declared account need not resolve": [(G+"pipeline.py", "            if parsed is None or not accounts.atoms_of(case, t):", "            if False:")],
  "R13 (B-2) breaker items need not be reachable": [(S+"fairness.py", '                        bad.append(f"{sid} layer {index}: breaker item {ref} is not on a fully-cued path")', "                        pass")],
  "R14 (B-3) the band is reported, not gated": [(G+"pipeline.py", '        bad += [f"band: {b}" for b in band_bad]', "        bad += []")],
  "R15 (B-3) every knob is in band by definition": [(S+"fairness.py", "        if got != difficulty:", "        if False:")],
  "R16 (B-3) the band loop reseeds a non-band failure too": [(G+"pipeline.py", "        if not (last.failed_at == \"V-6\" and band_bad):\n            break", "        if False:\n            break")],
  "R17 (B-3) the band loop gives up after one attempt": [(G+"pipeline.py", "    for attempt in range(max_attempts):", "    for attempt in range(1):")],

  # ---------------- RB-3: the independent verifier (I-57, I-58, I-59) ----------------
  "X1 (RB-3) the authored role labels are trusted over the CaseLog (offstage relabel)": [(S+"proof_material.py", "    if dom != sorted(case.living_actors()):", "    if False:")],
  "X3 (RB-3) a Heard constraint is true for ANY actor": [(S+"proof_material.py", "and (c.actor is None or e.actor == c.actor) for e in ev)", "for e in ev)")],
  "X6 (RB-3) a survivor's recorded times are carried, not re-derived": [(S+"proof.py", '            elif got.times != want["times"]:', "            elif False:")],
  "X7 (RB-3) the murder window is carried, not re-derived": [(S+"proof.py", "    if tuple(P.window) != solved.window:", "    if False:")],
  "X21 (RB-3) the NoStranger observer is dropped": [(S+"lattice.py", 'return Constraint(cid, item, "NoStranger", None, prop.location, iv, level, sources, observer=prop.observer)', 'return Constraint(cid, item, "NoStranger", None, prop.location, iv, level, sources, observer=None)')],
  "RB3-a the constraint set is not checked for completeness": [(S+"proof.py", "    for k in sorted(derived - claimed, key=repr)[:8]:", "    for k in []:")],
  "RB3-b the fairness level is read from the proof": [(S+"proof.py", "    fairness = pkg.fairness_level\n    # 2. candidate domain", "    fairness = P.fairness\n    # 2. candidate domain")],
  "RB3-c a constraint's item is never resolved": [(S+"proof.py", "        if c.item not in universe and not any(c.item == e.id for e in pkg.evidence):", "        if False:")],
  "RB3-d proof_core minimality is not checked": [(S+"proof.py", "    if minimal:\n        for i in core:", "    if False:\n        for i in core:")],
  "RB3-e robustness is not recomputed": [(S+"proof.py", "    if P.robustness.subsets_run != n:", "    if False:")],
  "RB3-f the bundle seal is not checked": [(S+"package.py", "    if case.bundle_seal != bundle_seal(pkg.seal, case.proof, case.report):", "    if False:")],
  "RB3-g the cracked set is not recomputed": [(S+"proof.py", "    if got_cracked != want_cracked:", "    if False:")],
  "RB3-h a forged proof_core is sufficient by assertion": [(S+"proof.py", "    if not uniq or s.survivors != survivors:", "    if False:")],
  "RB3-i the voice core is not checked": [(S+"proof.py", "        if (c is None or c.kind != \"Heard\" or c.loc != mloc or not c.actor or c.actor == x", "        if (False and c.kind != \"Heard\" or c.loc != mloc or not c.actor or c.actor == x")],
  "RB3-j an exception inside the verifier is a pass": [(S+"proof.py", '        return [f"verifier error: {type(e).__name__}"]', "        return []")],
  # ---------------- RB-1: account identity and delivery-only hearing (I-49…I-51, I-60) ----------------
  "RB1-a a lie mints an account": [("eidolon/minds/accounts.py", 'if (claim.sincerity != "truthful" or claim.modality != "actual" or claim.source != "plan"\n            or claim.confidence != "certain"):', "if False:")],
  "RB1-b minting skips the proposition-equality check": [("eidolon/minds/accounts.py", "and entry.proposition.kind == \"Did\" and entry.proposition == claim.proposition):", "and entry.proposition.kind == \"Did\"):")],
  "RB1-c presentation is not checked (I-51)": [("eidolon/decision/turn.py", "    if presented_ref is not None and (why := unheld_reason(state, presented_ref)):", "    if False:")],
  "RB1-d the heard fold does not check the statement lists the token": [("eidolon/decision/exploration.py", "    if event.token not in st.accounts:", "    if False:")],
  "RB1-e the heard fold does not check the speaker": [("eidolon/decision/exploration.py", "    if parsed is None or parsed[1] != st.speaker:", "    if False:")],
  "RB1-f V-3 (vi): an owner's own account may break their cover": [("eidolon/decision/cover_consistency.py", "            if parsed is not None and parsed[1] == secret.owner:", "            if False:")],
  "RB1-g the housekeeper may be the murderer": [(G+"planner.py", "    M = dr.murderer = rng.choice([a for a in living if role[a] != \"housekeeper\"])", "    M = dr.murderer = rng.choice(living)")],
  "RB1-h every committed statement is NOT heard": [("eidolon/decision/turn.py", "    heard = [StatementHeardEvent(statement_id=statement_id, turn=turn_id)]\n", "    heard = []\n")],
  "RB1-i an account is only deliverable if nobody withholds it is ignored (I-54 in V-3)": [("eidolon/decision/cover_consistency.py", "        if owner not in conceded and any(overlaps(seg, iv) for iv in protected.get(owner, ())):", "        if False:")],
  # ---------------- RB-2: engine-faithful interrogation (I-52…I-56) ----------------
  "RB2-a speakable is always true": [("eidolon/decision/speakable.py", "              knowledge, case) -> bool:\n    for s in secrets.for_owner(speaker):", "              knowledge, case) -> bool:\n    return True\n    for s in secrets.for_owner(speaker):")],
  "RB2-b the len(owned)==1 whereabouts fallback is restored": [("eidolon/decision/turn.py", "        if secret_topical(s, layer_of(s), query, addressee):\n            return s\n    return None", "        if secret_topical(s, layer_of(s), query, addressee):\n            return s\n    if len(owned) == 1 and query.kind in (\"where\", \"when\", \"did_you\", \"did_they\", \"who\"):\n        return owned[0]\n    return None")],
  "RB2-c LIE ignores whether it covers the asked proposition": [("eidolon/decision/strategy.py", "    if not any(c.sincerity == \"deceptive\" and claim_covers(c.proposition, inp.query, inp.character)\n               and on_topic(c.proposition, inp.query) for c in layer.claims):\n        return None", "    if not layer.claims:\n        return None")],
  "RB2-d the confession gate is applied to every secret again": [("eidolon/decision/peel.py", "    return secret.kind == \"murder\" or any(c.proposition.kind == \"Solution\" for c in layer.claims)", "    return True")],
  "RB2-e memory boosts are not applied at load": [(S+"session.py", "                                if m.id in boosts else m for m in mems)", "                                if False else m for m in mems)")],
  "RB2-f V-7 always passes": [(G+"pipeline.py", "        return not p, p, {\"scale\": \"full\" if full else \"reduced\"", "        return True, [], {\"scale\": \"full\" if full else \"reduced\"")],
  "RB2-g retrieval takes the first strong memory, not the best": [("eidolon/decision/turn.py", "                        key=lambda m: (-score(m, epistemic, cues), _mem_tiebreak(m.id)))", "                        key=lambda m: 0)")],
  "RB2-h retrieval always takes content[0]": [("eidolon/decision/turn.py", "            cands.sort(key=lambda b: (-cue_overlap(_cues_for_prop(b.proposition), cues), b.id))", "            cands = cands[:1]")],
  "RB2-i presence hints are not mapped onto the `at` topic": [("eidolon/decision/turn.py", "(_TOPIC_OF_HINT.get(hint, hint),) if hint else ())", "(hint,) if hint else ())")],
  "RB2-j V-4 deliverability is not run through the engine": [(S+"fairness.py", "                if _delivers(run_ask_turn(st, who, q), want_atoms, want_tokens, st):", "                if True:")],
  "RB2-k the murderer-peel bot is not a V-7 gate": [(G+"pipeline.py", "        if not res[\"murderer_peel\"].ok:", "        if False:")],
  "RB2-l the greedy/cue bots need not name the canonical murderer": [(G+"pipeline.py", "            if r.survivors != [murderer] or not r.solved:", "            if not r.solved:")],
  "RB2-m the bluff/adversarial bots are not V-7 gates": [(G+"pipeline.py", "            if not res[name].ok:\n                p.append(f\"{name} bot:", "            if False:\n                p.append(f\"{name} bot:")],
  "RB2-n a retracted statement is still credited to the bot": [(S+"bots.py", "        if st.retracted_by is not None:\n            continue\n        for c in st.claims:\n            if c.modality", "        for c in st.claims:\n            if c.modality")],
  "RB2-o finalize never climbs the boost ladder": [(G+"pipeline.py", "    for level in fair.BOOST_LADDER:", "    for level in fair.BOOST_LADDER[:1]:")],
}

# Mutants the suite is EXPECTED to survive because they change nothing observable (with the reason).
EQUIVALENT: dict[str, str] = {}


SEL = {   # a mutant is only ever run against the tests that can possibly kill it, to keep the sweep tractable
    "RB3": ["tests/solve/test_rb3_verifier.py", "tests/solve/test_mutation_gaps.py", "tests/solve/test_blocker_repairs.py"],
    "RB1": ["tests/solve/test_rb1_accounts.py", "tests/decision", "tests/gen/test_covers_and_bands.py"],
    "RB2": ["tests/solve/test_rb2_engine_faithful.py", "tests/decision/test_topicality.py", "tests/solve/test_blocker_repairs.py",
            "tests/decision/test_phase5_readiness.py", "tests/gen/test_covers_and_bands.py"],
}


def selection_for(name, default):
    for k, v in SEL.items():
        if name.startswith(k) or (k == "RB3" and name.startswith(("X1 ", "X3 ", "X6 ", "X7 ", "X21 "))):
            return v
    return default


def run(name, edits, selection):
    tmp = tempfile.mkdtemp(prefix="mut6_")
    try:
        for d in ("eidolon", "tests"):
            shutil.copytree(os.path.join(REPO, d), os.path.join(tmp, d), ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(os.path.join(REPO, "pyproject.toml"), tmp)
        if os.path.isdir(os.path.join(REPO, "cases")):
            shutil.copytree(os.path.join(REPO, "cases"), os.path.join(tmp, "cases"))
        for rel, old, new in edits:
            p = os.path.join(tmp, rel)
            src = open(p, encoding="utf8").read()
            n = src.count(old)
            if n != 1:
                return {"name": name, "error": f"anchor matched {n}x in {rel}: {old[:70]!r}"}
            open(p, "w", encoding="utf8").write(src.replace(old, new))
        try:
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *selection],
                               cwd=tmp, capture_output=True, text=True, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            # a mutant that makes the suite non-terminating within TIMEOUT is detected (the suite cannot pass) —
            # reported as a timeout-kill, distinct from an assertion failure
            return {"name": name, "killed": True, "error_only": False, "failed": [], "summary": f"TIMEOUT after {TIMEOUT}s"}
        failed = sorted(set(re.findall(r"^FAILED (\S+)", r.stdout, re.M)))
        errored = bool(re.search(r"^ERROR ", r.stdout, re.M)) and not failed
        summary = (r.stdout.strip().splitlines() or ["?"])[-1]
        return {"name": name, "killed": r.returncode != 0, "error_only": errored, "summary": summary, "failed": failed}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    quick = sys.argv[1:2] == ["quick"]
    selection = ["tests/solve"] if quick else ["tests/solve", "tests/gen"]
    base = run("baseline (no mutation)", [], selection)
    if base.get("killed") is not False:
        print("BASELINE IS NOT GREEN — mutation results would be meaningless:", base)
        sys.exit(2)
    print("baseline green:", base["summary"], flush=True)
    only = os.environ.get("MUT_ONLY")            # regex on the mutant name: re-run a subset (e.g. earlier survivors)
    items = [(n, e) for n, e in M.items() if not only or re.search(only, n)]
    with ThreadPoolExecutor(max_workers=int(os.environ.get("MUT_WORKERS", "6"))) as pool:
        results = list(pool.map(lambda item: run(item[0], item[1], selection_for(item[0], selection)), items))
    ok, counts = True, {"KILLED": 0, "SURVIVED": 0, "EQUIVALENT": 0, "ERROR": 0}
    for res in results:
        if "error" in res:
            ok = False
            counts["ERROR"] += 1
            print(f"ERROR      {res['name']}: {res['error']}")
            continue
        if res["name"] in EQUIVALENT and not res["killed"]:
            counts["EQUIVALENT"] += 1
            print(f"EQUIVALENT {res['name']}\n           {EQUIVALENT[res['name']]}")
            continue
        good = res["killed"]
        counts["KILLED" if good else "SURVIVED"] += 1
        ok &= good
        print(("KILLED     " if good else "SURVIVED   <-- UNEXPECTED ") + res["name"] + f"\n           {res['summary']}")
        for f in res["failed"][:3]:
            print(f"             - {f}")
    print("\nCOUNTS:", counts)
    print("MUTATION VERIFICATION:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
