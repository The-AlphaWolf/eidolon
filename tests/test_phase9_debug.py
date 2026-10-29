"""Phase 9 - §27.2 the debug server (separate process, separate port, `EIDOLON_DEBUG=1`), I-10, and the debug CLI."""
from __future__ import annotations

import ast
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from eidolon import game, trace, web
from eidolon.debug import app as dbg
from eidolon.llm.fakes import ScriptedTransport
from eidolon.llm.render import LLMRenderer, ModelLLM
from eidolon.store import Save
from tests.llm.llm_helpers import approve, faithful

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "cases" / "generated"
LOCAL = "http://127.0.0.1:8001"
ENV = {"EIDOLON_DEBUG": "1"}
VIEWS = ["turns", "turn/3", "characters", "character/David", "world", "world?t=30", "evidence", "validator", "failures", "ledger",
         "slo", "audit", "replay"]


@pytest.fixture(scope="module")
def saves(tmp_path_factory):
    d = tmp_path_factory.mktemp("dbg")
    p = d / "g1.db"
    Save.create(p, CASES / "study_party_s4.json", seed=7).close()
    s = Save.open(p, writable=True)
    step = lambda c, *a, **k: c(s, f"{c.__name__}@{s.last_seq}", s.last_seq, *a, **k)            # noqa: E731
    t = ScriptedTransport(generate=[faithful(1)], verify=[approve], repeat_last=True)
    ren = LLMRenderer(ModelLLM(t))
    step(game.goto, "Study")
    for who in sorted(s.state.case.living_actors()):
        step(game.ask, who, game.question(s.state.case, who, topic="presence", place="Study", bucket=1), renderer=ren)
    step(game.ask, "David", game.question(s.state.case, "David", topic="did"), accuse=True, renderer=ren)
    step(game.ask, "Elena", game.question(s.state.case, "Elena"), present="e" + "0" * 12)           # rejected: an aborted attempt
    s.close()
    return d


@pytest.fixture
def client(saves):
    with TestClient(dbg.create_debug_app(saves, env=ENV), base_url=LOCAL) as c:
        yield c


# ====================================================================== off unless asked; on its own port
def test_the_debug_server_does_not_start_unless_asked(saves):
    with pytest.raises(dbg.DebugDisabled):
        dbg.create_debug_app(saves, env={})
    with pytest.raises(dbg.DebugDisabled):
        dbg.create_debug_app(saves, env={"EIDOLON_DEBUG": "0"})


def test_the_debug_cli_refuses_without_the_flag_and_never_takes_the_players_port(saves):
    env = {k: v for k, v in __import__("os").environ.items() if k != "EIDOLON_DEBUG"}
    r = subprocess.run([sys.executable, "-m", "eidolon.debug", "slo", str(saves / "g1.db")], capture_output=True, text=True, cwd=ROOT, env=env)
    assert r.returncode == 2 and "EIDOLON_DEBUG=1" in r.stderr
    r = subprocess.run([sys.executable, "-m", "eidolon.debug", "serve", "--saves", str(saves), "--port", "8000"], capture_output=True,
                       text=True, cwd=ROOT, env={**env, "EIDOLON_DEBUG": "1"})
    assert r.returncode == 2 and "player's port" in r.stderr
    assert dbg.DEFAULT_PORT != dbg.PLAYER_PORT


# ====================================================================== every view renders; none writes
@pytest.mark.parametrize("view", VIEWS)
def test_every_view_renders(client, view):
    r = client.get(f"/g/g1/{view}")
    assert r.status_code == 200, r.text[:300]
    assert "<h1>" in r.text and "debug - engine truth" in r.text


def test_the_index_lists_saves_and_not_trace_files(client):
    text = client.get("/").text
    assert "g1" in text and "traces" not in text


def test_the_turn_inspector_shows_the_stages_the_state_diff_and_resolves_handles_against_the_sealed_case(client, saves):
    page = client.get("/g/g1/turn/3").text
    s = Save.open(saves / "g1.db")
    secret_id = next(sec.id for sec in s.state.secrets.all() if sec.kind == "murder")
    assert "State before" in page and "candidates" in page and "llm_calls" in page
    t3 = json.loads(dict(s.trace_rows())[3])
    assert "David" in page or "Elena" in page or "Margaret" in page
    # a handle in the trace is shown as the id it stands for: the debug process holds the key, the trace file does not
    table = trace.resolver(s)
    handle = next(h for h in re.findall(r'"[0-9a-f]{12}"', json.dumps(t3)) if h.strip('"') in table)
    assert table[handle.strip('"')] in page and "engine id" not in page
    assert secret_id not in dict(s.trace_rows())[3]


