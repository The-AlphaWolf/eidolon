"""V-4 (evidence reachability), V-6 (fairness contract, metrics, bands) and the material-level V-7
proxies (§19.4, §19.6, §19.7, §20).

FORMAL solvability (V-5: the constraint problem has exactly one answer) is a different thing from
HUMAN solvability (V-4: a detective can actually get to the proof along a fully-cued path, and
can ask for each proof-core testimony in a way the retrieval model answers `strong`) and from
FAIR gameplay (V-6: no lie without a breaker, no red herring without a refuter, nothing rests on a
suspect's word about their own secret, and the case cannot be solved by bluffing). A case that is
formally unique but fails V-4 or V-6 is REJECTED at its own stage and counted there.
"""
from __future__ import annotations

from ..evidence.contradiction import contradiction, evidence_implication_contradicts
from ..evidence.discovery import reachability, red_herring_refuter_reachable
from ..minds import accounts
from ..minds.belief import form_beliefs
from ..minds.knowledge import propagate_knowledge
from ..minds.memory import encode_memories
from ..decision.turn import run_ask_turn
from ..world.facts import FactIndex
from ..world.interval import overlaps
from ..world.perception import derive_perception
from .queries import expressible_queries, names_from_evidence, opening_names, public_names
from .session import new_session
from .lattice import Know, admissible, testimony_pool
from .package import CasePackage, MemoryBoost
from .solver import Ctx, evaluate

BOOST_BP = 6500          # the FIRST boost level: >= 0.6 (distortion-free, §8.7) and > RETRIEVE_STRONG
BOOST_LADDER = (6500, 8000, 10000)   # §19.4: "raises that memory's strength_0 until [an expressible query reaches strong]"


# ------------------------------------------------------------------ V-4
def named_locations(ctx: Ctx, mat: dict) -> set[str]:
    """§19.4 initial named set: the murder room and every exterior access (I-47), plus every place
    interrogable characters can name — asking everyone everything names it."""
    named = {ctx.murder_loc} | {l for l, x in ctx.case.locations.items() if x.exterior}
    for it in mat.values():
        if isinstance(it, Know):
            named.add(it.obs_loc)
            loc = getattr(it.prop, "location", None) or getattr(it.prop, "from_location", None)
            if loc:
                named.add(loc)
    return named - {None}


def v4_reachability(pkg: CasePackage, ctx: Ctx, mat: dict, core: list[str] | None) -> dict:
    rep = reachability(ctx.store, initial_locations=named_locations(ctx, mat))
    core_ev = sorted(i for i in (core or []) if ctx.store.get(i) is not None)
    declared = sorted(e.id for e in pkg.evidence if e.load_bearing)
    refuters = {e.id: red_herring_refuter_reachable(e, rep) for e in pkg.evidence if e.red_herring}
    bad = []
    bad += [f"proof-core item {i} is not on a fully-cued path" for i in core_ev if i not in rep.cued]
    bad += [f"load-bearing item {i} unreachable" for i in declared if i in rep.unreachable]
    bad += [f"load-bearing item {i} reachable only uncued" for i in declared if i in rep.reachable and i not in rep.cued]
    bad += [f"red herring {i}: refuter not reachable" for i, ok in refuters.items() if ok is not True]
    return {"ok": not bad, "problems": bad, "cued_depth": max((rep.cued_depth.get(i, 0) for i in core_ev), default=0),
            "proof_core_evidence": core_ev, "unreachable": sorted(rep.unreachable), "uncued": sorted(rep.reachable - rep.cued)}


def breakers_reachable(pkg: CasePackage, ctx: Ctx, mat: dict, breakers: dict) -> dict:
    """§20.1 item 2 ("every lie the player is expected to detect has a REACHABLE breaker"), checked
    against Phase 3's own discovery semantics rather than assumed: every evidence item in a derived
    breaker set must lie on a fully-cued path, and every pre-authored statement in one must be
    obtainable — §19.4 counts an account as obtainable by asking, so its speaker must still be
    interrogable at `t_investigation`."""
    rep = reachability(ctx.store, initial_locations=named_locations(ctx, mat))
    living = set(pkg.case.living_actors())
    bad, checked = [], 0
    for (sid, index), sets in sorted(breakers.items()):
        for bset in sets:
            for ref in sorted(bset):
                checked += 1
                if ctx.store.get(ref) is not None:
                    if ref not in rep.cued:
                        bad.append(f"{sid} layer {index}: breaker item {ref} is not on a fully-cued path")
                elif (parsed := accounts.parse(ref)) is not None and ref in pkg.accounts:
                    # §19.4 counts an account as obtainable by ASKING, so its speaker must still be interrogable
                    if parsed[1] not in living:
                        bad.append(f"{sid} layer {index}: breaker account {ref} has no interrogable speaker")
                else:
                    bad.append(f"{sid} layer {index}: breaker ref {ref} is neither evidence nor a declared account")
    return {"ok": not bad, "problems": bad, "checked": checked}


