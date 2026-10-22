"""I-16/I-29, statically: "no peel or slip predicate references composure or verbal
pressure" — checked the way the architecture itself specifies ("Static check on the
predicate signatures"), by inspecting the actual source of the functions that gate
`LayerPeel`/`SLIP`/`CONFESSION`, not by exercising them at runtime (that is
`test_long_conversation.py`'s job).
"""
from __future__ import annotations

import inspect

from eidolon.decision import peel, strategy, weight

FORBIDDEN_NAMES = ("composure", "verbal_pressure")


def _source_mentions(fn, names) -> list[str]:
    src = inspect.getsource(fn)
    return [n for n in names if n in src]


def test_evaluate_peel_never_reads_composure_or_verbal_pressure():
    hits = _source_mentions(peel.evaluate_peel, FORBIDDEN_NAMES)
    assert hits == [], f"evaluate_peel references forbidden state: {hits}"


def test_refutation_weight_never_reads_composure_or_verbal_pressure():
    hits = _source_mentions(weight.refutation_weight, FORBIDDEN_NAMES)
    assert hits == [], f"refutation_weight references forbidden state: {hits}"


def test_slip_candidate_gate_never_reads_composure():
    """`_slip` (§11.7) reads `refutation_weight`, `trigger_topic` and `slips_used` only —
    never `composure` (I-29 removed the `composure_max` conjunct in v0.3)."""
    hits = _source_mentions(strategy._slip, ("composure",))
    assert hits == [], f"_slip references composure: {hits}"


def test_confession_candidate_gate_never_reads_composure_or_pressure():
    hits = _source_mentions(strategy._confession, FORBIDDEN_NAMES)
    assert hits == [], f"_confession references forbidden state: {hits}"


def test_slip_model_has_no_composure_max_field():
    """§10.2: "REMOVED in v0.3: `composure_max`" — a structural guarantee, not just a
    behavioural one: the field cannot be reintroduced without this test noticing."""
    from eidolon.decision.secrets import Slip
    assert "composure_max" not in Slip.model_fields
