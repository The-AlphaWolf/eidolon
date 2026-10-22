# EIDOLON — Phase 7 repair report (persistence)

Date: 2026-10-17. Scope: the required fixes of `docs/EIDOLON-PHASE-7-HOSTILE-REVIEW.md` §8 (verdict B). Phase 8 was not started.
This is the author's record, not an independent re-audit: it is marked **ready for re-review**, not accepted.

## 1. What was repaired

| Finding | Repair | Where |
|---|---|---|
| **PB-1** (BLOCKING) recovery deleted verified rows | `truncate_to_last_valid` diagnoses with the loader itself (`_prepare` / `_replay`, each refusal carries a `stage`), recomputes the genesis from case seal + seed + schema + derived initial state, acts **only** on a chain break (cut to the start of the damaged turn, every complete turn kept) or a damaged genesis/head record (`reset_meta`, rows untouched), never touches a healthy save, **refuses with the reason** on a bundle / initial-state / fold refusal, proves the result loads **inside the same transaction** (rolled back otherwise), opens `mode=rw` so a missing path is never created, and has a dry run: `plan_truncation(path)` → `TruncationPlan`; without `confirm=True` the call raises `ConfirmationRequired` carrying that plan | `store.py` `_prepare`, `_replay`, `_plan_and_apply`, `plan_truncation`, `truncate_to_last_valid` |
| **PI-1** fold much thinner than claimed; load weaker than append | `fold_turn` is the one function both boundaries run, and it now ends with `check_state` (so load checks every turn, not only the last). Turn shape: a conversation turn has exactly one `ClaimMade` by the addressee for this turn, heard exactly once with exactly its accounts; a non-conversation turn has no statement, no peel, no minds rows. Peels must be voiced by a CONCESSION/CONFESSION statement that carries the layer's claims. Retractions only of the addressee's own standing statements, only in a turn that peeled, never self, only by this turn's statement. Grounding must be the speaker's own. All references resolve: secret ownership (`PressureChange`, `layer_scope`, peels), actors (`SuspicionShift`, `IncidentalPinned`, `TurnCommitted.character`), places and items (`LocationVisited`, `ItemTaken`), accusation targets, hypothesis support/against. `DetectiveModelUpdate` may add at most one item and rewrites nothing else. `TurnCommitted.action_id` must equal the row's. Duplicate rows and two statements in a turn are refused. `CaseSolved` cannot be overwritten. `run_goto_turn` / `run_take_turn` reject unknown places/items (`rejected=True`, nothing committed) | `store.py` `_fold_turn` & helpers; `decision/exploration.py` `known_locations/known_items`; `decision/turn.py` |
| **PI-2** floats / lossy hash | `_check_floats` at append **and** load: the only floats allowed are `Hypothesis.player_confidence` and `KnowledgeEntry.reliability`, each exactly on the basis-point grid (which implies 0..1); NaN/Infinity are not JSON here; `KnowledgeAdded.reliability ≤ trust` (I-25); a state that cannot be hashed is a load refusal; `eidolon replay` reports instead of crashing; `eidolon newsave` with a missing bundle exits 1 | `store.py` `_check_floats`, `_check_told`, `_loads`; `cli.py` |
| **PI-4** ABA | append compares `meta.head_hash` with `last_hash` inside `BEGIN IMMEDIATE` | `Save.append` |
| **PI-5** duplicate `action_id` | returns the existing turn: `AppendResult.ref = TurnRef(turn, first_seq, last_seq)`, `.same_events` says whether the retried events equal the committed ones; `Save.turn_for(action_id)` | `Save.append`, `Save.turn_for` |
| **PI-3** upcast then append bricks the save | a writable open of `schema_version < SCHEMA_VERSION` is refused; `schema_version` is bound into the genesis; the upcaster test now also asserts the refusal, and a native v2 save is appended to and reloaded | `_prepare`, `_genesis` |
| **PI-7** declared solution unconfirmed | `load_sealed_text` requires `proof.unique`, `survivors == [solution.murderer]`, `murder_loc == solution.location`, `window == solution.interval` | `solve/package.py` |
| **PI-6** derived initial world outside log and hash | `initial_digest(state)` (knowledge, beliefs, memories after boosts, personalities, initial character states; floats as millionths) is stored in `meta.initial_digest`, bound into the genesis, and checked on every load with its own refusal (stage `initial`); `meta.engine_version` is recorded. An engine that derives something else **refuses** the save; there is no converter (debt C-10) | `store.py` |
| PN-2, PN-13 (cheap, same code) | the stored payload text must equal the canonical text of what it parses to; non-canonical integers in `meta` are refused | `_valid_prefix`, `_prepare` |

## 2. Failing-first
There is no VCS in this tree, so "failing on the old code" is shown the way the project's mutation harness shows it: every guard added
here has a mutant in `tests/persistence_mutation_check.py` that restores the defect, and the guard's own test must fail for the right
reason (§4). The defect reproductions of the review (F1–F10, C1–C16, B7, E7) are the test bodies.

## 3. Tests added (`tests/test_persistence.py`)
`tests/test_persistence.py` grew from 59 to **174** tests (+115). Every `FORGERIES` entry (36) is offered twice: to `append` and, with a valid
re-chained hash chain, to `Save.open` — "refused at both boundaries". The negative control is a genuine peel turn. Groups:

