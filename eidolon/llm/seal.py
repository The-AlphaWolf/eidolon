"""The lexical guard's deny-set compiler and the seal-time guard (roadmap Phase 5; I-19, §33.2 #2).

Generation-time free text — voice specs, `reveals_text`, frames — is written before play and
later handed to a renderer or shown to the player. I-19: it must pass the protected-phrase guard
for the speaking character when the case is sealed. The Sealer (Phase 6) calls these; this module
only supplies the check.

The deny-set is compiled from PROTECTED facts and is engine-side only — it is used to refuse text,
never given to a model (ADR-8).
"""
from __future__ import annotations

from typing import Iterable

from ..decision.envelope import EnvelopeClaim
from ..decision.llm import render_claim
from ..decision.secrets import SecretStore
from ..minds.character import VoiceSpec
from ..world.case import Case
from ..world.ids import ActorId
from ..world.propositions import entities


def compile_deny_set(secrets: SecretStore, case: Case, speaker: ActorId) -> frozenset[str]:
    """Lowercase phrases the speaker's generation-time text must not contain: the canonical
    first-person rendering of each fact protected by ANY secret the speaker does not own (their
    own protected facts are voiced by authored layers, not by free text), and the display names
    of the objects those facts name (the weapon, the traceable item).

    ponytail: canonical renderings plus object names only; add paraphrase tables (§33.2 #2's
    "common phrasings") when the injection corpus shows a leak this misses."""
    phrases: set[str] = set()
    for secret in secrets.all():
        if secret.owner == speaker:
            continue
        for prop in secret.protected:
            phrases.add(render_claim(EnvelopeClaim(id="", proposition=prop), case).lower())
            phrases |= {case.objects[o].name.lower() for o in entities(prop)[2] if o in case.objects}
    return frozenset(p for p in phrases if p)


def guard_text(text: str, deny: Iterable[str]) -> list[str]:
    """`SEAL_PROTECTED_PHRASE:<phrase>` for every deny phrase present in `text`."""
    low = text.lower()
    return sorted(f"SEAL_PROTECTED_PHRASE:{p}" for p in deny if p in low)


def voice_violations(voice: VoiceSpec, deny: Iterable[str]) -> list[str]:
    """I-19 for a `VoiceSpec` (the register, idiom and tics that go to the renderer verbatim)."""
    deny = tuple(deny)
    return [v for text in (voice.voice_register, *voice.idiom, *voice.tics) for v in guard_text(text, deny)]
