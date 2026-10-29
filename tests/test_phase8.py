"""Phase 8 (§30, §16, §26.2; I-10, I-12, I-14, I-15, I-16, I-26): the player's controls, their event producers, the fold rules
that bind them, the case report, the strict projection and the browser app.

Every control runs through `eidolon.game`, which commits ONLY through `Save.append` — the validating fold. The engine's live
state is compared with the folded one after every new transition, and saves are reloaded (same process, fresh processes) to
the same hash. The forged-row versions of each new fold rule live in `tests/test_persistence.py` (`FORGERIES`, `P8_*`): there
every one is offered to `append` AND, re-chained, to `Save.open`.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

from eidolon import game, store
from eidolon.decision.hypotheses import Lied, Planted
from eidolon.decision.speech_acts import ACT_TABLE
from eidolon.decision.turn import CANARY, run_accusation_turn, run_ask_turn, run_goto_turn, run_hypothesis_turn
from eidolon.solve.bots import held_names
from eidolon.solve.queries import expressible_queries, public_names
from eidolon.store import Save, SaveRefusal
from eidolon.world.propositions import At, Motive, entities

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "cases" / "generated"
LOCAL = "http://127.0.0.1:8000"          # what a browser sends to `eidolon serve` (Host and Origin)
BUNDLE = CASES / "study_party_s4.json"
MURDERER, WEAPON, ROOM, WINDOW, MOTIVE = "David", "Decanter", "Study", (59, 60), "blackmail"


def step(save, control, *args, **kw):
    """One player action, the way the browser sends it: a fresh action id for this form at this head, and the head the
    page was rendered at."""
    return control(save, f"{control.__name__}@{save.last_seq}", save.last_seq, *args, **kw)


def frozen(save):
    return save.state_hash(), save.last_seq, save.last_hash


def discover_everything(save):
    """Search every spot in prerequisite order until nothing new opens (what a careful player does)."""
    while True:
        before = len(save.state.discovery.known_evidence)
        for ev in sorted(save.state.evidence.all(), key=lambda e: e.id):
            if ev.id not in save.state.discovery.known_evidence:
                step(save, game.search, ev.discovery.at, ev.discovery.action)
        if len(save.state.discovery.known_evidence) == before:
            return


def question_everyone(save):
    """Every parser-expressible question (the V-7 vocabulary, `solve.queries`) to every living character."""
    for who in sorted(save.state.case.living_actors()):
        for q in expressible_queries(save.state.case, who, held_names(save.state, public_names(save.state.case))):
            step(save, game.ask, who, q)


def copy_of(path, tmp_path, name="g.db"):
    p = tmp_path / name
    shutil.copy(path, p)
    return Save.open(p, writable=True)


@pytest.fixture(scope="module")
def blank(tmp_path_factory):
    p = tmp_path_factory.mktemp("blank") / "g.db"
    Save.create(p, BUNDLE, seed=7).close()
    return p


@pytest.fixture(scope="module")
def played(tmp_path_factory):
    """Played through the controls only: the study, every search, one question to each character."""
    p = tmp_path_factory.mktemp("played") / "g.db"
    s = Save.create(p, BUNDLE, seed=7)
    assert step(s, game.goto, ROOM).ok
    discover_everything(s)
    for who in sorted(s.state.case.living_actors()):
        assert step(s, game.ask, who, game.question(s.state.case, who, topic="presence", place=ROOM, bucket=1)).ok
    s.close()
    return p


@pytest.fixture(scope="module")
def questioned(tmp_path_factory, played):
    """`played`, then every expressible question to everyone: enough testimony for a proof without the stored core."""
    p = tmp_path_factory.mktemp("questioned") / "g.db"
    shutil.copy(played, p)
    s = Save.open(p, writable=True)
    question_everyone(s)
    s.close()
    return p


@pytest.fixture
def save(played, tmp_path):
    s = copy_of(played, tmp_path)
    yield s
    s.close()


@pytest.fixture
def fresh(blank, tmp_path):
    s = copy_of(blank, tmp_path, "fresh.db")
    yield s
    s.close()


def _held_statement(s, speaker=None):
    return next(i for i in sorted(s.state.discovery.known_statements)
                if speaker is None or s.state.decision.statements.get(i).speaker == speaker)


# ============================================================================== hypotheses (§16.1)
def test_a_hypothesis_is_created_revised_and_withdrawn_each_as_one_recorded_turn(save):
    st = _held_statement(save)
    speaker = save.state.decision.statements.get(st).speaker
    ev = sorted(save.state.discovery.known_evidence)[0]
    props = (At(actor="Elena", location=ROOM, interval=(50, 60)), Lied(actor=speaker, statement=st), Planted(evidence=ev))
    t0 = save.state.turn_counter
    out = step(save, game.hypothesize, props, 7000)
    assert out.ok and save.state.turn_counter == t0 + 1
    (h,) = save.state.decision.hypotheses
    assert (h.id, h.created_turn, h.updated_turn, h.propositions, h.player_confidence) == (f"H{t0 + 1:05d}", t0 + 1, t0 + 1, props, 0.7)
    assert step(save, game.hypothesize, props[:1], 2500, revise=h.id).ok
    (h2,) = save.state.decision.hypotheses
    assert (h2.id, h2.created_turn, h2.updated_turn, h2.propositions, h2.player_confidence) == (h.id, t0 + 1, t0 + 2, props[:1], 0.25)
    assert [x["id"] for x in game.notebook(save)["hypotheses"]] == [h.id]
    assert step(save, game.withdraw, h.id).ok
    assert save.state.decision.hypotheses[0].status == "withdrawn" and save.state.turn_counter == t0 + 3
    assert game.notebook(save)["hypotheses"] == []                       # a withdrawn hypothesis leaves the board
    before = frozen(save)
    assert step(save, game.hypothesize, props[:1], 5000, revise=h.id).status == "rejected"     # withdrawal is terminal
    assert step(save, game.withdraw, h.id).status == "rejected"
    assert frozen(save) == before
    h_ = save.state_hash()
    assert Save.open(save.path).state_hash() == h_


def _bad_hypotheses(s):
    other = next(a for a in sorted(s.state.case.living_actors())
                 if a != s.state.decision.statements.get(_held_statement(s)).speaker)
    T = s.state.case.t_investigation
    return {
        "planted_on_unheld_evidence": ((Planted(evidence="E_secret_Margaret"),), {}),
        "lied_on_a_statement_never_heard": ((Lied(actor="David", statement="S99999"),), {}),
        "lied_about_another_speakers_words": ((Lied(actor=other, statement=_held_statement(s)),), {}),
        "an_actor_the_case_lacks": ((At(actor="Ghost", location=ROOM, interval=(0, 10)),), {}),
        "a_place_the_case_lacks": ((At(actor="Elena", location="Atlantis", interval=(0, 10)),), {}),
        "a_window_off_the_clock": ((At(actor="Elena", location=ROOM, interval=(0, T + 1)),), {}),
        "a_motive_float_N6": ((Motive(actor="David", victim="Harold", motive_kind=MOTIVE, strength=0.7),), {}),
        "a_confidence_above_one": ((At(actor="Elena", location=ROOM, interval=(0, 10)),), {"confidence_bp": 12000}),
        "revising_an_unknown_hypothesis": ((At(actor="Elena", location=ROOM, interval=(0, 10)),), {"revise": "H99999"}),
        "no_proposition_at_all": ((), {}),
    }


BAD_HYPOTHESES =["planted_on_unheld_evidence", "lied_on_a_statement_never_heard", "lied_about_another_speakers_words",
                  "an_actor_the_case_lacks", "a_place_the_case_lacks", "a_window_off_the_clock", "a_motive_float_N6",
                  "a_confidence_above_one", "revising_an_unknown_hypothesis", "no_proposition_at_all"]


@pytest.mark.parametrize("name", BAD_HYPOTHESES)
def test_an_invalid_hypothesis_is_rejected_and_changes_nothing(request, name):
    """Unknown, unheld or contradictory references, and the N-6 floats, are refused — and a refusal records nothing: no
    row, no turn, no hash change (I-15). (`played` holds every item, so the unheld-item case runs on a blank save.)"""
    save = request.getfixturevalue("fresh" if name == "planted_on_unheld_evidence" else "save")
    props, kw = _bad_hypotheses(request.getfixturevalue("save"))[name]
    before = frozen(save)
    out = step(save, game.hypothesize, props, kw.pop("confidence_bp", 5000), **kw)
    assert out.status == "rejected" and out.reply == ""
    assert frozen(save) == before and save.state.decision.hypotheses == ()


def test_the_hypothesis_runner_shapes_exactly_one_board_row_per_turn(save):
    res = run_hypothesis_turn(save.state, (At(actor="Elena", location=ROOM, interval=(0, 10)),), 5000)
    assert [e.kind for e in res.events] == ["TurnCommitted", "HypothesisChanged"]
    assert res.events[0].character is None and res.events[1].hypothesis.updated_turn == save.state.turn_counter + 1


# ============================================================================== accusations (§16.3, §11.3)
def test_a_provisional_accusation_is_recorded_for_the_accused_and_never_peels(save):
    case = save.state.case
    t = save.state.turn_counter + 1
    res = run_ask_turn(save.state, "Margaret", game.question(case, "Margaret", topic="presence"), provisional_accusation=True)
    kinds = [e.kind for e in res.events]
    assert kinds.count("Accusation") == 1 and kinds.count("DetectiveModelUpdate") == 1
    assert kinds.index("Accusation") < kinds.index("DetectiveModelUpdate")
    assert step(save, game.ask, "Margaret", game.question(case, "Margaret", topic="presence"), accuse=True).ok
    acc = save.state.decision.accusations[-1]
    assert (acc.turn, acc.target, acc.provisional) == (t, "Margaret", True)
    assert save.state.characters["Margaret"].detective_model.accusations[-1] == (t, True, "Margaret")
    peels = save.state.decision.layer_peels
    for i in range(30):                                                  # I-16: accusation spam never peels
        assert step(save, game.ask, "Margaret", game.question(case, "Margaret", topic="did", bucket=i % 4), accuse=True).ok
    assert save.state.decision.layer_peels == peels
    assert len(save.state.characters["Margaret"].detective_model.accusations) == 31
    assert Save.open(save.path).state_hash() == save.state_hash()


@pytest.mark.parametrize("target,correct", [(MURDERER, True), ("Elena", False), ("Outsider", False)])
def test_a_final_accusation_closes_the_case_with_the_proven_verdict(save, target, correct):
    held = sorted(save.state.discovery.known_evidence)
    out = step(save, game.accuse, target, weapon=WEAPON, location=ROOM, interval=WINDOW, motive_kind=MOTIVE, cited=held)
    assert out.ok
    solved, acc = save.state.decision.solved, save.state.decision.accusations[-1]
    assert solved.correct is correct and solved.turn == acc.turn == save.state.turn_counter and not acc.provisional
    assert (acc.target, acc.weapon, acc.location, acc.interval, acc.motive_kind, acc.cited) == (target, WEAPON, ROOM, WINDOW, MOTIVE, tuple(held))
    before = frozen(save)
    q = game.question(save.state.case, "Elena", topic="presence")
    for o in (step(save, game.goto, "Hall"), step(save, game.accuse, MURDERER), step(save, game.ask, "Elena", q),
              step(save, game.hypothesize, (At(actor="Elena", location=ROOM, interval=(0, 10)),), 5000)):
        assert o.status == "rejected"                                    # the case is closed: nothing more is recorded
    assert frozen(save) == before
    assert Save.open(save.path).state.decision.solved == solved


def test_no_turn_follows_the_verdict_at_append_or_at_a_rechained_load_PN10(save, tmp_path):
    assert step(save, game.accuse, MURDERER).ok
    after = run_goto_turn(save.state, "Hall")
    assert not after.rejected                                            # the runner alone would happily move on...
    with pytest.raises(SaveRefusal, match="already solved"):
        save.append(after.events, save.last_seq, "after-the-verdict")     # ...the fold will not
    p = tmp_path / "forged.db"
    shutil.copy(save.path, p)
    from tests.test_persistence import inject
    inject(p, after.events, "after-the-verdict")
    with pytest.raises(SaveRefusal, match="already solved"):
        Save.open(p)


def _bad_accusations():
    return {
        "cites_evidence_never_found": dict(cited=("E_secret_Margaret",)),
        "cites_a_statement_never_made": dict(cited=("S99999",)),
        "cites_an_account_token": dict(cited=("clean@Elena",)),
        "names_a_weapon_the_case_lacks": dict(weapon="Excalibur"),
        "names_a_place_the_case_lacks": dict(location="Atlantis"),
        "a_window_off_the_clock": dict(interval=(0, 10 ** 6)),
        "a_reversed_window": dict(interval=(60, 50)),
    }


@pytest.mark.parametrize("name", list(_bad_accusations()))
def test_an_accusation_unsupported_by_legitimately_held_material_is_rejected(fresh, name):
    before = frozen(fresh)
    out = step(fresh, game.accuse, MURDERER, **_bad_accusations()[name])
    assert out.status == "rejected" and frozen(fresh) == before and fresh.state.decision.solved is None


@pytest.mark.parametrize("target", ["Nobody", "Harold", ""])
def test_an_accusation_outside_the_candidate_domain_is_rejected(fresh, target):
    before = frozen(fresh)
    assert step(fresh, game.accuse, target).status == "rejected"
    assert frozen(fresh) == before


def test_the_accusation_runner_shapes_the_verdict_from_the_proven_murderer(fresh):
    assert fresh.state.murderer == fresh.bundle.proof["survivors"][0] == MURDERER     # the PI-7-verified survivor
    res = run_accusation_turn(fresh.state, "Elena")
    assert [e.kind for e in res.events] == ["TurnCommitted", "Accusation", "CaseSolved"]
    assert res.events[0].character is None and res.events[2].correct is False


def test_the_runners_reject_what_the_fold_would_refuse(save):
    """Defence in depth: the runners refuse the obvious cases themselves (state untouched, no rows), as `run_goto_turn`
    does; the fold remains the contract (`FORGERIES` P8_*)."""
    from dataclasses import replace
    st = save.state
    unproven = replace(st, murderer=None)
    for given, res in ((st, run_accusation_turn(st, "Nobody")), (st, run_accusation_turn(st, MURDERER, cited=("E_never_found",))),
                       (unproven, run_accusation_turn(unproven, MURDERER)),
                       (st, run_hypothesis_turn(st, (At(actor="Elena", location=ROOM, interval=(0, 10)),), 5000, revise="H99999")),
                       (st, run_hypothesis_turn(st, withdraw="H99999")), (st, run_hypothesis_turn(st, (), 5000)),
                       (st, run_hypothesis_turn(st, (At(actor="Elena", location=ROOM, interval=(0, 10)),), 10001))):
        assert res.rejected and res.events == () and res.state is given
    closed = run_accusation_turn(st, MURDERER).state
    assert run_accusation_turn(closed, MURDERER).rejected
    assert run_hypothesis_turn(closed, (At(actor="Elena", location=ROOM, interval=(0, 10)),), 5000).rejected


def test_a_verdict_needs_a_proven_murderer_to_be_judged_against(save):
    """A state with no verified survivor (a bare package, never a save) cannot be given a verdict — the fold refuses,
    it does not guess (PN-10, I-15)."""
    from dataclasses import replace
    events = run_accusation_turn(save.state, "Elena").events
    with pytest.raises(SaveRefusal, match="no proven murderer"):
        store.fold_turn(replace(save.state, murderer=None), events, "x")


# ============================================================================== the case report (§16.3, N-7)
def test_there_is_no_report_before_the_verdict(save):
    assert game.report(save) is None


def test_the_report_scores_five_axes_against_the_caselog(save):
    held = sorted(save.state.discovery.known_evidence)
    assert step(save, game.accuse, MURDERER, weapon=WEAPON, location=ROOM, interval=(55, 65), motive_kind=MOTIVE, cited=held).ok
    r = game.report(save)
    assert r["axes"] == {"who": True, "method": True, "place_and_time": True, "motive": True, "evidence": True}
    assert r["truth"]["who"] == "David" and r["truth"]["where"] == "the study"
    assert any(row["kind"] == "Attack" for row in r["timeline"])


@pytest.mark.parametrize("kw,lost", [(dict(location="Library"), "place_and_time"), (dict(interval=(0, 30)), "place_and_time"),
                                     (dict(motive_kind="jealousy"), "motive"), (dict(weapon=None), "method"),
                                     (dict(cited=()), "evidence")])
def test_each_axis_is_scored_on_its_own(save, kw, lost):
    form = dict(weapon=WEAPON, location=ROOM, interval=WINDOW, motive_kind=MOTIVE, cited=sorted(save.state.discovery.known_evidence))
    assert step(save, game.accuse, MURDERER, **{**form, **kw}).ok
    axes = game.report(save)["axes"]
    assert [a for a, ok in axes.items() if not ok] == [lost]


def test_an_alternative_valid_proof_earns_full_evidence_credit(questioned, tmp_path):
    """§16.3: evidence is scored by solver uniqueness on the CITED set, never by subset of the stored proof core — so a
    proof that replaces a core item with testimony the player really heard is full credit."""
    s = copy_of(questioned, tmp_path)
    core = set(s.bundle.proof["proof_core"])
    held = s.state.discovery.known_evidence | s.state.discovery.known_statements
    alternative = sorted(held - {"E_alibi_room"})
    assert not core <= set(alternative) and game.establishes(s, alternative)
    assert not game.establishes(s, sorted(core - {"E_watch"}))
    assert step(s, game.accuse, MURDERER, cited=alternative).ok
    assert game.report(s)["axes"]["evidence"] is True
    s.close()


def test_the_scorer_never_reads_the_stored_proof_core_or_the_declared_solution():
    import inspect
    src = inspect.getsource(game.report) + inspect.getsource(game.establishes)
    assert "proof_core" not in src and ".solution" not in src


# ============================================================================== save / load / replay (§26, I-5)
def test_live_play_equals_the_fold_after_every_new_transition_and_a_resumed_save_continues_identically(played, tmp_path):
    s = copy_of(played, tmp_path)
    case = s.state.case
    turns = [
        lambda st: run_hypothesis_turn(st, (At(actor="Elena", location=ROOM, interval=(50, 60)),), 6000),
        lambda st: run_hypothesis_turn(st, (At(actor="Elena", location=ROOM, interval=(40, 60)),), 3000, revise=st.decision.hypotheses[0].id),
        lambda st: run_ask_turn(st, "Robert", game.question(case, "Robert", topic="presence"), provisional_accusation=True),
        lambda st: run_ask_turn(st, "Elena", game.question(case, "Elena", presenting=True), presented_ref="E_secret_Elena",
                                provisional_accusation=True),
        lambda st: run_hypothesis_turn(st, withdraw=st.decision.hypotheses[0].id),
    ]
    for i, turn in enumerate(turns):
        res = turn(s.state)
        assert not res.rejected, getattr(res, "violations", ())
        s.append(res.events, s.last_seq, f"t{i}")
        assert store.state_hash(res.state) == s.state_hash(), f"transition {i}: live state != folded state"
    assert {"LayerPeel"} <= {k for k in _kinds(s.path)}                  # the presentation really conceded a layer
    shutil.copy(s.path, tmp_path / "resume.db")
    verdict = run_accusation_turn(s.state, MURDERER, weapon=WEAPON, location=ROOM, interval=WINDOW, motive_kind=MOTIVE,
                                  cited=sorted(s.state.discovery.known_evidence))
    s.append(verdict.events, s.last_seq, "verdict")
    assert store.state_hash(verdict.state) == s.state_hash()
    resumed = Save.open(tmp_path / "resume.db", writable=True)        # a reloaded save continues exactly like the live one
    again = run_accusation_turn(resumed.state, MURDERER, weapon=WEAPON, location=ROOM, interval=WINDOW, motive_kind=MOTIVE,
                                cited=sorted(resumed.state.discovery.known_evidence))
    resumed.append(again.events, resumed.last_seq, "verdict")
    assert (resumed.state_hash(), resumed.last_hash) == (s.state_hash(), s.last_hash)
    assert Save.open(s.path).state_hash() == s.state_hash()
    resumed.close()
    s.close()


def _kinds(path):
    with sqlite3.connect(path) as c:
        return [k for (k,) in c.execute("SELECT kind FROM session_events")]


@pytest.mark.parametrize("seed", ["0", "1", "4242"])
def test_a_phase8_save_replays_to_the_same_hash_in_a_fresh_process(save, seed):
    assert step(save, game.hypothesize, (At(actor="Elena", location=ROOM, interval=(50, 60)),), 6000).ok
    assert step(save, game.ask, "Robert", game.question(save.state.case, "Robert", topic="did"), accuse=True).ok
    assert step(save, game.accuse, MURDERER, weapon=WEAPON, cited=sorted(save.state.discovery.known_evidence)).ok
    code = f"from eidolon.store import Save; print(Save.open({str(save.path)!r}).state_hash())"
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
                         env={**os.environ, "PYTHONHASHSEED": seed}, timeout=300)
    assert out.returncode == 0, out.stderr[-500:]
    assert out.stdout.strip() == save.state_hash()


# ============================================================================== I-14 at the control
def test_a_retried_action_returns_its_committed_turn_and_a_stale_page_commits_nothing(save):
    q = game.question(save.state.case, "Elena", topic="presence", place=ROOM, bucket=2)
    aid, seq = f"ask@{save.last_seq}", save.last_seq
    first = game.ask(save, aid, seq, "Elena", q)
    assert first.ok and first.reply
    before = frozen(save)
    again = game.ask(save, aid, seq, "Elena", q)                          # the browser re-sends the same form
    assert again.status == "duplicate" and again.turn == first.turn and frozen(save) == before
    other_tab = game.ask(save, "ask@other-tab", seq, "Elena", q)          # a second tab rendered at the old head
    assert other_tab.status == "stale" and frozen(save) == before


def test_a_runner_rejection_commits_nothing_and_shows_no_in_world_text(save):
    before = frozen(save)
    out = step(save, game.ask, "Elena", game.question(save.state.case, "Elena", presenting=True), present="clean@Elena")
    assert out.status == "rejected" and out.reply == "" and frozen(save) == before        # I-51 / I-12 / I-15
    assert step(save, game.goto, "Atlantis").status == "rejected" and frozen(save) == before
    assert step(save, game.ask, "Ghost", game.question(save.state.case, "Elena")).status == "rejected"
    assert frozen(save) == before


def test_the_question_builder_speaks_the_v7_vocabulary(save):
    """A player can put exactly the questions the V-7 bots solve every sealed case with (§19.7, ADR-29)."""
    case = save.state.case
    for q in expressible_queries(case, "Elena", held_names(save.state, public_names(case))):
        built = game.question(case, "Elena", topic=q.predicate_hint, about=q.subject.id if q.subject else None,
                              place=q.location, bucket=q.time.interval[0] // 30)
        assert (built.kind, built.subject, built.location, built.predicate_hint, built.time) == (
            q.kind, q.subject, q.location, q.predicate_hint, q.time)


# ============================================================================== projection (§12.1 stage 11, §13.4, §30)
def _engine_only_tokens(s):
    """Everything the player must never be shown: act and sincerity labels, engine field names, and every engine id."""
    st = s.state
    words = set(ACT_TABLE) | {"truthful", "sincere_false", "deceptive", "grounding", "sincerity", "layer_scope", "plan_act",
                              "verbal_pressure", "composure", "refutation", "authentic", "proof_core", "query_hash",
                              "trust_detective", "suspicion_of_detective", CANARY}
    ids = {sec.id for sec in st.secrets.all()} | {e.id for e in st.evidence.all()} | {k.id for k in st.knowledge.all()}
    ids |= {m.id for ms in st.memories.values() for m in ms}
    ids |= {b.id for a in st.case.living_actors() for b in st.beliefs.for_character(a)}
    ids |= set(s.bundle.package.accounts)
    return words, ids


def _leaks(text, s):
    words, ids = _engine_only_tokens(s)
    return sorted({w for w in words if re.search(rf"(?<![\w-]){re.escape(w)}(?![\w-])", text)} | {i for i in ids if i in text})


def test_no_projection_serializes_an_engine_only_field_or_identifier(played, tmp_path):
    from starlette.testclient import TestClient
    from eidolon import web
    saves = tmp_path / "saves"
    saves.mkdir()
    shutil.copy(played, saves / "case.db")
    with TestClient(web.create_app(saves, CASES), base_url=LOCAL) as c:      # every change goes through HTTP (one SQLite thread)
        page = c.get("/g/case").text
        s = c.app.state.games.open("case")                               # used below for in-memory reads only
        page = post(c, "case", "ask", page, addressee="Elena", present=game.handle(s, "E_secret_Elena")).text
        assert {"LayerPeel"} <= set(_kinds(s.path))                       # a concession happened: its act must not show
        page = post(c, "case", "hypothesize", page, kind="Planted", item=game.handle(s, "E_watch"), confidence="40").text
        page = post(c, "case", "hypothesize", page, kind="Lied", statement=_held_statement(s), confidence="60").text
        page = post(c, "case", "ask", page, addressee="Robert", topic="did", accuse="on").text
        assert len(s.state.decision.hypotheses) == 2 and s.state.decision.accusations
        assert c.get("/g/case/report").status_code == 404                # the answer stays sealed until the verdict
        assert not _leaks(page, s) and not _leaks(json.dumps(game.notebook(s)), s)
        assert not re.search(r"\b(murderer|solution|culprit)\b", page, re.I)
        page = post(c, "case", "accuse", page, suspect=MURDERER, weapon=WEAPON, confirm="on",
                    cited=[game.handle(s, e) for e in sorted(s.state.discovery.known_evidence)]).text
        assert s.state.decision.solved is not None
        for path in ("/g/case", "/g/case/report"):
            assert not _leaks(c.get(path).text, s), path
        assert not _leaks(json.dumps(game.report(s)), s)


def test_every_notebook_tension_is_between_two_items_the_player_holds(questioned, tmp_path):
    """§13.4: tensions are listed only between two held items, never with which side is true. A contradiction id that
    does not resolve to held material cannot reach the notebook (the fold side: `R1_contradiction_nothing_resolves`)."""
    s = copy_of(questioned, tmp_path)
    nb = game.notebook(s)
    shown = {x["ref"] for x in nb["evidence"]} | {x["ref"] for x in nb["statements"]}
    assert nb["tensions"], "a questioned case has tensions to show"
    for t in nb["tensions"]:
        assert {t["a"], t["b"]} <= shown and set(t) == {"a", "b", "a_label", "b_label"}
    s.close()


# ============================================================================== H8-B1: the player reasons over UNLOCKED implications
SEALED = ("study_party_s4", "study_party_s5", "manor_wing_s4", "manor_wing_s6")


def _known(s):
    d = s.state.discovery
    return frozenset(d.known_evidence | d.known_statements | d.known_accounts)


def _find_the_print(s):
    """Find the scene, then dust the weapon — the two searches the pages offer. The player now HOLDS `E_trace`."""
    scene, trace = s.state.evidence.get("E_scene"), s.state.evidence.get("E_trace")
    while "E_scene" not in s.state.discovery.known_evidence:
        assert step(s, game.search, scene.discovery.at, scene.discovery.action).ok
    assert step(s, game.search, trace.discovery.at, trace.discovery.action).ok
    assert "E_trace" in s.state.discovery.known_evidence
    return trace


def _hear(s, who):
    for q in expressible_queries(s.state.case, who, held_names(s.state, public_names(s.state.case))):
        step(s, game.ask, who, q)


def _print_label(s):
    return next(x["label"] for x in game.notebook(s)["evidence"] if x["ref"] == game.handle(s, "E_trace"))


def _tied_to(s, label):
    """(theory texts, tensions) that name the item `label` — what the notebook says about it."""
    nb = game.notebook(s)
    return ([h["text"] for h in nb["hypotheses"] if label in h["support"] + h["against"]],
            [t for t in nb["tensions"] if label in (t["a_label"], t["b_label"])])


@pytest.mark.parametrize("case", SEALED)
def test_H8_B1_a_locked_implication_reaches_no_theory_and_no_tension_until_its_account_is_heard(case, tmp_path):
    """§5.2 / §16.1: the player reasons over the implications they have UNLOCKED. In every sealed case the weapon print's
    only implication names the murderer and is locked behind the housekeeper's cleaning account: while that account is
    unheld, no theory (`At`, `Lied`, `Planted`) and no tension may be tied to the print — the board used to link it to the
    murderer alone. Once the account is heard the same theory IS tied: the filter is the unlock, not a blanket ban."""
    from eidolon.evidence.discovery import unlocked_implications
    from eidolon.minds import accounts as acct
    s = Save.create(tmp_path / "g.db", CASES / f"{case}.json", seed=7)
    trace = _find_the_print(s)
    (imp,) = trace.implications
    (token,) = imp.requires
    keeper, murderer = acct.parse(token)[1], s.state.murderer
    for who in sorted(s.state.characters):
        if who != keeper:
            _hear(s, who)
    assert token not in s.state.discovery.known_accounts and unlocked_implications(trace, _known(s)) == []
    label = _print_label(s)
    named = {x for e in s.state.discovery.known_evidence for i in s.state.evidence.get(e).implications
             for part in entities(i.proposition) for x in part}
    quiet = sorted(set(s.state.case.locations) - named - {s.state.evidence.get(e).discovery.at for e in s.state.discovery.known_evidence})[0]
    for who in sorted(s.state.characters):                      # the print's own place and a place no held item names
        for place, window in ((imp.proposition.location, imp.proposition.interval), (quiet, (0, 10))):
            assert step(s, game.hypothesize, (At(actor=who, location=place, interval=window),), 5000).ok
    for sid in sorted(s.state.discovery.known_statements):      # the murderer's own words, and every held item
        if s.state.decision.statements.get(sid).speaker == murderer:
            assert step(s, game.hypothesize, (Lied(actor=murderer, statement=sid),), 5000).ok
    for e in sorted(s.state.discovery.known_evidence):
        assert step(s, game.hypothesize, (Planted(evidence=e),), 5000).ok
    theories, tensions = _tied_to(s, label)
    assert theories == [] and tensions == [], (theories, tensions)
    _hear(s, keeper)
    assert token in s.state.discovery.known_accounts and unlocked_implications(trace, _known(s)) == [imp]
    theories, _ = _tied_to(s, label)
    assert theories and game.describe(s, At(actor=murderer, location=quiet, interval=(0, 10))) in theories
    assert not [t for t in theories if t.startswith(game.name(s.state.case, next(a for a in sorted(s.state.characters)
                                                                                  if a not in (murderer, keeper))))
                and f"in {game.name(s.state.case, quiet)} " in t]       # only the actor can link a theory about a quiet place
    s.close()


@pytest.mark.parametrize("case", SEALED)
def test_H8_B1_the_rendered_game_page_ties_the_print_to_no_one_before_its_account_is_heard(client, case):
    """The same attack as the browser sends it, and what the player reads: two searches, then a throw-away theory per
    suspect about a place no held item names, a question to the murderer, a `Lied` theory on the reply. The rendered theory
    list and tension list must not mention the item."""
    page = _new_game(client, "g1", case)
    s = client.app.state.games.open("g1")
    scene, trace = s.state.evidence.get("E_scene"), s.state.evidence.get("E_trace")
    while "E_scene" not in s.state.discovery.known_evidence:
        page = post(client, "g1", "search", page, target=scene.discovery.at, method=scene.discovery.action).text
    page = post(client, "g1", "search", page, target=trace.discovery.at, method=trace.discovery.action).text
    assert not s.state.discovery.known_statements and not s.state.discovery.known_accounts
    label = _print_label(s)
    named = {x for e in s.state.discovery.known_evidence for i in s.state.evidence.get(e).implications
             for part in entities(i.proposition) for x in part}
    quiet = sorted(set(s.state.case.locations) - named - {s.state.evidence.get(e).discovery.at for e in s.state.discovery.known_evidence})[0]
    for who in sorted(s.state.characters):
        page = post(client, "g1", "hypothesize", page, kind="At", actor=who, location=quiet, start="00:00", end="00:10",
                    confidence="50").text
    page = post(client, "g1", "ask", page, addressee=s.state.murderer, topic="heard").text
    sid = next(i for i in sorted(s.state.discovery.known_statements) if s.state.decision.statements.get(i).speaker == s.state.murderer)
    page = post(client, "g1", "hypothesize", page, kind="Lied", statement=sid, confidence="50").text
    theories = re.findall(r"<li>([^<]*? — \d+% — [^<]*)<form", page)
    assert len(theories) == len(s.state.characters) + 1
    tensions = re.search(r"<h3>Tensions</h3><ul>(.*?)</ul>", page, re.S).group(1)
    assert label not in " ".join(theories) and label not in tensions, (theories, tensions)
    assert label in page                                           # the item itself is listed: held, just not interpreted


def test_H8_B1_a_tension_between_two_held_items_rests_on_unlocked_implications_only(fresh):
    """Evidence against evidence (§13.1): two HELD items whose implications cannot both be true are a tension only once the
    implication that conflicts is the player's. (The claim-against-implication path is the sealed-case test above.)"""
    from dataclasses import replace
    from types import SimpleNamespace
    from eidolon.evidence.discovery import DiscoveryState
    from eidolon.evidence.model import DiscoverySpec, Evidence, EvidenceStore, Implication
    st = fresh.state
    who, (l1, l2) = sorted(st.case.living_actors())[0], sorted(st.case.locations)[:2]
    item = lambda eid, place, requires: Evidence(                      # noqa: E731
        id=eid, kind="Witness", implications=(Implication(proposition=At(actor=who, location=place, interval=(10, 20)), requires=requires),),
        discovery=DiscoverySpec(action="Look", at=l1))

    def tensions(*accounts):
        discovery = DiscoveryState(known_evidence=frozenset({"EA", "EB"}), known_accounts=frozenset(accounts))
        ns = SimpleNamespace(state=replace(st, evidence=EvidenceStore([item("EA", l1, ("clean@x",)), item("EB", l2, ())]),
                                           discovery=discovery), bundle=fresh.bundle, discovery_order=lambda: [])
        return game._tensions(ns, game._labels(ns))

    assert tensions() == []
    assert len(tensions("clean@x")) == 1


