# EIDOLON — Phase 9 repair re-review (H9-B1, H9-I1, H9-I2)

Date: 2026-10-22 (started 2026-10-21). Reviewer: a fresh Claude Code session (Opus 5.5) started by another session of this project; it
had no part in the Phase 9 implementation, the hostile review or the repair. It is not a human or a separate team. Read-only on the
repository by instruction: no production code, test, fixture, case or existing report was changed; every run and every attack below
executed in byte-verified scratch copies. This file is the only file written into the repository. No live provider was called.

Inputs: `docs/EIDOLON-PHASE-9-HOSTILE-REVIEW.md` (findings H9-B1, H9-I1, H9-I2 and its §10), `docs/EIDOLON-PHASE-9-REPAIR-REPORT.md`
(the author's claims), the code and tests the repair touched.

## Verdict

| finding | as filed | re-review | why |
|---|---|---|---|
| **H9-B1** (BLOCKING) | repeating a question tells a lie from a truth | **NOT CLOSED** | Closed when nothing is shown (reproduced: 563 of 563 claim-bearing first answers escalate identically). Re-opened by one click: the repair switches the §15.4 preference off whenever *any* item is shown, and the ask form's "Show them" select takes any held item. Showing one item that is inert for the addressee restores the defect exactly — the repaired engine's numbers on that path are **identical, row for row, to the pre-repair engine's** (LIE 50 of 50 never change in seven asks; TRUTH 2 of 35, VAGUE 6 of 348). Reproduced through `web.dispatch` → `game.ask` → `_commit`. See RR-B1. |
| **H9-I1** (IMPORTANT) | N-3 counted failed parses as classifications; mid-pass budget → PASS/FAIL | **CLOSED for N-3** (as filed) | refusal → miss, malformed → miss, transport/timeout/budget → UNMEASURED; reproduced. The same defect class survives in sibling metrics: N-4 PASSes on 1 of 25 corpus lines when the provider failed the other 24, and N-6/N-7 are judged on a session an outage cut to 31 of 60 turns (exit 0) — RR-I1, IMPORTANT, new. |
| **H9-I2** (IMPORTANT) | N-5 claimed `claude-fable-5-1`, called `claude-opus-5` | **CLOSED** | audit verify calls go to `claude-fable-5-1` (21 of 21 in a live-stand-in run; session generate/parse/verify stay on `claude-opus-5`); the note is read off the successful calls; a failing audit says "verifier not reached" and is UNMEASURED. |

**The review's verdict does not change: B. `REQUIRED FIXES — REMAIN IN PHASE 9`.** H9-B1 is still open (as RR-B1), RR-I1 is new, and
everything the review left open (H9-I3, H9-U1, H9-N1…N10, F-1, F-2) is unchanged by the repair.

---

## 1. Tree

Manifest formula as stated in the task: sha256 over the sorted `sha256 path` lines of every `*.py` (excluding `__pycache__`), one
space between hash and `./path`.

| tree | `*.py` files | digest | how verified |
|---|---|---|---|
| repository at the start of this re-review | 213 | `7648d50957eb79fb8af17290aeafbaddeba0e44f641de84945a19fc545fb8c58` | equal to the repair report's "after" digest; my line list is byte-identical to the repair session's own `manifest_final.txt` |
| every scratch copy used below (`S_full`, `S_mut9`, `S_atk`, `S_p45`) | 213 | `7648d509…` (first 16 hex re-computed in each copy before use) | |
| `S_study` (eidolon/, tests/, cases/ only) | — | eidolon+tests line list identical to the repository's | |
| `PRE`: the pre-repair tree, taken from the repair session's attack copy | 212 | `ded4fa6971aecf40…` in this formula | its line list is identical to the repair session's `manifest_py.txt`, whose raw file hash is the review's `9f9969c8…` |
| `S_guard`: a clean copy of the repaired tree (eidolon/, tests/, cases/) plus the candidate guard file | — | eidolon line list identical to the repository's | |
| `S_fix`: a remedy prototype (one line of `strategy.py` changed, §3.6; the guard file added) | — | not the repository's tree, by design | |

At the end of the re-review the repository's manifest was still `7648d509…` and no file under `eidolon/ tests/ spike/ cases/ docs/`
or `CLAUDE.md` was newer than the starting manifest, apart from this report.

Diff of `PRE` against the repository: exactly the files the repair report lists (`strategy.py`, `turn.py`, `nightly.py`, `promptdoc.py`;
`tests/phase9_mutation_check.py`, `test_phase9_corpus.py`, `test_phase9_docs.py`, `test_phase9_suites.py`; new `test_phase9_repairs.py`).
Nothing else changed.

**RR-N1 (NON-BLOCKING, report accuracy).** The repair report's §1 table compares digests computed two different ways. The review's
`9f9969c8…` is the hash of a manifest whose lines carry Git-Bash `sha256sum`'s binary marker (`<hash> *./path`); the repair's
`7648d509…` hashes lines without it. In one formula the pair is `ded4fa69…` → `7648d509…`; in the other `9f9969c8…` → `e6623363…`. The
trees themselves are what the report says they are (line lists compared directly).

Environment: Windows 11, Python 3.12.10, pydantic 2.13.5, starlette 1.3.1, pytest 9.1.1, hypothesis 6.167.1. `import anthropic` →
`ModuleNotFoundError`; no `ANTHROPIC_API_KEY`.

## 2. Commands and observed exit codes

| # | command (scratch copy) | observed |
|---|---|---|
| C1 | `python -m pytest -q -p no:cacheprovider` (`S_full`) | `3817 passed, 1 skipped, 1 xfailed, 1 warning in 7018.06s (1:56:58)`, **exit 0** — the same counts as the repair report (the skip is the real-provider cassette replay, the xfail the strict H8-X2 witness) |
| C2 | `python -m tests.phase9_mutation_check -j 6` (`S_mut9`) | `baseline green; 119 killed, 0 survived, 0 malformed, 0 infrastructure errors, 0 justified equivalent (119 run of 119)`, **exit 0** |
| C3 | `python -m tests.decision.mutation_check` (`S_p45`; Phase 4 set, `strategy.py`/`turn.py` changed) | `MUTATION VERIFICATION: PASS` — 57 KILLED, 2 justified equivalent (M2, M4, unchanged), **exit 0** (the author ran it on `6e6b0f0c…`; this is the final tree) |
| C4 | `python -m tests.decision.mutation_check phase5` (`S_p45`; three anchors in `turn.py`; **not** re-run by the author) | `MUTATION VERIFICATION: PASS` — 70 KILLED, 1 justified equivalent (P5-22, as recorded in CLAUDE.md), **exit 0** |
| C5 | `python -m eidolon.cli validate cases/generated/<case>.json` × 4 (`S_atk`) | `{"ok": true, "failed_at": null, "problems": []}`, **exit 0**, for each of `study_party_s4`, `study_party_s5`, `manor_wing_s4`, `manor_wing_s6` |
| C6 | `atk_bots.py`: `bots.run_bots(…, names=greedy, cue_following, murderer_peel, bluff, adversarial)` at full V-7 scale on the four sealed cases, on `PRE` and on the repaired tree, reports compared | **20 of 20 bot reports identical** (every field incl. the per-act counts), exit 0 both |
| C7 | `python -m eidolon.gen.study --seeds 20 --start 1 --workers 3 --out …` on `PRE` and on the repaired tree (`S_study`), rows compared | both trees: `manor_wing` 20/20 sealed, 20 in band; `study_party` 20/20 sealed, 20 in band; **40 of 40 rows identical** (failure stage, package seal, bands, metrics), exit 0 both (≈ 49 min wall each, run concurrently) |
| C8 | `atk_a1.py` — the review's Appendix A.1 repeat bot, nothing shown (`S_atk`) | §3.2, exit 0 |
| C9 | `atk_shown.py` — the same bot showing one inert held item each ask, on `S_atk` **and** on `PRE` | §3.3, exit 0 both |
| C10 | `atk_web.py` — RR-B1 through `web.dispatch` on `study_party_s4` | §3.3, exit 0 |
| C11 | `atk_retract.py` — real peels (`bots.peel_secret`) on the four murderers, then repeats | §3.4, exit 0 |
| C12 | `atk_nightly_rr.py`, `atk_nightly_n67.py` — nightly with the suite's SDK-shaped stand-in | §4, §5, exit 0 |
| C13 | `test_rr_b1.py` (candidate guard, scratch only) on a clean copy of the repaired tree and on `S_fix` | repaired: **2 failed**, exit 1; `S_fix`: **2 passed**, exit 0 |

Scripts and logs: `C:\Users\ASUS\AppData\Local\Temp\claude\D--Murder-Mystery\a236fc28-3525-493b-a35e-2d632b59f6f2\scratchpad\`
(machine-local; the decisive snippets are in Appendix A).

## 3. H9-B1

### 3.1 The claims, checked against the code

| claim (repair report §2) | code | holds? |
|---|---|---|
| `REPEAT_PRIOR` is built from the speaker's latest **standing** answer to this `query_hash`, never from retrieval | `turn.py:340-341` (`standing_for_speaker`, latest with claims), `strategy.py:232-237` | yes |
| a peel's retraction removes the answer from what is re-supplied | `standing_for_speaker` excludes retracted statements; §3.4 measures it on real peels | yes |
| `REPEAT_PRIOR` from the 3rd identical question scores 3.10, above every other act's ceiling of 3.00; `REFUSE` from the 6th ≥ 3.25 | `strategy.py:345-362`. Ceiling = 1.0+0.6+0.4+0.3+0.3+0.4 with every fit ≤ 1 (EVASION's penalty only lowers it). `REPEAT_PRIOR` = 2.40+0.70; `REFUSE` = 2.25+0.3(1−talk)+1.00 | yes, **for personality weights in [0, 1]** — `Personality.guile/talkativeness/self_preservation` are unconstrained `float`s (`minds/character.py:37-39`); `solve.session` derives them in [0.3, 0.9], so every shipped persona is inside. RR-N2 |
| forced acts (`CONFESSION`, `CONCESSION`, `STONEWALL`, `SLIP`) still win | `select_plan` picks them before utility (`strategy.py:434-442`) | yes |
| evidence responses are never swallowed | the preference is off whenever `presented_ref` is set (`strategy.py:355`) | yes — and that gate is RR-B1 |

### 3.2 Nothing shown: reproduced

The review's A.1 bot on the repaired tree (four sealed cases, every V-7 question to every living character, seven asks, chained state):

| first act | n | 6th–7th include REFUSE | more than one distinct claim set | 2nd ask's act differs |
|---|---|---|---|---|
| LIE | 250 | 250 | 0 | 0 |
| TRUTH | 32 | 32 | 0 | 0 |
| VAGUE | 281 | 281 | 0 | 3 |
| DONT_RECALL | 245 | 245 | 0 | 0 |
| DONT_KNOW | 109 | 109 | 0 | 14 (+3 more flip on the 3rd/4th ask) |

Every LIE, TRUTH and VAGUE first answer runs `[act, act, REPEAT_PRIOR ×3, REFUSE ×2]` except the 3 VAGUE that tie-flip on the second
ask (F-14). 0 rejected turns. This matches the repair report's §2.3 exactly. Through the production path (`web.dispatch`, C10,
nothing shown): LIE 11/11, TRUTH 3/3, VAGUE 18/18 refuse by the 7th ask.

### 3.3 RR-B1 — BLOCKING — show any inert item and repetition is a sincerity test again

**Mechanism.** `_repetition_penalty` applies the §15.4 preference only `if inp.presented_ref is None` (`strategy.py:355`). The ask form
puts a "Show them" select next to every structured question (`web.py:142`, `231-239`); any held item is accepted and turns the
question into `kind="challenge"` (`game.question`, `game.py:198`). `normalize` keys a question on `(kind, subject, hint, object,
location, bucket)` and ignores the exhibit (`query.py:69-80`), so the same challenge, shown the same — or any — item, accumulates
`repeat_count` with the preference switched off, i.e. with the pre-repair scorer: LIE 2.44 always beats `REPEAT_PRIOR` 2.40 and
beats `REFUSE` (2.25 + 0.3·(1 − talkativeness)) unless talkativeness < 0.37, while TRUTH/VAGUE tie `REPEAT_PRIOR` at 2.40 (hash
tie-break) and lose to `REFUSE` whenever talkativeness < 0.5.
§15.4 has no exemption for a shown item; the exemption is the repair's own design decision (report §2.2), justified by authored
evidence responses — which an inert item does not have.

**Decision level** (C9: A.1's bot, but each of the seven asks shows the first held item that is inert for the addressee — no
`evidence_responses` entry and zero `refutation_weight` against every layer of every secret it owns; no peel occurred in any sequence):

| first act | n | 6th–7th include REFUSE | act never changes in 7 asks |
|---|---|---|---|
| **LIE** | **50** | **0** | **50** |
| TRUTH | 35 | 3 | 2 |
| VAGUE | 348 | 129 | 6 |
| DONT_RECALL | 304 | 223 | 81 |
| DONT_KNOW | 180 | 86 | 74 |

On `PRE` (the unrepaired engine) the same script prints **the same table, every cell equal**. The repair does nothing on this path.

Read as an oracle over claim-bearing first answers (LIE, TRUTH, VAGUE): with a model renderer, where `REPEAT_PRIOR`'s "weary" delivery
is visible, "the act never changed" picks the lie with precision 50/58 = 86 % and recall 100 % (the review's H9-B1 figure for the same
reading: 80 %); with the template renderer, where only `REFUSE` changes the words, "it turned into a refusal" certifies "not a lie"
for 132 of 383 honest answers and for 0 of 50 lies ("never refused" picks the lie with precision 50/301 = 17 %, against the review's
55 % on the nothing-shown path).

**Production path** (C10: `web.dispatch` with `op=ask` and `present=<handle>`, `study_party_s4`, 16 questions per character, 7 posts each):

| first act | shown nothing: refuse by 7th / act never changes | shown one inert item: refuse by 7th / act never changes |
|---|---|---|
| LIE | 11 of 11 / 0 | **0 of 3 / 3** |
| TRUTH | 3 of 3 / 0 | 0 of 3 / 1 |
| VAGUE | 18 of 18 / 0 | 3 of 17 / 0 |

David (the murderer): `"I never touch a crystal decanter."` → shown nothing: `LIE, LIE, REPEAT_PRIOR ×3, REFUSE ×2`; showing an inert
item: `LIE ×7`, the same sentence seven times.

**Why the tests did not see it.** Every H9-B1 test and suite 2 ask with nothing shown. `test_H9_B1_a_shown_item_is_a_new_question_so_
repetition_never_hides_an_evidence_response` asserts the opposite of the fix — that the preference is 0 for *any* shown item, without
asking whether the item has an authored response — and the mutant `H9-B1-repetition-preferred-even-when-an-item-is-shown` is killed by
that test alone. The harness therefore pins the bypass.

**Cost to the player:** hold any one item (the first search gives one), pick it in "Show them", ask the same question 3–7 times.

**Remedy (smallest, prototyped in `S_fix`, §3.6).** Gate the preference on whether an authored response is actually in play, not on
whether something is shown: `if inp.presented_ref is None or _deny_evidence_or_reinterpret(inp) is None:` (peels are forced and need
no gate). Replace the shown-item unit test with (i) "an inert shown item escalates like nothing shown" and (ii) "an item with an authored
response is never swallowed"; add the repeat bot with an inert item shown (the candidate in Appendix A.2) next to the existing one; add
a mutant for each.

### 3.4 Attacks that held

* **Retracted answers.** On each sealed case the murderer was asked every V-7 question twice, layer 0 was broken through play
  (`bots.peel_secret`, the V-7 route), and every question was asked four more times. 106 statements were retracted across the four
  cases; **0** `REPEAT_PRIOR` turns re-supplied a retracted proposition; 0 rejected turns. A question whose lie was retracted gets a
  fresh answer from the new layer and then `REPEAT_PRIOR` of *that* — evidence-gated, not a tell.
* **Peels, slips, confessions.** Forced acts are selected before utility; a peel can only follow a presented set, and the repetition
  preference never outranks it. In C11 all four murderers' layer 0 broke through play (`peeled=True`), and C9 saw no peel or stonewall
  at all (the inert-item filter guarantees it).
* **Meta/coercion.** `enumerate_candidates` restricts them to `CLARIFY/ANGER/COUNTER_QUESTION` (+ voiced peels): no `REPEAT_PRIOR` or
  `REFUSE` candidate, no claims — act-independent.
* **Bluff parity.** A bluff pair shares one `query_hash` (the presupposition is not part of `normalize`), so both halves get the same
  `prior` and the same preference — parity cannot break through this change.
* **V-7 and case validation.** C6: all 20 bot reports identical to `PRE`'s, field for field. Structurally: greedy/cue/murderer-peel
  never repeat a nothing-shown question (`_ask_batch` dedupes) and their `challenge` presentations are shown, so ungated by the
  preference; bluff/adversarial repeat a key rarely and claimlessly. C5: all four sealed cases validate `ok` on the final tree. C7: seeds 1–20 of both skeletons generate the same sealed packages, byte-identical seals, on both trees.
* **Tie flips (F-14).** Measured in §3.2: 3 of 281 VAGUE, 14 of 109 DONT_KNOW on the 2nd ask, 0 LIE, 0 TRUTH; plus 3 DONT_KNOW-first
  answers that flip on the 3rd/4th ask (a claimless first answer has no `prior`, so the tie keeps being re-drawn until a claim appears) —
  KNOWN-DEBT F-14 says "the SECOND ask". Agree NON-BLOCKING: ~1 % of VAGUE answers certified "not a lie". Fix it with RR-B1 (the remedy
  touches the same scorer; keying `_tie_break` on the question rather than the turn would also remove the shown-item TRUTH↔`REPEAT_PRIOR`
  flips if the RR-B1 gate is not changed).
* **F-15** (`refuse_streak` never set): agree, act-independent.

### 3.5 Tests, harness and documentation for H9-B1

* Suite 2 is **strengthened**, not weakened: both arms now assert `[act, act, REPEAT_PRIOR ×3, REFUSE …]` exactly. One sub-check
  narrowed (`all(offered[2:6])` → `offered[2:5]`): immaterial, because `acts[5:] == REFUSE` is asserted.
* `test_phase9_corpus.py` `burst`: the two-sided `abs(Δ) ≤ 12` became `Δ ≤ 12` plus "smaller by more than 12 only if the final turn is
  `REFUSE` at repetition ≥ 5". Sound: for every non-repeating sequence the old lower bound still binds (repetition < 5).
* The 8 new H9-B1 mutants and the 2 re-pointed ones are killed (C2), but see RR-B1 for the one that pins the bypass.
* `docs/EIDOLON-PROMPTS-AND-CONSTANTS.md` describes `REPEAT_PRIOR_PREFERENCE` as beating "every other act's utility ceiling" with no
  mention of the shown-item exemption, and `CLAUDE.md` says "when nothing is shown" — the latter is accurate.

### 3.6 Remedy prototype (scratch only — not a repair)

`S_fix` is the final tree with one line of `strategy._repetition_penalty` changed:

```diff
-    if inp.presented_ref is None:
+    if inp.presented_ref is None or _deny_evidence_or_reinterpret(inp) is None:
```

| run on `S_fix` | result |
|---|---|
| C9's shown-item bot | every claim-bearing first answer escalates identically: LIE 50/50, TRUTH 35/35, VAGUE 342/348 run `[act, act, REPEAT_PRIOR ×3, REFUSE ×2]`; the other 6 VAGUE are F-14 tie flips on the 2nd ask, then the same escalation; 0 sequences where the act never changes |
| C6's V-7 bots, full scale, four sealed cases | **20 of 20 reports identical** to the repaired tree's (and so to `PRE`'s) |
| `test_phase9_repairs.py` (with `-x`) | the first and only failure is `test_H9_B1_a_shown_item_is_a_new_question_…` (`assert -1.4 == 0.0`), the test that pins the bypass, as expected |
| the rest of `test_phase9_repairs.py`, `test_phase9_suites.py`, `test_phase9_corpus.py` and the candidate guard (Appendix A.2), that test deselected | **783 passed**, 1 failed: the guard's coverage floor on `study_party_s4` (`Counter({'VAGUE': 42, 'TRUTH': 3, 'LIE': 3})`, floor 5) — its escalation assertion held for every sequence on both cases; floor lowered to 3 and re-run: **2 passed**, exit 0 |

This is evidence that a one-line gate closes RR-B1 without moving V-7 on the four sealed cases. It is not a repair: it was not run
against the whole suite, the harnesses or the seed study, and an authored-response check deserves its own unit tests. One thing a real
repair must re-measure: with the gate, an inert item shown again and again to the same addressee *does* escalate — including in V-7's
greedy bot, whose presentations (`Query(kind="challenge")`, no subject) share one hash per addressee. On these four cases greedy solves
before that matters (identical reports); on other seeds it may not, so the seed study must be re-run.

## 4. H9-I1

**Claims checked** (`nightly.py:130-161`, `204-223`):

* A `ProviderRefusal` → label `refused` (no category accepts it) → miss. A malformed reply (`MalformedOutput` is not a `ProviderError`)
  → `failed` → miss. A `ProviderError`/`ProviderTimeout`/`BUDGET_EXHAUSTED` → `unmeasured`, and one unmeasured line makes N-3 UNMEASURED.
  `ProviderRefusal` subclasses `ProviderError` but is caught first. Departing from the review's remedy (which put refusals with
  "unmeasured"), the repair counts a refusal as a miss — the conservative direction; agreed.
* N-4 is UNMEASURED when the budget is exhausted after the corpus sample.

**Reproduced** (C12, `AnthropicTransport` over the suite's `FakeAnthropicClient`, so `is_live` is true):

| arm | N-3 | exit |
|---|---|---|
| A: parser refuses 215 of 225 lines (SDK `stop_reason="refusal"`) | **FAIL 444** | 1 |
| B: malformed parse output for the non-coercion lines | **FAIL 1155** | 1 |
| repair tests: transport error / budget cut at 100 and 195 lines | UNMEASURED (as asserted by `test_phase9_repairs.py`, green in C1) | — |

### RR-I1 — IMPORTANT — the rule H9-I1 introduced is applied to N-3 only

The repair's own principle — "a measurement the provider or the budget cut short is not judged on what was left" (`nightly.py:17-18`,
"every metric that needed the missing turns is UNMEASURED") — holds for N-1 and N-3 and for N-4's *budget* case, and nowhere else:

| arm (C12) | committed | N-1 | N-4 | N-6 | N-7 | exit |
|---|---|---|---|---|---|---|
| C: every corpus-sample parse after the first fails at the transport (`APIConnectionError`), `corpus_turns_n=25` | 24/24 | PASS | **PASS `{"turns": 1}`** | — | — | **0** |
| generate route down after 12 calls (outage) | 9/60 | UNMEASURED | UNMEASURED | **FAIL 133** | **PASS** | 1 |
| generate route down after 40 calls | 31/60 | UNMEASURED | UNMEASURED | **PASS 129** | **PASS** | **0** |

* N-4: `corpus_turns` drops every line `interpret` turned into `Refused` — a transport failure (`Refused("PARSE_FAILED:ProviderError")`)
  exactly like a legitimate refusal — and every turn whose render failed, and judges the rest. One contained turn out of 25 is a PASS. §9
  of the review gives "N-4 with ≥ 25 lines" as the evidence that would close the criterion.
* N-6/N-7: `slo.from_save` over the committed turns, not gated on `complete` the way N-1 is.

Not introduced by the repair (both behaviours predate it), but it is the H9-I1 defect class — a PASS for answers the provider never gave
— on the sibling metrics of the same instrument, and the repair's docstring claims the general rule. Remedy: in `corpus_turns`, count
lines whose `interpret` result is `Refused("PARSE_FAILED:ProviderError")` or `…:ProviderTimeout` (a transport failure — not
`…:ProviderRefusal`, which is the model's answer), and turns whose render failed with a transport error, as unmeasured; N-4 UNMEASURED if any is, or if fewer than `corpus_turns_n` lines were turns *and* classified; gate N-6/N-7 on `complete` like
N-1; tests and mutants for each.

## 5. H9-I2

**Claims checked.** `audit_transport_for` re-points an `AnthropicTransport` at `AUDIT_MODEL` on the same client (`nightly.py:83-88`);
`run` gives the audit its own `BudgetedTransport` with what the session left and its own `GuardedTransport`, and builds N-5's note from
`audit_guard.drain()` — only successful calls carry a model (`provider.py:162-166`). `provider_calls`/`budget_exhausted` include the audit.

**Reproduced** (C12): models by role in arm A — `generate/parse/verify → claude-opus-5` for the session (31/231/25 calls), `verify →
claude-fable-5-1` for the audit (21 calls); note `"sampled 25; verifier claude-fable-5-1"`. Audit verify calls failing → note `"verifier
not reached"`, `verifier_errors 21`, N-5 UNMEASURED. Dry run → note `"verifier repairing-stub"`.

Residuals (NON-BLOCKING): **RR-N3** `Completion.model` is the model the transport *asked for* (`provider.py:106`), not the SDK
response's `model` field, so the note names the requested model; for a pinned id like `claude-fable-5-1` that is the same thing.
**RR-N4** `run(…, transport=<a wrapper around an AnthropicTransport>)` audits on the generation model (`audit_transport_for` only
recognises a bare `AnthropicTransport`) and, while naming that model honestly, can still PASS N-5 without the stronger verifier, and an
explicit `audit_transport` is never checked by `is_live`. Neither is reachable from `main()`, which passes a bare transport and `None`.

## 6. The constants document (repair §5)

Verified: `promptdoc._constants` and the docs test (a separate implementation) both unpack tuple targets; the regenerated document lists
`W_SAFETY … W_REPEAT`, `REPEAT_PRIOR_PREFERENCE`, `REFUSE_PREFERENCE`, the memory weights; `test_phase9_docs.py` green in C1. Neither
handles `[A, B] = …` or starred targets — none exists in the documented modules today.

## 7. Findings

| ID | severity | finding | blocks |
|---|---|---|---|
| **RR-B1** (= H9-B1, not closed) | **BLOCKING** | Showing any inert held item switches the §15.4 preference off; repetition is then exactly the pre-repair sincerity oracle (LIE 50/50 unchanged); a unit test and a mutant pin the bypass | Phase 9 acceptance, Phase 10 |
| **RR-I1** | **IMPORTANT** | N-4 PASSes on the corpus lines the provider did answer (1 of 25 → PASS, exit 0); N-6/N-7 judged on an outage-truncated session (31/60 → PASS, exit 0) | using N-4/N-6/N-7 as live evidence (F-1) |
| RR-N1 | NON-BLOCKING | Repair report §1 compares digests computed with two line formats | — |
| RR-N2 | NON-BLOCKING | The "structural" margins assume personality weights in [0, 1]; the type does not enforce it | — |
| RR-N3, RR-N4 | NON-BLOCKING | N-5's note names the requested model; a wrapped or explicit audit transport is not forced onto `AUDIT_MODEL` (not reachable from `main()`) | — |
| F-14 | NON-BLOCKING (agree; measured) | tie flips on the 2nd ask (and 3rd/4th after a claimless first answer) | — |
| F-15 | NON-BLOCKING (agree) | `refuse_streak` never produced | — |

Unchanged by the repair and still open: H9-I3, H9-U1, H9-N1…N10, F-1, F-2 (review §8–§9).

## 8. Required before the review's verdict can change

1. **RR-B1**: the gate in §3.3's remedy (or an equivalent that makes repetition act-independent whatever is shown, short of an authored
   response or a peel); the shown-item repeat bot as a test; mutants; re-run the Phase 4 and Phase 9 harnesses, the V-7 bots and the
   whole suite.
