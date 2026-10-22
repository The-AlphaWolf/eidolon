# EIDOLON — Phase 5 repair report

Scope: the three **BLOCKING** and ten **IMPORTANT** findings of the Phase 5 independent hostile
review, in two passes. No Phase 6 work was started and no architecture was redesigned.
Authoritative for Phase 5; supersedes `docs/EIDOLON-PHASE-5-REPORT.md` where they disagree.

Hostile review (findings F-1…F-17, 36 attacks):
https://claude.ai/artifact/WzaAsvZLDobMEdpiGqo7Jt

**Pass 1 — blocking**

| Finding | One line | Status |
|---|---|---|
| **F-1** | the committed claim SEQUENCE came from model segment ordering | repaired |
| **F-2** | repair feedback expanded an entity id into its canonical display name | repaired |
| **F-3** | the view's `names` was matched against the WHOLE case name index | repaired |

**Pass 2 — important.** Not every one was a code defect; each was classified first.

| Finding | Classification | Status |
|---|---|---|
| **F-4** `delivery_tone` encodes the act | **E** permitted residual + **B** false test claim | claim corrected, residual documented |
| **F-5** shared mutable output schema | **A** defect | fixed |
| **F-6** timing distinguishes outcomes | **B** acceptance mismatch + **A** wiring defect | corrected, floor wired, residual documented |
| **F-7** commit gate tests `rejected` | **A** defect | fixed |
| **F-8** latching rate limiter | **A** defect | fixed |
| **F-9** CLI hands over the whole cast | **A** defect | fixed |
| **F-10** unpinned guards | **D** tooling gap | 14 mutations + 50 tests added |
| **F-11** evidence ids in the prompt | **C** doc/impl mismatch | display labels, ids no longer rendered |
| **F-12** no long LLM-path session | **D** coverage gap | 300-turn checked in, 2 000 run |
| **F-13** injection corpus below 100 | **D** gap + **A** marker gaps | 112 prompts, 3 marker gaps closed |

Still open and deliberately untouched: the four NON-BLOCKING findings (F-14…F-17).

---

## Files changed

| File | Change |
|---|---|
| `eidolon/decision/turn.py` | commit iterates `plan.claims`; `result.claim_ids` is used as a SET (F-1) |
| `eidolon/llm/render.py` | `NameBook.of(case, permitted)` — `permitted` required, tables and alias filtered (F-3); new `permitted_ids(req)`; `_names` deleted, the three entity templates carry no detail, `repair_feedback` loses its `book` parameter, `import ast` dropped (F-2) |
| `eidolon/llm/fakes.py` | `reordering(shape)` + `REORDERINGS` — a FAITHFUL generator that varies only segment structure |
| `tests/llm/test_llm_blocking_repairs.py` | **new**, 47 tests (F-1: 13, F-2: 15, F-3: 19) |
| `tests/llm/test_llm_pipeline.py` | one assertion updated: it pinned the leaky feedback string |
| `tests/decision/mutation_check.py` | `P5-21` anchor updated; `P5-46/47/48/48a/48b` added; `P5-22` moved to `EQUIVALENT` |
| `CLAUDE.md` | baseline counts; the new guard file and its rule |

No Phase 0.5–4 test file was modified. No Phase 4 assertion was weakened.

---

# Pass 1 — the BLOCKING findings

## F-1 — the committed claim sequence

**Root cause.** `validate_draft` returns `claim_ids = dict.fromkeys(cid for seg in draft.segments
for cid in seg.claim_ids)` — pure model ordering — and `turn.py` committed
`for cid in result.claim_ids`. The model therefore decided the order of `Statement.claims`, which is
recorded, replayed and read by `digest.standing_claims_ordered`, whose five-claim budget truncates.

**Fix** (`turn.py`, the single authoritative commit site):

```python
voiced = set(result.claim_ids)
committed_claims = tuple(
    c.model_copy(update={"statement": statement_id})
    for c in plan.claims if c.id in voiced
)
```

`result.claim_ids` still answers *which* of the plan's claims were voiced; it no longer answers *in
what order*. The filter is retained rather than dropped: `omission_violations` already forces every
plan claim to be voiced, so the set is the plan's on both the accepted and the fallback path, but a
renderer that somehow voices a subset must not have the rest committed on its behalf.

`validate_draft` was deliberately **not** changed: `claim_ids` is a faithful record of what the
draft tagged, which is what the audit trail wants. The ordering decision belongs at the commit site.

