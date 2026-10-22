"""Phase 4 — the conversation / decision engine (§10-17 of the architecture).

Builds strictly on `eidolon.world` (canonical truth), `eidolon.minds` (knowledge/belief/
memory/character state) and `eidolon.evidence` (the artifact layer), per the layering rule
(§23.1): `world <- minds <- evidence <- decision`. Nothing here constructs a `Belief` or
`KnowledgeEntry`, and nothing here writes back into an earlier layer's stores — nothing here
mutates `WorldState`, `KnowledgeStore`, `BeliefStore` or `EvidenceStore` either; this layer
only ever reads them and produces its own claims/statements/plans.
"""
