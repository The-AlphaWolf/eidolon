"""Phase 7 (§26, I-13, I-22, I-23, I-31, I-41, I-58; T-22, T-23, T-24): save / load / replay.

Every integrity test here drives a REAL rejection boundary: the file is edited on disk (with or without the hash
chain repaired — an attacker who re-chains is the hard case), or a forged turn is offered to `append`, and the thing
under test must refuse. Nothing asserts the implementation's own assumptions back at it.
"""
from __future__ import annotations

import inspect
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from eidolon import store
from eidolon.decision.events import Accusation, ClaimMade, DecisionState, TurnCommitted
from eidolon.decision.exploration import AccountHeardEvent, StatementHeardEvent
from eidolon.decision.query import Query
from eidolon.decision.turn import run_ask_turn, run_goto_turn, run_search_turn
from eidolon.evidence.discovery import Discovery
from eidolon.minds.character import CharacterState, DetectiveModel
from eidolon.minds.epistemic import EpistemicState
from eidolon.minds.events import DetectiveModelUpdate, KnowledgeAdded
from eidolon.evidence.discovery import DiscoveryState
from eidolon.solve.package import SealRefusal as _Seal, bundle_seal
from eidolon.store import Save, SaveError, SaveRefusal, StaleAppend

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "cases" / "generated" / "study_party_s4.json"
OTHER_BUNDLE = ROOT / "cases" / "generated" / "study_party_s5.json"
TOPICS = ("kitchen", "study", "where", "clean")


def drive(save: Save, n: int, *, start: int = 0) -> None:
    """A mixed session: exploration, searches, asks, and presenting what was found. Every turn is appended through
    the store; the live `state` the engine returns is compared to the store's folded one at the end of each test."""
    st = save.state
    seq = start
    def put(res):
        nonlocal st, seq
        assert not getattr(res, "rejected", False), getattr(res, "violations", None)
        save.append(res.events, save.last_seq, f"act-{seq}")
        seq += 1
        st = res.state
        assert store.state_hash(st) == save.state_hash(), "the log is not the whole turn"
    if start == 0:
        put(run_goto_turn(st, "Study"))
        for ev in st.evidence.all():
            put(run_search_turn(st, ev.discovery.at, ev.discovery.action))
    for i in range(n):
        held = sorted(st.discovery.known_evidence)
        ref = held[i % len(held)] if held and i % 5 == 0 else None
        res = run_ask_turn(st, "David", Query(kind="challenge" if ref else "did_you", predicate_hint=TOPICS[i % 4],
                                               raw=f"q{i}"), presented_ref=ref, hostile_tone=i % 7 == 0,
                           provisional_accusation=i % 11 == 0)
        if res.rejected:
            continue
        put(res)
    return st


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    d = tmp_path_factory.mktemp("built")
    s = Save.create(d / "g.db", BUNDLE, seed=7)
    live = drive(s, 60)
    s.close()
    return d / "g.db", store.state_hash(live)


@pytest.fixture
def db(built, tmp_path):
    p = tmp_path / "g.db"
    shutil.copy(built[0], p)
    return p


def rechain(path, transform):
    """What a forger does: change rows, then repair every hash and the head so the CHAIN verifies."""
    c = sqlite3.connect(path, isolation_level=None)
    meta = dict(c.execute("SELECT key, value FROM meta"))
    rows = [{"turn": t, "kind": k, "action_id": a, "payload": json.loads(p)}
            for _, t, k, a, p, _, _ in c.execute("SELECT * FROM session_events ORDER BY seq")]
    rows = transform(rows)
    prev = meta["genesis"]
    c.execute("DELETE FROM session_events")
    for i, r in enumerate(rows, 1):
        h = store._row_hash(prev, i, r["turn"], r["kind"], r["action_id"], r["payload"])
        c.execute("INSERT INTO session_events VALUES (?,?,?,?,?,?,?)",
                  (i, r["turn"], r["kind"], r["action_id"], store._canon(r["payload"]), prev, h))
        prev = h
    c.execute("UPDATE meta SET value=? WHERE key='head_seq'", (str(len(rows)),))
    c.execute("UPDATE meta SET value=? WHERE key='head_hash'", (prev,))
    c.close()


def sql(path, stmt, args=()):
    c = sqlite3.connect(path, isolation_level=None)
    c.execute(stmt, args)
    c.close()


# ------------------------------------------------------------------ 1-3: round trip, replay, fresh process
def test_round_trip_reproduces_the_live_state_hash(db, built):
    s = Save.open(db)
    assert s.state_hash() == built[1]


def test_every_turn_the_engine_commits_is_fully_recorded(built):
    """`drive` asserts after EACH append that the folded store state equals the engine's live state — this proves the
    event list returned by the turn runners is the complete log (the Discovery / TurnCommitted rows were missing)."""
    s = Save.open(built[0])
    assert s.last_seq > 100 and s.state.turn_counter > 60
    assert s.state.discovery.known_evidence and s.state.decision.statements.all()


def test_open_is_read_only_and_idempotent_i23(db):
    before = db.read_bytes()
    a, b = Save.open(db).state_hash(), Save.open(db).state_hash()
    assert a == b and db.read_bytes() == before
    with pytest.raises(SaveError):
        Save.open(db).append([], 0, "x")


@pytest.mark.parametrize("seed", ["0", "1", "4242"])
def test_restoration_is_identical_in_a_fresh_process(db, built, seed):
    code = "import sys; from eidolon.store import Save; print(Save.open(sys.argv[1]).state_hash())"
    out = subprocess.run([sys.executable, "-c", code, str(db)], cwd=ROOT, capture_output=True, text=True, check=True,
                         env={**os.environ, "PYTHONHASHSEED": seed})
    assert out.stdout.strip() == built[1]


def test_changing_the_composure_formula_does_not_change_an_old_saves_hash_T24(db, built, monkeypatch):
    import eidolon.decision.pressure as pressure
    import eidolon.decision.turn as turn
    for mod in (pressure, turn):
        monkeypatch.setattr(mod, "update_composure", lambda *a, **k: 1)
        monkeypatch.setattr(mod, "update_verbal_pressure", lambda *a, **k: 1)
    assert Save.open(db).state_hash() == built[1]


# ------------------------------------------------------------------ 4: schema / version
def test_missing_garbage_and_foreign_files_fail_cleanly(tmp_path):
    with pytest.raises(SaveRefusal):
        Save.open(tmp_path / "nope.db")
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"this is not a database" * 50)
    with pytest.raises(SaveRefusal):
        Save.open(junk)
    other = tmp_path / "other.db"
    sqlite3.connect(other).close()                       # a valid, empty SQLite file
    with pytest.raises(SaveRefusal):
        Save.open(other)


def test_a_newer_schema_is_refused_a_missing_or_extra_meta_key_is_refused(db):
    sql(db, "UPDATE meta SET value='99' WHERE key='schema_version'")
    with pytest.raises(SaveRefusal, match="reads up to"):
        Save.open(db)
    sql(db, "UPDATE meta SET value='1' WHERE key='schema_version'")
    sql(db, "DELETE FROM meta WHERE key='seed'")
    with pytest.raises(SaveRefusal, match="meta"):
        Save.open(db)
    sql(db, "INSERT INTO meta VALUES ('seed','7')")
    sql(db, "INSERT INTO meta VALUES ('extra','x')")
    with pytest.raises(SaveRefusal, match="meta"):
        Save.open(db)


def test_a_non_integer_schema_version_is_refused(db):
    sql(db, "UPDATE meta SET value='one' WHERE key='schema_version'")
    with pytest.raises(SaveRefusal):
        Save.open(db)


def test_upcaster_round_trip_on_a_synthetic_v1_to_v2_change(db, built, monkeypatch):
    """A v1 file in which TurnCommitted spelled `turn` as `t`. Under the v1 engine it is refused; under a v2 engine that
    ships ONE in-memory upcaster it loads to the identical state, and the file on disk is not rewritten."""
    def old_spelling(rows):
        for r in rows:
            if r["kind"] == "TurnCommitted":
                r["payload"]["t"] = r["payload"].pop("turn")
        return rows
    rechain(db, old_spelling)
    with pytest.raises(SaveRefusal):
        Save.open(db)
    def up(kind, payload):
        if kind == "TurnCommitted":
            payload = {**payload, "turn": payload["t"]}
            del payload["t"]
        return payload
    monkeypatch.setattr(store, "SCHEMA_VERSION", 2)
    monkeypatch.setattr(store, "UPCASTERS", {1: up})
    before = db.read_bytes()
    assert Save.open(db).state_hash() == built[1]
    assert db.read_bytes() == before
    with pytest.raises(SaveRefusal, match="read-only"):    # PI-3: an append would label v2 spelling as v1 and brick the save
        Save.open(db, writable=True)
    monkeypatch.setattr(store, "UPCASTERS", {})
    with pytest.raises(SaveRefusal, match="upcaster"):
        Save.open(db)


# ------------------------------------------------------------------ 5: truncation / corruption
@pytest.mark.parametrize("keep", [0.1, 0.5, 0.9, 0.999])
def test_a_truncated_file_never_loads_and_never_raises_anything_else(db, keep):
    data = db.read_bytes()
    db.write_bytes(data[: int(len(data) * keep)])
    with pytest.raises(SaveRefusal):
        Save.open(db)