**Regression tests** (13). Four generator shapes — `reversed`, `rotated`, `merged` (one segment, ids
reversed), `split` (reversed, with an untagged `color` segment interleaved) — each asserted to be
*accepted*, not fallen back (the negative control: without it every other assertion would be
vacuous), then committed order, fingerprint equality with the Phase 4 template path, agreement
between all four shapes, digest stability across four turns, event-fold replay, and an adversarial
check that a draft omitting a plan claim is still refused rather than quietly committing a subset.

**Mutation.** `P5-46` restores the model-order commit — **KILLED** (10 failures).

---

## F-2 — repair feedback as an entity oracle

**Root cause.** `repair_feedback` rendered the violation's *detail* through `_names(detail, book)`,
which `ast.literal_eval`'d the list and mapped every item that was a known entity id to
`_display(book, i)`. Entity ids in these fixtures are first names, so a model guessing `Elena` was
told `Elena Ruiz`; `Gazebo` became `the gazebo`; `Glass1` became `a drinking glass`. An invented
name was echoed back verbatim, so the two cases were distinguishable — two guesses per turn, for as
many turns as the session runs.

**Fix.** Structural, not a wider deny-list: the function is given no case, no name book and no
envelope, and the templates interpolate nothing but the segment index.

```python
"UNKNOWN_ENTITY": "Segment {i}: it names something that is not in names; remove that reference and keep everything else.",
"SLOT_MISMATCH":  "Segment {i}: it names something its claims do not; remove that reference and keep everything else.",
"NONVERBAL_LEAK": "Segment {i}: it names something its claims do not; remove that reference and keep everything else.",
```

`repair_feedback(violations, deny=frozenset())` — the `book` parameter is gone, so there is no
argument through which case data could arrive. The model already has `names` in its view, so the
guidance it needs is present without the engine restating anything.

**Consequence, recorded rather than hidden.** The pre-existing engine-vocabulary backstop inside
`repair_feedback` is now **unreachable**: with no interpolation there is nothing for it to catch.
Verified directly — every template formatted with an index trips neither `leaked_tokens` nor
`ENGINE_VOCAB`. The guard is kept as a fail-closed backstop, its unreachability is pinned by
`test_f2_no_template_interpolates_anything_but_the_segment_index`, and its mutation `P5-22` is moved
to `EQUIVALENT` with that reasoning attached. If a placeholder is ever reintroduced, the static test
fails *and* `P5-22` stops being equivalent — the harness then reports it as UNEXPECTED.

**Regression tests** (15), covering hidden actor / hidden location / hidden object (asked of
Margaret, whose view carries neither the glass nor the library) / discovered-but-unpermitted /
invented. The oracle test is the sharp one: the **same turn, same segment, same sentence**, the only
difference being whether the guessed name is a real entity — the two must be byte-identical. Plus a
sweep over every entity id in the case, a check that a *permitted* entity named in the wrong slot is
not quoted either, and a signature assertion that no case-bearing parameter exists.

**Mutation.** `P5-47` restores `_names`, the `{d}` templates, the `book` parameter and both call
sites — **KILLED** (12 failures).

---

## F-3 — `names` against the whole case

**Root cause.** `build_view` did
`ids |= {speaker} | set(mentioned_entities(envelope.query_text, _name_index(case)))`, matching the
player's raw line against every actor, location, object and alias in the case. A player naming an
undiscovered real entity put that entity into the renderer's view; an invented one did not. The view
also advertised names the validator would then refuse the model for using.

**Fix.** The name index is narrowed at its source, so there is no whole-case index left to match
against:

```python
@classmethod
def of(cls, case: Case, permitted: frozenset[str]) -> "NameBook":
    book = lambda table: MappingProxyType({i: Named(e.name) for i, e in table.items() if i in permitted})
    return cls(book(case.actors), book(case.locations), book(case.objects),
               SimpleNamespace(names=MappingProxyType({n: t for n, t in case.alias.names.items() if t in permitted})))
```

`permitted` is **required** — there is no way to build an unrestricted book by accident — and
`permitted_ids(req)` computes the validator's own allow-list,
`allowed_entity_ids | envelope entities | {speaker}` (plus the persona's public facts, which
`build_view` must resolve in order to render them). `build_view`'s body is unchanged: the player-text
scan stays and becomes correct, because the index it searches now contains only permitted entities.
The alias table is filtered too — an alias is an index entry like any other.

This also narrows what every port sees. For David's turn the book is
`actors={David}, locations={Library}, objects={Glass1}`; the rest of the cast is not merely
unlisted, it is absent.