def test_H8_B1_the_form_vocabulary_names_no_object_only_a_locked_implication_mentions(fresh):
    """Hardening: the weapon / search-target list is built from what the player may see, not from `held_names`, which
    (it is the V-7 bots' function) reads every implication of a held item, locked ones included."""
    from dataclasses import replace
    from eidolon.evidence.model import EvidenceStore, Implication
    from eidolon.world.entities import Object
    from eidolon.world.frozen import FrozenDict
    from eidolon.world.propositions import Did
    from eidolon.solve.queries import Names
    st = fresh.state
    trace = st.evidence.get("E_trace")
    (token,) = trace.implications[0].requires
    secret = Implication(proposition=Did(actor=st.murderer, action="touch", interval=(1, 2), object="Candlestick",
                                         location=trace.implications[0].proposition.location), requires=(token,))
    objects = FrozenDict({**st.case.objects, "Candlestick": Object(id="Candlestick", name="a candlestick", kind="blunt",
                                                                   initial_location=trace.implications[0].proposition.location)})
    store_ = EvidenceStore([trace.model_copy(update={"implications": trace.implications + (secret,)}) if e.id == "E_trace" else e
                           for e in st.evidence.all()])
    held = replace(st, case=st.case.model_copy(update={"objects": objects}), evidence=store_,
                   discovery=st.discovery.model_copy(update={"known_evidence": frozenset({"E_trace"})}))
    assert "Candlestick" in held_names(held, Names()).objects          # the bot-side reading does see it...
    assert "Candlestick" not in game.player_objects(held)              # ...the player's form must not
    heard = replace(held, discovery=held.discovery.model_copy(update={"known_accounts": frozenset({token})}))
    assert "Candlestick" in game.player_objects(heard)                 # unlocked: it is the player's to name


