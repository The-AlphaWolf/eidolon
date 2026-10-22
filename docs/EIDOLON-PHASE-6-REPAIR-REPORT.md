# EIDOLON — Phase 6 blocker repair report

**Scope: the four BLOCKING findings of the independent hostile review, and nothing else.**
The eight IMPORTANT findings (I-1…I-8) and the seven NON-BLOCKING ones are untouched and still
open; D-1 (`Saw(nobody)` vs `NoStranger`) is deliberately **not** fixed here — it is IMPORTANT,
it needs an ADR on the closed proposition schema, and Phase 1 semantics were not altered.
Phase 7 was not begun.

| Blocker | Audited defect | State |
|---|---|---|
| **B-1** | V-7 bots absent; the bluff bot — a named Phase 6 exit criterion — was `evaluate(ctx, {})` | **repaired**, six engine-driven bots |
| **B-2** | Cover synthesis absent; the murderer's layer 0 had **no derivable breaker set**; V-3 ran 1 of its 5 checks | **repaired**, real `check_cover_consistency` in the pipeline |
| **B-3** | Bands computed, never gated; no §20.2 loop; `study_party` could not reach its declared band | **repaired**, band gated + loop + skeleton retuned |
| **B-4** | `verify_proof` accepted a proof with its exclusions deleted | **repaired**, candidate domain checked |

Headline numbers, all measured in this session:

| | before | after |
|---|---|---|
| Phase 6 tests | 126 | **194** |
| Seed study, 2×50, one attempt per seed | 97/100 sealed, **47/100 in band** | 96/100 sealed, **96/100 in band** |
| `derive_breaker_sets` on the murderer's layer 0 | `[]` | `[{E_trace, clean@<housekeeper>}]` |
| Real V-3 violations on a sealed case | 3 | **0** |
| Truncated-proof attacks rejected | 0 / 3 | **3 / 3** |
| V-7 bots on the real engine | 0 of 6 | **6 of 6** |
| Phase 6 mutation set | 49 | **66** |

---

## B-1 — V-7 bots

### Root cause
§19.7 names six bots and §30's Phase 6 line makes one of them an exit criterion ("the bluff bot
fails to converge on every sealed case"). None existed. What shipped was `fairness.bluff_converges`
= `evaluate(ctx, {}).unique` — the solver on an empty material set, which has no time pin, so the
window is the whole evening and every candidate survives. The function could not return `True` on
a well-formed case, which the project's own first mutation run had already demonstrated (mutant F4
replaced its body with `return False` and **survived**).

The deeper problem is that a material-level proxy cannot see the property I-40 exists for.
§19.7's bluff bot records *response classes*: it tests whether a character's behaviour under
pressure leaks what they are hiding (§6.5 response parity, §22.3 hidden-state leakage). No function
of the material set can observe that. It needs turns.

### Implementation
New module `eidolon/solve/bots.py` (≈330 lines). Every bot drives the real `decision.turn`
pipeline with `TemplateLLM` — a real `Query`, real strategy selection, the real envelope audit,
the real validator, real committed statements, real `LayerPeel` events.

* **`build_state(pkg)`** turns a sealed package into a playable `GameState`: Phase 2 derives
  knowledge/beliefs/memories from the CaseLog, Phase 3 supplies the discovery fold, Phase 4 the
  statement ledger. The package still carries no `Personality` (that is audit finding I-6, out of
  scope here), so the harness supplies a deterministic one derived from `sha256(case|actor)` and
  says so in the docstring — nothing is written back into the package.
* **Acquisition model.** A bot holds only what it obtained: evidence discovered through Phase 3's
  `DiscoverySpec`/prerequisite machinery, and testimony atoms obtained by *asking*. The pool it
  can ever draw from is `robust_material` — the layer-0 fixpoint — so nothing inside a
  secret-holder's protected interval can be extracted by asking (I-45). A question that names
  nothing yields nothing (§20.1 item 5: no load-bearing fact arrives by a character volunteering
  it).
* **Determinism.** `random` is banned outside `gen/` (I-6), so every "random" choice is
  `sha256(seed|key)`. Verified identical under `PYTHONHASHSEED` 0 and 777.

