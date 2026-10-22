"""§9 public speaking style — safe to give the LLM: how a character TALKS, never what it knows.

Derived at RENDER time, never stored in the character state. `store.initial_digest` binds the whole derived initial state into a
save's genesis (C-3), so a voice derived in `solve.session` refused every save made before it existed (review NR-B1). Here it is a
pure function of the actor's name and the session seed — never of secrets, guilt or sincerity — so it is a constant of the
character and can tell nobody anything (§22.3). An AUTHORED voice (anything but the legacy session default) is used as it is.
"""
from __future__ import annotations

import hashlib

from ..minds.character import VoiceSpec

VOICE_REGISTERS = ("clipped and formal", "warm and chatty", "nervous, apt to hedge", "dry and sardonic",
                   "blunt and impatient", "precise, a little pedantic", "gentle and soft-spoken", "brisk and businesslike")
VOICE_IDIOMS = ("if I'm honest", "mind you", "as it happens", "for what it's worth", "I dare say", "to be perfectly frank",
                "I'll grant you", "between ourselves")
VOICE_TICS = ("well...", "hm.", "you see,", "right,", "oh dear,", "look,", "I mean,", "quite.")
DERIVED = VoiceSpec(voice_register="plain")          # what `solve.session` stores: "no authored voice, derive one"


def _h(*parts) -> int:
    return int(hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:12], 16)


def voice_for(actor: str, seed: int) -> VoiceSpec:
    pick = lambda key, options: options[_h(seed, actor, "voice", key) % len(options)]       # noqa: E731
    return VoiceSpec(voice_register=pick("register", VOICE_REGISTERS), idiom=(pick("idiom", VOICE_IDIOMS),),
                     tics=(pick("tic", VOICE_TICS),))


def persona_voice(stored: VoiceSpec, actor: str, seed: int) -> VoiceSpec:
    """The voice the renderer is given: the authored one, or the derived one when the state carries the session default."""
    return voice_for(actor, seed) if stored == DERIVED else stored
