"""ADR-22 regression tests: the closed `ActionKind` vocabulary and the entailment from an
action to the `EventKind`s that make it true (§4.5, §4.7, `eidolon/world/actions.py`).

Oracle discipline as elsewhere: assertions come from the architecture's stated rule, from the
fixture's declared timeline, or from an invariance property — never from restating the
entailment table back at itself. The one place the table is enumerated (`_TOUCH_KINDS`) is
checked against what the CaseLog actually licenses, not against a copy of the constant.
"""
from __future__ import annotations

from typing import get_args

import pytest
from pydantic import ValidationError

from eidolon.world.actions import (
    ACTION_ENTAILED_BY, ENTAILED_ACTIONS, EVENT_KINDS, ActionKind, entailing_kinds,
)
from eidolon.world.events import EventKind, Event, Perceptibility
from eidolon.world.facts import FactIndex
from eidolon.world.physics import Implication, check_physics
from eidolon.world.propositions import Did, DidNot
from tests.world.fixtures.vance import (
    ACTORS, LOCATIONS, OBJECTS, TRAVEL, _PERCEPTION_V03, _stays, vance_v03,
)
from eidolon.world.case import Case


# --------------------------------------------------------------- the vocabulary is closed
def test_action_kind_is_a_superset_of_event_kind():
    """§4.7's schema block has always typed `Did.action` as `ActionKind`. Every `EventKind`
    must remain a legal action, or every existing `Did` fact the perception model derives
    (`Did(actor, e.kind, …)`) stops validating."""
    assert EVENT_KINDS <= set(get_args(ActionKind))
    assert set(get_args(EventKind)) == EVENT_KINDS


def test_the_only_action_that_is_not_an_event_kind_is_touch():
    """ADR-22 adds exactly one entailed action. `enter`/`hear` appear in the document's
    Phase 4 worked example but are deferred (see the ADR): their entailment source is
    presence and perception, not event kinds, and `hear`'s subject is a `sound_kind` that
    `Did`'s slots do not carry."""
    assert ENTAILED_ACTIONS == {"touch"}


def test_every_action_in_the_vocabulary_has_an_entailment_rule():
    """A vocabulary member with no rule resolves to Unknown, which would make a legal
    proposition permanently unsettleable. The table must stay total over `ActionKind`."""
    assert set(ACTION_ENTAILED_BY) == set(get_args(ActionKind))
    for action, kinds in ACTION_ENTAILED_BY.items():
        assert kinds, action
        assert kinds <= EVENT_KINDS, (action, kinds - EVENT_KINDS)


def test_an_event_named_action_entails_exactly_its_own_event_kind():
    """Identity for the event-named half: `Did(a, "Attack", …)` asserts an `Attack` occurred
    and nothing else. Widening one of these would silently reinterpret existing facts."""
    for kind in EVENT_KINDS:
        assert entailing_kinds(kind) == {kind}


@pytest.mark.parametrize("bad", ["attack", "ATTACK", "touching", "frobnicate", "", "Touch"])
def test_an_action_outside_the_vocabulary_is_rejected_at_construction(bad):
    """The typed/schema-level half of ADR-22: free text never enters the proposition schema.
    Matching is exact — the pre-ADR implementation compared `action.lower()` against
    `EventKind.lower()`, which accepted `"attack"`; a closed `Literal` does not."""
    with pytest.raises(ValidationError):
        Did(actor="David", action=bad, interval=(0, 10))
    with pytest.raises(ValidationError):
        DidNot(actor="David", action=bad, interval=(0, 10))


def test_entailing_kinds_reports_unknown_rather_than_guessing():
    assert entailing_kinds("frobnicate") is None
    assert entailing_kinds("attack") is None  # exact spelling, not case-insensitive


# ------------------------------------------------------- `touch` against the golden case
def test_touch_is_true_for_the_contact_the_caselog_actually_logs():
    """Oracle: `vance_v03`'s own `attack` event — `objects=("Glass1",)`, actor David,
    location Study, interval (76,77). A fingerprint on that glass licenses "David handled
    it", which is what `E_trace` asserts."""
    case, _ = vance_v03()
    index = FactIndex(case)
    assert index.truth_value(Did(actor="David", action="touch", object="Glass1",
                                 location="Study", interval=(12, 120))) is True
    assert index.truth_value(DidNot(actor="David", action="touch", object="Glass1",
                                    location="Study", interval=(12, 120))) is False


