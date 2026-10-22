"""Property tests (§28.3), Phase 2 exit criteria: "provenance chain property (I-8);
retrieval determinism/monotonicity"."""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from eidolon.minds.admissibility import admissibility_level
from eidolon.minds.belief import BeliefStore, form_beliefs
from eidolon.minds.epistemic import EpistemicState
from eidolon.minds.knowledge import propagate_knowledge
from eidolon.minds.memory import CueSet, cue_overlap, encode_memories, score
from eidolon.minds.provenance import AdmissibilityLevel, InvestigationTold
from eidolon.minds.soundness import check_knowledge_soundness
from eidolon.world.facts import FactIndex
from tests.world.fixtures.vance import vance_v03

_case, _ = vance_v03()
_store = propagate_knowledge(_case)
_fi = FactIndex(_case)
_beliefs = BeliefStore()
_memories = []
for _actor in _case.living_actors():
    _result = form_beliefs(_actor, _store, _case, _fi)
    for _b in _result.beliefs:
        _beliefs.add(_b)
    _memories += encode_memories(_actor, list(_result.beliefs), _store, _case)


@given(st.sampled_from(_store.all()))
@settings(max_examples=200, deadline=None)
def test_property_every_generated_entry_is_v2_sound(entry):
    """I-8, sampled over every entry `propagate_knowledge` actually produced for
    `vance_v03`: each one individually passes the soundness checker."""
    from eidolon.minds.knowledge import KnowledgeStore
    single = KnowledgeStore([entry])
    assert check_knowledge_soundness(single, _case) == []


@given(st.sampled_from(_store.all()))
@settings(max_examples=200, deadline=None)
def test_property_admissibility_never_exceeds_l1_without_told_or_inferred_chain(entry):
    """Base provenance (no corroboration modelled at Phase 2, `admissibility.py`
    docstring): Witnessed/Participated/Absence/Background/Read entries are always
    exactly L1, never accidentally L2/L3."""
    if entry.source.kind in ("Witnessed", "Participated", "Absence", "Background", "Read"):
        assert admissibility_level(entry.id, _store, _beliefs) == AdmissibilityLevel.L1


@given(st.sampled_from(_memories) if _memories else st.none(),
       st.integers(min_value=0, max_value=10000), st.integers(min_value=0, max_value=10000))
@settings(max_examples=150, deadline=None)
def test_property_retrieval_score_monotone_in_memory_strength(memory, lo, hi):
    """§8.4 retrieval is pure and its score is monotone non-decreasing in the overlay
    strength — raising `memory_strength` never lowers the score for the same cues."""
    if memory is None:
        return
    lo, hi = sorted((lo, hi))
    cues = memory.cues if memory.cues.tags() else CueSet(entities=("Elena",))
    low = EpistemicState(memory_strength={memory.id: lo})
    high = EpistemicState(memory_strength={memory.id: hi})
    assert score(memory, low, cues) <= score(memory, high, cues) + 1e-9


@given(st.sampled_from(_memories) if _memories else st.none())
@settings(max_examples=150, deadline=None)
def test_property_retrieval_is_deterministic_pure_function(memory):
    """Same inputs, called twice, produce the exact same score — no hidden state."""
    if memory is None:
        return
    cues = CueSet(entities=("Elena", "David"), location="Study", topic_tags=("at",))
    epistemic = EpistemicState()
    assert score(memory, epistemic, cues) == score(memory, epistemic, cues)


@given(
    e1=st.lists(st.text(alphabet="ABCDE", min_size=1, max_size=1), max_size=4, unique=True),
    e2=st.lists(st.text(alphabet="ABCDE", min_size=1, max_size=1), max_size=4, unique=True),
)
@settings(max_examples=200, deadline=None)
def test_property_cue_overlap_is_bounded_jaccard(e1, e2):
    a, b = CueSet(entities=tuple(e1)), CueSet(entities=tuple(e2))
    ov = cue_overlap(a, b)
    assert 0.0 <= ov <= 1.0
    assert cue_overlap(a, b) == cue_overlap(b, a)  # symmetric


@given(st.sampled_from(_store.all()))
@settings(max_examples=200, deadline=None)
def test_property_investigation_told_would_be_rejected_by_the_added_knowledge_gate(entry):
    """No entry `propagate_knowledge` produces at generation time carries
    `InvestigationTold` — that provenance is runtime-only (§6.5), reachable exclusively
    through `KnowledgeAdded`, whose `apply_epistemic` gate rejects anything else (already
    covered directly in `test_epistemic_and_character_fold.py`; this asserts the
    generation-time half of that guarantee)."""
    assert not isinstance(entry.source, InvestigationTold)
