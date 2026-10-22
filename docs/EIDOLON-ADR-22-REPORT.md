# ADR-22 — `ActionKind` schema change: API, compatibility and test report

**ADR:** `docs/EIDOLON-ARCHITECTURE.md` Part XII, **ADR-22** (inline, matching the house style
of ADR-1…ADR-21 — one normative paragraph each). This document carries the migration and
compatibility detail that does not belong in that summary.
**Date:** 2026-09-05.
**Scope:** schema only. **No Phase 3 feature was implemented.**

---

## What was wrong

§4.7's proposition schema block has always read:

```
| Did(actor, action: ActionKind, object?, target_actor?, location?, interval)
```

`ActionKind` appeared exactly once in the whole architecture and was **never defined**. The
implementation therefore typed it `str` and settled it by matching `action.lower()` against
`EventKind.lower()`. Three consequences:

1. **§5.1's own worked example was unexpressible.** The document writes
   `Did(David, touch, Glass1, interval=[21:20, 22:35))` as the implication a fingerprint
   licenses. `touch` is not an `EventKind`, so `vance_v03`'s `E_trace` had to be transcribed
   as `action="Attack"` — which **over-claims**: it asserts the murder the trace does not
   establish. The fixture carried a NOTE saying so and deferring the fix to an ADR.
2. **Free text in a schema whose whole value is being closed.** ADR-4's reasoning is that one
   closed proposition schema is what makes contradiction detection, envelope containment and
   leak checking deterministic. A `str` action lets the parser (Phase 5) or an LLM invent
   predicates and defeats §14.2c's deterministic slot checks.
3. **Case-insensitive matching** accepted `"attack"`, `"ATTACK"` and `"Attack"` as the same
   action — an ID slot resolved by string munging rather than by the vocabulary.

The root cause is that **forensic evidence under-determines the event**. A fingerprint says
the glass was handled; it cannot say whether it was drunk from, washed, moved, or used as a
weapon. Those are four different `EventKind`s. One vocabulary cannot serve both "what the
CaseLog records" and "what evidence can assert".

## The change

`ActionKind` is defined as a closed `Literal` = every `EventKind` verbatim **plus** entailed
actions, with every member carrying the set of event kinds that make it true.

### New module: `eidolon/world/actions.py` (84 lines)

| Symbol | Type | Meaning |
|---|---|---|
| `EventKind` | `Literal[…]`, 17 members | **Moved** here from `world/events.py`, unchanged. |
| `ActionKind` | `Literal[…]`, 18 members | The 17 event kinds, spelled identically, plus `"touch"`. |
| `EVENT_KINDS` | `frozenset[str]` | `get_args(EventKind)`, for set arithmetic. |
| `ACTION_ENTAILED_BY` | `dict[str, frozenset[str]]` | Total over `ActionKind`. Identity for event-named actions; a union for entailed ones. |
| `ENTAILED_ACTIONS` | `frozenset[str]` | `{"touch"}` — actions that are not event kinds. |
| `entailing_kinds(action)` | `-> frozenset[str] \| None` | The kinds that make `action` true; `None` = no rule = §4.7 Unknown. |

`EventKind` moved **only** to keep the import graph acyclic: `propositions.py` needs
`ActionKind`, and `events.py` already imports `propositions.py`. `world/events.py`
re-exports it, so `from eidolon.world.events import EventKind` is unchanged.

### The one entailed action

```
"touch"  <-  Take | Drop | Use | Give | Plant | Hide | Clean | Write | Attack
```

Each kind puts the actor's hands on the object it names, and a trace cannot tell them apart:
Take/Drop/Give move the object through the actor (P-3 already requires co-location); `Use` is
§5.2's own example; Plant/Hide place it; `Clean` handles it (§5.2 makes `Clean` the thing that
*removes* a trace, which only makes sense if the cleaner touched what they cleaned); `Write`
contacts the document; `Attack` contacts the weapon when the event names one (`vance_v03`'s
`attack` carries `objects=("Glass1",)`).

