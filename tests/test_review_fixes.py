"""Guards for the fixes made after `docs/EIDOLON-FULL-REVIEW-2026-10-22.md` (web, CLI, provider, trace, debug, nightly). Each test
names the finding it guards; do not weaken one to make a change pass."""
from __future__ import annotations

import http.server
import json
import re
import sqlite3
import threading
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from eidolon import game
from eidolon.llm.provider import ProviderError
from eidolon.store import Save
from eidolon.web import create_app

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "cases" / "generated"
CASE = CASES / "study_party_s4.json"


@pytest.fixture
def app_client(tmp_path):
    with TestClient(create_app(tmp_path, CASES, port=8000), base_url="http://127.0.0.1:8000") as c:
        c.post("/new", data={"name": "g", "case": "study_party_s4", "seed": "0"})
        yield c, tmp_path


def seq(c) -> str:
    return re.search(r'name="expected_seq" value="(\d+)"', c.get("/g/g").text).group(1)


def last_action(page: str) -> str:
    m = re.search(r"<h2>Last action</h2>(.*?)</section>", page, re.S)
    return re.sub(r"\s+", " ", re.sub("<[^>]+>", " ", m.group(1))).strip()


# ------------------------------------------------------------------ web boundary
def test_H8_N5_no_page_can_be_framed_by_another_site(app_client):
    c, _ = app_client
    for path in ("/", "/g/g"):
        r = c.get(path)
        assert r.headers["x-frame-options"] == "DENY" and "frame-ancestors 'none'" in r.headers["content-security-policy"]


def test_H8_N4_a_file_part_where_a_string_belongs_is_refused_not_a_500(app_client):
    """A form refusal, not an engine fault: without the guard a file part in `expected_seq` reaches `int()` and becomes the
    "something went wrong on our side" notice (and an aborted trace row)."""
    c, _ = app_client
    for data, files in (({"op": "goto", "action_id": "f@0", "expected_seq": seq(c)}, {"location": ("x.txt", b"Hall")}),
                        ({"op": "goto", "action_id": "f@1", "location": "Hall"}, {"expected_seq": ("x.txt", b"0")})):
        r = c.post("/g/g", data=data, files=files)
        said = last_action(r.text)
        assert r.status_code == 200 and "Nothing was recorded" in said and "on our side" not in said, said


@pytest.mark.parametrize("seed,ok", [("-5", False), (str(2 ** 31), False), (str(10 ** 30), False), ("5", True)])
def test_NR_N4_the_seed_is_a_non_negative_31_bit_integer(app_client, seed, ok):
    c, _ = app_client
    r = c.post("/new", data={"name": f"s{len(seed)}{seed[0]}", "case": "study_party_s4", "seed": seed}, follow_redirects=False)
    assert (r.status_code == 303) is ok, (seed, r.status_code)


def test_NR_N1_a_window_past_the_end_of_the_investigation_is_refused_with_its_reason(app_client):
    c, _ = app_client
    r = c.post("/g/g", data={"op": "hypothesize", "action_id": "h@0", "expected_seq": seq(c), "kind": "At", "actor": "David",
                             "location": "Hall", "start": "00:00", "end": "02:30", "confidence": "50"})
    assert "must run forwards and end by 02:00" in last_action(r.text)
    assert "02:00–02:30" not in r.text, "the question form offers no half hour that starts when the investigation ends"


def test_NR_N2_a_model_that_does_not_answer_is_reported_as_busy_not_as_a_broken_game(tmp_path):
    s = Save.create(tmp_path / "g.db", CASE, seed=0)
    try:
        def down(req):
            raise ProviderError("APIStatusError")
        from eidolon.decision.query import Query
        from eidolon.llm.render import LLMRenderer, ModelLLM

        class Down:
            def complete(self, req):
                raise ProviderError("HTTP 503: high demand")
        out = game.ask(s, "a@0", s.last_seq, "David", Query(kind="where", raw="Where were you?"),
                       renderer=LLMRenderer(ModelLLM(Down())))
        assert out.status == "rejected" and out.message == game.BUSY
    finally:
        s.close()


def test_H9_N4_an_engine_exception_is_a_retry_notice_not_a_500(app_client, monkeypatch):
    c, d = app_client

    def boom(*a, **k):
        raise RuntimeError("SECRET engine detail")
    monkeypatch.setattr(game, "run_goto_turn", boom)
    r = c.post("/g/g", data={"op": "goto", "location": "Hall", "action_id": "go@0", "expected_seq": seq(c)})
    assert r.status_code == 200 and "please try again" in last_action(r.text) and "SECRET" not in r.text
    rows = sqlite3.connect(d / "g.traces.db").execute("select trace from aborted").fetchall()
    assert rows, "the failed attempt is noted in the aborted table"


def test_H8_N8_items_keep_their_numbers_and_a_resent_form_shows_what_was_said(tmp_path):
    s = Save.create(tmp_path / "g.db", CASE, seed=0)
    try:
        evs = sorted(s.state.evidence.all(), key=lambda e: e.id)
        step = lambda c, *a, **k: c(s, f"{c.__name__}@{s.last_seq}", s.last_seq, *a, **k)      # noqa: E731
        found = []
        for ev in evs:
            if step(game.search, ev.discovery.at, ev.discovery.action).ok and len(s.state.discovery.known_evidence) > len(found):
                found = [e for e in s.discovery_order()]
                labels = game._labels(s)
                assert labels[found[0]].startswith("item 1:"), "the first item found stays item 1"
        assert len(found) >= 2
        from eidolon.decision.query import Query
        first = game.ask(s, "ask-once", s.last_seq, "Elena", Query(kind="where", raw="Where were you?"))
        again = game.ask(s, "ask-once", s.last_seq - 99, "Elena", Query(kind="where", raw="Where were you?"))
        assert first.ok and again.status == "duplicate" and again.reply == first.reply
    finally:
        s.close()