def test_flipped_bytes_in_the_middle_of_the_file_are_refused_or_load_identically(db, built):
    data = bytearray(db.read_bytes())
    for off in range(len(data) // 3, len(data), len(data) // 17):
        mutated = bytearray(data)
        mutated[off] ^= 0xFF
        db.write_bytes(bytes(mutated))
        try:
            s = Save.open(db)
        except SaveRefusal:
            continue
        assert s.state_hash() == built[1], f"byte {off} changed the state without being noticed"


# ------------------------------------------------------------------ 6: tampering (chain intact AND chain repaired)
def test_flipping_a_rows_kind_while_keeping_its_payload_breaks_the_chain_T22(db):
    sql(db, "UPDATE session_events SET kind='Accusation' WHERE seq=5")
    c = sqlite3.connect(db)
    rows = c.execute("SELECT * FROM session_events ORDER BY seq").fetchall()
    genesis = c.execute("SELECT value FROM meta WHERE key='genesis'").fetchone()[0]
    # the CHAIN alone must fail at seq 5 (the payload-kind check at load would otherwise mask a chain that ignores `kind`)
    assert store._valid_prefix(rows, genesis)[0] == 4
    with pytest.raises(SaveRefusal) as e:
        Save.open(db)
    assert e.value.seq == 5


@pytest.mark.parametrize("col,val", [("turn", 99), ("action_id", "forged"), ("payload", '{"kind":"TurnCommitted","turn":2}')])
def test_editing_any_hashed_column_breaks_the_chain(db, col, val):
    sql(db, f"UPDATE session_events SET {col}=? WHERE seq=6", (val,))
    with pytest.raises(SaveRefusal) as e:
        Save.open(db)
    assert e.value.seq == 6


def test_deleting_a_middle_row_a_tail_row_and_duplicating_a_row_are_refused(db):
    for stmt in ("DELETE FROM session_events WHERE seq=9",
                 "DELETE FROM session_events WHERE seq=(SELECT MAX(seq) FROM session_events)"):
        shutil.copy(db, str(db) + ".keep")
        sql(db, stmt)
        with pytest.raises(SaveRefusal):
            Save.open(db)
        shutil.copy(str(db) + ".keep", db)
    sql(db, "INSERT INTO session_events SELECT seq+1000,turn,kind,action_id,payload,prev_hash,hash FROM session_events WHERE seq=9")
    with pytest.raises(SaveRefusal):
        Save.open(db)


def test_a_different_seed_or_case_hash_in_meta_is_refused(db):
    sql(db, "UPDATE meta SET value='8' WHERE key='seed'")
    with pytest.raises(SaveRefusal, match="initial world"):      # the seed also moves the derived personalities
        Save.open(db)
    sql(db, "UPDATE meta SET value='7' WHERE key='seed'")
    g = sqlite3.connect(db).execute("SELECT value FROM meta WHERE key='genesis'").fetchone()[0]
    sql(db, "UPDATE meta SET value=? WHERE key='genesis'", (("0" if g[0] != "0" else "1") + g[1:],))
    with pytest.raises(SaveRefusal, match="genesis"):
        Save.open(db)
    sql(db, "UPDATE meta SET value=? WHERE key='genesis'", (g,))
    sql(db, "UPDATE meta SET value=? WHERE key='case_hash'", ("0" * 64,))
    with pytest.raises(SaveRefusal, match="different case"):
        Save.open(db)


def test_a_rechained_log_with_extra_payload_fields_is_refused(db):
    def add_field(rows):
        rows[3]["payload"]["smuggled"] = 1
        return rows
    rechain(db, add_field)
    with pytest.raises(SaveRefusal, match="fields or values"):
        Save.open(db)


# ------------------------------------------------------------------ 7: a failed load / append mutates nothing
def test_a_refused_load_leaves_the_file_byte_identical(db):
    sql(db, "UPDATE session_events SET kind='Accusation' WHERE seq=5")
    before = db.read_bytes()
    with pytest.raises(SaveRefusal):
        Save.open(db)
    assert db.read_bytes() == before


def test_a_refused_append_commits_nothing_and_leaves_the_live_save_unchanged(db):
    s = Save.open(db, writable=True)
    h, seq, hh = s.state_hash(), s.last_seq, s.last_hash
    forged = [TurnCommitted(turn=s.state.turn_counter + 1, character="David"), AccountHeardEvent(token="clean@Elena", statement_id="S99999", turn=s.state.turn_counter + 1)]
    with pytest.raises(SaveRefusal):
        s.append(forged, seq, "forged-1")
    assert (s.state_hash(), s.last_seq, s.last_hash) == (h, seq, hh)
    assert Save.open(db).state_hash() == h and Save.open(db).last_seq == seq


# ------------------------------------------------------------------ 8: unknown / invalid events fail closed
def test_a_rechained_unknown_event_kind_is_refused(db):
    def inject(rows):
        rows.append({"turn": rows[-1]["turn"], "kind": "GodMode", "action_id": rows[-1]["action_id"], "payload": {"kind": "GodMode"}})
        return rows
    rechain(db, inject)
    with pytest.raises(SaveRefusal, match="unknown event kind"):
        Save.open(db)


def test_a_payload_whose_kind_disagrees_with_its_column_is_refused(db):
    def swap(rows):
        rows[4]["kind"] = "Accusation" if rows[4]["kind"] != "Accusation" else "CaseSolved"
        return rows
    rechain(db, swap)
    with pytest.raises(SaveRefusal):
        Save.open(db)


def test_append_refuses_an_object_that_is_not_a_registered_event(db):
    s = Save.open(db, writable=True)
    class Sneaky(TurnCommitted):
        pass
    with pytest.raises(SaveRefusal):
        s.append([Sneaky(turn=s.state.turn_counter + 1)], s.last_seq, "sneaky")
    with pytest.raises(SaveRefusal):
        s.append([object()], s.last_seq, "obj")


def test_a_turn_must_open_with_turn_committed_and_continue_the_count(db):
    s = Save.open(db, writable=True)
    t = s.state.turn_counter
    with pytest.raises(SaveRefusal):
        s.append([Accusation(turn=t + 1, target="Elena", provisional=True)], s.last_seq, "no-head")
    with pytest.raises(SaveRefusal):
        s.append([TurnCommitted(turn=t + 5)], s.last_seq, "skip")
    with pytest.raises(SaveRefusal):
        s.append([TurnCommitted(turn=t + 1), TurnCommitted(turn=t + 1)], s.last_seq, "twice")
    with pytest.raises(SaveRefusal):
        s.append([TurnCommitted(turn=t + 1), Accusation(turn=t + 2, target="Elena", provisional=True)], s.last_seq, "row-turn")


def test_a_turn_must_open_with_turn_committed_and_every_row_carries_that_turn(db):
    """Phase 9, found by re-running this file's mutation harness: the assertion above is also refused by Phase 8's rule for a
    provisional accusation, so it no longer isolates the row-turn rule (mutant `row-turn-inside-a-turn-unchecked` survived).
    A location row is refused ONLY for carrying another turn's number."""
    from eidolon.decision.exploration import LocationVisited
    s = Save.open(db, writable=True)
    t = s.state.turn_counter
    with pytest.raises(SaveRefusal, match="inside turn"):
        s.append([TurnCommitted(turn=t + 1), LocationVisited(location="Study", turn=t + 2)], s.last_seq, "stamped-ahead")
    with pytest.raises(SaveRefusal, match="inside turn"):
        s.append([TurnCommitted(turn=t + 1), LocationVisited(location="Study", turn=t)], s.last_seq, "stamped-behind")
    assert s.state.turn_counter == t
    assert s.append([TurnCommitted(turn=t + 1), LocationVisited(location="Study", turn=t + 1)], s.last_seq, "stamped-right").appended


# ------------------------------------------------------------------ 9-10: impossible provenance / forged delivery
def ask(s, who="David", *, present=None, hint="where") -> list:
    """The complete, genuine event list of one conversation turn — what a forger starts from."""
    res = run_ask_turn(s.state, who, Query(kind="challenge" if present else "did_you", predicate_hint=hint, raw="q"),
                       presented_ref=present)
    assert not res.rejected, res.violations
    return list(res.events)


def _next(s):
    return TurnCommitted(turn=s.state.turn_counter + 1, character="David")


def test_a_hearing_row_cannot_make_an_old_or_unknown_statement_heard(db):
    """ADR-24 / I-50: an identifier in the file is not a delivery. Only a statement committed IN THIS TURN can be heard."""
    s = Save.open(db, writable=True)
    old = s.state.decision.statements.all()[0].id
    for ev in (StatementHeardEvent(statement_id=old, turn=s.state.turn_counter + 1),
               StatementHeardEvent(statement_id="S00000", turn=s.state.turn_counter + 1)):
        with pytest.raises(SaveRefusal, match="did not commit"):
            s.append([_next(s), ev], s.last_seq, f"h-{ev.statement_id}")


def test_an_account_token_cannot_be_minted_by_a_row(db):
    s = Save.open(db, writable=True)
    n = s.state.turn_counter + 1
    with pytest.raises(SaveRefusal):
        s.append([_next(s), AccountHeardEvent(token="clean@Elena", statement_id=f"S{n:05d}", turn=n)], s.last_seq, "mint")
    assert "clean@Elena" not in s.state.discovery.known_accounts


def test_a_statement_cannot_list_an_account_its_claims_do_not_deliver(db):
    s = Save.open(db, writable=True)
    n = s.state.turn_counter + 1
    base = next(st for st in reversed(s.state.decision.statements.all()) if st.claims)
    forged = base.model_copy(update={"id": f"S{n:05d}", "turn": n, "speaker": "David", "accounts": ("attack@David",),
                                     "claims": tuple(c.model_copy(update={"statement": f"S{n:05d}"}) for c in base.claims)})
    # David's OWN murder-event account, with every hearing row present: only the delivery check can refuse it
    with pytest.raises(SaveRefusal, match="do not deliver"):
        s.append([_next(s), ClaimMade(statement=forged), StatementHeardEvent(statement_id=forged.id, turn=n),
                  AccountHeardEvent(token="attack@David", statement_id=forged.id, turn=n)], s.last_seq, "acct")


def test_a_claim_grounded_in_nothing_is_refused(db):
    s = Save.open(db, writable=True)
    n = s.state.turn_counter + 1
    base = next(st for st in reversed(s.state.decision.statements.all()) if st.claims)
    c0 = base.claims[0].model_copy(update={"statement": f"S{n:05d}", "grounding": ("K:does-not-exist",)})
    forged = base.model_copy(update={"id": f"S{n:05d}", "turn": n, "speaker": "David", "accounts": (), "claims": (c0,)})
    with pytest.raises(SaveRefusal, match="resolves to nothing"):
        s.append([_next(s), ClaimMade(statement=forged)], s.last_seq, "ground")


def test_a_discovery_with_unmet_prerequisites_is_refused(built, tmp_path):
    s = Save.create(tmp_path / "fresh.db", BUNDLE, seed=7)
    gated = next(e for e in s.state.evidence.all() if e.discovery.prerequisites)
    d = Discovery(evidence_id=gated.id, turn=1, action=gated.discovery.action, at=gated.discovery.at)
    with pytest.raises(SaveRefusal, match="unmet prerequisites"):
        s.append([TurnCommitted(turn=1), d], 0, "skip-the-gate")
    assert not s.state.discovery.known_evidence


def test_a_detective_model_cannot_be_told_about_evidence_the_player_never_found(built, tmp_path):
    s = Save.create(tmp_path / "fresh.db", BUNDLE, seed=7)
    dm = DetectiveModel(known_evidence=frozenset({"E_trace"}))
    with pytest.raises(SaveRefusal, match="never discovered"):
        s.append(ask(s) + [DetectiveModelUpdate(new_model=dm)], 0, "telepathy")


def test_knowledge_added_must_carry_investigation_provenance(built, tmp_path):
    s = Save.create(tmp_path / "fresh.db", BUNDLE, seed=7)
    entry = s.state.knowledge.all()[0]          # a Participated/Perceived entry, not InvestigationTold
    with pytest.raises(SaveRefusal, match="InvestigationTold"):
        s.append(ask(s, entry.character) + [KnowledgeAdded(entry=entry)], 0, "inject")


def test_a_layer_peel_must_continue_the_recorded_cover_state(built, tmp_path):
    from eidolon.decision.events import LayerPeel
    s = Save.create(tmp_path / "fresh.db", BUNDLE, seed=7)
    sec = next(x for x in s.state.secrets.for_owner("David"))
    for bad in (LayerPeel(character="David", secret_id=sec.id, from_index=1, to_index=2),
                LayerPeel(character="David", secret_id=sec.id, from_index=0, to_index=99),
                LayerPeel(character="Elena", secret_id=sec.id, from_index=0, to_index=1),
                LayerPeel(character="David", secret_id="S_nope", from_index=0, to_index=1)):
        with pytest.raises(SaveRefusal):
            s.append([TurnCommitted(turn=1, character="David"), bad], 0, "peel")


def test_a_rechained_log_that_shows_a_character_undiscovered_evidence_is_refused_at_load(db):
    s = Save.open(db)
    undiscovered = next((e.id for e in s.state.evidence.all() if e.id not in s.state.discovery.known_evidence), "E_never_found")
    dm = DetectiveModel(known_evidence=frozenset({undiscovered}))
    def forge(rows):
        k = max(i for i, r in enumerate(rows) if r["kind"] == "TurnCommitted" and r["payload"]["character"] == "David")
        rows.insert(k + 1, {"turn": rows[k]["turn"], "kind": "DetectiveModelUpdate", "action_id": rows[k]["action_id"],
                            "payload": store._plain(DetectiveModelUpdate(new_model=dm))})
        return rows
    rechain(db, forge)
    with pytest.raises(SaveRefusal):
        Save.open(db)


def test_a_rechained_log_reusing_an_action_id_across_turns_is_refused(db):
    def reuse(rows):
        heads = [r for r in rows if r["kind"] == "TurnCommitted"]
        for r in rows:
            if r["turn"] == heads[1]["turn"]:
                r["action_id"] = heads[0]["action_id"]
        return rows
    rechain(db, reuse)
    with pytest.raises(SaveRefusal, match="action_id"):
        Save.open(db)


def test_a_peel_cannot_skip_a_layer_of_a_three_layer_cover(tmp_path):
    """Only a three-layer cover distinguishes 'continues the recorded index' from 'stays inside the cover'."""
    from eidolon.decision.events import LayerPeel
    s = Save.create(tmp_path / "manor.db", ROOT / "cases" / "generated" / "manor_wing_s4.json", seed=1)
    sec = next(x for x in s.state.secrets.all() if len(x.cover.layers) >= 3)
    with pytest.raises(SaveRefusal, match="does not continue"):
        s.append([TurnCommitted(turn=1, character=sec.owner),
                  LayerPeel(character=sec.owner, secret_id=sec.id, from_index=1, to_index=2)], 0, "skip")


def _overlay_events(s, turn):
    from eidolon.minds.epistemic import RecallRecord, Revision
    from eidolon.minds.events import BeliefRevised, MemoryCorrected, MemoryRecall
    from eidolon.minds.provenance import InvestigationTold
    mem = s.state.memories["David"][0]
    belief = s.state.knowledge and next(iter(s.state.beliefs.for_character("David")))
    entry = s.state.knowledge.all()[0].model_copy(update={"id": "K:detective-1", "character": "David",
                                                           "source": InvestigationTold(by_detective_turn=turn),
                                                           "reliability": 0.3})
    return mem, belief, ask(s, "David") + [
        MemoryRecall(memory_id=mem.id, turn_id=turn, new_strength_bp=5000, record=RecallRecord(turn_id=turn, cue_match_bp=3000, outcome="strong")),
        MemoryCorrected(memory_id=mem.id, field="interval", corrected_value=5, turn_id=turn),
        BeliefRevised(belief_id=belief.id, new_confidence_bp=4000, revision=Revision(turn_id=turn, old_bp=5000, new_bp=4000, reason="t")),
        KnowledgeAdded(entry=entry)]


def test_the_epistemic_overlay_round_trips_and_is_part_of_the_hash(tmp_path):
    s = Save.create(tmp_path / "e.db", BUNDLE, seed=7)
    h0 = s.state_hash()
    _, _, evs = _overlay_events(s, 1)
    s.append(evs, 0, "overlay")
    assert s.state.epistemic.added_knowledge and s.state_hash() != h0   # (also: a float `reliability` is hashed as bp)
    h = s.state_hash()
    s.close()
    assert Save.open(tmp_path / "e.db").state_hash() == h


def test_overlay_rows_must_name_something_the_case_derived(tmp_path):
    from eidolon.minds.epistemic import RecallRecord, Revision
    from eidolon.minds.events import BeliefRevised, MemoryRecall
    s = Save.create(tmp_path / "e.db", BUNDLE, seed=7)
    rec = RecallRecord(turn_id=1, cue_match_bp=1, outcome="strong")
    with pytest.raises(SaveRefusal, match="never derived"):
        s.append(ask(s) + [MemoryRecall(memory_id="M:ghost", turn_id=1, new_strength_bp=9999, record=rec)], 0, "m")
    with pytest.raises(SaveRefusal, match="never derived"):
        s.append(ask(s) + [BeliefRevised(belief_id="B:ghost", new_confidence_bp=1, revision=Revision(turn_id=1, old_bp=1, new_bp=1, reason="x"))], 0, "b")


# ------------------------------------------------------------------ 11-12: proof / package association
def _edit_bundle(db, edit, reseal):
    c = sqlite3.connect(db, isolation_level=None)
    doc = json.loads(c.execute("SELECT doc FROM case_bundle").fetchone()[0])
    edit(doc)
    if reseal:
        doc["bundle_seal"] = bundle_seal(doc["package"]["seal"], doc["proof"], doc["report"])
    c.execute("UPDATE case_bundle SET doc=?", (json.dumps(doc),))
    c.close()


def test_a_proof_with_its_exclusions_deleted_is_refused_even_with_the_bundle_seal_repaired(db):
    _edit_bundle(db, lambda d: d["proof"]["candidates"].pop("Elena"), reseal=True)
    with pytest.raises(SaveRefusal, match="embedded case refused"):
        Save.open(db)


def test_a_proof_claiming_a_different_survivor_is_refused(db):
    _edit_bundle(db, lambda d: d["proof"].update(survivors=["Elena"]), reseal=True)
    with pytest.raises(SaveRefusal, match="embedded case refused"):
        Save.open(db)


def test_swapping_in_another_cases_proof_is_refused(db):
    other = json.loads(OTHER_BUNDLE.read_text())
    _edit_bundle(db, lambda d: d.update(proof=other["proof"]), reseal=True)
    with pytest.raises(SaveRefusal, match="different package"):
        Save.open(db)


def test_editing_the_package_after_sealing_is_refused(db):
    _edit_bundle(db, lambda d: d["package"].update(seed=12345), reseal=False)
    with pytest.raises(SaveRefusal, match="embedded case refused"):
        Save.open(db)


def test_create_refuses_an_unverifiable_bundle_and_writes_nothing(tmp_path):
    bad = json.loads(BUNDLE.read_text())
    bad["proof"]["survivors"] = ["Elena"]
    bad["bundle_seal"] = bundle_seal(bad["package"]["seal"], bad["proof"], bad["report"])
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad))
    with pytest.raises(_Seal):
        Save.create(tmp_path / "x.db", p)
    assert not (tmp_path / "x.db").exists() and not (tmp_path / "x.db.tmp").exists()