def test_touch_does_not_name_the_event_kind_that_produced_it():
    """The whole point of the entailed action (§5.1's own example): a trace under-determines
    the event. `touch` must be settleable without the claim committing to `Attack` — and it
    must NOT imply the specific kind, which the pre-ADR `action="Attack"` transcription did."""
    case, _ = vance_v03()
    index = FactIndex(case)
    contact = Did(actor="Elena", action="touch", object="Glass1", location="Study", interval=(0, 120))
    assert index.truth_value(contact) is True  # Elena's `clean` event, kind Clean
    named = Did(actor="Elena", action="Attack", object="Glass1", location="Study", interval=(0, 120))
    assert index.truth_value(named) is False   # she cleaned it; she did not attack with it


def test_touch_is_false_for_an_actor_who_never_handled_the_object():
    """Oracle: the fixture's event list — only David (`attack`) and Elena (`clean`) are
    logged with Glass1 in `vance_v03`."""
    case, _ = vance_v03()
    index = FactIndex(case)
    handlers = {e.actor for e in case.events if "Glass1" in e.objects}
    assert handlers == {"David", "Elena"}, handlers
    for actor in set(case.actors) - handlers:
        assert index.truth_value(
            Did(actor=actor, action="touch", object="Glass1", interval=(0, 120))) is False


@pytest.mark.parametrize("kind", sorted(ACTION_ENTAILED_BY["touch"]))
def test_every_kind_in_the_touch_set_really_does_license_a_touch(kind):
    """Checks the table against the world rather than against itself: build a one-event case
    for each entailing kind and assert the CaseLog licenses `touch` on the object it names."""
    handling = Event(id="handling", kind=kind, interval=(10, 12), location="Kitchen",
                     actor="Elena", objects=("Glass1",),
                     perceptibility=Perceptibility(sight=0.5))
    events = tuple(_stays("Elena", [("Kitchen", 0, 120)])) + (handling,)
    case = Case(id="one_event", t_investigation=120, actors=ACTORS, locations=LOCATIONS,
                objects=OBJECTS, travel_edges=TRAVEL, perception_edges=_PERCEPTION_V03,
                events=events, rels=())
    index = FactIndex(case)
    assert index.truth_value(Did(actor="Elena", action="touch", object="Glass1",
                                 interval=(0, 120))) is True
    # ...and the kind itself is still settled independently — entailment does not collapse
    # the two vocabularies into one.
    assert index.truth_value(Did(actor="Elena", action=kind, object="Glass1",
                                 interval=(0, 120))) is True


@pytest.mark.parametrize("kind", sorted(EVENT_KINDS - ACTION_ENTAILED_BY["touch"]))
def test_no_kind_outside_the_touch_set_licenses_a_touch(kind):
    """The conservative direction, and the one that matters: over-claiming `touch` would
    manufacture forensic contact out of an event that never involved handling. `Read` is the
    interesting member — reading does not entail picking the document up."""
    seen = Event(id="seen", kind=kind, interval=(10, 12), location="Kitchen", actor="Elena",
                 objects=("Glass1",), perceptibility=Perceptibility(sight=0.5))
    events = tuple(_stays("Elena", [("Kitchen", 0, 120)])) + (seen,)
    case = Case(id="one_event", t_investigation=120, actors=ACTORS, locations=LOCATIONS,
                objects=OBJECTS, travel_edges=TRAVEL, perception_edges=_PERCEPTION_V03,
                events=events, rels=())
    assert FactIndex(case).truth_value(
        Did(actor="Elena", action="touch", object="Glass1", interval=(0, 120))) is False


