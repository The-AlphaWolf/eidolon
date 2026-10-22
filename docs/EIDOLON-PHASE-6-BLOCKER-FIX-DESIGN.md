# EIDOLON — Phase 6 re-audit: blocker fix architecture (RB-1, RB-2, RB-3)

**Status: design only. No code was changed.** Inputs: the Phase 6 hostile re-audit (RB-1…RB-3, I-1…I-11,
X1…X22), `docs/EIDOLON-ARCHITECTURE.md` v0.4, `docs/EIDOLON-PHASE-6-REPAIR-REPORT.md`, and the code under
`eidolon/decision`, `eidolon/evidence`, `eidolon/minds`, `eidolon/solve`, `eidolon/gen`.

Every root cause below was traced in source and, where marked **[probed]**, reproduced read-only against
`cases/generated/*.json` (scratch scripts outside the repo; nothing in the tree was modified).

Verdict: **READY FOR SONNET IMPLEMENTATION**, conditional on the seven ADRs in §G being accepted as written.
The fixes stay inside the existing architecture. Several of them are spec-level clarifications, not code
patches, and §H says where they will move numbers.

---

## A. Blocker-by-blocker root cause

### RB-1: the murderer's cover cannot be broken in real play

**Violated contract.** §20.1 item 6 and §19.3 assume that the breaker set V-3 derives can actually be
presented at runtime: "every lie the player is expected to detect has a reachable breaker". I-33 says
unlocking depends on the player's global *discovered* material. The six-state ladder
(`… DISCOVERED -> VISIBLE TO PLAYER`) says material is held only after it has been obtained. RB-1 breaks two
trust boundaries at once:

1. **The identity boundary.** One `requires` token resolves three or four different ways.
2. **The acquisition boundary.** Something the player never heard can unlock and peel.

**Data path (traced).**

