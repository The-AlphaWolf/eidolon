"""§19.5 "a brute-force checker cross-validates the solver on small cases": a whole case small enough
(3 rooms, 8 ticks) that EVERY candidate's walk space can be enumerated. The solver's per-candidate
verdict must equal exhaustive search over all walks satisfying the admissible constraints + the
murder hypothesis — for the real case and for each of several edits of it."""
import itertools

import pytest

from eidolon.evidence.model import DiscoverySpec, Evidence, Implication
from eidolon.solve.lattice import admissible
from eidolon.solve.oracle import brute_feasible
from eidolon.solve.package import CanonicalSolution, CasePackage, EliminationStructure, MethodSpec
from eidolon.solve.solver import build_ctx, compile_actor, evaluate, robust_material
from eidolon.world.case import Case
from eidolon.world.entities import Actor
from eidolon.world.events import EffActorAt, EffActorState, Event, Perceptibility
from eidolon.world.propositions import Did
from eidolon.world.space import Location, TravelEdge

T = 8


def stay(a, loc, s, e):
    return Event(id=f"stay:{a}:{s}", kind="Stay", interval=(s, e), location=loc, actor=a,
                 effects=(EffActorAt(actor=a, location=loc),))


def tiny(x_in_room=True, witnesses_apart=False, extra_witness=False):
    """x is in the study at the murder tick; y and z sit together in the hall (independent witnesses of each other)."""
    ev = [stay("v", "M", 0, T), stay("x", "M" if x_in_room else "A", 0, T), stay("y", "A", 0, T),
          stay("z", "B" if witnesses_apart else "A", 0, T),
          Event(id="die", kind="Die", interval=(4, 5), location="M", actor="v",
                effects=(EffActorState(actor="v", attr="alive", value="false"),)),
          Event(id="attack", kind="Attack", interval=(4, 5), location="M", actor="x", participants=("v",),
                perceptibility=Perceptibility(sight=1.0, sound=0.8))]
    if extra_witness:                      # w sits with y and z: y's alibi now has TWO independent sources
        ev.append(stay("w", "A", 0, T))
    case = Case(id="tiny", t_investigation=T,
                actors={"v": Actor(id="v", name="v", role="victim"), **{a: Actor(id=a, name=a, role="suspect") for a in "xyz" + ("w" if extra_witness else "")}},
                locations={k: Location(id=k, name=k, private=(k == "M")) for k in "ABM"},
                travel_edges=(TravelEdge(a="A", b="M", minutes=1), TravelEdge(a="A", b="B", minutes=1)), events=tuple(ev))
    pin = Evidence(id="E_watch", kind="Timepiece", created_at=(4, 5), discovery=DiscoverySpec(action="Look", at="M"),
                   implications=(Implication(proposition=Did(actor="v", action="Die", interval=(4, 5), location="M")),))
    sol = CanonicalSolution(murderer="x", victim="v", method="b", weapon="w", location="M", interval=(4, 5),
                            murder_event="attack", motive_kind="m", approach=(3, 6))
    return CasePackage(id="tiny", skeleton_id="t", seed=0, case=case, evidence=(pin,), secrets=(), method=MethodSpec(kind="b", weapon="w"),
                       structure=EliminationStructure(alibi_window=0, secret_clearance=0, opportunity_pin=False), solution=sol)


def brute_survivors(p):
    ctx = build_ctx(p)
    mat, _, _ = robust_material(ctx)
    cons = admissible(ctx.case, ctx.store, mat, ctx.comps, ctx.victim)
    hard = [c for c in cons if c.level >= 2]
    from eidolon.solve.solver import Constraint, murder_window
    lo, hi = murder_window(ctx, hard)
    out = []
    for X in sorted(ctx.case.living_actors()):
        hyp = Constraint("H", "H", "Exist", X, ctx.murder_loc, (lo, hi), 3)
        blocked, forced, exist = compile_actor(hard + [hyp], X)
        starts = [(loc, 0) for loc in sorted(ctx.case.locations)]
        if brute_feasible(ctx.case, T, blocked, forced, exist, starts):
            out.append(X)
    return ctx, mat, out


@pytest.mark.parametrize("x_in_room,witnesses_apart", list(itertools.product([True, False], [False, True])))
def test_solver_survivors_equal_exhaustive_search_on_small_cases(x_in_room, witnesses_apart):
    p = tiny(x_in_room, witnesses_apart)
    ctx, mat, brute = brute_survivors(p)
    assert evaluate(ctx, mat).survivors == brute


def test_the_small_case_is_uniquely_solved_when_the_alibis_corroborate_and_not_otherwise():
    ctx, mat, brute = brute_survivors(tiny())
    assert brute == ["x"] and evaluate(ctx, mat).unique                    # y and z corroborate each other: excluded
    ctx, mat, brute = brute_survivors(tiny(witnesses_apart=True))
    assert set(brute) >= {"x", "z"} and not evaluate(ctx, mat).unique       # z is unwitnessed: a second survivor
