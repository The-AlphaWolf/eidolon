"""Phase 8 — the player's browser app (§23.7, §30): server-rendered pages over `game`, plain HTML forms, no script.

* Every form carries the `action_id` minted for it when the page was rendered (form @ log head: deterministic, I-6) and
  the head it was rendered at (`expected_seq`). Re-sending a form — a double click, a browser retry after a lost
  response — returns the turn it already committed; a form from an older page (another tab) commits nothing (§26.2,
  I-14). Retrying is therefore always safe, which is the whole of retry-on-failure.
* A page shows projections only (`game.notebook`, `game.report`); evidence is named by opaque handles, never ids.
* There are no debug, trace or state routes here (I-10): the debug server is Phase 9's, in its own process.
* The app answers only the loopback names on the port it serves (`allowed_hosts`): `Host` is judged against that, `Origin` against
  the matching origins — never against each other, which a DNS-rebound page satisfies (H8-I2). A save opens only under the
  spelling it has on disk, so one file is one `Save`, one head, one rate window (H8-I3).
* Every form field is validated here, at the trust boundary, before it reaches an engine type.

ponytail: Starlette, not FastAPI — FastAPI is not installed and adds nothing these five routes use (it is Starlette
underneath); HTMX is not vendored (no network here) — full-page form posts do the same job without partial swaps.
ponytail: one process and one event-loop thread with open saves cached: every endpoint is `async`, so each SQLite
connection stays on the thread that opened it. A multi-user host needs a worker (or a fresh open) per game.
"""
from __future__ import annotations

import contextlib
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import jinja2
from starlette.applications import Starlette
from starlette.datastructures import Headers
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from starlette.routing import Route

from . import game
from .cli import encountered
from .llm.ingress import Asked, Clarify, Explore, ModelParser, interpret, rate_window
from .llm.render import LLMRenderer, ModelLLM
from .solve.package import SealRefusal
from .solve.queries import clock_buckets
from .store import Save, SaveError, SaveRefusal
from .trace import Observed
from .decision.hypotheses import Lied, Planted
from .world.propositions import At

NAME = re.compile(r"[A-Za-z0-9_-]{1,40}")
_RESERVED = re.compile(r"(con|prn|aux|nul|com\d|lpt\d)", re.I)       # Windows device names are not file names


@dataclass
class Chat:
    """Free text (§12.1 stages 0-2, 8-9), present only when a model transport is configured (`eidolon serve --llm`):
    screen → parse (names the player may use only) → ground → the same turn, rendered by the model and validated.
    `times` feeds the ingress rate window per save; every typed line counts, because every one costs a parse call."""
    parser: ModelParser
    renderer: LLMRenderer
    clock: Callable[[], float] = time.monotonic
    times: dict[str, list[float]] = field(default_factory=dict)


class Games:
    """Session management: the case library (sealed bundles in `cases_dir`) and the saves (`saves_dir/<name>.db`)."""

    def __init__(self, saves_dir, cases_dir):
        self.saves_dir, self.cases_dir = Path(saves_dir), Path(cases_dir)
        self._open: dict[str, Save] = {}

    def cases(self) -> list[str]:
        return sorted(p.stem for p in self.cases_dir.glob("*.json") if NAME.fullmatch(p.stem))

    def saves(self) -> list[str]:
        return sorted(p.stem for p in self.saves_dir.glob("*.db") if NAME.fullmatch(p.stem))

    def valid_name(self, name: str) -> bool:
        return bool(NAME.fullmatch(name)) and not _RESERVED.fullmatch(name)

    def create(self, name: str, case: str, seed: int) -> Save:
        if not self.valid_name(name) or case not in self.cases():
            raise SaveError("bad game name or case")
        save = Save.create(self.saves_dir / f"{name}.db", self.cases_dir / f"{case}.json", seed=seed)
        self._open[name] = save
        return save

    def open(self, name: str) -> Save | None:
        """Only under the spelling the save has on disk: NTFS maps `/g/G1` onto `g1.db`, and a second spelling would be a
        second `Save` on one file — two heads, two action ledgers, two rate windows (H8-I3)."""
        if not self.valid_name(name) or name not in self.saves():
            return None
        if name not in self._open:
            path = self.saves_dir / f"{name}.db"
            if not path.is_file():
                return None
            self._open[name] = Save.open(path, writable=True)
        return self._open[name]

    def close_all(self) -> None:
        for s in self._open.values():
            s.close()
        self._open.clear()