| Step | Code | What happens |
|---|---|---|
| 1 | `gen/compile.py::_evidence` | `E_trace.implications[0].requires = ("clean@<hk>",)` |
| 2 | `gen/compile.py::_statements` | A pre-authored `Statement(id="clean@<hk>", turn=0, …)` is sealed into `pkg.statements` |
| 3 | `gen/pipeline.py::decision_context` → `cover_consistency._context_for_subset` | V-3 puts `clean@<hk>` into `ctx.statements`. When the id is in a subset, it puts it into `DiscoveryState.known_statements`, so `E_trace` unlocks and `{E_trace, clean@hk}` is derived as the breaker set |
| 4 | `solve/lattice.py::_resolve` | The solver resolves the *same string* a different way, as "the speaker's own `Participated` atom whose events contain `clean`". A third meaning lives in `lattice.statement_intervals`, the P-9 hull, which accepts any `event@actor-or-participant` pair |
| 5 | `solve/bots.py::build_state` | The session starts with `StatementStore()` and `DiscoveryState()`, both empty, by design ("a bot must hear them") |
| 6 | `decision/turn.py::run_ask_turn` stage 10 | The commit writes `Statement(id=f"S{turn:05d}")`. **No code anywhere writes `DiscoveryState.known_statements`.** `StatementHeardEvent` exists in `decision/exploration.py`, but nothing emits it. A faithful delivery of the cleaning account therefore never becomes "heard" material |
| 7 | `decision/weight.py::refutation_weight` | `player_material = known_evidence ∪ known_statements ∪ presented`. The token can enter **only** through `presented`, and `presented_ref` is an unchecked string (`cli.py` passes the raw text after `present `) |
| 8 | `turn.py::relevant_secret` + `strategy._lie` | Even if step 6 were fixed, the housekeeper never delivers the account. Asked "did you clean the decanter", she answers with her own cover LIE **[probed: manor_wing_s4, study_party_s4 → `LIE At(hk, <lie_loc>, <secret_iv>)`]** (RB-2's mechanism, below) |

So:
- Legitimate play: E_trace stays locked forever, and the weight is 0 against `DidNot(M, touch, …)`.
- Presenting the bare string `clean@Beatrix` puts it into `presented`, unlocks E_trace, and peels the murderer **[probed: `CONCESSION`, 1 peel]**.

**Second, independent defect (I-9).** `planner.plan` draws `M = rng.choice(living)`, and `living` includes
the housekeeper. When `M == hk`, the only breaker set is `{E_trace, clean@M}`, which rests on the murderer's
own account. V-3 never asks whether a breaker account can be delivered by its speaker, or whether it belongs
to the secret's own owner.

### RB-2: proof-core testimony cannot be acquired through the engine, and the bots are not engine-faithful

**Violated contract.** §19.7 / T-20 requires that the cue-following bot solve on its own acquired set.
§20.1 items 5, 8 and 10 require proof-core testimony to be askable. I-39 requires strong retrieval from an
expressible `Query`. The trust boundary is between **what the engine committed** (the ledger) and **what the
bot is credited with**. That boundary does not exist today.

**Crediting path (traced).** In `solve/bots.py`:
- `greedy_bot`, `random_bot` and `cue_following_bot` call `_ask(...)` and then, unconditionally, `acq.atoms |= ask_yields(pool, who, targets)`.
- `ask_yields` returns every atom in the solver's fixpoint pool (`obtainable` = `robust_material`) whose proposition mentions a named entity.
- The act the engine chose, whether the turn was rejected, and what was committed are all ignored.
- `order_shuffled_bot` never asks at all; it reads `ask_yields` for every entity.
- `solve_on` then runs the solver on that set.

The bots therefore "solve" with a dead engine (attack 42), and the mutants X15 and X16 survive.

**V-7 is not wired (X18).** `pipeline.validate.v7` is `cued_depth <= N_CUE`. That is a reachability depth, and
no bot runs. `fair.bluff_converges` (`evaluate(ctx, {})`) is reported but can never be true.

**Why the real engine never yields the testimony.** These are independent causes, and each one alone is enough:

| # | Cause | Location | Evidence |
|---|---|---|---|
| C1 | **Whereabouts capture.** If the query names no protected entity, `relevant_secret` falls back to `return owned[0] if len(owned) == 1` for every `where/when/did_you/did_they/who` query. Every character owns exactly one secret (`compile._secrets`), so every whereabouts question is "about" the speaker's secret | `turn.py:144-149` | **[probed]** "Did you see Delphine at t_m?" → Beatrix answers `LIE` |
| C2 | **LIE ignores §10.3's precondition.** The table says LIE requires that "current layer has a claim **covering the asked proposition**". `_lie` offers the whole layer whenever a secret is topical, so a question about 21:40 in the Suite gets "I was in the Library 22:00-22:20" | `strategy.py::_lie` | same probe |
| C3 | **The scorer always prefers LIE.** `exposes_protected` and `contradicts_own_standing` are never set by any builder, so the safety and consistency terms are inert. `goal_fit` is 0.5 for LIE and 0.4 for TRUTH, so LIE (2.44) beats TRUTH (2.40) whenever both are candidates | `strategy.py::utility` | arithmetic over the constants |
| C4 | **Threat inflation.** A topical secret gives `threat = 0.6 > 0.4`, which brings in `EVASION` | `turn.py::compute_threat` | — |
| C5 | **Boosts are never applied.** `MemoryBoost` is sealed and V-4 applies it inside its own check, but `bots.build_state` and every other session constructor ignore it. Proof-core memories stay weak, which gives `VAGUE` | `bots.build_state` | **[probed]** exact-cue ask with no secrets and no boosts gives `VAGUE`; with boosts it gives `TRUTH` |
| C6 | **Topic vocabulary is split.** `query_cues` tags the topic with `predicate_hint` ("presence", "see"). Memories tag it with the proposition kind (`at`, `did`, `heard`). Jaccard needs about 0.85 overlap at strength 0.65, so a natural question can never reach `strong` | `turn.query_cues` vs `minds.memory._cues_for_prop` | **[probed]** hint `presence` gives `VAGUE`, hint `at` gives `TRUTH` (boosted, no secrets) |
| C7 | **V-4's I-39 check is a proxy.** `fairness.retrieval_check` scores a memory against its *own* cue set. No `Query` and no engine are involved, so it certifies queries the parser cannot produce and responses the strategy never selects | `fairness.retrieval_check` | the check passes while the probes above fail |
| C8 | **Retrieval selection is order-dependent.** `retrieve_for_query` takes the first strong memory in list order (not the highest score), then always `mem.content[0]`. A strong episodic memory whose relevant belief is not first can never be delivered | `turn.retrieve_for_query` | code |
| C9 | **Innocents cannot concede.** `peel.evaluate_peel` applies the I-21 uniqueness gate to *every* `terminal="confession"`. For a non-murder secret the confrontee is never the unique survivor, so the innocent STONEWALLs forever. That covers 50% of innocents, chosen by hash. The cracked material the solver's I-45 fixpoint credits is unobtainable in play | `peel.py:97-102`, `compile._secrets` (terminal by hash) | **[probed]** manor_wing_s4: Delphine (`confession`) + `E_secret_Delphine` gives `STONEWALL`, no peel. Beatrix (`stonewall`) gives `CONCESSION` |
| C10 | **Stonewall swallows everything.** Combined with C1, a character in the stonewalled state STONEWALLs every whereabouts question | `strategy.select_plan` forced-act loop + C1 | — |
| C11 | **No runtime mirror of I-45.** The solver withholds every atom whose observation segment overlaps the speaker's protected interval (`lattice.testimony_pool`). The runtime has no such rule. Today the withholding happens *by accident*, through C1–C3's LIE dominance. Fixing C1–C3 without adding this rule would leak protected-interval knowledge | `strategy._truth` checks `is_protected(prop)` only | — |

The manor_wing proof core is `{E_alibi_Beatrix, E_gate_Terrace, E_watch, S:P0062, S:P0063, S:P0064}`. The
three atoms are Beatrix's co-presence `At(Delphine|Emeric|Fiora, Suite, (51, 67))`, all outside her protected
interval. C1+C2+C3 make her LIE, and C5+C6 make her VAGUE once the LIE is removed. That is exactly the auditor's
"3 survivors".

### RB-3: `verify_proof` accepts forged proofs

**Violated contract.** The verifier is supposed to be an *independent* check that the case is unique *from
admissible, discoverable material at the case's fairness level*. Today it checks an internally consistent story
about **whatever constraints the proof chooses to list**. The trust boundary is between the proof (data) and
the package (sealed truth). The verifier accepts the proof's own statements about material, levels, fairness
and completeness without checking them.

**Traced holes in `solve/proof.py::verify_proof`:**

| # | Hole | Consequence |
|---|---|---|
| H1 | `c["item"]` is never resolved. No check confirms that it names an evidence item with that implication, or a testimony atom with that proposition | `item="GOD_MODE"` / `NO_SUCH_ITEM` verify |
| H2 | `c["level"]` is self-reported. Nothing re-derives I-44 fixing, I-37 corroboration or the `requires` minimum | True-but-unobtainable or L1 material passes as hard |
| H3 | The constraint **set** is never compared to what the package admits. Omissions are invisible | The truth audit and the robustness check only cover what was submitted; hiding a false admissible constraint or a distortion failure works |
| H4 | `proof["fairness"]` is self-reported, and every level is compared against it | `fairness = 0` verifies |
| H5 | `truth_audit` for `Heard` checks that an Attack happened at that place and time but **ignores `actor`** | `Heard(attack, actor=Elena)` passes for any attacker |
| H6 | The **voice whitelist**: `if voices and X not in voices and core[0]["kind"] == "Heard": if core[0]["id"] in ids: continue`. `voices` comes from the proof's own constraints. Combined with H5, one forged Heard excludes everyone else, including the true murderer | The wrong-murderer forgery (attack 7) |
| H7 | `proof_core`, `robustness` and `fragility` are carried through unchecked | Forged band and robustness claims |
| H8 | `proof["constraints"]`, `c["iv"]` and the rest are indexed raw | `{}`, string intervals and so on crash (`KeyError`/`TypeError`) instead of rejecting (I-15) |
| H9 | `NoStranger` audit hard-codes the victim as observer, and the JSON drops the observer (N-4) | The D-1 reading is unchecked (X21 survives) |
| H10 | `write_package` stores the proof next to the package with no hash. `read_package` returns it unverified | Phase 7 would persist a detached, unauthenticated trust root |
| H11 | The candidate domain is `case.living_actors()`, which is filtered by the authored `role` | An `offstage` relabel hides a viable suspect from both the solver and the verifier (I-2, X1) |

Independence still holds in the narrow sense: no solver function is called. `BIN` is imported from
`solver`, and `EXT` from world (N-13).

---

## B. Required invariants (new; each needs a mutation-killing test)

| ID | Invariant |
|---|---|
| **I-49 Account identity** | A `requires` / `StatementHeard` / breaker ref that is not an `EvidenceId` is an **account token** `"<event_id>@<actor_id>"`. It is resolved by exactly one module (`minds/accounts.py`). The token denotes the actor's `Participated` knowledge of that event whose proposition is a `Did`. P-9, the solver, V-3, V-4, the runtime unlock and the bots all call that module and nothing else |
| **I-50 Delivery-only hearing** | A session starts with an empty ledger, empty `known_statements` and empty `known_accounts`. A statement id enters `known_statements`, and a token enters `known_accounts`, **only** through the stage-10 commit of a non-rejected turn. A token is minted only when a committed, non-retracted `actual` claim's grounding contains the speaker's own `Participated(event_id=e)` entry **and** the claim's proposition equals that entry's proposition. Lies, cover claims, distortions, `InvestigationTold` chains, VAGUE hedges, incidentals and slips never mint. The fold refuses an `AccountHeard` / `StatementHeard` row the ledger does not back |
| **I-51 Held-only presentation** | `presented_ref` must be a package `EvidenceId` or a ledger `StatementId`. Account tokens are never presentable. Anything else is a rejected turn with no state change, never an exception |
| **I-52 Engine-faithful credit** | A V-7 bot's material is `state.discovery.known_evidence`, plus the testimony atoms of **committed ledger claims** (via I-49's entry→atom map, carrying the proposition as actually said). Nothing else counts. A turn that was rejected, or a claim that does not resolve to a perception entry of its speaker, credits nothing |
| **I-53 V-7 gates** | A package seals only if the engine-faithful greedy and cue-following bots each reach a unique survivor equal to `solution.murderer` within `N_MAX` / `N_CUE`, the murderer-peel bot peels the murderer's layer 0 with a derived breaker set obtained only through real turns, the bluff bot does not converge, and the adversarial bot records zero peels and zero leaks — **at the architecture's full scale**. The scale is recorded in the sealed report |
| **I-54 Runtime/solver withholding parity (I-45 mirror)** | At runtime a claim is speakable only if (a) its proposition is not protected for the speaker, (b) none of its grounding entries' observation segments overlap a protected interval of a speaker's secret that has not yet been conceded at the current layer, and (c) it does not contradict the speaker's current-layer claims. "Not yet conceded" is the runtime counterpart of the solver's "not cracked". Both read one `Secret.protected_intervals()` definition |
| **I-55 Topicality is a footprint, never a wording** | A secret is topical for a query iff the presented ref maps to it, or the query's footprint (actors, location, time) intersects the footprint of an **unconceded** protected proposition of that secret. LIE is a candidate iff the secret is topical **and** a current-layer deceptive claim's footprint intersects the query footprint (§10.3 "covering"). `Query.presupposes` is never read by topicality (bluff parity, §6.5) |
| **I-56 Murder-only confession gate** | I-21's uniqueness gate applies to the **murder** secret's `confession` terminal. A non-murder secret's `confession` terminal is a concession terminal: landing on it is an ungated peel voiced as CONCESSION, and no act other than CONCESSION ever voices it (no CONFESSION act for non-murder secrets) |
| **I-57 Proof completeness by independent derivation** | `verify_proof` re-derives the admissible hard-constraint set from the sealed package with an implementation that shares no code with `solve/lattice.py` or `solve/solver.py` (constants included). The proof's hard set must be **semantically equal** to it, compared at tick/cell level. Every constraint, core, survivor time, window, cracked set, proof-core claim and robustness claim is checked against that derivation. The fairness level is read from the package, never from the proof. Every proof field is either verified or absent |
| **I-58 Proof is sealed, never detached** | A case is persisted as one `SealedCase` bundle `{package, proof, report, bundle_seal}`, where `bundle_seal = sha256(canonical({package.seal, sha256(proof), sha256(report)}))` and `proof.package_seal == package.seal`. The only reader is `load_sealed_case()`, which refuses unless every seal matches **and** `verify_proof(package, proof) == []` **and** the report records every stage OK at full scale |
| **I-59 Candidate domain is physical** | The verifier's candidate domain is every actor with a CaseLog presence segment who is not dead at `t_investigation`, minus the victim. V-0 rejects a package whose `role` labels disagree with it (an `offstage` actor with presence, or a victim with no `Die`) |
| **I-60 Breaker accounts are deliverable** | For every derived breaker set: each account token's speaker is not the secret's owner, and the token is deliverable under I-54 at the layer state V-3 evaluates (round 0 of the availability fixpoint, §C.3). For the murder secret, at least one such set exists |

