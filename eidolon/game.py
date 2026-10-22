"""Phase 8 — the player's controls and everything the player is shown (§30).

* A control turns one player action into one turn through the decision runners and commits it ONLY through `Save.append`,
  the validating fold. Nothing here mutates state: the folded state the store returns is the session (§23.3).
* Every view is a PROJECTION of the folded state — rebuilt on demand, never hashed (§26.3 step 4) — and serializes no
  engine-only field: no act, sincerity, grounding, cover layer, pressure, secret, knowledge/belief/memory id, account
  token or evidence id (§12.1 stage 11, §13.4). Evidence is named by an opaque per-case handle.
* The case report (§16.3) exists only after the verdict. The answer is read from the CaseLog and the proof's verified
  survivor (N-7), never from the declared `solution`, and the evidence axis is the solver run on the CITED set — so any
  valid proof earns full credit, whatever the stored proof core is.

Layering: the top of the stack beside `cli`. It imports `store`, `solve` (the evidence axis) and `gen.skeletons` (the
motive vocabulary a case was generated from); nothing below imports it.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass
from typing import Callable, get_args

from . import trace as _trace
from .decision.hypotheses import Lied, Planted, evaluate_hypothesis
from .decision.query import EntityRef, Query
from .decision.solver import UniquenessResult
from .decision.turn import (
    run_accusation_turn, run_ask_turn, run_goto_turn, run_hypothesis_turn, run_search_turn,
)
from .evidence.contradiction import contradiction, evidence_implication_contradicts, evidence_vs_evidence
from .evidence.discovery import unlocked_view
from .evidence.model import DiscoverySpec
from .gen.skeletons import SKELETONS
from .llm.render import player_view
from .solve.bots import credited_material
from .solve.queries import BUCKET, Names, clock_buckets, names_from_evidence, names_of_proposition, time_phrase
from .solve.solver import build_ctx, evaluate
from .store import Save, SaveRefusal, StaleAppend
from .world.alias import render_time
from .world.interval import overlaps

CLOCK = time.monotonic        # injectable: a trace's timings are the only thing that reads a clock here

METHODS = tuple(m for m in get_args(DiscoverySpec.model_fields["action"].annotation) if m != "Ask")
TOPICS = {"presence": "who was where", "did": "what was done", "heard": "what was heard"}
OUTSIDER = "Outsider"
NOT_RECORDED = "That could not be done. Nothing was recorded."


@dataclass(frozen=True)
class Outcome:
    """What one action did, as the player may see it. `chip` is how the action was understood (§12.1 stage 1's
    interpretation chip); `reply` is in-world text that passed validation (I-12) — empty on any refusal (I-15)."""
    status: str                 # ok | rejected | duplicate | stale | clarify (an in-world "what do you mean?", nothing recorded)
    message: str = ""
    chip: str = ""
    reply: str = ""
    turn: int | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


# ------------------------------------------------------------------------------------ names and handles
def name(case, i: str | None) -> str:
    if i == OUTSIDER:
        return "someone from outside"
    for table in (case.actors, case.locations, case.objects):
        if i in table:
            return table[i].name
    return "?"


def handle(save: Save, evidence_id: str) -> str:
    """An evidence id says what the engine thinks an item is (`E_alibi_…`, `E_secret_…`); the player sees this instead."""
    return "e" + hashlib.sha256(f"{save.bundle.package.seal}|{evidence_id}".encode()).hexdigest()[:12]


def held_ref(save: Save, ref: str | None) -> str | None:
    """A player-side ref -> the engine ref, among HELD material only (an unheld or unknown ref resolves to nothing)."""
    d = save.state.discovery
    by_handle = {handle(save, e): e for e in d.known_evidence}
    return by_handle.get(ref) or (ref if ref in d.known_statements else None)


def _labels(save: Save) -> dict[str, str]:
    """engine ref -> what the player calls it: a numbered item for evidence, a numbered statement for testimony."""
    st, case = save.state, save.state.case
    out = {}
    for n, (_, e) in enumerate(sorted((handle(save, e), e) for e in st.discovery.known_evidence), 1):
        ev = st.evidence.get(e)
        out[e] = f"item {n}: {ev.kind.lower()} ({name(case, ev.discovery.at)})"
    for sid in st.discovery.known_statements:
        s = st.decision.statements.get(sid)
        out[sid] = f"statement {s.turn} ({name(case, s.speaker)})"
    return out


def _ref_out(save: Save, ref: str) -> str:
    return handle(save, ref) if save.state.evidence.get(ref) is not None else ref


def minutes(a: int, b: int) -> str:
    return f"{render_time(a)}–{render_time(b)}"


def describe(save: Save, p, labels: dict[str, str] | None = None) -> str:
    case, labels = save.state.case, labels if labels is not None else _labels(save)
    if isinstance(p, Lied):
        return f"{name(case, p.actor)} lied in {labels.get(p.statement, 'a statement')}"
    if isinstance(p, Planted):
        return f"{labels.get(p.evidence, 'an item')} was planted"
    if p.kind in ("At", "NotAt"):
        return f"{name(case, p.actor)} was {'not ' if p.kind == 'NotAt' else ''}in {name(case, p.location)} {minutes(*p.interval)}"
    return p.kind


# ------------------------------------------------------------------------------------ the controls
_STALE = "The case moved on since this page was loaded. Nothing was recorded."


def _already(ref, chip: str) -> Outcome:
    return Outcome("duplicate", f"Already recorded as turn {ref.turn}: this form was sent before. Nothing new was recorded.",
                   chip, turn=ref.turn)


def _game_id(save: Save) -> str:
    return re.sub(r"[^A-Za-z0-9_. \-]", "_", save.path.stem)[:48] or "game"


def _traced(write, *build_args, **build_kw) -> bool:
    """Build one `TurnTrace` and hand it to `write`; NOTHING that goes wrong here may touch the turn (§27.1). A failure is
    logged by exception CLASS only: its message may hold the very text the trace was meant to keep out of logs."""
    try:
        return bool(write(_trace.to_row(_trace.build_turn_trace(*build_args, **build_kw))))
    except Exception as exc:                                             # noqa: BLE001 - best effort, by contract
        logging.getLogger("eidolon.trace").warning("trace not built or written: %s", type(exc).__name__)
        return False


def note_attempt(save: Save, *, kind: str, outcome: str, character: str | None = None, observed=None, failures=(),
                 res=None, run_ms: int = 0) -> bool:
    """An attempt that committed nothing - a rejected control, a clarify, a blocked line, a fold refusal - recorded in the
    trace file's `aborted` table. Best effort; returns whether the row was written. Never touches the save."""
    return _traced(save.write_aborted, save, res, kind=kind, game_id=_game_id(save), outcome=outcome, character=character,
                   observed=observed, run_ms=run_ms, failures=failures)


