# EIDOLON — Phase 6 report: case generation + solver

**Status: implemented and self-verified (tests, an independent oracle + proof verifier, a mutation set); NOT yet independently reviewed.**
Phases 0.5–5 are untouched in behaviour; two Phase 1 files gained additive changes (§Files). Phase 6 is scoped
exactly as briefed: generator + solver + proof + validation pipeline. No UI, no persistence, no new LLM behaviour.

Bottom line, in numbers (all measured in this session, on this machine, no network, no API key):

| | |
|---|---|
| Full suite | **2126 passed** (2000 prior + 126 Phase 6); `spike/test_spike.py` 21 passed |
| Seed study, 2 skeletons × 50 seeds, **no retry, no reseed** | **97 / 100 sealed** (study_party 50/50, manor_wing 47/50) |
| Of the sealed, strictly in the skeleton's declared difficulty band | 47 / 97 (manor_wing 47/47; study_party 0/50 — proof core is 5, easy band says 3–4) |
| Independent verifier on every sealed case's proof | 97 / 97 verified (also re-run in tests on the 4 golden cases from disk) |
| Mutation set (Phase 6), final clean run on the final code + 126 tests | **49 killed, 0 survived, 0 equivalent, 0 error** (0 timeout-kills) — after the first run **let 20 of 48 survive** (§12) |

## 0. What was found before coding (and the map)

* `docs/EIDOLON-IMPLEMENTATION-CONTRACT.md` — named as an authoritative source in the brief — **does not exist in the
  repository.** I worked from `CLAUDE.md`, `EIDOLON-ARCHITECTURE.md` (§18 generation, §19 validation, §20 fairness, §30
  roadmap, invariants I-27, I-34, I-37, I-39, I-40, I-43…I-48) and the phase reports. If the contract carries constraints
  the architecture does not, they were not applied.
* Production had **no V-5 solver, no planner, no seal**. `decision/solver.py::unique()` is the scoped opportunity check
  Phase 4 needed (its own docstring says so). The only validated solver was the Phase 0.5 spike (`spike/solve.py`,
  `spike/minds.py`, `spike/gen.py`), on a throwaway dataclass model. Phase 6 **ported the spike's validated primitives onto
  the production models** rather than writing a second design; the differences are listed in §Solver architecture.
* Phase 6 acceptance criteria are §30 Phase 6 (deliverables, tests, exit) plus §19 (V-0…V-8), §20.1 (fairness contract),
  §19.5 (uniqueness, robustness), and the brief's own list. Every one is graded in §Acceptance.

## 1. Files created / changed

Created (production, 1 800 lines):
`eidolon/solve/{package,lattice,solver,oracle,proof,distort,fairness}.py`,
`eidolon/gen/{skeletons,planner,compile,pipeline,study,golden}.py`.
Created (tests, 1 900 lines): `tests/solve/{helpers,test_oracle,test_solver,test_bruteforce_case,test_negative_fixtures,test_selfcheck_and_lattice,test_independence_and_fairness,test_mutation_gaps,mutation_check}.py`,
`tests/gen/{test_generator,test_golden}.py`.
Generated data: `cases/generated/*.json` (4 golden packages + proofs), `out/*.json` (study/mutation logs, not part of the repo contract).

Changed (additive, all regressions green):

| File | Change | Why |
|---|---|---|
| `eidolon/world/feasibility.py` | `_dp` is now a thin wrapper over `_search`, which additionally returns a witness **path** and accepts a `goal` location | the solver's proofs carry witness walks and the phantom must END at `EXT`; one DP, not two. The 98 world tests + Hypothesis-vs-brute-force properties guard it |
| `eidolon/world/perception.py` | `derive_perception` is memoised (8 most recent cases, identity-keyed) | it was recomputed ~25× per candidate (12 s of a 39 s case); a `Case` is immutable (I-4) and the derivation pure (I-5/I-6), so a hit equals a rerun |
| `eidolon/cli.py` | `eidolon gen`, `eidolon validate` | roadmap §27.3/§30 Phase 6 |

## 2. Generator architecture

