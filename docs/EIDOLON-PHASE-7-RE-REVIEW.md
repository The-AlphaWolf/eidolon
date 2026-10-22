# EIDOLON — Phase 7 independent re-review and closure (persistence)

> **This document has two parts.**
> **Part II (below, dated 2026-10-19) is the closure record for the CURRENT (FINAL) tree** — the one that contains the R-1 and F-1 repairs.
> **Part I (from "Part I — re-review of the 2026-10-18 tree") is the original independent re-review of an OLDER tree** (manifest
> `2ffcab9d…`, `store.py` `336c2d1d…`). It is kept verbatim as history: its verdict **A** was given to that tree, with R-1 open,
> and is **not** a verdict on the current tree.

# Part II — Phase 7 closure gate (2026-10-19)

## II.0 Decision

**PHASE 7 ACCEPTED — READY FOR PHASE 8.** No BLOCKING or IMPORTANT finding is open on the final tree.

How this status was reached (the order matters, because the first answer was "accepted with F-1 open"):

1. **First closure pass** (tree `42414d07…`, `store.py` `aef73ed3…`; no production edits): all checks green, and a fresh-context review of the
   R-1 repair found it correct and free of false refusals — but raised **F-1 (IMPORTANT)**: unbounded `interval` slots in claims,
   hypotheses and told entries are accepted and starve or kill the character's later turns. I reproduced it. That tree was recorded as
   "accepted with F-1 open". Those results are **superseded** (§II.1) and none was reused.
2. **F-1 repair** (this pass, on explicit instruction): one structural guard in `eidolon/store.py` (`_check_times`), 7 forgeries,
   1 boundary control, 8 mutants. The only files that differ from the first-pass tree are `eidolon/store.py`,
   `tests/test_persistence.py` and `tests/persistence_mutation_check.py` (byte-compared, 187 files).
3. **Final verification on the new frozen tree** (§II.1–II.3), all four commands: green, exit 0.
4. **Narrow independent re-check of the F-1 fix** (same reviewer, resumed; §II.5): *"Is F-1 fixed, with no false refusals and no new
   BLOCKING/IMPORTANT finding on this tree: YES."*

Evidence on the final tree:

* 263 persistence tests, 2,364 other tests, 125 mutants killed / 0 survived / 0 malformed / 0 infrastructure errors / 5 justified
  equivalent, and the 500/1000/2000-turn sessions — all exit 0 (§II.2);
* two fresh-context reviews: the R-1 fix (194 attacks; 20,254 genuine engine turns, 0 refusals; 11 sampled mutants, all real kills) and
  the F-1 fix (1,194 grid inputs; the same 20,254-turn sweep re-run, 0 refusals; 6 PI-1 F1 mutants real kills, the 2 over-tight-bound
  mutants killed as test failures); neither found a BLOCKING finding (full report
  `docs/EIDOLON-PHASE-7-R1-INDEPENDENT-REVIEW.md`, §6 and §9).

**How independent those reviews are, stated plainly.** The reviewer is a fresh subagent with a cold context that wrote none of the
code, ran its own attacks from a scratch directory, and left the tree byte-identical (it hashed before and after). It was *launched by
the session that wrote the repairs*, it received the repair's claims as its checklist, and it is the same model family. It is
independent of the author's tests and reasoning; it is **not** an organisationally separate or human review. If your release gate
needs that, treat the status as "accepted on the strength of a fresh-context review" and have a human re-run the scripts listed in
the review's §7.

**Residual, not gating:** F1-a (no mutant for the lower bound of `Moved.t`/`Said.t`), F1-b, F1-c, F-2…F-9, N-1/N-2/N-4/N-5/N-7, C-1/C-2,
and cross-machine replay (unmeasured) — §II.7–II.9. The Phase 8 producers still owe their own fold rules.

## II.1 The frozen tree

No VCS exists, so identity is a SHA-256 manifest taken **before** any verification command ran and re-taken **after** all of
them had finished (code files compared line by line: **identical**). Two trees were frozen in this closure:

| Tree | Files | Manifest digest (`eidolon/`, `tests/`, `cases/`, excl. `__pycache__`, `*.pyc`) | Status |
|---|---|---|---|
| first pass (R-1 repair) | 187 | `42414d07720195823f233e1e61c019bd20d3b8c04f2a5e0740e6c9c2657dd4e8` — `store.py` `aef73ed3…`, 248 tests, 117 mutants | **superseded** by the F-1 repair |
| **FINAL (R-1 + F-1 repair)** | 187 | **`20899f0d862bfa2e278e90646d476c762311139d575648024592918ae30d18dc`** | **verified below** |

```bash
find eidolon tests cases -type f -not -path "*/__pycache__/*" -not -name "*.pyc" | sort | xargs -d '\n' sha256sum | sha256sum   # per-file list kept as closure-evidence/final2/manifest-code.txt
```

The docs set (24–25 files, `docs/`, `CLAUDE.md`, `pyproject.toml`) was hashed too (`80343e8c…` at freeze) but changes as these reports are
written; it is not part of any verified result.

| File | SHA-256 (FINAL tree) | vs. tree of Part I |
|---|---|---|
| `eidolon/store.py` | `aedb1c39090260433c6c85ccf27c42b138c0532bc44047184155552b75b2b7cb` | **changed** (was `336c2d1d…`) |
| `tests/test_persistence.py` | `197c8f04956e917976fc683bf0c9482d2f54e9a3bf6d544ad245a35d41c6c93c` | **changed** (was `ecf8cdb7…`) |
| `tests/persistence_mutation_check.py` | `dc58bfc185f9107226f44fcca8a67630a7970decfd1efeb98a6e6f420a10de82` | **changed** (was `1244c4eb…`) |
| `eidolon/solve/package.py` | `d84c20e13f7da29ceb7acff76f67d1366348d83bd49f48ce1e31d4409ebb65cb` | unchanged |
| `eidolon/cli.py` | `883685d31a500f4e25b2c5a9bfe65be1d325c2952df9086c367abfb2b79aecaa` | unchanged |
| `eidolon/decision/turn.py` | `b0450c43dda5a06bf50104c8b0ccb39c24357db41be00aef9967a04fbaec5e0e` | unchanged |
| `eidolon/world/feasibility.py` | `03082a450068e41e48259b28a58497a486fbc2f83c222f04ccca97453b54fe1b` | unchanged (the consumer F-1 starved) |
| `cases/generated/study_party_s4.json` | `fbfa9c1c21bd725c9ac436a5b030024b52ad0998d4bc3308b013176a4b6de407` | unchanged |
| `cases/generated/study_party_s5.json` | `1a51e427b8fa0cb738db757197471ac62f6cf0b47ef53a4b4441f766ae664228` | unchanged |
| `cases/generated/manor_wing_s4.json` | `f762df353e8db19e4bb302812e0f517b6a6530eac2f04e5c8b92726f08f4f823` | unchanged |
| `cases/generated/manor_wing_s6.json` | `b749d3a0cc731c59b8d2639e6f3f320b3067014bbe336def0d0c0de377291def` | unchanged |

The only production file changed since Part I's tree is `eidolon/store.py` (by the author's edit record — there is no copy of the
old file to diff). Every result reported in Part I (174 tests, 2,364 tests, 86 mutants, the 500/1000/2000 sessions) and every result
of the first closure pass belongs to an OLDER tree and is **superseded**: none was reused.

Environment: Windows 11, Python 3.12.10, pydantic 2.13.5, SQLite 3.49.1, 16 logical CPUs.

## II.2 Final verification on the FINAL tree

All four commands ran **concurrently** (with the focused re-check), from the repository root, with `PYTHONDONTWRITEBYTECODE=1`; each
exit status was collected from the shell, not inferred. Wall times are therefore inflated. Raw outputs and exit codes are kept in the
session notes folder (`closure-evidence/final2/`).

| # | Command | Observed result | Exit | Wall |
|---|---|---|---|---|
| 1 | `python -m pytest tests/test_persistence.py -q -p no:cacheprovider` | `263 passed in 2047.60s` | 0 | 2,049 s |
| 2 | `python -m pytest -q -p no:cacheprovider --ignore=tests/test_persistence.py` | `2364 passed in 3375.20s` | 0 | ≈3,377 s |
| 3 | `python -m tests.persistence_mutation_check -j 4` | `baseline green; 125 killed, 0 survived, 0 malformed, 0 infrastructure errors, 5 justified equivalent` | 0 | ≈2,050 s |
| 4 | `EIDOLON_LONG=1 python -m pytest tests/test_persistence.py -q -p no:cacheprovider -k long_session --durations=5` | `3 passed, 262 deselected in 1842.45s` — 500 turns 59.07 s, 1000 turns 353.56 s, 2000 turns 1426.52 s | 0 | 1,845 s |

2,364 + 263 = **2,627**, the figure in `CLAUDE.md` (two separate runs of one tree; no combined run was made).

**Honest notes on how this tree got here.**
* The first mutation run after the R-1 edits (2026-10-18) reported `BASELINE IS NOT GREEN`: an older test
  (`test_knowledge_added_must_carry_investigation_provenance`) put a `KnowledgeAdded` row in an exploration turn, which the new rule
  refuses with a different message. The harness did its job ("nothing above is evidence", exit 2). The test was moved to a conversation turn
  (it still asserts the `InvestigationTold` refusal) and the run repeated.
* While adding the F-1 mutants, `F1-clock-excludes-its-last-tick` was first reported `SURVIVED` ("killed by the WRONG test"): the
  control used a module fixture, so the too-tight bound errored in the fixture instead of failing the test (the harness correctly refuses
  a fixture error as a kill). The control was made self-contained; the mutant is now killed by a test failure — and the same run shows
  the engine's own authored claims end exactly AT `t_investigation` (the bound is inclusive by necessity, not choice).

