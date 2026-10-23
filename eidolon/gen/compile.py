"""Compile a planner `Draft` into a `CasePackage` (§18.3 stages 4, 6, 8, 11).

Everything the planner decided becomes a typed, sealed object: the CaseLog (`Stay`/action
events), the evidence table with its `DiscoverySpec`s and provenance, the `Secret`s with their
protected facts and a first-cut cover story, the red herring with its refuter, the canonical
solution and the DECLARED elimination structure. No solving happens here, and nothing here reads
a verdict: validation is `pipeline.validate`'s job, on the sealed package alone.
"""
from __future__ import annotations

import hashlib

from ..decision.claims import Claim
from ..decision.secrets import CoverLayer, CoverStory, EvidenceResponse, Secret, Stakes
from ..evidence.contradiction import contradiction
from ..evidence.model import DiscoverySpec, Evidence, Implication, Prereq, RedHerringSpec
from ..minds import accounts
from ..solve.package import (
    Alternative, CanonicalSolution, CasePackage, EliminationStructure,
)
from ..world.case import Case
from ..world.entities import Actor
from ..world.events import EffActorAt, EffActorState, Event
from ..world.frozen import FrozenDict
from ..world.perception import derive_perception
from ..world.propositions import At, Did, DidNot, Rel, Saw
from .planner import ALIBI_WINDOW, SECRET_CLEARANCE, Draft

RESOLVE_L0 = 6000        # bp a breaker set must reach to peel layer 0 (§10.2 `resolve`)
RESOLVE_PRE_TERMINAL = 8000
RESOLVE_TERMINAL = 10000


def _pick(seed: int, key: str, options: tuple):
    """Deterministic choice with no RNG state: hash of (seed, key). Used for flavor-level
    picks so adding one never perturbs the planner's random stream."""
    h = hashlib.sha256(f"{seed}|{key}".encode()).digest()
    return options[h[0] % len(options)]


def _stay_events(dr: Draft) -> list[Event]:
    out: list[Event] = []
    for a in sorted(dr.segments):
        for i, sg in enumerate(dr.segments[a]):
            eff = [EffActorAt(actor=a, location=sg.loc)]
            if sg.attention != "1.0":
                eff.append(EffActorState(actor=a, attr="attention", value=sg.attention))
            out.append(Event(id=f"stay:{a}:{i}", kind="Stay", interval=(sg.s, sg.e), location=sg.loc,
                             actor=a, effects=tuple(eff)))
    return out


