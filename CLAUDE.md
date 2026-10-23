# EIDOLON — project state

Simulation-driven murder-mystery engine. The simulation is the sole source of truth; the LLM
is a renderer (§2.1). Read `docs/EIDOLON-ARCHITECTURE.md` before changing anything — it is the
specification, and its invariant table (§2.2, I-1…I-58) and its ADRs (to ADR-31) are the contract.

## Where the project is

| Phase | State |
|---|---|
| 0.5 — feasibility gate | **PASSED** 2026-09-03 (`docs/EIDOLON-PHASE-0.5-REPORT.md`) |
| 1 — canonical world (`eidolon/world/`) | complete |
| 2 — minds (`eidolon/minds/`) | complete |
| 3 — evidence & discovery (`eidolon/evidence/`) | complete, hostile-audited, **all 16 findings repaired** |
| 4 — conversation / decision engine (`eidolon/decision/`) | **implemented** (`docs/EIDOLON-PHASE-4-REPORT.md`), hostile-audited, **all 6 blockers and the 4 Phase-5-readiness findings repaired** (`docs/EIDOLON-PHASE-4-REPAIR-REPORT.md`); 17 IMPORTANT open; **Phase 5 ready** — scoped: TemplateLLM only, no real LLM/persistence/UI |
| 5 — LLM integration + validation (`eidolon/llm/`) | **implemented** (`docs/EIDOLON-PHASE-5-REPORT.md`): stage-0 screening, parser schema + grounding, typed rendering view, provider boundary (`AnthropicTransport`), strict wire parsing, LLM verifier, bounded repair → deterministic fallback, fail-closed, player projection; hostile-audited, **all 3 BLOCKING and all 10 IMPORTANT findings repaired** (`docs/EIDOLON-PHASE-5-REPAIR-REPORT.md`) — guarded by `test_llm_blocking_repairs.py` (47), `test_llm_important_repairs.py` (50), the 112-prompt injection corpus (875) and mutants `P5-46…62a`; 4 NON-BLOCKING open. **Not yet run against a live model** (no network/key here): the live-model exit criteria (fallback rate < 5 % on 300 turns) are unmeasured. 4 phases remain after 6 (7 persistence, 8 player UI, 9 hardening, 10 optimization) |
| 6 — case generation + solver (`eidolon/gen/`, `eidolon/solve/`) | **implemented, blocker re-audit repaired** (`docs/EIDOLON-PHASE-6-RB-REPORT.md`): RB-3 independent proof verifier (`proof/2`, `solve/proof_material.py`, sealed `SealedCase` bundle, `load_sealed_case`), RB-1 shared account identity + delivery-only hearing (`minds/accounts.py`, ADR-23/24), RB-2 engine-faithful interrogation + V-7 (footprint topicality, `speakable`, argmax retrieval, ledger-credit bots, engine-driven V-4; ADR-25…29). Goldens regenerated at full V-7 scale. Seed study 2×50, one attempt per seed, full scale: first run 75/100 under the real gates; after the cluster repairs (planner hk-secret/cleaning-bucket clearance, no pin on herring targets, `name_places` boosts) **99/100 sealed, all in band** (manor_wing 49/50, study_party 50/50; the one rejection, manor_wing 45, is a genuinely non-robust case). Open: D-1, the earlier IMPORTANT/NON-BLOCKING lists |
| 7 — persistence (`eidolon/store.py`) | **PHASE 7 ACCEPTED — READY FOR PHASE 8** (closure gate 2026-10-19, `docs/EIDOLON-PHASE-7-RE-REVIEW.md` Part II; FINAL frozen tree manifest `20899f0d…`, `store.py` `aedb1c39…`): 263 persistence + 2364 other tests, 125 mutants killed / 0 survived / 5 equivalent, 500/1000/2000-turn sessions — all exit 0 on that tree. R-1, F-1 (unbounded `interval`/`t` slots, bound `[0, t_investigation]` inclusive), N-3, X45/X46 repaired and each checked by a fresh-context reviewer (`docs/EIDOLON-PHASE-7-R1-INDEPENDENT-REVIEW.md`: 194 + 1,194 attacks, 0 false refusals in 20,254 genuine turns, no BLOCKING/IMPORTANT open). That reviewer is a subagent launched by the repairing session, not a human or separate team. (History: reviewed B 2026-10-17, repaired, re-reviewed A on the older tree 2026-10-18, closure + F-1 fix 2026-10-19.) Debt in `docs/EIDOLON-KNOWN-DEBT.md` §C): SQLite `game.db` + `.traces.db`, full-row hash chain whose genesis binds case seal + seed + schema version + a digest of the DERIVED initial world (an engine that derives something else refuses the save), head-pinned tail (seq AND hash), closed event registry, canonical-text + float-free payloads (two bp-grid exceptions), ONE validating fold (`fold_turn`: turn shape, voiced peels, own-statement retractions, speaker-owned grounding, resolvable references, `check_state` every turn) run identically at append and load, embedded sealed bundle re-verified on every load incl. declared solution == proven survivor (`load_sealed_text`), duplicate `action_id` returns its turn (`TurnRef`), safe recovery (`plan_truncation` dry run / `truncate_to_last_valid(confirm=True)`, verified inside its own transaction), `eidolon replay`/`newsave`. All 1 BLOCKING + 7 IMPORTANT review findings repaired. Old-schema saves are read-only until a migrator exists. The fold also resolves nested references and binds epistemic/incidental rows to the addressee (R-1); a hot journal is refused, not rolled back. Open: C-1 (a re-chained forger can still inject a *structurally valid* unjustified peel / fabricated confession), C-4…C-7, C-10…C-12 (PN-1/3/4/5/6/8/10), re-review N-1/N-2/N-4/N-5/N-7, F-2…F-9 (NON-BLOCKING), cross-machine replay unmeasured. F1-a (no mutant for the lower bound of `Moved.t`/`Said.t` — add with the next `store.py` change). Phase 8 producers of `HypothesisChanged`/`CaseSolved`/`contradictions_caught` must add their own fold rules (KNOWN-DEBT C-1, C-2) |
| 8 — player interface (`eidolon/game.py`, `eidolon/web.py`) | **independent hostile review: NOT ACCEPTED (2026-10-20; `docs/EIDOLON-PHASE-8-HOSTILE-REVIEW.md`: 1 BLOCKING H8-B1, 3 IMPORTANT H8-I1/I2/I3, 9 NON-BLOCKING); H8-B1, H8-I1, H8-I2 and H8-I3 REPAIRED 2026-10-21 — READY FOR INDEPENDENT RE-REVIEW** (`docs/EIDOLON-PHASE-8-REPAIR-REPORT.md`, author's record, not yet re-reviewed; Phase 8 is **not accepted**). The repair: the hypothesis board, the tension list and the form vocabulary read only the implications the player has UNLOCKED (`evidence.discovery.held_material` / `unlocked_view`, `game.player_objects`); a refused search names no evidence / statement / account / kit id (`exploration._hint`); the app answers only the loopback names on the served port (`web.allowed_hosts`, a Host middleware, `Origin` checked against it, not against `Host`); a save opens only under its on-disk spelling and `game._commit` honours the store's `AppendResult` (H8-I3). Open: the review's H8-N1..N9, H8-X2, H8-N10 and the repair's own R-1..R-7 (KNOWN-DEBT §E). Phase 8 as first implemented (`docs/EIDOLON-PHASE-8-IMPLEMENTATION-REPORT.md`; author's record): browser app (`eidolon serve`, 127.0.0.1 only; Starlette + autoescaped Jinja2, plain form posts — FastAPI/HTMX not used, KNOWN-DEBT D-2), structured question / show / accuse-to-their-face / go / search / theory / final-accusation controls, free text through the Phase 5 parser + renderer with `eidolon serve --llm`, notebook (heard statements, found items by opaque handle, tensions between HELD items only, live theory status), map, session management, case report after the verdict (five axes; answer read from the CaseLog + the proof's verified survivor, N-7; evidence axis = solver on the CITED set, so an alternative proof earns credit). Every control commits ONLY via `game._commit` → `Save.append`; a re-sent form returns its committed turn, an old page commits nothing, a cross-site POST is refused. New producers: `Accusation` (provisional in `run_ask_turn`, final in `run_accusation_turn`), `HypothesisChanged` (`run_hypothesis_turn`; withdraw = status `withdrawn`), `CaseSolved` (`correct` = who axis vs `GameState.murderer`, the sealed proof's unique survivor). New fold rules (append AND load, `P8_*` forgeries): no row/turn after `CaseSolved` (PN-10 resolved), verdict derived not trusted, accusation turn shapes, citations held-only, F-3 for theories, `Lied` names its statement's own speaker; F1-a mutant added. N-6: no new float (board offers `At`/`Lied`/`Planted`; motive is a skeleton-vocabulary string). Exit measured on `study_party_s4` over HTTP (`vance_v03` has no sealed bundle, D-7). Not built (out of §30 scope): producers of `IncidentalPinned`/`KnowledgeAdded`/overlay/trust/suspicion kinds, `contradictions_caught` (no producer: every id refused). Open: KNOWN-DEBT §D (D-1 free text wired but never run against a live model, D-2…D-9) |
| 9 — observability, injection corpus, live-model validation (`eidolon/trace.py`, `eidolon/debug/`, `tests/test_phase9_*.py`) | **independent hostile review 2026-10-21: B. REQUIRED FIXES — REMAIN IN PHASE 9** (`docs/EIDOLON-PHASE-9-HOSTILE-REVIEW.md`: H9-B1 BLOCKING — repeating a question told a LIE from a TRUTH; H9-I1/I2 IMPORTANT — the nightly counted failed parses as classifications and audited on the wrong model; H9-I3 = F-3; H9-U1 latency floor vs live p99; N1–N10). **H9-B1, H9-I1, H9-I2 REPAIRED 2026-10-21 — READY FOR INDEPENDENT RE-REVIEW** → **independent re-review 2026-10-22** (`docs/EIDOLON-PHASE-9-REPAIR-RE-REVIEW.md`): H9-I2 closed, H9-I1 closed for N-3, **H9-B1 NOT closed** (RR-B1: any inert shown item switched the §15.4 escalation off — the gate is now `presented_ref is None or no authored DENY_EVIDENCE/REINTERPRET in play`) and RR-I1 (N-4/N-6/N-7 judged on what the provider left); **both repaired 2026-10-22 by the re-reviewing session — READY FOR INDEPENDENT RE-REVIEW** (`docs/EIDOLON-PHASE-9-RR-REPAIR-REPORT.md`, tree `98f91bb4…`) (`docs/EIDOLON-PHASE-9-REPAIR-REPORT.md`; same session as the review, so not independent): `REPEAT_PRIOR` re-supplies the standing answer and, with `REFUSE`, outranks every content act from the 3rd/6th identical question when nothing is shown (§15.4) — suite 2 now asserts §28.4 #2 for the liar too; the nightly's unanswered parse lines and budget cuts are UNMEASURED, its audit runs on `claude-fable-5-1`; the constants doc no longer skips tuple-assigned constants. Phase 9 is **not accepted**: exit criteria (two external playtesters, live nightly) unmet; H9-I3, H9-U1, N1–N10 and residuals F-14/F-15 open. As first implemented: **implemented 2026-10-21 — READY FOR INDEPENDENT REVIEW** (`docs/EIDOLON-PHASE-9-IMPLEMENTATION-REPORT.md`; author's record, not independently reviewed; Phase 8 is still not independently accepted; Phase 10 not started). Built: a typed, bounded `TurnTrace` (§27.1) produced by `game._commit` AFTER the commit, best-effort, in `<save>.traces.db` (engine ids become opaque handles, content becomes hashes and counts, text is scrubbed of the canary/credentials/ids; never exported, never read by the player process, deletable without effect on replay; rejected/clarify/blocked attempts go to an `aborted` table); the 225-line player-side injection corpus (`tests/llm/injection_corpus_v2.py`, 16 stateful sequences separate, the 54 model-side attacks separate) run through HTTP → parser → renderer → validator → store against a no-model twin; the §28.4 suites (`make_renderer()`: fake on a PR, live with `EIDOLON_LIVE=1`); T-25 (2000 turns, repairing stub, fallback 0.0000 at turn 1500) and T-26; the offline audit, SLOs, debug server (`python -m eidolon.debug serve|trace|slo|audit|nightly|promptdoc`, `EIDOLON_DEBUG=1`, GET-only, its own port) and the generated `docs/EIDOLON-PROMPTS-AND-CONSTANTS.md` (a test fails if it is stale). **Every live-model figure is UNMEASURED** (no key, no network, no SDK here; the nightly job prints PASS/FAIL only for a real `anthropic` client) and the two external playtesters are not done (`docs/EIDOLON-KNOWN-DEBT.md` §F, F-1/F-2). Notable: CONFESSION is unreachable in a browser game (F-3). Mutation: 103 Phase 9 mutants all killed; the persistence harness's earlier-phase survivor was closed with a new test. |

**Phase 4 is implemented**, on the `TemplateLLM` path (§28.2) — no real model call, no
persistence, no player UI. `Statement`/`Claim`/`ResponsePlan`/`Secret`/`CoverStory`/
`LayerPeel`/the hypothesis board/a scoped `solver.unique()`/a CLI all exist under
`eidolon/decision/`. See `docs/EIDOLON-PHASE-4-REPORT.md` for exact scope, invariants
enforced, and what is explicitly deferred to Phase 5/6/7/8 (the real solver, case generation,
`AnthropicLLM`, persistence, the player-facing UI).

## ADR-30 (2026-10-22): a lie answers only its own topic

`decision/footprint.py` `on_topic`: a LIE needs a covering deceptive claim of the question's topic (`predicate_hint` → `TOPIC_OF_HINT`
→ `TOPIC_KINDS`; one map shared with memory retrieval). No topic / unknown hint = unrestricted (bluff parity). Report:
`docs/EIDOLON-ADR-30-REPORT.md` (V-7 all ok, bluff identical, seed study 99/100 in band, goldens' seals unchanged). Also: per-character
voices (`solve.session.default_voice`), typed times → windows (`ingress.clock_interval`), "you" = addressee, tone-keyed claimless
lines (`decision.llm.CLAIMLESS_LINES`), widened `_NON_ENTITY_WORDS`. Author's record, not independently reviewed.

## Free model providers (play and development only)

`eidolon serve --provider gemini|groq|github|openrouter|ollama [--model M]`, `eidolon play --provider …` and `python -m eidolon.debug nightly
--provider …` run the real parse/render/verify pipeline against a free OpenAI-compatible endpoint (`llm.provider.OpenAICompatTransport`,
stdlib HTTP; keys only from `GEMINI_API_KEY` / `GROQ_API_KEY` / `GITHUB_MODELS_TOKEN` / `OPENROUTER_API_KEY`; Ollama needs none). Same leak guard, strict parsing and fail-closed
fallback. **ADR-31 (owner decision, 2026-10-22): a free-tier model on the real network path is a live measurement** — the nightly
judges PASS/FAIL, names the provider and model, audits on the provider's stronger free model and paces calls for the free tier
(`--rpm`, `llm.provider.Paced`, measurement runs only). F-1 is closed by one such recorded run. Guarded by `tests/llm/test_free_providers.py` (23).

## Full review and fixes (2026-10-22)

`docs/EIDOLON-FULL-REVIEW-2026-10-22.md` (§5 = per-finding status) and `docs/EIDOLON-KNOWN-DEBT.md` §G. Fixed: NR-B1 (voice derived at render
time, `decision/voice.py` — a derivation change bricks every save, C-10), NR-I1, NR-I3 (honest retrieval topic-strict), H9-I3/F-3 + **ADR-32**
(the confession gate is wired and a proof breaks the murderer's last denial, so CONFESSION happens exactly when a proof is shown),
F-14 (tie-break keyed on the question; hypotheticals answered only by HYPOTHETICAL), F-15 (`refuse_streak` produced, fold-checked; REFUSE ≤ 2
turns running), the web/CLI/provider NR-N and H8-N/H9-N items, NR-N11 (pyflakes clean, guarded by a test), NR-N12 (git), NR-N13 (pins,
`requirements-tested.txt`); **ADR-33** (2026-10-23, NR-I2/NR-I4): the murderer's cover also lies about whereabouts (a room nothing
contradicts, so no new breaker set), a LIE tells only its topic's claims, and an audible
scene in the alibi room gives innocents something heard — goldens re-sealed (same murderers and proof cores); seed study 2×50 100/100 sealed, all in band. Open: the rest of §2–§3.
Author's record, not independently reviewed.

## Read these first

0d. `docs/EIDOLON-PHASE-9-REPAIR-RE-REVIEW.md` (independent re-review: H9-B1 not closed → RR-B1, new RR-I1) and
   `docs/EIDOLON-PHASE-9-RR-REPAIR-REPORT.md` (both repaired — author's record by the re-reviewing session, awaiting independent
   re-review). Supersede (0c) where they disagree.
0c. `docs/EIDOLON-PHASE-9-HOSTILE-REVIEW.md` (independent review, verdict **B. REQUIRED FIXES — REMAIN IN PHASE 9**) and
   `docs/EIDOLON-PHASE-9-REPAIR-REPORT.md` (H9-B1/I1/I2 repaired — author's record by the same session as the review, awaiting independent
   re-review). Supersede (0b) where they disagree; the review's §8 is the open finding list.
0b. `docs/EIDOLON-PHASE-9-IMPLEMENTATION-REPORT.md` — **the authoritative current state of Phase 9**: the contract and each criterion's disposition, the TurnTrace schema against §27.1 and the one place it departs (handles for ids, hashes for content), the corpus by class, T-25/T-26 measured, what the nightly job measures and what it could not, the mutation and regression results, the findings (F-3 CONFESSION unreachable; the sink-scrubber bug), the debts (`docs/EIDOLON-KNOWN-DEBT.md` §F). `docs/EIDOLON-PROMPTS-AND-CONSTANTS.md` is generated from the code.
0a. `docs/EIDOLON-PHASE-8-REPAIR-REPORT.md` — **the authoritative current state of Phase 8**: root cause and repair of H8-B1 / H8-I1 / H8-I2 / H8-I3, the
   exact reproductions before and after, failing-first tests, mutants, run commands with exit statuses and the tree hashes, the comparison with the
   review's acceptance list, what stays open. The review itself: `docs/EIDOLON-PHASE-8-HOSTILE-REVIEW.md` (its §7 is the H8-X1 oracle follow-up; the
   repair section is appended at its end). Supersedes (0) where they disagree.
0. `docs/EIDOLON-PHASE-8-IMPLEMENTATION-REPORT.md` — Phase 8 as implemented: deliverable dispositions, the new control
   paths and fold rules, decisions where the architecture is silent, exact test/mutation results, what is unmet. Its debts
   are `docs/EIDOLON-KNOWN-DEBT.md` §D (and Phase 8 notes in §C).
1. `docs/EIDOLON-ARCHITECTURE.md` — the spec (v0.4, design-complete for Phases 1–9).
   1a. `docs/EIDOLON-PHASE-6-REPAIR-REPORT.md` — **the authoritative current state of Phase 6**: the four BLOCKING
   repairs (B-1 engine V-7 bots, B-2 cover synthesis + the real V-3, B-3 the band as a gate + §20.2's loop,
   B-4 proof candidate-domain completeness), the re-run seed study (96/100 sealed, 96/100 **in band**), and the
   8 IMPORTANT + 7 NON-BLOCKING findings that are still open. Supersedes (1b) where they disagree.
   1b. `docs/EIDOLON-PHASE-6-REPORT.md` — Phase 6 as shipped: generator, solver, proof + independent verifier, the
   original seed study (97/100), the mutation history (20 survivors closed), and the deviations D-1…D-9.
   Hostile review (4 BLOCKING, 8 IMPORTANT, 7 NON-BLOCKING, 42 attacks): https://claude.ai/artifact/9qktnKJW9xqLKsmpVzNVeY
2. `docs/EIDOLON-PHASE-5-REPAIR-REPORT.md` — **the authoritative current state of Phase 5**: the
   three BLOCKING repairs (F-1/F-2/F-3), their mutations, and the 10 IMPORTANT findings still open.
   Supersedes (2a) where they disagree.
   2a. `docs/EIDOLON-PHASE-5-REPORT.md` — Phase 5 as shipped.
   Hostile review (F-1…F-17, 36 attacks): https://claude.ai/artifact/WzaAsvZLDobMEdpiGqo7Jt
3. `docs/EIDOLON-PHASE-4-REPAIR-REPORT.md` — **the authoritative current state of Phase 4**:
   blocker repairs, mutation verification, the open IMPORTANT list. Supersedes (3a) where they
   disagree.
   3a. `docs/EIDOLON-PHASE-4-REPORT.md` — Phase 4 as shipped: scope and deferrals.
   Hostile review (findings B-1…B-6, I-1…I-16): https://claude.ai/code/artifact/5152cb54-cfa9-4a07-abf0-9cb96a6894de
4. `docs/EIDOLON-PHASE-3-REPAIR-REPORT.md` — the authoritative current state of Phase 3.
5. `docs/EIDOLON-PHASE-3-REPORT.md` — the original Phase 3 report. Kept as the as-shipped
   record; its test counts and several of its completeness claims are superseded by (4).
6. `docs/EIDOLON-PHASE-2-REPORT.md`, `docs/EIDOLON-PHASE-0.5-REPORT.md`,
   `docs/EIDOLON-ADR-22-REPORT.md`, and the two review documents.

Published audit artifact (findings + resolution, browsable):
https://claude.ai/code/artifact/be7a7e09-20cb-4927-978a-ef142000042e

## Tests — current baseline

```
python -m pytest -q                                                # 3837 passed, 1 skipped (the real-provider cassette replay: UNMEASURED), 1 xfailed (the strict H8-X2 witness); 3839 collected (1 h 25 min)
python -m pytest tests/test_phase9_trace.py tests/test_phase9_corpus.py tests/test_phase9_suites.py tests/test_phase9_observability.py tests/test_phase9_debug.py tests/test_phase9_nightly.py tests/test_phase9_docs.py tests/test_phase9_repairs.py -q   # 990 Phase 9 (71 trace, 752 corpus, 18 suites, 34 observability, 48 debug, 20 nightly, 28 docs, 19 repairs); EIDOLON_LONG=1 runs T-25 at 2000 turns (+7 min)
python -m tests.phase9_mutation_check -j 8                         # 124 mutants (103 + 16 for the H9-B1/I1/I2 repair and the constants doc + 5 net for RR-B1/RR-I1), 124 killed, 0 survived/malformed/errors (about an hour on a shared machine)
python -m eidolon.debug promptdoc                                  # regenerate docs/EIDOLON-PROMPTS-AND-CONSTANTS.md (tests/test_phase9_docs.py fails when it is stale)
python -m pytest tests/world -q                                    # 98   Phase 1
python -m pytest tests/minds -q                                    # 77   Phase 2
python -m pytest tests/evidence -q                                 # 169  Phase 3
python -m pytest tests/test_important.py tests/test_repairs.py -q  # 136  cross-phase repairs
python -m pytest tests/decision -q                                 # 202  Phase 4 ("180" was stale; +5 from the 2026-10-21 repair)
python -m pytest tests/llm -q                                      # 1340 Phase 5
python -m pytest tests/solve tests/gen -q                          # 349 passed + 1 xfailed (the earlier "194" was stale: the Phase 6 repairs grew it; the H8-X1 review measured 348)
python -m pytest tests/test_persistence.py -q                      # 316  Phase 7 + the Phase 8 fold rules + 1 Phase 9 (a row stamped for another turn) (1000/2000-turn cases: EIDOLON_LONG=1)
python -m pytest tests/test_phase8.py -q                           # 147  Phase 8 (controls, verdict, report, projection, browser app, free text; 106 + 41 `H8_*` repair tests)
python -m pytest spike/test_spike.py -q                            # 21   Phase 0.5 (outside testpaths)
python -m tests.decision.mutation_check                            # 60 killed (57 + ADR30-a/b/c), 2 equivalent
python -m tests.decision.mutation_check phase5                     # 70 killed, 1 equivalent (Phase 5 set)
python -m tests.solve.mutation_check                               # 102 mutants (Phase 6 + blockers + RB). Baseline alone ~25-53 min; the full run takes hours. Phase 8 re-ran the 14 in files it changed (`MUT_ONLY`, see the Phase 8 report §6): 14 killed, 0 survived
python -m tests.persistence_mutation_check                         # 197 mutants: Phase 7's 125 + F1-a + 45 Phase 8 + 26 Phase 8 repair (`-k P8-B1,P8-I1,P8-I2,P8-I3`; per-mutant test file); 8 justified equivalent. Repair run (2026-10-21, `-k "P8-,F1a-"`): baseline green, 72 killed, 0 survived. Phase 8 run: all 48 new/re-anchored killed, 0 survived (green-baseline gate, killed-for-the-right-reason, -j N workers on copies)
```

Any change must keep every test green. **Phase 9 (2026-10-21)** adds 971 tests in seven `tests/test_phase9_*.py` files plus one in `tests/test_persistence.py`: 3806 collected, 3804 passed + 1 skipped + 1 xfailed. They guard Phase 9 — same rule: do not weaken an assertion to make a change pass. The load-bearing ones: a trace is written AFTER the commit and its failure (file unopenable, writer raising, builder raising) changes nothing about the turn, the log or the page; no engine id (enumerated by a SEPARATE implementation in the test), credential, prompt, canary or solution key is in any trace row; the sink scrubs every string of a row whoever the caller is (never the serialized JSON); the player process never imports `eidolon.debug` and nothing outside that package names it; the corpus runs the production path against a no-model twin; the nightly job's PASS/FAIL come only from a real `anthropic` client (`is_live`) — everything else is UNMEASURED; the debug server never reads a raw proof (I-58).

Why a passing suite is not enough on its own: the Phase 4 review showed six invariant-breaking mutations surviving
547 green tests. If you add a guard, add its mutation to `tests/decision/mutation_check.py`
(the harness now refuses to report unless the unmutated baseline is green).

`tests/decision/test_long_conversation.py` runs at a reduced scale (300 turns/8 accusations)
by default for CI speed; it holds at the architecture's literal 2 000-turn/50-accusation scale
(153.2s after the blocker repair).

`tests/decision/test_blocking_repairs.py` (47), `tests/decision/test_invariant_mutants.py`
(18) and `tests/decision/test_phase5_readiness.py` (48) guard the Phase 4 blockers and the
Phase-5-readiness repairs — same rule as the Phase 3 regression files below.

`tests/llm/test_llm_blocking_repairs.py` (47) guards the three Phase 5 BLOCKING repairs — same
rule. In particular: the committed claim SEQUENCE is the plan's, never the draft's (`turn.py`
commits `for c in plan.claims`, using `result.claim_ids` only as a set); `repair_feedback` takes
no case/name book, so a violation's detail can never be rendered back to the model; and
`NameBook.of(case, permitted)` requires its allow-list, so the renderer's name index holds only
`allowed_entity_ids | envelope entities | {speaker}` and an undiscovered real entity is
indistinguishable from an invented one.

`tests/llm/test_llm_important_repairs.py` (50) guards F-5…F-12 — same rule. The load-bearing ones:
a request owns a DEEP COPY of its schema, so no provider can widen `DRAFT_SCHEMA` for later calls;
`run_ask_turn` commits on `ValidationResult.integrity()`/`committable`, never on `rejected` alone;
`rate_window` is a sliding count, so the limiter throttles a burst and then recovers instead of
latching; `cli.encountered()` derives what the player may name from the discovery fold, never from
the whole case; and the digest renders display labels, never `EvidenceId`s.

`tests/llm/test_llm_injection_corpus.py` (875) runs `tests/llm/injection_corpus.py` — 112 distinct
player-typed prompts over 15 categories plus 15 negative controls (roadmap §30's "≥ 100"). Each
entry DECLARES whether the deterministic stage-0 scan must flag it (71 of 112 do); the other 41 are
lexically innocent and are the parser's job, so what is asserted for all 112 is containment against
a model that obeys the injection. Do not "fix" a `flagged=False` entry by widening the marker
regexes — that would flag ordinary in-world questions and claim deterministic coverage that does
not exist.

`tests/solve/test_blocker_repairs.py` (30) and `tests/gen/test_covers_and_bands.py` (38) guard the four
Phase 6 BLOCKING repairs — same rule. The load-bearing ones: `verify_proof` compares the proof's candidate
table against `case.living_actors()`, so a proof with its exclusions deleted no longer verifies; V-3 runs
Phase 4's real `check_cover_consistency` AND requires the murderer's layer 0 to have a derivable breaker set
(V-6's `2_lies_breakable` does not catch its absence); V-6 REJECTS an out-of-band case; and the bluff bot is
an engine-driven 500-turn run whose measurement is proved non-vacuous by a fixture it fires on.

`eidolon/solve/bots.py` is V-7. The bots run the real `decision.turn` pipeline with `TemplateLLM`; the solver
appears only where §19.7 puts it, on the material a bot actually acquired. Do not replace one with a
`solve()` wrapper — that is the defect the audit found.

`tests/test_phase9_repairs.py` (19) guards the Phase 9 review's H9-B1/I1/I2 repair — same rule. The load-bearing ones: a LIE and a TRUTH
escalate identically when the same question is repeated (`REPEAT_PRIOR` from the 3rd ask re-supplies the STANDING answer, never retrieval;
`REFUSE` from the 6th; both whatever is shown unless an authored evidence response (`DENY_EVIDENCE`/`REINTERPRET`) is in play — an inert shown item must escalate exactly like nothing shown (RR-B1); their preferences clear the 3.00 ceiling of every other act); a repeat bot over two
generated cases learns nothing about sincerity; the nightly counts a refusal or malformed parse as a miss and a transport failure or budget
cut as UNMEASURED (never a hit), and N-4/N-6/N-7 are UNMEASURED when a call they needed went unanswered or the session is incomplete (RR-I1); the audit's verify calls go to `AUDIT_MODEL` and N-5's note is read off the calls. Suite 2 asserts §28.4 #2 for
the liar as for the truthful witness — never restore "a liar repeats his lie unchanged".

`tests/test_phase8.py` (147) and the `P8_*` entries of `FORGERIES` in `tests/test_persistence.py` guard Phase 8 — same rule.
The load-bearing ones: a control commits ONLY through `Save.append` (a runner rejection or a fold refusal leaves file, head
and hash unchanged and shows no in-world text); `CaseSolved.correct` is judged against `GameState.murderer` — the sealed
proof's unique survivor — never against the payload or the declared solution, and nothing follows the verdict; the
evidence axis is `game.establishes` on the CITED set, never the stored proof core; no page or projection serializes an
engine-only token or id (evidence is addressed by `game.handle` only); every form field is validated in `web.dispatch`.
The `H8_*` tests (the 2026-10-21 repair) add: while an item's implication is locked behind an account the player has not heard, no theory, tension or
form list may be tied to it — the filter is `unlocked_view` / `unlocked_implications`, never `Evidence.implications` (`tests/decision/test_hypotheses.py`
too); a refused search says nothing an engine id could be read from; `Host` is judged against the loopback allow-list and `Origin` against the matching
origins; a save opens only under its on-disk spelling and `_commit` believes the store's `AppendResult`. Do not weaken them to make a change pass.

`tests/evidence/test_blocking_regressions.py` (15) and
`tests/evidence/test_important_regressions.py` (41) guard the 16 audited defects. Each test's
docstring names the finding it guards and the failure mode it reproduces — do not weaken an
assertion there to make a change pass.

## Layering (§23.1) — one way, no exceptions

```
world  <-  minds  <-  evidence  <-  decision  <-  llm  <-  solve  <-  gen
                                                     (solve never imports gen; nothing below imports either — checked by test)
```

`eidolon/trace.py` sits beside `game` at the top (it reads `decision`/`llm` results and a `Save`; `store` imports nothing from it). `eidolon/debug/` may import anything and NOTHING imports it or names it (I-10, tested statically and by starting the player stack and inspecting `sys.modules`); its entry point is `python -m eidolon.debug`, deliberately not a subcommand of `eidolon.cli`, which the player process imports.

`eidolon/evidence/` must never construct a `Belief` or `KnowledgeEntry`, and must never write
to a `Case`, `FactIndex` or any minds store. This is what stops evidence becoming a second
source of truth (§5.2), and it is checked by test, not by convention.

Keep these six states distinct — collapsing any pair is the defect class the Phase 3 audit
found most of:

```
PRESENT IN WORLD -> GROUNDED -> DISCOVERABLE -> DISCOVERED -> VISIBLE TO PLAYER
                                                           -> KNOWN BY CHARACTER
```

And: **two evidence records are not two independent sources** unless `corroborates` says so
(I-37 — distinct known origins, both authentic, disjoint transitive derivation).

## House rules

- No `random`, `secrets` or `uuid4` outside `gen/` (I-6). Runtime is deterministic; tie-breaks
  hash (I-5, I-22).
- No float in authoritative state (I-17) — integer basis points.
- Fail closed (I-15): unknown provenance, unresolvable references and unvouched material
  resolve to refusal, never to permission.
- Sealed data is sealed all the way down (I-4): a `dict`-typed field on a `frozen=True` model
  is still mutable — use `Frozen`/`FrozenDict` from `eidolon/world/frozen.py`.
- Phase 1 and Phase 2 fixtures are owned by their phases. If a later phase's checker rejects
  one, fix the fixture rather than weakening the checker — see §5 of the Phase 3 repair report
  for the one case where that happened.