def _commit(save: Save, action_id: str, expected_seq: int, run: Callable, *, chip: str = "",
            say: Callable = lambda res: "", kind: str = "ask", character: str | None = None, observed=None) -> Outcome:
    """§26.2 / I-14 / I-15. A re-sent action returns the turn it committed; a page rendered at an older head commits
    nothing; a runner rejection or a fold refusal commits nothing and shows no in-world text. The STORE has the last word
    on a duplicate: this `Save` may not know an action another writer committed (a second process, a second handle on the
    file), and then the reply the runner just computed was never recorded - it is not shown (H8-I3).

    §27.1: the turn's trace is built and written AFTER the commit (a rejected attempt is noted in the `aborted` table). Both
    are best-effort and cannot change the Outcome."""
    if (ref := save.turn_for(action_id)) is not None:
        return _already(ref, chip)
    if expected_seq != save.last_seq:
        return Outcome("stale", _STALE, chip)
    if save.state.decision.solved is not None:
        return Outcome("rejected", "The case is closed.", chip)
    t0 = CLOCK()
    res = run(save.state)
    run_ms = int((CLOCK() - t0) * 1000)
    if res.rejected:
        note_attempt(save, kind=kind, outcome="rejected", character=character, observed=observed, res=res, run_ms=run_ms)
        return Outcome("rejected", NOT_RECORDED, chip)
    t1 = CLOCK()
    try:
        got = save.append(res.events, expected_seq, action_id)
    except StaleAppend:
        return Outcome("stale", _STALE, chip)
    except SaveRefusal:
        note_attempt(save, kind=kind, outcome="refused_by_store", character=character, observed=observed, res=res,
                     run_ms=run_ms, failures=("store_refused",))
        return Outcome("rejected", NOT_RECORDED, chip)
    if not got.appended:
        return _already(got.ref, chip) if got.same_events else Outcome("stale", _STALE, chip)
    append_ms = int((CLOCK() - t1) * 1000)
    _traced(lambda row: save.write_trace(got.ref.turn, row), save, res, kind=kind, game_id=_game_id(save), outcome="committed",
            character=character, observed=observed, committed=got, run_ms=run_ms, append_ms=append_ms)
    return Outcome("ok", "", chip, say(res), turn=save.state.turn_counter)


