# EIDOLON — Phase 2 Implementation Report

**Target:** `docs/EIDOLON-ARCHITECTURE.md` §30 "Phase 2 — Character / knowledge / memory".
**Date:** 2026-09-03.
**Scope note:** no `docs/EIDOLON-IMPLEMENTATION-CONTRACT.md` file exists in this repository
(only `EIDOLON-ARCHITECTURE.md`, `EIDOLON-ADVERSARIAL-REVIEW.md`, `EIDOLON-OPUS-HOSTILE-REVIEW.md`,
`EIDOLON-PHASE-0.5-REPORT.md`). The architecture document's own roadmap entry for Phase 2
(§30) was read as the authoritative deliverable/exit-criteria list for this phase; Part III
("Minds", §6-9) supplied the data models and rules. This is a documented fact, not a stop
condition — the architecture is fully self-contained for Phase 2's scope.

**Verdict:** Phase 2 gate criteria met. `eidolon/minds/` implements the canonical
knowledge/belief/memory/epistemic-state/character-state model on top of the unmodified
Phase 1 `eidolon/world/` package. 137 tests pass across the whole repository (61 Phase 1
`tests/world/`, 76 new `tests/minds/`); the Phase 0.5 spike suite (21 tests) still passes
unchanged.

---

## Files created/changed

**Created — `eidolon/minds/` (new package, 1359 lines):**

| File | Purpose |
|---|---|
| `ids.py` | `KnowledgeEntryId`/`BeliefId`/`MemoryId` aliases. |
| `provenance.py` | The closed `Provenance` union (§6.2) and `AdmissibilityLevel`/`level_below`. |
| `knowledge.py` | `KnowledgeEntry`, `KnowledgeStore`, `propagate_knowledge()` (perception + Told folding). |
| `belief.py` | `Belief`, `BeliefStore`, `form_beliefs()` (§6.4 rules 1-5), `trust_between()`. |
| `memory.py` | `Memory`, `Distortion`, `CueSet`, `encode_memories()`, `retrieve()`, `score()` (§8). |
| `epistemic.py` | `EpistemicState` overlay, `RecallRecord`, `Revision` (§6.3). |
| `character.py` | `CharacterState`, `Personality`, `Emotion`, `DetectiveModel`, `VoiceSpec` (§9). |
| `events.py` | The 11 Phase-2 `SessionEventKind` payloads + `MindsEvent` union. |
| `fold.py` | `apply_epistemic`/`apply_character` (I-22 fold) + `build_memory_recall_event`. |
| `admissibility.py` | `admissibility_level`, `apparent_admissibility` (§19.5, I-27). |
| `soundness.py` | V-2 knowledge-soundness checker (I-8). |
| `scale.py` | bp/fraction conversion (I-17). |
| `__init__.py` | Public API surface. |

**Created — `tests/minds/` (new, 1196 lines, 76 tests):** `test_provenance_admissibility.py`,
`test_knowledge.py`, `test_belief.py`, `test_memory.py`,
`test_epistemic_and_character_fold.py`, `test_soundness.py`, `test_adversarial.py`,
`test_serialization_and_regression.py`, `test_properties.py`.

**Changed:** none. `eidolon/world/` (Phase 1) is untouched — verified by re-running its
full test suite (61/61 pass) and by `Case.content_hash()` equality before/after every
Phase 2 operation (tested directly).

## Phase 2 components implemented

- **KnowledgeEntry propagation** (`knowledge.propagate_knowledge`) — folds Phase 1's
  `world/perception.derive_perception` (own-presence, co-presence, the gated absence rule,
  event perception, sustained identified observation) into `KnowledgeEntry` with the
  matching `Provenance` variant, plus `Told` entries from `InformationTransferred` effects
  on events the listener actually attended (I-8 enforced structurally: no entry is ever
  emitted for a listener who was not present).
- **Belief formation** (`belief.form_beliefs`) — §6.4 rules 1-5: direct (≥0.6), uncertain
  perception (unidentified form, 0.2-0.6), Told (`trust(A→B) × reliability`), one closed
  inference rule (`opportunity`, ID'd and auditable), and conflict resolution (higher
  confidence kept, loser returned as `suppressed`).