## II.3 Mutation harness: what was verified

| Requirement | Result |
|---|---|
| Baseline green before any mutant is counted | yes — the whole persistence file ran unmutated beside the mutants (exit 0; harness returns 2 otherwise) |
| Exact single-anchor match | yes — the harness refuses a mutant whose anchor does not match exactly once (`BAD`); I also checked all 125 anchors against the real tree: **0 with a count other than 1** (123 in `store.py`, 2 in `solve/package.py`) |
| Killed by the intended test | yes — pytest must exit 1 **and** a failing test id must contain one of the mutant's `fail` names; a wrong-test kill is reported `SURVIVED` |
| Categories reported separately | yes — the summary now prints killed / survived / malformed / infrastructure errors apart (it used to merge the last three; N-8) |
| Real source restored | yes — mutants run in private copies; the harness asserts `store.py` and `package.py` are byte-identical afterwards, and my post-run manifest of all 187 files is identical to the pre-run one (FINAL tree, `20899f0d…`) |

**What kind of kill each is** (the review's N-8 asked for this). I did **not** classify all 125 by kill type. The independent review
sampled 11 (8 random R-1 mutants, X45, X46, N3) and then all 8 F1 mutants, and found every one a real kill: for the 17 forgery-driven
mutants the shipped forgery is *accepted* under the mutant (so each new forgery trips only its own guard); the 2 over-tight-bound
mutants are killed as genuine test failures (the store's own false refusal).
Known exceptions, by design: at least three mutants are killed by a **crash** instead — `peel-past-the-end-unchecked`,
`R1-layer-scope-of-no-secret`, and the older `conversation-without-a-statement` — because with the guard removed the next line raises
`IndexError` / `AttributeError`; the property tested there is "refuses with `SaveRefusal`, not a raw exception". The eight
message-only kills Part I listed were re-built as single-guard forgeries (or, for `two-statements-in-a-turn`, moved to EQUIVALENT).

### The five EQUIVALENT mutants, individually

Each was probed by me in a private copy with the guard removed, offering the input the guard exists for to a live `Save.append`
**and** as a re-chained load (script `equiv_probe.py`). The independent review probed the same five.

| # | Entry | Probe under the mutant | Verdict |
|---|---|---|---|
| 1 | **X23** — no minds (`CharacterState`) rows outside a conversation turn | all 7 kinds (`EmotionalDelta`, `TrustChange`, `SuspicionShift`, `PressureChange`, `ComposureChange`, `CoverStateDelta`, `DetectiveModelUpdate`) in an exploration turn: **refused at both boundaries** — six by the `KeyError` on `chars[None]` ("turn does not fold: None"), `PressureChange` by its owner check | equivalent for acceptance. **The harness text is inaccurate**: it cites "the statement-required rule", which applies only to conversation turns; the real backstop is the `KeyError`. The message under the mutant is poor |
| 2 | **X26** — one `TurnCommitted` per turn | a second bracket: refused ("event kind 'TurnCommitted' has no fold") at both boundaries | equivalent |
| 3 | **X31** — payload `kind` must equal the column kind | a re-chained file whose column says `ClaimRetracted` over a `ClaimMade` payload: still refused (pydantic `Literal`), but as stage `None` "unreadable save: ValidationError" instead of stage `fold` | equivalent **for acceptance**; **not** for diagnostics — recovery would raise instead of returning a plan (review §4.1) |
| 4 | **two statements in one turn** (new) | a second `ClaimMade`: refused at both boundaries ("ClaimMade 'S00019' already committed with different content", from `apply_decision`); statement ids are forced to `S{turn}` so a second one always clashes | equivalent (the independent review reached the same result) |
| 5 | **float range 0 ≤ x ≤ 1** | there is no separate code to mutate. 1.5, −0.5, 1.00005, 0.50001: refused by the basis-point grid check at both boundaries; NaN refused ("does not validate"); **±inf raises a raw `OverflowError` from `append`** | equivalent **for finite values only**; ±inf is the open N-5 |

X45 and X46, which Part I rejected as "not equivalent", are no longer in this list: each has a test (`test_X45_…`, `test_X46_…`)
and a mutant, both killed, and the independent review confirmed both as real kills.

## II.4 Reconciliation with the previous review

### PB-1 and PI-1 … PI-7

Part I verified these independently on the OLD tree. On the FINAL tree they are covered by the green suite (263) and the
mutants (e.g. `trunc-*` for PB-1, `PI3_*`, `head-hash-not-compared-on-append`, `duplicate-does-not-return-its-turn`,
`digest-omits-*`, `declared-*-unchecked`) — **this pass did not re-attack them independently**; the focused review's scope was the
R-1 fix, N-3, the mutants and a false-refusal sweep. The only changes to `store.py` in the recovery path are the hot-journal guard
at the top of `_repair`; the PB-1 logic is unchanged.

| ID | Disposition at Part I | Now |
|---|---|---|
| PB-1 recovery | repaired | unchanged; suite + `trunc-*` mutants green; hot-journal refusal added (N-3) and independently verified |
| PI-1 one fold, both boundaries | repaired (core); **R-1 open** | **R-1 repaired** and **F-1 repaired** (§II.5), each reviewed by a fresh-context reviewer |
| PI-2 floats | repaired | unchanged; N-5 (±inf) open |
| PI-3 schema/upcast | repaired | unchanged |
| PI-4 head hash / ABA | repaired | unchanged |
| PI-5 duplicate `action_id` | repaired | unchanged |
| PI-6 derived initial state | repaired | unchanged; X46 now pins the seed binding |
| PI-7 declared solution | repaired | unchanged; N-7 (victim/weapon/method/event/approach unconfirmed) open |

## II.5 R-1 and F-1: the forgeries, the independent reviews

**Forgeries in the suite.** `FORGERIES` has 76 entries; **32 are named `R1_*` and 7 `F1_*`** (the brief for this pass said 17 R-1
forgeries — I cannot find that figure in the artifacts; 32 is the count in the tree). Six older entries were rebuilt so each trips only its own guard
(`peel_that_does_not_advance`, `peel_of_another_characters_secret`, `retraction_of_another_speaker`,
`retraction_by_an_uncommitted_statement`, `claim_bound_to_another_statement`, `a_character_who_does_not_exist`); the three float/told
forgeries (`a_float_in_an_overlay`, `told_more_reliably…`, `reliability_off_the_basis_point_grid`) were moved into the addressee's
conversation turn so the new addressee rule cannot mask the float/trust guard they test; and one entry was added
(`peel_of_a_secret_its_character_does_not_own`). Each entry is run
twice — refused by `Save.append` with the state/seq/head unchanged, and refused by `Save.open` on a correctly re-chained file — so
76 × 2 = 152 refusal tests. Each R-1 and F-1 guard has a mutant (§II.3).

**Guards added** (all structural; no weight recomputed, I-22): epistemic rows and `IncidentalPinned` only about the addressee;
claim / hypothesis / told-entry propositions name only case actors, places, objects (kit names included); `Lied`/`Planted` must name
held material; statement and incidental `layer_scope` must name the speaker's own secret and an in-range layer; `MemoryCorrected.field`
must be a field of the memory's distortion; `CoverStateDelta` slips, contradictions and counters; one `DetectiveModelUpdate` per turn;
peel voicing by equality; unique claim ids; `turn_id` (and `record`/`revision`) equals the turn.

**Independent focused review** (`docs/EIDOLON-PHASE-7-R1-INDEPENDENT-REVIEW.md`, tree hash verified before and after, 187 files
byte-compared):

| Check | Result |
|---|---|
| Re-chained equivalence | 194 attacks, each offered to a live `Save.append` and as a re-chained extra turn through `Save.open`: **the boundaries agreed on all 194**; no refused append changed rows, meta, `last_seq`, `last_hash` or state hash |
| R-1 table N1–N25 (old re-review) | each that still applies is refused by its intended guard (Attitude/Motive claims are stopped earlier by the float rule) |
| Expected refusals | 119 of 120 refused at both boundaries; the one accepted (repeated claim ids across *different* statements) was the reviewer's mistaken expectation — it is legitimate |
| Legitimate rows | 42 of 42 accepted at both boundaries with equal state hashes |
| Documented class (C-1 / "still accepted") | 32 rows accepted at both boundaries, as designed |
| Row order | 403,440 permutations of four genuine turns: no raw exception; every accepted order folds to the same state hash |
| Fuzz | 600,000 single-leaf substitutions on 8 genuine templates: no raw exception from `fold_turn` or `_decode`; no reference slot accepted an unresolvable value |
| **False-refusal sweep** | **20,254 genuine engine turns, 0 refusals**: all four cases, every living character, seeds 7/11/23, bots, all 16 query kinds (meta and coercion included), every held evidence/statement id presented to every character; folded hash = live hash after every append; reload = live. Rows over 18,814 turns: 89 `LayerPeel`, 159 `ClaimRetracted`, 7,788 `DetectiveModelUpdate`, 10 `AccountHeard`, 14,739 `CoverStateDelta`, 504 `MetaAttemptLogged` |
| Murderer paths | the account-token path and the layer-0 peel were driven through the real engine and `Save.append` in all four cases. **Not reachable:** the murderer's deeper path (in `manor_wing` no layer-1 breaker set exists), so no genuine `LayerPeel 1→2` or CONFESSION turn was produced |
| Hot journal (N-3) | `plan_truncation`, `truncate_to_last_valid(confirm=False)` and `(confirm=True)` leave db and journal byte-identical and refuse (stage `journal`); a writable open recovers to the pre-crash hash; a 0-byte journal does not block; a missing path creates no file; under the N3 mutant the dry run does roll back |
| Mutation spot-check | 8 random R-1 mutants + X45 + X46 + N3: each unmutated selection passes, each mutant fails the intended test, and the forged turn is **accepted** under the mutant — all 11 real kills |

Verdict of that review: *"Is the R-1 fix correct and free of false refusals on this tree: YES."* BLOCKING: none.

### F-1 (IMPORTANT): unbounded `interval` slots — found by the first review, **fixed**

*The finding.* `Claim`/`Hypothesis`/`KnowledgeAdded` propositions with an interval such as `At(David, Study, (0, 2**40))` were accepted at
both boundaries. `world/feasibility._compile` enumerates every tick of every standing `At`/`NotAt` claim
(`for t in ticks(p.interval)` in `eidolon/world/feasibility.py`), so the poisoned character's later turns got slower or died. The
reviewer ran `2**40` once and got a raw `MemoryError` on the next `run_ask_turn`; I did **not** repeat that. I reproduced the mechanism
at a safe size before the fix: `At(David, Study, (0, 2_000_000))` was accepted by `Save.append`, the file reloaded, and a David ask went
from 0.01 s to 0.31 s (31×); cost grows linearly with the interval (`closure-evidence/f1.py`).

*The fix* (`eidolon/store.py`, `_check_times`, called from `_check_proposition`, so claims, hypotheses and told entries all pass it): any
`interval` slot must satisfy `0 ≤ start < end ≤ case.t_investigation`, `Moved.t`/`Said.t` must satisfy `0 ≤ t ≤ case.t_investigation`,
and `Said.proposition` is checked recursively. Structural; no weight is consulted. **The bound is inclusive and that matters:** the
engine's own authored layer-0 claims end exactly AT `t_investigation` (120), so a bound off by one false-refuses real turns. The scan
of authored data (mine, then independently confirmed): 3,620 time slots across knowledge, beliefs, secrets and evidence of the four
cases, **0 outside `[0, 120]`**, 194 ending exactly at 120. Tests: 7 `F1_*` forgeries (claim far beyond / one tick past / before time
zero / `Moved` / nested `Said`, hypothesis, told entry), one self-contained boundary control
(`test_F1_the_clock_is_inclusive_…`: the widest legal claim and `Moved`/`Said` at the edges are accepted, reload, and the character is
still askable), and 8 mutants.

**Independent re-check of the fix** (same reviewer, resumed with the new hashes; report §9; store/test/harness hashes verified before and
after; all 187 files byte-compared, exactly three differ from the first-pass tree):

| Check | Result |
|---|---|
| Its own F-1 reproductions (At/Heard `[0, 2^40)`, `[-2^40, 0)`, `Moved t=2^40`; as claim, hypothesis, told entry) | all refused at `Save.append` and at a re-chained `Save.open`, state/rows/head unchanged; later asks still work |
| Variant grid | 1,194 inputs across all 11 interval kinds, `Moved.t`, `Said.t`, `Said` nested to depth 3; values include end = 121, start = −1, reversed, bool, float, str, wrong length, huge ints: **255 valid accepted, 552 out-of-clock refused by the clock guard, 387 malformed refused; 0 accepted bad slots, 0 boundary disagreements, 0 raw exceptions** |
| Other unbounded consumers | the only claim-data loops are `world/feasibility._compile` and `world/facts` (`ticks()`), both now bounded; no other numeric proposition slot remains |
| False refusals | the 20,254-turn sweep re-run on the new tree: **0 refusals**; engine claims reach the inclusive bound (`(0, 120)`); the earlier 194-attack battery re-run: 186 identical, 6 R2 attacks flipped to REFUSE, 0 of the 42 must-accept attacks refused |
| Mutants | 6 PI-1 F1 mutants: real kills (forgery accepted under the mutant); `F1-clock-excludes-its-last-tick` and `F1-moved-tick-excludes-the-last-tick`: killed as test failures |

Verdict of that re-check: *"Is F-1 fixed, with no false refusals and no new BLOCKING/IMPORTANT finding on this tree: YES."*
New NON-BLOCKING items from it: **F1-a** — no mutant covers the lower bound of `Moved.t`/`Said.t` (dropping `0 <=` survives all selected tests;
no test uses a negative `t`; the shipped code does refuse `t = −1`). Left open rather than starting a third verification cycle: it is test
quality, not a guard defect, and should be folded into the next change that touches `store.py` (add a `Moved(t=-1)` forgery and the mutant).
**F1-b** — `MemoryCorrected.corrected_value` is `Any` and could carry an interval; nothing reads it today, so it is inert; whoever wires
a consumer must apply the same clock bound. **F1-c** — an in-clock claim that contradicts the speaker's standing claims is accepted (the
documented C-1 class): every later turn of that character is then rejected `CONTRADICTS_PRIOR`, with no crash or memory exhaustion.

### Other findings of the first review (NON-BLOCKING)

F-2 `append` folds the caller's objects, `open` folds decoded ones (a `model_construct`ed bad claim raises a raw `AttributeError` from
`append`; load refuses cleanly; nothing committed). F-3 turn-valued fields are not tied to the turn (`Hypothesis.created_turn`/`updated_turn`,
`InvestigationTold.by_detective_turn`, `KnowledgeEntry.acquired_at`; inert today). F-4 `layer_scope` is range-checked, not tied to the
current layer. F-5 own-id fields accept anything (`''`; a `KnowledgeAdded` id equal to a sealed id is silently ignored). F-6 a non-empty
all-zero journal makes `plan_truncation` refuse with advice that does not clear it (delete the file by hand). F-7 carry-overs (X31
justification, N-5, append-time `stage` is `None`). F-8 Phase 8 integration hazards (§II.9). F-9 `contradictions_caught`/`slips_used`
accept removal/reordering of ids already held (unreachable today).
**UNMEASURED on this data:** kit place/item names (no case has one), slips (none in any case; a synthetic slip behaved), a genuine
CONFESSION / `LayerPeel 1→2` turn.