---

## C. Proposed design changes

### C.1 Shared `requires` / statement identity model (`eidolon/minds/accounts.py`, new)

It lives in `minds` because it needs world perception and minds knowledge, and because `evidence`, `decision`,
`solve` and `gen` all sit above `minds` (§23.1). It is pure, deterministic and cached per `Case`.

```text
AccountToken = str                                   # "<event_id>@<actor_id>"; parse/format here only
parse(token) -> (event_id, actor_id) | None          # malformed -> None (fail closed)
entries_of(case, knowledge, token) -> tuple[KnowledgeEntry]
    # the actor's Participated(event_id=e) entries whose proposition.kind == "Did"; () if none
atoms_of(case, token) -> tuple[str]                  # "S:P####" perception ids, same rule on PerceptionFact
token_interval(case, token) -> Interval | None       # the P-9 hull input: the event interval, only if entries_of() is non-empty
atom_of_entry(case, knowledge, entry_id) -> str | None
entry_of_atom(case, knowledge, atom_id) -> KnowledgeEntry | None
    # explicit identity by (character, proposition, provenance event) — replaces the positional
    # `zip(store.all(), derive_perception(case))` copied in distort.py, fairness.retrieval_check and
    # fairness.memory_boosts_for; returns None on any ambiguity (fail closed)
observation_segment(case, knowledge, entry_id) -> Interval | None   # pf.obs_interval (for I-54)
tokens_satisfied(case, knowledge, beliefs, claim, speaker) -> frozenset[AccountToken]   # I-50's minting rule
```

Consumers:
- **P-9:** `pipeline.v1` passes `accounts.token_intervals(case)` to `check_evidence_grounding` instead of
  `lattice.statement_intervals`. That is stricter, because the token must resolve to a real `Participated` entry.
- **Solver:** `lattice._resolve` uses `accounts.atoms_of` filtered to the material pool.
  `lattice.statement_intervals` is deleted.
- **Runtime:** `turn.run_ask_turn` stage 10 calls `tokens_satisfied` for every committed claim (§C.2).
- **V-3:** `cover_consistency` pools account tokens and derives their weighable claims from `entries_of` (§C.3).
- **V-4 and bots:** `atom_of_entry` / `entry_of_atom`.

### C.2 How a pre-authored account enters a session (RB-1)

1. **The package declares and does not script.** `CasePackage.statements: tuple[Statement]` is replaced by
   `accounts: tuple[AccountToken, ...]`, the accounts the case's covers and breakers rely on. The account's
   *content* is derived (`accounts.entries_of`) and never sealed as a second copy. Pre-authored text was flavor
   and has no runtime role. V-0 rejects a token that does not parse, does not resolve, or names a dead or
   `offstage` actor.
2. **The session starts empty (I-50).** `solve/session.py::new_session(sealed_case, personalities)` is the
   only constructor. It replaces `bots.build_state`, and the Phase 7 loader must call it. It:
   - builds the knowledge, belief and memory stores;
   - applies `memory_boosts` to `Memory.strength_0`. This is the §19.4 load-time obligation, and it is the
     only runtime reader;
   - starts with `StatementStore()`, `DiscoveryState()`, `known_accounts = ∅`.

   The harness default `Personality` stays an explicit argument (I-6 stays open).
3. **Delivery mints.** In `run_ask_turn` stage 10, after the `Statement` is built from the plan's voiced claims:
   - `accounts = ⋃ tokens_satisfied(claim)` over the committed claims;
   - the statement records `Statement.accounts = accounts`. This is a recorded outcome, never recomputed on
     replay (I-22);
   - the turn emits `StatementHeard(statement_id)` and one `AccountHeard(token, statement_id)` per token. The
     `decision.exploration` fold applies them to `DiscoveryState.known_statements` /
     `DiscoveryState.known_accounts` (a new frozenset field with an empty default).

   **Fold validation.** Like `apply_discovery`, the fold refuses a row whose statement is not in the ledger,
   whose speaker is not the token's actor, or whose statement does not list the token.
4. **Unlocking reads only held material.** `weight.refutation_weight`'s `player_material` and
   `discovery.project_for_player` use `known_evidence ∪ known_statements ∪ known_accounts ∪ presented`.
   `presented` is now I-51-checked, so it cannot carry a token. `_prereq_met(StatementHeard)` checks
   `known_statements ∪ known_accounts`.
