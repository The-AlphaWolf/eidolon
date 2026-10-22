"""The debug server (§27.2): a SEPARATE process on its own port that shows what the player is never shown - the trace of every
turn, the hidden state, the case the player is solving - and changes nothing.

* **Off unless asked**: `create_debug_app` refuses (`DebugDisabled`) unless `EIDOLON_DEBUG=1`. `python -m eidolon.debug serve`
  binds 127.0.0.1 only, and refuses the player app's port.
* **Read-only**: GET routes only (anything else is 405); a save is opened read-only and verified end to end, a trace file
  through a `mode=ro` handle; the audit page computes and writes nothing.
* **Same host rule as the player app**: `Host` is judged against the loopback names on the port served (DNS rebinding, H8-I2).
* The views: Turn inspector (stage by stage, with the state before and after), Character inspector, World inspector (a timeline
  scrubber over `world_at(t)`), Evidence inspector, Validator report, Failures, LLM ledger, SLOs, Offline audit, Replay.

Trace handles are resolved here and only here: the trace file holds opaque digests, and this process holds the sealed case that
turns them back into ids (`trace.resolver`).
"""
from __future__ import annotations

import contextlib
import json
import os
import sqlite3
from pathlib import Path

import jinja2
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.routing import Route

from .. import store, trace as trace_mod
from ..decision.peel import layer_index
from ..store import Save, SaveRefusal
from ..web import NAME, _LoopbackOnly, allowed_hosts
from ..world.state import world_at
from . import audit, replay, slo

DEFAULT_PORT = 8001
PLAYER_PORT = 8000


class DebugDisabled(RuntimeError):
    """`EIDOLON_DEBUG=1` is not set: the debug server does not start by accident."""


