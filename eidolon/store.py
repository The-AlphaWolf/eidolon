"""Phase 7 — persistence (§26): `game.db` (SQLite) = the sealed case bundle + a hash-chained `session_events` log.
`traces.db` is a separate best-effort file that never travels with a save.

What makes a save trustworthy here is NOT the file: it is that `Save.open` re-derives everything.
  * the embedded bundle goes back through `load_sealed_text` — the one I-58 verifier, which re-runs the independent
    proof verifier; a stored proof is never trusted because it was written (I-58);
  * the hash chain (I-13, I-41) covers `{seq, turn, kind, action_id, payload}`, starts at a genesis hash that binds
    the case seal and the seed, and the meta head pins the tail (a deleted tail is a break, not a shorter save);
  * every payload is parsed by a closed kind registry and must re-serialize to exactly the stored text (no extra
    fields, no coercion, no float outside the two documented bp-hashed fields — I-17);
  * the FOLD is a validating one: it applies recorded outcomes only (I-22) but refuses a turn no runner could have
    produced — wrong shape (one statement by the addressee, its hearing rows), a peel nobody voiced, a retraction of
    somebody else's words, a grounding that is not the speaker's, an unresolvable secret / actor / place / item /
    accusation target, a detective model told more than it was shown, impossible provenance (I-8, I-15, I-50). The
    same `fold_turn` runs at append and at load, `check_state` included, so the two boundaries cannot disagree.
    The serialized identifier of a statement/account never makes it "heard"; only a committed turn does (ADR-24);
  * the genesis binds the case seal, the seed, the schema version and a digest of the DERIVED initial state
    (knowledge, beliefs, memories, personalities, initial character states): an engine that derives something else
    refuses an old save instead of replaying it into a different world (§26.4, PI-6).

`Save.open` builds everything locally and returns a `Save` only on success, so a failed load can mutate nothing.
Layering: this module sits above `solve` (it needs `new_session` and the sealed-case reader); nothing imports it.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
import sqlite3
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Callable

from pydantic import BaseModel

from .decision.claims import StatementStore
from .decision.events import (
    Accusation, CaseSolved, ClaimMade, ClaimRetracted, DecisionState, FallbackUsed, HypothesisChanged,
    IncidentalPinned, LayerPeel, MetaAttemptLogged, PlayerActionLogged, TurnCommitted, ValidationFailure,
    apply_decision,
)
from .decision.hypotheses import Lied, Planted
from .decision.exploration import (
    AccountHeardEvent, ItemTaken, LocationVisited, StatementHeardEvent, apply_exploration, apply_heard,
    check_heard_state, known_items, known_locations,
)
from .decision.peel import claims_voiced_on_peel, confession_gated, layer_index
from .decision.turn import CANARY, GameState, slips_voiced
from .evidence.discovery import Discovery, apply_discovery, check_discovery_state
from .minds import accounts as acct
from .minds.events import (
    BeliefRevised, ComposureChange, CoverStateDelta, DetectiveModelUpdate, EmotionalDelta, KnowledgeAdded,
    MemoryCorrected, MemoryRecall, PressureChange, SuspicionShift, TrustChange,
)
from .minds.fold import apply_character, apply_epistemic
from .minds.provenance import InvestigationTold
from .minds.scale import BP_MAX, bp
from .world.propositions import entities
from .solve.package import SealRefusal, load_sealed_text
from .solve.session import new_session

SCHEMA_VERSION = 1
ENGINE_VERSION = "eidolon-8.0"      # recorded in meta for diagnosis; what REFUSES a drifted engine is the initial-state digest
# ponytail: no upcaster framework until a second schema exists (§26.3). A row is upcast IN MEMORY, one version at a
# time, `fn(kind, payload) -> payload`; the file is never rewritten and the chain is verified over the stored bytes.
UPCASTERS: dict[int, Callable[[str, dict], dict]] = {}

_META_KEYS = {"schema_version", "case_id", "case_hash", "seed", "genesis", "head_seq", "head_hash", "engine_version",
              "initial_digest"}
_SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT;
CREATE TABLE case_bundle(id INTEGER PRIMARY KEY CHECK (id = 1), doc TEXT NOT NULL) STRICT;
CREATE TABLE session_events(seq INTEGER PRIMARY KEY, turn INTEGER NOT NULL, kind TEXT NOT NULL,
    action_id TEXT NOT NULL, payload TEXT NOT NULL, prev_hash TEXT NOT NULL, hash TEXT NOT NULL) STRICT;
CREATE INDEX session_events_action ON session_events(action_id);
"""


_TRACE_TABLE = "CREATE TABLE IF NOT EXISTS traces(turn INTEGER PRIMARY KEY, trace TEXT NOT NULL)"
_ABORTED_TABLE = "CREATE TABLE IF NOT EXISTS aborted(n INTEGER PRIMARY KEY AUTOINCREMENT, trace TEXT NOT NULL)"

# What no trace row may ever hold, whoever wrote it (defence in depth: `eidolon.trace` has already scrubbed its own text).
_CANARY_RE = re.compile(re.escape(CANARY), re.I)
_SECRET_RE = re.compile(r"sk-[A-Za-z0-9_\-]{16,}|Bearer\s+[A-Za-z0-9._\-]{16,}|(?i:api[_-]?key|token|secret)\s*[:=]\s*[A-Za-z0-9_.+/=\-]{8,}")


def scrub_secrets(x):
    """The canary and credential-shaped tokens, replaced by fixed words - in every STRING of `x`, never in serialized JSON (a
    pattern that spans a quote would eat the structure around it)."""
    if isinstance(x, str):
        return _SECRET_RE.sub("[secret]", _CANARY_RE.sub("[canary]", x))
    if isinstance(x, dict):
        return {scrub_secrets(k): scrub_secrets(v) for k, v in x.items()}
    if isinstance(x, list):
        return [scrub_secrets(v) for v in x]
    return x


class SaveError(Exception):
    """Base for every store failure."""


class SaveRefusal(SaveError, ValueError):
    """A save that must not be loaded, or an append that must not commit. `seq` is the first bad row when known;
    `stage` says which verification refused (meta / bundle / initial / genesis / chain / head / fold / state) — what
    `truncate_to_last_valid` diagnoses with, so recovery acts only on damage that cutting can repair."""
    def __init__(self, msg: str, seq: int | None = None, stage: str | None = None):
        super().__init__(msg)
        self.seq, self.stage = seq, stage


class StaleAppend(SaveError):
    """`expected_seq` is not the log's head: the caller computed this turn on old state and must recompute it."""


# ------------------------------------------------------------------------------------ canonical form
EVENT_MODELS: dict[str, type[BaseModel]] = {m.model_fields["kind"].default: m for m in (
    PlayerActionLogged, TurnCommitted, ClaimMade, ClaimRetracted, LayerPeel, IncidentalPinned, HypothesisChanged,
    Accusation, MetaAttemptLogged, ValidationFailure, FallbackUsed, CaseSolved,
    MemoryRecall, MemoryCorrected, BeliefRevised, KnowledgeAdded, EmotionalDelta, TrustChange, SuspicionShift,
    PressureChange, ComposureChange, CoverStateDelta, DetectiveModelUpdate,
    Discovery, LocationVisited, ItemTaken, StatementHeardEvent, AccountHeardEvent)}
_DECISION = {m.model_fields["kind"].default for m in (
    PlayerActionLogged, ClaimMade, ClaimRetracted, LayerPeel, IncidentalPinned, HypothesisChanged, Accusation,
    MetaAttemptLogged, ValidationFailure, FallbackUsed, CaseSolved)}
_EPISTEMIC = {"MemoryRecall", "MemoryCorrected", "BeliefRevised", "KnowledgeAdded"}
_CHARACTER = {"EmotionalDelta", "TrustChange", "SuspicionShift", "PressureChange", "ComposureChange",
              "CoverStateDelta", "DetectiveModelUpdate"}


