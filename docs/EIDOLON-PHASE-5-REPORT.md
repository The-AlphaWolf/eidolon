# EIDOLON — Phase 5 Report: LLM integration + validation

Status: **implemented and verified on fakes; not yet exercised against a live model.**
Everything below that says "PASS" was demonstrated by a test in this repository that runs with no
network and no API key. The one thing that cannot be demonstrated here — behaviour against a real
model, including the roadmap's *fallback rate < 5 % on a 300-turn session* — is stated as
**NOT MEASURED**, not as passed.

Scope: exactly Phase 5 (§30). No case generation, solver, persistence or UI was built.

---

## Files created/changed

**Created — `eidolon/llm/`** (1 104 lines)

| File | Role |
|---|---|
| `provider.py` | `CompletionRequest`/`Completion`, the `Transport` port (`complete(request)` only), `AnthropicTransport`, `GuardedTransport` (prompt guard + call log), `LLMCallRecord`, error classes |
| `render.py` | `RenderView` (the LLM-facing envelope) + `build_view`/`serialize`, generator/verifier prompts and schemas, strict wire parsing, `ModelLLM`/`AnthropicLLM`, `NameBook`, `LLMRenderer` (repair → fallback → fail closed), `RenderAudit`, `PlayerTurn`/`player_view` |
| `ingress.py` | Stage 0 `screen`, stage 1 `PlayerAction` schema + `ModelParser`, stage 2 `ground`, `interpret` |
| `seal.py` | Deny-set compiler and seal-time guard for generation-time text (I-19) |
| `fakes.py` | `ScriptedTransport`, `RecordingTransport`/`RecordedTransport` (cassettes), `MutantLLM` (18 violation classes) |

**Created — `tests/llm/`**: `llm_helpers.py` and nine test files (367 tests, below).

**Changed (existing code)**

| File | Change |
|---|---|
| `eidolon/decision/validator.py` | New draft-level checks: time-slot on asserting segments, sincerity-blind length band (I-42), internal-identifier/engine-vocabulary leak, plan-claim omission, self-disclosure backstop; `verify` hook, run **last and only if every deterministic check passed**. `DRAFT_LEVEL_CODES` extended. |
| `eidolon/decision/turn.py` | A `Renderer` port (`RenderRequest`/`RenderOutcome`) on `run_ask_turn(renderer=…)`; any renderer exception aborts the turn (I-15); `TurnResult` gains `fallback`, `render_audit`. Default path (`renderer=None`) is unchanged. |
| `eidolon/decision/llm.py` | `LLMPort.generate(…, feedback=())`; `TemplateLLM` accepts and ignores it. |
| `eidolon/cli.py` | `play --llm` (live model through stages 0-2 and 7-9); `main(argv, transport=)` injectable. |
| `tests/decision/mutation_check.py` | Phase 5 mutant set (`M5`, 45 mutants); **baseline-must-be-green gate**; two Phase 4 mutant anchors updated (they matched lines this phase edited). |
| `CLAUDE.md`, `pyproject.toml` | State; optional `llm = ["anthropic"]` extra. |

No Phase 0.5–4 test file was modified. No Phase 4 assertion was weakened.

---

## Phase 5 components

```
player text
  └ stage 0  screen()            length/charset/rate; markers flag, never block; changes reported
  └ stage 1  ModelParser.parse   PlayerAction (closed schema, no irreversible variants)
  └ stage 2  ground()            names → ids the player may use; ambiguity/unknown → one generic reply
        │  Query
        ▼
  decision engine (Phase 4, unchanged, deterministic)  →  ResponsePlan
        ▼
  build_envelope → audit_envelope (Phase 4)  →  build_view → serialize   (LLM-facing, typed, pinned)
        ▼
  GuardedTransport.complete   ← last checkpoint before a prompt leaves the process
        ▼
  parse_draft (strict)  →  validate_draft (deterministic checks a→c, e→h)  →  verifier (LLM, last)
        ▼
  accepted | repair ≤ 2 | deterministic template render of the same plan | rejected (nothing committed)
        ▼
  run_ask_turn commits the PLAN's claims (never text-derived)  →  player_view(result) = text + ok
```