# ============================================================================== H8-I2: the Host is the allow-list, not the Origin's twin
EVIL = "http://attacker.example:8123"       # after DNS rebinding, attacker.example resolves to 127.0.0.1


def test_H8_I2_a_rebound_host_is_refused_on_every_route_even_with_a_matching_origin(tmp_path):
    """§26.1 / §22.1: a page on `attacker.example` re-pointed at 127.0.0.1 sends `Host: attacker.example` and an `Origin` equal
    to it, so comparing the two proved nothing. Every route, GET and POST, answers only the loopback name and the served port;
    the rebound page reads nothing, creates nothing, accuses no one."""
    from starlette.testclient import TestClient
    from eidolon import web
    saves = tmp_path / "saves"
    saves.mkdir()
    app = web.create_app(saves, CASES)
    with TestClient(app, base_url=LOCAL) as local:
        page = _new_game(local, "victim")
        evil = TestClient(app, base_url=EVIL)
        hdr = {"origin": EVIL}
        refused = [evil.get("/"), evil.get("/g/victim"), evil.get("/g/victim/report"), evil.get("/g/nobody"), evil.get("/nope"),
                   evil.post("/new", data={"name": "mine", "case": "study_party_s4", "seed": "7"}, headers=hdr, follow_redirects=False),
                   evil.post("/g/victim", data={"op": "accuse", **hidden(page, "accuse"), "suspect": "Elena", "confirm": "on"}, headers=hdr)]
        assert [r.status_code for r in refused] == [400] * len(refused) and not any("victim" in r.text for r in refused)
        assert sorted(p.name for p in saves.iterdir()) == ["victim.db"]
        assert local.app.state.games.open("victim").last_seq == 0 and "Turn 0" in local.get("/g/victim").text


