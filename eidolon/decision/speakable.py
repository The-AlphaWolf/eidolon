"""`speakable` (ADR-26, I-54) — the runtime mirror of the solver's layer-0 withholding (I-45).

The solver withholds every atom whose observation segment overlaps its holder's protected interval until that
holder's secret is cracked (`lattice.testimony_pool`). Before this gate the runtime had no such rule: the
withholding happened BY ACCIDENT, because a topical secret made every whereabouts question a LIE (RB-2/C1-C3).
Repairing those without this predicate would have turned the accident into a leak of protected-interval
knowledge. A claim is speakable by `speaker` only if

  (a) its proposition is not protected for the speaker and not yet conceded;
  (b) none of its grounding entries' observation segments overlaps a protected interval of a secret the
      speaker has not yet conceded — both sides read `Secret.protected_intervals()`;
  (c) it does not contradict the claims of the speaker's current cover layer.

Reads only the claim, the speaker's own secrets and their layer state — never the query, never `presupposes`.
"""
from __future__ import annotations

from collections.abc import Callable

from ..evidence.contradiction import contradiction
from ..minds import accounts
from ..world.interval import overlaps
from .claims import Claim
from .secrets import Secret, SecretStore


def speakable(claim: Claim, speaker: str, secrets: SecretStore, layer_of: Callable[[Secret], int],
              knowledge, case) -> bool:
    for s in secrets.for_owner(speaker):
        idx = layer_of(s)
        layer = s.cover.layers[idx]
        conceded = set(layer.concedes)
        live = [p for p in s.protected if p not in conceded]
        if claim.proposition in live:
            return False
        ivs = [iv for p in live if (iv := getattr(p, "interval", None)) is not None]
        for gid in claim.grounding:
            seg = accounts.observation_segment(case, knowledge, gid)
            if seg is not None and any(overlaps(seg, iv) for iv in ivs):
                return False
        if any(contradiction(claim.proposition, c.proposition, case=case) is not None for c in layer.claims):
            return False
    return True