## II.6 Recovery and transactionality (current tree)

* Refused appends leave file, `last_seq`, `last_hash` and state hash unchanged — 76 × 2 suite tests, plus the reviewer's 194 attacks
  (it asserted this on every refusal).
* Replay equality: folded state = live state after every turn in the 500/1000/2000-turn sessions (run 4), in the 1793-turn sweep I ran
  during the repair, and in the reviewer's 20,254-turn sweep.
* Recovery: the PB-1 tests are green; the dry run is read-only including with a hot journal (N-3); a hot journal is refused by both
  entry points, never rolled back.
* Not re-attacked this pass: the 33 damage scenarios of Part I §3 (unchanged logic; covered by the suite).

## II.7 Open findings carried forward

| ID | Severity | State |
|---|---|---|
| F-1 unbounded `interval` slots | was IMPORTANT | **closed** (§II.5); re-checked independently |
| F1-a no mutant for the lower bound of `Moved.t`/`Said.t` | NON-BLOCKING | open (test quality); fold into the next `store.py` change |
| F1-b `MemoryCorrected.corrected_value` could carry an interval | NON-BLOCKING | open, inert until a consumer exists |
| F1-c in-clock claim contradicting the speaker's own claims | NON-BLOCKING | documented C-1 class |
| N-1 turn-start recovery drops the previous complete turn | NON-BLOCKING | open; documented in KNOWN-DEBT C-8 |
| N-2 tail deletion described as "rows intact, 0 removed" | NON-BLOCKING | open |
| N-4 `initial_digest` record damage misdiagnosed as drift | NON-BLOCKING | open |
| N-5 raw `OverflowError` (±inf) / `ValidationError`→"unreadable" / head message names only the seq | NON-BLOCKING | open |
| N-6 `Attitude.intensity`/`Motive.strength` floats | NON-BLOCKING | recorded in KNOWN-DEBT C-2 |
| N-7 declared victim/weapon/method/event/approach unconfirmed | NON-BLOCKING | open |
| N-3, N-8, X45, X46, R-1, F-1 | — | **closed** this cycle |
| F-2 … F-9 | NON-BLOCKING | open (§II.5) |
| PN-1, PN-3…PN-6, PN-8, PN-10 | NON-BLOCKING | ledgered, KNOWN-DEBT C-12 |

## II.8 Residual debt and the threat model

**C-1** (`docs/EIDOLON-KNOWN-DEBT.md`): a forger who recomputes the hash chain and the head can still inject a *structurally valid but
unjustified* turn — an unearned peel, a fabricated CONFESSION, an uncomputed pressure/trust value, `Accusation` in a conversation turn,
`CaseSolved(correct=True)` without an accusation. Detecting these needs the weight/strategy code, which I-22 forbids in the fold.
**Documented threat model (§26.1): local save files are not cheat-proof.** What is guaranteed: an edit that does not re-chain is refused;
a re-chained edit cannot produce a turn the engine could not have shaped, except through the open NON-BLOCKING items (F-2…F-9, F1-a…c); hosted deployments keep saves server-side and the
client submits actions, not events.
**C-2** (inherited I-17 debt): `Hypothesis.player_confidence` and `KnowledgeEntry.reliability` are floats admitted only on the
basis-point grid; `Attitude.intensity` and `Motive.strength` are floats that are *refused* (latent; decide in Phase 8).

## II.9 Cross-machine replay, and Phase 8 entry assessment

**Cross-machine replay (X1) remains UNMEASURED.** Not re-measured in this pass. Part I's proxy (Python 3.14.6 vs 3.12.10, same machine:
identical hashes, rows and chain head) still stands as the only evidence; the initial-state digest rounds floats to millionths (C-11).
Measure on a second OS before external playtests (Phase 9). It is a Phase 7 exit criterion still to be measured, not a Phase 8 dependency.

