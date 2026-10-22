# EIDOLON — Phase 9 repair report (H9-B1, H9-I1, H9-I2)

Date: 2026-10-21. Author's record of the repair of the three findings that `docs/EIDOLON-PHASE-9-HOSTILE-REVIEW.md` §10 requires fixed.
**Disclosure:** the same session wrote the hostile review and this repair. That review was independent of the Phase 9 implementation;
this repair is not independent of the review, and nothing here has been re-reviewed. Nothing was committed (no VCS).

**Verdict: H9-B1, H9-I1 AND H9-I2 REPAIRED — READY FOR INDEPENDENT RE-REVIEW.** Phase 9 is **not** accepted: its explicit exit
criteria (two external playtesters on a generated case; the live-model nightly) are still unmet, H9-I3 (= F-3, confession unreachable)
and H9-U1 (the latency floor against a live model) are still open, and Phase 8 is still awaiting its own independent re-review.
Phase 10 was not started.

---

## 1. Tree

| | manifest (sha256 over the sorted `sha256 path` lines of every `*.py`) | files |
|---|---|---|
| before (the review's snapshot) | `9f9969c8f3af85dafdec354a12af15c81e56d1a6a07d82ba39f28e80e499f8d6` | 212 |
| after | `7648d50957eb79fb8af17290aeafbaddeba0e44f641de84945a19fc545fb8c58` | 213 |

Changed: `eidolon/decision/strategy.py`, `eidolon/decision/turn.py` (H9-B1); `eidolon/debug/nightly.py` (H9-I1, H9-I2);
`eidolon/debug/promptdoc.py` (§5). Tests: **new** `tests/test_phase9_repairs.py`; `tests/test_phase9_suites.py` (suite 2, strengthened —
§2.4); `tests/test_phase9_docs.py` (constant scan strengthened — §5); `tests/test_phase9_corpus.py` (one sequence-attack bound made
act-aware — §2.5); `tests/phase9_mutation_check.py` (2 anchors re-pointed, 16 mutants
added). Docs: `docs/EIDOLON-PROMPTS-AND-CONSTANTS.md` regenerated; this report; `CLAUDE.md`, `docs/EIDOLON-KNOWN-DEBT.md` and a closing
section of the review updated. No fixture, case, seal or proof changed.

---

## 2. H9-B1 — repetition no longer tells a lie from a truth

### 2.1 Root cause (from the review)

`strategy._repeat_prior` offered `REPEAT_PRIOR` only when this turn's memory **retrieval** had a claim — a liar's retrieval is empty — and
nothing in the scorer let `REPEAT_PRIOR` or `REFUSE` outscore a content act (the repetition term penalised only `EVASION`), so LIE (2.44)
beat `REPEAT_PRIOR` (2.40) and `REFUSE` (2.37). §15.4 specifies the opposite: "the **standing** (non-retracted) claim is re-supplied verbatim"
as "a high-utility candidate" from `repeat_count ≥ 2`, and `REFUSE`/`ANGER` from `≥ 5`.

### 2.2 The change

* `turn.run_ask_turn` finds the speaker's latest **standing** statement with this question's `query_hash` and claims, and passes its
  claims as `StrategyInput.prior_claims` (a peel's retraction removes a statement from the standing set, so a retracted answer is never
  re-supplied).
* `strategy._repeat_prior` builds `REPEAT_PRIOR` from `prior_claims` (whatever act produced them), never from retrieval.
* `strategy._repetition_penalty` gives `REPEAT_PRIOR` (from the third identical question) and `REFUSE` (from the sixth) a **preference**:
  `REPEAT_PRIOR_PREFERENCE = 1.4`, `REFUSE_PREFERENCE = 2.0`, weighted by `W_REPEAT = 0.5`. The margins are structural, not tuned to a
  case: every other act's utility is at most 3.00 (each weighted term at its maximum); `REPEAT_PRIOR` scores 2.40 + 0.70 = 3.10; `REFUSE` at
  least 2.25 + 1.00 = 3.25. The forced acts (`CONFESSION`, `CONCESSION`, `STONEWALL`, `SLIP`) are selected before utility, so a peel is
  still always voiced.
* **Only when nothing is shown** (`presented_ref is None`). `normalize` keys a question on its shape, not on the exhibit, so a run of
  challenges with *different* items shares one hash; an item put in front of the speaker is a new question and its authored response
  (`DENY_EVIDENCE`/`REINTERPRET`) must not be swallowed by "as I said". This is a design decision of the repair, recorded here and tested.

### 2.3 Before → after (the review's own reproduction, Appendix A.1, four generated cases, every V-7 question × 7 asks)

| first answer's act | n | before: answers 6–7 include REFUSE | after |
|---|---|---|---|
| LIE | 250 | **0** | **250** |
| TRUTH | 32 | 2 | 32 |
| VAGUE | 281 | 104 | 281 |
| DONT_RECALL | 245 | 181 | 245 |
| DONT_KNOW | 109 | 49 | 109 |

Per question, for every claim-bearing first answer (LIE, TRUTH, VAGUE — 563 questions): answers 3–5 are `REPEAT_PRIOR`, 6–7 `REFUSE`, and
every claim made for the question is the same claim. The production-path picture (`game.ask` on `study_party_s4`) is the same.

**Residuals, measured, not fixed:**

* **R9-1 (NON-BLOCKING).** A weak memory's `VAGUE` ties `DONT_KNOW` on utility (2.40 each) and the tie-break hashes `turn_id`, so the
  **second** ask can flip between them: 3 of 281 VAGUE and 14 of 109 DONT_KNOW first answers, 0 of 250 LIE, 0 of 32 TRUTH. Escalation from
  the third ask is unaffected and every claim made for the question is still the same claim. A flip says "not a lie" for ~4 % of weak-memory
  answers. Removing it means keying the tie-break on the question rather than the turn — a change to every tie in every session, which
  would need the Phase 6 bots and the sealed reports re-checked; left for the re-review to judge.
* **R9-2 (NON-BLOCKING, pre-existing).** §15.4 caps `REFUSE` at 2 consecutive turns; `CharacterState.refuse_streak` exists and folds, but
  no producer ever sets it, so a character refuses for ever from the sixth identical question. Act-independent (it applies to LIE as to
  TRUTH), so not a sincerity tell; unchanged by this repair.

### 2.4 Tests and mutants

`tests/test_phase9_repairs.py`:

* `test_H9_B1_a_lie_and_a_truth_escalate_identically_when_the_same_question_is_repeated` — Nora's TRUTH and David's LIE, 8 asks each:
  `[act, act, REPEAT_PRIOR ×3, REFUSE ×3]`, claims identical.
* `test_H9_B1_repeat_prior_never_resupplies_a_claim_a_peel_retracted` — after the knife print peels David's layer.
* `test_H9_B1_a_shown_item_is_a_new_question_so_repetition_never_hides_an_evidence_response`.
* `test_H9_B1_the_repetition_preferences_clear_the_ceiling_of_every_other_act` — the structural margins, computed from the weights.
* `test_H9_B1_a_repeat_bot_with_no_evidence_learns_nothing_about_sincerity[study_party_s4|manor_wing_s4]` — the review's repeat bot over
  every other V-7 question: every claim-bearing first answer, whatever its act, escalates identically (≥ 10 LIE and ≥ 10 non-LIE seen).

`tests/test_phase9_suites.py::test_suite_2…` is **strengthened**, not weakened: it now asserts §28.4 #2 — `[act, act, REPEAT_PRIOR ×3,
REFUSE …]`, claims identical — for the truthful witness **and** the liar. The previous version asserted that "a liar repeats his lie
unchanged" fifty times, which is the defect.

Mutants (`tests/phase9_mutation_check.py`): `H9-B1-repeat-prior-from-retrieval`, `-repeat-prior-preference-dropped`,
`-refuse-preference-dropped`, `-repeat-prior-preference-under-the-ceiling`, `-refuse-does-not-beat-repeat-prior`,
`-repetition-preferred-even-when-an-item-is-shown`, `-repeat-prior-resupplies-a-retracted-answer`, `-prior-answer-not-passed`; the existing
`repeat-prior-too-early`/`-too-late` re-pointed at the new line (same mutation).

### 2.5 An existing assertion the repair had to change, and why it is not weaker

The first harness run on the repaired tree failed its baseline on `test_a_sequence_attack_leaves_nothing_behind[burst]`. The `burst`
sequence asks the same question eight times; its last turn's envelope was asserted to be within ±12 tokens of the same line asked once
(`abs(final - alone) <= 12`) — "nothing accumulated in what the model sees". After the repair the eighth identical question is the §15.4
escalation (`REFUSE`, no claims), so its envelope is *smaller* than the line alone, and the two-sided bound failed. The lower half of that
bound held before only because the liar never escalated — the defect. The test now asserts the property it names: the final envelope is
**never larger** than the line alone (+12 tokens, unchanged), and it may be smaller **only** when the final turn is `REFUSE` at repetition
≥ 5 (asserted); for every other sequence the old two-sided check still applies in effect. All 16 sequences pass.

---

## 3. H9-I1 — the nightly no longer counts a failed parse as a classification

`nightly.classify_corpus`: a `ProviderRefusal` (the SDK reports it as `stop_reason="refusal"`) or a malformed reply is the model's answer
and not the expected one — a **miss**; a `ProviderError`/`ProviderTimeout`/budget exhaustion is no answer at all — the line is
**unmeasured**, and N-3 is UNMEASURED if any line is (its note counts them). N-4 is UNMEASURED if the budget ran out during the corpus
sample. Before → after (the review's Appendix A.2 reproductions, SDK-shaped stand-in):

| case | before | after |
|---|---|---|
| parser refuses 215 of 225 lines (SDK-faithful refusal) | N-3 PASS 10000, exit 0 | **N-3 FAIL**, exit 1 |
| parser's transport fails on 215 lines | N-3 PASS 10000, exit 0 | **N-3 UNMEASURED** ("lines with no answer … 215") |
| budget runs out after 195 of 225 parse calls | N-3 PASS 10000 | **UNMEASURED** |
| budget runs out after 100 of 225 | N-3 FAIL 9555 | **UNMEASURED** |
| budget runs out during the corpus-as-turns sample | N-4 judged on what was left | **N-4 UNMEASURED** |

Tests: `test_H9_I1_a_parser_that_refuses_hostile_lines_has_not_classified_them`, `…_a_provider_that_fails_during_the_parse_pass…`,
`…_a_budget_that_runs_out_during_the_parse_pass…[100|195]`, `…_during_the_corpus_sample_leaves_N4_unmeasured`. Mutants:
`H9-I1-parse-failure-counts-as-clarify` (the old code), `-transport-failure-is-a-miss`, `-refusal-is-unmeasured`,
`-unanswered-lines-judged`, `-cut-corpus-sample-judged`.

## 4. H9-I2 — the nightly audit runs on the model it names

`nightly.audit_transport_for` re-points a provider at `AUDIT_MODEL` (the same client); `run` gives the audit its own budget (what the
session left) and reads the model names for N-5's note **off the audit's call log** — never the constant. A stand-in that is not a provider
is used as it is and named as it is. Before → after (live stand-in): every call `claude-opus-5`, note "stronger verifier claude-fable-5-1
used" → session `generate`/`parse`/`verify` on `claude-opus-5`, audit `verify` on `claude-fable-5-1`, note "verifier claude-fable-5-1"; the
dry run's note names the rehearsal stub. `provider_calls` and `budget_exhausted` now include the audit's calls. Tests:
`test_H9_I2_the_nightly_audit_runs_on_the_stronger_model_it_names`, `…_a_run_without_a_stronger_verifier_does_not_say_it_had_one`.
Mutants: `H9-I2-audit-on-the-generation-model`, `-note-names-the-constant`.

## 5. Found while repairing: the constants document skipped tuple-assigned constants

`promptdoc._constants` and `test_every_constant_defined_in_a_documented_module_is_documented` both read only single-name assignments, so
`A, B = 1, 2` was invisible to both: **15 constants were missing** from `docs/EIDOLON-PROMPTS-AND-CONSTANTS.md`, including all seven utility
weights (`W_SAFETY` … `W_REPEAT`, the section was titled "the utility weights" and listed none), the render wire limits and the memory
salience weights. Both now unpack tuple targets; notes added (module-qualified where two modules share a name, e.g. `W_EMOTION`); the
document regenerated. Mutant `promptdoc-skips-tuple-constants` — the first harness run reported it SURVIVED: it was aimed at the
constants scan, which reads the checked-in document (already regenerated); the test that catches a `promptdoc` that renders less is
`test_the_checked_in_document_is_exactly_what_the_code_renders`, and the mutant now names it.

## 6. Failing first

`tests/test_phase9_repairs.py` was written and run before any source change: **10 failed, 1 passed** (the retraction guard, which the old
code also satisfies — it guards the new `prior` lookup and is backed by `H9-B1-repeat-prior-resupplies-a-retracted-answer`). The two
tests added afterwards (`…ceiling…`, `…corpus_sample…`) have their failing-first evidence in the mutants that remove what they guard.
The strengthened suite 2 fails on the old engine (the liar arm); the strengthened docs scan fails on the old `promptdoc` (15 missing).

## 7. Runs on the repaired tree (each in a byte-verified scratch copy)

Two trees: `6e6b0f0c…` (all source changes; before §2.5 and the mutant fix of §5) and the final `7648d509…`, which differs from it only in
`tests/test_phase9_corpus.py` and `tests/phase9_mutation_check.py` — so every run that does not execute those two files is valid for the
final tree.

| run | tree | result |
|---|---|---|
| `python -m pytest -q -p no:cacheprovider` | final | **3817 passed, 1 skipped, 1 xfailed, exit 0** (1 h 19 min). 3819 collected = 3806 + the 13 tests of `test_phase9_repairs.py`; the skip and the xfail are the same two as before (the real-provider cassette replay: UNMEASURED; the strict H8-X2 witness) |
| `python -m tests.phase9_mutation_check -j 5` | final | **baseline green; 119 killed, 0 survived, 0 malformed, 0 infrastructure errors (119 of 119)**, exit 0 |
| the same, first attempt | `6e6b0f0c…` | `BASELINE IS NOT GREEN` (`…sequence_attack…[burst]`, §2.5) → exit 2, nothing counted; `promptdoc-skips-tuple-constants` SURVIVED (§5). Both fixed, then the run above |
| `python -m tests.decision.mutation_check` (Phase 4 set; `strategy.py`, `turn.py` changed) | `6e6b0f0c…` | **PASS: 57 killed, 2 justified equivalent (M2, M4, unchanged)**, exit 0 |
| `python -m tests.persistence_mutation_check -j 4` (anchors in `turn.py`) | `6e6b0f0c…` | **baseline green; 197 killed, 0 survived, 8 justified equivalent**, exit 0 |
| `MUT_ONLY='^(RB1-c\|RB1-h\|RB2-b\|RB2-c\|RB2-g\|RB2-h\|RB2-i) ' python -m tests.solve.mutation_check` (the 7 Phase 6 mutants anchored in `turn.py`/`strategy.py`) | `6e6b0f0c…` | **baseline green (`tests/solve` + `tests/gen`: 349 passed, 1 xfailed); 7 killed, 0 survived**, PASS, exit 0 |
| `python -m eidolon.cli validate cases/generated/<case>.json` × 4 (re-runs every stage, the V-7 bots included, through the changed strategy) | `6e6b0f0c…` | **all four `ok`**, exit 0 |
| `python -m eidolon.debug promptdoc`, then `tests/test_phase9_docs.py` | final | regenerated (+15 constants); 28 passed |
| the review's reproductions (A.1, A.2) and `game.ask` | `6e6b0f0c…` | the "after" columns of §2.3, §3, §4 |

Not re-run: the Phase 5 harness (`tests.decision.mutation_check phase5`; three of its anchors are in `turn.py` and all 76 edits still match
exactly once, checked statically) and the rest of the Phase 6 harness (no file in its set changed except the two above); the
`EIDOLON_LONG=1` scales of T-25 and the persistence long sessions (the default scales are in the whole suite).

## 8. What stays open

* From the review, unchanged: **H9-I3** (= F-3, confession unreachable — must precede the playtests), **H9-U1** (latency floor vs a live
  p99 — precondition for Phase 10's first deliverable), **N1–N10**, the live-model criteria (F-1) and the two external playtesters (F-2) —
  the last two are explicit Phase 9 exit criteria.
* New: R9-1, R9-2 (§2.3) — KNOWN-DEBT F-14 and F-15.
* F-5 (KNOWN-DEBT §F) is **resolved** by this repair.

**H9-B1, H9-I1 AND H9-I2 REPAIRED — READY FOR INDEPENDENT RE-REVIEW**