# ------------------------------------------------------------------ append protocol (§26.2)
def test_stale_expected_seq_is_rejected_and_a_duplicate_action_is_a_noop(db):
    s = Save.open(db, writable=True)
    seq, h = s.last_seq, s.state_hash()
    ev = [TurnCommitted(turn=s.state.turn_counter + 1)]
    with pytest.raises(StaleAppend):
        s.append(ev, seq - 1, "stale")
    assert s.append(ev, seq, "new-act").appended
    assert s.last_seq == seq + 1
    again = s.append(ev, seq, "new-act")                  # a retry: same action_id, now-stale expected_seq
    assert not again.appended and s.last_seq == seq + 1
    assert Save.open(db).last_seq == seq + 1 and Save.open(db).state_hash() != h


def test_a_second_writer_makes_the_first_stale(db):
    a, b = Save.open(db, writable=True), Save.open(db, writable=True)
    a.append([TurnCommitted(turn=a.state.turn_counter + 1)], a.last_seq, "from-a")
    with pytest.raises(StaleAppend):
        b.append([TurnCommitted(turn=b.state.turn_counter + 1)], b.last_seq, "from-b")


def test_a_resumed_save_continues_and_reloads_to_the_live_hash(db):
    s = Save.open(db, writable=True)
    live = drive(s, 25, start=1000)
    s.close()
    assert Save.open(db).state_hash() == store.state_hash(live)


# ------------------------------------------------------------------ export, traces, recovery
def test_export_is_an_atomic_verified_copy_without_traces(db, tmp_path):
    s = Save.open(db, writable=True)
    s.append([TurnCommitted(turn=s.state.turn_counter + 1)], s.last_seq, "t", trace={"plan_act": "x"})
    dest = tmp_path / "out" / "copy.db"
    dest.parent.mkdir()
    s.export(dest)
    assert Save.open(dest).state_hash() == s.state_hash()
    assert not list(dest.parent.glob("*.tmp")) and not list(dest.parent.glob("*.traces.db"))


def test_trace_write_is_best_effort_and_gaps_are_reported_not_fatal(db):
    s = Save.open(db, writable=True)
    n = s.state.turn_counter
    s.append([TurnCommitted(turn=n + 1)], s.last_seq, "a", trace={"plan_act": "T"})
    assert n + 1 not in s.trace_gaps() and n in s.trace_gaps()
    s.trace_path.unlink()
    s.trace_path.mkdir()                                   # the trace file is unwritable: the turn must still commit
    assert s.append([TurnCommitted(turn=n + 2)], s.last_seq, "b", trace={"plan_act": "T"}).appended
    assert Save.open(db).state.turn_counter == n + 2


def test_truncation_recovery_needs_confirmation_and_yields_a_loadable_prefix(db):
    sql(db, "UPDATE session_events SET kind='Accusation' WHERE seq=50")
    with pytest.raises(SaveRefusal) as e:
        Save.open(db)
    assert e.value.seq == 50
    with pytest.raises(SaveError):
        store.truncate_to_last_valid(db)
    cut = store.truncate_to_last_valid(db, confirm=True)
    assert 0 < cut < 50
    assert Save.open(db).last_seq == cut


# ------------------------------------------------------------------ T-23: fold completeness, nothing recomputed
CHARACTER_WRITERS = {"emotion": "EmotionalDelta", "trust_detective": "TrustChange",
                     "suspicion_of_detective": "SuspicionShift", "suspicion": "SuspicionShift",
                     "verbal_pressure": "PressureChange", "composure": "ComposureChange",
                     "refuse_streak": "CoverStateDelta", "topics_probed": "CoverStateDelta",
                     "contradictions_caught": "CoverStateDelta", "slips_used": "CoverStateDelta",
                     "detective_model": "DetectiveModelUpdate"}
EPISTEMIC_WRITERS = {"memory_strength": "MemoryRecall", "recall_log": "MemoryRecall", "belief_confidence": "BeliefRevised",
                     "belief_revisions": "BeliefRevised", "distortion_corrections": "MemoryCorrected",
                     "added_knowledge": "KnowledgeAdded"}
DISCOVERY_WRITERS = {"known_evidence": "apply_discovery", "known_statements": "apply_heard", "known_accounts": "apply_heard",
                     "visited_locations": "apply_exploration", "held_items": "apply_exploration"}


def test_every_runtime_field_has_a_writer_in_a_fold_and_the_hash_covers_it_T23():
    from eidolon.decision import exploration
    from eidolon.evidence import discovery
    from eidolon.minds import fold
    assert set(CharacterState.model_fields) - {"actor", "personality"} == set(CHARACTER_WRITERS)
    assert set(EpistemicState.model_fields) == set(EPISTEMIC_WRITERS)
    assert set(DiscoveryState.model_fields) == set(DISCOVERY_WRITERS)
    for f, kind in CHARACTER_WRITERS.items():
        assert f'"{f}"' in inspect.getsource(fold.apply_character) and kind in inspect.getsource(fold.apply_character)
    for f, kind in EPISTEMIC_WRITERS.items():
        assert f'"{f}"' in inspect.getsource(fold.apply_epistemic) and kind in inspect.getsource(fold.apply_epistemic)
    src = {"apply_discovery": inspect.getsource(discovery.apply_discovery), "apply_heard": inspect.getsource(exploration.apply_heard),
           "apply_exploration": inspect.getsource(exploration.apply_exploration)}
    for f, fn in DISCOVERY_WRITERS.items():
        assert f in src[fn]
    # ...and the state hash covers every one of them (a field the hash skips could drift unnoticed):
    from eidolon.solve.session import new_session
    from eidolon.solve.package import load_sealed_case
    doc = store.canonical_state(new_session(load_sealed_case(str(BUNDLE)), seed=3))
    assert set(next(iter(doc["characters"].values()))) == set(CharacterState.model_fields) - {"personality"}
    assert set(doc["epistemic"]) == set(EpistemicState.model_fields)
    assert set(doc["discovery"]) == set(DiscoveryState.model_fields)
    assert set(doc["decision"]) == {f.name for f in __import__("dataclasses").fields(DecisionState)}


def test_the_folds_never_consult_a_weight_a_score_retrieval_or_a_model():
    from eidolon.decision import exploration
    from eidolon.minds import fold
    text = "".join(inspect.getsource(x) for x in (store.fold_turn, store._fold_turn, store._check_peel, fold.apply_character,
                                                    fold.apply_epistemic, exploration.apply_heard, exploration.apply_exploration))
    for banned in ("refutation_weight", "update_composure", "update_verbal_pressure", "retrieve(", "score(", "select_plan",
                   "evaluate_peel", "TemplateLLM", "random"):
        assert banned not in text, banned


def test_the_state_hash_contains_no_float_and_refuses_one():
    with pytest.raises(ValueError, match="float"):
        store._no_floats({"a": [1, {"b": 0.5}]})


def test_the_store_is_never_imported_by_a_lower_layer():
    import ast
    for layer in ("world", "minds", "evidence", "decision", "llm", "solve", "gen"):
        for f in (ROOT / "eidolon" / layer).glob("*.py"):
            for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
                mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                assert not any(m.split(".")[-1] == "store" for m in mods), f