# ------------------------------------------------------------------------------------ pages
_CSS = """body{font:1rem/1.5 system-ui,sans-serif;color:#111;background:#fff;margin:0}
main{max-width:72rem;margin:0 auto;padding:1rem}section{border:1px solid #888;border-radius:.4rem;padding:.5rem 1rem;margin:1rem 0}
label{display:inline-block;margin:.3rem .3rem .3rem 0;font-weight:600}select,input,button{font:inherit;margin-right:.8rem}
button{padding:.2rem .8rem}.chip{color:#333;font-style:italic}a{color:#0645ad}:focus-visible{outline:3px solid #0645ad}
table{border-collapse:collapse}td,th{border:1px solid #888;padding:.2rem .5rem;text-align:left}"""

_TEMPLATES = {
    "base": """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }} — Eidolon</title><style>""" + _CSS + """</style></head>
<body><main>{% block body %}{% endblock %}</main></body></html>""",

    "index": """{% extends "base" %}{% block body %}<h1>Eidolon</h1>
<section><h2>Saved games</h2><ul>{% for s in saves %}<li><a href="/g/{{ s }}">{{ s }}</a></li>{% else %}<li>None yet.</li>{% endfor %}</ul></section>
<section><h2>New game</h2>{% if error %}<p role="alert">{{ error }}</p>{% endif %}
<form method="post" action="/new">
<label for="new-name">Name</label><input id="new-name" name="name" required pattern="[A-Za-z0-9_-]{1,40}">
<label for="new-case">Case</label><select id="new-case" name="case">{% for c in cases %}<option value="{{ c }}">{{ c }}</option>{% endfor %}</select>
<label for="new-seed">Seed</label><input id="new-seed" name="seed" type="number" min="0" value="0">
<button type="submit">Start</button></form></section>{% endblock %}""",

    "game": """{% extends "base" %}{% macro hidden(op, suffix="") %}<input type="hidden" name="op" value="{{ op }}"><input type="hidden" name="action_id" value="{{ op }}{{ suffix }}@{{ seq }}"><input type="hidden" name="expected_seq" value="{{ seq }}">{% endmacro %}
{% macro options(items, blank=None) %}{% if blank %}<option value="">{{ blank }}</option>{% endif %}{% for i in items %}<option value="{{ i.id }}">{{ i.name }}</option>{% endfor %}{% endmacro %}
{% macro held(v, blank) %}<option value="">{{ blank }}</option>{% for e in v.evidence %}<option value="{{ e.ref }}">{{ e.label }}</option>{% endfor %}{% for s in v.statements %}<option value="{{ s.ref }}">statement {{ s.turn }} ({{ s.speaker }})</option>{% endfor %}{% endmacro %}
{% block body %}<h1>Game {{ name }}</h1>
<p>Turn {{ v.turn }} · {% if v.status == "open" %}The investigation is open.{% else %}The case is closed.{% endif %} · <a href="/">All games</a></p>
<section aria-live="polite"><h2>Last action</h2>{% if out %}{% if out.chip %}<p class="chip">{{ out.chip }}</p>{% endif %}{% if out.reply %}<p>{{ out.reply }}</p>{% endif %}{% if out.message %}<p>{{ out.message }}</p>{% endif %}{% else %}<p>Nothing yet.</p>{% endif %}</section>
{% if v.status != "open" %}<section><h2>Verdict</h2><p>The case is closed. <a href="/g/{{ name }}/report">Read the case report</a>.</p></section>{% else %}
{% if chat %}<section><h2>Say something</h2><form method="post">{{ hidden("say") }}
<label for="say-addressee">To</label><select id="say-addressee" name="addressee">{{ options(v.people) }}</select>
<label for="say-text">You say</label><input id="say-text" name="text" maxlength="1000" size="60" required>
<button type="submit">Say it</button></form></section>{% endif %}
<section><h2>Question someone</h2><form method="post">{{ hidden("ask") }}
<label for="ask-addressee">Ask</label><select id="ask-addressee" name="addressee">{{ options(v.people) }}</select>
<label for="ask-topic">About</label><select id="ask-topic" name="topic"><option value="">anything</option>{% for k, t in v.topics.items() %}<option value="{{ k }}">{{ t }}</option>{% endfor %}</select>
<label for="ask-about">Concerning</label><select id="ask-about" name="about">{{ options(v.everyone, "nobody in particular") }}</select>
<label for="ask-place">Where</label><select id="ask-place" name="place">{{ options(v.places, "anywhere") }}</select>
<label for="ask-bucket">When</label><select id="ask-bucket" name="bucket"><option value="">any time</option>{% for t in v.times %}<option value="{{ t.bucket }}">{{ t.label }}</option>{% endfor %}</select>
<label for="ask-present">Show them</label><select id="ask-present" name="present">{{ held(v, "nothing") }}</select>
<input type="checkbox" id="ask-accuse" name="accuse"><label for="ask-accuse">Accuse them to their face</label>
<button type="submit">Ask</button></form></section>
<section><h2>Move and search</h2>
<form method="post">{{ hidden("goto") }}<label for="goto-location">Go to</label><select id="goto-location" name="location">{{ options(v.places) }}</select><button type="submit">Go</button></form>
<form method="post">{{ hidden("search") }}<label for="search-target">Search</label><select id="search-target" name="target">{{ options(v.places) }}{{ options(v.objects) }}</select>
<label for="search-method">by</label><select id="search-method" name="method">{% for m in v.methods %}<option value="{{ m }}">{{ m }}</option>{% endfor %}</select><button type="submit">Search</button></form></section>
<section><h2>Theories</h2><form method="post">{{ hidden("hypothesize") }}
<label for="hyp-kind">Theory</label><select id="hyp-kind" name="kind"><option value="At">someone was somewhere</option><option value="Lied">someone lied in a statement</option><option value="Planted">an item was planted</option></select>
<label for="hyp-actor">Who</label><select id="hyp-actor" name="actor">{{ options(v.everyone) }}</select>
<label for="hyp-location">Where</label><select id="hyp-location" name="location">{{ options(v.places) }}</select>
<label for="hyp-start">From</label><input id="hyp-start" name="start" type="time" step="60" max="{{ v.clock_end }}">
<label for="hyp-end">Until</label><input id="hyp-end" name="end" type="time" step="60" max="{{ v.clock_end }}">
<label for="hyp-statement">Statement</label><select id="hyp-statement" name="statement"><option value="">none</option>{% for s in v.statements %}<option value="{{ s.ref }}">statement {{ s.turn }} ({{ s.speaker }})</option>{% endfor %}</select>
<label for="hyp-item">Item</label><select id="hyp-item" name="item"><option value="">none</option>{% for e in v.evidence %}<option value="{{ e.ref }}">{{ e.label }}</option>{% endfor %}</select>
<label for="hyp-confidence">Confidence (percent)</label><input id="hyp-confidence" name="confidence" type="number" min="0" max="100" value="50">
<button type="submit">Add theory</button></form>
<ul>{% for h in v.hypotheses %}<li>{{ h.text }} — {{ h.confidence }}% — {{ h.status }}{% if h.support %}; consistent with {{ h.support|join(", ") }}{% endif %}{% if h.against %}; against it: {{ h.against|join(", ") }}{% endif %}
<form method="post">{{ hidden("withdraw", "-" ~ h.id) }}<input type="hidden" name="hypothesis" value="{{ h.id }}"><button type="submit">Withdraw theory {{ h.id }}</button></form></li>{% else %}<li>No theories yet.</li>{% endfor %}</ul></section>
<section><h2>Final accusation</h2><form method="post">{{ hidden("accuse") }}
<label for="acc-suspect">Who</label><select id="acc-suspect" name="suspect">{{ options(v.people) }}<option value="Outsider">someone from outside</option></select>
<label for="acc-weapon">With</label><select id="acc-weapon" name="weapon">{{ options(v.objects, "not sure") }}</select>
<label for="acc-location">Where</label><select id="acc-location" name="location">{{ options(v.places, "not sure") }}</select>
<label for="acc-start">From</label><input id="acc-start" name="start" type="time" step="60" max="{{ v.clock_end }}">
<label for="acc-end">Until</label><input id="acc-end" name="end" type="time" step="60" max="{{ v.clock_end }}">
<label for="acc-motive">Why</label><select id="acc-motive" name="motive"><option value="">not sure</option>{% for m in v.motives %}<option value="{{ m }}">{{ m }}</option>{% endfor %}</select>
<fieldset><legend>Cite as proof</legend>{% for e in v.evidence %}<input type="checkbox" id="cite-{{ e.ref }}" name="cited" value="{{ e.ref }}"><label for="cite-{{ e.ref }}">{{ e.label }}</label>{% endfor %}{% for s in v.statements %}<input type="checkbox" id="cite-{{ s.ref }}" name="cited" value="{{ s.ref }}"><label for="cite-{{ s.ref }}">statement {{ s.turn }} ({{ s.speaker }})</label>{% endfor %}</fieldset>
<input type="checkbox" id="acc-confirm" name="confirm"><label for="acc-confirm">This is my final answer: it closes the case</label>
<button type="submit">Accuse</button></form></section>{% endif %}
<section><h2>Notebook</h2><h3>Statements</h3><ol>{% for s in v.statements %}<li value="{{ s.turn }}">{{ s.speaker }}: {{ s.text }}</li>{% else %}<li>Nobody has told you anything yet.</li>{% endfor %}</ol>
<h3>Evidence</h3><ul>{% for e in v.evidence %}<li>{{ e.label }} — {{ e.text }}</li>{% else %}<li>Nothing found yet.</li>{% endfor %}</ul>
<h3>Tensions</h3><ul>{% for t in v.tensions %}<li>{{ t.a_label }} and {{ t.b_label }} do not sit together.</li>{% else %}<li>None noticed yet.</li>{% endfor %}</ul></section>
<section><h2>Map</h2><ul>{% for p in v.places %}<li>{{ p.name }}{% if p.visited %} (visited){% endif %}</li>{% endfor %}</ul></section>{% endblock %}""",

    "report": """{% extends "base" %}{% block body %}<h1>Case report: game {{ name }}</h1>
<p>You accused {{ r.accused }}. {% if r.verdict == "solved" %}That was right.{% else %}That was wrong.{% endif %} <a href="/g/{{ name }}">Back to the notebook</a></p>
<section><h2>Your accusation, axis by axis</h2><ul>{% for axis, ok in r.axes.items() %}<li data-axis="{{ axis }}" data-ok="{{ 'true' if ok else 'false' }}">{{ axis|replace("_", " ") }}: {{ "right" if ok else "not established" }}</li>{% endfor %}</ul></section>
<section><h2>What happened</h2><p>{{ r.truth.who }} did it, in {{ r.truth.where }}, {{ r.truth.when }}, with {{ r.truth.weapon }}; the motive was {{ r.truth.motive }}.</p>
<table><caption>The evening, with what you found marked</caption><thead><tr><th scope="col">When</th><th scope="col">What</th><th scope="col">Who</th><th scope="col">Where</th><th scope="col">With</th><th scope="col">You found its trace</th></tr></thead><tbody>
{% for e in r.timeline %}<tr><td>{{ e.when }}</td><td>{{ e.kind }}</td><td>{{ e.who }}</td><td>{{ e.where }}</td><td>{{ e.with }}</td><td>{{ "yes" if e.found else "" }}</td></tr>{% endfor %}</tbody></table></section>{% endblock %}""",
}
_ENV = jinja2.Environment(loader=jinja2.DictLoader(_TEMPLATES), autoescape=True, undefined=jinja2.StrictUndefined)


