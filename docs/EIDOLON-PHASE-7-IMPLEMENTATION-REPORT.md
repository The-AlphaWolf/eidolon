# EIDOLON — Phase 7 implementation report (Persistence)

Date: 2026-10-17. Scope: architecture §26 / roadmap §30 "Phase 7 — Persistence" only. Phase 8 was not started.
This report states what was run and what its output was. Nothing here is an independent audit; the new code has been
written and tested by the same engineer, and it is marked **ready for independent review**, not accepted.

> **Superseded in part.** The independent review (`docs/EIDOLON-PHASE-7-HOSTILE-REVIEW.md`, verdict B) refuted several claims below (what is trusted on load, the "payload re-serializes to its stored bytes" claim, "impossible provenance" detection, the C-8 recovery claim, the C-5 count, the `[59]`/`[17 killed]` figures as evidence). The current state is `docs/EIDOLON-PHASE-7-REPAIR-REPORT.md` and `docs/EIDOLON-KNOWN-DEBT.md` §C.

## 1. Requirements and disposition

Source of the list: `docs/EIDOLON-ARCHITECTURE.md` §26, §30 Phase 7 (deliverables, tests, exit), invariants I-4, I-13, I-15,
I-17, I-22, I-23, I-31, I-41, I-58, tests T-22/T-23/T-24. No `docs/EIDOLON-IMPLEMENTATION-CONTRACT.md` exists on disk; the
architecture document is the contract.

