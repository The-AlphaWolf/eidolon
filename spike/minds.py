"""Phase 0.5 spike — minds slice.

Knowledge derivation (§4.8 incl. co-presence 4.8.6 and the gated absence rule 4.8.7 / I-34),
the layer-0 testimony pool (§19.5 robustness), the collusion graph (I-37) and the per-claim
admissibility lattice (§19.5, I-27). Only what V-5 needs; no beliefs, no memories.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict

from .model import (World, Prop, Evidence, Interval, iv_inter, iv_minus, iv_shrink, iv_widen,
                    ticks)

# case constants (§4.8, §8.3) — spike values
ATT_PRESENT = 0.3
ATT_AWAKE = 0.7
PERCEIVE = 0.2
IDENTIFY = 0.6
VOICE_ATTR = 0.4          # sound quality at which the voice's sex is perceived (not identity)
ABSENCE_DISCOUNT = 0.8
G_OWN = 2                 # granularity (min) of own-presence / co-presence claims
G_EVENT = 5               # sightings of routine events
G_ATTACK = 2              # the attack is salient (§8.3: strong memory -> fine granularity)
COLLUDING_RELS = {"spouse", "lover", "sibling", "accomplice", "employer_of_dependent"}


@dataclass
class Know:
    """KnowledgeEntry (§6.2): grounded access to a proposition, with provenance."""
    id: str
    who: str
    prop: Prop
    source: str                 # Participated | CoPresence | Absence | Witnessed | Heard
    events: tuple[str, ...]     # provenance *perception* ids (I-37: disjointness is over these)
    obs_loc: str                # where the observer was
    obs_iv: Interval            # when
    reliability: float
    g: int                      # time granularity of the claim this entry supports
    acquired_at: int


def _runs(vals: list[tuple[int, object]]) -> list[tuple[int, int, object]]:
    """Merge consecutive ticks with equal payload into (s, e, payload) runs."""
    out: list[tuple[int, int, object]] = []
    for t, v in vals:
        if out and out[-1][1] == t and out[-1][2] == v:
            out[-1] = (out[-1][0], t + 1, v)
        else:
            out.append((t, t + 1, v))
    return out


def derive_knowledge(w: World) -> list[Know]:
    ks: list[Know] = []
    n = 0

    def add(who, prop, source, events, obs_loc, obs_iv, rel, g, acq):
        nonlocal n
        n += 1
        ks.append(Know(f"K{n:04d}", who, prop, source, tuple(events), obs_loc, obs_iv, round(rel, 3), g, acq))

    for a in w.living():
        for i, sg in enumerate(w.segments[a]):
            ev = sg.event_id or f"stay:{a}:{i}"
            # 1. own presence (Participated)
            add(a, Prop("At", a, sg.loc, sg.iv), "Participated", [ev], sg.loc, sg.iv, 1.0, G_OWN, sg.s)
            if sg.attention < ATT_PRESENT:
                continue
            # 2. co-presence (§4.8.6)
            for x in w.actors:
                if x == a:
                    continue
                for xs in w.segments[x]:
                    if xs.loc != sg.loc:
                        continue
                    ov = iv_inter(sg.iv, xs.iv)
                    if ov:
                        add(a, Prop("At", x, sg.loc, ov), "CoPresence", [ev], sg.loc, sg.iv, sg.attention, G_OWN, ov[0])
            # 3. absence (§4.8.7, I-34): awake, continuous, entrances covered
            if sg.attention >= ATT_AWAKE and w.locs[sg.loc].entrances_visible:
                r = sg.attention * 1.0 * ABSENCE_DISCOUNT
                for x in w.living():
                    if x == a:
                        continue
                    here = [xs.iv for xs in w.segments[x] if xs.loc == sg.loc]
                    for sub in iv_minus(sg.iv, here):
                        add(a, Prop("NotAt", x, sg.loc, sub), "Absence", [ev], sg.loc, sg.iv, r, G_OWN, sub[0])
                add(a, Prop("NoStranger", None, sg.loc, sg.iv), "Absence", [ev], sg.loc, sg.iv, r, G_OWN, sg.s)
    # 4. event perception (§4.8.1-5)
    edges = defaultdict(list)
    for obs_at, perceives, modality, q in w.perception:
        edges[(obs_at, perceives)].append((modality, q))
    for e in w.events:
        if e.kind not in ("Attack", "Speak", "Clean", "Logged"):
            continue
        g = G_ATTACK if e.kind in ("Attack", "Speak") else G_EVENT
        sound_kind = "struggle" if e.kind == "Attack" else "argument"
        if e.kind == "Clean":  # cleaner's own Participated entry (the `requires` statement of a trace)
            own_seg = next((sg.iv for sg in w.segments[e.actor] if sg.s <= e.t < sg.e), e.iv)  # I-46 rule 9
            add(e.actor, Prop("Did", e.actor, e.loc, e.iv, ("clean", e.objects[0])), "Participated",
                [f"{e.id}@{e.actor}"], e.loc, own_seg, 1.0, G_OWN, e.t)
        for a in w.living():
            if a == e.actor or a in e.participants:
                continue
            per_tick: list[tuple[int, object]] = []
            for t in ticks(e.iv):
                la, att = w.loc_at(a, t), w.attention_at(a, t)
                if la is None or att < ATT_PRESENT:
                    continue
                if la == e.loc:
                    qs, qh = e.sight * att, e.sound * att
                else:
                    qs = max([q for m, q in edges[(la, e.loc)] if m == "sight"] or [0]) * e.sight * att
                    qh = max([q for m, q in edges[(la, e.loc)] if m == "sound"] or [0]) * e.sound * att
                per_tick.append((t, (la, round(qs, 3), round(qh, 3))))
            for s, en, (la, qs, qh) in _runs(per_tick):
                pid = f"{e.id}@{a}"
                seg_iv = next(sg.iv for sg in w.segments[a] if sg.s <= s < sg.e)  # observer's presence segment
                if qs >= PERCEIVE:
                    ident = qs >= IDENTIFY
                    add(a, Prop("Saw", e.actor if ident else None, e.loc, (s, en), (ident,)), "Witnessed",
                        [pid], la, seg_iv, qs, g, s)
                if e.kind in ("Attack", "Speak") and qh >= PERCEIVE:
                    who = e.actor if (qh >= IDENTIFY and e.identifies_voice) else None
                    attr = w.actors[e.actor].attrs.get("sex") if (who is None and e.identifies_voice and qh >= VOICE_ATTR) else None
                    add(a, Prop("Heard", who, e.loc, (s, en), (sound_kind, attr)), "Heard", [pid], la, seg_iv, qh, g, s)
    # 5. presence-based sightings through sight edges (Observe)
    for a in w.living():
        for x in w.actors:
            if x == a:
                continue
            per_tick = []
            for t in range(w.t_inv):
                la, att = w.loc_at(a, t), w.attention_at(a, t)
                lx = w.loc_at(x, t)
                if la is None or lx is None or la == lx or att < ATT_PRESENT:
                    continue
                q = max([q for m, q in edges[(la, lx)] if m == "sight"] or [0]) * att
                if q >= PERCEIVE:
                    per_tick.append((t, (la, lx, round(q, 3))))
            for s, en, (la, lx, q) in _runs(per_tick):
                seg_iv = next(sg.iv for sg in w.segments[a] if sg.s <= s < sg.e)
                if q >= IDENTIFY:  # continuous identified observation: universal presence, own-presence granularity
                    add(a, Prop("At", x, lx, (s, en)), "Witnessed", [f"see:{a}:{x}:{lx}:{s}"], la, seg_iv, q, G_OWN, s)
                else:
                    add(a, Prop("Saw", None, lx, (s, en), (False,)), "Witnessed", [f"see:{a}:{x}:{lx}:{s}"], la, seg_iv, q, G_EVENT, s)
    return ks


# ------------------------------------------------------------ collusion (I-37)
def collusion_components(w: World) -> dict[str, int]:
    parent = {a: a for a in w.living()}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        if a in parent and b in parent:
            parent[find(a)] = find(b)

    for a, b, kind in w.rels:
        if kind in COLLUDING_RELS:
            union(a, b)
    for sec in w.secrets.values():
        for b in sec.shared_with:
            union(sec.owner, b)
    roots = sorted({find(a) for a in parent})
    return {a: roots.index(find(a)) for a in parent}


# ------------------------------------------------------------- testimony pool
@dataclass
class Testimony:
    id: str
    k: Know


def testimony_pool(w: World, knowledge: list[Know], withhold: str = "layer0_all", cracked: set[str] = frozenset()) -> dict[str, Testimony]:
    """What can be obtained by asking, with secret-holders stuck at layer 0 (§19.5 robustness).

    withhold="layer0_all": every actor withholds knowledge acquired while inside their own
    protected interval, except actors in `cracked` (I-45 fixpoint rounds pass the innocents
    already excluded); the murderer is never cracked.
    withhold="murderer_only": only the murderer withholds (sensitivity: all innocents cracked).
    """
    pool: dict[str, Testimony] = {}
    for k in knowledge:
        if w.actors[k.who].role != "living":
            continue
        sec = w.secrets.get(k.who)
        withheld = k.who == w.murderer or (withhold == "layer0_all" and k.who not in cracked)
        if sec and withheld and iv_inter(k.obs_iv, sec.iv):
            continue
        pool[f"S:{k.id}"] = Testimony(f"S:{k.id}", k)
    return pool


def material_all(w: World, knowledge: list[Know], withhold: str, cracked: set[str] = frozenset()) -> dict[str, Evidence | Testimony]:
    m: dict[str, Evidence | Testimony] = {e.id: e for e in w.evidence}
    m.update(testimony_pool(w, knowledge, withhold, cracked))
    return m


# --------------------------------------------------------- admissibility (I-27)
@dataclass
class Constraint:
    id: str
    item: str                   # material item id
    prop: Prop                  # admissible proposition (possibly a sub-interval of the claim)
    level: int                  # 3 physical, 2 fixed/corroborated testimony, 1 single testimony
    sources: tuple[str, ...]    # speakers / pins / required items grounding the level (fragility report)

    def to_json(self):
        return {"id": self.id, "item": self.item, "prop": str(self.prop), "level": self.level, "sources": list(self.sources)}


def _ticks_to_ivs(ts: set[int]) -> list[Interval]:
    out, run = [], None
    for t in sorted(ts):
        if run and run[1] == t:
            run = (run[0], t + 1)
        else:
            if run:
                out.append(run)
            run = (t, t + 1)
    if run:
        out.append(run)
    return out


def _claimed(k: Know, T: int) -> Interval | None:
    if k.prop.kind in ("At", "NotAt", "NoStranger"):
        return iv_shrink(k.prop.iv, k.g)
    return iv_widen(k.prop.iv, k.g, 0, T)


def _resolve_requires(material: dict, requires: tuple[str, ...], lvl: dict) -> list[str] | None:
    """`requires` names evidence ids or provenance ids (a witness's own Participated event)."""
    out = []
    for r in requires:
        hits = [iid for iid, it in material.items() if iid == r or (isinstance(it, Testimony) and r in it.k.events)]
        if not hits:
            return None
        out.append(max(hits, key=lambda i: (lvl[i], i)))
    return out


def admissible(w: World, material: dict, comps: dict[str, int], fix: str = "tick") -> list[Constraint]:
    """Per-claim admissibility (§19.5). Returns constraints at levels 3/2/1.

    L2 for testimony = perception-grounded AND (speaker's relevant presence fixed by L3 pins,
    or by a non-colluding source with disjoint provenance) OR the claim itself is corroborated by
    such a source. `fix="tick"`: presence is fixed tick by tick; `fix="segment"`: one fixed tick
    fixes the whole presence segment (the reading §29.1 practises). The spec does not say which.
    """
    cons: list[Constraint] = []
    evs = sorted((it for it in material.values() if isinstance(it, Evidence)), key=lambda e: e.id)
    tests = sorted((it for it in material.values() if isinstance(it, Testimony)), key=lambda t: t.id)

    # pass A: physical evidence without `requires` (L3)
    l3_at: dict[str, set[tuple[str, int]]] = defaultdict(set)
    l3_fix: dict[tuple[str, str], set[str]] = defaultdict(set)
    for ev in evs:
        if not ev.authentic:
            continue
        for j, imp in enumerate(ev.implications):
            if imp.requires:
                continue
            p = imp.prop
            if p.iv and ev.established_iv is not None and not (ev.established_iv[0] <= p.iv[0] and p.iv[1] <= ev.established_iv[1]):
                continue  # P-9 / I-30: interval not established
            cons.append(Constraint(f"{ev.id}#{j}", ev.id, p, 3, (ev.id,)))
            if p.kind == "At":
                for t in ticks(p.iv):
                    l3_at[p.actor].add((p.loc, t))
                l3_fix[(p.actor, p.loc)].add(ev.id)

    # pass B: testimony
    by_speaker: dict[str, list[Testimony]] = defaultdict(list)
    for t in tests:
        by_speaker[t.k.who].append(t)

    def independent(a: Know, b: Know) -> bool:
        return a.who != b.who and comps.get(a.who) != comps.get(b.who) and not (set(a.events) & set(b.events))

    for tm in tests:
        k = tm.k
        s = k.who
        claimed = _claimed(k, w.t_inv)
        if claimed is None:
            continue
        fixed: set[int] = {t for (l, t) in l3_at.get(s, ()) if l == k.obs_loc and k.obs_iv[0] <= t < k.obs_iv[1]}
        fixers: set[str] = set(l3_fix.get((s, k.obs_loc), ())) if fixed else set()
        direct: set[int] = set()
        for r_sp, rts in by_speaker.items():
            if r_sp == s:
                continue
            for rt in rts:
                rk = rt.k
                if not independent(k, rk):
                    continue
                rc = _claimed(rk, w.t_inv)
                if rc is None:
                    continue
                # presence fixing: r places s at k.obs_loc
                if rk.prop.kind == "At" and rk.prop.actor == s and rk.prop.loc == k.obs_loc:
                    ov = iv_inter(rc, k.obs_iv)
                    if ov:
                        fixed |= set(ticks(ov))
                        fixers.add(rt.id)
                if rk.prop.kind == "Saw" and rk.prop.extra[0] and rk.prop.actor == s and rk.prop.loc == k.obs_loc and rk.g == 0:
                    fixed |= set(ticks(rk.prop.iv)) & set(ticks(k.obs_iv))
                    fixers.add(rt.id)
                # direct corroboration of the same claim
                same = (rk.prop.kind == k.prop.kind and rk.prop.actor == k.prop.actor and rk.prop.loc == k.prop.loc)
                if k.prop.kind == "Saw":
                    same = same and k.prop.extra[0] and rk.prop.extra[0]
                if k.prop.kind == "Heard":
                    same = same and rk.prop.extra == k.prop.extra
                if same:
                    ov = iv_inter(rc, claimed)
                    if ov:
                        direct |= set(ticks(ov))
                        fixers.add(rt.id)
        if fix == "segment" and fixed:
            fixed = set(ticks(k.obs_iv))
        p = k.prop
        if p.kind in ("At", "NotAt", "NoStranger"):
            l2 = set(ticks(claimed)) & (fixed | direct)
            n = 0
            for sub in _ticks_to_ivs(l2):
                cons.append(Constraint(f"{tm.id}#L2.{n}", tm.id, Prop(p.kind, p.actor, p.loc, sub, p.extra), 2, (s,) + tuple(sorted(fixers))))
                n += 1
            for sub in _ticks_to_ivs(set(ticks(claimed)) - l2):
                cons.append(Constraint(f"{tm.id}#L1.{n}", tm.id, Prop(p.kind, p.actor, p.loc, sub, p.extra), 1, (s,)))
                n += 1
        elif p.kind in ("Did", "Saw", "Heard"):
            if p.kind == "Saw" and not p.extra[0]:
                continue  # unidentified sightings never constrain (§13.2)
            iv = claimed
            if direct:
                level, iv = 2, _ticks_to_ivs(direct)[0]
            elif set(ticks(claimed)) <= fixed:
                level = 2
            else:
                level = 1
            cons.append(Constraint(f"{tm.id}#L{level}", tm.id, Prop(p.kind, p.actor, p.loc, iv, p.extra), level, (s,) + tuple(sorted(fixers))))

    # pass C: implications with `requires` — level = min over the chain (I-27)
    lvl: dict[str, int] = defaultdict(int)
    for c in cons:
        lvl[c.item] = max(lvl[c.item], c.level)
    for ev in evs:
        if not ev.authentic:
            continue
        for j, imp in enumerate(ev.implications):
            if not imp.requires:
                continue
            req_items = _resolve_requires(material, imp.requires, lvl)
            if req_items is None:
                continue
            level = min([3] + [lvl[i] for i in req_items])
            if level >= 1:
                cons.append(Constraint(f"{ev.id}#{j}", ev.id, imp.prop, level, (ev.id,) + tuple(req_items)))
    return sorted(cons, key=lambda c: c.id)
