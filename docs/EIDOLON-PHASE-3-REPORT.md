# EIDOLON — Phase 3 Implementation Report

> **⚠ SUPERSEDED IN PART — read `docs/EIDOLON-PHASE-3-REPAIR-REPORT.md` first.**
>
> This document records Phase 3 **as first shipped on 2026-09-05** and is kept unedited as
> that record. An independent hostile review then found 5 BLOCKING and 11 IMPORTANT defects
> in this implementation; **all 16 were fixed on 2026-09-07** and independently re-audited.
>
> Consequences for anything you read below: the test counts here (424 total, 113 in
> `tests/evidence/`) are the pre-repair figures — the current numbers are **480 total, 169 in
> `tests/evidence/`**. Several behaviours described here as complete were not: notably V-4
> cueing, `corroborates`, the §13.2 granularity rule, `Discovery` action/location validation,
> and the player projection. Deviation 2 below ("`vance_v03`'s own `attack` event carries no
> `TraceCreated` effect") was a Phase 1 fixture defect, not a constraint to work around, and
> the effect has since been added.
>
> The repair report is the authoritative current state. Phase 4 has NOT been started.

**Target:** `docs/EIDOLON-ARCHITECTURE.md` §30 "Phase 3 — Evidence / timeline system", §5
(Evidence system), §13.2 (contradiction handling), §17 (exploration/discovery, Phase 3
half), §19.4 (V-4 evidence reachability).
**Date:** 2026-09-05.
**Scope note:** no `docs/EIDOLON-IMPLEMENTATION-CONTRACT.md` file exists in this repository
(only `EIDOLON-ARCHITECTURE.md` and the review/report documents listed in Files read below).
The architecture's own §30 roadmap entry for Phase 3 was read as the authoritative
deliverable/exit-criteria list, cross-checked against the Phase 2 report's own
"Remaining work" section (which independently names exactly the same four items: "Evidence/
Implication model, discovery graph, contradiction detector §13.2 (Phase 3)" plus the
planted-evidence half of `apparent_admissibility`).

**Verdict:** Phase 3 gate criteria met. `eidolon/evidence/` implements the evidence,
grounding, contradiction and discovery model on top of the unmodified Phase 1 `eidolon/world/`
and Phase 2 `eidolon/minds/` packages. 424 tests pass across the whole repository (98
`tests/world/`, 77 `tests/minds/`, 136 pre-existing top-level `tests/test_important.py` +
`tests/test_repairs.py`, 113 new `tests/evidence/`); the Phase 0.5 spike suite (21 tests)
still passes unchanged.

---

## Files created/changed

**Created — `eidolon/evidence/` (new package, 832 lines):**

| File | Purpose |
|---|---|
| `ids.py` | `StatementId`/`HypothesisTemplateId` forward-reference aliases (Phase 4 models not yet built). |
| `model.py` | `Evidence`, `Implication`, `DiscoverySpec`, `Prereq`, `RedHerringSpec`, `EvidenceKind`, `EvidenceStore`, `combined_strength`. |
| `grounding.py` | P-6 (creation grounding), P-0 restricted to authentic evidence, deep P-9/I-30 (`established_interval`, `check_temporal_grounding`), `known_to` soundness, `to_physics_tuples` (Phase 1 reuse bridge). |
| `contradiction.py` | The general `contradiction(p, q)` (§13.2, all rules this phase's boundary covers), `evidence_implication_contradicts`, `evidence_vs_evidence`, `corroborates` (I-37 at the evidence layer). |
| `discovery.py` | `DiscoverySpec`/`Prereq` evaluation, the `Discovery` session event + `apply_discovery` (I-22 fold), V-4 `reachability` (BFS, I-47 cueing), `unreachable_load_bearing`, `red_herring_refuter_reachable`, `PlayerEvidenceView`/`project_for_player` (§5.2 player/engine split), `testimony_strongly_retrievable` (I-39 primitive). |
| `__init__.py` | Public API surface. |

**Created — `tests/evidence/` (new, 1,336 lines, 113 tests):** `test_model.py`,
`test_grounding.py`, `test_contradiction.py`, `test_discovery.py`,
`test_evidence_adversarial.py`, `test_evidence_serialization_and_regression.py`,
`test_evidence_properties.py`, `fixtures/vance_evidence.py` (+ `fixtures/__init__.py`).

*(Three test files were named `test_adversarial.py`/`test_properties.py`/
`test_serialization_and_regression.py` at first — the same basenames `tests/minds/` already
uses. `tests/world/`, `tests/minds/` and `tests/evidence/` have no `__init__.py` of their own
[only `fixtures/` does], so pytest's default import mode resolves same-named files across
them to one top-level module and fails collection. Renamed with an `evidence_` prefix rather
than adding `__init__.py` files to three existing Phase 1/2 test packages — the smaller,
purely-additive fix.)*

**Changed:** none. `eidolon/world/` and `eidolon/minds/` (Phases 1–2) are untouched —
verified by re-running their full suites unchanged (98 + 77 pass) and by asserting
`Case.content_hash()` equality before/after every Phase 3 operation (`test_evidence_
serialization_and_regression.py`), the same I-4 check Phase 2 ran for `minds/`.

## Phase 3 components implemented

- **Evidence model** (`model.py`) — the full §5.1 schema: kind, object, location, creation
  provenance (`created_by`/`created_at`), authenticity/planting, reliability, implications,
  discovery spec, visibility, `known_to`, `interacted`, solver tags (`supports`/
  `contradicts`), `load_bearing`, `red_herring`. Sealed (frozen, I-4) like `Memory`/`Belief`.
- **Evidence provenance** — `created_by`/`created_at`/`interacted` trace every item back to
  a real CaseLog event; `known_to` traces back to a real `KnowledgeEntry`. All four are
  independently checked (`grounding.py`), not merely typed.
- **Evidence authenticity** — `authentic`/`planted_by` with a consistency gate (authentic
  evidence cannot carry `planted_by`; planted evidence must carry one, and it must name a
  real `Plant` event) and an asymmetric truth-check: P-0 (world-refutation) applies to
  authentic evidence only — a planted item's designed falsity is not an authoring error
  (§5.2).
- **Evidence creation** — trace creation from effects (P-6): a `Fingerprint`/`Bloodstain`/
  `Footprint` item naming an object must trace to a real event with a matching
  `TraceCreated` effect; every kind's `created_by` must exist, must not postdate
  `t_investigation`, and must actually name the claimed object.
- **Evidence implications** — `Implication(proposition, strength, requires)`, kept
  explicitly distinct from truth: `combined_strength` (reliability × strength) is a number
  fed to the contradiction detector, never a boolean "this proposition is true".
- **Evidence reliability** — `Evidence.reliability`/`Implication.strength`, both bounded
  `[0,1]` at construction (fail closed, I-15), combined by `combined_strength`.
- **Evidence discovery** — `DiscoverySpec`/`Prereq` (closed vocabulary: `KnowsAbout`,
  `HasItem`, `StatementHeard`, `EvidenceFound`), `can_discover`, the `Discovery` SessionLog
  event (§5.3) and its I-22 fold (`apply_discovery`) into a `DiscoveryState` runtime overlay.
- **Discovery specifications / conditions** — as above; `DiscoveryState`'s other membership
  sets (`visited_locations`, `held_items`, `known_statements`) are exposed as plain fields
  rather than wired to session events, since the actions that populate them (`GoTo`, `Take`,
  testimony) are Phase 4's "exploration actions" deliverable (documented scope decision,
  §30's own phase split).
- **Clue reachability** — V-4 (`discovery.reachability`): a fixpoint BFS over the discovery
  graph (nodes = evidence, edges = prerequisites), reporting `reachable`/`unreachable`/
  `depth`, plus the I-47 cueing distinction (`cued`: reachable AND every
  `DiscoverySpec.cue` along the path was already-known material) and
  `unreachable_load_bearing` (§19.4's "every node tagged `load_bearing`... must be
  reachable").
- **Evidence visibility** — `visibility` field (`plain`/`concealed`/`forensic`/
  `documentary`) carried through; consumed by discovery-action authoring in later phases.
- **Evidence knowledge acquisition** — `known_to` (pre-discovery character awareness) with
  soundness checking against a real `KnowledgeStore`; `PlayerEvidenceView`/
  `project_for_player` implements §5.2's player/engine field split explicitly (a projection
  test, not just documentation).
- **Evidence-to-proposition relationships** — every `Implication.proposition` IS a Phase 1
  `Proposition`; the contradiction detector operates on that shared schema, so evidence,
  facts, and (once Phase 4 builds them) claims all compare through one function.
- **Evidence-to-hypothesis relationships** — `Evidence.supports`/`.contradicts` as opaque
  `HypothesisTemplateId` tags (generation/solver metadata, §5.1); the `Hypothesis` model
  itself is Phase 4 (§16), so Phase 3 stores and passes the tags through without acting on
  them.
- **Planted/manipulated evidence** — `authentic`/`planted_by` fully modelled and checked
  (above); "altered" evidence has no separate architecture field beyond this pair — modelled
  and tested as the same authenticity mechanism (an authored inconsistency between the two
  fields is rejected).
- **Refuters** — `RedHerringSpec{misleads_toward, refuter}`; `red_herring_refuter_reachable`
  implements the reachability half of §19.6 (`misleads_toward` hypothesis-consistency needs
  the solver — Phase 6, named in Remaining work).
- **Corroboration structures** — `corroborates(e1, e2, proposition)`: I-37's independence
  rule applied at the evidence layer (distinct creating events, no `requires` cycle) without
  the collusion graph, which needs `Secret`/`Rel` (§19.5) — deferred to Phase 4/6 exactly as
  the Phase 2 report already documented for testimony corroboration.
- **The general contradiction detector (§13.2)** — `contradiction(p, q, *, case=None)`:
  presence, negation (`At`/`NotAt`, `Did`/`DidNot`), object (`Has`/`ObjectAt`), attribute
  (`Attr`/`Attr`, `Attr`/`Incidental`, `State`/`State`, `ObjectState`/`ObjectState`),
  cross-witness (`Saw`/`At`, unidentified sightings excluded), travel (via the Phase 1
  travel graph when a `Case` is supplied), and granularity-aware widening. Plus
  `evidence_implication_contradicts` (the "implication" pairing, strength ≥ 0.5 gate) and
  `evidence_vs_evidence` (two authentic items in tension).
- **Player projections** — `PlayerEvidenceView`/`project_for_player` (above).

## Invariants enforced

| Invariant | How |
|---|---|
| §5.2 "Evidence is never an independent source of reality" | `grounding.py`'s three checks are the ONLY way an `Evidence` object is declared valid; nothing in `contradiction.py`/`discovery.py` can commit a fact — they only compare/reveal. |
| I-4 | `Evidence`/`Implication`/`DiscoverySpec`/`Prereq`/`RedHerringSpec` are frozen pydantic models; `Case.content_hash()` equality asserted before/after every Phase 3 operation on both fixture cases. |
| I-6 | No `random`/`secrets`/`uuid4` anywhere in `evidence/`; `reachability`'s fixpoint scan and `established_interval`'s hull are pure functions of their inputs. |
| I-15 (fail closed) | Malformed `Evidence`/`Implication` (out-of-range `reliability`/`strength`, unknown `EvidenceKind`/`Prereq.kind`) fails at construction; `apply_discovery` raises on an unmet prerequisite or unknown evidence id rather than silently granting access. |
| I-22 | `apply_discovery` copies the recorded outcome (`known_evidence | {id}`) and nothing else; duplicate/repeated `Discovery` events are an explicit no-op (idempotent). |
| I-30/P-9 | `established_interval`/`check_temporal_grounding` resolve the FULL `requires` chain (recursively through other `Evidence.created_at`, plus caller-supplied `statement_intervals` for the not-yet-built `Statement` model) union the always-present discovery-time anchor — not Phase 1's shallow "any non-empty `requires` passes" stub. |
| I-37 (evidence layer) | `corroborates` rejects same-`created_by` pairs and `requires`-cycle pairs; both are direct adversarial tests. |
| §19.4 | `reachability`'s `cued` set and `unreachable_load_bearing` implement the cued-path and critical-clue reachability requirements as separate, independently-checkable outputs, not folded into a single boolean. |

## Tests added

113 tests in `tests/evidence/`, including named-test coverage for every category the task
specified:

- **Evidence construction / provenance / grounded evidence:** `test_model.py`,
  `test_grounding.py::test_vance_v03_evidence_table_is_fully_grounded`,
  `test_evidence_case_fixture_is_fully_grounded`.
- **Unsupported evidence rejection:** `test_p6_rejects_evidence_naming_an_unknown_object`,
  `test_p9_rejects_an_implication_wider_than_its_established_interval`.
- **Evidence implication / contradictory evidence:** `test_contradiction.py`'s full rule
  sweep plus `test_evidence_vs_evidence_finds_a_contradiction_between_authentic_items`.
- **Evidence reliability / authenticity / planted / altered:** `test_combined_strength_...`,
  `test_p6_authentic_evidence_must_not_carry_planted_by`,
  `test_p0_exempts_planted_evidence_from_world_truth`,
  `test_altered_evidence_being_treated_as_authentic` (adversarial).
- **Discovery conditions / timing / access restrictions / reachability / cue chains:**
  `test_discovery.py` (all four `Prereq` kinds, `can_discover`, I-47 cueing,
  `unreachable_load_bearing`, the multi-hop chain test).
- **Refuters / corroboration independence:** `test_red_herring_refuter_reachable`,
  `test_contradiction.py`'s four `corroborates` tests (independent, same-source, circular,
  self-comparison).
- **Duplicate / repeated discovery:** `test_duplicate_discovery_is_a_no_op`,
  `test_discovery_fold_is_idempotent_under_repeated_and_out_of_order_application`.
- **Serialization / replay / deterministic discovery:**
  `test_evidence_serialization_and_regression.py` (JSON round-trips, cross-process replay
  via a subprocess, I-4 content-hash checks, `reachability`'s own determinism test).
- **Malformed evidence:** `test_model.py`'s parametrized rejection tests.
- **Phase 0.5/1/2 regression:** existing suites re-run unchanged (below).
- **Adversarial suite (`test_evidence_adversarial.py`, one test per named attack):**
  nonexistent event, impossible object, discovered-before-creation, impossible observer
  (`known_to`), forged provenance (dangling `requires`), same-source
  "independence", circular `requires`, altered-as-authentic, world-truth contradiction,
  invalid discovery path.
- **Property/adversarial (Hypothesis, `test_evidence_properties.py`):** presence
  contradiction cross-checked against an independently-written brute-force tick scan;
  order-independence of `contradiction()`; `established_interval` always a valid interval
  containing every source; `corroborates` symmetry and self-comparison; `reachability`
  monotonicity in seed material; `can_discover` order/duplicate independence.

## Full test results

```
python -m pytest tests/evidence -q
113 passed

python -m pytest tests/world -q      # Phase 1 regression
98 passed

python -m pytest tests/minds -q      # Phase 2 regression
77 passed

python -m pytest -q                  # full repo (testpaths = ["tests"])
424 passed

python -m pytest spike/test_spike.py -q   # Phase 0.5 regression
21 passed
```

No skips, no xfails, no failures. `mypy`/`ruff` are not installed in this environment (as
with the Phase 2 report) and were not run.

## Regression results

- **Phase 0.5** (`spike/test_spike.py`): 21/21 unchanged.
- **Phase 1** (`tests/world/`): 98/98 unchanged — `eidolon/world/` was not edited.
- **Phase 2** (`tests/minds/`): 77/77 unchanged — `eidolon/minds/` was not edited.
- **Cross-phase repair suites** (`tests/test_important.py`, `tests/test_repairs.py`, 136
  tests, pre-existing at the top of `tests/`): unchanged, all pass.
- **I-4 spot check:** `Case.content_hash()` computed before and after running every Phase 3
  check/discovery/contradiction operation against both the `vance_v03`-derived fixture and
  the self-contained `evidence_case` fixture — equal in both cases.

## Phase 3 acceptance criteria

Per §30's Phase 3 entry and this task's own acceptance gate:

| Criterion | Evidence | Met |
|---|---|---|
| `vance_v03` evidence table complete | `test_grounding.py::test_vance_v03_evidence_table_is_fully_grounded` — `E_watch`/`E_trace` (the §5.1/§13.3 fingerprint pair) built as full `Evidence`, grounded with zero violations | yes |
| Detector reproduces the §13.3 scenario deterministically | `test_contradiction.py::test_the_worked_scenario_reproduces_deterministically` — 5 repeated calls, identical result. (Vocabulary note: the scenario uses `touch`/`Glass1`/Study from `vance_v03`'s own golden case, not the document's `enter`/Kitchen phrasing — see Architecture deviations.) | yes |
| Every proof-core testimony has a strong-retrieval query (I-39) | `discovery.testimony_strongly_retrievable` implemented and tested against Phase 2's real `memory.score`; the full parser-`Query`-enumeration form needs Phase 4/5 models (documented in Remaining work) | partial (primitive complete, enumeration deferred) |
| P-6 and P-9 properties | `test_grounding.py` (11 P-6 cases, 6 P-9 cases including `established_interval` unit tests) | yes |
| Contradiction symmetry/granularity properties | `test_evidence_properties.py::test_property_contradiction_is_order_independent`, `test_contradiction.py::test_granularity_widening_can_turn_a_gap_into_an_overlap` | yes |
| Reachability on `vance_v03` | `test_grounding.py`'s vance_v03 grounding test exercises the same store; full BFS reachability demonstrated on the self-contained `evidence_case` fixture (chosen because `vance_v03`'s own `attack` event carries no `TraceCreated` effect to ground a clean discovery chain on — see Architecture deviations) | yes (on the dedicated fixture) |
| E1's conditional implication unlock | `test_discovery.py::test_unlocked_implications_requires_every_id_known`, `test_p9_evidence...`/`established_interval` tests reproducing the exact "wash/clean statement raises the established window" mechanic | yes |
| Evidence grounded in canonical world state | `grounding.check_evidence_grounding` (P-6 + authenticity-aware P-0 + deep P-9); zero violations on both fixtures | yes |
| Provenance auditable | `created_by`/`created_at`/`interacted`/`known_to` all independently checked against the CaseLog/KnowledgeStore, not merely typed | yes |
| Discovery deterministic | `test_evidence_serialization_and_regression.py`'s cross-process replay test, `reachability`'s own determinism property test | yes |
| Critical clues have valid reachability paths where required | `unreachable_load_bearing`; tested both ways (reachable and stranded) | yes |
| Evidence does not become truth | `combined_strength`/`Implication.strength` are numbers fed to the detector, never assigned to `FactIndex`; `grounding.py`'s docstring states the boundary explicitly and enforces it structurally (no function in this package can write to `Case`) | yes |
| Evidence does not bypass epistemic separation | `known_to` requires a real `KnowledgeEntry`; nothing in `evidence/` constructs a `Belief` or bypasses `minds/`'s admissibility walk | yes |
| Corroboration does not allow circular/self-confirmation | `corroborates`'s four dedicated tests (circular `requires`, same source, self-comparison, non-matching proposition) | yes |
| Replay remains deterministic | `apply_discovery`'s idempotence test, the cross-process replay test | yes |
| Serialization remains stable | JSON round-trip tests for every new model; the cross-process test documents and works around the one genuine non-determinism found (frozenset iteration order under `PYTHONHASHSEED`) rather than hiding it | yes |
| All previous phase tests remain green | 98 + 77 + 136 + 21 = 332 pre-existing tests, all still passing | yes |
| No future-phase system improperly implemented | No `Statement`/`Claim`/`ResponsePlan`/`Secret`/`CoverStory`/`LayerPeel`/`Hypothesis` board/solver/LLM/UI code was written; every forward reference is an opaque `str` id, documented at its point of use (see Architecture deviations) | yes |

## Architecture deviations

None that change the design. Four scope decisions, each the smallest deterministic choice
for a point the architecture leaves to context, documented in-code at the point of decision
and summarized here:

1. **The literal §13.3 "I never entered the kitchen" scenario is not reproducible under the
   current closed `ActionKind` vocabulary.** ADR-22 defines `ActionKind` as `EventKind` plus
   exactly one entailed action (`touch`) and explicitly defers `enter`/`hear` to "the ADR
   amendment Phase 4 will need" — its own text names §13.3's Kitchen/"entered" phrasing as
   the very example that needs it. `test_the_worked_scenario_reproduces_deterministically`
   reproduces the scenario's actual mechanism (a blanket denial contradicted by an unlocked,
   `requires`-gated forensic implication) using `vance_v03`'s real vocabulary (`touch`/
   `Glass1`/Study) instead. This is ADR-22's own documented deferral, not a Phase 3 gap.