| Bot | §19.7 requirement | What it does |
|---|---|---|
| **greedy** | searches everything, asks every template question, presents every item; solves within `N_max` | discovers in prerequisite order, asks the full template set per character, presents every held item; then the solver runs on **its** acquired set |
| **random** | uniform random valid actions; measures how often the proof core is stumbled on | hash-driven choice over ask/search/goto/present; reports which proof-core items it happened to acquire |
| **adversarial** | 500 odd questions per character before any evidence; zero `LayerPeel`, zero leaks, bounded tokens | hypothetical/opinion/smalltalk/narrative/recall/meta/coercion cycle; asserts no peel, no protected proposition ever committed, envelope under a constant ceiling |
| **order-shuffled** | random discovery orders; solver-equivalent end state | three hash-shuffled discovery orders; survivors/unique/bins/corridor compared |
| **cue-following** | never enumerates; only cued actions; **runs the solver on its own acquired set**; within `N_cue` | maintains a `named` set seeded per §19.4 (body, murder room, exterior accesses, interrogable cast) and grows it only from held material; skips any item whose cue is unnamed |
| **bluff** | 500 bluffs, presents nothing, records response classes, **must fail** | see below |

**The bluff bot.** Premises are drawn from the case's protected facts and physical details and put
as `Query.presupposes` — §12.2/I-25's implicit `Present` carrying zero evidential weight. They come
in **matched pairs**: two questions identical in kind, subject, location and hint, differing only in
whether the premise is true of the speaker, **both run from the same state** so that state drift
cannot masquerade as a leak. Two measurements:

* **convergence** — is the murderer the unique argmax of "tells" (`SLIP`, `CONCESSION`,
  `CONFESSION`, `STONEWALL`, `ANGER`, `REFUSE`, `DEFLECT`, `EVASION`, `ACCUSE_DETECTIVE`)? If yes,
  the case is solvable by bluffing and V-7 rejects it.
* **parity** — does the act differ between the two halves of a pair? §6.5 says it must not.

### Tests
`tests/solve/test_blocker_repairs.py`, 18 bot tests. The load-bearing ones:

* `test_B1_bluff_bot_FIRES_on_a_case_a_bluffer_could_solve` — the measurement is **not vacuous**.
  Drop the murderer's layer-0 `resolve` to zero and any bluff peels them: the tell lands on exactly
  one character, `converged=True`, `argmax == [murderer]`, and V-7 would reject the case.
* `test_B1_cue_following_bot_does_not_solve_a_case_whose_core_it_cannot_cue` — take the containment
  log's cue away and the bot stops short. It is not a formality.
* `test_B1_bots_never_hand_a_bot_material_a_suspect_would_withhold` — I-45 holds through the bot's
  acquisition path; the murderer's protected testimony is never obtainable.
* `test_B1_adversarial_bot_context_does_not_grow_with_turn_count` — I-7 in its sharp form: the same
  case at two scales, maxima compared.
* `test_B1_bluff_bot_REPORTS_a_parity_break_when_one_happens` — added after mutation R5 survived: in
  the shipped engine the premise's truth never reaches the strategy layer, so no real run can break
  parity, and asserting `parity_ok` on real cases cannot tell a working check from a deleted one.
  The bot is driven through a stub that answers the two halves differently.
* `test_B1_bluff_bot_fails_a_case_whose_covers_peel_under_pure_bluffing` — added after mutation R6
  survived: peels are their OWN failure condition. The fixture peels every cover (so the tells point
  at nobody and the bot does not converge) while conceding only non-protected claims (so nothing
  leaks), leaving the peel as the only thing the verdict can rest on.

