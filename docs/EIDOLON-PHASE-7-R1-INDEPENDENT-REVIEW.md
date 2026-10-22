# EIDOLON Phase 7 - independent review of the R-1 fix (store.py `fold_turn` and `_repair`)

Reviewer: independent, read-only. Date 2026-10-19. Nothing under `D:\Murder Mystery` was written. All work is under
`C:\Users\ASUS\AppData\Local\Temp\claude\r1-review\` (scripts, byte copies of saves, private copies of the tree for mutants).
Every process ran with `PYTHONDONTWRITEBYTECODE=1`; the real tree was imported via `PYTHONPATH`, mutants ran from their own copies with
`PYTHONPATH` unset.

## VERDICT

**Is the R-1 fix correct and free of false refusals on this tree: YES for everything the fix claims (and it is checked at both
boundaries, identically) - with one new IMPORTANT finding (F-1) that the fix does not claim to cover but that reproduces the
R-1 failure shape: a single accepted claim whose `interval` is huge poisons the character (raw `MemoryError` on the next turn).**

* 194 hand-written attacks, each offered to a live `Save.append` and as a correctly re-chained extra turn through `Save.open`:
  the two boundaries agreed on all 194; no refused append changed a row, `meta`, `last_seq`, `last_hash` or the state hash.
  Every nested-reference, binding, count, equality, turn_id and journal claim holds. The only "accepted but I expected refusal" was
  my own wrong expectation (claim ids legitimately repeat across statements).
* False refusals: 0 in 20,254 genuine engine turns (details in section 2).
* 8 of 8 randomly chosen R1 mutants (plus X45, X46, N3) are **real kills**: the shipped forgery is *accepted* at both boundaries
  under the mutant.

## 0. Tree hashes (read-only check)

| file | before | after |
|---|---|---|
| `eidolon/store.py` | `aef73ed3834d3118a42d5be9dc1f69642c65abab9704d7780a72332ed921b37f` | identical |
| `tests/test_persistence.py` | `86bc788c8f776bbc753632c6e1db430135e5855a66b5020ed7b15556d768afd7` | identical |
| `tests/persistence_mutation_check.py` | `e7d45fa1fe693f36cb9e363d3e20ce11b846668b5dc3db7d3a13f039b7281fbb` | identical |

`store.py` matches the expected hash. I also compared all 187 files of `eidolon/`, `tests/`, `cases/` against a byte copy taken at the
start of the review: no difference at the end.

## 1. A - re-chained-load equivalence (194 attacks)

Method. Base save: `cases/generated/study_party_s4.json`, seed 7, GoTo Study, every search, 6 David asks (two presenting evidence),
one Elena ask (so the Elena peel by presenting `E_secret_Elena` is buildable), 64 rows, turn 18. For each attack the events are built once
from a writable copy of the base, then (1) offered to `Save.append` on that live save (state hash, `last_seq`, `last_hash`, the row count
and the whole `meta` table compared before/after a refusal), and (2) written as one more turn into a *fresh byte copy* with every
`prev_hash`/`hash` and the head recomputed (the forger's re-chain) and opened with `Save.open`. Accepted pairs also had their
folded state hashes compared. The full list, with outcomes and messages, is in the appendix (section 8).

Totals (194 attacks):

| expectation | count | outcome |
|---|---|---|
| must refuse (structurally impossible / unresolvable) | 120 | 119 refused at both boundaries; 1 accepted = V38, **my expectation was wrong** (see below) |
| must accept (legitimate row) | 42 | 42 accepted at both boundaries, append-state hash == load-state hash |
| accepted-by-documented-design (`docs/EIDOLON-KNOWN-DEBT.md` C-1 and its "still accepted" list) | 32 | 32 accepted at both boundaries, hashes equal |

* **Boundary disagreement: none** (acceptance, refusal and message identical; the only difference is cosmetic, F-7c).
* **Refused append that mutated anything: none** (`mutated_on_refusal` false in all 194; also the three raw-exception probes below).
* **V38**: a new claim reusing a claim id of an earlier statement is accepted. That is correct: the genuine base has `C_David_L0` in 4
  statements (the engine re-voices the same authored claim). Not a finding.

R-1 table rows from the old re-review, re-run in their original form (all refused at both boundaries, by the intended guard - checked
from the message, not only the verdict): N1 (recall of Elena's memory in an exploration turn), N2 (belief of Elena inside David's turn),
N3/N4 (`KnowledgeAdded` for Elena inside David's turn / in an exploration turn), N5 (`MemoryCorrected` field `any_field_at_all`),
N7 (two `DetectiveModelUpdate`), N8 (`CoverStateDelta` with `slips_used=("nonsense",)`, `contradictions_caught=("bogus",)`,
`refuse_streak=-5`, run in exact form as `N8x`), N9 (`topics_probed={"where": -100}`), N10 (IncidentalPinned by Elena, `Atlantis`, scope
`("S_David", 7)`, exact form `N10a`), N11 (IncidentalPinned in an exploration turn), N12 (exact form `N12x`: `Lied(Ghost, S99999)` +
`Planted(E_nope)`), N13 (`At(Ghost, Atlantis)` claim), N14 (statement `layer_scope=("S_David", 9)`), N16 (peel claims keep ids but carry
another proposition), N19 (`MemoryRecall(turn_id=999)`, also record/revision/`MemoryCorrected`/negative/previous-turn variants), N25 (two
claims with one id). N6 (structured `corrected_value`) is still accepted - documented as "still accepted" in KNOWN-DEBT.

Variants beyond the table (all refused at both boundaries unless stated):
* `Said` nesting an unknown actor, an unknown place, double-nested `Has(Excalibur)`, unknown speaker (V01-V04);
  `Saw` unknown observer / location, `Heard` unknown from-location / actor / observer, `Moved` unknown from / to / actor, `Rel`, `Solution`
  unknown murderer / location, `Attr` / `Incidental` unknown entity, `ObjectAt` unknown holder, `Did` / `DidNot` unknown object / target /
  location, `ObjectState`, `State`, `Has` (V05-V33). The refusal message names the nested guard (`claim 'c:own' names actor 'Ghost'...`)
  in every case except `Attitude`/`Motive` (V30, V31), which are refused earlier by the float rule (they carry a float and can never be
  stored; the entity guard is not what stops them).
* Documented-by-design accepted: `Saw.subject="Atlantis"` (the schema makes it a literal), `ObjectAt.holder` naming a *case object*
  (ambiguous slot accepted against any pool).
* Hypothesis: `Lied` naming a REAL statement that the player does not yet hold. The only realisable case is within a turn: a hypothesis row
  placed before the `StatementHeard` row of the same turn is refused, after it is accepted (H3/H3b, same boundary result). `Planted` /
  `support` naming a REAL but undiscovered evidence id, tested on a second base where only 2 of 10 items were found: refused (H4/H4b, both
  boundaries). `Lied` with an actor that is not the statement's speaker is accepted (structural-only; H5b).
* `layer_scope`: negative (-1), 2^70, `True`, index == len(layers), foreign secret, unknown secret: refused. Real layers 0 and 1 of the
  speaker's own secret: accepted (statement and `IncidentalPinned`).
* `IncidentalPinned` scoped to a real layer of the speaker's secret: accepted (as required). `MemoryCorrected` of the addressee's
  memory with a valid field and a valid value: accepted (as required).
* Two `DetectiveModelUpdate` rows where the second is a no-op, where the first is a no-op, two identical no-ops, one adding an evidence and a
  statement, one that forgets an item: all refused (counts, or "appears twice", or the add/forget rule).
* `CoverStateDelta`: `refuse_streak=True` and `topics_probed={"where": True}` (bool): refused by the round-trip rule (a bool is not the
  int the schema re-serialises); negative values: refused.
* Row order: see 1.2.
* Epistemic rows after a peel: the addressee's own memory *after* the `LayerPeel` / between peel and retraction / last: accepted; David's
  memory / belief / told-entry placed in the middle / last / first position of Elena's peel turn: refused.
* `turn_id` as a bool on an empty save at turn 1 (where `True == 1`): `TurnCommitted(turn=True)` refused at append ("does not round-trip")
  and at load (chain/canonical refusal); `MemoryRecall(turn_id=True)` with `record.turn_id=True` refused at both; a float `turn_id=1.0` refused
  ("float at turn_id").

### 1.1 Documented-class rows that were accepted (not gaps)

C-1 / KNOWN-DEBT: `PressureChange` of an own secret to 10000, `TrustChange` to 10000, `Accusation` inside a conversation turn,
`CaseSolved(correct=True)` with no accusation, `CoverStateDelta(refuse_streak=10**12)`, `topics_probed` reset to `{}` / decreased / with an
unknown key, two distinct `CoverStateDelta` in one turn, a peel turn with an extra claim beside the owed ones, owed claims reordered,
peel voiced as `CONFESSION`, `IncidentalPinned.entity="Atlantis"` (documented: free text), `MemoryCorrected.corrected_value` a nested
structure or `None`, `KnowledgeAdded` with `acquired_at=10**9` or `by_detective_turn=999`, colliding with a sealed knowledge id, a
`Hypothesis` with `created_turn=999, updated_turn=-5`, `status="corroborated"`, empty claim `grounding`. See F-3/F-4/F-5 for the ones I
think deserve a line in the debt table.

### 1.2 Row-order battery (no I/O, `fold_turn` directly)

Every permutation of the rows after `TurnCommitted` for four genuine turns: David plain ask (120 permutations), David presenting evidence
(120), Elena peel (40,320), David ask + 4 addressee epistemic rows (362,880). Result: 403,440 orders, 0 raw exceptions; **every accepted
order folds to the identical state hash as the genuine order**; the only refused orders are those that put `StatementHeard` or
`ClaimRetracted` before the `ClaimMade` they depend on. `TurnCommitted` moved to any later position: refused in all positions (0 of 27
accepted). Rows whose position changes the verdict by design: a claim grounded in a same-turn `KnowledgeAdded` is accepted only if the told
entry precedes the `ClaimMade` (K7 accept, K8 refuse) - see F-8.

### 1.3 Raw-exception hunt (E)

* **Fuzz** of `_decode` + `fold_turn` on 8 genuine turn templates (plain ask, presenting ask, Elena peel, ask + 4 epistemic rows,
  exploration, hypothesis, incidental + minds rows, accusation + solve), no file I/O:
  300,000 single string-leaf substitutions with unresolvable ids (`Ghost`, `Atlantis`, `""`, `S99999`, `E_nope`, `K:nope`, ...),
  300,000 single int-leaf substitutions (0, -1, 2^40, 10000, 10001, ...), plus 3,000 multi-mutation / row delete-duplicate-swap
  iterations. **0 raw exceptions** (everything is a `SaveRefusal` or a pydantic validation error that `Save.open` wraps).
  The substitution fuzz is also a systematic gap finder: the only string positions where an unresolvable value was ever *accepted*
  are free text or an own-identifier (`BeliefRevised.revision.reason`, `ClaimMade.statement.text`/`query_hash`/`claims[].id`,
  `HypothesisChanged.hypothesis.id`, `IncidentalPinned.attr`/`entity`/`value`, `KnowledgeAdded.entry.id`). No reference slot is
  accepted unresolved. The only int positions accepted outside 0..10000 bp scales or small counters are: proposition `interval[]` ends
  (F-1), `Hypothesis.created_turn`/`updated_turn`, `KnowledgeEntry.acquired_at`, `InvestigationTold.by_detective_turn` (F-3),
  `MemoryCorrected.corrected_value[]` (N6), `topics_probed` values (counter inflation, C-1).
* **Deep nesting.** `Said` chains: depth 10 and 60 accepted at both boundaries; depth 150, 300, 600 refused at append
  (`ClaimMade does not validate: ValueError`); they cannot even be written as a canonical row (`json.dumps` depth limit), so no re-chained
  file can carry them.
* **Malformed in-memory objects (API misuse, `model_construct`).** At `Save.append`: a claim whose `proposition` is a `dict` raises a raw
  `AttributeError: 'dict' object has no attribute 'kind'` out of `fold_turn` (nothing committed, nothing mutated); the same row at load
  is a clean `SaveRefusal` ("claim names actor 'Ghost'"). A `layer_scope` given as a `list` is accepted at both boundaries. Wrong-typed
  fields (`memory_id=5`, `topics_probed={"where": "x"}`, short tuple, string scope) are refused cleanly at both. See F-2.

## 2. B - false-refusal sweep (genuine engine turns -> `Save.append`)

Every non-rejected turn the runners produced (`run_ask_turn`, `run_goto_turn`, `run_search_turn`, `run_take_turn`) was appended through
`Save.append`; after every append the folded state hash was compared with the engine's live state hash, and every save was reloaded
with `Save.open` and compared again. **Any `SaveRefusal` here would be a false refusal. There were none.**

| sweep | jobs | genuine turns appended | engine-rejected | SaveRefusals | live!=folded | reload!=live |
|---|---|---|---|---|---|---|
| generic: 4 cases x seeds 7, 11, 23; every living character (`living_actors()`); exploration in prerequisite order; round 1: `None` + EVERY held evidence and statement id presented to each character; round 2: `None` + first 60 held ids; plus 13 query kinds (incl. `meta`, `coercion`) with `hostile_tone`/`provisional_accusation` cycling | 12 | 11,256 | 0 | **0** | 0 | 0 |
| bots through the real pipeline (greedy, cue-following, adversarial, murderer_peel, random, order-shuffled, bluff) x 4 cases, recorded and replayed through the store | 28 | 3,558 | 0 | **0** | 0 | 0 |
| random bot, seeds 11, 23, 42, 77 x 4 cases (250 actions each) | 16 | 4,000 | 0 | **0** | 0 | 0 |
| all 16 query kinds with subject/object/location refs and all 4 tones, plus `GoTo` all places, `Take` all items (study_party_s4, manor_wing_s4, seed 5) | 2 | 352 | 0 | **0** | 0 | 0 |
| murderer deep path, manor_wing_s4/s6 (layer 0 via account token + evidence, then brute force: every held item x3 rounds, with a permissive confession hook) | 2 | 1,088 | 0 | **0** | 0 | 0 |
| **total** | 60 | **20,254** | 0 | **0** | 0 | 0 |

Rows (the first three sweeps, 56 jobs, 18,814 turns, 93,049 rows): `TurnCommitted` 18,814; `ClaimMade` 15,908 (= `StatementHeard` 15,908);
`LayerPeel` **89** (all `0 -> 1`); `ClaimRetracted` **159**; `DetectiveModelUpdate` **7,788**; `AccountHeard` **10**; `CoverStateDelta` 14,739;
`MetaAttemptLogged` 504 (meta/coercion); `PressureChange` 1,375; `ComposureChange` 15,908; `Discovery` 513; `LocationVisited` 1,334.
Acts: DONT_RECALL 9,212, REFUSE 3,978, LIE 1,036, CONCESSION 89, VAGUE 405, CLARIFY 504, DONT_KNOW 365, OPINION 159, TRUTH 61, DENY_EVIDENCE 41,
HYPOTHETICAL 55, REPEAT_PRIOR 2, CORRECT_DETECTIVE 1.

* **Murderer account-token path and murderer peel: driven, in all four cases.** `murderer_peel` bot (4 cases): the housekeeper delivers her
  account token through real questions (`AccountHeard` row in the log), then the murderer's layer 0 falls to `E_trace` (`LayerPeel 0->1`,
  `CONCESSION`); 4 saves appended, reloaded equal.
* **Not reachable:** the murderer's *deeper* path. In `manor_wing_*` the murder cover has three layers ending in a gated `confession`
  terminal. `derive_breaker_sets(murder, 1, ...)` is empty, and presenting EVERY held evidence/statement to the murderer 3 times (with a
  permissive solver hook) never moves layer 1, so no genuine `LayerPeel 1->2` and no genuine `CONFESSION` turn could be produced. In
  `study_party_*` the murder terminal is a `stonewall`. So the fold has never seen a genuine CONFESSION turn; the CONFESSION shape is
  covered only by the documented C-1 forgery. No generated case has a `CONFESSION` act in any sweep.
* **Static check** (every proposition the engine can ever voice - knowledge, beliefs, memories, cover claims, frames, concedes, evidence
  responses, deflections, slips, misleading truths, protected, evidence implications; 3,626 propositions over the 4 cases) through
  `_check_proposition`: **0 refusals**. Layer scopes for every secret/layer: all accepted.
* **`layer_scope` on genuine engine output.** No generated case has a cover `frame`, so no sweep ever produced a statement with a
  `layer_scope`. I gave the in-memory engine state a frame on layers 0 and 1 of David's and Elena's secrets, let the real engine produce
  the turns (ask, challenge, hostile, and Elena's peel turn, whose scope is the pre-peel `from_index`), and offered those events to
  `Save.append` on the real save: all four accepted.
* **Authored time bounds.** Every authored interval in every case lies in `[0, case.t_investigation]` (`t_investigation = 120`;
  3,596 intervals checked), so the bound proposed for F-1 would not false-refuse any authored data.

## 3. C - hot journal (N-3)

Crash reproduced exactly as in the tests (a subprocess opens the save, `PRAGMA cache_size=10`, `BEGIN`, 3,000 inserts, `os._exit(0)`):
journal 17,920 bytes beside a 462,848-byte save.

| step | result |
|---|---|
| `plan_truncation(db)` | `TruncationPlan(action="refuse", stage="journal")`; db and journal byte-identical after |
| `truncate_to_last_valid(db)` (no confirm) | `ConfirmationRequired`, `plan.action="refuse"`, `plan.stage="journal"`; bytes identical |
| `truncate_to_last_valid(db, confirm=True)` | `SaveRefusal(stage="journal")`; db and journal byte-identical, journal still present |
| `_repair(db, apply=True)` direct | refuse/journal; bytes identical |
| read-only `Save.open(db)` | `SaveRefusal("unreadable save: OperationalError: attempt to write a readonly database")`; bytes identical (X39) |
| writable `Save.open(db, writable=True)` | recovers: `last_seq` 64, state hash == pre-crash hash, journal gone |
| `plan_truncation` after recovery | `none`, 64 rows; a second read-only open equals the pre-crash state |
| EMPTY (0-byte) journal beside a healthy save | not blocked: plan `none`; `truncate_to_last_valid(confirm=True)` returns 64, db bytes unchanged |
| missing path (`plan_truncation`, `truncate_to_last_valid`) | `SaveRefusal("no such save")`; no file created (neither `nope.db` nor `nope.db-journal`) |
| missing db with a stray `-journal` | `SaveRefusal("no such save")`; nothing created |
| journal of 35 junk bytes | refused as `journal`; a writable open deletes it; plan `none` afterwards |
| **journal of 512 zero bytes** | refused as `journal`; a writable open **leaves it in place**; the next plan is refused again (F-6) |

Under the N3 mutant (`if journal.is_file() and journal.stat().st_size:` -> `if False:`) the same `plan_truncation` returns `none` and
**the db bytes change and the journal is gone** (confirmed directly, section 4), so the test guards a real property.

## 4. D - mutation spot-check (private copies, `python -m pytest tests/test_persistence.py -q -p no:cacheprovider -x -k "<k>"`)

The 27 mutants naming R1 were sampled with `random.Random(20261019).sample(...)` (8 picked, sorted), plus X45, X46, N3. For each: the unmutated
copy passes the selection (`rc 0`); the anchor matches exactly once; the mutated copy fails a test whose id contains the mutant's `fail`
name. Then the FORGERIES entry the mutant is meant to be killed by was built from the shipped `FORGERIES` table on the same fixture
(`drive(s, 6)` + Elena ask) *inside the mutated tree*, offered to `Save.append` and as a re-chained load.

| mutant | unmutated | killed by (test) | forgery under the mutant: append / load | kill type |
|---|---|---|---|---|
| R1-contradiction-nothing-resolves | 2 passed | `..._refused_at_append[R1_contradiction_nothing_resolves]` | ACCEPT / ACCEPT | **real** |
| R1-hypothesis-proposition-unchecked | 2 passed | `[R1_hypothesis_naming_an_unknown_actor_and_place]` | ACCEPT / ACCEPT | **real** |
| R1-knowledge-for-another-character | 4 passed | `[R1_knowledge_added_for_another_character]` | `..._for_another_character` and `..._in_an_exploration_turn`: ACCEPT / ACCEPT | **real** (2 of 2) |
| R1-layer-scope-index-unchecked | 4 passed | `[R1_incidental_scoped_to_a_layer_its_cover_lacks]` | incidental and statement variants: ACCEPT / ACCEPT | **real** (2 of 2) |
| R1-memory-of-another-character | 6 passed | `[R1_memory_recall_of_another_character]` | recall of another, recall in exploration, corrected for another: ACCEPT / ACCEPT | **real** (3 of 3) |
| R1-negative-topic-counter | 2 passed | `[R1_negative_topic_counter]` | ACCEPT / ACCEPT | **real** |
| R1-peel-voiced-by-claim-id-only | 2 passed | `[R1_peel_voiced_with_other_claims]` | ACCEPT / ACCEPT | **real** |
| R1-turn-id-of-a-recall-record | 2 passed | `[R1_recall_record_carrying_another_turn_id]` | ACCEPT / ACCEPT | **real** |
| X45-prev-hash-column-unchecked | 1 passed | `test_X45_an_edited_prev_hash_column...` | direct: an edited `prev_hash` column LOADS under the mutant | **real** |
| X46-genesis-does-not-bind-the-seed | 1 passed | `test_X46_the_genesis_binds_the_seed...` | direct (save created under the mutant, seed edited to 8, the test's own seed-ignoring `new_session`): LOADS. Control on the unmutated copy: `genesis` refusal | **real** |
| N3-dry-run-rolls-back-a-hot-journal | 1 passed | `test_N3_the_dry_run_and_the_repair_never_roll_back_a_hot_journal` | direct: `plan_truncation` returns `none`, db bytes change, journal deleted | **real** |

No message-only or crash-only kill among the 11. (The re-review's 8 weak kills in the old table were `peel-bound-unchecked`,
`retraction-of-another-speaker`, ... none of those is an R1 mutant.) I did not run `R1-claim-proposition-unchecked`, but the claim guard
messages in section 1 (V01-V33) come from `_check_proposition`, not from a `KeyError` in `tokens_satisfied`, so that guard is reached.

### 4.1 The five EQUIVALENT entries

Probed by applying a mutant removing the guard to a private copy, then offering the inputs the guard exists for (both boundaries).

| entry | verdict | evidence |
|---|---|---|
| **two statements in one turn** (new) | **holds** | guard removed; second `ClaimMade` variants: identical copy -> "appears twice" (duplicate-row rule); same id with other text / claims / act -> `apply_decision` "already committed with different content" (`turn does not fold`); other id or other speaker -> `_check_statement` refuses. No input was accepted under the mutant at either boundary. Only the message gets worse. |
| X23 no minds rows outside a conversation | holds (weak message) | guard removed; all 7 `CharacterState` kinds in an exploration turn refused: six by the `KeyError(None)` backstop ("turn does not fold: None"), `PressureChange` by its owner check |
| X26 one `TurnCommitted` per turn | holds | guard removed; a second bracket (same, other action_id, other character) refused: "event kind 'TurnCommitted' has no fold" |
| X31 payload kind == column kind | **acceptance holds, "equivalent" does not** | guard removed: a re-chained file whose last row's kind column says `ComposureChange` while the payload says another kind is still refused (pydantic `Literal`), but as `unreadable save: ValidationError` with stage `None`, and **`plan_truncation(path)` RAISES `SaveRefusal` instead of returning a refusal plan**. With the guard the plan is `refuse/fold: payload is not a ComposureChange`. Recovery diagnostics regress, so the justification should say so (carry-over of the re-review's X31 note) |
| float range 0<=x<=1 | holds for finite values; exception contract does not | 1.5, -0.5, 1.00005 refused by the grid rule at both boundaries; NaN refused; **`+-inf` and 1e308 make `append` raise a raw `OverflowError`** (`bp()` before the grid compare) and 1e308 loads as `unreadable save: OverflowError` (stage `None`). This is the re-review's N-5, still open |

## 5. E - code read

Read critically: `_check_proposition`, `_check_layer_scope`, `_check_epistemic_target`, `_check_hypothesis`, the `CoverStateDelta` branch,
`_check_peels_voiced`, the turn_id check, `_repair`. No logic error found in them for the claimed properties:

* `_check_proposition` pools are right: actors = `case.actors` (includes the victim, correctly - `At(Harold, ...)` accepted, `SuspicionShift(target="Harold")`
  is refused - executed: "names unknown actor 'Harold'" - because the victim is not a `characters` key), places/objects use `known_locations`/`known_items` (the same functions the
  runners use, so the two cannot drift); the ambiguous slots (`ObjectAt.holder`, `Attr.entity`, `Incidental.entity`) are accepted against the
  union. `entities()` has a slot list; I checked every proposition kind that can be stored (V-series; `Attitude`/`Motive` carry a float and can never be stored) - no kind has an unlisted reference slot.
* `_check_layer_scope`: `0 <= scope[1] < len(layers)` rejects negatives, huge ints; a bool cannot reach it (round-trip rule).
* `_check_epistemic_target`: `m.character != who` with `who is None` is always true for a str -> exploration turns refuse. Correct.
* peel equality: `said[c.id].model_copy(update={"statement": c.statement}) != c` compares every `Claim` field; single-field edits to
  `proposition`, `grounding`, `sincerity`, `source`, `modality`, `confidence`, `id` are each refused (PL1-PL6, PL9).
* `_repair` journal guard: size test, runs before `connect`; see section 3.
* `fold_turn` converts only `ValueError`/`KeyError`/`TypeError`; an `AttributeError`/`IndexError`/`OverflowError` is not converted at
  `append` (F-2, F-7). At load every exception ends as a `SaveRefusal` because `Save.open` wraps `Exception`.
* Observation F-2's root cause: `append` folds the caller's *original objects*, while load folds the *decoded* ones. `_encode` makes the
  payloads equal but not the in-memory shapes.

## 6. Findings

### BLOCKING
None.

### IMPORTANT

**F-1 - Unbounded `interval` (and other time-valued) slots in claims/hypotheses/told entries are accepted; one forged claim poisons the
character with a raw `MemoryError` (same failure shape as R-1's N13).**
Not in the R-1 table and not claimed by the fix, so it is not a defect of the fix as specified; it is a gap in the class R-1 was filed
for (a structurally impossible row the engine cannot live with), reachable the same way (re-chained local file or a future producer).
Accepted at both boundaries: `At(David, Study, [0, 2^40))`, `At(David, Study, [-2^40, 0))`, `Heard(... interval [0, 2^40))`,
as claims (`Moved(t=2^40)` is accepted too, but `feasibility` indexes a single tick for it, so it is not the hazard); the same `At` as a hypothesis proposition and as a `KnowledgeAdded` proposition (R2a-R2f in the appendix).
Consequence: `world/feasibility._compile` enumerates every tick of every standing claim (`for t in ticks(p.interval): forced[t] = ...`,
~85 bytes per tick, measured: 100k ticks 0.09 s/11 MB, 1M 0.96 s/85 MB, 2M 1.84 s/171 MB per call). With the 2^40 claim accepted by
`Save.append`, the **next** `run_ask_turn` for David died with a raw `MemoryError` from `consistency_check` ->
`feasible` -> `_compile` (`world/feasibility.py:57`); every later turn by that character would. (I ran the 2^40 case once; I did not repeat it.
At 2,000,000 ticks the turns still complete but cost ~16x.) A poisoned save loads fine and then kills or stalls play.
Minimal reproduction (against a copy of any save with David having spoken):
```
s = Save.open(copy, writable=True)
c = Claim(id="c:x", statement="S%05d" % (s.state.turn_counter+1), proposition=At(actor="David", location="Study", interval=(0, 2**40)),
          sincerity="truthful", source="plan", grounding=(s.state.knowledge.for_character("David")[0].id,))
