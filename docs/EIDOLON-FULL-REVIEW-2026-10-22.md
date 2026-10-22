# EIDOLON — full project review (2026-10-22)

Reviewer: the Claude Code session that, earlier the same day, re-reviewed the Phase 9 repair, repaired RR-B1/RR-I1, added the free
model providers, per-character voices, ADR-30 and the parser/fallback changes. **Those changes are self-reviewed here, not
independently.** No code was changed by this review; every probe ran in a scratch copy (the one exception: reading `saves/*.db`
read-only with `eidolon replay`).

**How:** (1) every recorded open item was collected from `docs/EIDOLON-KNOWN-DEBT.md`, the phase repair reports and the hostile
reviews; (2) fresh review of the trust boundary (`web.py`, `game.py`, `cli.py`, `llm/provider.py`), the decision path
(`decision/turn.py`, `strategy.py`, `footprint.py`, `validator.py`), the renderer (`llm/render.py`, `ingress.py`) and everything
changed today; (3) mechanical checks — `pyflakes` over `eidolon/`, `tests/`, `spike/`; house-rule greps (no `random`/`uuid` outside
`gen/`, no `eval`/`pickle`/`shell=True`); an AST scan for tests without assertions; (4) live probes — HTTP boundary inputs through
`starlette.testclient`, CLI error paths, memory-kind census of the generated cases, a replay of every save in `saves/`. Modules that
were hostile-reviewed and accepted (`store.py`, `trace.py`, `debug/`, `solve/`, `gen/`, `world/`, `minds/`, `evidence/`) were
spot-checked, not re-audited line by line; their findings below are the recorded ones.

Severity: **BLOCKING** (breaks something users rely on, or an invariant), **IMPORTANT** (must be fixed before the affected evidence
or feature is relied on), **NON-BLOCKING** (real, recorded), **UNMEASURED** (needs a live model or a human).

## Project status in one table

| Phase | State |
|---|---|
| 0.5–7 | done; 7 accepted by its closure gate. 4, 5, 6 carry open IMPORTANT lists (§3). 6 was never independently accepted |
| 8 player UI | **not accepted** — H8 repair awaits independent re-review |
| 9 observability / live validation | **not accepted** — RR repair awaits independent re-review; exit criteria F-1 (live nightly) and F-2 (two playtesters) unmet |
| ADR-30 + today's play-quality work | author's record only, not reviewed |
| 10 optimization | not started (needs 9) |

---

## 1. New findings (this review)

### NR-B1 — BLOCKING — today's voice change makes every older save unreadable (including the user's game `S`)

**Evidence.** `python -m eidolon.cli replay saves/S.db` → `ok: false`, "the initial world this engine derives from the case and seed
is not the one the save was made in". Same for `saves/geminitest.db`. The three saves created after the change load.
**Cause.** `solve.session.default_personality` now derives a per-character `VoiceSpec` (`default_voice`). `store.initial_digest`
(`store.py:644-653`) digests `_plain(state.characters[a])` — the whole character state, personality and voice included — into the
genesis, so a different derivation refuses the save (by design, C-3/C-10). The change's report wrongly said "personality is excluded
from the save's state digest" — true of `canonical_state` (`store.py:181`), not of `initial_digest`. No test caught it because every
persistence test creates its save with the engine under test.
**Fix.** (1) Keep the derived state as it was: `default_personality(...).voice = VoiceSpec(voice_register="plain")`. (2) Derive the
voice at render time instead: move `VOICE_*` and `default_voice` to `decision/voice.py` (decision may not import `solve`), and in
`turn.run_ask_turn` build `PersonaSlot(voice=voice_for(addressee, state.seed) if personality.voice == VoiceSpec(voice_register="plain")
else personality.voice)`. The voice never enters the fold or the digest, so old saves load again; the three test saves made today
(`voicetest`, `heardtest`, `topictest`) will then be refused — delete them. (3) Add a regression guard: commit a small save created by
the current engine under `tests/fixtures/saves/` and assert `Save.open` loads it and its `state_hash()` is unchanged; add a mutant that
changes any derived field. (4) Record in KNOWN-DEBT that any change to `new_session`'s derivation needs a migrator (C-10).