| Entry condition | Status |
|---|---|
| Persistence suite, rest of suite, mutation check, long sessions on the final tree | met (§II.2): 263 / 2,364 / 125 killed, 0 survived / 500-1000-2000 |
| No BLOCKING finding open | met |
| R-1 and F-1 repaired and independently exercised | met |
| No false refusal on genuine turns | met: 0 in 20,254 (reviewer, final tree) + 1,793 (author) turns |
| F-1 (IMPORTANT) | **closed** on the final tree |
| Phase 8 producers add their own fold rules | **open, by design:** `HypothesisChanged` (`updated_turn == turn`, F-3; the `Motive`/`Attitude` float decision, N-6), `CaseSolved.correct` against the proven survivor and no turns after solve (PN-10), `contradictions_caught` id resolution (F-9) |
| Phase 8 integration hazards (F-8) | a claim grounded in a same-turn `KnowledgeAdded` needs the told row **before** `ClaimMade`, but the engine appends minds rows after it; `run_ask_turn` hands the strategy `turn_id = state.turn_counter` (the previous turn), which would trip the new `turn_id == turn` rule — a producer must pass the current turn |
| Cross-machine replay | unmeasured, not a Phase 8 gate |

Phase 8 has **not** been started.

---

# Part I — re-review of the 2026-10-18 tree (historical)


Date: 2026-10-18. Role: independent hostile reviewer. I did not write the repairs.
Scope: the repairs claimed in `docs/EIDOLON-PHASE-7-REPAIR-REPORT.md`, checked against the review findings PB-1 and
PI-1…PI-7 of `docs/EIDOLON-PHASE-7-HOSTILE-REVIEW.md`. The contract is `docs/EIDOLON-ARCHITECTURE.md` §26, §27 and §30,
the invariants they cite, and the house rules in `CLAUDE.md`.

I modified no production code, test, fixture or report; this file is the only addition to the tree. Every attack ran
from a scratch directory outside the repository and imported the real tree read-only. Every mutant ran in a private
copy. Phase 8 was not started.

## Verdict

**A. PHASE 7 ACCEPTED — READY FOR PHASE 8** *(verdict on the 2026-10-18 tree `2ffcab9d…` only; superseded by Part II for the current tree)*

The blocker is fixed:

* Recovery never destroyed a verified row in 33 damage scenarios, including every scenario from the original review.
* A healthy save is never touched.
* Each refusal names the stage that refused.
* The dry run reports exactly what confirming would do.
* The repair is proven inside its own transaction, and a repair that would not load is rolled back.

PI-2 through PI-7 are fixed, and I verified each one independently.

PI-1's core is fixed:

* append and load run one function, `fold_turn`, so the two boundaries agreed on every one of roughly 70 forged
  inputs (all valid re-chains, so the hash chain was not what refused them);
* `check_state` runs after every turn;
* every forgery in the shipped table is refused for its stated reason.

No genuine turn was refused: 664 engine turns across all four generated cases and every speaker, plus the full
account-delivery and murderer-peel path in all four cases, appended and reloaded to the live state hash.

Every number the author reported was reproduced: 174 persistence tests, 2364 other tests, the 500/1000/2000-turn
sessions, and the mutation run (86 killed, 0 survived, 6 marked equivalent).

The verdict is not B. The open items below are real, and one of them, **R-1, is IMPORTANT**: the fold still accepts
some structurally impossible rows and some unresolvable nested references, and three statements in the repair report
claim more than the code does. But every R-1 row needs one of two things:

* a re-chained local file, which §26.1 explicitly does not protect ("Local save files are not cheat-proof"); or
* a producer that does not exist yet.

None of the R-1 rows can come from honest play or from a hosted deployment, where saves stay on the server. None
crashes the engine. Phase 8 creates producers for only two of the affected kinds: `HypothesisChanged` and `CaseSolved`.
Their fold rules belong with those producers (§9). The project has accepted a phase with IMPORTANT findings still open
before: Phase 4 went to Phase 5 with 17 open.

The verdict is not C. Nothing here needs architectural change.

## 1. Source snapshot reviewed

The tree is not a git repository, so the snapshot is a SHA-256 manifest of 210 files. It covers `eidolon/`, `tests/`,
`cases/`, `docs/`, `CLAUDE.md` and `pyproject.toml`, excluding `__pycache__`. I took it before any command ran, and
re-took it after every run had finished:

```bash
find eidolon tests cases docs CLAUDE.md pyproject.toml -type f -not -path "*/__pycache__/*" -not -name "*.pyc" | sort | xargs -d '\n' sha256sum | sha256sum
```

Manifest digest before: `2ffcab9d63a962f7b82e7524241ce5d73a0c530e79358932ff444c1d71a58229`. After: **identical**. No
`__pycache__` or `.pyc` file newer than the snapshot appeared, and `.pytest_cache` was not touched. This report was
written after the second manifest was taken.

| File | SHA-256 | mtime (+0530) |
|---|---|---|
| `eidolon/store.py` | `336c2d1d1e7cc178961192ec9eed9cc8b10aaf606ad98899cba8916a205d1ab9` | 2026-10-17 23:41:23 |
| `eidolon/decision/turn.py` | `b0450c43dda5a06bf50104c8b0ccb39c24357db41be00aef9967a04fbaec5e0e` | 2026-10-17 23:22:13 |
| `eidolon/decision/exploration.py` | `8f51bb5cdf24b21335b06117624678bcc8c1c9756399265a126e2d3b953b7ede` | 2026-10-17 23:22:13 |
| `eidolon/solve/package.py` | `d84c20e13f7da29ceb7acff76f67d1366348d83bd49f48ce1e31d4409ebb65cb` | 2026-10-17 23:21:24 |
| `eidolon/cli.py` | `883685d31a500f4e25b2c5a9bfe65be1d325c2952df9086c367abfb2b79aecaa` | 2026-10-17 23:34:39 |
| `eidolon/solve/proof.py` | `84953ad9e1087a0a1c25ae06dbe1872ba33e7ae7fdb0be569f4e2f0816ff290c` | 2026-10-09 02:57:29 |
| `eidolon/solve/session.py` | `83b7dcfc4a8892eb294dd69fac24cc306c0f47d9da560e9c95f65900ea6eab7f` | 2026-10-06 09:23:45 |
| `tests/test_persistence.py` | `ecf8cdb7ef35ecd31e0a800edf77076537d20448d8f7ca7c50e2e7c88dccf4f9` | 2026-10-18 00:03:31 |
| `tests/persistence_mutation_check.py` | `1244c4ebf6f03296fdb964b06ddc2720b0b3c291e893d21d241cf629369cb731` | 2026-10-18 00:03:31 |
| `docs/EIDOLON-ARCHITECTURE.md` | `c9fb2beb0500e662584b393047f7d8bbb4025d717beab1bc6f612f71bc50c8fb` | 2026-10-06 09:50:46 |
| `docs/EIDOLON-PHASE-7-REPAIR-REPORT.md` | `e8213cd1db77bace81891626549c131b25b3757ea2a1b7c796c7dea05c73f19a` | 2026-10-18 00:55:36 |
| `docs/EIDOLON-PHASE-7-HOSTILE-REVIEW.md` | `fa8b3be3e2616f2c7b7b43f7007356698677579ccf4a0ce301765bbb2765302b` | 2026-10-17 23:14:21 |
| `docs/EIDOLON-KNOWN-DEBT.md` | `21bba314b5b4d47fd818d68f288dc4ef3747c40a09fc0c9f184b244eba454a58` | 2026-10-17 23:44:07 |
| `cases/generated/study_party_s4.json` | `fbfa9c1c21bd725c9ac436a5b030024b52ad0998d4bc3308b013176a4b6de407` | 2026-10-15 09:59:10 |
| `CLAUDE.md` | `677a2ad1decd87e083d89b3e31460e1ba5d0e64d29ee58d915c9a55820754d80` | 2026-10-18 00:42:58 |

Environment: Windows 11 (win32), Python 3.12.10, pydantic 2.13.5, SQLite 3.49.1, 16 logical CPUs. `eidolon` is imported
from the working tree; it is not pip-installed. For a cross-interpreter check I also used Python 3.14.6 with pydantic
2.13.4 on the same machine (§7).

**Base save** used by most attacks: `study_party_s4`, seed 7, one `GoTo Study`, every search, then 60 David asks
(every fifth presents held evidence), then 3 Elena asks so that Elena has standing statements. Result: **390 rows, 74
turns, state hash `20d2e5f213903042…`**. Each attack used a fresh byte copy.

## 2. Commands and observed exit codes

Runs 1–4 ran **concurrently** in the original tree, with `PYTHONDONTWRITEBYTECODE=1` and `-p no:cacheprovider`. The
mutation harness copies the tree itself. My attack scripts ran alongside them, so every wall time is inflated.

| # | Command | Result | Exit | Wall |
|---|---|---|---|---|
| 1 | `python -m pytest tests/test_persistence.py -q -p no:cacheprovider` | `174 passed in 982.51s` | 0 | 986 s |
| 2 | `python -m pytest -q -p no:cacheprovider --ignore=tests/test_persistence.py` | `2364 passed in 2827.71s` | 0 | 2831 s |
| 3 | `EIDOLON_LONG=1 python -m pytest tests/test_persistence.py -q -p no:cacheprovider -k long_session --durations=5` | `3 passed, 173 deselected in 1039.86s`: 500 turns 63.92 s, 1000 turns 281.44 s, 2000 turns 692.15 s | 0 | 1043 s |
| 4 | `python -m tests.persistence_mutation_check -j 4` | `baseline green; 86 killed, 0 survived or malformed, 6 justified equivalent` | 0 | 990 s |
| 5 | Attack scripts (§3–§7), scratch directory, `PYTHONPATH` = the real tree | outcomes below | 0 after fixing my own harness bugs (listed in the next paragraph) | — |
| 6 | Manifest re-taken | identical | — | — |

