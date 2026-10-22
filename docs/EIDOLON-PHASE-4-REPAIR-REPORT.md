# EIDOLON — Phase 4 Blocker Repair Report

Status: **the six BLOCKING findings of the Phase 4 hostile review are repaired**, plus two
defects the post-repair audit found in the repair itself. A second pass then repaired the
**four Phase-5-readiness findings** (I-3, I-4, I-5, N-2) and five defects its own fresh audit
found (A-3…A-7) — see "Phase-5-readiness repair" at the end. The other IMPORTANT findings
remain open. Phase 5 has not begun.

Supersedes `EIDOLON-PHASE-4-REPORT.md` where the two disagree — in particular that report's
I-3/I-33, I-15, I-32 and I-37 rows, and its test counts.

---

## Results

```
BLOCKING remaining:   0
IMPORTANT remaining: 17   (see "Phase-5-readiness repair" for the current list)

python -m pytest -q                                                # 660 passed
python -m pytest tests/world -q                                    # 98   Phase 1   PASS
python -m pytest tests/minds -q                                    # 77   Phase 2   PASS
python -m pytest tests/evidence -q                                 # 169  Phase 3   PASS
python -m pytest tests/test_important.py tests/test_repairs.py -q  # 136  repairs   PASS
python -m pytest tests/decision -q                                 # 180  Phase 4   PASS
python -m pytest spike/test_spike.py -q                            # 21   Phase 0.5 PASS
python -m tests.decision.mutation_check                            # 57/57 killed, 2 equivalent   PASS
```

`660 = 98 + 77 + 169 + 136 + 180`. No Phase 0.5–3 test file was touched; their counts are
unchanged. `tests/decision` grew 67 → 132 in the blocker pass (`test_blocking_repairs.py` 47,
`test_invariant_mutants.py` 18) and 132 → 180 in the readiness pass (`test_phase5_readiness.py`
48). The counts in the sections below describe the blocker pass as it stood.

**Deterministic replay: PASS.** A 2 000-turn adversarial session (three addressees, every
query kind, meta + present, 50 accusations, mid-session unlock) re-folds to byte-identical
statement content, layer peels and meta log; every row applied twice in place is a no-op; and
the decision state and character state are identical across three processes under different
`PYTHONHASHSEED`s. The raw JSON of one field is *not* — see new IMPORTANT finding N-1.

**Long-session stress: PASS.** `test_long_conversation` at the literal 2 000-turn /
50-accusation scale: 153.2 s, zero peels, flat envelope, replay equal.

---

## The repairs

| # | Root cause | Fix | Files |
|---|---|---|---|
| B-1 | `validate_draft` turned *every* violation into a fallback render of `plan.claims`, and `run_ask_turn` committed `result.claim_ids` without reading `ok`. The fallback cures renderer failures, never plan failures. | Only an allow-list of draft-level codes may fall back; any other code — the plan-level checks and anything added later — returns `rejected` with no text and no claim ids, and the turn returns the caller's state untouched (I-15). The blanket CONCESSION/CORRECTION consistency waiver now applies only to the statements that turn actually retracts (§14.2(f): "contradicted claims ⊆ plan.retracts"). The Solution check covers everything the renderer sees (frame, reveals), not only `plan.claims`. | `validator.py`, `turn.py`, `cli.py` |
| B-2 | The peel ran only for `relevant_secret()` — a heuristic over the question's wording — or not at all. | `evaluate_peel` runs for every secret the addressee owns, every turn, over the presented set alone. The wording heuristic now picks only the plan's content. | `turn.py`, `strategy.py` |
| B-3 | The meta/coercion restriction removed CONCESSION from the candidate set while `turn.py` recorded the `LayerPeel` regardless. A second path: STONEWALL outranked CONCESSION when a peel stopped short of an ungated confession (`peeled` and `stonewalled` both true). | Acts that voice recorded state (CONFESSION, CONCESSION) survive the meta restriction; CONCESSION outranks STONEWALL (§11.4: `if i > peeled_from: plan.act = CONCESSION`). A backstop in `run_ask_turn` rejects any turn whose plan does not voice every layer it would record, whatever produced the plan. | `strategy.py`, `turn.py` |
| B-4 | `_corroborated` computed `own_entry` only for single-ground claims, so ≥ 2 grounds skipped both disjointness guards; the check read direct event slots only. | `provenance_origin()` walks the whole grounding transitively (`Told`, `Inferred`, `Belief.grounds`); disjointness is checked against every ground; a corroborator must be an established perception (fail closed on `Background`/dangling). | `admissibility.py` |
| B-5 | Causal grouping keyed on origin events only: `requires`-derived items and items with no `created_by` sat in their own groups and compounded. | Grouping tokens include the item's `requires` ancestry (the same closure Phase 3's `corroborates()` uses), the ancestors' own origins, and a required statement's perceptual sources. Unknown-origin items count by `max` only and never compound — monotone: they can never lower the weight already presented. | `weight.py` |
| B-6 | Tests asserted weak or tautological properties (T-9 compared a call with itself; T-10 exercised the unlock gate, not retraction; no negative slip case; I-29 checked by substring one level deep; validator tests never asserted non-commitment). | 65 new tests; every original survivor and every repair is now killed by a named test. `tests/decision/mutation_check.py` re-runs the whole set. | `tests/decision/` |

