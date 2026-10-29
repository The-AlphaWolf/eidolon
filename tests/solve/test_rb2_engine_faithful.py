"""RB-2 (Phase 6 re-audit): proof-core testimony could not be acquired through the engine, and the bots were not
engine-faithful. The bots credited themselves from the solver's own fixpoint, so a dead engine "solved" every case
(attack 42) and V-7 was `cued_depth <= N` (X18).

Recorded RED on the pre-fix tree (design §E / §A): a witness answered a whereabouts question with her own cover LIE
(probed), `predicate_hint="presence"` retrieved VAGUE where `"at"` retrieved TRUTH, an innocent's confession terminal
STONEWALLed forever, and `credited_material` did not exist — the bots read `ask_yields(robust_material(...))`.
"""
from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from eidolon.decision.query import Query
from eidolon.decision.turn import ExplorationTurnResult, TurnResult, run_ask_turn
from eidolon.gen.pipeline import validate
from eidolon.minds import accounts
from eidolon.solve import bots
from eidolon.solve import fairness as fair
from eidolon.solve.lattice import Know
from eidolon.solve.session import new_session
from tests.solve.helpers import GOLDEN, golden, loaded

GOLD = pytest.mark.parametrize("skel,seed", GOLDEN)
BOTS_SRC = Path(__file__).resolve().parents[2] / "eidolon" / "solve" / "bots.py"


def pk(skel, seed):
    return loaded(skel, seed).package


# ------------------------------------------------------------------------------- crediting (I-52)
@GOLD
def test_greedy_and_cue_following_bots_solve_every_golden_on_ledger_credit_only(skel, seed):
    p = pk(skel, seed)
    for bot, budget in ((bots.greedy_bot, bots.N_MAX), (bots.cue_following_bot, bots.N_CUE)):
        r = bot(p)
        assert r.ok and r.solved and r.survivors == [p.solution.murderer], (bot.__name__, r.to_json())
        assert r.actions <= budget and r.rejected == 0


@GOLD
def test_a_dead_engine_solves_nothing(skel, seed, monkeypatch):
    """Attack 42 (X15/X16): with `run_ask_turn` rejecting everything and searches finding nothing, a bot that credits
    itself from the ENGINE's commits holds nothing and solves nothing; one that read the solver's pool would not notice."""
    p = pk(skel, seed)
    dead = lambda state, who, query, **kw: TurnResult(state=state, text="", plan_act="", events=(), rejected=True,
                                                      violations=("DEAD",))
    nothing = lambda state, target, action: ExplorationTurnResult(state=replace(state, turn_counter=state.turn_counter + 1),
                                                                  text="", discovered=None)
    monkeypatch.setattr(bots, "run_ask_turn", dead)
    monkeypatch.setattr(bots, "run_search_turn", nothing)
    for bot in (bots.greedy_bot, bots.cue_following_bot):
        r = bot(p)
        assert not r.solved and r.survivors != [p.solution.murderer] and not r.ok, bot.__name__


def test_credit_ignores_rejected_turns_lies_and_other_peoples_perceptions():
    p = pk("study_party", 4)
    token = p.accounts[0]
    hk = accounts.parse(token)[1]
    state, _n, _f = bots._discover_all(new_session(p))
    base = bots.credited_material(state)
    assert set(base) == set(state.discovery.known_evidence)                     # evidence only: nothing was said
    # a rejected turn commits nothing and credits nothing
    rej = run_ask_turn(state, hk, Query(kind="challenge", raw="x"), presented_ref=token)
    assert rej.rejected and bots.credited_material(rej.state) == base
    # a LIE (no grounding) credits nothing, however many times it is said
    lie_q = Query(kind="did_you", raw="Were you there?")
    spoken = state
    for _ in range(3):
        spoken = run_ask_turn(spoken, hk, lie_q).state
    assert all(not isinstance(v, Know) for v in bots.credited_material(spoken).values())
    # a faithful delivery credits exactly the atom its claim is grounded on, with the proposition AS SAID
    from tests.solve.test_rb1_accounts import hear_token
    delivered = hear_token(p, state, token)
    credited = {k: v for k, v in bots.credited_material(delivered).items() if isinstance(v, Know)}
    assert credited and set(credited) & set(accounts.atoms_of(p.case, token))
    assert {v.who for v in credited.values()} == {hk}
    # an UNCORRECTED DISTORTION is credited as said: the same atom, a shifted proposition (V-5's robustness model)
    st = next(s for s in delivered.decision.statements.all() if token in s.accounts)
    c = next(c for c in st.claims if c.grounding)
    shifted = c.proposition.model_copy(update={"interval": (c.proposition.interval[0] + 7, c.proposition.interval[1] + 7)})
    from eidolon.decision.claims import StatementStore

    def distort(s):                        # every statement that delivered this entry is recalled shifted
        return s.model_copy(update={"claims": tuple(x.model_copy(update={"proposition": shifted})
                                                    if c.grounding[0] in x.grounding else x for x in s.claims)})
    swapped = replace(delivered, decision=replace(delivered.decision, statements=StatementStore(
        [distort(s) for s in delivered.decision.statements.all()])))
    got = bots.credited_material(swapped)
    atom = accounts.atom_of_entry(p.case, delivered.knowledge, c.grounding[0])
    assert got[atom].prop == shifted
    # a claim grounded on SOMEBODY ELSE's perception credits nothing
    other = next(a for a in p.case.living_actors() if a != hk)
    swapped2 = replace(delivered, decision=replace(delivered.decision, statements=StatementStore(
        [s.model_copy(update={"speaker": other}) if c.grounding[0] in {g for x in s.claims for g in x.grounding} else s
         for s in delivered.decision.statements.all()])))
    assert atom not in bots.credited_material(swapped2)