### Bot results
Reduced scale (in the suite) and full scale (§19.7's own numbers, run once for this report):

**Full scale**, §19.7's own numbers — 500 bluffs and 500 odd questions per character, every golden
case, `TemplateLLM`, no model calls:

| case | bot | actions | peels | rejected | verdict |
|---|---|---|---|---|---|
| study_party s4 | bluff | **2 000** | 0 | 0 | no convergence, parity holds, no leak |
| study_party s5 | bluff | **2 000** | 0 | 0 | same |
| manor_wing s4 | bluff | **2 500** | 0 | 0 | same |
| manor_wing s6 | bluff | **2 500** | 0 | 0 | same |
| study_party s4 | adversarial | 2 000 | 0 | 0 | no peel, no leak, envelope bounded |
| study_party s5 | adversarial | 2 000 | 0 | 0 | same |
| manor_wing s4 | adversarial | 2 500 | 0 | 0 | same |
| manor_wing s6 | adversarial | 2 500 | 0 | 0 | same |
| study_party s4 / s5 | greedy | 126 / 131 | 0 / 1 | 0 | solved, survivor = the canonical murderer |
| manor_wing s4 / s6 | greedy | 172 / 172 | 1 / 2 | 0 | solved |
| study_party s4 | cue-following | 148 | 0 | 0 | solved inside `N_cue` = 400 |
| manor_wing s4 / s6 | cue-following | 267 / 267 | 0 | 0 | solved inside `N_cue` |
| all four | order-shuffled | 3 orders | 0 | 0 | identical survivors / bins / corridor |
| all four | random | 150 | 0-1 | 0 | deterministic; reports the proof-core items it stumbled on |

**24 of 24 bot runs OK.** Cost: 48–59 s for a 2 000–2 500-turn bluff run, 25–35 s for the
adversarial run, under 3 s for the rest.

The bluff bot's own numbers on `study_party` seed 4, 500 bluffs per character:

```
tells   : {David: 0, Elena: 0, Margaret: 0, Robert: 0}      <- nobody tells
argmax  : [David, Elena, Margaret, Robert]                  <- so the argmax is everybody
acts    : David    {DONT_RECALL: 164, LIE: 336}
          Elena    {DONT_RECALL: 186, LIE: 314}
          Margaret {DONT_RECALL: 166, LIE: 334}
          Robert   {DONT_RECALL: 184, LIE: 316}
parity  : no break in 1 000 matched pairs
peels   : 0     leaks: 0     converged: False
```

Note the honest limit of that result: in the shipped engine the premise's truth never reaches the
strategy layer, so parity holds *structurally* — which is why the parity check is proved live by a
stub that forces a break (mutation R5), not by the real run alone.

Greedy's 1–2 peels are legitimate: the greedy bot *presents evidence*, and a peel under evidence is
the engine working. Zero peels is required of the bluff and adversarial bots, which present nothing.


---

## B-2 — cover synthesis and the real V-3

### Root cause
Two independent failures that masked each other.

1. **The generator authored stubs.** Every secret got a two-layer cover: a layer-0 lie and a
   terminal with **no claims**, no `EvidenceResponse`s, no breaker sets. §18.3 stage 7 asks for
   layers derived until V-3's contract holds; none of that existed.
2. **The pipeline ran 1 of V-3's 5 checks** — `check_monotone_concedes` — while Phase 4 already
   shipped the whole checker (`decision.cover_consistency.check_cover_consistency`).

Running the real checker on a sealed case returned 3 violations, and `derive_breaker_sets` returned
**nothing at all for the murderer**: the case was formally unique and conversationally unbreakable.

The mechanism behind that empty set is D-2's runtime half. `E_trace`'s only implication is
conditional on `requires=("clean@<housekeeper>",)`. The solver's `lattice._resolve` understands that
token (`<event>@<actor>` → that actor's own `Participated` perception), but Phase 3's runtime gate,
`unlocked_implications`, checks `ref in known_ids`, where the ids are evidence ids and heard
statement ids. `clean@Elena` was neither, so the trace could never unlock in play, never carried
weight, and no subset of material ever reached the layer's `resolve`.

### Implementation
* **Pre-authored statements.** `CasePackage` gains `statements: tuple[Statement, ...]` and the
  generator emits the accounts the covers rest on (`gen/compile.py::_statements`). The statement's
  id **is** the `requires` token, so one token resolves in both worlds — `lattice._resolve` matches
  it against the speaker's perception, `unlocked_implications` matches it against a heard statement.
  Its `grounding` is the speaker's real `KnowledgeEntry`, so `claim_admissibility` walks a true
  chain (I-27); V-3 rejects a statement whose grounding does not resolve rather than letting the
  admissibility walk raise (fail closed, I-15).
* **Real covers** (`_murder_cover`, `_innocent_cover`). An innocent's layer 0 is a counterfactual
  whereabouts contradicted outright by `E_secret_<a>`; layer 1 is the terminal that concedes it,
  with claims. The murderer's layer 0 denies ever handling the weapon — refuted by
  `{E_trace, clean@<hk>}`, which is §20.1 item 6 made operational — and layer counts follow §20.2's
  `Cover layers (murderer)` row: easy 2, standard 3. Every item of the intended breaker set carries
  an `EvidenceResponse`.
* **I-21 respected.** With two layers, layer 0 *is* the pre-terminal layer, and its breaker proves
  handling, never the blow — so a confession reached from it would be cheaper than a proof. A
  two-layer murderer cover therefore terminates in a **stonewall**; that murderer is convicted by
  elimination or not at all. A three-layer cover may confess, because its pre-terminal layer has no
  breaker set and nothing reaches the terminal for free.
* **The pipeline runs the contract.** `v3()` now calls `check_cover_consistency(..., murder_check)`
  — all five checks including joint layer-0 feasibility (I-28) and the murder pre-terminal
  uniqueness test (i) — and keeps Phase 6's own grounding checks (protected facts true in the log,
  layer-0 claims false).
* **One check added beyond the contract.** §19.3 check (iii) demands a breaker set for *innocents*;
  nothing demanded one for the murderer. V-3 now does, because that is exactly the audited defect
  and V-6's `2_lies_breakable` does **not** catch it — that proxy asks whether some admissible
  implication contradicts the lie, not whether any presentable subset reaches the layer's `resolve`.
  `test_B2_removing_the_murderers_breaker_is_rejected_by_V3` asserts both halves: V-3 rejects, and
  the V-6 proxy would have passed.
* **Refuter reachability** (requirement 3). `fairness.breakers_reachable` checks every evidence item
  in a derived breaker set against Phase 3's own cued-reachability report, and every statement
  against §19.4's "obtainable by asking" reading (its speaker must still be interrogable). Wired
  into V-4.
* **No solver truth.** `gen/compile.py` imports no solver, proof or fairness module — asserted by
  `test_B2_cover_synthesis_reads_no_solver_verdict`. The breaker is chosen from the world the
  planner built; V-3 confirms or rejects it.

### V-3 results
On all four golden cases, `check_cover_consistency` returns **zero** violations, and the murderer's
layer-0 breaker set is non-empty and contains `E_trace`:

```
S_David    layer 0 -> [['E_trace', 'clean@Elena']]      (was [])
S_Elena    layer 0 -> [['E_secret_Elena']]
S_Margaret layer 0 -> [['E_secret_Margaret']]
S_Robert   layer 0 -> [['E_secret_Robert']]
V-3 violations on a SEALED Phase 6 case: 0               (was 3)
```

V-3 stage cost: 0.57 s / 2.16 s / 0.88 s / 3.30 s on the four goldens. V-4 checks 5–6 breaker refs
per case.

### Generated-case evidence
All 96 sealed cases of the seed study passed V-3's real contract (it is the `cover_valid` column of
the funnel below, and a V-3 failure stops the package).