`Skeleton` (mechanics + role slots) + `seed` → `plan()` → `Draft` → `compile_draft()` → **sealed `CasePackage`**
→ `finalize()` (bounded distortions, I-39 memory boosts) → `validate()` (V-0…V-8). Generation is **compilation**:
the planner emits typed `Event`s (`Stay`, `Attack`, `Die`, `Clean`, `Speak`), a `Case`, an evidence table with
`DiscoverySpec`s, `Secret`s with protected facts, motives, relations, a `CanonicalSolution` and a *declared*
`EliminationStructure`. There is no free-text stage; names come from the skeleton's table.

The planner is the Phase 0.5 **constructive** design (I-43): it does not search for uniqueness, it realises the declared
structure — (a) one alibi room for every innocent over `[t_m ± 8]`, (b) protected intervals ≥ 12 min clear of `t_m`
and ≥ 6 min clear of every other forced window, (c) a self-grounding containment log at every exterior access,
(d) collusion consulted when lovers/shared secrets are placed, (e) an L3 time pin (`Die` timepiece), (f) the
housekeeper's ≥ 8-minute pinned stay with the clean event ≥ 2 minutes inside it. A seed whose structure cannot be
realised returns `Draft.error` and is **reported** (`planner` in the funnel), never repaired.

Two skeletons (`study_party`: 4 suspects, easy; `manor_wing`: 5 suspects, standard, discovery chain depth 3). Both are
blunt-force in a private room with one exterior access that no cast member ever visits (see §Deviations D-1).

Determinism: `random.Random(seed)` inside `gen/` only (I-6, checked statically over the package by test); every
choice is drawn from a **sorted** sequence; flavor-level picks use `sha256(seed|key)`, not RNG state. Tested: same seed
→ byte-identical package in process; same seal across processes under `PYTHONHASHSEED` 0 / 1 / 12345 / 777 (plan +
compile, and the full `generate` including the solver-derived boosts). Mutants D1 (unseeded), D2 (set iteration),
D3 (id()-ordered pick) attack exactly this.

## 3. Solver architecture

`solve/` reads a `CasePackage`. It never imports `gen/` (AST test), nothing below it imports it (AST test), and the
canonical solution is read in exactly **one** function, `judge()`, after the verdict (AST test). The verdict is a
function of `(Case, evidence, secrets)` alone: scrambling `solution`, `structure`, `alternatives`, `load_bearing`
leaves the verdict JSON byte-identical (test).

* `lattice.py` — the §19.5 per-claim admissibility lattice, ported from the spike. Testimony atoms come from the
  validated Phase 1 `derive_perception` (it carries the observer's presence segment and granularity, which
  `KnowledgeEntry` drops). L3 = authentic evidence whose interval **production P-9** (`established_interval`)
  establishes; L2 = perception-grounded testimony whose speaker's presence is fixed **tick by tick** (I-44) by L3
  material or an independent, non-colluding, provenance-disjoint source (I-37, via `SecretStore.collusion_edges`), or
  which is itself directly corroborated; L1 = single testimony; planted evidence and `InvestigationTold` chains are
  never admissible. Every secret-holder is stuck at layer 0 (their protected-interval knowledge is withheld), uniformly —
  the solver is never told who the murderer is.
* `solver.py` — V-5. Candidates = every interrogable non-victim actor; `Outsider` is a **reachability query**
  (`outsider_path`: a phantom starts at `EXT`, is in the murder room in the window, ends at `EXT`, through no cell the
  admissible containment material blocks); exclusion cores are deletion-minimal; the layer-0 **fixpoint** (I-45) cracks
  an excluded innocent's secret in the next round; `proof_core` is 1-minimal (chunked deletion).
* `distort.py` — memory distortions (§8.7) and the **subset** robustness run (§19.5).
* `oracle.py` — independent feasibility algorithms (§Proof model).
* `fairness.py` — V-4, V-6, the V-7 material proxies, absence-fragility, bands.

Differences from the spike (deliberate): production types; the production P-9; real `Secret`/`SecretStore` collusion;
`Heard(attack)` windows and an identified-voice exclusion; fail-closed classes; the sub-40-tick window bound made explicit.

## 4. Constraint / search approach

