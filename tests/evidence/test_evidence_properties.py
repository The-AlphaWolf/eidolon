"""Property tests (§28.3 pattern): invariants checked over many generated inputs rather
than one hand-picked example each. Oracles are independently constructed (brute-force
containment, symmetry, monotonicity) — never a re-implementation of the function under test.
"""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from eidolon.evidence.contradiction import contradiction, corroborates
from eidolon.evidence.discovery import DiscoveryState, can_discover, reachability
from eidolon.evidence.grounding import established_interval
from eidolon.evidence.model import DiscoverySpec, Evidence, EvidenceStore, Implication, Prereq
from eidolon.world.propositions import At
from tests.evidence.fixtures.vance_evidence import evidence_case_store

_locations = ("Kitchen", "Library", "Study", "Hall")
_ticks = st.integers(min_value=0, max_value=40)


def _interval():
    return st.tuples(_ticks, _ticks).filter(lambda t: t[0] < t[1])


# --- contradiction: symmetry and an independent brute-force presence oracle -------------
@given(_interval(), _interval(), st.sampled_from(_locations), st.sampled_from(_locations))
@settings(max_examples=200, deadline=None)
def test_property_presence_contradiction_matches_a_brute_force_tick_scan(i1, i2, l1, l2):
    """Independent oracle: scan every tick by hand for "same actor, two different rooms at
    once" rather than reusing `overlaps`/`widen` — a different code path from `contradiction`
    itself, so this cannot pass by sharing a bug."""
    a = At(actor="X", location=l1, interval=i1)
    b = At(actor="X", location=l2, interval=i2)
    brute = l1 != l2 and any(i1[0] <= t < i1[1] and i2[0] <= t < i2[1] for t in range(0, 41))
    c = contradiction(a, b)
    assert (c is not None and c.kind == "presence") == brute


@given(_interval(), _interval(), st.sampled_from(_locations), st.sampled_from(_locations))
@settings(max_examples=200, deadline=None)
def test_property_contradiction_is_order_independent(i1, i2, l1, l2):
    a = At(actor="X", location=l1, interval=i1)
    b = At(actor="X", location=l2, interval=i2)
    ab = contradiction(a, b, a_id="p", b_id="q")
    ba = contradiction(b, a, a_id="q", b_id="p")
    if ab is None:
        assert ba is None
    else:
        assert ba is not None and ab.kind == ba.kind and ab.severity == ba.severity


# --- established_interval: always a valid, non-empty interval containing every source ----
@given(st.lists(_interval(), min_size=0, max_size=4), _ticks)
@settings(max_examples=200, deadline=None)
def test_property_established_interval_always_contains_every_contributing_source(sources, t_inv):
    store = EvidenceStore()
    stmt = {f"S{i}": iv for i, iv in enumerate(sources)}
    imp = Implication(proposition=At(actor="X", location="Kitchen", interval=(0, 1)),
                       requires=tuple(stmt))
    hull = established_interval(imp, store, t_investigation=t_inv, statement_intervals=stmt)
    assert hull[0] < hull[1]  # a valid half-open interval, never empty
    assert hull[0] <= t_inv and t_inv + 1 <= hull[1]  # the discovery pin is always inside
    for iv in sources:
        assert hull[0] <= iv[0] and iv[1] <= hull[1]


# --- corroborates: symmetry, and never true for a self-comparison -----------------------
@given(st.integers(min_value=0, max_value=1))
@settings(max_examples=10, deadline=None)
def test_property_corroborates_is_symmetric(_ignored):
    store = evidence_case_store()
    items = store.all()
    for a in items:
        for b in items:
            for imp in a.implications:
                assert corroborates(a, b, imp.proposition) == corroborates(b, a, imp.proposition)


def test_property_corroborates_never_true_for_a_self_comparison():
    store = evidence_case_store()
    for ev in store.all():
        for imp in ev.implications:
            assert corroborates(ev, ev, imp.proposition) is False


# --- reachability: monotone in the seed material --------------------------------------
@given(st.sets(st.sampled_from(["Cellar", "kit"]), min_size=0, max_size=2))
@settings(max_examples=8, deadline=None)
def test_property_reachability_is_monotone_in_initial_material(seed):
    """More initial material never SHRINKS what is reachable — an independent monotonicity
    check, not a re-derivation of the BFS."""
    store = evidence_case_store()
    locs = [s for s in seed if s == "Cellar"]
    items = [s for s in seed if s == "kit"]
    small = reachability(store, initial_locations=locs, initial_items=items)
    big = reachability(store, initial_locations=["Cellar"], initial_items=["kit"])
    assert small.reachable <= big.reachable


@given(st.lists(st.sampled_from(["A", "B", "C"]), min_size=0, max_size=6))
@settings(max_examples=100, deadline=None)
def test_property_can_discover_depends_only_on_membership_not_on_order_or_duplicates(seed_list):
    """`DiscoveryState`'s prerequisite sets are unordered by construction — feeding the same
    membership through a shuffled/duplicated list must not change the verdict."""
    ev = Evidence(id="X", kind="Object", implications=(),
                  discovery=DiscoverySpec(action="Look", at="x", prerequisites=(
                      Prereq(kind="KnowsAbout", ref="A"), Prereq(kind="KnowsAbout", ref="B"),
                      Prereq(kind="KnowsAbout", ref="C"))))
    state = DiscoveryState(visited_locations=frozenset(seed_list))
    expected = {"A", "B", "C"} <= set(seed_list)
    assert can_discover(ev, state) == expected