### Tests
`tests/gen/test_covers_and_bands.py`, 27 V-3/cover tests, including the requested regressions:
removing the murderer's breaker (V-3 rejects), removing an `EvidenceResponse` (V-3 rejects), a cover
that lies about nothing (V-3 rejects), a statement whose grounding does not resolve (V-3 rejects,
does not raise), layer 1 never an empty dead end, and the `requires` token resolving on both paths.

---

## B-3 — difficulty-band gating

### Root cause
Two separate things, and the report conflated them.

1. **V-6 computed bands and never gated on them.** `metrics()["bands"]` was reported; nothing
   compared it to `pkg.difficulty`. A package whose band was literally `None` on every knob sealed.
2. **`study_party` could not reach its declared band.** Its proof cores measured 5 items (49 seeds)
   or 6 (1 seed) where the easy band is 3–4, so 0/50 were in band. §20.2's loop alone would have
   spun 20 times and reported, because the *structure* fixed the core size: with 4 suspects, three
   innocents each needed their own elimination, and 2 + 3 = 5.

### Band correction — **option A (retune), not option B (reclassify)**
Reclassifying `study_party` as standard would have required a fifth cast member (standard =
5–6 suspects), which makes it a second `manor_wing` and leaves v1 with no easy skeleton at all.
Retuning is both smaller and architecturally sanctioned, because §18.2's `EliminationStructure`
already contemplates the alternative it needs: an innocent is covered either by a corroborator
outside their collusion component **or by an L3 presence pin over the window**.

So the easy skeleton gets one room-level device log. New skeleton knob `shared_alibi_log: bool`;
`study_party` sets it. `E_alibi_room` is a single L3 item whose implications place **every** innocent
in the alibi room over `[t_m ± 8]`, which makes one item the elimination for all of them:

```
proof core, study_party seed 4:
  before  ['E_alibi_Margaret', 'E_gate_Gazebo', 'E_watch', 'S:P0235', 'S:P0236']   (5, easy band is 3-4)
  after   ['E_alibi_room', 'E_gate_Gazebo', 'E_watch']                             (3, in band)
```

