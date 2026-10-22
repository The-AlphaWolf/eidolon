"""Evidence construction, provenance fields, and `EvidenceStore` (§5.1)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from eidolon.evidence.model import (
    DiscoverySpec, Evidence, EvidenceStore, Implication, Prereq, combined_strength,
)
from eidolon.world.propositions import Did


def _implication(strength=1.0, requires=()):
    return Implication(proposition=Did(actor="Ann", action="touch", object="Knife",
                                        location="Parlor", interval=(2, 3)),
                        strength=strength, requires=requires)


def _evidence(**overrides):
    base = dict(id="E1", kind="Fingerprint", object="Knife",
                implications=(_implication(),),
                discovery=DiscoverySpec(action="Dust", at="Knife"))
    base.update(overrides)
    return Evidence(**base)


def test_evidence_construction_round_trips_every_field():
    ev = _evidence(location_at_investigation="Parlor", created_by="grip", created_at=(2, 3),
                    reliability=0.8, known_to={"Bea": "K0001"}, interacted=(("Ann", "grip"),),
                    supports=("H1",), contradicts=("H2",), load_bearing=True)
    assert ev.object == "Knife" and ev.created_by == "grip" and ev.reliability == 0.8
    assert ev.known_to == {"Bea": "K0001"}
    assert ev.interacted == (("Ann", "grip"),)


def test_evidence_is_frozen_i4():
    ev = _evidence()
    with pytest.raises(ValidationError):
        ev.reliability = 0.1  # type: ignore[misc]


def test_evidence_grounded_construction_is_the_common_case():
    """"Evidence construction" / "grounded evidence": a well-formed item with everything
    §5.1 asks for constructs without error — grounding against a `Case` is `grounding.py`'s
    separate, external concern (a `Case` isn't even required to construct one)."""
    ev = _evidence()
    assert ev.implications[0].proposition.action == "touch"


@pytest.mark.parametrize("field,bad", [("reliability", 1.5), ("reliability", -0.1)])
def test_malformed_evidence_reliability_rejected(field, bad):
    """"Malformed evidence": out-of-range scalars fail at construction (fail closed, I-15),
    the same discipline `Bp` uses for runtime scalars (I-17)."""
    with pytest.raises(ValidationError):
        _evidence(**{field: bad})


@pytest.mark.parametrize("bad", [1.5, -0.5])
def test_malformed_implication_strength_rejected(bad):
    with pytest.raises(ValidationError):
        Implication(proposition=Did(actor="Ann", action="touch", interval=(0, 1)), strength=bad)


def test_malformed_evidence_kind_rejected():
    """`EvidenceKind` is closed (ADR-22's own discipline applied here) — an unknown kind
    fails construction rather than silently accepting free text."""
    with pytest.raises(ValidationError):
        _evidence(kind="Ectoplasm")  # type: ignore[arg-type]


def test_combined_strength_multiplies_reliability_and_implication_strength():
    ev = _evidence(reliability=0.5)
    imp = Implication(proposition=Did(actor="Ann", action="touch", interval=(0, 1)), strength=0.4)
    assert combined_strength(ev, imp) == pytest.approx(0.2)


def test_evidence_store_crud_and_duplicate_rejection():
    store = EvidenceStore()
    e1 = _evidence(id="E1")
    store.add(e1)
    assert store.get("E1") is e1
    assert store.get("nope") is None
    assert store.all() == [e1]
    with pytest.raises(ValueError):
        store.add(_evidence(id="E1"))


def test_evidence_store_by_object_indexes_only_evidence_naming_that_object():
    store = EvidenceStore([_evidence(id="E1", object="Knife"), _evidence(id="E2", object=None),
                            _evidence(id="E3", object="Knife")])
    assert {e.id for e in store.by_object("Knife")} == {"E1", "E3"}
    assert store.by_object("nothing") == []


def test_evidence_store_constructor_accepts_iterable_and_preserves_all():
    items = [_evidence(id=f"E{i}") for i in range(3)]
    store = EvidenceStore(iter(items))
    assert {e.id for e in store.all()} == {"E0", "E1", "E2"}


def test_discovery_spec_and_prereq_round_trip():
    spec = DiscoverySpec(action="Search", at="Cellar",
                          prerequisites=(Prereq(kind="HasItem", ref="kit"),
                                         Prereq(kind="KnowsAbout", ref="Cellar")),
                          reveals_text="Dusty shelves.", cue="Cellar")
    assert spec.prerequisites[0].kind == "HasItem" and spec.cue == "Cellar"


def test_malformed_prereq_kind_rejected():
    with pytest.raises(ValidationError):
        Prereq(kind="Telepathy", ref="x")  # type: ignore[arg-type]
