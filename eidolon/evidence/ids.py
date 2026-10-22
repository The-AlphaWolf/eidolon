"""Evidence-layer ID aliases (§5), mirroring `world/ids.py` and `minds/ids.py`'s own
"plain str, stable and hashable" rule — name resolution against `Alias` is a parser-time
concern (Phase 5), not this layer's.
"""
from __future__ import annotations

StatementId = str
"""A witness statement's id. The full `Statement` model (utterance text, claims, modality,
sincerity — §12.2) is a Phase 4 model; Phase 3 only needs it as an opaque identifier that
`Implication.requires` and `Prereq(kind="StatementHeard")` can name — the same forward-
reference pattern Phase 2 used for `Distortion.correctable_by`/`SecretId`."""

HypothesisTemplateId = str
"""Generation-time solver tag carried on `Evidence.supports`/`.contradicts` (§5.1: "tags for
the solver"). The `Hypothesis` player-board model (§16) is Phase 4; Phase 3 only stores and
passes through the opaque id."""