`manor_wing` keeps per-innocent eliminations and stays at 6, inside the standard band's 5–6. The
knob is therefore §20.2's `Proof-core size` row made real, not a fudge: it is the lever that moves
a skeleton between bands. The red herring's refuter follows it — with a shared log the herring
points at `E_alibi_room`, and §19.6's "the herring must actually mislead" check still passes,
because withholding the shared log leaves its target unplaced.

11 band tests. `test_B3_study_party_reaches_the_easy_proof_core_band_by_construction` asserts both directions:
the knob on, the core is 3–4; the knob off, the same seed fails V-6 on `proof_core`.

### Retry behaviour
`generate_in_band(skeleton, seed, max_attempts=20)` implements §20.2 literally. Each attempt uses a
**derived** seed (`sha256("band|seed|attempt")`), every attempt's stage and reason is recorded, and
the result carries `attempts`, `seeds`, `rejections` and `in_band`.

Only V-6 **band** failures are retried. Everything else keeps its own rule, and the loop stops and
reports: a planner or physics failure as before, and a V-5 failure on a realised structure because
I-43 forbids reseeding a skeleton defect away. Verified on the four seeds the study rejects — all
four stop after **one** attempt:

```
study_party_s10: ok=False attempts=1 stage=V-5   band_problems=[]
manor_wing_s10 : ok=False attempts=1 stage=V-6   band_problems=[]   (red herring, not band)
manor_wing_s13 : ok=False attempts=1 stage=V-6   band_problems=[]
manor_wing_s29 : ok=False attempts=1 stage=V-5   band_problems=[]
```

`eidolon gen` runs the loop (Phase 6 exit: "produces sealed, **in-band** cases"); `--attempts 1`
asks for the single-attempt primitive.

### 2×50 seed study
`run(range(0,50), workers=3)`, both skeletons, **one attempt per seed, no retry** — the same
protocol as the original study, now with the band as a gate.

| stage (execution order) | study_party | manor_wing |
|---|---|---|
| seeds attempted | 50 | 50 |
| planner realised the structure | 50 | 50 |
| schema-valid (V-0) | 50 | 50 |
| physically valid (V-1) | 50 | 50 |
| knowledge sound (V-2) | 50 | 50 |
| **covers valid (V-3, the real contract)** | 50 | 50 |
| solver-unique + judged correct (V-5) | 50 | 50 |
| proof verified independently | 50 | 50 |
| robust to every distortion subset | 49 | 49 |
| reachable, cued, askable (V-4) | 49 | 49 |
| **fairness + band (V-6)** | 49 | 47 |
| simulation (V-7) → **sealed** | **49** | **47** |
| **in band** | **49 / 49** | **47 / 47** |

**96/100 sealed, 96/100 in band** (before: 97/100 sealed, **47**/100 in band). Retries used: 0 —
no seed failed for a band reason, so the loop never fired. That is the honest reading: the retune
removed the band failures at the source and the loop is insurance, proved by test rather than by
the study.

Rejections, all correct and at the stage that owns the defect:

| seed | stage | reason |
|---|---|---|
| study_party 10 | V-5:robust | uniqueness fails for 2 of 4 distortion subsets |
| manor_wing 10 | V-6 | `E_secret_Delphine`: already excluded without the refuter, so it misleads no one |
| manor_wing 13 | V-6 | `E_secret_Beatrix`: same |
| manor_wing 29 | V-5:robust | uniqueness fails for 4 of 8 distortion subsets |

`study_party` seed 10 is new: the shared alibi log changed the material, and this seed's distortion
set now breaks uniqueness on 2 of 4 subsets. A correct rejection, reported not reseeded.

Cost: 357 s wall on 3 workers; 6.2 s/case mean for `study_party`, 15.0 s for `manor_wing` under
contention.

---

## B-4 — proof candidate-table completeness

### Root cause
`verify_proof` iterated `proof["candidates"]` and checked every row it was handed. It never asked
which rows were **missing**. The audit's three attacks all verified clean: one excluded candidate
deleted, that row plus its constraints deleted, and — the sharpest form — a proof listing only the
survivor, asserting a unique murderer with no exclusions in it at all. The report's step 6
("`unique` follows from 3–5") is true only given a complete candidate table, which was the one
thing not checked.

