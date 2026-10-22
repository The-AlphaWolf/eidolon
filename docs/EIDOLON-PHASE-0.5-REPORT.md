# EIDOLON — Phase 0.5 Feasibility Gate Report

**Target:** `docs/EIDOLON-ARCHITECTURE.md` v0.3, §30 "Phase 0.5 — Feasibility gate (BLOCKING)".
**Date:** 2026-09-02.
**Verdict (one line):** the v0.3 generator as specified (plan by role templates, then *search* for uniqueness by reseeding) yields **0 of 20** uniquely-solvable cases in every configuration and under every reading of the unspecified semantics, and 0 of 20 even with 20 reseeds per seed. The solver, the admissibility lattice, `feasible()`, `outsider_excluded()`, the negative fixtures and determinism all work as specified. The architecture's own fallback for this outcome (R-B, *construct* uniqueness from a skeleton-declared elimination structure) was implemented as a variant of the same toy planner and yields **20/20, 20/20 and 19/20** under the strictest semantics. **PHASE 0.5 GATE: FAILED** for the planner as written; the required change is R-B and it is measured, not guessed.

---

## 1. Environment

| Item | Value |
|---|---|
| OS | Windows 11 Home 10.0.26200 |
| Python | 3.12.10 (`C:\Users\ASUS\AppData\Local\Programs\Python\Python312\python.exe`) |
| Dependencies | stdlib only (`dataclasses`, `random`, `heapq`, `json`, `hashlib`). `pytest` 9.1.1 for the checks. **No pydantic** (not installed; a throwaway spike does not need it — deviation from §24, noted). No Hypothesis. |
| Code | `spike/model.py`, `spike/minds.py`, `spike/solve.py`, `spike/gen.py`, `spike/fixtures.py`, `spike/run_spike.py`, `spike/verify.py`, `spike/test_spike.py` (≈1 500 lines) |
| Outputs | `spike/out/results.json` (all per-seed rows, verdicts, cores), `spike/out/verify.json`, `spike/out/run.log`, `cases/toy_v03.json`, `cases/vance_v03.json` |
| Runtime | full run 533 s single-threaded; search-mode configs ≈1–2 s per 20 seeds, constructive configs 20–54 s per 20 seeds (proof-core extraction dominates) |
| Reproduce | `python -m spike.run_spike` · `python -m pytest spike/test_spike.py -q` · `python -m spike.verify` |

## 2. What was implemented for the spike

Exactly the §30 deliverable list, throwaway quality, nothing from later phases:

| §30 item | Where | Notes |
|---|---|---|
| Proposition schema (subset) + `FactIndex.truth_value` | `model.py` `Prop`, `World.truth_value` | `At`, `NotAt`, `Did`, `Saw`, `Heard`, `Died`, `NoStranger` (= `Saw(observer,"nobody",…)`), `Attr`, `ObjectState`. Universal vs existential semantics per §4.7. |
| Travel graph, on-demand conditional Dijkstra (§4.3) | `World.travel_time/route`, `doors` | Edge conditions evaluated at departure tick; tested with a timed lock. |
| Physics P-1, P-2, P-4, P-9 (§4.9) | `check_physics` | P-2 uses half-open semantics (arrival ≥ last-present tick + travel), which is how §29.1's own timetable reads. |
| Perception incl. co-presence (§4.8.6) and the gated absence rule (§4.8.7, I-34) | `minds.derive_knowledge` | Absence only if attention ≥ 0.7, entrances visible, reliability = attention × 0.8 (< the matching `At`). |
| Layer-0 testimony pool (§19.5 robustness run) | `minds.testimony_pool` | Every secret-holder withholds knowledge acquired inside their protected interval. |
| Collusion graph, connectivity (I-37) | `minds.collusion_components` | Edges: listed `Rel`, shared `Secret`. |
| Per-claim admissibility L0–L3 (I-27, §19.5) | `minds.admissible` | L3 physical (P-9 checked; `requires` chains take the minimum over the chain). L2 = perception-grounded **and** speaker's relevant presence fixed by L3 or by a non-colluding, provenance-disjoint source, **or** the claim directly corroborated by such a source. Granularity: own/co-presence claims shrink by 2 min, event claims widen by 2–5 min. |
| `feasible(claim_set)` (§13.2a, I-28) | `solve.feasible` | Per-actor reachability DP over (location, tick, existential-mask) with transit and lingering; deletion-minimal infeasible core. |
| `outsider_excluded()` (AC-9) | `solve.outsider_path` | Phantom from `EXT` at t=0 → murder room during the admissible time window → back to `EXT`, through no cell covered by admissible `NoStranger` material. Returns the corridor when open. |
| V-5 solver (§19.5) | `solve.solve` | Per candidate: feasibility of admissible material ∪ "X in the murder room during the window"; time window from L3 `Died` / L2 `Heard(struggle)`; voice-attribute filter; time-bin uniqueness (10-min bins); machine-generated exclusion chain per excluded candidate. |
| Proof core (§19.5) | `solve.proof_core` | Deletion-minimal item subset preserving uniqueness (admissibility recomputed per subset, so corroborators are kept). |
| Cued discovery closure (§19.4) | `solve.cue_closure` | Item obtainable only when held material names its target entity/location; initial material = victim, body, murder room, cast. Reports cued depth and whether the cue-closure alone is unique (m-12). |
| Toy planner, one skeleton, 4 actors / 5 locations | `gen.py` | Hall / Study / Kitchen / Bedroom / Garden (+ `EXT`), roles housekeeper / guest / guest / gardener, victim in the study, murderer excursion, one red-herring secret (solo or shared meeting), optional lover pair, watch (time pin) p=0.75, murderer trace with a `requires` cleaning statement p=0.6, per-actor logged presence pins p=0.35. |
| Brute-force cross-check | `test_spike.py` | DP vs exhaustive walk enumeration on 250 random tiny instances; solver exclusions vs brute force on 120 tiny cases. `verify.py` adds independent witness checks on every generated case. |
| Negative fixtures | `fixtures.py` | `vance_v01_negative` (collusion), `vance_v02_negative` (Robert/outsider corridor, ungrounded E10), transitive alibi cycle, plus a pairwise-clean travel triple. |