def _plain(x):
    """JSON-ready, and ORDER-STABLE across processes: sets become sorted lists (a frozenset dumps in hash order,
    which varies with PYTHONHASHSEED), tuples become lists, models become dicts."""
    if isinstance(x, BaseModel):
        return _plain(x.model_dump(mode="python"))
    if isinstance(x, dict):
        return {str(k): _plain(v) for k, v in x.items()}
    if isinstance(x, (set, frozenset)):
        return sorted((_plain(v) for v in x), key=_canon)
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    return x


def _canon(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _row_hash(prev: str, seq: int, turn: int, kind: str, action_id: str, payload) -> str:
    """I-41: the FULL canonical row, not the payload alone."""
    return _sha(prev + _canon({"seq": seq, "turn": turn, "kind": kind, "action_id": action_id, "payload": payload}))


def _no_floats(x, path="state"):
    if isinstance(x, float):
        raise ValueError(f"float in authoritative state at {path} (I-17)")
    if isinstance(x, dict):
        for k, v in x.items():
            _no_floats(v, f"{path}.{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            _no_floats(v, f"{path}[{i}]")


def canonical_state(state: GameState) -> dict:
    """The authoritative runtime state (§26.3 step 5): everything a fold writes, nothing derived. The sealed stores,
    memories and `Personality` (a static float table derived from case + seed) are excluded — they are inputs to the
    fold, not outputs of it. `Hypothesis.player_confidence` is a float in the Phase 4 model (inherited I-17 debt); it
    is hashed as basis points so the hash itself is float-free."""
    d = state.decision
    decision = {f.name: (d.statements.all() if isinstance(getattr(d, f.name), StatementStore) else getattr(d, f.name))
                for f in fields(DecisionState)}
    doc = {"seed": state.seed, "turn": state.turn_counter,
           "characters": {a: c.model_dump(mode="python", exclude={"personality"}) for a, c in state.characters.items()},
           "epistemic": state.epistemic, "discovery": state.discovery, "decision": decision}
    doc = _plain(doc)
    for h in doc["decision"]["hypotheses"]:
        h["player_confidence"] = bp(h["player_confidence"])
    for e in doc["epistemic"]["added_knowledge"]:           # KnowledgeEntry.reliability is a 0..1 float (Phase 2 model)
        e["reliability"] = bp(e["reliability"])
    _no_floats(doc)
    return doc


def state_hash(state: GameState) -> str:
    return _sha(_canon(canonical_state(state)))


# ------------------------------------------------------------------------------------ the validating fold
def _refuse(msg: str, stage: str | None = None):
    raise SaveRefusal(msg, stage=stage)


def _owner_of_grounding(state: GameState, epistemic, gid: str):
    """-> the character a grounding id belongs to, or None when it resolves to nothing (I-8, I-27: grounding lives in the
    speaker's OWN stores)."""
    for store_ in (state.knowledge, state.beliefs):
        found = store_.get(gid)
        if found is not None:
            return found.character
    return next((e.character for e in epistemic.added_knowledge if e.id == gid), None)


def _check_proposition(state: GameState, prop, what: str) -> None:
    """Fail closed (I-15): a proposition may name only actors, places and objects the case (or a kit its evidence names)
    contains, at times inside the case's clock (`_check_times`). Structural; `truth_value` is not asked (I-22). `Saw.subject` is a literal by design and is not checked."""
    actors, places, things, either = entities(prop)
    pools = (("actor", actors, set(state.case.actors)), ("place", places, known_locations(state.case, state.evidence)),
             ("object", things, known_items(state.case, state.evidence)))
    for noun, named, pool in pools:
        if stray := sorted(named - pool):
            _refuse(f"{what} names {noun} {stray[0]!r}, which the case does not contain (I-15)", "fold")
    everything = pools[0][2] | pools[1][2] | pools[2][2]
    if stray := sorted(either - everything):
        _refuse(f"{what} names entity {stray[0]!r}, which the case does not contain (I-15)", "fold")
    _check_times(prop, state.case.t_investigation, what)


def _check_times(prop, horizon: int, what: str) -> None:
    """F-1: every time slot lies inside the case's own clock, `[0, t_investigation]`. `world.feasibility._compile` enumerates every
    tick of a standing `At`/`NotAt`, so an unbounded interval is an accepted row the engine cannot live with: the character's
    later turns slow down linearly or die with `MemoryError`. Authored data satisfies it (3,620 slots in the four generated cases)."""
    iv, tick = getattr(prop, "interval", None), getattr(prop, "t", None)
    if iv is not None and not 0 <= iv[0] < iv[1] <= horizon:
        _refuse(f"{what} has interval {tuple(iv)}, outside the case's clock [0, {horizon}] (I-15)", "fold")
    if tick is not None and not 0 <= tick <= horizon:
        _refuse(f"{what} has time {tick}, outside the case's clock [0, {horizon}] (I-15)", "fold")
    if prop.kind == "Said":
        _check_times(prop.proposition, horizon, what)


def _check_layer_scope(state: GameState, scope, owner, what: str) -> None:
    """A layer scope is `(secret, layer)`: a secret `owner` holds and a layer its cover has."""
    s = state.secrets.get(scope[0])
    if s is None or s.owner != owner or not 0 <= scope[1] < len(s.cover.layers):
        _refuse(f"{what} is scoped to a secret its speaker does not own, or to a layer that secret's cover does not have", "fold")


def _check_statement(state: GameState, epistemic, st, who, turn: int) -> None:
    if who is None or st.speaker != who or st.turn != turn or st.id != f"S{turn:05d}":
        _refuse(f"ClaimMade {st.id!r}: not this turn's statement by this turn's speaker")
    if st.retracted_by is not None:
        _refuse(f"ClaimMade {st.id!r} is born retracted")
    if st.layer_scope is not None:
        _check_layer_scope(state, st.layer_scope, who, f"ClaimMade {st.id!r}")
    if len({c.id for c in st.claims}) != len(st.claims):
        _refuse(f"ClaimMade {st.id!r} carries two claims with one id")
    delivered = frozenset().union(*[acct.tokens_satisfied(state.case, state.knowledge, c, st.speaker)
                                    for c in st.claims]) if st.claims else frozenset()
    if not set(st.accounts) <= delivered:
        _refuse(f"ClaimMade {st.id!r} lists accounts its claims do not deliver (I-50)")
    for c in st.claims:
        if c.statement != st.id:
            _refuse(f"claim {c.id!r} is not bound to its statement")
        _check_proposition(state, c.proposition, f"claim {c.id!r}")
        for g in c.grounding:
            owner = _owner_of_grounding(state, epistemic, g)
            if owner is None:
                _refuse(f"claim {c.id!r} is grounded in {g!r}, which resolves to nothing (I-8)")
            if owner != st.speaker:
                _refuse(f"claim {c.id!r} is grounded in {g!r}, which is {owner}'s, not its speaker's (I-27)")


def fold_turn(state: GameState, events, action_id: str | None = None) -> GameState:
    """One turn = one group opened by `TurnCommitted`. Applies recorded outcomes only (I-22): no weight, score,
    retrieval or model is consulted. Raises `SaveRefusal` for any turn that could not have been produced by a runner,
    and for one that leaves an unsound state. THE one function both `append` and `Save.open` run (PI-1)."""
    try:
        new = _fold_turn(state, events, action_id)
    except SaveError:
        raise
    except (ValueError, KeyError, TypeError) as e:     # the underlying folds raise these for impossible rows (I-15)
        raise SaveRefusal(f"turn does not fold: {e}", stage="fold") from e
    if problems := check_state(new):
        _refuse(f"turn leaves an unsound state: {problems[0]}", "fold")
    return new


def _fold_turn(state: GameState, events, action_id) -> GameState:
    events = tuple(events)
    if not events or not isinstance(events[0], TurnCommitted):
        _refuse("a turn must open with TurnCommitted", "fold")
    head = events[0]
    turn, who = head.turn, head.character
    if state.decision.solved is not None:
        _refuse("the case is already solved: no turn follows CaseSolved (PN-10)", "fold")
    if turn != state.turn_counter + 1:
        _refuse(f"turn {turn} does not follow turn {state.turn_counter}", "fold")
    if head.action_id is not None and head.action_id != action_id:
        _refuse(f"TurnCommitted names action {head.action_id!r}, but the turn is committed as {action_id!r}", "fold")
    if who is not None and who not in state.characters:
        _refuse(f"TurnCommitted names unknown character {who!r}", "fold")
    chars, decision, epi, disc = dict(state.characters), state.decision, state.epistemic, state.discovery
    made = None                                         # the one statement this turn committed
    heard: list[str] = []
    accounts: list[str] = []
    peels: list = []
    retracts = model_updates = 0
    rows_seen: set[str] = set()
    accused, final = False, None                        # this turn's provisional accusation / final accusation (§16.3)
    for ev in events[1:]:
        kind = ev.kind
        if decision.solved is not None:
            _refuse(f"{kind} after CaseSolved: nothing follows the verdict (PN-10)", "fold")
        if kind == "TurnCommitted":
            _refuse("two TurnCommitted rows in one turn", "fold")
        if getattr(ev, "turn", turn) != turn:
            _refuse(f"{kind} carries turn {ev.turn}, inside turn {turn}", "fold")
        if wrong := [t for t in (getattr(ev, "turn_id", turn), getattr(getattr(ev, "record", None), "turn_id", turn),
                                 getattr(getattr(ev, "revision", None), "turn_id", turn)) if t != turn]:
            _refuse(f"{kind} carries turn_id {wrong[0]}, inside turn {turn}", "fold")
        row = kind + _canon(_plain(ev))
        if row in rows_seen:
            _refuse(f"{kind} appears twice in one turn", "fold")
        rows_seen.add(row)
        if kind in _DECISION:
            if kind == "ClaimMade":
                if made is not None:
                    _refuse("two statements in one turn", "fold")
                _check_statement(state, epi, ev.statement, who, turn)
                made = ev.statement
            elif kind == "ClaimRetracted":
                _check_retraction(decision, ev, made, who)
                retracts += 1
            elif kind == "LayerPeel":
                _check_peel(state, decision, ev, who)
                peels.append(ev)
            elif kind == "MetaAttemptLogged" and ev.character != who:
                _refuse("MetaAttemptLogged for a character who was not addressed", "fold")
            elif kind == "Accusation":
                if ev.target not in state.characters and ev.target != "Outsider":
                    _refuse(f"Accusation of {ev.target!r}, who is not in the candidate domain", "fold")
                if ev.provisional:
                    if ev.target != who:                # (outside a conversation `who` is None)
                        _refuse("a provisional accusation is put to the addressee, inside a conversation turn (§16.3)", "fold")
                    if accused:
                        _refuse("two provisional accusations in one turn", "fold")
                    if ev.cited or (ev.weapon, ev.location, ev.interval, ev.motive_kind) != (None, None, None, None):
                        _refuse("a provisional accusation carries no solution form - that is a final accusation's (H8-N1)", "fold")
                    accused = True
                else:
                    if who is not None:
                        _refuse("a final accusation is a turn of its own, never part of a conversation (§16.3)", "fold")
                    if final is not None:
                        _refuse("two final accusations in one turn", "fold")
                    _check_accusation(state, disc, ev)
                    final = ev
            elif kind == "HypothesisChanged":
                held = disc.known_evidence | disc.known_statements
                if stray := [r for r in (*ev.hypothesis.support, *ev.hypothesis.against) if r not in held]:
                    _refuse(f"HypothesisChanged rests on {stray[0]!r}, which the player does not hold", "fold")
                _check_hypothesis(state, disc, ev.hypothesis)
                _check_board(decision, ev.hypothesis, who, turn)
            elif kind == "IncidentalPinned":
                if who is None or ev.speaker != who:
                    _refuse(f"IncidentalPinned by {ev.speaker!r}, who is not this turn's addressee", "fold")
                if ev.layer_scope is not None:
                    _check_layer_scope(state, ev.layer_scope, who, "IncidentalPinned")
            elif kind == "CaseSolved":                    # a second one is caught above: nothing follows the verdict
                _check_verdict(state, ev, final)
            decision = apply_decision(decision, ev)
        elif kind == "Discovery":
            disc = apply_discovery(disc, ev, state.evidence)
        elif kind in ("LocationVisited", "ItemTaken"):
            if who is not None:
                _refuse(f"{kind} inside a conversation turn", "fold")
            if kind == "LocationVisited" and ev.location not in known_locations(state.case, state.evidence):
                _refuse(f"LocationVisited {ev.location!r}: no such place", "fold")
            if kind == "ItemTaken" and ev.item not in known_items(state.case, state.evidence):
                _refuse(f"ItemTaken {ev.item!r}: no such item", "fold")
            disc = apply_exploration(disc, ev)
        elif kind in ("StatementHeard", "AccountHeard"):
            # ADR-24/I-50: hearing is a consequence of a commit made IN THIS TURN, never a standalone assertion.
            if made is None or ev.statement_id != made.id:
                _refuse(f"{kind} names {ev.statement_id!r}, which this turn did not commit", "fold")
            (heard if kind == "StatementHeard" else accounts).append(getattr(ev, "token", ev.statement_id))
            disc = apply_heard(disc, ev, decision.statements)
        elif kind in _EPISTEMIC:
            _check_epistemic_target(state, ev, who)
            if kind == "KnowledgeAdded":
                _check_told(state, chars, ev)
            epi = apply_epistemic(epi, ev)
        elif kind in _CHARACTER:
            if who is None:
                _refuse(f"{kind} outside a conversation turn", "fold")
            if kind == "DetectiveModelUpdate":
                model_updates += 1
                if model_updates > 1:
                    _refuse("two DetectiveModelUpdate rows in one turn", "fold")
            _check_character_row(state, chars, ev, who, turn, accused)
            if kind == "CoverStateDelta" and ev.refuse_streak is not None and ev.refuse_streak != (
                    chars[who].refuse_streak + 1 if made is not None and made.act == "REFUSE" else 0):
                _refuse("CoverStateDelta refuse_streak is not the run of consecutive REFUSE turns (§15.4)", "fold")
            if kind == "CoverStateDelta" and ev.slips_used is not None and frozenset(ev.slips_used) != (
                    chars[who].slips_used | (slips_voiced(made.act, made.claims) if made is not None else frozenset())):
                _refuse("CoverStateDelta slips_used is not the slips this turn voiced (§11.7)", "fold")
            chars[who] = apply_character(chars[who], ev)
        else:
            _refuse(f"event kind {kind!r} has no fold", "fold")
    if who is not None:                                 # a conversation turn: one statement, heard, with its accounts
        if made is None:
            _refuse("a conversation turn carries no statement", "fold")
        if heard != [made.id] or sorted(accounts) != sorted(made.accounts):
            _refuse(f"statement {made.id!r} is not heard exactly once with exactly its accounts", "fold")
    if peels:
        _check_peels_voiced(state, peels, made)
    if made is not None and made.act == "CONFESSION":
        _check_confession(state, decision, made, who)
    if retracts and not peels:
        _refuse("ClaimRetracted in a turn that peeled no layer", "fold")
    if accused and chars[who].detective_model.accusations[-1:] != ((turn, True, who),):
        _refuse("a provisional accusation the accused's detective model does not record (§11.3)", "fold")
    if final is not None and decision.solved is None:
        _refuse("a final accusation must close the case in the same turn (CaseSolved)", "fold")
    return replace(state, characters=chars, epistemic=epi, discovery=disc, decision=decision, turn_counter=turn)


def _check_retraction(decision: DecisionState, ev, made, who) -> None:
    """§11.4: a retraction withdraws the ADDRESSEE's own earlier, still-standing words, by this turn's statement."""
    if made is None or ev.retracted_by != made.id:
        _refuse(f"ClaimRetracted by {ev.retracted_by!r}, which this turn did not commit", "fold")
    if ev.statement_id == ev.retracted_by:
        _refuse("a statement cannot retract itself", "fold")
    old = decision.statements.get(ev.statement_id)
    if old is None or old.speaker != who or old.retracted_by is not None:
        _refuse(f"ClaimRetracted {ev.statement_id!r}: not a standing statement of the addressee", "fold")


def _check_peels_voiced(state: GameState, peels, made) -> None:
    """§11.4/I-15: whatever moved a cover said so — the turn's statement is a CONCESSION/CONFESSION that voices the layer
    it landed on. Structural only; no weight is recomputed (I-22)."""
    if made is None or made.act not in ("CONCESSION", "CONFESSION"):
        _refuse("LayerPeel in a turn whose statement is not a CONCESSION or CONFESSION", "fold")
    said = {c.id: c for c in made.claims}
    for ev in peels:
        owed = claims_voiced_on_peel(state.secrets.get(ev.secret_id).cover.layers[ev.to_index])
        if any(said.get(c.id) is None or said[c.id].model_copy(update={"statement": c.statement}) != c for c in owed):
            _refuse(f"LayerPeel of {ev.secret_id!r} to layer {ev.to_index} is not voiced by the turn's statement", "fold")


def _check_confession(state: GameState, decision: DecisionState, made, who) -> None:
    """H9-I3 / C-1 (c): a CONFESSION is the proven murderer (`GameState.murderer`, PI-7) standing at a GATED confession terminal
    of their own secret and saying exactly that layer's claims. Structural only (I-22): the uniqueness proof that opened the gate
    is the runner's (`game.confession_gate`); the fold checks that the record could have come from it, so a re-chained forger can
    no longer put a confession in anyone's mouth at any layer."""
    if state.murderer is None or who != state.murderer:
        _refuse("a CONFESSION by someone who is not the proven murderer", "fold")
    bare = lambda claims: tuple(c.model_copy(update={"statement": None}) for c in claims)        # noqa: E731
    for sec in state.secrets.for_owner(who):
        layer = sec.cover.layers[layer_index(decision.layer_peels, who, sec.id)]
        if layer.terminal == "confession" and confession_gated(sec, layer) and bare(made.claims) == bare(layer.claims):
            return
    _refuse("a CONFESSION that is not its speaker's gated confession layer, said exactly", "fold")


def _check_character_row(state: GameState, chars, ev, who, turn: int, accused: bool) -> None:
    kind = ev.kind
    if kind == "PressureChange":
        s = state.secrets.get(ev.secret_id)
        if s is None or s.owner != who:
            _refuse(f"PressureChange names secret {ev.secret_id!r}, which {who} does not own", "fold")
    elif kind == "SuspicionShift" and ev.target is not None and ev.target not in state.characters:
        _refuse(f"SuspicionShift names unknown actor {ev.target!r}", "fold")
    elif kind == "DetectiveModelUpdate":
        old, new = chars[who].detective_model, ev.new_model
        # §11.3: the model learns what was shown to THIS character and, in a turn whose provisional accusation was put to
        # them (seen above — the Accusation row precedes the minds rows), exactly that one accusation, at this turn.
        owed = old.accusations + (((turn, True, who),) if accused else ())
        if (new.accusations, new.probed_topics, new.estimated_suspicion_of_me, new.contradictions_confronted) != (
                owed, old.probed_topics, old.estimated_suspicion_of_me, old.contradictions_confronted):
            _refuse("DetectiveModelUpdate rewrites more than what the detective presented or said", "fold")
        added = (new.known_evidence - old.known_evidence) | (new.heard_statements - old.heard_statements)
        if not (old.known_evidence <= new.known_evidence and old.heard_statements <= new.heard_statements) or len(added) > 1:
            _refuse("DetectiveModelUpdate may add at most the one item presented, and forget nothing", "fold")
    elif kind == "CoverStateDelta":
        mine = {sl.id for s in state.secrets.for_owner(who) for sl in s.slips}
        if ev.slips_used is not None and not set(ev.slips_used) <= mine:
            _refuse(f"CoverStateDelta slips_used names a slip {who} does not have", "fold")
        if ev.contradictions_caught is not None and not set(ev.contradictions_caught) <= set(chars[who].contradictions_caught):
            _refuse("CoverStateDelta contradictions_caught names a contradiction nothing resolves", "fold")
        if (ev.refuse_streak or 0) < 0 or any(n < 0 for n in (ev.topics_probed or {}).values()):
            _refuse("CoverStateDelta carries a negative counter", "fold")


def _check_told(state: GameState, chars, ev) -> None:
    """I-25: what the detective tells a character is never more reliable than that character trusts the detective."""
    e = ev.entry
    if not isinstance(e.source, InvestigationTold):
        _refuse(f"KnowledgeAdded {e.id!r} must carry InvestigationTold provenance (I-27/AC-1)", "fold")
    if e.character not in chars:
        _refuse(f"KnowledgeAdded for unknown character {e.character!r}", "fold")
    _check_proposition(state, e.proposition, f"KnowledgeAdded {e.id!r}")
    if bp(e.reliability) > chars[e.character].trust_detective:
        _refuse(f"KnowledgeAdded {e.id!r}: reliability exceeds {e.character}'s trust in the detective (I-25)", "fold")


def _check_epistemic_target(state: GameState, ev, who) -> None:
    """An overlay row must be ABOUT something sealed AND about the addressee: a memory or belief the case derived for the
    character this turn spoke to. An exploration turn has no addressee (`who` is None), so it carries none. (The overlay
    folds copy a post-value onto whatever id they are given.)"""
    if ev.kind in ("MemoryRecall", "MemoryCorrected"):
        m = next((m for ms in state.memories.values() for m in ms if m.id == ev.memory_id), None)
        if m is None:
            _refuse(f"{ev.kind} names memory {ev.memory_id!r}, which the case never derived", "fold")
        if m.character != who:
            _refuse(f"{ev.kind} names {m.character}'s memory {ev.memory_id!r}, not about this turn's addressee ({who})", "fold")
        if ev.kind == "MemoryCorrected" and ev.field not in {d.field for d in m.distortions}:
            _refuse(f"MemoryCorrected names field {ev.field!r}, which memory {ev.memory_id!r} does not distort", "fold")
    elif ev.kind == "BeliefRevised":
        b = state.beliefs.get(ev.belief_id)
        if b is None:
            _refuse(f"BeliefRevised names belief {ev.belief_id!r}, which the case never derived", "fold")
        if b.character != who:
            _refuse(f"BeliefRevised names {b.character}'s belief {ev.belief_id!r}, not about this turn's addressee ({who})", "fold")
    elif ev.entry.character != who:
        _refuse(f"KnowledgeAdded for {ev.entry.character!r}, not about this turn's addressee ({who})", "fold")


def _check_hypothesis(state: GameState, disc, h) -> None:
    """The player's board may speculate only about what the case contains, and `Lied`/`Planted` only about material the
    player holds."""
    for p in h.propositions:
        if isinstance(p, Lied) and p.statement not in disc.known_statements:
            _refuse(f"hypothesis {h.id!r}: Lied names statement {p.statement!r}, which the player does not hold", "fold")
        if isinstance(p, Lied) and state.decision.statements.get(p.statement).speaker != p.actor:
            _refuse(f"hypothesis {h.id!r}: Lied names statement {p.statement!r}, which is not {p.actor}'s", "fold")
        if isinstance(p, Planted) and p.evidence not in disc.known_evidence:
            _refuse(f"hypothesis {h.id!r}: Planted names evidence {p.evidence!r}, which the player does not hold", "fold")
        _check_proposition(state, p, f"hypothesis {h.id!r}")


def _check_board(decision: DecisionState, h, who, turn: int) -> None:
    """§16.1 (Phase 8): a board edit is a turn of its own and is tied to it (F-3) — created now, or revised with its
    creation turn intact — and a withdrawn entry is never edited again (withdrawal is the board's removal)."""
    if who is not None:
        _refuse(f"HypothesisChanged {h.id!r} inside a conversation turn", "fold")
    if h.updated_turn != turn:
        _refuse(f"hypothesis {h.id!r} has updated_turn {h.updated_turn}, inside turn {turn} (F-3)", "fold")
    old = next((x for x in decision.hypotheses if x.id == h.id), None)
    if old is None and (h.created_turn != turn or h.status == "withdrawn"):
        _refuse(f"hypothesis {h.id!r} is new: it must be created in this turn, and not withdrawn (F-3)", "fold")
    if old is not None and (old.status == "withdrawn" or h.created_turn != old.created_turn):
        _refuse(f"hypothesis {h.id!r} revises a withdrawn entry or rewrites its creation turn", "fold")


def _check_accusation(state: GameState, disc, ev) -> None:
    """§16.3: a final accusation's form names only what the case contains, inside its clock, and cites only HELD material
    — the support of an accusation is what the player legitimately acquired (I-15). The score is not checked here: it is
    the case report's, a projection, and never stored."""
    held = disc.known_evidence | disc.known_statements
    if stray := [r for r in ev.cited if r not in held]:
        _refuse(f"Accusation cites {stray[0]!r}, which the player does not hold", "fold")
    if ev.weapon is not None and ev.weapon not in known_items(state.case, state.evidence):
        _refuse(f"Accusation names weapon {ev.weapon!r}, which the case does not contain (I-15)", "fold")
    if ev.location is not None and ev.location not in known_locations(state.case, state.evidence):
        _refuse(f"Accusation names place {ev.location!r}, which the case does not contain (I-15)", "fold")
    _check_times(ev, state.case.t_investigation, "Accusation")


def _check_verdict(state: GameState, ev, final) -> None:
    """PN-10: the verdict is derived, never trusted — it closes the turn of a final accusation, and `correct` must be what
    that accusation's target IS against the proof's verified unique survivor (`GameState.murderer`, PI-7)."""
    if final is None:
        _refuse("CaseSolved without a final accusation in this turn (PN-10)", "fold")
    if state.murderer is None:
        _refuse("CaseSolved in a case with no proven murderer to judge against (PN-10)", "fold")
    if ev.correct != (final.target == state.murderer):
        _refuse(f"CaseSolved.correct={ev.correct} disagrees with the proven murderer (PN-10)", "fold")


def _check_peel(state: GameState, decision: DecisionState, ev, who) -> None:
    """Structural only (a weight is never recomputed, I-22): the peel is for the addressed character's own secret,
    starts where the folded index stands and stays inside the cover."""
    s = state.secrets.get(ev.secret_id)
    if s is None or s.owner != ev.character or ev.character != who:
        _refuse(f"LayerPeel of {ev.secret_id!r} by {ev.character!r} is not the addressee's own secret", "fold")
    if ev.from_index != layer_index(decision.layer_peels, ev.character, ev.secret_id) \
            or not ev.from_index < ev.to_index < len(s.cover.layers):
        _refuse(f"LayerPeel {ev.from_index}->{ev.to_index} does not continue the recorded cover state", "fold")


def check_state(state: GameState) -> list[str]:
    """Soundness of a whole folded state (the hearing/discovery checks Phases 3-4 wrote for exactly this): a
    character cannot have been shown evidence the player never found, or heard a statement that is not on the record."""
    problems = check_discovery_state(state.discovery, state.evidence) + check_heard_state(state.discovery, state.decision.statements)
    for a, c in sorted(state.characters.items()):
        dm = c.detective_model
        problems += [f"{a}: detective model holds evidence {i!r} the player never discovered"
                     for i in sorted(dm.known_evidence - state.discovery.known_evidence)]
        problems += [f"{a}: detective model heard {i!r}, which is not on the record"
                     for i in sorted(dm.heard_statements) if state.decision.statements.get(i) is None]
    return problems


# ------------------------------------------------------------------------------------ rows
# I-17: the ONLY floats a payload may carry are the two Phase 2/4 models that still hold a 0..1 float. Each must be a
# basis-point value exactly (so `bp()` is lossless: 0.50001 and 0.5 can never hash alike), and both are range-checked.
_FLOAT_FIELDS = {"HypothesisChanged": ("hypothesis", "player_confidence"), "KnowledgeAdded": ("entry", "reliability")}


def _check_floats(kind: str, obj) -> None:
    def walk(x, path):
        if isinstance(x, float):
            if path != _FLOAT_FIELDS.get(kind) or bp(x) / BP_MAX != x:     # on the grid <=> inside 0..1 (bp clamps)
                _refuse(f"{kind} carries a float at {'.'.join(path) or 'the root'} (I-17)")
        elif isinstance(x, dict):
            for k, v in x.items():
                walk(v, path + (str(k),))
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v, path)
    walk(obj, ())


def _encode(ev) -> tuple[str, str]:
    """-> (kind, canonical payload). Refuses what would not survive a reload (fail closed at WRITE time)."""
    kind = getattr(ev, "kind", None)
    model = EVENT_MODELS.get(kind)
    if model is None or type(ev) is not model:
        _refuse(f"unknown event {type(ev).__name__}")
    try:
        payload = _plain(ev)
        _check_floats(kind, payload)
        round_trips = _canon(_plain(model.model_validate(payload))) == _canon(payload)
    except SaveError:
        raise
    except (ValueError, TypeError) as e:
        raise SaveRefusal(f"{kind} does not validate: {type(e).__name__}") from e
    if not round_trips:
        _refuse(f"{kind} does not round-trip")
    return kind, _canon(payload)


def _decode(kind: str, obj, version: int):
    for v in range(version, SCHEMA_VERSION):
        if v not in UPCASTERS:
            _refuse(f"schema_version {version} has no upcaster to {SCHEMA_VERSION}")
        obj = UPCASTERS[v](kind, obj)
    model = EVENT_MODELS.get(kind)
    if model is None:
        _refuse(f"unknown event kind {kind!r}")
    if not isinstance(obj, dict) or obj.get("kind") != kind:
        _refuse(f"payload is not a {kind}")
    _check_floats(kind, obj)
    ev = model.model_validate(obj)
    if _canon(_plain(ev)) != _canon(obj):
        _refuse(f"{kind} payload carries fields or values the schema does not")
    return ev


def _micro(x):
    """Floats in the DERIVED initial state (personalities, a belief's grounds weights…) are digested as integer
    millionths: the digest must survive a different libm in the last ulp, and must still move when a derivation does.
    ponytail: a value that straddles a millionth boundary across machines would false-refuse; widen if X1 shows it."""
    if isinstance(x, float):
        return round(x * 1_000_000)
    if isinstance(x, dict):
        return {k: _micro(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_micro(v) for v in x]
    return x


def initial_digest(state: GameState) -> str:
    """PI-6: a digest of everything `new_session` DERIVES from (case, seed) and the fold then reads but no row carries —
    knowledge, beliefs, memories (after boosts), personalities and the initial character states. Bound into the genesis,
    so an engine whose derivation changed refuses an old save instead of silently replaying it into another world."""
    actors = sorted(state.characters)
    doc = {"knowledge": sorted((_plain(e) for e in state.knowledge.all()), key=_canon),
           "beliefs": [_plain(b) for a in actors for b in sorted(state.beliefs.for_character(a), key=lambda b: b.id)],
           "memories": {a: [_plain(m) for m in state.memories.get(a, ())] for a in actors},
           "characters": {a: _plain(state.characters[a]) for a in actors}}
    return _sha(_canon(_micro(doc)))


def _genesis(case_hash: str, seed: int, version: int, initial: str) -> str:
    """Binds the case seal, the seed, the schema version the file was CREATED under, and the derived initial state."""
    return _sha(_canon({"case": case_hash, "seed": seed, "schema": version, "initial": initial}))


def _loads(text: str):
    """Strict JSON: NaN / Infinity are not JSON (I-17)."""
    def bad(c):
        raise ValueError(f"non-finite number {c}")
    return json.loads(text, parse_constant=bad)


def _valid_prefix(rows, genesis: str) -> tuple[int, str, str]:
    """-> (n rows whose chain verifies, hash after them, why the next one does not). Pure; never raises on bad data. A
    row also breaks the chain if its stored text is not the canonical text of what it parses to (so a payload with a
    duplicate key, reordered keys or a `\\u` escape is not the row that was hashed)."""
    prev = genesis
    for i, r in enumerate(rows, 1):
        if not (len(r) == 7 and isinstance(r[0], int) and isinstance(r[1], int) and all(isinstance(x, str) for x in r[2:])):
            return i - 1, prev, f"row {i}: malformed"
        seq, turn, kind, aid, payload, ph, h = r
        try:
            obj = _loads(payload)
            ok = payload == _canon(obj) and h == _row_hash(prev, seq, turn, kind, aid, obj)
        except (ValueError, TypeError, RecursionError):
            return i - 1, prev, f"row {i}: payload is not JSON"
        if seq != i or ph != prev or not ok:
            return i - 1, prev, f"row {i}: hash chain breaks"
        prev = h
    return len(rows), prev, ""


@dataclass(frozen=True)
class _Prepared:
    meta: dict
    version: int
    seed: int
    bundle: object
    genesis: str            # RECOMPUTED from the embedded case, the seed, the schema version and the derived initial state


def _prepare(conn, writable: bool) -> _Prepared:
    """Everything a load verifies BEFORE it looks at a single log row. Each refusal names its stage."""
    meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
    if set(meta) != _META_KEYS:
        _refuse("meta is not the schema's", "meta")
    try:
        version, seed = int(meta["schema_version"]), int(meta["seed"])
    except ValueError:
        _refuse("meta schema_version / seed are not integers", "meta")
    if str(version) != meta["schema_version"] or str(seed) != meta["seed"]:
        _refuse("meta schema_version / seed are not in canonical form", "meta")
    if version > SCHEMA_VERSION:
        _refuse(f"save is schema_version {version}; this engine reads up to {SCHEMA_VERSION}", "meta")
    if version < 1:
        _refuse("schema_version below 1", "meta")
    if writable and version < SCHEMA_VERSION:
        # An append would write the NEW spelling under the OLD label, and the next load would upcast it a second time.
        _refuse(f"save is schema_version {version}, this engine writes {SCHEMA_VERSION}: it opens read-only until migrated", "meta")
    docs = conn.execute("SELECT doc FROM case_bundle").fetchall()
    if len(docs) != 1:
        _refuse("a save embeds exactly one case bundle", "bundle")
    try:
        bundle = load_sealed_text(docs[0][0])          # seals, independent proof verifier, full-scale report
    except SealRefusal as e:
        raise SaveRefusal(f"embedded case refused: {e}", stage="bundle") from e
    if meta["case_hash"] != bundle.package.seal or meta["case_id"] != bundle.package.id:
        _refuse("meta names a different case than the embedded one (I-4)", "bundle")
    digest = initial_digest(new_session(bundle, seed=seed))
    if meta["initial_digest"] != digest:
        _refuse(f"the initial world this engine derives from the case and seed is not the one the save was made in "
                f"(recorded engine {meta['engine_version']!r}, this engine {ENGINE_VERSION!r}): refusing to replay it", "initial")
    return _Prepared(meta, version, seed, bundle, _genesis(bundle.package.seal, seed, version, digest))


def _rows(conn):
    return conn.execute("SELECT seq, turn, kind, action_id, payload, prev_hash, hash FROM session_events ORDER BY seq").fetchall()


def _replay(conn, prep: _Prepared, rows=None):
    """Verify the genesis, the chain, the head pin, every row and the fold. -> (state, rows, last_hash, actions).
    Reads only; raises `SaveRefusal` naming its stage."""
    meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
    if meta["genesis"] != prep.genesis:
        _refuse("genesis hash does not bind this case, seed, schema and initial state", "genesis")
    rows = _rows(conn) if rows is None else rows
    n, last_hash, why = _valid_prefix(rows, meta["genesis"])
    if n != len(rows):
        raise SaveRefusal(f"{why}: refusing to load past it (I-13)", seq=n + 1, stage="chain")
    if (str(len(rows)), last_hash) != (meta["head_seq"], meta["head_hash"]):
        raise SaveRefusal(f"log ends at seq {len(rows)} but the head records seq {meta['head_seq']}: "
                          f"rows were removed or added outside the store", seq=len(rows) + 1, stage="head")
    state = new_session(prep.bundle, seed=prep.seed)
    actions: dict[str, tuple[int, int, int]] = {}
    i = 0
    while i < len(rows):
        j = i
        while j < len(rows) and rows[j][1] == rows[i][1]:
            j += 1
        group = rows[i:j]
        try:
            if len({r[3] for r in group}) != 1 or group[0][3] in actions or not group[0][3]:
                _refuse("a turn's rows share one fresh, non-empty action_id", "fold")
            evs = [_decode(r[2], _loads(r[4]), prep.version) for r in group]
            if evs[0].kind != "TurnCommitted" or evs[0].turn != group[0][1]:
                _refuse("row turn does not match its TurnCommitted", "fold")
            state = fold_turn(state, evs, group[0][3])
            actions[group[0][3]] = (group[0][1], group[0][0], group[-1][0])
        except SaveRefusal as e:
            raise SaveRefusal(f"seq {group[0][0]}: {e}", seq=group[0][0], stage=e.stage or "fold") from e
        i = j
    try:
        state_hash(state)                               # a state that cannot be hashed cannot be compared (I-17)
    except ValueError as e:
        raise SaveRefusal(f"folded state cannot be hashed: {e}", stage="state") from e
    return state, rows, last_hash, actions


@dataclass(frozen=True)
class TurnRef:
    """Where a committed turn sits in the log: what a duplicate `action_id` resolves to (§26.2)."""
    turn: int
    first_seq: int
    last_seq: int


class AppendResult:
    def __init__(self, appended: bool, last_seq: int, ref: TurnRef | None = None, same_events: bool | None = None,
                 trace_written: bool | None = None):
        self.appended, self.last_seq, self.ref = appended, last_seq, ref
        self.same_events = same_events      # duplicates only: do the retried events equal the committed ones?
        self.trace_written = trace_written  # None: no trace was offered; False: it was lost AFTER the commit (§27.1)


class Save:
    """An open save: the folded `state` plus the log head. Mutated only by a successful `append`."""

    def __init__(self, path, conn, writable, bundle, seed, state, last_seq, last_hash, actions):
        self.path, self._conn, self.writable = Path(path), conn, writable
        self.bundle, self.seed, self.state = bundle, seed, state
        self.last_seq, self.last_hash = last_seq, last_hash
        self._actions: dict[str, tuple[int, int, int]] = actions        # action_id -> (turn, first seq, last seq)

    @property
    def _turns(self) -> set[int]:
        return {t for t, _, _ in self._actions.values()}

    @property
    def trace_path(self) -> Path:
        return self.path.with_suffix(".traces.db")

    def state_hash(self) -> str:
        return state_hash(self.state)

    def turn_for(self, action_id: str) -> TurnRef | None:
        """§26.2: the committed turn an `action_id` produced (a client retrying after a lost response asks this)."""
        found = self._actions.get(action_id)
        return TurnRef(*found) if found else None

    def close(self) -> None:
        self._conn.close()

    # ---------------------------------------------------------------- create
    @classmethod
    def create(cls, path, bundle_path, *, seed: int = 0) -> "Save":
        """A new save from a sealed-case FILE. The bundle is verified (seals + independent proof verifier) before a byte
        is written; the file appears atomically or not at all."""
        path = Path(path)
        if path.exists():
            raise SaveError(f"{path} already exists")
        text = Path(bundle_path).read_text(encoding="utf-8")
        case = load_sealed_text(text)                      # raises SealRefusal
        digest = initial_digest(new_session(case, seed=seed))
        stale = path.with_name(path.stem + ".traces.db")
        if stale.exists():                     # H9-N2: a sidecar left by an earlier game of this name is not this game's
            n = 1
            while stale.with_name(f"{stale.name}.stale-{n}").exists():
                n += 1
            stale.rename(stale.with_name(f"{stale.name}.stale-{n}"))
        tmp = path.with_name(path.name + ".tmp")
        tmp.unlink(missing_ok=True)
        with contextlib.closing(sqlite3.connect(tmp, isolation_level=None)) as c:
            c.executescript(_SCHEMA)
            c.execute("INSERT INTO case_bundle VALUES (1, ?)", (text,))
            g = _genesis(case.package.seal, seed, SCHEMA_VERSION, digest)
            c.executemany("INSERT INTO meta VALUES (?, ?)", [
                ("schema_version", str(SCHEMA_VERSION)), ("case_id", case.package.id), ("case_hash", case.package.seal),
                ("seed", str(seed)), ("genesis", g), ("head_seq", "0"), ("head_hash", g),
                ("engine_version", ENGINE_VERSION), ("initial_digest", digest)])
        os.replace(tmp, path)
        return cls.open(path, writable=True)

    # ---------------------------------------------------------------- load (§26.3)
    @classmethod
    def open(cls, path, *, writable: bool = False) -> "Save":
        """Read-only unless `writable` (I-23), and verified end to end: bundle, initial state, chain, every row, the fold,
        the final state. Raises `SaveRefusal` and nothing else."""
        p = Path(path)
        if not p.is_file():
            raise SaveRefusal(f"no such save: {p}")
        conn = None
        try:
            conn = sqlite3.connect(f"{p.resolve().as_uri()}?mode={'rw' if writable else 'ro'}", uri=True,
                                   isolation_level=None)
            save = cls._load(p, conn, writable)
        except SaveError:
            if conn is not None:
                conn.close()
            raise
        except Exception as e:                                             # noqa: BLE001 - corrupt/truncated/odd files
            if conn is not None:
                conn.close()
            raise SaveRefusal(f"unreadable save: {type(e).__name__}: {e}") from e
        if not writable:
            conn.close()
        return save

    @classmethod
    def _load(cls, p, conn, writable) -> "Save":
        prep = _prepare(conn, writable)
        state, rows, last_hash, actions = _replay(conn, prep)
        return cls(p, conn, writable, prep.bundle, prep.seed, state, len(rows), last_hash, actions)

    # ---------------------------------------------------------------- append (§26.2, the only write path)
    def append(self, events, expected_seq: int, action_id: str, *, trace: dict | None = None) -> AppendResult:
        """One turn, one transaction. Duplicate `action_id` -> `AppendResult(appended=False)` carrying the EXISTING
        turn's `ref` (nothing written). `expected_seq` / the head hash != the log's head -> `StaleAppend`. A turn the
        validating fold refuses commits nothing and leaves `self.state` untouched (I-15)."""
        if not self.writable:
            raise SaveError("save was opened read-only")
        if not isinstance(action_id, str) or not action_id:
            raise SaveRefusal("action_id must be a non-empty string")
        events = tuple(events)
        c = self._conn
        c.execute("BEGIN IMMEDIATE")
        try:
            hit = c.execute("SELECT turn, MIN(seq), MAX(seq) FROM session_events WHERE action_id = ?", (action_id,)).fetchone()
            if hit[1] is not None:
                stored = c.execute("SELECT kind, payload FROM session_events WHERE action_id = ? ORDER BY seq",
                                   (action_id,)).fetchall()
                c.execute("ROLLBACK")
                try:
                    same = [_encode(ev) for ev in events] == stored
                except SaveRefusal:
                    same = False
                return AppendResult(False, hit[2], TurnRef(*hit), same)
            head = int(c.execute("SELECT value FROM meta WHERE key = 'head_seq'").fetchone()[0])
            head_hash = c.execute("SELECT value FROM meta WHERE key = 'head_hash'").fetchone()[0]
            if head != expected_seq or head != self.last_seq or head_hash != self.last_hash:
                raise StaleAppend(f"head is seq {head}, caller expected {expected_seq}")
            encoded = [_encode(ev) for ev in events]
            new_state = fold_turn(self.state, events, action_id)
            turn = events[0].turn
            prev, seq = self.last_hash, self.last_seq
            out = []
            for kind, payload in encoded:
                seq += 1
                h = _row_hash(prev, seq, turn, kind, action_id, json.loads(payload))
                out.append((seq, turn, kind, action_id, payload, prev, h))
                prev = h
            c.executemany("INSERT INTO session_events VALUES (?, ?, ?, ?, ?, ?, ?)", out)
            c.execute("UPDATE meta SET value = ? WHERE key = 'head_seq'", (str(seq),))
            c.execute("UPDATE meta SET value = ? WHERE key = 'head_hash'", (prev,))
            c.execute("COMMIT")
        except BaseException:
            if c.in_transaction:
                c.execute("ROLLBACK")
            raise
        first = self.last_seq + 1
        self.state, self.last_seq, self.last_hash = new_state, seq, prev
        self._actions[action_id] = (turn, first, seq)
        written = self.write_trace(turn, trace) if trace is not None else None
        return AppendResult(True, seq, TurnRef(turn, first, seq), trace_written=written)

    def write_trace(self, turn: int, trace) -> bool:
        """§27.1: AFTER the commit, best-effort, to a separate file (one transaction cannot span two database files). A
        failure here loses an audit row, never a turn; it is reported as `False` and logged by CODE only (an exception's
        message may carry the very text that failed). The text is scrubbed of the canary and of credential-shaped tokens
        on the way in, whoever the caller is."""
        return self._trace_insert("INSERT OR REPLACE INTO traces(turn, trace) VALUES (?, ?)", turn, trace)

    def write_aborted(self, trace) -> bool:
        """The same, for an attempt that committed nothing (a rejected control, a clarify, a blocked line, a fold refusal):
        no turn number exists for it, so it is appended to its own table. The Failures view and the SLOs read it."""
        return self._trace_insert("INSERT INTO aborted(trace) VALUES (?)", None, trace)

    def _trace_insert(self, sql: str, turn, trace) -> bool:
        try:
            text = _canon(scrub_secrets(_plain(trace)))
            # H9-N3: best effort on the request path - a locked sidecar costs at most half a second, never the default 5 s
            with contextlib.closing(sqlite3.connect(self.trace_path, timeout=0.5)) as t, t:
                t.execute(_TRACE_TABLE)
                t.execute(_ABORTED_TABLE)
                t.execute(sql, (text,) if turn is None else (turn, text))
            return True
        except Exception as exc:                                           # noqa: BLE001 - best effort, by contract
            logging.getLogger("eidolon.trace").warning("trace not written: %s", type(exc).__name__)
            return False

    def discovery_order(self) -> list[str]:
        """Evidence ids in the order the player found them (the log's `Discovery` rows) - for stable item numbers (H8-N8)."""
        try:
            rows = self._conn.execute("SELECT payload FROM session_events WHERE kind = 'Discovery' ORDER BY seq").fetchall()
        except sqlite3.Error:                  # a read-only save has closed its connection: no order to offer
            return []
        return list(dict.fromkeys(json.loads(r[0])["evidence_id"] for r in rows))

    def kinds_between(self, first_seq: int, last_seq: int) -> list[str]:
        """The registry kinds of committed rows `first_seq..last_seq` (what a turn's trace says it committed)."""
        return [r[0] for r in self._conn.execute("SELECT kind FROM session_events WHERE seq BETWEEN ? AND ? ORDER BY seq",
                                                 (first_seq, last_seq))]

    def trace_rows(self, *, aborted: bool = False) -> list[tuple[int, str]]:
        """Every trace row, oldest first, read through a read-only handle: `(turn, json)` for committed turns, `(n, json)`
        for aborted attempts. A missing or unreadable trace file is no rows (a gap, §27.1), never an error."""
        sql = "SELECT n, trace FROM aborted ORDER BY n" if aborted else "SELECT turn, trace FROM traces ORDER BY turn"
        try:
            with contextlib.closing(sqlite3.connect(f"{self.trace_path.resolve().as_uri()}?mode=ro", uri=True)) as t:
                return [(r[0], r[1]) for r in t.execute(sql)]
        except sqlite3.Error:
            return []

    def trace_gaps(self) -> list[int]:
        """Committed turns with no trace row. EXPECTED after a crash (§27.1) and for exploration turns — reported, not
        treated as corruption."""
        turns = sorted(self._turns)
        try:
            with contextlib.closing(sqlite3.connect(f"{self.trace_path.resolve().as_uri()}?mode=ro", uri=True)) as t:
                have = {r[0] for r in t.execute("SELECT turn FROM traces")}
        except sqlite3.Error:
            have = set()
        return [t for t in turns if t not in have]

    # ---------------------------------------------------------------- export (§26.1)
    def export(self, dest) -> None:
        """`Connection.backup()` to a temp file, then an atomic rename: a torn copy never appears at `dest`. Traces do
        not travel."""
        dest = Path(dest)
        tmp = dest.with_name(dest.name + ".tmp")
        tmp.unlink(missing_ok=True)
        with contextlib.closing(sqlite3.connect(tmp)) as out:
            self._conn.backup(out)
        os.replace(tmp, dest)


# ------------------------------------------------------------------------------------ recovery (§26.3 step 3)
@dataclass(frozen=True)
class TruncationPlan:
    """What `truncate_to_last_valid` would do, decided by the loader's own verification and PROVEN by loading the result
    inside the transaction that would make it. `action`: `none` (nothing to repair), `reset_meta` (rows intact, only the
    genesis / head record is damaged — lossless), `cut` (chain break: back to the start of the damaged turn), `refuse`
    (the damage is not something cutting repairs — the reason says what is)."""
    action: str
    reason: str
    stage: str | None
    rows: int
    new_head_seq: int
    rows_removed: int
    turns_removed: int
    new_head_hash: str

    def describe(self) -> str:
        if self.action == "refuse":
            return f"cannot repair ({self.stage}): {self.reason}"
        return (f"{self.action}: {self.reason}; keeps {self.new_head_seq} of {self.rows} rows, removes "
                f"{self.rows_removed} rows / {self.turns_removed} turns")


class ConfirmationRequired(SaveError):
    """`truncate_to_last_valid` without `confirm=True`. `plan` is the dry run: exactly what confirming would do."""
    def __init__(self, plan: TruncationPlan):
        super().__init__(f"truncation destroys rows; plan — {plan.describe()}; call with confirm=True")
        self.plan = plan


def _refusal_plan(rows: int, e: SaveRefusal) -> TruncationPlan:
    return TruncationPlan("refuse", str(e), e.stage, rows, rows, 0, 0, "")


def _is_turn_start(row, last_turn) -> bool:
    """Is this (damaged) row plausibly the first row of the NEXT turn? Its `turn` column must differ from the last
    verified row's, and either its kind column or its payload must say TurnCommitted."""
    try:
        return row[1] != last_turn and (row[2] == "TurnCommitted" or _loads(row[4]).get("kind") == "TurnCommitted")
    except (ValueError, TypeError, AttributeError, IndexError, RecursionError):
        return False


def _plan_and_apply(conn, apply: bool) -> TruncationPlan:
    try:
        prep = _prepare(conn, writable=False)
    except SaveRefusal as e:
        return _refusal_plan(0, e)
    rows = _rows(conn)
    total = len(rows)
    n, last_hash, _why = _valid_prefix(rows, prep.genesis)
    meta_ok = prep.meta["genesis"] == prep.genesis and (str(total), last_hash) == (prep.meta["head_seq"], prep.meta["head_hash"])
    if n == total:
        if meta_ok:                                     # the chain and the head are fine: is it the fold?
            try:
                _replay(conn, prep, rows)
            except SaveRefusal as e:
                return _refusal_plan(total, e)
            return TruncationPlan("none", "the save loads; nothing to repair", None, total, total, 0, 0, last_hash)
        action, candidates, reason = "reset_meta", [total], "rows are intact; only the genesis / head record is damaged"
    else:
        if prep.meta["genesis"] != prep.genesis:
            return TruncationPlan("refuse", "the genesis record disagrees with the case and seed AND the chain does not verify "
                                  "under the recomputed genesis; cutting cannot tell which side is damaged", "genesis",
                                  total, total, 0, 0, "")
        start = n
        while start > 0 and rows[start - 1][1] == rows[n - 1][1]:
            start -= 1
        candidates = [n] if n == 0 or _is_turn_start(rows[n], rows[n - 1][1]) else []
        candidates += [start] if start != n else []
        action, reason = "cut", f"the hash chain breaks at seq {n + 1}"
    conn.execute("BEGIN IMMEDIATE")
    try:
        chosen, last_err = None, None
        for cut in candidates:
            head = rows[cut - 1][6] if cut else prep.genesis
            conn.execute("SAVEPOINT r")
            conn.execute("DELETE FROM session_events WHERE seq > ?", (cut,))
            conn.executemany("UPDATE meta SET value = ? WHERE key = ?",
                             [(str(cut), "head_seq"), (head, "head_hash"), (prep.genesis, "genesis")])
            try:
                _replay(conn, prep)                     # the repaired file must LOAD, or nothing is changed
                chosen = cut
                break
            except SaveRefusal as e:
                last_err = e
                conn.execute("ROLLBACK TO r")
                conn.execute("RELEASE r")
        if chosen is None or not apply:
            conn.execute("ROLLBACK")
        else:
            conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    if chosen is None:
        return TruncationPlan("refuse", f"no cut leaves a loadable save ({last_err})", last_err.stage if last_err else None,
                              total, total, 0, 0, "")
    return TruncationPlan(action, reason, None, total, chosen, total - chosen, len({r[1] for r in rows[chosen:]}),
                          rows[chosen - 1][6] if chosen else prep.genesis)


def _repair(path, apply: bool) -> TruncationPlan:
    p = Path(path)
    if not p.is_file():
        raise SaveRefusal(f"no such save: {p}")        # never create a file at a path that is not one
    journal = p.with_name(p.name + "-journal")
    if journal.is_file() and journal.stat().st_size:
        # Any read-write open rolls a hot journal back: the dry run would write the file and erase the crash evidence (X39).
        return _refusal_plan(0, SaveRefusal("a hot journal from an interrupted write sits beside the save: opening it for "
                                            "repair would make SQLite roll it back; open the save writable once to recover it, "
                                            "then plan again", stage="journal"))
    conn = None
    try:
        conn = sqlite3.connect(f"{p.resolve().as_uri()}?mode=rw", uri=True, isolation_level=None)
        return _plan_and_apply(conn, apply)
    except SaveError:
        raise
    except Exception as e:                                                  # noqa: BLE001 - corrupt/locked/odd files
        raise SaveRefusal(f"unreadable save: {type(e).__name__}: {e}") from e
    finally:
        if conn is not None:
            conn.close()


def plan_truncation(path) -> TruncationPlan:
    """The dry run: diagnose with the loader's own verification and report what `truncate_to_last_valid(confirm=True)`
    would do. Writes nothing: the transaction that proves the repair loads is rolled back, and a save with a hot journal
    (a crashed append) is REFUSED unopened (stage `journal`) — a read-write open would make SQLite roll the journal back,
    which writes the file and erases the crash evidence. `truncate_to_last_valid` refuses it the same way."""
    return _repair(path, apply=False)


def truncate_to_last_valid(path, *, confirm: bool = False) -> int:
    """§26.3 step 3. Needs an explicit `confirm=True` (without it: `ConfirmationRequired`, carrying the dry-run plan).
    Acts only on damage cutting repairs — a chain break (cut back to the start of the damaged turn; every complete turn
    before it is kept) or a damaged genesis/head record (rows untouched). A healthy save is left alone; a refusal in the
    fold, bundle or initial state is reported, never "repaired" by deleting rows. The delete and a full re-verification
    share one transaction, rolled back unless the result loads. Returns the new head seq."""
    plan = _repair(path, apply=confirm)
    if not confirm:
        raise ConfirmationRequired(plan)
    if plan.action == "refuse":
        raise SaveRefusal(plan.reason, stage=plan.stage)
    return plan.new_head_seq