### Verifier correction
`solve/proof.py::candidate_domain_complete` derives the candidate space from the package using
§19.5's own definition — "candidates = every interrogable non-victim actor",
`pkg.case.living_actors()` — and requires the table to be **exactly** it: nothing missing, nothing
extra, and no survivor named outside it. Called from `verify_proof` before anything else uses the
table.

Independence is preserved exactly as it was. `proof.py` still imports no solver function, reads no
`.solution`, and re-checks every core with the independent oracle; the AST tests that enforce all
three still pass. The new check reads one world-layer accessor on the package, the same kind of read
`_feasible` already makes for `pkg.case.locations`.

This does **not** close audit finding I-2: the candidate domain is still derived from the authored
`Actor.role` field, so an `offstage` label still hides a physically viable suspect from the whole
pipeline. That is IMPORTANT, not BLOCKING, and it stays open by instruction.

### Tampered-proof tests
`tests/solve/test_blocker_repairs.py`, 12 tests:

| attack | before | after |
|---|---|---|
| a proof from the live builder (all 4 goldens) | verifies | verifies |
| one excluded candidate row deleted | **ACCEPTED** | rejected, names the missing actor |
| that row **and** its constraints deleted | **ACCEPTED** | rejected |
| survivor-only proof (every exclusion deleted) | **ACCEPTED** | rejected, names all three |
| an extra candidate the case does not contain | accepted | rejected |
| a candidate renamed (identity tampering) | accepted | rejected as both a gap and an intruder |
| a survivor outside the domain | accepted | rejected |
| the candidate table reordered | verifies | verifies (order-insensitive) |
| no candidate table at all | crash | rejected |

Every pre-existing proof-tampering test (dropped constraint, forged survivor, false constraint,
wrong package, non-minimal core, infeasible core, outsider verdict, seal) still passes unchanged.

---

## Mutation

Protocol unchanged: each mutation is a list of exact `(relpath, old, new)` replacements, each `old`
must occur **exactly once** (checked before every run — all 66 anchors verified), it is applied to a
fresh copy of the tree, the unmutated baseline must be green first, and a mutant is KILLED iff the
selected tests fail.

### Phase 6 — the set grew from 49 to 66

17 new mutants, one per decision the four repairs introduced:

| id | mutation | result |
|---|---|---|
| R1 | (B-4) the verifier does not check the candidate domain | KILLED |
| R2 | (B-4) a missing candidate row is tolerated | KILLED |
| R3 | (B-4) an extra candidate is tolerated | KILLED |
| R4 | (B-1) the bluff bot never converges | KILLED |
| R5 | (B-1) the bluff bot ignores response parity | KILLED |
| R6 | (B-1) the bluff bot ignores layer peels | KILLED |
| R7 | (B-1) a bot is handed material it never acquired | KILLED |
| R8 | (B-1) the cue-following bot ignores cues | KILLED |
| R9 | (B-1) a question that names nothing yields everything | KILLED |
| R10 | (B-2) V-3's real contract is not run | KILLED |
| R11 | (B-2) the murderer needs no breaker set | KILLED |
| R12 | (B-2) a statement's grounding is not checked | KILLED |
| R13 | (B-2) breaker items need not be reachable | KILLED |
| R14 | (B-3) the band is reported, not gated | KILLED |
| R15 | (B-3) every knob is in band by definition | KILLED |
| R16 | (B-3) the band loop reseeds a non-band failure too | KILLED |
| R17 | (B-3) the band loop gives up after one attempt | KILLED |

**The history matters more than the final line.**

| run | suite | result |
|---|---|---|
| 1 (all 66, first) | 191 tests | **63 killed, 3 SURVIVED** — R5, R6, R13 |
| 2 (the 3, after closing tests) | 194 tests | 2 killed, 1 survived (R6) |
| 3 (R6, fixture rebuilt) | 194 tests | R6 killed |
| 4 (final, all 66, clean, one piece) | **194 tests** | **66 killed, 0 survived, 0 equivalent, 0 error, 0 timeout** |

All three survivors were real gaps in the code this repair added, and **no production code was
changed to make a mutant die**:

* **R5** — `parity_ok` was asserted only on real runs, and in the shipped engine the premise's truth
  never reaches the strategy layer, so no real run can break parity. Deleting the comparison changed
  nothing observable in the suite. Closed by driving the bot through a stub that answers the two
  halves of every pair differently.