2. **RR-I1**: provider failures in the corpus sample make N-4 UNMEASURED; N-6/N-7 gated on a complete session; tests.
3. An independent re-review of those two.

**Verdict: H9-I2 CLOSED; H9-I1 CLOSED for N-3 with RR-I1 open; H9-B1 NOT CLOSED (RR-B1). The review stays at B. `REQUIRED FIXES —
REMAIN IN PHASE 9`.**

---

## Appendix A — reproductions

### A.1 RR-B1, decision level

The review's A.1 bot with one change — each ask shows a held item that is inert for the addressee (`atk_shown.py`; run from the
tree's root as `python -I atk_shown.py .`):

```python
from eidolon.decision.weight import refutation_weight
...
    ctx = st.ctx()
    for who in sorted(st.case.living_actors()):
        secrets = list(st.secrets.for_owner(who))
        inert = lambda e: (not any(r.evidence == e for s in secrets for r in s.evidence_responses)
                           and all(refutation_weight(frozenset({e}), layer, who, ctx) == 0
                                   for s in secrets for layer in s.cover.layers))
        item = next(e for e in sorted(st.discovery.known_evidence) if inert(e))
        for q in expressible_queries(st.case, who, names):
            q = q.model_copy(update={"kind": "challenge"})     # game.question(..., presenting=True)
            acts = []
            for _ in range(7):
                r = run_ask_turn(st, who, q, presented_ref=item)
                st, acts = (st, acts + ["REJECTED"]) if r.rejected else (r.state, acts + [r.plan_act])
            # group by acts[0]: LIE 50 -> act never changes 50, REFUSE in asks 6-7: 0  (repaired tree == PRE)
```

