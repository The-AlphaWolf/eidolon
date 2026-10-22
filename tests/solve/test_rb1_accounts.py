"""RB-1 (Phase 6 re-audit): the murderer's cover could not be broken in real play, and a bare string could break
it anyway. Two trust boundaries, both closed here (ADR-23/24, I-49…I-51, I-60):

  * the IDENTITY boundary — one `requires` token meant three different things to P-9, the solver and V-3;
  * the ACQUISITION boundary — something the player never heard could unlock and peel.

Recorded RED on the pre-fix tree (design §E): presenting the bare string `clean@<hk>` peeled the murderer
(CONCESSION, 1 peel) and the housekeeper, asked about the cleaning, answered with her own cover LIE — so the
legitimate path never peeled anyone.
"""
from __future__ import annotations

import copy
from dataclasses import replace

import pytest

from eidolon.decision.claims import Claim, Statement, StatementStore
from eidolon.decision.exploration import AccountHeardEvent, StatementHeardEvent, apply_heard
from eidolon.decision.query import Query
from eidolon.decision.turn import run_ask_turn, run_search_turn
from eidolon.evidence.discovery import DiscoveryState
from eidolon.evidence.grounding import check_temporal_grounding
from eidolon.evidence.model import EvidenceStore
from eidolon.gen.compile import compile_draft
from eidolon.gen.pipeline import validate
from eidolon.gen.planner import plan
from eidolon.gen.skeletons import SKELETONS
from eidolon.minds import accounts
from eidolon.minds.knowledge import propagate_knowledge
from eidolon.minds.provenance import InvestigationTold
from eidolon.solve import bots
from eidolon.solve.lattice import Know, _resolve
from eidolon.solve.session import new_session
from tests.solve.helpers import GOLDEN, loaded

GOLD = pytest.mark.parametrize("skel,seed", GOLDEN)


def parts(skel, seed):
    p = loaded(skel, seed).package
    murder = next(s for s in p.secrets if s.kind == "murder")
    token = p.accounts[0]
    return p, murder, token, accounts.parse(token)[1]


def hear_token(p, state, token):
    """Ask the token's speaker every expressible question until the ENGINE commits a faithful delivery."""
    speaker = accounts.parse(token)[1]
    asked: set = set()
    acts: dict = {}
    for _ in range(3):
        names = bots.held_names(state, bots.public_names(p.case))
        state, *_ = bots._ask_batch(state, speaker, bots.expressible_queries(p.case, speaker, names), asked, acts, 10**6)
        if token in state.discovery.known_accounts:
            break
    return state


# --------------------------------------------------------------------------- legitimate play
@GOLD
def test_legit_play_peels_the_murderer_on_every_golden(skel, seed):
    """Real search, a real ask of the housekeeper through an expressible question, a real presentation: the murderer's
    layer 0 falls with `LayerPeel(0 -> 1)`. Nothing was pre-heard; the account is minted by the delivery alone."""
    p, murder, token, hk = parts(skel, seed)
    state = new_session(p)
    assert state.discovery.known_accounts == frozenset() and not state.decision.statements.all()
    state, _n, _found = bots._discover_all(state)
    assert token not in state.discovery.known_accounts
    state = hear_token(p, state, token)
    assert token in state.discovery.known_accounts, "the engine never let the housekeeper deliver her own account"
    delivered = next(s for s in state.decision.statements.all() if token in s.accounts)
    assert delivered.speaker == hk and delivered.act == "TRUTH"
    state2, act, peels, rej = bots._ask(state, murder.owner, Query(kind="challenge", raw="E_trace"), presented="E_trace")
    assert not rej and peels == 1 and act == "CONCESSION", (act, peels, rej)
    assert [(e.secret_id, e.from_index, e.to_index) for e in state2.decision.layer_peels] == [(murder.id, 0, 1)]