Also run, beyond the minimum: the same planner on the §29.1 Vance layout (7 locations, 4 living actors) so that `vance_v03` is produced on its own layout; a 5-actor toy variant; and the R-B constructive variant of the planner (§6 below).

**Not implemented (out of Phase 0.5 scope, stated so the numbers are read correctly):** beliefs/memories/distortions (§6.4, §8; the distortion-robustness sub-runs of V-5 are therefore not measured), cover-story synthesis and V-3, `Told`/`Read` provenance, motives, planted evidence, red-herring *refuters*, bots (V-7), any LLM, persistence. Testimony intervals do carry granularity (§8.3-style), which stands in for the coarsest memory effect.

## 3. Seed set and configurations

Seeds **1–20** for every configuration × semantic mode. Reseed experiment: derived seeds `base×1000+k`, k = 0..19, for base 1–20. Golden-case search: seeds 1–20, then 21–120 for the Vance layout, then the constructive planner from seed 1.

| Config | Layout | Living actors (all are candidates) | Planner |
|---|---|---|---|
| `toy3` | toy 5-location | 3 (+ victim = 4 actors, the §30 skeleton) | v0.3 search |
| `toy4` | toy | 4 (Easy band, §20.2) | v0.3 search |
| `vance4` | §29.1 Vance house | 4 | v0.3 search |
| `toy3C`, `toy4C`, `vance4C` | as above | as above | **R-B constructive** |

Two semantic questions the architecture leaves open were run both ways rather than guessed:

- **withhold** — `layer0_all`: every secret-holder is stuck at layer 0 (the §19.5 robustness run, literally); `murderer_only`: innocents' secrets are cracked.
- **fix** — what "relevant presence fixed" means: `tick` (a witness is fixed only at ticks actually covered by a pin or a non-colluding co-presence claim); `segment` (one fixed tick fixes the whole presence segment — the reading §29.1 practises for Elena and Robert's glow).

**Primary (gate) mode = `layer0_all/tick`**, the strictest literal reading. Fairness level `standard` (L2 ∪ L3) throughout.

## 4. Generation methodology

Solution-first, per §18.3: the seed fixes murderer, murder time (21:40–22:30), dinner end, the murderer's excursion (arrive 1–3 min before the blow, leave 0–2 min after), a red-herring secret interval and location, an optional lover pair, an optional cleaning visit by the housekeeper (grounds the trace's `requires`), and per-actor logged presence pins. Role schedules are then realised by a seeded random walk over the role's location weights with forced picks (dinner, excursion, secret, cleaning) honoured on time; routes through the hub produce 1-tick hops; late bedroom stays are asleep (attention 0.3). Events (blow, argument, cleaning, logs) and physical evidence are *derived* from the timeline (P-6 direction). Knowledge is derived, never authored. The planner does one attempt per seed; uniqueness is decided by V-5 afterwards. This is the "plan, then check, then reseed" loop of v0.3 — R-A's question is precisely what that loop yields.