**No combined full-suite run was made.** The project total of 2538 is the sum of runs 1 and 2 (2364 + 174), from two
separate runs of the same snapshot.

My own harness defects, each fixed and re-run:

* My row reader could not open a file I had deliberately cut short (the original review hit the same problem).
* One `NameError`.
* A continuous-versus-resumed comparison reused action ids.
* My injector read `.turn` off a reordered first row.
* My injector could not encode `inf`.

None of these was a defect in the code under review.

## 3. PB-1 — recovery: verified

Each scenario starts from a byte copy of the base save (390 rows). "Rows deleted" counts rows present before the repair
and absent after it.

| Scenario | Load before | `plan_truncation` | Dry run left the file identical | `truncate(confirm=True)` | Rows deleted | Load after |
|---|---|---|---|---|---|---|
| F1 healthy | OK | `none` | yes | returns 390 | 0 | OK, identical hash |
| F2 one hex digit of `meta.genesis` | REFUSED `genesis` | `reset_meta` | yes | 390 | **0** | OK, identical hash |
| F2b `meta.seed` 7→8 | REFUSED `initial` | `refuse` (`initial`) | yes | REFUSED | 0 | still REFUSED (correct) |
| F3 chain-valid row the fold refuses (`S_nope`) | REFUSED `fold` | `refuse` (`fold`) | yes | REFUSED | 0 | still REFUSED (correct) |
| F4 `genesis` meta row deleted | REFUSED `meta` | `refuse` | yes | REFUSED | 0 | — |
| F5 missing path | — | `SaveRefusal`; **no file created** | — | — | — | — |
| F6 `NaN` in row 200 | REFUSED `chain` | `cut`, keep 198 | yes | 198 | 192 (the damaged turn and everything after it) | OK |
| F7 `head_seq` + 1 | REFUSED `head` | `reset_meta` | yes | 390 | 0 | OK, identical hash |
| F8 first row of turn 40 damaged | REFUSED `chain` | `cut`, keep 186 (turn 39 kept) | yes | 186 | 204 | OK |
| F8b middle row of turn 40 damaged | REFUSED `chain` | `cut`, keep 186 | yes | 186 | 204 | OK |
| F9 file cut to 80 % | REFUSED (malformed) | `SaveRefusal` (unreadable) | yes | REFUSED | 0 | — |
| F10 no `confirm` | REFUSED | `cut` | yes | `ConfirmationRequired` carrying the plan | 0 | unchanged |
| `meta.initial_digest` one digit | REFUSED `initial` | `refuse` (`initial`) | yes | REFUSED | 0 | — (see N-4) |
| `meta.case_hash` one digit / `case_id` edited | REFUSED `bundle` | `refuse` | yes | REFUSED | 0 | — |
| `meta.engine_version` edited | **OK** (diagnostic only, by design) | `none` | yes | 390 | 0 | OK |
| `schema_version` = 0 / extra meta key | REFUSED `meta` | `refuse` | yes | REFUSED | 0 | — |
| `head_seq` = `abc` / one `head_hash` digit | REFUSED `head` | `reset_meta` | yes | 390 | 0 | OK, identical hash |
| one character of the embedded bundle | REFUSED `bundle` | `refuse` (`bundle`) | yes | REFUSED | 0 | — |
| genesis digit **and** chain break at row 100 | REFUSED `genesis` | `refuse` (`genesis`) — not guessed | yes | REFUSED | 0 | — |
| genesis digit **and** last turn deleted | REFUSED `genesis` | `reset_meta`, "rows are intact" | yes | 384 | 0 | OK at 384 (see N-2) |
| last turn's rows deleted, `meta` untouched | REFUSED `head` | `reset_meta`, "rows are intact; removes 0 rows" | yes | 384 | 0 | OK at 384 (see N-2) |
| row 187 (turn 40's bracket) deleted | REFUSED `chain` | `cut`, keep **180** | yes | 180 | 209: **complete turn 39 dropped** (N-1) | OK |
| row 188 (turn 40, second row) deleted | REFUSED `chain` | `cut`, keep 186 | yes | 186 | 203 | OK |
| row 1 damaged | REFUSED `chain` | `cut`, keep 0 | yes | 0 | 390 (no valid prefix exists) | OK, empty |
| turn 40's bracket with both `kind` and `payload` zeroed / its turn column set to 39 | REFUSED `chain` | `cut`, keep 180 | yes | 180 | 210: turn 39 dropped (N-1) | OK |
| fold-refused row early **and** chain break late | REFUSED `chain` | `refuse`: "no cut leaves a loadable save" (`fold`) | yes | REFUSED | **0** (in-transaction proof rolled back) | — |
| re-chained out-of-range bp (pydantic `ValidationError`) | REFUSED (stage `None`) | **raises** `SaveRefusal` (unreadable) instead of returning a plan | yes | REFUSED | 0 | — (N-5) |
| hot journal from a crashed append | read-only open REFUSED | `none` | **NO: the dry run rolled the journal back** | — | 0 committed rows | (N-3) |
| `truncate` while another writable `Save` is open | — | — | — | completes | 0 | the other writer's next append succeeds; a real cut gives it `StaleAppend` (head-hash check, PI-4) |
| v1 save under a v2 engine (upcaster present) | read-only OK | `cut` | yes | 296 | — | reloads; `meta.schema_version` still 1; no v2 row written |

Checklist:

| Requirement | Result |
|---|---|
| A healthy save is never modified | yes |
| A break between complete turns keeps every prior complete turn | yes, when the damaged row is recognisable as a turn start; otherwise the previous complete turn is also dropped (N-1) |
| A break inside a turn removes only that turn | yes |
| A damaged genesis or head is diagnosed without deleting verified rows | yes |
| A bundle, initial-state or fold refusal is not treated as a recoverable chain problem | yes; all three are `refuse` with their stage |
| `plan_truncation` is read-only | yes, **except with a hot journal** (N-3) |
| `confirm=True` is required | yes |
| A missing path is not created | yes |
| The repair is verified in the same transaction, and rolled back completely if verification fails | yes (also killed by mutant `trunc-does-not-reverify`) |

Two cases can only be diagnosed, not repaired by cutting, and the tool does not guess at either:

* damage where the recomputed genesis does not verify the chain **and** `meta.genesis` disagrees (it refuses);
* tail deletion (it accepts the shorter log, but describes it inaccurately — N-2).

## 4. PI-1 — one fold for append and load: core verified, coverage incomplete (R-1)

**Equivalence.** `Save.append` and `_replay` both call `fold_turn`, which ends in `check_state`. The original review's
C7 case, a detective model ahead of its discovery, is now refused at load. I offered every forged turn below twice:

1. to `append` on a live save;
2. as a correctly re-chained extra turn (valid hashes and head) loaded through `Save.open`.

The two boundaries **agreed on every input**. Refused appends left both the file bytes and the in-memory state hash,
`last_seq` and `last_hash` unchanged; my helper asserts this on every refusal.

**What is refused** (the shipped 36-entry `FORGERIES` table at both boundaries, re-run green, plus my probes):

* turn shape: one statement by the addressee, heard exactly once with exactly its accounts; two statements; a bare
  conversation bracket; minds rows without a statement;
* peels: an unvoiced peel, a peel beside a non-concession, a peel of another character's secret, a peel that does not
  advance or runs past the cover;
* retractions: of another speaker's words, of itself, by an uncommitted statement, outside a peel turn;
* claims: by another speaker, bound to another statement, grounded in another character's knowledge or in nothing;
* accounts: unearned tokens, and an `AccountHeard` row its statement does not list;
* unknown event-level references: place, item, secret in `PressureChange`, actor in `SuspicionShift`, accusation
  target, speaker of `IncidentalPinned`, character in `TurnCommitted`;
* detective model: one that rewrites other fields, or is shown everything at once;
* everything else in the table: `TurnCommitted.action_id` disagreeing with the row, a duplicate row, `CaseSolved`
  twice, a hypothesis on material never held, and an over-trusted or off-grid `KnowledgeAdded`;
* row order: `StatementHeard` or `ClaimRetracted` before `ClaimMade`, `TurnCommitted` not first, and two turns swapped
  (all refused). Rows whose order does not matter (`LayerPeel` or minds rows before `ClaimMade`) fold to the
  **identical** state hash as the genuine order, which is benign.

**No false refusals.** Every turn the real runners produced appended, and the folded state equalled the live state
after every append:

* the sweep: 664 genuine turns across `study_party_s4`, `study_party_s5`, `manor_wing_s4` and `manor_wing_s6`, every
  living character, with presented evidence **and** presented statements, meta and coercion queries, and hostile and
  provisional-accusation features. It produced 5 `LayerPeel`, 3 `ClaimRetracted`, 44 `Discovery`, 139
  `DetectiveModelUpdate` and 72 `MetaAttemptLogged` rows, with zero store refusals and reload equal to live in all 4;
* the RB-1 legitimate path in all four cases: the housekeeper delivers her account token through real questions, then
  the murderer's layer 0 falls to a real presentation. Every turn went through `Save.append`, and the reload has the
  peel and the token.

### R-1 (IMPORTANT) — forged rows the fold still accepts

Every row below was **accepted at both boundaries**: `append` returned `appended=True`, and the re-chained file loaded.

| # | Forged row | Rule it breaks |
|---|---|---|
| N1 | `MemoryRecall` of **Elena's** memory in an exploration turn (no addressee) | the repair report's "a non-conversation turn has no … minds rows" (refuted: only the 7 `CharacterState` kinds are refused) |
| N2 | `BeliefRevised` of Elena's belief inside a **David** turn | minds rows belong to the addressee |
| N3 / N4 | `KnowledgeAdded` for Elena inside a David turn / in an exploration turn | the same |
| N5 | `MemoryCorrected(field="any_field_at_all", corrected_value="Atlantis")` | fail closed (unresolvable `field`); `corrected_value: Any` |
| N6 | `MemoryCorrected(corrected_value={"a": [1, {"b": "c"}]})` | a structured value in an overlay that downstream code reads |
| N19 | `MemoryRecall(turn_id=999)` in turn 75 | the turn check reads only `turn`, never `turn_id` |
| N7 | **two** `DetectiveModelUpdate` rows in one turn, each adding one item, so two items are added | the repair report's "may add at most one item" (refuted) |
| N8 | `CoverStateDelta(slips_used=("nonsense",), contradictions_caught=("bogus",), refuse_streak=-5)` | fail closed (unresolvable ids); a negative counter |
| N9 | `CoverStateDelta(topics_probed={"where": -100})` | a negative counter |
| N10 | `IncidentalPinned(speaker="Elena", entity="Atlantis", layer_scope=("S_David", 7))` inside a David turn | speaker is not the addressee; unresolvable entity; foreign secret, layer out of range |
| N11 | `IncidentalPinned` in an exploration turn | the same |
| N12 | hypothesis with `Lied(actor="Ghost", statement="S99999")` and `Planted(evidence="E_nope")` | fail closed (unknown actor, statement and evidence) |
| N13 | David's statement claims `At(actor="Ghost", location="Atlantis")` | fail closed (unknown actor and place in a claim's proposition) |
| N14 | `Statement.layer_scope = ("S_David", 9)` on a 2-layer cover | fail closed (layer index out of range) |
| N16 | Elena's peel turn whose owed claims keep their **ids** but carry a different proposition | voicing is checked by claim id only |
| N25 | two claims with one id in one statement | ids must be unique |

