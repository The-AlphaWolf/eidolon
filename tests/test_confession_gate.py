"""H9-I3 (= F-3 = H8-N9): the I-21 confession gate is wired in the shipped game. `game.ask` passes `game.confession_gate`, which
runs the solver on the material the player presented (the crediting rule of V-7 and the evidence axis); `peel.confession_permitted`
binds the verdict to the confrontee; `store._check_confession` refuses a forged confession (`H9I3_*` in `test_persistence.py`)."""
from __future__ import annotations

from pathlib import Path

from eidolon import game
from eidolon.decision.peel import confession_permitted
from eidolon.decision.query import Query
from eidolon.decision.turn import run_ask_turn
from eidolon.solve import bots
from eidolon.solve.package import load_sealed_case
from eidolon.solve.queries import expressible_queries, public_names
from eidolon.solve.session import new_session
from eidolon.store import Save

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "cases" / "generated" / "manor_wing_s4.json"      # its murder cover ends in a gated confession layer


def _everything_held():
    sealed = load_sealed_case(str(CASE))
    st, _, _ = bots._discover_all(new_session(sealed, seed=7))
    names = bots.held_names(st, public_names(st.case))
    for who in sorted(st.case.living_actors()):
        for q in expressible_queries(st.case, who, names):
            r = run_ask_turn(st, who, q)
            st = r.state if not r.rejected else st
    return sealed, st


def test_the_gate_opens_only_on_material_that_proves_the_confrontee_uniquely():
    sealed, st = _everything_held()
    pkg, murderer = sealed.package, st.murderer
    murder = next(s for s in st.secrets.all() if s.kind == "murder")
    check = game.confession_gate(st, pkg)
    everything = frozenset(st.discovery.known_evidence | {s.id for s in st.decision.statements.all()})
    assert confession_permitted(check, murder, murderer, everything, st.ctx()), "the whole case proves the murderer"
    assert not confession_permitted(check, murder, murderer, frozenset(), st.ctx()), "nothing presented proves nothing"
    other = next(a for a in sorted(st.case.living_actors()) if a != murderer)
    assert not confession_permitted(check, murder, other, everything, st.ctx()), "a proof licenses its survivor only"


def test_the_shipped_ask_control_passes_the_gate(tmp_path, monkeypatch):
    seen = {}
    real = game.run_ask_turn

    def spy(*a, **k):
        seen.update(k)
        return real(*a, **k)
    monkeypatch.setattr(game, "run_ask_turn", spy)
    s = Save.create(tmp_path / "g.db", CASE, seed=7)
    try:
        who = sorted(s.state.characters)[0]
        game.ask(s, "a@0", s.last_seq, who, Query(kind="where", raw="Where were you?"))
        assert callable(seen.get("confession_check")), "H9-I3: game.ask must pass the I-21 gate"
    finally:
        s.close()