## 5. Raw yield numbers — v0.3 search planner

Per 20 seeds. "pass" = unique at L2 **and** proof core fully cued **and** cue-closure alone unique.

| Config | Mode | planner ok | unique @L2 | fully cued | **pass** | rejection stages |
|---|---|---|---|---|---|---|
| toy3 | layer0_all / tick (primary) | 20 | 0 | 0 | **0** | multiple survivors 19 · time under-determined 1 |
| toy3 | layer0_all / segment | 20 | 0 | 0 | 0 | multiple 17 · outsider-only 2 · time 1 |
| toy3 | murderer_only / tick | 20 | 0 | 0 | 0 | multiple 17 · outsider-only 2 · time 1 |
| toy3 | murderer_only / segment | 20 | 0 | 0 | 0 | multiple 16 · outsider-only 3 · time 1 |
| toy4 | layer0_all / tick | 20 | 0 | 0 | **0** | multiple 19 · outsider-only 1 |
| toy4 | layer0_all / segment | 20 | 0 | 0 | 0 | multiple 18 · outsider-only 1 · time 1 |
| toy4 | murderer_only / tick | 20 | 0 | 0 | 0 | multiple 19 · outsider-only 1 |
| toy4 | murderer_only / segment | 20 | 0 | 0 | 0 | multiple 18 · outsider-only 1 · time 1 |
| vance4 | layer0_all / tick | 20 | 0 | 0 | **0** | multiple 19 · outsider-only 1 |
| vance4 | layer0_all / segment | 20 | 0 | 0 | 0 | multiple 18 · outsider-only 2 |
| vance4 | murderer_only / tick | 20 | 0 | 0 | 0 | multiple 18 · outsider-only 2 |
| vance4 | murderer_only / segment | 20 | 0 | 0 | 0 | multiple 17 · outsider-only 3 |

Supporting counts (primary mode): admissible L2+L3 constraints per case — toy3 mean 47.6, toy4 91.0, vance4 74.4 (there is plenty of hard material; it is just not *where the murder is*). Excluded candidates per case — toy3 {0 excluded: 17 cases, 1: 2, 2: 1}; toy4 {0: 14, 2: 5, 3: 1}; vance4 {0: 13, 1: 1, 2: 5, 3: 1}. Outsider corridor open in 20/20 cases of every search config (19/20 in one). Planner never failed physics (P-1/P-2/P-4 clean, 240/240).

**Reseeding (the Phase-6 "≤ 20 attempts" criterion), toy3 primary:** 0 of 20 base seeds found a passing case in 20 attempts each (400 cases, 0 passes).

