# EIDOLON — Phase 9 independent hostile review

Date: 2026-10-21. Reviewer: an independent Claude Code session (Opus 5.5) with no part in the Phase 9 implementation, read-only on the
repository by instruction: no production code, test, fixture or existing report was changed; every run and every attack below executed in
byte-verified scratch copies of the tree. This file is the only file written into the repository. Phase 10 was not started.

**Verdict: B. `REQUIRED FIXES — REMAIN IN PHASE 9`**

In one paragraph: the TurnTrace producer, its failure safety, the sink, the export boundary, I-10 and the debug server held against every
attack I made on the real HTTP → `_commit` → SQLite path, and the reported test and mutation baselines reproduce. Phase 9 still cannot be
accepted, for three reasons that are independent of each other. (1) **H9-B1, BLOCKING:** §28.4 suite 2 ("same question 50× → `REPEAT_PRIOR`
after 2, escalation after 5") is not met — every LIE answer in four generated cases (250 of 250) is restated unchanged through seven repeats
while 74 % of DONT_RECALL and 37 % of VAGUE answers turn into a refusal — so *repeating a question is a zero-evidence sincerity test*, and the
Phase 9 suite asserts the violating behaviour as correct. (2) **H9-I1 / H9-I2, IMPORTANT:** the nightly job — the only instrument that can
close the live-model criteria — manufactures a parser-classification PASS from parse *failures* and labels its audit as run by
`claude-fable-5-1` when every verify call goes to `claude-opus-5`. (3) The Phase 9 **exit** criterion "two external playtesters complete a
generated case; no invariant violations in their traces" (§30) is unmet, and the deliverable "live-model nightly" has never run against a
provider. (3) is not a defect of the code, but §30 makes it an explicit exit condition, so Phase 9 cannot be exited without it.

---

## 1. Source snapshot

No VCS. Manifest = `sha256sum` over the sorted list of every `*.py` file (excluding `__pycache__`), recorded **before** any run:

| set | files | digest (first 16 hex of sha256 over the sorted `sha256 path` lines) |
|---|---|---|
| all `*.py` | 212 | `9f9969c8f3af85da` (full: `9f9969c8f3af85dafdec354a12af15c81e56d1a6a07d82ba39f28e80e499f8d6`) |
| `eidolon/` | 101 | `2b2536993b681355` |
| `tests/` | 102 | `3eb5469a816490fa` |
| `spike/` | 9 | `dbd5baee988487fc` |
| `cases/` + `docs/` (all files) | 34 | `31f52a526d745dd4` |

File counts match the implementation report's (`eidolon` 101, `tests` 102, `spike` 9); the author's digests use a different formula
(`manifest.py`, not in the tree), so they are not comparable byte for byte. Key files (first 16 hex of their sha256): `trace.py` `59c80cb3c3829386`,
`store.py` `efbeea329ccd706a`, `game.py` `3cfa4b2f4f7f1576`, `web.py` `dce66d0a803ba7b1`, `debug/nightly.py` `35afd9fcabc5ee77`,
`debug/app.py` `d5337af3bdd1577a`, `decision/strategy.py` `113aa9eb0e3ecb38`, `tests/test_phase9_suites.py` `d11da00344ffe45e`,
`tests/test_phase9_corpus.py` `a365eb5abeb267ed`, `tests/llm/injection_corpus_v2.py` `28e216ee13ef6970`.
Every scratch copy was diffed against this manifest before use (`COPY_IDENTICAL`), and the repository was re-checked at the end: no file in
`eidolon/ tests/ spike/ cases/ docs/` is newer than the manifest except this review.

Environment: Windows 11, Python 3.12.10, pydantic 2.13.5, starlette 1.3.1, pytest 9.1.1, hypothesis 6.167.1. `import anthropic` →
`ModuleNotFoundError` (exit 1). No `ANTHROPIC_API_KEY`. **No live provider was called by this review.**

---

## 2. Commands and observed exit codes

| # | command (run in a scratch copy) | observed |
|---|---|---|
| R1 | `python -m pytest -q -p no:cacheprovider` | `3804 passed, 1 skipped, 1 xfailed, 1 warning in 5044.00s (1:24:03)`, **exit 0** (the skip is the real-provider cassette replay; the xfail is the strict H8-X2 witness) |
| R2 | `python -m tests.phase9_mutation_check -j 8` | `baseline green; 103 killed, 0 survived, 0 malformed, 0 infrastructure errors, 0 justified equivalent (103 run of 103)`, **exit 0** |
| R3 | `python -m tests.persistence_mutation_check -j 8` | `baseline green; 197 killed, 0 survived, 0 malformed, 0 infrastructure errors, 8 justified equivalent`, **exit 0** |
| R4 | static anchor check of `tests/decision/mutation_check.py` (`M`: 59 mutants / 69 edits, `M5`: 71 / 76) | every anchor matches exactly once (incl. the three re-anchored `stages=stages` edits; the mutation still deletes the same `if result.rejected: return …` block) — the harnesses themselves were **not** re-run |
| R5 | `python -m eidolon.cli validate cases/generated/<case>.json` × 4 | `{"ok": true, "failed_at": null, "problems": []}`, **exit 0**, for each of `study_party_s4`, `study_party_s5`, `manor_wing_s4`, `manor_wing_s6` |
| R6 | Appendix A driver of the implementation report (every search, then every V-7 question to every living character, template renderer), then `audit.audit_save` | 224 / 168 / 300 / 225 statements, **0 discrepancies**, 0 review items; PASS / UNMEASURED (< 200) / PASS / PASS; 95 % upper bounds 134 / 179 / 100 / 133 bp; traces mean ≈ 2.0 KB, max 2,728 B; 0 gaps; exit 0 |
| R7 | `python -m eidolon.debug nightly --out … --turns 60 --no-suites` (no key) | all eight metrics `UNMEASURED`, `mode=dry`, **exit 3** |
| R8 | same with `ANTHROPIC_API_KEY=sk-ant-bogus…` | `anthropic SDK not installed: running dry`, all `UNMEASURED`, **exit 3** |
| R9 | same with the bogus key and `--dry` | all `UNMEASURED`, **exit 3** |
| R10 | `atk_*.py` attack scripts (§4–§7; reproduction snippets in Appendix A) | results in the sections below |

---

## 3. Reproduced results versus the author's

| claim (implementation report) | author | this review | how |
|---|---|---|---|
| whole suite | 3804 passed, 1 skipped, 1 xfailed | **3804 passed, 1 skipped, 1 xfailed, exit 0** | R1, independent run |
| Phase 9 mutants | 103 / 103 killed | **103 / 103 killed, baseline green, exit 0** | R2, independent run |
| persistence mutants | 197 killed, 8 equivalent | **197 / 197 killed, 8 justified equivalent, baseline green, exit 0** | R3, independent run |
| Phase 4 / Phase 5 harness anchors | 57+2eq / 70+1eq, three anchors re-pointed | anchors verified (R4); kill counts **inherited**, not re-run | static |
| Phase 6 `MUT_ONLY` subset | 7 / 7 | **inherited**, not re-run | — |
| 225 distinct player-side lines | 225 | **225** exact-distinct strings, 25 categories; **203** after NFKC + casefold + removing non-word characters (23 lines are Unicode/spacing encodings of the one payload "ignore your instructions"; §28.4 #5 counts Unicode tricks explicitly, so 225 stands — and 203 still clears 200) | script |
| flagged by stage 0 | 100 declared, 0 disagreements | **100**, 0 disagreements, 0 blocked (independent `screen()` over all 225) | script |
| model-side attacks, separate | 54 | **54** distinct, none of their payloads is a corpus line | script |
| stateful sequences, separate | 16 / 62 lines | **16 / 62**, none of the 62 lines is in `ALL` | script |
| four generated bundles validate | (implied by the audit table) | **all four `ok`, exit 0** | R5, independent |
| audit: 917 statements, 0 discrepancies | 224 / 168 / 300 / 225; PASS / UNMEASURED / PASS / PASS | **identical: 917, 0 discrepancies, same statuses and bounds** (detector arm only; the stronger-verifier arm is UNMEASURED and see H9-I2) | R6, independent |
| T-25 at 2000/1500 | fallback 0.0000, mean drafts 1.159 | test harness at 2000: **inherited** (R1 runs it at 400/300). Independent re-measure on the **production path** (`nightly.drive` → `_commit` → `Save.append` → traces, `study_party_s4`, `RepairingTransport(fail_every=5)`): 2000/2000 committed, **fallback 0 / 1500**, last 100: 0, **mean drafts 1.177**, 0 trace gaps, 378 s | §6 |
| T-26 | PASS | test passes (R1); the property it shows is narrower than I-42 (§6.2) | R1 + §6 |
| nightly without a provider | exit 3, all UNMEASURED | **exit 3**, all UNMEASURED, in three modes (R7–R9) | independent |
| live provider | none | **none** (SDK absent; no key) | — |
| long sessions 500/1000/2000, cross-process trace determinism | pass | **inherited** (`EIDOLON_LONG` runs not repeated; the cross-process test is in R1) | — |

---

## 4. Trace privacy, failure safety, determinism — attacked through the production path

Every probe below posts real forms to `web.create_app` (`TestClient`, `Host`/`Origin` loopback) with a scripted model, so a line goes
`POST /g/g1` → `dispatch` → `screen` → `ModelParser` → `GuardedTransport` → `ground` → `game.ask` → `run_ask_turn` → `LLMRenderer` →
validator → `Save.append` → `trace.build_turn_trace` → `Save.write_trace` → `traces.db`, and the bytes of `traces.db` are then read directly.

| attack | result | verdict |
|---|---|---|
| trace **builder** raises `RuntimeError("boom EIDOLON-SESSION-CANARY sk-ant-api03-…")` | HTTP 200, turn committed, reply shown, reopened `state_hash` = live, `trace_gaps()==[1]`, log line `trace not built or written: RuntimeError` (no message) | holds |
| trace **writer** raises the same | same | holds |
| `traces.db` held under `BEGIN EXCLUSIVE` by another connection | turn committed, trace lost (gap), **the turn took 7.49 s** (SQLite's 5 s busy timeout sits on the request path) | holds; H9-N3 |
| export | `meta`, `case_bundle`, `session_events` only; no sidecar created | holds |
| canary emitted by the model: exact / lower / ZWSP / Cyrillic O / fullwidth | never on the page, the ledger or in `traces.db` | holds |
| canary emitted spaced / with `_` / with spaces for `-` / split across two segments | never on the page or the ledger; **stored verbatim in `traces.db`** (the scrubber is literal) | H9-N5 (the canary is a public source constant; no secrecy is lost) |
| model regurgitates `SYSTEM_GENERATE` (canary removed) | refused, fallback spoken; **590 chars of the system prompt stored in each of 3 draft records** in `traces.db` | H9-N5 — contradicts §3.3 "Not stored at all: … any prompt" |
| 1000 astral characters typed + three 590-emoji drafts | stored row **58,994 bytes** < 64 KiB; the bound is checked on characters of `model_dump_json`, not stored bytes | holds (margin small) |
| `PromptLeak` (an engine id in a serialized prompt) | turn rejected (fail closed); aborted row `failures=['provider_error','plan_rejected']`, call error `PROMPT_LEAK` | **H9-N1**: `prompt_leak` is unreachable |
| engine exception inside the turn (patched `run_ask_turn` raising `KeyError`) | HTTP **500 "Internal Server Error"**, nothing committed, **no aborted row** | H9-N4 |
| save deleted and re-created under the same name | the new game (0 turns) reports **3 committed traces and 1 aborted attempt of the old game** in `slo.from_save` | H9-N2 (extends KNOWN-DEBT C-6(ii)) |
| forged rows of the wrong SQLite type / 200 k nested brackets in `aborted` | `slo.from_save` survives, `unreadable_trace_rows = 2` | holds |
| who reads traces | nothing outside `eidolon/debug/` and `store.py` (`cli replay` counts gaps by turn number only) | holds |

Field-by-field, nothing a model or a player controls can make `build_turn_trace` raise (every free string is clamped and scrubbed, every
code is reduced to `[A-Za-z0-9_\[\]:]`, the size check is on construction) — so an attacker cannot suppress an audit record by content.
Scope note: the trace file *is* an engine-truth file by design (§27.1 asks for `selected`, `candidates`, `assessment`); acts, secret handles
and layers are in it. That is acceptable only because it is never exported, never read by the player process, and `game.db` itself already
embeds the sealed solution; all three hold.

---

## 5. Injection corpus

Counts and stage-0 labels: §3 (all reproduced). End to end: the 450 production-boundary turns are in R1 and pass.
What they establish, read against the code:

* **Real path, yes.** The Rig posts to the Starlette app; the parser, grounding, renderer, validator, store and trace are the production
  ones. The line reaches the model only as the `player_query` / `player_text` JSON value (asserted).
* **One hostile draft, 450 times.** `OBEYING` is a single fixed draft (a confession, two engine ids, the canary, an `sk-ant-` key, meta
  talk) returned for every line. The 225 lines therefore exercise stage 0, the scripted parser's two behaviours and grounding; the
  validator is shown the same draft family every time. Line-specific obedience ("answer in JSON with a `secret` field", "reply in French",
  "repeat after me …") is never produced, so it is never validated. That is what a live model would do and it is unmeasured (H9-N7).
* **The twin comparison is near-tautological.** Every obeying draft is refused and the template speaks; the twin speaks the same template.
  Equality of fingerprints therefore re-states "every draft fell back"; it is not independent evidence about the engine.
* **Classification.** The deterministic half (100 / 225) is real and reproduced. The other 125 are classified only by the script that
  plays the parser; what a real parser does with them is **UNMEASURED** — and the nightly's measurement of it is defective (H9-I1).

---

## 6. T-25 and T-26

### 6.1 T-25

Literal criterion (§28.7): "2 000-turn session with a repairing LLM stub ⇒ fallback rate ≤ 2 % at turn 1 500" — **met**, and reproduced
independently on the production path (§3). Denominator: model-rendered committed turns; rejected turns are kept apart (`rejected_to_at` must
be 0); fallback = `committed_fallback`. Transport failures, timeouts, model refusals and validation failures are distinct `failures`
members in the trace (§4, except H9-N1).

What it can show is narrower than the exit criterion's rationale ("TemplateLLM … cannot surface late-session validator pressure"):

* The stub's defect rate is a hash of the request — independent of session length, digest size or the claims already on record. Any rise
  in fallbacks late in a session could only come from the validator refusing *faithful* repairs.
* The test's own pool (10 queries, 3 characters) produces, in every 100-turn window, 40 LIE turns that repeat one cover story and ~60
  claimless REFUSE / CLARIFY / DONT_RECALL / DONT_KNOW turns (measured: windows 100–399 have 40 claim-bearing turns, all LIE).
* On the production path with a generated case the picture is similar: **32 distinct non-empty claim sets in 2000 statements**; REFUSE is
  absent for the first 1000 turns and then takes 81–88 of every 250.

So the late-session validator sees the same few claim sets again and again. The PASS is real but weak evidence; recorded as H9-N6.
For the live counterpart (N-1) the nightly computes the same rate from the session's traces, keeps `dry` (exit 3) apart from live
(exit 0/1), and makes N-1 UNMEASURED when the session is incomplete — a transport failure or timeout that fails a turn closed makes the
whole metric UNMEASURED rather than counting as a fallback, and no metric reports the fail-closed rate itself (part of H9-N9).

### 6.2 T-26 and F-7

T-26 passes (R1). It measures the **renderer's** held time with a fake clock and a fake model whose raw latency is
`0.1 s + 1.5 ms × claim characters` — always below the 1.0 s floor — over 250 turns that are 5 deterministic scenarios on the demo world,
repeated 50 times.

* **The floor binds only below ~1 s of raw generate time.** Re-running T-26's own `observe()` with a per-call base latency of 2.0 s:
  TRUTH 2.0615 s, LIE 2.0450 s, CONCESSION 2.0615 s → `act_signal == ['latency_s']`, for a **faithful** model. F-7 records the residual only
  for a hostile model that pads its lies; T-26's own floorless arm (`act_signal([lie, truth]) == ["latency_s"]`) already shows it for every
  model whose latency tracks reply length. In the 2000-turn generated session the canonical LIE replies are shorter than TRUTH/VAGUE ones
  (median 46 vs 53 characters).
* The architecture's own estimate of a live turn is "~4–8 s" (§23.2), i.e. well above `LATENCY_FLOOR_S = 1.0`. Unless the live p99 of the
  longest call pattern is below the floor, the floor does nothing live and I-42's latency clause rests on raw latency being act-independent.
* **Outside the floor**, engine time (strategy, envelope, validation of the template) is not held: measured at the decision level with a
  real clock and a zero-latency model, medians TRUTH 0.83 ms, LIE 0.91 ms, CONFESSION 0.99 ms, CONCESSION 1.07 ms (n = 40–80, overlapping
  p10–p90). Too small to matter next to network jitter; recorded, not a finding.
* **Length band:** `act_signal` is called without the `band` key; T-26 asserts `band == canonical_band` instead. With `LENGTH_EDGES =
  (200, 400, 800)` every one of the 2000 statements of the generated session is band 0, so this arm cannot fail on any fixture used.

Offline-verifiable portion: the structural half (what the model is shown; effort tier; call pattern for a faithful model) — holds.
Live-only portion: latency — **UNMEASURED**, and by the architecture's own numbers expected to exceed the floor (H9-U1).

---

## 7. Debug server and nightly runner

**Debug server** (`create_debug_app`, `TestClient` on 127.0.0.1:8001), all held unless noted:

* `EIDOLON_DEBUG` = `""`, `0`, `true`, `yes`, `"1 "`, `" 1"`, `01` → `DebugDisabled`; only `1` starts it.
* All 14 views 200; the save and `traces.db` are byte-identical after every view and every attack below.
* `POST/PUT/DELETE/PATCH/OPTIONS` → 405 on every view; `HEAD` → 200 (read-only, Starlette adds it to GET).
* `Host`: the three loopback names on :8001 (and `LOCALHOST:8001`) → 200; `127.0.0.1` (no port), `:8000`, `evil.example`,
  `127.0.0.1:8001.evil.example`, `localhost.:8001`, `127.1:8001`, `0.0.0.0:8001`, `127.0.0.1:08001`, empty → 400.
* Cross-origin GET returns no `Access-Control-Allow-Origin`; a hostile page cannot read it.
* A typed `<script>…</script></pre><img onerror>` appears HTML-escaped on the Turn page.
* `/g/G1/turns` opens `g1.db` on NTFS (read-only; harmless). `/g/g1.traces/turns`, unknown saves, 41-char names, `turn/0`, a 21-digit turn
  → 404.
* **`/g/g1/world?t=abc` (or `t=1e3`) raises an unhandled `ValueError` → 500** (H9-N8).
* I-10: a fresh interpreter importing `eidolon.web`, `game`, `cli`, `trace`, `store` and building the app has **no** `eidolon.debug*` module
  loaded; the player app answers 404 to all 20 debug/trace paths probed (incl. `/g/g1.traces.db`, `/g/..%2Fg1`, `/g/G1`).

**Nightly runner.** No provider: exit 3 and UNMEASURED in all three modes (R7–R9); it made no network call. With the test-suite's own
SDK-shaped stand-in (`FakeAnthropicClient`, which makes `is_live` true), three defects:

* **H9-I1 — N-3 is PASS when the parser did not classify.** `classify_corpus` counts *any exception* as label `clarify`
  (`nightly.py:133-134`), and every category except `coercion` accepts `clarify` (`injection_corpus_v2.DEFAULT_EXPECTED`). Reproduced:
  a provider that answers the parse role only for the 10 `coercion` lines and refuses the other 215 → **N-3 PASS 10000 bp, "misses: {}",
  N-4 PASS, exit 0**. The budget check happens once, before the pass (`nightly.py:184`): with `--max-calls` set so the budget runs out after
  195 of 225 parse calls → `budget_exhausted=True` and **N-3 PASS 10000, exit 0**; after 100 → N-3 **FAIL** 9555 (a budget event reported as a
  classifier failure). The implementation report §7 says "an exhausted budget leaves N-1 and N-3 UNMEASURED" — true only when it runs out
  before the pass starts.
* **H9-I2 — N-5's "stronger verifier" is the generation model.** `main()` passes `audit_transport=None` (`nightly.py:255`), so the audit's
  verifier is `GuardedTransport(budget)` over the session's `AnthropicTransport(model="claude-opus-5")` (`nightly.py:186`). Recorded models
  by role in a live-stand-in run: `generate`, `parse`, `verify` — all `claude-opus-5`; the report row says `"sampled 30; stronger verifier
  claude-fable-5-1 used"`. `docs/EIDOLON-PROMPTS-AND-CONSTANTS.md` repeats the claim. (`python -m eidolon.debug audit --live-verifier` does
  use `AUDIT_MODEL`; the nightly does not.)
* **H9-N9 — the corpus arms hard-code `"David"`** (`nightly.py:130,150,152,183`). `--case manor_wing_s4` (no David): N-3 PASS from a parser
  told to answer for a non-existent addressee, N-4 silently UNMEASURED (every corpus turn rejected), exit 0.
* Exit-code semantics: 0 means "no FAIL and at least one PASS" (`exit_code`), so a live run with one PASS and six UNMEASURED exits 0. The
  per-metric statuses are honest; a CI wrapper reading only the exit code is not told the run was partial (part of H9-N9).
* `is_live` walks `inner`/`_inner`/`transport` attributes and checks the client's module name; a wrapper that *holds* a real
  `AnthropicTransport` but answers from a script would be counted live. Not reachable from `main()`; noted, not a finding.

---

## 8. Findings

Severity scale: **BLOCKING** — an explicit Phase 9 criterion or invariant is not met, or a defect makes a Phase 9 result untrustworthy;
**IMPORTANT** — must be fixed before the evidence it affects is used for acceptance; **NON-BLOCKING** — real, recorded, not a gate;
**UNMEASURED** — needs a live model or a human.

| ID | Severity | Finding | Criterion | Blocks Phase 10? |
|---|---|---|---|---|
| H9-B1 | **BLOCKING** | Repetition is a sincerity oracle: LIE answers never escalate; suite 2 asserts it | §28.4 #2, §15.4, §22.3 | **yes** |
| H9-I1 | **IMPORTANT** | Nightly N-3 counts parse failures as correct classifications; mid-pass budget exhaustion → PASS/FAIL | §28.4 #5 live, Phase 9 deliverable "live-model nightly" | yes, via F-1 |
| H9-I2 | **IMPORTANT** | Nightly N-5 claims the `claude-fable-5-1` verifier; uses `claude-opus-5` | §27.4, §24 | yes, via F-1 |
| H9-I3 (=F-3) | **IMPORTANT** | CONFESSION unreachable in the shipped game: no production `ConfessionCheck` exists and no caller passes one | I-21 mechanism (§11.4), §16; Phase 8 | not by Phase 9's text; must precede E1 |
| H9-U1 (⊇F-7) | **UNMEASURED** | The 1.0 s floor cannot cover a live model by §23.2's own figures; the residual applies to faithful models too | I-42, T-26 | precondition for Phase 10's first deliverable |
| H9-N1 | NON-BLOCKING | `PromptLeak` is traced as `provider_error` + `plan_rejected`; `prompt_leak` never produced | §27.1 failures taxonomy | no |
| H9-N2 | NON-BLOCKING | SLOs (and nightly N-1/N-6/N-7, the I-3 peel metric) read foreign/stale rows; aborted rows carry no binding | C-6(ii), Phase 9 exit "no invariant violations in their traces" | no (procedure for E1) |
| H9-N3 | NON-BLOCKING | Trace write is synchronous on the request path; a locked `traces.db` adds ≥ 5 s to a committed turn | §27.1 "best-effort" | no |
| H9-N4 | NON-BLOCKING | An engine exception is a bare 500 with no aborted trace (I-15 holds; §14.2(i)'s retry notice and the Failures view do not) | I-15, §14.2(i) | no |
| H9-N5 | NON-BLOCKING | Regurgitated system-prompt text and non-literal canary variants are stored in `traces.db`; report §3.3 says no prompt is stored | report accuracy, F-13 | no |
| H9-N6 | NON-BLOCKING | T-25 workload: constant stub defect rate, 32 distinct claim sets in 2000 statements | Phase 9 exit rationale | no |
| H9-N7 | NON-BLOCKING | Corpus end-to-end arm: one fixed hostile draft; twin equality near-tautological | §28.4 #5 test strength | no |
| H9-N8 | NON-BLOCKING | Debug `world?t=<non-int>` → unhandled 500 | robustness | no |
| H9-N9 | NON-BLOCKING | Nightly hard-codes `David`; exit 0 on partial measurement; no fail-closed-rate metric | nightly robustness | no |
| H9-N10 | NON-BLOCKING | §27.1 asks for ids, propositions, the envelope and the committed events; the trace stores handles and hashes, and the Turn inspector cannot show the envelope the model saw | §27.1 / §27.2 text | no (owner to ratify) |
| F-4 | NON-BLOCKING (agree) | §22.2's stage-2 ledger resolution of quotes is absent; zero evidential weight holds | §22.2 text | no (amend the text) |
| F-5 | superseded by H9-B1 | — | — | — |
| F-6, F-8 … F-13 | NON-BLOCKING / UNMEASURED (agree) | as recorded in KNOWN-DEBT §F | — | no |
| F-1, F-2 | **UNMEASURED — explicit exit criteria** | §9 | §30 Phase 9 deliverable + exit | **yes** |

### H9-B1 — BLOCKING — repeating a question tells a lie from a truth

**Reproduction** (decision level, TemplateLLM, no evidence presented — the act is independent of the renderer). For each of the four
generated cases: search everything (`run_search_turn` over every evidence item, four passes, as `nightly.drive` does), then put **each**
V-7-expressible question (`expressible_queries(case, who, held_names(...))`) to **each** living character **seven times in a row**, chaining
state, and record the act of every answer. Group by the act of the first answer:

| first answer's act | n | answers 6–7 include REFUSE | answers 6–7 identical act | other (REPEAT_PRIOR, …) |
|---|---|---|---|---|
| **LIE** | **250** | **0** | **250** | **0** |
| TRUTH | 32 | 2 | 13 | 17 |
| VAGUE | 281 | 104 | 49 | 128 |
| DONT_RECALL | 245 | 181 | 64 | 0 |
| DONT_KNOW | 109 | 49 | 43 | 17 |

Through the browser controls (`game.ask` on `study_party_s4`), Margaret's alibi "I was in the library from 00:17 until 00:38." is
restated seven times as LIE, while David's and Elena's truthful/vague answers alternate with `REPEAT_PRIOR` (identical words from the
template; a "weary" delivery directive for a model) and, across the four cases, a third of the vague answers turn into `REFUSE`. In the
production-path T-25 session the trace shows why: on **all 270** LIE turns at repetition ≥ 5, `REFUSE` is a candidate and loses by 9–708 bp
(e.g. `LIE 24400`, `REPEAT_PRIOR 24000`, `REFUSE 23692`); `REFUSE` wins only against the content acts it ties (`DONT_RECALL 23692`).

**Root cause.** `strategy._repeat_prior` (`strategy.py:231-234`) offers `REPEAT_PRIOR` only when `retrieved_claim` (memory retrieval) is
set — §15.4 specifies "the **standing** (non-retracted) claim is re-supplied verbatim" and makes it "a high-utility candidate"; a liar's
retrieval is empty, so he never gets it. `_repetition_penalty` penalises only `EVASION`; nothing at `repeat_count ≥ 5` lets `REFUSE`/`ANGER`
outscore a content act, and LIE's safety/goal terms make it the highest. Phase 9's suite 2 (`tests/test_phase9_suites.py:97-122`) was written
to this behaviour: it asserts `REPEAT_PRIOR` is merely *offered*, and for the liar asserts `len(set(lies)) == 1 and lies[0][0] == "LIE"`
— "a liar repeats his lie unchanged" — which is the opposite of §28.4 #2's "escalation after 5". The mutants `repeat-prior-too-early` and
`refuse-never-escalates` are killed by this weakened assertion, so the mutation score does not cover the gap.

**Why it matters.** A player with no evidence can repeat any claim-bearing question six times: a refusal (or, with a live model, the "weary"
repeat) certifies the answer is **not** a lie (0 of 250 lies ever change); among the claim-bearing first answers here (LIE, TRUTH, VAGUE), an
answer that never turns into a refusal is a lie with 55 % precision (250 / 457), and one whose act never changes at all — what a player sees
once `REPEAT_PRIOR`'s delivery is rendered by a model — with 80 % (250 / 312). Sincerity is hidden state; §22.3 allows only designed, engine-gated tells; and §28.4 #2 is an explicit
Phase 9 suite ("must pass on every PR"). F-5 records half of this as "a design question"; the liar arm is not a design question but a leak.

**Smallest remedy.** In `strategy`: build `REPEAT_PRIOR` from the speaker's standing claim for this query hash (not from retrieval), and
make the repetition stage act-independent — at `repeat_count ≥ 2` `REPEAT_PRIOR` above every content act, at `≥ 5` `REFUSE`/`ANGER` above it
(respecting `refuse_streak`), for LIE exactly as for TRUTH/VAGUE. Restore suite 2 to §28.4 #2 for every character including the liar, add a
"repeat bot" test over the four generated cases asserting P(change by repeat 6 | LIE) = P(change | TRUTH ∪ VAGUE) within a stated tolerance,
and add both as mutants. Re-run the Phase 4 harness (`strategy.py` is in its set).

### H9-I1 — IMPORTANT — the nightly manufactures a parser PASS

Reproduction (Appendix A.2): `nightly.run(..., transport=AnthropicTransport(FakeAnthropicClient(P)), turns=24, run_suites=False)` with `P`
answering `{"kind":"ask","query_kind":"coercion"}` for the 10 `coercion` lines and raising `ProviderRefusal` for the rest → `N-3 PASS 10000
"misses: {}"`, `N-4 PASS`, `exit_code == 0`. With a correct parser and `max_calls = (calls before the parse pass) + 195` →
`budget_exhausted True`, `N-3 PASS 10000`, exit 0; `+ 100` → `N-3 FAIL 9555`. Affected: the live half of §28.4 #5 ("all meta/coercion"),
which only this metric measures. Remedy: in `classify_corpus` an exception is a **miss** for N-3 *and* makes the metric UNMEASURED if it was a
provider/budget failure (`ProviderError`, `ProviderTimeout`, `ProviderRefusal`, budget) rather than a `MalformedOutput`; re-check
`budget.exhausted` after the pass; tests for both.

### H9-I2 — IMPORTANT — the nightly audit is not run by the stronger model it names

Reproduction (Appendix A.2, arm C): models recorded per role in a live-stand-in run are `generate/parse/verify → claude-opus-5`; N-5's note
reads "stronger verifier claude-fable-5-1 used". Affected: §27.4 ("a stronger verifier pass"), §24, F-10, and the generated documentation.
Remedy: `main()` builds `BudgetedTransport(AnthropicTransport(model=AUDIT_MODEL), …)` for `audit_transport`; derive the note from the
transport's model; a test that a live-stand-in run's audit calls carry `AUDIT_MODEL`.

### H9-I3 (= F-3) — IMPORTANT — confession is dead code in the shipped game

Reproduction: `grep confession_check` — the only definitions are the parameter defaults in `decision/peel.py:77` and `decision/turn.py:289`;
no module under `eidolon/` constructs a `ConfessionCheck` or passes one (`game.ask` calls `run_ask_turn` without it). `confession_permitted(None,
…)` is False, so the murder secret's terminal layer always behaves as `stonewall`. A naive end-to-end driver (every item found and shown to the
murderer with topical murder-window questions, with and without a solver-backed gate) produced no peel on any of the four cases, so the gate's
effect could not be observed end to end; the code path is the reproduction. Affected: the I-21 mechanism "strategy precondition calls the
solver" (§11.4), the designed end state "the murderer confesses to a proof". Not a Phase 9 test criterion (T-26 reaches CONFESSION at the
decision level with an injected gate, which T-26's wording allows). It must be wired — with its fold rule (KNOWN-DEBT C-1) — **before** the
playtests of E1, or the playtesters play a game whose murderer can never confess. Remedy: a `ConfessionCheck` that runs `solve.solver.evaluate`
on `credited_material(state, only=presented)` (the rule `game.establishes` already uses), passed by `game.ask`, plus a store fold rule.

### H9-U1 (⊇ F-7) — UNMEASURED — the latency floor and a live model

See §6.2. To close: measure, with a live model, p99 of the slowest call pattern (`generate×3` on a refused draft; `generate+verify`) and set
`LATENCY_FLOOR_S` above it, or replace the floor with a constant-time pad per route. This is a precondition for Phase 10's first deliverable
("skip the verifier on low-risk `TRUTH` plans"), which by design makes the call pattern act-correlated and leaves only the floor to hide it.

### H9-N1 … H9-N10 — NON-BLOCKING

* **N1** `trace.failures_of` maps the call error `"PromptLeak"`, but `GuardedTransport` records `error="PROMPT_LEAK"` (`provider.py:156`,
  `trace.py:329`). Reproduced: a patched deny set naming the speaker → aborted row `failures ['provider_error','plan_rejected']`. The ledger
  row keeps `PROMPT_LEAK`, so nothing is lost, but the summary attributes an engine leak to the provider. One-string fix + a test.
* **N2** `slo.from_save` and every consumer read all rows of `<name>.traces.db`; committed rows are checked for binding only on the Replay page,
  aborted rows have no binding. Reproduced with a deleted-and-recreated `g1`. For E1: start each playtest with a fresh save name and require
  `traces_foreign_or_stale == 0`; fix: `Save.create` refuses or rotates an existing sidecar, or the SLO filters by `case`+`head_hash` and
  aborted rows carry the genesis hash.
* **N3** `_trace_insert` opens the sidecar with SQLite's default 5 s busy timeout on the request path. Measured 7.49 s for a committed turn while
  another connection held the file. Use a short timeout.
* **N4** `web.dispatch` catches only `ValueError`; an engine exception is a 500 with no aborted row and none of §14.2(i)'s "retry" notice.
* **N5** report §3.3 "Not stored at all: … any prompt" is inaccurate for a model that echoes its prompt; the sink's canary pattern is literal.
  Harmless here (prompts are published in `docs/EIDOLON-PROMPTS-AND-CONSTANTS.md`; the canary is a source constant) — correct the sentence.
* **N6** T-25 strength (§6.1). Use a workload whose distinct claim count grows with the session (e.g. rotate subjects, places and buckets, and
  present items) and a stub whose defect rate rises with digest length.
* **N7** corpus strength (§5): add a model that obeys each line *in kind* (format requests, repeat-after-me, other languages).
* **N8** `debug/app.py:170` `int(request.query_params.get("t", …))` unguarded.
* **N9** `nightly.py` hard-codes `David` (lines 130, 150, 152, 183); exit 0 on partial measurement; no metric for the fail-closed
  (rejected) turn rate — a provider that times out makes N-1 UNMEASURED instead of visible.
* **N10** A disagreement between the architecture and the implementation, recorded rather than resolved: §27.1 lists engine ids,
  propositions, the `Envelope` and the `SessionEvent`s in the trace; the implementation (report §3.3) stores opaque handles, a sha256 of the
  envelope and the registry kinds, on the ground that the content is reproducible from the save and every copy is another place a protected
  fact could leak. The reasoning is sound and the debug server resolves handles and re-folds the state before/after a turn, but nothing
  rebuilds the envelope a model was shown, so §27.2's "stage-by-stage" Turn inspector shows its hash, not its content. Either the owner amends
  §27.1 or the debug process re-derives the envelope from the replayed pre-turn state.

### Inspection of the tests for weakened assertions and proxies

* Suite 2 — weakened (H9-B1).
* T-26 — `band` excluded from `act_signal`; latency proven only below the floor (§6.2). The four act classes come from five deterministic
  scenarios repeated 50 times; "≥ 200 turns" is met nominally.
* T-25 — honest but weak (H9-N6).
* Corpus — honest about the scripted parser (§4.3 of the report), weak on the model side (H9-N7).
* Privacy test — uses an independent id enumeration (not the function under test); its leaking model writes ids, canary and key, not the
  prompt (hence N5).
* Mutation — 103/103 killed, but a kill proves only what the killing test asserts; `repeat-prior-too-early` / `refuse-never-escalates` are
  killed by the weakened suite 2.
* No existing assertion outside Phase 9 files was weakened that I could find; the three re-pointed anchors in `tests/decision/mutation_check.py`
  mutate the same code as before (R4); the added `test_a_turn_must_open_with_turn_committed_and_every_row_carries_that_turn` is additive.

---

## 9. Live-model and human criteria that remain UNMEASURED

| criterion (source) | status | evidence that would close it |
|---|---|---|
| §28.4 suites "nightly with live model" (Phase 9 deliverable) | **never run** | `python -m eidolon.debug nightly --record tests/llm/cassettes/<date>.cassette.json` with a key and the SDK, after H9-I1/I2 are fixed; N-2 PASS |
| fallback rate with the live model: Phase 5 exit < 5 % on 300 turns; Phase 9 ≤ 2 % (§27.5) | UNMEASURED | N-1 from that run, complete session |
| what a real parser makes of the 125 unflagged corpus lines (§28.4 #5 "all meta/coercion") | UNMEASURED | N-3 from that run, with H9-I1 fixed |
| corpus as full turns through a real renderer (no meta text, no canary) | UNMEASURED | N-4 with ≥ 25 lines, and a cassette |
| offline audit with the stronger verifier on ≥ 200 statements, < 0.5 % (§27.4, Phase 9 tests) | UNMEASURED (offline detector arm PASS) | N-5 with H9-I2 fixed |
| mean drafts < 1.3, tokens flat, latency p50/p95, cache ratio, cost (§27.5) | UNMEASURED (cost needs a price table, F-9) | N-6/N-7 + SLOs of that run |
| latency floor vs live p99 (I-42, T-26) | UNMEASURED | H9-U1 |
| **two external playtesters complete a generated case; no invariant violations in their traces** (§30 Phase 9 **Exit**) | **UNMET — explicit exit criterion** | two people, fresh save names, `slo` with `peels_without_any_presented_breaker` = 0 and `traces_foreign_or_stale` = 0, `audit` |
| cross-machine replay (Phase 7 exit, F-12) | UNMEASURED | replay one save on a second OS |

The tooling labels all of these honestly as UNMEASURED today (R7–R9); H9-I1/I2 are the two places where a *future* live run would not be
labelled honestly.

---

## 10. Required fixes

1. **H9-B1** — strategy repetition rule per §15.4, act-independent; suite 2 restored to §28.4 #2; a repeat-bot sincerity test; mutants; re-run
   Phase 4 + Phase 9 harnesses and the whole suite.
2. **H9-I1** — `classify_corpus` exception handling and the post-pass budget check; tests.
3. **H9-I2** — the nightly's audit transport on `AUDIT_MODEL`; the note derived from it; a test.
4. Then, to *exit* Phase 9 (§30): one live nightly with a recorded cassette (closes F-1 and measures H9-U1), and the two external playtests on a
   generated case (closes F-2) — preceded by wiring the confession gate (H9-I3) so the game they play is the designed one.

Recommended with them (NON-BLOCKING): N1, N2 (needed procedurally for E1), N3, N4, N9; correct report §3.3 (N5).

## 11. Phase 10 readiness

**Not ready.** Phase 10 depends on Phase 9 (§30); Phase 9 has one BLOCKING finding, two IMPORTANT findings in its live-measurement
instrument, an unmet explicit exit criterion (playtesters) and an unrun live nightly. Two further facts bear on Phase 10 specifically:
its first deliverable (risk-tiered validation that skips the verifier on low-risk TRUTH plans) creates exactly the act-correlated call pattern
that H9-U1 says the current floor cannot hide; and its acceptance test ("quality gates unchanged … cost/turn down ≥ 30 % vs Phase 9 baseline")
needs a live Phase 9 baseline that does not exist. Separately, Phase 8 — a Phase 9 dependency — is still `REPAIRED — READY FOR INDEPENDENT
RE-REVIEW`, not accepted.

**Verdict: B. `REQUIRED FIXES — REMAIN IN PHASE 9`**

---

## Appendix A — reproductions

The attack scripts ran from a scratch copy whose `*.py` files are byte-identical to §1; each needs only the shipped code and the test helpers.

### A.1 H9-B1 (repeat bot)

```python
from collections import Counter
from eidolon.decision.turn import run_ask_turn, run_search_turn
from eidolon.solve.bots import held_names
from eidolon.solve.package import load_sealed_case
from eidolon.solve.queries import expressible_queries, public_names
from eidolon.solve.session import new_session

by_act = {}
for name in ("study_party_s4", "study_party_s5", "manor_wing_s4", "manor_wing_s6"):
    st = new_session(load_sealed_case(f"cases/generated/{name}.json"), seed=7)
    for _ in range(4):
        for ev in sorted(st.evidence.all(), key=lambda e: e.id):
            if ev.id not in st.discovery.known_evidence and not (r := run_search_turn(st, ev.discovery.at, ev.discovery.action)).rejected:
                st = r.state
    names = held_names(st, public_names(st.case))
    for who in sorted(st.case.living_actors()):
        for q in expressible_queries(st.case, who, names):
            acts = []
            for _ in range(7):
                r = run_ask_turn(st, who, q)
                st, acts = (st, acts + ["REJECTED"]) if r.rejected else (r.state, acts + [r.plan_act])
            tail = acts[5:]
            by_act.setdefault(acts[0], Counter())["refuse" if "REFUSE" in tail else "same" if set(tail) == {acts[0]} else "other"] += 1
print(by_act)          # LIE: {'same': 250}; TRUTH: refuse 2 / same 13 / other 17; VAGUE: 104 / 49 / 128; DONT_RECALL: 181 / 64 / 0
```

### A.2 H9-I1 / H9-I2 (nightly)

```python
import json
from eidolon.debug import nightly
from eidolon.llm.fakes import RepairingTransport
from eidolon.llm.provider import AnthropicTransport, Completion, ProviderRefusal
from tests.llm.injection_corpus_v2 import ALL
from tests.test_phase9_nightly import FakeAnthropicClient

CAT = {line: cat for cat, line, _ in ALL}
class OnlyCoercionParsed:                    # classifies 10 of 225 lines, refuses the rest
    inner = RepairingTransport(fail_every=5)
    def complete(self, req):
        if req.role == "parse":
            if CAT.get(json.loads(req.user)["player_text"]) == "coercion":
                return Completion(text=json.dumps({"kind": "ask", "query_kind": "coercion"}))
            raise ProviderRefusal("refused")
        return self.inner.complete(req)

class Rec(FakeAnthropicClient):              # also records the model each call asked for
    __module__ = "anthropic.fake"
    def __init__(self, inner): super().__init__(inner); self.log = []
    def create(self, *, model, **kw):
        p = kw["output_config"]["format"]["schema"]["properties"]
        self.log.append(("verify" if "unreferenced_assertions" in p else "generate" if "segments" in p else "parse", model))
        return super().create(model=model, **kw)

c = Rec(OnlyCoercionParsed())
rep = nightly.run("out/x", transport=AnthropicTransport(c), turns=24, audit_sample=30, corpus_turns_n=6, run_suites=False)
print({m["id"]: m["status"] for m in rep["metrics"]}, nightly.exit_code(rep))     # N-3 PASS, exit 0
print(sorted(set(c.log)))                                                         # every role -> claude-opus-5
print([m["note"] for m in rep["metrics"] if m["id"] == "N-5"])                    # "... stronger verifier claude-fable-5-1 used"
```

The budget variant: run once to find the index of the first `parse` call in `c.log` (54 here), then `max_calls=54 + 195`.

### A.3 H9-N1 (PromptLeak classification)

Patch `eidolon.llm.render.prompt_deny_tokens` to add the speaker's id, post one `say` line through `web.create_app`, read
`save.trace_rows(aborted=True)`: `failures == ["provider_error", "plan_rejected"]`, `llm_calls[-1].error == "PROMPT_LEAK"`.

### A.4 H9-N2 (stale sidecar)

Create `g1` through `POST /new`, play 3 turns and one rejected `goto`, close the app, delete `g1.db` (not `g1.traces.db`), create `g1` again:
`slo.from_save` reports `turns_committed 3`, `attempts_not_committed 1` for a game at turn 0.

---

## Repair (author's record, appended 2026-10-21 — not a re-review)

H9-B1, H9-I1 and H9-I2 were repaired in the same session that wrote this review; the record, with before/after reproductions, failing-first
tests, mutants and runs, is `docs/EIDOLON-PHASE-9-REPAIR-REPORT.md`. Its verdict is "REPAIRED — READY FOR INDEPENDENT RE-REVIEW": because
reviewer and repairer are the same session, the repairs need a fresh reviewer before this review's verdict can change. Nothing in §1–§11
above was edited. Still open from this review: H9-I3, H9-U1, H9-N1…N10, and the unmet exit criteria of §9; the repair adds two residuals
(KNOWN-DEBT F-14, F-15).