**Regression tests** (19). `names` is exactly the permitted set; a *grounded* entity the player named
is still offered (the fix must not over-narrow); hidden actor / location / object never enter the
view; a 3×3 matrix asserting that hidden-real and invented guesses produce identical prompts once
the player's own line is removed; the port's book contents; alias filtering; `NameBook.of` rejecting
a missing allow-list; `permitted_ids` covering the validator's set; and that a genuinely unauthorable
envelope still fails closed with `ViewError` and no call.

**Mutations.** `P5-48` (whole-case book), `P5-48a` (alias half only), `P5-48b` (view re-admits the
player's raw line) — all three **KILLED** (15 / 1 / 14 failures).

---

# Pass 2 — the IMPORTANT findings

Each was classified before anything was edited: **A** genuine defect · **B** test/acceptance
mismatch · **C** documentation/architecture mismatch · **D** measurement/tooling gap · **E**
deliberate residual the architecture permits. Three of the ten were not code defects, and saying so
is part of the job — inventing a fix for a permitted residual would add complexity and a false
claim at the same time.

---

## F-4 — `delivery_tone` encodes the act injectively

**Classification: E (permitted residual) + B (the test claimed a stronger contract).**

**Root cause.** Every candidate builder in `strategy.py` attaches a constant tone string, and the
map is injective (`LIE → "composed"`, `TRUTH → "relaxed"`, `CONCESSION → "caught, minimizing"`, …),
so a renderer reading `delivery_tone` recovers the act — and for LIE-vs-TRUTH the act is the
sincerity.

**Does the architecture require act-correlated delivery to be removed? No — it requires the
opposite.** Three places say so explicitly:

* §21 line 948 — "The LLM never sees act names for deceptive acts. It sees *content* … and
  *delivery*."
* §33's F-1 row — least privilege means "the generator does not know what is dangerous beyond
  delivery directives, **which are themselves designed tells**".
* ADR-8's consequences (line 2521) — "guilty behaviour must be authored as directives/slips (a
  feature: controllable)".

And I-42, the observable-parity invariant, scopes itself to "latency band, LLM effort tier, envelope
**section count** and response length band" — not to the content of a delivery string.

So the behaviour is correct and the **claim** was wrong. The old
`test_prompt_bytes_do_not_depend_on_sincerity_source_grounding_or_act` held `DeliveryDirective`
fixed while varying the act, which the production path never does, and its name asserted a property
it did not test.

**Action taken.** No behaviour change. The test was renamed to
`test_prompt_bytes_do_not_depend_on_sincerity_source_or_grounding` — which is exactly what it
proves — and its docstring now says why the act is out of its scope. A new test states the residual
positively: the act→tone map is injective, that is intended, and `delivery_tone` is the *only*
act-derived field in the view. `DeliveryDirective`'s own docstring records the architectural basis
and the one thing still owed: §33's mitigation is that directives be **authored per character**;
Phase 5 ships shared constants, which is what makes the map trivially invertible. That is content
work, not a code change.

**Files changed.** `eidolon/decision/strategy.py` (docstring), `tests/llm/test_llm_view.py`.

**Regression tests.** `test_the_act_is_recoverable_from_delivery_tone_and_that_is_the_intended_residual`
— pins the injectivity, the two anchor entries, and that nothing else in the serialized view varies
with the act.

**Mutation result.** None added: there is no guard here to mutate. The invariant that *is* guarded —
sincerity/source/grounding absence — is already covered by `P5-2m` and the Hypothesis property.

**Status.** Resolved as a permitted residual, documented, contract now pinned accurately.

---

## F-5 — a transport could mutate the process-wide output schema

**Classification: A.**

**Root cause.** `CompletionRequest.schema: dict` held a reference to the module-level
`DRAFT_SCHEMA` / `VERIFY_SCHEMA` / `ACTION_SCHEMA`. `@dataclass(frozen=True)` blocks rebinding the
attribute, not mutating the container — the exact failure mode `CLAUDE.md`'s I-4 house rule names
and `world/frozen.py` exists to prevent. One hostile or buggy provider could relax the structured
output contract for every later call in the process.

**Action taken.** Each request takes a deep copy at construction:

```python
def __post_init__(self) -> None:
    object.__setattr__(self, "schema", copy.deepcopy(self.schema))
```

A provider may now scribble on its own request all it likes; the next request is built from the
pristine constant. A deep copy rather than `dict()` because the nesting is what a vandal reaches
for (`properties.segments.items.additionalProperties`). The dicts are small and there are at most
four calls per turn.

**Files changed.** `eidolon/llm/provider.py`.

**Regression tests** (5). A `SchemaVandal` transport run through a real turn; the constant is
unchanged and the vandal's own copies show the mutation. Per-schema identity checks for all three
constants, and a shallow-vs-deep test that mutates a nested node.