def _page(template: str, status: int = 200, **ctx) -> HTMLResponse:
    return HTMLResponse(_ENV.get_template(template).render(**ctx), status_code=status)


# ------------------------------------------------------------------------------------ the boundary: form -> control
def _minute(text: str | None) -> int | None:
    """`HH:MM` (the native time input) or a bare minute count; empty is None; anything else is an error."""
    text = (text or "").strip()
    if not text:
        return None
    if re.fullmatch(r"\d{1,2}:\d{2}", text):
        h, m = text.split(":")
        return int(h) * 60 + int(m)
    if re.fullmatch(r"\d{1,5}", text):
        return int(text)
    raise ValueError(f"not a time: {text!r}")


def _window(form) -> tuple[int, int] | None:
    start, end = _minute(form.get("start")), _minute(form.get("end"))
    if start is None and end is None:
        return None
    if start is None or end is None:
        raise ValueError("a window needs both ends")
    return start, end


def _one_of(value: str | None, allowed) -> str | None:
    """'' -> None; a value outside `allowed` is an error (never passed on to the engine as a name)."""
    if not value:
        return None
    if value not in allowed:
        raise ValueError(f"unknown value {value!r}")
    return value


def dispatch(save: Save, form, chat: Chat | None = None) -> game.Outcome:
    case, st = save.state.case, save.state
    op, aid = form.get("op"), form.get("action_id") or ""
    try:
        seq = int(form.get("expected_seq", ""))
    except ValueError:
        return game.Outcome("rejected", game.NOT_RECORDED)
    try:
        if op == "ask":
            raw = form.get("present") or None
            present = game.held_ref(save, raw) if raw else None
            if raw and present is None:
                raise ValueError("not held")
            bucket = _one_of(form.get("bucket"), {str(b) for b in clock_buckets(case)})
            q = game.question(case, form.get("addressee", ""), topic=_one_of(form.get("topic"), game.TOPICS),
                              about=_one_of(form.get("about"), case.actors), place=_one_of(form.get("place"), case.locations),
                              bucket=int(bucket) if bucket is not None else None, presenting=present is not None)
            return game.ask(save, aid, seq, form.get("addressee", ""), q, present=present, accuse=form.get("accuse") == "on",
                            renderer=chat.renderer if chat else None)
        if op == "say":
            if chat is None:
                raise ValueError("no model is configured for free text")
            who = form.get("addressee", "")
            if who not in st.characters:
                raise ValueError("nobody of that name is here")
            times = chat.times.setdefault(str(save.path), [])
            seen: dict = {}
            out = interpret(form.get("text", ""), parse=chat.parser.parse, case=case, known=encountered(st, who),
                            addressee=who, turns_in_window=rate_window(times, chat.clock()),
                            observe=lambda ing, action: seen.update(ing=ing, action=action))
            times.append(chat.clock())
            calls = chat.parser.transport.drain()          # the parse-stage calls, charged to THIS line and no other
            obs = lambda grounded, reason="", query=None, escalated=False: Observed(     # noqa: E731
                seen.get("ing"), seen.get("action"), grounded, reason, query, escalated, calls)
            if isinstance(out, Asked):
                return game.ask(save, aid, seq, who, out.query, renderer=chat.renderer, typed=True,
                                observed=obs("asked", "", out.query.kind, out.escalated))
            if isinstance(out, Explore):
                o = obs("explore")
                return (game.goto(save, aid, seq, out.target, observed=o) if out.kind == "goto"
                        else game.search(save, aid, seq, out.target, out.method or "Look", observed=o))
            if isinstance(out, Clarify):                # one answer for every grounding failure: no name enumeration (§22.2)
                game.note_attempt(save, kind="say", outcome="clarify", character=who, observed=obs("clarify", out.reason),
                                  failures=("clarify",))
                return game.Outcome("clarify", "Nothing was recorded.", f"To {game.name(case, who)}",
                                    f"{game.name(case, who)}: {out.text}")
            game.note_attempt(save, kind="say", outcome="blocked", character=who, observed=obs("refused", out.reason),
                              failures=("parse_failed" if out.reason.startswith("PARSE_") else "ingress_blocked",))
            return game.Outcome("rejected", game.NOT_RECORDED)
        if op == "goto":
            return game.goto(save, aid, seq, form.get("location", ""))
        if op == "search":
            target = _one_of(form.get("target"), {*case.locations, *case.objects})
            if target is None:
                raise ValueError("nothing to search")
            return game.search(save, aid, seq, target, form.get("method", ""))
        if op == "hypothesize":
            kind, pct = form.get("kind"), int(form.get("confidence", "50"))
            if not 0 <= pct <= 100:
                raise ValueError("confidence out of range")
            if kind == "At":
                prop = At(actor=_one_of(form.get("actor"), case.actors), location=_one_of(form.get("location"), case.locations),
                          interval=_window(form))
            elif kind == "Lied":
                sid = game.held_ref(save, form.get("statement"))
                if sid is None or sid not in st.discovery.known_statements:
                    raise ValueError("not a held statement")
                prop = Lied(actor=st.decision.statements.get(sid).speaker, statement=sid)
            elif kind == "Planted":
                eid = game.held_ref(save, form.get("item"))
                if eid is None or eid not in st.discovery.known_evidence:
                    raise ValueError("not held evidence")
                prop = Planted(evidence=eid)
            else:
                raise ValueError("unknown theory")
            return game.hypothesize(save, aid, seq, (prop,), pct * 100)
        if op == "withdraw":
            return game.withdraw(save, aid, seq, form.get("hypothesis", ""))
        if op == "accuse":
            if form.get("confirm") != "on":
                return game.Outcome("rejected", "A final accusation closes the case: tick the box to confirm it. Nothing was recorded.")
            cited = [game.held_ref(save, c) for c in form.getlist("cited")]
            if None in cited:
                raise ValueError("not held")
            return game.accuse(save, aid, seq, form.get("suspect", ""), weapon=_one_of(form.get("weapon"), case.objects),
                               location=_one_of(form.get("location"), case.locations), interval=_window(form),
                               motive_kind=_one_of(form.get("motive"), game.motive_menu(save)), cited=cited)
    except ValueError:                                  # pydantic's ValidationError is one: a malformed form is refused
        return game.Outcome("rejected", game.NOT_RECORDED)
    return game.Outcome("rejected", game.NOT_RECORDED)


