# EIDOLON — Phase 3 Repair Report (hostile-audit remediation)

**Companion to:** `docs/EIDOLON-PHASE-3-REPORT.md` (the original implementation report).
**Source of the findings:** an independent hostile review of the Phase 3 evidence/discovery
system, conducted 2026-09-05 against the code as shipped, with 48 executed attacks.
**Repair dates:** 2026-09-07 (5 BLOCKING), 2026-09-07 (11 IMPORTANT). Report written 2026-09-09.
**Published audit artifact:** https://claude.ai/code/artifact/be7a7e09-20cb-4927-978a-ef142000042e

**Status: all 16 findings resolved. BLOCKING 0, IMPORTANT 0. Phase 4 readiness: YES.**
Phase 4 has NOT been started.

---

## 1. Measured results (2026-09-09, re-verified for this report)

| Suite | Command | Result |
|---|---|---|
| Full repository | `python -m pytest -q` | **480 passed** |
| Phase 0.5 spike | `python -m pytest spike/test_spike.py -q` | **21 passed** (1 warning) |
| Phase 1 | `python -m pytest tests/world -q` | **98 passed** |
| Phase 2 | `python -m pytest tests/minds -q` | **77 passed** |
| Phase 3 | `python -m pytest tests/evidence -q` | **169 passed** |
| Cross-phase repairs | `python -m pytest tests/test_important.py tests/test_repairs.py -q` | **136 passed** |

480 = 98 (Phase 1) + 77 (Phase 2) + 136 (cross-phase) + 169 (Phase 3). The spike suite is
outside `testpaths` and is run separately.

**Test-count history:** 424 at the original Phase 3 report → 439 after the BLOCKING repairs
(+15) → 480 after the IMPORTANT repairs (+41). No test was deleted; three pre-existing tests
were corrected (§4).

**Determinism: PASS.**
- `reachability` over 6 `EvidenceStore` insertion permutations → 1 identical result
  (`reachable`, `cued`, `depth`, `cued_depth`).
- 4 `PYTHONHASHSEED` values × fresh interpreters → 1 identical reachability + fold result.
- `Case.content_hash()` unchanged before/after every Phase 3 operation on both fixtures (I-4).
- `apply_discovery` idempotent under repeated and out-of-order application.

**Attack re-run: 46 of 48 DEFENDED.** The 2 still open are `A-25` (`Discovery.turn` carries
no ordering constraint) and `A-44` (`DiscoveryState` JSON is not byte-canonical across
`PYTHONHASHSEED`). Both were classified **NON-BLOCKING** by the original audit, were never in
the 16 findings scoped for repair, and are recorded in §6 as carried forward.

---

## 2. The five BLOCKING findings — resolved