def _delivers(res, targets_atoms: set, tokens: set, state) -> set:
    """Which of the targets this committed turn delivered: the atoms whose entry a committed claim is grounded on
    (explicit identity), and the tokens the statement minted."""
    if res.rejected:
        return set()
    st = res.state.decision.statements.all()[-1]
    got = set(st.accounts) & tokens
    for c in st.claims:
        if c.sincerity != "truthful":
            continue
        for g in c.grounding:
            a = accounts.atom_of_entry(state.case, state.knowledge, g)
            if a in targets_atoms:
                got.add(a)
    return got


def engine_retrieval(pkg: CasePackage, atoms: set, tokens: set, breakers: dict | None = None, names=None) -> dict:
    """I-39 / AC-9 companion, ENGINE-FAITHFUL (ADR-29): every proof-core testimony atom and every breaker account
    token must be DELIVERABLE by the real engine. For each target, some `q` in `queries.expressible_queries` — a real
    `Query` — addressed to its speaker from a fresh `new_session(pkg)` must commit a claim grounded on that atom (or
    mint that token). The memory boosts the package carries are applied by `new_session`, as in play. An atom held
    back by its speaker's own secret (I-45/I-54) is checked from a state in which that secret has been peeled
    through REAL turns. The old check scored a memory against its own cue set: no `Query`, no engine — it certified
    questions the parser cannot produce and answers the strategy never selects (RB-2/C7)."""
    from .bots import peel_secret
    case = pkg.case
    base = new_session(pkg)
    if names is None:
        names = public_names(case)
        for e in pkg.evidence:
            names = names.union(names_from_evidence(case, e))
    pfs = {f"S:{p.id}": p for p in derive_perception(case)}
    speakers = {a: pfs[a].observer for a in atoms if a in pfs}
    speakers.update({t: accounts.parse(t)[1] for t in tokens if accounts.parse(t)})
    secrets = {s.owner: s for s in pkg.secrets}
    peeled: dict = {}
    bad, checked = [], 0
    for target in sorted(speakers):
        who = speakers[target]
        checked += 1
        want_atoms = {target} & atoms
        want_tokens = {target} & tokens
        states = [base]
        pf = pfs.get(target)
        s = secrets.get(who)
        if pf is not None and s is not None and any(overlaps(pf.obs_interval, iv) for iv in s.protected_intervals()):
            if who not in peeled:
                bsets = (breakers or {}).get((s.id, 0))
                if bsets is None:
                    from dataclasses import replace
                    from ..decision.cover_consistency import derive_breaker_sets, deliverable_accounts
                    from .session import decision_context
                    dctx = decision_context(pkg)
                    dctx = replace(dctx, accounts=tuple(sorted(deliverable_accounts(list(pkg.secrets), dctx))))
                    bsets = derive_breaker_sets(s, 0, dctx)
                st, ok, *_ = peel_secret(base, pkg, s, bsets)
                peeled[who] = st if ok else None
            states = [peeled[who]] if peeled[who] is not None else []
        found = False
        for st in states:
            for q in expressible_queries(case, who, names):
                if _delivers(run_ask_turn(st, who, q), want_atoms, want_tokens, st):
                    found = True
                    break
            if found:
                break
        if not found:
            bad.append(f"{target}: no expressible query makes {who} deliver it through the engine (I-39)")
    return {"ok": not bad, "checked": checked, "problems": bad, "boosted": len(pkg.memory_boosts)}