@GOLD
def test_the_murderer_peel_bot_succeeds_through_real_turns_only(skel, seed):
    p, murder, token, hk = parts(skel, seed)
    r = bots.murderer_peel_bot(p)
    assert r.ok and r.solved and r.peels == 1 and token in r.detail["accounts_heard"], r.to_json()


@GOLD
def test_no_peel_before_the_account_is_heard(skel, seed):
    """(guard) E_trace presented first — before anyone has delivered the cleaning — weighs nothing."""
    p, murder, token, hk = parts(skel, seed)
    state, _n, _f = bots._discover_all(new_session(p))
    _s, act, peels, rej = bots._ask(state, murder.owner, Query(kind="challenge", raw="E_trace"), presented="E_trace")
    assert not rej and peels == 0 and act != "CONCESSION"


# --------------------------------------------------------------------------- I-51: only held material is presentable
@GOLD
def test_presenting_an_account_token_is_rejected_with_no_state_change(skel, seed):
    """The auditor's attack: `present clean@<hk>` used to unlock E_trace and peel the murderer."""
    p, murder, token, hk = parts(skel, seed)
    state, _n, _f = bots._discover_all(new_session(p))
    res = run_ask_turn(state, murder.owner, Query(kind="challenge", raw=token), presented_ref=token)
    assert res.rejected and res.violations == ("UNHELD_PRESENTED_REF",)
    assert res.state is state and res.events == () and state.decision.layer_peels == ()


@pytest.mark.parametrize("ref", ["S99999", "", "   ", "clean@Nobody", "E_NO_SUCH_ITEM", "S00001"])
def test_presenting_an_unknown_or_unheld_id_is_rejected_not_raised(ref):
    p, murder, *_ = parts("study_party", 4)
    state = new_session(p)
    res = run_ask_turn(state, murder.owner, Query(kind="challenge", raw=ref), presented_ref=ref)
    assert res.rejected and res.violations == ("UNHELD_PRESENTED_REF",) and res.state is state


def test_presenting_evidence_with_unmet_prerequisites_rejects_instead_of_raising():
    """`E_trace` is gated on `E_scene`: presenting it cold used to raise ValueError out of `apply_discovery`."""
    p, murder, *_ = parts("study_party", 4)
    state = new_session(p)
    assert "E_trace" not in state.discovery.known_evidence
    res = run_ask_turn(state, murder.owner, Query(kind="challenge", raw="x"), presented_ref="E_trace")
    assert res.rejected and res.violations == ("UNHELD_PRESENTED_REF",) and res.state is state


# --------------------------------------------------------------------------- I-50: minted only by faithful delivery
def test_tokens_are_minted_only_by_faithful_delivery():
    p, murder, token, hk = parts("study_party", 4)
    ks = propagate_knowledge(p.case)
    entry = accounts.entries_of(p.case, ks, token)[0]
    truth = Claim(id="c", proposition=entry.proposition, sincerity="truthful", source="plan", grounding=(entry.id,))
    mint = lambda c, who=hk, k=ks: accounts.tokens_satisfied(p.case, k, c, who)
    assert mint(truth) == frozenset({token})                                   # a faithful TRUTH mints exactly it
    assert mint(truth.model_copy(update={"sincerity": "deceptive"})) == frozenset()          # a cover LIE
    assert mint(truth.model_copy(update={"grounding": ()})) == frozenset()                   # no grounding at all
    assert mint(truth.model_copy(update={"confidence": "unsure"})) == frozenset()            # a VAGUE hedge
    assert mint(truth.model_copy(update={"source": "slip"})) == frozenset()                  # a slip
    assert mint(truth.model_copy(update={"source": "incidental"})) == frozenset()
    assert mint(truth.model_copy(update={"modality": "hypothetical"})) == frozenset()
    shifted = entry.proposition.model_copy(update={"interval": (entry.proposition.interval[0] + 9,
                                                                entry.proposition.interval[1] + 9)})
    assert mint(truth.model_copy(update={"proposition": shifted})) == frozenset()            # a DISTORTED memory
    assert mint(truth, who=murder.owner) == frozenset()                                      # somebody else's perception
    # an InvestigationTold chain: the grounding entry lives only in the runtime overlay, never in the sealed store
    told = entry.model_copy(update={"id": "K_TOLD", "source": InvestigationTold(by_detective_turn=1)})
    chained = truth.model_copy(update={"grounding": (told.id,)})
    assert mint(chained) == frozenset()