def test_the_turn_inspector_says_when_there_is_no_trace_for_a_turn(client, saves):
    assert client.get("/g/g1/turn/9999").status_code == 404
    assert "gap" in client.get("/g/g1/turn/9999").text.lower()


def test_failures_ledger_slo_audit_and_replay_say_what_they_are_for(client):
    assert "rejected" in client.get("/g/g1/failures").text and "rejected_action" in client.get("/g/g1/failures").text
    led = client.get("/g/g1/ledger").text
    assert "generate" in led and "verify" in led and "n/a" in led and "price table" in led
    assert "UNMEASURED" in client.get("/g/g1/slo").text and "peels_without_any_presented_breaker" in client.get("/g/g1/slo").text
    assert "detector, not a guarantee" in client.get("/g/g1/audit").text.lower()
    rep = html.unescape(client.get("/g/g1/replay").text)
    assert '"equal": true' in rep and "traces_bound_to_this_log" in rep


def test_the_character_world_evidence_and_validator_inspectors_show_hidden_truth(client, saves):
    s = Save.open(saves / "g1.db")
    murder = next(sec for sec in s.state.secrets.all() if sec.kind == "murder")
    assert murder.id in client.get(f"/g/g1/character/{murder.owner}").text and "breaker_sets" in client.get(f"/g/g1/character/{murder.owner}").text
    assert "world_at(30)" in client.get("/g/g1/world?t=30").text and "Timeline" in client.get("/g/g1/world").text
    ev = client.get("/g/g1/evidence").text
    assert all(e.id in ev for e in s.state.evidence.all())
    page = html.unescape(client.get("/g/g1/validator").text)
    assert '"V-3"' in page and '"proof_core"' in page and '"metrics"' in page, "the sealed REPORT: every stage's verdict and the proof's size"
    assert "independently when this save was opened" in page
    sealed = Save.open(saves / "g1.db").bundle
    assert not any(e in page for e in sealed.proof["proof_core"]), "the raw proof's contents are not read by the debug server (I-58)"


def test_the_scrubber_clamps_t_to_the_clock(client):
    assert client.get("/g/g1/world?t=99999").status_code == 200 and client.get("/g/g1/world?t=-5").status_code == 200


# ====================================================================== read-only, loopback, GET-only
def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_visiting_every_view_changes_no_byte_of_the_save_or_its_traces(client, saves):
    before = (digest(saves / "g1.db"), digest(saves / "g1.traces.db"))
    for v in VIEWS:
        assert client.get(f"/g/g1/{v}").status_code == 200
    assert (digest(saves / "g1.db"), digest(saves / "g1.traces.db")) == before


@pytest.mark.parametrize("method", ["post", "put", "delete", "patch"])
def test_nothing_but_get_is_routed(client, method):
    for path in ("/", "/g/g1/turns", "/g/g1/audit", "/g/g1/replay", "/g/g1/turn/1"):
        assert getattr(client, method)(path).status_code == 405


def test_only_the_loopback_names_on_the_served_port_are_answered(saves):
    app = dbg.create_debug_app(saves, port=8001, env=ENV)
    assert TestClient(app, base_url="http://127.0.0.1:8001").get("/").status_code == 200
    for host in ("127.0.0.1:8000", "evil.example", "127.0.0.1:8001.evil.example", "localhost.evil.example:8001", ""):
        assert TestClient(app, base_url=LOCAL).get("/", headers={"host": host}).status_code == 400, host


def test_a_tampered_save_is_refused_on_the_page_and_a_hostile_name_is_not_found(client, saves, tmp_path):
    shutil.copy(saves / "g1.db", saves / "bad.db")
    import contextlib
    import sqlite3
    with contextlib.closing(sqlite3.connect(saves / "bad.db")) as c, c:
        c.execute("UPDATE session_events SET payload = replace(payload, 'Study', 'Hall')")
    r = client.get("/g/bad/turns")
    assert r.status_code == 409
    for name in ("nope", "..", "a%2Fb", "x" * 80, "g1.traces", "g1.db"):                     # the trace file and the file itself are not game names
        assert client.get(f"/g/{name}/turns").status_code == 404
    (saves / "bad.db").unlink()


def test_a_foreign_trace_file_is_detected_not_trusted(saves, tmp_path):
    d = tmp_path / "s"
    d.mkdir()
    shutil.copy(saves / "g1.db", d / "g1.db")
    other = d / "other.db"
    Save.create(other, CASES / "manor_wing_s4.json", seed=7).close()
    o = Save.open(other, writable=True)
    game.goto(o, "a", 0, sorted(o.state.case.locations)[0])
    o.close()
    shutil.copy(d / "other.traces.db", d / "g1.traces.db")                  # the PN-7 hazard: a stale/foreign trace file at the same name
    with TestClient(dbg.create_debug_app(d, env=ENV), base_url=LOCAL) as c:
        rep = html.unescape(c.get("/g/g1/replay").text)
    assert '"traces_foreign_or_stale": 1' in rep and '"traces_bound_to_this_log": 0' in rep


