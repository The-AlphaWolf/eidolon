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


# ====================================================================== ADR-32: the proof breaks the last denial
def _put_everything_to_the_murderer(gate_for):
    """Show the murderer every held item and statement, one per turn, each turn folded by the store as it would be on append."""
    from eidolon.store import fold_turn
    sealed, st = _everything_held()
    murderer = st.murderer
    refs = sorted(st.discovery.known_evidence) + sorted(s.id for s in st.decision.statements.all() if s.speaker != murderer)
    q = Query(kind="challenge", raw="What do you make of this?")
    acts, permitted = [], []
    for ref in refs:
        gate = gate_for(st, sealed.package)
        r = run_ask_turn(st, murderer, q, presented_ref=ref, confession_check=gate)
        assert not r.rejected, r.violations
        fold_turn(st, r.events)                                  # the store accepts the turn exactly as the runner made it
        st = r.state
        murder = next(s for s in st.secrets.all() if s.kind == "murder")
        dm = st.characters[murderer].detective_model
        permitted.append(gate is not None and confession_permitted(gate, murder, murderer,
                                                                   frozenset(dm.known_evidence | dm.heard_statements), st.ctx()))
        acts.append(r.plan_act)
        if r.plan_act == "CONFESSION":
            break
    return acts, permitted


def test_ADR32_a_murderer_shown_a_proof_confesses_and_never_before():
    """F-3 / H9-I3: the murder cover's last denial (the blow) has no evidence breaker by design (§19.3 (i)), so with the gate
    wired the confession was still unreachable. ADR-32: a presented set that proves the confrontee the unique culprit breaks
    it. I-21 holds: no CONFESSION while the material shown does not prove them."""
    acts, permitted = _put_everything_to_the_murderer(game.confession_gate)
    assert acts[-1] == "CONFESSION", acts
    assert permitted[-1] and all(a != "CONFESSION" for a, p in zip(acts, permitted) if not p)
    assert "STONEWALL" not in acts, "short of a proof the last denial simply holds; nothing reaches the terminal to stonewall"


def test_ADR32_without_the_gate_nothing_confesses():
    acts, _ = _put_everything_to_the_murderer(lambda st, pkg: None)
    assert "CONFESSION" not in acts and "CONCESSION" in acts, acts


def test_ADR32_short_of_a_proof_the_last_denial_simply_holds():
    """Standing on the last denial with material that breaks layer 0 but proves nothing: the murderer neither confesses nor
    stonewalls - the denial holds, as any denial does when what is shown does not reach it (the gate is consulted, not
    obeyed blindly)."""
    sealed, st = _everything_held()
    murderer = st.murderer
    murder = next(s for s in st.secrets.all() if s.kind == "murder")
    breakers = sorted(r.evidence for r in murder.evidence_responses if r.layer == 0)   # the authored (V-3-derived) breaker set
    shown = [b if st.evidence.get(b) is not None else next(s.id for s in st.decision.statements.all() if b in s.accounts)
             for b in breakers]
    q = Query(kind="challenge", raw="What do you make of this?")
    acts = []
    for ref in shown + [shown[0]]:
        r = run_ask_turn(st, murderer, q, presented_ref=ref, confession_check=game.confession_gate(st, sealed.package))
        assert not r.rejected, r.violations
        st = r.state
        acts.append(r.plan_act)
    dm = st.characters[murderer].detective_model
    assert not confession_permitted(game.confession_gate(st, sealed.package), murder, murderer,
                                    frozenset(dm.known_evidence | dm.heard_statements), st.ctx()), "the layer-0 breakers are no proof"
    assert "CONCESSION" in acts and not {"CONFESSION", "STONEWALL"} & set(acts), acts