5. **Presentation is checked (I-51).** At the top of `run_ask_turn`:
   - `presented_ref ∉ evidence ∪ ledger` → rejected `UNHELD_PRESENTED_REF`, with no state change.
   - An evidence item that is not yet known and whose prerequisites are unmet is also rejected. Today it raises
     `ValueError` out of `apply_discovery`, which violates I-15.
   - The stricter "evidence must already be in `known_evidence`" rule is I-10's remaining half. It changes
     Phase 4 fixtures that present undiscovered items, so it is recommended but not required for RB-1.
6. **A presented statement matches authored responses by token.** `relevant_secret` and
   `_deny_evidence_or_reinterpret` compare `EvidenceResponse.evidence` / breaker refs against
   `{presented_ref} ∪ ledger[presented_ref].accounts`. Presenting the housekeeper's delivered statement to the
   murderer then finds the authored `EvidenceResponse("clean@hk", layer 0)`.
7. **The housekeeper is never the murderer (I-9, construction).** `planner.plan` draws `M` from
   `[a for a in living if role[a] != "housekeeper"]`. The housekeeper role exists to be the §18.3(f)
   opportunity witness. The I-60 V-3 check is the invariant that catches a regression.
8. **Breaker-account memories are protected like proof-core memories.** In `pipeline.finalize`, the memories
   behind every token in a derived murder-layer-0 breaker set are boosted and excluded from distortion. A
   distorted delivery does not mint (I-50), and boosts make it retrievable.

**End-to-end path after the fix (the RB-1 acceptance scenario):**
1. `Search(E_scene)`, then `Dust(E_trace)`.
2. Ask the housekeeper an expressible question about the cleaning. The answer is `TRUTH Did(hk, Clean, weapon, …)`
   with grounding equal to her `Participated(clean)` entry. That commits `S000k`, mints `clean@hk`, and
   `known_accounts ∋ clean@hk`.
3. Present `E_trace` to the murderer, or address any later turn to them (I-33 recomputes every turn). E_trace's
   implication is now unlocked, the weight is at least `RESOLVE_L0`, and `LayerPeel(0→1)` is voiced as
   CONCESSION.

Presenting `clean@hk` itself is rejected at step 5 of §C.2.

### C.3 V-3 over the same identity (RB-1)

- `_candidate_pool` = authentic evidence ids ∪ `pkg.accounts` tokens that are **deliverable** (I-54 / I-60).
- The weighable claims of a token are built from `entries_of(token)`:
  `Claim(id=f"acct:{token}:{i}", proposition=e.proposition, sincerity="truthful", source="plan", grounding=(e.id,))`.
  These are exactly the claims a faithful delivery commits, so V-3 and the runtime weigh the same thing.
- `_context_for_subset` puts tokens into `known_accounts`.
- **Availability fixpoint (mirrors I-45 over covers).**
  - Round 0: tokens whose entries' observation segments avoid every unconceded protected interval.
  - Round k+1: add the tokens of owners whose secret has a breaker set drawn from round-k material that lands on
    a conceding layer.
  - The murderer's secret never contributes.
- **New V-3 checks:**
  - (vi) **I-60**: no breaker set of a secret contains an account by that secret's owner.
  - (vii) **I-56 parity**: V-3 models the peel gate exactly as `evaluate_peel` does (murder-only).

### C.4 Strategy and engine behaviour (RB-2, C1–C11)

All of the following are in `decision/`:

| Fix | Change | Closes |
|---|---|---|
| **S1 Footprint topicality** | `relevant_secret` = presented-ref match (incl. account tokens, §C.2.6) **or** query-footprint ∩ unconceded-protected-footprint (I-55). The `len(owned)==1` fallback is deleted. Footprint: actors = `{subject, object if actor}` ∪ `{speaker}` for self-directed kinds; location = `query.location` or *any*; time = `query.time.interval` or `[0, T)`. §29.2 turns 1–2 stay LIE, because the times and locations overlap the protected footprint | C1, C4, C10 |
| **S2 LIE covers** | `_lie` is built only when a non-terminal current-layer claim's footprint intersects the query footprint | C2 |
| **S3 Speakability (I-54)** | A single `speakable(claim, speaker, secrets, layer_state, knowledge)` predicate gates `_truth`, `_vague`, `_repeat_prior` and `_correct_detective`. An unspeakable claim produces no candidate. The fallback is then DONT_RECALL / EVASION / LIE per the act table. It reads `Secret.protected_intervals()`, the same helper `lattice.protected_intervals` uses | C11 (and keeps C1–C3 from turning into leaks) |
| **S4 Scorer** | `_truth` sets `contradicts_own_standing` via `contradiction()` against standing ledger claims, so W_CONSIST becomes live. The `goal_fit` constants are unchanged. Once S1/S2 remove LIE from non-covering questions, the 0.04 margin no longer decides those turns. When LIE *does* cover, lying is the intended answer | C3 |
| **S5 Murder-only gate (I-56)** | `evaluate_peel`: the confession gate fires iff `secret.kind == "murder"`. `_confession` returns `None` for a non-murder secret. M8 (`test_invariant_mutants.py`, `kind="murder"`) is unaffected | C9 |
| **S6 Retrieval selection** | `retrieve_for_query` takes the **highest-scoring** strong (else weak) memory with a hash tie-break, and within it the belief whose `_cues_for_prop` overlaps the query cues most (tie by id), instead of `content[0]` | C8 |
| **S7 Topic vocabulary** | `query_cues` maps `predicate_hint`/`kind` through a closed table onto proposition-kind topics (`where/who/presence/see/with` → `at`; `hear/heard` → `heard`; action verbs → `did`; else the hint as today). The parser and the Phase 5 schema are unchanged. This is grounding's "topics→TopicIds" (§12.1 stage 2) made real at the one place cues are built | C6 |
| **S8 Boosts at load** | `new_session` applies `memory_boosts` (§C.2.2) | C5 |

### C.5 Engine-faithful bots and a real V-7 (RB-2)

- **Delete** `obtainable`, `ask_yields` and the `Acquired.atoms` side-channel.
- **Add** `credited_material(state, case, knowledge) -> dict[str, Item]`:
  - evidence = `state.discovery.known_evidence`;
  - testimony: for every ledger statement and every non-retracted committed claim whose grounding resolves (via
    `accounts.entry_of_atom` / `atom_of_entry`) to a perception entry **of that speaker**, add `Know(id=atom,
    who=speaker, prop=claim.proposition, source/events/obs from the perception fact)`. The proposition is the one
    *actually said*, so an uncorrected distortion is credited as said, which is exactly V-5's robustness model;
  - nothing else (I-52).
- **Query vocabulary.** `expressible_queries(case, speaker, named)` is shared by V-4 and the bots: kinds
  `{did_they, who, where, did_you, what}` × subjects/locations named by held material × 30-minute
  `TimePhrase` buckets named by held material (the time pin's bucket, the alibi log's window). Greedy enumerates
  over everything held; cue-following uses only cued names. No hidden memory cues are read.
- **Murderer-peel bot (new).** The bot holds only real-turn material. For each derived murder-layer-0 breaker set,
  it acquires the evidence by search and the accounts by asking, then addresses the murderer. It must record
  `LayerPeel(0→1)`. This is RB-1's acceptance as a V-7 bot.
