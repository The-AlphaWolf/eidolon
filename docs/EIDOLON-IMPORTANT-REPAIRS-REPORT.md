# EIDOLON — IMPORTANT-findings repair report

**Scope:** the findings classified IMPORTANT (non-blocking) in the Phase 1 + Phase 2 audit,
carried forward after the nine BLOCKING defects were repaired and independently re-checked.
**Date:** 2026-09-05.
**Not in scope:** Phase 3. No Phase 3 work was started.

**Verdict:** all seven carried-forward IMPORTANT findings are fixed, each with a regression
test whose oracle is independent of the code under test. 274 tests pass across the
repository (61 `tests/world/`, 77 `tests/minds/`, 36 `tests/test_repairs.py`, 100 new
`tests/test_important.py`); the Phase 0.5 spike suite still passes unchanged at 21/21. No
BLOCKING issue remains. No IMPORTANT issue remains.

---

## Note on the audit source

No standalone audit/blocking-repair document exists in this repository (`docs/` holds
`EIDOLON-ARCHITECTURE.md`, `EIDOLON-ADVERSARIAL-REVIEW.md`, `EIDOLON-OPUS-HOSTILE-REVIEW.md`,
`EIDOLON-PHASE-0.5-REPORT.md`, `EIDOLON-PHASE-2-REPORT.md`). The nine BLOCKING defects are
recorded in the code as `tests/test_repairs.py` (36 tests, one section per defect). The
IMPORTANT list was therefore taken from the carried-forward items named in the task brief,
and each was **reproduced against the actual code before being fixed** rather than accepted
on the strength of the label. Two of the seven were additionally pinned in the tree itself:

- `tests/minds/test_epistemic_and_character_fold.py` carried an explicit exposure pin for
  the duplicate-`MemoryRecall` finding, naming the intended fix ("dedupe … in the fold") and
  saying it was pinned "so the fix cannot land silently". It fired on this repair.
- `tests/world/fixtures/vance.py`'s `E_trace` comment documents the `Did.action` limitation
  and says widening the schema is deliberately not done. That constraint was respected.

## Reproduction (before the repair)

Every finding was reproduced on the unmodified tree:

| # | Finding | Observed before repair |
|---|---|---|
| 1 | bp bounds | `ComposureChange(new_composure_bp=999999)` accepted; `TrustChange(-5000)` accepted; `Emotion(anxiety=10**9)` accepted; `EpistemicState(memory_strength={"M1": 50000})` accepted |
| 2 | duplicate `MemoryRecall` | applying one event twice → `recall_log` length 2, `repetition_factor` 1.05 → 1.10 |
| 3 | `Case` dict mutability | `case.actors["GHOST"] = …` succeeded on a sealed case and changed `content_hash()` |
| 4 | `content_hash` canonicalization | same content, dicts/tuples reordered → different hash |
| 5 | dead-character perception | victim produced 0 perception facts while alive; a dead-but-not-`role="victim"` actor produced `NotAt(David, Study, [77,120))` — a corpse supplying an absence alibi |
| 6 | §4.10 timeline API | 6 of 7 entry points missing (only `presence` existed) |
| 7 | `Did.action` | `truth_value(Did(action="touch", …))` returned `False` (REFUTED) where the world has no opinion |

---

## IMPORTANT findings fixed

### 1. bp bounds (I-17)

**Defect.** I-17 requires every hashed runtime scalar to be an integer in basis points, and
§9's own code block pins the range at `0..10000`. Nothing enforced it. Every bp field was a
bare `int`, so any value — negative, or a hundred times the cap — entered authoritative
state unchallenged. The one exception made it worse: `apply_character` silently *clamped*
`PressureChange`, so a single field rewrote a recorded outcome (against I-22) while the
other eleven accepted nonsense.

