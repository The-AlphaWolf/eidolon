"""The two closed action vocabularies and the entailment between them (§4.5, §4.7, ADR-22).

`EventKind` (§4.5) names what the CaseLog *records*: a discrete authored occurrence with an
interval, a location, effects and a perceptibility. `ActionKind` (§4.7) names what a
`Did`/`DidNot` proposition may *assert*: what an actor did, as evidence, testimony and
hypotheses talk about it. The architecture has always typed `Did.action` as `ActionKind`
(§4.7's schema block) without defining the type; ADR-22 defines it.

The two are not the same vocabulary, because forensic evidence under-determines the event.
A fingerprint on a glass licenses `Did(David, touch, Glass1, …)` (§5.1's own example) — it
does not say whether he drank from it, washed it, moved it or hit someone with it. Every one
of those is a different `EventKind`, and the implication has to be expressible without
choosing between them.

So `ActionKind` is `EventKind` plus a small set of ENTAILED actions, and each action carries
the set of event kinds that entail it. Identity for event-named actions; a union for entailed
ones. Extending either vocabulary stays an ADR-level change (§4.7: "the schema is closed").

`EventKind` lives here rather than in `events.py` only to keep the import graph acyclic —
`propositions.py` needs `ActionKind`, and `events.py` already imports `propositions.py`.
`events.py` re-exports it, so `from .events import EventKind` is unchanged.
"""
from __future__ import annotations

from typing import Literal, get_args

EventKind = Literal[
    "Move", "Stay", "Take", "Drop", "Use", "Give", "Speak", "Meet",
    "Attack", "Die", "Clean", "Hide", "Plant", "Write", "Read",
    "Observe", "Environmental",
]

ActionKind = Literal[
    # Every `EventKind`, spelled identically: an action named after an event kind asserts
    # exactly that kind occurred. `Did(Harold, "Die", …)` keeps working verbatim.
    "Move", "Stay", "Take", "Drop", "Use", "Give", "Speak", "Meet",
    "Attack", "Die", "Clean", "Hide", "Plant", "Write", "Read",
    "Observe", "Environmental",
    # ...plus the entailed actions, spelled lowercase so the two classes are distinguishable
    # on sight (§4.7/§5.1 write this one lowercase in the document's own examples).
    "touch",
]

EVENT_KINDS: frozenset[str] = frozenset(get_args(EventKind))

# Physical contact with an object in `Event.objects`. §5.2: "a fingerprint exists because a
# `Use(glass)` event with a `TraceCreated` effect occurred without gloves" — but every kind
# below puts the actor's hands on the object it names, and a trace cannot tell them apart:
#
#   Take / Drop / Give   the object changes holder through the actor (P-3 requires co-location)
#   Use                  §5.2's own example
#   Plant / Hide         placing the object somewhere
#   Clean                handling it — and §5.2 makes `Clean` the thing that REMOVES a trace,
#                        which only makes sense if the cleaner touched what they cleaned
#   Write                contact with the document written on
#   Attack               contact with the weapon, when the event names one (`vance_v03`'s
#                        `attack` carries `objects=("Glass1",)`)
#
# `Read` is deliberately excluded: reading does not entail handling (a notice, a screen, a
# page over someone's shoulder). A `touch` the world cannot stand behind would manufacture
# forensic contact out of nothing, so the set is conservative — under-claiming leaves an
# implication Unknown, over-claiming invents evidence.
_TOUCH_KINDS = frozenset({"Take", "Drop", "Use", "Give", "Plant", "Hide", "Clean", "Write", "Attack"})

ACTION_ENTAILED_BY: dict[str, frozenset[str]] = (
    {kind: frozenset({kind}) for kind in sorted(EVENT_KINDS)} | {"touch": _TOUCH_KINDS}
)

ENTAILED_ACTIONS: frozenset[str] = frozenset(ACTION_ENTAILED_BY) - EVENT_KINDS
"""Actions that are not themselves event kinds. They assert something an event implies
rather than the event itself, so their object slot is load-bearing (see `facts._tv_Did`)."""


def entailing_kinds(action: str) -> frozenset[str] | None:
    """The `EventKind`s whose occurrence makes `Did(actor, action, …)` true, or `None` when
    the vocabulary has no entailment rule for `action`.

    `None` is not "false": it is §4.7's Unknown — the world has no way to settle a predicate
    it cannot express. `ActionKind` makes that unreachable through normal construction, but
    the guard stays live for two real paths: `model_construct`/`model_copy(update=…)` bypass
    pydantic validation, and a future ADR that adds an `ActionKind` member without adding its
    entailment row must get Unknown rather than a silent refutation.
    """
    return ACTION_ENTAILED_BY.get(action)
