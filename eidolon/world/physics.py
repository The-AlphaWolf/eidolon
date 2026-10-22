"""Physics checker (§4.9): `check_physics(case) -> list[Violation]`. Applied by the
validator (later phases) and by property tests here. Every rule is a pure function over
the CaseLog; none of them consult an LLM or randomness (I-6, I-11)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

from .case import Case
from .ids import EvidenceId
from .interval import Interval
from .propositions import Proposition
from .space import Condition, ConditionCheck
from .state import death_ticks, loc_at, presence, world_at


@dataclass(frozen=True)
class Violation:
    rule: str  # "P-1" .. "P-9"
    detail: str

    def __str__(self) -> str:
        return f"{self.rule}: {self.detail}"


class Implication(NamedTuple):
    """The physics-relevant slice of §5.1's `Evidence.Implication` — `strength` and the rest
    of the full Evidence model (discovery, visibility, red herrings, …) are Phase 3."""
    proposition: Proposition
    requires: tuple[str, ...] = ()
    created_at: Interval | None = None  # interval established by discovery/creation alone


def _condition_check(case: Case) -> ConditionCheck:
    """Default P-5 evaluator: door/key state read off `world_at` (§4.9 P-5). `LightOn`/`Night`
    have no case fixture exercising them yet and default to always-open."""
    def check(c: Condition, t: int) -> bool:
        ws = world_at(case.events, t)
        if c.kind == "DoorUnlocked":
            (door_id,) = c.args
            return ws.object_state.get(door_id, {}).get("locked") == "false"  # fail-closed by default
        if c.kind == "DoorOpen":
            (door_id,) = c.args
            return ws.object_state.get(door_id, {}).get("open") == "true"  # fail-closed by default
        if c.kind == "HasKey":
            actor_id, key_id = c.args
            return ws.object_at.get(key_id) == actor_id
        return True
    return check


def _p1_p2(case: Case) -> list[Violation]:
    """P-1 presence uniqueness; P-2 travel feasibility (corrected, half-open, §4.9 v0.4):
    `I2.start - (I1.end - 1) >= travel_time(L1, L2, I1.end - 1)`."""
    v: list[Violation] = []
    for actor in case.actors:
        segs = presence(case.events, actor)
        for i, (iv, loc) in enumerate(segs):
            if i == 0:
                continue
            prev_iv, prev_loc = segs[i - 1]
            if iv[0] < prev_iv[1]:
                v.append(Violation("P-1", f"{actor} overlaps {prev_loc}{prev_iv} / {loc}{iv}"))
                continue
            if loc == prev_loc:
                continue
            last_tick = prev_iv[1] - 1
            tt = case.travel_graph.travel_time(prev_loc, loc, last_tick)
            gap = iv[0] - last_tick
            if tt is None or gap < tt:
                v.append(Violation("P-2", f"{actor} {prev_loc}->{loc}: gap {gap} < travel {tt}"))
    return v


def _p3(case: Case) -> list[Violation]:
    """P-3 object continuity: `Take`/`Use` require the actor to be where the object is."""
    v: list[Violation] = []
    for e in case.events:
        if e.kind not in ("Take", "Use") or e.actor is None:
            continue
        actor_loc = loc_at(case.events, e.actor, e.interval[0])
        if actor_loc is None or actor_loc != e.location:
            v.append(Violation("P-3", f"{e.id}: {e.actor} not at {e.location} for {e.kind}"))
    return v


def _p4(case: Case) -> list[Violation]:
    """P-4 vital state: no actor acts after being killed; `Attack` requires attacker/victim
    co-location. Death is `ActorState(actor, "alive", "false")` — the closed schema (§4.7)
    has no dedicated "Died" predicate."""
    v: list[Violation] = []
    death_tick = death_ticks(case.events)  # one authority on who is dead when (state.py)
    passive = {"Stay", "Die", "Environmental"}  # presence and the death-marking event itself are not "acts"
    for e in case.events:
        if e.actor and e.kind not in passive and e.actor in death_tick and e.interval[0] >= death_tick[e.actor]:
            v.append(Violation("P-4", f"{e.id}: {e.actor} acts at {e.interval} after death at {death_tick[e.actor]}"))
        if e.kind == "Attack" and e.actor:
            attacker_loc = loc_at(case.events, e.actor, e.interval[0])
            for target in e.participants:
                target_loc = loc_at(case.events, target, e.interval[0])
                if attacker_loc != e.location or target_loc != e.location:
                    v.append(Violation("P-4", f"{e.id}: attacker/victim not co-located at {e.interval[0]}"))
    return v


def _p5(case: Case) -> list[Violation]:
    """P-5 door/lock gating: a presence transition through a conditional edge must have had
    its conditions hold at the traversal tick."""
    v: list[Violation] = []
    check = _condition_check(case)
    for actor in case.actors:
        segs = presence(case.events, actor)
        for i in range(1, len(segs)):
            prev_iv, prev_loc = segs[i - 1]
            _iv, loc = segs[i]
            if loc == prev_loc:
                continue
            last_tick = prev_iv[1] - 1
            if case.travel_graph.travel_time(prev_loc, loc, last_tick, check) is None:
                v.append(Violation("P-5", f"{actor} moved {prev_loc}->{loc} at {last_tick} with a travel condition unmet"))
    return v


def _p9(implications: list[tuple[EvidenceId, Implication]]) -> list[Violation]:
    """P-9 temporal grounding (I-30): an implication whose proposition spans an interval
    must have that interval established by its own `requires` chain, not by discovery time."""
    v: list[Violation] = []
    for eid, imp in implications:
        interval = getattr(imp.proposition, "interval", None)
        if interval is None or imp.requires:
            continue
        if imp.created_at is None or not (imp.created_at[0] <= interval[0] and interval[1] <= imp.created_at[1]):
            v.append(Violation("P-9", f"{eid}: {imp.proposition} spans more than established {imp.created_at} with no requires"))
    return v


class PhysicsViolationError(ValueError):
    """Raised when a subsystem downstream of `world/` is handed a case the physics checker
    rejects. Carries the violations so a caller can report them (I-15: fail closed)."""

    def __init__(self, case_id: str, violations: list[Violation]):
        self.violations = violations
        super().__init__(f"case {case_id!r} is not physically valid:\n" +
                          "\n".join(f"  {v}" for v in violations))


def require_physics_valid(case: Case) -> None:
    """The `world <- minds` gate (§23.1). §4.9 makes `check_physics` "a pure function applied
    by the validator"; nothing downstream may *assume* validity without establishing it, and
    every derivation in `minds/` assumes at least P-1 (one actor, one place) when it reads
    `presence`/`loc_at`. So the boundary asserts it rather than trusting the caller.

    P-1..P-5 only: those are the rules about the world itself. P-9 grades evidence
    implications, which are an argument *about* the world and may legitimately be rejected
    while the world stays sound (`vance_v02_negative`'s E10 is exactly that case).
    """
    violations = check_physics(case)
    if violations:
        raise PhysicsViolationError(case.id, violations)


def _implication_truth(case: Case, implications: list[tuple[EvidenceId, Implication]]) -> list[Violation]:
    """An implication asserts a proposition about the canonical world; the world is the
    authority on whether it holds (§4.7 `truth_value`). An implication the world *refutes*
    is an authoring error, and reporting it is what keeps "authored wrong" distinguishable
    from "deliberately false" once Phase 3 introduces planted evidence (`Evidence.authentic`).

    Unknown is not a violation: an implication may legitimately concern something the
    CaseLog does not settle. Only an outright `False` is reported.

    Reported under "P-0" because it is a precondition on the evidence input rather than one
    of §4.9's numbered world rules — it is deliberately NOT folded into the P-1..P-5 gate
    (`require_physics_valid`), which grades the world, not arguments about it.
    """
    from .facts import FactIndex  # local: facts.py imports this module's `Implication`

    index = FactIndex(case)
    v: list[Violation] = []
    for eid, imp in implications:
        if index.truth_value(imp.proposition) is False:
            v.append(Violation("P-0", f"{eid}: implication is contradicted by the canonical "
                                       f"world: {imp.proposition}"))
    return v


def check_physics(case: Case, implications: list[tuple[EvidenceId, Implication]] | None = None) -> list[Violation]:
    """P-1..P-5 always run; P-0 and P-9 run when `implications` is supplied (the full
    `Evidence` model with discovery/visibility/red herrings is Phase 3 — Phase 1 checks
    these on the minimal `Implication` shape above)."""
    v: list[Violation] = []
    v += _p1_p2(case)
    v += _p3(case)
    v += _p4(case)
    v += _p5(case)
    if implications:
        v += _implication_truth(case, implications)
        v += _p9(implications)
    return v
