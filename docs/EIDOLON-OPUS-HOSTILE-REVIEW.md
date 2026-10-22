# EIDOLON — Hostile Independent Architecture Review

**Reviewer:** independent adversarial pass (Claude Opus 5)
**Targets:** `docs/EIDOLON-ARCHITECTURE.md` v0.2 · `docs/EIDOLON-ADVERSARIAL-REVIEW.md`
**Date:** 2026-09-02
**Posture:** both documents treated as untrusted proposals; the previous review's conclusions treated as guilty until proven innocent.
**Status:** review only. No repository code was written.

---

## Resolution status (added after v0.3 of the architecture)

The required changes AC-1…AC-9 and the six documented contradictions were applied to `docs/EIDOLON-ARCHITECTURE.md`, which is now **v0.3**. This review is retained unchanged below as the audit trail; the table records what the revision closed.

| Finding | Status in architecture v0.3 |
|---|---|
| D-1 admissibility per-witness | **Resolved** — `Claim.grounding`; `admissibility(claim, confrontee)`; I-27 |
| D-2 pairwise contradiction only | **Resolved** — `feasible(claim_set)` §13.2a; V-3(v); check (f); I-28 |
| D-3 I-16 false via composure | **Resolved** — composure barred from all three gates; `composure_max` deleted; I-29 |
| D-4 golden case v0.2 unsolvable | **Resolved as a defect; the fixture is not replaced by hand** — case demoted to `vance_v02_negative`; P-9 added; `vance_v03` is a Phase 0.5 deliverable produced by the solver |
| D-5 runtime state mutates sealed case | **Resolved** — `EpistemicState` overlay; `strength_0`/`confidence_0`; ADR-20 |
| D-6 event catalogue incomplete | **Resolved** — `ComposureChange`, `CoverStateDelta`, `BeliefRevised`; `Snapshot` removed; I-31 |
| D-7 weight double-counting | **Resolved** — `max` within a causal group; I-32 |
| D-8 peel evaluated only on `Present` | **Resolved** — evaluated every turn over `presented ∩ unlocked`; I-33 |
| D-9 absence conflates five states | **Resolved** — `Absence` provenance; awake/coverage/entrance gates; `Location.entrances`; fragility report; I-34 |
| D-10 zero-weight oracle, bluff detector | **Resolved** — `apparent_admissibility` split from `admissibility`; response parity; bluff bot; I-35, I-40 |
| D-11 `color` bypasses slot checks | **Resolved** — deterministic checks on every segment kind; restrictive `color`; I-36 |
| D-12 `DetectiveModel` telepathy | **Resolved** — term removed |
| D-13 trace atomicity impossible | **Resolved** — traces best-effort post-commit; I-1 restated structurally |
| D-14 check (f) cost and blind spot | **Partly** — the joint-feasibility half is addressed (I-28); the contradiction-candidate context slot was **not** in the required set and remains open. T-25 will measure it. |
| D-15 retrieval degrades proof core | **Resolved** — V-4 retrieval-expressibility check; I-39 |
| D-16 `Outsider` excluded by assertion | **Resolved** — `outsider_excluded()` reachability query |
| D-17 corroboration undefined | **Resolved** — disjoint provenance events; collusion-graph connectivity; I-37 |
| D-18 retracted testimony vs monotonicity | **Resolved** — retracted material weighs zero; layer index is `max` over history; I-38 |
| D-19 layer-scoped incidentals | **Open** — not in the required set; behaviour unchanged |
| m-1, m-3, m-5, m-17, m-20 | **Resolved** as consequences of I-41, the Turn-3 fix, I-42, the pressure cap and the §8.6 ordering rule |
| m-2, m-4, m-6, m-9, m-10, m-11, m-12 | m-11 and m-12 **resolved** (distortion subsets; cue bot runs the solver). The rest are **open** — outside the required set |
| §7 overengineering removals | **Not applied** — deliberately out of scope for a "required changes only" revision |
| R-A Phase 0.5 | **Applied** — inserted as a blocking gate |
| R-B…R-F recommendations | **Open** — R-B is referenced as the Phase 0.5 fallback path; R-C…R-F are not applied |

**The one finding a document revision cannot close** is D-4's root cause. The architecture now *rejects* the broken case and *specifies* how the replacement is produced, but the replacement itself, and the generator yield that decides whether producing it is routine or hard, are measurements — not text. That is what the Phase 0.5 gate exists to obtain.

---

## 1. Executive verdict

**B — IMPLEMENT AFTER REQUIRED ARCHITECTURAL CHANGES.**

Spine survives attack. Event sourcing, four epistemic layers, closed proposition schema, least-privilege positive-only envelope, claim-tagged generation with by-reference commit, solution-first compilation, deterministic strategy — all sound, all well-argued, several genuinely excellent. v0.2 is a real improvement over v0.1, not cosmetic.

But v0.2 is not implementation-ready. Three reasons:

1. **The previous review found one instance of each bug class and did not sweep for siblings.** It found "combination refutations" break pairwise breaker authoring — then left `contradiction(p,q)` pairwise in three other load-bearing places. It found extraction-as-containment unsafe — then left a generator-controlled `color` label that bypasses the new containment. It found colluding-lovers testimony must be L0 — then defined admissibility per *witness* instead of per *claim*, leaving a laundering path. Pattern: fix at the reported symptom, not the shared root. Ironic given the document's own bug-fix philosophy.

2. **The golden case v0.2 — the only worked fixture, the Phase 1–4 oracle — does not establish the uniqueness it claims.** Second consecutive hand-verification failure on a 5-actor, 7-location case (§2, D-4). This is the strongest single argument in the review: if a careful author cannot hand-verify uniqueness twice, the case-generation loop (Phase 6, "reseed ≤ 20 times") is a much larger unknown than the roadmap prices in.

3. **Internal contradictions that are not typos.** I-16 is false as specified (composure back-channels verbal pressure into slips). `DetectiveModel` requires telepathy the doc forbids two lines earlier. Traces are claimed atomic with commit while living in a second database file. Runtime mutates memory `strength` and `Belief.revised` inside the sealed, hash-verified, immutable `Case`. Each is contract-level, cheap now, expensive after Phase 4.

Not **C**: no paradigm change needed. Every defect below is a contract fix, a missing invariant, or a fixture rebuild. Not **A**: six defects (D-1, D-2, D-3, D-5, D-6, D-9) become expensive once Phases 2–4 encode them.

---

## 2. Critical flaws

### D-1 · Admissibility is per-witness; must be per-claim. Belief-laundering exploit.

`refutation_weight` calls `admissibility(item, confrontee)`. §19.5 defines admissibility over *material*: "L2 = testimony of a witness whose relevant presence is fixed by L3 evidence, or corroborated by a non-colluding source." That is a property of the **witness**, not of the **claim's grounding**.

§6.5 says anything the detective states to C becomes `KnowledgeEntry(p, InvestigationTold, reliability = trust)`, and a belief forms if `trust × strength > confidence`.

Exploit:

```
1. Detective asserts to Elena: "David crossed the hall at 21:50."   (bluff, no item)
2. trust(E->det) = 0.8 -> belief forms, confidence 0.56 > her prior 0.5 -> revised.
3. Later, ask Elena about the hall. Her speakable set includes that belief. She says it.
4. Statement S_elena is committed. Elena is L2 (presence fixed by E9).
5. Present(David, S_elena) -> admissibility(S_elena, David) = 0.7 -> weight -> LayerPeel.
```

I-25 is satisfied to the letter — the player *assertion* never entered a breaker set. A *statement* did. `Statement.claims[].source ∈ {plan, frame, incidental, slip}` carries no link back to the grounding `KnowledgeEntryId` / `BeliefId`, so nothing can detect the laundering at `Present` time.

**Required:** `Claim` gains `grounding: list[KnowledgeEntryId | BeliefId]`. `admissibility` becomes `admissibility(claim, confrontee)` = min over the claim's grounding chain; any chain containing `InvestigationTold` → L0. Same function used by solver and peel (the doc already insists on that; make it per-claim).