# ------------------------------------------------------------------ CLI
def test_cli_replay_verifies_and_reports_gaps_and_refuses_a_broken_save(db, built, capsys):
    from eidolon.cli import main
    assert main(["replay", str(db), "--verify"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] and out["state_hash"] == built[1] and out["trace_gaps"] > 0
    sql(db, "UPDATE session_events SET kind='Accusation' WHERE seq=5")
    assert main(["replay", str(db), "--verify"]) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


# ------------------------------------------------------------------ scale: save/load/replay equality
@pytest.mark.parametrize("n", [500] + ([1000, 2000] if os.environ.get("EIDOLON_LONG") else []))
def test_long_session_save_load_replay_equality(tmp_path, n):
    s = Save.create(tmp_path / f"long{n}.db", BUNDLE, seed=n)
    live = drive(s, n)
    h = store.state_hash(live)
    assert s.state_hash() == h
    s.close()
    assert Save.open(tmp_path / f"long{n}.db").state_hash() == h


# ==================================================================================================================
# Phase 7 REPAIRS (docs/EIDOLON-PHASE-7-HOSTILE-REVIEW.md). Every test below is named for the finding it guards.
# ==================================================================================================================
from dataclasses import replace as _replace                                                   # noqa: E402

from eidolon.decision.claims import Claim                                                      # noqa: E402
from eidolon.decision.events import CaseSolved, ClaimRetracted, HypothesisChanged, LayerPeel, MetaAttemptLogged  # noqa: E402
from eidolon.decision.exploration import ItemTaken, LocationVisited                            # noqa: E402
from eidolon.decision.hypotheses import Hypothesis                                             # noqa: E402
from eidolon.decision.turn import run_take_turn                                                # noqa: E402
from eidolon.minds.events import ComposureChange, MemoryCorrected, PressureChange, SuspicionShift  # noqa: E402
from eidolon.minds.provenance import InvestigationTold                                         # noqa: E402
from eidolon.store import ConfirmationRequired, TurnRef                                        # noqa: E402
from eidolon.decision.events import IncidentalPinned                                           # noqa: E402
from eidolon.decision.hypotheses import Lied, Planted                                          # noqa: E402
from eidolon.decision.peel import claims_voiced_on_peel                                        # noqa: E402
from eidolon.minds.epistemic import RecallRecord, Revision                                     # noqa: E402
from eidolon.minds.events import BeliefRevised, CoverStateDelta, MemoryRecall                  # noqa: E402
from eidolon.world.propositions import At, DidNot, Has, Moved, ObjectAt, Said                          # noqa: E402


def inject(path, events, action_id):
    """What a forger who RE-CHAINS does: write `events` as one more turn with a valid hash chain and head, skipping
    `append`'s validation entirely. The loader is then the only thing standing between the file and the player."""
    c = sqlite3.connect(path, isolation_level=None)
    meta = dict(c.execute("SELECT key, value FROM meta"))
    seq, prev, turn = int(meta["head_seq"]), meta["head_hash"], events[0].turn
    for ev in events:
        seq += 1
        payload = store._plain(ev)
        h = store._row_hash(prev, seq, turn, ev.kind, action_id, payload)
        c.execute("INSERT INTO session_events VALUES (?,?,?,?,?,?,?)",
                  (seq, turn, ev.kind, action_id, store._canon(payload), prev, h))
        prev = h
    c.execute("UPDATE meta SET value=? WHERE key='head_seq'", (str(seq),))
    c.execute("UPDATE meta SET value=? WHERE key='head_hash'", (prev,))
    c.close()


def restate(evs, **update):
    """The same turn with its committed statement changed (what a forger edits)."""
    return [ClaimMade(statement=e.statement.model_copy(update=update)) if e.kind == "ClaimMade" else e for e in evs]


@pytest.fixture(scope="module")
def forge_base(tmp_path_factory):
    d = tmp_path_factory.mktemp("forge")
    s = Save.create(d / "f.db", BUNDLE, seed=7)
    st = drive(s, 6)
    res = run_ask_turn(st, "Elena", Query(kind="did_you", predicate_hint="where", raw="e1"))
    s.append(res.events, s.last_seq, "elena-1")                    # Elena has an earlier statement to be retracted
    s.close()
    return d / "f.db"


@pytest.fixture(scope="module")
def fsave(forge_base, tmp_path_factory):
    p = tmp_path_factory.mktemp("fs") / "f.db"
    shutil.copy(forge_base, p)
    s = Save.open(p, writable=True)
    yield s
    s.close()


def _n(s):
    return s.state.turn_counter + 1


def _sid(s):
    return f"S{_n(s):05d}"


def _peel_turn(s):
    evs = ask(s, "Elena", present="E_secret_Elena")
    assert {"LayerPeel", "ClaimRetracted"} <= {e.kind for e in evs}
    return evs


def _elena_old(s):
    return s.state.decision.statements.for_speaker("Elena")[0].id


def _david_secret(s):
    return s.state.secrets.for_owner("David")[0].id


def _forged_claim(s, **update):
    k = s.state.knowledge.for_character("Elena")[0]
    return Claim(id="c:forged", statement=_sid(s), proposition=k.proposition, sincerity="truthful", source="plan",
                 grounding=(k.id,)).model_copy(update=update)


def _own_claim(s, **update):
    """A claim David could really make: his own knowledge, bound to this turn's statement. Every forgery built from it
    carries ONE defect, so it can be refused by one guard only."""
    k = s.state.knowledge.for_character("David")[0]
    return Claim(id="c:own", statement=_sid(s), proposition=k.proposition, sincerity="truthful", source="plan",
                 grounding=(k.id,)).model_copy(update=update)


def _layer_claims(s, secret_id, index):
    """What a CONCESSION landing on `secret_id`'s layer `index` voices, bound to this turn's statement."""
    layer = s.state.secrets.get(secret_id).cover.layers[index]
    return tuple(c.model_copy(update={"statement": _sid(s)}) for c in claims_voiced_on_peel(layer))


def _peel_with(s, peel, voiced):
    """Elena's genuine peel turn, with its LayerPeel replaced by `peel` and the statement voicing exactly `voiced`."""
    return [peel if e.kind == "LayerPeel" else e for e in restate(_peel_turn(s), claims=voiced, accounts=())]


def _david_mem(s, who="David"):
    return s.state.memories[who][0]


def _recall(s, who="David", **kw):
    base = dict(memory_id=_david_mem(s, who).id, turn_id=_n(s), new_strength_bp=5000,
                record=RecallRecord(turn_id=_n(s), cue_match_bp=3000, outcome="strong"))
    return MemoryRecall(**{**base, **kw})


def _revised(s, who="David", turn_id=None):
    b = s.state.beliefs.for_character(who)[0]
    return BeliefRevised(belief_id=b.id, new_confidence_bp=4000,
                         revision=Revision(turn_id=turn_id or _n(s), old_bp=5000, new_bp=4000, reason="t"))


def _memory_float(s):
    return ask(s) + [MemoryCorrected(memory_id=_david_mem(s).id, field="interval", corrected_value=0.5, turn_id=_n(s))]


def _told_row(s, reliability, who="David", **entry):
    k = s.state.knowledge.all()[0].model_copy(update={"id": "K:told-1", "character": who, "reliability": reliability,
                                                      "source": InvestigationTold(by_detective_turn=_n(s)), **entry})
    return KnowledgeAdded(entry=k)


def _told(s, reliability):
    return ask(s) + [_told_row(s, reliability)]


def _two_model_updates(s):
    dm = s.state.characters["David"].detective_model
    a, b = sorted(s.state.discovery.known_evidence - dm.known_evidence)[:2]
    return ask(s) + [DetectiveModelUpdate(new_model=dm.model_copy(update={"known_evidence": dm.known_evidence | {a}})),
                     DetectiveModelUpdate(new_model=dm.model_copy(update={"known_evidence": dm.known_evidence | {a, b}}))]


_NOWHERE = At(actor="Ghost", location="Atlantis", interval=(0, 1))


def _hyp(s, **kw):
    """A board edit shaped as the Phase 8 producer shapes it — created and updated in this turn (F-3) — so every forgery
    built from it carries only the defect it names."""
    return [TurnCommitted(turn=_n(s)), HypothesisChanged(hypothesis=Hypothesis(id="H1", **{"created_turn": _n(s),
                                                                                           "updated_turn": _n(s), **kw}))]


def _acc(s, target="David", **kw):
    """A final accusation (§16.3) of this turn."""
    return Accusation(turn=_n(s), target=target, provisional=False, **kw)


def _verdict(s, target="David", correct=None, **kw):
    """The genuine shape of a verdict turn: its own bracket, one final accusation, the case closed with the PROVEN answer
    (`David` is study_party_s4's proof survivor)."""
    return [TurnCommitted(turn=_n(s)), _acc(s, target, **kw),
            CaseSolved(turn=_n(s), correct=(target == "David") if correct is None else correct)]


def _prov(s, target="David"):
    return Accusation(turn=_n(s), target=target, provisional=True)


def _accused_model(s, who="David", turn=None):
    old = s.state.characters[who].detective_model
    return DetectiveModelUpdate(new_model=old.model_copy(update={"accusations": old.accusations + ((turn or _n(s), True, who),)}))


def _dm(s, **kw):
    old = s.state.characters["David"].detective_model
    return ask(s) + [DetectiveModelUpdate(new_model=old.model_copy(update=kw))]


def _everything(s):
    return dict(known_evidence=frozenset(s.state.discovery.known_evidence),
                heard_statements=frozenset(x.id for x in s.state.decision.statements.all()))


# name -> (builder(save) -> the forged turn, regex the refusal must match). EVERY row is a turn no runner can produce.
FORGERIES = {
    "peel_with_no_statement": (lambda s: [TurnCommitted(turn=_n(s), character="David"),
                                          LayerPeel(character="David", secret_id=_david_secret(s), from_index=0, to_index=1)],
                               "carries no statement"),
    "peel_beside_a_non_concession": (lambda s: restate(_peel_turn(s), act="DEFLECT"), "not a CONCESSION"),
    "peel_nobody_voiced": (lambda s: restate(_peel_turn(s), claims=(), accounts=()), "not voiced"),
    "retraction_of_another_speaker": (lambda s: _peel_turn(s) + [ClaimRetracted(statement_id=s.state.decision.statements.for_speaker("David")[0].id,
                                                                                retracted_by=_sid(s))],
                                      "not a standing statement of the addressee"),
    "retraction_without_a_peel": (lambda s: ask(s, "Elena") + [ClaimRetracted(statement_id=_elena_old(s), retracted_by=_sid(s))],
                                  "peeled no layer"),
    "retraction_of_itself": (lambda s: _peel_turn(s) + [ClaimRetracted(statement_id=_sid(s), retracted_by=_sid(s))],
                             "retract itself"),
    "retraction_by_an_uncommitted_statement": (lambda s: [e.model_copy(update={"retracted_by": "S99999"}) if e.kind == "ClaimRetracted" else e
                                                          for e in _peel_turn(s)], "did not commit"),
    "claim_grounded_in_another_characters_knowledge": (lambda s: restate(ask(s), claims=(_forged_claim(s),), accounts=()),
                                                       "not its speaker's"),
    "statement_by_another_speaker": (lambda s: restate(ask(s), speaker="Elena"), "not this turn's statement"),
    "claim_bound_to_another_statement": (lambda s: restate(ask(s), claims=(_own_claim(s, statement="S00001"),), accounts=()),
                                         "not bound to its statement"),
    "peel_that_does_not_advance": (lambda s: _peel_with(s, LayerPeel(character="Elena", secret_id="S_Elena", from_index=0, to_index=0),
                                                        _layer_claims(s, "S_Elena", 0)), "does not continue"),
    "peel_past_the_end_of_the_cover": (lambda s: [e.model_copy(update={"to_index": 99}) if e.kind == "LayerPeel" else e
                                                  for e in _peel_turn(s)], "does not continue"),
    "peel_of_another_characters_secret": (lambda s: _peel_with(s, LayerPeel(character="David", secret_id="S_David", from_index=0, to_index=1),
                                                               _layer_claims(s, "S_David", 1)), "not the addressee's own secret"),
    "peel_of_a_secret_its_character_does_not_own": (lambda s: _peel_with(s, LayerPeel(character="Elena", secret_id="S_David", from_index=0, to_index=1),
                                                                         _layer_claims(s, "S_David", 1)), "not the addressee's own secret"),
    "meta_attempt_for_someone_else": (lambda s: ask(s) + [MetaAttemptLogged(turn=_n(s), character="Elena", query_kind="meta")],
                                      "not addressed"),
    "location_visited_inside_a_conversation": (lambda s: ask(s) + [LocationVisited(location="Study", turn=_n(s))],
                                               "inside a conversation turn"),
    "a_character_who_does_not_exist": (lambda s: [TurnCommitted(turn=_n(s), character="Ghost"),
                                                  ClaimMade(statement=ask(s)[1].statement.model_copy(update={"speaker": "Ghost", "claims": (), "accounts": ()})),
                                                  StatementHeardEvent(statement_id=_sid(s), turn=_n(s))], "unknown character"),
    "minds_rows_and_no_statement": (lambda s: [TurnCommitted(turn=_n(s), character="David"), ComposureChange(new_composure_bp=0),
                                               PressureChange(secret_id=_david_secret(s), new_value_bp=10000)],
                                    "carries no statement"),
    "a_statement_nobody_heard": (lambda s: [e for e in ask(s) if e.kind != "StatementHeard"], "heard exactly once"),
    "a_bare_conversation_bracket": (lambda s: [TurnCommitted(turn=_n(s), character="David")], "carries no statement"),
    "detective_model_rewrites_other_fields": (lambda s: _dm(s, accusations=((1, True, "Elena"),)), "rewrites more"),
    "detective_model_shown_everything_at_once": (lambda s: _dm(s, **_everything(s)), "at most the one item"),
    "detective_model_ahead_of_discovery": (lambda s: _dm(s, known_evidence=s.state.characters["David"].detective_model.known_evidence | {"E_never_found"}),
                                         "never discovered"),
    "go_to_a_place_that_does_not_exist": (lambda s: [TurnCommitted(turn=_n(s)), LocationVisited(location="Atlantis", turn=_n(s))],
                                          "no such place"),
    "take_an_item_that_does_not_exist": (lambda s: [TurnCommitted(turn=_n(s)), ItemTaken(item="Excalibur", turn=_n(s))],
                                         "no such item"),
    "pressure_on_a_secret_that_does_not_exist": (lambda s: ask(s) + [PressureChange(secret_id="S_nope", new_value_bp=10)],
                                                 "does not own"),
    "suspicion_of_nobody": (lambda s: ask(s) + [SuspicionShift(target="Nobody", new_value_bp=10)], "unknown actor"),
    "accusation_of_nobody": (lambda s: [TurnCommitted(turn=_n(s)), Accusation(turn=_n(s), target="Nobody", provisional=False)],
                             "candidate domain"),
    "turn_names_another_action": (lambda s: [TurnCommitted(turn=_n(s), action_id="some-other-action")], "committed as"),
    "the_same_row_twice": (lambda s: ask(s) + [ComposureChange(new_composure_bp=5000), ComposureChange(new_composure_bp=5000)],
                           "appears twice"),
    "two_statements_in_one_turn": (lambda s: ask(s) + [ClaimMade(statement=ask(s)[1].statement.model_copy(update={"text": "again"}))],
                                   "two statements"),
    "a_hypothesis_on_material_never_held": (lambda s: _hyp(s, support=("E_never_found",)), "does not hold"),
    "a_float_in_an_overlay": (_memory_float, "float"),
    "told_more_reliably_than_trusted_I25": (lambda s: _told(s, 1.0), "trust"),
    "reliability_off_the_basis_point_grid": (lambda s: _told(s, 0.30001), "float"),
    "a_confidence_outside_0_1": (lambda s: _hyp(s, player_confidence=7.0), "float"),
    "a_confidence_off_the_basis_point_grid": (lambda s: _hyp(s, player_confidence=0.50001), "float"),
    # ---- R-1 (re-review): the nested references and shapes the first fold left open. One defect each.
    "R1_memory_recall_of_another_character": (lambda s: ask(s) + [_recall(s, "Elena")], "not about this turn's addressee"),
    "R1_memory_recall_in_an_exploration_turn": (lambda s: [TurnCommitted(turn=_n(s)), _recall(s)], "not about this turn's addressee"),
    "R1_memory_corrected_for_another_character": (lambda s: ask(s) + [MemoryCorrected(memory_id=_david_mem(s, "Elena").id, field="interval",
                                                                                      corrected_value=5, turn_id=_n(s))],
                                                  "not about this turn's addressee"),
    "R1_belief_revised_for_another_character": (lambda s: ask(s) + [_revised(s, "Elena")], "not about this turn's addressee"),
    "R1_belief_revised_in_an_exploration_turn": (lambda s: [TurnCommitted(turn=_n(s)), _revised(s)], "not about this turn's addressee"),
    "R1_knowledge_added_for_another_character": (lambda s: ask(s) + [_told_row(s, 0.3, "Elena")], "not about this turn's addressee"),
    "R1_knowledge_added_in_an_exploration_turn": (lambda s: [TurnCommitted(turn=_n(s)), _told_row(s, 0.3)], "not about this turn's addressee"),
    "R1_memory_corrected_field_the_memory_does_not_distort": (lambda s: ask(s) + [MemoryCorrected(memory_id=_david_mem(s).id, field="any_field_at_all",
                                                                                                  corrected_value="Atlantis", turn_id=_n(s))],
                                                              "does not distort"),
    "R1_memory_recall_carrying_another_turn_id": (lambda s: ask(s) + [_recall(s, turn_id=999)], "carries turn_id 999"),
    "R1_recall_record_carrying_another_turn_id": (lambda s: ask(s) + [_recall(s, record=RecallRecord(turn_id=999, cue_match_bp=3000, outcome="strong"))],
                                                  "carries turn_id 999"),
    "R1_belief_revision_carrying_another_turn_id": (lambda s: ask(s) + [_revised(s, turn_id=999)], "carries turn_id 999"),
    "R1_two_detective_model_updates_in_one_turn": (_two_model_updates, "two DetectiveModelUpdate"),
    "R1_slip_nobody_has": (lambda s: ask(s) + [CoverStateDelta(slips_used=("nonsense",))], "slips_used"),
    "R1_contradiction_nothing_resolves": (lambda s: ask(s) + [CoverStateDelta(contradictions_caught=("bogus",))], "contradictions_caught"),
    "R1_negative_refuse_streak": (lambda s: ask(s) + [CoverStateDelta(refuse_streak=-5)], "negative counter"),
    "F15_refuse_streak_in_a_turn_that_did_not_refuse": (lambda s: ask(s) + [CoverStateDelta(refuse_streak=2)], "run of consecutive REFUSE"),
    "R1_negative_topic_counter": (lambda s: ask(s) + [CoverStateDelta(topics_probed={"where": -100})], "negative counter"),
    "R1_incidental_pinned_by_another_character": (lambda s: ask(s) + [IncidentalPinned(speaker="Elena", entity="port", attr="x", value="y")],
                                                  "not this turn's addressee"),
    "R1_incidental_pinned_in_an_exploration_turn": (lambda s: [TurnCommitted(turn=_n(s)), IncidentalPinned(speaker="David", entity="port", attr="x", value="y")],
                                                    "not this turn's addressee"),
    "R1_incidental_scoped_to_a_layer_its_cover_lacks": (lambda s: ask(s) + [IncidentalPinned(speaker="David", entity="port", attr="x", value="y",
                                                                                              layer_scope=("S_David", 9))], "scoped to"),
    "R1_incidental_scoped_to_a_secret_it_does_not_own": (lambda s: ask(s) + [IncidentalPinned(speaker="David", entity="port", attr="x", value="y",
                                                                                               layer_scope=("S_Elena", 0))], "scoped to"),
    "R1_incidental_scoped_to_no_secret": (lambda s: ask(s) + [IncidentalPinned(speaker="David", entity="port", attr="x", value="y",
                                                                                layer_scope=("S_nope", 0))], "scoped to"),
    "R1_statement_scoped_to_a_layer_its_cover_lacks": (lambda s: restate(ask(s), layer_scope=("S_David", 9)), "scoped to"),
    "R1_statement_scoped_to_a_secret_it_does_not_own": (lambda s: restate(ask(s), layer_scope=("S_Elena", 0)), "scoped to"),
    "R1_two_claims_with_one_id": (lambda s: restate(ask(s), claims=(_own_claim(s), _own_claim(s)), accounts=()), "two claims with one id"),
    "R1_claim_naming_an_unknown_actor_and_place": (lambda s: restate(ask(s), claims=(_own_claim(s, proposition=_NOWHERE),), accounts=()),
                                                   "does not contain"),
    "R1_claim_naming_an_unknown_object": (lambda s: restate(ask(s), claims=(_own_claim(s, proposition=Has(actor="David", object="Excalibur", interval=(0, 1))),),
                                                            accounts=()), "does not contain"),
    "R1_claim_naming_an_unknown_holder": (lambda s: restate(ask(s), claims=(_own_claim(s, proposition=ObjectAt(object=next(iter(s.state.case.objects)),
                                                                                                            holder="Atlantis", interval=(0, 1))),),
                                                            accounts=()), "does not contain"),
    "R1_hypothesis_naming_an_unknown_actor_and_place": (lambda s: _hyp(s, propositions=(_NOWHERE,)), "does not contain"),
    "R1_hypothesis_Lied_on_a_statement_never_held": (lambda s: _hyp(s, propositions=(Lied(actor="David", statement="S99999"),)), "Lied names statement"),
    "R1_hypothesis_Planted_on_evidence_never_held": (lambda s: _hyp(s, propositions=(Planted(evidence="E_nope"),)), "Planted names evidence"),
    "R1_knowledge_told_naming_an_unknown_actor": (lambda s: ask(s) + [_told_row(s, 0.3, proposition=_NOWHERE)], "does not contain"),
    # ---- F-1 (closure review): a time slot outside the case's own clock [0, t_investigation]. `feasible` enumerates every tick of a standing
    # claim, so an unbounded one starves or kills the character's later turns. One defect each; everything else is genuine.
    "F1_claim_interval_far_beyond_the_clock": (lambda s: restate(ask(s), claims=(_own_claim(s, proposition=At(actor="David", location="Study", interval=(0, 2 ** 40))),),
                                                                 accounts=()), "outside the case's clock"),
    "F1_claim_interval_ending_one_tick_past_the_clock": (lambda s: restate(ask(s), claims=(_own_claim(s, proposition=At(
        actor="David", location="Study", interval=(100, s.state.case.t_investigation + 1))),), accounts=()), "outside the case's clock"),
    "F1_claim_interval_starting_before_time_zero": (lambda s: restate(ask(s), claims=(_own_claim(s, proposition=At(
        actor="David", location="Study", interval=(-2 ** 40, 0))),), accounts=()), "outside the case's clock"),
    "F1_claim_moved_at_a_tick_far_beyond_the_clock": (lambda s: restate(ask(s), claims=(_own_claim(s, proposition=Moved(
        actor="David", from_loc="Study", to_loc="Study", t=2 ** 40)),), accounts=()), "outside the case's clock"),
    "F1a_claim_moved_at_a_negative_tick": (lambda s: restate(ask(s), claims=(_own_claim(s, proposition=Moved(
        actor="David", from_loc="Study", to_loc="Study", t=-1)),), accounts=()), "outside the case's clock"),   # F1-a (re-review)
    "F1_claim_said_nesting_an_unbounded_interval":(lambda s: restate(ask(s), claims=(_own_claim(s, proposition=Said(
        speaker="David", listener="Elena", t=5, proposition=At(actor="David", location="Study", interval=(0, 2 ** 40)))),), accounts=()),
        "outside the case's clock"),
    "F1_hypothesis_interval_far_beyond_the_clock": (lambda s: _hyp(s, propositions=(At(actor="David", location="Study", interval=(0, 2 ** 40)),)),
                                                    "outside the case's clock"),
    "F1_knowledge_told_interval_far_beyond_the_clock": (lambda s: ask(s) + [_told_row(s, 0.3, proposition=At(actor="David", location="Study",
                                                                                                          interval=(0, 2 ** 40)))],
                                                        "outside the case's clock"),
    "R1_peel_voiced_with_other_claims": (lambda s: _peel_with(s, next(e for e in _peel_turn(s) if e.kind == "LayerPeel"),
                                                              tuple(c.model_copy(update={"proposition": s.state.knowledge.for_character("David")[0].proposition})
                                                                    for c in _layer_claims(s, "S_Elena", 1))), "not voiced"),
    # ---- Phase 8: the producer contracts of `HypothesisChanged`, `Accusation` and `CaseSolved`. One defect each.
    "P8_hypothesis_inside_a_conversation_turn": (lambda s: ask(s) + [_hyp(s)[1]], "inside a conversation turn"),
    "P8_hypothesis_updated_in_another_turn_F3": (lambda s: _hyp(s, updated_turn=999), "updated_turn"),
    "P8_hypothesis_created_in_another_turn_F3": (lambda s: _hyp(s, created_turn=3), "created"),
    "P8_hypothesis_born_withdrawn": (lambda s: _hyp(s, status="withdrawn"), "withdrawn"),
    "P8_hypothesis_Lied_about_another_speakers_words": (lambda s: _hyp(s, propositions=(Lied(actor="Elena", statement=next(
        i for i in sorted(s.state.discovery.known_statements) if s.state.decision.statements.get(i).speaker == "David")),)),
        "not Elena's"),
    "P8_provisional_accusation_outside_a_conversation": (lambda s: [TurnCommitted(turn=_n(s)), _prov(s)], "provisional accusation"),
    "P8_provisional_accusation_of_someone_not_addressed": (lambda s: ask(s) + [_prov(s, "Elena")], "provisional accusation"),
    "P8_provisional_accusation_the_model_does_not_record": (lambda s: ask(s) + [_prov(s)], "does not record"),
    "H8N1_provisional_accusation_carrying_a_solution_form": (
        lambda s: ask(s) + [_prov(s).model_copy(update={"weapon": "ghost", "interval": (0, 2 ** 40)}), _accused_model(s)], "no solution form"),
    "H8N1_provisional_accusation_citing_anything": (
        lambda s: ask(s) + [_prov(s).model_copy(update={"cited": ("E_nonexistent",)}), _accused_model(s)], "no solution form"),
    "P8_model_records_an_accusation_nobody_made": (lambda s: ask(s) + [_accused_model(s)], "rewrites more"),
    "P8_model_records_the_accusation_at_another_turn": (lambda s: ask(s) + [_prov(s), _accused_model(s, turn=999)], "rewrites more"),
    "P8_final_accusation_inside_a_conversation": (lambda s: ask(s) + _verdict(s)[1:], "a turn of its own"),
    "P8_final_accusation_citing_material_never_held": (lambda s: _verdict(s, cited=("E_never_found",)), "does not hold"),
    "P8_final_accusation_citing_an_account_token": (lambda s: _verdict(s, cited=("clean@Elena",)), "does not hold"),
    "P8_final_accusation_naming_a_weapon_the_case_lacks": (lambda s: _verdict(s, weapon="Excalibur"), "does not contain"),
    "P8_final_accusation_naming_a_place_the_case_lacks": (lambda s: _verdict(s, location="Atlantis"), "does not contain"),
    "P8_final_accusation_window_off_the_clock": (lambda s: _verdict(s, interval=(0, 2 ** 40)), "outside the case's clock"),
    "P8_final_accusation_that_does_not_close_the_case": (lambda s: _verdict(s)[:2], "must close the case"),
    # H9-I3 / C-1 (c): a confession is the proven murderer at a gated confession layer, saying exactly that layer
    "H9I3_confession_where_the_cover_has_no_confession_layer": (lambda s: restate(ask(s), act="CONFESSION"), "CONFESSION"),
    "H9I3_confession_by_someone_who_is_not_the_murderer": (lambda s: restate(ask(s, "Elena"), act="CONFESSION"),
                                                             "not the proven murderer"),
    "P8_two_final_accusations_in_one_turn": (lambda s: [TurnCommitted(turn=_n(s)), _acc(s, "Elena"), *_verdict(s)[1:]],
                                             "two final accusations"),
    "P8_case_solved_without_an_accusation_PN10": (lambda s: [TurnCommitted(turn=_n(s)), CaseSolved(turn=_n(s), correct=False)],
                                                  "without a final accusation"),
    "P8_case_solved_correct_for_an_innocent_PN10": (lambda s: _verdict(s, "Elena", correct=True), "proven murderer"),
    "P8_case_solved_incorrect_for_the_murderer_PN10": (lambda s: _verdict(s, "David", correct=False), "proven murderer"),
    "P8_case_solved_inside_a_conversation": (lambda s: ask(s) + [CaseSolved(turn=_n(s), correct=False)], "without a final accusation"),
    "P8_a_row_after_the_verdict_in_its_own_turn": (lambda s: _verdict(s) + [LocationVisited(location="Study", turn=_n(s))],
                                                   "nothing follows the verdict"),
}


@pytest.mark.parametrize("name", list(FORGERIES))
def test_PI1_a_turn_no_runner_can_produce_is_refused_at_append(fsave, name):
    build, why = FORGERIES[name]
    before = (fsave.state_hash(), fsave.last_seq, fsave.last_hash)
    with pytest.raises(SaveRefusal, match=why):
        fsave.append(build(fsave), fsave.last_seq, f"forge-{name}")
    assert (fsave.state_hash(), fsave.last_seq, fsave.last_hash) == before


@pytest.mark.parametrize("name", list(FORGERIES))
def test_PI1_the_same_forged_turn_is_refused_at_load(forge_base, fsave, tmp_path, name):
    """A forger who re-chains skips `append`. The loader runs the SAME fold, so it must say the same thing."""
    build, why = FORGERIES[name]
    p = tmp_path / "f.db"
    shutil.copy(forge_base, p)
    inject(p, build(fsave), f"forge-{name}")
    with pytest.raises(SaveRefusal, match=why):
        Save.open(p)


def test_PI1_a_genuine_peel_turn_is_accepted_and_reloads(forge_base, tmp_path):
    """The negative control: the fold is strict about forgeries, not about what the engine really does."""
    p = tmp_path / "f.db"
    shutil.copy(forge_base, p)
    s = Save.open(p, writable=True)
    assert s.append(_peel_turn(s), s.last_seq, "peel-1").appended
    h = s.state_hash()
    s.close()
    again = Save.open(p)
    assert again.state_hash() == h and again.state.decision.layer_peels


def test_PI1_the_case_cannot_be_solved_twice(tmp_path):
    # Phase 8: the first verdict is now the genuine shape (a bare `CaseSolved` is itself refused — PN-10, `P8_case_solved_*`).
    s = Save.create(tmp_path / "c.db", BUNDLE, seed=7)
    s.append(_verdict(s, "Elena"), 0, "s1")
    with pytest.raises(SaveRefusal, match="already solved"):
        s.append([TurnCommitted(turn=2), CaseSolved(turn=2, correct=True)], s.last_seq, "s2")
    with pytest.raises(SaveRefusal, match="already solved"):
        s.append(_verdict(s, "David"), s.last_seq, "s3")


def test_PI1_the_exploration_runners_reject_what_the_fold_would_refuse(fsave):
    st = fsave.state
    for res in (run_goto_turn(st, "Atlantis"), run_take_turn(st, "Excalibur")):
        assert res.rejected and res.events == () and res.state is st
    assert not run_goto_turn(st, "Study").rejected


# ------------------------------------------------------------------ PI-2: I-17 at the boundary
def test_PI2_a_bp_confidence_is_hashed_and_two_states_never_collide(tmp_path):
    a = Save.create(tmp_path / "h.db", BUNDLE, seed=7)
    a.append(_hyp(a, player_confidence=0.25), 0, "h1")
    b = Save.create(tmp_path / "h2.db", BUNDLE, seed=7)
    b.append(_hyp(b, player_confidence=0.5), 0, "h1")
    assert a.state_hash() != b.state_hash()                         # X41: the confidence is in the hash, as bp
    h = a.state_hash()
    a.close()
    assert Save.open(tmp_path / "h.db").state_hash() == h


def test_PI2_canonical_state_refuses_a_float_that_got_in_by_another_door(db):
    s = Save.open(db)
    bad = _replace(s.state, epistemic=s.state.epistemic.model_copy(update={"distortion_corrections": {"M::x": 0.5}}))
    with pytest.raises(ValueError, match="float"):                  # X42
        store.state_hash(bad)


@pytest.mark.parametrize("text", ["NaN", "Infinity", "-Infinity", "0.5"])
def test_PI2_a_non_finite_or_stray_number_in_a_stored_payload_is_a_refusal_not_a_crash(db, text):
    seq = sqlite3.connect(db).execute("SELECT MAX(seq) FROM session_events WHERE kind='ComposureChange'").fetchone()[0]
    sql(db, "UPDATE session_events SET payload=? WHERE seq=?", ('{"kind":"ComposureChange","new_composure_bp":%s}' % text, seq))
    with pytest.raises(SaveRefusal):
        Save.open(db)


def test_PI2_replay_reports_a_state_that_cannot_be_hashed_instead_of_crashing(db, capsys, monkeypatch):
    from eidolon.cli import main
    def boom(self):
        raise ValueError("float in authoritative state at x (I-17)")
    monkeypatch.setattr(Save, "state_hash", boom)
    assert main(["replay", str(db), "--verify"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and "float" in out["error"]


def test_PN8_newsave_with_a_missing_bundle_is_a_refusal_not_a_traceback(tmp_path):
    from eidolon.cli import main
    assert main(["newsave", str(tmp_path / "nope.json"), str(tmp_path / "x.db")]) == 1
    assert not (tmp_path / "x.db").exists()


# ------------------------------------------------------------------ PI-4 / PI-5: the append protocol
def test_PI4_an_append_computed_on_a_head_that_has_since_been_replaced_is_stale_even_at_the_same_seq(tmp_path):
    p = tmp_path / "aba.db"
    s = Save.create(p, BUNDLE, seed=7)
    for i in range(1, 7):
        s.append([TurnCommitted(turn=i)], s.last_seq, f"t{i}")
    s.close()
    a = Save.open(p, writable=True)                                  # session A is open at head seq 6
    def other_writer(rows):                                          # recovered to seq 4, then a different two-row turn
        return rows[:4] + [{"turn": 5, "kind": "TurnCommitted", "action_id": "z5", "payload": store._plain(TurnCommitted(turn=5))},
                           {"turn": 5, "kind": "LocationVisited", "action_id": "z5",
                            "payload": store._plain(LocationVisited(location="Study", turn=5))}]
    rechain(p, other_writer)
    assert sqlite3.connect(p).execute("SELECT value FROM meta WHERE key='head_seq'").fetchone()[0] == "6"
    with pytest.raises(StaleAppend):
        a.append([TurnCommitted(turn=7)], a.last_seq, "from-a")
    assert sqlite3.connect(p).execute("SELECT COUNT(*) FROM session_events").fetchone()[0] == 6
    Save.open(p)                                                     # and the file still loads


def test_PI5_a_duplicate_action_id_returns_the_turn_it_committed(tmp_path):
    s = Save.create(tmp_path / "d.db", BUNDLE, seed=7)
    go = run_goto_turn(s.state, "Study").events
    first = s.append(go, 0, "go-1")
    assert first.appended and first.ref == TurnRef(1, 1, 2)
    s.append([TurnCommitted(turn=2)], s.last_seq, "two")
    s.append([TurnCommitted(turn=3)], s.last_seq, "three")
    again = s.append(go, 0, "go-1")                                  # a client retrying a lost response, two turns later
    assert not again.appended and again.ref == TurnRef(1, 1, 2) and again.last_seq == 2 and again.same_events is True
    other = s.append([TurnCommitted(turn=1)], 0, "go-1")            # same id, DIFFERENT events: reported, not committed
    assert not other.appended and other.ref == TurnRef(1, 1, 2) and other.same_events is False
    assert s.last_seq == 4 and s.turn_for("two") == TurnRef(2, 3, 3) and s.turn_for("nope") is None
    s.close()
    assert Save.open(tmp_path / "d.db").turn_for("go-1") == TurnRef(1, 1, 2)


def test_X47_an_empty_or_non_string_action_id_writes_nothing(tmp_path):
    s = Save.create(tmp_path / "e.db", BUNDLE, seed=7)
    for bad in ("", None, 5):
        with pytest.raises(SaveRefusal, match="action_id"):
            s.append([TurnCommitted(turn=1)], 0, bad)
    assert s.append([TurnCommitted(turn=1)], 0, "ok").appended
    s.close()
    assert Save.open(tmp_path / "e.db").last_seq == 1


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_X30_an_event_that_would_not_survive_a_reload_is_refused_at_write_time(tmp_path):
    s = Save.create(tmp_path / "w.db", BUNDLE, seed=7)
    bad = Accusation.model_construct(kind="Accusation", turn=1, target="Elena", provisional=1)     # validates as True, dumps as 1
    with pytest.raises(SaveRefusal, match="round-trip"):
        s.append([TurnCommitted(turn=1), bad], 0, "bad")
    assert s.append([TurnCommitted(turn=1)], 0, "good").appended     # and the save is still usable
    s.close()
    assert Save.open(tmp_path / "w.db").last_seq == 1


# ------------------------------------------------------------------ load-side gaps the extended audit found (X35, X36, X39)
def test_X35_a_turns_row_column_must_equal_its_bracket(db):
    def shift_last_turn(rows):
        last = rows[-1]["turn"]
        for r in rows:
            if r["turn"] == last:
                r["turn"] = last + 1
        return rows
    rechain(db, shift_last_turn)
    with pytest.raises(SaveRefusal, match="row turn"):
        Save.open(db)


def test_X36_one_turn_one_action_id(db):
    def split_ids(rows):
        rows[-1]["action_id"] = "another-action"
        return rows
    rechain(db, split_ids)
    with pytest.raises(SaveRefusal, match="action_id"):
        Save.open(db)


def test_X39_a_read_only_open_never_repairs_a_hot_journal(db):
    """I-23. A crash mid-append leaves a hot journal. A READ-ONLY open must refuse and leave every byte alone; only a
    writable open may roll it back. (An open that quietly rolled back would also hide a torn write from the player.)"""
    code = ("import os, sqlite3, sys\n"
            "c = sqlite3.connect(sys.argv[1], isolation_level=None)\nc.execute('PRAGMA cache_size=10')\nc.execute('BEGIN')\n"
            "for i in range(3000): c.execute('INSERT INTO session_events VALUES (?,?,?,?,?,?,?)', "
            "(10000+i, 1, 'x', 'a', '{}' + ' ' * 80, 'p', 'h'))\n"
            "os._exit(0)\n")
    subprocess.run([sys.executable, "-c", code, str(db)], check=True, cwd=ROOT)
    journal = db.with_name(db.name + "-journal")
    assert journal.exists(), "the crash did not leave a hot journal; the test cannot see the property"
    before, jbefore = db.read_bytes(), journal.read_bytes()
    with pytest.raises(SaveRefusal):
        Save.open(db)
    assert db.read_bytes() == before and journal.read_bytes() == jbefore
    assert Save.open(db, writable=True).last_seq > 0               # the writable open DOES recover it


# ------------------------------------------------------------------ PB-1: recovery (§26.3 step 3) must not destroy verified data
def _rows(path):
    return sqlite3.connect(path).execute("SELECT seq, turn, kind, action_id, payload, prev_hash, hash FROM session_events ORDER BY seq").fetchall()


def _first_seq(path, turn):
    return sqlite3.connect(path).execute("SELECT MIN(seq) FROM session_events WHERE turn=?", (turn,)).fetchone()[0]


def _break(path, seq):
    sql(path, "UPDATE session_events SET payload=? WHERE seq=?", ('{"kind":"TurnCommitted","turn":1,"x":1}', seq))


def _flip_genesis(path):
    g = sqlite3.connect(path).execute("SELECT value FROM meta WHERE key='genesis'").fetchone()[0]
    sql(path, "UPDATE meta SET value=? WHERE key='genesis'", (("0" if g[0] != "0" else "1") + g[1:],))


def test_PB1_a_healthy_save_is_never_cut(db, built):
    before = db.read_bytes()
    plan = store.plan_truncation(db)
    assert plan.action == "none" and plan.rows_removed == 0 and plan.new_head_seq == plan.rows
    assert store.truncate_to_last_valid(db, confirm=True) == plan.rows
    assert db.read_bytes() == before and Save.open(db).state_hash() == built[1]


def test_PB1_a_damaged_genesis_record_costs_no_row(db, built):
    """F2: one hex digit of `meta.genesis` used to delete every one of 372 intact rows and still not load."""
    rows = _rows(db)
    _flip_genesis(db)
    with pytest.raises(SaveRefusal):
        Save.open(db)
    plan = store.plan_truncation(db)
    assert (plan.action, plan.rows_removed, plan.new_head_seq) == ("reset_meta", 0, len(rows))
    assert store.truncate_to_last_valid(db, confirm=True) == len(rows)
    assert _rows(db) == rows and Save.open(db).state_hash() == built[1]


def test_PB1_a_damaged_genesis_and_a_broken_chain_together_are_not_guessed_at(db):
    """With the genesis wrong AND the chain broken, cutting cannot tell which side to trust: report, delete nothing."""
    _flip_genesis(db)
    _break(db, 100)
    before = db.read_bytes()
    plan = store.plan_truncation(db)
    assert plan.action == "refuse" and plan.stage == "genesis" and plan.rows_removed == 0
    with pytest.raises(SaveRefusal):
        store.truncate_to_last_valid(db, confirm=True)
    assert db.read_bytes() == before


def test_PB1_a_head_record_that_is_off_by_one_is_reset_not_paid_for_with_a_turn(db, built):
    """F7: a lossless head reset existed; the old code cut a whole turn instead."""
    rows = _rows(db)
    sql(db, "UPDATE meta SET value=? WHERE key='head_seq'", (str(len(rows) + 1),))
    with pytest.raises(SaveRefusal):
        Save.open(db)
    assert store.truncate_to_last_valid(db, confirm=True) == len(rows)
    assert _rows(db) == rows and Save.open(db).state_hash() == built[1]


def test_PB1_a_damaged_seed_is_diagnosed_and_nothing_is_deleted(db):
    """F2b: the cause is in `meta`, so deleting rows cannot help — the old code cut a turn and still did not load."""
    sql(db, "UPDATE meta SET value='8' WHERE key='seed'")
    before = db.read_bytes()
    plan = store.plan_truncation(db)
    assert plan.action == "refuse" and plan.stage == "initial" and plan.rows_removed == 0
    with pytest.raises(SaveRefusal, match="initial world"):
        store.truncate_to_last_valid(db, confirm=True)
    assert db.read_bytes() == before


def test_PB1_a_chain_valid_row_the_fold_refuses_is_reported_and_never_cut(db):
    """F3: three confirmed calls used to eat three turns and the save still did not load."""
    def poison(rows):
        k = next(i for i, r in enumerate(rows) if r["kind"] == "PressureChange" and r["turn"] > 30)
        rows[k]["payload"]["secret_id"] = "S_nope"
        return rows
    rechain(db, poison)
    with pytest.raises(SaveRefusal):
        Save.open(db)
    before = db.read_bytes()
    assert store.plan_truncation(db).action == "refuse"
    for _ in range(3):
        with pytest.raises(SaveRefusal, match="does not own"):
            store.truncate_to_last_valid(db, confirm=True)
    assert db.read_bytes() == before


@pytest.mark.parametrize("damage", ["genesis-row-deleted", "missing-path", "nan-payload", "file-cut-short"])
def test_PB1_recovery_refuses_or_repairs_odd_damage_it_never_raises_anything_else(db, tmp_path, damage):
    """F4, F5, F6, F9 raised KeyError / OperationalError (and created a 0-byte file) / ValueError / DatabaseError."""
    if damage == "genesis-row-deleted":
        sql(db, "DELETE FROM meta WHERE key='genesis'")
    elif damage == "missing-path":
        db = tmp_path / "typo.db"
    elif damage == "nan-payload":
        sql(db, "UPDATE session_events SET payload=? WHERE seq=200", ('{"kind":"ComposureChange","new_composure_bp":NaN}',))
    else:
        db.write_bytes(db.read_bytes()[: int(db.stat().st_size * 0.8)])
    if damage == "nan-payload":
        cut = store.truncate_to_last_valid(db, confirm=True)
        assert cut < 200 and Save.open(db).last_seq == cut
        return
    if damage == "genesis-row-deleted":
        assert store.plan_truncation(db).action == "refuse"
        with pytest.raises(SaveRefusal):
            store.truncate_to_last_valid(db, confirm=True)
        return
    with pytest.raises(SaveRefusal):
        store.plan_truncation(db)
    if damage == "missing-path":
        assert not db.exists()


def test_PB1_a_break_between_turns_keeps_the_complete_turn_before_it(db):
    """F8: the old code dropped the last verified turn as well, complete or not."""
    first = _first_seq(db, 40)
    assert sqlite3.connect(db).execute("SELECT COUNT(*) FROM session_events WHERE turn=40").fetchone()[0] > 1
    _break(db, first)
    assert store.truncate_to_last_valid(db, confirm=True) == first - 1
    assert Save.open(db).state.turn_counter == 39


def test_PB1_a_break_inside_a_turn_drops_only_that_partial_turn(db):
    """F8b"""
    first = _first_seq(db, 40)
    _break(db, first + 1)
    assert store.truncate_to_last_valid(db, confirm=True) == first - 1
    assert Save.open(db).state.turn_counter == 39


def test_PB1_the_dry_run_writes_nothing_and_is_exactly_what_confirming_does(db):
    _break(db, 200)
    before = db.read_bytes()
    plan = store.plan_truncation(db)
    assert db.read_bytes() == before and plan.action == "cut" and 0 < plan.new_head_seq < 200
    assert plan.rows_removed == plan.rows - plan.new_head_seq and plan.turns_removed > 0
    with pytest.raises(ConfirmationRequired) as e:
        store.truncate_to_last_valid(db)
    assert e.value.plan == plan and db.read_bytes() == before         # F10: and it names what it would do
    assert store.truncate_to_last_valid(db, confirm=True) == plan.new_head_seq
    assert Save.open(db).last_seq == plan.new_head_seq


def test_PB1_a_repair_that_would_not_load_is_rolled_back(db):
    """The delete and the re-verification share one transaction: if the cut prefix does not LOAD, nothing is cut."""
    def poison(rows):
        k = next(i for i, r in enumerate(rows) if r["kind"] == "PressureChange" and 5 < r["turn"] < 20)
        rows[k]["payload"]["secret_id"] = "S_nope"                     # a fold-bad turn EARLY in the log
        return rows
    rechain(db, poison)
    _break(db, 300)                                                    # and a chain break LATER
    before = db.read_bytes()
    plan = store.plan_truncation(db)
    assert plan.action == "refuse" and "no cut leaves a loadable save" in plan.reason
    with pytest.raises(SaveRefusal):
        store.truncate_to_last_valid(db, confirm=True)
    assert db.read_bytes() == before


def test_PB1_recovery_without_confirm_is_a_SaveError_and_changes_nothing(db):
    _break(db, 50)
    before = db.read_bytes()
    with pytest.raises(SaveError):
        store.truncate_to_last_valid(db)
    assert db.read_bytes() == before


# ------------------------------------------------------------------ PI-3: the upcaster mechanism and the schema label
def test_PI3_an_older_save_opens_read_only_and_a_native_new_save_appends_and_reloads(db, built, tmp_path, monkeypatch):
    monkeypatch.setattr(store, "SCHEMA_VERSION", 2)
    monkeypatch.setattr(store, "UPCASTERS", {1: lambda kind, payload: payload})
    assert Save.open(db).state_hash() == built[1]                     # the v1 file READS under a v2 engine…
    with pytest.raises(SaveRefusal, match="read-only"):               # …but a write would put v2 spelling under a v1 label
        Save.open(db, writable=True)
    s = Save.create(tmp_path / "native.db", BUNDLE, seed=7)           # a NATIVE v2 save appends and reloads
    s.append([TurnCommitted(turn=1)], 0, "a")
    s.close()
    again = Save.open(tmp_path / "native.db", writable=True)
    assert again.append([TurnCommitted(turn=2)], again.last_seq, "b").appended
    again.close()
    assert Save.open(tmp_path / "native.db").last_seq == 2


def test_PI3_relabelling_the_schema_version_is_a_refusal(db, monkeypatch):
    monkeypatch.setattr(store, "SCHEMA_VERSION", 2)
    monkeypatch.setattr(store, "UPCASTERS", {1: lambda kind, payload: payload})
    sql(db, "UPDATE meta SET value='2' WHERE key='schema_version'")
    with pytest.raises(SaveRefusal, match="genesis"):
        Save.open(db)


def test_PN13_non_canonical_integers_in_meta_are_refused(db):
    for key, bad in (("schema_version", "01"), ("seed", " 7"), ("seed", "+7")):
        good = sqlite3.connect(db).execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()[0]
        sql(db, "UPDATE meta SET value=? WHERE key=?", (bad, key))
        with pytest.raises(SaveRefusal, match="canonical"):
            Save.open(db)
        sql(db, "UPDATE meta SET value=? WHERE key=?", (good, key))


def test_PN2_the_stored_payload_text_must_be_the_text_that_was_hashed(db):
    seq = sqlite3.connect(db).execute("SELECT MAX(seq) FROM session_events").fetchone()[0]
    text = sqlite3.connect(db).execute("SELECT payload FROM session_events WHERE seq=?", (seq,)).fetchone()[0]
    for variant in (json.dumps(json.loads(text)), text.replace("{", "{ ", 1)):     # same object, different bytes
        assert variant != text and json.loads(variant) == json.loads(text)
        sql(db, "UPDATE session_events SET payload=? WHERE seq=?", (variant, seq))
        with pytest.raises(SaveRefusal) as e:
            Save.open(db)
        assert e.value.seq == seq
        sql(db, "UPDATE session_events SET payload=? WHERE seq=?", (text, seq))


# ------------------------------------------------------------------ PI-6: the derived initial world is part of what the save is
def test_PI6_an_engine_that_derives_a_different_initial_world_refuses_the_save_instead_of_replaying_it(db, monkeypatch):
    import eidolon.solve.session as session
    orig = session.default_personality
    monkeypatch.setattr(session, "default_personality",
                        lambda a, seed: orig(a, seed).model_copy(update={"composure_base": 0.9}))   # an "engine upgrade"
    with pytest.raises(SaveRefusal, match="initial world") as e:
        Save.open(db)
    assert e.value.stage == "initial"


def test_PI6_meta_records_the_engine_and_the_digest_and_the_genesis_binds_the_digest(db):
    meta = dict(sqlite3.connect(db).execute("SELECT key, value FROM meta"))
    s = Save.open(db)
    from eidolon.solve.session import new_session
    assert meta["engine_version"] == store.ENGINE_VERSION
    assert meta["initial_digest"] == store.initial_digest(new_session(s.bundle, seed=7))
    sql(db, "UPDATE meta SET value=? WHERE key='initial_digest'", ("0" * 64,))
    with pytest.raises(SaveRefusal, match="initial world"):
        Save.open(db)
    assert store._genesis("c", 7, 1, "a") != store._genesis("c", 7, 1, "b") != store._genesis("c", 7, 2, "b")


def test_PI6_every_derived_store_moves_the_digest():
    from eidolon.minds.belief import BeliefStore
    from eidolon.minds.knowledge import KnowledgeStore
    from eidolon.solve.package import load_sealed_case
    from eidolon.solve.session import new_session
    st = new_session(load_sealed_case(str(BUNDLE)), seed=7)
    base = store.initial_digest(st)
    assert store.initial_digest(new_session(load_sealed_case(str(BUNDLE)), seed=7)) == base
    mems = {a: tuple(m.model_copy(update={"strength_0": (m.strength_0 + 1) % 10000}) for m in ms) for a, ms in st.memories.items()}
    pers = {a: c.model_copy(update={"personality": c.personality.model_copy(update={"guile": 0.123456})}) for a, c in st.characters.items()}
    some = st.knowledge.all()[0]
    for name, changed in (
            ("knowledge", _replace(st, knowledge=KnowledgeStore([e for e in st.knowledge.all() if e.id != some.id]))),
            ("beliefs", _replace(st, beliefs=BeliefStore([b for a in st.characters for b in st.beliefs.for_character(a)][1:]))),
            ("memories", _replace(st, memories=mems)),
            ("personalities", _replace(st, characters=pers)),
            ("initial composure", _replace(st, characters={a: c.model_copy(update={"composure": 1}) for a, c in st.characters.items()}))):
        assert store.initial_digest(changed) != base, name


# ------------------------------------------------------------------ PI-7: the declared solution is the proven one
def _resealed(update):
    from eidolon.solve.package import CasePackage
    doc = json.loads(BUNDLE.read_text(encoding="utf-8"))
    pkg = CasePackage.model_validate(doc["package"])
    forged = pkg.model_copy(update={"solution": pkg.solution.model_copy(update=update)}).sealed()
    doc["package"], doc["proof"]["package_seal"] = json.loads(forged.model_dump_json()), forged.seal
    doc["bundle_seal"] = bundle_seal(forged.seal, doc["proof"], doc["report"])
    return json.dumps(doc)


@pytest.mark.parametrize("update", [{"murderer": "Elena"}, {"location": "Hall"}, {"interval": (58, 60)}])
def test_PI7_a_declared_murderer_place_or_moment_the_proof_does_not_prove_is_refused(update, tmp_path):
    from eidolon.solve.package import load_sealed_text
    text = _resealed(update)
    with pytest.raises(_Seal, match="declared"):
        load_sealed_text(text)
    forged = tmp_path / "forged.json"
    forged.write_text(text, encoding="utf-8")
    with pytest.raises(_Seal):
        Save.create(tmp_path / "x.db", forged)
    assert not (tmp_path / "x.db").exists()


# ==================================================================================================================
# Phase 7 RE-REVIEW repairs (docs/EIDOLON-PHASE-7-RE-REVIEW.md): R-1, N-3, N-8.
# ==================================================================================================================
def test_X45_an_edited_prev_hash_column_is_refused_though_every_row_hash_still_verifies(db):
    """The `prev_hash` column is not hashed (each row's hash covers the RUNNING prev), so only the explicit comparison
    notices that the stored column was edited. The re-review loaded such a file when the comparison was removed."""
    sql(db, "UPDATE session_events SET prev_hash=? WHERE seq=6", ("0" * 64,))
    with pytest.raises(SaveRefusal, match="hash chain breaks") as e:
        Save.open(db)
    assert e.value.seq == 6 and e.value.stage == "chain"


def test_X46_the_genesis_binds_the_seed_even_when_nothing_derived_depends_on_it(db, monkeypatch):
    """With an engine whose derivation ignores the seed (C-3's planned flavour slot) the initial-state digest cannot
    notice a seed edit; only the genesis can. Re-seeding the file must be refused as a genesis mismatch."""
    real = store.new_session
    monkeypatch.setattr(store, "new_session", lambda bundle, seed=0: real(bundle, seed=7))
    sql(db, "UPDATE meta SET value='8' WHERE key='seed'")
    with pytest.raises(SaveRefusal, match="genesis") as e:
        Save.open(db)
    assert e.value.stage == "genesis"


def _crash_mid_append(db):
    code = ("import os, sqlite3, sys\n"
            "c = sqlite3.connect(sys.argv[1], isolation_level=None)\nc.execute('PRAGMA cache_size=10')\nc.execute('BEGIN')\n"
            "for i in range(3000): c.execute('INSERT INTO session_events VALUES (?,?,?,?,?,?,?)', "
            "(10000+i, 1, 'x', 'a', '{}' + ' ' * 80, 'p', 'h'))\n"
            "os._exit(0)\n")
    subprocess.run([sys.executable, "-c", code, str(db)], check=True, cwd=ROOT)
    journal = db.with_name(db.name + "-journal")
    assert journal.exists(), "the crash did not leave a hot journal; the test cannot see the property"
    return journal


def test_N3_the_dry_run_and_the_repair_never_roll_back_a_hot_journal(db):
    """N-3: `plan_truncation` opened the file read-write, so SQLite rolled a crashed append's journal back: the dry run
    WROTE the file and erased the crash evidence (X39). A hot journal is now refused unopened, by both entry points."""
    journal = _crash_mid_append(db)
    before, jbefore = db.read_bytes(), journal.read_bytes()
    plan = store.plan_truncation(db)
    assert plan.action == "refuse" and plan.stage == "journal" and "hot journal" in plan.reason
    with pytest.raises(SaveRefusal, match="hot journal"):
        store.truncate_to_last_valid(db, confirm=True)
    assert db.read_bytes() == before and journal.read_bytes() == jbefore and journal.exists()
    assert Save.open(db, writable=True).last_seq > 0                  # the writable open DOES recover it...
    assert store.plan_truncation(db).action in ("none", "cut", "reset_meta")   # ...and then recovery can be planned


def test_R1_a_genuine_hypothesis_and_overlay_turn_are_accepted_and_reload(forge_base, tmp_path):
    """The negative control for the nested-reference guards: real entities, held material, the addressee's own rows."""
    p = tmp_path / "f.db"
    shutil.copy(forge_base, p)
    s = Save.open(p, writable=True)
    k = s.state.knowledge.for_character("David")[0]
    held_statement = sorted(s.state.discovery.known_statements)[0]
    held_evidence = sorted(s.state.discovery.known_evidence)[0]
    hyp = [TurnCommitted(turn=_n(s)), HypothesisChanged(hypothesis=Hypothesis(
        id="H1", propositions=(k.proposition, Lied(actor="David", statement=held_statement), Planted(evidence=held_evidence)),
        support=(held_evidence,), player_confidence=0.5, created_turn=_n(s), updated_turn=_n(s)))]   # Phase 8: F-3
    assert s.append(hyp, s.last_seq, "hyp").appended
    mine = [_recall(s), MemoryCorrected(memory_id=_david_mem(s).id, field="interval", corrected_value=5, turn_id=_n(s)),
            _revised(s), _told_row(s, 0.3)]
    assert s.append(ask(s) + mine, s.last_seq, "mine").appended
    h = s.state_hash()
    s.close()
    assert Save.open(p).state_hash() == h


def test_P8_a_withdrawn_hypothesis_cannot_be_revised_at_append_or_at_load(forge_base, tmp_path):
    """Withdrawal is terminal (§16.1 board, Phase 8). The genuine create and withdraw are accepted; a revision after it is
    refused by `append`, and — re-chained past `append` — by `Save.open`."""
    p = tmp_path / "f.db"
    shutil.copy(forge_base, p)
    s = Save.open(p, writable=True)
    created = _hyp(s, player_confidence=0.5)
    assert s.append(created, s.last_seq, "h-create").appended
    h = s.state.decision.hypotheses[-1]
    assert s.append([TurnCommitted(turn=_n(s)), HypothesisChanged(hypothesis=h.model_copy(
        update={"status": "withdrawn", "updated_turn": _n(s)}))], s.last_seq, "h-withdraw").appended
    revived = [TurnCommitted(turn=_n(s)), HypothesisChanged(hypothesis=h.model_copy(update={"updated_turn": _n(s)}))]
    before = (s.state_hash(), s.last_seq)
    with pytest.raises(SaveRefusal, match="withdrawn"):
        s.append(revived, s.last_seq, "h-revive")
    assert (s.state_hash(), s.last_seq) == before
    s.close()
    inject(p, revived, "h-revive")
    with pytest.raises(SaveRefusal, match="withdrawn"):
        Save.open(p)


def test_P8_a_revision_cannot_rewrite_its_creation_turn_F3(forge_base, tmp_path):
    p = tmp_path / "f.db"
    shutil.copy(forge_base, p)
    s = Save.open(p, writable=True)
    assert s.append(_hyp(s, player_confidence=0.5), s.last_seq, "h-create").appended
    h = s.state.decision.hypotheses[-1]
    moved = [TurnCommitted(turn=_n(s)), HypothesisChanged(hypothesis=h.model_copy(update={"updated_turn": _n(s),
                                                                                           "created_turn": h.created_turn - 1}))]
    with pytest.raises(SaveRefusal, match="rewrites its creation turn"):
        s.append(moved, s.last_seq, "h-move")
    s.close()
    inject(p, moved, "h-move")
    with pytest.raises(SaveRefusal, match="rewrites its creation turn"):
        Save.open(p)


def test_P8_an_incidental_the_addressee_pinned_is_accepted_and_reloads(forge_base, tmp_path):
    """The negative control for the `R1_incidental_*` forgeries: §14.4's admissible incidental, by the addressee, in a
    conversation turn, is a turn the fold accepts (Phase 8 adds no producer for it; see the implementation report)."""
    p = tmp_path / "f.db"
    shutil.copy(forge_base, p)
    s = Save.open(p, writable=True)
    assert s.append(ask(s) + [IncidentalPinned(speaker="David", entity="port", attr="vintage", value="1927")],
                    s.last_seq, "pin").appended
    h = s.state_hash()
    s.close()
    assert Save.open(p).state_hash() == h


def test_P8_a_contradiction_id_made_of_held_material_is_still_refused_F9(fsave):
    """`contradictions_caught` has no producer in any phase (§9 names the field, nothing writes or reads it), so NO id is
    legitimate: an id spelled from two items the player really holds is refused like `"bogus"` is. That is what closes F-9
    (reorder/removal needs a held id, and none can ever be held)."""
    a, b = sorted(fsave.state.discovery.known_evidence)[:2]
    before = (fsave.state_hash(), fsave.last_seq)
    with pytest.raises(SaveRefusal, match="contradictions_caught"):
        fsave.append(ask(fsave) + [CoverStateDelta(contradictions_caught=(f"{a}~{b}",))], fsave.last_seq, "f9")
    assert (fsave.state_hash(), fsave.last_seq) == before


@pytest.mark.parametrize("name", ["study_party_s4", "study_party_s5", "manor_wing_s4", "manor_wing_s6"])
def test_R1_the_nested_guards_never_refuse_a_turn_the_engine_really_produces(name, tmp_path):
    """The re-review's sweep, scaled down: every living character of each generated case, asked with and without every
    held item presented (hostile / provisional features on), every turn appended through the store. A store refusal here is
    a FALSE refusal. The live state must equal the folded one after every turn, and a reload must equal both."""
    s = Save.create(tmp_path / "s.db", ROOT / "cases" / "generated" / f"{name}.json", seed=7)
    n = 0

    def put(res):
        nonlocal n
        if res.rejected:
            return
        n += 1
        s.append(res.events, s.last_seq, f"sweep-{n}")
        assert store.state_hash(res.state) == s.state_hash()
    for ev in s.state.evidence.all():
        if (go := run_goto_turn(s.state, ev.discovery.at)) and not go.rejected:
            put(go)
        put(run_search_turn(s.state, ev.discovery.at, ev.discovery.action))
    for who in s.state.case.living_actors():
        held = sorted(s.state.discovery.known_evidence | s.state.discovery.known_statements)
        for i, ref in enumerate([None, *held[:10]]):
            put(run_ask_turn(s.state, who, Query(kind="challenge" if ref else TOPICS_KINDS[i % 4], predicate_hint=TOPICS[i % 4], raw=f"q{i}"),
                             presented_ref=ref, hostile_tone=i % 7 == 0, provisional_accusation=i % 11 == 0))
    assert n > 40
    h = s.state_hash()
    s.close()
    assert Save.open(tmp_path / "s.db").state_hash() == h


TOPICS_KINDS = ("did_you", "where", "meta", "coercion")


def test_F1_the_clock_is_inclusive_at_both_ends_and_the_character_stays_playable(tmp_path):
    """The negative control for F-1: the whole clock `[0, t_investigation]` is legal (a bound off by one would false-refuse real
    claims — David's authored layer-0 claims end exactly AT `t_investigation`, so `drive` itself trips such a bound), and a character
    who made the widest legal claim can still be asked — nothing poisons the next turn. Self-contained (no module fixture) so a
    too-tight bound shows up as a failing test, not a fixture error."""
    p = tmp_path / "f.db"
    s = Save.create(p, BUNDLE, seed=7)
    drive(s, 6)
    H = s.state.case.t_investigation
    weapon = sorted(s.state.case.objects)[0]
    # the widest legal claim, consistent with what David has already said (his own deed denial over the whole clock) - an
    # At(Study, [0, H]) here would contradict the whereabouts lie his cover now tells (NR-I4) and poison the ledger itself
    widest = restate(ask(s), claims=(_own_claim(s, proposition=DidNot(actor="David", action="touch", object=weapon,
                                                                     interval=(0, H))),), accounts=())
    assert s.append(widest, s.last_seq, "widest").appended
    hyp = [TurnCommitted(turn=_n(s)), HypothesisChanged(hypothesis=Hypothesis(id="H1", propositions=(
        Moved(actor="David", from_loc="Study", to_loc="Study", t=0), Moved(actor="David", from_loc="Study", to_loc="Study", t=H),
        Said(speaker="David", listener="Elena", t=H, proposition=At(actor="David", location="Study", interval=(H - 1, H)))),
        player_confidence=0.5, created_turn=_n(s), updated_turn=_n(s)))]          # Phase 8: F-3
    assert s.append(hyp, s.last_seq, "edges").appended
    res = run_ask_turn(s.state, "David", Query(kind="where", predicate_hint="where", raw="again"))
    assert not res.rejected, res.violations
    h = s.state_hash()
    s.close()
    assert Save.open(p).state_hash() == h
