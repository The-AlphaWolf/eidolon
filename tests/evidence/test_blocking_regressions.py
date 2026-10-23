"""Regression tests for the five BLOCKING defects found by the Phase 3 hostile audit.

Every test here fails on the pre-fix code and passes after. Each names the invariant it
guards, not the symptom, so a future rewrite that reintroduces the bug under a different
shape still trips it.

B-1  I-47 cueing was a per-node flag, so an item counted as "fully cued" through an uncued
     prerequisite (§19.4: "the proof core must be reachable along a fully-cued path").
B-2  `DiscoverySpec.at` was never checked, so a load-bearing item at an address the world
     does not contain passed V-4 from an empty seed set.
B-3  `reachability` mutated traversal state mid-pass, making `depth`/`cued` a function of
     `EvidenceStore` insertion order rather than of case content.
B-4  `corroborates` counted dependent records as independent sources (I-37).
B-5  granularity WIDENED intervals, manufacturing overlaps across real gaps (§13.2, I-44).
"""
from __future__ import annotations

import itertools

from eidolon.evidence.contradiction import contradiction, corroborates
from eidolon.evidence.discovery import reachability, uncued_load_bearing
from eidolon.evidence.grounding import check_creation_grounding
from eidolon.evidence.model import DiscoverySpec, Evidence, EvidenceStore, Implication, Prereq
from eidolon.world.propositions import At, NotAt, Saw
from tests.evidence.fixtures.vance_evidence import evidence_case, evidence_case_items


def _ev(id_, *, at="Knife", prerequisites=(), cue=None, **kw):
    return Evidence(id=id_, kind="Object",
                    implications=kw.pop("implications", ()),
                    discovery=DiscoverySpec(action="Look", at=at, prerequisites=prerequisites, cue=cue),
                    **kw)


# --- B-1: cueing is a property of the PATH, not of the node ----------------------------
def test_b1_an_item_is_not_cued_when_its_prerequisite_is_uncued():
    """`B`'s own cue ("A") is satisfied the moment A is found, but A itself was never cued,
    so no cued path to B exists. The pre-fix code reported `cued == {"B"}`."""
    store = EvidenceStore([
        _ev("A", cue="NEVER_NAMED"),
        _ev("B", prerequisites=(Prereq(kind="EvidenceFound", ref="A"),), cue="A", load_bearing=True),
    ])
    report = reachability(store, initial_items=["Knife"])
    assert report.reachable == frozenset({"A", "B"})   # both prerequisite-reachable
    assert "A" not in report.cued                      # its own cue is never named
    assert "B" not in report.cued                      # ...so B's only path is uncued
    assert uncued_load_bearing(store, report) == frozenset({"B"})


def test_b1_the_same_chain_is_fully_cued_once_the_root_cue_is_named():
    """The other direction: the guard must not simply refuse every chain. Naming A's cue
    cues A, whose discovery then names A for B."""
    store = EvidenceStore([
        _ev("A", cue="MAP"),
        _ev("B", prerequisites=(Prereq(kind="EvidenceFound", ref="A"),), cue="A", load_bearing=True),
    ])
    report = reachability(store, initial_items=["Knife", "MAP"])
    assert report.cued == frozenset({"A", "B"})
    assert report.cued_depth == {"A": 0, "B": 1}
    assert uncued_load_bearing(store, report) == frozenset()


# --- B-2: `at` is validated against the canonical world, and gates cueing ---------------
def test_b2_a_load_bearing_clue_at_an_unnamed_location_is_not_cued():
    """The audit's own construction: a proof-core item whose discovery site nothing names.
    Pre-fix this was reachable, cued and depth 0 from a completely empty seed set."""
    store = EvidenceStore([_ev("E_core", at="SealedVaultOnTheMoon", load_bearing=True)])
    report = reachability(store)
    assert report.cued == frozenset()
    assert uncued_load_bearing(store, report) == frozenset({"E_core"})


def test_b2_grounding_rejects_a_discovery_site_the_world_does_not_contain():
    """§5.1 types `at` as `LocationId | ObjectId`. A syntactically valid string that resolves
    to neither is not a discovery site, and P-6 says so."""
    case = evidence_case()
    bad = EvidenceStore([_ev("E1", at="SealedVaultOnTheMoon")])
    assert any("discovery.at" in x.detail and x.rule == "P-6"
               for x in check_creation_grounding(case, bad))
    for good in ("Knife", "Parlor"):          # a real object, and a real location
        assert not [x for x in check_creation_grounding(case, EvidenceStore([_ev("E1", at=good)]))
                    if "discovery.at" in x.detail]


# --- B-3: reachability is a pure function of case content ------------------------------
def test_b3_depth_and_cued_are_independent_of_evidence_store_insertion_order():
    """Pre-fix, `E_fp_wide` was reported at depth 0 or 1 depending purely on which order the
    items were added to the store — traversal state was mutated inside the pass."""
    seeds = dict(initial_locations=["Parlor", "Cellar"], initial_items=["kit", "Knife"])
    reports = [reachability(EvidenceStore(list(perm)), **seeds)
               for perm in itertools.permutations(evidence_case_items())]
    assert len({tuple(sorted(r.depth.items())) for r in reports}) == 1
    assert len({tuple(sorted(r.cued_depth.items())) for r in reports}) == 1
    assert len({r.cued for r in reports}) == 1
    assert len({r.reachable for r in reports}) == 1