def _evidence(dr: Draft) -> tuple[Evidence, ...]:
    skel, M, T = dr.skel, dr.murderer, dr.skel.T
    victim = skel.victim[0]
    vloc, obj, t_m = skel.murder_loc, skel.weapon.id, dr.t_m
    hk, t_c, t_clean = dr.meta["hk"], dr.meta["t_c"], dr.meta["t_clean"]
    ev: list[Evidence] = []

    def look(at, text, **kw):
        return DiscoverySpec(action="Look", at=at, reveals_text=text, **kw)

    ev.append(Evidence(id="E_scene", kind="Object", object=obj, location_at_investigation=vloc,
                       discovery=look(vloc, f"{victim} lies dead in {next(l.name for l in skel.locations if l.id == vloc)}; "
                                            f"{skel.weapon.name} lies nearby."), load_bearing=False))
    ev.append(Evidence(id="E_watch", kind="Timepiece", created_at=(t_m, t_m + 1), load_bearing=True,
                       implications=(Implication(proposition=Did(actor=victim, action="Die", interval=(t_m, t_m + 1),
                                                                 location=vloc)),),
                       discovery=look(vloc, "The victim's watch stopped at the moment of the blow.")))
    ev.append(Evidence(id="E_trace", kind="Fingerprint", object=obj, location_at_investigation=vloc,
                       reliability=0.9, load_bearing=True,
                       implications=(Implication(
                           proposition=Did(actor=M, action="touch", object=obj, location=vloc, interval=(t_clean, T)),
                           strength=0.9, requires=(f"clean@{hk}",)),),
                       discovery=DiscoverySpec(action="Dust", at=obj, prerequisites=(Prereq(kind="EvidenceFound", ref="E_scene"),),
                                               reveals_text="A print on the weapon.", cue=obj)))
    ev.append(Evidence(id="E_pin_clean", kind="Digital", created_at=(t_c, t_c + 8), load_bearing=True,
                       implications=(Implication(proposition=At(actor=hk, location=vloc, interval=(t_c, t_c + 8))),),
                       discovery=look(vloc, "A door log records who was in the room while it was cleaned.")))
    inn = dr.meta["innocents"]
    n_rh = {"easy": 1, "standard": 2, "hard": 3}[skel.difficulty]           # §20.2 red herrings per band
    ranked = sorted((a for a in inn if a in dr.secrets), key=lambda a: hashlib.sha256(f"{dr.seed}|rh|{a}".encode()).hexdigest())
    rhs = set(ranked[:n_rh])
    dr.meta["rh"] = sorted(rhs)
    for pid, a, loc, iv in dr.pins:
        if a in rhs:                       # a herring target's own pin would exclude it without the refuter (§19.6)
            continue
        ev.append(Evidence(id=pid, kind="Digital", created_at=iv,
                           implications=(Implication(proposition=At(actor=a, location=loc, interval=iv)),),
                           discovery=look(loc, "A device log places someone here.")))
    for ext in skel.exterior:
        g = dr.meta["t_gate"]
        ev.append(Evidence(id=f"E_gate_{ext}", kind="Digital", created_at=(g, T), load_bearing=True,
                           implications=(Implication(proposition=Saw(observer=victim, subject="nobody", location=ext,
                                                                     interval=(g, T), identified=False)),),
                           discovery=look(ext, "The gate log shows no stranger passed.")))
    # secrets' revealers (breakers, §19.3 (iii)) and the red herring with its refuter (§19.6)
    a_loc, a0, a1 = dr.meta["alibi"]
    # §20.2 `Proof-core size`, realised as a planner knob (B-3). One room-level device log that
    # records EVERY innocent in the alibi room is a single L3 elimination for all of them, so the
    # deletion-minimal proof core is {time pin, containment, this log} — the easy band's 3-4.
    # Without it each innocent needs their own elimination and the core grows with the cast, which
    # is what the standard band wants. `EliminationStructure` already contemplates exactly this
    # choice ("co-present with an actor from ANOTHER collusion component ... OR carries an L3
    # presence pin over the window", §18.2).
    if skel.shared_alibi_log:
        ev.append(Evidence(id="E_alibi_room", kind="Digital", created_at=(a0, a1), load_bearing=True,
                           implications=tuple(Implication(proposition=At(actor=a, location=a_loc, interval=(a0, a1)))
                                              for a in sorted(inn)),
                           discovery=look(a_loc, "A room log records everyone who was in here around the time of death.")))
    for a in sorted(inn):
        sec = dr.secrets[a]
        red = None
        if a in rhs:
            # The refuter is whatever actually fixes this innocent over the murder window: their own
            # pin, or the shared room log. §19.6's "the herring must mislead" check withholds it, and
            # with the shared log withheld nothing else places them — the herring still misleads.
            refuter = "E_alibi_room" if skel.shared_alibi_log else f"E_alibi_{a}"
            red = RedHerringSpec(misleads_toward=f"H_{a}_did_it", refuter=refuter)
            if not skel.shared_alibi_log:
                ev.append(Evidence(id=f"E_alibi_{a}", kind="Digital", created_at=(a0, a1),
                                   implications=(Implication(proposition=At(actor=a, location=a_loc, interval=(a0, a1))),),
                                   discovery=look(a_loc, "A device log fixes where this person was around the time of death.")))
        ev.append(Evidence(id=f"E_secret_{a}", kind="Object" if a in rhs else "Digital", created_at=sec["iv"],
                           red_herring=red,
                           implications=(Implication(proposition=At(actor=a, location=sec["loc"], interval=sec["iv"])),),
                           discovery=look(sec["loc"], "Something here shows someone was not where they said.")))
    return _chain(dr, tuple(ev))


