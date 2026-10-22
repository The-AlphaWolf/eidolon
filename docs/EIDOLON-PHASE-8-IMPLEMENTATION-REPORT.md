# EIDOLON — Phase 8 implementation report

Date: 2026-10-19 – 2026-10-20. Author's record of the Phase 8 implementation — **not** an independent review. Phase 9 was not started.
Contract: `docs/EIDOLON-ARCHITECTURE.md` §30 (Phase 8), §16 (hypotheses, accusation, scoring), §12.1 stages 10-11, §13.4,
§26.2, the invariant table (I-10, I-12, I-14, I-15, I-16, I-17, I-22, I-26, I-31), the Phase 7 re-review's Phase 8 entry
tasks (`docs/EIDOLON-PHASE-7-RE-REVIEW.md` Part II §II.9 and Part I §9) and `docs/EIDOLON-KNOWN-DEBT.md`.

## 0. The contract, established before coding

**§30 Phase 8 is the player-facing interface**: a web app with HTMX views (chat with interpretation chip; notebook with
statements / evidence / tensions / hypotheses; structured `Present` / `Accuse` / `Hypothesize` controls; map/location),
client `action_id` generation and retry-on-failure, session management, case report on solve, a strict projection layer.
Tests: projection leak test, accessibility basics, HTTP probe (debug routes 404 on the player port). Exit: a tester can
play `vance_v03` start to finish in a browser without the CLI.

**Entry tasks owed by Phase 7** (re-review §II.9): `HypothesisChanged` fold rules (F-3 `updated_turn == turn`; the N-6
`Attitude`/`Motive` float decision), `CaseSolved.correct` against the PI-7-verified survivor and no turns after solve
(PN-10), `contradictions_caught` id resolution (F-9), the F-8 integration hazards.