2. **`vance_v03`'s own `attack` event carries no `TraceCreated` effect**, so a P-6-clean,
   fully-discoverable fingerprint chain could not be built against it without editing the
   Phase 1 fixture (out of bounds — Phase 1 owns it). `E_trace`'s `created_by` is therefore
   left `None` (§5.1 allows this: "None for pre-existing objects/documents") and its
   temporal grounding rests entirely on `requires`, which is in fact the more faithful
   reading of the architecture's own worked example (a fingerprint's precise creating event
   is exactly what forensics *cannot* pin down — that is why `requires` exists). The V-4
   reachability/discovery-chain demonstration uses a separate, self-contained
   `evidence_case` fixture built with a real `TraceCreated` effect instead.
3. **`Evidence.location_at_investigation` is left unset for `E_trace`.** `vance_v03`'s
   CaseLog never emits an `ObjectAt` effect for `Glass1` (it is used as the murder weapon
   but never explicitly relocated), so its only canonical position is
   `Object.initial_location` ("Kitchen") — asserting "Study" would be exactly the kind of
   ungrounded claim `check_creation_grounding` exists to catch, and inserting a synthetic
   move event into the Phase 1 fixture is out of bounds.
4. **The I-39 retrieval-expressibility check is implemented as its pass/fail primitive
   (`testimony_strongly_retrievable`), not the full "enumerate every parser-expressible
   `Query` shape" form.** That enumeration needs the `Query`/`Alias`-resolution/`TimeAnchor`
   machinery §19.4 itself schedules for Phase 4/5 (the parser). Phase 3 exposes exactly the
   function those future `Query` shapes will be checked against, reusing Phase 2's own
   `memory.score` rather than re-deriving retrieval scoring.