def test_minting_through_the_real_engine_is_faithful_and_only_faithful():
    p, murder, token, hk = parts("study_party", 4)
    state, _n, _f = bots._discover_all(new_session(p))
    state = hear_token(p, state, token)
    minted = [s for s in state.decision.statements.all() if s.accounts]
    assert [s.accounts for s in minted] == [(token,)]
    assert all(s.speaker == hk and s.act == "TRUTH" for s in minted)
    # nobody else's statement, and no LIE/VAGUE/DONT_RECALL statement, ever carries a token
    assert all(not s.accounts for s in state.decision.statements.all() if s.act != "TRUTH")


# --------------------------------------------------------------------------- the session starts empty
@GOLD
def test_a_new_session_holds_nothing_and_applies_the_boosts(skel, seed):
    p, *_ = parts(skel, seed)
    st = new_session(p)
    assert st.decision.statements.all() == [] and st.discovery == DiscoveryState()
    assert st.discovery.known_statements == frozenset() and st.discovery.known_accounts == frozenset()
    boosts = {b.memory: b.strength_bp for b in p.memory_boosts}
    assert boosts, "the golden must carry boosts"
    seen = {m.id: m for ms in st.memories.values() for m in ms}
    assert all(seen[mid].strength_0 >= bp for mid, bp in boosts.items())


# --------------------------------------------------------------------------- the validating fold
def test_the_heard_fold_refuses_rows_the_ledger_does_not_back():
    p, murder, token, hk = parts("study_party", 4)
    empty = StatementStore()
    d0 = DiscoveryState()
    with pytest.raises(ValueError, match="not in the ledger"):
        apply_heard(d0, StatementHeardEvent(statement_id="S00001", turn=1), empty)
    with pytest.raises(ValueError, match="not in the ledger"):
        apply_heard(d0, AccountHeardEvent(token=token, statement_id="S00001", turn=1), empty)
    st = Statement(id="S00001", turn=1, speaker=hk, text="x", act="TRUTH", accounts=(token,))
    ledger = StatementStore([st])
    other = Statement(id="S00002", turn=2, speaker=murder.owner, text="x", act="TRUTH", accounts=(token,))
    with pytest.raises(ValueError, match="not an account of"):
        apply_heard(d0, AccountHeardEvent(token=token, statement_id="S00002", turn=2), ledger.add(other))   # wrong speaker
    unlisted = Statement(id="S00003", turn=3, speaker=hk, text="x", act="TRUTH", accounts=())
    with pytest.raises(ValueError, match="does not deliver"):
        apply_heard(d0, AccountHeardEvent(token=token, statement_id="S00003", turn=3), ledger.add(unlisted))   # unlisted
    ok = apply_heard(d0, AccountHeardEvent(token=token, statement_id="S00001", turn=1), ledger)
    assert ok.known_accounts == frozenset({token}) and apply_heard(ok, AccountHeardEvent(
        token=token, statement_id="S00001", turn=1), ledger) == ok                    # idempotent replay