@pytest.mark.parametrize("host,origin,status", [
    ("127.0.0.1:8000", None, 200), ("localhost:8000", None, 200), ("LOCALHOST:8000", None, 200), ("[::1]:8000", None, 200),
    ("127.0.0.1:8000", "http://localhost:8000", 200),             # another loopback name of the same server
    ("127.0.0.1:9999", None, 400), ("127.0.0.1", None, 400), ("localhost.evil.example:8000", None, 400),
    ("127.0.0.1.evil.example:8000", None, 400), ("evil.example", None, 400), ("0.0.0.0:8000", None, 400),
    ("127.0.0.1:8000", "http://localhost:3000", 403),             # a different local app (another port) is another origin
    ("127.0.0.1:8000", "http://127.0.0.1:8000.evil.example", 403), ("127.0.0.1:8000", "null", 403),
    ("127.0.0.1:8000", "https://127.0.0.1:8000", 403), ("127.0.0.1:8000", "http://evil.example", 403)])
def test_H8_I2_the_allow_list_is_the_loopback_names_on_the_served_port(tmp_path, host, origin, status):
    from starlette.testclient import TestClient
    from eidolon import web
    saves = tmp_path / "saves"
    saves.mkdir()
    with TestClient(web.create_app(saves, CASES), base_url=LOCAL) as c:
        page = _new_game(c)
        headers = {"host": host, **({"origin": origin} if origin else {})}
        r = (c.get("/g/g1", headers=headers) if origin is None
             else c.post("/g/g1", data={"op": "goto", "location": ROOM, **hidden(page, "goto")}, headers=headers))
        assert r.status_code == status
        assert (c.app.state.games.open("g1").last_seq > 0) == bool(origin and status == 200)      # only an accepted POST records