def _chain(dr: Draft, ev: tuple[Evidence, ...]) -> tuple[Evidence, ...]:
    """§20.2 `Min discovery depth`: gate the proof-core items behind one another so the deepest is
    `chain_depth` hops from the opening material (scene -> watch -> door log -> containment log).
    Each hop is a real prerequisite the earlier item's discovery satisfies (`EvidenceFound`)."""
    order = ["E_scene", "E_watch", "E_pin_clean"] + [f"E_gate_{e}" for e in dr.skel.exterior][:1]
    order = order[:dr.skel.chain_depth + 1]
    gates = {order[i]: order[i - 1] for i in range(1, len(order))}
    out = []
    for e in ev:
        if e.id in gates:
            d = e.discovery
            e = e.model_copy(update={"discovery": d.model_copy(update={
                "prerequisites": d.prerequisites + (Prereq(kind="EvidenceFound", ref=gates[e.id]),)})})
        out.append(e)
    return tuple(out)


def _accounts(dr: Draft, case: Case) -> tuple[str, ...]:
    """§18.3 stage 7 / ADR-23: the ACCOUNT TOKENS a cover's breaker rests on — here, the housekeeper's own account
    of the cleaning, the token `E_trace`'s `requires` names. Declared, not scripted: what the housekeeper can SAY is
    derived from her own `Participated` knowledge (`minds.accounts`), the one resolver the solver, P-9, V-3 and the
    runtime all use. If the account has nothing behind it, nothing is declared and V-3 will say so."""
    token = f"clean@{dr.meta['hk']}"
    return (token,) if accounts.atoms_of(case, token) else ()


def _secrets(dr: Draft, case: Case, evidence=()) -> tuple[Secret, ...]:
    """§18.3 stage 7 (cover synthesis). Each cover is authored so that V-3 (§19.3) can DERIVE a
    breaker set for its layer 0 from material that is actually in the case and actually
    admissible, and so that every item of that intended set carries an `EvidenceResponse`.
    Nothing here reads a solver verdict: the breaker is chosen from the world the planner built
    (the trace it created, the secret-revealing item it placed), and V-3 confirms or rejects it.

    Layer counts follow §20.2's `Cover layers (murderer)` row: easy 2, standard 3. A terminal
    layer carries the concession it lands on, so it is never an empty dead end; V-3 derives no
    breaker set for a terminal layer (§10.2: the peel stops there)."""
    skel = dr.skel
    out: list[Secret] = []
    kinds = ("affair", "theft", "debt", "minor_infraction")
    n_murder_layers = 2 if skel.difficulty == "easy" else 3
    for a in sorted(dr.secrets):
        s = dr.secrets[a]
        murder = s.get("murder", False)
        loc, iv = s["loc"], s["iv"]
        protected = (At(actor=a, location=loc, interval=iv),)
        if murder:    # where the murderer was over the whole excursion (hops and the stay in the room)
            protected = tuple(At(actor=a, location=l, interval=(s0, e0)) for l, s0, e0 in s["segs"])
            protected += (Did(actor=a, action="Attack", interval=(dr.t_m, dr.t_m + 1), object=skel.weapon.id,
                              location=skel.murder_loc),)
        kind = "murder" if murder else ("affair" if s["shared_with"] else _pick(dr.seed, f"kind:{a}", kinds))
        cover_locs = tuple(sorted(l for l in skel.role_weights["guest"] if l not in (loc, skel.murder_loc)))
        lie_loc = _pick(dr.seed, f"lie:{a}", cover_locs)
        terminal = "confession" if int.from_bytes(hashlib.sha256(f"{dr.seed}|term:{a}".encode()).digest()[:1], "big") < 128 \
            else "stonewall"
        if murder:
            layers, responses = _murder_cover(dr, a, protected, terminal, n_murder_layers,
                                              _alibi_lie(dr, case, evidence, a, iv))
        else:
            layers, responses = _innocent_cover(a, loc, iv, lie_loc, terminal)
        out.append(Secret(id=f"S_{a}", owner=a, kind=kind, protected=protected,
                          stakes=Stakes(legal=1.0 if murder else 0.2, social=0.5),
                          beneficiaries=tuple(s["shared_with"]),
                          cover=CoverStory(layers=layers), evidence_responses=responses))
    return tuple(out)