# ------------------------------------------------------------------------------------ routes
LOOPBACK = ("127.0.0.1", "localhost", "[::1]")


def allowed_hosts(port: int) -> frozenset[str]:
    """The only `Host` values the app answers: the loopback names with the port it serves (a browser leaves the port out
    only when it is the scheme's default, 80)."""
    return frozenset(f"{h}:{port}" for h in LOOPBACK) | (frozenset(LOOPBACK) if port == 80 else frozenset())


class _LoopbackOnly:
    """DNS rebinding (H8-I2): `attacker.example` re-pointed at 127.0.0.1 sends `Host: attacker.example` and an `Origin` equal
    to it, which is exactly what the browser would send to a site that really lives there — so neither header can be judged
    against the other. The server judges `Host` against the names it is actually reachable by, on every route and method,
    before a route runs. (400, as `TrustedHostMiddleware` answers.)"""

    def __init__(self, app, hosts: frozenset[str]):
        self.app, self.hosts = app, hosts

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and Headers(scope=scope).get("host", "").lower() not in self.hosts:
            return await PlainTextResponse("Invalid host header", status_code=400)(scope, receive, send)
        await self.app(scope, receive, send)


def _same_origin(request: Request) -> bool:
    """CSRF: no cookie identifies a player here, so a page on another site could otherwise post moves to a local game.
    Browsers send `Origin` on every cross-site POST; a request without one is not from a browser page. An `Origin` is
    accepted only if it is one of this server's own loopback origins (never because it equals whatever `Host` says)."""
    origin = request.headers.get("origin")
    return origin is None or origin in request.app.state.origins


