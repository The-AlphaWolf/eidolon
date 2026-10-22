"""The ONE resolver for account tokens (ADR-23, I-49).

A `requires` / `StatementHeard` / breaker reference that is not an `EvidenceId` is an ACCOUNT
TOKEN `"<event_id>@<actor_id>"`: "the actor's own account of that event". Before this module the
same string resolved three different ways (the P-9 hull accepted any `event@participant`, the
solver matched the speaker's `Participated` atom, and V-3 matched a pre-authored statement id).
Every consumer — P-9, the solver, V-3, V-4, the runtime unlock, the bots, the proof verifier —
now calls the functions below and nothing else, so a token means the same thing everywhere.

The denotation: the actor's `Participated` knowledge of that event whose proposition is a `Did`.
Nothing else is an account: not a co-presence sighting, not a `Told` entry, not a lie.

Pure and deterministic (I-5, I-6); results are cached per `Case` object (a `Case` is immutable,
I-4). Lives in `minds` because it needs world perception and minds knowledge, and everything that
consumes it sits above `minds` (§23.1).
"""
from __future__ import annotations

from dataclasses import dataclass

from ..world.case import Case
from ..world.interval import Interval
from ..world.perception import PerceptionFact, derive_perception
from .knowledge import KnowledgeEntry, KnowledgeStore
from .provenance import Participated

AccountToken = str


def format_token(event_id: str, actor_id: str) -> AccountToken:
    return f"{event_id}@{actor_id}"


def parse(token: object) -> tuple[str, str] | None:
    """`(event_id, actor_id)`, or None for anything that is not a well-formed token (fail closed,
    I-15). The split is on the LAST `@`, so an event id may itself contain `:`."""
    if not isinstance(token, str) or token.count("@") < 1:
        return None
    event_id, _, actor_id = token.rpartition("@")
    if not event_id or not actor_id or any(c.isspace() for c in token):
        return None
    return event_id, actor_id


def _is_account_fact(pf: PerceptionFact) -> bool:
    return pf.source == "Participated" and pf.proposition.kind == "Did"


def _key(character: str, prop, event_id: str) -> tuple:
    return (character, prop.model_dump_json(), event_id)


@dataclass(frozen=True)
class _Index:
    atoms: dict            # (event_id, actor) -> tuple[perception fact]
    by_atom: dict          # "S:P####" -> PerceptionFact
    entry_to_atom: dict    # KnowledgeEntry.id -> "S:P####"   (only unambiguous identities)
    atom_to_entry: dict    # "S:P####" -> KnowledgeEntry.id


_CACHE: list[tuple[Case, KnowledgeStore, _Index]] = []
_CACHE_SIZE = 8


def _index(case: Case, knowledge: KnowledgeStore) -> _Index:
    for c, k, ix in reversed(_CACHE):
        if c is case and k is knowledge:
            return ix
    pfs = derive_perception(case)
    by_atom = {f"S:{pf.id}": pf for pf in pfs}
    atoms: dict[tuple[str, str], list] = {}
    for pf in pfs:
        if _is_account_fact(pf) and pf.provenance:
            atoms.setdefault((pf.provenance[0], pf.observer), []).append(pf)
    # Explicit identity by (character, proposition, provenance event) — never by position. A key
    # that two perception facts (or two entries) share is AMBIGUOUS and resolves to nothing.
    pf_by_key: dict[tuple, list[str]] = {}
    for aid, pf in by_atom.items():
        ev = pf.provenance[0] if pf.provenance else ""
        pf_by_key.setdefault(_key(pf.observer, pf.proposition, ev), []).append(aid)
    e_by_key: dict[tuple, list[KnowledgeEntry]] = {}
    for e in knowledge.all():
        src = e.source
        ev = getattr(src, "event_id", "") or ""
        e_by_key.setdefault(_key(e.character, e.proposition, ev), []).append(e)
    entry_to_atom, atom_to_entry = {}, {}
    for key, aids in pf_by_key.items():
        es = e_by_key.get(key, [])
        if len(aids) == 1 and len(es) == 1:
            entry_to_atom[es[0].id] = aids[0]
            atom_to_entry[aids[0]] = es[0].id
    ix = _Index({k: tuple(v) for k, v in atoms.items()}, by_atom, entry_to_atom, atom_to_entry)
    _CACHE.append((case, knowledge, ix))
    del _CACHE[:-_CACHE_SIZE]
    return ix


# ------------------------------------------------------------------ the token's denotation
def atoms_of(case: Case, token: object, knowledge: KnowledgeStore | None = None) -> tuple[str, ...]:
    """`"S:P####"` perception ids the token denotes (the solver's testimony-atom ids)."""
    p = parse(token)
    if p is None:
        return ()
    ix = _atoms_only(case)
    return tuple(f"S:{pf.id}" for pf in ix.get(p, ()))