* **R6** — the first fixture peeled every cover by dropping `resolve` to zero, but a peel onto a
  layer that concedes protected facts also LEAKS, so `ok` was already False for the other reason and
  the `peels == 0` term was untested. Closed by rebuilding the fixture so the conceded claims are
  non-protected: peels without leaks, so the peel is the only thing the verdict can rest on.
* **R13** — no test made a breaker item unreachable. Closed by gating an innocent's revealing item
  behind a kit item no case contains: still derived as the breaker set, now unreachable, V-4 rejects.

`EQUIVALENT` is empty for Phase 6: nothing was declared equivalent to avoid writing a test.

### Phase 4 and Phase 5 — re-run, unchanged

Neither set's anchors touch `solve/` or `gen/`, and all 130 of them still match exactly once, but
they were re-run rather than asserted:

| set | result | recorded baseline |
|---|---|---|
| `python -m tests.decision.mutation_check` | 57 killed, 2 equivalent — **PASS** | 57 killed, 2 equivalent |
| `python -m tests.decision.mutation_check phase5` | 70 killed, 1 equivalent — **PASS** | 70 killed, 1 equivalent |

### What the four blocker-specific claims rest on

| claim | mutant(s) | test that kills it |
|---|---|---|
| **B-1 the bluff bot is not vacuous** | R4, R5, R6 | `test_B1_bluff_bot_FIRES_on_a_case_a_bluffer_could_solve`, `..._REPORTS_a_parity_break_when_one_happens`, `..._fails_a_case_whose_covers_peel_under_pure_bluffing` |
| **B-2 V-3 checks breaker/EvidenceResponse completeness** | R10, R11, R13 | `test_B2_removing_the_murderers_breaker_is_rejected_by_V3`, `test_B2_removing_an_evidence_response_is_rejected_by_V3`, `test_B2_an_unreachable_breaker_item_is_rejected_at_V4` |
| **B-3 out-of-band cases cannot seal** | R14, R15 | `test_B3_an_out_of_band_case_cannot_seal`, `test_B3_every_sealed_case_is_in_its_declared_band` |
| **B-4 incomplete proofs cannot verify** | R1, R2, R3 | `test_B4_a_deleted_candidate_row_is_rejected`, `..._a_survivor_only_proof_is_rejected`, `..._an_extra_candidate_is_rejected` |


---

## Regression

```
python -m pytest -q                                       2194 passed in 416.7s
python -m pytest spike/test_spike.py -q                     21 passed        Phase 0.5
python -m pytest tests/world -q                             98 passed        Phase 1
python -m pytest tests/minds -q                             77 passed        Phase 2
python -m pytest tests/evidence -q                         169 passed        Phase 3
python -m pytest tests/decision -q                         180 passed        Phase 4
python -m pytest tests/llm -q                             1340 passed        Phase 5
python -m pytest tests/test_important.py tests/test_repairs.py -q
                                                           136 passed        cross-phase
python -m pytest tests/solve tests/gen -q                  194 passed        Phase 6 (126 + 68)
```

`2194 = 98 + 77 + 136 + 169 + 180 + 1340 + 194`.

| | PASS/FAIL |
|---|---|
| Phase 0.5 | **PASS** (21/21) |
| Phase 1 | **PASS** (98/98) |
| Phase 2 | **PASS** (77/77) |
| Phase 3 | **PASS** (169/169) |
| Phase 4 | **PASS** (180/180) |
| Phase 5 | **PASS** (1340/1340) |
| Phase 6 | **PASS** (194/194) |

**No existing assertion was weakened to make the suite green.** Four pre-existing tests changed, each
because the world they are built on changed and the test's INTENT needed restoring, not relaxing:

* `test_N1_multiple_valid_murderers_is_rejected_at_V5` and
  `test_verifier_re_derives_the_uniqueness_claim_V4` used `blind_everyone` to produce a case with
  several possible murderers. Blinding the cast no longer does that on `study_party`, because the
  room-level alibi log is physical, not perceived. A new helper `unalibied()` blinds the cast **and**
  removes the presence pins — restoring the property the fixtures were asserting.
* `test_verifier_flags_a_core_that_is_not_actually_infeasible_V3` picked "any other constraint about
  X" as a harmless one; with everyone in one alibi room, every hard constraint about an innocent
  excludes them. It now picks explicitly — a constraint whose interval misses the murder window —
  which is a stronger statement of the same test.