**Mutation result.** `P5-58` (remove the copy) and `P5-58a` (make it shallow) — both **KILLED**.

**Status.** Fixed.

---

## F-6 — turn latency distinguishes accepted / fallback / rejected

**Classification: B (the review's framing overstated the contract) + A (the floor was not wired on
the live path through a named constant).**

**Root cause, and what the contract actually says.** I-42's own wording is *"independent of the
plan's **act class**"*, and §12.3's mechanism sentence is "the turn runner holds every response to a
latency floor so that **act class** is not readable from the clock". Outcome parity — accepted vs
fallback vs rejected — was never in the contract, and could not be delivered by a floor anyway: the
floor is a *minimum*, and `test_a_slow_provider_is_not_padded_further` pins that deliberately,
because padding every turn to the worst case makes every turn as slow as the worst.

So F-6 conflated two things. Act-class parity *is* required and is delivered by three mechanisms
together (constant effort per route, envelope parity, the floor). Outcome timing is a **permitted
residual**.

**Action taken.** No equalisation strategy was invented for a contract that does not exist. Instead:

* `LATENCY_FLOOR_S` is now a named constant in `eidolon/llm/render.py` carrying the full contract in
  its docstring — what the floor buys, what it does not, and that its value is a placeholder because
  making it dominate a real model's latency needs a measured p99, which is **UNMEASURED** here.
* `cli.py` wires it on the live path by name instead of a bare literal, so the mechanism I-42 names
  is demonstrably engaged where a model is actually called.
* The residual is asserted rather than left implicit.

**Files changed.** `eidolon/llm/render.py`, `eidolon/cli.py`.

**Regression tests** (3). Act-class parity under an injected clock with per-act model latencies —
three different acts, all landing on the floor; the outcome residual asserted as a real difference
plus a check that it is documented in source; and a test that the live path configures a floor.

**Mutation result.** `P5-16` (no latency floor) already existed and still **KILLED**.

**Status.** Acceptance corrected, mechanism wired and tested, residual documented. T-26 (200 turns
× 4 act classes against a real provider) remains **UNMEASURED**.

---

## F-7 — the commit gate tested `rejected`, not the result's semantics

**Classification: A.**

**Root cause.** `run_ask_turn` committed whenever `not result.rejected`. A
`ValidationResult(ok=False, rejected=False, fallback=False)` — a validation *failure* — was therefore
committed. Unreachable through `run_ask_turn` today because `audit_envelope` runs first, but the
`Renderer`/`RenderRequest` port is public and Phase 6 and Phase 8 will both call it.

**Action taken.** `ValidationResult` now states its own legal shapes:

```python
def integrity(self) -> str | None:   # None == a shape this module can produce
@property
def committable(self) -> bool:       # integrity() is None and not rejected and (ok or fallback)
```

There are exactly three legal shapes — accepted, fallback (ok or not), rejected — and five named
illegal ones. `run_ask_turn` checks `integrity()` first and fails closed on any code, keeps the
existing `rejected` branch with its own violations, and carries `committable` as a backstop.

**Files changed.** `eidolon/decision/validator.py`, `eidolon/decision/turn.py`.

