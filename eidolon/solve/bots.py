"""V-7 — the scripted detective bots (§19.7), run against the REAL engine.

Every bot here drives `decision.turn`'s pipeline with `TemplateLLM` (§28.2: "no model calls"):
a real `Query`, a real strategy choice, a real envelope audit, a real validator, real committed
statements and real `LayerPeel` events. None of them is a wrapper around `solve()` — the solver
appears only where §19.7 puts it, as the thing a bot runs *on the material it actually acquired*.

**Acquisition model.** A bot holds exactly what it has obtained: evidence it discovered through
Phase 3's `DiscoverySpec`/prerequisite machinery, and testimony atoms it got by asking a
character about something. Asking `X` about entity `e` yields `X`'s own perception atoms that
mention `e` — and only those a suspect would actually part with, because the candidate pool is
the layer-0 fixpoint's material (`robust_material`), so nothing inside a secret-holder's
protected interval can be acquired by asking (§19.5, I-45).

**Determinism (I-5/I-6).** `random` is banned outside `gen/`, and these bots are not generation,
so every "random" choice here is `sha256(seed|key)` — reproducible across processes and hash
seeds, with no RNG state to carry.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from dataclasses import replace

from ..decision.events import LayerPeel as LayerPeelEvent
from ..decision.query import EntityRef, Query
from ..decision.turn import GameState, run_ask_turn, run_goto_turn, run_search_turn
from ..evidence.discovery import can_discover
from ..minds import accounts
from .lattice import Know
from .package import CasePackage
from .queries import (
    Names, expressible_queries, names_from_evidence, names_of_proposition, opening_names, public_names,
)
from .session import decision_context, new_session
from .solver import Ctx, build_ctx, evaluate

N_MAX = 400          # §19.7 greedy bot: actions allowed to reach a solution
N_CUE = 400          # §19.7 cue-following bot: the "a human would plausibly get there" budget.
                     # Measured: the cued closure is exhausted in 148 actions on study_party and 267
                     # on manor_wing, so the budget is a ceiling the bot finishes under, not a cut-off.
N_BLUFF = 500        # §19.7 bluff bot / T-12: "500 templated bluffs ... per character"
N_ADVERSARIAL = 500  # §19.7 adversarial bot: "500 templated odd questions per character"
ENVELOPE_CEILING = 4096  # I-7: the per-turn envelope is O(1), not O(turns) — measured max ~470

# Acts that would tell a bluffing detective something. A bot that can pick the murderer out of
# these has solved the case without evidence, which I-40 forbids.
TELLS = frozenset({"SLIP", "CONCESSION", "CONFESSION", "STONEWALL", "ANGER", "REFUSE",
                   "DEFLECT", "EVASION", "ACCUSE_DETECTIVE"})


def _h(*parts) -> int:
    return int(hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:12], 16)


def pick(seed, key, options: list):
    """Deterministic uniform choice — `random` is not available to this layer (I-6)."""
    return options[_h(seed, key) % len(options)] if options else None


# ------------------------------------------------------------------ what a bot is CREDITED with (I-52)
def credited_material(state: GameState, only: frozenset[str] | None = None) -> dict:
    """`only` (Phase 8, the accusation's evidence axis): restrict to the evidence ids and statement ids a player CITED —
    the same crediting rule over a subset of what they hold, never more.

    A bot's material is what the ENGINE committed, and only that: the evidence it discovered
    (`state.discovery.known_evidence`) plus the testimony atoms of COMMITTED, standing ledger claims whose
    grounding resolves — by explicit identity (`minds.accounts.atom_of_entry`), not position — to a perception
    entry OF THAT SPEAKER. The proposition credited is the one actually SAID, so an uncorrected distortion is
    credited as said, which is exactly V-5's robustness model. A rejected turn committed nothing and credits
    nothing; a lie (no grounding) credits nothing; a claim resolving to somebody else's perception credits nothing.

    Nothing here reads the solver's pool, a fixpoint, or a memory: derive testimony from the solver because the
    solver knows it and the bot is a wrapper around `solve()` — the defect the audit found (RB-2, attack 42)."""
    mat: dict = {i: state.evidence.get(i) for i in state.discovery.known_evidence
                 if state.evidence.get(i) is not None and (only is None or i in only)}
    for st in state.decision.statements.all():
        if only is not None and st.id not in only:
            continue
        if st.retracted_by is not None:
            continue
        for c in st.claims:
            if c.modality != "actual":
                continue
            for gid in c.grounding:
                entry = state.knowledge.get(gid)
                if entry is None or entry.character != st.speaker:
                    continue
                atom = accounts.atom_of_entry(state.case, state.knowledge, gid)
                pf = accounts.fact_of_atom(state.case, state.knowledge, atom) if atom else None
                if pf is None or pf.observer != st.speaker:
                    continue
                mat[atom] = Know(atom, st.speaker, c.proposition, pf.source, pf.provenance, pf.obs_location,
                                 pf.obs_interval, pf.granularity)
                break
    return mat


def solve_on(ctx: Ctx, state: GameState):
    """§19.7/T-20: run the solver on the bot's OWN credited material, never on the sealed case."""
    return evaluate(ctx, credited_material(state), want_cores=False)


def held_names(state: GameState, base: Names) -> Names:
    """What the bot may NAME: `base` plus whatever its held material introduces — every discovered item's
    objects, places and times, every committed claim's entities and times."""
    n = base
    for eid in state.discovery.known_evidence:
        ev = state.evidence.get(eid)
        if ev is not None:
            n = n.union(names_from_evidence(state.case, ev))
    for st in state.decision.statements.all():
        for c in st.claims:
            n = n.union(names_of_proposition(state.case, c.proposition))
    return n


# ------------------------------------------------------------------ templated questions
def template_queries(case, subject: str | None = None) -> list[Query]:
    """The template question set a scripted bot can ask — one per `QueryKind` the parser can
    express, over the case's own locations and cast (§19.7 greedy: "asks each character each
    template question")."""
    out = [Query(kind="where", predicate_hint="whereabouts", raw="Where were you?"),
           Query(kind="when", predicate_hint="timing", raw="When was that?"),
           Query(kind="what", predicate_hint="events", raw="What happened?"),
           Query(kind="why", predicate_hint="motive", raw="Why?"),
           Query(kind="opinion", predicate_hint="opinion", raw="What did you make of him?")]
    for loc in sorted(case.locations):
        out.append(Query(kind="did_you", predicate_hint="presence", location=loc,
                         raw=f"Were you in {loc}?"))
    for other in sorted(case.actors):
        ref = EntityRef(id=other, kind="actor")
        out.append(Query(kind="did_they", subject=ref, predicate_hint="presence",
                         raw=f"Did you see {other}?"))
    if subject:
        out.append(Query(kind="who", subject=EntityRef(id=subject, kind="actor"),
                         predicate_hint="presence", raw=f"Who was with {subject}?"))
    return out


def odd_queries(case, n: int) -> list[Query]:
    """§19.7 adversarial bot: templated ODD questions — hypotheticals, opinions, smalltalk,
    meta and coercion attempts. None of them carries evidence, so none may move a cover."""
    kinds = ["hypothetical", "opinion", "smalltalk", "narrative", "recall_detail", "meta", "coercion"]
    locs = sorted(case.locations)
    out = []
    for i in range(n):
        kind = kinds[i % len(kinds)]
        out.append(Query(kind=kind, predicate_hint=f"odd{i % 17}", location=locs[i % len(locs)],
                         raw=f"[{kind}] question {i}"))
    return out


def bluff_pairs(pkg: CasePackage, target: str, pairs: int) -> list[tuple[Query, Query]]:
    """§19.7 bluff bot: loaded premises drawn from the case's protected facts and physical
    details, put as presuppositions (§12.2/I-25 — an implicit `Present` carrying ZERO evidential
    weight). They come in MATCHED PAIRS: two questions identical in kind, subject, location and
    time, differing only in whether the premise is TRUE of the target. That is exactly the shape
    §6.5's response parity is stated in — "all else equal, does the truth of the premise change
    the answer?" — and it is the only comparison that isolates the premise from the question."""
    true_props = [p for s in pkg.secrets if s.owner == target for p in s.protected]
    false_props = [p for s in pkg.secrets if s.owner != target for p in s.protected]
    false_props += [imp.proposition for e in pkg.evidence for imp in e.implications
                    if getattr(imp.proposition, "actor", None) not in (None, target)]
    if not true_props or not false_props:
        return []
    kinds = ["did_you", "where", "when", "who", "what", "recall_detail", "challenge", "narrative"]
    locs, people = sorted(pkg.case.locations), sorted(pkg.case.actors)
    out: list[tuple[Query, Query]] = []
    for i in range(pairs):
        kind = kinds[i % len(kinds)]
        loc = locs[_h(pkg.seed, target, "loc", i) % len(locs)]
        who = people[_h(pkg.seed, target, "who", i) % len(people)]
        shape = dict(kind=kind, predicate_hint=f"bluff{i % 23}", location=loc,
                     subject=EntityRef(id=who, kind="actor"),
                     raw=f"We already know. {i}")
        t = true_props[_h(pkg.seed, target, "t", i) % len(true_props)]
        f = false_props[_h(pkg.seed, target, "f", i) % len(false_props)]
        out.append((Query(presupposes=(t,), **shape), Query(presupposes=(f,), **shape)))
    return out


# ------------------------------------------------------------------ bot reports
@dataclass
class BotReport:
    name: str
    actions: int
    solved: bool
    survivors: list = field(default_factory=list)
    peels: int = 0
    rejected: int = 0
    acts: dict = field(default_factory=dict)
    detail: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return bool(self.detail.get("ok", True))

    def to_json(self) -> dict:
        return {"bot": self.name, "actions": self.actions, "solved": self.solved,
                "survivors": self.survivors, "peels": self.peels, "rejected": self.rejected,
                "acts": dict(sorted(self.acts.items())), **self.detail}


def _count(acts: dict, act: str) -> None:
    acts[act] = acts.get(act, 0) + 1


def _ask(state: GameState, who: str, query: Query, presented=None):
    """One real turn. Returns (state, act, peels, rejected)."""
    res = run_ask_turn(state, who, query, presented_ref=presented)
    peels = sum(1 for e in res.events if isinstance(e, LayerPeelEvent))
    if res.rejected:
        return state, f"REJECTED:{res.violations[0] if res.violations else '?'}", 0, True
    return res.state, res.plan_act, peels, False


def _discover_all(state: GameState) -> tuple[GameState, int, set]:
    """Search everything, in prerequisite order, until nothing new opens up."""
    found, actions = set(), 0
    while True:
        progress = False
        for ev in sorted(state.evidence.all(), key=lambda e: e.id):
            if ev.id in found or not can_discover(ev, state.discovery):
                continue
            out = run_search_turn(state, ev.discovery.at, ev.discovery.action)
            state, actions = out.state, actions + 1
            if out.discovered:
                found.add(out.discovered)
                progress = True
        if not progress:
            return state, actions, found


# ------------------------------------------------------------------ the bots
def adversarial_bot(pkg: CasePackage, *, per_character: int = N_ADVERSARIAL) -> BotReport:
    """§19.7: "asks 500 templated odd questions per character before presenting any evidence;
    asserts zero `LayerPeel`, zero leaks, bounded tokens (I-3, I-7)"."""
    state = new_session(pkg)
    acts: dict = {}
    peels = rejected = 0
    sizes: list[int] = []
    leaked: list[str] = []
    for who in sorted(pkg.case.living_actors()):
        protected = {p for s in pkg.secrets if s.owner == who for p in s.protected}
        for q in odd_queries(pkg.case, per_character):
            res = run_ask_turn(state, who, q)
            peels += sum(1 for e in res.events if isinstance(e, LayerPeelEvent))
            if res.rejected:
                rejected += 1
                _count(acts, "REJECTED")
                continue
            state = res.state
            _count(acts, res.plan_act)
            if res.envelope is not None:
                sizes.append(len(str(res.envelope)))
            for st in state.decision.statements.for_speaker(who)[-1:]:
                for c in st.claims:
                    if c.proposition in protected:
                        leaked.append(f"{who}: {c.id}")
    # I-7/§15.1: context is O(1) in turn count. Measured, the envelope grows once as the digest
    # fills and then SATURATES (~305 -> ~470 chars and flat from there), so the in-run check is a
    # constant ceiling — the property "O(1)" literally states. The sharp form (the ceiling does
    # not move when the run gets longer) is the cross-scale test in `test_blocker_repairs.py`.
    bounded = max(sizes, default=0) <= ENVELOPE_CEILING
    return BotReport("adversarial", per_character * len(pkg.case.living_actors()), False, [], peels,
                     rejected, acts,
                     {"ok": peels == 0 and not leaked and bounded, "leaks": leaked,
                      "max_envelope_chars": max(sizes, default=0), "envelope_bounded": bounded})


def _ask_batch(state, who, queries, asked, acts, budget):
    """Ask `who` every not-yet-asked query (up to `budget` actions). Returns (state, actions, peels, rejected)."""
    n = peels = rejected = 0
    for q in queries:
        key = (who, q.model_dump_json())
        if key in asked or n >= budget:
            continue
        asked.add(key)
        state, act, p, rej = _ask(state, who, q)
        n, peels, rejected = n + 1, peels + p, rejected + int(rej)
        _count(acts, act)
    return state, n, peels, rejected


def _footprint_of(state: GameState) -> tuple:
    """What a bot holds, as a comparable value: progress means this changed."""
    return (len(credited_material(state)), len(state.discovery.known_accounts), len(state.discovery.known_evidence))


def greedy_bot(pkg: CasePackage, *, n_max: int = N_MAX) -> BotReport:
    """§19.7: "searches everything, asks each character each template question, presents every
    contradiction. Must solve within `N_max` actions". The questions are `queries.expressible_queries` over the
    cast, the places of the house and every name/time the bot's own HELD material introduces; what it learns is
    what the engine commits (`credited_material`), and the solver runs on that and nothing else."""
    state, ctx = new_session(pkg), build_ctx(pkg)
    people = sorted(pkg.case.living_actors())
    acts: dict = {}
    asked: set = set()
    presented: set = set()
    state, actions, _found = _discover_all(state)
    peels = rejected = 0
    base = public_names(pkg.case)
    v = solve_on(ctx, state)
    while actions < n_max and not v.unique:
        before = _footprint_of(state)
        names = held_names(state, base)
        for who in people:
            state, n, p, rej = _ask_batch(state, who, expressible_queries(pkg.case, who, names), asked, acts, n_max - actions)
            actions, peels, rejected = actions + n, peels + p, rejected + rej
            v = solve_on(ctx, state)               # "must solve within N_max": the first moment the bot's own material is unique
            if v.unique or actions >= n_max:
                break
        for who in people:
            for ref in sorted(state.discovery.known_evidence):
                if v.unique or actions >= n_max or (who, ref) in presented:
                    continue
                presented.add((who, ref))
                state, act, p, rej = _ask(state, who, Query(kind="challenge", raw=f"present {ref}"), presented=ref)
                actions, peels, rejected = actions + 1, peels + p, rejected + int(rej)
                _count(acts, act)
        if actions < n_max and not v.unique:
            state, n, _found = _discover_all(state)
            actions += n
        v = solve_on(ctx, state)
        if _footprint_of(state) == before:
            break
    held = credited_material(state)
    return BotReport("greedy", actions, v.unique, v.survivors, peels, rejected, acts,
                     {"ok": v.unique and actions <= n_max, "n_max": n_max,
                      "evidence": len(state.discovery.known_evidence),
                      "atoms": sum(1 for k in held if k.startswith("S:")), "accounts": len(state.discovery.known_accounts)})


def cue_following_bot(pkg: CasePackage, *, n_cue: int = N_CUE) -> BotReport:
    """§19.7/T-20: "never enumerates; only performs actions cued by material it already holds.
    Must solve within `N_cue`." The bot's initial named set is §19.4's — the body, the murder room, every exterior
    access, everyone interrogable — and a name (a place, an object, a half-hour) enters only when held material
    introduces it. It runs the solver on what the ENGINE committed for it."""
    state, ctx = new_session(pkg), build_ctx(pkg)
    people = sorted(pkg.case.living_actors())
    base = opening_names(pkg.case, ctx.victim, ctx.murder_loc)
    acts: dict = {}
    asked: set = set()
    actions = peels = rejected = 0
    progress = True
    v = solve_on(ctx, state)
    while progress and actions < n_cue and not v.unique:
        before = _footprint_of(state)
        names = held_names(state, base)
        named = set(names.actors) | set(names.locations) | set(names.objects)
        for ev in sorted(state.evidence.all(), key=lambda e: e.id):
            if ev.id in state.discovery.known_evidence or not can_discover(ev, state.discovery):
                continue
            if (ev.discovery.cue or ev.discovery.at) not in named:     # uncued: a cue-follower never tries it
                continue
            out = run_search_turn(state, ev.discovery.at, ev.discovery.action)
            state, actions = out.state, actions + 1
        names = held_names(state, base)
        for who in people:
            state, n, p, rej = _ask_batch(state, who, expressible_queries(pkg.case, who, names), asked, acts, n_cue - actions)
            actions, peels, rejected = actions + n, peels + p, rejected + rej
            v = solve_on(ctx, state)
            if v.unique or actions >= n_cue:
                break
        progress = _footprint_of(state) != before
    held = credited_material(state)
    return BotReport("cue_following", actions, v.unique, v.survivors, peels, rejected, acts,
                     {"ok": v.unique and actions <= n_cue, "n_cue": n_cue,
                      "named": len(names.actors | names.locations | names.objects),
                      "evidence": len(state.discovery.known_evidence),
                      "atoms": sum(1 for k in held if k.startswith("S:")), "accounts": len(state.discovery.known_accounts)})


def peel_secret(state: GameState, pkg: CasePackage, secret, bsets, *, n_max: int = N_MAX):
    """Break `secret`'s layer 0 THROUGH REAL TURNS: for a derived breaker set, discover the evidence by searching,
    obtain each account token by ASKING its speaker (the token enters `known_accounts` only when the engine commits a
    faithful delivery, I-50), then present the evidence to the owner. Returns
    `(state, peeled, actions, peels, rejected, acts, tried)`. Nothing is seeded and nothing is credited from the
    solver; a bare token cannot be presented (I-51)."""
    acts: dict = {}
    asked: set = set()
    actions = peels = rejected = 0
    tried: list = []
    peeled = False
    for bset in sorted(bsets, key=lambda b: (len(b), sorted(b))):
        tried.append(sorted(bset))
        state, n, _found = _discover_all(state)
        actions += n
        for token in sorted(r for r in bset if r in pkg.accounts):
            speaker = accounts.parse(token)[1]
            for _round in range(3):
                if token in state.discovery.known_accounts or actions >= n_max:
                    break
                names = held_names(state, public_names(pkg.case))
                state, n, p, rej = _ask_batch(state, speaker, expressible_queries(pkg.case, speaker, names), asked,
                                              acts, n_max - actions)
                actions, peels, rejected = actions + n, peels + p, rejected + rej
        for ref in sorted(r for r in bset if state.evidence.get(r) is not None):
            if actions >= n_max:
                break
            state, act, p, rej = _ask(state, secret.owner, Query(kind="challenge", raw=f"present {ref}"), presented=ref)
            actions, peels, rejected = actions + 1, peels + p, rejected + int(rej)
            _count(acts, act)
        peeled = any(e.character == secret.owner and e.secret_id == secret.id and e.from_index == 0 and e.to_index >= 1
                     for e in state.decision.layer_peels)
        if peeled:
            break
    return state, peeled, actions, peels, rejected, acts, tried


def murderer_peel_bot(pkg: CasePackage, *, n_max: int = N_MAX) -> BotReport:
    """RB-1's acceptance as a V-7 bot (I-53): the murderer's layer 0 must be broken THROUGH LEGITIMATE PLAY, for a
    derived murder-layer-0 breaker set, and the bot must record `LayerPeel(0 -> 1)`."""
    from ..decision.cover_consistency import derive_breaker_sets, deliverable_accounts
    dctx = decision_context(pkg)
    dctx = replace(dctx, accounts=tuple(sorted(deliverable_accounts(list(pkg.secrets), dctx))))
    murder = next((s for s in pkg.secrets if s.kind == "murder"), None)
    if murder is None:
        return BotReport("murderer_peel", 0, False, [], 0, 0, {}, {"ok": False, "why": "no murder secret"})
    state, peeled, actions, peels, rejected, acts, tried = peel_secret(
        new_session(pkg), pkg, murder, derive_breaker_sets(murder, 0, dctx), n_max=n_max)
    return BotReport("murderer_peel", actions, peeled, [], peels, rejected, acts,
                     {"ok": peeled, "breaker_sets_tried": tried, "owner": murder.owner,
                      "accounts_heard": sorted(state.discovery.known_accounts),
                      "evidence": len(state.discovery.known_evidence)})


def random_bot(pkg: CasePackage, *, actions: int = 150, seed: int = 0, core=None) -> BotReport:
    """§19.7: "uniformly random valid actions; measures how often the proof core is stumbled
    upon (should be low but nonzero)". Choices are hash-derived, so the run is reproducible; what it learns is
    what the engine committed."""
    state, ctx = new_session(pkg, seed=seed), build_ctx(pkg)
    acts: dict = {}
    people = sorted(pkg.case.living_actors())
    queries = template_queries(pkg.case)
    peels = rejected = 0
    for i in range(actions):
        kind = ["ask", "search", "goto", "present"][_h(seed, "k", i) % 4]
        if kind == "search":
            ev = pick(seed, f"s{i}", sorted(state.evidence.all(), key=lambda e: e.id))
            state = run_search_turn(state, ev.discovery.at, ev.discovery.action).state
        elif kind == "goto":
            state = run_goto_turn(state, pick(seed, f"g{i}", sorted(pkg.case.locations))).state
        elif kind == "present" and state.discovery.known_evidence:
            who, ref = pick(seed, f"p{i}", people), pick(seed, f"r{i}", sorted(state.discovery.known_evidence))
            state, act, p, rej = _ask(state, who, Query(kind="challenge", raw="present"), presented=ref)
            peels, rejected = peels + p, rejected + int(rej)
            _count(acts, act)
        else:
            who, q = pick(seed, f"w{i}", people), pick(seed, f"q{i}", queries)
            state, act, p, rej = _ask(state, who, q)
            peels, rejected = peels + p, rejected + int(rej)
            _count(acts, act)
    v = solve_on(ctx, state)
    held = credited_material(state)
    stumbled = sorted(set(core or ()) & set(held))
    return BotReport("random", actions, v.unique, v.survivors, peels, rejected, acts,
                     {"ok": True, "core_size": len(core or ()), "stumbled_core": stumbled,
                      "evidence": len(state.discovery.known_evidence),
                      "atoms": sum(1 for k in held if k.startswith("S:"))})


def order_shuffled_bot(pkg: CasePackage, *, orders: int = 3) -> BotReport:
    """§19.7: "discovers evidence in random orders; asserts solver-equivalent end state". The end state is what the
    engine let the bot discover; the solver's verdict on it must not depend on the order."""
    ctx = build_ctx(pkg)
    verdicts = []
    for o in range(orders):
        state = new_session(pkg, seed=o)
        items = sorted(state.evidence.all(), key=lambda e: _h(o, "order", e.id))
        for _ in range(len(items)):
            for ev in items:
                if ev.id not in state.discovery.known_evidence and can_discover(ev, state.discovery):
                    state = run_search_turn(state, ev.discovery.at, ev.discovery.action).state
        v = solve_on(ctx, state)
        verdicts.append((tuple(v.survivors), v.unique, tuple(v.time_bins), v.outsider["excluded"],
                         tuple(sorted(state.discovery.known_evidence))))
    same = len(set(verdicts)) == 1
    return BotReport("order_shuffled", orders, verdicts[0][1], list(verdicts[0][0]), 0, 0, {},
                     {"ok": same, "verdicts": [list(map(list, (v[0], v[2]))) + [v[1], v[3]] for v in verdicts]})


def bluff_bot(pkg: CasePackage, *, per_character: int = N_BLUFF) -> BotReport:
    """§19.7/T-12/I-40: "presents NOTHING. Issues 500 templated bluffs and loaded premises per
    character, drawn from the case's protected facts and physical details, and records each
    character's response class. **Must fail** — the murderer must be identified no better than
    chance. A converging bluff bot fails the case, not the bot."

    Two measurements, both on the real engine:
      * **convergence** — is the murderer the unique argmax of "tells" (§6.5's guilty-looking
        acts)? If yes, the case is solvable by bluffing and V-7 rejects it.
      * **parity** — for each character, does the response-class distribution differ between
        bluffs whose premise is TRUE of them and bluffs whose premise is false? §6.5 requires
        it not to; a difference is a hidden-state leak through behaviour (§22.3).
    """
    state = new_session(pkg)
    by_char: dict[str, dict] = {}
    parity_breaks: list[str] = []
    peels = rejected = 0
    leaked: list[str] = []
    turns = 0
    for who in sorted(pkg.case.living_actors()):
        protected = {p for s in pkg.secrets if s.owner == who for p in s.protected}
        acts: dict = {}
        for q_true, q_false in bluff_pairs(pkg, who, max(1, per_character // 2)):
            # Both halves of a pair run from the SAME state, so the only difference between
            # them is the premise's truth — state drift cannot masquerade as a leak.
            outcomes = []
            for q in (q_true, q_false):
                res = run_ask_turn(state, who, q)  # presents NOTHING: presented_ref stays None
                turns += 1
                peels += sum(1 for e in res.events if isinstance(e, LayerPeelEvent))
                if res.rejected:
                    rejected += 1
                    outcomes.append((f"REJECTED:{res.violations[0] if res.violations else '?'}", res))
                else:
                    outcomes.append((res.plan_act, res))
            if outcomes[0][0] != outcomes[1][0]:
                parity_breaks.append(f"{who}: true-premise {outcomes[0][0]} vs false-premise {outcomes[1][0]}")
            for act, _ in outcomes:
                _count(acts, act)
            keep = outcomes[turns % 2][1]          # commit one of the two, alternating
            if not keep.rejected:
                state = keep.state
                for st in state.decision.statements.for_speaker(who)[-1:]:
                    for c in st.claims:
                        if c.proposition in protected:
                            leaked.append(f"{who}: {c.id}")
        by_char[who] = acts
    tells = {w: sum(n for a, n in acts.items() if a in TELLS) for w, acts in by_char.items()}
    best = max(tells.values(), default=0)
    argmax = sorted(w for w, n in tells.items() if n == best)
    converged = argmax == [pkg.solution.murderer] and best > 0
    return BotReport("bluff", turns, converged, [], peels, rejected,
                     {w: dict(sorted(a.items())) for w, a in by_char.items()},
                     {"ok": not converged and peels == 0 and not leaked and not parity_breaks,
                      "converged": converged, "tells": tells, "argmax": argmax,
                      "parity_ok": not parity_breaks, "parity_breaks": parity_breaks[:5],
                      "leaks": leaked, "per_character": per_character})


ALL_BOTS = ("greedy", "cue_following", "murderer_peel", "bluff", "adversarial", "random", "order_shuffled")


def run_bots(pkg: CasePackage, *, names=ALL_BOTS, bluffs: int = N_BLUFF,
             odd: int = N_ADVERSARIAL) -> dict:
    """Every V-7 bot over one sealed package. Scale knobs exist so CI can run a reduced sweep
    (the Phase 4 long-conversation test's own convention); the architecture's numbers are the
    defaults and the repair report runs them."""
    out: dict = {}
    for name in names:
        if name == "greedy":
            out[name] = greedy_bot(pkg)
        elif name == "random":
            out[name] = random_bot(pkg)
        elif name == "adversarial":
            out[name] = adversarial_bot(pkg, per_character=odd)
        elif name == "order_shuffled":
            out[name] = order_shuffled_bot(pkg)
        elif name == "cue_following":
            out[name] = cue_following_bot(pkg)
        elif name == "murderer_peel":
            out[name] = murderer_peel_bot(pkg)
        elif name == "bluff":
            out[name] = bluff_bot(pkg, per_character=bluffs)
    return out