* `blind_everyone` now RE-GROUNDS the pre-authored statements against the edited CaseLog instead of
  dropping them (knowledge ids are positional), so an edited fixture still reaches the stage it
  exists to exercise.

Two files were renamed/added rather than edited: `tests/gen/test_blocker_repairs.py` became
`tests/gen/test_covers_and_bands.py` (pytest rejects two test modules with the same basename in
rootdir-relative packages).

Golden cases were regenerated (`python -m eidolon.gen.golden`) — they are machine-generated
artifacts, and the covers, statements and alibi log changed their seals. Each one re-validates from
disk, its recorded proof re-verifies, and regeneration reproduces seal and proof byte for byte.

**Determinism: PASS.** Identical package seals, proof cores and statement tables for both skeletons
under `PYTHONHASHSEED` ∈ {0, 1, 12345, 777}, in separate processes; identical bot reports
(bluff/greedy/cue-following) under 0 and 777.


---

## Hostile self-check

The eleven attacks the repair brief names, re-run against the repaired tree:

| # | attack | result |
|---|---|---|
| 1 | build a case with two possible murderers | rejected at V-5 (`test_N1`, `unalibied` fixture) |
| 2 | hide the second candidate through role metadata | **still succeeds** — audit finding I-2, IMPORTANT, out of scope, open |
| 3 | delete an excluded proof candidate | rejected by `verify_proof` (B-4) |
| 4 | remove the murderer's breaker set | rejected at V-3 |
| 5 | remove an `EvidenceResponse` | rejected at V-3 |
| 6 | seal an out-of-band easy case | rejected at V-6 with the numbers in the reason |
| 7 | 500 bluffs with zero evidence | no convergence, no peel, no leak, parity holds |
| 8 | cue-following bot on only what it acquired | solves inside `N_cue`; fails when the core is uncued |
| 9 | reverse evidence/event ordering | verdict unchanged |
| 10 | swap actor ordering | verdict unchanged |
| 11 | `PYTHONHASHSEED` 0 / 1 / 12345 / 777 | identical seals, identical proof cores, identical bot reports |

Attack 2 is the one that still works, and it is left working on purpose: it is finding I-2, the
brief says not to fix the IMPORTANT list, and fixing it would change the candidate domain that B-4
now pins the proof to.

---

## Final tally

```
Full suite:                       2194 / 2194

Phase 0.5:  PASS (21)             Phase 3:  PASS (169)      Phase 6:  PASS (194)
Phase 1:    PASS (98)             Phase 4:  PASS (180)
Phase 2:    PASS (77)             Phase 5:  PASS (1340)

V-3 on generated cases:           96 / 96 sealed cases pass the REAL contract, 0 violations
V-7 bots:                         PASS   24 / 24 full-scale runs across 4 golden cases
500-bluff:                        PASS   2000-2500 turns/case, 0 peels, 0 leaks, no convergence
Cue-following:                    PASS   solves on its own acquired set (148 / 267 actions)
Difficulty-band gate:             PASS   out-of-band cases rejected at V-6
2x50 seed study:                  96 / 100 sealed, 96 / 100 IN BAND      (was 47 / 100 in band)

Proof verification
  valid generated proofs:         4 / 4 goldens + 96 / 96 study proofs
  truncated-proof attacks:        9 / 9 rejected  (3 / 3 of the audit's own)

Mutation
  Phase 4:                        57 killed, 2 equivalent          PASS
  Phase 5:                        70 killed, 1 equivalent          PASS
  Phase 6:                        66 killed, 0 survived, 0 error   PASS
  blocker-specific (R1-R17):      17 / 17 killed

Determinism:                      PASS

BLOCKING remaining:   0
IMPORTANT remaining:  8
NON-BLOCKING:         7
```

## What this repair did NOT touch

* **D-1** `Saw(nobody)` vs `NoStranger` — documented, carried forward, Phase 1 semantics unchanged.
* **I-1** the identified-voice exclusion (unsound rule, verifier whitelist, untested).
* **I-2** the candidate domain derived from `Actor.role`.
* **I-3**…**I-8**: D-1's ADR, memory-boost application at load, the realised `EliminationStructure`,
  flavor slots / `Personality` in the package, the general `requires`-token problem (only the
  `clean@<hk>` path was fixed, because B-2 required it), `vance_v03`'s status.
* The seven NON-BLOCKING findings.
* Phase 7.

**BLOCKING remaining: 0. IMPORTANT remaining: 8. NON-BLOCKING: 7.**