**Fix.** `minds/scale.py` gains `Bp = Annotated[int, Field(ge=0, le=BP_MAX)]`, applied to
every bp field on `Emotion`, `DetectiveModel`, `CharacterState`, `EpistemicState`,
`RecallRecord`, `Revision`, `Belief.confidence_0`, `Memory.salience`/`strength_0`, and all
six bp-carrying event payloads. Enforcement is on the **models**, not in the fold: `apply_*`
copies post-values with `model_copy(update=…)`, which skips validation by design (I-22), so
the range has to hold where a value *enters* — constructing the event, or constructing the
state. The `PressureChange` clamp is deleted; out-of-range is now rejected, which is the
stronger rule and the I-22-consistent one.

`RecallRecord.cue_match: float` was also a float inside `EpistemicState` — hashed
authoritative state, which I-17 forbids outright. It is now `cue_match_bp: Bp`.

### 2. Duplicate `MemoryRecall` (I-5, I-13, I-22)

**Defect.** Three `EpistemicState` fields are append-shaped — `recall_log`,
`belief_revisions`, `added_knowledge`. Appending is not idempotent. `repetition_factor` is a
function of exactly `len(recall_log[m])` and multiplies `memory.score`, so replaying one
duplicated row raised the factor and could flip a retrieval from weak to strong. I-5 requires
replay to reproduce identical state; I-13 treats a duplicated row as corruption, and the fold
was amplifying that corruption into different state rather than absorbing it.

**Fix.** `fold._append_once` appends a record only when an equal one is not already held. The
same event applied any number of times is a no-op; two genuinely different records (different
turn, different outcome, different revision) both land. `KnowledgeAdded` gets the same
treatment, and additionally **fails closed** when two *different* entries share one id — that
is impossible provenance, not a duplicate, and `with_overlay` would otherwise silently keep
whichever it saw first.

Equality is the only identity available: §26's `SessionEvent` envelope (`seq`, `action_id`)
is Phase 7, and I-41 hashes the payload anyway.

### 3. `Case` dict mutability (I-4)

**Defect.** `Case` and everything reachable from it is `ConfigDict(frozen=True)`, but
pydantic's `frozen` blocks attribute *rebinding* only. A `dict`-typed field was still a live
container: `case.actors["GHOST"] = …` succeeded on a sealed case and moved its content hash.
I-4 held for the attributes and not for what they pointed at.

**Fix.** New `world/frozen.py` with `FrozenDict` (a `dict` subclass whose every mutating
operation raises) and a `Frozen[K, V]` annotation, applied to `Case.actors`/`locations`/
`objects`, `Actor.static_attrs`, `Object.static_attrs`, `Location.attributes`, `Alias.names`.

A `dict` subclass rather than `types.MappingProxyType`: the proxy is not JSON-serializable by
pydantic (`PydanticSerializationError: unknown type mappingproxy`) and the case must round-trip
through `model_dump_json`/`model_validate_json`. A dict subclass reads, compares and serializes
identically, so no call site changed. `__reduce__`/`__copy__`/`__deepcopy__` are overridden
because `dict.__reduce__` round-trips through `__setitem__`, which now raises.

One subtlety worth recording: pydantic does not validate **defaults**, so `= {}` stayed a
plain mutable dict even after the field type was frozen. Defaults are now `FrozenDict()`
(covered by `test_a_default_constructed_case_is_frozen_too`).

### 4. `content_hash` canonicalization (I-4)

**Defect.** The hash was `sha256(model_dump_json(exclude={"alias"}))`, which preserves dict
insertion order and tuple order. Neither is semantic: §4.1 says the CaseLog is a *set* of
events, and the graph/attitude/motive tuples are unordered collections. Two cases with
identical content hashed differently, so "verified on load" was a coin flip on how the case
happened to be built or serialized.

**Fix.** The hash is taken over a canonical rendering: events in `ordered_events` order (the
same canonical order every fold already imposes for I-5), the five unordered tuple fields
sorted by their own canonical JSON, and `json.dumps(..., sort_keys=True)` for mappings.
`alias` stays excluded — it is a rendering table (§4.11), not case content.

