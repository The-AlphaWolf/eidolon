"""`new_session` — the ONE constructor of a playable `GameState` from a sealed case (ADR-24/29, I-50).

The Phase 7 loader must call this and nothing else. It:
  * derives knowledge, beliefs and memories from the CaseLog (Phase 2);
  * APPLIES the package's `memory_boosts` to `Memory.strength_0` — §19.4's load-time obligation ("generation
    raises that memory's `strength_0`"), previously honoured only inside V-4's own check, so a real session
    never saw a boosted memory (RB-2/C5);
  * starts with an EMPTY ledger, empty `known_statements`, empty `known_accounts`, empty discovery: nothing is
    pre-heard, nothing is pre-seeded. A statement or an account token becomes heard only through a committed
    turn (I-50).

The package carries no `Personality` (audit I-6: the flavor slot is not built), so the harness default below is an
explicit, overridable argument — a BOT-HARNESS default, never written back into the package.
"""
from __future__ import annotations

import hashlib

from ..decision.claims import StatementStore
from ..decision.events import DecisionState
from ..decision.secrets import SecretStore
from ..decision.turn import GameState
from ..evidence.discovery import DiscoveryState
from ..evidence.model import EvidenceStore
from ..minds.belief import BeliefStore, form_beliefs
from ..minds.character import Personality, VoiceSpec, initial_character_state
from ..minds.epistemic import EpistemicState
from ..minds.knowledge import propagate_knowledge
from ..minds.memory import encode_memories
from ..world.facts import FactIndex
from .package import CasePackage, SealedCase


def _h(*parts) -> int:
    return int(hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:12], 16)


def default_personality(actor: str, seed: int) -> Personality:
    """Deterministic, derived from the case id and the actor's name (no RNG, I-6)."""
    def w(key, lo, hi):
        return lo + (_h(seed, actor, key) % 1000) / 1000 * (hi - lo)
    return Personality(composure_base=w("comp", 0.35, 0.75), volatility=w("vol", 0.1, 0.6),
                       deference=w("def", 0.2, 0.8), guile=w("guile", 0.2, 0.8),
                       talkativeness=w("talk", 0.3, 0.7), self_preservation=w("self", 0.4, 0.9),
                       voice=VoiceSpec(voice_register="plain"))   # the voice is derived at render time (`decision.voice`)


def new_session(case: CasePackage | SealedCase, personalities: dict | None = None, *, seed: int = 0) -> GameState:
    pkg = case.package if isinstance(case, SealedCase) else case
    world = pkg.case
    knowledge = propagate_knowledge(world)
    idx = FactIndex(world)
    boosts = {b.memory: b.strength_bp for b in pkg.memory_boosts}
    beliefs: list = []
    memories: dict[str, tuple] = {}
    for actor in sorted(world.living_actors()):
        own = form_beliefs(actor, knowledge, world, idx).beliefs
        beliefs += list(own)
        mems = encode_memories(actor, list(own), knowledge, world)
        memories[actor] = tuple(m.model_copy(update={"strength_0": max(m.strength_0, boosts[m.id])})
                                if m.id in boosts else m for m in mems)
    people = personalities or {}
    # The verdict is judged against the PROOF's unique survivor — what `load_sealed_text` verified (I-58, PI-7) — never the
    # declared `solution`. A bare package carries no proof, so its session has no verdict to give (accusations refused).
    proof = case.proof if isinstance(case, SealedCase) else {}
    murderer = proof["survivors"][0] if proof.get("unique") is True and len(proof.get("survivors", ())) == 1 else None
    return GameState(case=world, knowledge=knowledge, beliefs=BeliefStore(beliefs), memories=memories,
                     secrets=SecretStore(pkg.secrets), evidence=EvidenceStore(pkg.evidence),
                     characters={a: initial_character_state(a, people.get(a) or default_personality(a, seed))
                                 for a in sorted(world.living_actors())},
                     epistemic=EpistemicState(), discovery=DiscoveryState(),
                     decision=DecisionState(statements=StatementStore()), seed=seed, murderer=murderer)


def decision_context(pkg: CasePackage):
    """The Phase 4 view of a sealed package, for V-3 and the murderer-peel bot. Discovery starts EMPTY:
    `derive_breaker_sets` supplies its own per-subset discovery state, so a breaker set is what that subset alone
    establishes (§13.3), never what the whole sealed pool would. The ledger starts empty too (I-50): the declared
    account tokens are the only pre-authored material, and they are derived, not scripted."""
    from ..decision.context import DecisionContext
    return DecisionContext(case=pkg.case, knowledge=propagate_knowledge(pkg.case), beliefs=BeliefStore(),
                           secrets=SecretStore(pkg.secrets), evidence=EvidenceStore(pkg.evidence),
                           statements=StatementStore(), epistemic=EpistemicState(), discovery=DiscoveryState(),
                           accounts=tuple(sorted(pkg.accounts)))