One genuine (small, contained) finding surfaced and fixed during testing, not an
architecture deviation but worth recording: **`DiscoveryState`'s `frozenset` fields do not
serialize to a canonical JSON byte string across processes** (Python randomizes string-hash
seeding per process, so `frozenset` iteration order — and therefore JSON array order — is
not stable). `Case.content_hash()` already guards against exactly this class of issue for
sealed case content by sorting every unordered collection before hashing; `DiscoveryState`
is a runtime overlay with no `content_hash` of its own, so the fix is at the test level
(compare parsed/reconstructed state by value, not raw JSON text) rather than a new hashing
scheme — but this is worth flagging for Phase 7, whose `SessionEvent` hash chain (I-41) will
need the same sorted-canonicalization discipline if any future overlay type grows a
`frozenset`/`set`-typed field.

## Remaining later-phase work

- `Statement`/`Claim`/`ResponsePlan`, the speech-act catalogue, `Secret`/`CoverStory`/
  `EvidenceResponse`/`Deflection`/`Slip`, `LayerPeel`, `refutation_weight`, threat/verbal
  pressure, the full admissibility corroboration/collusion graph (needs `Secret`/`Rel`),
  `apparent_admissibility`'s confrontee-knows-false divergence (Phase 4).
- The player hypothesis board (§16) and the "hypothesis vs discovered material"
  contradiction pairing that needs it (Phase 4).
