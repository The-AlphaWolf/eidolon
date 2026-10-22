"""A minimal `unique()` primitive for the `CONFESSION` gate (I-21, §11.4).

**Scope, stated plainly.** §19.5's V-5 is a full case-generation solver: a candidate space of
`(suspect, method, time_bin, location)`, the complete admissibility lattice with the
collusion-graph corroboration bump, `outsider_excluded` as a travel-graph reachability query,
elimination-structure realisation (I-43), the layer-0 robustness fixpoint (I-45),
absence-fragility banding, and machine-generated exclusion chains — explicitly a Phase 6
deliverable (roadmap §30) built during CASE GENERATION, over material the generator itself
authored. Phase 4 does not build that solver; building it now would be exactly the "implement
Phase 5+ functionality prematurely" the brief forbids, and it would need a `Solution`/
`EliminationStructure` this phase's fixtures do not have.

What Phase 4's OWN invariant needs is narrower: `LayerPeel`'s `CONFESSION` precondition
(I-21) only has to distinguish "the presented set already pins down who could have done it"
from "more than one suspect is still physically possible" — an OPPORTUNITY question, not a
full solve. `unique()` below answers exactly that, by reusing the joint-feasibility engine
Phase 3 already built (`world.feasibility.feasible`, I-28) per-candidate: is it feasible, given
everything ADMISSIBLE that has been said about candidate X's whereabouts, for X to also have
been at the murder scene during the murder window? A candidate for whom that is infeasible is
excluded; if exactly one candidate remains, the set is unique at the level tested. Method,
motive, collusion and outsider-exclusion stay out of scope — Phase 6's solver is a strict
superset of this question, not a competing implementation of it, and CAN call this function
as its own opportunity-elimination step rather than re-deriving `feasible()` integration.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..minds.provenance import AdmissibilityLevel
from ..world.case import Case
from ..world.feasibility import Claim as FeasClaim
from ..world.feasibility import feasible
from ..world.ids import ActorId, LocationId
from ..world.propositions import At, Proposition

FairnessLevel = str  # "standard" (L3 union L2 hard) | "hard-fair" (L3 alone)

_LEVEL_FLOOR = {"standard": AdmissibilityLevel.L2, "hard-fair": AdmissibilityLevel.L3}


@dataclass(frozen=True)
class AdmissibleClaim:
    """The minimal shape `unique()` needs from a claim/implication: who it is about, what it
    asserts, and the admissibility level it was computed at (`admissibility.py`) — never the
    apparent level, per I-21/I-35 ("solver.unique is called on... true admissibility, so
    planted material and detective-induced beliefs can never license a confession")."""
    actor: ActorId
    proposition: Proposition
    level: AdmissibilityLevel


@dataclass(frozen=True)
class UniquenessResult:
    unique: bool
    survivors: tuple[ActorId, ...]


def unique(candidates: Iterable[ActorId], murder_location: LocationId, murder_interval: tuple[int, int],
           admissible: Iterable[AdmissibleClaim], case: Case,
           fairness_level: FairnessLevel = "standard") -> UniquenessResult:
    """For each candidate, is `At(candidate, murder_location, murder_interval)` jointly
    feasible with every admissible claim ABOUT THAT CANDIDATE at or above the fairness
    floor? Candidates for whom it is not are excluded (their own admissible material
    places them elsewhere, or blocks the travel). Unique iff exactly one survives."""
    floor = _LEVEL_FLOOR[fairness_level]
    survivors: list[ActorId] = []
    for cand in candidates:
        theirs = [FeasClaim(id=f"adm:{i}", proposition=c.proposition)
                  for i, c in enumerate(admissible) if c.actor == cand and c.level >= floor]
        hypothesis = FeasClaim(id="hyp:opportunity",
                                proposition=At(actor=cand, location=murder_location, interval=murder_interval))
        if feasible(case, theirs + [hypothesis]).ok:
            survivors.append(cand)
    return UniquenessResult(unique=len(survivors) == 1, survivors=tuple(survivors))