_BASE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{{ title }} - Eidolon debug</title>
<style>body{font:14px/1.45 system-ui,sans-serif;margin:1rem 2rem;background:#fff;color:#111}table{border-collapse:collapse;margin:.5rem 0}
td,th{border:1px solid #888;padding:.15rem .5rem;text-align:left;vertical-align:top}pre{background:#f4f4f4;padding:.5rem;overflow:auto}
nav a{margin-right:1rem}.UNMEASURED{background:#fde}.FAIL{background:#fbb}.PASS{background:#dfd}h1{font-size:1.2rem}</style></head><body>
<h1>{{ title }} <small>(debug - engine truth, not for players)</small></h1>
{% if name %}<nav><a href="/">saves</a><a href="/g/{{ name }}/turns">turns</a><a href="/g/{{ name }}/characters">characters</a>
<a href="/g/{{ name }}/world">world</a><a href="/g/{{ name }}/evidence">evidence</a><a href="/g/{{ name }}/validator">validator</a>
<a href="/g/{{ name }}/failures">failures</a><a href="/g/{{ name }}/ledger">llm ledger</a><a href="/g/{{ name }}/slo">slo</a>
<a href="/g/{{ name }}/audit">audit</a><a href="/g/{{ name }}/replay">replay</a></nav>{% endif %}
{% for block in blocks %}{% if block.heading %}<h2>{{ block.heading }}</h2>{% endif %}
{% if block.table is defined %}<table><thead><tr>{% for c in block.table[0] %}<th>{{ c }}</th>{% endfor %}</tr></thead><tbody>
{% for row in block.table[1:] %}<tr class="{{ block.classes[loop.index0] if block.classes else '' }}">{% for c in row %}<td>{{ c }}</td>{% endfor %}</tr>{% endfor %}</tbody></table>
{% elif block.json is defined %}<pre>{{ block.json }}</pre>{% else %}<p>{{ block.text }}</p>{% endif %}{% endfor %}</body></html>"""
_ENV = jinja2.Environment(loader=jinja2.DictLoader({"base": _BASE}), autoescape=True)


def page(title, blocks, name=None, status=200):
    return HTMLResponse(_ENV.get_template("base").render(title=title, blocks=blocks, name=name), status_code=status)


def pretty(x) -> str:
    return json.dumps(x, indent=1, sort_keys=True, default=str)


def table(header, rows, heading=None, classes=None):
    return {"heading": heading, "table": [header, *rows], "classes": classes}


def create_debug_app(saves_dir, *, port: int = DEFAULT_PORT, env=None) -> Starlette:
    env = os.environ if env is None else env
    if env.get("EIDOLON_DEBUG") != "1":
        raise DebugDisabled("set EIDOLON_DEBUG=1 to start the debug server")
    saves = Path(saves_dir)
    cache: dict[tuple, Save] = {}

    def open_save(name: str) -> Save | None:
        p = saves / f"{name}.db"
        if not NAME.fullmatch(name) or not p.is_file():
            return None
        key = (str(p), p.stat().st_mtime_ns, p.stat().st_size)
        if key not in cache:
            cache.clear()                                   # one save at a time: a debug session is one investigation
            cache[key] = Save.open(p)                       # read-only, verified end to end
        return cache[key]

    def guarded(view):
        async def handler(request: Request):
            name = request.path_params.get("name", "")
            try:
                save = open_save(name) if name else None
            except SaveRefusal as e:
                return page("Save refused", [{"text": f"{e}"}], name, 409)
            if name and save is None:
                return HTMLResponse("Not Found", status_code=404)
            return await view(request, name, save)
        return handler

    def traces_of(save):
        committed, bad1 = slo.parse_rows(save.trace_rows())
        aborted, bad2 = slo.parse_rows(save.trace_rows(aborted=True))
        return committed, aborted, bad1 + bad2

    async def index(request: Request):
        names = sorted(p.stem for p in saves.glob("*.db") if NAME.fullmatch(p.stem) and not p.name.endswith(".traces.db"))
        return page("Saves", [table(["save", "turn inspector"], [[n, f"/g/{n}/turns"] for n in names])])

    async def turns(request, name, save):
        committed, aborted, bad = traces_of(save)
        rows = [[t.turn_id, t.kind, t.character or "", t.outcome, t.selected.act if t.selected else "", ", ".join(t.failures),
                 f"/g/{name}/turn/{t.turn_id}"] for t in committed]
        return page("Turn inspector", [table(["turn", "kind", "who", "outcome", "act", "failures", "link"], rows),
                                       {"text": f"trace gaps (committed turns with no trace): {save.trace_gaps()}; unreadable rows: {bad}"}], name)

    async def turn(request, name, save):
        n = int(request.path_params["n"])
        committed, _, _ = traces_of(save)
        t = next((x for x in committed if x.turn_id == n), None)
        if t is None:
            return page("Turn", [{"text": f"No trace for turn {n} (a gap is expected after a crash, or the turn is not there)."}], name, 404)
        table_ = {h: i for h, i in trace_mod.resolver(save).items()}
        row = json.loads(t.model_dump_json())

        def res(x):
            if isinstance(x, str):
                return f"{table_[x]}  [{x}]" if x in table_ else x
            if isinstance(x, list):
                return [res(v) for v in x]
            if isinstance(x, dict):
                return {k: res(v) for k, v in x.items()}
            return x
        before, after = replay.before_after(save.path, n)
        d = replay.diff(replay.summary(before), replay.summary(after)) if before is not None and after is not None else {}
        return page(f"Turn {n}", [{"heading": "State before -> after (what changed)", "json": pretty(d)},
                                  {"heading": "Trace (handles resolved against the sealed case)", "json": pretty(res(row))}], name)

    async def characters(request, name, save):
        st = save.state
        rows = []
        for a in sorted(st.characters):
            c = st.characters[a]
            rows.append([a, c.composure, "; ".join(f"{s.id}@L{layer_index(st.decision.layer_peels, a, s.id)}" for s in st.secrets.for_owner(a)),
                         json.dumps(c.verbal_pressure, sort_keys=True), sorted(c.slips_used), len(st.knowledge.for_character(a)),
                         len(st.beliefs.for_character(a)), len(st.memories.get(a, ())), f"/g/{name}/character/{a}"])
        return page("Character inspector", [table(["who", "composure bp", "secret@layer", "verbal pressure", "slips used", "knowledge",
                                                   "beliefs", "memories", "link"], rows)], name)

    async def character(request, name, save):
        a = request.path_params["who"]
        st = save.state
        if a not in st.characters:
            return HTMLResponse("Not Found", status_code=404)
        k = [[e.id, e.proposition.kind, type(e.source).__name__, e.reliability, e.is_true] for e in st.knowledge.for_character(a)]
        b = [[x.id, x.proposition.kind, x.confidence_0, ",".join(x.grounds), x.is_true] for x in st.beliefs.for_character(a)]
        m = [[x.id, x.kind, x.strength_0, x.salience, ",".join(x.content)] for x in st.memories.get(a, ())]
        sec = [{"heading": f"Secret {s.id} ({s.kind})", "json": pretty({"protected": [p.kind for p in s.protected], "layers": [
            {"index": l.index, "resolve": l.resolve, "terminal": l.terminal, "claims": [c.id for c in l.claims],
             "breaker_sets": [sorted(b) for b in l.breaker_sets]} for l in s.cover.layers],
            "layer_reached": layer_index(st.decision.layer_peels, a, s.id)})} for s in st.secrets.for_owner(a)]
        return page(f"Character {a}", [{"heading": "State", "json": pretty(json.loads(st.characters[a].model_dump_json()))}, *sec,
                                       table(["id", "kind", "source", "reliability", "true"], k, "Knowledge (provenance)"),
                                       table(["id", "kind", "confidence bp", "grounds", "true"], b, "Beliefs"),
                                       table(["id", "kind", "strength bp", "salience bp", "content"], m, "Memories")], name)

    async def world(request, name, save):
        case = save.state.case
        t = int(request.query_params.get("t", case.t_investigation))
        w = world_at(case.events, max(0, min(t, case.t_investigation)))
        ev = sorted(case.events, key=lambda e: (e.interval[0], e.id))
        return page("World inspector", [
            {"heading": f"world_at({w.t}) - scrub with ?t=N (0..{case.t_investigation})", "json": pretty(
                {"actor_at": w.actor_at, "object_at": w.object_at, "object_state": w.object_state})},
            table(["start", "end", "kind", "actor", "where", "with"],
                  [[e.interval[0], e.interval[1], e.kind, e.actor or "", e.location or "", ",".join((*e.participants, *e.objects))]
                   for e in ev if e.kind != "Stay"], "Timeline (Stay events omitted)")], name)

    async def evidence(request, name, save):
        st = save.state
        rows = [[e.id, e.kind, e.object or "", "yes" if e.id in st.discovery.known_evidence else "no",
                 f"{e.discovery.action}@{e.discovery.at}", len(e.implications), ",".join(p.ref for p in e.discovery.prerequisites)]
                for e in sorted(st.evidence.all(), key=lambda e: e.id)]
        return page("Evidence inspector", [table(["id", "kind", "object", "discovered", "how", "implications", "needs"], rows)], name)

    async def validator(request, name, save):
        # The raw proof is not read here: I-58 allows only `solve/package.py` and its verifier to touch it. The sealed REPORT is
        # what §27.2's "Validator report for the case" is, and it records the proof's size and every stage's verdict.
        return page("Validator report", [{"heading": "Sealed case report (every stage, at full scale)", "json": pretty(save.bundle.report)},
                                         {"text": "The proof was verified independently when this save was opened (I-58); its contents are not shown here."}], name)

    async def failures(request, name, save):
        committed, aborted, bad = traces_of(save)
        rows = [[t.turn_id if t.turn_id is not None else "-", t.kind, t.outcome, ", ".join(t.failures),
                 "; ".join(f"{d.outcome}:{','.join(d.violations)}" for d in t.drafts if d.violations)]
                for t in [*committed, *aborted] if t.failures or t.outcome not in ("committed",)]
        return page("Failures (validation failures, fallbacks, attempts that committed nothing)", [
            table(["turn", "kind", "outcome", "failures", "violations by attempt"], rows)], name)

    async def ledger(request, name, save):
        committed, aborted, _ = traces_of(save)
        rows = [[t.turn_id if t.turn_id is not None else "-", c.role, c.model, c.effort, c.input_tokens, c.output_tokens,
                 c.cache_read_tokens, c.latency_ms, c.cost_micro_usd if c.cost_micro_usd is not None else "n/a", c.error, c.prompt_hash]
                for t in [*committed, *aborted] for c in t.llm_calls]
        tot = lambda f: sum(f(c) for t in [*committed, *aborted] for c in t.llm_calls)                    # noqa: E731
        return page("LLM ledger", [{"text": f"calls {len(rows)}; input {tot(lambda c: c.input_tokens)}; output {tot(lambda c: c.output_tokens)}; "
                                            f"cache read {tot(lambda c: c.cache_read_tokens)}; (cost is n/a without a price table)"},
                                   table(["turn", "role", "model", "effort", "in", "out", "cache", "ms", "cost uUSD", "error", "prompt hash"], rows)], name)

    async def slo_view(request, name, save):
        ms = slo.from_save(save)
        return page("SLOs", [table(["metric", "value", "target", "status", "note"],
                                   [[m.name, json.dumps(m.value, sort_keys=True), m.target, m.status, m.note] for m in ms],
                                   classes=[m.status for m in ms])], name)

    async def audit_view(request, name, save):
        rep = audit.audit_save(save)
        return page("Offline audit (a detector, not a guarantee)", [
            {"heading": "Summary", "json": pretty(rep.summary())},
            table(["statement", "speaker", "act", "violations"], [[f.statement, f.speaker, f.act, ", ".join(f.violations)] for f in rep.findings],
                  "Discrepancies")], name)

    async def replay_view(request, name, save):
        fresh = Save.open(save.path)
        bound = foreign = 0
        with contextlib.closing(sqlite3.connect(f"{save.path.resolve().as_uri()}?mode=ro", uri=True)) as c:
            heads = dict(c.execute("SELECT seq, hash FROM session_events"))
        committed, _, _ = traces_of(save)
        for t in committed:
            ok = t.committed.head_hash == heads.get(t.committed.last_seq) and t.committed.case == save.bundle.package.seal[:16]
            bound, foreign = bound + ok, foreign + (not ok)
        finals = {t: s for t, s in replay.turn_states(save.path)}
        last = finals[max(finals)]
        return page("Replay (re-fold and compare)", [{"heading": "Result", "json": pretty({
            "state_hash_loaded": save.state_hash(), "state_hash_reopened": fresh.state_hash(), "state_hash_refolded_turn_by_turn": store.state_hash(last),
            "equal": save.state_hash() == fresh.state_hash() == store.state_hash(last), "turns": max(finals),
            "trace_gaps": save.trace_gaps(), "traces_bound_to_this_log": bound, "traces_foreign_or_stale": foreign})}], name)

    def route(path, view):
        return Route(path, guarded(view), methods=["GET"])

    return Starlette(routes=[
        Route("/", index, methods=["GET"]),
        route("/g/{name}/turns", turns), route("/g/{name}/turn/{n:int}", turn),
        route("/g/{name}/characters", characters), route("/g/{name}/character/{who}", character),
        route("/g/{name}/world", world), route("/g/{name}/evidence", evidence), route("/g/{name}/validator", validator),
        route("/g/{name}/failures", failures), route("/g/{name}/ledger", ledger), route("/g/{name}/slo", slo_view),
        route("/g/{name}/audit", audit_view), route("/g/{name}/replay", replay_view)],
        middleware=[Middleware(_LoopbackOnly, hosts=allowed_hosts(port))])
