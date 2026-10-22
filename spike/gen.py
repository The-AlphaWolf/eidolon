"""Phase 0.5 spike — toy planner (§18.3 stages 1–4, 6, 8; solution-first).

One skeleton = layout template + role templates + evidence menu probabilities. The planner
realises a seeded canonical timeline (murderer excursion + role schedules + one red-herring
secret + optional lover pair), then derives events and physical evidence from it. It SEARCHES
for uniqueness by reseeding (the v0.3 design); it does not construct it (R-B).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .model import (World, Actor, Loc, Seg, Event, Evidence, Implication, Secret, Prop, EXT,
                    check_physics)


@dataclass
class Skeleton:
    id: str
    locs: list[Loc]
    travel: list[tuple[str, str, int]]
    perception: list[tuple[str, str, str, float]]
    murder_loc: str
    hub: str
    roles: list[str]
    role_weights: dict[str, dict[str, float]]
    secret_locs: list[str]
    victim: tuple[str, str]                 # (name, sex)
    living: list[tuple[str, str]]           # (name, sex) per role slot
    T: int = 120
    t_m_range: tuple[int, int] = (40, 90)
    sleep_after: int = 95
    p_watch: float = 0.75
    p_trace: float = 0.6
    p_pin: float = 0.35
    p_lover: float = 0.5
    p_secret_meeting: float = 0.4
    trace_object: str = "decanter"
    knobs: dict = field(default_factory=dict)


def toy_skeleton() -> Skeleton:
    return Skeleton(
        id="toy_4x5",
        locs=[Loc("Hall", "the hall", True), Loc("Study", "the study", True, private=True), Loc("Kitchen", "the kitchen", True),
              Loc("Bedroom", "the bedroom", True), Loc("Garden", "the garden", False, exterior=True), Loc(EXT, "outside", False)],
        travel=[("Hall", "Study", 1), ("Hall", "Kitchen", 1), ("Hall", "Bedroom", 2), ("Hall", "Garden", 2),
                ("Kitchen", "Garden", 1), ("Garden", EXT, 3)],
        perception=[("Hall", "Study", "sound", 0.7), ("Kitchen", "Hall", "sight", 0.5), ("Hall", "Kitchen", "sight", 0.5),
                    ("Bedroom", "Hall", "sound", 0.4), ("Garden", "Kitchen", "sight", 0.4)],
        murder_loc="Study", hub="Hall",
        roles=["housekeeper", "guest", "guest", "gardener"],
        role_weights={"housekeeper": {"Kitchen": 0.55, "Hall": 0.2, "Bedroom": 0.15, "Garden": 0.1},
                      "guest": {"Hall": 0.3, "Bedroom": 0.3, "Garden": 0.2, "Kitchen": 0.2},
                      "gardener": {"Garden": 0.5, "Kitchen": 0.2, "Hall": 0.2, "Bedroom": 0.1}},
        secret_locs=["Garden", "Bedroom"],
        victim=("Hugo", "M"),
        living=[("Ada", "F"), ("Ben", "M"), ("Cora", "F"), ("Dev", "M")],
    )


def vance_skeleton() -> Skeleton:
    """The Vance House layout of §29.1 as a skeleton (for solver-produced vance_v03 and the fixtures)."""
    return Skeleton(
        id="vance_5x7",
        locs=[Loc("Hall", "the hall", True), Loc("Study", "the study", True, private=True), Loc("Library", "the library", True),
              Loc("Kitchen", "the kitchen", True), Loc("BackSteps", "the back steps", True),
              Loc("Gazebo", "the gazebo", False, exterior=True), Loc("Room", "Margaret's room", True), Loc(EXT, "outside", False)],
        travel=[("Hall", "Study", 1), ("Hall", "Library", 1), ("Hall", "Kitchen", 1), ("Hall", "Room", 1),
                ("Kitchen", "BackSteps", 1), ("BackSteps", "Gazebo", 3), ("Gazebo", EXT, 2), ("Study", "Gazebo", 2)],
        perception=[("BackSteps", "Study", "sound", 0.7), ("Kitchen", "Hall", "sight", 0.5), ("Hall", "Study", "sound", 0.6)],
        murder_loc="Study", hub="Hall",
        roles=["housekeeper", "guest", "guest", "guest"],
        role_weights={"housekeeper": {"Kitchen": 0.6, "Hall": 0.15, "BackSteps": 0.1, "Room": 0.15},
                      "guest": {"Hall": 0.25, "Library": 0.25, "Room": 0.2, "Gazebo": 0.15, "Kitchen": 0.1, "BackSteps": 0.05}},
        secret_locs=["Gazebo", "BackSteps", "Room"],
        victim=("Harold", "M"),
        living=[("Elena", "F"), ("David", "M"), ("Margaret", "F"), ("Robert", "M")],
        trace_object="Glass1",
    )


def empty_world(skel: Skeleton) -> World:
    travel = {}
    for a, b, d in skel.travel:
        travel[(a, b)] = d
        travel[(b, a)] = d
    return World(actors={}, locs={l.id: l for l in skel.locs}, travel=travel, doors={}, perception=list(skel.perception),
                 segments={}, events=[], t_inv=skel.T, victim="", murderer="", t_m=0, murder_loc=skel.murder_loc,
                 secrets={}, rels=[], evidence=[], meta={"skeleton": skel.id})


# ------------------------------------------------------------------ planner
def _schedule(w: World, rng: random.Random, a: str, weights: dict[str, float], forced: list[tuple[str, int, int]],
              T: int, sleep_after: int, murder_loc: str) -> list[Seg]:
    segs: list[Seg] = []
    fq = sorted(forced, key=lambda f: f[1])
    cur, t = w.meta["hub"], 0
    locs = [l for l in weights if l != murder_loc]
    wts = [weights[l] for l in locs]

    def att(loc, s):
        return 0.3 if (loc == "Bedroom" or loc == "Room") and s >= sleep_after else 1.0

    def stay(loc, s, e):
        if e > s:
            segs.append(Seg(loc, s, e, att(loc, s), f"stay:{a}:{len(segs)}"))

    def travel_to(dest, last_tick):
        nonlocal cur
        path = w.route(cur, dest, last_tick)
        tt = last_tick
        for i in range(1, len(path)):
            tt += w.travel[(path[i - 1], path[i])]
            if i < len(path) - 1 and tt < T:
                segs.append(Seg(path[i], tt, tt + 1, 1.0, f"hop:{a}:{len(segs)}"))
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
    # loop invariant: the actor has just ARRIVED at `cur` at tick `t`; decide the stay, then move.
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
            # at the forced location with its window imminent: hold through it, then move on
            e = min(T, max(f[2], t + 1))
            stay(cur, t, e)
            fq.pop(0)
            if e >= T:
                break
            t = travel_to(loc, e - 1)
            continue
        d = w.travel_time(cur, f[0], t) or 0
        latest_last = f[1] - d                      # last tick here that still reaches f on time
        e = max(t + 1, min(t + dur, latest_last + 1, T))
        stay(cur, t, e)
        if e >= T:
            break
        d1 = w.travel_time(cur, loc, e - 1) or 0
        d2 = w.travel_time(loc, f[0], e - 1 + d1) or 0
        if (e - 1) + d1 + d2 <= f[1]:               # a detour still reaches f on time
            t = travel_to(loc, e - 1)
        elif cur == f[0]:                           # already here and no time to detour: extend through the window
            segs[-1].e = min(T, max(f[2], e))
            t = segs[-1].e
            fq.pop(0)
            if t >= T:
                break
            t = travel_to(loc, t - 1)
        else:
            t = travel_to(f[0], e - 1)
    # merge adjacent same-location stays (maximal presence segments)
    merged: list[Seg] = []
    for s in segs:
        if merged and merged[-1].loc == s.loc and merged[-1].e == s.s and merged[-1].attention == s.attention:
            merged[-1].e = s.e
        else:
            merged.append(s)
    return merged


def plan(skel: Skeleton, seed: int, n_living: int = 3, construct: bool = False) -> World:
    """One seeded realisation of the skeleton (one attempt; no uniqueness search inside).

    construct=False: the v0.3 planner as written — role schedules are random; uniqueness is
        SEARCHED for by reseeding (§18.3 stage 3 + §19 loop).
    construct=True: the R-B variant — the skeleton DECLARES an elimination structure and the planner
        realises it: (a) every innocent shares one alibi window around t_m with the other innocents,
        (b) the red-herring secret is kept clear of the murder window, (c) a containment device
        (an L3 gate log at the exterior access) is present, (d) no collusion edge joins the only two
        innocents (every innocent keeps a non-colluding corroborator), (e) a physical time pin (the
        watch) is always present. V-5 then CONFIRMS instead of discovers.
    """
    rng = random.Random(seed)
    w = empty_world(skel)
    w.meta.update({"hub": skel.hub, "seed": seed, "n_living": n_living, "construct": construct})
    T = skel.T
    vname, vsex = skel.victim
    w.actors[vname] = Actor(vname, vname, "victim", {"sex": vsex})
    living = []
    for (nm, sex), role in zip(skel.living[:n_living], skel.roles[:n_living]):
        w.actors[nm] = Actor(nm, nm, "living", {"sex": sex, "role": role})
        living.append(nm)
    w.victim = vname
    w.murderer = rng.choice(living)
    M = w.murderer
    w.t_m = rng.randint(*skel.t_m_range)
    d0 = rng.randint(4, 12)  # dinner ends

    # victim: dinner in the hall, then the study for the rest of the evening
    vs = [Seg(skel.hub, 0, d0, 1.0, f"stay:{vname}:0")]
    arr = (d0 - 1) + w.travel[(skel.hub, skel.murder_loc)]
    vs.append(Seg(skel.murder_loc, arr, T, 1.0, f"stay:{vname}:1"))
    w.segments[vname] = vs

    forced: dict[str, list[tuple[str, int, int]]] = {a: [(skel.hub, 0, d0)] for a in living}
    # murderer's excursion
    pre, post = rng.randint(1, 3), rng.randint(0, 2)
    t_arr, t_dep = w.t_m - pre, w.t_m + 1 + post
    forced[M].append((skel.murder_loc, t_arr, t_dep))
    # red-herring secret (stage 6/8): one innocent has a protected interval; maybe shared
    innocents = [a for a in living if a != M]
    rh = rng.choice(innocents)
    kind = "meeting" if (len(innocents) >= 2 and rng.random() < skel.p_secret_meeting) else "solo"
    if construct and len(innocents) < 3:
        kind = "solo"  # (d) a shared secret between the only two innocents would make their alibi colluding
    sloc = rng.choice(skel.secret_locs)
    ss = rng.randint(20, T - 40)
    siv = (ss, ss + rng.randint(10, 25))
    if construct:  # (b) keep the innocent's secret clear of the murder window [t_m-12, t_m+12]
        for _ in range(40):
            if siv[1] <= w.t_m - 12 or siv[0] >= w.t_m + 12:
                break
            ss = rng.randint(20, T - 40)
            siv = (ss, ss + rng.randint(10, 25))
        else:
            siv = (w.t_m + 14, min(T, w.t_m + 30)) if w.t_m + 30 <= T else (20, w.t_m - 14)
    partner = rng.choice([a for a in innocents if a != rh]) if kind == "meeting" else None
    w.secrets[rh] = Secret(rh, siv, kind, (partner,) if partner else ())
    forced[rh].append((sloc, siv[0], siv[1]))
    if partner:
        w.secrets[partner] = Secret(partner, siv, kind, (rh,))
        forced[partner].append((sloc, siv[0], siv[1]))
    # relationships (stage 2)
    if rng.random() < skel.p_lover and len(living) >= 2:
        a, b = rng.sample(living, 2)
        if construct and M not in (a, b):
            # (d) every innocent keeps a corroborator outside its collusion component: a lover pair that,
            # together with the shared secret, would leave some innocent with no independent peer is
            # re-drawn to include the murderer instead.
            comp = {x: x for x in innocents}
            def find(x):
                while comp[x] != x:
                    x = comp[x]
                return x
            for p, q in [(a, b)] + ([(rh, partner)] if partner else []):
                comp[find(p)] = find(q)
            if any(all(find(y) == find(x) for y in innocents) for x in innocents):
                a, b = M, rng.choice(innocents)
        w.rels.append((a, b, "lover"))
    if construct:  # (a) declared elimination structure: one shared alibi window for all innocents
        alibi_loc = rng.choice([l for l in skel.role_weights["guest"] if l != skel.murder_loc])
        for a in innocents:
            forced[a].append((alibi_loc, w.t_m - 8, w.t_m + 8))
        w.meta["alibi_window"] = [alibi_loc, w.t_m - 8, w.t_m + 8]
    # housekeeper cleans an object in the study before the murder -> the trace's `requires`
    hk = next((a for a in living if w.actors[a].attrs["role"] == "housekeeper"), None)
    trace = hk is not None and (construct or rng.random() < skel.p_trace) and w.t_m - 20 > d0 + 6
    t_c = t_clean = None
    if trace and construct:
        # (f) opportunity pin: cleaning stay >= 8 min, pinned over the whole stay, the event >= 2 min inside it,
        # so the cleaner's `Did(clean)` claim (granularity 2) is presence-fixed over its widened window (I-44)
        t_c = rng.randint(d0 + 5, w.t_m - 20)
        t_clean = t_c + 2
        forced[hk].append((skel.murder_loc, t_c, t_c + 8))
    elif trace:
        t_c = rng.randint(d0 + 5, w.t_m - 15)
        t_clean = t_c
        forced[hk].append((skel.murder_loc, t_c, t_c + rng.randint(2, 5)))
    # schedules (stage 3)
    for a in living:
        w.segments[a] = _schedule(w, rng, a, skel.role_weights[w.actors[a].attrs["role"]], forced[a], T,
                                  skel.sleep_after, skel.murder_loc)
    # murderer's protected interval = the whole excursion (from leaving the pre-stay to reaching the post-stay)
    segs = w.segments[M]
    j = next((i for i, s in enumerate(segs) if s.loc == skel.murder_loc and s.s <= w.t_m < s.e), None)
    if j is None:
        w.meta["planner_error"] = "murderer not in the murder room at t_m"
        return w
    pre_seg = next((s for s in reversed(segs[:j]) if s.event_id.startswith("stay:")), None)
    post_seg = next((s for s in segs[j + 1:] if s.event_id.startswith("stay:")), None)
    w.secrets[M] = Secret(M, (pre_seg.e if pre_seg else 0, post_seg.s if post_seg else T), "murder")
    # events (stage 4): the blow (with a cry) at t_m; an audible argument for up to 3 minutes before it
    obj = skel.trace_object
    t_arr = max(segs[j].s, w.t_m - 3)
    w.events.append(Event("attack", "Attack", M, skel.murder_loc, w.t_m, None, (obj,), sight=1.0, sound=0.8,
                          identifies_voice=True))
    if t_arr < w.t_m:
        w.events.append(Event("argue", "Speak", M, skel.murder_loc, t_arr, w.t_m, (), sight=1.0, sound=0.8,
                              identifies_voice=True, participants=(vname,)))
    if trace:
        w.events.append(Event("clean", "Clean", hk, skel.murder_loc, t_clean, None, (obj,), sight=0.6, sound=0.2))
        if construct:
            w.events.append(Event(f"log_clean_{hk}", "Logged", hk, skel.murder_loc, t_c, t_c + 8, ("device",), sight=0.5))
            w.evidence.append(Evidence(f"E_pin_clean_{hk}", "pin", skel.murder_loc, (hk, skel.murder_loc),
                                       [Implication(Prop("At", hk, skel.murder_loc, (t_c, t_c + 8)))], established_iv=(t_c, t_c + 8)))
    # evidence (stage 4/8)
    w.evidence.append(Evidence("E_scene", "scene", skel.murder_loc, (vname, skel.murder_loc, "body") + ((obj,) if trace else ()), []))
    if rng.random() < skel.p_watch or construct:  # (e) construct mode realises the skeleton's time_pin by construction
        w.evidence.append(Evidence("E_watch", "watch", skel.murder_loc, (vname, "watch", skel.murder_loc),
                                   [Implication(Prop("Died", vname, skel.murder_loc, (w.t_m, w.t_m + 1)))],
                                   established_iv=(w.t_m, w.t_m + 1)))
    if trace:
        w.evidence.append(Evidence("E_trace", "trace", skel.murder_loc, (M, obj, skel.murder_loc),
                                   [Implication(Prop("Did", M, skel.murder_loc, (t_clean, T), ("touch", obj)), requires=(f"clean@{hk}",))],
                                   discover_needs=(obj,)))
    for a in living:
        if rng.random() >= skel.p_pin:
            continue
        sec = w.secrets.get(a)
        cands = [s for s in w.segments[a] if s.e - s.s >= 4 and s.loc != EXT and s.event_id.startswith("stay:")
                 and not (sec and not (s.e <= sec.iv[0] or s.s >= sec.iv[1]))]
        if not cands:
            continue
        s = rng.choice(cands)
        ln = rng.randint(3, min(8, s.e - s.s))
        t0 = rng.randint(s.s, s.e - ln)
        w.events.append(Event(f"log_{a}", "Logged", a, s.loc, t0, t0 + ln, ("device",), sight=0.5))
        w.evidence.append(Evidence(f"E_pin_{a}", "pin", s.loc, (a, s.loc),
                                   [Implication(Prop("At", a, s.loc, (t0, t0 + ln)))], established_iv=(t0, t0 + ln)))
    if construct:  # (c) containment device: the exterior access is logged from t_gate on (self-grounding, L3)
        t_gate = rng.randint(0, 20)
        for ext in [l.id for l in skel.locs if l.exterior]:
            w.events.append(Event(f"gate_{ext}", "Logged", vname, ext, t_gate, T, ("gate",), sight=0.0))
            w.evidence.append(Evidence(f"E_gate_{ext}", "gatelog", ext, (ext, "gate"),
                                       [Implication(Prop("NoStranger", None, ext, (t_gate, T)))], established_iv=(t_gate, T)))
        w.meta["t_gate"] = t_gate
    w.meta["physics"] = check_physics(w)
    if construct:  # the realised EliminationStructure, recorded for the case report (I-43)
        w.meta["structure"] = {"alibi_window": 8, "corroborator_rule": "outside_component", "time_pin": "physical",
                               "containment": "device_L3", "secret_clearance": 12, "opportunity_pin": bool(trace),
                               "alibi": w.meta.get("alibi_window"), "t_gate": w.meta.get("t_gate")}
    w.meta.update({"t_arr": segs[j].s, "t_dep": segs[j].e, "red_herring": rh, "secret_kind": kind, "trace": trace,
                   "watch": any(e.id == "E_watch" for e in w.evidence),
                   "pins": [e.id for e in w.evidence if e.kind == "pin"], "lovers": list(w.rels)})
    return w