Per candidate, "can X have been in the murder room in the window, given every admissible constraint about X?" is a
**reachability problem over (location, tick, existential-bitmask)** with universal presence (`At`) as forced cells,
`NotAt` as blocked cells, `Did/Saw/Heard` as existential visits, and the travel graph's edge times as the transition
relation — solved **exactly** by the production layered DP (`world.feasibility._search`). Chosen because it is the
machinery Phase 1 already validated (I-28), the domain is tiny (≤ 8 rooms × 120 ticks × ≤ 2¹⁰ masks), and it is exact, so
there is no heuristic to audit. No SAT/SMT/CP framework: nothing here needs one, and adding one would add a second
semantics to keep in step with `feasible()`. The bounded domain is stated in the module docstring and in §Uniqueness.

## 5. Canonical solution model

`CanonicalSolution`: murderer, victim, method, weapon, location, interval, murder event id, motive kind, the
murderer's **approach** interval (opportunity), the **opportunity witness**, the load-bearing evidence ids, the critical
constraints (`time_pin:`, `opportunity:`, `containment:`), and one **declared alternative** per innocent + the outsider
(`reason`, `material`). It is enough to check the intended murderer, the timing, the opportunity and every alternative —
and it is *declared, never trusted*: the solver re-derives every one of those from the world.

## 6. Proof model

`build_proof` writes `eidolon.proof/1`: seal, fairness level, cracked set and rounds, the murder window, **every hard
constraint** with its item, kind, level and sources, per candidate either a deletion-minimal exclusion core or the
ticks it admits, the containment blocks behind the outsider verdict, the proof core, the distortion-robustness result and
the absence-fragility report.

`verify_proof` re-checks it **without calling `solve`** (AST test forbids `solve/evaluate/robust_material/proof_core/
feasible_actor/actor_core` and any `.solution` read in it):

1. the seal matches the package; 2. **truth audit** — every constraint at or above the fairness level is TRUE in the
canonical CaseLog (a lattice bug that promoted a false claim is caught here, not by the solver); 3. every core is
infeasible under `oracle_feasible` — a different algorithm from the solver's DP (arrival-jump DFS, no transit-state
machine) — and deletion-minimal; 4. every survivor's times equal the oracle's feasible ticks; 5. the outsider verdict
re-derived by the oracle over the recorded blocks; 6. `unique` follows from 3–5. Three implementations of one
question — DP, oracle, exhaustive enumeration — agree under Hypothesis (`test_oracle.py`) and on whole small cases
(`test_bruteforce_case.py`). Tampering with a proof (dropped constraint, false constraint, forged survivor, wrong package)
is caught (`test_proof_verifier_catches_tampering`; mutants V1–V6).

## 7. Uniqueness guarantee — sound / complete / bounded

* **SOUND.** `unique=True` ⇒ every non-survivor has a deletion-minimal core that both the DP *and* the independent
  oracle find infeasible; the outsider corridor is closed under the oracle; every admissible constraint used is true in the
  canonical world (truth audit); one time bin remains. The solver may reject a case a richer model could prove unique;
  it never accepts a non-unique one within its model.
* **COMPLETE only over the bounded domain**: candidates = interrogable non-victim actors + the outsider (as
  reachability); location = the body's; time = a window ≤ 40 ticks (wider ⇒ reported "no time pin", not approximated);
  one method per skeleton; fairness level `standard` (L3 ∪ L2). **Outside it the answer is "not unique" (fail closed,
  I-15)**: `MethodSpec.admits` = Accident/Suicide, an `accomplice` relation, no victim, no body location.
* **Known incompleteness (sound direction)**: candidates are tested independently; "someone else must have been in the
  room" is not used to exclude a candidate, so a case can be *more* unique than the solver proves.
* Distortion robustness is exhaustive over **active** distortions (≤ 10; more ⇒ `bounded`, singletons + extreme +
  leave-one-out only). Observed: the 4 golden cases have 0–2 active distortions (1–4 subsets, never `bounded`); the one study
  case whose subset count is on record, seed 29, had 3 active (8 subsets, 4 failing). The study rows do not store `bounded`, so I
  make no claim about it across all 97.

"Uniqueness" is never "the solver found no other solution": it is a checked set of infeasibility cores + a closed corridor
+ one bin, and the negative fixtures (§Negative fixtures) show each way of getting it wrong being rejected.

## 8. Solvability / fairness — three layers, three verdicts