_CTX: dict[str, object] = {}          # solver context per sealed package (by seal): built once, it is static


def _solver_ctx(pkg):
    if pkg.seal not in _CTX:
        _CTX[pkg.seal] = build_ctx(pkg)
    return _CTX[pkg.seal]


def confession_gate(st, pkg):
    """I-21 (H9-I3): the murderer confesses only when the material put to them PROVES them the unique culprit - the solver,
    run on what the player has presented (`credited_material(only=presented)`, the crediting rule V-7 and the evidence axis
    use) at the case's fairness level. `decision.peel.confession_permitted` binds the verdict to identity (the survivor must
    be the confrontee). The store re-checks the turn's shape (`store._check_confession`)."""
    def check(actor, secret, presented, ctx):
        v = evaluate(_solver_ctx(pkg), credited_material(st, only=frozenset(presented)), fairness=pkg.fairness_level,
                     want_cores=False)
        return UniquenessResult(unique=bool(v.unique), survivors=tuple(v.survivors))
    return check


def question(case, addressee: str, *, topic: str | None = None, about: str | None = None, place: str | None = None,
             bucket: int | None = None, presenting: bool = False) -> Query:
    """The structured question form -> the engine's `Query`. It speaks the V-7 vocabulary (`solve.queries`): exactly the
    questions the bots solve every sealed case with, so the case is solvable from this form (§19.7)."""
    subject = EntityRef(id=about, kind="actor") if about else None
    when = time_phrase(bucket) if bucket is not None else None
    words = [f"about {TOPICS.get(topic, 'anything')}"]
    words += [f"concerning {name(case, about)}"] if about else []
    words += [f"in {name(case, place)}"] if place else []
    words += [f"around {minutes(*when.interval)}"] if when else []
    return Query(kind="challenge" if presenting else "did_they" if subject else "did_you", subject=subject, location=place,
                 predicate_hint=topic or None, time=when, raw=f"I'd like to ask you {' '.join(words)}.")


def understood(case, query: Query) -> str:
    """The interpretation chip for a TYPED line (§12.1 stage 1): what the parser and grounding made of it, in plain words —
    names the player may already use, never anything the line did not carry."""
    parts = [query.kind.replace("_", " ")]
    parts += [f"about {TOPICS.get(query.predicate_hint, query.predicate_hint)}"] if query.predicate_hint else []
    parts += [f"concerning {name(case, r.id)}" for r in (query.subject, query.object) if r is not None]
    parts += [f"in {name(case, query.location)}"] if query.location else []
    parts += [f"when: “{query.time.text}”"] if query.time is not None else []
    return "understood as: " + ", ".join(parts)


def ask(save: Save, action_id: str, expected_seq: int, addressee: str, query: Query, *, present: str | None = None,
        accuse: bool = False, renderer=None, typed: bool = False, observed=None) -> Outcome:
    """`renderer` is stages 8-9 with a model (`llm.render.LLMRenderer`); absent, `TemplateLLM` renders. `typed`: the
    query came from free text through the parser, so the chip says how it was understood."""
    case = save.state.case
    if addressee not in save.state.characters:
        return Outcome("rejected", NOT_RECORDED)
    chip = f"To {name(case, addressee)}: “{query.raw}”" + (f" — {understood(case, query)}" if typed else "")
    if present:
        chip += f" — showing {_labels(save).get(present, 'something')}"
    if accuse:
        chip += " — and you accuse them"
    return _commit(save, action_id, expected_seq,
                   lambda st: run_ask_turn(st, addressee, query, presented_ref=present, provisional_accusation=accuse,
                                           confession_check=confession_gate(st, save.bundle.package), renderer=renderer),
                   chip=chip, say=lambda res: f"{name(case, addressee)}: {player_view(res).text}",
                   kind="say" if typed else "ask", character=addressee, observed=observed)


def goto(save: Save, action_id: str, expected_seq: int, location: str, *, observed=None) -> Outcome:
    where = name(save.state.case, location)
    return _commit(save, action_id, expected_seq, lambda st: run_goto_turn(st, location), chip=f"Go to {where}",
                   say=lambda res: f"You go to {where}.", kind="goto", observed=observed)


def search(save: Save, action_id: str, expected_seq: int, target: str, method: str, *, observed=None) -> Outcome:
    if method not in METHODS:
        return Outcome("rejected", NOT_RECORDED)
    return _commit(save, action_id, expected_seq, lambda st: run_search_turn(st, target, method),
                   chip=f"{method}: {name(save.state.case, target)}", say=lambda res: res.text, kind="search",
                   observed=observed)