def test_H8_I2_the_default_port_may_be_left_out_of_the_host_only_on_port_80():
    from eidolon import web
    assert "127.0.0.1" in web.allowed_hosts(80) and "localhost:80" in web.allowed_hosts(80)
    assert "127.0.0.1" not in web.allowed_hosts(8000) and web.allowed_hosts(8000) == {"127.0.0.1:8000", "localhost:8000", "[::1]:8000"}


# ============================================================================== H8-I3: one save, one writer; the store has the last word
def test_H8_I3_a_second_spelling_of_a_game_is_not_a_second_writer(client):
    """NTFS maps `/g/G1` onto `g1.db`; the app used to open it as a second `Save` (its own head, its own action ledger), so a
    second tab answered forms from a stale state, showed replies nothing recorded, and went on doing so after the verdict.
    Only the spelling the save has on disk opens. (On a case-sensitive file system `G1.db` never exists and this holds
    trivially; the mutant that restores the alias is only distinguishable on a case-insensitive one.)"""
    page = _new_game(client)
    games = client.app.state.games
    form = {"op": "ask", **hidden(page, "ask"), "addressee": "Elena", "topic": "presence"}
    for path in ("/g/G1", "/g/G1/report"):
        assert client.get(path).status_code == 404
    other = client.post("/g/G1", data=form)
    assert other.status_code == 404 and "Elena:" not in other.text
    assert sorted(games._open) == ["g1"] and games.open("g1").last_seq == 0
    assert "Elena:" in client.post("/g/g1", data=form).text and games.open("g1").state.turn_counter == 1
    post(client, "g1", "accuse", client.get("/g/g1").text, suspect=MURDERER, confirm="on")
    closed = games.open("g1").last_seq
    after = client.post("/g/G1", data={**form, "action_id": "ask@elsewhere", "accuse": "on"})
    assert after.status_code == 404 and "Margaret:" not in after.text and games.open("g1").last_seq == closed