### Found by the post-repair audit (fixed as part of B-1 and B-5)

- **A-1 — livelock (B-1 × peel retraction).** `superseded_propositions` retracted only
  `layer.claims`. V-3(ii) requires an `EvidenceResponse` for every breaker item, so a character
  routinely answers a not-yet-decisive item in-layer ("I was never in the kitchen"). When the
  owed concession later contradicted that answer, the now-strict B-1 gate rejected it — and since
  the peel re-fires every turn (I-33), **every later turn to that character was rejected**.
  EvidenceResponse claims authored at the abandoned layers are now superseded with them (§10.2:
  "what to say when an item is presented *at a layer*").
- **A-2 — transitive dependency (B-5).** The first B-5 fix linked items only by ids in the
  `requires` graph. An item resting on a statement, and a trace created by the event that
  statement witnessed, still compounded (6400 → 8704 bp, across resolve 8000).

### The one changed pre-existing test

`test_llm_and_validator.py::test_contradiction_with_standing_claim_caught_unless_concession`
asserted that a CONCESSION contradicting a standing claim passes validation with **no**
retraction. That is the blanket waiver B-1 removes; §14.2(f) conditions the waiver on the
contradicted claims being retracted. The test now passes `retracting={"s0"}` for its positive
case (its original intent) and adds the negative case. The same mutation is independently
killed by `test_b1_a_concession_may_contradict_only_what_it_retracts`, so the kill does not
rest on the modified expectation.

---

## Mutation verification

`python -m tests.decision.mutation_check [selection]`: each mutation is an exact-string
replacement that must match exactly once (so a mutation cannot silently no-op), applied to a
fresh temporary copy of the repository.

| Mutation | Result |
|---|---|
| R-B1 full revert, and each of its parts: fallback instead of reject · turn ignores `rejected` · blanket waiver | killed (8 / 2 / 2 tests) |
| R-B2 peel only the wording-selected secret | killed (16) |
| R-B3 full revert, and each part: meta drops voiced acts · STONEWALL > CONCESSION · no backstop | killed (6 / 4 / 1 / 1) |
| R-B4a/b/c single-ground-only disjointness · non-transitive walk · non-perceptual corroborator | killed (1 each) |
| R-B5a/b `requires` ignored · unknown origin treated as independent | killed (4 / 3) |
| A-1 EvidenceResponse claims not superseded · A-2a/b required statement's / item's origins ignored | killed (1 each) |
| M1 every item its own group (I-32) | killed (5) |
| M2a both monotone floors removed · M2b `layer_index` last-write (I-20/I-38) | killed |
| M3 retracted material weighs (I-38) | killed |
| M4b `InvestigationTold` walks to L1 in `minds` (I-27) | killed |
| M5 planted loses apparent weight (I-35) · M6 no collusion (I-37) | killed |
| M7 slip on topic alone (I-16) · M8 confession gate defaults open (I-21) | killed (2 / 1) |
| M9 no consistency check (I-28) · M10/M10b envelope padded with own / all ledger (I-1) | killed |
| M11 slip gate reads `composure` (I-29) | killed |
| **M2** final `max(i, reached)` removed · **M4** `_chain_poisoned` disabled | **survive — equivalent** |