@GOLD
def test_a_question_that_names_nothing_yields_nothing(skel, seed):
    """§20.1 item 5: no load-bearing fact is obtained by a character volunteering it. 'What happened?', 'Why?' and
    smalltalk name no actor, place or time, so the engine commits no claim grounded on a perception."""
    p = pk(skel, seed)
    state, _n, _f = bots._discover_all(new_session(p))
    base = bots.credited_material(state)
    for who in sorted(p.case.living_actors()):
        for kind in ("what", "why", "smalltalk", "narrative", "recall_detail", "opinion"):
            res = run_ask_turn(state, who, Query(kind=kind, raw="What happened?"))
            assert not res.rejected
            assert bots.credited_material(res.state) == base, (who, kind)


def test_the_bots_module_reads_no_solver_pool():
    """AST: nothing in `bots.py` may reference the solver's fixpoint or the old pool-crediting helpers."""
    names = {n.id for n in ast.walk(ast.parse(BOTS_SRC.read_text(encoding="utf-8"))) if isinstance(n, ast.Name)} | \
            {n.attr for n in ast.walk(ast.parse(BOTS_SRC.read_text(encoding="utf-8"))) if isinstance(n, ast.Attribute)} | \
            {a.name for n in ast.walk(ast.parse(BOTS_SRC.read_text(encoding="utf-8"))) if isinstance(n, ast.ImportFrom) for a in n.names}
    assert not names & {"robust_material", "robust_trace", "obtainable", "ask_yields", "testimony_pool", "Acquired"}, names
    # the canonical solution is read exactly once, to JUDGE the bluff bot's convergence (§19.7: "the murderer must be identified
    # no better than chance"); the solving bots never see it — the pipeline compares their survivor with it (I-53)
    tree = ast.parse(BOTS_SRC.read_text(encoding="utf-8"))
    readers = [f.name for f in ast.walk(tree) if isinstance(f, ast.FunctionDef)
               and any(isinstance(n, ast.Attribute) and n.attr == "solution" for n in ast.walk(f))]
    assert readers == ["bluff_bot"], readers


# ------------------------------------------------------------------------------- V-7 is wired (X18)
def test_v7_rejects_when_a_bot_fails(monkeypatch):
    p = golden("study_party", 4).package
    real = bots.run_bots

    def failing(pkg, **kw):
        out = real(pkg, names=("cue_following", "murderer_peel", "bluff", "adversarial"), bluffs=kw["bluffs"], odd=kw["odd"])
        out["greedy"] = bots.BotReport("greedy", 1, False, [], 0, 0, {}, {"ok": False})
        return out

    monkeypatch.setattr(bots, "run_bots", failing)
    rep = validate(p, bluffs=2, odd=2)
    assert rep.failed_at == "V-7" and any("greedy bot" in x for x in rep.problems), (rep.failed_at, rep.problems)


def test_v7_records_its_scale_and_only_full_scale_seals():
    full = loaded("study_party", 4).report["stages"]["V-7"]
    assert full["scale"] == "full" and full["bluffs_per_character"] == bots.N_BLUFF
    assert full["adversarial_per_character"] == bots.N_ADVERSARIAL and full["ok"]
    reduced = golden("study_party", 4).report.stages["V-7"]
    assert reduced["scale"] == "reduced"
    assert set(full["bots"]) == {"greedy", "cue_following", "murderer_peel", "bluff", "adversarial"}