- **`pipeline.v7`** runs greedy, cue-following, murderer-peel, bluff (`N_BLUFF = 500` per character) and
  adversarial (`N_ADVERSARIAL = 500`) at full scale, gating per I-53. `judge`-style comparison: the bot survivor
  must equal `solution.murderer`, read **only** in the pipeline. The bluff convergence / parity measurement is
  unchanged. `fair.bluff_converges` is deleted from V-6 item 9, which now reads the V-7 bluff result. Reports
  carry `{"scale": "full"|"reduced"}`, and only `full` seals.
- **V-4 engine-faithful I-39** (`fairness.retrieval_check` replaced). For each proof-core atom and each breaker
  token, some `q ∈ expressible_queries` addressed to its speaker from `new_session(pkg)` commits a claim whose
  `atom_of_entry` is that atom (or which mints that token). For cracked atoms, the check runs from a state where
  the owner's secret has been peeled through real turns. `finalize` raises the boost (6500 → … → 10000, bounded)
  until this passes, as §19.4 literally specifies. Otherwise V-4 rejects.

### C.6 Proof verification redesign (RB-3)

**Proof document `eidolon.proof/2`** is a strict pydantic model (`extra="forbid"`, strict ints, bounded list
lengths):

```text
schema, package_seal, fairness, candidate_domain[],
cracked[]: {actor, round, core[constraint ids]},
constraints[]: {id, item, kind, actor, observer?, loc, iv[2], level, sources[]},
window[2], murder_loc,
candidates{X: {excluded, core: [ids] | {"kind":"VOICE","by":id} | {"kind":"TIME"}, times[]}},
survivors[], time_bins[], outsider{excluded, blocked[constraint ids]}, unique,
proof_core[], robustness{subsets_run, failures[]}
```

`fragility` and `reasons` are removed: they are recomputed by V-6 from verified cores. This is the "verified or
absent" rule.

**Verifier pipeline** (`solve/proof.py` + new `solve/proof_material.py`; no imports from
`solver/lattice/distort/fairness/bots`; `BIN` / `MAX_WINDOW` move to `solve/package.py`):

0. **Parse.** Malformed input returns `["malformed proof: …"]`. The whole verifier body is wrapped so any
   exception becomes `["verifier error: <type>"]`. This is fail-closed, and goldens-must-verify keeps bugs visible.
1. **Seal binding.** `pkg.verify_seal()`, `proof.package_seal == pkg.seal`.
2. **Fairness.** `proof.fairness == pkg.fairness_level`, a new sealed package field (v1 default `2`, "standard").
   All level tests use the package's value (H4).
3. **Candidate domain (I-59).** Derived from CaseLog presence and death ticks. It must equal
   `proof.candidate_domain`, the candidate table keys, and `case.living_actors()` (the last equality is I-2's
   label check) (H11).
4. **Independent derivation (I-57).** `proof_material.derive(pkg, cracked)` is written **from §19.5 /
   I-27 / I-37 / I-44 / I-45, not from `lattice.py`**:
   - L3: authentic implications, P-9 via `evidence.grounding.established_interval`, `requires` via `minds.accounts`.
   - L2: tick-level presence fixing by L3 `At` or by independent `At` testimony (different speaker, different
     collusion component, disjoint provenance events), or direct corroboration.
   - L1 otherwise.
   - Withholding by `Secret.protected_intervals()` unless cracked.
   - The I-45 fixpoint is recomputed with the oracle. The recomputed cracked set must equal `proof.cracked`, and
     each cracked entry's core must use only material available in its round.
5. **Completeness and soundness (H1–H3).** The proof's hard constraints, expanded to cells
   (`At`/`NotAt`: (kind, actor, loc, tick); `Exist`/`Heard`/`Died`/`NoStranger`: (kind, actor, observer, loc, iv)),
   must equal the verifier's derived hard set exactly. Every `item` must exist in the derived universe. Any
   difference is reported per constraint.
6. **Truth audit** over the *derived* hard set:
   - `At`/`NotAt`/`Exist` via `loc_at`;
   - `Died` via death ticks;
   - `Heard(attack)`: an `Attack` event at that location overlapping the interval **whose `actor` equals the
     constraint's actor** (H5);
   - `NoStranger` via the Phase 1 reading A, with the constraint's **recorded observer** (H9, N-4).
     Phase 1 semantics are not changed.
7. **Window** = intersection of derived pins at the murder location; it must equal `proof.window`.
8. **Per candidate.**
   - Excluded with a constraint core: cores ⊆ derived ids; the oracle says infeasible; deletion-minimal.
   - `VOICE`: the cited id must be a *derived* hard `Heard(attack)` at the murder location, overlapping the
     window, with `actor ≠ X`. If the derived hard set names two or more distinct voices, reject (fail closed).
     This replaces the whitelist (H6).
   - `TIME`: the oracle finds no feasible tick.
   - Survivor: `times` = the oracle-feasible ticks. A window longer than `MAX_WINDOW` is rejected (the verifier
     never approximates).
9. **Outsider** re-derived from the derived `NoStranger` cells. **Unique** re-derived.
10. **proof_core (H7).**
    - Every item is a derived-universe item available at the fixpoint.
    - Re-deriving from the core material alone gives a unique result with the same survivor, one bin, and a
      closed corridor.
    - The core is 1-minimal (drop any item and uniqueness fails).
11. **Robustness (H7).** Every subset of relevant `pkg.distortions` (those whose atoms yield a constraint at any
    level, base or shifted) is re-derived with shifted atoms and must stay unique with the same survivor. More than
    `2**10` subsets is rejected ("robustness unverifiable within bound"), never sampled.
    `proof.robustness.failures` must be empty and `subsets_run` must equal the verifier's count.

**Sealing (§C.7 / I-58).**
- `solve/package.py::SealedCase` holds `{package, proof, report, bundle_seal}`.
- `pipeline.write_package` writes it, and `read_package` is replaced by `load_sealed_case(path)`, which performs
  I-58's checks or raises a typed refusal. `eidolon validate` uses it.
- The proof is never a premise for gameplay: the I-21 confession check and §16.3 scoring use the runtime solver on
  presented material.
- An AST test asserts that nothing outside `solve/package.py`, `gen/pipeline.py` and `cli.py` touches a raw proof
  dict.

---

## D. Exact files / modules to change