Verified invariant under 8 shuffle seeds, under full reversal, under dict reordering, and
stable across processes under three different `PYTHONHASHSEED` values; still sensitive to a
changed `id`, `t_investigation`, a moved event and a dropped event.

### 5. Dead-character perception (§4.8, §4.9 P-4, I-34)

**Defect.** Observer eligibility was `case.living_actors()`, which filtered on the authored
`Actor.role`. That is metadata about a character's narrative function, not a fact about the
timeline, and it was wrong in **both** directions:

- The victim contributed no perception at all, despite being alive for 76 of 120 ticks in
  `vance_v03` and being the only other person in the room when he was killed.
- Any actor killed mid-case whose role was not `"victim"` kept perceiving after death. The
  reproduction produced `NotAt(David, Study, [77,120))` from a corpse — `Absence` provenance
  is the fairness spine (I-34), so this was a dead man certifying an alibi.

**Fix.** `state.death_ticks(events)` becomes the single authority on who is dead when,
derived from §4.9 P-4's own `ActorState(actor, "alive", "false")` marker. `physics._p4` now
reuses it instead of recomputing it. `derive_perception` takes every non-`offstage` actor as
an observer and clips **each** observation site at that actor's death tick: own-presence
segments, co-presence, the absence runs, participation facts, event perception, sustained
observation, and the `obs_interval` backing each fact (I-46 rule 9 — the body stays in the
room, the witness does not).

`Case.living_actors()` is now log-derived as well: not offstage, and not dead by the CaseLog.
The authored `role` filter is **kept** alongside it — dropping it would widen the pool on a
case whose victim has no `Die` event — so the change is strictly non-weakening.

Perception is not the only way information reaches a character, so the same gate was applied
to `Told`: `knowledge._told_present` now requires the listener to be alive at the `Speak`
event, not merely listed as a participant. Verified non-vacuous — without the gate, a corpse
acquires the entry.

Observer and subject iteration are now `sorted(...)`, so the synthetic perception-fact ids
(`P0001`…) and the `KnowledgeEntry` ids derived from them no longer depend on `case.actors`
insertion order. This matters *because* of finding 4: two cases that now hash equal must
derive equal perception.

### 6. §4.10 timeline query API

**Defect.** §4.10 defines seven entry points and calls them "used by every other subsystem".
Only `presence` existed.

**Fix.** New `world/timeline.py` implements the six pure world queries — `who_was_at`,
`events_at`, `could_reach`, `could_observe`, `possible_window` — exported from
`eidolon.world`. The seventh, `information_reach(proposition, t) -> {actor: KnowledgeEntry}`,
returns a `minds/` model, so it lives on `minds.knowledge.KnowledgeStore`: §23.1's dependency
direction is one-way and `world/` may not name a `KnowledgeEntry`. It is implemented as
`knowers(proposition, by_t=t)` rather than as a second index.

Nothing in the module is a new derivation — every function is a projection of
`state.presence`, `space.TravelGraph` and `perception.derive_perception`, so a caller cannot
get a different answer here than from the model those three define. `could_observe` is tested
against `derive_perception`'s own output for every (actor, event) pair in the golden case:
the two are not permitted to disagree.

Three underspecified points, each resolved to the smallest documented reading and recorded
at the decision site:

