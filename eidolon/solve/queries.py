"""The questions a player can actually put to the engine (ADR-29, §19.4/§19.7): ONE vocabulary shared by V-4's
engine-faithful I-39 check and every V-7 bot.

A question is a real `Query` — a kind, a subject/object the case contains, a place, a 30-minute `TimePhrase`
bucket and a topic hint — and nothing else: no hidden memory cue is ever read to build one. What a player may
NAME is what they hold (`Names`): the cast and the places of the house are public; a time bucket becomes
nameable when held material mentions it (the pin's bucket, the alibi log's window, a committed claim's
interval). The greedy bot may sweep the public clock as well.

Shapes (§19.4 "enumerates every parser-expressible `Query` shape"), most specific first — three, over `Names`:
  did_they(A, B)      "Was A about at B?"            topic `at`   — presence, co-presence, absence
  did_they(self, B)   "What did you do at B?"        topic `did`  — one's own actions (the account of a cleaning)
  did_you(L, B)       "Were you in L at B?"          topic `at`
(`who(L, B)` carries the SAME cues as `did_you(L, B)` — place, half-hour, topic — so it is not a fourth shape: it
would only double every sweep against the architecture's action budgets, N_MAX = N_CUE = 400.)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..decision.query import EntityRef, Query, TimePhrase
from ..world.propositions import entities

BUCKET = 30


@dataclass(frozen=True)
class Names:
    actors: frozenset[str] = frozenset()
    locations: frozenset[str] = frozenset()
    objects: frozenset[str] = frozenset()
    buckets: frozenset[int] = frozenset()

    def union(self, other: "Names") -> "Names":
        return Names(self.actors | other.actors, self.locations | other.locations,
                     self.objects | other.objects, self.buckets | other.buckets)


def bucket_of(iv) -> int:
    return iv[0] // BUCKET


def names_of_proposition(case, prop) -> Names:
    a, l, o, amb = entities(prop)
    allx = a | l | o | amb
    iv = getattr(prop, "interval", None)
    return Names(frozenset(x for x in allx if x in case.actors), frozenset(x for x in allx if x in case.locations),
                 frozenset(x for x in allx if x in case.objects), frozenset({bucket_of(iv)}) if iv else frozenset())


def public_names(case) -> Names:
    """The cast and the places of the house are known to the detective from the start (§19.4's initial named set)."""
    return Names(frozenset(case.actors), frozenset(case.locations), frozenset(case.objects), frozenset())


def opening_names(case, victim, murder_loc) -> Names:
    """§19.4's initial named set: the cast, the body, the murder room and every exterior access (I-47) — a place enters
    only when held material names it. The cue-following bot starts here; `public_names` is the looser, all-places set."""
    return Names(actors=frozenset(case.living_actors()) | frozenset({victim} - {None}),
                 locations=frozenset({murder_loc} - {None}) | frozenset(l for l, x in case.locations.items() if x.exterior))


def clock_buckets(case) -> frozenset[int]:
    return frozenset(range(0, case.t_investigation // BUCKET + 1))


def names_from_evidence(case, ev) -> Names:
    n = Names(objects=frozenset(x for x in (ev.object,) if x),
              locations=frozenset(x for x in (ev.discovery.at, ev.location_at_investigation) if x in case.locations))
    if ev.created_at:
        n = n.union(Names(buckets=frozenset({bucket_of(ev.created_at)})))
    for imp in ev.implications:
        n = n.union(names_of_proposition(case, imp.proposition))
    return n


def time_phrase(bucket: int) -> TimePhrase:
    return TimePhrase(text=f"b{bucket}", interval=(bucket * BUCKET, bucket * BUCKET + BUCKET))


def expressible_queries(case, speaker: str, names: Names) -> list[Query]:
    """Every question of the four shapes over `names`, deterministic order, without duplicates."""
    out: list[Query] = []
    actors = sorted(a for a in names.actors if a in case.actors)
    locs = sorted(l for l in names.locations if l in case.locations)
    for b in sorted(names.buckets):
        tp = time_phrase(b)
        for a in actors:
            out.append(Query(kind="did_they", subject=EntityRef(id=a, kind="actor"), predicate_hint="presence",
                             time=tp, raw=f"Where was {a} around b{b}?"))
        out.append(Query(kind="did_they", subject=EntityRef(id=speaker, kind="actor"), predicate_hint="did",
                         time=tp, raw=f"What did you do around b{b}?"))
        for l in locs:
            out.append(Query(kind="did_you", location=l, predicate_hint="presence", time=tp,
                             raw=f"Were you in {l} around b{b}?"))
    return out
