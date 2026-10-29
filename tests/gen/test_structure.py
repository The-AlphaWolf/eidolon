"""Phase 6 review I-5: V-5 CONFIRMS the elimination structure a package declares (I-43's third step) and, when the CaseLog does not
realise it, names the innocent and the window (§19.5's diagnostic). Before, `pkg.structure` was a constant nobody read."""
from __future__ import annotations

import pytest

from eidolon.gen.pipeline import structure_problems
from tests.solve.helpers import GOLDEN, loaded


@pytest.mark.parametrize("skel,seed", GOLDEN)
def test_I5_every_golden_realises_the_structure_it_declares(skel, seed):
    assert structure_problems(loaded(skel, seed).package) == []


@pytest.mark.parametrize("skel,seed", GOLDEN)
def test_I5_a_declared_structure_the_log_does_not_realise_is_reported_by_name(skel, seed):
    p = loaded(skel, seed).package
    innocents = sorted(a for a in p.case.living_actors() if a != p.solution.murderer)
    wide = p.model_copy(update={"structure": p.structure.model_copy(update={"alibi_window": 50})})
    said = structure_problems(wide)
    assert said and all(any(a in s for s in said) for a in innocents[:1]), said
    tight = p.model_copy(update={"structure": p.structure.model_copy(update={"secret_clearance": 200})})
    assert any("protected interval" in s for s in structure_problems(tight))


def test_I5_v5_refuses_to_seal_a_case_whose_structure_is_not_realised():
    from eidolon.gen.pipeline import validate
    p = loaded("study_party", 4).package
    rep = validate(p.model_copy(update={"structure": p.structure.model_copy(update={"alibi_window": 50})}).sealed())
    assert rep.failed_at == "V-5" and any(s.startswith("structure:") for s in rep.problems), (rep.failed_at, rep.problems[:3])
