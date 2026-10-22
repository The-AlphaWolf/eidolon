# EIDOLON — Phase 9 re-review repair report (RR-B1, RR-I1)

Date: 2026-10-22. Author's record of the repair of the two findings `docs/EIDOLON-PHASE-9-REPAIR-RE-REVIEW.md` §8 requires fixed.
**Disclosure:** the same session that wrote the re-review made this repair (at the user's request). The re-review was independent of
the first repair; this repair is not independent of the re-review, and nothing here has been re-reviewed. No VCS; nothing committed.

**Verdict: RR-B1 (= H9-B1) AND RR-I1 REPAIRED — READY FOR INDEPENDENT RE-REVIEW.** Phase 9 is still **not** accepted: H9-I3, H9-U1,
H9-N1…N10 and the explicit exit criteria (live nightly, two external playtesters — F-1, F-2) are untouched.

## 1. Tree

Manifest (sha256 over the sorted `<sha256> ./path` lines of every `*.py`, no binary marker):

| | digest | files |
|---|---|---|
| before (the re-review's tree) | `7648d50957eb79fb8af17290aeafbaddeba0e44f641de84945a19fc545fb8c58` | 213 |
| after | `98f91bb4e6c7a89c7dd1e1e119fe16d6dd77ae76244743f9c5d6913c10aa55b7` | 213 |

Changed: `eidolon/decision/strategy.py` (RR-B1, one condition + docstring), `eidolon/debug/nightly.py` (RR-I1),
`eidolon/debug/promptdoc.py` (two notes); `tests/test_phase9_repairs.py` (one test replaced by two, three added, `ask_repeatedly`
takes `presented_ref`); `tests/phase9_mutation_check.py` (one mutant replaced by two, four added); `docs/EIDOLON-PROMPTS-AND-CONSTANTS.md`
regenerated; this report; `CLAUDE.md`, `docs/EIDOLON-KNOWN-DEBT.md`. No fixture, case, seal or proof changed.

## 2. RR-B1 — an inert shown item no longer switches the §15.4 escalation off

**Root cause.** `_repetition_penalty` applied the preference only `if inp.presented_ref is None`. The ask form's "Show them" accepts any
held item (and makes the question a `challenge`, whose hash ignores the item), so showing anything restored the pre-repair scorer: a LIE
(2.44) outscored `REPEAT_PRIOR` (2.40) and usually `REFUSE`, while TRUTH/VAGUE tied or lost to them.

**Change** (`strategy.py:355`):

```python
if inp.presented_ref is None or _deny_evidence_or_reinterpret(inp) is None:
```

The preference is off only while an authored response to the shown item is in play at this layer (`DENY_EVIDENCE`/`REINTERPRET`) —
the case the first repair meant to protect. Peels (`CONCESSION`/`CONFESSION`/`STONEWALL`/`SLIP`) are forced before utility and were
never gated. §15.4 itself has no shown-item exemption.

**Before → after** (the re-review's C9, four sealed cases, every V-7 question as a `challenge` showing an inert held item, 7 asks):

| first act | n | before: act never changes | after: act never changes | after: 6th–7th REFUSE |
|---|---|---|---|---|
| LIE | 50 | **50** | **0** | 50 |
| TRUTH | 35 | 2 | 0 | 35 |
| VAGUE | 348 | 6 | 0 | 348 |
| DONT_RECALL | 304 | 81 | 0 | 304 |
| DONT_KNOW | 180 | 74 | 0 | 180 |

Production path (`web.dispatch`, `study_party_s4`, inert item shown): LIE 3/3, TRUTH 3/3, VAGUE 17/17 now refuse by the 7th ask
(before 0, 0, 3); David: `LIE ×7` → `LIE, LIE, REPEAT_PRIOR ×3, REFUSE ×2`. Nothing shown: unchanged (A.1 bot 563/563 claim-bearing
answers escalate identically, 0 rejected). After real peels on the four murderers: 106 retracted statements, 0 re-supplied.

**Tests** (`tests/test_phase9_repairs.py`):

* `test_H9_B1_a_shown_item_is_a_new_question_so_repetition_never_hides_an_evidence_response` — **removed**: it asserted the preference
  is 0 for *any* shown item, i.e. it pinned the bypass. Replaced by:
* `test_H9_B1_an_authored_evidence_response_is_never_swallowed_by_repetition` — demo secret, `E_knife` has an authored `DENY_EVIDENCE`
  at layer 0: `select_plan` answers `DENY_EVIDENCE` at repeat 2, 3, 5, 7.
* `test_H9_B1_an_inert_shown_item_escalates_exactly_like_nothing_shown` — same input with nothing shown and with an unrelated ref:
  not `REPEAT_PRIOR` at repeat 1, `REPEAT_PRIOR` at 2, `REFUSE` at 5.
* `test_H9_B1_showing_an_inert_item_does_not_turn_repetition_back_into_a_sincerity_test[study_party_s4|manor_wing_s4]` — the repeat bot
  with an inert item shown on every ask: every claim-bearing first answer runs `[act, act, REPEAT_PRIOR ×3, REFUSE ×2]`, one claim set.

**Mutants:** `H9-B1-repetition-preferred-even-when-an-authored-response-is-shown` (gate → `True`; killed by the authored-response test)
replaces `…-even-when-an-item-is-shown`; new `RR-B1-preference-off-for-any-shown-item` (gate → `presented_ref is None`, the bypass;
killed by the inert tests).

## 3. RR-I1 — the "not judged on what was left" rule on N-4, N-6, N-7

* `nightly.Unanswered` wraps the budgeted transport and counts calls that got no answer (`ProviderError`, incl. timeouts and
  `BUDGET_EXHAUSTED`; **not** `ProviderRefusal`, which is the model's answer).
* N-4 is UNMEASURED if any call during the corpus sample went unanswered (or the budget ran out); its note and
  `report["corpus"]["sample"]["unanswered_calls"]` give the count.
* N-6 and N-7 describe the scripted session and, like N-1, are judged only when it is complete (`committed == turns`, budget not
  exhausted); otherwise UNMEASURED, note "incomplete session: not judged".

Before → after (the re-review's arms, SDK-shaped stand-in):

| arm | before | after |
|---|---|---|
| 24 of 25 corpus-sample parses get no answer | N-4 PASS `{"turns": 1}`, exit 0 | **N-4 UNMEASURED** ("… no answer …: 24") |
| parser refuses the sample lines (an answer) | N-4 PASS | N-4 PASS (unchanged, `unanswered_calls` 0) |
| generate down after 12 calls (9/60 committed) | N-6 FAIL 133, N-7 PASS | **N-6, N-7 UNMEASURED** |
| generate down after 40 calls (31/60 committed) | N-6 PASS 129, N-7 PASS, exit 0 | **N-6, N-7 UNMEASURED** |

N-3/N-5 unchanged (refusal → FAIL 444, malformed → FAIL 1155; audit on `claude-fable-5-1`). The outage arms still exit 0 because the
parse pass (N-3) completed and PASSes — exit-on-partial-measurement is H9-N9, not addressed here.

**Tests:** `test_RR_I1_a_corpus_sample_the_provider_did_not_answer_is_not_judged`, `…_a_refusal_during_the_corpus_sample_is_an_answer_and_is_still_judged`,
`…_a_session_an_outage_cut_short_does_not_judge_its_session_metrics`. **Mutants:** `RR-I1-provider-failure-in-the-sample-judged`,
`-refusal-counted-as-no-answer`, `-incomplete-session-judged-N6`, `-incomplete-session-judged-N7`.

## 4. Failing first

The seven new tests run against a clean copy of the before tree: **6 failed, 1 passed**. The pass is the authored-response test (the
old gate also never swallowed an authored response; the new gate is backed by its mutant). The refusal test fails there on the missing
`unanswered_calls` key rather than on behaviour; its behaviour is backed by `RR-I1-refusal-counted-as-no-answer`.

## 5. Runs on the after tree (each in a byte-verified scratch copy, manifest `98f91bb4…`)

| run | result |
|---|---|
| `python -m pytest -q -p no:cacheprovider` | **3823 passed, 1 skipped, 1 xfailed, 1 warning in 8092.16s (2:14:52)**, exit 0 — 3825 collected = 3819 − 1 removed + 7 new; the skip and xfail are the usual two |
| `python -m tests.phase9_mutation_check -j 5` | **baseline green; 124 killed, 0 survived, 0 malformed, 0 infrastructure errors (124 of 124)**, exit 0 |
| `python -m tests.decision.mutation_check` (Phase 4; `strategy.py` changed) | **PASS: 57 killed, 2 justified equivalent (M2, M4)**, exit 0 |
| `MUT_ONLY='^(RB1-c\|RB1-h\|RB2-b\|RB2-c\|RB2-g\|RB2-h\|RB2-i) ' python -m tests.solve.mutation_check` (Phase 6 mutants anchored in `strategy.py`/`turn.py`) | first attempt: `BASELINE IS NOT GREEN … TIMEOUT after 1500s` (machine load; exit 2, nothing counted); re-run with `MUT_TIMEOUT=6000 MUT_WORKERS=4`: **baseline green, 7 killed, 0 survived, PASS**, exit 0 |
| `python -m eidolon.cli validate cases/generated/<case>.json` × 4 | all four `{"ok": true}`, exit 0 |
| V-7 bots at full scale on the four sealed cases (`bots.run_bots`, five bots) | **20 of 20 reports identical** to the before tree's |
| `python -m eidolon.gen.study --seeds 50 --start 1` (both skeletons) | `manor_wing` 49/50 sealed (49 in band; the one rejection `V-5:robust`, the case CLAUDE.md records), `study_party` 50/50 (50 in band); **100 of 100 rows identical** to the before tree's (failure stage, package seal, bands, metrics), exit 0 — so the gate moved no generated case, greedy's repeated presentations included |
| `python -m eidolon.debug promptdoc`, `tests/test_phase9_docs.py` | regenerated; 28 passed |
| the re-review's attack scripts (C8–C12) | the "after" columns above |

Not re-run: the Phase 5 harness and the persistence harness (no file in their anchor sets changed: `turn.py` is untouched);
`EIDOLON_LONG=1` scales.

## 6. What stays open

H9-I3, H9-U1, H9-N1…N10 (incl. N9: exit 0 on partial measurement), F-1, F-2 (explicit Phase 9 exit criteria), F-14 (tie flips, measured
unchanged: 3/281 VAGUE, 14/109 DONT_KNOW on the 2nd ask), F-15, and the re-review's NON-BLOCKING RR-N1…N4.

**RR-B1 AND RR-I1 REPAIRED — READY FOR INDEPENDENT RE-REVIEW**