**Correction to the hostile review.** It reported six of ten mutations surviving and read all
six as test gaps. Two were **equivalent mutants**: M2 — the loop starts at `reached` and only
increments, and the step-back is already floored, so the monotone floor is implemented twice
and deleting either copy changes nothing; M4 — `minds.admissibility` already walks any
`InvestigationTold` id to L0 and `claim_admissibility` takes the `min` over grounds, so the
poison never depended on `_chain_poisoned`. No test can kill either. Their killable
counterparts (M2a, M2b, M4b) are killed. The genuine gaps were four: M1, M3, M7, M8.

---

## Fresh audit of the repaired areas

Scope: every repaired function, its immediate callers and callees, the mutation cases, and
the interactions between repairs. Two defects found and fixed (A-1, A-2 above). Nothing left
at blocking severity.

**New IMPORTANT (not fixed):**

- **N-1 — non-canonical event serialization.** `DetectiveModelUpdate.new_model.known_evidence`
  is a `frozenset`; its JSON order follows the hash seed (5 of 6 631 events in the stress run).
  State is unaffected, but Phase 7's hash chain (I-13/I-41) must canonicalize set-valued fields
  or cross-process verification will fail. Predates the repair.
- **N-2 — gate-open confession voiced as CONCESSION.** `_confession` checks the *pre-turn*
  layer, so once a real confession checker is wired (Phase 5/6), a peel landing on the confession
  layer produces CONCESSION; if that layer carries a `Solution`, B-1 rejects it every turn.
  Unreachable today (the gate is hard-wired closed, and M8's tests pin that). Predates the repair.
- **N-3 — residual fail-closed livelock on mis-authored covers.** A concession that contradicts
  a *non-cover* statement the character made (TRUTH, SLIP reveal, DEFLECT) cannot be committed
  and is rejected on every turn. That is §14.2(f) working as specified; the missing piece is a
  V-3 rule checking each layer against the owner's own speakable non-cover material.
- **N-4 — `corroborates()` (Phase 3) treats required statements as leaves.** The A-2 gap
  remains at the Phase 3 / Phase 6 solver layer; Phase 4's weight no longer depends on it.

The review's 16 IMPORTANT findings stand. I-11 (over-broad retraction) is unchanged in kind:
A-1 widened *what* belongs to an abandoned layer; retraction still has no "conflicts with
layers[i]" filter.

**Non-blocking, noted:** a rejected `TurnResult` still carries `plan_act`, which a UI must not
display (it names the attempted act); `KnowledgeStore.knowers()` keeps one best entry per
character, so an independent entry shadowed by a stronger non-perceptual one is missed
(conservative); `noisy_or` multiplies groups in set-iteration order, so bp rounding is
float-order-sensitive at exact .5 boundaries (replay is unaffected — I-22 records outcomes).

---

## Phase-5-readiness repair

Scope: the four findings named as Phase 5 prerequisites — I-3, I-4, I-5 from the review and
N-2 from the blocker pass's audit. Every attack below was re-run against a temporary copy with
that fix reverted (`R-P5-*` in `mutation_check.py`) and against the repaired tree.

### I-3 — entity allow-list (§14.2(b))

- **Reproduction.** `"I was with Mr Fothergill in the orangery at half past."` (`kind="color"`)
  produced **no violation**. A draft ending `"Colonel Mustard can vouch for me."` was spoken
  verbatim and its claims committed.
- **Root cause.** `mentioned_entities` searched the text for names the case *contains*, and
  `lexical_guard` reported `mentioned − allowed`: a deny-list over known names. A name the case
  does not contain never enters `mentioned`, so it could not be flagged. `world/alias.py` was not
  consulted.
- **Fix.** `unresolved_names` masks every surface form in the case name + `Alias` table
  (word-bounded, longest first); any capitalised token left over must be a closed-class
  function word, or it is `UNKNOWN_ENTITY` — in every segment kind. The known-but-unpermitted
  rule is kept, so a name must be both resolvable and permitted. `UNKNOWN_ENTITY` is a
  renderer failure: the draft falls back to the plan (§14.3) and the invented name is neither
  spoken nor committed. `render_claim` now renders verbs lowercase ("I never use …") so the
  engine's own output does not trip the guard.
- **Limit (by design).** Lowercase common-noun inventions ("the orangery") are not
  deterministically detectable; §14.2(d)'s verifier ("no unreferenced assertions") owns them.

### I-4 — §14.2(e) leak check and the envelope boundary (§21.2)

- **Reproduction.** Elena asserting `At(David, Study, [71,72))` — true, and hers only if she
  had some provenance for it — validated `ok` and committed. David naming Margaret's protected
  fact committed even with the reveal "authorized". The envelope handed the renderer every
  `Claim` field: `sincerity="deceptive"`, `source`, `grounding`. An envelope builder padding the
  retrieval slot with another character's words reached the renderer.
- **Root cause.** `leak_check` re-checked claim-id containment and blocked `Solution`; the two
  rules §14.2(e) exists for were absent. Nothing inspected the envelope's string slots, which
  `props()` excludes by design.
- **Fix.**
  - `leak_violations` implements all three rules over what each visible claim *asserts* (a
    `negated` claim asserts the negation; a `Said` claim's content is checked in its own right):
    no `Solution` outside CONFESSION; no **unknowable** proposition — a true fact
    (`FactIndex`) the speaker has no provenance for (knowledge entry incl. the runtime overlay,
    own belief, or being its subject: §6.2 `Participated`/`Witnessed`, computed lazily) unless
    listed in `authorized_reveals`; no **other character's protected fact** without access —
    authorization does not lift this one. Plan-level: rejects the turn.
  - `audit_envelope` runs in `run_ask_turn` **before** the renderer is called and traces every
    field to its one permitted source: claims and reveals exactly the plan + frame, projected;
    §14.2(e) over claims, reveals and `persona.public_facts`; `digest_text` is the render of
    this speaker's digest, whose presented items the player holds; retrieval/exchange slots are
    the speaker's own committed text; style strings name only what the claims carry;
    `query_text` is the player's own words. A schema pin over the actual object types fails the
    envelope if any field, or any subclass, has no rule.
  - `EnvelopeClaim` is the renderer's view of a claim: id, proposition, modality, confidence.
    `sincerity`, `source` and `grounding` stay engine-side (§10.3).
  - `validate_draft` now requires `ctx` — the leak check cannot be skipped by omission.

### I-5 — confession gate identity binding (I-21)

- **Reproduction.** A verdict `survivors=('David',)` opened **Elena's** confession layer:
  `run_ask_turn(Elena, …)` with David's proof → `CONCESSION`, Elena layer 0 → 1.
- **Root cause.** `ConfessionCheck = Callable[[], bool]` could not say whose confession a
  proof licenses; any truthy result opened any gate.
- **Fix.** `ConfessionCheck(actor, secret, presented, ctx) -> UniquenessResult`, and
  `confession_permitted` opens only when the secret is the confessor's own, the verdict is a
  `UniquenessResult`, `unique` is true, and `survivors == (confessor,)`. Anything else —
  including a bare `True`, a malformed "unique" with two survivors, or no checker — is closed.
  `run_ask_turn(confession_check=…)` is the hook Phase 6's solver wires; default closed.

### N-2 — gate-open landing on the confession layer

- **Reproduction.** Gate open, E_knife presented: `CONCESSION rejected=True
  violations=('SOLUTION_LEAK',) peels=[]` on turn 0, 1 and 2 — the peel never records, and the
  confession is unreachable.
- **Root cause.** §11.4 voices every peel as `CONCESSION` with `layers[i].claims`; §14.2(e)
  allows `Solution` only under `CONFESSION`. A confession layer carrying its `Solution` claim
  therefore produced a plan the validator must reject, every turn.
- **Semantics kept.** Gate open is not a confession. The turn the peel *lands* on the confession
  layer is a `CONCESSION` (§11.4; §10.3: CONCESSION's precondition is "LayerPeel just fired",
  CONFESSION's is "terminal layer reached"). `CONFESSION` comes from a character already
  standing on that layer, with the gate open on that turn.
- **Fix.** `claims_voiced_on_peel`: a concession landing on a confession layer voices its
  claims minus `Solution`; the `CONFESSION` act carries the `Solution`. `_concession` and the
  unvoiced-peel backstop use the same function. After the fix: turn 0 `CONCESSION` (peel 0→1),
  turn 1 `CONFESSION` (Solution committed); if the proof is lost, `STONEWALL` and the layer holds.

### Fresh audit of the readiness repair

Scope: the four repaired areas, their interfaces with validate/commit, the envelope,
confession/LayerPeel transitions, and the six blocker areas. Five defects found **in this
repair** and fixed, each with a regression test and a killed mutant:

| # | Defect | Fix |
|---|---|---|
| A-3 | `will`/`may` in the closed class: an invented "Will" or "May" passed | removed; rule recorded beside the list |
| A-4 | `[A-Z]` only: "Émile", "ÖLAF" invisible | Unicode word tokens, `isupper()` on the first letter |
| A-5 | substring masking: "Harold Vanceworth" masked as "harold vance" + "worth" | word-bounded masking |
| A-6 | `Said(speaker=self, …)` was first-person, laundering its content | reported content checked in its own right |
| A-7 | a `negated` claim was tested as asserted: "Robert was NOT in the house" (true, Robert's) passed | truth tested against what the claim asserts |

One design correction: the first style rule ("delivery names no entity but the speaker") was
stricter than the spec, whose §10.3 delivery example names a person. It now follows the
nonverbal rule (I-24): the speaker and what the envelope's claims already carry.

**Six blocker areas:** every `R-B*`/`A1`/`A2` reversion is still killed; 2 000-turn stress: 0
rejected, replay equal, 4.2 → 15.2 ms/turn; gated-confession stress (600 turns, David and
Elena, identity-bound gate): 0 rejected, Elena never confesses, `Solution` only under
`CONFESSION`, replay equal, zero guard violations on template output. Decision and character
state identical across `PYTHONHASHSEED` 1/2/3.

**Pre-existing tests changed, and why (no assertion changed):** `validate_draft` call sites in
`test_llm_and_validator.py` and `test_blocking_repairs.py` pass `ctx` (now required); the two
gate lambdas in `test_invariant_mutants.py` use the identity-bound signature; the A-1 livelock
test marks E1 discovered, since the state it seeded (E1 shown to David, never discovered) cannot
arise in play and the audit rightly rejects a digest naming an undiscovered item.

**New IMPORTANT:**

- **N-5 — CONFESSION at the terminal layer depends on wording.** Standing on an open-gate
  confession layer, the character confesses only when `relevant_secret` picks that secret; other
  questions get `REFUSE`/`DONT_KNOW`/`CLARIFY` (gated stress: 110 `CONFESSION`, 130 `REFUSE`).
  Safe direction — nothing is recorded or withheld from the ledger, and the cover never moves on
  wording — but the endgame beat is question-shaped.

**Notes (non-blocking):** the fallback render is not re-guarded (engine text from case tables;
an authored claim naming an entity id absent from the case would print the raw id); the Vance
fixtures' `Alias` table is empty, so real prose saying "David" falls back until Phase 6 authors
aliases; `recent_exchange` accepts only the speaker's own committed text — Phase 5 needs a
delimited slot (like `query_text`) for the player's lines; `Rel` is not treated as first-person,
so an authored true relationship claim without a knowledge entry is rejected (over-strict);
N-3 now also covers a `Solution` authored outside a confession layer (rejected every turn; V-3
should forbid it).

**Open IMPORTANT (17):** review I-1, I-2, I-6…I-16 (13) and N-1, N-3, N-4, N-5. Of the review's
§08 list, stage 0 ingress (I-16), envelope parity (I-12) and the non-equality verifier contract
are Phase 5's own deliverables — the stages Phase 5 builds — not prerequisites for starting it.

**Verdict: Phase 5 ready — YES.** Nothing at blocking severity survives in the repaired areas or
their interfaces; every guard added is held by a named test and a killed mutant.