_FORBIDDEN = HTMLResponse("Forbidden", status_code=403)
_UNREADABLE = "This save failed verification and cannot be opened. Nothing in it was changed."


def create_app(saves_dir, cases_dir, *, port: int = 8000, transport=None, latency_floor_s: float = 0.0,
               clock=time.monotonic) -> Starlette:
    """`port` is the one `eidolon serve` listens on: it fixes the `Host`/`Origin` values the app answers (loopback names only).
    `transport` (an `llm.provider` transport) turns on free text and model rendering; `latency_floor_s` is I-42's
    floor (`LATENCY_FLOOR_S` with a live model; 0 for a scripted one)."""
    games = Games(saves_dir, cases_dir)
    chat = None
    if transport is not None:
        model = ModelLLM(transport)
        chat = Chat(ModelParser(model.transport), LLMRenderer(model, min_latency_s=latency_floor_s), clock)

    async def index(request: Request):
        return _page("index", title="Games", saves=games.saves(), cases=games.cases(), error=None)

    async def new_game(request: Request):
        if not _same_origin(request):
            return _FORBIDDEN
        form = await request.form()
        name, case = form.get("name", ""), form.get("case", "")
        try:
            seed = int(form.get("seed") or 0)
            games.create(name, case, seed)
        except (ValueError, SaveError, SealRefusal, OSError):
            return _page("index", 400, title="Games", saves=games.saves(), cases=games.cases(),
                         error="That game could not be created: pick an unused name of letters, digits, - or _, and a case.")
        return RedirectResponse(f"/g/{name}", status_code=303)

    async def play(request: Request):
        name = request.path_params["name"]
        if request.method == "POST" and not _same_origin(request):
            return _FORBIDDEN
        try:
            save = games.open(name)
        except SaveRefusal:                             # a damaged or forged save: refused, never half-loaded (I-15)
            return HTMLResponse(_UNREADABLE, status_code=409)
        if save is None:
            return HTMLResponse("Not Found", status_code=404)
        out = dispatch(save, await request.form(), chat) if request.method == "POST" else None
        return _page("game", title=f"Game {name}", name=name, seq=save.last_seq, v=game.notebook(save), out=out,
                     chat=chat is not None)

    async def report(request: Request):
        name = request.path_params["name"]
        try:
            save = games.open(name)
        except SaveRefusal:
            return HTMLResponse(_UNREADABLE, status_code=409)
        r = game.report(save) if save is not None else None
        if r is None:
            return HTMLResponse("Not Found", status_code=404)
        return _page("report", title=f"Report {name}", name=name, r=r)

    @contextlib.asynccontextmanager
    async def lifespan(app):
        yield
        games.close_all()

    hosts = allowed_hosts(port)
    app = Starlette(routes=[Route("/", index), Route("/new", new_game, methods=["POST"]),
                            Route("/g/{name}", play, methods=["GET", "POST"]), Route("/g/{name}/report", report)],
                    middleware=[Middleware(_LoopbackOnly, hosts=hosts)], lifespan=lifespan)
    app.state.games = games
    app.state.origins = frozenset(f"http://{h}" for h in hosts)
    return app