| # | Requirement | Disposition |
|---|---|---|
| D1 | SQLite schema, `game.db` + `traces.db` | **Done.** `game.db`: `meta`, `case_bundle`, `session_events` (STRICT tables). `<save>.traces.db`: `traces(turn, trace)` |
| D2 | `append(events, expected_seq, action_id)`, one transaction, stale / duplicate handling | **Done.** `Save.append`: duplicate `action_id` → `AppendResult(appended=False)` (checked first, a retry is also stale); `expected_seq` ≠ head → `StaleAppend`; any fold refusal rolls back and leaves the live `Save` untouched |
| D3 | Hash chain over the **full canonical row** (I-41) | **Done.** `sha256(prev ‖ canonical{seq, turn, kind, action_id, payload})`. Row 1's `prev` is a *genesis hash* binding the case seal and the seed |
| D4 | Read-only load → fold → verify, **including the `EpistemicState` overlay** | **Done.** `Save.open` (SQLite `mode=ro` unless `writable`). The overlay is folded by `apply_epistemic`; overlay rows must name a memory/belief the case derived (§3) |
| D5 | Integer basis-point state hashing | **Done**, with two documented exceptions that are hashed as bp (§3, debt C-2) |
| D6 | Best-effort post-commit trace write | **Done.** Written after `COMMIT`, to a separate file, exceptions swallowed. Test makes the trace path unwritable and the turn still commits |
| D7 | `backup()` export | **Done.** `Save.export`: `Connection.backup()` → temp file → `os.replace`. Traces do not travel (tested) |
| D8 | `schema_version`, no upcaster framework until needed | **Done.** `SCHEMA_VERSION = 1`, `UPCASTERS = {}`; a version > engine is refused, a version < engine without an upcaster is refused. In-memory upcast verified on a synthetic v1→v2 change |
| D9 | `eidolon replay --verify`, trace gaps reported as expected, not corruption | **Done.** `python -m eidolon.cli replay <save> --verify` (always verifies; `--verify` accepted for §27.3's spelling). Also added `newsave` |
| D10 | Offer truncation to the last valid row with explicit confirmation (§26.3 step 3) | **Done, conservative.** `store.truncate_to_last_valid(path, confirm=True)`; drops the last verified turn too (debt C-8) |
| T1 | save/load/replay equality at 500 / 1000 / 2000 turns | **Done.** Results in §4 |
| T2 | tampered case refused | **Done** (case hash, genesis, bundle seal, package edit, proof edits, swapped proof) |
| T3 | upcaster round-trip v1→v2 | **Done** |
| T4 | T-22 (kind flip fails the chain at that seq) | **Done**, asserted on the chain function itself so the load-time payload-kind check cannot mask it |
| T5 | T-23 fold completeness | **Done, by source inspection + hash key-set** (same technique as Phase 4's test; debt C-9) |
| T6 | T-24 engine upgrade changing the composure formula replays identically | **Done** (formulas monkey-patched to constants; hash unchanged) |
| X1 | Exit: any session resumes on another machine with an identical state hash | **Partly measured.** Identical hash across fresh processes under `PYTHONHASHSEED` ∈ {0, 1, 4242}; identical chain *head bytes* for a save built under seeds {0, 1, 999}. A second physical machine / OS was not available |
| X2 | Exit: fold-completeness test passes with no field recomputed | **Done** (T-23 + "folds never consult a weight/score/retrieval/model" source test) |

## 2. Files changed

New: `eidolon/store.py`, `tests/test_persistence.py`, `tests/persistence_mutation_check.py`,
`docs/EIDOLON-KNOWN-DEBT.md`, this report.

Modified (all small):
* `eidolon/decision/turn.py` — **the turn runners now return the turn's *complete* log.** Before, `TurnResult.events` omitted the
  `Discovery` a presentation causes and the `TurnCommitted` bracket, and `run_goto/search/take_turn` returned no events at all, so
  no log could have reproduced the live state. Now `events = [TurnCommitted] + decision + [Discovery] + hearing + minds`; the
  exploration results gained an `events` field. The order is the order the live code folds in (Discovery before hearing, because a
  `StatementHeard` prerequisite can depend on it). `drive()` in the tests asserts after **every** append that the folded state hash equals the engine's live state hash.
* `eidolon/solve/package.py` — `load_sealed_case(path)` split into file read + `load_sealed_text(text)`; the verifier body is unchanged
  and there is still exactly one (I-58). A save embeds the bundle text and re-verifies it on every load.
* `eidolon/cli.py` — `replay` and `newsave` subcommands.

## 3. Design decisions, schema and migration

* **What is trusted on load: nothing in the file.** The embedded bundle goes through `load_sealed_text` (seals, `verify_proof`,
  full-scale report) every time; the proof is never accepted because it was written.
* **Genesis hash** = `sha256({case seal, seed})`. Row 1 chains from it; `meta.genesis` must equal the recomputation. A different seed
  or case is refused even for a save with no rows.
* **Head pinned in `meta`** (`head_seq`, `head_hash`), updated in the append transaction. Without it a deleted tail is just a shorter,
  valid chain. With it, tail deletion is a refusal. (A forger who also edits `meta` and re-chains is debt C-1.)
* **Closed event registry** (28 kinds). Unknown `kind` → refusal on load, and on write. A payload must also **re-serialize to exactly
  its stored bytes** after parsing, so extra fields and silent coercions are refused (pydantic ignores extras by default).
* **Order-stable serialization.** `frozenset`s are emitted sorted (they otherwise dump in hash order, which varies with
  `PYTHONHASHSEED`).
* **The fold is a *validating* fold, but not a recomputing one** (I-22): it never consults a weight, score, retrieval or model. It
  refuses rows that name impossible provenance:
  * a turn must open with `TurnCommitted` and continue the turn count;
  * `StatementHeard` / `AccountHeard` must name a statement **committed in the same turn** (ADR-24 / I-50): an identifier in a file never makes anything heard;
  * `apply_heard`'s existing ledger checks (token's actor must be the speaker, statement must list it) and `apply_discovery`'s
    prerequisite / action / place checks;
  * a `ClaimMade` must be this turn's statement by the addressed speaker, its `accounts ⊆ tokens_satisfied(its claims)`, its claims
    bound to its id, every `grounding` id must resolve (knowledge, belief or overlay);
  * `ClaimRetracted.retracted_by` must be this turn's statement; `LayerPeel` must be the addressee's own secret, start at the
    folded index and stay inside the cover (structural only, see C-1);
  * overlay rows must name a derived memory/belief; `KnowledgeAdded` must carry `InvestigationTold` (existing fold check);
  * after every append and at the end of load: `check_discovery_state`, `check_heard_state`, and "a character's detective model holds
    no evidence the player did not discover and no statement not on the record".
* **Failed load cannot mutate a live session**: `Save.open` builds everything locally and returns a `Save` only on success; the
  file is opened read-only. A refused load leaves the file byte-identical (tested). A refused append rolls back and `self.state`,
  `last_seq` and `last_hash` are unchanged (tested).
* **State hash.** Everything a fold writes (characters minus the static `Personality`, epistemic overlay, discovery, decision,
  turn counter, seed). Any float raises, except two inherited ones converted to bp first: `Hypothesis.player_confidence` and
  `KnowledgeEntry.reliability` (found while testing the overlay round-trip). Both are Phase 2/4 model debt (C-2).
* **Schema/migration.** v1 only. An upcaster is `fn(kind, payload) -> payload`, applied per row in memory; the chain is verified over
  the stored bytes and the file is never rewritten (test compares file bytes before/after).
* **Specification ambiguities, resolved to the smallest consistent reading:**
  1. §26.1 says "`game.db`" and "`traces.db`" without saying where; traces live beside the save as `<save>.traces.db`, so several saves can share a directory.
  2. §26.2 does not say whether `action_id` is per row or per turn; it is stored on every row of a turn, a turn = one append, uniqueness is per turn.
  3. §26.1 mentions WAL for export; the live file uses the default rollback journal (C-7) because a read-only open of a WAL database needs write access to `-shm`, contradicting I-23.
  4. The architecture's `TurnCommitted` has no stated role in replay; it is used as the turn bracket and the carrier of "which character the bare minds rows belong to" (the minds events carry no character).
  5. `PlayerAction` is registered but not written (C-4).

## 4. Tests and exact results

All figures are from commands run in this session; "exit" is the observed process exit status.

| Command | Result |
|---|---|
| `python -m pytest -q` **before any Phase 7 edit** (baseline; started at the beginning of the session, note below) | `2364 passed in 2173.80s`, exit 0 |
| `python -m pytest -q` after the store, runner and CLI changes (intermediate tree) | `2421 passed in 2333.55s`, exit 0 (2364 + 57 new) |
| `python -m pytest -q` on the **final tree** (adds the overlay checks/tests) | `2423 passed in 1826.21s`, exit 0 (2364 + 59 new) |
| `python -m pytest tests/test_persistence.py -q` (final tree) | see §4.1 |
| `EIDOLON_LONG=1 python -m pytest tests/test_persistence.py -k long_session` | `3 passed in 637.40s`, exit 0 — 500 turns 38 s, 1000 turns 129 s, 2000 turns 469 s (run concurrently with the full regression, so wall times are inflated) |
| `python -m tests.persistence_mutation_check` | see §4.2 |

Baseline caveat: I edited `turn.py`, `package.py` and `cli.py` while the baseline was still running. Test modules and the engine are
imported at collection time, so it measures the pre-edit code for in-process tests; the few tests that spawn subprocesses may have
read edited files. The post-change full run (2423, final tree) is the regression result that matters.

`tests/test_persistence.py` — what it covers (the spec's 14 scenarios, by number):
1. canonical round trip (hash equal to the live engine's after **every** turn); 2. event history/replay incl. resumed saves and
append-after-reload; 3. fresh processes under 3 hash seeds; 4. missing / garbage / empty-SQLite files, newer schema, missing or extra
meta keys, non-integer version; 5. truncation at 4 lengths and byte flips across the file (each must be refused *or* load to the
identical hash); 6. kind flip (T-22), edits to every hashed column, deleted middle/tail row, duplicated row, seed/case-hash edits,
re-chained extra fields; 7. refused load leaves the file byte-identical, refused append leaves the live save unchanged;
8. re-chained unknown kind, kind/column disagreement, non-registered classes, a turn without a bracket / with a skipped count;
9. forged detective knowledge, forged `KnowledgeAdded`, forged peels (incl. a 3-layer cover for the skip-a-layer case), a claim
grounded in nothing, a discovery with unmet prerequisites, ghost memory/belief ids; 10. hearing of an old/unknown statement, a minted
account token, a statement listing an account its claims do not deliver; 11. proofs with deleted exclusions or a wrong survivor, **with
the bundle seal repaired** (the forger's best case); 12. another case's proof swapped in, package edited after sealing; 13. the
overlay round trip and the v1→v2 upcaster (existing golden bundles keep loading through the same reader); 14. the full suite.

### 4.1 Final-tree persistence run
`59 passed in 164.33s`, exit 0 (default scale: the 500-turn case; 1000/2000 are gated behind `EIDOLON_LONG=1`).

### 4.2 Mutation check of `store.py`
`17 killed, 0 survived`, exit 0 (the final tree; each mutant verified to match its target exactly once and `store.py` verified restored afterwards).

Mutation check = `tests/persistence_mutation_check.py`: each guard is disabled in turn and the named tests must fail. A first run
had **two survivors**, and both were genuine weaknesses of the tests, not equivalent mutants: (a) T-22's test passed even with `kind`
removed from the hash because the load-time payload-kind check masked it — the test now asserts on the chain function directly;
(b) the peel-continuity guard was only exercised by two-layer covers, where "stay inside the cover" subsumes it — a test on the
three-layer cover in `manor_wing_s4` now kills it. One mutant pattern was also wrong (matched 0×) and was corrected.

## 5. Persistence integrity and replay results

* Live vs replay: after each of the ~100–4000 appended turns in the tests, `state_hash(engine state) == Save.state_hash()`.
* Fresh-process restoration identical under PYTHONHASHSEED 0 / 1 / 4242.
* Byte-determinism of the *file*: three processes with hash seeds 0 / 1 / 999 building the same 201-row session ended on the identical
  chain head `c548111e…500ca`.
* Weight-change replay (T-24): passes.
* 2000-turn session: save, reload and fold reproduce the live hash.

## 6. Remaining limitations and known debt

See `docs/EIDOLON-KNOWN-DEBT.md` (Phase 6 items **recorded, not re-certified**; C-1…C-9 are Phase 7's own). The ones a reviewer should
look at first:
* **C-1** a forger who recomputes the chain can inject a structurally valid but *unjustified* `LayerPeel`/pressure value. Detecting it
  would need the fold to recompute `refutation_weight`, which I-22 forbids; §26.1 says local saves are not cheat-proof.
* **C-5** the producers of `Accusation` / `HypothesisChanged` / `CaseSolved` / `KnowledgeAdded` / overlay events do not exist yet; the
  store accepts them in the fold, but only direct-`append` tests exercise them. Phase 8 may need stricter per-row checks.
* **C-3** `Personality` is derived from `(case, actor, seed)`; custom personalities cannot be persisted.
* The Phase 6 mutation sweep, generation determinism across hash seeds, D-1 and the 8 IMPORTANT / 7 NON-BLOCKING findings are
  unchanged and un-re-run.

## 7. Criteria not satisfied

* "Resumed on another **machine**": only other *processes* were tested (X1).
* `TurnTrace` (§27.1) — no model, no writer wired into the turn runner (C-6); only the best-effort mechanism exists.
* `PlayerAction` rows are not written (C-4).
* WAL journal mode (C-7) and the lossless form of truncation recovery (C-8).
* No independent review has happened.

## 8. Verdict

**PHASE 7 IMPLEMENTED — READY FOR INDEPENDENT REVIEW**

With the §7 list of criteria not satisfied (cross-machine resume untested, no `TurnTrace` model, `PlayerAction` not logged) and the C-1 forged-but-valid-chain limitation, none of which blocks the deliverables the architecture lists for Phase 7. Phase 6 is not independently accepted (`docs/EIDOLON-KNOWN-DEBT.md`).