def test_H8_I3_one_rate_window_per_save_whatever_its_spelling(chat):
    from eidolon.llm.ingress import RATE_LIMIT
    c, t = chat
    _new_game(c, "abc")
    t.queues["parse"] = [json.dumps({"kind": "clarify"})] * (8 * RATE_LIMIT)
    for spelling in ("abc", "ABC", "Abc", "aBc", "abC", "ABc", "AbC", "aBC"):
        page = c.get(f"/g/{spelling}").text
        if 'name="expected_seq"' in page:                       # (a spelling that opens a game page)
            for _ in range(RATE_LIMIT + 1):
                post(c, spelling, "say", page, addressee="Elena", text="Hmm?")
    assert t.calls("parse") == RATE_LIMIT                       # it was 8 x RATE_LIMIT: one window per spelling


def test_H8_I3_a_duplicate_the_store_detects_but_this_save_missed_shows_no_new_reply(blank, tmp_path):
    """Two handles on one file (two server processes, or a cache that missed). The second handle's `turn_for` knows nothing
    of `ask@0`, so the runner computes a reply from a stale state; the store finds the action id on disk and says nothing was
    appended. `_commit` honours that: a re-sent form reads as the duplicate it is, a different action under a reused id as
    stale — never as a fresh answer, and nothing is written."""
    a = copy_of(blank, tmp_path)
    b = Save.open(a.path, writable=True)
    case = a.state.case
    q = game.question(case, "Elena", topic="presence")
    first = game.ask(a, "ask@0", 0, "Elena", q)
    assert first.ok and first.reply
    written = (a.state_hash(), a.last_seq, a.last_hash)
    again = game.ask(b, "ask@0", 0, "Elena", q)
    assert (again.status, again.turn, again.reply) == ("duplicate", first.turn, "")
    other = game.ask(b, "ask@0", 0, "Robert", game.question(case, "Robert", topic="did"))      # another action under the reused id
    assert (other.status, other.reply) == ("stale", "")
    fresh_id = game.ask(b, "ask@new", 0, "Margaret", q)                                         # a new id at the old head
    assert (fresh_id.status, fresh_id.reply) == ("stale", "")
    assert game.accuse(a, "accuse@2", a.last_seq, MURDERER).ok
    closed = (a.state_hash(), a.last_seq, a.last_hash)
    for form_id in ("ask@0", "ask@later"):
        late = game.ask(b, form_id, 0, "Elena", q)
        assert late.status in ("duplicate", "stale") and late.reply == ""
    assert Save.open(a.path).state_hash() == a.state_hash() and (a.state_hash(), a.last_seq, a.last_hash) == closed != written
    a.close()
    b.close()


# ============================================================================== H8-I1: a search hint names nothing the player has not seen
@pytest.mark.parametrize("case", SEALED)
def test_H8_I1_no_search_hint_in_any_sealed_case_names_an_engine_id(case, tmp_path):
    """§22.2 Storage: "player never receives IDs of undiscovered evidence". Every place and object, with every method, from a
    blank save: the in-world line a refused search gives names no evidence, statement, account or kit id (it used to say
    "You would need to find E_pin_clean first.")."""
    from eidolon.decision.exploration import search as explore
    s = Save.create(tmp_path / "g.db", CASES / f"{case}.json", seed=7)
    words, ids = _engine_only_tokens(s)
    ids |= {e.id for e in s.state.evidence.all()} | {p.ref for e in s.state.evidence.all() for p in e.discovery.prerequisites}
    hints = {}
    for target in sorted({*s.state.case.locations, *s.state.case.objects}):
        for method in game.METHODS:
            r = explore(s.state.evidence, s.state.discovery, target, method, 1, s.state.case)
            if r.discovery is None:
                hints[(target, method)] = r.hint
    assert any(h != "Nothing like that here." for h in hints.values()), "the case has a gated item: a hint is exercised"
    for key, hint in hints.items():
        assert not [i for i in ids if i in hint], (key, hint)
    s.close()


@pytest.mark.parametrize("case", SEALED)
def test_H8_I1_no_page_of_a_search_sweep_leaks_an_identifier(client, case):
    """The same through the browser: search every place and every object (the weapon first, offered or not — a crafted form
    may name an object no page lists yet) with every method, twice round, reading the page after each. (Reproduced: a first
    look round the `manor_wing` terrace printed the id of the item it hides behind.)"""
    page = _new_game(client, "g1", case)
    s = client.app.state.games.open("g1")
    seen = set()
    every = sorted({*s.state.case.locations, *s.state.case.objects})
    for _ in range(2):
        f = Forms(page)
        for target in dict.fromkeys([*sorted(s.state.case.objects), *reversed(f.options["target"]), *every]):
            for method in f.options["method"]:
                page = post(client, "g1", "search", page, target=target, method=method).text
                seen.add(last_action(page))
                assert not _leaks(page, s), (target, method, last_action(page))
    assert any("turn up first" in a for a in seen), "a gated hint was shown and read"


def test_H8_I1_the_search_runner_hands_the_case_to_the_hint(fresh):
    """The display names a hint may use come from the case the runner searches in (a sealed case gates only on found
    items, so a place-gated item is built here)."""
    from dataclasses import replace
    from eidolon.decision.turn import run_search_turn
    from eidolon.evidence.model import DiscoverySpec, Evidence, EvidenceStore, Prereq
    st = fresh.state
    gated = Evidence(id="E_gated", kind="Object", discovery=DiscoverySpec(
        action="Look", at="Study", prerequisites=(Prereq(kind="KnowsAbout", ref="Library"),)))
    res = run_search_turn(replace(st, evidence=EvidenceStore([gated])), "Study", "Look")
    assert res.text == f"You would need to know about {game.name(st.case, 'Library')} first."


def test_H8_I1_a_denial_that_puts_the_weapon_on_the_list_does_not_name_the_scene_either(client):
    """The second reproduction: the murderer's denial offers the decanter as a search target before the scene is found."""
    page = _new_game(client)
    # ADR-30: the deed denial answers a question about what was DONE (it used to answer "heard" too - the non-sequitur)
    page = post(client, "g1", "ask", page, addressee=MURDERER, topic="did").text
    assert 'value="Decanter"' in page
    out = post(client, "g1", "search", page, target="Decanter", method="Dust").text
    s = client.app.state.games.open("g1")
    assert not _leaks(out, s) and "E_scene" not in out and "Nothing was recorded" not in out
    assert "have to turn up first" in out


# ============================================================================== the browser app (§30 Phase 8)
class Forms(HTMLParser):
    """Collects every form control and every label of a page."""
    def __init__(self, text):
        super().__init__()
        self.controls, self.labels, self.options, self.buttons, self.lang, self._sel, self._btn = [], set(), {}, [], None, None, None
        self.feed(text)

    def handle_starttag(self, tag, a):
        a = dict(a)
        if tag == "html":
            self.lang = a.get("lang")
        if tag in ("input", "select", "textarea") and a.get("type") not in ("hidden", "submit"):
            self.controls.append(a)
        if tag == "input" and a.get("type") == "checkbox":
            self.options.setdefault(a.get("name"), []).append(a.get("value"))
        if tag == "label" and a.get("for"):
            self.labels.add(a["for"])
        if tag == "select":
            self._sel = a.get("name")
            self.options.setdefault(self._sel, [])
        if tag == "option" and self._sel:
            self.options[self._sel].append(a.get("value"))
        if tag == "button":
            self._btn = ""

    def handle_data(self, data):
        if self._btn is not None:
            self._btn += data

    def handle_endtag(self, tag):
        if tag == "select":
            self._sel = None
        if tag == "button":
            self.buttons.append(self._btn.strip())
            self._btn = None


def hidden(text, form):
    """The hidden action id and expected seq of the form with `name=op value=form`."""
    block = re.search(rf'<form[^>]*>(?:(?!</form>).)*?value="{form}"(?:(?!</form>).)*</form>', text, re.S).group(0)
    return {k: re.search(rf'name="{k}" value="([^"]*)"', block).group(1) for k in ("action_id", "expected_seq")}


@pytest.fixture
def client(tmp_path):
    from starlette.testclient import TestClient
    from eidolon import web
    saves = tmp_path / "saves"
    saves.mkdir()
    with TestClient(web.create_app(saves, CASES), base_url=LOCAL) as c:
        yield c