| File | Change |
|---|---|
| `eidolon/minds/accounts.py` **(new)** | §C.1 shared identity resolver |
| `eidolon/minds/knowledge.py` | No model change. `accounts` reads it. (Optional: expose the perception id on the entry if the explicit match proves ambiguous; prefer not to) |
| `eidolon/evidence/discovery.py` | `DiscoveryState.known_accounts` (additive); `_prereq_met`, `project_for_player` and the reachability seed include it |
| `eidolon/decision/claims.py` | `Statement.accounts: tuple[str, ...] = ()` (engine-side; never rendered) |
| `eidolon/decision/exploration.py` | `AccountHeard` event; `StatementHeard` / `AccountHeard` fold validation against the ledger (needs ledger access, so the validating fold lives in decision) |
| `eidolon/decision/turn.py` | I-51 presented-ref check; S1 `relevant_secret`; S6 `retrieve_for_query`; S7 `query_cues`; stage-10 minting + heard events; pass layer state to `speakable` |
| `eidolon/decision/strategy.py` | S2 `_lie` covering; S3 `speakable` gate in `_truth` / `_vague` / `_repeat_prior` / `_correct_detective`; S4 `contradicts_own_standing`; S5 `_confession` murder-only |
| `eidolon/decision/peel.py` | S5 gate murder-only |
| `eidolon/decision/secrets.py` | `Secret.protected_intervals()`; footprint helper (or in a small `decision/footprint.py`) |
| `eidolon/decision/weight.py` | `player_material` includes `known_accounts` |
| `eidolon/decision/cover_consistency.py` | Token pool + derived content + availability fixpoint; checks (vi) and (vii) |
| `eidolon/solve/package.py` | `statements` → `accounts`; `fairness_level`; `BIN` / `MAX_WINDOW` constants; `SealedCase`; `load_sealed_case` |
| `eidolon/solve/session.py` **(new)** | `new_session` (boosts applied, empty ledger) |
| `eidolon/solve/lattice.py` | `_resolve` via `minds.accounts`; delete `statement_intervals`; `protected_intervals` via `Secret.protected_intervals()`; emit `observer` on `NoStranger` constraints |
| `eidolon/solve/solver.py` | Import constants from `package.py`; voice exclusion keeps its semantics but its core is `{"kind":"VOICE","by":id}` |
| `eidolon/solve/distort.py`, `eidolon/solve/fairness.py` | Positional zips → `accounts.entry_of_atom`; `retrieval_check` → engine-faithful I-39; `breakers_reachable` over tokens; delete `bluff_converges` from the contract; `memory_boosts_for` covers breaker tokens |
| `eidolon/solve/bots.py` | §C.5: `credited_material`, `expressible_queries`, murderer-peel bot; `new_session`; delete `obtainable` / `ask_yields` |
| `eidolon/solve/proof.py` + `eidolon/solve/proof_material.py` **(new)** | §C.6 |
| `eidolon/gen/planner.py` | `M` drawn from non-housekeeper roles |
| `eidolon/gen/compile.py` | Emit `accounts` tokens (delete `_statements`); everything else unchanged |
| `eidolon/gen/pipeline.py` | V-0 (accounts resolve, roles vs CaseLog); V-1 P-9 via `accounts.token_intervals`; V-3 per §C.3; V-4 engine-faithful I-39; V-7 real bots; `finalize` iterative boosts + breaker memories; `SealedCase` IO |
| `eidolon/cli.py` | `validate` → `load_sealed_case`; `play` relies on I-51 inside the turn runner |
| `cases/generated/*.json` | Regenerated by `python -m eidolon.gen.golden` (seals change) |
| `docs/EIDOLON-ARCHITECTURE.md` | ADRs in §G, invariants I-49…I-60 |
| `tests/decision/mutation_check.py`, `tests/solve/mutation_check.py` | Re-anchor any Phase 4/5 mutants whose `old` text moves; add the new mutants (§E) |

---

## E. Tests that must be added **before** implementation (red first)

Each test must **fail on today's tree**. Record that failure in the repair report before any production edit.
Tests marked (guard) pass today and must keep passing.

**RB-1** (`tests/solve/test_rb1_accounts.py`)
1. `legit_play_peels_the_murderer_on_every_golden`: real search, real ask of the housekeeper (expressible query), real presentation; asserts `LayerPeel(0→1)` for the murder secret. *Fails today (hk LIEs).*
2. `presenting_an_account_token_is_rejected`: `presented_ref="clean@<hk>"` gives `rejected`, `UNHELD_PRESENTED_REF`, state unchanged, no peel. *Fails today (peels).*
3. `presenting_an_unknown_statement_id_is_rejected`: `"S99999"` and `""` are rejected. *Fails today.*
4. `presenting_evidence_with_unmet_prerequisites_rejects_not_raises`. *Fails today (ValueError).*
5. `no_peel_before_the_account_is_heard` (guard): E_trace presented first gives no peel.
6. `tokens_are_minted_only_by_faithful_delivery`: the same proposition via a cover LIE, via an `InvestigationTold` chain (the detective told the housekeeper), via a distorted memory, and via VAGUE mints nothing. A faithful TRUTH mints exactly `{clean@hk}`.
7. `a_new_session_holds_nothing`: `new_session(pkg)` has an empty ledger, `known_statements` and `known_accounts`, and boosts are applied (`strength_0` equals the boost).
8. `fold_refuses_unbacked_heard_rows`: an `AccountHeard` / `StatementHeard` row naming no ledger statement, the wrong speaker, or an unlisted token raises on replay; replaying a real session reproduces `known_accounts` byte for byte.
9. `one_resolver_four_consumers`: for every golden token, `accounts.atoms_of` equals the atoms `lattice._resolve` hits, `token_interval` is defined, V-3's derived token claims equal the claims a faithful engine delivery commits (proposition + grounding), and P-9 rejects a token whose actor never participated.
10. `presented_delivered_statement_selects_the_authored_response`: presenting `S000k` (which carries `clean@hk`) to the murderer while E_trace is held but not yet presented picks `EvidenceResponse("clean@hk", 0)`.
11. `housekeeper_is_never_the_murderer` (planner, 100 seeds) and `v3_rejects_a_self_account_breaker` (I-60): a fixture with `M == hk` is rejected at V-3. *Fails today (23/96 seal).*
12. `breaker_account_memories_are_boosted_and_undistorted`.

**RB-2** (`tests/solve/test_rb2_engine_faithful.py`, `tests/decision/test_topicality.py`)
1. `greedy_bot_solves_every_golden_on_ledger_credit_only`. *Fails today on manor_wing (3 survivors) once crediting is ledger-only. Write it against `credited_material` with a temporary shim that reads today's ledger.*
2. `a_dead_engine_solves_nothing`: monkeypatch `run_ask_turn` to always reject; greedy and cue-following report `solved=False`. *Fails today (attack 42; kills X15/X16-class).*
3. `credit_ignores_rejected_turns_and_unfaithful_claims`.
4. `v7_rejects_when_a_bot_fails`: stub greedy to fail and `validate()` stops at V-7. *Fails today (X18).*
5. `v7_records_full_scale_and_reduced_scale_cannot_seal`.
6. `witness_answers_truthfully_outside_their_secret_footprint`: for each proof-core atom, the expressible query gives a `TRUTH` committing that atom. *Fails today (LIE).*
7. `secret_footprint_questions_still_get_the_cover` (guard): §29.2 turns 1–2 and the golden walkthrough are unchanged.
8. `protected_interval_knowledge_is_never_spoken_before_concession`: every atom whose observation segment overlaps an unconceded protected interval, asked by every expressible query, is never committed. After a real peel to the concession layer it becomes deliverable.
9. `innocent_confession_terminal_peels_as_concession` (manor_wing_s4 Delphine). *Fails today (STONEWALL).* Plus `murder_confession_gate_unchanged` (guard; M8).
10. `stonewalled_character_answers_non_topical_questions`.
11. `retrieval_picks_highest_score_and_best_matching_belief`.
12. `natural_presence_hint_reaches_the_at_topic`: `predicate_hint="presence"` gives `TRUTH`. *Fails today (VAGUE).*
13. `v4_i39_is_engine_faithful`: replacing the engine with a LIE-only stub makes V-4 fail. *Fails today (the proxy passes).*
14. `bluff_parity_ignores_presuppositions_under_the_new_topicality` (guard): matched pairs give identical acts.
15. `bots_module_reads_no_solver_pool` (AST): `bots.py` does not reference `robust_material`, `obtainable` or `ask_yields`.