def hypothesize(save: Save, action_id: str, expected_seq: int, propositions, confidence_bp: int, *,
                revise: str | None = None) -> Outcome:
    labels = _labels(save)
    chip = "Theory: " + "; ".join(describe(save, p, labels) for p in propositions)
    return _commit(save, action_id, expected_seq,
                   lambda st: run_hypothesis_turn(st, propositions, confidence_bp, revise=revise), chip=chip,
                   say=lambda res: "Noted in your notebook.", kind="hypothesis")


def withdraw(save: Save, action_id: str, expected_seq: int, hypothesis_id: str) -> Outcome:
    return _commit(save, action_id, expected_seq, lambda st: run_hypothesis_turn(st, withdraw=hypothesis_id),
                   chip="Withdraw a theory", say=lambda res: "Struck from your notebook.", kind="withdraw")


def accuse(save: Save, action_id: str, expected_seq: int, target: str, *, weapon: str | None = None,
           location: str | None = None, interval: tuple[int, int] | None = None, motive_kind: str | None = None,
           cited=()) -> Outcome:
    chip = f"You accuse {name(save.state.case, target)}, citing {len(tuple(cited))} item(s)"
    return _commit(save, action_id, expected_seq,
                   lambda st: run_accusation_turn(st, target, weapon=weapon, location=location, interval=interval,
                                                  motive_kind=motive_kind, cited=cited),
                   chip=chip, say=lambda res: "The case is closed.", kind="accuse")


# ------------------------------------------------------------------------------------ projections
def _tensions(save: Save, labels: dict[str, str]) -> list[dict]:
    """§13.4: a "tension" between two items the player HOLDS, never which side is true. Statement claims and evidence
    implications strong enough to contradict (§13.2) are compared pairwise; the flag is the detector's own
    `visible_to_player` (both sides held, no engine-only kind).
    ponytail: O(n²) over held propositions per render; cache by log head if a long session makes the page slow."""
    st, case = save.state, save.state.case
    held = frozenset(st.discovery.known_evidence | st.discovery.known_statements)     # both SIDES of a tension are held items
    claims = [(sid, c.proposition) for sid in sorted(st.discovery.known_statements)
              for c in st.decision.statements.get(sid).claims if c.proposition.kind != "Incidental"]   # engine-only kind
    found = [unlocked_view(st.evidence.get(e), st.discovery) for e in sorted(st.discovery.known_evidence)]   # H8-B1: unlocked only
    pairs: dict[tuple[str, str], None] = {}
    for i, (a, p) in enumerate(claims):
        for b, q in claims[i + 1:]:
            if a != b and (c := contradiction(p, q, a_id=a, b_id=b, case=case, player_material=held)) and c.visible_to_player:
                pairs[(a, b)] = None
        for ev in found:
            if any(evidence_implication_contradicts(imp, p, imp_id=ev.id, other_id=a, case=case) for imp in ev.implications):
                pairs[(a, ev.id)] = None
    for i, e1 in enumerate(found):
        for e2 in found[i + 1:]:
            if evidence_vs_evidence(e1, e2, case):        # §13.1: the planted-item tension, player-visible
                pairs[(e1.id, e2.id)] = None
    return [{"a": _ref_out(save, a), "b": _ref_out(save, b), "a_label": labels[a], "b_label": labels[b]} for a, b in pairs]


def motive_menu(save: Save) -> list[str]:
    """The vocabulary the case's motives were drawn from — never the case's own motives, which would name the answer."""
    skel = SKELETONS.get(save.bundle.package.skeleton_id)
    return sorted(skel.motive_menu) if skel else []


def player_objects(st) -> frozenset[str]:
    """The objects the player's own material names — the weapon and search-target lists. `solve.bots.held_names` is the
    V-7 bots' reading of the same thing and sees EVERY implication of a held item, locked ones included; this one goes
    through the unlocked view (H8-B1), over the statements the player heard."""
    names = Names()
    for e in st.discovery.known_evidence:
        if (ev := st.evidence.get(e)) is not None:
            names = names.union(names_from_evidence(st.case, unlocked_view(ev, st.discovery)))
    for sid in st.discovery.known_statements:
        for c in st.decision.statements.get(sid).claims:
            names = names.union(names_of_proposition(st.case, c.proposition))
    return names.objects