**Consequences.** No accepted save crashed the engine: I continued play on each, asking every suspect with and without
presentations. But N13 is not inert. After the one forged `At(Ghost, Atlantis)` claim, **all 32 of 32** later genuine
David turns were rejected `JOINTLY_INFEASIBLE`. The save loads, and David can never speak again. The store accepted a
reference the engine cannot live with, which is the failure the fail-closed rule exists to prevent.

**Classification.** These are real violations of the house rule ("unresolvable references … resolve to refusal",
I-15), and three statements in the repair report claim more than the code does. Every row needs a re-chained local file
(§26.1: not cheat-proof) or a producer that does not exist: no runner emits any epistemic kind, `IncidentalPinned`, or
a `CoverStateDelta` field other than `topics_probed`; claims and their propositions come only from sealed beliefs and
covers. I rate it IMPORTANT, as the original review rated the same class. It does **not** block Phase 8, because no
Phase 8 producer emits these rows except `HypothesisChanged` (§9). The fixes are all structural, and none recomputes a
weight (I-22):

* bind epistemic and incidental rows to the addressee, inside a conversation turn;
* resolve nested references: claim and hypothesis proposition entities against `case.actors`, `locations` and
  `objects`; `Lied.statement` and `Planted.evidence` against held material; `layer_scope` index within the cover;
  `MemoryCorrected.field` against the memory's distortion; `slips_used` and `contradictions_caught`;
* allow at most one `DetectiveModelUpdate` per turn;
* check that the voiced claims are **equal** to the layer's authored claims, not just that the ids match;
* require unique claim ids within a statement;
* check `turn_id == turn` wherever a row carries `turn_id`.

**Documented class, re-confirmed (C-1, not a finding).** These rows are accepted at both boundaries:

* an unearned murderer peel: David's CONCESSION voicing layer 1 with nothing presented (cover moves to layer 1);
* a fabricated CONFESSION that mints `attack@David`;
* a CONFESSION by an innocent;
* `TrustChange` to 10000;
* `Accusation` inside a conversation turn;
* `CaseSolved(correct=True)` with no accusation (PN-10).

Detecting these needs the weight or strategy code, which I-22 forbids in the fold. §26.1 permits the attack, and C-1
records it. **This is an intended limitation, not a violation.**

## 5. PI-2 … PI-7: verified

| ID | Attack | Result |
|---|---|---|
| PI-2 | `player_confidence` 0.5 / 1.0 / 0.0 at both boundaries | accepted (on the grid) |
| | `player_confidence` 1.0001 / 0.12345 / 1.5 / −0.5 / 1.00005 | REFUSED "carries a float" |
| | NaN | REFUSED ("does not validate") |
| | ±inf | **raw `OverflowError`**, not `SaveRefusal`; rolled back, nothing written (N-5) |
| | `KnowledgeAdded.reliability` exactly equal to trust (5000 bp) | accepted |
| | `reliability` = trust + 1 bp | REFUSED (I-25) |
| | stored `NaN` / `Infinity` / `5000.0` / `1e4` (no re-chain) | REFUSED |
| | re-chained `new_composure_bp: 5000.0` | REFUSED (I-17) at load |
| | `MemoryCorrected` float (shipped forgery) | REFUSED at both boundaries |
| | CLI: `eidolon replay --verify` on a broken save | exit 1, JSON `{"ok": false, "error": …, "at_seq": 5}`, empty stderr |
| | CLI: `replay` on a healthy save | exit 0 |
| | CLI: `newsave` with a missing bundle | exit 1, no file created |
| | Latent (N-6): `Attitude.intensity` and `Motive.strength` are floats inside the closed `Proposition` schema, so a hypothesis or claim carrying one is refused | Today `speakable` never voices the 6 `Attitude` beliefs in the generated cases (checked: retrieval yields nothing and `speakable` is False), so no genuine turn is refused. This is fail-closed, not corruption, but C-2 lists only two float fields |
| PI-3 | v1 save under a v2 engine with an upcaster | read-only open gives the identical hash, bytes unchanged |
| | writable open of that save | REFUSED "opens read-only until migrated" |
| | no upcaster | REFUSED |
| | `schema_version` 2 or 3 under v1 | REFUSED "reads up to 1" |
| | `schema_version` 0 or −1 | REFUSED |
| | native current-version save: append, then reload | identical |
| | relabelling `schema_version` | REFUSED (shipped test; genesis binds the schema) |
| | truncating a v1 save under a v2 engine | works; writes no v2 row |
| PI-4 | A and B open at one head; A appends, then B appends | `StaleAppend` |
| | ABA: same `head_seq`, different `head_hash` (another writer re-chained the last turn) | `StaleAppend`; the file still loads |
| | 4 competing **processes** × 15 turns, retrying on stale | 60 appended, 45 `StaleAppend`, 0 lock errors, 0 duplicates; final file loads at 450 rows, with exactly 60 distinct writer action ids |
| PI-5 | first commit | `TurnRef(75, 391, 392)` |
| | retry with a stale `expected_seq`, one turn later | `appended=False`, the **same** `TurnRef`, `same_events=True`, `last_seq=392` |
| | same id, different events | the same `TurnRef`, `same_events=False` |
| | retry from a second `Save` instance (another tab) | the same `TurnRef`, `same_events=True` |
| | rows carrying that action id | 2 (one turn) |
| | `turn_for` | correct in both instances |
| PI-6 | engine drift, one derivation at a time: knowledge (one entry dropped), beliefs (one fewer), memories (`strength_0` + 1), personality (`guile` + 0.01), initial character state (trust 5000 → 5001) | **all REFUSED** at stage `initial` |
| | personality changed by 1e-7, below the digest's millionths | loads. This is C-11 by design: the fold never reads personality, and later turns read it only through bp-rounded decision-time formulas |
| PI-7 | resealed package declaring murderer Elena, place Hall, or interval (58, 60) | REFUSED "declared …" |
| | proof `survivors` [Elena] or [David, Elena]; `unique: false`; `window` [58, 60]; `murder_loc` Hall | REFUSED by `verify_proof` |
| | a forged-declaration bundle swapped into an existing save | REFUSED at stage `bundle` |
| | **declared `victim`, `weapon` or `murder_event` changed** | **accepted**: these fields are not compared (N-7; nothing reads them today) |

## 6. Transactionality, replay, export, traces, canonical form: verified

| Check | Result |
|---|---|
| Folded state equals live state after every turn | yes: the sweep (664 turns), the account path, and the shipped long sessions up to 2000 turns |
| Save → load → replay → append | 60 turns straight through vs 30, close, reopen, 30, with four speakers and a peel: **rows identical**, state hash and chain head identical |
| A refused append leaves the database and the in-memory state unchanged | yes, for all four kinds tried: a fold refusal, a skipped turn, an empty list, and a non-event object (byte compare plus hash, seq and head). The next genuine append still works |
| A read-only open changes no byte | yes, including the v2-engine upcast open and the hot-journal refusal (shipped X39) |
| Export | from a writable save: atomic, and the copy loads to the same hash. From a read-only save: `ProgrammingError` and a `.tmp` left behind. Onto its own path: `PermissionError`, source intact. Both are PN-6, still open as ledgered (C-12) |
| A trace failure after commit | the turn commits and reloads (trace path made a directory; an unserialisable trace value) |
| Tampering with the proof↔case association | a bundle edit is REFUSED at stage `bundle`; a mismatch between meta and case is REFUSED |
| Canonical payloads | reordered keys, a duplicate key, a `\u` escape, or an extra field in stored text (no re-chain): REFUSED at `chain`. A re-chained unknown kind or extra field: REFUSED at `fold` |
| 2000-turn session | `3 passed` (run 3) |

