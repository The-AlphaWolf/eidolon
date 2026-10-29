"""The V-5 material model and the per-claim admissibility lattice (§19.5, I-27, I-37, I-44, I-45).

Ported from the Phase 0.5 spike (`spike/minds.py::admissible`, the version that passed the gate)
onto the production models, with three deliberate differences:

* testimony atoms come from `world.perception.derive_perception` (the validated Phase 1
  derivation; it carries the observer's presence segment and the claim granularity, which
  `KnowledgeEntry` drops), not from a second derivation;
* the L3 gate is the production P-9 (`evidence.grounding.established_interval`), not a copy;
* the collusion graph is `SecretStore.collusion_edges` (I-37), not re-derived.

Nothing here reads a `CanonicalSolution`, a `Secret.kind`, or any `load_bearing` flag.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from ..decision.secrets import SecretStore
from ..evidence.grounding import established_interval
from ..evidence.model import Evidence, EvidenceStore
from ..minds import accounts
from ..world.case import Case
from ..world.interval import contains, intersect, overlaps, shrink, ticks, widen
from ..world.interval import Interval
from ..world.perception import derive_perception

L0, L1, L2, L3 = 0, 1, 2, 3


@dataclass(frozen=True)
class Know:
    """One piece of obtainable testimony: what an interrogable actor could be asked, with the
    provenance the lattice needs (I-37 disjointness is over `events`; I-44 fixing is over
    `obs_loc`/`obs_iv`)."""
    id: str
    who: str
    prop: object                    # a world Proposition (At / NotAt / Did / Saw / Heard / …)
    source: str                     # Participated | CoPresence | Absence | Witnessed
    events: tuple[str, ...]
    obs_loc: str
    obs_iv: Interval
    g: int


@dataclass(frozen=True)
class Constraint:
    """An admissible constraint on ONE actor's whereabouts (or a window/containment fact).

    kind: "At" (forced, universal) | "NotAt" (blocked) | "Exist" (some tick in `iv` at `loc`)
          | "Died" (time pin: the victim's death was in `loc` during `iv`)
          | "Heard" (an attack was heard from `loc` during `iv`)  | "NoStranger" (containment —
          `observer` is who looked, and so who is excluded from "nobody": Phase 1 reading A)."""
    id: str
    item: str
    kind: str
    actor: str | None
    loc: str | None
    iv: Interval
    level: int
    sources: tuple[str, ...] = ()
    observer: str | None = None

    def to_json(self) -> dict:
        return {"id": self.id, "item": self.item, "kind": self.kind, "actor": self.actor, "observer": self.observer,
                "loc": self.loc, "iv": list(self.iv), "level": self.level, "sources": list(self.sources)}


Item = Evidence | Know


# ------------------------------------------------------------------ testimony pool
def know_atoms(case: Case) -> list[Know]:
    """Every observation an interrogable actor could report. Dead actors are not
    interrogable (their perceptions end with them; the body is scene evidence, not a witness)."""
    alive = set(case.living_actors())
    return [Know(f"S:{pf.id}", pf.observer, pf.proposition, pf.source, pf.provenance,
                 pf.obs_location, pf.obs_interval, pf.granularity)
            for pf in derive_perception(case) if pf.observer in alive]


def protected_intervals(secrets: SecretStore) -> dict[str, list[Interval]]:
    """Owner -> intervals their secrets protect (ADR-26: `Secret.protected_intervals()`, the one definition)."""
    out: dict[str, list[Interval]] = defaultdict(list)
    for s in secrets.all():
        out[s.owner] += s.protected_intervals()
    return {o: ivs for o, ivs in out.items() if ivs}


def testimony_pool(atoms: Iterable[Know], protected: dict[str, list[Interval]],
                   cracked: frozenset[str] = frozenset()) -> dict[str, Know]:
    """§19.5 round 0 / I-45: a secret-holder is stuck at layer 0 — they withhold everything they
    acquired inside their own protected interval — unless `cracked`. Uniform over every secret
    holder: the solver never asks which of them is the murderer."""
    pool: dict[str, Know] = {}
    for k in atoms:
        if k.who not in cracked and any(overlaps(k.obs_iv, iv) for iv in protected.get(k.who, ())):
            continue
        pool[k.id] = k
    return pool


def material(evidence: Iterable[Evidence], pool: dict[str, Know]) -> dict[str, Item]:
    m: dict[str, Item] = {e.id: e for e in evidence}
    m.update(pool)
    return m


# ------------------------------------------------------------------ collusion (I-37)
def components(case: Case, secrets: SecretStore) -> dict[str, int]:
    parent = {a: a for a in case.actors}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for edge in secrets.collusion_edges(case.rels):
        a, *rest = sorted(edge)
        for b in rest:
            if a in parent and b in parent:
                parent[find(a)] = find(b)
    roots = sorted({find(a) for a in parent})
    return {a: roots.index(find(a)) for a in parent}


# ------------------------------------------------------------------ helpers
def claimed(k: Know, T: int) -> Interval | None:
    """The window a claim actually asserts (§13.2): a universal claim only asserts the inner part
    at its granularity; an existential claim's window is widened by it."""
    if k.prop.kind in ("At", "NotAt"):
        return shrink(k.prop.interval, k.g)
    return widen(k.prop.interval, k.g, 0, T)


def _runs(ts: set[int]) -> list[Interval]:
    out: list[Interval] = []
    run: Interval | None = None
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


def _resolve(case: Case, mat: dict[str, Item], requires: tuple[str, ...], lvl: dict[str, int]) -> list[str] | None:
    """One `requires` token -> the best item it names in the material. An account token resolves
    through `minds.accounts` (ADR-23, I-49) — the SAME resolver P-9, V-3 and the runtime unlock use."""
    out: list[str] = []
    for r in requires:
        if r in mat and isinstance(mat[r], Evidence):
            hits = [r]
        else:
            hits = [a for a in accounts.atoms_of(case, r) if a in mat]
        if not hits:
            return None
        out.append(max(hits, key=lambda i: (lvl.get(i, 0), i)))
    return out


def _as_constraint(prop, cid: str, item: str, level: int, sources: tuple[str, ...], iv: Interval | None = None,
                   victim: str | None = None) -> Constraint | None:
    """Map a world proposition to the solver's constraint kinds. Everything the DP cannot use
    (state, objects, relations, unidentified sightings) is dropped, never approximated."""
    k = prop.kind
    iv = iv or getattr(prop, "interval", None)
    if k == "At":
        return Constraint(cid, item, "At", prop.actor, prop.location, iv, level, sources)
    if k == "NotAt":
        return Constraint(cid, item, "NotAt", prop.actor, prop.location, iv, level, sources)
    if k == "Did":
        if prop.action == "Die" and prop.actor == victim and prop.location:
            return Constraint(cid, item, "Died", prop.actor, prop.location, iv, level, sources)
        if prop.location:
            return Constraint(cid, item, "Exist", prop.actor, prop.location, iv, level, sources)
        return None
    if k == "Saw":
        if prop.subject == "nobody":
            return Constraint(cid, item, "NoStranger", None, prop.location, iv, level, sources, observer=prop.observer)
        if prop.identified and prop.subject != "figure":
            return Constraint(cid, item, "Exist", prop.subject, prop.location, iv, level, sources)
        return None
    if k == "Heard":
        if prop.sound_kind == "attack" and prop.from_location:
            c = Constraint(cid, item, "Heard", prop.identified_actor, prop.from_location, iv, level, sources)
            return c
        if prop.identified_actor and prop.from_location:
            return Constraint(cid, item, "Exist", prop.identified_actor, prop.from_location, iv, level, sources)
        return None
    return None


# ------------------------------------------------------------------ the lattice
def admissible(case: Case, store: EvidenceStore, mat: dict[str, Item], comps: dict[str, int],
               victim: str | None = None, fix: str = "tick") -> list[Constraint]:
    """Per-claim admissibility (§19.5). L3 = authentic physical evidence whose interval P-9
    establishes; L2 = perception-grounded testimony whose speaker's presence is fixed tick by
    tick (I-44) by L3 material or by an independent, non-colluding source, or which is itself
    directly corroborated; L1 = single uncorroborated testimony; planted evidence (L0) and
    `InvestigationTold` chains are never here. `fix="segment"` is the rejected reading
    (one fixed tick fixes the whole segment) kept only for the negative test that shows it."""
    T = case.t_investigation
    stmt = accounts.token_intervals(case)
    evs = sorted((it for it in mat.values() if isinstance(it, Evidence)), key=lambda e: e.id)
    tests = sorted((it for it in mat.values() if isinstance(it, Know)), key=lambda t: t.id)
    cons: list[Constraint] = []

    # pass A: authentic physical evidence with no `requires` (L3), P-9 gated
    l3_at: dict[str, set[tuple[str, int]]] = defaultdict(set)
    l3_fix: dict[tuple[str, str], set[str]] = defaultdict(set)
    for ev in evs:
        if not ev.authentic:
            continue
        for j, imp in enumerate(ev.implications):
            if imp.requires:
                continue
            iv = getattr(imp.proposition, "interval", None)
            if iv is not None and not contains(established_interval(imp, store, T, stmt, ev.created_at), iv):
                continue
            c = _as_constraint(imp.proposition, f"{ev.id}#{j}", ev.id, L3, (ev.id,), victim=victim)
            if c is None:
                continue
            cons.append(c)
            if c.kind == "At":
                for t in ticks(c.iv):
                    l3_at[c.actor].add((c.loc, t))
                l3_fix[(c.actor, c.loc)].add(ev.id)

    # pass B: testimony
    by_speaker: dict[str, list[Know]] = defaultdict(list)
    for t in tests:
        by_speaker[t.who].append(t)

    def independent(a: Know, b: Know) -> bool:
        return a.who != b.who and comps.get(a.who) != comps.get(b.who) and not (set(a.events) & set(b.events))

    for k in tests:
        s = k.who
        cl = claimed(k, T)
        if cl is None:
            continue
        fixed: set[int] = {t for (l, t) in l3_at.get(s, ()) if l == k.obs_loc and k.obs_iv[0] <= t < k.obs_iv[1]}
        fixers: set[str] = set(l3_fix.get((s, k.obs_loc), ())) if fixed else set()
        direct: set[int] = set()
        for r_sp, rts in by_speaker.items():
            if r_sp == s:
                continue
            for rk in rts:
                if not independent(k, rk):
                    continue
                rc = claimed(rk, T)
                if rc is None:
                    continue
                rp, kp = rk.prop, k.prop
                if rp.kind == "At" and rp.actor == s and rp.location == k.obs_loc:
                    ov = intersect(rc, k.obs_iv)
                    if ov:
                        fixed |= set(ticks(ov))
                        fixers.add(rk.id)
                if _same_claim(kp, rp):
                    ov = intersect(rc, cl)
                    if ov:
                        direct |= set(ticks(ov))
                        fixers.add(rk.id)
        if fix == "segment" and fixed:
            fixed = set(ticks(k.obs_iv))
        p = k.prop
        if p.kind in ("At", "NotAt"):
            l2 = set(ticks(cl)) & (fixed | direct)
            for n, sub in enumerate(_runs(l2)):
                c = _as_constraint(p, f"{k.id}#L2.{n}", k.id, L2, (s,) + tuple(sorted(fixers)), sub, victim)
                if c:
                    cons.append(c)
            for n, sub in enumerate(_runs(set(ticks(cl)) - l2)):
                c = _as_constraint(p, f"{k.id}#L1.{n}", k.id, L1, (s,), sub, victim)
                if c:
                    cons.append(c)
        else:
            iv, level = cl, L1
            if direct:
                level, iv = L2, _runs(direct)[0]
            elif set(ticks(cl)) <= fixed:
                level = L2
            c = _as_constraint(p, f"{k.id}#L{level}", k.id, level, (s,) + tuple(sorted(fixers)), iv, victim)
            if c:
                cons.append(c)

    # pass C: implications with `requires` — level = min over the chain (I-27), P-9 by the hull
    lvl: dict[str, int] = defaultdict(int)
    for c in cons:
        lvl[c.item] = max(lvl[c.item], c.level)
    for ev in evs:
        if not ev.authentic:
            continue
        for j, imp in enumerate(ev.implications):
            if not imp.requires:
                continue
            req = _resolve(case, mat, imp.requires, lvl)
            if req is None:
                continue
            iv = getattr(imp.proposition, "interval", None)
            if iv is not None and not contains(established_interval(imp, store, T, stmt, ev.created_at), iv):
                continue
            level = min([L3] + [lvl[i] for i in req])
            if level >= L1:
                c = _as_constraint(imp.proposition, f"{ev.id}#{j}", ev.id, level, (ev.id,) + tuple(req), victim=victim)
                if c:
                    cons.append(c)
    return sorted(cons, key=lambda c: c.id)


def _same_claim(a, b) -> bool:
    """Do two testimonies assert the same thing (so that one can corroborate the other)?"""
    if a.kind != b.kind:
        return False
    if a.kind in ("At", "NotAt"):
        return a.actor == b.actor and a.location == b.location
    if a.kind == "Did":
        return a.actor == b.actor and a.location == b.location and a.action == b.action and a.object == b.object
    if a.kind == "Saw":
        return a.identified and b.identified and a.subject == b.subject and a.location == b.location
    if a.kind == "Heard":
        return (a.from_location == b.from_location and a.sound_kind == b.sound_kind
                and a.identified_actor == b.identified_actor)
    return False