### D-2 · Contradiction detection is pairwise everywhere. n-ary infeasibility is undetectable.

`contradiction(p, q, context)` is explicitly "one function over pairs". Used by: validator check (f), notebook tensions, solver constraints, V-3 intra-layer consistency, refutation weight.

The previous review identified this exact defect for breaker sets and fixed it *only there* (subset enumeration ≤ 4). Everywhere else, pairwise stands.

Constructed failure — **transitive alibi cycle**, all pairs valid, joint state impossible:

```
A claims At(A, Gazebo,  [22:00,22:20)) ∧ At(B, Gazebo,  ...)   "I was with B"
B claims At(B, Kitchen, [22:05,22:25)) ∧ At(C, Kitchen, ...)   "I was with C"
C claims At(C, Library, [22:10,22:30)) ∧ At(A, Library, ...)   "I was with A"
```

No single actor is in two places by any *pair* of claims taken alone under the §13.2 presence rule — but the conjunction requires A in Gazebo and Library, B in Gazebo and Kitchen, C in Kitchen and Library, all overlapping. Cover synthesis (§18.3 stage 7) builds each character's layers **independently**; V-3 checks per-secret, per-layer. Nothing checks the joint feasibility of the cast's layer-0 claims. Generation can emit this and pass V-0…V-8.

**Required:** claim-set consistency is a feasibility check, not a pairwise scan. At case scale (≤ 8 actors, ≤ 20 locations, ≤ 720 ticks) interval propagation over presence constraints is cheap. Run it (a) in V-3 across all characters' layers jointly, (b) in validator check (f) over the speaker's standing claims plus the presented set.

### D-3 · I-16 is false. Verbal pressure gates slips through `composure`.

I-16: "`LayerPeel`, `Slip` and `CONFESSION` depend only on the presented set's refutation weight; verbal pressure never contributes."

§11.7 slip gate: `refutation_weight ≥ min_weight_fraction × resolve ∧ composure ≤ composure_max ∧ topic ∧ unused`.

§11.2: `composure -= 0.4 × Δverbal + 0.6 × Δrefutation_weight`.

Composure is a function of verbal pressure. The slip gate reads composure. Therefore verbal pressure contributes to slips. Test F-11 (accusation spam ×50 → zero slips) passes only because spam alone fails the *weight* conjunct — it never tests **modest real evidence + spam**, which is the exploit:

> Present one weak item reaching 0.5 × resolve. Accuse 40 times. Composure floors. Slip fires. Guilty knowledge bought with 39 free actions.

This is the precise loophole the previous review declared closed, reopened through a back door it introduced in the same revision.

**Required:** the slip gate reads only `refutation_weight` and static personality. Composure drives delivery, `ANGER`, `REFUSE` — nothing gated by I-16. Add a test: weight at 0.5 × resolve + 50 accusations → zero slips.

### D-4 · Golden case v0.2 does not exclude `Robert` or `Outsider`. The fixture is broken again.

§29.1 asserts: "E10 plus Elena's watch on the kitchen door exclude Robert and `Outsider`; David remains."

From the document's own graph:

- Travel: `Gazebo↔BackSteps 3`, `BackSteps↔Kitchen 1`, `Hall↔any 1`. The only garden→house route is Gazebo → Back Steps → Kitchen → Hall.
- E10 bolts the Study terrace door → the direct garden→Study route is closed. Correct.
- Elena is **on the Back Steps** 22:05–22:15 → co-presence yields `NotAt(x, BackSteps, [22:05,22:15))`.

Counter-model, unexcluded at L2/L3:

```
22:01  Robert leaves Gazebo        (only Margaret can deny — L0, colluding lovers)
22:04  crosses Back Steps          (before Elena arrives 22:05 — no NotAt coverage)
22:05  Kitchen  -> 22:07 Hall -> 22:08 Study
22:08-22:10  argument (two MALE voices — consistent with Robert)
22:10  attack
22:16  back across Back Steps      (Elena returned to Kitchen 22:15 — no coverage)
22:19  Gazebo, then walks home
```

Every L2/L3 item is satisfied. E9 fixes where Elena was, not where Robert was. "Two male voices" excludes Margaret, **not** Robert. `Outsider` uses the identical corridor. Elena's Hall sighting at 22:15–22:16 is one unidentified figure — consistent.

Also: §29.1 prose says Elena "watched the kitchen door 22:05–22:15." **No `BackSteps→Kitchen` perception edge is listed.** The exclusion mechanism the text names does not exist in the authored graph; the mechanism that does exist (co-presence on the Back Steps) has the two uncovered windows above.

Separately, **E10 is a temporal-grounding error of the exact class the doc handled correctly for E1.** Discovery establishes `ObjectState(terrace_door, bolted)` at `t_investigation` (23:00). The murder window is 22:08–22:10. Nothing establishes the bolt was engaged *then*. E1's fingerprint correctly carries `requires: [S_wash]` to pin its interval. E10 carries no equivalent and is load-bearing.

**Required:** (a) re-derive the golden case with the solver, not by hand — it is a Phase 6 deliverable being used as a Phase 1 oracle; (b) a general rule plus invariant: every physical-evidence implication whose proposition spans an interval must carry a `requires` chain establishing that interval; V-1 rejects "state now ⟹ state then" without support.

### D-5 · Runtime epistemic state has no home. Sealed data is mutated.

I-4: case data immutable after validation, SHA-256 verified, opened read-only. `Memory` and `Belief` live inside `Case`.

- §6.3: "At runtime only: memory `strength` and `recall_log` change; beliefs can be revised."
- §8.5: "Each retrieval appends `RecallRecord`."
- §6.2: `Belief.revised: list[(turn_id, old_confidence, reason)]` — a runtime field on a sealed model.

`CharacterState` has no memory or belief fields. `Game` has none. There is **no model that holds runtime memory strength, recall logs, or belief revisions**, and no `BeliefRevised` in `SessionEventKind`. Under I-22 (fold applies recorded outcomes only), every one of these must be an event payload. They are not.

**Required:** a per-game overlay `EpistemicState{memory_strength: dict[MemoryId,int], recall_log: dict[MemoryId,list], belief_confidence: dict[BeliefId,int], belief_revisions: list}` folded from `MemoryRecall`, `MemoryCorrected`, `BeliefRevised`, `KnowledgeAdded`. Add `BeliefRevised` to the event kinds.

### D-6 · `SessionEventKind` does not cover the state model. The fold is incomplete.

Mutated per turn with no event carrying the value: `composure`, `refuse_streak`, `topics_probed`, `contradictions_caught`, `slips_used`, `suspicion_of_detective`, memory strength, belief confidence. Present events: `PressureChange`, `EmotionalDelta`, `TrustChange`, `SuspicionShift`, `LayerPeel`, `MemoryRecall`, `KnowledgeAdded`, `DetectiveModelUpdate`.

Composure is neither pressure nor emotion, is read by the slip gate, and has no event. Under I-22 the fold cannot reconstruct it — so either replay silently recomputes it (violating I-22 and bricking saves on any formula change) or state diverges.

`Snapshot` is still in the enum after snapshots were removed. Dead.

**Required:** invariant — every runtime-mutable field of authoritative state has an event kind that records its post-value; a CI test enumerates `CharacterState` fields and asserts each is written by some `apply()`.

---

## 3. Important flaws

### D-7 · `refutation_weight` double-counts. `noisy_or` over non-independent implications.

```python
for item in presented:
    for impl in implications_unlocked(item):
        w = noisy_or(w, bp(impl.strength * item.reliability * sev * adm))
```

`noisy_or` assumes independence. E1's implications (`Did(D, touch, Glass1)` and derived `At(D, Kitchen, ...)`) come from **one** fingerprint. Two implications at 0.5 → 0.75, not 0.5. Any item with k implications gets `1-(1-w)^k`. Two items derived from the same `support: list[EventId]` compound the same way.