def test_b3_depth_is_a_true_bfs_depth_along_a_dependency_chain():
    """A dependant is strictly deeper than what it depends on. The pre-fix scan collapsed
    both to 0 whenever the root was visited earlier in the same pass.

    The ids matter: `A_root` sorts BEFORE `B_leaf`, so a scan that applies discoveries
    mid-pass reaches the root first and satisfies the leaf within the same level. Naming
    them the other way round hides the defect, so both orderings are asserted."""
    for root_id, leaf_id in (("A_root", "B_leaf"), ("Y_root", "X_leaf")):
        root = _ev(root_id)
        leaf = _ev(leaf_id, prerequisites=(Prereq(kind="EvidenceFound", ref=root_id),))
        for order in ([root, leaf], [leaf, root]):
            report = reachability(EvidenceStore(order), initial_items=["Knife"])
            assert report.depth == {root_id: 0, leaf_id: 1}
            assert report.cued_depth == {root_id: 0, leaf_id: 1}


# --- B-4: genuine source independence (I-37) -------------------------------------------
_P = At(actor="Ann", location="Parlor", interval=(2, 3))


def _src(id_, created_by, requires=(), **kw):
    return _ev(id_, created_by=created_by,
               implications=(Implication(proposition=_P, requires=requires),), **kw)


def test_b4_two_items_with_no_recorded_source_are_not_independent():
    """`created_by=None` is unknown provenance, not distinct provenance. Fail closed."""
    assert corroborates(_src("E1", None), _src("E2", None), _P) is False
    assert corroborates(_src("E1", None), _src("E2", "wipe"), _P) is False


def test_b4_a_shared_prerequisite_is_a_shared_source():
    e1, e2 = _src("E1", "grip", ("S_root",)), _src("E2", "wipe", ("S_root",))
    assert corroborates(e1, e2, _P, EvidenceStore([e1, e2])) is False


def test_b4_transitive_derivation_is_not_independence():
    """E1 -> M -> E2. Only the direct edge was checked pre-fix, so any chain of length >= 2
    laundered a dependent record into a second source."""
    e1 = _src("E1", "grip", ("M",))
    mid = _src("M", "mid", ("E2",))
    e2 = _src("E2", "wipe")
    assert corroborates(e1, e2, _P, EvidenceStore([e1, mid, e2])) is False


def test_b4_planted_evidence_is_never_a_corroborating_source():
    """§19.5 puts planted material at L0 — "never admissible for the solver" — so it cannot
    supply the second source that promotes a proposition to L2."""
    authentic = _src("E1", "grip")
    planted = _src("E2", "plant", authentic=False, planted_by="plant")
    store = EvidenceStore([authentic, planted])
    assert corroborates(authentic, planted, _P, store) is False
    assert corroborates(planted, authentic, _P, store) is False


def test_b4_genuinely_independent_items_still_corroborate():
    """The guard must not collapse to "nothing ever corroborates": distinct creating events,
    disjoint derivation, both authentic."""
    e1, e2 = _src("E1", "grip", ("S_a",)), _src("E2", "wipe", ("S_b",))
    store = EvidenceStore([e1, e2])
    assert corroborates(e1, e2, _P, store) is True
    assert corroborates(e2, e1, _P, store) is True       # symmetric
    assert corroborates(_src("E1", "grip"), _src("E2", "wipe"), _P) is True  # no requires, no store


# --- B-5: granularity shrinks what a claim asserts, it never widens it ------------------
def test_b5_a_sharp_claim_inside_a_vague_one_is_not_a_contradiction():
    """§13.2's second clause, verbatim. Pre-fix this returned presence at severity 1.0."""
    sharp = At(actor="David", location="Study", interval=(60, 65))
    vague = At(actor="David", location="Kitchen", interval=(0, 120))
    assert contradiction(sharp, vague, granularity_b=60) is None
    assert contradiction(vague, sharp, granularity_a=60) is None


def test_b5_vagueness_never_turns_a_gap_into_an_overlap_in_any_rule():
    """All three interval rules shared the widening bug; all three are checked."""
    assert contradiction(At(actor="X", location="Study", interval=(10, 20)),
                          At(actor="X", location="Kitchen", interval=(40, 50)),
                          granularity_a=30, granularity_b=30) is None
    assert contradiction(At(actor="X", location="Kitchen", interval=(10, 20)),
                          NotAt(actor="X", location="Kitchen", interval=(40, 50)),
                          granularity_a=30, granularity_b=30) is None
    assert contradiction(Saw(observer="Elena", subject="David", location="Kitchen",
                              interval=(10, 20), identified=True),
                          At(actor="David", location="Library", interval=(40, 50)),
                          granularity_a=30, granularity_b=30) is None


def test_b5_a_genuine_overlap_still_contradicts_at_every_granularity_that_asserts_it():
    """The guard must not silence real contradictions: the shrunk intervals still overlap."""
    a = At(actor="X", location="Study", interval=(0, 100))
    b = At(actor="X", location="Kitchen", interval=(0, 100))
    for g in (0, 10, 40):
        c = contradiction(a, b, granularity_a=g, granularity_b=g)
        assert c is not None and c.kind == "presence"


def test_b5_travel_uses_the_asserted_interval_not_the_authored_span():
    """A vaguer claim commits to fewer ticks, so the traveller has MORE time, never less —
    the gap must be computed on what the claims assert."""
    from tests.evidence.fixtures.vance_evidence import vance_v03_evidence
    case = vance_v03_evidence()[0]
    a = At(actor="David", location="Hall", interval=(0, 1))
    b = At(actor="David", location="Gazebo", interval=(1, 2))   # Hall->Gazebo needs 3 minutes
    assert contradiction(a, b, case=case).kind == "travel"      # sharp: still infeasible
    assert contradiction(a, b, granularity_a=5, granularity_b=5, case=case) is None