def name_places(pkg: CasePackage, ctx: Ctx, boosts: tuple, atoms: set, tokens: set, level: int = BOOST_LADDER[-1]) -> tuple:
    """§19.4 cueing, engine-faithful (RB study): a place that hosts evidence must be NAMEABLE before it can be searched,
    and the opening material names only the murder room and the exterior accesses (I-47). Suspects hide their own
    secret place, but even a place nobody hides (the alibi room) is never said unless some memory of it is retrievable.
    For each hosting place no cued path names, raise ONE layer-0 `At` testimony atom about it — a holder with no secret
    first, then by id — that the real engine then delivers WITHOUT displacing any earlier target; a place with no such
    atom is left for V-7 to reject. Returns the extended boosts. Deterministic."""
    named = {ctx.murder_loc} | {l for l, x in ctx.case.locations.items() if x.exterior}
    picked: list = []
    secretive = {s.owner for s in pkg.secrets}
    pool = sorted(testimony_pool(ctx.atoms, ctx.protected).values(), key=lambda k: (k.who in secretive, k.id))
    for _ in ctx.case.locations:
        cued = reachability(ctx.store, initial_locations=named).cued
        need = sorted({e.discovery.at for e in pkg.evidence if e.id not in cued and e.discovery.at in ctx.case.locations} - named)
        if not need:
            break
        loc = need[0]
        held = opening_names(ctx.case, ctx.victim, ctx.murder_loc)     # what a player can say BEFORE `loc` is named
        for e in pkg.evidence:
            if e.id in cued:
                held = held.union(names_from_evidence(ctx.case, e))
        named.add(loc)
        # a holder who has already told a cover lie that contradicts the truth will not then say it (I-54(c)): a player
        # can ask in any order, so only an atom no layer-0 claim of its holder contradicts can be relied on to be said
        covers = {s.owner: s.cover.layers[0].claims for s in pkg.secrets}
        free = [k for k in pool if k.prop.kind == "At" and k.prop.location == loc
                and not any(contradiction(k.prop, c.proposition, case=ctx.case) is not None for c in covers.get(k.who, ()))]
        for k in free[:8]:
            more = tuple(MemoryBoost(memory=m, actor=a, strength_bp=level) for m, a in memory_boosts_for(pkg, {k.id}))
            trial = tuple({b.memory: b for b in boosts + more}.values())
            tp = pkg.model_copy(update={"memory_boosts": trial})
            # every earlier pick must still be said with the names IT had (a later, larger name set must not rescue it),
            # and the proof-core atoms and tokens with the full ones
            if (engine_retrieval(tp, atoms, tokens)["ok"]
                    and all(engine_retrieval(tp, {a}, set(), names=h)["ok"] for a, h in [*picked, (k.id, held)])):
                boosts, picked = trial, [*picked, (k.id, held)]
                break
    return boosts


def retrieval_check(pkg: CasePackage, ctx: Ctx, core: list[str] | None, breakers: dict | None = None) -> dict:
    atoms = {c for c in (core or []) if c.startswith("S:")}
    tokens = {t for sets in (breakers or {}).values() for b in sets for t in b if t in pkg.accounts}
    if not atoms and not tokens:
        return {"ok": True, "checked": 0, "problems": [], "boosted": len(pkg.memory_boosts)}
    return engine_retrieval(pkg, atoms, tokens, breakers)


def memory_boosts_for(pkg: CasePackage, atoms) -> list[tuple[str, str]]:
    """(memory id, actor) of every memory grounding one of `atoms` — what generation must raise to satisfy I-39
    (proof-core testimony AND the accounts behind the murderer's breaker, I-50). Pure; the generator turns it into
    `MemoryBoost`s. Identity is explicit (`minds.accounts.atom_of_entry`), never positional."""
    atoms = {a for a in (atoms or ()) if a.startswith("S:")}
    if not atoms:
        return []
    case = pkg.case
    store = propagate_knowledge(case)
    idx = FactIndex(case)
    out = []
    for actor in sorted(case.living_actors()):
        beliefs = form_beliefs(actor, store, case, idx).beliefs
        bmap = {b.id: b for b in beliefs}
        for m in encode_memories(actor, list(beliefs), store, case):
            if any(accounts.atom_of_entry(case, store, g) in atoms for bid in m.content for g in bmap[bid].grounds):
                out.append((m.id, actor))
    return out


# ------------------------------------------------------------------ V-6
def fragility(verdict) -> dict:
    """§19.5 absence-fragility report: for every elimination, does it rest on `NotAt` material and
    on how many distinct sources? Reported, banded by V-6, never rejected on its own."""
    out = {}
    for X, e in sorted(verdict.candidates.items()):
        if not e["excluded"]:
            continue
        core = e.get("core") or []
        notat = [c for c in core if c.get("kind") == "NotAt"]
        sources = {s for c in notat for s in c.get("sources", [])}
        out[X] = {"rests_on_absence": bool(notat), "absence_sources": len(sources),
                  "levels": sorted({c.get("level") for c in core if "level" in c})}
    return out


def bluff_converges(ctx: Ctx, fairness: int = 2) -> bool:
    """I-40, MATERIAL-level proxy (NOT a V-6/V-7 gate any more — the engine-driven bluff bot of V-7 is the real
    measurement): a detective who presents NOTHING holds no admissible material; does the solver still converge? It must
    not. Kept as a pure solver property the tests pin."""
    return evaluate(ctx, {}, fairness, want_cores=False).unique