Production path (`atk_web.py`): `web.dispatch(save, {"op": "ask", "action_id": …, "expected_seq": str(save.last_seq), "addressee": who,
"topic": hint, "about": subject, "place": loc, "bucket": b, "present": game.handle(save, item)})`, seven times; the act is read from
`save.state.decision.statements.for_speaker(who)[-1].act`.

### A.2 RR-B1, candidate guard (fails on the repaired tree, passes on the prototype)

`test_rr_b1.py` — the repeat bot of `test_phase9_repairs.py` with an inert item shown; asserts `acts[2:] == [REPEAT_PRIOR]*3 +
[REFUSE]*2` for every claim-bearing first answer and at least 3 LIE and 3 non-LIE answers seen. On a clean copy of the repaired tree: **2 failed** (`study_party_s4`: `At index 1 diff: 'TRUTH' != 'REPEAT_PRIOR'`;
`manor_wing_s4`: `At index 0 diff: 'TRUTH' != 'REPEAT_PRIOR'`), exit 1. On `S_fix`: **2 passed**, exit 0.

### A.3 RR-I1

`atk_nightly_rr.py` arm C (`AnthropicTransport` over `tests.test_phase9_nightly.FakeAnthropicClient`):

```python
class CorpusSampleFails(ParserToo):            # the 225-line parse pass is answered; then every corpus-sample parse but one fails
    def __init__(self): super().__init__(); self.parses = 0
    def complete(self, req):
        if req.role == "parse":
            self.parses += 1
            if self.parses > len(ALL) + 1:
                raise ProviderError("APIConnectionError")
        return super().complete(req)

rep = nightly.run(out, transport=AnthropicTransport(Rec(CorpusSampleFails())), turns=24, audit_sample=30, corpus_turns_n=25,
                  run_suites=False)
# N-1 PASS, N-3 PASS 10000, N-4 PASS {"turns": 1, "dirty": []}, N-5 UNMEASURED; exit_code 0
```

`atk_nightly_n67.py`: `ParserToo` whose `generate` role raises `ProviderError("APIStatusError")` after N calls; `turns=60`. N=40 →
31/60 committed, N-1 UNMEASURED, N-6 PASS 129, N-7 PASS, exit 0.

---

## Repair of RR-B1 and RR-I1 (appended 2026-10-22 — author's record, not a re-review)

At the user's request the session that wrote this re-review repaired RR-B1 and RR-I1: `docs/EIDOLON-PHASE-9-RR-REPAIR-REPORT.md`. The
gate in §3.3 was applied as proposed; the pinning test and mutant were replaced; N-4/N-6/N-7 follow the H9-I1 rule. Because reviewer
and repairer are again the same session, the repair needs an independent re-review before this re-review's verdict can change.
Nothing above this section was edited.
