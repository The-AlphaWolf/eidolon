"""The contradiction detector (§13.2): "one function over pairs of propositions with
provenance". This is the general engine `minds.belief`'s rule 5 explicitly deferred
("the general contradiction detector is §13.2, Phase 3") — that Phase 2 function stays as
it is (narrow, belief-formation-only); this module is the real thing other phases build on.

Scope note (the task's own boundary): the architecture's §13.1 pairing table also lists
`claim vs prior claim`, `claim vs another character's claim` and `hypothesis vs discovered
material` — those need `Statement`/`Claim`/`ResponsePlan` (§12) and the player hypothesis
board (§16), both Phase 4 models this phase does not build. `contradiction()` itself is
claim-shape-agnostic: it compares raw `Proposition`s, so Phase 4 will call it directly once
`Claim.proposition` exists, exactly as `evidence_implication_contradicts` already does for
`Implication.proposition` here.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..world.case import Case
from ..world.interval import Interval, overlaps, shrink
from ..world.propositions import Proposition
from .model import Evidence, EvidenceStore, Implication

ContradictionKind = Literal[
    "presence", "negation", "object", "attribute", "cross_witness", "implication", "travel",
]


class Contradiction(BaseModel):
    """§13.2's output shape. `a`/`b` are opaque `Ref`s (§13.2: "StatementId/ClaimId,
    EvidenceId, FactId, HypothesisId") — the caller's choice of what identifies each side;
    this module never resolves them, it only compares the propositions they carry."""
    model_config = ConfigDict(frozen=True)

    a: str
    b: str
    kind: ContradictionKind
    severity: float
    explanation: str
    visible_to_player: bool = False


def asserted(interval: Interval, granularity: int) -> Interval | None:
    """§13.2's granularity rule: what a claim at granularity `g` actually ASSERTS.

    Testimony at granularity `g` locates an event only to within ±g, so the only ticks it
    commits to are the inner part — `interval.shrink`, whose Phase 1 docstring names this
    exact rule ("Testimony at granularity g: only the inner part is asserted"), and the same
    shrinking I-44 applies before deciding whether presence is fixed. `None` means the claim
    is too vague to commit to any tick, and a claim that asserts nothing cannot contradict
    anything.

    This is the direction the invariant's second clause requires: "a 'sharp' claim inside a
    'vague' one is not a contradiction". WIDENING both sides gets that backwards — it can
    only ever manufacture overlaps, so the vaguer a witness became the more refutation
    weight they would carry, and two claims genuinely separated by a gap would register as
    inconsistent (§13.2, I-44).
    """
    return shrink(interval, granularity)


def _rule_presence_travel(p, q, a_id, b_id, ga, gb, case) -> Contradiction | None:
    if p.kind == "At" and q.kind == "At" and p.actor == q.actor:
        if p.location == q.location:
            return None
        pi, qi = asserted(p.interval, ga), asserted(q.interval, gb)
        if pi is None or qi is None:
            return None  # at least one side asserts no tick at all
        if overlaps(pi, qi):
            return Contradiction(a=a_id, b=b_id, kind="presence", severity=1.0,
                                  explanation=f"{p.actor} cannot be at both {p.location} "
                                              f"and {q.location} at once",)
        if case is not None:
            # Ordered on the ASSERTED intervals too: the gap a traveller actually has is the
            # one between the ticks the two claims commit to, never the wider authored span.
            (first_iv, first), (second_iv, second) = (
                ((pi, p), (qi, q)) if pi[0] <= qi[0] else ((qi, q), (pi, p)))
            last_tick = first_iv[1] - 1
            gap = second_iv[0] - last_tick
            tt = case.travel_graph.travel_time(first.location, second.location, last_tick)
            if tt is None or gap < tt:
                shortfall = 1.0 if tt is None else max(0.0, min(1.0, (tt - gap) / tt))
                return Contradiction(a=a_id, b=b_id, kind="travel", severity=round(shortfall, 3),
                                      explanation=f"{p.actor}: {first.location}->{second.location} "
                                                  f"gap {gap} < travel time {tt}",)
    return None


_DID_SLOTS = ("object", "target_actor", "location")


def _denies(did, didnot) -> bool:
    """Does `didnot` actually deny `did`? §13.2 pairs `Did`/`DidNot` "with matching
    object/target", and `location` is a slot of both — so all three are compared, not two.

    The comparison is directional, matching `FactIndex._tv_Did`'s own reading of an unfilled
    slot (`facts.py`: "`Did(a, 'touch', object=None)` asks whether the actor handled ANY
    object"). On the DENIAL side an unfilled slot is a blanket "none of them" — "I never
    touched anything" denies touching Glass1 in particular. On the ASSERTION side it is an
    existential "something" — "I touched something" does not contradict "I did not touch
    Glass1", because the something may have been another object.

    Both readings were missing: exact `==` let a denial about the Study contradict an act in
    the Kitchen (a false contradiction), and made the blanket denial of §13.3's own worked
    scenario fail to contradict the forensic implication that refutes it (a missed one).
    """
    for slot in _DID_SLOTS:
        denied = getattr(didnot, slot, None)
        if denied is not None and denied != getattr(did, slot, None):
            return False
    return True


def _rule_negation(p, q, a_id, b_id, ga, gb) -> Contradiction | None:
    if {p.kind, q.kind} == {"At", "NotAt"}:
        at, nat = (p, q) if p.kind == "At" else (q, p)
        at_id, nat_id = (a_id, b_id) if p.kind == "At" else (b_id, a_id)
        gat, gnat = (ga, gb) if p.kind == "At" else (gb, ga)
        ai, ni = asserted(at.interval, gat), asserted(nat.interval, gnat)
        if (ai is not None and ni is not None
                and at.actor == nat.actor and at.location == nat.location
                and overlaps(ai, ni)):
            return Contradiction(a=at_id, b=nat_id, kind="negation", severity=1.0,
                                  explanation=f"{at.actor} is claimed both at and not at {at.location}",)
    if {p.kind, q.kind} == {"Did", "DidNot"}:
        did, didnot = (p, q) if p.kind == "Did" else (q, p)
        gdid, gnot = (ga, gb) if p.kind == "Did" else (gb, ga)
        di, ni = asserted(did.interval, gdid), asserted(didnot.interval, gnot)
        if (di is not None and ni is not None
                and did.actor == didnot.actor and did.action == didnot.action
                and _denies(did, didnot) and overlaps(di, ni)):
            return Contradiction(a=a_id, b=b_id, kind="negation", severity=1.0,
                                  explanation=f"{did.actor} both did and did not {did.action}")
    return None


def _rule_object(p, q, a_id, b_id) -> Contradiction | None:
    if {p.kind, q.kind} == {"Has", "ObjectAt"}:
        has, oat = (p, q) if p.kind == "Has" else (q, p)
        if has.object == oat.object and overlaps(has.interval, oat.interval) and oat.holder != has.actor:
            return Contradiction(a=a_id, b=b_id, kind="object", severity=1.0,
                                  explanation=f"{has.object} cannot be both held by {has.actor} "
                                              f"and at {oat.holder}",)
    return None


def _rule_attribute(p, q, a_id, b_id) -> Contradiction | None:
    if p.kind == "Attr" and q.kind == "Attr" and p.entity == q.entity and p.attr == q.attr and p.value != q.value:
        return Contradiction(a=a_id, b=b_id, kind="attribute", severity=1.0,
                              explanation=f"{p.entity}.{p.attr} cannot be both {p.value!r} and {q.value!r}",)
    if {p.kind, q.kind} == {"Attr", "Incidental"}:
        attr, inc = (p, q) if p.kind == "Attr" else (q, p)
        attr_id, inc_id = (a_id, b_id) if p.kind == "Attr" else (b_id, a_id)
        if attr.entity == inc.entity and attr.attr == inc.attr and attr.value != inc.value:
            # §4.7: "Incidental vs Attr (canonical wins)" — never player-visible: this is an
            # engine-side authoring check, not a tension the notebook shows (§13.4).
            return Contradiction(a=attr_id, b=inc_id, kind="attribute", severity=1.0,
                                  explanation=f"{attr.entity}.{attr.attr} is canonically "
                                              f"{attr.value!r}, not {inc.value!r}")
    if (p.kind == "State" and q.kind == "State" and p.actor == q.actor and p.attr == q.attr
            and p.value != q.value and overlaps(p.interval, q.interval)):
        return Contradiction(a=a_id, b=b_id, kind="attribute", severity=1.0,
                              explanation=f"{p.actor}.{p.attr} cannot be both {p.value!r} "
                                          f"and {q.value!r} at once",)
    if (p.kind == "ObjectState" and q.kind == "ObjectState" and p.object == q.object
            and p.attr == q.attr and p.value != q.value and overlaps(p.interval, q.interval)):
        return Contradiction(a=a_id, b=b_id, kind="attribute", severity=1.0,
                              explanation=f"{p.object}.{p.attr} cannot be both {p.value!r} "
                                          f"and {q.value!r} at once",)
    return None


def _rule_cross_witness(p, q, a_id, b_id, ga, gb) -> Contradiction | None:
    if {p.kind, q.kind} == {"Saw", "At"}:
        saw, at = (p, q) if p.kind == "Saw" else (q, p)
        saw_id, at_id = (a_id, b_id) if p.kind == "Saw" else (b_id, a_id)
        gsaw, gat = (ga, gb) if p.kind == "Saw" else (gb, ga)
        # "Unidentified sightings never contradict (they only support)" (§13.2).
        if saw.identified and saw.subject == at.actor and saw.location != at.location:
            si, ai = asserted(saw.interval, gsaw), asserted(at.interval, gat)
            if si is not None and ai is not None and overlaps(si, ai):
                return Contradiction(a=saw_id, b=at_id, kind="cross_witness", severity=0.8,
                                      explanation=f"{saw.observer} identified {at.actor} at "
                                                  f"{saw.location} while claimed at {at.location}",)
    return None


_RULES = (_rule_presence_travel, _rule_negation, _rule_object, _rule_attribute, _rule_cross_witness)


_ENGINE_ONLY_KINDS = frozenset({"Incidental"})
"""§4.7/§14.4: a runtime-only soft claim is an engine-side authoring check, never a tension
the notebook shows (§13.4) — so an `Incidental` side is never player-visible whatever the
player holds."""


def contradiction(p: Proposition, q: Proposition, *, a_id: str = "a", b_id: str = "b",
                   granularity_a: int = 0, granularity_b: int = 0,
                   case: Case | None = None,
                   player_material: frozenset[str] | None = None) -> Contradiction | None:
    """§13.2's rules, dispatched by proposition-kind pair. Order-independent: callers pass
    `p`/`q` in whichever order they hold them, and `a_id`/`b_id` follow the propositions they
    name, not positional convention.

    `granularity_a`/`granularity_b` implement the granularity rule via `asserted()` — pass
    the claim's `Memory`/testimony granularity (§8.3) where known; `0` (the default)
    reproduces exact-interval comparison for canonical facts.

    `player_material` is the set of `Ref`s the player actually holds — discovered evidence
    ids, heard statement ids. §13.2 defines `visible_to_player` as "both sides in player's
    material", and §13.4 has the notebook list exactly the visible ones, so the flag is a
    fact about the PLAYER, not about the rule that fired: each rule reports the structural
    verdict and this is the one place visibility is decided. Omitting the argument yields
    `False` — fail closed, because a contradiction whose sides the caller cannot vouch for
    must not be rendered into the notebook (VISIBLE TO PLAYER is downstream of DISCOVERED,
    never a property of the tension itself).
    """
    for rule in _RULES:
        if rule is _rule_presence_travel:
            r = rule(p, q, a_id, b_id, granularity_a, granularity_b, case)
        elif rule in (_rule_negation, _rule_cross_witness):
            r = rule(p, q, a_id, b_id, granularity_a, granularity_b)
        else:
            r = rule(p, q, a_id, b_id)
        if r is not None:
            held = player_material is not None and {r.a, r.b} <= player_material
            engine_only = bool({p.kind, q.kind} & _ENGINE_ONLY_KINDS)
            return r.model_copy(update={"visible_to_player": held and not engine_only})
    return None


def evidence_implication_contradicts(imp: Implication, other: Proposition, *, imp_id: str, other_id: str,
                                      other_granularity: int = 0,
                                      case: Case | None = None) -> Contradiction | None:
    """§13.2 "Implication": "evidence implication p with strength >= 0.5 vs claim
    contradicting p (using the above rules)". Below that strength the implication is too
    weak to license a contradiction on its own."""
    if imp.strength < 0.5:
        return None
    base = contradiction(imp.proposition, other, a_id=imp_id, b_id=other_id,
                          granularity_b=other_granularity, case=case)
    if base is None:
        return None
    return base.model_copy(update={"kind": "implication", "severity": round(base.severity * imp.strength, 3)})


def evidence_vs_evidence(e1: Evidence, e2: Evidence, case: Case | None = None) -> list[Contradiction]:
    """§13.1's "evidence vs evidence" pairing, whose engine use that table gives as
    **"planted-evidence tension; validator"** — two uses, one comparison.

    So the tension is reported for every pair, planted included. Gating on authenticity
    (the v1 form) silenced exactly the row the pairing exists for: a planted item's tension
    with genuine material IS the unmasking material §19.5 requires every planted item to
    have, and the detector is what surfaces it.

    The two uses are separated by the CALLER, which holds the authenticity flags:

    - **V-1/V-5 authoring check** — "two authentic items implying incompatible propositions"
      is a defect: filter to `e1.authentic and e2.authentic`.
    - **Unmasking (§11.2, I-35)** — a planted item in tension with an authentic one is
      working as designed, and is what a player assembles to expose it.

    Authenticity stays engine-only either way (§5.2): this returns the tension, never the
    verdict on which side is the forgery.
    """
    out: list[Contradiction] = []
    for i1 in e1.implications:
        for i2 in e2.implications:
            c = contradiction(i1.proposition, i2.proposition, a_id=e1.id, b_id=e2.id, case=case)
            if c is not None:
                out.append(c.model_copy(update={"kind": "implication",
                                                 "severity": round(c.severity * i1.strength * i2.strength, 3)}))
    return out


def _direct_requires(ev: Evidence) -> set[str]:
    return {r for i in ev.implications for r in i.requires}


def _requires_closure(ev: Evidence, store: EvidenceStore) -> set[str]:
    """Every id `ev` rests on, transitively. A reference the store cannot resolve (a
    `StatementId` — the `Statement` model is Phase 4) stays in the set under its own id, so
    two items resting on the same statement still collide on it; it simply has no further
    ancestors to walk."""
    seen: set[str] = set()
    frontier = list(_direct_requires(ev))
    while frontier:
        r = frontier.pop()
        if r in seen:
            continue
        seen.add(r)
        nxt = store.get(r)
        if nxt is not None:
            frontier.extend(_direct_requires(nxt))
    return seen


def corroborates(e1: Evidence, e2: Evidence, proposition: Proposition,
                  store: EvidenceStore | None = None) -> bool:
    """I-37 at the evidence layer: two items corroborate the SAME proposition only when they
    are genuinely INDEPENDENT sources. "Two evidence records" is not a proxy for "two
    sources" — §19.5's own rule is *distinct* sources with *disjoint* provenance, and every
    clause below is one way two records can turn out to be one source.

    1. **Authenticity.** A planted item is L0 — "never admissible **for the solver**"
       (§19.5) — so it is not a source at all and cannot corroborate, in either direction.
       Its *apparent* weight in conversation is a separate notion (§11.2, I-35).
    2. **Source identity must be known.** An item with no `created_by` has no established
       origin, so independence cannot be *established* either. Fail closed (I-15): unknown
       provenance is not independent provenance.
    3. **Distinct origin.** Same `created_by` is one observation yielding two records
       (I-37: "one perception yielding two beliefs is one source, not two").
    4. **Disjoint provenance, transitively.** Neither item may lie in the other's `requires`
       closure (circular or chained derivation: A→M→B is still B), and the two closures may
       not intersect (a shared prerequisite is a shared source — §19.5's "connectivity, not
       adjacency", applied to the derivation graph rather than the collusion graph).

    `store` resolves that closure. Without one, only directly-named ids are visible, so an
    item that names ANY prerequisite cannot be shown independent and is refused rather than
    assumed clean — the same fail-closed direction as clause 2.

    The collusion graph over `{shared Secret, Rel, Secret.beneficiaries}` is the other half
    of I-37 and needs `Secret`/`Rel` (Phase 4/6); this function covers the evidence half.
    """
    if e1.id == e2.id:
        return False
    if not (e1.authentic and e2.authentic):
        return False
    if not any(i.proposition == proposition for i in e1.implications):
        return False
    if not any(i.proposition == proposition for i in e2.implications):
        return False
    if e1.created_by is None or e2.created_by is None:
        return False
    if e1.created_by == e2.created_by:
        return False

    if store is None:
        if _direct_requires(e1) or _direct_requires(e2):
            return False  # unresolvable derivation graph; independence cannot be established
        return True

    dep1, dep2 = _requires_closure(e1, store), _requires_closure(e2, store)
    if e2.id in dep1 or e1.id in dep2:
        return False  # one derives from the other, directly or through a chain
    if dep1 & dep2:
        return False  # a shared ancestor is a shared source
    return True