* PB-1 (15 test cases, one is parametrized x4): healthy save never cut; damaged genesis costs no row; off-by-one head reset losslessly; damaged seed diagnosed, nothing deleted; fold-refused row reported, three
  confirmed calls change nothing; genesis-row-deleted / missing path (no file created) / NaN payload / file cut to 80 %; break between turns keeps the complete turn; break inside a
  turn drops only that turn; dry run writes nothing and equals the confirmed result; a repair that would not load is rolled back; genesis AND chain damaged is not guessed at.
* PI-1 (36 x 2 + 3): the forged turns above (C1…C19, X18-X24 of the review plus the peel-bound / other-secret cases), genuine peel accepted, case solved once, runners reject unknown places/items.
* PI-2: bp confidence hashed / no collision (X41), canonical state refuses a float (X42), NaN/Infinity/stray float in a stored payload, `replay` reports a hash failure, `newsave` missing bundle.
* PI-3: older save read-only + native v2 save appends and reloads; relabelling refused; the upcaster test also asserts the writable refusal. PN-13, PN-2.
* PI-4 (ABA at equal seq), PI-5 (turn returned, `same_events`, `turn_for`), X47, X30, X35, X36, X39 (hot journal left by a crashed subprocess: read-only open refuses and changes no byte).
* PI-6 (engine drift refused, meta records engine + digest, every derived store moves the digest), PI-7 (murderer / place / moment).

## 4. Mutation harness
`tests/persistence_mutation_check.py` was rewritten: **86 mutants** (the 17 shipped + 69 new, which include the review's 14 real-gap survivors X18-22, X24, X30,
X35, X36, X39, X41, X42, X43 (superseded by the truncation mutants), X47). Each runs in a private copy of the tree (`-j N` workers), so the real sources are never touched.
It now (a) gates on a **green baseline** of the whole persistence file (exit 2 and "nothing above is evidence" otherwise), (b) requires each anchor to match exactly once and
the selection to collect >= 1 test unmutated, (c) requires pytest **exit 1** and one of the failing test ids to be the test written for that guard ("killed for the right reason").

Results: first full run **81 killed, 5 survived**. All five were real test weaknesses and were fixed, not excused: `unearned-accounts` (the old test also lacked its `AccountHeard`
row, so a different rule refused it - the test now forges David's own `attack@David` with every hearing row present), `peel-bound` and `peel-of-another-secret` (a downstream
rule hid them - three forgeries added), `trunc-guesses-when-genesis-and-chain-both-fail` (the harness edit that renamed it had silently not applied - fixed and re-run) and
`declared-place-and-moment` (wrong expected test name). Re-run of those five: **5 killed**. **Total: 86 killed, 0 survived.**

Six mutants are **justified equivalent** and not run (table in the harness): X23, X26, X31, X45, X46 (the seed also moves the derived personalities, so the initial-digest check refuses
first), and the 0<=x<=1 float range (implied by the basis-point grid). Two of the review's four "equivalent" survivors are among them; X23/X26 were re-argued against the new fold.

## 5. Commands run
All from `D:\Murder Mystery`, Python 3.12.10, Windows 11; bash tool, runs in the background with other jobs competing for CPU (wall times inflated).

| Command | Result | Exit |
|---|---|---|
| `python -m pytest tests/test_persistence.py -q -p no:cacheprovider` (168 tests, before the last 6 forgeries) | `168 passed in 538.89s` | 0 |
| `python -m pytest -q -p no:cacheprovider --ignore=tests/test_persistence.py` | `2364 passed in 2362.58s` | 0 |
| `python -m tests.persistence_mutation_check -j 4` | baseline green, `81 killed, 5 survived or malformed, 6 justified equivalent` | printed 1 |
| the five survivors re-run one by one (`-k unearned`, `peel-bound`, `peel-of-another`, `trunc-guesses`, `declared-`), each with its own full-file green baseline of **174** tests | `5 killed, 0 survived` in total | 0 |
| `python -m pytest tests/test_persistence.py --collect-only -q` | `174 tests collected` | 0 |

**Not run as one command:** the project baseline `python -m pytest -q` is quoted as 2364 + 174 = **2538** from the two runs above (store.py/turn.py/package.py/cli.py did not change after
them; only tests and the harness did, and the 174-test file was re-run green by the mutation re-runs). `EIDOLON_LONG=1 python -m pytest tests/test_persistence.py -q -k long_session` was run after the repair: `3 passed in 568.98s` (500 turns 27.05 s, 1000 turns 113.13 s, 2000 turns 427.76 s), exit 0. The Phase 6 sweep and seed study were not re-run (they do not touch persistence).

## 6. Remaining debt
`docs/EIDOLON-KNOWN-DEBT.md` §C is corrected. Open after this repair: C-1 (structurally valid but unjustified turns after a re-chain,
including a fabricated CONFESSION), C-4/C-5/C-6 (no `PlayerAction` rows, 14 producer-less kinds, no `TurnTrace`), C-10 (old-schema saves
read-only, no migrator), C-11 and PU-1 (cross-machine replay unmeasured), C-12 (PN-1, 3, 4, 5, 6, 8, 10 NON-BLOCKING). Phase 6 items are unchanged.

## 7. Phase 8 entry conditions (review §9)
Fixes 1–5, 6, 7 and 8 have landed with tests and mutants; the persistence suite and the extended mutants are green with every survivor
justified (EQUIVALENT table in the harness). Not satisfied and not claimed: cross-machine replay (PU-1), independent re-review.

**PHASE 7 REPAIRED - READY FOR RE-REVIEW** (not accepted; cross-machine replay remains unmeasured).