**Regression tests** (14). All ten flag combinations parametrised over `integrity()`/`committable`;
the F-7 hole reproduced end to end (smuggled text, `RESULT_INTEGRITY:NEITHER_OK_NOR_REJECTED`,
caller's state untouched by identity); every illegal shape driven through a real renderer; and two
tests that the gate did not become so strict that accepted and fallback turns stop committing.

**Mutation result.** `P5-57` (revert the gate), `P5-57a` (integrity accepts everything), `P5-57b`
(rejected may carry content), `P5-57c` (`committable` is just `not rejected`) — all four **KILLED**.

**Status.** Fixed.

---

## F-8 — the rate limiter latched at turn 30

**Classification: A.**

**Root cause.** `ingress.screen` takes `turns_in_window` and reads no clock by design (it must stay
deterministic and replayable). `cli.py` passed a **monotonic turn total**, so once 30 turns had ever
happened the limiter refused every turn thereafter, forever. The roadmap's Phase 5 exit measurement
is a 300-turn session, which could not be reached at all.

**Intended semantics.** §22.2's ingress row reads "per-session rate & token budget"; `RATE_LIMIT`'s
own comment says "turns per window". A rate limit throttles a burst and then recovers.

**Action taken.** `RATE_WINDOW_S = 60.0` and a `rate_window(turn_times, now, window_s)` counter in
`ingress.py`, with the module docstring stating why a monotonic total is the wrong argument. The CLI
keeps the timestamps of its turns and passes the sliding count; its clock is injectable so the
window is testable without sleeping. The protection is preserved, not removed.

**Files changed.** `eidolon/llm/ingress.py`, `eidolon/cli.py`.

**Regression tests** (6). `rate_window` unit behaviour; turn 30 accepted and turn 31 refused inside
the window, then recovery once the window passes; a 40-turn burst still throttled to exactly
`RATE_LIMIT`; 40 turns at human pace all answered; and **300 turns at human pace all answered**
through the real `main(["play"])` entry point.

**Mutation result.** `P5-59` (count everything, not the window) and `P5-59a` (the CLI passes a total
again) — both **KILLED**.

**Status.** Fixed. The 300-turn measurement is now possible through the shipped entry point.

---

## F-9 — the CLI handed the parser the whole cast

**Classification: A.**

**Root cause.** `known = frozenset({*case.actors, *case.locations, *case.objects})`. §22.2 requires
grounding to resolve "only against `player-encountered ∪ addressee-known` entities, so name-guessing
cannot enumerate the cast". Handing in the whole case named every actor, location and object —
including the murder weapon — in the very first parse prompt, and re-opened at stage 1 the
enumeration F-3 had just closed at stage 7.

**Action taken.** An `encountered(state, addressee)` helper derives the set from the discovery fold:
the addressee, visited locations, held items, and the object/location of each discovered evidence
item. It grows as the player explores, which is the intended progression — you cannot ask about
evidence you have not found.

**Files changed.** `eidolon/cli.py`.

**Regression tests** (3). A fresh demo session has encountered exactly `{David}`; the first parse
prompt's `known_names` is `['David Kessler']` and contains none of the cast, rooms or the knife;
and presenting the knife discovers it, after which its entities become referable.

**Mutation result.** `P5-60` (revert to the whole case) — **KILLED**.

**Status.** Fixed. Phase 8's UI owns the real encountered ledger and should pass it in.

---

## F-10 — guards that no test pinned

**Classification: D.**

**Root cause.** An independent mutation battery run during the review removed seven guards and the
full 1 027-test suite stayed green. Several were masked: the `oversized_output` attack sends
`"x" * 40000`, which fails as `NOT_JSON` once the size cap is gone, so the test still passed — but a
32 000+ character *valid* JSON document is then parsed.

**Action taken.** 50 tests and 14 mutations, covering exactly the list the review named:

| Guard | Tests | Mutation |
|---|---|---|
| wire-schema segment-count cap | refuses with `SEGMENTS`, inclusive at the limit | `P5-49` |
| per-segment text cap | refuses with `TEXT`, inclusive at the limit | `P5-50` |
| claim_ids-per-segment cap | refuses with `CLAIM_IDS` | `P5-51` |
| raw pre-parse size cap | refuses with `TOO_LARGE`, and *before* parsing | `P5-52` |
| internal tokens — evidence ids | every evidence id is in the set | `P5-53` |
| internal tokens — statement ids | every statement id is in the set | `P5-54` |
| fallback re-validation | `_fallback` calls `_validate` | `P5-55` |
| plan-level vs draft-level classification | — (already covered by the Solution test) | `P5-56` |
| validation → commit boundary | see F-7 | `P5-57`…`P5-57c` |

Mutations already killed by unrelated checks were not added for the count. `P5-56` is included
because the check that kills it is the relevant one, not an unrelated one.

**Harness.** Unchanged in behaviour and still meets every requirement: it refuses to report unless
the unmutated baseline is green, each anchor must match **exactly once** (all 145 verified across both sets), and
killed / survived / equivalent / error are reported separately, with `EQUIVALENT` an explicit set
rather than a silent pass.

**Files changed.** `tests/llm/test_llm_important_repairs.py` (new), `tests/decision/mutation_check.py`.

**Status.** Fixed.

---

## F-11 — raw evidence ids in the prompt

**Classification: C.**

**Root cause.** `render_digest` emitted `f"Presented: {', '.join(digest.evidence_presented)}."` —
raw `EvidenceId`s. §15.3 *does* specify `evidence_presented: list[EvidenceId]` in the structured
digest, and `audit_envelope` needs those ids to check them against `DiscoveryState`; but §15.3 only
says the digest is "rendered to a short paragraph by templates". The id in the rendered text was an
implementation choice, not a requirement.

**Action taken.** `evidence_labels(evidence, case, discovered)` produces display-level names —
`"a kitchen knife"`, `"the fingerprint on a drinking glass"` — and `render_digest(digest, labels)`
renders those. Only **discovered** items get a label, so an id that reached `evidence_presented`
without being discovered renders as `"an item"` rather than describing itself (I-15). The structured
digest is unchanged, so the existing discovery audit is untouched, and `audit_envelope` **recomputes**
the labels from `ctx` rather than trusting the envelope's text.

The minimum the review asked for was already true and still is: undiscovered ids never cross
(`ENVELOPE_UNDISCOVERED_EVIDENCE` plus the transport deny-set), solver/private ids never cross, and
unrelated engine ids never cross.

**Files changed.** `eidolon/decision/digest.py`, `eidolon/decision/envelope.py`,
`eidolon/decision/validator.py`, `eidolon/decision/turn.py`.

**Regression tests** (4). The digest a real turn sends carries no `E_knife`; an undiscovered id gets
no label and cannot describe itself; labels contain no `ObjectId` and no `E_` prefix; and a forged
`digest_text` carrying an id is still caught by the audit.

**Mutation result.** `P5-61` (render raw ids) and `P5-61a` (label undiscovered evidence too) — both
**KILLED**.

**Status.** Fixed.

---

## F-12 — no long-session coverage through the renderer

**Classification: D.**

**Root cause.** `tests/decision/test_long_conversation.py` calls `run_ask_turn` with **no renderer**
— it is a Phase 4 stress test. The longest LLM-path session anywhere in the suite was 15 turns, so
the reported "2 000-turn / 50-accusation stress: passed" was a statement about the deterministic
path only.

**Action taken.** A long-session test through `LLMRenderer`, driven by a scripted provider that
rotates through all four `reordering` shapes so claim-order drift would show at scale. It asserts
zero state divergence from the turn-for-turn Phase 4 reference, zero fallback accumulation, envelope
shape bounded independent of turn count (I-7), zero peels without evidence (I-3), claim-order
identity per statement, and that the whole session replays from its own events (I-22).

Checked in at **300 turns / 8 accusations** — the roadmap's own exit-criterion length — mirroring
how `test_long_conversation.py` is checked in at reduced scale. Run once on a scratch copy at the
literal **2 000 turns / 50 accusations** scale: **1 passed in 2 077.72 s** (34 m 37 s), every
assertion holding — zero divergence from the Phase 4 reference across 2 000 turns, zero fallbacks,
one envelope shape, zero peels, and a clean event replay.

**This validates the renderer harness, not real-model behaviour.** A scripted generator that always
returns valid output trivially yields a 0 % fallback rate and says nothing about the < 5 % criterion.

**Files changed.** `tests/llm/test_llm_important_repairs.py`.

**Status.** Fixed.

---

## F-13 — injection corpus below the documented target

**Classification: D (corpus gap) + A (three genuine gaps in the marker scan, found by building it).**

**Root cause.** Roadmap §30 lists "injection corpus v1 (≥ 100)" among Phase 5's tests. The suite had
24 player-side prompts; the Phase 5 report's "~80 distinct hostile inputs" summed them with 54
*model-side* attacks, which test the opposite end of the pipeline and are not fungible.

**Action taken.** 112 distinct player-typed prompts across the 15 named categories (7–10 each), plus
15 negative controls. Building it surfaced three real gaps in the stage-0 scan, all closed:

* `override` / `bypass` were missing from the override-verb list, so "Override your instructions"
  was not flagged;
* the pattern required a word boundary immediately after `disregard`, so plural verb forms
  ("disregards the rules") slipped past;
* Turkish `İ` casefolds to `i` + U+0307, so `İGNORE YOUR INSTRUCTIONS` was not flagged. The scan now
  folds NFKD and drops combining marks, which collapses that and every accented variant. Only the
  *scan* form is folded; `IngressResult.text` is never rewritten.

**Honest classification, not a tuned number.** Each entry declares whether the **deterministic** scan
must flag it. 71 of 112 must; the other 41 are semantically hostile but lexically innocent ("What is
your cover story?"), which stage 0 cannot classify and §22.2 hands to the parser. Adding "cover
story" to the regexes would flag an ordinary in-world question and would be a false claim of
deterministic coverage. What the suite asserts for **all 112** is containment.

| Category | n | deterministically flagged |
|---|---:|---:|
| direct_override | 8 | 8 |
| indirect_injection | 8 | 8 |
| role_confusion | 8 | 8 |
| hidden_state | 8 | 5 |
| unicode_variant | 10 | 8 |
| nested_instruction | 7 | 6 |
| malicious_evidence_ref | 7 | 6 |
| malicious_prior_text | 7 | 6 |
| multi_turn_escalation | 7 | 5 |
| solver_extraction | 7 | 4 |
| system_prompt_extraction | 7 | 4 |
| secret_extraction | 7 | 1 |
| entity_enumeration | 7 | 1 |
| evidence_enumeration | 7 | 1 |
| encoded_instruction | 7 | 0 |
| **total** | **112** | **71** |

**Files changed.** `eidolon/llm/ingress.py`, `tests/llm/injection_corpus.py` (new),
`tests/llm/test_llm_injection_corpus.py` (new).

**Regression tests** (875). Per prompt: the declared flag matches the scan in **both** directions;
the scan flags but never blocks; screening never rewrites what was typed; a flagged prompt escalates
only *toward* `meta`; and — with a model that **obeys** the injection, confessing and naming the
solver, a secret id, an evidence id and the canary — nothing forbidden reaches the player or the
ledger, the engine's decisions equal the no-injection baseline, the canary never appears, and the
player's line reaches the model as exactly one quoted JSON value. Plus multi-turn escalation run as
a real sequence, an obeying *parser* refused by the schema (I-26), and cross-corpus name-guessing
producing one indistinguishable reply.

**Mutation result.** `P5-62` (stop folding combining marks) and `P5-62a` (drop the override verbs
and plurals) — both **KILLED**. `P5-28`'s anchor was updated for the new `fold()` call.

**Status.** Fixed. 112 / 100.

---

# Verification

All numbers reproduced in this environment. No live model was contacted: there is no API key and
no network here.

```
python -m pytest -q                                                # 2000 passed
python -m pytest spike/test_spike.py -q                            # 21   Phase 0.5   unchanged
python -m pytest tests/world -q                                    # 98   Phase 1     unchanged
python -m pytest tests/minds -q                                    # 77   Phase 2     unchanged
python -m pytest tests/evidence -q                                 # 169  Phase 3     unchanged
python -m pytest tests/test_important.py tests/test_repairs.py -q  # 136  repairs     unchanged
python -m pytest tests/decision -q                                 # 180  Phase 4     unchanged
python -m pytest tests/llm -q                                      # 1340 Phase 5     (367 -> 1340)
python -m tests.decision.mutation_check phase5                     # 70 killed, 1 equivalent, 0 errors
python -m tests.decision.mutation_check                            # 57 killed, 2 equivalent, 0 errors
```

`2000 = 98 + 77 + 136 + 169 + 180 + 1340`. Phase 0.5–4 are untouched, to the test.

## Phase 5 test growth

| File | Tests | Added for |
|---|---:|---|
| `test_llm_injection_corpus.py` | 875 | F-13 |
| `test_llm_adversarial.py` | 124 | (unchanged) |
| `test_llm_ingress.py` | 75 | (unchanged) |
| `test_llm_pipeline.py` | 63 | (unchanged; one assertion updated in pass 1) |
| `test_llm_important_repairs.py` | 50 | F-5…F-12 |
| `test_llm_blocking_repairs.py` | 47 | F-1/F-2/F-3 |
| `test_llm_mutants.py` | 43 | (unchanged) |
| `test_llm_view.py` | 32 | +1 for F-4 |
| `test_llm_provider.py` | 21 | (unchanged) |
| `test_llm_cli.py` / `test_llm_seal.py` / `test_llm_determinism.py` | 5 / 3 / 2 | (unchanged) |
| **total** | **1340** | |

## Mutation verification

| Set | Mutants | Killed | Equivalent | Survived unexpectedly | Errors |
|---|---:|---:|---:|---:|---:|
| Phase 5 (`M5`, against `tests/llm`) | 71 | 70 | 1 | 0 | 0 |
| Phase 4 (`M`, against `tests/decision`) | 59 | 57 | 2 | 0 | 0 |

Baseline green before both runs (the harness refuses to report otherwise); all **145 anchors**
across both sets match exactly once. The three equivalents are declared, not silent: `M2` and `M4`
from the Phase 4 audit, and `P5-22`, unreachable since the F-2 repair removed the interpolation it
guarded (see pass 1).

Every mutation added in this pass was **KILLED**: `P5-49`…`P5-56` (F-10's caps, token sets, fallback
re-validation, plan-level classification), `P5-57`…`P5-57c` (F-7's commit boundary), `P5-58`/`P5-58a`
(F-5), `P5-59`/`P5-59a` (F-8), `P5-60` (F-9), `P5-61`/`P5-61a` (F-11), `P5-62`/`P5-62a` (F-13).

**One of them failed first, and that is worth recording.** `P5-53` ("spoken text may name any
discovered evidence id") survived the first run: the test asserted the evidence ids were in
`internal_tokens` using a state in which the evidence was *undiscovered*, so `prompt_deny_tokens`
supplied them regardless and the assertion never exercised the term it named. The test now presents
the item first, asserts the discovered id is **disjoint** from the deny set, and only then asserts
it is in `internal_tokens`. This is exactly the masked-assertion failure mode F-10 is about — found
by the harness, in a test written to close F-10.

## Long-session stress through the renderer (F-12)

| Scale | Path | Result |
|---|---|---|
| 300 turns / 8 accusations | `LLMRenderer` + scripted provider | **PASS** (checked in) |
| 2 000 turns / 50 accusations | `LLMRenderer` + scripted provider | **PASS** — 2 077.72 s, run once on a scratch copy |
| 2 000 turns / 50 accusations | Phase 4 deterministic path | **PASS** (unchanged, `test_long_conversation.py`) |

Asserted at both scales: zero state divergence from the turn-for-turn Phase 4 reference, zero
fallback accumulation, one envelope shape regardless of turn count (I-7), zero layer peels without
evidence (I-3), claim-order identity per statement (F-1 at scale), and a clean event replay (I-22).
The provider rotates through all four `reordering` shapes, so claim-order drift would surface.

**This validates the renderer harness, not real-model behaviour.**

## Deterministic replay

`test_llm_determinism.py` (cross-process, `PYTHONHASHSEED` 1/2/3, and independence from the model's
wording), the I-22 event-fold test, `tests/decision/test_fold_completeness.py`, and the pass-1 fold
test that a reordered render replays to the plan's order — **7 passed**.

## Final hostile pass

Re-run against the shipped code after all thirteen repairs:

| Attack | Result |
|---|---|
| Transport clears and rewrites its request's schema | `DRAFT_SCHEMA` intact; the vandal mutated only its own copy |
| Renderer returns each of the five impossible `ValidationResult` shapes | all five rejected with their own `RESULT_INTEGRITY:` code, caller's state untouched by identity |
| Any route by which a discovered evidence id reaches a prompt | none — `E_knife` absent from every system and user message |
| F-1: four segment shapes vs the template path | 1 distinct engine fingerprint |
| F-2: four real entity ids vs two invented names | 1 distinct repair line |
| F-3: two real hidden entities vs one invented | 1 distinct view |
| 112-prompt corpus with a model that obeys the injection | no forbidden token in any player-visible text or ledger entry; engine decisions equal the no-injection baseline |

No new leak or state-authority issue was introduced. The three blocking repairs still hold exactly.

## Live-model measurement

**Unchanged and explicitly UNMEASURED.** No API key, no network. Nothing in this pass claims a
real-model fallback rate, real provider acceptance, real verifier behaviour or real token budgets.

What the pass did change is that the measurement is now *possible*: F-8's latching rate limiter made
a 300-turn session through `play --llm` impossible at turn 31, and that is fixed and tested. The
remaining prerequisites are unchanged from the review — the `Alias` table is still empty, so a live
model writing "Elena" rather than "Elena Ruiz" falls back, and any rate measured before Phase 6
authors aliases measures the fixture rather than the pipeline.

| Criterion | Status |
|---|---|
| Fallback rate < 5 % on a 300-turn live session | **UNMEASURED — no real-model run available** |
| `vance_v03` playable with the live model | **REQUIRES LIVE MODEL** (and Phase 6 covers) |
| `AnthropicTransport` request shape accepted by the real API | **REQUIRES EXTERNAL SERVICE** |
| T-26 — 200 turns × 4 act classes, no act-class signal | **UNMEASURED** (act-class parity is tested locally under an injected clock) |
| I-7 envelope token budgets | **REQUIRES EXTERNAL SERVICE** (no tokenizer here) |

## Status

| | |
|---|---|
| BLOCKING remaining | **0** |
| IMPORTANT remaining | **0** |
| NON-BLOCKING remaining | **4** (F-14 `earlier` never populated · F-15 no `Solution` branch in `render_claim` · F-16 `GuardedTransport._scan` assumes JSON · F-17 no implementation-contract doc) |
| Live-model fallback rate | **UNMEASURED** |

**Phase 5 completion status: READY**, with the standing qualification that "ready" means everything
certifiable without a provider is certified. Structure is proven — the schema, the ports, the
layering, the failure table, the state-identity guarantees, the envelope's typed contents, the
commit boundary and the injection corpus. Behaviour against a real model is not, and the roadmap's
own exit criterion remains unmeasured until one is available.