def test_H8_N8_a_window_as_wide_as_the_evening_does_not_establish_the_time(tmp_path):
    """The report's place-and-time axis: the right room and a window round the blow earns it; the right room and "some time
    this evening" does not, though that window overlaps the blow too."""
    for n, wide in enumerate((False, True)):
        s = Save.create(tmp_path / f"w{n}.db", CASE, seed=0)
        try:
            attack = next(e for e in s.state.case.events if e.kind == "Attack")
            window = (0, s.state.case.t_investigation) if wide else (attack.interval[0] - 15, attack.interval[0] + 15)
            assert game.accuse(s, "acc", s.last_seq, s.state.murderer, location=attack.location, interval=window).ok
            assert game.report(s)["axes"]["place_and_time"] is (not wide), window
        finally:
            s.close()


def test_NR_N3_every_save_touch_runs_on_one_worker_thread(app_client, monkeypatch):
    c, _ = app_client
    threads = set()
    real = game.notebook

    def spy(save):
        threads.add(threading.current_thread().name)
        return real(save)
    monkeypatch.setattr(game, "notebook", spy)
    for _ in range(3):
        c.get("/g/g")
    assert len(threads) == 1 and next(iter(threads)).startswith("eidolon-game")


def test_H8_N7_the_notebook_is_built_once_per_log_head(tmp_path):
    s = Save.create(tmp_path / "g.db", CASE, seed=0)
    try:
        a, b = game.notebook(s), game.notebook(s)
        assert a is b
        ev = sorted(s.state.evidence.all(), key=lambda e: e.id)[0]
        game.search(s, "x@0", s.last_seq, ev.discovery.at, ev.discovery.action)
        assert game.notebook(s) is not a
    finally:
        s.close()


# ------------------------------------------------------------------ store
def test_H9_N2_a_new_game_never_adopts_the_trace_file_of_an_older_game_of_that_name(tmp_path):
    stale = tmp_path / "g.traces.db"
    stale.write_bytes(b"old rows")
    Save.create(tmp_path / "g.db", CASE, seed=0).close()
    assert not stale.exists() or stale.read_bytes() != b"old rows"
    assert (tmp_path / "g.traces.db.stale-1").read_bytes() == b"old rows"


# ------------------------------------------------------------------ CLI
def test_NR_N5_cli_newsave_refuses_instead_of_raising(tmp_path, capsys):
    from eidolon import cli
    assert cli.main(["newsave", str(CASE), str(tmp_path / "missing" / "x.db")]) == 1
    assert "refused" in capsys.readouterr().out
    assert cli.main(["newsave", str(CASE), str(tmp_path / "y.db"), "--seed", "-1"]) == 1


# ------------------------------------------------------------------ provider
class _Redirect(http.server.BaseHTTPRequestHandler):
    seen_auth: list = []

    def do_POST(self):                         # 302: urllib would follow a POST with a GET that keeps Authorization
        _Redirect.seen_auth.append(self.headers.get("Authorization"))
        self.send_response(302)
        self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/elsewhere")
        self.end_headers()

    def do_GET(self):
        _Redirect.seen_auth.append(self.headers.get("Authorization"))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *a):
        pass


def test_NR_N6_a_redirect_is_never_followed_so_the_key_is_sent_once(tmp_path):
    from eidolon.llm import provider
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Redirect)
    threading.Thread(target=lambda: [srv.handle_request() for _ in range(2)], daemon=True).start()
    try:
        with pytest.raises(ProviderError):
            provider._http_post(f"http://127.0.0.1:{srv.server_port}/v1/chat/completions", {"x": 1},
                                {"Authorization": "Bearer K"}, 5.0)
        assert _Redirect.seen_auth == ["Bearer K"]
    finally:
        srv.server_close()


# ------------------------------------------------------------------ parser, trace, debug, nightly
def test_NR_N7_pm_is_afternoon():
    from eidolon.llm.ingress import clock_interval
    assert clock_interval("1pm", 150) is None and clock_interval("1am", 150) == (60, 90)


def test_H9_N1_a_prompt_leak_is_traced_as_a_prompt_leak():
    from types import SimpleNamespace
    from eidolon.trace import failures_of
    audit = SimpleNamespace(calls=(SimpleNamespace(error="PROMPT_LEAK"),), attempts=(), reason="", outcome="rejected")
    assert "prompt_leak" in failures_of(audit) and "provider_error" not in failures_of(audit)


def test_H9_N9_the_nightly_addresses_the_cases_own_cast(tmp_path):
    from eidolon.debug import nightly
    asked = []

    class Spy(nightly.DryTransport):
        def complete(self, req):
            if req.role == "parse":
                asked.append(json.loads(req.user)["addressee"])
            return super().complete(req)
    nightly.run(tmp_path, transport=Spy(), case="manor_wing_s4", turns=4, audit_sample=4, corpus_turns_n=2, run_suites=False)
    assert asked and "David" not in asked


# ------------------------------------------------------------------ dead code
def test_NR_N11_no_unused_import_or_local_in_the_engine_or_its_tests():
    api = pytest.importorskip("pyflakes.api")
    import io
    from pyflakes.reporter import Reporter
    out = io.StringIO()
    assert api.checkRecursive([str(ROOT / d) for d in ("eidolon", "tests", "spike")], Reporter(out, out)) == 0, out.getvalue()