- **`who_was_at` returns one interval per actor** (§4.10's signature). `presence()` already
  merges touching runs, so an actor with two entries in the window genuinely left and came
  back; only the earliest visit is reported, because hulling two visits would assert presence
  across the gap between them. Callers needing every visit read `presence()`.
- **`could_reach`** takes the origin from `from_state` when supplied, otherwise from the
  actor's last canonical placement at or before `by_t`. When the actor is *inside* a segment
  spanning `by_t` this reduces to "are they already there" — which is the correct answer,
  since §4.1's log says where they are and P-1 says it is one place. The query earns its keep
  on the two non-trivial cases: an actor in transit at `by_t`, and a counterfactual
  `from_state` (how the cover-story planner asks "granting this claimed position, could they
  still have made it?").
- **`possible_window`** — §4.1 makes presence total, so nothing is literally unconstrained.
  §4.10's own gloss ("where a lie is *not* refuted") is implemented as: exclude a tick when
  **another** actor's §4.8 fact places this actor elsewhere or certifies their absence from
  the room. Travel feasibility is deliberately left to `could_reach`, which is the other §4.10
  entry point; the docstring says so.

### 7. `Did.action` schema limitation (§4.7)

**Defect.** `Did.action`/`DidNot.action` are free `str` in the closed proposition schema, but
`FactIndex` settles them by matching against §4.5's closed `EventKind`. An action outside that
set came back `False` — **refuted** — when the world in fact has no way to express it. `DidNot`
compounded it: `not None` is `True`, so the negation of an unexpressible action was reported as
canonically true.

The consequence is not cosmetic. `check_physics`'s P-0 reports implications the world refutes,
which is what keeps "authored wrong" distinguishable from "deliberately planted" once Phase 3
introduces `Evidence.authentic`. An implication naming an unmodelled action was being filed as
a contradiction by a world with no opinion on it. The fixture documents the gap itself:
`vance_v03`'s `E_trace` had to be transcribed as `Did(David, "Attack", Glass1, …)` because the
spike's `('touch','Glass1')` predicate has no `EventKind`.

**Fix.** `_tv_Did` returns `None` (Unknown) for an action outside `EventKind` — exactly §4.7's
"attributes never defined" case — and `_tv_DidNot` propagates Unknown instead of negating it.
`EventKind` is **not** widened: that is an ADR-level change to a closed schema, and the fixture
explicitly declines it. Actions inside the set are still settled True/False by the complete
CaseLog, case-insensitively as before.

---

## Findings intentionally left unchanged

| Item | Reason |
|---|---|
| `Personality` fields stay `float` | The architecture's own §9 code block types them `float` (`composure_base: float; volatility: float; …; loyalty: dict[ActorId, float]`). They are generation-time static weights, never runtime-mutable. Changing them would deviate from the spec, not conform to it. Recorded, not silently accepted. |
| `EventKind` not widened for contact verbs like `touch` | Explicitly an ADR-level change to a closed schema (§4.7), and `tests/world/fixtures/vance.py` states the decision not to make it. Finding 7 fixes the *truth function*, which is what was actually wrong; the schema question is left open for whoever writes that ADR. |
| P-4 does not reject a dead **participant** of a later event | P-4's stated text is "no actor **acts** after `Die`", and being spoken to is not acting. Widening a physics rule past its stated text would be changing semantics. The knowledge layer now fails safe (no `Told` entry is emitted for a dead listener), so the hole is closed where it had consequences. Flagged for the phase that revises §4.9. |
| Corroboration (L1→L2), `apparent_admissibility` divergence, `Read`/`Background` derivation, identity-inference-by-silhouette, remaining `Distortion` kinds, `motive-from-relationship`/`consistency` rules | Forward references to Phase 3/4/6 models, already documented as scope decisions in the Phase 2 report. Untouched. |
| `EpistemicState.distortion_corrections: dict[str, Any]` | `Any` in hashed state is a real looseness, but its value type is `Distortion.recalled_value`, which is `object` by the architecture's own §8 model and will be pinned when `correctable_by` gets real `EvidenceId`/`StatementId` values (Phase 3/4). Not a bp violation and not on the IMPORTANT list. |
| `world/timeline.py` re-derives perception per `possible_window` call | The dominant cost of that query. Rather than adding a cache (a second source of truth), the function takes an optional `facts` argument so a caller can hand in `FactIndex(case).perception`. No memoisation, no invalidation problem. |
| `alive_at` helper | Written during the repair, then deleted: `death_ticks` is one line away and had all three call sites. Two ways to ask one question is the thing being removed elsewhere in this repair, not added. |

---

## Files changed

**Created (3):**

| File | Lines | Purpose |
|---|---|---|
| `eidolon/world/frozen.py` | 60 | `FrozenDict` + `Frozen[K, V]` — I-4 sealed-case immutability |
| `eidolon/world/timeline.py` | 154 | §4.10's six pure world queries |
| `tests/test_important.py` | 658 | 100 regression tests, one section per finding |

**Changed — `eidolon/world/` (9):**

| File | Change |
|---|---|
| `case.py` | `Frozen` mappings; canonical `content_hash`; log-derived `living_actors` |
| `entities.py` | `Frozen` `static_attrs` on `Actor`/`Object` |
| `space.py` | `Frozen` `Location.attributes` |
| `alias.py` | `Frozen` `Alias.names` |
| `state.py` | new `death_ticks` — the single authority on who is dead when |
| `perception.py` | death-gated observation at every site; sorted, deterministic iteration |
| `physics.py` | `_p4` reuses `death_ticks` instead of recomputing it |
| `facts.py` | `_tv_Did`/`_tv_DidNot` return Unknown for unexpressible actions |
| `__init__.py` | exports `death_ticks` + the five §4.10 queries |

**Changed — `eidolon/minds/` (8):**

| File | Change |
|---|---|
| `scale.py` | new `Bp` annotated type (the I-17 enforcement point) |
| `character.py` | `Bp` on every runtime scalar; `initial_character_state` uses `bp()` |
| `epistemic.py` | `Bp` fields; `cue_match` → `cue_match_bp` (no float in hashed state) |
| `events.py` | `Bp` on all six bp-carrying payloads |
| `belief.py` | `Bp` `confidence_0` |
| `memory.py` | `Bp` `salience`/`strength_0` |
| `fold.py` | idempotent appends; clamp removed; `KnowledgeAdded` id-conflict fails closed |
| `knowledge.py` | `information_reach`; `knowers(by_t=…)`; `Told` death gate |

**Changed — existing tests (3).** Two had pinned the defective behaviour and were updated to
the corrected semantics; one was a field rename.

| File | Change |
|---|---|
| `tests/minds/test_epistemic_and_character_fold.py` | the duplicate-`MemoryRecall` exposure pin (which existed precisely to fire on this fix) now asserts idempotency; the `PressureChange` clamp test now asserts rejection |
| `tests/minds/test_memory.py` | `cue_match=1.0` → `cue_match_bp=10000` |
| `tests/minds/test_serialization_and_regression.py` | `store.for_character("Harold") == []` replaced by the correct rule: the victim knows his evening up to t=76 and nothing after |

## Tests added

100 tests in `tests/test_important.py`. Highlights, by finding:

- **bp bounds** — every bp-carrying event and every bp state field rejects `-1`, `BP_MAX+1`,
  `999999`, `-5000`; endpoints `0` and `10000` stay legal (guard against an off-by-one bound);
  `RecallRecord` carries no float into hashed state.
- **duplicate events** — re-applying an event 5× never moves the state; genuinely different
  records still accumulate; a wholly duplicated log folds to the same state as one pass;
  `KnowledgeAdded` id-conflict raises.
- **immutability** — 13 distinct mutating operations across `Case`, `Actor`, `Object`,
  `Location` and `Alias` all raise, and the content hash is unmoved; reads/serialization/
  round-trip unchanged; a default-constructed `Case` is frozen too.
- **canonical hash** — invariant under 8 shuffle seeds, full reversal, and mapping/graph
  reordering; still detects a changed `id`, `t_investigation`, a moved event, a dropped event.
- **dead characters** — a dead witness perceives nothing after their death tick; a corpse
  neither witnesses an arrival nor supplies an absence alibi; a dead listener is not told
  anything; the victim knows his own evening up to the tick he dies and nothing of his own
  death; `living_actors` is decided by the log; perception is independent of dict order.
- **§4.10** — all seven entry points exist; `who_was_at` agrees with `presence` for every
  (room, actor) pair; `could_observe` agrees with `derive_perception` for every (actor, event)
  pair; `possible_window` excludes every tick another witness refutes and is a disjoint,
  ordered cover inside the case clock; `information_reach` matches the `acquired_at <= t` rule.
- **`Did.action`** — an unexpressible action is Unknown, is not reported as a P-0
  contradiction, while an expressible-and-refuted one still is; every expressible action still
  gets a definite verdict; every `Did` fact the golden case derives is still True.

Oracles are computed from the architecture's stated rule, from the fixture's declared
timeline, or from an invariance property — never by restating the implementation.

## Test results

```
python -m pytest -q                        # whole repository (testpaths = tests/)
274 passed in 47.54s

python -m pytest tests/world -q            # Phase 1 regression
61 passed in 3.52s

python -m pytest tests/minds -q -W error::UserWarning   # Phase 2, warnings as errors
77 passed in 18.73s

python -m pytest tests/test_repairs.py -q  # the nine BLOCKING defects
36 passed in 20.94s

python -m pytest tests/test_important.py -q  # the seven IMPORTANT findings
100 passed in 9.80s
```

No skips, no xfails, no new warnings.

## Phase 0.5 regression

```
python -m pytest spike/test_spike.py -q
21 passed, 1 warning in 16.68s
```

Unchanged from the Phase 2 report's 21/21. The one warning is the pre-existing
`PytestCollectionWarning` on `spike/minds.py:176` (`Testimony` has an `__init__`), present
before this repair and untouched by it. No spike file was modified.

## Fresh audit of the repaired areas

Run independently of the test suite (22 checks, all pass):

- All seven findings verified fixed against their original reproductions.
- V-2 knowledge soundness clean on `vance_v01_negative`, `vance_v02_negative`, `vance_v03` —
  including the victim's newly-derived entries, which the checker now walks.
- No perception-derived entry recorded as refuted on any of the three fixtures (the
  blocking-defect-5 invariant still holds with the widened observer pool).
- I-4: `content_hash` unchanged after the full propagate → believe → encode pipeline on all
  three fixtures.
- Physics verdicts unchanged: v01 and v03 clean, v02 retains exactly its one deliberate P-9
  negative (T-16).
- `content_hash` identical across three subprocesses under `PYTHONHASHSEED` 0/1/2.
- No `KnowledgeEntry` anywhere is acquired at or after its holder's death tick.
- Belief formation for the victim runs without error (Phase 3 will call it).
- No `float` remains on any runtime `CharacterState`/`EpistemicState`/`Emotion`/`RecallRecord`
  scalar (`Personality` excluded, per the architecture — see above).
- I-6: no `random`, `secrets` or `uuid4` anywhere in `eidolon/`.

## Status

| Question | Answer |
|---|---|
| BLOCKING issues remaining | **None.** All 36 `tests/test_repairs.py` tests pass; the two invariants those repairs established (no refuted perception entry, order-invariant `Told` chains) were re-checked against the widened observer pool. |
| IMPORTANT issues remaining | **None.** All seven carried-forward findings are fixed; two adjacent gaps found during the repair (`Told` bypassing the death gate; unbounded `RecallRecord.cue_match` float) were fixed in the same pass. Items left unchanged are listed above with reasons, and none is a defect. |
| Is Phase 3 safe to begin | **Yes**, with the caveats below. |

**Caveats for whoever starts Phase 3.** These are not defects; they are places where Phase 3's
own work will touch what this repair established.

1. `Did.action` now returns Unknown outside `EventKind`. Phase 3's evidence/implication model
   will want contact verbs (`touch`, `handle`) that no event kind names. That needs the ADR
   this repair deliberately declined to write — not a workaround at the call site.
2. The victim now contributes knowledge. `vance_v03`'s Harold holds 16 entries covering
   t=0..76. Anything Phase 3 iterates over "all characters with knowledge" now includes him,
   and any cover story for the murderer has to survive that the victim was in the room.
3. `EpistemicState.added_knowledge` now rejects two different entries sharing one id.
   Phase 3/4 id generation for runtime entries must be collision-free, not merely unique per
   turn.
4. §4.10's `possible_window` implements the "not refuted by another witness" half only;
   travel feasibility is `could_reach`. A cover-story planner needs both, composed.
