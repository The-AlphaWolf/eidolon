"""`LayerPeel` (§11.4, I-3, I-20, I-21, I-33, I-38) — the ONLY way a cover story changes.

`layer_reached` is derived, never stored (§9's own comment: storing it "invited drift
between the stored index and the index the weight function implies"). This module computes
one turn's peel decision given the CALLER-SUPPLIED `reached` index — `turn.py` derives that
index by folding the session's own `LayerPeel` events with `layer_index()` below (I-22: the
fold applies the recorded `to` value, it never re-runs the weight function over history),
which is cheap and exactly matches "`max` over the session" without recomputing anything.

The `CONFESSION` gate defaults CLOSED (`confession_check=None` -> never allowed). I-21 says a
confession requires the presented set to establish solver uniqueness; the absence of a wired
uniqueness check is not evidence that it does, so the fail-closed default (I-15's own
direction, applied here) is STONEWALL, not silent confession. A wired check is bound to
identity (`confession_permitted`): a proof names one survivor, and licenses only that
survivor's confession of their own secret.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..world.propositions import Proposition
from .context import DecisionContext
from .secrets import CoverLayer, Ref, Secret
from .solver import UniquenessResult
from .weight import refutation_weight
from .claims import Statement, StatementStore
from .ids import SecretId
from ..world.ids import ActorId

# (confessing actor, the secret whose terminal layer is reached, this turn's presented set,
# this turn's context) -> the solver's verdict on exactly that question (§11.4: solver.unique
# over admissible(presented ∪ player_hard_material)).
ConfessionCheck = Callable[[ActorId, Secret, frozenset[Ref], DecisionContext], UniquenessResult]


def confession_permitted(check: ConfessionCheck | None, secret: Secret, confrontee: ActorId,
                         presented: frozenset[Ref], ctx: DecisionContext) -> bool:
    """I-21, bound to identity. A uniqueness proof licenses exactly one confession: the unique
    survivor's, of that survivor's own secret, over this turn's presented set. No checker, a
    secret the confrontee does not own, a verdict that is not a `UniquenessResult`, a
    non-unique verdict, or a survivor other than the confrontee: closed (I-15)."""
    if check is None:
        return False
    if secret.owner != confrontee:
        return False
    result = check(confrontee, secret, presented, ctx)
    return isinstance(result, UniquenessResult) and result.unique and result.survivors == (confrontee,)


def confession_gated(secret: Secret, layer: CoverLayer) -> bool:
    """I-21 / I-56: does reaching this `confession` terminal need a uniqueness proof? Yes for the murder secret, and
    for any terminal that would put a `Solution` on the record (§14.2(e)); no for an innocent's ordinary concession."""
    return secret.kind == "murder" or any(c.proposition.kind == "Solution" for c in layer.claims)


def layer_index(peel_events, character: ActorId, secret_id: SecretId) -> int:
    """§9/§11.4: `layer_reached` is `max` over the session's `LayerPeel(character, secret,
    from, to)` events' `to` field — the fold's own contract (I-22): apply the recorded
    outcome, never recompute it. `peel_events` is any iterable of objects with
    `character`/`secret_id`/`to_index` attributes (`events.LayerPeel`)."""
    tos = [e.to_index for e in peel_events if e.character == character and e.secret_id == secret_id]
    return max(tos, default=0)


@dataclass(frozen=True)
class PeelResult:
    secret_id: SecretId
    from_index: int
    to_index: int
    peeled: bool
    stonewalled: bool
    weight_bp: int              # refutation weight against the layer that stopped the advance


def evaluate_peel(secret: Secret, presented: frozenset[Ref], reached: int, confrontee: ActorId,
                   ctx: DecisionContext, confession_check: ConfessionCheck | None = None) -> PeelResult:
    """§11.4's loop, verbatim. `reached` and the return's `to_index` are indices into
    `secret.cover.layers`."""
    layers = secret.cover.layers
    i = reached
    last_weight = 0
    while i < len(layers) - 1 and layers[i].terminal is None:
        w = refutation_weight(presented, layers[i], confrontee, ctx)
        last_weight = w
        if w < layers[i].resolve:
            nxt = layers[i + 1]
            # ADR-32: the last denial before a gated confession has no evidence breaker by design (§19.3 (i)); a presented
            # set that PROVES the confrontee the unique culprit is its breaker, so the confession costs exactly a proof (I-21)
            if not (nxt.terminal == "confession" and confession_gated(secret, nxt)
                    and confession_permitted(confession_check, secret, confrontee, presented, ctx)):
                break
        i += 1

    stonewalled = False
    if layers[i].terminal == "confession" and confession_gated(secret, layers[i]):
        # I-21 / ADR-25 (I-56): the uniqueness gate protects the SOLUTION — the murder secret's confession, or any
        # terminal whose claims entail a `Solution`. A plain non-murder "confession" terminal is a concession
        # terminal: reaching it is an ordinary, ungated peel (§19.5 "cracking [an excluded innocent] costs nothing"
        # is the premise the solver's I-45 fixpoint already relies on).
        allowed = confession_permitted(confession_check, secret, confrontee, presented, ctx)
        if not allowed:
            i = max(i - 1, reached)  # I-20: never land below where we already stood
            stonewalled = True

    i = max(i, reached)  # I-38: weight may fall (retraction); the layer may not
    return PeelResult(secret_id=secret.id, from_index=reached, to_index=i,
                       peeled=i > reached, stonewalled=stonewalled, weight_bp=last_weight)


def claims_voiced_on_peel(layer: CoverLayer) -> tuple:
    """What the CONCESSION that lands on `layer` says (§11.4: `plan.claims = layers[i].claims`).
    Landing on a confession terminal is still a peel, voiced as CONCESSION — only a character
    already standing at that layer confesses (§10.3: CONCESSION's precondition is "LayerPeel
    just fired", CONFESSION's is "terminal layer reached"). A `Solution` claim waits for the
    CONFESSION act, the only act that may entail it (§14.2(e)); voicing it here would reject
    the turn every time, so the peel could never be recorded (N-2)."""
    if layer.terminal != "confession":
        return layer.claims
    return tuple(c for c in layer.claims if c.proposition.kind != "Solution")


def superseded_propositions(secret: Secret, peeled_from: int, to_index: int) -> frozenset[Proposition]:
    """The denial propositions §11.4 says to retract: everything the layers between
    `peeled_from` (inclusive) and `to_index` (exclusive) claimed — the ground the character
    is giving up by conceding to `to_index`. That includes the `EvidenceResponse` claims
    authored AT those layers (§10.2: "what to say when an item is presented at a layer",
    "consistent with the layer"): they are part of the abandoned story. Leaving them standing
    makes the owed concession contradict the ledger on every later turn, and a concession
    that cannot be committed rejects the turn — permanently, since the peel re-fires (I-33)."""
    props: set[Proposition] = set()
    for layer in secret.cover.layers[peeled_from:to_index]:
        props |= {c.proposition for c in layer.claims}
    props |= {c.proposition for r in secret.evidence_responses if peeled_from <= r.layer < to_index for c in r.claims}
    return frozenset(props)


def statements_to_retract(statements: StatementStore, speaker: ActorId,
                           superseded: frozenset[Proposition]) -> list[Statement]:
    """§11.4: "retract claims of layers[peeled_from..i-1] that conflict with layers[i]" — the
    statements naming any of `superseded`'s propositions, still standing."""
    return [s for s in statements.standing_for_speaker(speaker)
            if any(c.proposition in superseded for c in s.claims)]