### NR-I1 — IMPORTANT — a reply with nothing to state can never pass the model verifier

**Evidence.** Live (Gemini): every claimless turn (DONT_RECALL / DONT_KNOW / REFUSE …) ran 3 generate calls and then the template
fallback; drafts were rejected `UNREFERENCED_ASSERTION` / `UNTAGGED_ASSERTION`. **Cause.** `SYSTEM_VERIFY`: "A segment whose kind is not
'assert' must assert nothing" — "I can't remember" is an assertion to the verifier. **Consequence.** (a) the call pattern and fallback
rate are act-correlated (claimless acts always cost 3 generates + fallback; a content act usually 1+1) — the F-7/H9-U1 timing channel,
now systematic; (b) the nightly's N-1 fallback rate is inflated by every claimless turn. **Fix.** Tell the verifier that a statement
only about the speaker's own memory, knowledge, feelings or willingness to answer ("I can't remember", "I'd rather not say") is not an
assertion; test it with a scripted verifier fixture and measure the claimless fallback rate live. Until then the stock line
(`decision.llm.CLAIMLESS_LINES`) is what players see.

### NR-I2 — IMPORTANT (gameplay) — generated cases have no "heard" memories, and almost no "did" memories

**Evidence.** Memory census (`new_session` on the sealed cases): `study_party_s4` At 143, NotAt 191, Saw 15, Did 3, Attitude 2,
**Heard 0**; `manor_wing_s4` At 221, NotAt 284, Saw 27, Did 3, **Heard 0**. **Consequence.** The question form's "what was heard" topic
(`game.TOPICS`) and the parser's `heard` hint can never get a substantive answer; "what was done" is mostly answered with whereabouts.
**Fix.** Either generate audible perceptions (`world/perception.py`: a `Heard` fact for events with a sound in earshot — the Phase 1
model already has `Heard`) and re-run the seed study, or drop `heard` from `TOPICS`/the parse prompt until cases carry it.

### NR-I3 — IMPORTANT (gameplay) — honest answers ignore the question's topic

**Evidence.** `study_party_s4`, David, `heard` 01:00–01:30 → VAGUE "I was in the guest room from 01:29 until 01:59"; `did` 00:00–00:30 →
VAGUE "I was in the library…". **Cause.** `minds.memory` retrieval scores topic tags as one cue among several and returns the best
memory even when its topic differs (ADR-30 gates LIEs only). **Fix.** When the question names a topic (`footprint.query_topic`), let
TRUTH/VAGUE use only memories of `TOPIC_KINDS[topic]` (fall through to DONT_RECALL otherwise); same verification as ADR-30 (V-7,
goldens, seed study).

### NR-I4 — IMPORTANT (gameplay) — each cover story has one lie

**Evidence.** Every sealed case: the murder secret's layer 0 is a single `DidNot`; other secrets a single `At`. Since ADR-30 a liar
asked off-topic gives a non-answer, never a topic-appropriate lie ("I heard nothing"). **Fix.** Cover synthesis (`gen/`) authors one
covering claim per topic the secret's protected footprint touches; V-3 must still pass; re-run V-7 and the seed study.

### NR-N1 — NON-BLOCKING — the time menus run past the end of the investigation

`solve.queries.clock_buckets` is `range(0, t_investigation // BUCKET + 1)`, so a case ending at 02:00 offers "02:00–02:30". A theory
or accusation window reaching past `t_investigation` passes the runner and is refused by the store's bounds check with the generic
"That could not be done. Nothing was recorded." (probe: "David was in the hall 00:00–02:30" on `study_party_s4`). **Fix.** Buckets
`range(0, ceil(t / BUCKET))` with the last one clipped; validate windows in `web.dispatch` against `t_investigation` and say why.