This directly attacks the peel guarantee: authoring an evidence item with three implications silently triples its breaking power — exactly the "mis-authored breaker" class V-3's derivation was meant to eliminate.

**Required:** aggregate `max` within an item; aggregate `max` across items with intersecting `support`; `noisy_or` only across causally disjoint items.

### D-8 · Peel is evaluated only on `Present`. This kills the claimed idempotency and creates the reverse present-twice loophole.

§11.4: peel logic runs "on `Present(item)` to C". Weight is a function of the presented set **and** of `implications_unlocked`, which depends on the player's *global discovered* set via `Implication.requires`.

```
T10  Present(David, E1)         weight 0.57 < resolve 0.60 -> no peel
T20  obtain S_wash from Elena   E1's tight interval unlocked -> weight would be 0.73
T21  Present(David, E1) AGAIN   -> NOW peels
```

Presenting the same item twice produced different outcomes. Test F-8 ("no peel on the second presentation alone") is contradicted by the document's own §13.3 walkthrough logic. Players will learn "re-show everything after every discovery" — the mechanical trick v0.2 was written to remove.

**Required:** evaluate peel at the start of every turn addressed to C, over `presented ∩ currently-unlocked`. Then re-presentation is genuinely inert.

### D-9 · Knowledge-of-absence collapses five distinct epistemic states into one rule — and that rule is the fairness spine.

The only mechanism is co-presence `NotAt(x, L, I)` at `reliability = attention`, emitted for every non-co-present actor over every presence segment with `attention ≥ 0.3`.

It cannot distinguish — and the `Provenance` union has no vocabulary for:

| Situation | "I know John wasn't in the library" | Representable? |
|---|---|---|
| Scanned once, empty | one-moment observation | conflated with continuous |
| Monitored continuously | whole-interval attention | conflated with scan |
| Inferred (he was with me) | `Inferred(rule)` | rule not in the closed set |
| Expectation violated (habit) | habit inference | no habit rule in §6.4 |
| Hearsay | `Told` | yes |
| **Non-observation** ("wasn't watching") | absence of an entry | **not representable** |

Three defects follow:

1. **`attention ≥ 0.3` includes asleep/drunk.** A sleeping actor is issued absence knowledge over the whole interval. Absence is strictly harder than presence: presence needs one moment, absence needs continuous coverage of every entrance.
2. **Perceptibility is ignored.** Co-presence emits full-attention reliability regardless of location size, lighting, or door state — while the very same case model has `PerceptionEdge` with `quality 0.5, partial`.
3. **Non-observation is unrepresentable**, so characters never say "I wasn't paying attention." Every character is a perfect absence witness. Because L2 absence testimony is what eliminates suspects, **the entire elimination requirement rests on the least defensible derivation in the model.**

**Required (smallest correction):** new provenance `Absence(basis: continuous | scan | inference, coverage_bp, entrances_covered: bool)`. Emit `NotAt` only when attention ≥ AWAKE, coverage spans the full interval, and the location's `entrances` are within perception. Reliability strictly below the corresponding `At`. V-5 emits a **fragility report**: which eliminations depend on absence testimony, and how many on a single source.

### D-10 · Planted evidence and detected bluffs produce weight exactly 0 — a mechanical oracle.

`admissibility(planted) = L0 = 0.0`; `confrontee_knows_false → adm = 0`.

**Planted-evidence detector.** Present an item that obviously contradicts a standing claim. If the character produces no weight change at all (no peel, no composure move, an authored `EvidenceResponse` that never escalates), the item is planted. The player cannot know it is planted — that is the puzzle — and the mechanics tell them for free. The design conflates *inadmissible for proof* with *unpersuasive to a person*. Different questions.

**Bluff oracle = free lie detector.** The previous review called this "a genuine, derivable differentiator that v0.1 wasted." It is an exploit. `bluff_detected` requires the confrontee to hold a contradicting belief at confidence ≥ 0.7. Only the murderer holds such beliefs about the murder's physical details.

```
"We found your prints on the bookend."   murderer (wiped it): confident correction
                                          innocent: uncertain_premise -> VAGUE
"We found your hair in the study."        same discriminator
... binary-search the cast with zero evidence.
```

No evidence spent, no pressure that matters, unlimited repetitions, converges in ~10 questions.

**Required:** (a) planted evidence weighs by *apparent* admissibility for characters who do not know it is planted; inadmissibility is a solver-only property. (b) The bluff response must not be discriminable in kind — innocents with *any* contradicting belief (including co-presence-derived) respond identically, and `bluff_detected` alters delivery only within the noise of ordinary denial. (c) New V-7 bot: **bluff bot**, bluffs only, must NOT converge on the murderer. The fairness contract gains: "the case must not be solvable without evidence."

### D-11 · `color` segments bypass every deterministic check. Containment regression.

`Segment{text, claim_ids, kind: "assert"|"color"|"question"|"nonverbal"}`. Slot checks (§14.2c) run on `assert` segments. `color` segments "may carry no proposition (verified)" — verified by the **LLM verifier**, i.e. by the same blind "does this text contain an assertion?" judgment the design abandoned as the weakest link.

**The kind label is chosen by the generator.** A generator that mislabels an assertion as `color` skips the entire deterministic layer and lands on the fuzzy one.

**Required:** deterministic entity/time checks run on **every** segment regardless of kind. `color` is defined restrictively and checked deterministically: no entity names beyond the speaker, no time expressions, no location names. Add a MutantLLM class: assertion mislabeled as `color`.

### D-12 · `DetectiveModel` requires telepathy the document forbids.

§11.3: "Updated only from interactions with that character (no telepathy)." Same block: `estimated_suspicion_of_me` "rises with threat; **falls when detective probes others**."

A character cannot know the detective probed others (v1 explicitly cuts inter-suspect diffusion). Straight contradiction, and it feeds `plausibility(c)` in the scorer, so it changes behavior.

**Required:** delete the falls-when-probing-others term, or add an explicit in-fiction channel (an authored `Tell` schedule) and derive it from that.

### D-13 · Trace atomicity is impossible as specified.

§27.1: `TurnTrace` "written in the same transaction as the commit." §26.1: traces live in **`traces.db`, a separate file**.

One SQLite transaction does not span two database files without `ATTACH`, and attaching defeats the isolation the separate file exists to provide.

The consequence goes beyond tidiness: several invariants are *tested over traces* (I-1's property test, I-22's replay comparison, the offline audit). If traces are best-effort, the test population is incomplete and those invariants are sampled, not proven.

