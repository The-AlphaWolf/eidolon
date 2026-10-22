from eidolon.world import interval as iv


def test_intersect_and_overlap():
    assert iv.intersect((0, 10), (5, 15)) == (5, 10)
    assert iv.intersect((0, 5), (5, 10)) is None  # half-open: touching is not overlap
    assert iv.overlaps((0, 10), (9, 20))
    assert not iv.overlaps((0, 5), (5, 10))


def test_contains():
    assert iv.contains((0, 10), (2, 8))
    assert not iv.contains((0, 10), (2, 12))
    assert iv.contains_tick((0, 10), 9)
    assert not iv.contains_tick((0, 10), 10)


def test_shrink_and_widen():
    assert iv.shrink((0, 10), 2) == (2, 8)
    assert iv.shrink((0, 4), 2) is None  # granularity swallows the whole interval
    assert iv.widen((5, 10), 2) == (3, 12)
    assert iv.widen((0, 10), 5, lo=0, hi=100) == (0, 15)  # clamped at lo


def test_subtract_and_union():
    assert iv.subtract((0, 10), [(2, 4), (6, 8)]) == [(0, 2), (4, 6), (8, 10)]
    assert iv.subtract((0, 10), [(0, 10)]) == []
    assert iv.union([(0, 5), (5, 10), (20, 25)]) == [(0, 10), (20, 25)]


def test_valid():
    assert iv.valid((0, 1))
    assert not iv.valid((5, 5))
    assert not iv.valid((5, 3))


def test_ticks():
    assert list(iv.ticks((3, 6))) == [3, 4, 5]