def test_replaying_a_real_sessions_events_reproduces_the_heard_state_byte_for_byte():
    p, murder, token, hk = parts("study_party", 4)
    state, _n, _f = bots._discover_all(new_session(p))
    asked: set = set()
    log: list = []
    names = bots.held_names(state, bots.public_names(p.case))
    for q in bots.expressible_queries(p.case, hk, names)[:40]:
        res = run_ask_turn(state, hk, q)
        log += list(res.events)
        state = res.state
    assert token in state.discovery.known_accounts
    ledger, disc = StatementStore(), DiscoveryState()
    from eidolon.decision.events import ClaimMade
    for ev in log:
        if isinstance(ev, ClaimMade):
            ledger = ledger.add(ev.statement)
        elif isinstance(ev, (StatementHeardEvent, AccountHeardEvent)):
            disc = apply_heard(disc, ev, ledger)
    assert disc.known_accounts == state.discovery.known_accounts
    assert disc.known_statements == state.discovery.known_statements


def test_a_forged_heard_state_is_detected():
    from eidolon.decision.exploration import check_heard_state
    p, murder, token, hk = parts("study_party", 4)
    assert check_heard_state(DiscoveryState(), StatementStore()) == []
    forged = DiscoveryState(known_statements=frozenset({"S_note"}), known_accounts=frozenset({token}))
    bad = check_heard_state(forged, StatementStore())
    assert any("S_note" in b for b in bad) and any(token in b for b in bad)


# --------------------------------------------------------------------------- one resolver, every consumer
@GOLD
def test_one_resolver_four_consumers(skel, seed):
    p, murder, token, hk = parts(skel, seed)
    case = p.case
    atoms = accounts.atoms_of(case, token)
    assert atoms and accounts.token_interval(case, token) is not None
    assert token in accounts.token_intervals(case)
    # the solver's `requires` resolution hits exactly those atoms
    from eidolon.solve.lattice import know_atoms, material
    mat = material(p.evidence, {k.id: k for k in know_atoms(case)})
    hit = _resolve(case, mat, (token,), {})
    assert hit is not None and hit[0] in atoms
    # V-3 weighs the content a faithful delivery commits (proposition + grounding), derived from the same entries
    ks = propagate_knowledge(case)
    entries = accounts.entries_of(case, ks, token)
    assert {accounts.atom_of_entry(case, ks, e.id) for e in entries} == set(atoms)
    state, _n, _f = bots._discover_all(new_session(p))
    state = hear_token(p, state, token)
    said = next(s for s in state.decision.statements.all() if token in s.accounts)
    assert {(c.proposition, c.grounding) for c in said.claims if c.grounding} & {(e.proposition, (e.id,)) for e in entries}
    # P-9 rejects a token whose actor never participated (the old hull accepted any `event@participant` pair)
    ev_id = token.partition("@")[0]
    ghost = f"{ev_id}@{murder.owner}"
    assert ghost not in accounts.token_intervals(case)
    forged = next(e for e in p.evidence if e.id == "E_trace")
    imp = forged.implications[0].model_copy(update={"requires": (ghost,)})
    store = EvidenceStore([e if e.id != "E_trace" else e.model_copy(update={"implications": (imp,)}) for e in p.evidence])
    assert any("unresolved reference" in str(v) for v in check_temporal_grounding(case, store, accounts.token_intervals(case)))


def test_parse_is_total_and_fails_closed():
    for bad in (None, 3, "", "@", "a@", "@b", "no-at-sign", "a b@c", ["a@b"]):
        assert accounts.parse(bad) is None
    assert accounts.parse("clean@Elena") == ("clean", "Elena")
    assert accounts.parse("stay:A:0@Elena") == ("stay:A:0", "Elena")


# --------------------------------------------------------------------------- authored responses follow the tokens
def test_presented_delivered_statement_selects_the_authored_response():
    p, murder, token, hk = parts("study_party", 4)
    state, _n, _f = bots._discover_all(new_session(p))
    state = hear_token(p, state, token)
    sid = next(s.id for s in state.decision.statements.all() if token in s.accounts)
    res = run_ask_turn(state, murder.owner, Query(kind="challenge", raw="she says so"), presented_ref=sid)
    assert not res.rejected and res.plan_act == "DENY_EVIDENCE" and res.state.decision.layer_peels == ()