**RB-3** (`tests/solve/test_rb3_verifier.py`)
1. `auditor_wrong_murderer_forgery_is_rejected`: omit the framed innocent's alibi constraints and add `Heard(attack, actor=<innocent>)` with `item="NO_SUCH_ITEM"`, on study_party_s4 and manor_wing_s4. *Fails today.*
2. `omniscient_true_constraints_with_fabricated_items_are_rejected` (`item="GOD_MODE"`). *Fails today.*
3. `item_resolving_to_a_different_proposition_is_rejected`.
4. `heard_with_wrong_actor_fails_truth_audit`. *Fails today (X3–X5).*
5. `omitting_a_true_hard_constraint_is_rejected_as_incomplete`. *Fails today.*
6. `lowered_fairness_is_rejected`. *Fails today.*
7. `forged_proof_core_is_rejected`: nonexistent item, non-minimal core, insufficient core. *Fails today.*
8. `forged_robustness_is_rejected`. *Fails today.*
9. `malformed_proofs_never_raise`: Hypothesis over arbitrary JSON values plus the auditor's `{}`, missing keys, string core and string intervals. *Fails today (crash).*
10. `forged_cracked_set_is_rejected`.
11. `survivor_times_and_window_tampering_rejected` (X6, X7).
12. `offstage_relabelled_viable_suspect_is_rejected` (I-59, X1).
13. `nostranger_audit_uses_the_recorded_observer` (N-4, X21).
14. `sealed_bundle_refuses_swap_edit_and_resealed_forgery`: a proof from another package (seal mismatch), an edited proof without reseal (bundle seal), an edited proof with reseal (`verify_proof` fails), and a reduced-scale report (refused).
15. `verifier_imports_nothing_from_the_solver_side` (AST, constants included; N-13).
16. `differential_verifier_equals_solver_hard_set`: semantic cell equality on the 4 goldens. In the study harness (not CI), every sealed seed.

**Mutation additions** (`tests/solve/mutation_check.py`):
- RB-1: minting accepts lies; minting skips the proposition-equality check; I-51 off; fold validation off; V-3 (vi) off; planner allows `M == hk`.
- RB-2: credit from the pool instead of the ledger; credit rejected turns; `v7` always passes (X18); `speakable` always true; the `len(owned)==1` fallback restored; `_lie` ignores covering; murder-only gate widened back to all secrets; boosts not applied in `new_session`.
- RB-3: the auditor's X3–X7 and X21 (re-targeted to the new code), plus: completeness check off; fairness read from the proof; item resolution off; proof_core minimality off; robustness recompute off; bundle-seal check off.

Every one of these must be KILLED.

---

## F. Tests that must pass **after** implementation

1. Everything in §E green. Every listed mutant KILLED. Phase 6 mutation set (66 + new) at 0 survivors. Auditor X1, X3–X7, X15, X16, X18 and X21 killed.
2. Full suite green. The 2194 baseline changes only by added tests plus the explicitly listed rewrites in §H.5. **No assertion in the Phase 3/4/5 regression files (`test_blocking_regressions`, `test_important_regressions`, `test_blocking_repairs`, `test_invariant_mutants`, `test_phase5_readiness`, `test_llm_*_repairs`, the injection corpus) may be weakened.**
3. Phase 4 mutation set re-run: 57 killed / 2 equivalent, re-anchored where the `old` text moved, with each re-anchor listed. Phase 5 set: 70 killed / 1 equivalent.
4. `test_long_conversation` at 2 000 turns / 50 accusations: zero peels, bounded envelope.
5. Full-scale bluff (500 per character) and adversarial bots on all 4 regenerated goldens: no convergence, parity holds, zero peels, zero leaks. Greedy, cue-following and murderer-peel all OK.
6. Seed study 2×50 with the full engine-faithful V-7 and the new verifier, one attempt per seed: **report the funnel honestly**. The yield may drop. A drop is a finding to explain stage by stage. It is never a reason to relax V-7, the verifier, or `N_MAX` / `N_CUE`.
7. Determinism: `PYTHONHASHSEED` ∈ {0, 1, 12345, 777} give identical bundle seals, proofs, bot reports and minted-token sequences.
8. Goldens regenerated and loaded with `load_sealed_case` from disk. `eidolon validate` passes. Regeneration is byte-identical.
9. Spike: 21 passed.

---

## G. Architecture / ADR changes required