**Required:** state plainly that traces are best-effort, written after commit; make I-1 provable **structurally** instead — the envelope builder is a pure function of `(plan, view)`, so assert `envelope.propositions ⊆ speakable(plan)` on the typed object, not on prose. (As written, I-1's test requires extracting propositions from free-form prompt text — the operation this architecture correctly refuses to trust.)

### D-14 · Validator check (f) is O(all prior claims) and enforces what the prompt cannot see.

Check (f): no contradiction with the speaker's non-retracted prior claims. After 1500 turns that is thousands of claims, scanned per draft per repair attempt. This directly contradicts ADR-10's O(1)-per-turn framing.

Worse than cost: the **generator's context contains the top 5 statements by `(topic match, entity overlap, recency)`**, while the **validator enforces against all of them**. Late in a session the generator cannot see the constraint it is being judged on → rising repair rate → rising fallback rate → the fallback template is itself a detectable side channel (§33.1 item 7). The 2% fallback SLO will not survive a long session.

**Required:** the retrieved-statements slot is filled by **contradiction candidates** — prior claims sharing `(predicate, entity, time_bucket)` with the plan's claims — not by topic ranking. Same budget, correct content. Index prior claims by that key; check (f) queries the index rather than scanning.

### D-15 · Retrieval thresholds can silently degrade proof-core testimony below usability.

§8.2 promotes proof-core memories to `strength ≥ 0.6`. §8.4: `strong` requires `score ≥ 0.55`, `score = strength × cue_overlap × …`. At strength 0.6, strong requires `cue_overlap ≥ 0.92` (Jaccard over entities/location/time-bucket/topic). Anything less → `weak` → `VAGUE` act → "hedged content, **widened interval**, no identity claims."

Widening the interval is exactly what destroys a load-bearing testimony. Elena's "kitchen 21:05–22:05, nobody came in" is the derived breaker set of David's L1. Delivered as `VAGUE` ("most of the evening"), severity drops, weight falls under `resolve`, the layer never peels. **Fairness contract item 5 ("no load-bearing fact depends on volunteering; it must be obtainable by a question the parser can express") is not enforced against the retrieval mechanism.**

**Required:** V-4 gains a check — for every proof-core testimony, there exists a parser-expressible `Query` whose cue set yields `score ≥ 0.55` for the required memory. Mechanically checkable: enumerate Query templates × cue sets against the memory's `CueSet`. Promote strength until it passes.

### D-16 · `Outsider` exclusion is by assertion, not by construction.

The solver enumerates `Outsider` as one candidate and checks authored exclusion constraints. But "an outsider" is a class with unbounded properties. The solver cannot verify that the authored exclusion is adequate — D-4 shows how easily it is not. Uniqueness inherits the assertion.

**Required (and cheaper than the current design):** model `Outsider` as a **reachability query**, not a candidate. "Does any spatiotemporal path exist into and out of the murder location within the window that is not excluded by L2/L3 material?" The engine already has Dijkstra over conditional edges plus presence. This is checkable rather than authored, and it generalizes to every future skeleton.

### D-17 · Corroboration counting is undefined; self-corroboration is possible.

L2 requires "corroborated by a non-colluding source." Nothing defines what is counted. Turn 3 commits **two** claims (`Saw(E, figure, …)` and `Saw(E, David, …)`) from **one** perception. If corroboration counts claims or beliefs, one glance corroborates itself.

Collusion is defined as a static `Rel` list plus "no shared secret". It misses blackmail, dependency chains, and transitive structure (A corroborates B, B corroborates C, A and C are lovers).

**Required:** corroboration counted over distinct `KnowledgeEntry` with **disjoint provenance events**. Collusion = connectivity in a graph over `{shared Secret, listed Rel, Secret.beneficiaries}`; corroborating sources must sit in different components. `Secret.beneficiaries` already exists — use it.

### D-18 · Layer monotonicity vs. retracted testimony. Unspecified, and both answers are wrong.

A statement peels David L0→L1. The player later corrects the witness's distortion (`MemoryCorrected`), invalidating that statement. Does the retracted statement still contribute weight?

- **Yes** → the player peels with testimony subsequently known false, permanently.
- **No** → the computed layer index decreases, violating I-20's monotonicity.

**Required:** retracted or corrected statements contribute zero weight; the layer index is `max` over history, documented as a deliberate asymmetry (a liar does not un-concede). Add an invariant and a test.

### D-19 · Layer-scoped incidentals are discarded but their claims are not retracted.

§14.4 rule 5: incidentals pinned in a layer's `frame` are discarded on `LayerPeel`. §29.2 T5 does exactly this to the port and the Trollope, calling it "realistic."

It is not. The player *heard* "a glass of Harold's port"; the text is verbatim in the ledger. If the claim is not retracted, the next answer contradicting it fails check (f) → repair → fallback. If it is retracted, the player sees a contradiction on a harmless detail — a **free tell that a peel occurred at a specific earlier turn**.

**Required:** incidentals are never layer-scoped. They are soft attributes about the speaker's self; they belong to the character, not to the lie. Delete `layer_scope` from `IncidentalPinned`.

---

## 4. Minor flaws

| # | Flaw | Fix |
|---|---|---|
| m-1 | Hash chain covers `payload` only. `kind` and `action_id` unprotected — flip `ClaimMade`→`ClaimRetracted` and the chain still verifies. | Hash the full canonical row minus the hash fields. |
| m-2 | `Evidence.reliability`, `Implication.strength`, `Contradiction.severity`, `resolve` are floats and they decide peels. I-17 covers hashed state only. | Extend I-17 to all decision inputs. Basis points throughout. |
| m-3 | Turn 3 commits `Saw(E, David, …, identified=False, conf low)`. No confidence field exists in the schema. The golden trace asserts a field the normative schema lacks. | Add `Claim.confidence ∈ {certain, probable, unsure}` (ordered ints). Fixes hedging, `VAGUE`, "probably", "might have" in one field without touching proposition comparison. Contradiction severity scales by min(confidence). |
| m-4 | `predicate_hint: str \| None`, "canonical form" undefined. The query-normalization hash drives `REPEAT_PRIOR`. "enter" vs "go into" → different hashes → the same question answered fresh 20 times. | Closed enum. |
| m-5 | Effort is `medium`, "high for CONCESSION/CONFESSION turns" → latency reveals concession turns before the text renders. Contradicts §1.6's own "timing is not a channel." | Constant effort, or pad to a fixed floor. |
| m-6 | Unknown-to-addressee name → in-world "who?"; known-to-addressee → real answer. Probe names across characters to enumerate each character's acquaintance set. The cast-enumeration fix created a relationship oracle. | The response must be identical for unknown-to-world and known-but-unacquainted. |
| m-7 | `cover_layer` is stored but is a pure monotone function of the presented set. Redundant state invites drift. | Derive it, or add an invariant asserting equality. |
| m-8 | `Said` appears in the proposition schema; §13.2's contradiction rules never mention it. An implementer will either add a rule (wrong — hearsay is not a claim about the world) or omit it (hearsay inert). | Specify: `Said` contradicts only another `Said` with the same `(speaker, listener, t)` and incompatible content. |
| m-9 | No conditional claims. "If Elena was in the kitchen she'd have seen me" — a natural liar move — collapses to an unconditioned claim; contradiction detection against it is wrong. | `Claim.condition: Proposition \| None`; `contradiction()` returns `None` when either side's condition is unsatisfied or unknown. |
| m-10 | `Hypothesis.propositions` is a conjunction. The player cannot hold "either David or Robert" — the actual mid-game epistemic state of a detective. | `Hypothesis.alternatives: list[list[Proposition]]` (disjunction of conjunctions). Board only; never a claim, never a fact. |
| m-11 | Distortion robustness runs "with every distorted value substituted" — the all-distorted extreme. The dangerous case is *subsets* (the player corrects some). | Enumerate subsets; k ≤ 2/witness × 5 witnesses = 2^10, trivially enumerable. |
| m-12 | The solver's `unlocked requires` assumes the player holds everything discoverable. The cue bot checks reachability separately. Nothing checks that the **cue-reachable set alone** establishes uniqueness. | The cue bot must run the solver on its own acquired set; that becomes the fairness gate. |
| m-13 | No payload-evolution rule. Without upcasters, adding a `CharacterState` field breaks the fold on old saves. | State it: "the fold treats absent payload fields as their documented default"; test with a synthetic field addition. |
| m-14 | `Case` (large) is parsed per request if there is one connection per request. | Process-level immutable parsed-Case cache. Safe — it is immutable. |
| m-15 | The verifier receives the addressee's known-entity alias index. Prompt extraction against the verifier reveals who a character knows. | Pass rendered claims only; resolve aliases engine-side before the call. |
| m-16 | `Snapshot` remains in `SessionEventKind` after snapshot removal. | Delete. |
| m-17 | Uncapped `verbal_pressure` (+1500/accusation, 5% decay). 50 accusations → 75 000 bp, decaying for hundreds of turns. | Hard cap. |
| m-18 | Log-truncation recovery silently reverts a character's layer (the layer is a function of the presented set). The player experiences an in-fiction impossibility. | Surface it: "case rolled back to turn N." |
| m-19 | No global per-turn deadline. Worst case: 3 generations + 3 verifications + retries. | One turn deadline; fail closed on expiry. |
| m-20 | `MemoryCorrected` and `LayerPeel` both fire on one `Present`; order unspecified. Worse: `confrontee_knows_false` reads beliefs the same item may revise — a fixed point with no defined evaluation order. | Fix the order explicitly: weight computed against **pre-turn** beliefs; corrections and revisions applied at commit. |

---

## 5. Missing invariants

Each prevents a failure demonstrated above. None is speculative.

| ID | Invariant | Closes |
|---|---|---|
| **I-27** | Admissibility is computed per claim from its grounding chain. Any chain containing `InvestigationTold` is L0. | D-1 |
| **I-28** | The set of standing claims of all characters, plus the presented set, is jointly feasible under presence/travel propagation — not merely pairwise non-contradictory. | D-2 |
| **I-29** | Slip, peel and confession predicates read no quantity influenced by `verbal_pressure`, transitively (composure included). | D-3 |
| **I-30** | Every physical-evidence implication whose proposition spans an interval carries a `requires` chain establishing that interval. No "state at `t_investigation` ⟹ state at `t`" without support. | D-4 |
| **I-31** | Every runtime-mutable field of authoritative state has a `SessionEventKind` that records its post-value; no `apply()` recomputes any of them. | D-5, D-6 |
| **I-32** | Weight aggregation uses `max` within an item and across items with intersecting `support`; `noisy_or` only across causally disjoint items. | D-7 |
| **I-33** | `refutation_weight` is evaluated every turn addressed to C over `presented ∩ unlocked`. Re-presenting an already-presented item never changes any outcome. | D-8 |
| **I-34** | `NotAt` knowledge requires attention ≥ AWAKE, continuous coverage of the full interval, and perception coverage of the location's entrances. Its reliability is strictly below the corresponding `At`. | D-9 |
| **I-35** | The character-visible response to an inadmissible item (planted, or known-false) is indistinguishable from the response to an admissible one of equal apparent strength. Inadmissibility is a solver-only property. | D-10 |
| **I-36** | Deterministic entity/time/slot checks run on every segment regardless of `kind`. | D-11 |
| **I-37** | Corroboration is counted over `KnowledgeEntry` with disjoint provenance events; corroborating sources lie in different components of the collusion graph over `{shared Secret, Rel, beneficiaries}`. | D-17 |
| **I-38** | Retracted or corrected statements contribute zero refutation weight; `cover_layer` is monotone non-decreasing over the session. | D-18 |
| **I-39** | For every proof-core testimony there exists a parser-expressible `Query` whose cue set yields strong retrieval (`score ≥ 0.55`) for the required memory. | D-15 |
| **I-40** | The case is not solvable without presenting evidence: a bluff-only bot must not converge on the murderer. | D-10 |
| **I-41** | Every `SessionEvent` row is hashed over its full canonical content including `kind` and `action_id`. | m-1 |
| **I-42** | Player-observable turn characteristics (latency, effort tier, envelope section count, response length band) are independent of the plan's act class. | m-5, D-11 |

---

## 6. Missing tests

Beyond the 36 in the previous review's §F.

**Epistemic**

1. Detective asserts p to Elena → Elena states p → `Present(David, S_elena)` yields a weight contribution of **zero** (D-1).
2. A sleeping or drunk actor produces **no** `NotAt` entries (D-9).
3. A location with an unmonitored entrance caps `NotAt` reliability below `At` (D-9).
4. One perception yielding two beliefs cannot corroborate itself at L2 (D-17).
5. Collusion graph: A–B corroborate, B–C corroborate, A–C lovers ⇒ the chain is rejected as non-independent (D-17).
6. A belief revised by a trusted assertion while its memory carries a corrected distortion ⇒ a defined, deterministic retrieved value (D-5, m-20).

**Peel / strategy**

7. Weight at exactly `0.5 × resolve` + 50 accusations ⇒ **zero slips** (D-3).
8. Present E1 (no peel) → discover `S_wash` → present E1 again ⇒ the same outcome as if the peel had fired on discovery; re-presentation is inert (D-8).
9. An evidence item with 3 implications ⇒ weight equals `max`, not `noisy_or` (D-7).
10. Peel via statement S → S retracted by `MemoryCorrected` ⇒ the layer does **not** regress; S's weight is zero for any subsequent evaluation (D-18).
11. The planted-evidence response is indistinguishable from an authentic item of equal apparent strength — assert equality of act class, latency band, and length band (D-10).
12. Bluff bot: 500 bluffs, zero evidence, across all suspects ⇒ murderer identification no better than chance (D-10, I-40).

**Generation / validation**

13. Mutant: an assertion mislabeled `kind="color"` ⇒ caught by the deterministic slot check, not by the verifier (D-11).
14. Mutant: a `color` segment naming a location ⇒ caught deterministically (D-11).
15. V-3 with three characters whose layer-0 claims form a transitive alibi cycle ⇒ **rejected** (D-2). Ship as a negative fixture.
16. Evidence whose implication interval exceeds its `requires` support ⇒ V-1 rejects (D-4, I-30).

**Solver / fairness**

17. Golden case v0.2 as written ⇒ V-5 **rejects** at L2 (Robert and Outsider unexcluded). Ship as the second negative fixture. v0.3 passes.
18. `Outsider` as a reachability query: any unexcluded corridor into and out of the murder location in the window ⇒ reject (D-16).
19. Distortion robustness over all **subsets**, not just all-distorted (m-11).
20. The cue-following bot runs the solver on its own acquired set and achieves uniqueness (m-12).
21. Proof-core testimony is retrievable at `strong` from a parser-expressible query (D-15, I-39).

**Persistence / long session**

22. Flip `kind` on a row, keep the payload ⇒ chain verification fails (m-1).
23. Fold-completeness: enumerate `CharacterState` fields; assert each is written by some `apply()` (D-6, I-31).
24. An engine upgrade changing the composure formula ⇒ the old save replays to an identical hash **and** the next live turn is flagged as a compatibility-epoch change.
25. Turn 1500: contradiction candidates for check (f) are present in the generator's context slot; fallback rate ≤ 2% (D-14).
26. Turn latency and envelope section count are act-class-independent across 200 turns spanning `TRUTH` / `LIE` / `CONCESSION` / `CONFESSION` (I-42).

---

## 7. Overengineering to remove

Only items where the simpler architecture demonstrably preserves correctness.

| Item | Why it goes | Preserves |
|---|---|---|
| `Deflection.cost` + `Personality.loyalty` dict + `SuspicionShift` + `CharacterState.suspicion` + `estimated_suspicion_of_me` | A social-simulation subsystem serving one speech act. `DEFLECT` is adequately served as an `EvidenceResponse` variant with a fixed authored target. | All invariants; D-12 disappears with it. |
| `misleading_truths` + `MISLEADING_TRUE` act | A second authored pool overlapping `frame`. Same effect from `PARTIAL_TRUTH` + `OMISSION` over frame content. | Nothing depends on it. |
| 5 of 8 personality scalars (`volatility`, `deference`, `self_preservation`, `loyalty`, `talkativeness`) | Eight uncalibrated scalars feeding seven utility terms, tuned before any playtest data exists. Keep `composure_base`, `guile`, `voice`. | The scorer keeps its shape; weights collapse to constants. Re-add with data. |
| Suppressed-belief surfacing (§6.4 rule 5 + `HOLD_MEMORY` path) | Serves one narrative beat. `MemoryCorrected` is load-bearing (the distortion-corrector fairness rule); suppressed beliefs are not. | Fairness contract item 4 unaffected. |
| `Query.kind` values `smalltalk`, `challenge`, `recall_detail` | `challenge` duplicates `Present` (now UI-only); the others route to existing kinds. 17 kinds is a parser-accuracy tax. | Parser precision improves. |
| Second skeleton in v1 | One skeleton plus the golden case proves the generator. The second is content risk stacked on the riskiest phase. | The Phase 6 exit criterion narrows but does not weaken. |
| Debug **web app** with 8 inspectors | I-10 requires a separate *process*, not a separate web application. `eidolon trace/inspect/replay` plus one static trace HTML page covers the developer need. | I-10 fully preserved. |
| `Snapshot` event kind | Dead after v0.2. | — |

**Do NOT remove**, despite looking heavy: the closed proposition schema, the four layers, breaker-set derivation, `MutantLLM`, cross-platform replay, the separate debug process, solution-first compilation, layer-0 solvability robustness. Each earns its cost.

---

## 8. Required architectural changes

Gate on all nine.

- **AC-1** Admissibility per claim, from grounding provenance. `Claim.grounding` field. One function shared by solver and peel. *(D-1, I-27)*
- **AC-2** Claim-set consistency becomes a feasibility check over presence/travel constraints, applied in V-3 across all characters jointly and in validator check (f). Retire pairwise-only reasoning wherever a *set* is being judged. *(D-2, I-28)*
- **AC-3** Sever composure from the slip/peel/confession gates. Cap `verbal_pressure`. *(D-3, I-29)*
- **AC-4** Runtime epistemic overlay (`memory_strength`, `recall_log`, `belief_confidence`, `belief_revisions`) as folded state, with `BeliefRevised` added to the event kinds; fold-completeness invariant plus its CI test. *(D-5, D-6, I-31)*
- **AC-5** Weight aggregation: `max` within an item and across items with intersecting `support`; `noisy_or` only across disjoint support. Peel evaluated every turn over `presented ∩ unlocked`. *(D-7, D-8, I-32, I-33)*
- **AC-6** Absence provenance: new `Absence(basis, coverage, entrances_covered)`, awake threshold, entrance coverage, reliability strictly below `At`; V-5 fragility report on absence-dependent eliminations. *(D-9, I-34)*
- **AC-7** Inadmissibility becomes solver-only. Planted and known-false items weigh by apparent strength for the character; the bluff response is non-discriminable; a bluff bot is added to V-7; the fairness contract gains "not solvable without evidence." *(D-10, I-35, I-40)*
- **AC-8** Deterministic checks on every segment kind; `color` defined restrictively and checked without an LLM. *(D-11, I-36)*
- **AC-9** `Outsider` reframed from a candidate to a **reachability query** over the travel graph and L2/L3-excluded windows. Temporal-grounding `requires` mandatory on interval-spanning physical implications. Golden case re-derived **by the solver**, with the current v0.2 retained as a second negative fixture. *(D-4, D-16, I-30)*

---

## 9. Revised architecture recommendations

**R-A · Move the highest-risk component first. Insert Phase 0.5.**
The generator + solver yield is the largest unknown in the document, and it is scheduled at Phase 6 — after five phases of investment. Phase 6's exit criterion ("2 skeletons × 50 seeds, ≥ 80% in-band within 20 attempts") is an assumption stated as a target, with no prototype behind it. The evidence that it is optimistic is in the document itself: **a careful human author failed to produce a uniquely-solvable 5-actor case twice in a row.** A random planner with a validation oracle in the loop, retrying 20 times, may have a yield of 5% or 80% and nobody knows which.

Spike, roughly two weeks, before Phase 1: minimal `Proposition` + `FactIndex` + travel graph + admissibility + V-5 solver + a toy 4-actor / 5-location planner. Measure yield. If it is low, the fix is in skeleton design (constrain the search so uniqueness is *constructed*, not *discovered*) — a fix that reshapes Phases 1–6 and is unaffordable to learn at Phase 6.

**R-B · Construct uniqueness; do not search for it.**
"Solution-first" currently means "plan the timeline, then check uniqueness, then reseed." Make it mean: the skeleton declares the *elimination structure* (which item excludes which suspect at which level), the planner's job is to realize that structure, and V-5 confirms rather than discovers. Reseeding becomes rare instead of load-bearing. This is the difference between a compiler and a fuzzer.

**R-C · Surface admissibility to the player.**
The lattice decides solvability and is invisible. The player has no way to know Elena's account is corroborated by Robert's independent sighting — the exact reasoning the fairness guarantee assumes they perform. Add a notebook relation "supported by / uncorroborated" computed **only from player-held material**. Costs one projection. Without it, "solvable at L2" does not imply "a reasonable player believes the L2 material", and the human-fairness score cannot rise.

**R-D · Add a compatibility epoch.**
I-22 guarantees *state* reproduces. It does not guarantee the *game* reproduces: continuing an old save under a new build runs new `cue_overlap`, `contradiction`, `noisy_or` and scorer code. Record `engine_epoch: int` in the first event of each turn; bump it on any change to a non-constant decision function; warn (do not refuse) on continuation across epochs. Two lines, and it closes an honest overclaim.

**R-E · Make the cue bot non-circular.**
Cues are authored by generation; the bot follows cues. It verifies that the cue graph is connected — not that a human would traverse it. Constrain the cue vocabulary so a cue is valid only when the source item's `reveals_text` **deterministically names** the target entity or location, and add the one human-fairness metric the bot cannot game: the maximum number of premises required *simultaneously* at any single inference step in the proof core. That number, not depth, is what exceeds human working memory. It is cheap to compute from the hitting-set structure already produced.

**R-F · State the containment boundary honestly in §21.**
Containment is guaranteed at the **proposition** level (by-reference commit — genuinely strong) and best-effort at the **pragmatic** level (insinuation, implicature). The document knows this and buries it in §33.3. It belongs in the boundary statement, because it is the difference between "the LLM cannot leak" and "the LLM cannot leak *propositions*."

---

## 10. Red team scenarios

Format — **F:** failure · **W:** why · **D:** current defense · **S:** sufficient? · **C:** required change.

**RT-1 · Detective asserts a fact to Elena, later presents her statement to David.**
F: a player assertion gains L2 weight and peels a layer. W: admissibility keyed to witness, not claim grounding. D: I-25 (assertions never enter breaker sets). S: **No** — a statement did, not an assertion. C: AC-1.

**RT-2 · Three suspects' layer-0 alibis form a transitive cycle.**
F: a globally impossible cover set ships. W: `contradiction()` is pairwise; cover synthesis is per-character. D: V-3 per-secret. S: **No.** C: AC-2.

**RT-3 · Present one weak item, then accuse 40 times.**
F: a slip fires; guilty knowledge for free. W: composure carries verbal pressure into the slip gate. D: I-16, test F-11. S: **No** — F-11 tests spam alone. C: AC-3.

**RT-4 · Bluff systematically about physical details across all suspects.**
F: the murderer is identified with zero evidence. W: only the guilty hold conf ≥ 0.7 contrary beliefs about wiped or planted details. D: none — the design treats this as a feature. S: **No.** C: AC-7 plus a bluff bot.

**RT-5 · Present an item that obviously contradicts a standing claim; observe zero reaction.**
F: planted evidence identified with certainty. W: `adm = 0` produces no state change at all. D: none. S: **No.** C: AC-7.

**RT-6 · Present E1 (no peel), obtain `S_wash`, present E1 again.**
F: re-presentation peels; "show everything again after every discovery" becomes optimal play. W: peel evaluated only on `Present`; the `requires` unlock is global. D: the stateless-weight claim; test F-8. S: **No** — F-8 tests the wrong sequence. C: AC-5.

**RT-7 · Author an evidence item with four implications.**
F: it breaks layers that no single item should break. W: `noisy_or` over non-independent implications. D: V-3 derives breaker sets — using the same flawed function. S: **No** — the derivation inherits the bug. C: AC-5.

**RT-8 · Robert leaves the gazebo at 22:01, returns at 22:16.**
F: the golden case is not uniquely solvable. W: Elena's Back Steps coverage `[22:05,22:15)` misses both traversals; "two male voices" excludes only Margaret. D: §29.1's asserted exclusion. S: **No** — the mechanism does not exist as authored. C: AC-9.

**RT-9 · Same corridor, unnamed actor.**
F: `Outsider` unexcluded. W: exclusion authored, not derived. D: "locked doors + a watched entrance." S: **No.** C: AC-9 (reachability query).

**RT-10 · Ask when the terrace bolt was engaged.**
F: E10 proves state at 23:00 and is used as if it proved state at 22:08. W: no general temporal-grounding rule; E1's `requires` pattern was not generalized. D: none. S: **No.** C: I-30.

**RT-11 · Sleeping character asked "did anyone come in?"**
F: confident absence testimony from an unconscious witness, possibly load-bearing at L2. W: co-presence emits `NotAt` at attention ≥ 0.3 = asleep. D: none. S: **No.** C: AC-6.

**RT-12 · Ask a witness about a room with two doors, one out of view.**
F: absence asserted over an unmonitored entrance. W: co-presence ignores `PerceptionEdge` and entrance topology. D: none. S: **No.** C: AC-6.

**RT-13 · Ask "were you watching the door the whole time?"**
F: the character cannot say "I wasn't paying attention" — no representation for non-observation. W: absence of an entry is unspeakable; auto-derived `NotAt` is always present. D: `DONT_KNOW` (fires only when no entry exists). S: **No.** C: AC-6.

**RT-14 · Mislabel an assertion as `kind="color"`.**
F: the assertion skips all deterministic checks and is judged only by the fuzzy verifier. W: the generator chooses the label. D: the verifier "verifies color carries no proposition." S: **No** — that is the abandoned blind-extraction task. C: AC-8.

**RT-15 · Turn 1500, ask about a topic first covered at turn 40.**
F: rising repair rate, fallback breaches the SLO, and the fallback template leaks "something forbidden was near." W: the generator sees the top 5 by topic/recency; the validator enforces against all prior claims. D: ADR-10 plus check (f). S: **No** — mutually incompatible as specified. C: the D-14 fix (contradiction-candidate slot).

**RT-16 · Ask a proof-core question with 85% cue overlap.**
F: load-bearing testimony degrades to `VAGUE`, the interval widens, the breaker set never reaches `resolve`; the case becomes unsolvable at runtime despite passing V-5. W: the fairness contract is never checked against retrieval thresholds. D: memory promotion to `strength ≥ 0.6`. S: **No** — 0.6 requires cue overlap ≥ 0.92. C: I-39.

**RT-17 · Correct a witness's distortion after her statement already peeled a layer.**
F: either the peel rests on refuted testimony, or the layer regresses. W: unspecified. D: none. S: **No.** C: I-38.

**RT-18 · Ask David about the port after his L0 peels.**
F: he contradicts an incidental the player heard verbatim; or the retraction reveals the peel point. W: incidentals are layer-scoped. D: called "realistic." S: **No.** C: D-19 (incidentals are never layer-scoped).

**RT-19 · Ask the same question 20 ways ("did you enter", "did you go into", "were you ever in").**
F: no repeat detection; 20 fresh generations, 20 incidental opportunities, rising fallback exposure. W: `predicate_hint` is a free string with an undefined canonical form. D: the query-normalization hash. S: **No.** C: m-4.

**RT-20 · Time a concession turn.**
F: the player knows a concession is coming before reading it. W: `effort: high` on `CONCESSION` / `CONFESSION`. D: §1.6 claims timing is not a channel. S: **No** — contradicted by §12.3. C: I-42.

**RT-21 · Probe names across characters ("do you know Robert Hale?").**
F: enumerate each character's acquaintance set — hidden relationship data. W: "who?" only for unknown-to-addressee. D: the grounding-scope fix, which created this. S: **No.** C: m-6.

**RT-22 · Ask "what do you think I know?"**
F: `Clarify` on a natural interrogation move; or leakage of `DetectiveModel`. W: no `Query.kind` covers it; `OPINION` carries only `Attitude`. D: `COUNTER_QUESTION` fallback. S: **Partly** — safe but poor. C: an authored `COUNTER_QUESTION` family; measure the `Clarify` rate on this shape.

**RT-23 · Ask about the murderer's own composure while spamming accusations.**
F: `REFUSE` / terse oscillation forever; composure permanently floored. W: uncapped `verbal_pressure`, slow decay. D: `refuse_streak` ≤ 2. S: **Partly** — playable, degenerate, and it holds the slip gate's composure conjunct permanently open. C: AC-3 plus m-17.

**RT-24 · Two browser tabs; a commit in tab A peels a layer while tab B computes.**
F: tab B's rejected turn is re-run against a peeled layer with different semantics. W: `expected_seq` rejects the write, not the intent. D: I-14. S: **Partly.** C: the UI must surface "state changed — review before resubmitting."

**RT-25 · Kill the process between the commit transaction and the trace write.**
F: a committed turn with no trace; invariant property tests sample an incomplete population. W: traces live in a second DB file; one transaction cannot span both. D: §27.1's atomicity claim. S: **No** — physically impossible. C: D-13 (traces best-effort; I-1 proved structurally).

**RT-26 · Flip a row's `kind` from `ClaimMade` to `ClaimRetracted`, keep the payload.**
F: tampering undetected; a lie silently un-said. W: the hash covers the payload only. D: I-13. S: **No.** C: I-41.

**RT-27 · Ship an engine build with a fixed `cue_overlap` bug; the player continues a save.**
F: characters behave differently mid-conversation; the player reads it as inconsistency. W: I-22 protects state, not decision functions. D: constants in `CaseConstants`. S: **No** — code is not a constant. C: R-D (compatibility epoch).

**RT-28 · Ask "if Elena had been in the kitchen, would she have seen you?"**
F: the conditional collapses to an unconditioned claim; contradiction detection against it is wrong. W: no `Claim.condition`. D: `HYPOTHETICAL` modality, which drops the antecedent. S: **No.** C: m-9.

**RT-29 · The player believes "David or Robert" and records it.**
F: the hypothesis board cannot hold the actual mid-game epistemic state. W: `propositions` is a conjunction. D: "multiple board entries." S: **No** — separate entries are separate hypotheses, not a disjunction. C: m-10.

**RT-30 · Correct one witness distortion, leave the other.**
F: uniqueness holds for all-distorted and for none, and fails for a mixed subset. W: the robustness run tests only the extreme. D: §19.5 robustness. S: **No.** C: m-11.

**RT-31 · The cue bot solves; the human path requires holding six premises at once.**
F: formally solvable, cued, and practically impossible. W: the cue graph verifies connectivity; nothing measures inference load. D: depth band plus cue bot. S: **No** — the cue bot is circular (cues authored by the same process). C: R-E.

**RT-32 · Elena's single glance yields two claims (`figure`, `David`); count them as corroboration.**
F: one witness corroborates herself into L2, and the elimination requirement rests on it. W: corroboration counting undefined. D: L2's "non-colluding source." S: **No** — "source" is undefined. C: I-37.

**RT-33 · Add a field to `CharacterState` in v1.1; load a v1.0 save.**
F: the fold cannot reconstruct the field; no upcaster framework exists. W: I-22 requires payload-carried values; there is no payload-evolution rule. D: `schema_version` refusal. S: **Partly** — refusal is safe but bricks saves on any change. C: m-13.

**RT-34 · Deploy hosted; a player runs a 2000-turn session.**
F: roughly $120 of model spend on one session; no hard budget. W: only a per-session rate limit is mentioned. D: the ingress token budget. S: **Partly.** C: a hard per-session cost ceiling with a graceful in-world end.

**RT-35 · `MemoryCorrected` and `LayerPeel` triggered by the same presented item.**
F: order-dependent outcome; `confrontee_knows_false` reads beliefs that the same item revises — an undefined fixed point. W: stage 6 lists both as proposals with no ordering. D: none. S: **No.** C: m-20 (weight against pre-turn beliefs; revisions at commit).

---

## 11. Scores

| Dimension | Score | Justification (all < 7 explained) |
|---|---|---|
| Correctness | **5** | Five internal contradictions that are not typos: I-16 false via composure (D-3); `DetectiveModel` telepathy contradicting its own no-telepathy line (D-12); trace atomicity across two DB files (D-13); sealed `Case` mutated at runtime (D-5); the golden trace commits a claim field the normative schema lacks (m-3). The event catalogue does not cover the state model (D-6). |
| Determinism | **7** | Genuinely strong: hash chain, recorded-outcome fold, `action_id`, `expected_seq`, integer state, no-runtime-RNG lint, cross-platform replay test. Deductions: the hash omits `kind` / `action_id`; floats decide peels; behavioral (as opposed to state) reproducibility across builds is unaddressed. |
| Epistemic consistency | **5** | The four-layer separation is correct and well-argued. But absence — the load-bearing addition of v0.2 — is one crude rule conflating five states (D-9); belief laundering defeats the admissibility guarantee (D-1); the runtime composition of a revised belief with a corrected distortion is undefined (D-5); corroboration counting is undefined (D-17); n-ary claim consistency is absent (D-2). |
| LLM containment | **8** | The best part of the design. By-reference commit, deterministic slot checks, verifier, least-privilege positive-only envelope, no tools, structured irreversible actions, seal-time guards. Deductions: the generator-chosen `color` label bypasses the deterministic layer (D-11); insinuation is admitted unsolved; the verifier receives the addressee entity index. |
| Murderer intelligence | **6** | Consistency over hours is genuinely guaranteed, and adaptivity is correctly bounded by authored layers. Deductions: the bluff oracle hands the player a lie detector (D-10); the zero-weight oracle identifies planted evidence (D-10); composure back-channels spam into slips (D-3); layer regression on retracted testimony is undefined (D-18). |
| Case solvability | **4** | The solver's form is sound (complete enumeration over a finite candidate space; the layer-0 robustness run is excellent). But `Outsider` exclusion is authored, not derived (D-16); the sole worked fixture fails uniqueness for the second consecutive revision (D-4); distortion robustness tests only the extreme (m-11); nothing checks that the cue-reachable set alone suffices (m-12). Uniqueness has now been hand-asserted and hand-refuted twice — the guarantee is still procedural, not mechanical. |
| Human fairness | **4** | Formal / human / fair is correctly distinguished, and only the formal side is enforced. The cue bot is circular (R-E). The admissibility lattice — the thing that makes a case solvable — is invisible to the player (R-C). There is no inference-load metric. Retrieval thresholds can silently degrade proof-core testimony below usability (D-15). The document's own honest note ("a proof cued and reachable but longer than a human holds in mind") remains unaddressed. |
| Long-session stability | **5** | O(1) context is real and well-designed. But check (f) is O(all prior claims) and enforces constraints the prompt cannot see, so repair and fallback rates rise with session length precisely where the 2% SLO is asserted (D-14); `verbal_pressure` is uncapped (m-17); several state fields are unbounded. The 2000-turn test as specified would not surface D-14 because `TemplateLLM` never repairs. |
| Security | **8** | Least privilege is the strongest single decision in the document and it survives every attack constructed here. No tools, a separate debug process with an import-graph test, ingress guard, canary, structured irreversible actions, quoted-statement resolution by ID. Deductions: the effort-tier timing channel (m-5); the name-probing relationship oracle (m-6); the zero-weight oracle (D-10). All three are mechanical side channels, not prompt-injection failures. |
| Maintainability | **6** | Modular monolith, dependency lint, pure functions, ADRs — the right shape. Deductions: a very large surface for a v1 (26 invariants, 30+ models, 25 speech acts, 8 validator stages, 5 bots, 2 web apps); several models have no owner (runtime memory state); roughly 8 uncalibrated personality scalars feeding 7 utility terms is tuning surface nobody can resolve before playtests. |
| Testability | **8** | Excellent. `MutantLLM` with a per-class 100% catch rate, `TemplateLLM` enabling the full pipeline without a model, Hypothesis properties, an invariant→test map with CI enforcement, cross-platform replay, five bot classes. Deductions: I-16 is untestable because it is false; I-1's stated test implies prompt-text extraction (it should be structural over the typed envelope); I-8 depends on an "unknowable set" membership relation that is never defined — what entails what, across interval containment, is the whole question. |
| v1 practicality | **4** | Phases 0–9 at this scope is a multi-person-year effort, and the largest unknown — generator and solver yield — is validated at Phase 6, after five phases of investment, on an assumption with no prototype behind it. The document's own evidence argues against that ordering: two hand-authored uniqueness failures. Two skeletons, 8 debug views, a bespoke planner, a bespoke solver and a full web UI compound the risk. |

**Mean ≈ 5.8.** The distribution is the story: containment, security and testability are 8s; solvability, fairness and practicality are 4s. This is an architecture whose *defensive* engineering is far ahead of its *generative* engineering — very good at not letting the LLM lie to the engine, and not yet good at proving the case it generates can be solved by a person.

---

## 12. Implementation gate checklist

Every box before Phase 1 code.

**Correctness contracts**

- [ ] AC-1 `Claim.grounding`; admissibility per claim; a single shared function.
- [ ] AC-2 Feasibility-based claim-set consistency in V-3 (cross-character) and check (f).
- [ ] AC-3 Composure severed from slip / peel / confession; `verbal_pressure` capped.
- [ ] AC-4 Runtime epistemic overlay plus `BeliefRevised`; fold-completeness invariant and its CI test.
- [ ] AC-5 Weight aggregation corrected; peel evaluated every turn over `presented ∩ unlocked`.
- [ ] AC-6 `Absence` provenance with awake threshold, coverage and entrance rules.
- [ ] AC-7 Inadmissibility becomes solver-only; bluff response non-discriminable; bluff bot in V-7.
- [ ] AC-8 Deterministic checks on all segment kinds; `color` restrictively defined.
- [ ] AC-9 `Outsider` as reachability; temporal-grounding `requires` mandatory; golden case re-derived **by the solver**.

**Contradictions resolved in the document**

- [ ] I-16 restated to match the implementation (D-3).
- [ ] `DetectiveModel` telepathy term removed (D-12).
- [ ] Trace atomicity claim corrected; I-1 restated as a structural property (D-13).
- [ ] `Case` immutability reconciled with runtime epistemic state (D-5).
- [ ] Golden trace Turn 3 fixed; `Claim.confidence` added (m-3).
- [ ] `Snapshot` removed from the event enum.

**Invariants and tests**

- [ ] I-27…I-42 written into §2.2 with named tests.
- [ ] Tests 1–26 (§6 above) exist as failing or skipped stubs, each assigned to an owning phase.
- [ ] Negative fixtures sealed: `vance_v01` (collusion), **`vance_v02` (Robert / Outsider unexcluded)**, `transitive_alibi_cycle`.

**Feasibility gate — blocking**

- [ ] **Phase 0.5 spike complete.** Minimal `Proposition` + `FactIndex` + travel graph + admissibility + V-5 + toy planner on a 4-actor / 5-location skeleton. **Report the measured yield: cases per 20 seeds passing uniqueness at L2 with a fully-cued proof core.** If yield < 30%, adopt R-B (construct uniqueness from the skeleton's declared elimination structure) before Phase 1.
- [ ] Golden case v0.3 produced by that solver, not by hand, with its uniqueness argument printed as a machine-generated exclusion chain per candidate.

**Scope cuts applied**

- [ ] §7 removals executed (deflection subsystem, `misleading_truths`, 5 personality scalars, suppressed-belief surfacing, 3 `Query.kind` values, second skeleton, debug web app).

**Honesty edits**

- [ ] §21 boundary restated: containment guaranteed at the proposition level, best-effort at the pragmatic level.
- [ ] R-D compatibility epoch recorded per turn.
- [ ] R-C player-facing corroboration relation specified.
- [ ] R-E cue validity made deterministic; simultaneous-premise metric added to V-6.

---

## Verdict

**B — IMPLEMENT AFTER REQUIRED ARCHITECTURAL CHANGES.**

The spine is real and it survived. A serious team can build this — after AC-1 through AC-9, after the six documented contradictions are resolved, and **only after the Phase 0.5 spike returns a yield number.** That last gate is the one that should not be waived. Everything else on this list is a week of specification work. The generator's yield is the item that decides whether EIDOLON is an eighteen-month project or a five-year one, and the architecture currently answers it with a target instead of a measurement.

*End of review.*