**Sensitivity — outsider assumed excluded (v0.2's authored exclusion, primary mode):** toy3 0/20, toy4 1/20, vance4 1/20. The AC-9 reachability rule is therefore *not* what kills the yield; the eliminations are.

## 6. Yield — R-B constructive planner (the architecture's prescribed fallback)

Same solver, same admissibility, same semantics, same evidence menu. The only change is in `gen.plan(construct=True)`: the skeleton declares its elimination structure and the planner realises it — (a) all innocents share one alibi window `[t_m−8, t_m+8]` in one room; (b) the red-herring secret is kept clear of `[t_m−12, t_m+12]`; (c) a containment device exists: an L3 gate log at the exterior access from a seeded tick ≤ 21:20 (self-grounding interval, P-9 clean); (d) no collusion edge may leave an innocent without a corroborator outside their collusion component (a lover pair that would do so is re-drawn to include the murderer); (e) the time pin (watch) is always present.

| Config | layer0_all/tick (primary) | layer0_all/segment | murderer_only/tick | murderer_only/segment |
|---|---|---|---|---|
| toy3C | **20/20** | 20/20 | 20/20 | 20/20 |
| toy4C | **20/20** | 20/20 | 20/20 | 20/20 |
| vance4C | **19/20** (seed 5: proof core not fully cued) | 19/20 | 20/20 | 20/20 |

Reseeding, toy3C primary: 20/20 base seeds pass at the **first** attempt. Proof cores: size 4–5 items in every passing case (gate log, watch, and 2–3 co-presence statements); cued depth 2 in every passing case; **0 of 160** exclusions rest on absence (`NotAt`/`NoStranger`) material — all eliminations are positive co-presence corroborated across a non-colluding pair.

The single constructive failure (vance4C seed 5, layer0 modes) is instructive: the proof core needs the Gazebo gate log, but no held item ever *names* the Gazebo (nobody went there), so the containment device is unreachable along a cued path and the cue-closure alone is not unique. Under `murderer_only` the same seed passes because an innocent's withheld Gazebo visit becomes tellable and names the location. This is a real cue-graph requirement for skeletons: **the containment device must be cued from the initial material** (the map, or the scene).

Before rules (d) and (e) were added, the constructive variant scored 6/20 (toy3C), 18/20 (toy4C) and 17/20 (vance4C); the failure anatomy was 11 of 13 failures with the only two innocents in one collusion component (lovers or a shared secret), and 3 with no time pin. Those two rules are therefore load-bearing parts of any declared elimination structure, not tuning.

## 7. Pass/fail breakdown and where valid-looking cases fail

Anatomy of the primary toy3 search run (per innocent at `t_m`): a non-colluding actor co-present in **3 of 20** seeds; a logged pin covering `t_m` in **1 of 20**; both innocents covered in **0**. Everything else is L1: an innocent alone in a room, at the moment that matters, has only their own word — which the lattice correctly refuses. Random role schedules put two innocents together at `t_m` about 15 % of the time per pair, and the outsider corridor additionally needs continuous L2 coverage of the hall over the whole entry window (from ≈21:05 to `t_m`) or over the whole exit window (`t_m` to ≈22:54) — with random schedules that never happened (20/20 open). The failures are structural, not tuning: no knob on the search planner short of forcing structure changes the order of magnitude, and forcing structure *is* R-B.

Specific observations from the rows:

- **"Multiple survivors" is 85–95 % of search-mode rejections.** In most cases nobody is excluded at all.
- **The trace never became admissible.** `opportunity_pin` = 0 in all 240 search cases and all 240 constructive cases: the murderer's trace implication carries `requires: [cleaning statement]`, the cleaner's own `Did(clean)` statement is L1 unless her presence in the study at that minute is fixed, and I-27 takes the minimum over the chain. Uniqueness never needed it (elimination suffices), but §20.1 item 6 ("the murderer's layer 0 is refutable by physical evidence alone") is not met by any generated case. Grounding the `requires` statement to L2 needs a witness or a pin *for the cleaner at cleaning time* — a skeleton-level structure, again.
- **Time pins matter twice.** With no watch and no L2 hearer the window is the whole evening; even an alibi at `t_m` then excludes nobody (seed 2 of toy3C before rule (e): the outsider corridor was legitimately "open" at 21:06–21:15, before the gate log started — the solver was right).
- **Layer-0 withholding removes witnesses.** In `vance_v02` the male-voices testimony is Elena's, acquired while she was secretly smoking; under the literal §19.5 robustness run it is withheld and Margaret is not excluded. The architecture's own worked argument for v0.2 depends on cracking a minor secret first. This is a spec contradiction to resolve (see §12).

## 8. Uniqueness results — does the solver *establish* uniqueness?

Yes, in the strong sense. For every non-murderer candidate the solver returns a **deletion-minimal unsatisfiable core** (constraints ∪ hypothesis), i.e. an exclusion proof, not a failed search; the outsider check is an exhaustive reachability search over all (location, tick) cells for a phantom with lingering allowed; the murder time is enumerated over the admissible window and reported per bin. Completeness of the DP is checked against exhaustive enumeration (§10). Example from `cases/vance_v03.json` (seed 1, constructive, primary mode):

```
Robert excluded:  (At Robert Kitchen [70,82)) L2   ← Robert's own claim, fixed by Margaret's co-presence [non-colluding]
                  ∧ HYP (Did Robert Study [76,77) attack Harold)      → unsat
Margaret excluded:(At Margaret Kitchen [70,82)) L2 ← Robert's co-presence claim, fixed by Margaret's own + Elena's
Elena excluded:   (At Elena Kitchen [70,82)) L2    ← Robert's co-presence claim, fixed by ...
Outsider:         no (EXT,0)→(Study,76)→EXT walk avoids NoStranger(Gazebo,[14,120)) [L3 gate log]
Time:             window [76,77) from E_watch (L3); one bin
Proof core (5):   E_gate_Gazebo, E_watch, S:K0194 (Margaret: Robert with me, Kitchen 22:08–22:24),
                  S:K0263 (Robert: Elena with me), S:K0266 (Robert: Margaret with me)
Fully cued:       yes (depth 2); cue closure alone unique: yes
```

The chain shows the lattice doing its job: Robert and David are lovers in this seed, so Robert's statements are worthless *about David* but perfectly good about Margaret and Elena, whose components differ from his.

Known content wart in `vance_v03`: the Vance layout's terrace edge (Study–Gazebo, 2 min) makes the study the shortest route between the hall and the gazebo, so guests pass through the murder room in 1-tick hops earlier in the evening. Physically valid, solver-irrelevant, and a layout-template defect to fix in Phase 1 (routes must not transit private rooms, or the terrace door needs a condition).

## 9. Proof-core results

Primary mode (`layer0_all/tick`), 60 constructive cases (toy3C, toy4C, vance4C):

| | search planner | constructive planner |
|---|---|---|
| Unique at L2, proof core extracted | 0 / 60 | 60 / 60 |
| Core size | — | 4 (toy3C, all 20), 4–5 (toy4C, vance4C) |
| Fully cued | — | 59 / 60 (vance4C seed 5: uncued gate log) |
| Min cued discovery depth | — | 2 in every cued case (a statement must name the room before its pin/log can be searched) |
| Cue-closure alone unique (m-12) | — | 59 / 60 |
| Exclusions resting on absence material (I-34 fragility) | — | 0 / 160 |

The cue graph as implemented is conservative (only the study and the cast are named initially; locations become nameable through statements or scene items). Even so it bit exactly once, on the containment device, which is the right place for it to bite.

## 10. Negative fixture results

All four semantic modes; V-5 at fairness `standard`. "Rejected" = not unique.

| Fixture | Result | Survivors | Outsider | Notes |
|---|---|---|---|---|
| `vance_v01_negative` (§29.1 v0.1, lovers alibi each other) | **rejected**, 4/4 modes | David, Margaret, Robert, Elena | corridor open, path reported | Margaret's and Robert's mutual alibi is in one collusion component → L1. Elena uncorroborated (glow unidentified) → L1. Nobody excluded. |
| `vance_v02_negative` (E9/E10 added) | **rejected**, 4/4 modes | `murderer_only`: **David, Robert** (the hostile review's counter-model exactly); `layer0_all`: all four | corridor open (both the kitchen route at 22:04/22:16 and the terrace) | Margaret and Elena excluded by Elena's L2 "male voices" only when her smoking secret is cracked. **P-9 flags E10**: `ObjectState(terrace_door bolted) [21:00,23:00)` exceeds the established `[23:00,23:01)` with no `requires` (T-16). |
| transitive alibi cycle (§13.2a) | `feasible()` = **False**, core = all 6 claims | — | — | Note: three of its pairs *are* pairwise presence contradictions (e.g. `At(B,Gazebo)` vs `At(B,Kitchen)` overlapping) — the v0.2 gap was that nobody compared claims *across* characters, which `feasible()` over the union does. |
| pairwise-clean triple (three existential visits, two hops each, in a 4-tick window) | `feasible()` = **False**, core = 3 claims; `contradiction()` finds **nothing** on any pair | — | — | The genuinely n-ary case the pairwise detector cannot see (T-15 in the strong form). |

All fixture outcomes are asserted in `spike/test_spike.py::test_negative_fixtures_rejected_in_every_mode` and `test_feasible_rejects_cycle_and_pairwise_clean_triple`.

## 11. Determinism results

- Same process, same config run twice: SHA-256 of canonical JSON of the per-seed rows **equal**.
- Fresh interpreter (`subprocess`), same config: digest `8e75b743…` **equal** to the in-process digest.
- Two complete `run_spike` executions (one interrupted after the search configs, one full): the search-config summary lines were byte-identical.
- No `random` outside `gen.py`; all iteration is over sorted keys; dict order is insertion order. `test_determinism` asserts the in-process equality.

## 12. Validation-stage rejections and solver checks

**Stages that rejected cases (12 search runs × 20 = 240 cases):** V-1 (physics): 0. V-5 multiple survivors: 215. V-5 outsider-only: 19. V-5 time under-determined: 6. Constructive runs: V-4 proof core not cued: 2 (vance4C seed 5 in both `layer0_all` modes); V-5: 0. No case ever tripped "SOLVER BUG: murderer excluded" — the canonical world is a model of every admissible constraint in every case (`test_canonical_world_satisfies_admissible_material_and_murderer_survives`, 7 seeds × 4 modes, plus all 480 rows).

**Solver vs brute force:** DP feasibility vs exhaustive walk enumeration, 250 random tiny instances (6 ticks, 3 rooms, random blocked/forced/existential cells): 250/250 agree. Per-candidate exclusion vs brute force on 120 random tiny cases: all agree. `verify.py` on all 120 generated cases (primary mode): every surviving candidate's witness path re-validated by an independent naive checker — **249/249 valid**; every exclusion attacked with 300 biased random walks against its minimal core — **0 counter-examples in 191**; outsider corridors re-validated **60/60**; outsider exclusions attacked **60/60 hold**.

**pytest:** 13 passed (`python -m pytest spike/test_spike.py -q`, 3 s).

## 13. Failures encountered while building, and root causes

1. **Planner merged forced picks with adjacent stays** (housekeeper "cleaned" the study for an hour and murdered from inside it). Root cause: hold-until-window logic ignored slack. Fixed; adjacent same-room stays are merged into maximal segments afterwards.
2. **Continuous identified sightings were modelled as existential `Saw`.** Robert watching Elena's glow for ten minutes is universal presence knowledge (`At`), not "at some tick". Root cause: one `Saw` shape for both event-perception and sustained observation. Fixed: sustained identified observation through a sight edge yields `At` at own-presence granularity.
3. **Observer interval recorded as the perception run, not the presence segment.** Made "presence fixed" impossible for any heard event. Root cause: `obs_iv` semantics. Fixed.
4. **Outsider exit was checked from one witness path only**, so a phantom that reached the study late "could not leave" and the corridor was reported closed. Root cause: existential DP returns one path. Fixed: exit is checked from every reachable murder-room cell.
5. **Attack event spanned the argument**, so a hearer who caught only the argument's first minute narrowed the murder window incorrectly. Fixed: the blow is instantaneous (`struggle`, time pin); the argument is a separate `Speak` event (`argument`, voice attribute only).
6. **Proof-core extraction re-derived exclusion chains inside its deletion loop** (6.8 s per case). Fixed (0.6 s).

Items 2–4 are the kind of semantic detail the document leaves to the implementer; each silently changed whether the golden fixtures behaved as §29.1 claims. That is an argument for the Phase 1 exit criteria to pin these semantics with tests, and they are listed below as spec decisions.

## 14. Required architectural changes

**R-B is required (already the architecture's own contingency for this outcome), and it must be specific.** "Construct uniqueness" means the skeleton's `required_proof_core_shape` is realised by the planner, item by item, and V-5 confirms. The measured minimum for a 4–5 actor case at fairness `standard`:

1. **Elimination per innocent by construction:** each innocent gets, at `t_m ± margin`, either a co-present corroborator from a *different collusion component*, or an L3 presence pin. The planner must consult the collusion graph when placing lovers and shared secrets (rule (d)); without it the 3-actor case fell from 20/20 to 6/20.
2. **Time pin by construction:** an L3 `Died` pin (watch) or an L2-fixed `Heard(struggle)` witness. Without it, alibis exclude nobody and the outsider is legitimately unexcluded before the containment starts.
3. **Containment device by construction, and cued:** an L3, self-grounding (P-9-clean) absence item at every exterior access — gate/door log, or a continuously L2-fixed watcher — *and* the initial material must name the exterior access so the item is reachable along a cued path.
4. **If the opportunity pin (§20.1 item 6) is required, construct its grounding too:** the `requires` witness of the murderer's trace needs a fixed presence at cleaning time. In 480 generated cases it never reached L2 on its own.

Smaller spec decisions surfaced by the spike (each changed a number or a fixture outcome; none needs a redesign):

- **Define "relevant presence fixed" at tick or segment level** (§19.5). Tick-level is the defensible reading and is what the gate used; §29.1's argument assumes segment-level.
- **Resolve the layer-0 robustness run vs witness secrets** (§19.5 vs §29.1): as written, every load-bearing witness who has *any* secret over the murder window is silenced, and the v0.2 worked argument depends on the opposite. Either the robustness run exempts non-murder secrets whose owner is L2-excluded, or skeletons must not give load-bearing witnesses secrets over the window.
- **State that sustained identified observation grounds universal `At`**, and that event perception records the observer's presence segment (§4.8).
- **Add the Phase 1 layout rule** that routes never transit non-hub private rooms (the terrace-edge artifact in `vance_v03`).
- **P-2 with half-open intervals** is `I2.start − (I1.end − 1) ≥ travel_time` (§4.9 as printed is off by one against §29.1's own timetable).

## 15. Gate decision

The exit criterion (§30): *cases per 20 seeds passing uniqueness at L2 with a fully-cued proof core; if below 30 %, redesign the planner to construct uniqueness before Phase 1.*

| Measurement | Result |
|---|---|
| v0.3 search planner, primary mode, toy 4-actor / 5-location skeleton | **0 / 20** (0 %) |
| same, 5 actors; same, Vance layout | 0 / 20; 0 / 20 |
| same, any of the four semantic readings | 0 / 20 in all 12 runs |
| same, with 20 reseeds per seed | 0 / 20 base seeds (400 cases) |
| same, with the outsider assumed excluded | 0 / 20, 1 / 20, 1 / 20 |
| R-B constructive planner, primary mode | 20 / 20, 20 / 20, 19 / 20 |

**PHASE 0.5 GATE: FAILED** — for the generator as specified. The number is 0 %, far below the 30 % line, and it is not a tuning artifact: it holds across actor counts, layouts, every reading of the open semantics, and 400 reseeds. Phase 1 must not start on the v0.3 planner design.

What the spike **does** establish, with evidence: the proposition schema, `FactIndex`, conditional Dijkstra, the gated absence rule, the collusion graph, per-claim admissibility, `feasible()`, the AC-9 outsider query and the V-5 solver work as specified, produce genuine exclusion proofs, agree with brute force, reject both broken golden cases for the documented reasons, and are deterministic across processes. The prescribed remedy (R-B) applied to the *same* solver on the *same* evidence menu yields 59/60 under the strictest reading, at the first attempt, with 4–5-item fully-cued proof cores and no reliance on absence testimony. `cases/vance_v03.json` and `cases/toy_v03.json` are solver-selected outputs of that constructive planner (search found none in 120 Vance seeds), with machine-generated exclusion chains per candidate; they are shipped as the golden fixtures **on the condition that R-B is adopted into the architecture** — under the v0.3 planner they would not be reproducible.

**Recommended next step:** amend §18.3 stage 3 and §18.2 (`required_proof_core_shape`) with the four constructions of §14, resolve the five spec decisions, re-run this spike unchanged (it takes nine minutes), and then open Phase 1.

---

## Addendum — re-run against architecture v0.4 (2026-09-03)

**Gate status: PASSED — signed off by the owner on 2026-09-03** on the evidence below, against the v0.4 gate criteria (§30 (i)–(vi)) as written in the architecture on 2026-09-03; no criterion was relaxed and no measured number was changed. The v0.3 planner's result (0/20, §15 above) stands as recorded; the pass is for the v0.4 constructive planner.

**What changed in the spike to match v0.4** (all in `spike/`; the report above describes the 2026-09-02 state):
- primary semantics are now `layer0_fixpoint / tick` (I-45, I-44); `layer0_all` (v0.3 literal) and `segment` fixing are kept as sensitivity rows only;
- the constructive planner is the specified planner (I-43) and carries constructions (a)–(f) of §18.3 stage 3, including the cleaning-stay pin for the opportunity pin (f); the v0.3 search planner is kept as a baseline row;
- `route()` never transits private rooms (I-48); the study is private in both skeletons;
- the initial named set includes every exterior access (I-47);
- event-perception and `Participated` entries record the observer's presence segment (I-46 rule 9) — this also made the cleaner's `Did(clean)` statement presence-fixable;
- named checks T-27…T-34 added to `spike/test_spike.py` (21 tests, all passing).

**Commands run:** `python -m spike.run_spike` (857 s) · `python -m pytest spike/test_spike.py -q` (21 passed) · `python -m spike.verify`.

| Measurement (20 seeds each) | v0.3 search planner (baseline row) | **v0.4 constructive planner** |
|---|---|---|
| toy 4 actors, `layer0_fixpoint/tick` | 0 / 20 | **20 / 20** |
| toy 5 actors, `layer0_fixpoint/tick` | 0 / 20 | **20 / 20** |
| Vance layout, `layer0_fixpoint/tick` | 0 / 20 | **20 / 20** |
| every other semantic row (4 × 3 configs) | 0 / 20 in all 12 | 20 / 20 in all 12 |
| within 20 reseeds (toy, primary) | 0 / 20 base seeds | 20 / 20 at the first attempt |
| opportunity pin admissible (T-34), primary | 0 / 60 | **60 / 60** (16–18 / 20 under `layer0_all`, where the cleaner's own secret can withhold her statement; the fixpoint cracks it) |
| proof core size / cued depth | — | 4–5 items / depth 1 in all 60 (exterior access now cued from the start) |
| exclusions resting on absence material | — | 0 / 160 |
| fixpoint rounds | — | 1 round in every Vance case (the red herring, excluded, is cracked; nothing else changes) |

**Fixtures under the new primary semantics:** `vance_v01_negative` rejected (4 survivors, corridor open); `vance_v02_negative` rejected — 4 survivors under `layer0_fixpoint` (Robert's corroborating sighting lies inside his own protected interval and he is never excluded, so round 0 is the fixpoint) and {David, Robert} under the all-cracked sensitivity; the transitive cycle and the pairwise-clean triple are infeasible with the expected cores. T-29's crack mechanism is demonstrated on a constructive toy case instead (`test_T29_layer0_fixpoint`).

**Independent checks:** `verify.py` — 248 survivor witness paths valid, 0 counter-examples against 192 exclusions, 60 corridors valid, 60 outsider exclusions hold. Determinism: in-process and fresh-process digests equal (`1eddc891…`).

**Golden cases regenerated:** `cases/vance_v03.json` (constructive planner, seed 1, primary mode) — no actor transits the study en route any more (the terrace edge is no longer used as a corridor); exclusion chains for Elena, Margaret and Robert are single L2 co-presence claims from the shared kitchen alibi 22:08–22:24, fixed across two collusion components (Robert and David are lovers in this seed; Robert's claims about the two women stand); outsider excluded by the L3 gate log from 21:08; proof core = gate log, watch, three co-presence statements, all at cued depth 1; the murderer's trace is admissible at L2 through the pinned cleaning stay. `cases/toy_v03.json` likewise.

**Acceptance evidence against the documented v0.4 gate (§30 (i)–(vi)):**

| Criterion | Required | Measured (`spike/out/results.json`, run of 2026-09-03, 857 s) | Met |
|---|---|---|---|
| (i) yield per configuration, v0.4 planner, `layer0_fixpoint/tick`, outsider derived | ≥ 30 % of 20 seeds, each of 3 configurations | toy 4-actor 20/20; toy 5-actor 20/20; Vance layout 20/20 | yes |
| (ii) negative fixtures rejected under the same semantics | `vance_v01`, `vance_v02`, transitive cycle | v01: 4 survivors, corridor open; v02: 4 survivors, corridor open, P-9 rejects E10; cycle infeasible (core 6); pairwise-clean triple infeasible (core 3) | yes |
| (iii) `python -m spike.verify` | 0 invalid witness paths, 0 counter-examples | 248 survivor paths valid; 0 counter-examples in 192 exclusions; 60 corridors valid; 60 outsider exclusions hold | yes |
| (iv) determinism across processes | equal digests | in-process and fresh-process digest `1eddc8917185df1e…` equal | yes |
| (v) `vance_v03` regenerated under I-48 with exclusion chains, cued with the exterior access | — | `cases/vance_v03.json`, seed 1, no private-room transit, chains for Elena/Margaret/Robert, proof core at cued depth 1, cue-closure unique | yes |
| (vi) T-34 on every sealed case | opportunity pin admissible | 60 / 60 | yes |
| tests | T-27…T-34 present and passing | `python -m pytest spike/test_spike.py -q`: 21 passed | yes |

**PHASE 0.5 GATE: PASSED** (owner sign-off, 2026-09-03).

**Tracked later-phase work (explicitly NOT measured by this spike; carried into the architecture's roadmap, §30):**

| Item | Owner phase |
|---|---|
| Memory distortions and the distortion-subset robustness runs of V-5 | Phase 2 (model), Phase 6 (V-5 runs) |
| Cover synthesis and V-3 (breaker sets, joint layer feasibility) | Phase 4 (checker), Phase 6 (synthesis) |
| V-7 bots (greedy, random, adversarial, order-shuffled, cue-following, bluff) | Phase 6 |
| Planted evidence and its reachable unmasking | Phase 3 (model), Phase 6 (validation) |
| Red-herring refuters (§19.6) | Phase 3 (model), Phase 6 (validation) |
| Motives (§18.3 stage 2, `Motive` model) | Phase 6 |
| `Told` / `Read` provenance and belief formation from them | Phase 2 |
| The LLM path (parser, generator, verifier, validation) | Phase 5 |
| Difficulty-band mapping of `alibi_window`, `secret_clearance`, containment timing (§20.2) | Phase 6 |