**Excluded:** `Die`, `Environmental`, `Meet`, `Move`, `Observe`, `Read`, `Speak`, `Stay`.
`Read` is the interesting exclusion — reading does not entail handling (a notice, a screen, a
page over someone's shoulder). The set is deliberately conservative: under-claiming leaves an
implication Unknown, over-claiming **invents forensic contact**.

### `FactIndex` (`world/facts.py`)

`_matching_events(actor, action, …)` becomes `_matching_events(actor, kinds, …)` — it takes a
**set** of kinds and tests `e.kind in kinds` (exact, no `.lower()`).

`_tv_Did` now:

```python
kinds = entailing_kinds(p.action)
if kinds is None:
    return None                       # no entailment rule: Unknown, not refuted
matches = self._matching_events(p.actor, kinds, p.interval, p.object, p.target_actor, p.location)
if p.action in ENTAILED_ACTIONS and p.object is None:
    matches = (e for e in matches if e.objects)
return next(matches, None) is not None
```

The `object is None` guard: `Did(a, "touch")` with no object asks whether the actor handled
*anything*, so the matched event must name an object — otherwise a bare-handed `Attack`
(which carries no `objects`) would satisfy a claim about object contact.

## Exact API / schema change

| Surface | Before | After | Direction |
|---|---|---|---|
| `Did.action` | `str` | `ActionKind` (closed `Literal`, 18 members) | **narrowing** |
| `DidNot.action` | `str` | `ActionKind` | **narrowing** |
| Action matching | `e.kind.lower() == action.lower()` | `e.kind in entailing_kinds(action)` | exact; set-valued |
| `FactIndex._tv_Did` on `"touch"` | `False` (refuted) | `True`/`False` from the CaseLog | **more decidable** |
| `FactIndex._tv_Did` on an unknown action | `False` before the prior repair; `None` after it | `None`, and now unconstructable | unchanged property, stronger gate |
| `FactIndex._matching_events` | `(actor, action, …)` | `(actor, kinds, …)` | private method; signature changed |
| `eidolon.world.events.EventKind` | defined there | re-exported from `actions.py` | **no import change** |
| `eidolon.world` package exports | — | unchanged (`ActionKind` is imported from `eidolon.world.actions`) | none |

Nothing was added to `Did`'s slots. No new proposition variant. No new physics rule. No new
`Effect`. No new event kind.

## Compatibility impact

**Breaking (all fail-closed, all narrowing):**

1. **Case-variant action spellings are rejected.** `Did(action="attack")` used to construct
   and match; it now raises `ValidationError`. Every in-repo construction already used
   canonical spelling; the only affected caller was one parametrised test case, updated.
2. **Free-text actions are rejected at construction.** Previously any `str` constructed and
   returned Unknown at query time. Now `ValidationError`. This matches §4.7's own posture for
   the other slots ("resolved against the case `Alias` table, **or fail**") and I-15.
3. **A stored case whose CaseLog contains a `Did`/`DidNot` inside an
   `InformationTransferred` effect with a non-vocabulary action will fail to load.**
   `Proposition` is reachable from `Event.effects`, so this is a real load-time surface.
   Verified: neither `cases/vance_v03.json` nor `cases/toy_v03.json` contains any `Did`
   proposition, so no stored case is affected.
4. **`FactIndex._matching_events` signature changed** (private; single caller `_tv_Did`).

**Non-breaking:**

- Every existing `Did`/`DidNot` with a canonical `EventKind` spelling behaves identically —
  `entailing_kinds(kind) == {kind}` is exact identity for all 17.
- `from eidolon.world.events import EventKind` unchanged.
- **No `Case` field changed**, so no sealed case's content hash moves (I-4). Confirmed by
  test and by the cross-process hash check in the standing audit.
- `E_trace` moved from `action="Attack"` to `action="touch"`, which is a **fixture** change:
  evidence implications are returned alongside the `Case`, not stored in it, so the hash is
  untouched. `check_physics(vance_v03, evidence)` stays clean (P-0 and P-9).

## What was deliberately NOT done

| Item | Reason |
|---|---|
| `enter`, `hear` | The document's Phase 4 worked example uses both (`DidNot(D, enter, Kitchen, tonight)`, `DidNot(D, hear, argument)`). Their entailment source is **presence** and the **perception model**, not event kinds, so they do not fit `ACTION_ENTAILED_BY` — and `hear`'s subject is a `sound_kind`, which `Did`'s slots do not carry at all. Adding them would mean inventing semantics with no consumer and no test. Deferred to the ADR amendment Phase 4 needs; ADR-22 records the reason. |
| Widening `EventKind` with a `Touch` kind | Rejected in the ADR: contact is a *consequence* of nine kinds, not a standalone occurrence. The generator would have to author a redundant `Touch` beside every `Use`, doubling the log and making "a `Use` without its `Touch`" a physics hole (P-3/P-6). It would also move every existing case's content hash. |
| A `Contact(actor, object, interval)` proposition variant | Rejected in the ADR: bigger than defining a type the schema already names, and it splits "what an actor did" across two predicates, so §13.2's contradiction detector, §14's envelope containment and the admissibility walk each need two code paths. |
| Emitting entailed actions from the perception model | **Load-bearing non-change.** Entailment is a truth relation on `FactIndex`, not a knowledge-generation rule. §4.8 keeps emitting `Did(actor, e.kind, …)` only. Emitting `touch` too would invent knowledge entries nobody acquired, renumber every `KnowledgeEntry` id, and change what V-2 checks. Pinned by `test_perception_still_derives_event_named_did_facts_only`. |
| A pluggable entailment-source framework | YAGNI. One future action grounded in presence or perception needs one branch in `_tv_Did`, which the ADR that needs it should specify. |
| Exporting `ActionKind` from `eidolon.world.__init__` | Not needed by anything; `eidolon.world.actions` is the import path. No unrelated changes. |

## Nothing weakened

| Property | Why it holds |
|---|---|
| **Canonical truth** | `_tv_Did` is still a pure function of the CaseLog. Strictly *more* decidable: `touch` moved from Unknown to True/False; nothing moved the other way. The `touch` set is conservative, so no proposition became True that the log does not license (one test per entailing kind; one per excluded kind). |
| **Deterministic replay** | No state, no RNG, no ordering. `ACTION_ENTAILED_BY` is a module constant built from a sorted comprehension. I-6 re-checked: no `random`/`secrets`/`uuid4` in `eidolon/`. |
| **Provenance** | Untouched. No `Provenance` variant, no `KnowledgeEntry`, no admissibility rule changed. Entailment produces no entries, so no chain gained or lost a link. |
| **Proposition semantics** | `Did`'s slots are unchanged and are still filtered exactly as before — entailment widens which **event kinds** match, never which **slots**. `DidNot` remains the strict negation of `Did` wherever `Did` is settled (tested exhaustively over every actor × object in the golden case). |
| **Physics validation** | P-1…P-9 unchanged. P-0 gains accuracy: it no longer flags an implication as "contradicted by the canonical world" when the world simply cannot express it. `vance_v03` and `vance_v01_negative` stay clean; `vance_v02_negative` keeps exactly its one deliberate P-9 (T-16). |
| **Epistemic separation** | The load-bearing non-change above. I-1/I-8 surface unchanged; V-2 clean on all three fixtures. |
| **Phase 0.5 / 1 / 2 invariants** | I-4 (no `Case` field changed; hash stable, incl. across processes), I-5, I-6, I-8, I-15 (now fail-closed at construction), I-17, I-22, I-27, I-31, I-34 all re-checked by the standing suites and the audit script. |

## Files changed

**Created (2):**

| File | Lines | Purpose |
|---|---|---|
| `eidolon/world/actions.py` | 84 | `EventKind`, `ActionKind`, `ACTION_ENTAILED_BY`, `entailing_kinds` |
| `tests/world/test_actions.py` | 228 | 37 ADR-22 regression tests |

**Changed — source (3):**

| File | Change |
|---|---|
| `eidolon/world/events.py` | `EventKind` imported from `actions.py` and re-exported via `__all__` |
| `eidolon/world/propositions.py` | `Did.action`/`DidNot.action`: `str` → `ActionKind`; docstring on `Did` |
| `eidolon/world/facts.py` | `_matching_events` takes a kind **set**, exact match; `_tv_Did` uses `entailing_kinds` + the entailed-action object guard |

**Changed — docs (1 file, 4 sites):**

| Site | Change |
|---|---|
| §4.5 | `EventKind` marked closed, cross-referenced to `ActionKind` |
| §4.7 schema block | `ActionKind` **defined** (the type the block has always named) |
| §4.7 notes | Two new notes: fact extraction uses event-named actions only; `ActionKind` is not `EventKind`, with the `True`/`False`/`Unknown` rule and the exact-match rule |
| §5.2 | New design point: an implication names the contact, not the event |
| Part XII | **ADR-22** added |

**Changed — tests (2):**

| File | Change |
|---|---|
| `tests/world/fixtures/vance.py` | `E_trace` transcribed as `action="touch"` — the spike's original predicate, which the NOTE said was blocked. NOTE rewritten to record that ADR-22 unblocked it and that `"Attack"` over-claimed. |
| `tests/test_important.py` | The two IMPORTANT-7 tests updated: `touch` is now expressible, so the "Unknown, not refuted" property is exercised through `model_construct` (the validation-bypass path that keeps the guard live); the lowercase `"attack"` parameter is replaced, and `"touch"` added to the definite-verdict sweep |

## Tests added

37 tests in `tests/world/test_actions.py`:

- **Vocabulary is closed and coherent** — `ActionKind ⊇ EventKind`; the only entailed action is
  `touch`; the entailment table is total over `ActionKind` and every row is a subset of
  `EventKind`; an event-named action entails exactly itself (all 17); out-of-vocabulary and
  case-variant actions raise at construction on both `Did` and `DidNot`; `entailing_kinds`
  reports `None` rather than guessing.
- **`touch` against the golden case** — true for the contact the CaseLog logs; settleable
  *without* committing to the event kind (Elena's `Clean` makes `touch` true and `Attack`
  false); false for every actor who never handled the object, with the handler set computed
  from the fixture's events rather than asserted.
- **The table checked against the world, not itself** — one generated single-event case per
  entailing kind (9) asserting the log licenses `touch`, and one per excluded kind (8)
  asserting it does not. This is what stops the constant from drifting into a fiction.
- **Slots and negation** — `touch` respects `location` and `interval`; `DidNot` is the exact
  negation over every actor × object pair; the no-object form requires the event to name one
  (bare-handed `Attack` does not satisfy it, and it flips to true once she cleans a glass).
- **Nothing else moved** — `E_trace` is still P-0 clean and `vance_v03` still has an empty
  physics verdict; perception still derives event-named `Did` facts only; the case hash
  round-trips unchanged.

## Test results

```
python -m pytest -q                          # whole repository
311 passed in 53.59s

python -m pytest tests/world -q               # Phase 1 + ADR-22
98 passed in 6.37s

python -m pytest tests/minds -q -W error::UserWarning   # Phase 2, warnings as errors
77 passed in 16.80s

python -m pytest tests/test_repairs.py -q     # the nine BLOCKING defects
36 passed in 22.35s

python -m pytest tests/test_important.py -q   # the seven IMPORTANT findings
100 passed in 11.17s

python -m pytest tests/world/test_actions.py -q   # ADR-22
37 passed in 2.67s
```

No skips, no xfails, no new warnings.

## Phase 0.5 regression

```
python -m pytest spike/test_spike.py -q
21 passed, 1 warning in 18.40s
```

Unchanged. `spike/` imports nothing from `eidolon/` (verified) and has its own model, so it is
structurally unaffected; the run confirms it. The single warning is the pre-existing
`PytestCollectionWarning` on `spike/minds.py:176`, present before this change.

## Standing audit

The IMPORTANT-findings audit script was re-run with its IMPORTANT-7 probe updated (it had used
`touch` as its "unexpressible" example — now expressible by design, which is the point of the
ADR). 23 checks, **ALL CLEAN**, including V-2 soundness on all three fixtures, I-4 hash
stability across processes, physics verdicts, no-float-in-runtime-state, and I-6.

## Status

| | |
|---|---|
| BLOCKING issues | **0 / 9** — all 36 `tests/test_repairs.py` tests pass |
| IMPORTANT issues | **0 / 7** — all 100 `tests/test_important.py` tests pass |
| Phase 0.5 regression | **PASS** (21/21) |
| Ready for Phase 3 | **YES** |

Phase 3 was not started. `Evidence`, `DiscoverySpec`, the discovery graph and §13.2's
contradiction detector remain unimplemented; this change only makes their proposition
vocabulary expressible.

Remaining forward notes for whoever starts Phase 3 (unchanged from the IMPORTANT-repairs
report except item 1, which this ADR resolves):

1. ~~Contact verbs need an ADR~~ — **done, ADR-22.** `enter`/`hear` will need its amendment
   when Phase 4 cover stories arrive; their entailment source is presence/perception.
2. The victim now contributes knowledge (16 entries in `vance_v03`); any cover story must
   survive that he was in the room.
3. `EpistemicState.added_knowledge` rejects two different entries sharing one id — runtime id
   generation must be collision-free.
4. §4.10's `possible_window` covers "not refuted by another witness" only; compose it with
   `could_reach` for travel feasibility.