## 7. Mutation harness: reproduced, then audited

**Run 4 reproduced the author's result**: baseline green, 86 killed, 0 survived or malformed, 6 marked equivalent. The
real source files were unchanged afterwards (the harness asserts this, and my manifest agrees).

| Requirement | Assessment |
|---|---|
| Green-baseline gate | **yes**. The whole persistence file runs unmutated beside the mutants; if it is red, the harness exits 2 and prints "nothing above is evidence" |
| Each anchor matches exactly once | **yes** (`count(old) != 1` → `BAD`) |
| The selection collects at least one test unmutated | **yes** |
| At least one intended test fails for the intended guard | **yes**: pytest must exit 1, and a failing test id must contain the guard's name. But see the next paragraph |
| Killed, equivalent, survived and malformed kept apart | **yes** in the per-line verdicts; the summary line merges survived and malformed. Infrastructure errors (a `TimeoutExpired`, a worker exception) crash the harness with a traceback instead of being reported as a category (minor) |
| The real source tree is left unchanged | **yes** (private copies; asserted; manifest identical) |

**How the PI-1 mutants are killed.** For 30 of them, the guard's test runs a forged turn and matches the refusal
message. I re-ran each of those mutants against its forgery to see what happens to the input itself:

* **22 are real kills**: under the mutant, the forged turn is accepted.
* **8 are killed only through a different message or a raw exception.** The forgery is still refused by another rule
  under the mutant, so the test fails on its message regex or on the exception type:

| Mutant | What happens to the shipped forgery under the mutant |
|---|---|
| `peel-bound-unchecked` | refused by the voicing rule / a raw `IndexError` |
| `retraction-of-another-speaker` | refused by "peeled no layer" |
| `retraction-by-an-uncommitted-statement` | refused by "not a standing statement" |
| `claim-bound-to-another-statement` | refused by the grounding rule |
| `unknown-speaker-accepted` | refused by "carries no statement" |
| `conversation-without-a-statement` | raw `AttributeError` |
| `two-statements-in-a-turn` | refused by `apply_decision`'s id clash |
| `peel-of-another-secret` | refused by the voicing rule |

For four of these I built an input that isolates the guard. In each case the **real code refuses it and the mutant
accepts it**, so the guard is necessary and correct; the shipped forgery just does not exercise it alone:

* an Elena peel turn retracting a David statement;
* a claim bound to `S00001` with David's own grounding;
* a "Ghost" turn carrying its own statement and hearing row;
* **an Elena turn that moves David's cover to layer 1**.

`two-statements-in-a-turn` is equivalent in effect: statement ids are forced to `S{turn}`, so a second statement always
clashes in `apply_decision`. Its kill is message-only. This is NON-BLOCKING test quality (N-8). The fix is to make each
forgery trip only its own guard, for example by using a peel turn for the retraction-speaker case.

**The six claimed equivalents**, each mutated in a private copy and probed with the input its guard exists for:

| Mutant | Claim | Probe under the mutant | Verdict |
|---|---|---|---|
| X23 no minds rows outside a conversation | a missing `chars[who]` / the statement rule refuses them | all 7 `CharacterState` kinds still REFUSED: "turn does not fold: None", or the owner check for `PressureChange` | **accepted**. The refusals come from the `KeyError` backstop; the statement rule cited applies only to conversation turns |
| X26 one `TurnCommitted` per turn | no fold for a second bracket | REFUSED "event kind 'TurnCommitted' has no fold" | **accepted** |
| X31 payload kind = column kind | pydantic `Literal` | REFUSED, but two of three probes surface as a raw `ValidationError`, which becomes "unreadable save" with stage `None` | **accepted for acceptance.** The diagnosis gets worse: recovery would raise instead of returning a plan |
| X45 stored `prev_hash` column check | the column is redundant | **LOADS** a file whose `prev_hash` column was edited; the real code refuses it | **rejected as stated: not equivalent.** Harmless, because the column is not authoritative and each hash covers the running prev; one test would kill it |
| X46 genesis binds the seed | the seed moves personalities, so the digest refuses first | seed 7→8: REFUSED (`initial`); with the digest recomputed for seed 8: REFUSED (`genesis`). **Under an engine whose personality ignores the seed** (C-3's planned flavor slot) the mutant **LOADS with `state.seed = 8`**; the real code refuses | **rejected as "by construction"**: it holds only while `default_personality` reads the seed. No test pins the explicit seed binding |
| float range 0 ≤ x ≤ 1 | implied by the grid check | 1.5 / −0.5 / 1.00005: REFUSED; NaN: REFUSED; ±inf: raw `OverflowError` | **accepted** for finite values; exception contract noted (N-5) |

## 8. Findings

### BLOCKING
None.

### IMPORTANT
* **R-1:** the validating fold still accepts structurally impossible rows and nested unresolvable references (§4).
  Three repair-report statements are inaccurate:
  * "a non-conversation turn has no … minds rows";
  * "`DetectiveModelUpdate` may add at most one item";
  * "all references resolve" (true only for event-level fields).

  One accepted reference makes a character permanently mute. This is a contract violation (fail-closed rule, I-15),
  reachable only by re-chaining or a future producer. It does not block Phase 8 (§9).

### NON-BLOCKING
* **N-1** (recovery): when the first row of a turn is deleted or both its `kind` and payload are destroyed, the cut also
  drops the **preceding complete turn**. The behaviour is conservative and is shown in the dry run, but C-8 describes
  only the opposite direction.
* **N-2** (recovery diagnosis): tail deletion, with or without a damaged genesis, is planned as `reset_meta` with
  "rows are intact; … removes 0 rows". In fact the head recorded 390 rows and 384 remain. The plan should say how many
  recorded rows are missing.
* **N-3** (dry run is not read-only): with a hot journal, `plan_truncation` opens `mode=rw` and SQLite rolls the
  journal back. The file changes, the journal disappears, and the plan says "none". No committed data is lost, but the
  docstring ("Writes nothing") is wrong, and the crash evidence that X39 deliberately preserves is erased. Fix: open the
  dry run `mode=ro`, or detect the journal and report it.
* **N-4** (diagnosis): a damaged `meta.initial_digest` is reported as engine drift. The intact genesis could tell the
  two apart: if the genesis recomputed from the stored digest is wrong but the one from the derived digest is right,
  only the record is damaged. Nothing is deleted either way.
* **N-5** (exception contract, PN-8 residual):
  * ±inf in `player_confidence` or `reliability` raises a raw `OverflowError` from `append`;
  * a chain-valid row that fails pydantic validation surfaces as "unreadable save" with `stage=None, seq=None`, and
    `plan_truncation` raises instead of returning a `refuse` plan;
  * the head-hash mismatch messages name only the seq: "head records seq 390", and "head is seq 391, caller expected
    391" for ABA.

  All of these fail closed.
* **N-6** (I-17 debt understated): `Attitude.intensity` and `Motive.strength` are floats in the `Proposition` schema,
  so claims, hypotheses and `KnowledgeAdded` entries carrying them are refused. This is latent today and a Phase 8
  dependency (§9). C-2 should list them.
* **N-7** (PI-7 scope): the declared `victim`, `weapon`, `method`, `murder_event` and `approach` are not confirmed. All
  are derivable from the CaseLog. Nothing reads them today; Phase 8's case report must read them from the CaseLog or
  confirm them first.
* **N-8** (mutation harness):
  * 8 of 30 PI-1 kills come from a message or exception change, and their shipped forgeries do not isolate the guard
    (4 guards proven necessary by isolated inputs);
  * `two-statements-in-a-turn` is effectively equivalent but counted as killed;
  * the X45 and X46 equivalence claims are not supported as stated;
  * the summary merges survived and malformed;
  * an infrastructure error crashes the harness instead of being reported.
* The review's PN-1 and PN-3…PN-6, PN-8 and PN-10 remain open as ledgered (C-12). I re-observed PN-6 (export from a
  read-only save) and PN-10 (`CaseSolved.correct` unchecked).

### UNMEASURED
* **U-1 (X1)** cross-machine and cross-OS replay. Partial evidence: under Python 3.14.6 with pydantic 2.13.4 on the same
  machine, four saves built under 3.12 load with **identical** state hashes and chain heads, and a 60-turn,
  four-speaker session rebuilt from scratch produces **identical rows**, chain head, state hash and initial digest.
  WSL Ubuntu is present (Python 3.14.4) but has no pydantic; installing it needs a download, which I did not do.
* **U-2** sessions rendered by a live model, then persisted and replayed (no key or network).
* **U-3** power-loss durability of the export rename.
* **U-4** the Phase 6 mutation sweep and generation determinism. Not re-run: they do not touch persistence.

## 9. Contract violations vs intended limitations, and Phase 8 entry assessment

| Item | Contract | Classification |
|---|---|---|
| R-1 nested unresolvable references; minds rows unbound to the addressee; two `DetectiveModelUpdate` rows | I-15 / `CLAUDE.md` fail-closed rule; the repair report's own claims | **Violation (re-chain or future-producer only)**: IMPORTANT, not a Phase 8 gate |
| N-3 dry run writes on a hot journal | the store's docstring; the I-23 spirit (X39) | **Violation of a stated property**, benign effect: NON-BLOCKING |
| C-1 unearned peel, fabricated confession, uncomputed values | §26.1 "not cheat-proof"; I-22 forbids recomputing weights in the fold | **Intended limitation** |
| PN-1, PN-3…PN-6, PN-8, PN-10 | §26.1 / §26.2 | **Ledgered limitations** (C-12) |

