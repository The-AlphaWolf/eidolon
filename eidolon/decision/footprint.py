"""Footprints (ADR-26, I-55): topicality is a FOOTPRINT, never a wording.

A secret is *topical* for a query iff the presented ref maps to it, or the query's footprint
(actors, place, time) intersects the footprint of an UNCONCEDED protected proposition of that secret.
A LIE is a candidate iff the secret is topical AND a current-layer claim's footprint intersects the query's
(§10.3's "a claim covering the asked proposition").

Reads only what the query ASKS — its subject/object/location/time — never `Query.presupposes` (§6.5 bluff
parity: a loaded premise is an implicit `Present` of ZERO weight and must not move which act fires) and never
the character's secrets-as-hidden-truth beyond the protected propositions the secret itself names.

Location is part of a footprint only for propositions where it is a SCENE (`Did`, `Saw`, `Heard`…). For `At`/`NotAt`
it is the CONTENT of the answer, not part of what is asked — "where was X at t?" is the question whatever
place the asker has in mind — so those carry no location constraint.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..world.interval import overlaps
from ..world.propositions import Proposition, entities
from .query import Query

# Questions whose implicit subject is the person being asked ("where were you", "did you leave").
SELF_KINDS = frozenset({"where", "when", "did_you"})


@dataclass(frozen=True)
class Footprint:
    actors: frozenset[str]
    location: str | None
    interval: tuple[int, int] | None


def query_footprint(query: Query, speaker: str) -> Footprint:
    actors = {r.id for r in (query.subject, query.object) if r is not None and r.kind == "actor"}
    if query.kind in SELF_KINDS:
        actors.add(speaker)
    iv = query.time.interval if query.time is not None else None
    return Footprint(frozenset(actors), query.location, tuple(iv) if iv is not None else None)


def prop_footprint(prop: Proposition) -> Footprint:
    scene = None if prop.kind in ("At", "NotAt") else (getattr(prop, "location", None) or getattr(prop, "from_location", None))
    iv = getattr(prop, "interval", None)
    return Footprint(frozenset(entities(prop)[0]), scene, tuple(iv) if iv is not None else None)


def intersects(q: Footprint, p: Footprint) -> bool:
    """Do the asked-about footprint `q` and the protected/claimed footprint `p` share an actor, a place and a time?"""
    if q.actors:
        if not (q.actors & p.actors):
            return False
    elif q.location is None or p.location != q.location:     # no actor asked about: a place must carry it
        return False
    if q.location is not None and p.location is not None and q.location != p.location:
        return False
    if q.interval is not None and p.interval is not None and not overlaps(q.interval, p.interval):
        return False
    return True


# ADR-27: a question's `predicate_hint` maps onto a closed topic vocabulary - the proposition kinds memories tag
# themselves with. ONE map, read by memory retrieval (`turn.query_cues`) and by the LIE gate below.
TOPIC_OF_HINT = {**{h: "at" for h in ("where", "who", "presence", "see", "seen", "with", "whereabouts", "location",
                                      "there", "at")},
                 **{h: "heard" for h in ("hear", "heard", "sound", "noise")},
                 **{h: "did" for h in ("did", "do", "done", "action", "act", "clean", "wipe", "touch", "take", "use")}}
# ADR-30: which claims answer a question on each topic. "where was X / who was there / who was seen" is answered by
# whereabouts and sightings; "what did you hear" by hearing; "what did you do" by deeds and denials.
TOPIC_KINDS = {"at": frozenset({"At", "NotAt", "Saw"}), "heard": frozenset({"Heard"}), "did": frozenset({"Did", "DidNot"})}

def query_topic(query: Query) -> str | None:
    """The topic a question ASKS, from its hint - what the question form and the parser set; None when it names none, and
    then any covering claim may answer, as before ADR-30. An unknown hint (a bluff's `bluffN`) names no topic, so bluff
    parity is untouched. ponytail: the query KIND is not read ("where" implies presence); add it if hint-less questions
    still produce off-topic lies in play."""
    hint = (query.predicate_hint or "").strip().lower()
    return TOPIC_OF_HINT.get(hint)


def on_topic(claim_prop: Proposition, query: Query) -> bool:
    """ADR-30: a claim answers a question only on its own topic. "What did you hear?" is never answered with "I never
    touched the decanter": with no on-topic lie the speaker does not lie, and `speakable` still keeps every protected
    truth back, so the answer is a non-answer (DONT_RECALL / EVASION / …), never a leak."""
    topic = query_topic(query)
    return topic is None or claim_prop.kind in TOPIC_KINDS[topic]


def unconceded_protected(secret, layer_index: int) -> tuple[Proposition, ...]:
    """The protected propositions the secret's owner has NOT yet conceded at `layer_index` — the runtime
    counterpart of the solver's "not cracked" (I-54)."""
    conceded = set(secret.cover.layers[layer_index].concedes)
    return tuple(p for p in secret.protected if p not in conceded)


def secret_topical(secret, layer_index: int, query: Query, speaker: str) -> bool:
    q = query_footprint(query, speaker)
    return any(intersects(q, prop_footprint(p)) for p in unconceded_protected(secret, layer_index))


def claim_covers(claim_prop: Proposition, query: Query, speaker: str) -> bool:
    return intersects(query_footprint(query, speaker), prop_footprint(claim_prop))