# ------------------------------------------------------------------------------- the engine delivers proof-core testimony
@GOLD
def test_every_proof_core_atom_and_breaker_account_is_deliverable_by_the_real_engine(skel, seed):
    """V-4's I-39 is engine-faithful: each target is delivered by a real `Query` from a fresh session."""
    c = loaded(skel, seed)
    p = c.package
    core_atoms = {i for i in c.proof["proof_core"] if i.startswith("S:")}
    tokens = set(p.accounts)
    out = fair.engine_retrieval(p, core_atoms, tokens)
    assert out["ok"], out["problems"]
    assert out["checked"] == len(core_atoms | tokens)


@GOLD
def test_a_witness_answers_truthfully_outside_their_secret_footprint(skel, seed):
    """C1-C3: the housekeeper asked about the cleaning at the cleaning's own half-hour used to answer with her cover LIE."""
    p = pk(skel, seed)
    token = p.accounts[0]
    hk = accounts.parse(token)[1]
    state, _n, _f = bots._discover_all(new_session(p))
    names = bots.held_names(state, bots.public_names(p.case))
    hits = [(q, run_ask_turn(state, hk, q)) for q in bots.expressible_queries(p.case, hk, names)]
    delivering = [(q, r) for q, r in hits if not r.rejected and token in r.state.decision.statements.all()[-1].accounts]
    assert delivering and all(r.plan_act == "TRUTH" for _q, r in delivering)


@GOLD
def test_the_cover_still_answers_questions_inside_the_secret_footprint(skel, seed):
    """(guard) §29.2 turns 1-2: 'where were you' with no time named is about the speaker's secret — the secret is topical,
    the cover is a candidate, and the speaker NEVER answers with the protected truth. (Whether LIE or a non-committal act
    wins is the scorer's, personality-dependent and unchanged: `goal_fit` and the weights are not touched.)"""
    from eidolon.decision.turn import relevant_secret
    p = pk(skel, seed)
    state = new_session(p)
    q = Query(kind="where", raw="Where were you?")
    for sec in p.secrets:
        assert relevant_secret(sec.owner, state.secrets, q, None, state.evidence) is sec
        r = run_ask_turn(state, sec.owner, q)
        assert r.plan_act in {"LIE", "DONT_RECALL", "EVASION", "COUNTER_QUESTION", "DONT_KNOW", "VAGUE"}, (sec.owner, r.plan_act)
        said = r.state.decision.statements.all()[-1].claims
        assert not any(c.proposition in sec.protected for c in said)


@GOLD
def test_protected_interval_knowledge_is_never_spoken_before_concession(skel, seed):
    """I-54: every atom whose observation segment overlaps an unconceded protected interval of its holder, asked by every
    expressible question, is never committed — the runtime counterpart of the solver's layer-0 withholding (I-45)."""
    p = pk(skel, seed)
    base = new_session(p)
    names = bots.public_names(p.case)
    for e in p.evidence:
        from eidolon.solve.queries import names_from_evidence
        names = names.union(names_from_evidence(p.case, e))
    from eidolon.world.perception import derive_perception
    pfs = {pf.id: pf for pf in derive_perception(p.case)}
    for sec in p.secrets:
        who = sec.owner
        ivs = sec.protected_intervals()
        withheld = {a for a in (f"S:{i}" for i in pfs) if pfs[a[2:]].observer == who and
                    any(pfs[a[2:]].obs_interval[0] < hi and lo < pfs[a[2:]].obs_interval[1] for lo, hi in ivs)}
        assert withheld
        for q in bots.expressible_queries(p.case, who, names):
            res = run_ask_turn(base, who, q)
            if res.rejected:
                continue
            for c in res.state.decision.statements.all()[-1].claims:
                for g in c.grounding:
                    assert accounts.atom_of_entry(p.case, base.knowledge, g) not in withheld, (who, q.raw)


@GOLD
def test_bluff_parity_ignores_presuppositions_under_the_new_topicality(skel, seed):
    """(guard, §6.5) matched pairs identical but for the premise's truth get identical acts."""
    r = bots.bluff_bot(pk(skel, seed), per_character=40)
    assert r.detail["parity_ok"], r.detail["parity_breaks"]
    assert not r.detail["converged"] and r.peels == 0 and not r.detail["leaks"]


def test_v4_i39_is_engine_faithful_a_dead_or_lying_engine_fails_it(monkeypatch):
    """C7: the old check scored a memory against its OWN cue set, so it passed whatever the engine did."""
    p = pk("study_party", 4)
    c = loaded("study_party", 4)
    atoms = {i for i in c.proof["proof_core"] if i.startswith("S:")}
    tokens = set(p.accounts)
    assert fair.engine_retrieval(p, atoms, tokens)["ok"]
    dead = lambda state, who, query, **kw: TurnResult(state=state, text="", plan_act="", events=(), rejected=True,
                                                      violations=("DEAD",))
    monkeypatch.setattr(fair, "run_ask_turn", dead)
    out = fair.engine_retrieval(p, atoms, tokens)
    assert not out["ok"] and len(out["problems"]) == len(atoms | tokens)