| ADR | Content | Sections touched |
|---|---|---|
| **ADR-23 Account identity** | §C.1 / I-49. `Implication.requires` and `Prereq(StatementHeard)` name an `EvidenceId`, a ledger `StatementId`, or an `AccountToken`. `CasePackage.statements` becomes `accounts`. Retires D-2 and closes audit I-7 | §5.1, §10.2, §18.3 st.7, §19.3, §25 |
| **ADR-24 Delivery-only hearing** | I-50 / I-51; `AccountHeard` and `StatementHeard` session events; `DiscoveryState.known_accounts` | §11.2, §11.4, §12.1 st.10, §25 event catalogue |
| **ADR-25 I-21 scope** | I-56: the uniqueness gate is the murder secret's. A non-murder "confession" terminal is a concession terminal. Amends §11.4's pseudocode, which as written gates every secret and contradicts §19.5's premise that "cracking [an excluded innocent] costs nothing" | §10.2, §11.4, I-21 |
| **ADR-26 Topicality and speakability** | I-54 / I-55. Makes §10.3's "covering the asked proposition" operational. Adds the runtime mirror of I-45 | §10.3, §11.5, §12.1 st.6 |
| **ADR-27 Cue vocabulary** | Topics are proposition kinds. `query_cues` canonicalises hints. Retrieval is argmax with a best-matching belief | §8.4, §12.2, §15.4 |
| **ADR-28 Proof as hints, verifier as N-version** | I-57 / I-59. `eidolon.proof/2`. The fairness level is sealed in the package. "Every proof field verified or absent." The voice exclusion is an identity core checked against a truth-audited `Heard.actor` | §19.5 "exclusion chains", Phase 6 brief |
| **ADR-29 Sealed case bundle and engine-faithful V-7** | I-58 / I-52 / I-53. The §19.4 boost obligation moves to `new_session` (named in §30's Phase 7 deliverables). V-4's I-39 check runs the engine | §19.4, §19.7, §26.3, §30 Phase 7 |

The D-1 ADR (`Saw(nobody)`) is **not** part of this pass. The verifier uses the production reading A
unchanged. It is listed in §I.

---

## H. Risks

1. **Seed-study yield will move, possibly a lot.** Engine-faithful V-7 (with full-scale bluff and adversarial runs), the stricter verifier, I-60 and the planner change all reject or reshape cases. The RNG draw for `M` changes, so every golden and every study seed is a different case. Mitigation: report it, find the stage, and fix the *skeleton or planner construction* (I-43). Never reseed past V-5 or V-7, and never relax a gate.
2. **The N-version verifier will disagree with the lattice somewhere.** Granularity shrink/widen, existential windows, corroboration windows and requires-chain minima are subtle. Each disagreement is a real bug in one of the two implementations and needs a written finding. Do not "align" them by copying code. Write the verifier from the spec text.
3. **Verifier and V-7 cost.**
   - The verifier's robustness re-derivation is up to 2^n subsets × candidates × oracle. With ≤1 distortion per witness that is ≤64 subsets.
   - Full-scale bluff and adversarial runs cost about 50–60 s per case (repair report).
   - Expect about 1.5–2 min per case and roughly 1 h for the 2×50 study on 3 workers.
   - Do not reduce the scale to buy speed. Optimisation is Phase 10.
4. **Phase 4/5 behaviour shift.** S1–S7 change which act fires on many turns. Watch:
   - `test_golden_trace_walkthrough` (§29.2);
   - the strategy tests;
   - the Phase 5 injection corpus. Its assertions are containment, and they must hold unchanged; any act-level expectation that moves must be justified in writing as a spec correction, not edited to pass;
   - Phase 4/5 mutation anchors in `turn.py` / `strategy.py` / `peel.py` will move and must be re-anchored and re-run.
5. **A new tell surface.** S3 makes characters DONT_RECALL / EVADE about times inside their *own* secret's footprint. Every character owns a secret (§10.1), so this is not murderer-specific. However, the bluff bot's TELLS set contains EVASION. Re-run convergence at full scale. Parity must still hold because topicality ignores `presupposes`. If convergence appears, it is a real finding.
6. **The honest-answer rate rises.** That raises I-1/leak exposure on more turns. The envelope audit and validator are unchanged. Keep the adversarial and leak suites at full scale.
7. **`known_accounts` consumers.** `decision.hypotheses` iterates `known_statements` and skips unknown ids (safe). Adding committed `StatementId`s to `known_statements` *activates* hypothesis evaluation over heard testimony, which was previously dead because the set was always empty. `cli.encountered()` reads only locations, items and evidence (safe). Tokens and `Statement.accounts` must never reach the envelope, digest, `player_view` or notebook. Add a test.
8. **Two admissibility functions remain** (`decision.admissibility` for V-3/runtime weight, `solve.lattice` for V-5). I-27 says "one function shared". That divergence predates this pass, and RB-1 only needs V-3 ⇔ runtime parity (both use `decision`). Record it as an open IMPORTANT item, not as fixed.
9. **I-10 half-measure.** Requiring evidence to be held before presentation is deferred, because Phase 4 fixtures present undiscovered items. Until it is fixed, a player can "discover by presenting" an item whose prerequisites are met.
10. **`Statement.accounts` replay compatibility.** It is an additive field with a default, but the Phase 7 schema must include it from day one.
11. **Hard difficulty** (2 distortions per witness, up to 8 witnesses) can exceed the 2^10 robustness bound and fail closed. v1 ships easy and standard only.

---

## I. Things that must NOT be changed

1. **I-3 / I-16 / I-29 / I-33 / I-38.** Peel, slip and confession read only the presented set, unlocked material and static personality. The peel runs for **every** secret on **every** turn. Topicality (S1) chooses plan *content*, never whether a cover moves.
2. **I-21 for the murder secret.** The gate stays closed without a checker (M8). A confession is never cheaper than a proof.
3. **I-25 / I-27 poisoning.** A detective-told chain never mints a token, never enters a breaker set and is never admissible.
4. **I-45 semantics in the solver.** The murderer is never cracked. Runtime parity is added, and the solver rule is not loosened.
5. **The solver never reads** `pkg.accounts`, `pkg.solution` (except `judge`), `load_bearing`, `structure`, `memory_boosts` or personalities. The planner and compiler never read a verdict. `finalize`'s existing §19.4 proof-core boost is the only sanctioned generation→solver read, and V-3 / I-60 use no solver.
6. **Verifier independence.** No import from `solver`, `lattice`, `distort`, `fairness` or `bots`, constants included. The verifier never reads `pkg.solution`.
7. **No seeding.** No constructor, loader, fixture helper, CLI or bot may write the ledger, `known_statements` or `known_accounts` outside a committed turn. Pre-authored accounts are never ledger rows.
8. **Acceptance numbers.** `N_BLUFF = 500` and `N_ADVERSARIAL = 500` per character, `N_MAX`, `N_CUE`, the §20.2 bands as a gate, the 20-attempt loop, I-43's no-reseed-past-V-5 rule, and the 2 000-turn / 50-accusation long-conversation scale.
9. **Phase 1 semantics.** `FactIndex._tv_Saw` (D-1 reading A), `derive_perception` and the `_tv_*` family are unchanged. D-1 needs its own ADR.
10. **Phase 2 memory model.** `score`, `RETRIEVE_STRONG = 0.55`, `RETRIEVE_WEAK`, decay and distortion assignment are unchanged. Generation raises `strength_0` through boosts, as §19.4 says.
11. **Phase 5 boundary.** The parser schema, the injection-corpus `flagged` declarations (do not widen marker regexes), F-1 claim order, `NameBook` allow-lists, `repair_feedback`'s signature, the envelope audit and I-1 containment.
12. **Envelope parity (I-18 / I-42) and bluff parity (§6.5).** Topicality and speakability never read `presupposes` or premise truth.
13. **Determinism (I-5 / I-6).** No `random` outside `gen/`. Hash tie-breaks only. Minting and crediting are pure functions of committed state.
14. **Existing regression tests.** No assertion is weakened. The rewrites in §H.5 and below are fixture migrations that preserve the guarded property:
    - `tests/solve/test_blocker_repairs.py::test_B1_bots_never_hand_a_bot_material_a_suspect_would_withhold` and `::test_B1_a_question_that_names_nothing_yields_nothing` guard R7 / R9 through `ask_yields`. They are replaced by ledger-credit equivalents (§E RB-2 #3, #8) that kill R7 / R9 re-targeted. They are not deleted until the replacements kill them.
    - `tests/decision/test_blocking_repairs.py::test_b2_i33_newly_unlocked_implication_peels_on_an_off_topic_turn` fabricates `StatementHeardEvent("S_note")` with no ledger statement. Under I-50 that row is illegal. The test must obtain `S_note` through a committed turn. Its I-33 assertion is unchanged.
15. **Out of scope and left open:** D-1, I-2 beyond the verifier/V-0 label check, I-4 boost *validation* at V-0, I-5 realised structure, I-6 Personality, I-8 `vance_v03`, I-10's "held evidence" half, N-1…N-13 except N-4 / N-12 / N-13, which close as side effects of RB-3.

---

## Verdict

**READY FOR SONNET IMPLEMENTATION**, under three conditions:
- ADR-23…29 are accepted before the first production edit.
- The §E tests are committed red first, with their failures recorded.
- The implementation is sequenced RB-3 (verifier + bundle; self-contained) → RB-1 (identity + delivery) → RB-2 (strategy + bots + V-7), because RB-2's acceptance depends on RB-1's minting and on the verifier being trustworthy.

No blocker may be reported fixed on the strength of a pre-existing green test. Each one closes only when its §E tests and mutants pass and the §F.6 study has been re-run and reported.
