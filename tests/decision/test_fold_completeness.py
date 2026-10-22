"""I-31, T-23's own shape for the Phase 4 slice: every runtime-mutable `DecisionState` field
is written by some `apply_decision` branch, and none is left for a caller to patch by hand."""
from __future__ import annotations

import inspect

from eidolon.decision.events import DecisionState, apply_decision

# Fields whose only legal writer is a specific event kind (I-31's own per-field mapping,
# mirrored here the way `minds`'s own T-23-equivalent would be written once it exists).
EXPECTED_WRITERS = {
    "statements": ("ClaimMade", "ClaimRetracted"),
    "layer_peels": ("LayerPeel",),
    "hypotheses": ("HypothesisChanged",),
    "accusations": ("Accusation",),
    "meta_attempts": ("MetaAttemptLogged",),
    "validation_failures": ("ValidationFailure",),
    "fallbacks": ("FallbackUsed",),
    "incidentals": ("IncidentalPinned",),
    "solved": ("CaseSolved",),
}


def test_every_decisionstate_field_has_a_named_writer():
    fields = {f.name for f in __import__("dataclasses").fields(DecisionState)}
    assert fields == set(EXPECTED_WRITERS)


def test_apply_decision_source_mentions_every_expected_event_kind():
    src = inspect.getsource(apply_decision)
    for field, kinds in EXPECTED_WRITERS.items():
        for kind in kinds:
            assert kind in src, f"apply_decision never mentions {kind} (writer of {field!r})"


def test_apply_decision_never_recomputes_a_weight_or_score():
    """I-22: "the fold applies recorded outcomes only... never re-runs strategy, retrieval
    scoring, weights". `apply_decision` must not import the modules that compute them."""
    import eidolon.decision.events as events_module
    forbidden_modules = ("eidolon.decision.weight", "eidolon.decision.strategy", "eidolon.decision.peel")
    src_file = inspect.getsource(events_module)
    for mod in forbidden_modules:
        assert mod not in src_file