def _innocent_cover(a: str, loc: str, iv, lie_loc: str, terminal: str):
    """Layer 0 is a counterfactual whereabouts for the protected interval; `E_secret_<a>` places
    them where they really were, so it contradicts the lie outright and is the derived breaker.
    Layer 1 is the terminal that concedes it."""
    lie = Claim(id=f"C_{a}_L0", proposition=At(actor=a, location=lie_loc, interval=iv),
                sincerity="deceptive", source="plan")
    truth = Claim(id=f"C_{a}_L1", proposition=At(actor=a, location=loc, interval=iv),
                  sincerity="truthful", source="plan")
    layers = (CoverLayer(index=0, claims=(lie,), resolve=RESOLVE_L0),
              CoverLayer(index=1, claims=(truth,), concedes=(truth.proposition,),
                         resolve=RESOLVE_TERMINAL, terminal=terminal))
    responses = (EvidenceResponse(evidence=f"E_secret_{a}", layer=0, act="REINTERPRET"),)
    return layers, responses


def _alibi_lie(dr: Draft, case: Case, evidence, a: str, iv) -> Claim | None:
    """NR-I4: the murderer's whereabouts lie for the excursion ("I was in the library"), so a question about where they were
    meets a lie on its own topic (ADR-30) instead of a non-answer. The room is one nothing in the case can contradict - no
    living witness's perception (the victim is never questioned), no item's implication - so it adds no breaker set: layer 0 still breaks on the trace and the
    housekeeper's account alone, exactly as V-3 derived it before. The room they were in just before is preferred; no such
    room, no lie (the cover stays as it was)."""
    skel = dr.skel
    before = [s.loc for s in dr.segments[a] if s.e <= iv[0] and not s.hop]
    rooms = sorted(l for l in skel.role_weights["guest"] if l not in (skel.murder_loc, dr.meta["alibi"][0]))
    rooms = ([before[-1]] if before and before[-1] in rooms else []) + [l for l in rooms if not before or l != before[-1]]
    witnesses = set(case.living_actors()) - {a}
    known = [f.proposition for f in derive_perception(case) if f.observer in witnesses]
    known += [imp.proposition for e in evidence for imp in e.implications]
    for room in rooms:
        lie = At(actor=a, location=room, interval=iv)
        if all(contradiction(p, lie, case=case) is None for p in known):
            return Claim(id=f"C_{a}_L0b", proposition=lie, sincerity="deceptive", source="plan")
    return None


def _murder_cover(dr: Draft, a: str, protected: tuple, terminal: str, n_layers: int, alibi: Claim | None = None):
    """§20.1 item 6 made operational: layer 0 denies ever handling the weapon, and the trace plus
    the housekeeper's account of the cleaning (the statement its `requires` names) is the derived
    breaker set. Layer 1 (standard band) concedes the handling and denies the blow — nothing in
    the case entails the blow directly, so it has no breaker set and the murderer is convicted by
    elimination, never by a confession (I-21)."""
    hk, t_clean, T = dr.meta["hk"], dr.meta["t_clean"], dr.skel.T
    weapon, vloc = dr.skel.weapon.id, dr.skel.murder_loc
    deny_touch = Claim(id=f"C_{a}_L0", proposition=DidNot(actor=a, action="touch", object=weapon, interval=(0, T)),
                       sincerity="deceptive", source="plan")
    concede_touch = Claim(id=f"C_{a}_L1", proposition=Did(actor=a, action="touch", object=weapon, location=vloc,
                                                          interval=(t_clean, T)),
                          sincerity="truthful", source="plan")
    deny_blow = Claim(id=f"C_{a}_L1b", proposition=DidNot(actor=a, action="Attack", object=weapon,
                                                          target_actor=dr.skel.victim[0], interval=(0, T)),
                      sincerity="deceptive", source="plan")
    confess = Claim(id=f"C_{a}_LT", proposition=protected[-1], sincerity="truthful", source="plan")
    responses = (EvidenceResponse(evidence="E_trace", layer=0, act="DENY_EVIDENCE"),
                 EvidenceResponse(evidence=f"clean@{hk}", layer=0, act="DENY_EVIDENCE"))
    first = (deny_touch,) + ((alibi,) if alibi is not None else ())
    if n_layers == 2:
        # I-21 / §19.3 check (i): with two layers, layer 0 IS the pre-terminal layer, and its
        # breaker set (the trace) proves handling, never the blow — so a confession reached from
        # it would be cheaper than a proof. The terminal is a stonewall; this murderer is
        # convicted by elimination or not at all. (A three-layer cover may confess: its
        # pre-terminal layer has no breaker set, so nothing reaches the terminal for free.)
        layers = (CoverLayer(index=0, claims=first, resolve=RESOLVE_L0),
                  CoverLayer(index=1, claims=(concede_touch, confess), concedes=(concede_touch.proposition,
                                                                                 confess.proposition),
                             resolve=RESOLVE_TERMINAL, terminal="stonewall"))
        return layers, responses
    layers = (CoverLayer(index=0, claims=first, resolve=RESOLVE_L0),
              CoverLayer(index=1, claims=(concede_touch, deny_blow), concedes=(concede_touch.proposition,),
                         resolve=RESOLVE_PRE_TERMINAL),
              CoverLayer(index=2, claims=(confess,), concedes=(concede_touch.proposition, confess.proposition),
                         resolve=RESOLVE_TERMINAL, terminal=terminal))
    return layers, responses