**The brief's investigation targets, checked against §30** — `Accusation`, `HypothesisChanged`, `CaseSolved`: Phase 8
(the `Accuse`/`Hypothesize` controls and the case report need them) → producers + fold rules built. `IncidentalPinned`,
`KnowledgeAdded`, the epistemic overlay kinds: **not** Phase 8 deliverables — their producers are §12.1 stage 10 /
§6.5 / §8.5-8.6 turn-pipeline work, and the re-review says the same ("The epistemic, incidental, trust, emotion and
suspicion kinds are not Phase 8 deliverables; R-1's fixes for them belong with their producers"). No producer was added
for them; their existing fold rules are unchanged and still tested (§8, C-5).

**Baseline before any change** (`D:\Murder Mystery`, Python 3.12.10, Windows 11):

| Command | Result | Exit |
|---|---|---|
| `python -m pytest tests/test_persistence.py -q -p no:cacheprovider` | `263 passed in 632.14s` | 0 |
| `python -m pytest tests/decision/test_hypotheses.py tests/decision/test_exploration.py tests/decision/test_fold_completeness.py tests/decision/test_cli.py tests/llm/test_llm_cli.py tests/decision/test_static_invariants.py -q -p no:cacheprovider` | `24 passed in 3.28s` | 0 |

`store.py` hashed to `aedb1c39…` (the Phase 7 frozen manifest) before the first edit. There is no VCS in this tree, so the
pre-change tree was snapshotted and every "failing first" claim below is a recorded run against unmodified engine code.

**Plan** (written before implementation; one row per deliverable):

| Deliverable | Existing model | Control / producer | Transition | Events | Rejected when | Tests |
|---|---|---|---|---|---|---|
| Hypothesize: create / revise / withdraw | `Hypothesis` (+ status `withdrawn`), `HypothesisChanged` | `run_hypothesis_turn` ← `game.hypothesize`/`withdraw` ← form | board replace-by-id; turn + 1 | `TurnCommitted(None)`, `HypothesisChanged` | unknown/withdrawn id; `Lied`/`Planted`/support on unheld material; `Lied` about another speaker's words; unknown entity; off-clock; N-6 floats; inside a conversation; created/updated turn ≠ turn; case closed | runner, controls, `P8_*` forgeries at append + load, replay |
| Provisional accusation | `Accusation(provisional)`, `DetectiveModel.accusations` | `run_ask_turn(provisional_accusation=True)` ← "accuse them to their face" | verbal pressure (existing) + accusations += `(turn, True, target)` | `+Accusation`, the turn's one `DetectiveModelUpdate` | outside a conversation; target ≠ addressee; model records an accusation no row made, at another turn, or fails to record it | same |
| Final accusation and verdict | `Accusation` + defaulted form fields; `CaseSolved`; `GameState.murderer` | `run_accusation_turn` ← `game.accuse` ← form | accusations + `solved`; terminal | `TurnCommitted(None)`, `Accusation(final)`, `CaseSolved` | outside the candidate domain; cites unheld material; unknown weapon/place; off-clock window; inside a conversation; two finals; `CaseSolved` without a final accusation or vice versa; `correct` ≠ (target == proven survivor); any row/turn after it | same |
| Case report | projection (never hashed) | `game.report` | — | — | before the verdict | five axes, alternative-proof credit, answer from the CaseLog |
| Notebook, map, chat | projection | `game.notebook` | — | — | — | leak test, tensions held-only |
| Browser app, sessions, `action_id` | `Save` | `web.create_app` (Starlette) | only via `Save.append` | — | duplicate id → its committed turn; stale head → nothing; crafted field → refused at the boundary | HTTP flows, double POST, two tabs, 404 probes, a11y, playthrough |

## 1. Architecture deliverables and their disposition

| §30 deliverable / test | Disposition |
|---|---|
| Web app (FastAPI + uvicorn, Jinja2, HTMX) | **Delivered with two substitutions** (debt D-2): Starlette (FastAPI's own base; FastAPI is not installed and these five routes use nothing it adds), Jinja2 autoescaped, uvicorn via `eidolon serve` bound to `127.0.0.1`. HTMX is not vendored (no network): full-page form posts |
| Chat with interpretation chip | **Delivered.** Structured questions always; free text when a model is configured (`eidolon serve --llm`): §12.1 stages 0-2 (`llm.ingress.interpret`: screen, parse with only the names the player may use, ground) then the same turn rendered by the model and validated (`LLMRenderer`), the chip saying how the line was understood; one in-world answer for every unclear or unknown name (§22.2); every typed line feeds the rate window. Tested with a scripted transport; a live model has not been run here (D-1) |
| Notebook: statements / evidence / tensions / hypotheses | Delivered (`game.notebook`): heard statements, found items (opaque handles + label + the item's own text), tensions between two HELD items (§13.4, never which side is true), live re-evaluated theories |
| Structured `Present` / `Accuse` / `Hypothesize` controls | Delivered: "show them" on the question form (Present), "accuse them to their face" (provisional, §16.3) and the final accusation form (§16.3's solution form + cited proof + confirmation), the theory form (`At`, `Lied`, `Planted`) with withdraw |
| Map / location | Delivered: places, visited marks, go-to and search controls |
| Client `action_id` generation and retry-on-failure | Delivered: each rendered form carries its `action_id` (`<form>@<head seq>`, deterministic, I-6) and `expected_seq`; re-sending returns the committed turn (§26.2), an old page commits nothing (I-14). D-6 records the one message imprecision |
| Session management | Delivered: case library (sealed bundles in a directory), new game (validated name, library case only, seed), resume (saves directory), opened writable and verified end to end by `Save.open` |
| Case report on solve | Delivered (`game.report`): five axes, the answer derived from the CaseLog and the proof's verified survivor (N-7), the evening's timeline with the player's finds marked |
| Strict projection layer | Delivered: no act, sincerity, grounding, cover/secret, pressure, composure, knowledge/belief/memory id, account token, evidence id or canary reaches a page; before the verdict no "murderer"/"solution" word and no report route |
| Test: projection leak | `test_no_projection_serializes_an_engine_only_field_or_identifier` (after a real concession, theories, a provisional accusation; again after the verdict, report included) |
| Test: accessibility basics | `test_pages_meet_accessibility_basics`: `lang`, one `h1`, `main`, a label for every control, named buttons, a polite live region; plain HTML controls (keyboard-operable), dark text on white |
| Test: HTTP probe — debug routes 404 | `test_debug_and_engine_routes_do_not_exist_on_the_player_app_I10` (12 paths) + an import check that `web.py` imports no debug/bot tooling |
| (boundary, beyond §30's list) | every form field validated before it reaches an engine type (`test_a_crafted_form_is_refused_…`, 18 crafted posts); a cross-site POST is refused — no cookie identifies a player, so this is the CSRF guard (`test_a_cross_site_post_is_refused_…`); a save that fails verification gets a refusal page naming no engine detail instead of an error (`test_a_tampered_save_gets_a_refusal_page_…`); game names and cases are validated against path traversal and Windows device names |
| Exit: play `vance_v03` in a browser | **Measured on `study_party_s4`** (D-7): `vance_v03` is a CaseLog with no sealed bundle (no secrets, covers or proof) and cannot be saved or played — the substitution Phase 4 made for its CLI exit. `test_a_tester_can_play_the_case_to_a_proven_verdict_in_the_browser` plays it over HTTP only, from what the pages offer, to a correct verdict with every axis right. A manual run in the Claude browser pane against `eidolon serve` on `manor_wing_s4` went new game → search (scene found, weapon becomes nameable) → question (chip + validated reply) → theory ("65% — corroborated; consistent with statement 2") → final accusation (confirmed) → report (five axes, the answer from the CaseLog, the evening's timeline) |

## 2. Files changed

| File | Change |
|---|---|
| `eidolon/game.py` | **new** (325 lines): controls, `_commit` (the only path to `Save.append`), the question builder and the typed-line chip (`understood`), projections (`notebook`, `report`, `establishes`), opaque evidence handles |
| `eidolon/web.py` | **new** (366 lines): Starlette app, `Games` (session management), `Chat` (free text with a model), inline autoescaped templates, `dispatch` (form → control, every field validated at the boundary), same-origin check on POSTs, refusal page for a save that fails verification |
| `eidolon/decision/turn.py` | +75 −3: `GameState.murderer`; `ExplorationTurnResult.violations`; provisional accusation rows in `run_ask_turn`; `run_hypothesis_turn`, `run_accusation_turn` |
| `eidolon/decision/events.py` | +14 −1: `Accusation` gains `weapon`, `location`, `interval`, `motive_kind`, `cited` (all defaulted); docstrings |
| `eidolon/decision/hypotheses.py` | +3 −1: status `withdrawn` |
| `eidolon/store.py` | +75 −9: the Phase 8 fold rules (§4); `ENGINE_VERSION = "eidolon-8.0"`; one dead check removed |
| `eidolon/solve/session.py` | +5 −1: `new_session` sets `murderer` from the sealed proof's unique survivor |
| `eidolon/solve/bots.py` | +9 −3: `credited_material(state, only=…)` (the cited subset, same crediting rule) |
| `eidolon/cli.py` | +22: `eidolon serve` (`--llm` for a live model) |
| `pyproject.toml` | +1: optional `web` extra |
| `tests/test_phase8.py` | **new** (780 lines, 106 tests) |
| `tests/test_persistence.py` | +125 −5: 26 `P8_*` + 1 `F1a_*` forgeries, 4 fold tests, fixture updates (below) |
| `tests/persistence_mutation_check.py` | +120 −14: per-mutant test file, comma `-k`, 46 new mutants (45 Phase 8 + F1-a), 2 re-anchored, 3 justified equivalents |
| `docs/EIDOLON-KNOWN-DEBT.md` | Phase 8 dispositions in place; §D |
| `CLAUDE.md` | the Phase 8 row, the reading list, the test baseline |

**Existing tests whose fixtures changed, and why (no assertion was removed or weakened):** `_hyp` (the hypothesis-forgery
helper) now builds producer-shaped entries (created/updated this turn), so each `R1_*`/`F1_*` hypothesis forgery still
carries only its one defect under the new F-3 rule; `test_R1_a_genuine_hypothesis_and_overlay_turn_are_accepted_and_reload`
and `test_F1_the_clock_is_inclusive_…` (negative controls) set `created_turn`/`updated_turn` to the turn for the same
reason; `test_PI1_the_case_cannot_be_solved_twice` now opens with a genuine verdict turn — its old first turn (a bare
`CaseSolved`) is exactly PN-10's forgery and is now refused — and gained a second refused verdict.

## 3. Control paths and state transitions

Every control is `game.<control>(save, action_id, expected_seq, …)` → `_commit`:

1. `save.turn_for(action_id)` exists → **duplicate**: the committed turn is reported, nothing runs (§26.2).
2. `expected_seq != save.last_seq` → **stale**: nothing runs (I-14).
3. the case is solved → **rejected** ("The case is closed").
4. the decision runner shapes the turn from the authoritative (folded) state; `rejected` → **rejected**, nothing committed.
5. `Save.append(events, expected_seq, action_id)` — the validating fold. `SaveRefusal` → **rejected**, `StaleAppend` →
   **stale**; either way nothing is committed (I-15) and no in-world text is shown (I-12).
6. **ok**: the session is the store's folded state; the runner's own state is discarded.

| Control | Runner | Turn shape | State written |
|---|---|---|---|
| question (+ show, + accuse to their face) | `run_ask_turn` | conversation turn; + `Accusation(provisional)` and the accusation in the one `DetectiveModelUpdate` | ledger, hearing, cover/peel (existing); `decision.accusations`, the accused's `detective_model.accusations`, verbal pressure |
| say (free text; only with a model) | `llm.ingress.interpret` → `run_ask_turn(renderer=LLMRenderer)` / go / search | the matching turn above; an unclear line or unknown name is an in-world "what do you mean?" with nothing recorded | as the matching turn |
| go to / search | `run_goto_turn` / `run_search_turn` | exploration turn (existing) | discovery |
| theory: add / revise | `run_hypothesis_turn` | `TurnCommitted(None)`, `HypothesisChanged` | `decision.hypotheses` (replace by id): propositions, `player_confidence = bp/10000`, created/updated turn, commit-time evaluation |
| theory: withdraw | `run_hypothesis_turn(withdraw=)` | same | status `withdrawn` (terminal) |
| final accusation | `run_accusation_turn` | `TurnCommitted(None)`, `Accusation(final)`, `CaseSolved` | `decision.accusations`, `decision.solved`; nothing may follow |

**Decisions recorded** (the smallest justified choice where the architecture is silent):
* **`CaseSolved.correct` is the WHO axis** against the sealed proof's verified unique survivor (`GameState.murderer`, set by
  `new_session` from `proof["survivors"]`, which `load_sealed_text` already requires to equal the declared murderer —
  PI-7). The other four axes are the report's, a projection: **the score is never stored**, so there is nothing to trust or
  to re-verify.
* **A final accusation ends the case** whatever the verdict (`Game.status` solved/failed, §25): §16.3 calls it `final`.
* **`Accusation` gained five defaulted fields; `SCHEMA_VERSION` stays 1.** The strict round-trip makes the addition
  breaking for an existing `Accusation` row, but no producer ever wrote one before Phase 8, so no genuine save holds one; a
  hand-made v1 file that does is refused (fail closed). Every other kind's payload is byte-identical.
* **Removal is withdrawal** (status `withdrawn`, terminal, kept in the log and in state, off the board).
* **Provisional accusations are put to the accused** (target = addressee: §16.3 "shift the accused's …", §11.3 "made TO THIS
  CHARACTER") and recorded in the accused's detective model, which the digest already reads. `suspicion_of_detective` /
  `estimated_suspicion_of_me` are not written: §16.3 gives no size and nothing reads them (D-3).
* **N-6:** no new float — see §8.
* **Hypothesis `support`/`against`/`status`** are recorded at commit (the model's post-value) and checked only for held-ness;
  the notebook re-evaluates live, because the player's material keeps growing (§16.1 "from player-held material only").

## 4. Event producers and fold changes

Producers added: `Accusation` (provisional: `run_ask_turn`; final: `run_accusation_turn`), `HypothesisChanged`
(`run_hypothesis_turn`), `CaseSolved` (`run_accusation_turn`). `game._commit` is now the production caller of
`Save.append` (C-5 said none existed).

Fold rules added to `fold_turn` — the one function `append` and `Save.open` both run — each structural (no weight, score,
retrieval, model or solver is consulted, I-22; `test_the_folds_never_consult_…` still passes):

| Rule | Refusal | Forgery (append + re-chained load) |
|---|---|---|
| No turn follows `CaseSolved` (PN-10) | "the case is already solved: no turn follows CaseSolved" | `test_no_turn_follows_the_verdict_…`, `test_PI1_the_case_cannot_be_solved_twice` |
| No row follows `CaseSolved` in its own turn | "… after CaseSolved: nothing follows the verdict" | `P8_a_row_after_the_verdict_in_its_own_turn` |
| A provisional accusation is put to the addressee inside a conversation | "a provisional accusation is put to the addressee …" | `P8_provisional_accusation_outside_a_conversation`, `…_of_someone_not_addressed` |
| The accused's model records exactly that accusation, at this turn, and nothing else | "rewrites more than …" / "… the accused's detective model does not record" | `P8_model_records_an_accusation_nobody_made`, `…_at_another_turn`, `P8_provisional_accusation_the_model_does_not_record` |
| A final accusation is a turn of its own; one per turn | "a final accusation is a turn of its own …" / "two final accusations" | `P8_final_accusation_inside_a_conversation`, `P8_two_final_accusations_in_one_turn` |
| It cites only held material and names only what the case contains, inside its clock | "cites … which the player does not hold" / "does not contain" / "outside the case's clock" | `P8_final_accusation_citing_material_never_held`, `…_citing_an_account_token`, `…_naming_a_weapon…`, `…_naming_a_place…`, `…_window_off_the_clock` |
| It must close the case in the same turn | "must close the case" | `P8_final_accusation_that_does_not_close_the_case` |
| `CaseSolved` needs a final accusation in its turn; `correct` == (target == proven survivor); a proven survivor must exist | "without a final accusation" / "disagrees with the proven murderer" / "no proven murderer" | `P8_case_solved_without_an_accusation_PN10`, `…_inside_a_conversation`, `…_correct_for_an_innocent_PN10`, `…_incorrect_for_the_murderer_PN10`, `test_a_verdict_needs_a_proven_murderer…` |
| A board edit is its own turn, tied to it (F-3): created now, or revised with its creation turn intact; never born withdrawn; a withdrawn entry is never edited | "inside a conversation turn" / "updated_turn … (F-3)" / "must be created in this turn, and not withdrawn" / "revises a withdrawn entry or rewrites its creation turn" | `P8_hypothesis_inside_a_conversation_turn`, `…_updated_in_another_turn_F3`, `…_created_in_another_turn_F3`, `…_born_withdrawn`, `test_P8_a_withdrawn_hypothesis_cannot_be_revised…`, `test_P8_a_revision_cannot_rewrite_its_creation_turn_F3` |
| `Lied(actor, statement)` names a statement that actor made | "which is not Elena's" | `P8_hypothesis_Lied_about_another_speakers_words` |
| (F1-a) `Moved.t` lower bound | "outside the case's clock" | `F1a_claim_moved_at_a_negative_tick` |

No existing fold guard was weakened. The domain check on `Accusation.target` and the old "already solved" message are
kept; the old in-row `CaseSolved` re-solve check became unreachable once "nothing follows the verdict" runs first and was
removed (its mutant was re-anchored on the turn-level rule that now carries it). `DetectiveModelUpdate`'s rule is
*tightened*, not widened: the accusation list may change only by the one tuple the turn's own row owes.

## 5. Tests and exact observed results

| Command | Result | Exit |
|---|---|---|
| failing first: `python -m pytest tests/test_phase8.py -q -x` (unmodified engine) | collection error: no `eidolon.game` | 2 |
| failing first: `python -m pytest tests/test_persistence.py -q -k "P8 or solved_twice or R1_a_genuine or F1_the_clock or PI2_a_bp"` (unmodified engine) | `43 failed, 8 passed` | 1 |
| `python -m pytest tests/test_phase8.py -q` (after implementation) | `75 passed, 1 failed` (a test's case-sensitive string check, fixed; re-run of it: 1 passed) | 1 → fixed |
| later additions, targeted (`-k "crafted or runners_reject or proven_murderer_to_be"`, `-k runners_reject`) | `18 passed, 1 failed` (test bug: identity check, fixed) → `1 passed` | — |
| `python -m pytest tests/decision tests/world tests/minds tests/evidence tests/test_important.py tests/test_repairs.py -q` | `677 passed in 73.14s` | 0 |
| `python -m pytest tests/test_persistence.py -q` | `308 passed, 2 failed in 647.54s` — both `P8_final_accusation_inside_a_conversation` (append, load): the guard refused, but the forgery's regex ("its own turn") did not match the message ("a turn of its own"); regex corrected; the file is green in the mutation gates and in the final full suite | 1 → fixed |
| full suite (first run) `python -m pytest -q -p no:cacheprovider -W ignore::DeprecationWarning` (every phase's tests, `test_phase8.py` included; started after the last engine edit, before the regex fix, which the mutation gate covers — §6) | `2775 passed, 1 warning in 4187.28s` | 0 |
| boundary guards (cross-site POST, empty search, tampered save) and free text with a scripted model, targeted (`-k "cross_site or tampered or crafted or …"`, `-k "typed_question or unclear_or_unknown or over_long or rate_window or without_a_model or cli_serves"`) | `47 passed`; `8 passed` | 0 |
| **final full suite on the final tree** `python -m pytest -q -p no:cacheprovider -W ignore::DeprecationWarning` (source hashes of `store.py`, `game.py`, `web.py`, `cli.py`, `decision/turn.py` identical before and after; run beside mutation harnesses) | **`2785 passed, 1 warning in 6180.34s`** | **0** |
| `EIDOLON_LONG=1 python -m pytest tests/test_persistence.py -q -k long_session` (after every fold change) | `3 passed in 1368.39s` — 500 / 1000 / 2000 turns: 54.84 s / 201.40 s / 1109.30 s (run beside three mutation harnesses and a full suite; Phase 7 measured 27 / 113 / 428 s alone) | 0 |

Not run: `spike/test_spike.py` (outside `testpaths`; nothing it imports changed).

## 6. Mutation results

`python -m tests.persistence_mutation_check -j 3 -k "P8-,F1a-,case-solved-twice,accusation-outside-the-domain"` (43 selected:
40 new Phase 8 mutants, F1-a, two re-anchored): **`baseline green; 43 killed, 0 survived, 0 malformed, 0 infrastructure errors,
8 justified equivalent`, exit 0.** The green-baseline gate ran `tests/test_persistence.py` and `tests/test_phase8.py` in full on a
copy of the tree at that point (after the regex fix in §5), so both files passed there.

After that run, `web.py`, `game.py` and `cli.py` changed (the three boundary guards; free text with a model) and five mutants were
added. `store.py`, `decision/turn.py`, `solve/session.py` and `solve/bots.py` did not change after it started (hashes compared),
so its kills of their guards stand on the final tree. On the final tree:

| Command | Result | Exit |
|---|---|---|
| `python -m tests.persistence_mutation_check -j 2 -k "P8-web-chat"` | `baseline green; 2 killed, 0 survived, 0 malformed, 0 infrastructure errors` (gate: all of `tests/test_phase8.py`) | 0 |
| `python -m tests.persistence_mutation_check -j 3 -k "P8-web-"` (the whole browser boundary: name, library, confirmation, cross-site POST, field validation, tampered save, empty search, unheld presentation, both chat guards) | `baseline green; 10 killed, 0 survived, 0 malformed, 0 infrastructure errors` | 0 |
| `python -m tests.persistence_mutation_check -j 2 -k "P8-control,P8-handle,P8-evidence,P8-report"` (the four `game.py` guards, re-run because the file changed) | `baseline green; 4 killed, 0 survived, 0 malformed, 0 infrastructure errors` | 0 |

**Phase 8 mutation total on the final tree: 48 distinct mutants — 45 `P8-*`, F1-a, and the 2 re-anchored Phase 7 mutants — every
one killed for the right reason (the first run's kills for the files that did not change after it, the re-runs above for the
rest), 0 survived; 3 new justified equivalents (8 in the table). The harness now lists 171 mutants.**

An earlier `-k "P8-web-"` run killed its 8 mutants but ended in the harness's own `AssertionError: a source file changed` — the chat
wiring was edited into `web.py` while it ran — so it is not counted; the run above replaces it. Three new justified equivalents are in the harness's
`EQUIVALENT` table (unresolvable cited handle, control-level stale check, murderer from the declared solution). The anchors of the
decision (59), Phase 5 (71) and Phase 6 (102) harnesses were re-verified to match exactly once (one Phase 6 anchor, `RB2-n`, was
restored by keeping its line intact in `credited_material`), and the harnesses were re-run on the changed tree:

| Command | Result | Exit |
|---|---|---|
| `python -m tests.decision.mutation_check` | 57 KILLED, 2 SURVIVED — both listed EQUIVALENT (M2, M4), as recorded before Phase 8; `MUTATION VERIFICATION: PASS` | 0 |
| `python -m tests.decision.mutation_check phase5` | 70 KILLED, 1 SURVIVED — the listed EQUIVALENT P5-22, as recorded before Phase 8 (each mutant's selection `tests/llm`: 1340 tests); `MUTATION VERIFICATION: PASS` | 0 |
| `MUT_ONLY='^(R4 \|R5 \|R6 \|R7 \|R8 \|R9 \|RB1-c \|RB1-h \|RB2-b \|RB2-e \|RB2-g \|RB2-h \|RB2-i \|RB2-n )' MUT_WORKERS=14 MUT_TIMEOUT=7200 python -m tests.solve.mutation_check` — the 14 Phase 6 mutants anchored in files Phase 8 changed (`solve/bots.py` 7, `decision/turn.py` 6, `solve/session.py` 1), run alone | `baseline green: 347 passed in 1478.48s`; 14 KILLED (each on a failing assertion, none by timeout), 0 SURVIVED, 0 ERROR; `MUTATION VERIFICATION: PASS` | 0 |

The other 88 Phase 6 mutants are anchored in files Phase 8 did not change (`solver.py`, `proof.py`, `gen/pipeline.py`, `lattice.py`,
…) and were **not** re-run: the full 102-mutant run was attempted twice and finished neither time — once its baseline exceeded the
1500 s per-run timeout while competing with a full-suite run, once the session ended mid-run. Their killing tests are unchanged
and pass in the final full suite.

## 7. Save / load / replay integration

Passed in `tests/test_phase8.py` runs: live state == folded state after every new transition (theory create/revise/withdraw,
provisional accusation with and without a presentation that conceded a layer, the verdict); a reloaded copy continued with the same
verdict reaches the same state hash and chain head as the original; a Phase 8 save replays to the in-process hash in fresh
processes under `PYTHONHASHSEED` 0, 1 and 4242; every `P8_*` forgery is refused at append and, re-chained, at load (the one regex fix of §5 included: green in the
mutation gates and the final full suite). The 500/1000/2000-turn sessions save, reload and replay to the live hash after
the fold change (§5).

## 8. Remaining known debt (Phase 8 touched)

| Item | State after Phase 8 |
|---|---|
| PN-10 (`CaseSolved.correct` unchecked, turns after solve) | **resolved** (§4) |
| F-3 (turn-valued fields not tied to the turn) | **resolved for hypotheses**; `InvestigationTold.by_detective_turn` / `KnowledgeEntry.acquired_at` remain (no producer) |
| N-6 / C-2 (`Attitude.intensity`, `Motive.strength` floats) | **decided**: not offered by the board, still refused if forged; the motive axis is a skeleton-vocabulary string; no new float in authoritative state; the two grid-checked exceptions unchanged |
| F-9 / C-1 `contradictions_caught` | **no producer by scope** (§30 does not ask; nothing reads it): every id is refused, even one spelled from two held items; the id rule is owed by its first producer |
| F-8 hazards | provisional accusation / board / verdict rows stamp the current turn (checked by the fold); the strategy's `turn_id` and the told-row ordering remain hazards for future overlay producers (D-9) |
| N-7 (declared victim/weapon/method/event unconfirmed) | **resolved for the report**: it reads the attack event, its room, window and objects and the murderer's motive from the CaseLog, and the who from the verified proof; nothing reads the declared fields |
| F1-a (no mutant for the `Moved.t` lower bound) | **resolved** (forgery + mutant, with this `store.py` change as `CLAUDE.md` asked) |
| C-5 producer-less kinds | 14 → **11**; the remaining are out of §30's Phase 8 scope |
| C-4 (`PlayerAction` rows) | open: the chip is shown live, replay does not need the text |
| C-1 (re-chained, structurally valid turns) | narrowed by §4; a forger can still add a structurally valid provisional accusation or theory |
| C-11 / PU-1 cross-machine replay | still unmeasured (fresh-process, three hash seeds, same machine: equal) |
| New: D-1 … D-9 | `docs/EIDOLON-KNOWN-DEBT.md` §D |

Items unrelated to Phase 8 keep their ledger status unchanged.

## 9. Unmet acceptance criteria

None of §30's Phase 8 deliverables is missing. What is not met, or met only by substitution, stated plainly:

* **Exit criterion substituted** (D-7): measured on the generated `study_party_s4`, because `vance_v03` has no sealed bundle and
  cannot be played. An HTTP-only automated playthrough reaches a proven, five-axes-right verdict; one manual run in a browser
  covered every control; **no independent human tester** has played a case (two external playtesters are Phase 9's exit).
* **Free text has never run against a live model** (D-1): no network or key here; tested with a scripted transport only.
* **FastAPI and HTMX substituted** by Starlette and plain form posts (D-2).
* **Cross-machine replay still unmeasured** (C-11; a Phase 7 exit criterion carried forward, not a Phase 8 gate).
* **Phase 6 mutation harness re-run only for the 14 mutants in files Phase 8 changed** (§6); `spike/test_spike.py` not run.
* **No independent review** of Phase 8.

**PHASE 8 IMPLEMENTED — READY FOR INDEPENDENT REVIEW**