def _atoms_only(case: Case) -> dict:
    """Token -> perception facts, without needing a knowledge store (the solver and P-9 have none)."""
    for c, facts in reversed(_ATOM_CACHE):
        if c is case:
            return facts
    atoms: dict[tuple[str, str], list] = {}
    for pf in derive_perception(case):
        if _is_account_fact(pf) and pf.provenance:
            atoms.setdefault((pf.provenance[0], pf.observer), []).append(pf)
    out = {k: tuple(v) for k, v in atoms.items()}
    _ATOM_CACHE.append((case, out))
    del _ATOM_CACHE[:-_CACHE_SIZE]
    return out


_ATOM_CACHE: list[tuple[Case, dict]] = []


def entries_of(case: Case, knowledge: KnowledgeStore, token: object) -> tuple[KnowledgeEntry, ...]:
    """The actor's `Participated(event_id=e)` knowledge entries whose proposition is a `Did`."""
    p = parse(token)
    if p is None:
        return ()
    event_id, actor = p
    return tuple(e for e in knowledge.for_character(actor)
                 if isinstance(e.source, Participated) and e.source.event_id == event_id
                 and e.proposition.kind == "Did")


def token_interval(case: Case, token: object) -> Interval | None:
    """The P-9 hull input: the event's own interval — and only if the token denotes something."""
    p = parse(token)
    if p is None or not atoms_of(case, token):
        return None
    ev = next((e for e in case.events if e.id == p[0]), None)
    return ev.interval if ev is not None else None


def token_intervals(case: Case) -> dict[str, Interval]:
    """Every token that resolves, with the interval it establishes. Replaces the old
    `lattice.statement_intervals`, which accepted any `event@participant` pair whether or not that
    participant ever acquired a `Did` for the event."""
    by_id = {e.id: e for e in case.events}
    return {format_token(ev, actor): by_id[ev].interval
            for (ev, actor), facts in _atoms_only(case).items() if facts and ev in by_id}


def all_tokens(case: Case) -> tuple[AccountToken, ...]:
    return tuple(sorted(token_intervals(case)))


# ------------------------------------------------------------------ entry <-> atom identity
def atom_of_entry(case: Case, knowledge: KnowledgeStore, entry_id: str) -> str | None:
    return _index(case, knowledge).entry_to_atom.get(entry_id)


def entry_of_atom(case: Case, knowledge: KnowledgeStore, atom_id: str) -> KnowledgeEntry | None:
    eid = _index(case, knowledge).atom_to_entry.get(atom_id)
    return knowledge.get(eid) if eid else None


def fact_of_atom(case: Case, knowledge: KnowledgeStore, atom_id: str) -> PerceptionFact | None:
    """The perception fact behind a testimony atom — its source kind, provenance events, observation segment and
    granularity: everything a credited `Know` needs and a `KnowledgeEntry` drops."""
    return _index(case, knowledge).by_atom.get(atom_id)


def observation_segment(case: Case, knowledge: KnowledgeStore, entry_id: str) -> Interval | None:
    """The observer's presence segment behind an entry (`PerceptionFact.obs_interval`) — the span
    I-54 compares against the speaker's protected intervals."""
    ix = _index(case, knowledge)
    atom = ix.entry_to_atom.get(entry_id)
    return ix.by_atom[atom].obs_interval if atom else None


# ------------------------------------------------------------------ minting (I-50)
def tokens_satisfied(case: Case, knowledge: KnowledgeStore, claim, speaker: str) -> frozenset[AccountToken]:
    """The tokens one COMMITTED claim delivers. Minted only when the claim is a truthful, `actual`,
    plan-sourced claim whose grounding contains the speaker's OWN `Participated` entry AND whose
    proposition equals that entry's proposition. Lies, cover claims, distortions (a shifted
    proposition is not equal), `InvestigationTold` chains, hedged recollections and slips never
    mint — and a claim that resolves to a perception entry of somebody else never does either."""
    if (claim.sincerity != "truthful" or claim.modality != "actual" or claim.source != "plan"
            or claim.confidence != "certain"):
        return frozenset()
    out: set[str] = set()
    for gid in claim.grounding:
        entry = knowledge.get(gid)
        if (entry is not None and entry.character == speaker and isinstance(entry.source, Participated)
                and entry.proposition.kind == "Did" and entry.proposition == claim.proposition):
            out.add(format_token(entry.source.event_id, speaker))
    return frozenset(out)