---

## LLM boundary

* **One vocabulary, no tools (I-11).** A model call is `Transport.complete(CompletionRequest)`. The
  request has five fields (`role, system, user, schema, max_tokens`) — nothing that could carry
  `tools`, `tool_choice`, MCP servers or search. Tests assert the dataclass fields, the protocol's
  only method, the exact keyword set handed to the SDK, and that no other file names the SDK call.
* **`AnthropicTransport`**: structured output via `output_config.format = json_schema`, effort from a
  constant per-route table (`parse: low, generate: medium, verify: low` — I-42), a constant cacheable
  system block, `stop_reason == "refusal"` → `ProviderRefusal`, timeouts classified, SDK imported
  lazily, default client built with `max_retries=0` so **every retry is ours, bounded and audited**.
* **The renderer sees a `RenderView`, not the engine.** 13 fields, pinned by test. It carries claim
  `id`, a neutral first-person `content` sentence, `modality`, `confidence`; the speaker's public
  voice; delivery; public facts; the display names the reply may use; the digest; the character's own
  earlier words; the player's line; the length window. It has **no field** for sincerity, source,
  grounding, act, secret, evidence, solution, layer, pressure, belief, knowledge or any deny-list.
* **Ports receive names, not the case.** `LLMRenderer` hands generator and verifier a read-only
  `NameBook` (id → display name) in place of the sealed `Case`. A port cannot reach the CaseLog,
  timeline, relationships or roles (`test_a_port_receives_names_and_nothing_else_of_the_world`).
* **The model chooses words only.** Act, claims, peels, retractions, confessions were fixed by the
  engine before rendering; the ledger commits **the plan's claims by id**, so nothing is ever read out
  of model text (ADR-9).

---

## Security/leakage controls