# ====================================================================== I-10
def test_nothing_outside_the_debug_package_refers_to_it():
    """The player-facing process imports `web`, `game`, `cli`, `store`... If none of them even names `eidolon.debug`, no import
    path - static, lazy or conditional - can load it."""
    offenders = []
    for p in (ROOT / "eidolon").rglob("*.py"):
        if "debug" in p.relative_to(ROOT / "eidolon").parts[:1]:
            continue
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            mods = [n.module or ""] if isinstance(n, ast.ImportFrom) else [a.name for a in n.names] if isinstance(n, ast.Import) else []
            if any(m == "debug" or m.startswith("debug.") or ".debug" in m or "eidolon.debug" in m for m in mods) or \
                    (isinstance(n, ast.ImportFrom) and n.level and any(a.name == "debug" for a in n.names)):
                offenders.append(str(p))
    assert not offenders, offenders


def test_importing_the_whole_player_stack_does_not_load_the_debug_package():
    code = ("import sys, tempfile, pathlib\n"
            "import eidolon.web, eidolon.game, eidolon.cli, eidolon.store, eidolon.trace, eidolon.llm.render, eidolon.llm.provider\n"
            "d = pathlib.Path(tempfile.mkdtemp()); eidolon.web.create_app(d, d)\n"
            "bad = sorted(m for m in sys.modules if m == 'eidolon.debug' or m.startswith('eidolon.debug.'))\n"
            "assert not bad, bad\nprint('ok')")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stderr


@pytest.mark.parametrize("path", ["/debug", "/debug/turns", "/g/g1/turns", "/g/g1/turn/1", "/g/g1/slo", "/g/g1/audit", "/g/g1/replay",
                                  "/g/g1/ledger", "/g/g1/failures", "/g/g1/characters", "/g/g1/world", "/g/g1/evidence", "/g/g1/validator"])
def test_http_probe_the_player_app_serves_none_of_the_debug_views(saves, path):
    with TestClient(web.create_app(saves, CASES, port=8000), base_url="http://127.0.0.1:8000") as c:
        got = c.get(path)
        assert got.status_code == 404, (path, got.status_code)


def test_the_player_page_of_a_traced_game_carries_no_trace_data(saves):
    with TestClient(web.create_app(saves, CASES, port=8000), base_url="http://127.0.0.1:8000") as c:
        page = c.get("/g/g1").text
    s = Save.open(saves / "g1.db")
    held = s.state.discovery.known_statements                       # a heard statement's id IS the player's ref to it (Phase 8)
    for token in trace.engine_ids(s.state) - held:
        assert not re.search(rf"(?<![\w@]){re.escape(token)}(?![\w@])", page), token
    for _, row in s.trace_rows():
        for h in re.findall(r'"([0-9a-f]{12})"', row):
            assert h not in page


# ====================================================================== the debug CLI
def run_cli(*args, env=None):
    return subprocess.run([sys.executable, "-m", "eidolon.debug", *args], capture_output=True, text=True, cwd=ROOT,
                          env={**__import__("os").environ, "EIDOLON_DEBUG": "1", **(env or {})})


def test_cli_trace_resolves_handles_and_reports_a_gap(saves):
    ok = run_cli("trace", str(saves / "g1.db"), "--turn", "3")
    assert ok.returncode == 0
    doc = json.loads(ok.stdout)
    assert doc["turn_id"] == 3 and doc["committed"]["head_hash"]
    s = Save.open(saves / "g1.db")
    assert any(sec.id in ok.stdout for sec in s.state.secrets.all() if sec.owner in ("David", "Elena", "Margaret")) or "kind" in doc
    gap = run_cli("trace", str(saves / "g1.db"), "--turn", "999")
    assert gap.returncode == 1 and "gap" in gap.stderr


def test_cli_slo_exits_nonzero_only_on_a_failed_slo(saves, tmp_path):
    ok = run_cli("slo", str(saves / "g1.db"))
    assert ok.returncode == 0 and "UNMEASURED" in ok.stdout
    j = run_cli("slo", str(saves / "g1.db"), "--json")
    assert any(m["name"] == "fallback_rate_bp" for m in json.loads(j.stdout))


def test_cli_audit_summarises_and_writes_fixtures_only_when_asked(saves, tmp_path):
    r = run_cli("audit", str(saves / "g1.db"), "--out", str(tmp_path / "fx"))
    out = json.loads(r.stdout)
    assert r.returncode == 0 and out["discrepancies"] == 0 and out["status"] == "UNMEASURED"       # few statements: bound not judged
    assert not (tmp_path / "fx").exists()                                                          # nothing to file, nothing written