* **Formal** (V-5): unique + judged against the canonical solution + proof verified + robust to every distortion subset.
* **Human** (V-4): the proof core lies on a **fully-cued** path (`evidence.discovery.reachability`, exterior accesses in
  the initial named set, I-47); load-bearing items and red-herring refuters reachable; every proof-core *testimony* is
  retrievable at `strong` (I-39) once the generator's recorded `memory_boosts` are applied (`test_retrieval_expressibility_
  needs_the_generators_memory_boosts_I39`: without the boost the check fails — Phase 2's salience×decay puts co-presence
  memories at ≈ 0.3–0.45 < 0.55).
* **Fair** (V-6, §20.1 items 1, 2/6, 3, 4, 8, 9, 10): nothing rests on the survivor's word about their own secret; every
  secret's layer-0 lie has an admissible refuting item (the murderer's "I never touched it" is refuted by `E_trace`, whose
  `requires` chain reaches L2 — item 6); every red herring's refuter exists **and the herring actually misleads** (§19.6
  first half: its target is still a live suspect without the refuter — this rejected 2 of 100 study cases); distortions
  are subset-robust; the proof core is cued; a **bluff converges only if `evaluate({})` is unique — it is not** (material-level
  proxy for I-40).

A formally unique case that fails V-4/V-6 is rejected at its own stage (`test_N3` shows a formally unique case with an
unreachable proof item failing at V-4). Items 5 (no volunteered facts — the parser-expressibility half) and 7 (planted
items, accident/suicide) are partly vacuous in v1: no skeleton emits planted evidence or admits accident.

## 9. Generation yield — the seed study (actual numbers)

`python -m eidolon.gen.study --seeds 50` — 2 skeletons × 50 seeds, **each seed attempted once**, no retry, no reseed
(`--retries` exists; no planner or physics failure occurred, so it would not have changed a number).

| stage (execution order) | study_party | manor_wing |
|---|---|---|
| seeds attempted | 50 | 50 |
| planner realised the structure | 50 | 50 |
| schema-valid (V-0) | 50 | 50 |
| physically valid (V-1) | 50 | 50 |
| knowledge sound (V-2) | 50 | 50 |
| covers/secrets valid (V-3, structural) | 50 | 50 |
| **solver-unique + judged correct (V-5)** | 50 | 50 |
| **proof verified independently** | 50 | 50 |
| robust to every distortion subset | 50 | 49 |
| reachable, cued, askable (V-4) | 50 | 49 |
| fairness contract (V-6) | 50 | 47 |
| simulation proxies (V-7) → **sealed** | **50** | **47** |
| **yield** | **1.00** | **0.94** |
| strictly in the declared band | 0 | 47 |

Failures by validator stage (all three are *correct rejections*, none an infrastructure error): `V-5:robust` ×1
(seed 29: "uniqueness fails for 4 of 8 distortion subsets"); `V-6` ×2 (seeds 10, 13: "E_secret_X: X is already excluded
without the refuter, so it misleads no one"). No seed failed physics, knowledge soundness or uniqueness.

Reading this honestly: yield ≈ 97 % is at the top of the Phase 0.5 prediction ("constructive planner: near 100 %"), so it
is **not** a surprise, and the roadmap's rule applies — "a run between 30 % and 90 % is a skeleton defect report"; this one is above.
It also means the funnel is dominated by the *constructed* structure; the value of the numbers is that the independent
verifier and the mutation set (§Mutation) show the checks would have caught a broken structure, not that the structure is hard to make.

**Band fit is a real gap.** `min_depth` and the red-herring count are tuned by the skeleton knobs (`chain_depth`, per-band
count); the **proof-core size is not**: study_party's proof cores are 5 items (49×) or 6 (1×) where the easy band is 3–4, so
0/50 are strictly in-band. manor_wing (standard) hits all four measured knobs (suspects 5, herrings 2, core 6, depth 3).
"Generation loops until V-6 metrics fall in band (max 20 attempts)" is **not implemented** (D-7).

## 10. Golden cases

`python -m eidolon.gen.golden` writes `cases/generated/{study_party_s4,study_party_s5,manor_wing_s4,manor_wing_s6}.json`
— package + machine-readable proof, **produced by the generator**, nothing hand-authored. `tests/gen/test_golden.py`
reloads each from disk, re-runs V-0…V-7, runs the independent verifier on the recorded proof, and regenerates two from
`(skeleton, seed)` to compare seals byte for byte. Each has: a canonical solution, a verified proof, 3–4 non-trivial
exclusions with cores of 1–3 constraints, a closed corridor, bounded distortions and their subset-robustness result. Negatives
are *derived from* them by editing the package (`tests/solve/helpers.py`), not authored.

## 11. Negative fixtures

Phase 0.5 fixtures, re-run under the **production** solver: `vance_v01_negative` (collusion) and `vance_v02_negative`
(corridor + ungrounded E10): both **not unique** (3 survivors, "outsider corridor open"); the transitive alibi cycle and the
pairwise-clean travel triple: infeasible under `world.feasibility`, the solver's compile+DP **and** the oracle. Also found:
the Phase 1 `vance_v03` fixture as shipped has only `E_watch`/`E_trace` — David is the lone survivor but there is no
containment device, so the production solver refuses to call it unique (correct; the spike's golden carried the gate log —
see D-1 on why it cannot be transcribed).

Phase 6 negatives (each rejected **at the stage that owns the defect**): N1 multiple valid murderers (V-5); N2 impossible
murderer (V-1 P-4, and the solver's own exclusion); N3 unreachable proof (V-4, while formally unique); N4 ambiguous
timeline (not unique; window > 1 tick); N5 unsupported uniqueness claim — `admits=("Accident",)` (fails closed, V-5); N6 hidden
critical clue — uncued (V-4); N7 impossible knowledge path (V-2, both a hand-built entry and a distortion Phase 2 would not
assign); N8 contradictory evidence (V-1); N9 planted evidence: ignored while `authentic=False`, caught (V-1 P-0) when
mislabelled authentic, and would have changed the verdict; N10 an alternative the generator *says* it excluded, with its
material removed: the solver derives the corridor open; plus "no valid murderer".

## 12. Mutation results

`python -m tests.solve.mutation_check` — 49 mutants over the decisions the brief names: the uniqueness condition (U1–U4),
survivor calculation and candidate enumeration (S1–S6), timeline/time pin (T1–T2), the outsider/containment query (O1–O3),
the DP/travel/oracle (P1–P2), evidence support, provenance and collusion in the lattice (L1–L10), proof validation and
the independent verifier (V1–V8), distortion robustness (B1–B3), deterministic seeding (D1–D3), pipeline stages (G1–G4)
and fairness (F1–F4). Protocol as Phase 4/5: each `old` anchor occurs exactly once (checked before every run — one
anchor, P1, failed this check and was fixed), applied to a fresh copy, KILLED iff the tests fail, baseline must be green first.

**The history matters more than the final line, so here it is:**

| run | suite | result |
|---|---|---|
| 1 (first full run) | 102 tests | **28 killed, 20 SURVIVED** (one — T2 — never terminated, was killed by me after 35 min and is *not* counted as a test kill) |
| 2 (the 20 + T2, after closing tests) | 126 tests | 20 killed, 1 survived (B2) |
| 3 (B2/B3, mutant B2 rewritten, B3 added) | 126 tests | B2 killed, **B3 survived** |
| 4 (final, all 49, clean, one piece) | **126 tests** | **49 killed, 0 survived** |

Why the first run had 20 survivors — every one a real suite gap, none an "equivalent mutant" excuse:

* **the verifier's individual checks (V2–V6)** each had a *redundant* guard, so a tampered proof was caught by some other check
  and no test isolated the one under mutation (deletion-minimality, core re-check, uniqueness re-derivation, seal, outsider);
* **pipeline stages (G2–G4)**: the physics stage, the `judge()` call and the verifier call were each masked by a later stage
  failing the same package for another reason;
* **lattice rules (L2, L4, L6, L8, L9, L10)** were exercised only end-to-end, where the generated cases never put the rule
  under load (disjoint provenance; P-9 for L3; min-over-the-chain; granularity; requires resolving to the actor's own account;
  the statement interval);
* **`bluff_converges` (F4)** was only ever asserted `False`, so a function returning `False` always passed;
* **P1**: every travel test used edges ≤ 2 minutes, where the mutated transit bookkeeping (`d-2` vs `d-3`) is identical;
* **S6/U2/T2/O3**: every generated case has a 1-tick window and a single containment device, so per-tick time resolution, the
  bin condition, the wide-window bound and "the phantom starts outside" were never distinguishable;
* **B2/B3**: the first B2 was itself too weak (`False and X or Y` still ran the second disjunct — near-equivalent); rewritten. B3
  (ignore the leave-one-out activity test) survived because no case had two redundant sources of one claim.

`tests/solve/test_mutation_gaps.py` (18 tests) and additions to `test_oracle.py`/`test_selfcheck_and_lattice.py`/`test_bruteforce_case.py`
close them, each *isolating* one decision (e.g. a proof whose core is padded with a redundant constraint; a package whose only
defect is a P-1 overlap; a single-suspect case for the bluff and bin conditions; a 3-minute edge; a containment log covering only
the time before the murder). **No production code was changed to make a mutant die.** `EQUIVALENT` is empty: nothing was declared
equivalent to avoid writing a test.

What this does *not* show: the set was chosen by me to attack the decisions in the brief; a 49/49 result says the suite
distinguishes those 49 edits, not that no other defect exists. The audit that found 6 – 16 defects per phase in Phases 3 – 5 has
not been run on Phase 6. The mutation harness has a per-mutant timeout (1 800 s) — a timeout is reported as `TIMEOUT`, not as an
assertion kill; the final run had none.

## 13. Performance

Serial, idle machine, seeds 4/5/6 per skeleton (`out/perf.py`; 4 CPU-seconds is not a target, it is a measurement):

| step | study_party (4 suspects) | manor_wing (5 suspects) |
|---|---|---|
| plan + compile | < 0.02 s | < 0.02 s |
| `finalize` (proof core → I-39 boosts; Phase 2 distortion derivation + bounded pick) | 1.6 – 2.1 s | 2.6 – 2.9 s |
| layer-0 fixpoint (1 round each) | 0.10 – 0.12 s | 0.19 – 0.32 s |
| **one V-5 solve** (DP calls) | 0.19 – 0.28 s (100–106) | 0.41 – 0.60 s (141–189) |
| proof core (1-minimal) | 1.0 – 1.2 s | 1.4 – 1.6 s |
| independent proof verification | 0.20 – 0.23 s | 0.34 – 0.43 s (one 3.3 s first-call outlier) |
| **full `validate` V-0…V-8** incl. robustness + verification | 2.8 – 3.1 s | 4.8 – 5.2 s |
| end to end per case, serial | ≈ 4.4 – 5.3 s | ≈ 7.4 – 8.1 s |

Throughput: ≈ 0.12 – 0.23 cases/s per core serial; the 100-case study on 15 worker processes took **128 s wall = 0.78 cases/s**
(its per-row "seconds" of 14 – 22 s are contention, not serial cost). Search space per case: 4 – 5 candidate hypotheses ×
a **1-tick** pin window (≤ 40 otherwise) × 1 location × 1 method, plus one outsider reachability query; each DP is
T = 120 × 8 locations = 960 cells × ≤ 2^k existential masks; 350 – 520 testimony atoms → 200 – 350 constraints (130 – 244 hard);
**survivor count 1 in every sealed case**; distortion subsets enumerated 1 – 8. Nothing was optimised beyond the `derive_perception`
memo (§1) and the chunked proof-core deletion (≈ 250 → 35 solves, measured on seed 4 of both skeletons), both done because they were 10× of the wall time.

## 14. Full test results

`python -m pytest -q` → **2126 passed** in 292 s. Breakdown: 98 world + 77 minds + 136 cross-phase repairs + 169 evidence + 180 decision +
1340 llm + **126 Phase 6** (`tests/solve` 97 + `tests/gen` 29). `python -m pytest spike/test_spike.py -q` → 21 passed.
Phase 6 tests by file: solver/verifier 15, oracle (Hypothesis 40 examples × DP/oracle/brute, + 3-minute edges) 5, whole-case brute force 5,
negative fixtures 16, self-checks/lattice/robustness/malformed 18, independence/fairness/V-4 20, mutation-gap closers 18,
generator/determinism/matrix/CLI 22, golden 7.

## 15. Previous-phase regression

No prior test was edited. Phase 1–5 suites (98 / 77 / 136 / 169 / 180 / 1340) all pass unchanged after the `_search`
refactor and the `derive_perception` memo. The Phase 4/5 mutation harnesses were **not** re-run (none of their anchors touch
`world/`; a grep confirms it) — I state that rather than claim it.

## 16. Determinism

Same `(skeleton, seed, generator version, architecture version)` ⇒ identical sealed package: in process (byte-identical JSON),
across separate processes, across `PYTHONHASHSEED` ∈ {0, 1, 12345, 777}. Survivor sets/verdict JSON deterministic across runs; the
verdict is invariant under shuffling events, evidence, secrets and the actor table (3 shuffles × 2 skeletons). `random`/`secrets`/
`uuid` are imported nowhere outside `gen/` (AST test).

## 17. Final self-check (the four questions)

1. *Secretly replace the murderer, keep the world consistent, rerun.* `plan(..., murderer=X)` regenerates the world with only
   the murderer changed (`test_Q1…`, both skeletons, ≥ 4 valid swaps): the solver's survivor follows the **world**
   (`survivors == [X]` or not unique), and `judge()` flags any package whose claim disagrees. Editing only the claim
   leaves the verdict byte-identical (`test_solver_never_reads_the_declared_solution_or_structure`). **Yes.**
2. *Reorder without changing semantics.* Survivors, `unique`, bins, corridor and window unchanged under shuffles. Proof
   *core ids* can differ (perception ids depend on event order) — the semantic result does not. **Yes.**
3. *Remove a critical clue.* Dropping any proof-core evidence item is never silent: either uniqueness is lost with reasons,
   or the item was redundant and is absent from the new proof core (`test_Q3…`); dropping the containment log opens the
   corridor (`test_Q3b`). **Yes.**
4. *Plausible case with two valid explanations.* N1 (nobody sees anyone) and the colluding-witness fixture
   (`test_collusion_destroys_corroboration_once_physical_pins_are_removed`) are rejected at V-5. One real finding: with L3
   pins present, colluding witnesses *remain* admissible — correct under I-44, and pinned by
   `test_physical_pins_keep_a_colluding_witness_admissible`. **Yes.**

## 18. Phase 6 acceptance criteria

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 1 | Deterministic case generation | **PASS** | §16; D1–D3 mutants |
| 2 | Canonical solution representation | **PASS** | §5; `CanonicalSolution` + `judge()` |
| 3 | Independent solver, no circular validation | **PASS** | AST tests (import graph, one `.solution` read, verifier never calls solve); scrambled-metadata test |
| 4 | Unique-solution validation per documented guarantee | **PASS** | §7; N1/N5/N10, self-check 1–4 |
| 5 | Machine-verifiable proof | **PASS** | §6; 97/97 study proofs + 4 goldens verified; tamper tests |
| 6 | Negative cases rejected (incl. all Phase 0.5 fixtures) | **PASS** | §11, 16 tests |
| 7 | Fairness / solvability (V-4, V-6) | **PASS** for items 1, 2/6, 3, 4, 8, 9, 10; **PARTIAL** for 5, 7 | §8; items 5/7 partly vacuous in v1 |
| 8 | Measurable generation yield, by stage | **PASS** | §9: 97/100, funnel by stage |
| 9 | Solver vs brute force on small cases | **PASS** | `test_oracle.py`, `test_bruteforce_case.py` |
| 10 | Every sealed case passes V-0…V-7 with its realised structure + exclusion chain per candidate | **PARTIAL** | V-0…V-2, V-4…V-6 full; **V-3 is structural only** (D-3); V-7 is material-level (D-5) |
| 11 | Robustness over distortion subsets | **PASS** (time_compression only) | `distort.py`; subsets 2^active enumerated; failure path tested |
| 12 | `absence-fragility` reported | **PASS** | 0 of 338 study eliminations rest on `NotAt` (report only, never gated) |
| 13 | Bluff bot fails to converge on every sealed case | **PARTIAL** | material-level proxy holds on all 97; the *engine-driven* 500-bluff bot is **UNMEASURED** (D-5) |
| 14 | Greedy / random / adversarial / order-shuffled / cue-following bots on the real engine | **UNMEASURED** | not built; proxies only (D-5) |
| 15 | Cover synthesis + V-3 breaker-set derivation | **UNMEASURED** | minimal 2-layer covers; `derive_breaker_sets` not run (D-3) |
| 16 | Flavor-slot LLM calls with checks | **UNMEASURED** | not built; deterministic tables (D-4). No LLM in the Phase 6 path |
| 17 | Difficulty-band loop ("until in band, ≤ 20 attempts") | **FAIL** | no loop; 47/97 in band; proof-core size untuned (D-7) |
| 18 | All previous-phase regressions | **PASS** | 2126 passed |
| 19 | `eidolon gen` / `eidolon validate` | **PASS** | CLI test incl. tampered-seal rejection |

## 19. Architecture deviations

* **D-1 `NoStranger` vs `Saw(nobody)`.** §4.7's `NoStranger` is transcribed as `Saw(observer, "nobody", loc, iv)`, but Phase 1's
  `FactIndex._tv_Saw` makes that true only if *nobody but the observer* was there. So a containment device is canonically true only
  at an access no cast member visits — both skeletons are built that way, and the Phase 0.5 `vance_v03` (whose Gazebo the cast
  visits, under the spike's "no *stranger*" reading) cannot be transcribed. `containment="watcher_L2"` would need a stranger-absence
  derivation `perception.py` does not have; the field allows only `device_L3`. This is a Phase 1/architecture question, not fixed here.
* **D-2 `requires` tokens.** `<event>@<actor>` ("that actor's own account of that event") is the token the solver resolves, as in the
  spike's `clean@Elena`; Phase 3's `S_clean`-style opaque statement ids do not resolve (the Phase 4 `Statement` store does not exist at
  seal time). `statement_intervals(case)` supplies the P-9 hull for them.
* **D-3 V-3 / cover synthesis (§18.3 stage 7, §19.3).** Secrets carry minimal 2-layer covers (layer-0 lie; terminal by hash). Checked:
  protected facts true in the log, layer-0 claims false, monotone `concedes`, and (in V-6) every lie has an admissible refuter.
  **Not** run: breaker-set derivation (`decision.cover_consistency.derive_breaker_sets`), `EvidenceResponse` coverage, slips,
  deflections, joint cover feasibility (I-28) — these need pre-authored `Statement`s the generator does not yet emit.
* **D-4 Flavor slots.** No LLM-filled names/voices/prose (§18.4). Nothing plot-structural comes from anywhere but the planner.
* **D-5 V-7.** Material-level proxies only: greedy ≡ V-5; cue-following = proof-core cued depth ≤ 5; bluff = `evaluate({})` not
  unique; order-shuffled = tests. The engine-driven bots (real `TemplateLLM` turn loop, 500 bluffs, adversarial 500 questions,
  random bot) are not built.
* **D-6 Retrieval expressibility (I-39)** is checked for the claim's own cue set (the most specific query), not the full
  parser-`Query` enumeration; `memory_boosts` are recorded in the package and applied by V-4's check, but **no session loader applies
  them yet** (Phase 7/8).
* **D-7 Difficulty banding** is measured and reported, tuned for suspects / red herrings / discovery depth, not for proof-core size,
  and there is no regenerate-until-in-band loop.
* **D-8 Distortions**: only `time_compression` (all Phase 2 assigns). The generator bounds them per witness (Phase 2 alone
  assigns 30–60 per witness); the bound is 1 per witness for easy/standard.
* **D-9** `docs/EIDOLON-IMPLEMENTATION-CONTRACT.md` is missing (§0).

## 20. Remaining non-blocking work

Later-phase (genuine): applying `memory_boosts` at session load and persisting the package/proof (Phase 7); surfacing the case
report/exclusion chains to the player (Phase 8); live-model V-7 bots and long-session fallback rate (Phase 9); cost-tiering (Phase 10).
Phase-6-internal, carried forward honestly: D-3, D-5, D-6, D-7 above, and an independent hostile review of this phase (the Phase 3/4/5
pattern found 6–16 defects each time; this phase has had none yet, which is a statement about review, not about correctness).

**Phases left after this one: 4** — 7 persistence, 8 player UI, 9 hardening, 10 optimization.
