"""Re-fold a save one turn at a time (the debug server's "state before/after" and "Replay (re-fold and diff)" views, §27.2).

Read-only: the save is opened `mode=ro`, verified by the store's own `_prepare`/chain check, and folded with the store's own
`fold_turn` - the SAME fold append and load use, so a diff here is a diff of what the engine believes, not a second reading.
"""
from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path

from .. import store
from ..decision.peel import layer_index
from ..solve.session import new_session
from ..store import SaveRefusal


def turn_states(path):
    """Yield `(turn, state)` after every committed turn, starting with `(0, initial state)`. Refuses exactly as `Save.open`
    does: a chain or fold failure raises `SaveRefusal` before anything is yielded past it."""
    p = Path(path)
    with contextlib.closing(sqlite3.connect(f"{p.resolve().as_uri()}?mode=ro", uri=True, isolation_level=None)) as conn:
        prep = store._prepare(conn, writable=False)
        rows = store._rows(conn)
        n, _, why = store._valid_prefix(rows, prep.genesis)
        if n != len(rows):
            raise SaveRefusal(f"{why}: refusing to replay past it", seq=n + 1, stage="chain")
        state = new_session(prep.bundle, seed=prep.seed)
        yield 0, state
        i = 0
        while i < len(rows):
            j = i
            while j < len(rows) and rows[j][1] == rows[i][1]:
                j += 1
            group = rows[i:j]
            evs = [store._decode(r[2], store._loads(r[4]), prep.version) for r in group]
            state = store.fold_turn(state, evs, group[0][3])
            yield group[0][1], state
            i = j


def summary(state) -> dict:
    """The parts of a state a person debugging a turn wants to compare, as plain numbers and ids."""
    layers = {}
    for who in state.characters:
        for sec in state.secrets.for_owner(who):
            layers[f"{who}/{sec.id}"] = layer_index(state.decision.layer_peels, who, sec.id)
    return {
        "turn": state.turn_counter,
        "state_hash": store.state_hash(state)[:16],
        "statements": len(state.decision.statements.all()),
        "layers": layers,
        "composure_bp": {a: c.composure for a, c in sorted(state.characters.items())},
        "verbal_pressure_bp": {f"{a}/{s}": v for a, c in sorted(state.characters.items()) for s, v in sorted(c.verbal_pressure.items())},
        "slips_used": sorted(s for c in state.characters.values() for s in c.slips_used),
        "detective_shown": {a: [len(c.detective_model.known_evidence), len(c.detective_model.heard_statements)]
                            for a, c in sorted(state.characters.items())},
        "known_evidence": len(state.discovery.known_evidence),
        "known_statements": len(state.discovery.known_statements),
        "known_accounts": len(state.discovery.known_accounts),
        "visited": len(state.discovery.visited_locations),
        "hypotheses": len(state.decision.hypotheses),
        "accusations": len(state.decision.accusations),
        "solved": None if state.decision.solved is None else state.decision.solved.correct,
    }


def diff(before: dict, after: dict) -> dict:
    """Only what changed, as `{key: (before, after)}`; nested dicts are compared entry by entry."""
    out = {}
    for k in after:
        a, b = before.get(k), after[k]
        if isinstance(b, dict) and isinstance(a, dict):
            sub = {kk: (a.get(kk), b.get(kk)) for kk in sorted(set(a) | set(b)) if a.get(kk) != b.get(kk)}
            if sub:
                out[k] = sub
        elif a != b:
            out[k] = (a, b)
    return out


def state_at(path, turn: int):
    for t, st in turn_states(path):
        if t == turn:
            return st
    return None


def before_after(path, turn: int):
    """`(state before turn, state after turn)` in ONE re-fold; `(None, None)` if there is no such turn."""
    prev = None
    for t, st in turn_states(path):
        if t == turn:
            return prev, st
        prev = st
    return None, None