| Control | Where | Stops |
|---|---|---|
| Ingress: ≤ 1 000 chars (refused, never truncated), control/zero-width/bidi stripped **and reported**, rate limit (caller's count) | `screen` | payload smuggling; silent rewriting |
| Marker scan (NFKC-casefolded) → `meta` flag, escalates a query *toward* `meta` only | `screen`, `ground` | "ignore your instructions", role resets, engine probes |
| `PlayerAction` closed schema, `extra=forbid`, no proposition/evidence/claim fields | `ingress.py` | hidden-state injection through the parser (I-26) |
| Grounding: id / article-stripped name / alias / a token naming exactly **one known** entity; ambiguity → nothing | `_resolve` | name-guessing; cast enumeration (unmet-real and invented names get the identical reply) |
| Player text is a JSON *string value* in `player_query`, never structure; system prompt is constant | `serialize` | prompt-structure injection |
| Prompt guard on **every** route: refuses to send secret ids, undiscovered-evidence ids, act names, engine vocabulary. Player-typed text exempt. Deny-set is engine-side only. | `GuardedTransport` | envelope bugs; leaks the model never sees |
| Strict wire parse: exact keys, no duplicate keys, no NaN, bounded size/depth, NFKC, no control characters | `parse_draft` | schema abuse, tool-shaped output, unicode evasion |
| Entity allow-list (Phase 4 §14.2b) on **every** segment kind | `validate_draft` | invented/unpermitted names |
| Time slots: only the referenced claims' clock times; no other time expression in asserting segments | `slot_checks` | out-of-envelope times |
| Internal-identifier + engine-vocabulary check on spoken text | `internal_token_violations` | claim/secret/evidence ids, act names, "sincerity", "grounding"… |
| Self-disclosure backstop (confession phrasing outside `CONFESSION`; lie-tells outside concession acts) | `disclosure_violations` | "I killed him" in a `color` segment |
| Plan-claim completeness: every plan claim must be voiced | `omission_violations` | the model deciding what the ledger records |
| Verifier (LLM, **no envelope, no persona, no truth**), runs last, can only add violations | `ModelLLM.verify` | in-slot semantic drift, implicature |
| Repair feedback never carries an engine identifier or a reason | `repair_feedback` | echoing hidden vocabulary back to the model |
| Canary in the system prompt; regurgitation refused | `SYSTEM_GENERATE`, `lexical_guard` | prompt extraction |

---

## Validation model

Draft-level failures (the renderer's fault, cured by repair then the template): `FORBIDDEN_VOCAB`,
`CANARY_LEAK`, `UNKNOWN_ENTITY`, `UNTAGGED_ASSERTION`, `CLAIM_ID_NOT_IN_ENVELOPE`, `SLOT_MISMATCH`,
`TIME_SLOT_MISMATCH`, `COLOR_CARRIES_CONTENT`, `QUESTION_*`, `NONVERBAL_LEAK`, `UNAUTHORIZED_CLAIM`,
`INTERNAL_TOKEN_LEAK`, `LENGTH_BAND`, `PLAN_CLAIM_OMITTED`, `SELF_DISCLOSURE`, and the verifier's
`ASSERTS_NOT_EXACTLY`, `EXTRA_ASSERTION`, `UNREFERENCED_ASSERTION`, `MODALITY_MISMATCH`.

Plan-level failures (`SOLUTION_LEAK`, `UNKNOWABLE_CLAIM`, `FOREIGN_PROTECTED`, `CONTRADICTS_PRIOR`,
`JOINTLY_INFEASIBLE`, `HYPOTHETICAL_STATED_AS_ACTUAL`): no rendering can repair them — the turn is
**rejected**, never falls back (Phase 4's B-1, re-verified through this pipeline).

Order matters and is tested: all deterministic checks first; the verifier only if none fired. A
lenient verifier therefore cannot rescue a bad draft — for 100 % of the attacks it is never called.

---

## Failure/fallback model

| Event | Behaviour | Player sees |
|---|---|---|
| Draft-level violation | repair (feedback = what was written, never why), regenerate; ≤ 2 repairs | nothing until it passes |
| Repairs exhausted / repeated invalid output | **template render of the same plan**, through the same validation | the dull-but-valid line (indistinguishable, I-12) |
| Refusal (`stop_reason: refusal`) | a renderer failure: asked again, then template | as above |
| Malformed / truncated / oversized / non-schema output | `MALFORMED_OUTPUT:<code>` → same as a draft-level failure | as above |
| Generation **timeout** or provider error | **fail closed**: rejected, nothing committed, no retry inside the turn | out-of-world "try again" |
| Verifier timeout / malformed verdict | fail closed | out-of-world "try again" |
| Plan-level violation | rejected | out-of-world "try again" |
| Prompt would carry an engine identifier | call never made; rejected | out-of-world "try again" |
| Any exception anywhere in a renderer | rejected (`RENDERER_EXCEPTION:<type>`) | out-of-world "try again" |

Bounds: ≤ 1 + `max_repairs` (3) generation calls and ≤ 3 verifier calls per turn; a valid reply that
arrives on the fourth attempt is never requested. Retries mutate nothing: the caller's state is the
same object after any failure (asserted by identity and by fingerprint). A latency floor (injected
clock) holds every outcome — accepted, fallback, rejected, timeout — to the same minimum time.

Every attempt is recorded in `RenderAudit` (outcome, violations, the draft, per-call role / effort /
prompt hash / tokens / latency). It is engine-side; `PlayerTurn` is `{text, ok}` only.

---

## Tests

`tests/llm` — **367** tests, no network, no key.

| File | Tests | Covers |
|---|---:|---|
| `test_llm_ingress.py` | 75 | screening, injection markers (13 + 10 negative controls), parser schema, malformed queries (12), grounding, hidden-state injection through the real parse path, ambiguity, aliases |
| `test_llm_view.py` | 31 | view schema pin, byte-identical prompts across sincerity/source/grounding/act, leak detection, guard, serialization round-trips, verifier isolation, effort constancy, Hypothesis property over random plans |
| `test_llm_provider.py` | 21 | SDK request shape (no tools), effort per route, refusal/timeout classification, no hidden retries, lazy SDK, cassettes, layering, no randomness, no SDK at module level |
| `test_llm_pipeline.py` | 63 | accepted, determinism vs the Phase 4 path, replay/fold, repair, bounds, fail-closed (generation/repair/verifier), refusal, malformed outputs, plan-level rejection, latency floor, audit, player projection, equal-length, modality classes |
| `test_llm_adversarial.py` | 124 | 54 attacks × 2 assertions + wire-schema exactness + hostile-port and injection-through-data tests |
| `test_llm_mutants.py` | 43 | `MutantLLM` catch rate per class; plan-level classes |
| `test_llm_cli.py` | 5 | `play --llm` end to end over a scripted transport |
| `test_llm_determinism.py` | 2 | decision state across processes/hash seeds; independence from wording |
| `test_llm_seal.py` | 3 | I-19 |

**Oracles are independent of the code under test:** hand-written token lists and field sets; the
Phase 4 `TemplateLLM` path (a separate implementation) for "what the engine decided"; scripted
verifier responses; and a *worst-case verifier that approves everything*.

**Mutation verification** (`python -m tests.decision.mutation_check phase5`): 45 mutants — every
Phase 5 guard has one — **45 / 45 killed, baseline green**. The harness now refuses to report unless the
unmutated baseline is green (see "What testing found").

---

## Adversarial tests

54 named attacks, each run against a verifier that approves everything, and each judged against the
same turn on the Phase 4 path: nothing hostile shown or stored, engine state equal to the baseline,
committed claims equal to the plan's, caller's state untouched, model called exactly 3 times, verifier
called **zero** times. Categories:

* **Hallucinated entities (12):** invented person / place / object, near-match (`Davidson`), accented
  (`Émile`), substring collision (`David Kesslerman`), alias to an entity not permitted this turn,
  zero-width-split name, Cyrillic homoglyph, fullwidth name, a known person not permitted on this turn,
  another character's protected fact, cross-character knowledge.
* **Engine leakage (14):** solver, secret id, undiscovered evidence id, fabricated evidence id,
  another turn's evidence, internal metadata, provenance, sincerity label, sincerity lie-tell, state
  transition named in text, act names, canary, meta text, fullwidth engine vocabulary.
* **Fabricated / unauthorized claims (4):** fabricated id, another layer's claim, stale (retracted)
  claim, claim omitted to dodge a concession.
* **Confession / solution (3):** in a `color` segment, without the gate, for the wrong suspect.
* **Schema / tool-shaped output (12):** wrong act at top level and in a segment, forbidden
  `sincerity` field, tool-call object, state object, incidentals, fenced JSON, truncated JSON,
  duplicate-key smuggling, 20 000-deep nesting, 40 000-char output, control characters — plus a
  separate test that an otherwise **perfect** reply with one extra field is refused (so the schema
  check, not the omission check, is what refuses it).
* **Time (4), mislabelled content (3), length fingerprint (1), injection reaching the model (1).**
* **Not "bad text":** provider timeout; a valid reply that arrives after the bound; provider
  disagreement (verifier objects every time); a lenient verifier that cannot rescue a bad draft; a
  port that mutates the frozen envelope; a port handed only names; a port returning a non-`Draft`; a
  renderer that raises anything; prompt injection inside **evidence text** (never reaches the model)
  and inside the character's **own earlier statements** (stays a JSON string; an obeying model is
  still stopped).

`MutantLLM` catch rate: **18 / 18 classes, 100 %**; 16 with a verifier that approves everything
(including the three v0.3 classes, where the verifier is never even called); 2 (`tense/negation
inversion`, `unreferenced implicature`) are caught by the verifier only, and the test says so.

---

## Full suite

```
python -m pytest -q                                        # 1027 passed  (= 660 + 367)
python -m pytest tests/llm -q                              # 367   Phase 5
python -m tests.decision.mutation_check                    # 57 killed, 2 equivalent (unchanged; two anchors updated)
python -m tests.decision.mutation_check phase5             # 45 / 45 killed (Phase 5 set)
```

## Previous-phase regression

```
python -m pytest tests/world -q                                    # 98   Phase 1    unchanged
python -m pytest tests/minds -q                                    # 77   Phase 2    unchanged
python -m pytest tests/evidence -q                                 # 169  Phase 3    unchanged
python -m pytest tests/test_important.py tests/test_repairs.py -q  # 136  repairs     unchanged
python -m pytest tests/decision -q                                 # 180  Phase 4    unchanged
python -m pytest spike/test_spike.py -q                            # 21   Phase 0.5  unchanged
```

Baseline before this session, reproduced first: **660 passed** (59 s). Long-session stress at the
literal 2 000-turn / 50-accusation scale on the (unchanged) default path: **passed** (2 tests, 610 s — run concurrently with the mutation sets, so slower than the 153 s of the Phase 4 report; all assertions held: zero peels, flat envelope, replay equal).

---

## Determinism

* **Separated.** Deterministic state = act, claims committed, layer peels, retractions, character,
  epistemic and discovery state, turn counter. Non-deterministic = `Statement.text` only.
* **Proven three ways.** (1) Same turn through the Phase 4 template path and through the LLM path with
  three different wordings: identical fingerprints; only text differs. (2) A multi-turn session with a
  concession, and a session in which the model fails every third turn (fallback): identical to the
  all-template run, turn for turn. (3) Cross-process: identical decision digests under
  `PYTHONHASHSEED` 1/2/3, and identical across wordings; folding the recorded events reproduces the
  same statements and peels (I-22: replay never re-runs the renderer, strategy or model).
* No `random`/`secrets`/`uuid` in `eidolon/llm` (static test, I-6); no wall-clock read except through
  an injected clock in `LLMRenderer`.
* The architecture specifies no seeded generation for the live model (I-5's own text: live play is
  not reproducible, its outputs are recorded). Cassettes (`RecordingTransport`/`RecordedTransport`)
  keyed by prompt hash replay a live run in CI; a changed prompt is a hard miss.

---

## Acceptance criteria

| Criterion | | Evidence |
|---|---|---|
| Stage-0 screening exists | **PASS** | `screen`; 75 ingress tests; mutants P5-26…29, 33 killed |
| Structured rendering envelope exists | **PASS** | `RenderView`, schema pinned; 31 view tests + Hypothesis property; P5-20 killed |
| LLM provider boundary exists | **PASS** *(on fakes)* | `Transport`/`AnthropicTransport`/`GuardedTransport`; 21 provider tests. The SDK call is verified against a duck-typed client only — see deviations |
| LLM output validation exists | **PASS** | strict parse + `validate_draft` + verifier; 43 mutant tests; P5-8…11, 35…42 killed |
| Leak checks exist | **PASS** | prompt guard on every route, spoken-text token/vocabulary checks, Phase 4 §14.2(e); P5-4, 5, 22, 23, 38, 42 killed |
| Entity checks exist | **PASS** | Phase 4 allow-list reused on all segment kinds; 12 entity attacks incl. accented/substring/alias/homoglyph/fullwidth |
| Fallback behaviour is safe | **PASS** | bounded, audited, fail-closed table above; state identity asserted after every failure; P5-12…15, 24, 43 killed |
| Honest/deceptive constraints satisfied | **PASS** | byte-identical prompts across sincerity/source/grounding/act (example + Hypothesis); same length band; constant effort; latency floor; sincerity-blind verifier; P5-3, 16, 37 killed |
| Deterministic state separate from wording | **PASS** | see Determinism |
| All Phase 0.5–4 regressions pass | **PASS** | numbers above |
| Adversarial tests pass | **PASS** | 54 attacks, 100 % contained |
| No forbidden hidden information crosses the renderer boundary | **PASS**, scoped | What crosses is the audited envelope's claims, authored public voice/delivery, digest, the character's own words and the player's line. Engine ids and vocabulary are checked at the transport; ports get names only. *Residual:* authored persona/delivery strings and the digest are content, trusted after Phase 4's audit |
| Roadmap exit: `vance_v03` playable with the live model; fallback < 5 % on 300 turns | **NOT MEASURED** | no key or network in this environment. `play --llm` is wired and tested over a scripted transport; the demo case (not `vance_v03`, which has no covers until Phase 6) is what it plays |
| Roadmap: injection corpus v1 ≥ 100 | **NOT MET** | 24 player-side injection prompts + 54 model-side attacks (~ 80 distinct hostile inputs); Phase 9's target is ≥ 200 |

---

## Architecture deviations

Nothing contradicts an invariant. These are places where Phase 5 delivers less than, or differently
from, the roadmap text:

1. **Live model never run.** `AnthropicTransport`'s request shape (`output_config.format`,
   `effort`, `cache_control`) follows the SDK documentation and is verified only against a
   duck-typed fake. First live contact may need adjustment (e.g. schema keyword support).
2. **No per-character voice-variant fallback** (§33.2 #7, roadmap deliverable). One template family;
   the fallback is a text a careful player could learn to recognise. Needs authored voice content.
3. **Repair calls use the `generate` effort (`medium`), not `low`** (§14.3). Constant effort per
   route is the property I-42 needs; the cost difference is untested.
4. **No server-side model fallback on refusal** (F-11's mitigation). Refusal → repair → template.
5. **Incidental claims (§14.4) not implemented**: the wire schema has no `new_incidentals` field, and
   a model that sends one is refused.
6. **Verifier does not emit typed implicature flags**; it reports extra/unreferenced assertions.
7. **Parser emits no `presupposes` or `quoted_statement`, and time phrases are not resolved to
   intervals** (`TimePhrase.interval` stays `None`); `TimeAnchor` content is Phase 6.
8. **Injection corpus below ≥ 100** (above).
9. **`MutantLLM` is draft-level.** The classes "contradiction with a prior claim", "hypothetical
   stated as actual" and "jointly infeasible" are plan-level and are tested as plan scenarios
   (they cannot be produced by a draft).
10. **`envelope_tokens` (I-7 budgets) not measured**: there is no tokenizer here; slot caps from
    Phase 4 bound the view structurally.

**Limits that follow from the design, not from a shortfall, and that a live model will exercise:**

* Lowercase invented common nouns ("the orangery") and spelled-out times in a `color` segment
  ("around ten") are not deterministically detectable; they are the verifier's. A `color` segment
  can carry implicature ("some people can't be trusted"); `MutantLLM` shows a blind verifier lets it
  through. Least privilege (the model is never told anything to insinuate) is the defence (§33.3).
* A verifier that is itself prompt-injected by a `color` segment is a residual with a real model.
* **The Vance fixtures' `Alias` table is empty**, so a live model writing "Elena" instead of "Elena
  Ruiz" is an unknown entity and falls back. The prompt lists the exact display names; the
  fallback-rate SLO will be dominated by this until Phase 6 authors aliases.
* The self-disclosure backstop is a narrow lexical net (a dozen phrasings), not a proof.

### What testing found (and was fixed in this phase)

Ten defects surfaced by the tests themselves, each now pinned:
`you are now …` marker missed (the spec's own example); polarity read as a modality mismatch; repair
feedback echoed engine tokens back at the model (the guard refused, aborting the turn); the guard's
vocabulary forbade a legitimate view key (`modality`); ports were handed the whole sealed `Case`
(now a `NameBook`); a `color` segment could confess ("I killed him") — no deterministic check saw it;
player wording ("David", "the kitchen") did not ground; schema abuse was masked by the omission check
(now tested independently); NFKC normalization was unpinned (fullwidth clock times and words); and
the mutation harness reported "all killed" against a red baseline — it now aborts on one.

---

## Deferred Phase 6 work

Only what §30 assigns to Phase 6: skeletons and cast/layout instantiation; the timeline planner in
production; **cover synthesis** (including authoring the `Alias`/`TimeAnchor` tables the parser and
lexical guard resolve against); red herrings; distortion assignment; the discovery-graph builder;
**flavor-slot calls with checks** (§18.4); the real solver V-5 with robustness runs and
absence-fragility (which is what wires `run_ask_turn(confession_check=…)`, I-21); fairness
metrics/bands (V-6); the bots V-7 including the bluff bot; sealing + report (the Sealer that calls
`eidolon.llm.seal`, I-19); `eidolon gen` / `eidolon validate`.