def notebook(save: Save) -> dict:
    """Everything the player holds, as they may see it — the statements they heard, the items they found, the tensions
    between them, their live theories — plus what the forms may offer: the cast and the house (public, §19.4), the
    objects their material names, the clock."""
    st, case = save.state, save.state.case
    labels = _labels(save)
    statements = sorted((st.decision.statements.get(i) for i in st.discovery.known_statements), key=lambda s: s.turn)
    hypotheses = []
    for h in st.decision.hypotheses:
        if h.status == "withdrawn":
            continue
        live = evaluate_hypothesis(h, st.evidence, st.decision.statements, st.discovery, st.turn_counter)
        hypotheses.append({"id": h.id, "text": "; ".join(describe(save, p, labels) for p in h.propositions),
                           "confidence": round(h.player_confidence * 100), "status": live.status,
                           "support": [labels[r] for r in live.support if r in labels],
                           "against": [labels[r] for r in live.against if r in labels]})
    objects = player_objects(st)
    solved = st.decision.solved
    return {
        "turn": st.turn_counter,
        "status": "open" if solved is None else "solved" if solved.correct else "failed",
        "statements": [{"ref": s.id, "turn": s.turn, "speaker": name(case, s.speaker), "text": s.text} for s in statements],
        "evidence": sorted(({"ref": handle(save, e), "label": labels[e], "text": st.evidence.get(e).discovery.reveals_text}
                            for e in st.discovery.known_evidence), key=lambda x: x["label"]),
        "tensions": _tensions(save, labels),
        "hypotheses": hypotheses,
        "people": [{"id": a, "name": name(case, a)} for a in sorted(st.characters)],
        "everyone": [{"id": a, "name": name(case, a)} for a in sorted(case.actors)],
        "places": [{"id": loc, "name": name(case, loc), "visited": loc in st.discovery.visited_locations}
                   for loc in sorted(case.locations)],
        "objects": [{"id": o, "name": name(case, o)} for o in sorted(objects)],
        "times": [{"bucket": b, "label": minutes(b * BUCKET, b * BUCKET + BUCKET)} for b in sorted(clock_buckets(case))],
        "methods": list(METHODS), "topics": dict(TOPICS), "motives": motive_menu(save),
        "clock_end": render_time(case.t_investigation),
    }


def establishes(save: Save, cited) -> bool:
    """§16.3's evidence axis: does the CITED set alone — under the same crediting rule the V-7 bots are held to (I-52) —
    make the proof's survivor the unique one at the case's fairness level (§19.5)?"""
    st, pkg = save.state, save.bundle.package
    verdict = evaluate(_solver_ctx(pkg), credited_material(st, only=frozenset(cited)), fairness=pkg.fairness_level,
                       want_cores=False)
    return verdict.unique and list(verdict.survivors) == [st.murderer]


def report(save: Save) -> dict | None:
    """§16.3 — after the verdict only. Five axes, each on its own: who (the proof's survivor), method (the weapon the
    CaseLog's attack used), place and time (the attack's room, and an overlapping window), motive (the murderer's motive
    in the CaseLog), evidence (`establishes`). Then the canonical timeline, with what the player found marked."""
    st, case = save.state, save.state.case
    if st.decision.solved is None:
        return None
    acc = next(a for a in reversed(st.decision.accusations) if not a.provisional)
    attack = next((e for e in case.events if e.kind == "Attack" and e.actor == st.murderer), None)
    motive = next((m.motive_kind for m in case.motives if m.actor == st.murderer), None)
    axes = {
        "who": acc.target == st.murderer,
        "method": attack is not None and acc.weapon is not None and acc.weapon in attack.objects,
        "place_and_time": attack is not None and acc.location == attack.location and acc.interval is not None
                          and overlaps(tuple(acc.interval), tuple(attack.interval)),
        "motive": motive is not None and acc.motive_kind == motive,
        "evidence": establishes(save, acc.cited),
    }
    found = {e.created_by for e in st.evidence.all() if e.id in st.discovery.known_evidence}
    timeline = [{"when": minutes(*e.interval), "kind": e.kind, "who": name(case, e.actor) if e.actor else "",
                 "where": name(case, e.location) if e.location else "", "found": e.id in found,
                 "with": ", ".join(name(case, x) for x in (*e.participants, *e.objects))}
                for e in sorted(case.events, key=lambda e: (e.interval[0], e.id)) if e.kind != "Stay"]
    return {
        "verdict": "solved" if st.decision.solved.correct else "failed",
        "accused": name(case, acc.target),
        "axes": axes,
        "truth": {"who": name(case, st.murderer), "weapon": ", ".join(name(case, o) for o in attack.objects) if attack else "?",
                  "where": name(case, attack.location) if attack else "?",
                  "when": minutes(*attack.interval) if attack else "?", "motive": motive or "?"},
        "timeline": timeline,
    }