def contract(pkg: CasePackage, ctx: Ctx, mat: dict, cons, core, verdict, v4: dict, retr: dict, robust: dict) -> dict:
    """§20.1 items that are checkable on the sealed package. Each entry: (passed, detail)."""
    fair = verdict.fairness
    hard = [c for c in cons if c.level >= fair]
    case, out = pkg.case, {}
    # 1/5: the proof rests on no suspect's word about their own secret
    bad = []
    for c in cons:
        if c.item in mat and isinstance(mat[c.item], Know) and c.level >= fair and c.item in (core or []):
            k = mat[c.item]
            if any(overlaps(k.obs_iv, iv) for iv in ctx.protected.get(k.who, ())) and k.who in verdict.survivors:
                bad.append(f"{c.item}: the survivor's own word about their protected interval")
    out["1_proof_core_fair"] = (not bad, bad)
    # 2/6: every secret's layer-0 lie has a reachable breaker at the fairness level
    idx = FactIndex(case)
    breaks, lvl_of = [], {}
    for c in hard:
        lvl_of.setdefault(c.item, c.level)
    for s in pkg.secrets:
        l0 = s.cover.layers[0]
        broken = False
        for claim in l0.claims:
            for ev in pkg.evidence:
                if ev.id not in lvl_of or not ev.authentic:
                    continue
                for imp in ev.implications:
                    if evidence_implication_contradicts(imp, claim.proposition, imp_id=ev.id, other_id=claim.id, case=case):
                        broken = True
        if not broken:
            breaks.append(f"{s.id}: layer-0 lie has no admissible refuting evidence")
    out["2_lies_breakable"] = (not breaks, breaks)
    # 3: red herrings have refuters that actually contradict what they mislead toward, and mislead
    rh_bad = []
    for ev in pkg.evidence:
        if ev.red_herring is None:
            continue
        ref = ctx.store.get(ev.red_herring.refuter)
        if ref is None:
            rh_bad.append(f"{ev.id}: refuter {ev.red_herring.refuter} is not in the evidence table")
    # §19.6 first half: the red herring must actually MISLEAD — its target is still a live suspect on the
    # physical material alone once the refuter is withheld (else it misleads no one)
    for ev in pkg.evidence:
        if ev.red_herring is None:
            continue
        target = next((a for a in ctx.case.living_actors() if ev.id == f"E_secret_{a}"), None)
        if target is None:
            continue
        physical = {e.id: e for e in pkg.evidence if e.id != ev.red_herring.refuter}
        if target not in evaluate(ctx, physical, fair, want_cores=False).survivors:
            rh_bad.append(f"{ev.id}: {target} is already excluded without the refuter, so it misleads no one")
    out["3_red_herrings_refutable"] = (not rh_bad, rh_bad)
    out["4_distortions_correctable"] = (robust.get("ok", False), robust.get("failures", []))
    out["8_cued_path"] = (v4["ok"], v4["problems"])
    out["10_proof_testimony_askable"] = (retr["ok"], retr["problems"])
    return out


# ------------------------------------------------------------------ V-6 metrics and bands
BANDS = {   # §20.2: knob -> {band: (lo, hi)}
    "suspects": {"easy": (4, 4), "standard": (5, 6), "hard": (7, 8)},
    "red_herrings": {"easy": (1, 1), "standard": (2, 2), "hard": (3, 3)},
    "proof_core": {"easy": (3, 4), "standard": (5, 6), "hard": (7, 9)},
    "min_depth": {"easy": (0, 2), "standard": (3, 3), "hard": (4, 5)},
}


def band_of(knob: str, value: int) -> str | None:
    for band, (lo, hi) in BANDS[knob].items():
        if lo <= value <= hi:
            return band
    return None


def band_violations(difficulty: str, m: dict) -> list[str]:
    """§20.2's table read as a GATE, not a report (B-3). Every measured knob must land in the
    band the case declares; "in band" is the Phase 6 exit criterion's own word, so a knob that
    sits in no band at all, or in a neighbouring one, is a rejection with the number in it."""
    out = []
    for knob in sorted(BANDS):
        got = m["bands"].get(knob)
        if got != difficulty:
            lo, hi = BANDS[knob][difficulty]
            out.append(f"{knob}={m[knob]} is {got or 'in no band'}, not {difficulty} ({lo}-{hi})")
    return out


def metrics(pkg: CasePackage, ctx: Ctx, core, v4: dict, robust: dict, frag: dict) -> dict:
    core = core or []
    per_w: dict[str, int] = {}
    for s in pkg.distortions:
        per_w[s.actor] = per_w.get(s.actor, 0) + 1
    m = {"suspects": len(ctx.case.living_actors()),
         "red_herrings": sum(1 for e in pkg.evidence if e.red_herring),
         "proof_core": len(core), "min_depth": v4["cued_depth"],
         "cover_layers": max((len(s.cover.layers) for s in pkg.secrets), default=0),
         "distortions_per_witness_max": max(per_w.values(), default=0),
         "conditional_implications": sum(1 for e in pkg.evidence for i in e.implications if i.requires),
         "eliminations_on_absence": sum(1 for f in frag.values() if f["rests_on_absence"]),
         "eliminations": len(frag)}
    m["bands"] = {k: band_of(k, m[k]) for k in BANDS}
    return m