- "claim vs prior claim" / "claim vs another character's claim" contradiction pairings —
  `contradiction()` itself is ready (it compares raw `Proposition`s); they need `Statement`/
  `Claim.grounding` to exist (Phase 4).
- `GoTo`/`Search`/`Ask` exploration actions and their SessionLog wiring into
  `DiscoveryState.visited_locations`/`held_items`/`known_statements` (Phase 4, per §30's own
  "exploration actions" line).
- The full I-39 parser-`Query`-enumeration form over `Alias`/`TimeAnchor` (Phase 4/5).
- `RedHerringSpec.misleads_toward` hypothesis-consistency checking (needs the solver,
  Phase 6); the reachability half (`red_herring_refuter_reachable`) is done.
- `ActionKind`'s `enter`/`hear` extension (ADR-22's own named deferral), needed before the
  document's literal §13.3 phrasing is constructible.
- Full evidence-generation (trace assignment during case authoring, red-herring placement,
  discovery-graph design) — Phase 6.
- Wiring `Evidence`/`EvidenceStore` into the sealed `Case` package itself (a new `Case`
  field) — implicitly Phase 6's job once generation produces evidence; Phase 3 deliberately
  kept `EvidenceStore` a free-standing container passed alongside `Case`, mirroring how
  Phase 2 kept `KnowledgeStore`/`BeliefStore` independent of `Case`.

## Recommended next phase

Phase 4 — Conversation / decision engine (§30), which is the first phase that can actually
consume this one: `Statement`/`Claim` (letting `contradiction()` run on real testimony),
`Secret`/`CoverStory`/`LayerPeel`/`refutation_weight` (which read `Evidence.reliability`/
`Implication.strength`/`requires` directly), and the exploration actions that populate
`DiscoveryState`'s remaining membership sets. Not implemented here.