def test_touch_with_no_object_asks_about_any_object_and_needs_one():
    """`Did(a, "touch")` with no object asks whether the actor handled ANYTHING. A
    bare-handed `Attack` names no object and must not satisfy it — otherwise a claim about
    object contact would be settled by an event that involved none."""
    bare = Event(id="bare", kind="Attack", interval=(10, 12), location="Kitchen", actor="Elena",
                 participants=("Margaret",), perceptibility=Perceptibility(sight=1.0))
    events = (tuple(_stays("Elena", [("Kitchen", 0, 120)]))
              + tuple(_stays("Margaret", [("Kitchen", 0, 120)])) + (bare,))
    case = Case(id="bare_handed", t_investigation=120, actors=ACTORS, locations=LOCATIONS,
                objects=OBJECTS, travel_edges=TRAVEL, perception_edges=_PERCEPTION_V03,
                events=events, rels=())
    index = FactIndex(case)
    assert index.truth_value(Did(actor="Elena", action="Attack", interval=(0, 120))) is True
    assert index.truth_value(Did(actor="Elena", action="touch", interval=(0, 120))) is False

    # ...and it IS true once the same actor handles something.
    with_object = case.model_copy(update={"events": case.events + (
        Event(id="wash", kind="Clean", interval=(20, 21), location="Kitchen", actor="Elena",
              objects=("Glass1",)),)})
    assert FactIndex(with_object).truth_value(
        Did(actor="Elena", action="touch", interval=(0, 120))) is True


# ------------------------------------------------------- slots and negation still hold
def test_touch_respects_the_location_and_interval_slots():
    """Entailment widens which EVENT KINDS match, never which slots. Oracle: the fixture —
    David's only Glass1 contact is in the Study at (76,77)."""
    case, _ = vance_v03()
    index = FactIndex(case)
    assert index.truth_value(Did(actor="David", action="touch", object="Glass1",
                                 location="Kitchen", interval=(0, 120))) is False
    assert index.truth_value(Did(actor="David", action="touch", object="Glass1",
                                 location="Study", interval=(0, 40))) is False
    assert index.truth_value(Did(actor="David", action="touch", object="Glass1",
                                 location="Study", interval=(70, 80))) is True


def test_didnot_touch_is_the_exact_negation_wherever_did_touch_is_settled():
    """`DidNot` must stay the strict negation of `Did` on the same slots (§4.7's "explicit
    negation"), for the entailed action as much as for the event-named ones."""
    case, _ = vance_v03()
    index = FactIndex(case)
    for actor in case.actors:
        for obj in case.objects:
            did = index.truth_value(Did(actor=actor, action="touch", object=obj, interval=(0, 120)))
            not_did = index.truth_value(DidNot(actor=actor, action="touch", object=obj, interval=(0, 120)))
            assert did is not None and not_did is (not did), (actor, obj)


# ----------------------------------------------------------- nothing else moved (I-4, P-0)
def test_the_golden_cases_evidence_is_still_clean_under_the_new_transcription():
    """`E_trace` now says `touch` instead of over-claiming `Attack`. The world must still not
    refute it (P-0), and `vance_v03` must keep its clean physics verdict."""
    case, evidence = vance_v03()
    assert ("E_trace", ) in [(eid,) for eid, _ in evidence]
    trace = next(imp for eid, imp in evidence if eid == "E_trace")
    assert trace.proposition.action == "touch"
    assert FactIndex(case).truth_value(trace.proposition) is True
    assert check_physics(case, evidence) == []


def test_perception_still_derives_event_named_did_facts_only():
    """Epistemic separation: entailment is a TRUTH relation on `FactIndex`, not a knowledge
    generation rule. §4.8 keeps emitting `Did(actor, e.kind, …)` for participants — adding
    entailed actions there would invent knowledge entries nobody acquired and change what
    V-2 checks."""
    from eidolon.world.perception import derive_perception
    case, _ = vance_v03()
    actions = {f.proposition.action for f in derive_perception(case) if f.proposition.kind == "Did"}
    assert actions <= EVENT_KINDS, actions - EVENT_KINDS
    assert "touch" not in actions


def test_the_action_vocabulary_change_does_not_move_the_case_hash():
    """I-4: `ActionKind` types a PROPOSITION field. No `Case` field changed, so no sealed
    case's content hash may move — evidence implications live outside the `Case`."""
    case, _ = vance_v03()
    reloaded = Case.model_validate_json(case.model_dump_json())
    assert reloaded.content_hash() == case.content_hash()
