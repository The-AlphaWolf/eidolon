"""The constructive timeline planner (§18.3 stages 1-4, 6, 8; I-43) — the Phase 0.5 design
(`spike/gen.py::plan(construct=True)`, 20/20 on all three configurations) promoted to production.

It does NOT search for uniqueness. It REALISES the skeleton's declared `EliminationStructure`
as forced picks before filling the rest of each schedule (§18.3 stage 3 (a)-(f)):

  (a) every innocent is placed in ONE alibi room over [t_m - alibi_window, t_m + alibi_window];
  (b) every innocent's protected interval stays >= secret_clearance minutes clear of t_m;
  (c) the containment device is emitted at every exterior access (self-grounding L3, I-47);
  (d) the collusion graph is consulted when lovers/shared secrets are placed, so no innocent is
      left without a corroborator outside their component;
  (e) the time pin is emitted (an L3 `Die` timepiece);
  (f) the housekeeper's stay in the murder room is >= 8 minutes, pinned over the whole stay, with
      the clean event >= 2 minutes inside it (`opportunity_pin`).

All randomness is `random.Random(seed)` — `gen/` is the only package allowed to import `random`
(I-6) — and every choice is made from a SORTED sequence, so the result does not depend on
`PYTHONHASHSEED` (tested across processes). A seed whose structure cannot be realised returns a
`Draft` with `error` set: it is REPORTED, never searched into uniqueness.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from ..world.events import EffActorState, EffTraceCreated, Event, Perceptibility
from ..world.propositions import Motive
from ..world.space import TravelGraph
from ..solve.queries import BUCKET
from .skeletons import Skeleton

ALIBI_WINDOW = 8
SECRET_CLEARANCE = 12
STRUCTURE = {"alibi_window": ALIBI_WINDOW, "secret_clearance": SECRET_CLEARANCE, "opportunity_pin": True}


@dataclass
class Seg:
    loc: str
    s: int
    e: int
    attention: str = "1.0"
    hop: bool = False


@dataclass
class Draft:
    """One realisation attempt: everything the compiler needs, and the realised structure."""
    skel: Skeleton
    seed: int
    murderer: str = ""
    t_m: int = 0
    segments: dict = field(default_factory=dict)          # actor -> [Seg]
    events: list = field(default_factory=list)            # non-stay Events
    secrets: dict = field(default_factory=dict)           # actor -> dict(kind, loc, iv, shared_with, protected_iv)
    rels: list = field(default_factory=list)
    motives: list = field(default_factory=list)
    pins: list = field(default_factory=list)              # (id, actor, loc, iv)
    meta: dict = field(default_factory=dict)
    error: str | None = None


def _isolates(nodes, edge_groups) -> bool:
    """True when the collusion edges would leave some node with no partner outside its own
    component (§18.3 stage 3 (d))."""
    parent = {x: x for x in nodes}

    def find(x):
        while parent[x] != x:
            x = parent[x]
        return x
    for grp in edge_groups:
        grp = [x for x in grp if x in parent]
        for x in grp[1:]:
            parent[find(x)] = find(grp[0])
    return any(all(find(y) == find(x) for y in nodes) for x in nodes)


class Nav:
    """The planner's view of the house: routes never transit a private room (I-48) and never
    touch an exterior access (cast do not use it, so its device log stays canonically true)."""

    def __init__(self, skel: Skeleton):
        blocked = set(skel.exterior) | {"EXT"}
        edges = [e for e in skel.travel if e.a not in blocked and e.b not in blocked]
        locs = {l.id: l for l in skel.locations if l.id not in blocked}
        self.g = TravelGraph(locs, edges)
        self.minutes = {}
        for e in edges:
            self.minutes[(e.a, e.b)] = self.minutes[(e.b, e.a)] = e.minutes

    def route(self, a, b, t):
        return self.g.route(a, b, t)

    def travel_time(self, a, b, t):
        return self.g.travel_time(a, b, t)


def _schedule(nav: Nav, rng: random.Random, skel: Skeleton, weights: dict, forced: list, T: int) -> list[Seg]:
    """Role schedule with forced windows (port of the spike's `_schedule`)."""
    segs: list[Seg] = []
    fq = sorted(forced, key=lambda f: f[1])
    cur, t = skel.hub, 0
    locs = sorted(l for l in weights if l != skel.murder_loc)
    wts = [weights[l] for l in locs]

    def att(loc, s):
        return "0.3" if loc in skel.sleep_locs and s >= skel.sleep_after else "1.0"

    def stay(loc, s, e):
        if e > s:
            segs.append(Seg(loc, s, e, att(loc, s)))

    def travel_to(dest, last_tick):
        nonlocal cur
        path = nav.route(cur, dest, last_tick)
        tt = last_tick
        for i in range(1, len(path)):
            tt += nav.minutes[(path[i - 1], path[i])]
            if i < len(path) - 1 and tt < T:
                segs.append(Seg(path[i], tt, tt + 1, "1.0", hop=True))
        cur = dest
        return tt

    def pick():
        loc = cur
        for _ in range(20):
            loc = rng.choices(locs, wts)[0]
            if loc != cur:
                break
        return loc, rng.randint(6, 30)

    guard = 0
    while t < T and guard < 300:
        guard += 1
        f = fq[0] if fq else None
        loc, dur = pick()
        if f is None:
            e = min(t + dur, T)
            stay(cur, t, e)
            if e >= T:
                break
            t = travel_to(loc, e - 1)
            continue
        if cur == f[0] and (t >= f[1] or f[1] - t <= 6):
            e = min(T, max(f[2], t + 1))
            stay(cur, t, e)
            fq.pop(0)
            if e >= T:
                break
            t = travel_to(loc, e - 1)
            continue
        d = nav.travel_time(cur, f[0], t) or 0
        latest_last = f[1] - d
        e = max(t + 1, min(t + dur, latest_last + 1, T))
        stay(cur, t, e)
        if e >= T:
            break
        d1 = nav.travel_time(cur, loc, e - 1) or 0
        d2 = nav.travel_time(loc, f[0], e - 1 + d1) or 0
        if (e - 1) + d1 + d2 <= f[1]:
            t = travel_to(loc, e - 1)
        elif cur == f[0]:
            segs[-1].e = min(T, max(f[2], e))
            t = segs[-1].e
            fq.pop(0)
            if t >= T:
                break
            t = travel_to(loc, t - 1)
        else:
            t = travel_to(f[0], e - 1)
    merged: list[Seg] = []
    for s in segs:
        if merged and merged[-1].loc == s.loc and merged[-1].e == s.s and merged[-1].attention == s.attention:
            merged[-1].e = s.e
            merged[-1].hop = merged[-1].hop and s.hop
        else:
            merged.append(Seg(s.loc, s.s, s.e, s.attention, s.hop))
    return merged


def plan(skel: Skeleton, seed: int, n_living: int | None = None, murderer: str | None = None) -> Draft:
    """One seeded realisation. No uniqueness search inside (R-B, I-43). `murderer` overrides the drawn
    murderer only (tests); every other draw is identical, so the world differs only where it must."""
    n = n_living or len(skel.cast)
    rng = random.Random(seed)
    dr = Draft(skel, seed)
    nav = Nav(skel)
    T = skel.T
    victim, _ = skel.victim
    living = [nm for nm, _ in skel.cast[:n]]
    role = dict(zip(living, skel.roles))
    # I-9 (ADR-23): the housekeeper is the §18.3(f) opportunity witness, and the murder cover's breaker rests on
    # HER account of the cleaning — a murderer who is also that witness would be broken by their own word.
    M = dr.murderer = rng.choice([a for a in living if role[a] != "housekeeper"])
    if murderer is not None:      # test hook (the 'swap the murderer' self-check): the random stream is unchanged
        M = dr.murderer = murderer
    t_m = dr.t_m = rng.randint(*skel.t_m_range)
    d0 = rng.randint(4, 12)

    arr = (d0 - 1) + nav.minutes[(skel.hub, skel.murder_loc)]
    dr.segments[victim] = [Seg(skel.hub, 0, d0), Seg(skel.murder_loc, arr, T)]
    forced = {a: [(skel.hub, 0, d0)] for a in living}
    pre, post = rng.randint(1, 3), rng.randint(0, 2)
    t_arr, t_dep = t_m - pre, t_m + 1 + post
    forced[M].append((skel.murder_loc, t_arr, t_dep))
    innocents = [a for a in living if a != M]

    # relationships (stage 2), shared secrets and per-innocent secrets (stage 6)
    meeting = len(innocents) >= 3 and rng.random() < skel.p_meeting
    pair = tuple(rng.sample(innocents, 2)) if meeting else ()
    if rng.random() < skel.p_lover:
        a, b = rng.sample(living, 2)
        if M not in (a, b) and _isolates(innocents, [pair, (a, b)]):
            a, b = M, rng.choice(innocents)          # (d) keep an outside corroborator
        dr.rels.append((a, b, "lover"))
    # (a) one alibi room for all innocents; (f) the housekeeper's pinned stay; both before secrets
    alibi_loc = rng.choice(sorted(l for l in skel.role_weights["guest"] if l != skel.murder_loc))
    for a in innocents:
        forced[a].append((alibi_loc, t_m - ALIBI_WINDOW, t_m + ALIBI_WINDOW))
    hk = next(a for a in living if role[a] == "housekeeper")
    t_c = rng.randint(d0 + 5, t_m - 20)
    forced[hk].append((skel.murder_loc, t_c, t_c + 8))

    def place_secret(actors):
        """(b) a protected interval >= SECRET_CLEARANCE clear of t_m and >= 6 minutes clear of every
        other forced window of every actor concerned; None if no placement is found."""
        sloc = rng.choice(sorted(skel.secret_locs))
        drawn = rng.randint(10, 25)
        for length in dict.fromkeys((drawn, 10)):    # a draw too long to fit (hk: bucket + alibi window) retries at the minimum
            for _ in range(60):
                s0 = rng.randint(14, T - length - 4)
                iv = (s0, s0 + length)
                if not (iv[1] <= t_m - SECRET_CLEARANCE or iv[0] >= t_m + SECRET_CLEARANCE):
                    continue
                if hk in actors:                # the Clean account is asked about by time bucket: a bucket that overlaps hk's own
                    b0 = (t_c + 2) // BUCKET * BUCKET       # protected interval draws a LIE instead (I-55), so it must stay clear
                    if iv[0] < b0 + BUCKET and b0 < iv[1]:
                        continue
                if all(f[2] + 6 <= iv[0] or iv[1] + 6 <= f[1] for x in actors for f in forced[x] if f[1] > 0):
                    return sloc, iv
        return None

    todo = ([pair] if pair else []) + [(a,) for a in innocents if a not in pair]
    for group in todo:
        placed = place_secret(group)
        if placed is None:
            dr.error = "structure_unrealised: no protected interval clears the murder window"
            return dr
        for a in group:
            other = tuple(x for x in group if x != a)
            dr.secrets[a] = {"loc": placed[0], "iv": placed[1], "shared_with": other}
            forced[a].append((placed[0], *placed[1]))
    t_clean = t_c + 2
    dr.meta["alibi"] = (alibi_loc, t_m - ALIBI_WINDOW, t_m + ALIBI_WINDOW)
    dr.meta.update(hk=hk, t_c=t_c, t_clean=t_clean)
    for a in living:
        dr.segments[a] = _schedule(nav, rng, skel, skel.role_weights[role[a]], forced[a], T)

    # the murderer's excursion (protected interval) and the segment that holds the attack
    segs = dr.segments[M]
    j = next((i for i, s in enumerate(segs) if s.loc == skel.murder_loc and s.s <= t_m < s.e), None)
    if j is None:
        dr.error = "structure_unrealised: murderer not in the murder room at t_m"
        return dr
    pre_seg = next((s for s in reversed(segs[:j]) if not s.hop), None)
    post_seg = next((s for s in segs[j + 1:] if not s.hop), None)
    lo = segs.index(pre_seg) + 1 if pre_seg else 0
    hi = segs.index(post_seg) if post_seg else len(segs)
    dr.secrets[M] = {"loc": skel.murder_loc, "iv": (segs[lo].s, segs[hi - 1].e), "shared_with": (), "murder": True,
                     "segs": [(x.loc, x.s, x.e) for x in segs[lo:hi]]}
    dr.meta.update(t_arr=segs[j].s, t_dep=segs[j].e)

    # events (stage 4)
    obj, vloc = skel.weapon.id, skel.murder_loc
    talk = max(segs[j].s, t_m - 3)
    dr.events.append(Event(id="attack", kind="Attack", interval=(t_m, t_m + 1), location=vloc, actor=M,
                           participants=(victim,), objects=(obj,),
                           effects=(EffTraceCreated(object=obj, trace_kind="fingerprint"),),
                           perceptibility=Perceptibility(sight=1.0, sound=0.8, identifies_voice=True)))
    dr.events.append(Event(id="die", kind="Die", interval=(t_m, t_m + 1), location=vloc, actor=victim,
                           effects=(EffActorState(actor=victim, attr="alive", value="false"),)))
    if talk < t_m:
        dr.events.append(Event(id="argue", kind="Speak", interval=(talk, t_m), location=vloc, actor=M,
                               participants=(victim,),
                               perceptibility=Perceptibility(sight=1.0, sound=0.8, identifies_voice=True)))
    dr.events.append(Event(id="clean", kind="Clean", interval=(t_clean, t_clean + 1), location=vloc, actor=hk,
                           objects=(obj,), perceptibility=Perceptibility(sight=0.6, sound=0.2)))
    # NR-I2: one innocent holds forth in the alibi room as the alibi window closes - an ordinary, audible scene, so every
    # listener has something HEARD to tell (listeners, not participants: a participant's knowledge is what they DID). Late
    # in the window, the freshest memory the window allows (§8.3 decay). No rng draw: the rest of the plan is unchanged.
    alibi_loc, _, a1 = dr.meta["alibi"]
    talkers = sorted(innocents)
    if len(talkers) >= 2:
        dr.events.append(Event(id="chat", kind="Speak", interval=(a1 - 3, a1 - 1), location=alibi_loc, actor=talkers[0],
                               perceptibility=Perceptibility(sight=1.0, sound=0.8, identifies_voice=True)))
    dr.events.append(Event(id=f"alive0:{victim}", kind="Environmental", interval=(0, 1), location=skel.hub,
                           effects=(EffActorState(actor=victim, attr="alive", value="true"),)))
    # motives (stage 2): the murderer and at least one other suspect
    kinds = sorted(skel.motive_menu)
    others = [a for a in innocents if a != hk] or innocents
    for a in sorted({M, rng.choice(sorted(others))}):
        dr.motives.append(Motive(actor=a, victim=victim, motive_kind=rng.choice(kinds), strength=0.7))
    # random device pins (stage 4/8), never over the owner's own protected interval
    for a in living:
        if rng.random() >= skel.p_pin:
            continue
        sec = dr.secrets.get(a)
        cands = [s for s in dr.segments[a] if s.e - s.s >= 4 and not s.hop
                 and not (sec and not (s.e <= sec["iv"][0] or s.s >= sec["iv"][1]))]
        if not cands:
            continue
        s = rng.choice(cands)
        ln = rng.randint(3, min(8, s.e - s.s))
        t0 = rng.randint(s.s, s.e - ln)
        dr.pins.append((f"E_pin_{a}", a, s.loc, (t0, t0 + ln)))
    dr.meta.update(t_gate=rng.randint(0, 20), pair=pair, innocents=innocents, alibi_loc=alibi_loc, living=living,
                   role=role)
    return dr
