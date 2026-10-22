# EIDOLON — Phase 7 independent hostile review (persistence)

Date: 2026-10-17. Role: independent security reviewer and adversarial test engineer; not the implementation author.
Scope: `docs/EIDOLON-ARCHITECTURE.md` §26, §27, §30 (Phase 7) and the invariants they cite, measured against
`eidolon/store.py` and its callers. No production code, test, fixture, report or architecture document was modified;
every attack and mutant ran against scratch copies of the tree outside the repository. Phase 8 was not started.

## Verdict

**B. REQUIRED FIXES — REMAIN IN PHASE 7**

The core of Phase 7 holds up under attack, and holds up well. Every unrepaired edit to a hashed column, row order,
row count, seed, case hash or tail was refused. The fold calls no strategy, weight, retrieval, pressure or model code:
it still replayed identically with 17 of those functions stubbed to raise. Replay is byte-deterministic: the same
session built under four `PYTHONHASHSEED` values produced byte-identical SQLite files. A session saved, reloaded and
continued wrote exactly the rows the uninterrupted session wrote (604 rows). The independent proof verifier refused
every forged or malformed proof, except for cosmetic label fields. Rollback held under a full disk, a blocked COMMIT,
a held write lock and a crash with a hot journal. The architecture is sound, so this is not verdict C.

It is not verdict A for four reasons:

* **One BLOCKING defect.** The recovery deliverable (§26.3 step 3) destroys verified data. If one hex digit of
  `meta.genesis` is corrupted, `truncate_to_last_valid(confirm=True)` deletes all 372 intact rows, and the save still
  refuses to load. It also deletes a turn from a healthy save, and deletes a turn on every call against a save it
  cannot repair.
* **The validating fold enforces much less than the implementation report claims.** It appends:
  * a murderer's `LayerPeel` with no statement;
  * a retraction of another speaker's statement;
  * a claim grounded in another character's knowledge;
  * a fabricated confession that mints the murderer's own murder-event account;
  * references to secrets, actors, locations and items that do not exist.

  Load also skips a soundness check that append enforces.
* **Four cheap, concrete defects at the write boundary:**
  * a float can enter authoritative state, and `eidolon replay --verify` then crashes;
  * an upcast save bricks itself after its first append;
  * the append ABA case writes a broken chain and reports success;
  * a duplicate `action_id` does not identify the committed turn, which §26.2 requires.
* **Two inherited Phase 6 gaps that bear directly on what a loaded save treats as truth:**
  * personality derivation lives outside the log and outside the state hash;
  * the declared solution is never checked against the verified proof.

Most semantic forgeries found here need a re-chained file. §26.1 explicitly permits that kind of forgery for local
saves, and this review does not count them as cheating defects. They are reported for three reasons. They falsify
specific claims in the implementation report. Several are unresolvable references, which the project's fail-closed
rule says must refuse. And the fold is the only backstop Phase 8's new event producers will have.

## 1. Code snapshot reviewed

The tree is not a git repository, so the snapshot is a SHA-256 manifest. It covers 208 files (`eidolon/`, `tests/`,
`cases/`, `docs/`, `CLAUDE.md`, `pyproject.toml`; `__pycache__` excluded), taken before any command ran:

```bash
find eidolon tests cases docs CLAUDE.md pyproject.toml -type f -not -path "*/__pycache__/*" -not -name "*.pyc" | sort | xargs -d '\n' sha256sum | sha256sum
```

→ manifest digest `b93d7fc101c977a2ec99594c56b55483be8a8a36f29ad60b915a7520a578812f` (Git Bash `sha256sum` format on
Windows). The same manifest re-taken after the review is identical, except for the addition of this file (§2).

| File | SHA-256 | mtime (+0530) |
|---|---|---|
| `eidolon/store.py` | `fa9d496d6301cd3904ebe8498a8c3056c8c01126b111a3bb858da36c4dae1f61` | 2026-10-17 19:19:13 |
| `eidolon/decision/turn.py` | `6974e0447935f48eb455c6fdd681ef047897829ca81c2ed3b2589da646935d5f` | 2026-10-17 18:17:29 |
| `eidolon/solve/package.py` | `0661e81658cf129c1066ec6c09e2232fecd08702b46af85209379a3ad346a559` | 2026-10-17 18:17:36 |
| `eidolon/cli.py` | `d97e0e51b1e3ae49530c6975a3f8092b2fb984d8a04108779ba4d13bbe13c205` | 2026-10-17 18:21:45 |
| `eidolon/solve/proof.py` | `84953ad9e1087a0a1c25ae06dbe1872ba33e7ae7fdb0be569f4e2f0816ff290c` | — |
| `eidolon/solve/session.py` | `83b7dcfc4a8892eb294dd69fac24cc306c0f47d9da560e9c95f65900ea6eab7f` | — |
| `tests/test_persistence.py` | `004f350677858fe3cdecd82b6283a892630966cf2610c3df30feed3a72e40e33` | 2026-10-17 19:14:52 |
| `tests/persistence_mutation_check.py` | `a1c81b00ecadac231d08ad37317ba5afadaca1dec67d373119f904ad195e209d` | 2026-10-17 19:16:19 |
| `docs/EIDOLON-ARCHITECTURE.md` | `c9fb2beb0500e662584b393047f7d8bbb4025d717beab1bc6f612f71bc50c8fb` | — |
| `docs/EIDOLON-PHASE-7-IMPLEMENTATION-REPORT.md` | `062aad808f10034844d453887a36703d3018c30da2891b73fb188dcca1c20965` | — |
| `docs/EIDOLON-KNOWN-DEBT.md` | `3f240fb36d190343e7b75f22c637221656afc3f81800f3f436608295c5bd08f2` | — |
| `cases/generated/study_party_s4.json` | `fbfa9c1c21bd725c9ac436a5b030024b52ad0998d4bc3308b013176a4b6de407` | — |
| `cases/generated/manor_wing_s4.json` | `f762df353e8db19e4bb302812e0f517b6a6530eac2f04e5c8b92726f08f4f823` | — |
| `CLAUDE.md` | `24748c45dc29adf3f92ef10a412846f50faffff8331c1966134e7627415741fb` | 2026-10-17 19:52 |

Environment: Windows 11 (win32), Python 3.12.10, pydantic 2.13.5, SQLite 3.49.1, 16 logical CPUs. `eidolon` is not
pip-installed; it is imported from the working tree.

Most attacks use one base save, built the way `tests/test_persistence.py::drive` builds one: `study_party_s4`, seed 7,
one `GoTo`, every search, then 60 asks with every fifth one presenting held evidence. Result: **372 rows, 71 turns,
live state hash `69f0f8bf45fa18e3…`**. The murderer is David; four living suspects each own a two-layer cover; the
case declares one account token (`clean@Elena`).

## 2. Commands run and observed exit codes

"Original tree" means `D:\Murder Mystery` itself, run with `PYTHONDONTWRITEBYTECODE=1 -p no:cacheprovider` so that
nothing was written into it. Every other command ran in a byte-identical scratch copy, one copy per concurrent job.
Wall times were inflated by up to eight concurrent jobs.