def _new_game(c, name="g1", case="study_party_s4"):
    r = c.post("/new", data={"name": name, "case": case, "seed": "7"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/g/{name}"
    return c.get(f"/g/{name}").text


def post(c, name, op, page, **fields):
    return c.post(f"/g/{name}", data={"op": op, **hidden(page, op), **fields})


def last_action(page):
    """The text of the page's "Last action" section, tags removed."""
    m = re.search(r"<h2>Last action</h2>(.*?)</section>", page, re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", m.group(1))).strip()


def test_the_index_lists_the_case_library_and_a_new_game_starts_empty(client):
    index = client.get("/")
    assert index.status_code == 200 and "study_party_s4" in index.text
    page = _new_game(client)
    assert "Turn 0" in page and client.get("/").text.count("/g/g1") >= 1


def test_every_control_round_trips_over_http(client):
    page = _new_game(client)
    page = post(client, "g1", "goto", page, location=ROOM).text
    assert "You go to" in page
    for _ in range(3):                                              # search, the way a player would: the study first
        page = post(client, "g1", "search", page, target=ROOM, method="Look").text
    page = post(client, "g1", "ask", page, addressee="Elena", topic="presence", place=ROOM, bucket="1").text
    assert "Elena" in page
    held = Forms(page).options["present"]
    page = post(client, "g1", "ask", page, addressee="Robert", topic="", present=held[-1], accuse="on").text
    page = post(client, "g1", "hypothesize", page, kind="At", actor="Elena", location=ROOM, start="40", end="60",
                confidence="70").text
    assert "Elena" in page and "70%" in page
    hid = re.search(r'name="hypothesis" value="(H\d+)"', page).group(1)
    page = post(client, "g1", "withdraw", page, hypothesis=hid).text
    assert "70%" not in page
    page = post(client, "g1", "accuse", page, suspect=MURDERER, location=ROOM, start="00:55", end="01:05", motive=MOTIVE,
                confirm="on").text
    assert "closed" in page.lower()
    report = client.get("/g/g1/report")
    assert report.status_code == 200 and "who" in report.text.lower()


@pytest.mark.parametrize("fields", [dict(op="ask", addressee="Elena", about="Ghost"), dict(op="ask", addressee="Elena", place="Atlantis"),
                                    dict(op="ask", addressee="Elena", bucket="99"), dict(op="ask", addressee="Elena", topic="secrets"),
                                    dict(op="ask", addressee="Elena", present="e0123456789ab"), dict(op="ask", addressee="Ghost"),
                                    dict(op="search", target="Atlantis", method="Look"), dict(op="search", target=ROOM, method="Ask"),
                                    dict(op="search", target="", method="Look"),
                                    dict(op="hypothesize", kind="At", actor="Ghost", location=ROOM, start="00:10", end="00:20"),
                                    dict(op="hypothesize", kind="At", actor="Elena", location=ROOM, start="00:20", end="00:10"),
                                    dict(op="hypothesize", kind="Planted", item="E_watch"), dict(op="hypothesize", kind="Lied", statement="S99999"),
                                    dict(op="hypothesize", kind="At", actor="Elena", location=ROOM, start="00:10", end="00:20", confidence="101"),
                                    dict(op="accuse", suspect=MURDERER, confirm="on", cited="e0123456789ab"),
                                    dict(op="accuse", suspect=MURDERER, confirm="on", motive="greed"),
                                    dict(op="accuse", suspect=MURDERER, confirm="on", start="00:50"),
                                    dict(op="teleport")])
def test_a_crafted_form_is_refused_at_the_boundary_and_records_nothing(client, fields):
    """The browser only offers valid choices; a hand-made POST must be refused before it reaches an engine type, and
    commit nothing (I-15). Evidence is never addressed by its id (`E_watch`), only by its handle."""
    page = _new_game(client)
    ids = hidden(page, "goto" if fields["op"] == "teleport" else fields["op"])
    out = client.post("/g/g1", data={**ids, **fields}).text
    assert "Turn 0" in out and "Nothing was recorded" in out
    assert client.app.state.games.open("g1").last_seq == 0


def test_a_cross_site_post_is_refused_and_records_nothing(client):
    """CSRF: a page on another site cannot drive a local game or create one; a same-origin browser post still works."""
    page = _new_game(client)
    evil = {"origin": "http://evil.example"}
    r = client.post("/g/g1", data={"op": "goto", "location": ROOM, **hidden(page, "goto")}, headers=evil)
    assert r.status_code == 403 and client.app.state.games.open("g1").last_seq == 0
    r = client.post("/new", data={"name": "g9", "case": "study_party_s4", "seed": "7"}, headers=evil, follow_redirects=False)
    assert r.status_code == 403 and "g9" not in client.app.state.games.saves()
    ok = client.post("/g/g1", data={"op": "goto", "location": ROOM, **hidden(page, "goto")}, headers={"origin": LOCAL})
    assert ok.status_code == 200 and client.app.state.games.open("g1").last_seq > 0


def test_a_tampered_save_gets_a_refusal_page_that_names_no_engine_detail(client, played):
    saves = client.app.state.games.saves_dir
    shutil.copy(played, saves / "bad.db")
    with sqlite3.connect(saves / "bad.db") as c:                       # an edit that does not re-chain
        c.execute("UPDATE session_events SET payload = replace(payload, 'Study', 'Hall')")
    for path in ("/g/bad", "/g/bad/report"):
        r = client.get(path)
        assert r.status_code == 409 and "failed verification" in r.text
        assert not re.search(r"seq|chain|hash|K\d{4}|E_\w+|S\d{5}", r.text)


def test_a_final_accusation_without_confirmation_records_nothing(client):
    page = _new_game(client)
    out = post(client, "g1", "accuse", page, suspect=MURDERER).text
    assert "Turn 0" in out and client.get("/g/g1/report").status_code == 404


def test_a_double_post_commits_once_and_a_second_tab_commits_nothing_I14(client):
    page = _new_game(client)
    fields = dict(op="goto", location=ROOM, **hidden(page, "goto"))
    first = client.post("/g/g1", data=fields).text
    assert "Turn 1" in first
    again = client.post("/g/g1", data=fields).text                  # double click / browser retry: same action id
    assert "Turn 1" in again and "already recorded" in again.lower()
    stale = client.post("/g/g1", data={**fields, "action_id": "another-tab"}).text
    assert "Turn 1" in stale and "moved on" in stale.lower()
    games = client.app.state.games
    assert games.open("g1").state.turn_counter == 1


def _opening(c, name, case):
    page = _new_game(c, name, case)
    return re.search(r'<section class="opening">(.*?)</section>', page, re.S).group(1), page


def test_the_case_file_is_opening_material_only_and_the_same_whoever_did_it(client):
    """The opening, the cast and the map are fixed per skeleton: two cases with different murderers (study_party s4/s5:
    David/Robert; manor_wing s4/s6: Delphine/Cormac) open with the same file, which names no weapon."""
    from eidolon import story
    from eidolon.gen.skeletons import SKELETONS
    for skel, a, b in (("study_party", "study_party_s4", "study_party_s5"), ("manor_wing", "manor_wing_s4", "manor_wing_s6")):
        (one, page), (two, _) = _opening(client, f"o{a}", a), _opening(client, f"o{b}", b)
        assert one == two and "Begin the investigation" in one and "What to do next" in page
        assert SKELETONS[skel].weapon.name.split()[-1] not in one.lower()
        assert all(n in story._STORIES[skel]["people"] for n, _ in SKELETONS[skel].cast)
        assert all(loc.id in story._STORIES[skel]["rooms"] for loc in SKELETONS[skel].locations)
    page = post(client, f"o{a}", "goto", page, location="Office").text
    assert "<h2>Where you are</h2>" in page and "This is where he was found." in page
    assert '<section class="opening">' not in page                       # the opening plays once, at turn 0


def test_a_theme_is_a_cosmetic_cookie_that_changes_no_game(client):
    page = _new_game(client)
    assert 'data-theme="auto"' in page
    r = client.post("/theme", data={"theme": "noir"}, headers={"referer": f"{LOCAL}/g/g1"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/g/g1" and "samesite=strict" in r.headers["set-cookie"].lower()
    assert 'data-theme="noir"' in client.get("/g/g1").text and 'data-theme="noir"' in client.get("/").text
    assert client.post("/theme", data={"theme": "x\" onload=\""}).status_code == 400          # only a known theme
    assert client.post("/theme", data={"theme": "noir"}, headers={"referer": "http://e.example//evil.example/"},
                       follow_redirects=False).headers["location"] == "/"                   # never an open redirect
    assert client.post("/theme", data={"theme": "noir"}, headers={"origin": EVIL}).status_code == 403
    client.cookies.set("theme", "nonsense")
    assert 'data-theme="auto"' in client.get("/").text


@pytest.mark.parametrize("path", ["/debug", "/debug/trace", "/trace", "/traces", "/state", "/truth", "/admin",
                                  "/g/g1/state", "/g/g1/debug", "/g/g1/trace", "/g/g1/events", "/g/g1/solution"])
def test_debug_and_engine_routes_do_not_exist_on_the_player_app_I10(client, path):
    _new_game(client)
    assert client.get(path).status_code == 404


def test_the_player_process_never_imports_engine_debug_tooling():
    import ast
    tree = ast.parse((ROOT / "eidolon" / "web.py").read_text(encoding="utf-8"))
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {a.name for n in ast.walk(tree)
                                                                                  if isinstance(n, ast.Import) for a in n.names}
    assert not any("debug" in (m or "") or (m or "").endswith("bots") for m in mods)


@pytest.mark.parametrize("name", ["../x", "..", "a/b", "a b", "x" * 80, "con.db", ""])
def test_a_hostile_game_name_is_refused(client, name):
    r = client.post("/new", data={"name": name, "case": "study_party_s4", "seed": "7"}, follow_redirects=False)
    assert r.status_code == 400
    assert not list(client.app.state.games.saves_dir.iterdir())


@pytest.mark.parametrize("case", ["../study_party_s4", "nonexistent", "study_party_s4.json", "../generated/study_party_s4"])
def test_only_a_library_case_can_start_a_game(client, case):
    r = client.post("/new", data={"name": "g2", "case": case, "seed": "7"}, follow_redirects=False)
    assert r.status_code == 400


def test_pages_meet_accessibility_basics(client):
    """Labels for every control, a document language, one h1, landmark, named buttons, a live region for results."""
    page = _new_game(client)
    page = post(client, "g1", "goto", page, location=ROOM).text
    for text in (client.get("/").text, page):
        f = Forms(text)
        assert f.lang == "en"
        unlabelled = [c for c in f.controls if c.get("id") not in f.labels]
        assert not unlabelled, unlabelled
        assert all(b for b in f.buttons)
        assert text.count("<h1") == 1 and "<main" in text
    assert 'aria-live="polite"' in page


def test_a_tester_can_play_the_case_to_a_proven_verdict_in_the_browser(client):
    """§30 Phase 8 exit, measured on the generated `study_party_s4` (`vance_v03` carries no sealed bundle): only HTTP
    forms, only what the pages offer — search every spot, then accuse, citing what was found. The verdict is correct and
    the cited set proves it."""
    page = _new_game(client)
    for _ in range(4):
        f = Forms(page)
        for target in f.options["target"]:
            for method in f.options["method"]:
                page = post(client, "g1", "search", page, target=target, method=method).text
    f = Forms(page)
    page = post(client, "g1", "accuse", page, suspect=MURDERER, weapon=f.options["weapon"][-1], location=ROOM,
                start="00:55", end="01:05", motive=MOTIVE, confirm="on", cited=f.options["cited"]).text
    report = client.get("/g/g1/report").text
    assert "closed" in page.lower()
    for axis in ("who", "method", "place_and_time", "motive", "evidence"):
        assert re.search(rf'data-axis="{axis}" data-ok="true"', report), axis


# ============================================================================== free text (§12.1 stages 0-2, 8-9; D-1)
@pytest.fixture
def chat(tmp_path):
    """The app with a model: a scripted transport (no network) whose parse queue each test fills; the generator words the
    plan's claims freely (`faithful`) and the verifier agrees. A fixed clock drives the ingress rate window."""
    from starlette.testclient import TestClient
    from eidolon import web
    from eidolon.llm.fakes import ScriptedTransport
    from tests.llm.llm_helpers import approve, faithful
    saves = tmp_path / "saves"
    saves.mkdir()
    t = ScriptedTransport(generate=[faithful()], verify=[approve], repeat_last=True)
    with TestClient(web.create_app(saves, CASES, transport=t, clock=lambda: 100.0), base_url=LOCAL) as c:
        yield c, t


def _say(c, page, text, who="Elena"):
    return post(c, "g1", "say", page, addressee=who, text=text).text


def test_a_typed_question_is_parsed_grounded_and_answered_through_the_model(chat):
    from markupsafe import escape
    c, t = chat
    page = post(c, "g1", "goto", _new_game(c), location=ROOM).text        # the study is now a name the player may use
    t.queues["parse"].append(json.dumps({"kind": "ask", "query_kind": "did_you", "location": "the study",
                                         "predicate_hint": "presence"}))
    page = _say(c, page, "Were you in the study tonight?")
    s = c.app.state.games.open("g1")
    last = s.state.decision.statements.all()[-1]
    assert "Turn 2" in page and "understood as: did you, about who was where, in the study" in page
    assert last.speaker == "Elena" and str(escape(last.text)) in page       # the validated wording is what is shown (I-12)
    assert t.calls("parse") == 1 and t.calls("generate") >= 1 and t.calls("verify") >= 1
    assert Save.open(s.path).state_hash() == s.state_hash()


@pytest.mark.parametrize("action", [{"kind": "clarify"}, {"kind": "ask", "query_kind": "where", "location": "the cellar"},
                                    {"kind": "ask", "query_kind": "where", "subject": "Bartholomew"}])
def test_an_unclear_or_unknown_line_gets_one_in_world_answer_and_records_nothing(chat, action):
    """§22.2: an unclear line, a place that does not exist and a person who is not in the case get the SAME reply, so
    typing names cannot probe for anything the page does not already show; nothing is recorded. (This used "Harold", whom
    the page lists - review H8-N3: the page's cast and places are public, so typed text may name them too.)"""
    c, t = chat
    page = _new_game(c)
    t.queues["parse"].append(json.dumps(action))
    out = _say(c, page, "Tell me about it.")
    assert "not sure what you mean" in out and "Turn 0" in out and c.app.state.games.open("g1").last_seq == 0


def test_H8_N3_typed_text_may_name_anyone_the_page_lists(chat):
    """H8-N3: the structured form lists the whole cast under "Concerning"; typed "Did you see David?" to Elena was refused as
    an unknown name while the same question from the form was answered. Typed text now names what the page shows."""
    c, t = chat
    page = _new_game(c)
    t.queues["parse"].append(json.dumps({"kind": "ask", "query_kind": "did_they", "subject": "David", "predicate_hint": "presence"}))
    out = _say(c, page, "Did you see David?")
    assert "not sure what you mean" not in out and "Turn 1" in out and c.app.state.games.open("g1").last_seq > 0


def test_an_over_long_line_is_refused_before_any_model_call(chat):
    c, t = chat
    out = _say(c, _new_game(c), "why " * 300)
    assert "Nothing was recorded" in out and t.calls("parse") == 0 and c.app.state.games.open("g1").last_seq == 0


def test_the_ingress_rate_window_throttles_a_burst_of_typed_lines(chat):
    """Every typed line costs a parse call, so every one feeds the rate window: the 31st inside it is refused unparsed."""
    from eidolon.llm.ingress import RATE_LIMIT
    c, t = chat
    page = _new_game(c)
    t.queues["parse"] = [json.dumps({"kind": "clarify"})] * RATE_LIMIT
    for _ in range(RATE_LIMIT):
        assert "not sure what you mean" in _say(c, page, "Hmm?")
    assert "Nothing was recorded" in _say(c, page, "Hmm?") and t.calls("parse") == RATE_LIMIT


def test_without_a_model_there_is_no_free_text(client):
    page = _new_game(client)
    assert 'name="text"' not in page
    out = client.post("/g/g1", data={"op": "say", "addressee": "Elena", "text": "Hello", **hidden(page, "goto")}).text
    assert "Nothing was recorded" in out and client.app.state.games.open("g1").last_seq == 0


def test_the_cli_serves_the_player_app_on_localhost_only(monkeypatch, tmp_path):
    import uvicorn
    from eidolon import cli
    seen = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: seen.update(app=app, **kw))
    assert cli.main(["serve", "--saves", str(tmp_path), "--cases", str(CASES), "--port", "8123"]) == 0
    assert seen["host"] == "127.0.0.1" and seen["port"] == 8123 and seen["app"] is not None
    from starlette.testclient import TestClient
    assert TestClient(seen["app"], base_url="http://127.0.0.1:8123").get("/").status_code == 200       # H8-I2: the served port is the allowed one
    assert TestClient(seen["app"], base_url=LOCAL).get("/").status_code == 400
