"""Decision-layer ID aliases (§10-16), mirroring `world/ids.py`/`minds/ids.py`/
`evidence/ids.py`'s "plain str, stable and hashable" rule. `StatementId` and
`HypothesisTemplateId` already live in `evidence/ids.py` as forward references from Phase 3;
this module owns everything that is new at this phase.
"""
from __future__ import annotations

SecretId = str
ClaimId = str
HypothesisId = str
ContradictionId = str
TopicId = str
SlipId = str