def test_without_the_memory_boosts_the_breaker_account_is_not_deliverable():
    """§19.4 / C5: boosts are applied at LOAD (`new_session`); strip them and the housekeeper only hedges (VAGUE)."""
    p = pk("study_party", 4)
    stripped = p.model_copy(update={"memory_boosts": ()})
    assert not fair.engine_retrieval(stripped, set(), set(p.accounts))["ok"]
    assert fair.engine_retrieval(p, set(), set(p.accounts))["ok"]


# ---------------------------------------------------------------------------- mutation-closing tests (RB2-k/l/m/n)
def _fake_reports(murderer, **override):
    ok = lambda n, **d: bots.BotReport(n, 10, True, [murderer] if n in ("greedy", "cue_following") else [], 0, 0, {},
                                       {"ok": True, "converged": False, **d})
    out = {n: ok(n) for n in ("greedy", "cue_following", "murderer_peel", "bluff", "adversarial")}
    out.update(override)
    return out


@pytest.mark.parametrize("which,report", [
    ("greedy", lambda m: bots.BotReport("greedy", 10, True, ["Somebody Else"], 0, 0, {}, {"ok": True})),
    ("cue_following", lambda m: bots.BotReport("cue_following", 10, True, ["Somebody Else"], 0, 0, {}, {"ok": True})),
    ("murderer_peel", lambda m: bots.BotReport("murderer_peel", 10, False, [], 0, 0, {}, {"ok": False})),
    ("bluff", lambda m: bots.BotReport("bluff", 10, True, [], 0, 0, {}, {"ok": False, "converged": True})),
    ("adversarial", lambda m: bots.BotReport("adversarial", 10, False, [], 1, 0, {}, {"ok": False})),
])
def test_v7_is_gated_on_every_bot_and_on_the_canonical_murderer(which, report, monkeypatch):
    """RB2-k/l/m: each gate of I-53 rejects on its own — a wrong survivor from a bot that 'solved', a murderer who is never
    peeled through play, a converging bluff bot, a peeling/leaking adversarial bot."""
    p = golden("study_party", 4).package
    m = p.solution.murderer
    monkeypatch.setattr(bots, "run_bots", lambda pkg, **kw: _fake_reports(m, **{which: report(m)}))
    rep = validate(p, bluffs=1, odd=1)
    assert rep.failed_at == "V-7" and rep.problems and which.split("_")[0] in " ".join(rep.problems), rep.problems
    monkeypatch.setattr(bots, "run_bots", lambda pkg, **kw: _fake_reports(m))
    assert validate(p, bluffs=1, odd=1).ok


def test_a_retracted_statement_is_not_credited_to_the_bot():
    """RB2-n: material the speaker has taken back (a concession retracted it) is not something the bot holds."""
    from tests.solve.test_rb1_accounts import hear_token
    p = pk("study_party", 4)
    token = p.accounts[0]
    state, _n, _f = bots._discover_all(new_session(p))
    delivered = hear_token(p, state, token)
    atoms = set(accounts.atoms_of(p.case, token))
    assert atoms & set(bots.credited_material(delivered))
    store = delivered.decision.statements
    for st in list(store.all()):
        store = store.retract(st.id, "S99999")
    retracted = replace(delivered, decision=replace(delivered.decision, statements=store))
    assert not atoms & set(bots.credited_material(retracted))


def test_credit_requires_the_atoms_observer_to_be_the_speaker(monkeypatch):
    """R9: even when the speaker's OWN entry resolves (by a corrupted index) to an atom somebody else perceived, nothing is
    credited — the entry guard and the observer guard are independent checks."""
    p = pk("study_party", 4)
    token = p.accounts[0]
    hk = accounts.parse(token)[1]
    state, _n, _f = bots._discover_all(new_session(p))
    from tests.solve.test_rb1_accounts import hear_token
    delivered = hear_token(p, state, token)
    assert any(isinstance(v, Know) for v in bots.credited_material(delivered).values())
    foreign = next(a for a, f in accounts._index(p.case, delivered.knowledge).by_atom.items() if f.observer != hk)
    monkeypatch.setattr(accounts, "atom_of_entry", lambda *a, **k: foreign)
    assert not any(isinstance(v, Know) for v in bots.credited_material(delivered).values())