Phase 8 entry, limitation by limitation, under the existing contract (§30: "Dependencies: Phases 4–7"; the original
review's §9 conditions):

| Limitation | Blocks Phase 8? | Why |
|---|---|---|
| Cross-machine replay unmeasured | **No** | It is a Phase 7 *exit* criterion still to be measured, not a dependency of local browser play. The design is float-free in the hash (millionths in the digest), saves are byte-identical across hash seeds, and the cross-interpreter proxy is green. Measure it on a second OS before external playtests (Phase 9) |
| No persisted `PlayerAction` rows | **No** | Replay does not need them (I-22). The kind is registered and foldable. Phase 8's ingress is the producer, so write it there |
| No integrated `TurnTrace` model or writer | **No** | §27.1 is observability (Phase 9). Phase 7 delivered the best-effort post-commit write mechanism, which works (§6) |
| Some kinds have no producer | **No, with one entry task** | Phase 8 produces `Accusation` (fold-checked), `HypothesisChanged` and `CaseSolved`. When those producers are written, add their fold rules in the same change: `Lied`/`Planted`/entity resolution for hypothesis propositions, a decision on `Motive`/`Attitude` floats (N-6), and `CaseSolved.correct` checked against the PI-7-verified survivor plus no turns after solve (PN-10). The epistemic, incidental, trust, emotion and suspicion kinds are not Phase 8 deliverables; R-1's fixes for them belong with their producers |
| Older-schema saves are read-only | **No** | No second schema exists. The interim refusal is exactly what the original review asked for (C-10) |
| A forger can re-chain a structurally valid, unjustified event | **No** | §26.1 permits it for local saves; hosted deployments keep saves server-side, and the client submits actions, not events |

The original review's §9 conditions:

| Condition | Status |
|---|---|
| Fixes 1, 3, 4, 5 | landed with tests and mutants |
| Fix 2 | landed for every item it named at event level; nested references and two of its shape clauses are R-1 |
| Fix 6 | landed (writable opens of older schemas refused; schema bound into the genesis) |
| Fix 7 | landed |
| Fix 8 | landed (initial digest bound into the genesis, refused on drift) |
| Persistence suite and mutants green | **reproduced**. No survivor; two equivalence justifications are wrong as stated but both mutants are harmless (§7) |

**Recommended before or alongside early Phase 8 work (not gates):**

* add R-1's structural checks, or at least ledger R-1, and correct the three repair-report statements plus C-2, C-8 and
  the `plan_truncation` docstring;
* fix N-3 (one-line `mode=ro` dry run);
* add the X45 and X46 tests and isolate the 8 message-only forgeries;
* measure X1 on a second OS.

## 10. Reproduction (no production files modified)

Run from the repository root in a fresh scratch directory for the `.db` files, with `PYTHONPATH` pointing at the tree.
Observed output: `R-1a True`, `R-1c True ['E_alibi_room', 'E_gate_Gazebo']`, `R-1b True`, `reload 39`, then
`N-3 journal: True | plan: none | file unchanged: False | journal left: False`.

```python
import os, subprocess, sys
from eidolon.store import Save, plan_truncation
from eidolon.decision.claims import Claim
from eidolon.decision.events import ClaimMade, IncidentalPinned, TurnCommitted
from eidolon.decision.query import Query
from eidolon.decision.turn import run_ask_turn, run_goto_turn, run_search_turn
from eidolon.minds.epistemic import RecallRecord
from eidolon.minds.events import DetectiveModelUpdate, MemoryRecall
from eidolon.world.propositions import At
BUNDLE = os.environ.get("BUNDLE", "cases/generated/study_party_s4.json")

s = Save.create("rr.db", BUNDLE, seed=7)
s.append(run_goto_turn(s.state, "Study").events, 0, "go")
for i, ev in enumerate(s.state.evidence.all()):
    s.append(run_search_turn(s.state, ev.discovery.at, ev.discovery.action).events, s.last_seq, f"s{i}")
n = lambda: s.state.turn_counter + 1
def ask(who="David", hint="where"):
    res = run_ask_turn(s.state, who, Query(kind="did_you", predicate_hint=hint, raw=hint))
    assert not res.rejected, res.violations
    return list(res.events)

# R-1a: a minds row for Elena's memory in an exploration turn (no addressee)
m = s.state.memories["Elena"][0]
print("R-1a", s.append([TurnCommitted(turn=n()), MemoryRecall(memory_id=m.id, turn_id=n(), new_strength_bp=10000,
      record=RecallRecord(turn_id=n(), cue_match_bp=3000, outcome="strong"))], s.last_seq, "r1a").appended)
# R-1c: two DetectiveModelUpdate rows add two items in one turn ("at most one item")
dm = s.state.characters["David"].detective_model
a, b = sorted(s.state.discovery.known_evidence - dm.known_evidence)[:2]
print("R-1c", s.append(ask(hint="study") + [DetectiveModelUpdate(new_model=dm.model_copy(update={"known_evidence": dm.known_evidence | {a}})),
                                 DetectiveModelUpdate(new_model=dm.model_copy(update={"known_evidence": dm.known_evidence | {a, b}}))],
                       s.last_seq, "r1c").appended, sorted(s.state.characters["David"].detective_model.known_evidence))
# R-1b: David's statement claims At(Ghost, Atlantis); an incidental pinned by Elena inside David's turn, scoped to David's secret
sid = f"S{n():05d}"
ghost = Claim(id="c:g", statement=sid, proposition=At(actor="Ghost", location="Atlantis", interval=(0, 1)),
              sincerity="truthful", source="plan")
evs = [ClaimMade(statement=e.statement.model_copy(update={"claims": (ghost,), "accounts": ()})) if e.kind == "ClaimMade" else e
       for e in ask() if e.kind != "AccountHeard"]
evs.append(IncidentalPinned(speaker="Elena", entity="Atlantis", attr="x", value="y", layer_scope=("S_David", 7)))
print("R-1b", s.append(evs, s.last_seq, "r1b").appended)     # afterwards every genuine David ask is JOINTLY_INFEASIBLE
s.close()
print("reload", Save.open("rr.db").last_seq)

# N-3: the "dry run" rolls back a hot journal (a crash mid-append) — it writes the file
code = ("import os, sqlite3, sys\nc = sqlite3.connect(sys.argv[1], isolation_level=None)\nc.execute('PRAGMA cache_size=10')\n"
        "c.execute('BEGIN')\nfor i in range(3000): c.execute('INSERT INTO session_events VALUES (?,?,?,?,?,?,?)', "
        "(10000+i, 1, 'x', 'a', '{}' + ' ' * 80, 'p', 'h'))\nos._exit(0)\n")
subprocess.run([sys.executable, "-c", code, "rr.db"], check=True)
before = open("rr.db", "rb").read()
print("N-3 journal:", os.path.exists("rr.db-journal"), "| plan:", plan_truncation("rr.db").action,
      "| file unchanged:", open("rr.db", "rb").read() == before, "| journal left:", os.path.exists("rr.db-journal"))
```

To reproduce a guard isolation from §7, take the mutant from `tests/persistence_mutation_check.py`, for example
`peel-of-another-secret`, and apply it to a copy of the tree. Then append this turn: `TurnCommitted(character="Elena")`,
a CONCESSION by Elena whose claims are `claims_voiced_on_peel(S_David.layers[1])`,
`LayerPeel(character="David", secret_id="S_David", 0, 1)`, and its `StatementHeard`. The real code refuses it ("not the
addressee's own secret"); the mutant accepts it and moves David's cover to layer 1.

## Severity index

| ID | Severity | One line |
|---|---|---|
| PB-1 | **repaired** | recovery diagnoses with the loader, never cuts healthy or verified rows, has a dry run, and proves its repair in-transaction |
| PI-1 | **repaired (core)** | one fold at both boundaries, `check_state` every turn, the shipped forgeries refused, no false refusals in 664 + 4×RB-1 turns |
| PI-2 | **repaired** | floats refused off the two bp-grid fields; I-25 enforced; NaN refused; CLI clean |
| PI-3 | **repaired** | older schema read-only; schema bound into the genesis; native append and reload |
| PI-4 | **repaired** | head hash compared; ABA and 4-process race clean |
| PI-5 | **repaired** | a duplicate returns the original `TurnRef` with `same_events`; `turn_for` |
| PI-6 | **repaired** | every derived store bound by the initial digest; drift refused |
| PI-7 | **repaired** | declared murderer, place and moment must equal the verified proof |
| R-1 | IMPORTANT | the fold still accepts impossible minds, incidental and detective-model rows and nested unresolvable references; three report claims overstated |
| N-1 | NON-BLOCKING | an unrecognisable bracket damage also drops the previous complete turn |
| N-2 | NON-BLOCKING | tail deletion described as "rows intact, 0 removed" |
| N-3 | NON-BLOCKING | `plan_truncation` rolls back a hot journal ("Writes nothing" is false) |
| N-4 | NON-BLOCKING | `initial_digest` record damage misdiagnosed as engine drift |
| N-5 | NON-BLOCKING | raw `OverflowError` / `ValidationError` paths; head messages name only the seq |
| N-6 | NON-BLOCKING | float fields inside `Proposition` (`Attitude`, `Motive`) are unrepresentable; C-2 understated |
| N-7 | NON-BLOCKING | declared victim, weapon, method, event and approach unconfirmed |
| N-8 | NON-BLOCKING | mutation harness: 8 message-only kills; X45 and X46 equivalence claims wrong as stated |
| U-1 | UNMEASURED | cross-machine/OS replay (cross-interpreter proxy green) |
| U-2…U-4 | UNMEASURED | live model; export power-loss; the Phase 6 sweep |