def compile_draft(dr: Draft) -> CasePackage:
    skel, M = dr.skel, dr.murderer
    victim, vsex = skel.victim
    role = dr.meta["role"]
    actors = {victim: Actor(id=victim, name=victim, role="victim", static_attrs=FrozenDict({"sex": vsex}))}
    for nm, sex in skel.cast:
        if nm in role:
            actors[nm] = Actor(id=nm, name=nm, role="witness" if role[nm] == "housekeeper" else "suspect",
                               static_attrs=FrozenDict({"sex": sex}))
    rels = tuple(Rel(a=a, b=b, rel_kind=k) for a, b, k in dr.rels)
    case = Case(id=f"{skel.id}_s{dr.seed}", t_investigation=skel.T, actors=actors,
                locations={l.id: l for l in skel.locations}, objects={skel.weapon.id: skel.weapon},
                travel_edges=skel.travel, perception_edges=skel.perception,
                events=tuple(_stay_events(dr)) + tuple(dr.events), rels=rels, motives=tuple(dr.motives))
    evidence = _evidence(dr)
    hk = dr.meta["hk"]
    structure = EliminationStructure(alibi_window=ALIBI_WINDOW, secret_clearance=SECRET_CLEARANCE, opportunity_pin=True)
    alts = tuple(Alternative(candidate=a, reason="alibi", material=(f"E_alibi_{a}",) if a in dr.meta["rh"] else ())
                 for a in sorted(dr.meta["innocents"]))
    alts += (Alternative(candidate="Outsider", reason="containment", material=tuple(f"E_gate_{e}" for e in skel.exterior)),)
    sol = CanonicalSolution(
        murderer=M, victim=victim, method=skel.method.kind, weapon=skel.weapon.id, location=skel.murder_loc,
        interval=(dr.t_m, dr.t_m + 1), murder_event="attack",
        motive_kind=next(m.motive_kind for m in dr.motives if m.actor == M),
        approach=(dr.meta["t_arr"], dr.meta["t_dep"]), opportunity_witness=hk,
        load_bearing=tuple(sorted(e.id for e in evidence if e.load_bearing)),
        critical_constraints=("time_pin:E_watch", "opportunity:E_pin_clean+E_trace",
                              *(f"containment:E_gate_{e}" for e in skel.exterior)),
        alternatives=alts)
    return CasePackage(id=case.id, skeleton_id=skel.id, seed=dr.seed, case=case, evidence=evidence,
                       secrets=_secrets(dr, case, evidence), accounts=_accounts(dr, case), method=skel.method,
                       structure=structure, solution=sol, difficulty=skel.difficulty).sealed()
