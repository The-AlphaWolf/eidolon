"""`Claim`/`Statement` (§25) — the committed-utterance layer. A `Statement` is what a
character actually said in a turn; each of its `Claim`s is one proposition it commits, tagged
with modality/confidence/sincerity (engine-only) and the grounding chain admissibility walks
(I-27).

`Claim.statement` is `None` for a claim that has not yet been spoken — the pre-authored
"template" claims living in a `CoverLayer`/`EvidenceResponse`/`Deflection`/`Slip`/
`misleading_truths` (`secrets.py`) are exactly this: content the generator authored ahead of
play, not yet bound to any turn. It is set to the owning `Statement.id` only once the claim
is actually committed at stage 10 (`turn.py`) — a deliberate, narrow reading of §25's
consolidated listing (which types the field as a bare `StatementId`) forced by the fact that
the same `Claim` model is asked to serve both roles; nothing about I-1/I-2/I-27 depends on
the field being non-optional, since admissibility and containment are computed from a
claim's `grounding`/`source`, never from whether it has been spoken yet.
"""
from __future__ import annotations

from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict

from ..evidence.ids import StatementId
from ..minds.ids import BeliefId, KnowledgeEntryId
from ..world.ids import ActorId
from ..world.propositions import Proposition
from .ids import ClaimId, SecretId
from .speech_acts import Sincerity, SpeechAct

Modality = Literal["actual", "hypothetical", "reported", "negated"]
Confidence = Literal["certain", "probable", "unsure"]
ClaimSource = Literal["plan", "frame", "incidental", "slip"]


class Claim(BaseModel):
    """§25. `grounding` is what `admissibility()` (I-27) walks; empty only for `incidental`
    claims (L0 by construction, §25's own comment) — an authored `plan`/`frame`/`slip` claim
    about the speaker's own protected facts is L0 for a different reason (§19.5's L0 row:
    "any suspect's claims about their own protected facts"), checked by `secrets.py`'s
    protected-fact lookup rather than by an empty chain, so its `grounding` may legitimately
    be empty too without collapsing the two L0 reasons into one code path.
    """
    model_config = ConfigDict(frozen=True)

    id: ClaimId
    statement: StatementId | None = None
    proposition: Proposition
    modality: Modality = "actual"
    confidence: Confidence = "certain"
    sincerity: Sincerity
    source: ClaimSource
    grounding: tuple[KnowledgeEntryId | BeliefId, ...] = ()


class Statement(BaseModel):
    """§25. `retracted_by` names the statement whose `CONCESSION`/`CORRECTION` retracted this
    one (§11.4: "retract claims of layers[peeled_from..i-1] that conflict with layers[i]");
    `layer_scope` marks a statement authored inside a cover layer's `frame`, discarded on
    peel (§14.4 rule 5)."""
    model_config = ConfigDict(frozen=True)

    id: StatementId
    turn: int
    speaker: ActorId
    addressee: Literal["detective"] = "detective"
    text: str
    claims: tuple[Claim, ...] = ()
    act: SpeechAct
    retracted_by: StatementId | None = None
    layer_scope: tuple[SecretId, int] | None = None
    accounts: tuple[str, ...] = ()
    """ADR-24 / I-50: the account tokens THIS statement delivered (`minds.accounts.tokens_satisfied` at
    commit). A RECORDED outcome — replay never recomputes it (I-22). Engine-side only: it never reaches an
    envelope, a digest, the player view or the notebook."""
    query_hash: str | None = None
    """§15.4's repetition key (`query.normalize()`), stored on the statement it answered so
    `turn.py` can count same-question repeats without a separate index — not in §25's own
    consolidated listing, which predates `Query.normalize()`'s hash shape, but needed by
    anything that implements `repeat_count` at all."""


class StatementStore:
    """The canonical statement storage (§15.2): every committed utterance, with the indexes
    §15.2/§15.3 need — by speaker and by claim id.

    Unlike `EvidenceStore`/`KnowledgeStore` (sealed at generation, mutated only while being
    BUILT from generation output and never again), this store is RUNTIME state — it grows
    every turn from `ClaimMade`/`ClaimRetracted` session events. I-5/I-22 require runtime
    state to be a fold that never mutates in place, the same discipline
    `evidence.discovery.DiscoveryState` already follows for the other runtime-growing store —
    so `add`/`retract` return a NEW `StatementStore` rather than mutating `self`; nothing here
    is a snapshot cache that could drift from the event log, it is simply recomputed cheaply
    (a few thousand statements at case scale) from an updated tuple each time.
    """

    def __init__(self, statements: Iterable[Statement] = ()):
        self._statements: tuple[Statement, ...] = tuple(statements)
        self._by_id: dict[StatementId, Statement] = {}
        self._by_speaker: dict[ActorId, list[StatementId]] = {}
        self._claim_index: dict[ClaimId, tuple[StatementId, Claim]] = {}
        for s in self._statements:
            if s.id in self._by_id:
                raise ValueError(f"duplicate Statement id: {s.id}")
            self._by_id[s.id] = s
            self._by_speaker.setdefault(s.speaker, []).append(s.id)
            for c in s.claims:
                self._claim_index[c.id] = (s.id, c)

    def get(self, statement_id: StatementId) -> Statement | None:
        return self._by_id.get(statement_id)

    def all(self) -> list[Statement]:
        return list(self._statements)

    def for_speaker(self, speaker: ActorId) -> list[Statement]:
        return [self._by_id[i] for i in self._by_speaker.get(speaker, [])]

    def standing_for_speaker(self, speaker: ActorId) -> list[Statement]:
        """§15.3's `standing_claims`: non-retracted statements only."""
        return [s for s in self.for_speaker(speaker) if s.retracted_by is None]

    def claim(self, claim_id: ClaimId) -> Claim | None:
        found = self._claim_index.get(claim_id)
        return found[1] if found else None

    def statement_of_claim(self, claim_id: ClaimId) -> Statement | None:
        found = self._claim_index.get(claim_id)
        return self._by_id.get(found[0]) if found else None

    def standing_claims(self, speaker: ActorId) -> list[Claim]:
        """Every non-retracted claim currently on the record for `speaker` — what
        `feasible()`/the contradiction gate (§14.2f) checks a new draft against."""
        return [c for s in self.standing_for_speaker(speaker) for c in s.claims]

    def add(self, statement: Statement) -> "StatementStore":
        """Returns a NEW store with `statement` appended (`ClaimMade`'s fold, §26.2: "the
        fold applies recorded outcomes only")."""
        if statement.id in self._by_id:
            raise ValueError(f"duplicate Statement id: {statement.id}")
        return StatementStore(self._statements + (statement,))

    def retract(self, statement_id: StatementId, retracted_by: StatementId) -> "StatementStore":
        """Returns a NEW store with `statement_id` marked retracted (`ClaimRetracted`'s
        fold) — idempotent: retracting an already-retracted statement with the SAME
        `retracted_by` is a no-op, matching `minds.fold`'s own replay-duplication guard."""
        current = self._by_id.get(statement_id)
        if current is None:
            raise KeyError(f"unknown Statement id: {statement_id!r}")
        if current.retracted_by == retracted_by:
            return self
        updated = current.model_copy(update={"retracted_by": retracted_by})
        others = tuple(s for s in self._statements if s.id != statement_id)
        return StatementStore(others + (updated,))