evs = [e if e.kind != "ClaimMade" else ClaimMade(statement=e.statement.model_copy(update={"claims": (c,), "accounts": ()}))
       for e in <genuine David ask events>]
s.append(evs, s.last_seq, "x")                                   # -> appended=True (and the re-chained file loads)
run_ask_turn(s.state, "David", Query(kind="where", predicate_hint="where", raw="q"))   # -> MemoryError
```
Suggested fix (structural, no weight): in `_check_proposition` require `0 <= start < end <= case.t_investigation` for `interval`, and
`0 <= t <= case.t_investigation` for `Moved.t`/`Said.t`. I verified that every one of the 3,596 authored intervals in the four cases satisfies it,
so it cannot false-refuse authored data.

### NON-BLOCKING

* **F-2** `append` folds the caller's objects, `Save.open` folds decoded ones. A malformed in-memory event that survives `_encode`
  (`model_construct` with a `dict` proposition) raises a raw `AttributeError` out of `append`; at load it is a clean `SaveRefusal`.
  Nothing is committed or mutated. Fix: fold `[_decode(...)]` of the encoded payloads at append, which also makes "identical at both
  boundaries" true by construction.
* **F-3** Turn-valued fields are not tied to the turn: `Hypothesis.created_turn`/`updated_turn`, `InvestigationTold.by_detective_turn`,
  `KnowledgeEntry.acquired_at` accept -1, 999, 2^40 (fuzz and R2 probes). No reader today (`created_turn`/`updated_turn` are write-only;
  a grep finds no reader of `acquired_at` for overlay entries). The Phase 8 `HypothesisChanged` producer must set `updated_turn == turn` and the fold should check it.
* **F-4** `layer_scope` is range-checked only. A statement or incidental scoped to an unreached but in-range layer is accepted (David at layer 0,
  scope `("S_David", 1)`, L7/L10). The engine always scopes to the current layer (`from_index` in a peel turn), which `layer_index(...)` gives
  without any weight.
* **F-5** Own-identifier fields accept anything: `''` as claim id, `Hypothesis.id` or `KnowledgeEntry.id`; a `KnowledgeAdded` whose id collides
  with a sealed knowledge id is accepted and silently ignored by `with_overlay` (inert: the sealed entry wins). `IncidentalPinned.entity`
  free text and structured/`None` `corrected_value` are the documented ones.
* **F-6** A non-empty journal whose header is all zero bytes makes `plan_truncation`/`truncate_to_last_valid` refuse with advice
  ("open the save writable once ... then plan again") that does not clear it: a writable open leaves such a journal in place (a junk
  non-zero journal is deleted). It is cleared by the next successful append, which a damaged save cannot make. Rare (needs a PERSIST-style
  or half-written journal); the user must delete the file by hand.
* **F-7** Carry-overs, still true on this tree: (a) X31's "equivalent" justification is incomplete (recovery regresses, section 4.1);
  (b) N-5: `+-inf`/1e308 raw `OverflowError` out of `append`; (c) the append-time `SaveRefusal.stage` is `None` for refusals raised by
  `_check_statement`/`_encode` while the load-time stage is `fold` (messages identical).
* **F-8** Phase 8 integration hazards created by the new rules (no producer today, so no false refusal today): (i) a claim grounded in a
  same-turn `KnowledgeAdded` is accepted only when the told row precedes `ClaimMade`, but the engine's row convention
  (`[TurnCommitted] + events + discovered + heard + minds_events`) puts minds rows after it; (ii) `run_ask_turn` hands the strategy
  `turn_id=state.turn_counter` (the previous turn), and `build_memory_recall_event(memory_id, turn_id, ...)` takes a turn id from the
  caller; a producer that reuses that value would trip the new "turn_id == turn" rule.
* **F-9** (documented limit) `contradictions_caught` accepts removal, reordering and duplication of ids the character already holds
  (`("x","y") -> ("x",)`, `()`, `("y","x")`, `("x","x","y")` all accepted by `fold_turn`; extension refused); `slips_used` may shrink. Both
  are unreachable today because no row can create a non-empty `contradictions_caught`, and no generated case has a slip.

### UNMEASURED (not weakened, just not exercised by data)

* Evidence-kit names in `known_locations`/`known_items`: no generated case has a `KnowsAbout`/`HasItem` prerequisite naming a place or item
  outside `case.locations`/`case.objects` (both difference sets are empty), so removing the kit extension from `_check_proposition` would
  not be visible on any case.
* `slips_used` positive path: no generated case has a slip. I synthesised a slip: `slips_used=("SL1",)` accepted, `("SL1","nonsense")` refused,
  shrink accepted.
* A genuine CONFESSION turn and a genuine `LayerPeel 1->2` (see section 2).
* Cross-machine / cross-libm replay (as in the re-review).

## 7. Commands (reproduction)

All scripts are in `C:\Users\ASUS\AppData\Local\Temp\claude\r1-review\`; run from that directory with
`PYTHONPATH="D:\Murder Mystery" PYTHONDONTWRITEBYTECODE=1`.
`mkbase.py` (base save), `attacks.py` + `run_attacks.py` (194 attacks, two boundaries), `analyze_a.py`, `perms.py` (row orders),
`fuzz.py`/`fuzz2.py`/`fuzz3.py` (hostile payloads), `sweep.py` (generic + bots), `extra_sweep.py`, `confess.py` (murderer deep path),
`frame_test.py` (layer_scope on genuine output), `static_scan.py`, `horizon.py`, `c_journal.py`, `mut.py` + `mut_direct.py` + `mkeq.py` +
`equiv.py` (mutants and EQUIVALENT probes), `interval_poison.py` + `mem2m.py` (F-1), `probes_e.py`, `direct.py`.

## 8. Appendix - every attack, both boundaries

Legend: expectation `refuse` = structurally impossible/unresolvable (accepting it would be an R-1 gap), `accept` = legitimate (refusing it
would be a false refusal), `doc` = accepted by documented design or inert (see 1.1). Refusal text is truncated.
| attack | expectation | Save.append (live) | re-chained Save.open | state hash append==load | note |
|---|---|---|---|---|---|
| C1_slips_nonsense | refuse | REFUSE: CoverStateDelta slips_used names a slip David does not have | REFUSE: CoverStateDelta slips_used names a slip David does not have |  |  |
| C2_contradictions_bogus | refuse | REFUSE: CoverStateDelta contradictions_caught names a contradiction nothing resolves | REFUSE: CoverStateDelta contradictions_caught names a contradiction nothing resolves |  |  |
| C3_refuse_streak_negative | refuse | REFUSE: CoverStateDelta carries a negative counter | REFUSE: CoverStateDelta carries a negative counter |  |  |
| C4_topic_negative | refuse | REFUSE: CoverStateDelta carries a negative counter | REFUSE: CoverStateDelta carries a negative counter |  |  |
| C5_all_three_nonsense | refuse | REFUSE: CoverStateDelta slips_used names a slip David does not have | REFUSE: CoverStateDelta slips_used names a slip David does not have |  |  |
| C6_empty_slips_empty_contradictions | accept | ACCEPT | ACCEPT | = |  |
| C7_refuse_streak_zero | accept | ACCEPT | ACCEPT | = |  |
| C8_refuse_streak_huge | doc | ACCEPT | ACCEPT | = | unjustified counter value, C-1(b) class |
| C9_topics_reset_to_empty | doc | ACCEPT | ACCEPT | = | counters may shrink; C-1(b) |
| C10_topics_unknown_key | doc | ACCEPT | ACCEPT | = |  |
| C11_topics_decreased | doc | ACCEPT | ACCEPT | = |  |
| C12_refuse_streak_bool | refuse | REFUSE: CoverStateDelta does not round-trip | REFUSE: CoverStateDelta payload carries fields or values the schema does not |  |  |
| C13_topics_value_bool | refuse | REFUSE: CoverStateDelta does not round-trip | REFUSE: CoverStateDelta payload carries fields or values the schema does not |  |  |
| C14_cover_delta_in_exploration | refuse | REFUSE: CoverStateDelta outside a conversation turn | REFUSE: CoverStateDelta outside a conversation turn |  |  |
| C15_two_cover_deltas_distinct | doc | ACCEPT | ACCEPT | = | two CoverStateDelta in one turn: not claimed |
| D1_two_model_updates_each_adding_one | refuse | REFUSE: two DetectiveModelUpdate rows in one turn | REFUSE: two DetectiveModelUpdate rows in one turn |  |  |
| D2_two_model_updates_first_is_noop | refuse | REFUSE: two DetectiveModelUpdate rows in one turn | REFUSE: two DetectiveModelUpdate rows in one turn |  |  |
| D3_two_model_updates_second_is_noop | refuse | REFUSE: two DetectiveModelUpdate rows in one turn | REFUSE: two DetectiveModelUpdate rows in one turn |  |  |
| D3b_two_identical_noop_updates | refuse | REFUSE: DetectiveModelUpdate appears twice in one turn | REFUSE: DetectiveModelUpdate appears twice in one turn |  |  |
| D4_one_noop_update | accept | ACCEPT | ACCEPT | = |  |
| D5_one_update_adding_one_held | accept | ACCEPT | ACCEPT | = |  |
| D6_update_adds_one_evidence_and_one_statement | refuse | REFUSE: DetectiveModelUpdate may add at most the one item presented, and forget nothin | REFUSE: DetectiveModelUpdate may add at most the one item presented, and forget nothin |  |  |
| D7_update_forgets_item | refuse | REFUSE: DetectiveModelUpdate may add at most the one item presented, and forget nothin | REFUSE: DetectiveModelUpdate may add at most the one item presented, and forget nothin |  |  |
| D8_update_estimated_suspicion | refuse | REFUSE: DetectiveModelUpdate rewrites more than what the detective presented | REFUSE: DetectiveModelUpdate rewrites more than what the detective presented |  |  |
| D9_update_probed_topics | refuse | REFUSE: DetectiveModelUpdate rewrites more than what the detective presented | REFUSE: DetectiveModelUpdate rewrites more than what the detective presented |  |  |
| D10_update_contradictions_confronted | refuse | REFUSE: DetectiveModelUpdate rewrites more than what the detective presented | REFUSE: DetectiveModelUpdate rewrites more than what the detective presented |  |  |
| H1_hyp_unknown_actor_place | refuse | REFUSE: hypothesis 'H1' names actor 'Ghost', which the case does not contain (I-15) | REFUSE: hypothesis 'H1' names actor 'Ghost', which the case does not contain (I-15) |  |  |
| H2_hyp_Lied_unknown_actor_held_statement | refuse | REFUSE: hypothesis 'H1' names actor 'Ghost', which the case does not contain (I-15) | REFUSE: hypothesis 'H1' names actor 'Ghost', which the case does not contain (I-15) |  |  |
| H3_hyp_Lied_real_statement_unheld_same_turn_before_hearing | refuse | REFUSE: hypothesis 'H1': Lied names statement 'S00019', which the player does not hold | REFUSE: hypothesis 'H1': Lied names statement 'S00019', which the player does not hold |  |  |
| H3b_hyp_Lied_same_turn_statement_after_hearing | accept | ACCEPT | ACCEPT | = |  |
| H4_hyp_Planted_real_undiscovered_evidence | refuse | REFUSE: hypothesis 'H1': Planted names evidence 'E_pin_Elena', which the player does n | REFUSE: hypothesis 'H1': Planted names evidence 'E_pin_Elena', which the player does n |  |  |
| H4b_hyp_support_real_undiscovered_evidence | refuse | REFUSE: HypothesisChanged rests on 'E_pin_Elena', which the player does not hold | REFUSE: HypothesisChanged rests on 'E_pin_Elena', which the player does not hold |  |  |
| H5_hyp_Lied_held_statement_real_actor | accept | ACCEPT | ACCEPT | = |  |
| H5b_hyp_Lied_actor_mismatch_statement_speaker | doc | ACCEPT | ACCEPT | = | Lied.actor not tied to the statement's speaker (structural-only) |
| H6_hyp_Planted_held_evidence | accept | ACCEPT | ACCEPT | = |  |
| H7_hyp_Said_nested_unknown | refuse | REFUSE: hypothesis 'H1' names actor 'Ghost', which the case does not contain (I-15) | REFUSE: hypothesis 'H1' names actor 'Ghost', which the case does not contain (I-15) |  |  |
| H8_hyp_Saw_subject_literal | doc | ACCEPT | ACCEPT | = |  |
| H9_hyp_created_turn_999 | doc | ACCEPT | ACCEPT | = | Hypothesis.created_turn/updated_turn not tied to the turn (not claimed) |
| H10_hyp_status_corroborated_unjustified | doc | ACCEPT | ACCEPT | = | status is player/engine bookkeeping; C-1 class |
| H11_hyp_empty | accept | ACCEPT | ACCEPT | = |  |
| H12_hyp_Heard_unknown_from_location | refuse | REFUSE: hypothesis 'H1' names place 'Atlantis', which the case does not contain (I-15) | REFUSE: hypothesis 'H1' names place 'Atlantis', which the case does not contain (I-15) |  |  |
| H13_hyp_Attr_unknown_entity | refuse | REFUSE: hypothesis 'H1' names entity 'Atlantis', which the case does not contain (I-15 | REFUSE: hypothesis 'H1' names entity 'Atlantis', which the case does not contain (I-15 |  |  |
| H14_hyp_in_conversation_turn_valid | accept | ACCEPT | ACCEPT | = |  |
| H15_hyp_against_unknown_ref | refuse | REFUSE: HypothesisChanged rests on 'S99999', which the player does not hold | REFUSE: HypothesisChanged rests on 'S99999', which the player does not hold |  |  |
| K1_told_unknown_actor_prop | refuse | REFUSE: KnowledgeAdded 'K:told-1' names actor 'Ghost', which the case does not contain | REFUSE: KnowledgeAdded 'K:told-1' names actor 'Ghost', which the case does not contain |  |  |
| K2_told_id_collides_with_sealed | doc | ACCEPT | ACCEPT | = | colliding id silently ignored by with_overlay; inert |
| K3_told_prop_known | accept | ACCEPT | ACCEPT | = |  |
| K4_told_two_entries_same_id_diff_content | refuse | REFUSE: turn does not fold: KnowledgeAdded id K:told-1 already added with different co | REFUSE: turn does not fold: KnowledgeAdded id K:told-1 already added with different co |  |  |
| K5_told_trust_boundary_equal | accept | ACCEPT | ACCEPT | = |  |
| K6_told_over_trust | refuse | REFUSE: KnowledgeAdded 'K:told-1': reliability exceeds David's trust in the detective  | REFUSE: KnowledgeAdded 'K:told-1': reliability exceeds David's trust in the detective  |  |  |
| K7_claim_grounded_in_told_entry_listed_before_claim | accept | ACCEPT | ACCEPT | = |  |
| K8_claim_grounded_in_told_entry_listed_after_claim | refuse | REFUSE: claim 'c:own' is grounded in 'K:told-1', which resolves to nothing (I-8) | REFUSE: claim 'c:own' is grounded in 'K:told-1', which resolves to nothing (I-8) |  |  |
| L1_stmt_scope_layer_9 | refuse | REFUSE: ClaimMade 'S00019' is scoped to a secret its speaker does not own, or to a lay | REFUSE: ClaimMade 'S00019' is scoped to a secret its speaker does not own, or to a lay |  |  |
| L2_stmt_scope_negative | refuse | REFUSE: ClaimMade 'S00019' is scoped to a secret its speaker does not own, or to a lay | REFUSE: ClaimMade 'S00019' is scoped to a secret its speaker does not own, or to a lay |  |  |
| L3_stmt_scope_huge | refuse | REFUSE: ClaimMade 'S00019' is scoped to a secret its speaker does not own, or to a lay | REFUSE: ClaimMade 'S00019' is scoped to a secret its speaker does not own, or to a lay |  |  |
| L4_stmt_scope_foreign | refuse | REFUSE: ClaimMade 'S00019' is scoped to a secret its speaker does not own, or to a lay | REFUSE: ClaimMade 'S00019' is scoped to a secret its speaker does not own, or to a lay |  |  |
| L5_stmt_scope_unknown_secret | refuse | REFUSE: ClaimMade 'S00019' is scoped to a secret its speaker does not own, or to a lay | REFUSE: ClaimMade 'S00019' is scoped to a secret its speaker does not own, or to a lay |  |  |
| L6_stmt_scope_layer0 | accept | ACCEPT | ACCEPT | = |  |
| L7_stmt_scope_layer1 | accept | ACCEPT | ACCEPT | = |  |
| L8_stmt_scope_layer_2_exactly_len | refuse | REFUSE: ClaimMade 'S00019' is scoped to a secret its speaker does not own, or to a lay | REFUSE: ClaimMade 'S00019' is scoped to a secret its speaker does not own, or to a lay |  |  |
| L9_stmt_scope_bool_index | refuse | REFUSE: ClaimMade does not round-trip | REFUSE: ClaimMade payload carries fields or values the schema does not |  |  |
| L10_stmt_scope_layer_not_yet_reached | doc | ACCEPT | ACCEPT | = | in-range but unreached layer (David is at layer 0; layer 1 is in range) |
| M1_meta_attempt_own | accept | ACCEPT | ACCEPT | = |  |
| M2_suspicion_None_target | accept | ACCEPT | ACCEPT | = |  |
| M3_suspicion_unknown | refuse | REFUSE: SuspicionShift names unknown actor 'Ghost' | REFUSE: SuspicionShift names unknown actor 'Ghost' |  |  |
| M4_pressure_own_secret_max | doc | ACCEPT | ACCEPT | = | C-1(b): value nobody computed |
| M5_pressure_foreign_secret | refuse | REFUSE: PressureChange names secret 'S_Elena', which David does not own | REFUSE: PressureChange names secret 'S_Elena', which David does not own |  |  |
| M6_trust_to_max | doc | ACCEPT | ACCEPT | = | C-1 |
| M7_accusation_in_conversation | doc | ACCEPT | ACCEPT | = | C-1 |
| M8_accusation_unknown | refuse | REFUSE: Accusation of 'Ghost', who is not in the candidate domain | REFUSE: Accusation of 'Ghost', who is not in the candidate domain |  |  |
| M9_case_solved_no_accusation | doc | ACCEPT | ACCEPT | = | PN-10 / C-1 |
| M10_turn_committed_character_Ghost | refuse | REFUSE: TurnCommitted names unknown character 'Ghost' | REFUSE: TurnCommitted names unknown character 'Ghost' |  |  |
| M11_genuine_david | accept | ACCEPT | ACCEPT | = |  |
| M12_genuine_elena_present | accept | ACCEPT | ACCEPT | = |  |
| N1_recall_Elena_in_exploration_turn | refuse | REFUSE: MemoryRecall names Elena's memory 'MElena0001', not about this turn's addresse | REFUSE: MemoryRecall names Elena's memory 'MElena0001', not about this turn's addresse |  |  |
| N1b_recall_David_in_exploration_turn | refuse | REFUSE: MemoryRecall names David's memory 'MDavid0001', not about this turn's addresse | REFUSE: MemoryRecall names David's memory 'MDavid0001', not about this turn's addresse |  |  |
| N1d_peel_turn_with_DAVID_recall_in_middle | refuse | REFUSE: MemoryRecall names David's memory 'MDavid0001', not about this turn's addresse | REFUSE: MemoryRecall names David's memory 'MDavid0001', not about this turn's addresse |  |  |
| N1e_peel_turn_with_DAVID_belief_last | refuse | REFUSE: BeliefRevised names David's belief 'BDavid0001', not about this turn's address | REFUSE: BeliefRevised names David's belief 'BDavid0001', not about this turn's address |  |  |
| N1f_peel_turn_with_DAVID_told_first_position | refuse | REFUSE: KnowledgeAdded for 'David', not about this turn's addressee (Elena) | REFUSE: KnowledgeAdded for 'David', not about this turn's addressee (Elena) |  |  |
| N2a_recall_Elena_in_David_turn | refuse | REFUSE: MemoryRecall names Elena's memory 'MElena0001', not about this turn's addresse | REFUSE: MemoryRecall names Elena's memory 'MElena0001', not about this turn's addresse |  |  |
| N2b_belief_Elena_in_David_turn | refuse | REFUSE: BeliefRevised names Elena's belief 'BElena0001', not about this turn's address | REFUSE: BeliefRevised names Elena's belief 'BElena0001', not about this turn's address |  |  |
| N2c_belief_David_in_exploration_turn | refuse | REFUSE: BeliefRevised names David's belief 'BDavid0001', not about this turn's address | REFUSE: BeliefRevised names David's belief 'BDavid0001', not about this turn's address |  |  |
| N3_told_Elena_in_David_turn | refuse | REFUSE: KnowledgeAdded for 'Elena', not about this turn's addressee (David) | REFUSE: KnowledgeAdded for 'Elena', not about this turn's addressee (David) |  |  |
| N4_told_David_in_exploration_turn | refuse | REFUSE: KnowledgeAdded for 'David', not about this turn's addressee (None) | REFUSE: KnowledgeAdded for 'David', not about this turn's addressee (None) |  |  |
| N5_corrected_field_not_distorted | refuse | REFUSE: MemoryCorrected names field 'any_field_at_all', which memory 'MDavid0001' does | REFUSE: MemoryCorrected names field 'any_field_at_all', which memory 'MDavid0001' does |  |  |
| N5b_corrected_Elena_memory_in_David_turn | refuse | REFUSE: MemoryCorrected names Elena's memory 'MElena0001', not about this turn's addre | REFUSE: MemoryCorrected names Elena's memory 'MElena0001', not about this turn's addre |  |  |
| N5c_corrected_in_exploration_turn | refuse | REFUSE: MemoryCorrected names David's memory 'MDavid0001', not about this turn's addre | REFUSE: MemoryCorrected names David's memory 'MDavid0001', not about this turn's addre |  |  |
| N5d_corrected_field_of_a_memory_with_no_distortions | refuse | REFUSE: MemoryCorrected names field 'interval', which memory 'MDavid0002' does not dis | REFUSE: MemoryCorrected names field 'interval', which memory 'MDavid0002' does not dis |  |  |
| N6_corrected_structured_value | doc | ACCEPT | ACCEPT | = | KNOWN-DEBT: corrected_value is Any |
| N6b_corrected_None_value | doc | ACCEPT | ACCEPT | = |  |
| N6c_corrected_float_value | refuse | REFUSE: MemoryCorrected carries a float at corrected_value (I-17) | REFUSE: MemoryCorrected carries a float at corrected_value (I-17) |  |  |
| N6d_corrected_valid_interval | accept | ACCEPT | ACCEPT | = |  |
| N8x_exact_cover_delta | refuse | REFUSE: CoverStateDelta slips_used names a slip David does not have | REFUSE: CoverStateDelta slips_used names a slip David does not have |  |  |
| N9x_exact_topics_minus_100 | refuse | REFUSE: CoverStateDelta carries a negative counter | REFUSE: CoverStateDelta carries a negative counter |  |  |
| N10a_incidental_Elena_in_David_turn | refuse | REFUSE: IncidentalPinned by 'Elena', who is not this turn's addressee | REFUSE: IncidentalPinned by 'Elena', who is not this turn's addressee |  |  |
| N10b_incidental_David_in_exploration_turn | refuse | REFUSE: IncidentalPinned by 'David', who is not this turn's addressee | REFUSE: IncidentalPinned by 'David', who is not this turn's addressee |  |  |
| N10c_incidental_scope_layer_9 | refuse | REFUSE: IncidentalPinned is scoped to a secret its speaker does not own, or to a layer | REFUSE: IncidentalPinned is scoped to a secret its speaker does not own, or to a layer |  |  |
| N10d_incidental_scope_negative_layer | refuse | REFUSE: IncidentalPinned is scoped to a secret its speaker does not own, or to a layer | REFUSE: IncidentalPinned is scoped to a secret its speaker does not own, or to a layer |  |  |
| N10e_incidental_scope_huge_layer | refuse | REFUSE: IncidentalPinned is scoped to a secret its speaker does not own, or to a layer | REFUSE: IncidentalPinned is scoped to a secret its speaker does not own, or to a layer |  |  |
| N10f_incidental_scope_foreign_secret | refuse | REFUSE: IncidentalPinned is scoped to a secret its speaker does not own, or to a layer | REFUSE: IncidentalPinned is scoped to a secret its speaker does not own, or to a layer |  |  |
| N10g_incidental_scope_unknown_secret | refuse | REFUSE: IncidentalPinned is scoped to a secret its speaker does not own, or to a layer | REFUSE: IncidentalPinned is scoped to a secret its speaker does not own, or to a layer |  |  |
| N10h_incidental_scope_real_layer | accept | ACCEPT | ACCEPT | = |  |
| N10i_incidental_scope_layer0 | accept | ACCEPT | ACCEPT | = |  |
| N10j_incidental_unresolvable_entity | doc | ACCEPT | ACCEPT | = | KNOWN-DEBT: IncidentalPinned.entity free text |
| N10k_incidental_unscoped_valid | accept | ACCEPT | ACCEPT | = |  |
| N10l_incidental_scope_bool_index | refuse | REFUSE: IncidentalPinned does not round-trip | REFUSE: IncidentalPinned payload carries fields or values the schema does not |  |  |
| N12x_exact_Lied_Ghost_S99999_and_Planted_E_nope | refuse | REFUSE: hypothesis 'H1': Lied names statement 'S99999', which the player does not hold | REFUSE: hypothesis 'H1': Lied names statement 'S99999', which the player does not hold |  |  |
| N13_claim_At_Ghost_Atlantis | refuse | REFUSE: claim 'c:own' names actor 'Ghost', which the case does not contain (I-15) | REFUSE: claim 'c:own' names actor 'Ghost', which the case does not contain (I-15) |  |  |
| N19_recall_turn_id_999 | refuse | REFUSE: MemoryRecall carries turn_id 999, inside turn 19 | REFUSE: MemoryRecall carries turn_id 999, inside turn 19 |  |  |
| N19b_recall_record_turn_id_999 | refuse | REFUSE: MemoryRecall carries turn_id 999, inside turn 19 | REFUSE: MemoryRecall carries turn_id 999, inside turn 19 |  |  |
| N19c_belief_revision_turn_id_999 | refuse | REFUSE: BeliefRevised carries turn_id 999, inside turn 19 | REFUSE: BeliefRevised carries turn_id 999, inside turn 19 |  |  |
| N19d_corrected_turn_id_999 | refuse | REFUSE: MemoryCorrected carries turn_id 999, inside turn 19 | REFUSE: MemoryCorrected carries turn_id 999, inside turn 19 |  |  |
| N19e_recall_turn_id_negative | refuse | REFUSE: MemoryRecall carries turn_id -1, inside turn 19 | REFUSE: MemoryRecall carries turn_id -1, inside turn 19 |  |  |
| N19f_recall_turn_id_previous_turn | refuse | REFUSE: MemoryRecall carries turn_id 18, inside turn 19 | REFUSE: MemoryRecall carries turn_id 18, inside turn 19 |  |  |
| N19g_told_by_detective_turn_999 | doc | ACCEPT | ACCEPT | = | turn-ish field of InvestigationTold not checked (not claimed) |
| N19h_told_acquired_at_huge | doc | ACCEPT | ACCEPT | = |  |
| P1_recall_addressee | accept | ACCEPT | ACCEPT | = |  |
| P2_belief_addressee | accept | ACCEPT | ACCEPT | = |  |
| P3_told_addressee | accept | ACCEPT | ACCEPT | = |  |
| P4_all_four_addressee_rows | accept | ACCEPT | ACCEPT | = |  |
| P5_recall_Elena_in_Elena_turn | accept | ACCEPT | ACCEPT | = |  |
| P6_epistemic_before_claimmade | accept | ACCEPT | ACCEPT | = |  |
| P7_epistemic_after_hearing | accept | ACCEPT | ACCEPT | = |  |
| P8_peel_turn_with_Elena_recall_last | accept | ACCEPT | ACCEPT | = |  |
| P9_peel_turn_with_Elena_recall_between_peel_and_retraction | accept | ACCEPT | ACCEPT | = |  |
| PL0_genuine_peel | accept | ACCEPT | ACCEPT | = |  |
| PL1_peel_claim_other_proposition | refuse | REFUSE: LayerPeel of 'S_Elena' to layer 1 is not voiced by the turn's statement | REFUSE: LayerPeel of 'S_Elena' to layer 1 is not voiced by the turn's statement |  |  |
| PL2_peel_claim_other_grounding | refuse | REFUSE: LayerPeel of 'S_Elena' to layer 1 is not voiced by the turn's statement | REFUSE: LayerPeel of 'S_Elena' to layer 1 is not voiced by the turn's statement |  |  |
| PL3_peel_claim_other_sincerity | refuse | REFUSE: LayerPeel of 'S_Elena' to layer 1 is not voiced by the turn's statement | REFUSE: LayerPeel of 'S_Elena' to layer 1 is not voiced by the turn's statement |  |  |
| PL4_peel_claim_other_source | refuse | REFUSE: LayerPeel of 'S_Elena' to layer 1 is not voiced by the turn's statement | REFUSE: LayerPeel of 'S_Elena' to layer 1 is not voiced by the turn's statement |  |  |
| PL5_peel_claim_other_modality | refuse | REFUSE: LayerPeel of 'S_Elena' to layer 1 is not voiced by the turn's statement | REFUSE: LayerPeel of 'S_Elena' to layer 1 is not voiced by the turn's statement |  |  |
| PL6_peel_claim_other_confidence | refuse | REFUSE: LayerPeel of 'S_Elena' to layer 1 is not voiced by the turn's statement | REFUSE: LayerPeel of 'S_Elena' to layer 1 is not voiced by the turn's statement |  |  |
| PL7_peel_extra_claim_beside_owed | doc | ACCEPT | ACCEPT | = | extra claims beside the owed ones are accepted |
| PL8_peel_claims_reversed | doc | ACCEPT | ACCEPT | = | claim order not checked (engine order is the plan's) |
| PL9_peel_claim_id_changed | refuse | REFUSE: LayerPeel of 'S_Elena' to layer 1 is not voiced by the turn's statement | REFUSE: LayerPeel of 'S_Elena' to layer 1 is not voiced by the turn's statement |  |  |
| PL10_peel_duplicate_owed_claim | refuse | REFUSE: ClaimMade 'S00019' carries two claims with one id | REFUSE: ClaimMade 'S00019' carries two claims with one id |  |  |
| PL11_peel_act_confession | doc | ACCEPT | ACCEPT | = | CONFESSION is an allowed act on a peel turn |
| PL12_peel_no_owed_claims | refuse | REFUSE: LayerPeel of 'S_Elena' to layer 1 is not voiced by the turn's statement | REFUSE: LayerPeel of 'S_Elena' to layer 1 is not voiced by the turn's statement |  |  |
| PL13_peel_before_claimmade | accept | ACCEPT | ACCEPT | = |  |
| PL14_retraction_before_claimmade | refuse | REFUSE: ClaimRetracted by 'S00019', which this turn did not commit | REFUSE: ClaimRetracted by 'S00019', which this turn did not commit |  |  |
| PL15_minds_rows_before_claimmade | accept | ACCEPT | ACCEPT | = |  |
| PL16_heard_before_claimmade | refuse | REFUSE: StatementHeard names 'S00019', which this turn did not commit | REFUSE: StatementHeard names 'S00019', which this turn did not commit |  |  |
| PL17_second_peel_row_same_secret | refuse | REFUSE: LayerPeel 1->2 does not continue the recorded cover state | REFUSE: LayerPeel 1->2 does not continue the recorded cover state |  |  |
| PL18_peel_uncommitted_retraction_target | refuse | REFUSE: ClaimRetracted by 'S99999', which this turn did not commit | REFUSE: ClaimRetracted by 'S99999', which this turn did not commit |  |  |
| R2a_claim_At_interval_2_40 | doc | ACCEPT | ACCEPT | = | NEW: interval bound not checked; engine feasibility enumerates ticks |
| R2b_claim_At_negative_interval | doc | ACCEPT | ACCEPT | = | NEW |
| R2c_claim_Heard_interval_2_40 | doc | ACCEPT | ACCEPT | = | NEW |
| R2d_hyp_At_interval_2_40 | doc | ACCEPT | ACCEPT | = | NEW |
| R2e_told_At_interval_2_40 | doc | ACCEPT | ACCEPT | = | NEW |
| R2f_claim_Moved_t_2_40 | doc | ACCEPT | ACCEPT | = | NEW |
| V01_claim_Said_nesting_unknown_actor | refuse | REFUSE: claim 'c:own' names actor 'Ghost', which the case does not contain (I-15) | REFUSE: claim 'c:own' names actor 'Ghost', which the case does not contain (I-15) |  |  |
| V02_claim_Said_nesting_unknown_place | refuse | REFUSE: claim 'c:own' names place 'Atlantis', which the case does not contain (I-15) | REFUSE: claim 'c:own' names place 'Atlantis', which the case does not contain (I-15) |  |  |
| V03_claim_Said_double_nested_unknown | refuse | REFUSE: claim 'c:own' names object 'Excalibur', which the case does not contain (I-15) | REFUSE: claim 'c:own' names object 'Excalibur', which the case does not contain (I-15) |  |  |
| V04_claim_Said_unknown_speaker | refuse | REFUSE: claim 'c:own' names actor 'Ghost', which the case does not contain (I-15) | REFUSE: claim 'c:own' names actor 'Ghost', which the case does not contain (I-15) |  |  |
| V05_claim_Saw_unknown_observer | refuse | REFUSE: claim 'c:own' names actor 'Ghost', which the case does not contain (I-15) | REFUSE: claim 'c:own' names actor 'Ghost', which the case does not contain (I-15) |  |  |
| V06_claim_Saw_unknown_location | refuse | REFUSE: claim 'c:own' names place 'Atlantis', which the case does not contain (I-15) | REFUSE: claim 'c:own' names place 'Atlantis', which the case does not contain (I-15) |  |  |
| V07_claim_Saw_literal_subject_Atlantis | doc | ACCEPT | ACCEPT | = | Saw.subject is a literal by design |
| V08_claim_Heard_unknown_from_location | refuse | REFUSE: claim 'c:own' names place 'Atlantis', which the case does not contain (I-15) | REFUSE: claim 'c:own' names place 'Atlantis', which the case does not contain (I-15) |  |  |
| V09_claim_Heard_unknown_identified_actor | refuse | REFUSE: claim 'c:own' names actor 'Ghost', which the case does not contain (I-15) | REFUSE: claim 'c:own' names actor 'Ghost', which the case does not contain (I-15) |  |  |
| V10_claim_Heard_unknown_observer | refuse | REFUSE: claim 'c:own' names actor 'Ghost', which the case does not contain (I-15) | REFUSE: claim 'c:own' names actor 'Ghost', which the case does not contain (I-15) |  |  |
| V11_claim_Moved_unknown_from | refuse | REFUSE: claim 'c:own' names place 'Atlantis', which the case does not contain (I-15) | REFUSE: claim 'c:own' names place 'Atlantis', which the case does not contain (I-15) |  |  |
| V12_claim_Moved_unknown_to | refuse | REFUSE: claim 'c:own' names place 'Atlantis', which the case does not contain (I-15) | REFUSE: claim 'c:own' names place 'Atlantis', which the case does not contain (I-15) |  |  |
| V13_claim_Moved_unknown_actor | refuse | REFUSE: claim 'c:own' names actor 'Ghost', which the case does not contain (I-15) | REFUSE: claim 'c:own' names actor 'Ghost', which the case does not contain (I-15) |  |  |
| V14_claim_Rel_unknown_b | refuse | REFUSE: claim 'c:own' names actor 'Ghost', which the case does not contain (I-15) | REFUSE: claim 'c:own' names actor 'Ghost', which the case does not contain (I-15) |  |  |
| V15_claim_Solution_unknown_murderer | refuse | REFUSE: claim 'c:own' names actor 'Ghost', which the case does not contain (I-15) | REFUSE: claim 'c:own' names actor 'Ghost', which the case does not contain (I-15) |  |  |
| V16_claim_Solution_unknown_location | refuse | REFUSE: claim 'c:own' names place 'Atlantis', which the case does not contain (I-15) | REFUSE: claim 'c:own' names place 'Atlantis', which the case does not contain (I-15) |  |  |
| V17_claim_Attr_unknown_entity | refuse | REFUSE: claim 'c:own' names entity 'Atlantis', which the case does not contain (I-15) | REFUSE: claim 'c:own' names entity 'Atlantis', which the case does not contain (I-15) |  |  |
| V18_claim_Incidental_unknown_entity | refuse | REFUSE: claim 'c:own' names entity 'Atlantis', which the case does not contain (I-15) | REFUSE: claim 'c:own' names entity 'Atlantis', which the case does not contain (I-15) |  |  |
| V19_claim_Attr_known_actor | accept | ACCEPT | ACCEPT | = |  |
| V20_claim_Incidental_known_object | accept | ACCEPT | ACCEPT | = |  |
| V21_claim_ObjectAt_unknown_holder | refuse | REFUSE: claim 'c:own' names entity 'Atlantis', which the case does not contain (I-15) | REFUSE: claim 'c:own' names entity 'Atlantis', which the case does not contain (I-15) |  |  |
| V22_claim_ObjectAt_holder_is_an_object | doc | ACCEPT | ACCEPT | = | ambiguous slot accepted against any pool |
| V22b_claim_ObjectAt_holder_known_place | accept | ACCEPT | ACCEPT | = |  |
| V22c_claim_ObjectAt_holder_known_actor | accept | ACCEPT | ACCEPT | = |  |
| V23_claim_Did_unknown_object | refuse | REFUSE: claim 'c:own' names object 'Excalibur', which the case does not contain (I-15) | REFUSE: claim 'c:own' names object 'Excalibur', which the case does not contain (I-15) |  |  |
| V24_claim_Did_unknown_target_actor | refuse | REFUSE: claim 'c:own' names actor 'Ghost', which the case does not contain (I-15) | REFUSE: claim 'c:own' names actor 'Ghost', which the case does not contain (I-15) |  |  |
| V25_claim_Did_unknown_location | refuse | REFUSE: claim 'c:own' names place 'Atlantis', which the case does not contain (I-15) | REFUSE: claim 'c:own' names place 'Atlantis', which the case does not contain (I-15) |  |  |
| V26_claim_DidNot_unknown_object | refuse | REFUSE: claim 'c:own' names object 'Excalibur', which the case does not contain (I-15) | REFUSE: claim 'c:own' names object 'Excalibur', which the case does not contain (I-15) |  |  |
| V27_claim_ObjectState_unknown_object | refuse | REFUSE: claim 'c:own' names object 'Excalibur', which the case does not contain (I-15) | REFUSE: claim 'c:own' names object 'Excalibur', which the case does not contain (I-15) |  |  |
| V28_claim_State_unknown_actor | refuse | REFUSE: claim 'c:own' names actor 'Ghost', which the case does not contain (I-15) | REFUSE: claim 'c:own' names actor 'Ghost', which the case does not contain (I-15) |  |  |
| V29_claim_Has_unknown_actor | refuse | REFUSE: claim 'c:own' names actor 'Ghost', which the case does not contain (I-15) | REFUSE: claim 'c:own' names actor 'Ghost', which the case does not contain (I-15) |  |  |
| V30_claim_Attitude_unknown_b | refuse | REFUSE: ClaimMade carries a float at statement.claims.proposition.intensity (I-17) | REFUSE: ClaimMade carries a float at statement.claims.proposition.intensity (I-17) |  |  |
| V31_claim_Motive_unknown_victim | refuse | REFUSE: ClaimMade carries a float at statement.claims.proposition.strength (I-17) | REFUSE: ClaimMade carries a float at statement.claims.proposition.strength (I-17) |  |  |
| V32_claim_At_known | accept | ACCEPT | ACCEPT | = |  |
| V33_claim_NotAt_unknown_place | refuse | REFUSE: claim 'c:own' names place 'Atlantis', which the case does not contain (I-15) | REFUSE: claim 'c:own' names place 'Atlantis', which the case does not contain (I-15) |  |  |
| V34_claim_victim_Harold_dead_actor_known | accept | ACCEPT | ACCEPT | = |  |
| V35_claim_own_unchanged | accept | ACCEPT | ACCEPT | = |  |
| V36_two_claims_one_id | refuse | REFUSE: ClaimMade 'S00019' carries two claims with one id | REFUSE: ClaimMade 'S00019' carries two claims with one id |  |  |
| V37_two_claims_distinct_ids_same_prop | accept | ACCEPT | ACCEPT | = |  |
| V38_claim_id_collides_with_earlier_statement_claim | refuse | ACCEPT | ACCEPT | = | my expectation was wrong: claim ids legitimately repeat across statements (genuine base has C_David_L0 x4); accepting is correct |
| V39_claim_grounding_empty | doc | ACCEPT | ACCEPT | = | grounding may be empty |
| V40_claim_grounding_unknown_id | refuse | REFUSE: claim 'c:own' is grounded in 'K:nope', which resolves to nothing (I-8) | REFUSE: claim 'c:own' is grounded in 'K:nope', which resolves to nothing (I-8) |  |  |
| X1_two_claims_one_id_different_propositions | refuse | REFUSE: ClaimMade 'S00019' carries two claims with one id | REFUSE: ClaimMade 'S00019' carries two claims with one id |  |  |
| X2_ClaimMade_retracted_by_set | refuse | REFUSE: ClaimMade 'S00019' is born retracted | REFUSE: ClaimMade 'S00019' is born retracted |  |  |


## 9. Re-check of the F-1 fix (tree aedb1c39...)

Reviewer: same, still read-only on `D:\Murder Mystery`; scratch work in `...\r1-review\` (`work2\` for saves, `mut2\` for the private tree copies).
Narrow scope: is F-1 fixed, with no false refusals and no new BLOCKING/IMPORTANT finding.

### 9.0 Verdict

**Is F-1 fixed, with no false refusals and no new BLOCKING/IMPORTANT finding on this tree: YES.**
Every time slot the fold can reach (`interval` of 11 proposition kinds, `Moved.t`, `Said.t`, nested `Said` to depth 3) is bounded to
`[0, t_investigation]` at both `Save.append` and a re-chained `Save.open`; 0 false refusals in 20,254 genuine turns; the 3,620 authored slots are
all inside the clock. Three NON-BLOCKING notes (a surviving mutant, F1-a; a future-consumer note, F1-b; a documented-class note, F1-c).

| file | hash before = after (recorded by me) |
|---|---|
| `eidolon/store.py` | `aedb1c39090260433c6c85ccf27c42b138c0532bc44047184155552b75b2b7cb` |
| `tests/test_persistence.py` | `197c8f04956e917976fc683bf0c9482d2f54e9a3bf6d544ad245a35d41c6c93c` |
| `tests/persistence_mutation_check.py` | `dc58bfc185f9107226f44fcca8a67630a7970decfd1efeb98a6e6f420a10de82` |

All three match the coordinator's values. A `cmp` of all 187 files of `eidolon/`, `tests/`, `cases/` against my start-of-review copy shows exactly
those three differ and nothing else. The diff is what was described: `_check_times` (13 lines) called at the end of `_check_proposition`; 7
forgeries + 1 control test + 8 mutants + one extra import line.

### 9.1 My own F-1 reproductions (R2a-R2f), full SQLite + hash-chain run, both boundaries

`f1_repro.py`: each case is built from a writable copy, offered to `Save.append` (state hash, `last_seq`, `last_hash`, rows and the whole `meta`
compared before/after), then David/Elena are asked four more times and the answers appended, then the same events are written as a re-chained extra
turn and opened with `Save.open`. 14 refusals + 4 boundary acceptances:

| case | `Save.append` | nothing mutated | 4 later asks (David, Elena) | re-chained `Save.open` |
|---|---|---|---|---|
| R2a claim `At [0, 2^40)` | REFUSE "interval (0, 1099511627776), outside the case's clock [0, 120]" | yes | 4/4 ok, 0.23 s | same refusal |
| R2b claim `At [-2^40, 0)` | REFUSE (same guard) | yes | 4/4 | same |
| R2c claim `Heard [0, 2^40)` | REFUSE | yes | 4/4 | same |
| R2d hypothesis `At [0, 2^40)` | REFUSE ("hypothesis 'H1' has interval ...") | yes | 4/4 | same |
| R2e `KnowledgeAdded` `At [0, 2^40)` | REFUSE ("KnowledgeAdded 'K:told-1' has interval ...") | yes | 4/4 | same |
| R2f claim `Moved t=2^40` | REFUSE "has time 1099511627776, outside the case's clock" | yes | 4/4 | same |
| S1 claim `Said(t=5, At [0,2^40))` | REFUSE | yes | 4/4 | same |
| S2 claim `Said(Said(At [-1,5)))` | REFUSE | yes | 4/4 | same |
| S3 hypothesis `Said(t=2^40)` | REFUSE ("has time ...") | yes | 4/4 | same |
| S4 told `Said(Said(t=H+1))` | REFUSE ("has time 121") | yes | 4/4 | same |
| E1-E5 `NotAt [0,H+1)`, `Did [-1,H)`, `Saw [H,H+1)` (hyp), `ObjectAt [0,10^9)` (told), `Solution [0,H+1)` | REFUSE (same guard) | yes | 4/4 | same |
| OK1 claim `At [0, H)` (whole clock) | ACCEPT | - | 4/4 | ACCEPT, then an ask on the loaded save is not rejected |
| OK2 claim `Moved t=H` | ACCEPT | - | 4/4 | ACCEPT |
| OK3 hypothesis `Said(t=0, Said(t=H, At [H-1,H)))` | ACCEPT | - | 4/4 | ACCEPT |
| OK4 told `At [0, 1)` | ACCEPT | - | 4/4 | ACCEPT |

(`H = 120`.) Also: the widest legal claims of every kind `feasible` enumerates (`At`, `NotAt`, `Saw` identified, `Heard` with a place, all `[0, 120)`, plus
`Moved t=120`) in one statement: appended, then 8 later David turns all ok in 0.47 s total (before the fix a single 2^40 claim killed the next turn
with `MemoryError`). A `Did(touch, Decanter)` claim over `[0,120)` is accepted, then every later David turn is rejected `CONTRADICTS_PRIOR:<that claim>`
- a graceful violation, no crash, and not a time-slot issue: it is the documented C-1 class (an in-structure claim that contradicts the speaker's
standing claims; see F1-c).

The earlier 194-attack battery was re-run on the new tree: 186 identical outcomes, the 6 R2 attacks flipped from ACCEPT/ACCEPT to REFUSE/REFUSE with
the new message, the 2 `H4` attacks need the partial base and were re-run on it (REFUSE/REFUSE as before). No refused append mutated anything, no
append-vs-load hash difference, no raw exception, none of the 42 "must accept" attacks refused.

### 9.2 Variants (1,194 inputs, both boundaries emulated exactly where they differ)

`grid_f1.py`: append = `_encode` (write-time validation) + `fold_turn` on the caller's objects; load = canonical row text -> `_decode` + `fold_turn` on the
decoded objects (no `_encode`, as in a re-chained file). 398 cases x 3 contexts (claim, hypothesis, `KnowledgeAdded`):

* interval kinds: `At, NotAt, Did, DidNot, Saw, Heard, Has, ObjectAt, ObjectState, State, Solution` x 27 values: valid `(0,1) (0,H) (H-1,H) (60,61)`;
  out of clock `(0,H+1) (H,H+1) (H+1,H+2) (-1,5) (-1,H) (-5,-1) (0,2^40) (-2^40,0) (2^70,2^70+1) (-1,2^63) (0,10^9)`; malformed, built with
  `model_construct` to bypass pydantic: `(5,5) (0,0) (H,H)` (start==end), reversed `(7,3) (H,0)`, bool `(False,True) (True,2)`, float `(0.0,5.0)`, str, length 3,
  length 1; and the same value as a `list` `[0,5]`.
* time kinds `Moved.t`, `Said.t` x 12 values: `0, 60, H` valid; `H+1, -1, 2^40, -2^40, 2^70` out of clock; bool True/False, float 5.0, str '5'.
* nesting: `Said` x1, x2, x3 around `At` with each interval value; `Said` x2/x3 around `Moved.t` values; the outer `Said.t` of the innermost and outer `Said`.

Result: **255 valid inputs accepted at both boundaries (no false refusal); 552 out-of-clock inputs refused by the clock guard at both boundaries
(the append message contains "outside the case's clock"); 387 malformed inputs refused at both (156 at both by the store, 231 at append by the store and at load by the
decoder); 0 accepted bad slots, 0 boundary disagreements, 0 raw exceptions.** A `list`-typed `[0,5]` is accepted (same canonical value as the tuple, inside the clock).
Inclusive both ends, as the coordinator noted: `(0,H)` and `Moved.t=H` accepted, `(0,H+1)` and `t=H+1` refused. `start==end` is already impossible: pydantic's
`Interval` validator refuses it at construction and at decode, so the guard's own `iv[0] < iv[1]` is redundant - confirmed by a private mutant `iv[0] <= iv[1]`
(`mB_interval_nonempty`): the whole grid is identical under it (equivalent mutant).

**Other unbounded numeric slots?** I grepped `ticks(`, `range(` and `while` over `eidolon/` (outside `gen/`). Consumers that iterate over claim, hypothesis or told data:
`world/feasibility.py` (`ticks(p.interval)` in `_compile`; `range(T)` with `T = case.t_investigation`), `world/facts.py` (`ticks(p.interval)` in
`truth_value`, `contradiction(..., case=...)`). Every other `ticks`/`range` consumer reads sealed case or package data (`world/perception`, `world/timeline`,
`world/state`, `solve/*`, `gen/*`) or iterates a graph bounded by data size (`admissibility`, `contradiction`, `weight`, `validator`, `space`). So, apart from
`interval` and `t`, no proposition slot is numeric: the rest are ids, enumerations (`ActionKind`), free strings, a bool (`Saw.identified`), and two floats
(`Attitude.intensity`, `Motive.strength`) that can never be stored (float rule). Non-proposition numerics that survive the fold are used arithmetically only:
`topics_probed` values (`count * REPEATED_PROBE_BP < CAP`), `refuse_streak` (`< 2`), bp fields (range-checked), `Hypothesis.created_turn/updated_turn`
and `KnowledgeEntry.acquired_at` (no reader, F-3). `MemoryCorrected.corrected_value` is `Any` and is not read anywhere (`current_distortion_value` has no caller),
see F1-b. Conclusion: no other unbounded slot remains that reaches a loop.

### 9.3 No false refusal

* **Genuine-turn sweep on the new tree**, same scripts as section 2: generic 12 jobs (4 cases x seeds 7, 11, 23, every living character, every held evidence and
  statement id presented in round 1, 13 query kinds incl. meta/coercion, hostile/provisional features) 11,256 turns; bots 44 jobs (greedy, cue, adversarial, murderer_peel,
  order-shuffled, bluff, random seeds 0/11/23/42/77, x 4 cases) 7,558 turns; all-16-kinds sweep with entity refs and tones, `GoTo`/`Take`/`Search` (2 cases) 352 turns;
  murderer deep path attempt (manor_wing_s4/s6) 1,088 turns. **Total 20,254 genuine turns, 0 `SaveRefusal`, 0 live!=folded state hashes, every reload equal.**
  Rows (generic + bots, 18,814 turns, 93,049 rows): `LayerPeel` 89, `ClaimRetracted` 159, `DetectiveModelUpdate` 7,788, `AccountHeard` 10, `CoverStateDelta` 14,739,
  `MetaAttemptLogged` 504. The murderer's account-token path and layer-0 peel again went through `Save.append` in all four cases (4 `murderer_peel` jobs).
* **The inclusive bound is exercised by real engine output.** I scanned every committed `ClaimMade` row of the 56 generic+bot saves: the smallest interval start is
  0 and the largest interval end is **120**, i.e. engine statements reach exactly `t_investigation` (David's `C_David_L0` ends at 120), and no committed claim has a
  `Moved`/`Said` proposition.
* **Static scan, independently confirmed: 3,620 slots, 0 outside `[0, 120]`.** Every `interval` of every proposition in knowledge (1,779), beliefs (1,706), secrets'
  protected propositions (25), cover claims (42), `concedes` (24) and evidence implications (44), over the four cases (751 + 792 + 1,129 + 948). `evidence_responses`,
  `deflections`, `slips`, `misleading_truths` and cover `frame` carry no proposition in these four cases, so those sources are vacuous here. There are **no authored `Moved` /
  `Said`** (0 `t` slots). Minimum start 0 (228 slots start at 0), maximum end 120 (**194 slots end exactly at 120**: knowledge 85, belief 85, cover claims 10, concedes 6,
  evidence implications 8), so an off-by-one bound would be caught by authored data itself. (The earlier 3,596 in section 2 excluded `concedes`; 3,596 + 24 = 3,620.)
* `Memory.distortions[].recalled_value` is the true interval shifted by up to 20 ticks and can leave `[0, 120]`, but it is never voiced: `retrieve_for_query` builds the claim from
  the belief's own proposition, and `recalled_value` is read only by `solve/distort.py`. Not a false-refusal source.
* Layer-scope on genuine output (frames added in memory, real engine turns): still 4/4 accepted.

### 9.4 Mutation spot-check of the 8 F1-* mutants

`mut2/` holds a byte copy of the new tree (hashes match); each mutant is applied to its own copy with an exact single anchor match, then
`python -m pytest tests/test_persistence.py -q -p no:cacheprovider -x -k "<k>"` from the copy (no `PYTHONPATH`). First, every selection passes unmutated (`rc 0`: 14, 2, 6, 2, 2, 2, 1, 1 passed).

| mutant | killed by | forgery under the mutant: append / load | kill type |
|---|---|---|---|
| F1-times-not-checked | `..._refused_at_append[F1_claim_interval_far_beyond...]` | all 7 F1 forgeries (claim x5, hypothesis, told): ACCEPT / ACCEPT | **real** (7 of 7) |
| F1-interval-start-unbounded | `[F1_claim_interval_starting_before_time_zero]` | ACCEPT / ACCEPT | **real** |
| F1-interval-end-unbounded | `[F1_claim_interval_far_beyond_the_clock]` | claim, hypothesis, told: ACCEPT / ACCEPT | **real** (3 of 3) |
| F1-interval-end-one-tick-too-lax | `[F1_claim_interval_ending_one_tick_past_the_clock]` | ACCEPT / ACCEPT | **real** |
| F1-moved-tick-unbounded | `[F1_claim_moved_at_a_tick_far_beyond_the_clock]` | ACCEPT / ACCEPT | **real** |
| F1-said-interval-not-descended-into | `[F1_claim_said_nesting_an_unbounded_interval]` | ACCEPT / ACCEPT | **real** |
| F1-clock-excludes-its-last-tick | `test_F1_the_clock_is_inclusive_at_both_ends_and_the_character_stays_playable` | n/a (false-refusal side) | **test failure, not a fixture error** |
| F1-moved-tick-excludes-the-last-tick | same test | n/a | **test failure, not a fixture error** |

The two false-refusal-side mutants: pytest exit 1, `0` collection/setup `ERROR` lines, one `FAILED tests/test_persistence.py::test_F1_the_clock_is_inclusive...`. The failure
is the store's own false refusal raised inside the test body: under `iv[1] < horizon` the very first `drive(s, 6)` append raises `SaveRefusal: claim 'C_David_L0' has interval (0, 120),
outside the case's clock [0, 120]` (an AUTHORED genuine claim refused); under `tick < horizon` the hypothesis with `Moved(t=H)` raises `SaveRefusal: hypothesis 'H1' has time 120`.
So the control now fails as a test failure for the right reason. Because all 7 forgeries are accepted when `_check_times` is removed, **each new forgery trips only the clock
guard** (no other guard refuses it).

**F1-a (NON-BLOCKING, test quality): a mutant the harness does not have survives.** Dropping the lower bound of the time check
(`not 0 <= tick <= horizon` -> `not tick <= horizon`, private copy `mA_tick_lower_bound`) passes all 25 tests of the selection `F1 or R1_claim_naming or R1_hypothesis_naming or
R1_knowledge_told or R1_claim_`, and no test in the file builds a negative `t` (grep for `t=-` finds none). In the grid, under that mutant `Moved.t = -1 / -2^40` and `Said.t = -1 / -2^40`
(plain and nested) are accepted at both boundaries as claim, hypothesis and told entry; the shipped code refuses them. The lower bound of `interval` is covered
(`F1-interval-start-unbounded`); the lower bound of `t` is not. Fix: one more forgery (`Moved(t=-1)`) and a mutant `("not 0 <= tick <= horizon", "not tick <= horizon")`.

### 9.5 The three changed files

* `_check_times` is correct: `getattr(prop, "interval"/"t")` hits exactly `Moved.t`, `Said.t` and the 11 interval kinds; `Lied`/`Planted` have neither; recursion through `Said.proposition`
  terminates at the JSON nesting limit; the message names the slot owner (`claim 'c:own'`, `hypothesis 'H1'`, `KnowledgeAdded 'K:told-1'`) and the clock. It runs after the entity checks, so a
  slot with both defects reports the entity first (cosmetic). It runs inside `_check_proposition`, which is the one function all three contexts (claim, hypothesis, `KnowledgeAdded`) call, so
  there is no per-context bypass; the per-context mutants (`R1-claim-proposition-unchecked` etc.) already pin each call site.
* No performance cost, no raw exception (fuzz-level: the 1,194-input grid has none), no change to the refusal protocol (`stage="fold"`).
* The new forgeries are single-defect (see 9.4). The control test is self-contained (own `Save.create`, own `drive`) and passes unmutated.
* The doc comment's "3,620 slots" is exact.

### 9.6 Findings for this re-check

| id | severity | one line |
|---|---|---|
| F-1 | **closed** | Unbounded time slots are refused at both boundaries for all 13 time-bearing kinds, nested `Said` included; no state change; later turns unaffected; inclusive bounds verified against authored and engine data. |
| F1-a | NON-BLOCKING | No test or mutant covers the lower bound of `Moved.t`/`Said.t`: dropping `0 <=` survives 25 selected tests and accepts negative `t` (real code refuses). Add `Moved(t=-1)` and the mutant. |
| F1-b | NON-BLOCKING (future consumer) | `MemoryCorrected.corrected_value` (`Any`, documented N6) can carry an `interval` for field `interval`; nothing reads it today (`current_distortion_value` has no caller), so inert. Whoever wires it must apply the same clock bound. |
| F1-c | NON-BLOCKING (documented class, not new) | An in-clock claim that contradicts the speaker's standing claims is accepted and makes every later turn of that character `CONTRADICTS_PRIOR` (graceful, no crash) - C-1 "structurally valid but unjustified". Only the crash/OOM form (F-1) was a store-integrity hole. |

No new BLOCKING or IMPORTANT finding. Carry-overs F-2 to F-9 from section 6 are unchanged by this fix (not re-tested beyond the 194-attack regression above).

Scripts for this section (all in `...\r1-review\`): `static_times.py`/`static_times2.py` (slot scan), `f1_repro.py` (R2a-R2f and variants), `grid_f1.py` (1,194 variants), `widest.py`,
`sweep.py` + `agg_f1.py` (sweeps with claim-interval stats), `extra_sweep.py`, `confess.py`, `frame_test.py`, `mut_f1.py` (8 F1 mutants + probes), `mut2\mA_tick_lower_bound`, `mut2\mB_interval_nonempty`,
`run_attacks.py` (194-attack regression, `results_f1_full.jsonl`).