| # | Command | Where | Result | Exit |
|---|---|---|---|---|
| 1 | `python -m pytest tests/test_persistence.py -q -p no:cacheprovider` | original tree | `59 passed in 177.77s` | 0 |
| 2 | `EIDOLON_LONG=1 python -m pytest tests/test_persistence.py -q -k long_session --durations=5` | copy | `3 passed, 58 deselected in 602.82s`: 500 turns 41.03 s, 1000 turns 138.05 s, 2000 turns 422.40 s | 0 |
| 3 | `python -m tests.persistence_mutation_check` | copy | `17 killed, 0 survived`, 3 m 35.6 s; `store.py` hash unchanged afterwards | 0 |
| 4 | Extended mutation audit (§5): green baselines, then 17 shipped + 30 new mutants against the **whole** persistence file with `-x -rf`. After its first 8 mutants, the sequential run was stopped and the remaining 39 were split across six parallel copies to cut wall time. Every copy started byte-identical | 7 copies | 47 mutants: **29 killed** (17 of 17 shipped, each by its own guard's test; 12 of 30 new), **18 survived** (14 real gaps, 4 equivalent); every copy's `store.py` verified restored | 0 (every worker) |
| 5 | `python -m pytest -q -p no:cacheprovider` (full suite) | copy | `2423 passed in 2908.36s` (48 m 28 s; contended — the report's 1826 s was uncontended) | 0 |
| 6 | Attack scripts A, B, C, D, E, F, G, Z (§3) and the reproductions of §4 | copies | outcomes tabulated below. Two harness defects of mine were fixed and re-run: the first mutation run failed at start-up (`__file__` undefined in `exec`), and the recovery script stopped at F9 because its own row-count helper could not read the deliberately corrupted file; F9–G were re-run from a corrected copy | 0 after the fixes |
| 7 | Manifest re-taken after the review | original tree | identical except `docs/EIDOLON-PHASE-7-HOSTILE-REVIEW.md` added | — |

All five of the implementation report's test claims were reproduced: the full suite (2 423), the persistence file
(59), the long sessions, the 17 shipped mutants, and fresh-process determinism. None of this is evidence of the
properties §3 attacks. Every finding below was found with all 2 423 tests green.

## 3. Attack-by-attack results

The outcome vocabulary is the store's own. **REFUSED** means `SaveRefusal`; LOADED and APPENDED are successes; any
other exception is named. A "finding" column entry points to §4.

### A. Save integrity and hash chain

| Attack | Outcome | Assessment |
|---|---|---|
| Edit each of `seq, turn, kind, action_id, payload, prev_hash, hash` on 7 sampled rows (1, 2, 3, 5, 186, 371, 372), no re-chain — 49 edits | all REFUSED | holds (I-13, I-41) |
| Genesis recomputation | `meta.genesis == sha256(canon({case: seal, seed}))` | holds |
| Delete a middle row / delete the tail row (meta untouched) / swap two rows / duplicate the last row | all REFUSED | holds |
| Delete the whole last turn and copy the new last row's stored `hash` column into `meta.head_hash` — **no hash computed** | **LOADED**, 70 of 71 turns | PN-1: the head pin stops accidents and naive edits only |
| Same parsed payload, different stored text: whitespace, reversed key order, `\u006b` escape, a **duplicate key whose first value is `"Accusation"`** | **LOADED**, identical hash (all four) | PN-2: the chain authenticates the parsed object, not the stored bytes; first-wins JSON readers see a different row |
| Re-chained coercions: `turn: "5"`, `new_composure_bp: 5000.0`, `turn: true`, a dict field as a list of pairs, a defaulted key removed | all REFUSED (round-trip check). The type error surfaces as "unreadable save: ValidationError" with `seq=None` (PN-8) | holds |
| `meta.schema_version` = `" 1"`, `"01"`, `"+1"`; `meta.seed` = `" 7"`, `"07"` | LOADED | PN-13 (harmless now) |
| `meta.case_id`, `genesis`, `head_hash`, `head_seq="0372"` edited | all REFUSED | holds (the head message names only the seq) |
| Extra table and view in the file | LOADED | PN-3 |
| Planted `AFTER INSERT` trigger that rewrites the inserted payload | `append` → **APPENDED**; reopen → REFUSED at row 373 | PN-3: the store reports success for a row it did not durably write |
| File switched to WAL mode | read-only open LOADS, bytes unchanged, `-wal`/`-shm` sidecars created | acceptable (C-7) |
| Another save's whole log transplanted into a fresh save of the same case and seed | LOADED, identical hash | by design: no per-save identity in the genesis |
| Byte flips at 249 offsets spread over the **whole** 253 952-byte file | 187 REFUSED, 62 LOADED with the identical hash, **0 other outcomes** | holds |
| File cut to 2 %, 5 %, 30 %, 60 %, 97 %, 99.99 % | all REFUSED | holds |
| `action_id` index b-tree corrupted | writable open LOADS (no integrity check); retrying an **existing** `action_id` → **APPENDED** (an I-14 duplicate); reopen REFUSED | PN-3 |

### B. Transactionality and failure safety

| Attack | Outcome | Assessment |
|---|---|---|
| Stale `expected_seq` | `StaleAppend`; file and state unchanged | holds |
| Retry of a committed `action_id` two turns later | `appended=False, last_seq=390` (the current head, not the turn's seq 378) | **PI-5** |
| Same `action_id`, different events | `appended=False`; the mismatch is not reported | PI-5 |
| Genuine turn with a forged `AccountHeard` as row 4 | REFUSED; file and state unchanged; next append works | holds |
| Non-event object in the middle of a turn | `AttributeError` (not `SaveRefusal`); rolled back | PN-8 |
| `SQLITE_FULL` during the insert (`max_page_count` fault injection) | `OperationalError`; not in a transaction; state and file unchanged; same `action_id` succeeds once space returns; reopen equals live | holds |
| COMMIT while another reader holds SHARED | `OperationalError: database is locked` after 5.6 s; rolled back; state and file unchanged; next append works | holds |
| Another writer holds RESERVED | `OperationalError` after 5.5 s, no transaction left open, state unchanged | holds (PN-8: raw sqlite exception) |
| Crash mid-append (3 000 rows inserted, cache spilled, `os._exit`) | hot journal left; **read-only open REFUSED** ("attempt to write a readonly database"); `eidolon replay` exit 1; writable open rolls back and loads the pre-crash hash | correct and fail-closed; recovery is undiscoverable (PN-8) |
| ABA: A open at head 372; another writer truncates to 366 and appends one-row turns back to 372; A appends | **APPENDED**; reopen REFUSED at row 373 (chain break) | **PI-4** |
| `export()` from a read-only `Save` | `ProgrammingError` (connection closed at open); `<dest>.tmp` left behind | PN-6 |
| `export()` onto the save's own path | `PermissionError` on Windows (on POSIX it would orphan the live inode — not measured, PU-3) | PN-6 |
| Append on a closed save / empty event list / empty `action_id` | `ProgrammingError` / REFUSED / REFUSED | holds |

### C. Fold completeness and semantic validity

Each row was offered to `append` on a writable copy of the base save, which validates exactly like load (C7 is the
one exception). The control row, a genuine David turn, was APPENDED as expected.

| Forged turn (no turn runner can produce any of these, except C9/C9b — the Phase 4 `GoTo`/`Take` runners accept any string too) | Outcome | Finding |
|---|---|---|
| C1 `TurnCommitted(David)` + `LayerPeel(David, S_David, 0→1)`, no statement | **APPENDED** — the murderer's cover moved with no statement and no evidence | PI-1 |
| C1b the same peel beside a statement voicing none of the layer (the runner refuses `UNVOICED_LAYER_PEEL`) | **APPENDED** | PI-1 |
| C2 David's turn retracts **Elena's** statement, no peel | **APPENDED** | PI-1 |
| C2b retraction of an old own statement in a turn without a peel / C2c a statement retracting itself | **APPENDED** / **APPENDED** | PI-1 |
| C3 David's claim grounded in Elena's knowledge entry (§25/I-27: grounding is in the speaker's own stores) | **APPENDED** | PI-1 |
| C4 fabricated `CONFESSION` ("Fine. I did it.") with a truthful claim `Did(David, Attack, Decanter, Study)` grounded on David's own `Participated` entry, plus its hearing rows | **APPENDED**; `attack@David` — the murder event's account — is now in `known_accounts` | C-1 class; contradicts "unearned accounts … detected" |
| C5 conversation turn with no statement, only `ComposureChange(0)` + `PressureChange(S_David, 10000)` | **APPENDED** | PI-1 |
| C6 statement committed but never heard / C19 a bare `TurnCommitted(David)` | **APPENDED** / **APPENDED** | PI-1, PN-9 |
| C7 re-chained: David's detective model holds `E_scene` at turn 1; `E_scene` is found at turn 2 | load: **LOADED**; the same rows via `append`: REFUSED ("never discovered") | PI-1: load is weaker than append |
| C8 `DetectiveModelUpdate` rewriting `accusations`, `probed_topics`, `estimated_suspicion_of_me`, `contradictions_confronted` / C8b every discovered item and statement "presented" at once | **APPENDED** / **APPENDED** | PI-1 (C-1 class for values) |
| C9 `LocationVisited("Atlantis")` / C9b `ItemTaken("Excalibur")` | **APPENDED** / **APPENDED** (the Phase 4 runners accept any string too) | PI-1, inherited |
| C10 `PressureChange(secret_id="S_nope")` / C10b `SuspicionShift(target="Nobody")` | **APPENDED** / **APPENDED** | PI-1 (unresolvable references) |
| C11 `MemoryCorrected(field="any_field_at_all", corrected_value=0.5)` | **APPENDED**; `state_hash()` → `ValueError` (float, I-17); reopen LOADS but cannot be hashed; `eidolon replay --verify` exits 1 with a traceback and no JSON | **PI-2** |
| C12 `KnowledgeAdded` with reliability 1.0 vs 9.9 (I-25 caps it at trust) | both APPENDED, **identical state hashes** | PI-2, PN-10 |
| C13 `Hypothesis.player_confidence` 1.0 vs 7.0, and 0.50001 vs 0.5 | APPENDED, **identical state hashes** in both pairs | PI-2 |
| C13c `player_confidence = NaN` | `ValueError` from `_canon` (not `SaveRefusal`); rolled back; the save stays usable | PN-8 |
| C14 `CaseSolved(correct=True)` with no accusation; a turn after it; a second `CaseSolved(correct=False)` overwriting the first | all **APPENDED** | PN-10 (no producer, C-5) |
| C15 `Accusation(target="Nobody", provisional=False)` / C16 `TurnCommitted.action_id` disagreeing with the row's | **APPENDED** / **APPENDED** | PI-1 |
| C17 re-chained duplicate `ComposureChange` and duplicate `ClaimMade` rows inside one turn | LOADED, identical hash (idempotent folds) | benign; the I-13 "duplicate" test holds only at the chain level |
| Discovery with the wrong action / wrong place / unknown id / unmet prerequisites | all REFUSED | holds |
| Hearing an old or unknown statement; an account its statement does not list; a claim grounded in nothing; a ghost memory or belief; a peel skipping a layer; a peel of another's secret | all REFUSED (the shipped tests, re-run) | holds |

**Producers.** A grep of `eidolon/` for constructors outside `store.py` finds production emitters for only these
kinds:

* `TurnCommitted`, `ClaimMade`, `LayerPeel`, `ClaimRetracted`, `MetaAttemptLogged`;
* `Discovery`, `StatementHeard`, `AccountHeard`, `LocationVisited`, `ItemTaken`;
* `PressureChange`, `ComposureChange`, `DetectiveModelUpdate`, and `CoverStateDelta` (only its `topics_probed` field).

The other **14 of the 28 registered kinds** have no emitter:

* `EmotionalDelta`, `TrustChange`, `SuspicionShift`;
* `MemoryRecall`, `MemoryCorrected`, `BeliefRevised`, `KnowledgeAdded`;
* `IncidentalPinned`, `HypothesisChanged`, `Accusation`, `CaseSolved`;
* `PlayerAction`, `ValidationFailure`, `FallbackUsed`.

The C-5 debt entry lists 5 of them. No production code calls `Save.append`, and none passes `trace=`.

### D. Proof and sealed-case verification (through the save's embedded bundle)

| Attack (bundle seal recomputed where noted) | Outcome | Assessment |
|---|---|---|
| Exclusion of Elena deleted; survivors `[Elena]`; Elena marked not excluded; fairness 2→3; `robustness.subsets_run` forged; `proof_core` shrunk; `cracked` emptied; `unique=false`; constraint names `E_nope`; constraint level raised; last constraint deleted; another case's proof relabelled to this package's seal | all REFUSED by `verify_proof` | holds (I-57, I-58) |
| Malformed proofs: `{}`, only `package_seal`, list, string, null, extra key, wrong types, 5 280 constraints | all REFUSED as `SealRefusal` → `SaveRefusal`; never another exception | holds |
| Malformed bundles: not JSON, array, missing key, extra key, package not an object | all REFUSED | holds |
| Report: package mismatch, V-7 at reduced scale, a stage not OK, `ok=false` | all REFUSED | holds |
| `E_watch` (proof core) removed from the package, package + proof binding + bundle **fully re-sealed** | REFUSED ("neither evidence in the package nor an obtainable testimony atom") | holds: a re-sealed edit to case content is still re-proved |
| Generic fuzz: 247 of the proof's 1 724 leaves mutated (every 7th), bundle resealed each time | 217 REFUSED, **30 ACCEPTED**, 0 errors. Every accepted mutation was an unreferenced `constraints[i].id` label or the `observer` field of a non-`NoStranger` constraint | PN-4: I-57's "every field verified or absent" is not literal; no semantic field passed |
| **Declared `solution.murderer` set to Elena**, package, proof binding and bundle fully re-sealed | **ACCEPTED**. `Save.create` builds a save from it; the existing 71-turn save, moved onto it (meta + re-chain), LOADS with the identical state hash. The proof still proves David | **PI-7** |
| `case.alias.names` rewritten in the embedded bundle, **no reseal, no re-chain** | LOADED, identical hash, new alias table in force | PN-4 (alias is outside `Case.content_hash`; the validator, ingress and renderer read it) |
| `report.metrics`/`problems` rewritten, bundle seal recomputed, **no re-chain** (the genesis binds only the package seal) | LOADED | PN-4 |
| Unknown fields inside the embedded package JSON, no reseal | LOADED (pydantic ignores extras) | PN-4 |

### E. Deterministic replay and canonical hashing

| Check | Outcome |
|---|---|
| Continuous 60 + 40-turn session vs. 60 turns → close → reopen → 40 more turns | rows **identical (604)**, chain head identical, state hash identical, reopened hash identical |
| The same 30-turn session built in fresh processes under `PYTHONHASHSEED` 0 / 1 / 12345 / random | 1 chain head, 1 state hash, **1 file digest** (byte-identical SQLite files) |
| Base save reloaded in 4 fresh processes (hash seeds 0, 7, 999, random) | 1 hash, equal to the live hash |
| Load with 17 decision-time functions stubbed to raise: `refutation_weight`, `evaluate_peel`, `select_plan`, `retrieve`, `score`, `update_composure`, `update_verbal_pressure`, `speakable`, `retrieve_for_query`, `relevant_secret` (and their home-module bindings), plus `TemplateLLM.generate` | LOADED, identical hash. This is a runtime proof of I-22 and stronger than the source-text test |
| T-24 as shipped (`update_composure`/`update_verbal_pressure` → constants) | identical hash (re-run in suite #1) |
| Engine change to `default_personality` (composure_base → 0.9) | LOADS silently with a **different** state hash (**PI-6**) |
| Fresh sessions of two different cases (`study_party_s4`, `study_party_s5`), seed 7 | **identical state hash** (PN-5: the state hash does not bind the case; the chain head does) |
| bp conversion (C12, C13) | out-of-range values and sub-basis-point differences collide (PI-2) |
| Synthetic v1→v2 upcaster (the shipped test's), writable open, append one turn, reopen | load OK, append APPENDED, then **reopen REFUSED (`KeyError: 't'`)**: the new v2 row is upcast a second time (**PI-3**) |
| A v2-native save relabelled `schema_version=1` in meta, no re-chain | REFUSED (`KeyError`): meta decides how chain-verified rows are interpreted (PI-3) |
| Upcast load preserves stored bytes; newer schema refused; older without upcaster refused | holds (shipped tests) |

So there are three distinct equalities, and they must not be conflated:

* **State-hash equality.** It is lossy for the two float fields (PI-2). It is blind to the case (PN-5), to personality
  and to the derived stores (PI-6).
* **Serialized equality.** It is not byte equality, because the stored payload text is malleable (PN-2).
* **Chain-head equality.** It is the only one of the three that binds case, seed and full history. It is the right
  identifier for X1's "identical state hash" comparison.

### F. Recovery and migration (`truncate_to_last_valid`)

| Scenario | Load before | `truncate_to_last_valid(confirm=True)` | Load after |
|---|---|---|---|
| F1 healthy save, nothing broken | LOADED | **cut 372→366** | LOADED (one valid turn destroyed) |
| F2 one hex digit of `meta.genesis` flipped; all rows intact | REFUSED (genesis) | **cut 372→0 — every row deleted** | **still REFUSED (genesis)** |
| F2b `meta.seed` 7→8 | REFUSED (genesis) | cut 372→366 | still REFUSED |
| F3 a chain-valid but fold-refused row at turn 30 (a producer bug) | REFUSED at seq 129 | cut 373→367 | still REFUSED at seq 129; three more confirmed calls → 361, 355, 349, still REFUSED |
| F4 meta row `genesis` deleted | REFUSED | `KeyError: 'genesis'` | — |
| F5 path does not exist | — | `OperationalError` and **a 0-byte file created** | — |
| F6 row 200 payload contains `NaN` | REFUSED | `ValueError` (the "pure, never raises" `_valid_prefix` raises) | — |
| F7 `meta.head_seq` raised by one; rows intact | REFUSED | cut 372→366 (a lossless head reset existed) | LOADED |
| F8 first row of turn 40 corrupted (turn boundary) | REFUSED at 187 | cut → 180 (complete turn 39 dropped too) | LOADED |
| F8b middle row of turn 40 corrupted | REFUSED at 189 | cut → 186 (only the partial turn dropped — correct) | LOADED |
| F9 file cut to 80 % of its bytes | REFUSED (malformed) | `DatabaseError` | — |
| F10 no `confirm=True` | — | `SaveError`, file byte-identical | — |

Explicit confirmation is required, and nothing is written before it: both hold. But the function never reports what
it is about to cut, never checks that the result loads, and never asks why the load was refused.

### G. Traces, player actions and leakage

| Check | Outcome | Assessment |
|---|---|---|
| Trace failure (trace path made a directory) | the turn commits (shipped test) | holds (§26.2, §27.1) |
| Traces travel with `export` | they do not (shipped test) | holds |
| Trace content | any `dict` is stored verbatim, including `{"secret": "the murderer is David"}` | PN-7. Not a Phase 7 vulnerability: keeping it unreachable from the player-facing process is I-10, Phase 8/9 |
| A save deleted, a new save created at the same path | the new save adopts the old `.traces.db`: `trace_gaps() == []` for a turn it never traced | PN-7 |
| Export to a destination beside a stale `.traces.db` | the exported save reports **0 gaps of 71 turns** (foreign traces taken as its own) | PN-7 |
| `a.db` and `a.sqlite` in one directory | both map to `a.traces.db` | PN-7 |
| `PlayerAction` rows (C-4), `TurnTrace` model (C-6) | absent; no production caller passes `trace=`, so `replay --verify` reports every turn as a gap | PN-11. The architecture lists `PlayerAction` as a kind and `TurnTrace` as §27.1. Phase 7's deliverables require only the best-effort write mechanism. Not promoted |

## 4. Confirmed vulnerabilities, with minimal reproductions

Every reproduction below was run verbatim from an empty directory, with `PYTHONPATH` pointing at a copy of the tree.
The quoted output is the observed output. The reproductions share this preamble; run them from the repository root,
in a fresh directory for the `.db` files:

```python
import json, sqlite3
from eidolon import store
from eidolon.store import Save
from eidolon.decision.events import Accusation, LayerPeel, TurnCommitted
from eidolon.decision.peel import layer_index
from eidolon.decision.turn import run_goto_turn, run_search_turn
from eidolon.minds.events import MemoryCorrected, PressureChange
from eidolon.solve.package import CasePackage, bundle_seal, load_sealed_text
BUNDLE = "cases/generated/study_party_s4.json"
```

### PB-1 (BLOCKING) — recovery destroys verified data and reports success

§26.3 step 3: "On a break: refuse to load past it; offer truncation to the last valid row with explicit user
confirmation." `truncate_to_last_valid` does none of the loader's verification:

* it trusts `meta["genesis"]` instead of recomputing it from `case_hash` + `seed`;
* it ignores why the load was refused;
* it cuts the last *verified* turn unconditionally;
* it never re-opens the result.

```python
s = Save.create("r1.db", BUNDLE, seed=7)
s.append(run_goto_turn(s.state, "Study").events, 0, "a1")
for ev in s.state.evidence.all()[:3]:
    s.append(run_search_turn(s.state, ev.discovery.at, ev.discovery.action).events, s.last_seq, f"s-{ev.id}")
s.close()
c = sqlite3.connect("r1.db", isolation_level=None)
g = c.execute("SELECT value FROM meta WHERE key='genesis'").fetchone()[0]
c.execute("UPDATE meta SET value=? WHERE key='genesis'", (("0" if g[0] != "0" else "1") + g[1:],)); c.close()
store.truncate_to_last_valid("r1.db", confirm=True)
```

Observed: 8 rows before → `0` returned → 0 rows after; `Save.open` refuses before and after with "genesis hash does
not bind this case and seed". On a healthy two-turn save, the same call returns `2` and leaves 1 turn of 2 (F1).

Impact: a one-character metadata corruption, or any fold refusal (the exact failure mode C-5's future producers make
likely), turns the offered repair into irreversible loss, while the function returns normally. The user's
"explicit confirmation" is uninformed, because nothing reports the planned cut. The function also crashes on four
other kinds of damage (F4, F5, F6, F9), and creates an empty file at a mistyped path.

Required: see fix 1 in §8.

### PI-1 (IMPORTANT) — the validating fold is much thinner than claimed; load is weaker than append

The implementation report: "It refuses rows that name impossible provenance"; the debt ledger says "Detected: …
impossible provenance". Every row in table C marked PI-1 is a row no turn runner can produce (C9/C9b excepted: the
Phase 4 runners accept any location or item string, which is the inherited part). The store appends each one. The
grounding claim (C3) was checked against the shipped cases: authored cover claims carry no grounding at all, and
retrieval claims ground only on the speaker's own beliefs.

```python
s = Save.create("r3.db", BUNDLE, seed=7)
s.append([TurnCommitted(turn=1, character="David"),
          LayerPeel(character="David", secret_id="S_David", from_index=0, to_index=1)], 0, "x1")        # True
s.append([TurnCommitted(turn=2, character="David"), PressureChange(secret_id="S_nope", new_value_bp=10000)],
         s.last_seq, "x2")                                                                               # True
s.append([TurnCommitted(turn=3), Accusation(turn=3, target="Nobody", provisional=False)], s.last_seq, "x3")  # True
layer_index(s.state.decision.layer_peels, "David", "S_David")                                            # 1
```

The checks that are missing are all structural, and none of them recomputes a weight (I-22):

* a peel must be voiced by its turn's CONCESSION/CONFESSION statement;
* a retraction must be of the addressee's own earlier statement, in a turn with a peel;
* a grounding entry must belong to the speaker;
* a conversation turn must carry exactly one `ClaimMade`, together with its hearing rows;
* references must resolve: secrets, actors, locations, objects and accusation targets;
* a `DetectiveModelUpdate` may only add the turn's presented item.

C7 shows the asymmetry. `append` runs `check_state` after every turn, but load runs it once, at the end. A
detective-model row ahead of the discovery it depends on therefore loads, although `append` would refuse it.

Classification. The unresolvable references (C9, C9b, C10, C10b, C15) break the project's fail-closed rule:
"unresolvable references … resolve to refusal, never to permission". Under §26.1 a re-chaining forger gains no
capability beyond C-1, which is why this is not BLOCKING. But the fold is the only backstop for the 14 producer-less
kinds Phase 8 will start emitting.

### PI-2 (IMPORTANT) — I-17: a float enters authoritative state; the hash is lossy

```python
s = Save.create("r4.db", BUNDLE, seed=7)
mem = next(m for ms in s.state.memories.values() for m in ms)
s.append([TurnCommitted(turn=1), MemoryCorrected(memory_id=mem.id, field="x", corrected_value=0.5, turn_id=1)], 0, "m")  # True
s.state_hash()   # ValueError: float in authoritative state at state.epistemic.distortion_corrections.MDavid0001::x (I-17)
```

The save then still opens. `python -m eidolon.cli replay r4.db --verify` exits 1, with empty stdout and a
`ValueError` traceback, instead of §27.3's refusal report. The cause is `MemoryCorrected.corrected_value: Any` (a
Phase 2 model). The store detects floats only when it hashes; it never checks them at append or load.

Separately, `bp()` clamps and rounds. Two different authoritative states therefore hash identically when
`player_confidence` is 1.0 vs 7.0 or 0.50001 vs 0.5 (C13), or when `KnowledgeAdded` reliability is 1.0 vs 9.9 (C12).
I-25 caps that reliability at trust, and nothing checks it. C-2 documents the floats but not the collisions.

### PI-3 (IMPORTANT, latent until v2) — the upcaster mechanism bricks resumed saves

This is the shipped T3 scenario with one more step: append after the upcast load. Here `r5.db` is a one-turn save
whose `TurnCommitted` payloads were rewritten to the "v1" spelling `t` and re-chained, exactly as
`test_upcaster_round_trip_on_a_synthetic_v1_to_v2_change` prepares its file. `up` is that test's upcaster.

```python
store.SCHEMA_VERSION, store.UPCASTERS = 2, {1: up}                 # `up` = the shipped test's t -> turn upcaster
s = Save.open("r5.db", writable=True)                              # the v1 file loads
s.append([TurnCommitted(turn=2)], s.last_seq, "a2")               # True — written in v2 spelling, meta still "1"
Save.open("r5.db")                                                 # SaveRefusal: unreadable save: KeyError: 't'
```

Two defects combine here:

* Old-version saves open writable, and new rows are written in the new schema under the old `schema_version` label.
* `schema_version` is not bound into the genesis or the rows. A meta-only relabel changes how chain-verified rows are
  interpreted (E7b).

The test that "verifies" the upcaster never appends after upcasting.

### PI-4 (IMPORTANT) — ABA: append compares the head *seq*, never the head *hash*

Session A is open at head 6. Someone else recovers to head 4, then plays a different two-row turn, so the head is 6
again. A then appends: `True`. Reopen: `SaveRefusal: row 7: hash chain breaks`. A's rows chain from a hash that is no
longer the head, so the store reports success for a write that corrupts the log. The fix is one comparison inside
the existing `BEGIN IMMEDIATE`: check `meta.head_hash == self.last_hash`.

### PI-5 (IMPORTANT) — a duplicate `action_id` does not return the existing turn

§26.2: "if `action_id` already exists (duplicate — returns the existing turn's projection)". Here, the first commit
had `last_seq=2`. A retry one turn later returns `appended=False, last_seq=4`: the current head, not that turn. A
retry carrying *different* events returns the same answer, and the store has no lookup from an `action_id` to its
turn. Phase 8's retry-on-failure flow needs exactly this. Without it the server can only show its *recomputed,
uncommitted* turn, so the player sees text that is not on the record.

### PI-6 (IMPORTANT, inherited, affects persistence) — replayed state depends on engine code outside the log

```python
s = Save.create("r8.db", BUNDLE, seed=7)
s.append(run_goto_turn(s.state, "Study").events, 0, "a1"); h = s.state_hash(); s.close()
import eidolon.solve.session as session
orig = session.default_personality                       # an "engine upgrade" that retunes one personality range
session.default_personality = lambda a, seed: orig(a, seed).model_copy(update={"composure_base": 0.9})
Save.open("r8.db").state_hash() == h          # False — the save loads silently with a different state
```

`Personality` is not in the package (Phase 6 audit I-6) and is excluded from the state hash. Yet initial composure
is `bp(personality.composure_base)`, and the turn runner reads personality on every later turn: the composure
update, the envelope voice and the strategy input. `new_session` also
re-derives knowledge, beliefs and memories from the CaseLog on every load. `meta` records no `engine_version`
(§25's `Game` has one).

So an engine change to any initial-state derivation alters how an old save replays and continues. §26.4 forbids
that, and nothing detects it. T-24 covers only recorded-outcome formulas. (C-3 also misstates the derivation: the
code hashes `(actor, seed)`, not the case id.)

### PI-7 (IMPORTANT, inherited, affects persistence) — the declared solution is never confirmed at load

```python
doc = json.loads(open(BUNDLE, encoding="utf-8").read())
pkg = CasePackage.model_validate(doc["package"])
forged = pkg.model_copy(update={"solution": pkg.solution.model_copy(update={"murderer": "Elena"})}).sealed()
doc["package"], doc["proof"]["package_seal"] = json.loads(forged.model_dump_json()), forged.seal
doc["bundle_seal"] = bundle_seal(forged.seal, doc["proof"], doc["report"])
load_sealed_text(json.dumps(doc))       # accepted; declared murderer Elena, proof's unique survivor ['David']
```

`verify_proof` deliberately never reads `pkg.solution`, which is correct for independence, but then nothing compares
the two. `Save.create` accepts the bundle, and the 71-turn base save moved onto it loads with an unchanged hash.
Nothing at runtime reads `pkg.solution` today. Phase 8 must, for `CaseSolved.correct` and the case report. Until
`load_sealed_text` requires `proof.unique and proof.survivors == [pkg.solution.murderer]` (with matching
`murder_loc`/window), "verified on every load" does not cover the one fact players are scored against.

## 5. Mutation results

### Shipped harness (`tests/persistence_mutation_check.py`)

Reproduced: **17 killed, 0 survived**, exit 0. Every anchor matched exactly once, and `store.py` was byte-identical
afterwards. Inspecting the harness against the project's own standard found three gaps:

* **No green-baseline gate.** `CLAUDE.md` says the decision harness "refuses to report unless the unmutated baseline
  is green"; this one never runs the baseline.
* **"Killed" means only a non-zero exit code.** pytest's exit code 5 ("no tests collected"), a collection error or a
  fixture crash all count as kills.
* **Only 17 of the roughly 55 guard points in `store.py` are mutated.** Counted from the source: refusals and checks
  in the fold, codec, chain, loader, append, truncation, creation and canonical-state code.

The extended audit closed the first two gaps for the shipped set. It ran the whole persistence file once unmutated
(`59 passed in 222.06s`, exit 0) and each shipped `-k` selection unmutated (all passed). It then re-ran every
shipped mutant against the **whole** file, recording the first failing test.

**All 17 shipped mutants are killed, each by its own guard's test.** First failing test, by mutant:

* hearing → `test_a_hearing_row_cannot_…`
* head pin → `test_deleting_a_middle_row_…`
* unearned accounts → `…cannot_list_an_account…`
* grounding → `test_a_claim_grounded_in_nothing…`
* chain-ignores-kind → `…T22`
* chain-ignores-action-id → `test_editing_any_hashed_column[action_id-forged]`
* genesis → `test_a_different_seed_or_case_hash…`
* payload round-trip → `…extra_payload_fields…`
* load check_state → `…undiscovered_evidence_is_refused_at_load`
* peel continuity → `test_a_peel_cannot_skip_a_layer…`
* peel bound → `test_a_layer_peel_must_continue…`
* action-id reuse → `…reusing_an_action_id…`
* stale append and duplicate append → both `test_stale_expected_seq…`
* unknown kind on write → `…not_a_registered_event`
* overlay target → `test_overlay_rows_must_name…`
* verifier bypass → `test_a_proof_with_its_exclusions_deleted…`

### Extended audit (30 new mutants, X18–X47)

Each mutant disables one guard that the shipped harness does not mutate. Every **survivor** was then classified by
re-running, under the mutant, the single forged input that guard exists for:

* "real gap": the mutated store now accepts the input, so the guard matters and no test covers it;
* "equivalent": another check still refuses it.

| Mutant | Guard disabled | Result | First failing test, or probe outcome |
|---|---|---|---|
| X18 | `ClaimMade` by this turn's speaker, with this turn's id | SURVIVED | probe: Elena's statement inside a David turn APPENDED — **real gap** |
| X19 | claims bound to their statement | SURVIVED | probe: claim bound to `S00001` APPENDED — **real gap** |
| X20 | retraction made by this turn's statement | SURVIVED | probe: `retracted_by="S99999"` APPENDED — **real gap** |
| X21 | `MetaAttemptLogged` only for the addressee | SURVIVED | probe APPENDED — **real gap** |
| X22 | no `LocationVisited`/`ItemTaken` inside a conversation | SURVIVED | probe APPENDED — **real gap** |
| X23 | no minds rows outside a conversation | SURVIVED | probe still REFUSED (`chars[None]` KeyError backstop) — equivalent |
| X24 | `TurnCommitted` names a living character | SURVIVED | probe: bracket for `"Ghost"` APPENDED — **real gap** |
| X25 | row `turn` field equals the turn | killed | `test_a_turn_must_open_with_turn_committed_and_continue_the_count` |
| X26 | one bracket per turn | SURVIVED | probe still REFUSED ("has no fold") — equivalent |
| X27 | turn count continues | killed | `test_a_turn_must_open_with_turn_committed_and_continue_the_count` |
| X28 | turn opens with `TurnCommitted` | killed | `test_append_refuses_an_object_that_is_not_a_registered_event`, via an `AttributeError` rather than the guard's refusal |
| X29 | peel of the addressee's own secret | killed | `test_a_layer_peel_must_continue_the_recorded_cover_state` |
| X30 | write-time round trip | SURVIVED | probe: an unloadable row APPENDED, reopen REFUSED — **real gap (bricks the save)** |
| X31 | payload kind equals column kind | SURVIVED | probe still REFUSED (pydantic `Literal`) — equivalent |
| X32 | meta `case_hash`/`case_id` | killed | `test_a_different_seed_or_case_hash_in_meta_is_refused` |
| X33 | meta key set | killed | `test_a_newer_schema_is_refused_a_missing_or_extra_meta_key_is_refused` |
| X34 | newer schema refused | killed | same |
| X35 | row turn column equals bracket turn | SURVIVED | refined probe: a column-only mismatch LOADS; the next append succeeds; reopen REFUSED — **real gap** |
| X36 | one `action_id` per turn | SURVIVED | probe: a turn with two `action_id`s LOADS — **real gap** |
| X37 | append runs `check_state` | killed | `test_a_detective_model_cannot_be_told_about_evidence_the_player_never_found` |
| X38 | rollback on failure | killed | `test_append_refuses_an_object_that_is_not_a_registered_event` (the next append fails: a transaction was left open) |
| X39 | read-only load (I-23) | SURVIVED | probe: bytes unchanged. The I-23 byte test cannot see a read-write open; a hot-journal load would — **real gap** |
| X40 | sets sorted in `_plain` | killed | `test_restoration_is_identical_in_a_fresh_process[0]` |
| X41 | `player_confidence` → bp | SURVIVED | probe: any hypothesis makes `state_hash()` raise; no test has a hypothesis — **real gap** |
| X42 | `canonical_state` refuses floats | SURVIVED | probe: a float hashed silently — **real gap (I-17)** |
| X43 | conservative truncation cut | SURVIVED | probe: keeps a half turn (rows 187–188 of turn 40), which then loads as turn 40 — **real gap** (and PN-9) |
| X44 | truncation cut computation | killed | `test_truncation_recovery_needs_confirmation_and_yields_a_loadable_prefix` |
| X45 | stored `prev_hash` column check | SURVIVED | probe: identical load — equivalent (the column is redundant; each hash covers the running prev) |
| X46 | genesis binds the seed | killed | `test_a_different_seed_or_case_hash_in_meta_is_refused` |
| X47 | non-empty `action_id` on append | SURVIVED | probe: APPENDED, reopen REFUSED — **real gap (bricks the save)** |

**Result: 47 mutants, 29 killed (17 shipped + 12 new), 18 survived: 14 real gaps and 4 equivalent.** The shipped
claim "17 killed, 0 survived" is true of the 17 it chose. It is not evidence that the store's guards are tested:
14 of the 30 new mutants (47 %) disable a guard that matters and that no test exercises. Three of those survivors
(X30, X35, X47) let the store **write a save that it then refuses to load**.

## 6. Contract violations versus documented limitations

| Item | Contract | Classification |
|---|---|---|
| PB-1 truncation deletes valid rows, can delete all, does not repair, crashes | §26.3 step 3; I-15 (a failed operation must not report success) | **Violation** |
| PI-1 unresolvable references accepted | `CLAUDE.md` fail-closed rule (I-15) | **Violation** |
| PI-1 structurally impossible turns accepted; load weaker than append | Implementation report §3's own claims; §26.3 | **Overstated claim**; the forgery itself is the §26.1 permitted class |
| PI-2 float in state; replay crash; hash collisions | I-17; §26.3 step 5; §27.3 | **Violation** (float); collisions extend documented C-2 |
| PI-3 mixed-schema log; unbound `schema_version` | §26.3 step 1, §26.4 ("on-disk log is never rewritten" — so appends must stay readable) | **Violation (latent)** |
| PI-4 ABA | §26.2, I-14 | **Violation** (needs a concurrent writer) |
| PI-5 duplicate does not return the existing turn | §26.2 | **Violation** |
| PI-6 personality/derivations outside log and hash | §26.4, I-5 | **Violation, inherited** (Phase 6 I-6) |
| PI-7 declared solution unconfirmed | I-43 ("metadata to be CONFIRMED"), I-58 | **Gap, inherited** |
| C-1 re-chained, structurally valid but unjustified peel/value | §26.1 "Local save files are not cheat-proof" | **Documented limitation**; the C-1 text understates it (C4: a fabricated confession mints `attack@David`; C8: a forged detective model) |
| Tail deletion with no re-chain (A4); report/alias edits with no re-chain (D1, D2) | §26.1 | **Documented-class limitation**, framed inaccurately ("a forger who also edits meta and re-chains") |
| C-8 drops the last verified turn | §26.3 step 3 | **Permitted conservative reading**, only once PB-1 is fixed: correct for mid-turn breaks (F8b), loses one complete turn at turn boundaries (F8) |
| C-4 `PlayerAction` not written; C-6 no `TurnTrace` | §25 kind list; §27.1 | **Documented, not a Phase 7 exit criterion**; Phase 8/9 entry criteria |
| C-5 producer-less kinds | §26.3 | **Permitted Phase 8 dependency**, but understated (14 kinds, not 5) and only safe once PI-1 lands |
| C-7 rollback journal instead of WAL | §26.1 | **Acceptable**: export uses `backup()` and the read-only open holds |
| X1 cross-machine | §30 Phase 7 exit | **Unmeasured** (PU-1) |

## 7. Phase 6 (and earlier) inherited debt that directly affects persistence

* **Phase 6 audit I-6 / C-3** (personality not packaged) → PI-6.
* **The I-58 reader never compares `pkg.solution` with the proof** → PI-7.
* **RB-3 / I-57** ("every proof field verified or absent"): unreferenced constraint `id` labels and non-`NoStranger`
  `observer` fields are accepted mutated (D15). No semantic effect today.
* **Phase 1 `Case.content_hash` excludes `alias`**: an embedded save's alias table is editable with no seal or chain
  change, and the validator, ingress and renderer read it. Generated cases ship an empty table, so today a forger can
  only add entries.
* **Phase 2 `MemoryCorrected.corrected_value: Any`** → PI-2.
* **Phase 2/4 float fields** (`KnowledgeEntry.reliability`, `Hypothesis.player_confidence`, C-2) → the PI-2
  collisions.
* **Phase 4 `run_goto_turn`/`run_take_turn` accept any string**, and `KnowsAbout`/`HasItem` prerequisites read
  exactly those sets → C9 and C9b are runner gaps that the fold mirrors.

The Phase 6 mutation sweep, generation determinism and the 2×50 seed study were **not** re-run: they do not touch
persistence (PU-4).

## 8. Required fixes, ranked by severity

Every fix needs a test that fails today and a mutant added to `tests/persistence_mutation_check.py`. The harness
also needs:

* a green-baseline gate;
* a "failed for the guarded reason" check: exit code 1 plus the named test;
* the 14 real-gap mutants of §5, each with a test that kills it. X30, X35 and X47 come first, because each lets the
  store write a save it then refuses to load.

1. **PB-1 — make recovery safe.**
   * Diagnose with the loader itself: recompute the genesis from `case_hash` + `seed`, verify the bundle, and act only
     on a chain/tail refusal at seq *k*.
   * Return a dry-run plan (rows/turns to cut, resulting head) before `confirm=True`.
   * Cut to the start of the turn containing *k*, keeping every complete turn. Repair a head-only mismatch losslessly.
   * Never cut a healthy save, and refuse with a reason on a fold refusal.
   * Do the delete and a full re-verification in one transaction, and roll back unless the result loads.
   * Never create a file at a missing path.

   Tests: F1, F2, F2b, F3, F4–F9.
2. **PI-1 — finish the validating fold, and run it identically at load and append.**
   * Per-turn shape: a conversation turn has one `ClaimMade` by `who`, its `StatementHeard` and one `AccountHeard`
     per listed account; an exploration turn has no minds rows.
   * Peels are voiced by the turn's statement (`claims_voiced_on_peel(layers[to])` ⊆ claims, act ∈
     CONCESSION/CONFESSION).
   * Retractions are only of `who`'s own earlier, non-retracted statements, in a turn with a peel, never self.
   * Grounding entries belong to the speaker.
   * All references resolve: secrets owned, actors living, locations and objects in the case, accusation targets in
     the candidate domain. Fix the Phase 4 runners for `GoTo`/`Take` at the same time.
   * `DetectiveModelUpdate` adds at most the presented ref and leaves the other fields unchanged.
   * Run `check_state` (or its detective-model part) after every turn on load.

   Tests: C1–C10b, C15, C16, C19 refused at both boundaries; C7 refused at load.
3. **PI-2 — enforce I-17 at the boundary.**
   * Reject any float in a payload except the two documented fields.
   * Range-check those two (0 ≤ x ≤ 1, and reliability ≤ trust for `InvestigationTold` entries, I-25).
   * Have `eidolon replay` report a hashing failure as a refusal.
   * Better: convert the two models to bp.
4. **PI-4** — compare `head_hash` as well as `head_seq` inside `BEGIN IMMEDIATE`; test the B7 sequence.
5. **PI-5** — on a duplicate, return the existing turn (turn number + seq range), and expose `turn_for(action_id)`.
   Optionally, report whether the retried events differ.
6. **PI-3 — before any schema change.**
   * Either refuse writable opens of `version < SCHEMA_VERSION`, or carry the schema version per row inside the hashed
     row and upcast per row.
   * Bind `schema_version` into the genesis.
   * Extend T3 with append-then-reopen.
7. **PI-7** — after `verify_proof`, require `proof.unique`, `survivors == [solution.murderer]` and agreement on
   murder location/window. Phase 8 scoring reads the verified survivor.
8. **PI-6** — bind a digest of the derived initial state into the genesis (or meta, checked on load): knowledge,
   beliefs, memories (after boosts), personalities and initial `CharacterState`s. Record `engine_version`. A mismatch
   must refuse, or route to a converter. It must never silently re-derive.
9. **NON-BLOCKING, in order of value:**
   * PN-3: verify `sqlite_master` and run `PRAGMA quick_check` on open; keep the loaded action-id set in memory for
     the duplicate check.
   * PN-2: require the stored payload text to equal `_canon(obj)`.
   * PN-7: bind trace rows to the genesis; clear stale trace files on create/export; derive the trace name from the
     full file name.
   * PN-6: export through a fresh read-only connection, refuse `dest == self.path`, and clean the tmp file.
   * PN-8: document or wrap the exception contract, and diagnose hot journals.
   * PN-4: bind the bundle seal (or an alias digest) into the genesis.
   * PN-1, PN-10, PN-11, PN-14: correct the debt ledger and the implementation report's claims, listed in the
     appendix.

## 9. Phase 8 readiness decision

**Not ready.** Phase 8 builds the web layer on `append` (retries, two tabs, `action_id`s), on recovery (§26.3's
user-confirmed truncation) and on the fold as the backstop for its new producers. Each of these is currently
defective (PI-5, PI-4, PB-1, PI-1).

Phase 8 may start when:

* fixes 1–5 have landed with their tests and mutants;
* fix 6 has landed, or writable opens of older schemas are refused (a one-line interim);
* fix 7 has landed;
* fix 8 has landed or been accepted in an ADR that states the consequence;
* the persistence suite and the extended mutants are green, with no survivor left unexplained.

None of this needs architectural rework.

## Severity index

| ID | Severity | One line |
|---|---|---|
| PB-1 | BLOCKING | `truncate_to_last_valid` deletes verified rows (all 372 on a one-digit meta corruption), does not repair, reports success |
| PI-1 | IMPORTANT | fold accepts structurally impossible turns and unresolvable references; load checks less than append |
| PI-2 | IMPORTANT | float reaches state through `MemoryCorrected`; hash/replay crash; bp clamping collides different states |
| PI-3 | IMPORTANT | upcast → append → reopen bricks the save; `schema_version` unbound (latent until v2) |
| PI-4 | IMPORTANT | ABA: append checks head seq only and writes a broken chain with success |
| PI-5 | IMPORTANT | duplicate `action_id` returns the current head, not the committed turn (§26.2) |
| PI-6 | IMPORTANT (inherited) | personality and derived stores outside log/hash; engine change silently alters replay |
| PI-7 | IMPORTANT (inherited) | declared murderer never checked against the verified proof at load |
| PN-1 | NON-BLOCKING | tail turn removable by meta edit alone (no hashing) |
| PN-2 | NON-BLOCKING | payload bytes malleable; duplicate-key parser differential |
| PN-3 | NON-BLOCKING | no schema/integrity check: triggers, extra objects, index corruption (duplicate action appended) |
| PN-4 | NON-BLOCKING | alias, report, extra package fields, proof label fields editable without detection |
| PN-5 | NON-BLOCKING | state hash does not bind the case; three equalities differ |
| PN-6 | NON-BLOCKING | export fails from read-only saves (litter); export onto own path |
| PN-7 | NON-BLOCKING | traces not bound to their save; stale files adopted; name collisions |
| PN-8 | NON-BLOCKING | raw `AttributeError`/`ValueError`/`OperationalError`; hot-journal refusal undiagnosed; schema type errors lose their seq; `eidolon newsave` with a missing bundle exits with an uncaught `FileNotFoundError` traceback |
| PN-9 | NON-BLOCKING | incomplete turns accepted; C-8 loses a complete turn at boundary breaks |
| PN-10 | NON-BLOCKING | C-5 understated (14 producer-less kinds); `CaseSolved` overwritable, post-solve turns, I-25 reliability unchecked |
| PN-11 | NON-BLOCKING | no `PlayerAction` rows, no `TurnTrace`, no trace producer — every turn a "gap" |
| PN-12 | NON-BLOCKING | mutation harness: no baseline gate, no reason check, 17 of ~55 guards; 14 real-gap survivors among 30 new mutants, three of which let the store write a save it then refuses to load |
| PN-13 | NON-BLOCKING | non-canonical meta integers accepted; head mismatch message names only seq |
| PN-14 | NON-BLOCKING | C-3/docstring say personality uses the case id; code uses `(actor, seed)` |
| PU-1 | UNMEASURED | cross-machine/OS/Python-version replay (X1) |
| PU-2 | UNMEASURED | sessions rendered by a live model, persisted and replayed |
| PU-3 | UNMEASURED | power-loss durability of export rename; POSIX export-onto-self |
| PU-4 | UNMEASURED | Phase 6 mutation sweep / generation determinism (out of scope, not re-run) |
| PU-5 | UNMEASURED | load cost at scale (a 372-row load takes 1.85 s, of which the bundle verifier is 1.59 s; 2000-turn load not isolated) |

## Appendix — the implementation report's claims, checked

| Claim | Evidence | Status |
|---|---|---|
| 2 423 full-suite tests pass | suite #5: `2423 passed in 2908.36s`, exit 0 | **confirmed** |
| 59 persistence tests pass | suite #1, original tree: `59 passed` | **confirmed** |
| 500 / 1 000 / 2 000-turn equality | suite #2: `3 passed` | **confirmed** |
| 17 mutants killed, 0 survived | harness #3; extended audit | **confirmed for those 17**, each killed by its own test; 14 more guards matter and go untested (§5) |
| Fresh-process determinism | E3: byte-identical files under 4 hash seeds | **confirmed (stronger)** |
| "A payload must also re-serialize to exactly its stored bytes" | A2 | **refuted**: object equality, not byte equality |
| "With it, tail deletion is a refusal. (A forger who also edits meta and re-chains is debt C-1.)" | A4 | **inaccurate**: no re-chain is needed |
| "What is trusted on load: nothing in the file" | D1, D2, D3, E7b, D11 | **refuted** for alias, report, extras, `schema_version`, declared solution |
| "A refused append rolls back… unchanged (tested)" | B1–B5, B10 | **confirmed** |
| "Any other float in state raises" | C11 | **only at hash time**; append and load accept it |
| Upcaster "verified on a synthetic v1→v2 change" | E7 | **incomplete**: bricks on the first append |
| C-8 "conservative data loss of ≤ 1 turn, only with explicit `confirm=True`" | F2, F3, F1 | **refuted**: up to every row, repeatedly, and on healthy saves |
| The fold "refuses rows that name impossible provenance"; debt "Detected: … unearned accounts" | C1–C10b, C15, C16, C19; C4 | **refuted** as stated |
| C-5 lists five producer-less kinds | producer grep | **understated**: fourteen |
| "The fold never consults a weight, score, retrieval or model" | E4 | **confirmed** at runtime |
| T-24 | suite #1; E5 | **confirmed for recorded-outcome formulas only** |