### NR-N2 — NON-BLOCKING — a busy or failing model looks like a broken game

A provider error (free-tier 503/429, timeout) shows "That could not be done. Nothing was recorded." **Fix.** For `PROVIDER_*`
rejections show an out-of-world "the model is busy — try again" (§14.2(i)'s retry notice; H9-N4 family).

### NR-N3 — NON-BLOCKING — the web server stalls during every model call

`web.py` handlers are `async` but run `game.ask` → urllib → model synchronously, and the latency floor uses `time.sleep`: the event
loop blocks 3–10 s per typed line; every other request waits. **Fix.** One dedicated worker thread per process for `dispatch` (so each
SQLite connection keeps its thread, D-5), `await anyio.to_thread.run_sync(..., limiter=one)`; or open the save per request.

### NR-N4 — NON-BLOCKING — the seed field accepts anything

`POST /new` accepts `seed=-5`, `10**30`, `2**63` (all created and opened). **Fix.** Bound to `0 <= seed < 2**31` in `new_game` and
`cli newsave`.

### NR-N5 — NON-BLOCKING — CLI tracebacks on ordinary mistakes

`eidolon newsave <bundle> <missing-dir>/x.db` → raw `sqlite3.OperationalError` (PN-8 family; `_run_newsave` catches `OSError`, not
`sqlite3.Error`). `_run_replay` imports `SaveError` and never catches it (pyflakes). **Fix.** Catch `sqlite3.Error` and `SaveError`,
print the JSON refusal.

### NR-N6 — NON-BLOCKING — free-provider transport hardening (`llm/provider.py`)

(a) `_http_post` reads the whole response before `strict_json`'s size cap applies — cap the read (e.g. `r.read(MAX_RAW_CHARS * 4)`);
(b) urllib follows redirects and re-sends the `Authorization` header — install an opener with no redirect handler; (c) the provider's
error text (≤ 300 chars) is printed to the operator's terminal — fine today, keep it out of anything the player page shows; (d) the
free-tier data-use terms (Gemini, Mistral) belong in the user-facing docs; (e) GitHub Models answers a bare `OK` from this network —
environmental, documented, not a code fault.

### NR-N7 — NON-BLOCKING — `clock_interval` ignores am/pm

"1pm" maps to 01:00. Harmless in night-time cases, wrong in principle. **Fix.** `pm` adds 12 h (then falls outside the night and gives
no window).

### NR-N8 — NON-BLOCKING — the free-text rate window grows without bound

`web.Chat.times[save]` appends every typed line and never prunes; `rate_window` is O(n). **Fix.** Drop entries older than
`RATE_WINDOW_S` on append.

### NR-N9 — NON-BLOCKING — two fallback voices

`validator._fallback_text` still returns `"..."` for a claimless plan, while `TemplateLLM` (the renderer's fallback) now speaks
`CLAIMLESS_LINES`. The validator path is not what players see for model renders, but two definitions of "the fallback" will drift.
**Fix.** Build `_fallback_text` from `TemplateLLM`, or delete it.

### NR-N10 — UNMEASURED — the offline audit may count the stock lines as findings

`debug.audit` runs a stronger verifier over committed statements; with today's `SYSTEM_VERIFY` it would flag "I'm sorry. I honestly
can't remember." as an unreferenced assertion, inflating N-5. **Fix.** NR-I1's verifier rule, or exempt template colour in the audit;
measure with the live nightly.

### NR-N11 — NON-BLOCKING — dead code

`pyflakes eidolon/`: 25 unused imports or locals, e.g. `validator.py` (`Segment`, `Ref`), `query.py` (`ActorId`, `TopicId`),
`secrets.py`, `lattice.py` (6 names), `fairness.py:263` builds a `FactIndex` it never uses (wasted work per V-6 run),
`pipeline.py:130` `secrets` unused, `cli.py:183` `SaveError`. Tests: ~76 unused imports, a dozen unused locals; one f-string without
placeholders (`tests/llm/test_llm_pipeline.py:424`). No test was found without an assertion (the AST scan's ten hits all assert through
helpers or tripwires). **Fix.** Remove; add `pyflakes` (or `ruff`) to the check list.

### NR-N12 — IMPORTANT (process) — no version control

The tree has no VCS. Every change is unrecoverable; reviews identify trees by ad-hoc manifests computed two different ways (RR-N1);
"nothing committed" appears in every report. **Fix.** `git init`, commit the current tree, tag the accepted phases' manifests, and run
the suite and harnesses in CI on every change.

### NR-N13 — NON-BLOCKING — dependencies are unpinned and one is deprecated

`pyproject.toml` pins nothing upper (`pydantic>=2.11`; `starlette`, `jinja2`, `uvicorn`, `httpx` bare). Starlette 1.3 warns that its
`TestClient` will drop `httpx` (`StarletteDeprecationWarning … install httpx2`) — the 147 Phase 8 and the Phase 9 web tests depend on
it. **Fix.** Pin tested versions (a lock or `==`), move to the supported test client, record the Python/OS matrix (only Windows +
3.12.10 is ever measured, F-12).

### NR-N14 — NON-BLOCKING — documentation drift

* `docs/EIDOLON-ARCHITECTURE.md` header: "Version 0.4", "Contains no production code", while its ADRs run to ADR-30 "(v0.7)" and its
  invariant table to I-58; `CLAUDE.md` calls I-1…I-48 "the contract".
* `CLAUDE.md`: the Phase 8 row still says "Phase 9 not started"; the "Tests — current baseline" paragraph splices two sentences
  ("a passing suite is **Phase 9 (2026-10-21)** adds 971 tests…"); the free-provider section says `test_free_providers.py` has 14 tests
  (19) and omits `GITHUB_MODELS_TOKEN` and the `github` provider's key; the read-first list now runs 0d, 0c, 0b, 0a, 0, 1 with
  overlapping "authoritative" claims.
* `docs/EIDOLON-KNOWN-DEBT.md`: the header says Phase 9 "awaits independent review"; ADR-30's open items (NR-I2…I4) and today's
  changes are not in it.
* `docs/EIDOLON-ADR-30-REPORT.md` repeats NR-B1's wrong sentence ("saves are unaffected").
**Fix.** One pass: bump the architecture version/status, fix the three `CLAUDE.md` passages, add a §G to KNOWN-DEBT for 2026-10-22.

### NR-N15 — NON-BLOCKING — clutter

`saves/` holds four test games from today's live checks; `out/` holds study outputs from before Phase 6's repairs. **Fix.** Delete or
move to a scratch folder; keep `saves/S.db` (the user's).

---

## 2. Recorded and still open — Phase 9 (observability, live validation)

| ID | Sev. | Finding | Fix |
|---|---|---|---|
| RR repair | — | RR-B1/RR-I1 repaired by the re-reviewer (`docs/EIDOLON-PHASE-9-RR-REPAIR-REPORT.md`) | independent re-review |
| H9-I3 (= F-3 = H8-N9) | IMPORTANT | CONFESSION is unreachable: no production caller passes `confession_check` | a `ConfessionCheck` running `solve.solver.evaluate` on `credited_material(state, only=presented)` passed by `game.ask`, plus a fold rule (C-1 (c)); handle Phase 4 N-2 (a peel onto a confession layer voiced as CONCESSION) in the same change |
| H9-U1 (⊇ F-7) | UNMEASURED | the 1.0 s latency floor cannot cover a live model; free models take 3–10 s | measure live p99 of the slowest call pattern and raise `LATENCY_FLOOR_S`, or pad per route; NR-I1 removes the worst act-correlated pattern |
| F-1 | exit criterion | every live-model metric UNMEASURED (no Claude key/SDK); free models are reported `free-model`/UNMEASURED by design | one live nightly with `--record` |
| F-2 | exit criterion | two external playtesters | two people, fresh save names, `slo` + `audit` |
| H9-N1 | NON-BLOCKING | `PromptLeak` traced as `provider_error` | map `"PROMPT_LEAK"` in `trace.failures_of` |
| H9-N2 | NON-BLOCKING | SLOs read foreign/stale trace rows | `Save.create` rotates an existing sidecar; filter rows by case + head |
| H9-N3 | NON-BLOCKING | trace write on the request path; a locked sidecar adds ≥ 5 s | short busy timeout on `_trace_insert` |
| H9-N4 | NON-BLOCKING | an engine exception is a bare 500, no aborted trace | catch in `dispatch`, note an aborted row, show the retry notice (with NR-N2) |
| H9-N5 | NON-BLOCKING | report says no prompt is stored; an echoing model's text is | correct the sentence |
| H9-N6 | NON-BLOCKING | T-25 workload too uniform | rotate subjects/places/buckets; stub defect rate grows with digest length |
| H9-N7 | NON-BLOCKING | corpus end-to-end arm uses one hostile draft | a model that obeys each line in kind |
| H9-N8 | NON-BLOCKING | debug `world?t=abc` → 500 | guard the `int()` |
| H9-N9 | NON-BLOCKING | nightly hard-codes `David`; exit 0 on partial measurement | pick the addressee from the case; exit non-zero when any metric is UNMEASURED in live mode |
| H9-N10 | NON-BLOCKING | the trace stores handles/hashes, not §27.1's ids/envelope | owner ratifies, or the debug process re-derives the envelope |
| RR-N1…N4 | NON-BLOCKING | manifest formats; unenforced personality range; N-5 note names the requested model; wrapped audit transport not forced to `AUDIT_MODEL` | see `docs/EIDOLON-PHASE-9-REPAIR-RE-REVIEW.md` §7 |
| F-4, F-6, F-8…F-13 | NON-BLOCKING | quote resolver absent; reveals slot vs view; debug CLI location; no prices (cost UNMEASURED); audit blind spots; debug server O(turns); cross-OS replay unmeasured; what a trace stores | as recorded in KNOWN-DEBT §F |
| F-14 | NON-BLOCKING | VAGUE/DONT_KNOW tie flips on the 2nd ask (≈1–4 % of weak answers certified "not a lie") | key `_tie_break` on the question (seed, speaker, query hash) and re-check V-7 |
| F-15 | NON-BLOCKING | `refuse_streak` never produced: a character refuses forever | produce the delta and honour the 2-turn cap |

## 3. Recorded and still open — earlier phases

**Phase 8 (player UI; not accepted).** Independent re-review of the H8 repair. H8-N1 (provisional accusation form fields unchecked
by the fold), H8-N2 (a typed line is parsed before the duplicate/stale/closed checks — check first), H8-N3 (free text can name only
addressee/visited/held while the page lists the cast — align the two), H8-N4 (a multipart file part gives 500 — reject non-string
fields), H8-N5 (no anti-framing header — confirmed again today: add `X-Frame-Options: DENY` and `Content-Security-Policy:
frame-ancestors 'none'`), H8-N6 (two guards without a killing test), H8-N7 (notebook O(theories × material) per render — cache by head),
H8-N8 (items renumber; §16.1 "plainly" warning missing; the time axis accepts the whole evening; a retry shows no projection),
H8-N10/E-8 (Phase 6 harness lacks `tail_ok`; H8-X2 room-without-edge oracle drift, strict xfail). D-1 (free text never measured on
Claude), D-2 (Starlette not FastAPI/HTMX), D-3 (no `SuspicionShift`), D-4 (no `Take` control), D-5/E-1 (one process, cached saves),
D-6/E-2 (same-id message), D-7 (exit on `study_party_s4`), D-8 (O(n²) tensions), D-9 (tie-break turn hazard), E-3…E-7.

**Phase 7 (persistence; accepted).** C-1 (a re-chaining forger can inject structurally valid but unearned peels, pressure, a fabricated
CONFESSION, a detective-model entry — by design §26.1; mitigate by server-side saves), C-2 (two float fields on the bp grid), C-3
(derived personalities bound into the genesis — NR-B1 is its first real casualty), C-4 (player text not logged), C-5 (11 event kinds
without producers), C-6 (trace sink accepts any dict; sidecar not bound to its save), C-7 (rollback journal, refusal says nothing —
PN-8), C-8 (truncation edge cases), C-9 (fold completeness by source inspection), C-10 (**no migrator**: any derivation change bricks
saves — build one before the next such change), C-11/F-12 (cross-machine replay unmeasured), C-12 (PN-1 tail removal via `meta`, PN-3
no `quick_check`, PN-4 alias/report not bound, PN-5 state hash not bound to case, PN-6 export edge cases, PN-8 raw SQLite errors),
F1-b/F1-c, the re-review's N-1/N-2/N-4/N-5/N-7 and F-2…F-9.

**Phase 6 (generation + solver; never independently accepted).** D-1 `Saw(nobody)` vs `NoStranger`; I-1 identified-voice exclusion
(unsound, verifier whitelist, untested); I-2 candidate domain from `Actor.role` (role metadata can hide a candidate); I-3…I-8 (D-1's ADR,
memory boosts at load — since applied by `new_session`, re-check and close, realised `EliminationStructure`, flavor slots/`Personality`
in the package — would also have prevented NR-B1, the general `requires`-token problem, `vance_v03` status); the 7 NON-BLOCKING; hard
difficulty exceeding the `2**10` robustness bound (fails closed); two admissibility functions (`decision.admissibility` vs
`solve.lattice`); lattice `requires` single-hop vs verifier recursive; I-10 presenting an undiscovered item can discover it; mutation
sweep and `PYTHONHASHSEED` determinism not re-run after the last generator changes.

**Phase 5 (LLM integration).** F-14 `earlier` never populated, F-15 no `Solution` branch in `render_claim`, F-16 `GuardedTransport._scan`
assumes JSON, F-17 no implementation-contract doc; live exit criterion (fallback < 5 % on 300 turns) unmeasured on Claude.

**Phase 4 (decision engine).** 17 IMPORTANT: review I-1, I-2, I-6…I-16 (in the review artifact), N-1 (set-valued event fields — now
canonicalised by the Phase 7 store; verify and close), N-3 (fail-closed livelock on a mis-authored cover — add the V-3 rule), N-4
(`corroborates()` treats required statements as leaves), N-5 (the endgame confession is question-shaped). N-2 (gate-open confession
voiced as CONCESSION) becomes live with H9-I3.

---

## 4. Recommended order

1. **NR-B1** — restore the user's save (render-time voice), add the committed-save regression test. Small, urgent.
2. **NR-N12** — put the tree under git before anything else changes.
3. **NR-I1** — the verifier rule for claimless replies (live-visible, a timing tell).
4. **H9-I3** with Phase 4 N-2 — wire the confession gate, so a playtest can end the designed way.
5. **NR-I2, NR-I3, NR-I4** — topic-strict retrieval, audible perceptions, per-topic covers; one change, verified like ADR-30.
6. The two independent re-reviews (Phase 8 H8 repair, Phase 9 RR repair, plus ADR-30 and today's changes).
7. NR-N1…N11, NR-N13, NR-N14 and the NON-BLOCKING lists, in any order.
8. Phase 9 exit: a live Claude nightly (F-1) and two playtesters (F-2); then Phase 10.