# --------------------------------------------------------------------------- the housekeeper is never the murderer (I-9, I-60)
@pytest.mark.parametrize("skel", sorted(SKELETONS))
def test_the_planner_never_makes_the_housekeeper_the_murderer(skel):
    sk = SKELETONS[skel]
    for seed in range(1, 101):
        dr = plan(sk, seed)
        if dr.error:
            continue
        assert dr.meta["hk"] != dr.murderer, (skel, seed)


def test_v3_rejects_a_breaker_that_rests_on_the_murderers_own_account():
    """I-60: with `M == hk` the only breaker set is {E_trace, clean@M} — the murderer broken by their own word."""
    sk = SKELETONS["study_party"]
    dr = plan(sk, 4)
    hk_name = dr.meta["hk"]
    forged = compile_draft(plan(sk, 4, murderer=hk_name))
    rep = validate(forged, bluffs=1, odd=1)
    assert rep.failed_at == "V-3", (rep.failed_at, rep.problems[:2])
    assert any("I-60" in x or "own account" in x or "no derivable breaker" in x for x in rep.problems), rep.problems[:3]


@GOLD
def test_breaker_account_memories_are_boosted_and_undistorted(skel, seed):
    p, murder, token, hk = parts(skel, seed)
    ks = propagate_knowledge(p.case)
    entries = {e.id for e in accounts.entries_of(p.case, ks, token)}
    from eidolon.solve import fairness as fair
    targets = {a for a in accounts.atoms_of(p.case, token)}
    behind = {m for m, _a in fair.memory_boosts_for(p, targets)}
    assert behind and behind <= {b.memory for b in p.memory_boosts}
    assert not (behind & {d.memory for d in p.distortions}) and entries


# --------------------------------------------------------------------------- tokens never reach the player-facing surfaces
def test_tokens_and_statement_accounts_never_reach_the_envelope_digest_or_player_view():
    from eidolon.llm.render import player_view
    p, murder, token, hk = parts("study_party", 4)
    state, _n, _f = bots._discover_all(new_session(p))
    asked: set = set()
    names = bots.held_names(state, bots.public_names(p.case))
    for q in bots.expressible_queries(p.case, hk, names):
        res = run_ask_turn(state, hk, q)
        if res.rejected:
            continue
        state = res.state
        assert token not in repr(res.envelope) and token not in repr(player_view(res)) and token not in res.text
    assert token in state.discovery.known_accounts


def test_the_legacy_unvalidated_heard_branch_is_never_used_by_production_code():
    """`apply_exploration(StatementHeardEvent)` survives only for the hand-authored Phase 4 fixtures that prime
    `known_statements`; nothing under `eidolon/` may call it (I-50, design §I.7)."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "eidolon"
    for f in root.rglob("*.py"):
        if f.name == "exploration.py":
            continue
        assert "StatementHeardEvent(" not in f.read_text(encoding="utf-8").replace("StatementHeardEvent(statement_id=statement_id", ""), f


def test_a_token_whose_observation_overlaps_its_speakers_unconceded_protected_interval_is_not_deliverable():
    """RB1-i / I-54 in V-3: round 0 of the availability fixpoint withholds what the speaker acquired inside their own
    protected interval until that secret is conceded."""
    from eidolon.decision.cover_consistency import _speakable_token
    from eidolon.solve.session import decision_context
    p, murder, token, hk = parts("study_party", 4)
    ctx = decision_context(p)
    ev = next(e for e in p.case.events if e.id == token.partition("@")[0])
    assert _speakable_token(token, ctx, {}, set())
    assert not _speakable_token(token, ctx, {hk: [ev.interval]}, set())          # overlapping and unconceded
    assert _speakable_token(token, ctx, {hk: [ev.interval]}, {hk})              # conceded: released
    assert _speakable_token(token, ctx, {hk: [(ev.interval[1] + 50, ev.interval[1] + 60)]}, set())   # disjoint