| ID | Finding | Fix | Location |
|---|---|---|---|
| **B-1** | I-47 cueing was a per-node flag, so an item counted as fully cued through an *uncued* prerequisite | Ported the Phase 0.5 spike's `cue_closure` semantics (`spike/solve.py`): the cued closure runs `can_discover` against a state whose `known_evidence` is the **cued** set, and only cued items contribute names | `evidence/discovery.py` |
| **B-2** | `DiscoverySpec.at` was never validated, so a prerequisite-free item at any string was reachable, cued, depth 0 from an empty seed set | Canonical half: P-6 rejects an `at` that is neither a known location nor object. Reachability half: `_cue_satisfied` requires `at ∈ named` (the spike's `it.at in named`). Added `uncued_load_bearing()` for §19.4's cued-path gate | `evidence/grounding.py`, `evidence/discovery.py` |
| **B-3** | `reachability` mutated traversal state mid-pass, making `depth`/`cued` a function of `EvidenceStore` insertion order | Two level-synchronous closures: each pass computes its whole frontier against the previous level's state before applying it; items iterated in sorted id order. Added `cued_depth` for §19.4's "minimum cued discovery depth" | `evidence/discovery.py` |
| **B-4** | `corroborates` counted four kinds of dependent evidence as independent sources (I-37) | Four clauses: planted items are never a source (§19.5 L0); missing `created_by` is unknown provenance, not distinct provenance (fail closed); neither item may lie in the other's **transitive** `requires` closure; closures may not intersect (shared ancestor = shared source) | `evidence/contradiction.py` |
| **B-5** | Granularity WIDENED intervals, manufacturing overlaps across real gaps and inverting §13.2's "a sharp claim inside a vague one is not a contradiction" | New `asserted() = shrink(interval, granularity)` — what a claim at granularity *g* actually commits to; `None` asserts nothing and cannot contradict. Applied in all three interval rules; travel measures the gap on asserted intervals | `evidence/contradiction.py` |

**Regression tests:** `tests/evidence/test_blocking_regressions.py` — 15 tests.

---

## 3. The eleven IMPORTANT findings — resolved

| ID | Finding | Fix | Location |
|---|---|---|---|
| **F-1** | P-0 could not refute object / attribute / state / `Moved` claims: `truth_value` returns the same Unknown for "the world does not settle this" and "the world has never heard of this entity" | (a) `FactIndex.case_object_holder` falls back to `Object.initial_location` — one authority, where `grounding` already had the fallback and `FactIndex` did not. (b) New `check_reference_integrity` walks the closed schema slot by slot via new `propositions.entities()` (ported from the spike's `Prop.entities()`), checking PRESENT IN WORLD before GROUNDED | `world/facts.py`, `world/propositions.py`, `evidence/grounding.py` |
| **F-2** | The forensic-trace warrant was opt-in — the `TraceCreated` check sat inside `if created_by is not None` | An unpinned trace is the weaker claim, not no claim: with `created_by` unset, some event in the CaseLog must still carry a `TraceCreated` on that object | `evidence/grounding.py` |
| **F-3** | The dangling-`requires` check sat *below* the `interval is None` guard, so forged provenance passed on `Attr`/`Rel`/`Motive`/`Moved`/`Incidental` implications | Hoisted above the guard. Referential integrity now runs on every implication; the hull check still runs only on interval-bearing ones | `evidence/grounding.py` |
| **F-4** | `known_to` was a live dict on a `frozen=True` model — post-seal provenance rewrite (I-4) | Reused Phase 1's existing `world/frozen.py` `Frozen`/`FrozenDict`, the same guard `Case.actors`/`.locations`/`.objects` already use. No new mechanism | `evidence/model.py` |
| **F-6** | `Did`/`DidNot` ignored the `location` slot (false positives), missed the `object=None` wildcard (§13.3's own blanket-denial shape), and dropped granularity | New `_denies()`: a `None` slot on the **denial** side is a wildcard; on the **assertion** side it stays existential — matching `FactIndex._tv_Did`'s own reading. `location` compared; granularity applied via `asserted()` | `evidence/contradiction.py` |
| **F-7** | `visible_to_player` was hard-coded `True` per rule; §13.2 defines it as "both sides in player's material" | Rules report the structural verdict only; `contradiction()` takes `player_material` and decides visibility in one place. Omitting it yields `False` (fail closed). `Incidental` pairings stay engine-side unconditionally | `evidence/contradiction.py` |
| **F-8** | `evidence_vs_evidence` refused the planted pairing §13.1 names it for ("planted-evidence tension; validator") | Gate dropped; tension reported for every pair. The caller holds the flags and separates the two uses — V-1's "two authentic items in tension" is a one-line filter. Authenticity never enters the returned `Contradiction` | `evidence/contradiction.py` |
| **F-9** | `Discovery.action` / `at` were never validated — both fields were decorative, collapsing DISCOVERABLE into DISCOVERED | Both compared against the item's own `DiscoverySpec`; mismatch raises (I-15) | `evidence/discovery.py` |
| **F-10** | `project_for_player` was not gated on discovery — an undiscovered item returned its full `reveals_text`, kind and location | Takes a `DiscoveryState`, returns `None` for an undiscovered item; unlocks read `known_evidence \| known_statements` from that same state | `evidence/discovery.py` |
| **F-11** | A forged `DiscoveryState` was trusted by every reader; the fold was the only *checked* path, not the only path | `check_discovery_state(state, store)` — the same answer Phase 2 gives for hand-built knowledge in `minds/soundness.py`, one layer up. Reports unknown ids and any member no legal discovery order could have admitted | `evidence/discovery.py` |
| **F-13** | `known_to` bound awareness to a person, not to the item: any other entry of that actor's satisfied the field, so a sealed binding silently rebinds when positional `K%04d` ids shift | A sound binding must ground in the item: the entry's provenance names one of the item's own events (`created_by`/`planted_by`/`interacted`), or its proposition names the item's object. Plus an actor-exists check | `evidence/grounding.py` |

**Regression tests:** `tests/evidence/test_important_regressions.py` — 41 tests.

*(F-5 and F-12 were classified NON-BLOCKING by the audit and are carried forward — see §6.)*

---

## 4. Files changed

**Implementation (`eidolon/`):**

| File | Findings |
|---|---|
| `eidolon/evidence/discovery.py` | B-1, B-2, B-3, F-9, F-10, F-11 |
| `eidolon/evidence/contradiction.py` | B-4, B-5, F-6, F-7, F-8 |
| `eidolon/evidence/grounding.py` | B-2, F-1, F-2, F-3, F-13 |
| `eidolon/evidence/model.py` | F-4 |
| `eidolon/evidence/__init__.py` | exports `uncued_load_bearing`, `check_discovery_state`, `check_reference_integrity` |
| `eidolon/world/facts.py` | F-1 (`case_object_holder` falls back to `Object.initial_location`) |
| `eidolon/world/propositions.py` | F-1 (new `entities()` helper; no schema change) |

`eidolon/minds/` is untouched.

**Fixture (`tests/world/fixtures/vance.py`)** — one deliberate correction, see §5.

**Tests (`tests/evidence/`):**

| File | Change |
|---|---|
| `test_blocking_regressions.py` | **new**, 15 tests |
| `test_important_regressions.py` | **new**, 41 tests |
| `test_contradiction.py` | 3 tests corrected (below) |
| `test_discovery.py` | 2 tests corrected (below) |

**Corrected pre-existing tests.** Each encoded a defect as its expected behaviour, or used an
API whose contract changed. None was weakened.

1. `test_granularity_widening_can_turn_a_gap_into_an_overlap` → renamed
   `test_granularity_never_manufactures_an_overlap_across_a_gap`. It asserted B-5's failure
   mode as its pass condition.
2. `test_reachability_is_cue_aware_i47` — relied on B-3's ordering artifact. Its seed material
   now names the knife the player can see at case start; its intent (E_letter uncued, the
   other two cued) is unchanged and now true for the right reason.
3. `test_evidence_vs_evidence_excludes_planted_items` → renamed
   `test_evidence_vs_evidence_reports_planted_tension_the_caller_classifies_it` (F-8).
4. `test_presence_contradiction_...`, `test_attr_vs_attr_...`, `test_incidental_vs_attr_...`
   now pass `player_material` (F-7's changed contract).
5. `test_player_view_hides_engine_only_fields`, `test_player_view_only_shows_unlocked_implications`
   now pass a `DiscoveryState` (F-10's changed contract).

---

## 5. One Phase 1 fixture defect exposed and corrected

Fixing F-2 surfaced a latent defect in the Phase 1 golden fixture. `vance_v03` declares
`Glass1` as `traceable=("fingerprint",)` and has David handle it bare-handed in the `attack`
event, yet the fixture contained **zero** `TraceCreated` effects anywhere — so its flagship
`E_trace` fingerprint had no cause in the world at all.

§5.2 is explicit: "Evidence is created by events. A fingerprint exists because a `Use(glass)`
event with a `TraceCreated` effect occurred", and the validator must verify "that every cause
that *should* create a trace did". The missing effect was added to the `attack` event rather
than weakening P-6.

`E_trace` still leaves `created_by` unset, which remains the correct §13.3 semantics: which
handling left the mark is exactly what forensics cannot pin down, and that is what `requires`
grounds. Phase 1's 98 tests pass unchanged; no Phase 1 test pins a literal content hash.

---

## 6. Carried forward (NON-BLOCKING, unchanged, not in scope for this repair)

These were classified NON-BLOCKING by the audit and were deliberately not addressed:

- **F-5** — `established_interval`'s hull is permissive: one early `requires` licenses the
  span to `t_investigation + 1`, and intermediate interruptions are invisible.
- **F-12 / attack A-25** — `Discovery.turn` carries no constraint or ordering; turn
  monotonicity belongs to Phase 7's SessionLog.
- **Attack A-44** — `DiscoveryState` JSON is not byte-canonical across `PYTHONHASHSEED`
  (frozenset iteration order). Values compare equal; only the byte rendering varies.
  `Case.content_hash()` already demonstrates the sorted-canonicalization pattern this needs.
  Relevant to Phase 7's I-41 hash chain.
- `Contradiction` has no `id` field (§13.2 lists `id: ContradictionId`); Phase 4's I-38
  retraction filter will want one.
- `Said(p)` nesting is not decomposed — belongs with Phase 4's reported-speech handling.
- `Evidence.location_at_investigation` is optional where §5.1 types it required.
- An implication at `strength=0.0` yields `None`, indistinguishable from "no tension".

**Known Phase 4 hand-off notes (not defects):**

- `DiscoveryState`'s `visited_locations` / `held_items` / `known_statements` are read as
  authoritative by `_prereq_met` and `_cue_satisfied` and are populated by nothing. Phase 4's
  exploration actions (`GoTo`/`Take`/testimony) wire them. `check_discovery_state` is the
  guard for hand-built states in the meantime.
- Phase 2's `KnowledgeEntry` ids remain positional (`K%04d`). F-13 makes a silent rebind
  **detectable**, not impossible. Changing the id scheme is a Phase 2 decision.

---

## 7. Verification method

Every fix was verified three ways, not by the passing suite alone.

**1. Reproduce first.** Each of the 16 findings was reproduced against the then-current code
before any edit, and re-probed afterwards by an independent script (not the new tests).

**2. Mutation verification.** For each fix, the pre-fix behaviour was re-introduced in an
isolated copy of the repository and the regression suite re-run, confirming the test actually
catches the defect rather than restating the implementation. **18 mutants, 18 caught** — 6 for
the BLOCKING set, 12 for the IMPORTANT set. Two tests were strengthened when this step showed
them passing under their own mutant:

- `test_b3_depth_is_a_true_bfs_depth_along_a_dependency_chain` — its ids sorted in the
  non-exposing order, so the mutant survived. Now asserts both id orderings.
- The B-3 permutation test could not expose mid-pass mutation once iteration was sorted; the
  strict-depth test covers it.

**3. Fresh focused audit.** After the IMPORTANT repairs, an independent sweep over the
repaired areas, their interfaces, and their interaction with the five earlier blocker fixes:
B-1…B-5 all still hold; F-6 × B-5, F-7 × F-8, F-9 × F-10, F-11 × B-3 interactions clean;
0 of 9 malformed discovery events accepted; player view is exactly
`{id, kind, location, reveals_text, unlocked}`; visibility lattice
`[None, ∅, one-side, other-side, both] → [F, F, F, F, T]`; reference integrity catches a
nonexistent actor in every slot including nested `Said` and `Solution`, with zero false
positives on real entities.

One check in that sweep initially failed. It was the **probe**, not the code: it asserted
`E_fp` was found while recording that the kit was never held. `check_discovery_state` is
correct to refuse that state, and accepts the same evidence set once the state records its
seed material. Recorded here rather than silently corrected.

---

## 8. Boundaries preserved

The audit's central question was whether evidence could become an untrusted second source of
truth. It cannot, and the repairs did not relax that:

- `eidolon/evidence/` constructs no `Belief` and no `KnowledgeEntry`, and writes to no `Case`,
  `FactIndex` or `KnowledgeStore`. Verified by grep, not by assertion (attacks A-47, A-48).
- The six states the brief named stay distinct: **PRESENT IN WORLD** (`check_reference_integrity`)
  → **GROUNDED** (P-6 / P-0 / P-9) → **DISCOVERABLE** (`can_discover`, cued closure) →
  **DISCOVERED** (`apply_discovery`, `check_discovery_state`) → **VISIBLE TO PLAYER**
  (`project_for_player`, `visible_to_player`) → **KNOWN BY CHARACTER** (`known_to` soundness).
- "Two evidence records" is not "two independent sources": `corroborates` requires distinct
  known origins, authenticity, and disjoint transitive derivation.
- Fail-closed throughout: unknown provenance, unresolvable derivation graphs, unvouched
  player material and mismatched discovery events all resolve to refusal, never to permission.

---

## 9. Reproducing this report

```
python -m pytest -q                                     # 480 passed
python -m pytest tests/world -q                         # 98  (Phase 1)
python -m pytest tests/minds -q                         # 77  (Phase 2)
python -m pytest tests/evidence -q                      # 169 (Phase 3)
python -m pytest tests/test_important.py tests/test_repairs.py -q   # 136
python -m pytest spike/test_spike.py -q                 # 21  (Phase 0.5)
```

The two regression suites are the durable record of the 16 findings:
`tests/evidence/test_blocking_regressions.py` and
`tests/evidence/test_important_regressions.py`. Each test's docstring names the finding it
guards and the failure mode it reproduces.

**Phase 4 has not been started.** No `Statement`, `Claim`, `ResponsePlan`, `Secret`,
`CoverStory`, `LayerPeel`, hypothesis board, solver, LLM or UI code exists.
