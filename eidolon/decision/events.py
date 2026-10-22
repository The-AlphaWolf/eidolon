"""The Phase 4 slice of the `SessionEventKind` catalogue (§25, I-31): every kind Phase 4
introduces, following `minds/events.py`'s own pattern exactly — each payload carries its
POST-value, and `apply_decision` never recomputes a weight, a layer index or a hash, it only
copies the payload into `DecisionState` (I-22).

Combined with `minds.events.MindsEvent` and `evidence.discovery.Discovery`, this completes
§25's full `SessionEventKind` union for the phases built so far: `PlayerAction`, `Discovery`
(Phase 3), `TurnCommitted`, `ClaimMade`, `ClaimRetracted`, `LayerPeel`, the Phase 2 minds
kinds, `IncidentalPinned`, `HypothesisChanged`, `Accusation`, `MetaAttemptLogged`,
`ValidationFailure`, `FallbackUsed`, `CaseSolved` (Phase 4). `PressureChange`/
`ComposureChange`/`EmotionalDelta`/`TrustChange`/`SuspicionShift`/`CoverStateDelta`/
`DetectiveModelUpdate` already live in `minds.events` (Phase 2 built them for exactly this
phase's use, per that module's own docstring).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from ..evidence.ids import StatementId
from ..world.ids import ActorId, LocationId, ObjectId
from ..world.propositions import Interval
from .claims import Statement, StatementStore
from .hypotheses import Hypothesis
from .ids import SecretId
from .secrets import Ref


class _DecisionEvent(BaseModel):
    model_config = ConfigDict(frozen=True)


class PlayerActionLogged(_DecisionEvent):
    """The `PlayerAction` `SessionEventKind` (§25): stage 1's parsed, schema-validated output,
    logged verbatim for the trace/digest — never re-parsed on replay (I-22)."""
    kind: Literal["PlayerAction"] = "PlayerAction"
    turn: int
    raw_text: str
    parsed_kind: str  # Query.kind, or "present"/"accuse"/"hypothesize"/"goto"/"search"


class TurnCommitted(_DecisionEvent):
    kind: Literal["TurnCommitted"] = "TurnCommitted"
    turn: int
    character: ActorId | None = None
    action_id: str | None = None


class ClaimMade(_DecisionEvent):
    """Carries the full committed `Statement` — the fold's job is to append it, never to
    re-derive its claims/text from a plan (I-22)."""
    kind: Literal["ClaimMade"] = "ClaimMade"
    statement: Statement


class ClaimRetracted(_DecisionEvent):
    kind: Literal["ClaimRetracted"] = "ClaimRetracted"
    statement_id: StatementId
    retracted_by: StatementId


class LayerPeel(_DecisionEvent):
    """§11.4. `character`/`secret_id` are what `peel.layer_index()` folds over to derive
    `layer_reached` without ever re-running `refutation_weight` against history."""
    kind: Literal["LayerPeel"] = "LayerPeel"
    character: ActorId
    secret_id: SecretId
    from_index: int
    to_index: int


class IncidentalPinned(_DecisionEvent):
    kind: Literal["IncidentalPinned"] = "IncidentalPinned"
    speaker: ActorId
    entity: str
    attr: str
    value: str
    layer_scope: tuple[SecretId, int] | None = None


class HypothesisChanged(_DecisionEvent):
    kind: Literal["HypothesisChanged"] = "HypothesisChanged"
    hypothesis: Hypothesis


class Accusation(_DecisionEvent):
    """§16.3. Provisional: put to the accused during an interrogation — verbal pressure and the accused's detective model,
    never a peel (I-16). Final (Phase 8): its own turn, carrying the player's solution form and the refs `cited` as proof;
    the store requires the same turn to close the case with `CaseSolved`. The form is what the player SAID: the case
    report (a projection, never hashed) is what scores it."""
    kind: Literal["Accusation"] = "Accusation"
    turn: int
    target: ActorId
    provisional: bool
    weapon: ObjectId | None = None
    location: LocationId | None = None
    interval: Interval | None = None
    motive_kind: str | None = None
    cited: tuple[Ref, ...] = ()


class MetaAttemptLogged(_DecisionEvent):
    kind: Literal["MetaAttemptLogged"] = "MetaAttemptLogged"
    turn: int
    character: ActorId
    query_kind: Literal["meta", "coercion"]


class ValidationFailure(_DecisionEvent):
    kind: Literal["ValidationFailure"] = "ValidationFailure"
    turn: int
    check: str
    detail: str = ""


class FallbackUsed(_DecisionEvent):
    kind: Literal["FallbackUsed"] = "FallbackUsed"
    turn: int
    reason: str = ""


class CaseSolved(_DecisionEvent):
    """Terminal. `correct` is the WHO axis: the final accusation names the proof's verified unique survivor (the store
    checks it against `GameState.murderer`, never trusts it). Nothing may follow it (PN-10)."""
    kind: Literal["CaseSolved"] = "CaseSolved"
    turn: int
    correct: bool


DecisionEvent = Annotated[
    Union[PlayerActionLogged, TurnCommitted, ClaimMade, ClaimRetracted, LayerPeel,
          IncidentalPinned, HypothesisChanged, Accusation, MetaAttemptLogged,
          ValidationFailure, FallbackUsed, CaseSolved],
    Field(discriminator="kind"),
]


@dataclass(frozen=True)
class DecisionState:
    """The Phase 4 slice of runtime authoritative state — everything `minds.CharacterState`/
    `EpistemicState` and `evidence.DiscoveryState` do not already own. A plain frozen
    dataclass rather than a pydantic model: its fields are stores/tuples with their own
    equality and hashing, and nothing here needs JSON validation beyond what the contained
    models already provide."""
    statements: StatementStore
    layer_peels: tuple[LayerPeel, ...] = ()
    hypotheses: tuple[Hypothesis, ...] = ()
    accusations: tuple[Accusation, ...] = ()
    meta_attempts: tuple[MetaAttemptLogged, ...] = ()
    validation_failures: tuple[ValidationFailure, ...] = ()
    fallbacks: tuple[FallbackUsed, ...] = ()
    incidentals: tuple[IncidentalPinned, ...] = ()
    solved: CaseSolved | None = None


def initial_decision_state() -> DecisionState:
    return DecisionState(statements=StatementStore())


def _append_once(existing: tuple, record) -> tuple:
    """`minds.fold._append_once`'s own guard, reused here: replaying the same row twice must
    be a no-op (I-5), never a second entry."""
    return existing if record in existing else existing + (record,)


def apply_decision(state: DecisionState, event: DecisionEvent) -> DecisionState:
    """I-22: applies the recorded outcome only. `PlayerActionLogged`/`TurnCommitted` are pure
    audit rows with nothing to fold into `DecisionState` (they exist for the trace/replay
    cursor, §26.2's `TurnCommitted` bookkeeping, not for any field read by a later stage)."""
    if isinstance(event, ClaimMade):
        existing = state.statements.get(event.statement.id)
        if existing is not None:
            if existing == event.statement:
                return state  # duplicated row: already applied (I-5)
            raise ValueError(f"ClaimMade {event.statement.id!r} already committed with different content")
        return replace(state, statements=state.statements.add(event.statement))
    if isinstance(event, ClaimRetracted):
        return replace(state, statements=state.statements.retract(event.statement_id, event.retracted_by))
    if isinstance(event, LayerPeel):
        return replace(state, layer_peels=_append_once(state.layer_peels, event))
    if isinstance(event, IncidentalPinned):
        return replace(state, incidentals=_append_once(state.incidentals, event))
    if isinstance(event, HypothesisChanged):
        others = tuple(h for h in state.hypotheses if h.id != event.hypothesis.id)
        return replace(state, hypotheses=others + (event.hypothesis,))
    if isinstance(event, Accusation):
        return replace(state, accusations=_append_once(state.accusations, event))
    if isinstance(event, MetaAttemptLogged):
        return replace(state, meta_attempts=_append_once(state.meta_attempts, event))
    if isinstance(event, ValidationFailure):
        return replace(state, validation_failures=_append_once(state.validation_failures, event))
    if isinstance(event, FallbackUsed):
        return replace(state, fallbacks=_append_once(state.fallbacks, event))
    if isinstance(event, CaseSolved):
        return replace(state, solved=event)
    return state  # PlayerActionLogged, TurnCommitted: audit-only