- **Detective-information rule with grounding propagation** — `KnowledgeAdded` (always
  `InvestigationTold`, enforced by `apply_epistemic` raising on any other provenance) +
  `admissibility_level`'s recursive minimum, so anything reached through it is L0 in every
  belief/inference chain it touches (AC-1, I-27).
- **Memory** (`memory.py`) — encoding (§8.2's salience formula), generation-time decay
  (§8.3's exponential), time-granularity banding, `time_compression` distortion assignment
  (§8.7), and pure runtime `retrieve()`/`score()` (§8.4) with strong/weak thresholds,
  cue-overlap Jaccard, and repetition-factor strengthening.
- **Correction rules with the pre-turn snapshot ordering** (§8.6) — `MemoryCorrected`/
  `BeliefRevised` write only the `EpistemicState` overlay; a snapshot taken before a turn's
  events never sees that turn's own corrections (T-6, tested directly).
- **`EpistemicState` overlay and its four event kinds** (§6.3) — `MemoryRecall`,
  `MemoryCorrected`, `BeliefRevised`, `KnowledgeAdded`, each fold-applied as a pure
  post-value copy (I-22).
- **`CharacterState`/`Personality`/`Emotion`/`DetectiveModel`** (§9) — bp-typed runtime
  state (I-17), `composure` reachable only through `ComposureChange` (delivery-only by
  construction — no peel/slip/confession logic exists yet to accidentally read it),
  `DetectiveModel` with no telepathy term.
- **Knowledge-soundness checker (V-2)** — re-derives "positioned to perceive" independently
  of `perception.py`, checks `Told`/`Read`/`Inferred` grounding referential integrity, and
  that `Absence` provenance never grounds a non-`NotAt` proposition (I-34).
- **`admissibility(claim)` / `apparent_admissibility(claim, confrontee, view)`** — base
  provenance-chain minimum (§19.5/I-27's core rule), documented as the pre-corroboration
  half of the full lattice (see Architecture deviations).

## Invariants implemented

| Invariant | How |
|---|---|
| I-4 | Nothing in `minds/` mutates `Case`; `content_hash()` equality asserted after full-pipeline and 200-round-of-churn runs. |
| I-6 | No `random`/`secrets`/`uuid4` anywhere in `minds/`; distortion "seeding" uses a `hashlib.sha256(case.id, memory.id, ...)` deterministic draw (documented in `memory.py`). |
| I-8 | `propagate_knowledge` structurally prevents impossible provenance (Told gated on listener presence); V-2 independently re-checks it; property test sweeps every entry `vance_v03` produces. |
| I-17 | Every `CharacterState`/`EpistemicState` runtime scalar is `int` (bp); `Personality` stays `float` (generation-time, not runtime-mutable, matching the architecture's own code block). |
| I-22 | `apply_epistemic`/`apply_character` copy payload post-values only; no decay/weight/factor is recomputed in the fold (tested: repeated and out-of-order application). |
| I-25 (foundation) | `InvestigationTold` is the only legal `KnowledgeAdded` provenance (enforced, raises otherwise) and always resolves to L0, poisoning any chain — the knowledge-layer precondition for "player assertions never enter breaker sets" (the breaker-set/weight machinery itself is Phase 4). |
| I-27 | `admissibility_level` walks the grounding chain and takes the minimum; `InvestigationTold` poisons; `Told` is one step below the teller's own level. |
| I-31 | Every `CharacterState`/`EpistemicState` field is written by exactly one event kind — asserted by enumerating `model_fields` against the set of fields touched by all 11 kinds (T-23-style test). |
| I-34 | Reused unmodified from Phase 1 (`Absence` provenance, reliability discount); V-2 additionally rejects `Absence` grounding anything but `NotAt`. |

## Tests added

76 tests in `tests/minds/`, including named-test coverage:

- **T-6** (§28.7): `test_t6_pre_turn_snapshot_unaffected_by_same_turns_revision_and_correction`.
- **T-23**-style (I-31 field-coverage): `test_i31_every_characterstate_field_has_a_writing_event_kind`, `test_i31_every_epistemicstate_field_has_a_writing_event_kind`.
- Provenance chain property (I-8): `test_properties.py::test_property_every_generated_entry_is_v2_sound` (Hypothesis, sweeps every `vance_v03` entry).
- Retrieval determinism/monotonicity: `test_property_retrieval_score_monotone_in_memory_strength`, `test_property_retrieval_is_deterministic_pure_function`.
- Distortion bounds: `test_time_compression_distortion_shifts_recalled_interval_within_bound`.
- `vance_v03` knowledge tables vs. hand expectations: `test_vance_v03_knowledge_table_matches_hand_expectations`.
- User-brief adversarial list: wrong location (`test_soundness.py`), insufficient co-presence (`test_soundness.py`, `test_perception`-derived cases), impossible provenance (`test_soundness.py`, `test_provenance_admissibility.py`), belief-promoted-to-fact (`test_adversarial.py`), memory claiming impossible observation (`test_adversarial.py::test_memory_never_bundles_a_belief_the_character_could_not_have_formed`), contradictory epistemic updates / repeated / out-of-order event application (`test_adversarial.py`, `test_epistemic_and_character_fold.py`).
- Serialization round-trip (every Phase 2 model + the `MindsEvent` discriminated union) and replay consistency: `test_serialization_and_regression.py`.
- Phase 0.5/Phase 1 regression: existing suites re-run unchanged (see Test results).

## Test results

```
python -m pytest tests/world -q      # Phase 1 regression
61 passed

python -m pytest tests/minds -q      # Phase 2
76 passed

python -m pytest -q                  # both (repo testpaths)
137 passed

python -m pytest spike/test_spike.py -q   # Phase 0.5 regression
21 passed
```

No skips, no xfails, no warnings (`-W error::UserWarning` clean on `tests/minds`).

## Acceptance criteria

Per §30's Phase 2 entry:

| Criterion | Evidence | Met |
|---|---|---|
| V-2 passes on `vance_v03` | `test_soundness.py::test_v2_passes_on_vance_v03`, `test_serialization_and_regression.py::test_v2_passes_on_vance_v03_full_pipeline` (propagation + belief formation) — 0 violations | yes |
| All §7.1 queries answered from indexes | `test_section_7_1_queries_all_answered_from_indexes` exercises `knowers`, `entry.source`, `entry.acquired_at`, `entry.reliability`, `belief_for`, `type(entry.source)` | yes |
| Sealed case byte-identical after a long session (nothing mutates it) | `test_case_byte_identical_after_a_long_run_of_epistemic_churn` (200 rounds of fold + retrieval activity), `content_hash()` equal before/after | yes |
| Provenance chain property (I-8) | Hypothesis property test over every `vance_v03`-derived entry | yes |
| Retrieval determinism/monotonicity | Two dedicated property tests | yes |
| Distortion bounds | `test_time_compression_distortion_shifts_recalled_interval_within_bound` | yes |
| `vance_v03` knowledge tables match hand expectations | `test_vance_v03_knowledge_table_matches_hand_expectations` | yes |
| T-1, T-6 | T-6 implemented directly (above); T-1's knowledge-layer half (InvestigationTold contributes weight-relevant admissibility 0) is covered — its full form ("contributes weight 0" in `refutation_weight`) needs the Phase 4 weight function and is named in Remaining work | partial (documented) |

## Architecture deviations

None that change the design. Ten scope decisions, each the smallest deterministic choice
for an underspecified point, documented in-code at the point of decision and summarized here:

1. **Corroboration (L1→L2 promotion)** is not implemented — it needs the collusion graph
   over `Secret`/`Rel` (§19.5), and `Secret` is a Phase 4 model. `admissibility_level`
   implements the pre-corroboration base rule (min over the grounding chain) that Phase 3/4
   take a further `min` against once corroboration exists.
2. **`apparent_admissibility` equals `admissibility_level`** at this phase — the two
   diverge only for planted evidence (`Evidence.authentic`, Phase 3) and confrontee-knows-
   false claims (`Claim`/`ResponsePlan`, Phase 4), neither of which exists yet.
3. **Belief rule 2's identity-inference-by-silhouette-margin** sub-clause is a documented
   no-op hook: it needs an observed-attribute payload on `Saw` that the closed proposition
   schema (§4.7) does not carry, and adding one is an ADR-level change this phase does not
   make.
4. **Belief rule 4's inference-rule registry** implements only `opportunity` (the one rule
   the architecture gives a precise formula for); `motive-from-relationship` and
   `consistency` are named but not formalized in the architecture, so they are left for
   whichever phase defines them rather than guessed.
5. **Belief rule 5's conflict check** is narrow — scoped to the four proposition kinds
   rules 1-4 actually produce (`At`/`Saw`/`Heard`/`Attitude`) — not the general
   contradiction detector, which is §13.2 (Phase 3).
6. **Memory distortion auto-assignment** implements `time_compression` only;
   `identity_confusion`/`gap_fill` need data the schema does not carry (per point 3, and
   "unobserved detail" has no defined source to fill from); `conflation`/`suggestion` need
   multi-memory/cross-source context out of a single memory's scope. All five `Distortion`
   kinds are modeled and admissibility/correction-handled identically.
7. **`Distortion.correctable_by` is always empty** — it types `EvidenceId | StatementId`,
   neither of which exists yet (Phase 3/4). The correction *mechanism* (§8.6,
   `MemoryCorrected` + the pre-turn snapshot ordering, T-6) is fully implemented and tested
   against hand-supplied item ids.
8. **`Read`/`Background` provenance are typed but not auto-derived.** `Read` needs a
   document-content model Phase 1's `Object` does not carry; `Background` has no
   generation rule in the architecture (a kind name, not a derivation).
9. **`trust(A→B)`** has no formula in the architecture; `trust_between` uses an authored
   close-`Rel` check (0.8) with a neutral default (0.5), reusing §19.5's own "close
   relation" kind set as the closeness test.
10. **§6.5's "bluff rules with response parity"** decomposes into a knowledge-layer half
    (implemented: `InvestigationTold`/grounding poisoning, point 2 above) and a
    conversational-scoring half (`contradicts_own_belief`/`uncertain_premise` features,
    act-class parity) that needs `Query`/`ResponsePlan` — building those would be
    "conversational dialogue", which this phase's own boundary excludes. Deferred to
    Phase 4, which is where the roadmap's Query/ResponsePlan models are scheduled.

None of these are contradictions in the architecture — each is a forward reference to a
model a later phase introduces, and each decision point is documented in the module that
makes it (searchable via its docstring) as well as here.

## Remaining work (later phases only)

- Corroboration graph, collusion components, `Secret` model, full L1→L2 promotion (Phase 4/6, §19.5).
- Planted-evidence/confrontee-knows-false divergence in `apparent_admissibility` (`Evidence.authentic` — Phase 3; `Claim`/`ResponsePlan` — Phase 4).
- `Query`/`ResponsePlan`/speech-act catalogue, bluff scorer features and response-parity act-class mapping, `refutation_weight`, threat, verbal pressure production logic, peel/slip/confession (Phase 4).
- Evidence/Implication model, discovery graph, contradiction detector §13.2 (Phase 3).
- `Read` document-content model; `Background` generation rule; identity-inference-by-silhouette (needs an ADR extending the closed proposition schema).
- `motive-from-relationship`/`consistency` inference rules; the remaining `Distortion` kinds' auto-assignment; difficulty-band-driven distortion caps (§20.2, Phase 6).
- Full `SessionLog`/hash-chain persistence (Phase 7) — this phase's event *shapes* exist; the store, `expected_seq`, and load/replay machinery do not.
- LayerPeel, murderer strategy, deception generation, UI — explicitly out of this phase's boundary and not started.
