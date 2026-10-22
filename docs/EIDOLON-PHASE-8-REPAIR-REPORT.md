# EIDOLON — Phase 8 targeted repair report (H8-B1, H8-I1, H8-I2, H8-I3)

Date: 2026-10-21. Author's record of the repair — **not** an independent review. Phase 9 was not started. Nothing was committed (the
repository has no VCS).
Contract: the independent hostile review `docs/EIDOLON-PHASE-8-HOSTILE-REVIEW.md` (verdict NOT ACCEPTED — REQUIRED FIXES; §1, §2 for
the findings, §6 for the acceptance list, §7 for the oracle follow-up), `docs/EIDOLON-ARCHITECTURE.md` §5.2, §13.2, §16.1, §22.2, §26.2,
§30, `docs/EIDOLON-PHASE-8-IMPLEMENTATION-REPORT.md`, `docs/EIDOLON-KNOWN-DEBT.md`.

## Verdict

`PHASE 8 REPAIRED — READY FOR INDEPENDENT RE-REVIEW`

H8-B1, H8-I1, H8-I2 and H8-I3 are repaired: each original reproduction now fails to reproduce (sections 2-5), each has failing-first regression tests (40 of 48 selected new tests fail on the pristine
source; the 8 that pass are control rows), and each guard has a mutant that the tests kill (the whole `P8-`/`F1a-` set, 46 existing + 26 new: 72 killed, 0 survived). `tests/test_phase8.py` 147/147,
`tests/test_persistence.py` 315/315, `tests/solve tests/gen` 349 passed + 1 strict xfail, the full suite 2833 passed + 1 xfailed, all exit 0. The four sealed bundles revalidate stage by stage (including V-7 at full scale) and
no seal, proof or generation file changed. **This is the author's record, not an acceptance.** Phase 8 is not declared accepted, the review's NON-BLOCKING findings (H8-N1..N9, H8-X2, H8-N10) are open, seven new NON-BLOCKING items
were found while repairing (section 11), and several things are unmeasured (section 11). Phase 9 was not started. Nothing was committed.

Evidence labels used below. **Fresh** = run in this session on the tree named, with the command and exit status shown.
**Inherited** = taken from the hostile review or an earlier report and not re-run here. **Unmeasured** = not run, nothing claimed.

## 1. Object, method, baseline

| | |
|---|---|
| Tree before | manifest `fb6efde63b921e7e70490315053139793178c4089efe783f0311ea0bc3831262` (184 `.py` files under `eidolon/` and `tests/`, sha256 over sorted `path sha256` lines + trailing newline — the hostile review's recipe). It is **byte-identical to the review's follow-up tree** (§7.1 "Today's tree": the same manifest), so every reproduction in the review applies to it. |
| Tree after | **Final** manifest `282cc2662679aaf4a32c211e0ad7232181540be3885508d87b72a612d19da097` (184 files). The long runs used frozen byte-identical copies (manifest re-checked per copy): **T1** `ef1bdac90ebb8ad2fb4f3481266210477da650d1f59c49ed33321333bd2b0aef`, which differs from Final in `tests/test_phase8.py` only (section 8). |
| Not touched | `eidolon/store.py` (`333a3df8f1d853b4`, as in the review), `eidolon/solve/**`, `eidolon/gen/**`, `eidolon/world/**`, `eidolon/minds/**`, `eidolon/llm/**`, `cases/generated/*.json` (sha256 first 16: `manor_wing_s4 f762df353e8db19e`, `manor_wing_s6 b749d3a0cc731c59`, `study_party_s4 fbfa9c1c21bd725c`, `study_party_s5 1a51e427b8fa0cb7`, unchanged), `eidolon/solve/oracle.py` (`dd7a578955b316e3`, the H8-X1 repair is preserved byte for byte). `diff -rq` against a pristine copy lists exactly the seven production files in §6. |
| Baseline before edits | a pristine copy of the pre-edit tree: `tests/test_phase8.py` **106 passed in 313.77 s, exit 0** (fresh); `tests/decision/test_hypotheses.py tests/decision/test_exploration.py tests/solve/test_oracle.py tests/evidence/test_discovery.py` **35 passed in 2.72 s** (fresh). |
| Order | B1, then I1, I2, I3 — the review's order (§6), and the dependency order: B1 changes `hypotheses.py`/`game.py` (projection), I1 `exploration.py`/`turn.py` (what a refused search says), I2 `web.py`/`cli.py` (the request boundary), I3 `game._commit`/`web.Games` (the writer). I3 sits last because it rests on the request boundary I2 fixes (an attacker's spellings multiplied by a rebound page). |
| Method per finding | reproduce the review's attack on the current tree → failing-first test (run on the pristine source: **40 of the 48 selected new/updated tests fail there**; the 8 that pass are control rows, section 8) → smallest repair → rerun the attack → neighbouring valid behaviour → mutant → document. |

## 2. H8-B1 — the player reasons over unlocked implications only

**Root cause.** §5.2: the player sees "implications they have **unlocked**". Phase 3's `unlocked_implications` /
`project_for_player` do that. The Phase 8 board did not use them: `decision/hypotheses.py` (`_evaluate_plain_proposition`,
`_evaluate_lied`, `_evaluate_planted`) and `game._tensions` iterated `Evidence.implications`, locked ones included, and
`game.notebook` took the forms' object vocabulary from `solve.bots.held_names`, which does the same. In every sealed case the
weapon print's only implication is locked behind the housekeeper's cleaning account and names the murderer.

**Repair** (smallest change at the one place all readers route through):
- `evidence/discovery.py`: `held_material(state)` = `known_evidence | known_statements | known_accounts` (the set `weight.py` unlocks against)
  and `unlocked_view(evidence, state)` = the item with only its unlocked implications (8 lines, no behaviour change to
  existing functions).
- `decision/hypotheses.py`: the plain and `Lied` evaluators iterate `unlocked_implications(ev, held_material(d))`; the `Planted`
  evaluator compares `unlocked_view(target)` with `unlocked_view(other)`. The plain evaluator applies §13.2's floor through
  `evidence_implication_contradicts`: a contradiction weaker than `strength 0.5` is **neither** against nor support (it used to be
  reported as support).
- `game.py`: `_tensions` builds `found` from `unlocked_view`s (one filter serving both evidence paths: claim-against-implication and
  evidence-against-evidence); `player_objects(state)` (new) replaces `held_names(...).objects` for the notebook's weapon / search
  vocabulary and reads the unlocked view. **`held_names` itself is unchanged** (the V-7 bots' function; changing it changes what seals).
- Replay is unaffected, as the review said: `HypothesisChanged` rows store the commit-time evaluation and the fold applies them as
  recorded (I-22); the notebook re-evaluates live. Checked (fresh), §10.

**Attack, before and after** (`r_b1_all_cases.py`, the review's script with its `p8h` preamble, outputs verbatim):

```
before  study_party_s4: … tied to 'item 2: fingerprint (a crystal decanter)': ['David']; proven murderer: David     (s5 Robert, manor_wing_s4 Delphine, _s6 Cormac likewise)
after   study_party_s4: … tied to 'item 2: fingerprint (a crystal decanter)': []; proven murderer: David           (all four cases: [])
```

The tension channel and the `Lied` channel (`r_b1_locked_implication.py`): before, `TENSIONS: ['statement 9 (David) and item 4: fingerprint … do not sit together.']`
and `David lied in statement 9 … corroborated; consistent with item 4: fingerprint`; after, `TENSIONS: []` and `… — 50% — open`.

**Tests** (`tests/test_phase8.py` §H8-B1, `tests/decision/test_hypotheses.py`). Failing first on the pristine source; passing on the repaired tree:
- `test_H8_B1_a_locked_implication_reaches_no_theory_and_no_tension_until_its_account_is_heard[×4 sealed cases]` — find the scene, dust the
  weapon, hear everyone but the housekeeper; file an `At` theory per character at the print's own place and at a place no held item names, a
  `Lied` theory on every statement by the murderer, a `Planted` theory on every held item: nothing in any support/against list and no
  tension names the print. Then hear the housekeeper: the print **is** tied (the murderer's quiet-place theory, and not another suspect's) —
  the filter is the unlock, not a ban.
- `test_H8_B1_the_rendered_game_page_ties_the_print_to_no_one_before_its_account_is_heard[×4]` — the same through HTTP, reading the rendered
  theory list and tension list.
- `test_H8_B1_a_tension_between_two_held_items_rests_on_unlocked_implications_only` (synthetic pair: tension only after the account is heard).
- `test_H8_B1_the_form_vocabulary_names_no_object_only_a_locked_implication_mentions` (the bot-side reading sees the object, the player's does not;
  once unlocked it is the player's).
- Unit tests: `…locked_implication_is_neither_for_nor_against_a_plain_theory_until_its_requirement_is_held` (unlock by an account, a statement and
  an evidence id), `…contradiction_weaker_than_half…` (0.49 → open, 0.5 → contradicted, agreement needs no floor),
  `…lied_theory_is_not_corroborated_by_a_locked_implication`, `…planted_theory_is_not_corroborated…` (all four locked/planted combinations).

**Mutants** (harness `tests/persistence_mutation_check.py`, 11 new `P8-B1-*`): plain / `Lied` / `Planted`-target / `Planted`-other evaluators read locked
implications; the §13.2 floor dropped; accounts do not unlock; `unlocked_view` returns the whole item; `_tensions` items unfiltered (both paths);
claim-against-implication reads raw; evidence-against-evidence reads raw; the form vocabulary reads locked implications. All 11 killed in the full run (below), each by the test written for it.
One mutant (`P8-B1-planted-target-not-unlocked`) **survived the first run**: my first `Planted` test never made the *planted* item the locked
one. The test was strengthened (all four combinations) and the mutant is now killed — recorded here because it is evidence the harness checks the tests.

## 3. H8-I1 — a search hint names nothing the player has not seen

**Root cause.** `decision/exploration._hint` formatted `{ref}` with the raw prerequisite ref, so a refused search printed
"You would need to find E_pin_clean first." (and the same for statements, kits and places).

**Repair.** `_hint(prereqs, case)`: `EvidenceFound` → "Something else would have to turn up first."; `StatementHeard` → "Someone would have to tell you
something first."; `KnowsAbout` / `HasItem` → the place's / object's **display name** from the case, or a generic line when the case does not name
the ref ("You need something you do not have yet for that."). `search(..., case=None)` takes the case; `run_search_turn` passes `state.case`.

**Attack, before and after** (`r_i1_hint_ids.py`):

```
before  manor_wing_s4, look round the terrace -> | Look: the terrace | | You would need to find E_pin_clean first. |    _leaks(): ['E_pin_clean']
        study_party_s4, ask David, dust the decanter -> … You would need to find E_scene first. …                      _leaks(): ['E_scene']
after   manor_wing_s4, look round the terrace -> | Look: the terrace | | Something else would have to turn up first. |  _leaks(): []
        study_party_s4, ask David, dust the decanter -> … Something else would have to turn up first. …                _leaks(): []
```

**Tests.** `test_H8_I1_no_search_hint_in_any_sealed_case_names_an_engine_id[×4]` (every place and object × every method from a blank save, hint text vs every
evidence / statement / account / prerequisite id); `test_H8_I1_no_page_of_a_search_sweep_leaks_an_identifier[×4]` (the review's `_leaks()` predicate on every
page of a two-round search sweep through HTTP; in every case the sweep reads at least one gated hint); `…a_denial_that_puts_the_weapon_on_the_list_does_not_name_the_scene_either`
(the second reproduction); `…the_search_runner_hands_the_case_to_the_hint`; and in `tests/decision/test_exploration.py` the display-name behaviour for each prerequisite kind.
One existing Phase 4 test pinned the leak (`test_search_without_kit_yields_hint_not_discovery` asserted that the raw ref `kit` appears in the hint): it now
asserts the generic line, with the reason in a comment. That test and the base-URL fixtures of section 4 are the only edits to existing tests.
**Mutants** (6 `P8-I1-*`): the hint prints the evidence id / statement id / kit ref / place ref; ignores the display name; the runner forgets the case. All 6 killed, on T1 and again on Final.

## 4. H8-I2 — the Host header is the allow-list

**Root cause.** `web._same_origin` accepted a POST when `Origin`'s host:port equalled the request's own `Host`; nothing judged `Host`. A DNS-rebound page
sends `Host: attacker.example:8123` and an `Origin` equal to it.

**Repair.** `web.allowed_hosts(port)` = `{127.0.0.1, localhost, [::1]}` × the served port (the bare names only on port 80). A pure-ASGI middleware
`_LoopbackOnly` answers **400 "Invalid host header"** to every HTTP request — any route, GET or POST — whose lower-cased `Host` is not in that set, before a route runs.
`_same_origin` now requires `Origin` to be one of the matching `http://<allowed host>` origins (stored on `app.state.origins`), never "whatever `Host` says".
`create_app(..., port=8000)` takes the port and `eidolon serve` passes `--port`. No new dependency.

**Attack, before and after** (`r_i2_rebinding.py`, TestClient with `base_url=http://attacker.example:8123`; plus a live `uvicorn` process, below):

```
before  POST /new from the attacker's page: 303 /g/victim | GET / readable: True | POST final accusation: 200 … The case is closed. | on disk: ['TurnCommitted','Accusation','CaseSolved']
after   POST /new from the attacker's page: 400 None      | GET / readable: False 400 | on disk: no save
```

**Live server check (fresh).** `eidolon serve --port 8791` (real uvicorn, then stopped), `curl`:
`GET /` 127.0.0.1:8791 → 200, `localhost:8791` → 200; `Host: attacker.example:8791` → **400 Invalid host header**; `Host: 127.0.0.1:8000` (wrong port) → **400**; `POST /new` with
the rebound Host **and** a matching Origin → **400**; real Host with `Origin: http://evil.example` → **403**; real Host with its own Origin → 303 to `/g/victim`;
`GET /g/Victim` → 404, `GET /g/victim` → 200; `GET /g/victim` with the rebound Host → 400. No save was created by any refused request.

**Tests.** `test_H8_I2_a_rebound_host_is_refused_on_every_route_even_with_a_matching_origin` (index, game page, report, unknown game, unknown path, `POST /new`, final
accusation — all 400, nothing created, the victim's game still at turn 0); `test_H8_I2_the_allow_list_is_the_loopback_names_on_the_served_port[×16]` (accepted: the three loopback
names, upper-case, an Origin that is another loopback name of the same port; refused: wrong port, no port, `localhost.evil.example`, `127.0.0.1.evil.example`, `0.0.0.0`, an Origin on another local port, an Origin with a
trailing `.evil.example`, `Origin: null`, `https://`, a foreign origin); `…default_port_may_be_left_out…`; and `test_the_cli_serves_the_player_app_on_localhost_only` now also checks the served port
is the allowed one. All existing web tests talk to the app at `http://127.0.0.1:8000` (the Host a browser sends); that fixture change is the only edit to them.
**Mutants** (6 `P8-I2-*` plus the existing `P8-web-cross-site-post-accepted`, whose anchor moved with the code): Host unchecked; Origin compared with Host again; any port accepted; the bare host accepted; Host compared
case-sensitively; `serve` ignores its port. All 7 killed (full run below).

## 5. H8-I3 — one save, one writer; the store has the last word

**Root cause.** Two faults. (1) `web.Games` keyed its cache by the URL's spelling of the name; NTFS maps `/g/G1` onto `g1.db`, so two spellings were two `Save`s on one file (two heads, two
action ledgers, two rate windows, and a verifying open per spelling on a GET). (2) `game._commit` decided "duplicate" only from the in-memory `turn_for` and discarded the `AppendResult`
(`appended`, `same_events`) that `Save.append` returns, so a form the store had already recorded was answered with a freshly computed reply from a stale state.

**Repair.**
- `Games.open(name)` opens a save only under the spelling it has on disk (`name in self.saves()`; the review allowed "refuse a name whose on-disk spelling differs"). A second spelling is a 404 with no `Save`
  opened — which also removes the per-spelling cost of a GET (the `r_i3_gets.py` figures below) and makes `Chat.times`' `str(save.path)` key unique per file.
- `_commit` honours the result: `appended=False` is a duplicate; `same_events=True` → "Already recorded as turn n …" with that turn, `same_events=False` (a different action under a reused id) → the stale outcome. The runner's reply
  is never shown on that path. The two messages are shared helpers (`_already`, `_STALE`).

**Attack, before and after** (`r_i3_alias.py`, `r_i3_gets.py`):

```
before  cached: ['G1','g1'] same file: True | B: Turn 0 … Robert: I was in the kitchen … | B after the verdict: Turn 0 · The investigation is open … Margaret: … | on disk: turns 2, speakers ['Elena']
        RATE_LIMIT 30/window; parse calls made inside one window for one save: 240 | 8 GETs of spellings: 20.2 s, Saves cached: 8   (the last figure is the review's measurement; the rest of the 'before' lines were re-run here)
after   GET /g/G1 status: 404 | cached: ['g1'] | on disk: turns 2, speakers ['Elena'] | parse calls inside one window: 30 | 8 GETs: [200, 404×7] in 1.6 s, Saves cached: 1
```

**Tests.** `test_H8_I3_a_second_spelling_of_a_game_is_not_a_second_writer` (the page, the report and a POST on the other spelling are 404, no in-world text, no second `Save`, nothing recorded — before and after the verdict);
`test_H8_I3_one_rate_window_per_save_whatever_its_spelling` (8 spellings × 31 typed lines → exactly `RATE_LIMIT` parse calls; it was 240);
`test_H8_I3_a_duplicate_the_store_detects_but_this_save_missed_shows_no_new_reply` (two writable handles on one file: the re-sent form is a `duplicate` with the committed turn and no reply; a different action under the reused id is `stale`; a new
id at the old head is `stale`; after the verdict both handles show nothing; the file is unchanged by the second handle).
Neighbouring behaviour kept: `test_a_double_post_commits_once_and_a_second_tab_commits_nothing_I14`, `test_a_retried_action_returns_its_committed_turn_and_a_stale_page_commits_nothing` (unchanged, passing).
**Mutants** (3 `P8-I3-*`): another spelling opens a second `Save`; `_commit` ignores the append result; a different action under a reused id reads as a duplicate. All 3 killed (full run below).
The spelling mutant is distinguishable only on a case-insensitive file system (this machine's NTFS); on a case-sensitive one `G1.db` never exists and the test holds trivially (stated in its docstring).

## 6. Files changed

| File | +/- | Why |
|---|---|---|
| `eidolon/evidence/discovery.py` | +8 | `held_material`, `unlocked_view` (B1) |
| `eidolon/decision/hypotheses.py` | +13 −8 | the three evaluators read unlocked implications; §13.2 floor (B1) |
| `eidolon/game.py` | +31 −11 | `_tensions` unlocked view; `player_objects`; `_commit` honours `AppendResult` (B1, I3) |
| `eidolon/decision/exploration.py` | +16 −11 | `_hint` names no engine id; `search(…, case)` (I1) |
| `eidolon/decision/turn.py` | +1 −1 | `run_search_turn` passes `state.case` (I1) |
| `eidolon/web.py` | +35 −7 | `allowed_hosts`, `_LoopbackOnly`, `Origin` allow-list, `create_app(port=)`, `Games.open` by on-disk spelling (I2, I3) |
| `eidolon/cli.py` | +1 −1 | `serve` passes its port (I2) |
| `tests/test_phase8.py` | 106 → 147 tests | +10 B1, +10 I1, +18 I2, +3 I3; fixtures talk to `127.0.0.1:8000`; `_new_game(case=)`, `last_action` helpers |
| `tests/decision/test_hypotheses.py` | 4 new | B1 unit tests |
| `tests/decision/test_exploration.py` | 1 new, 1 updated | I1 |
| `tests/solve/test_oracle.py` | 2 new | the oracle witnesses of §7 |
| `tests/persistence_mutation_check.py` | 171 → 197 mutants | 26 new mutants; the cross-site mutant's anchor follows the code |

## 7. The oracle follow-up (H8-X1) — preserved; the two residuals are not claimed solved

`eidolon/solve/oracle.py` is byte-identical (`dd7a578955b316e3`) and `test_tail_cannot_stay_put_on_a_blocked_tick` is untouched and passing. Classification of the review's two NON-BLOCKING residuals is **unchanged**:
- **H8-X2** (a room with no exit: the DP says infeasible, the oracle and brute force still drift out) — **open, NON-BLOCKING, latent** (no generated case has such a room). A deterministic witness was added as a
  **strict `xfail`** (`test_known_divergence_a_room_with_no_exit_cannot_be_left`; I checked it diverges as documented: DP `False`, oracle `True`, brute force `True`). It fails the suite the day someone fixes the oracle without removing the marker.
- **H8-N10** (TK3, an under-approximating variant of the fix, survived every deterministic test) — the deterministic test the review proposed was added
  (`test_a_walk_may_drift_in_transit_straight_after_its_last_visit`) and **kills TK3** (checked on a scratch copy with the mutation applied: 1 failed). **Still open:** no TK1/TK3 entry was added to the Phase 6 harness `tests/solve/mutation_check.py`
  (its run takes hours), and the random property test is not derandomised. Classification stays NON-BLOCKING.

## 8. Results

**Trees.** *Pristine* = the pre-edit tree, manifest `fb6efde6...` (also the review's follow-up tree). *T1* = the repaired tree frozen first, manifest `ef1bdac90ebb8ad2fb4f3481266210477da650d1f59c49ed33321333bd2b0aef`.
*Final* (= T2 = the working tree) = `282cc2662679aaf4a32c211e0ad7232181540be3885508d87b72a612d19da097`. **T1 and Final differ in exactly one file, `tests/test_phase8.py`** (I strengthened the I1 page sweep to every place and every object, offered or crafted, after T1 was frozen;
`diff -rq` confirms). The full suite, `tests/solve tests/gen` and `tests/test_persistence.py` ran on T1; `tests/test_phase8.py` and the I1 mutants ran again on Final. Frozen copies were used so the working tree could be edited while the hour-long runs went on.

**Fresh runs (this session; exit status is the process's own).**

| Run | Command (from the tree's root; `PYTHONDONTWRITEBYTECODE=1 python -B -m ... -p no:cacheprovider`) | Tree | Result | Exit |
|---|---|---|---|---|
| Baseline, Phase 8 | `pytest tests/test_phase8.py -q` | Pristine | 106 passed, 313.77 s | 0 |
| Baseline, small focused | `pytest tests/decision/test_hypotheses.py tests/decision/test_exploration.py tests/solve/test_oracle.py tests/evidence/test_discovery.py -q` | Pristine | 35 passed, 2.72 s | 0 |
| **Failing-first**: every new/updated test run against the pristine source (the final test files copied over it) | `pytest tests/test_phase8.py tests/decision/test_exploration.py tests/decision/test_hypotheses.py -k "H8_ or cli_serves or without_kit or display_name or weaker or locked or planted_theory"` | Pristine source | **40 failed, 8 passed** of 48 selected, 312.07 s. The 8 that pass are `H8_I2` matrix rows that were already right before the repair: the loopback names with no Origin (4) and the foreign-Origin 403 rows (4) - the controls | expected non-zero |
| Phase 8 | `pytest tests/test_phase8.py -q` | Final | **147 passed**, 1 warning, 1006.21 s (0:16:46) | **0** |
| Persistence | `pytest tests/test_persistence.py -q` | T1 | **315 passed**, 1262.66 s (0:21:02) | **0** |
| Solve + gen | `pytest tests/solve tests/gen -q` | T1 | **349 passed, 1 xfailed** (the strict H8-X2 witness), 2733.15 s (0:45:33) | **0** |
| **Full suite** | `pytest -q` | T1 | **2833 passed, 1 xfailed, 1 warning**, 3963.86 s (1:06:03); 2834 collected | **0** |
| Persistence mutation set, the 26 new mutants + the changed cross-site one | `python -m tests.persistence_mutation_check -j 4 -k "P8-B1,P8-I1,P8-I2,P8-I3,P8-web-cross-site"` | T1 | baseline green; **27 killed, 0 survived**, 0 malformed, 0 infrastructure errors, 8 justified equivalent | 0 |
| I1 mutants again, against the strengthened sweep | `... -j 3 -k "P8-I1"` | Final | baseline green; **6 killed, 0 survived** | 0 |
| **WHOLE `P8-` + `F1a-` set** (the 46 existing Phase 8 mutants + the new ones) | `... -j 6 -k "P8-,F1a-"` | Final | baseline green; **72 killed** (46 existing + 26 new), **0 survived**, 0 malformed, 0 infrastructure errors, 8 justified equivalent | **0** |
| Phase 4 decision mutation harness | `python -m tests.decision.mutation_check` | Final copy | `MUTATION VERIFICATION: PASS` - 57 killed, 2 justified equivalent (M2, M4), as `CLAUDE.md` states | 0 |
| Bundle revalidation (4 bundles) | `revalidate.py` = `load_sealed_case` + `gen.pipeline.validate` | Final (gen/solve/oracle byte-identical to pristine) | all 4 ok, section 10 | 0 |
| Random page-valid play + invariants | `fuzz2.py <case> 600 2`, four cases; pristine control | Final / Pristine | section 9 | 0 |
| Cross-version replay | `xver.py make` on Pristine, `open` on Final and Pristine | both | same state hash `7f10e88c...`, section 10 | 0 |
| Live server | `eidolon serve --port 8791` + `curl` | Final | section 4 | - |
| Notebook render cost (H8-N7 unchanged?) | `r_n7.py`, 168 held statements, best of 3, machine loaded | Pristine / Final | 0 theories 41 ms / 47 ms; 100 theories 1555 ms / 1588 ms - no regression | 0 |

An earlier mutation run (only the B1 mutants, before the `Planted` test was strengthened) ended 10 killed / **1 survived** (section 2); the survivor's test was repaired and the table lists the runs that stand.

**Inherited, not re-run (from the hostile review or earlier reports):** the review's full-suite run on the pre-repair tree (2786 passed, exit 0, 3924 s); the Phase 7 mutation set (125 killed / 5 equivalent) and `P8-`/`F1a-` figures in the author's report (the whole set *was* re-run here, line above); the oracle differential and seed-study trace (review sections 7.2, 7.5); the `EIDOLON_LONG=1` 1000/2000-turn sessions; the Phase 6 harness (102 mutants); `spike/`; the Phase 5 mutation set (`tests.decision.mutation_check phase5`).
The repository's `.hypothesis/` directory was touched by runs started from the repository root (its `constants` cache; its `examples` directory holds 3 files); every long run used a copy.


## 9. Browser and projection security results

All fresh unless marked. "Rendered" means the HTML a browser would receive, read with the review's own `_leaks()` predicate (engine-only words and every
evidence / secret / knowledge / memory / belief / account id), not an internal projection object.

| Property | How it was checked | Result |
|---|---|---|
| No hidden truth in pages, before the verdict | `test_no_projection_serializes_an_engine_only_field_or_identifier` (existing); H8-B1 and H8-I1 tests through HTTP (4 sealed cases each); `fuzz2.py` below | no leak |
| No hidden truth in pages and JSON after the verdict | the same existing test reads `/g/case` and `/g/case/report` and `json.dumps(game.report)` after the verdict; `fuzz2.py` ends every run with a final accusation and `_leaks(json.dumps(report))` | no leak |
| Undiscovered evidence ids | I1 sweep: every place and object x every method, twice round, page by page, per case; the denial path that offers the weapon before the scene is found | none (was `E_pin_clean`, `E_scene`) |
| Locked implications | B1 tests; `fuzz2.py` invariant "no item all of whose implications are locked appears in any theory's support/against or any tension", checked after **every** action | none |
| `fuzz2.py` (random page-valid play: ask incl. presentations and provisional accusations, search, goto, theory, withdraw; the review's `fuzz.py` plus the two invariants and a per-step `_leaks` on the notebook JSON and the last-action text) | 600 actions x 4 sealed cases, seed 2, then a page-built final accusation; live state == folded state every 60 actions | **0 fold refusals of a page-valid form, 0 exceptions, 0 invariant violations, 0 post-verdict report leaks**, all four cases, exit 0. Control: the same script on the **pristine** tree (`study_party_s4`, 400 actions) reports `leak ['E_scene']` at actions 30, 236 and 262, so it can see the defect |
| Crafted form fields | existing `test_a_crafted_form_is_refused_at_the_boundary_and_records_nothing` (18 forms); every form field still goes through `_one_of` / held-ref checks | refused, nothing recorded |
| Path traversal, reserved and unsafe names, cases outside the library | existing `...hostile_game_name...` (`../x`, `a/b`, `con.db`, 80 characters, empty), `...only_a_library_case...`; the on-disk-spelling rule of H8-I3 | refused (400/404) |
| CSRF | existing cross-site POST test (403, nothing recorded) with the fixture now at `127.0.0.1:8000`; the 16-row Host/Origin matrix (H8-I2); live `curl` | holds; DNS rebinding now refused (400) |
| Duplicate submission and conflicting tabs | existing double-post / second-tab test; the new two-handle test (duplicate -> committed turn, different action under a reused id -> stale, after the verdict nothing); the second-spelling tab | nothing double-commits, no unrecorded reply is shown |
| Tampered saves | existing `...tampered_save_gets_a_refusal_page...` (409, no engine detail) | holds |
| Free text through a scripted transport | the 7 existing free-text tests + `...one_rate_window_per_save_whatever_its_spelling` | holds; 31 typed lines x 8 spellings -> 30 parse calls |
| Error and fallback paths | refusal pages are constants (`Invalid host header`, `Forbidden`, `Not Found`, the 409 text); a rejected / stale / duplicate outcome carries no in-world reply (asserted in the I3 tests) | no engine data |

Not changed and still open (NON-BLOCKING, section 11): a multipart file part where a string is expected still gives a 500 (H8-N4); no anti-framing header (H8-N5); a typed line is parsed before the duplicate/stale/closed checks (H8-N2).


## 10. Seals, proofs and case generation

- **Bundles unchanged.** `cases/` is identical to the pristine copy (`diff -rq`); file hashes (first 16 hex) `manor_wing_s4 f762df353e8db19e`, `manor_wing_s6 b749d3a0cc731c59`, `study_party_s4 fbfa9c1c21bd725c`, `study_party_s5 1a51e427b8fa0cb7`.
- **Fresh revalidation of all four, on the repaired tree** (`revalidate.py`: `load_sealed_case` = every seal + the independent proof verifier + declared murderer == proven survivor + the full-scale report, then `gen.pipeline.validate` = the stages including V-7 at full scale; the same as `eidolon validate`). All four: `proof.unique = true`, `validate_ok = true`, no problems.

| Bundle | package seal | survivors = declared murderer | `load_sealed_case` | `validate()` |
|---|---|---|---|---|
| manor_wing_s4 | `9ea995b0662e6ae6` | Delphine | 5.1 s | ok, 163.5 s |
| manor_wing_s6 | `604f720bb383ad51` | Cormac | 5.2 s | ok, 153.3 s |
| study_party_s4 | `00b709d689b3cea0` | David | 2.7 s | ok, 107.8 s |
| study_party_s5 | `88070a4e2a358b28` | Robert | 3.1 s | ok, 109.7 s |

  The seals and survivors equal the review's section 7.4 figures; the review listed V-7/`validate()` as **unmeasured** - it is measured here.
- **Seals, proofs and generation outcomes did not change, and cannot have by this repair.** No file under `eidolon/gen/`, `eidolon/solve/`, `eidolon/world/` or `eidolon/minds/` changed (`diff -rq` against the pristine copy;
  `solve/oracle.py` is byte-identical, so the H8-X1 repair and `test_tail_cannot_stay_put_on_a_blocked_tick` are preserved). The 2x50 seed study was **not** re-run: nothing it exercises changed. Its last measurement is the review's section 7.5
  (99/100 sealed; 4,037 verifier oracle queries, 0 disagreements between the repaired oracle, the pre-fix oracle and the DP) - inherited, and this repair does not move it. The shared pieces this repair touched (`evidence/discovery.py` gained two
  functions and changed none; `decision/turn.py` passes one more argument) are exercised by the four `validate()` runs and the full suite.
- **Old saves.** A save written by the **pre-repair** engine (`xver.py`: a `study_party_s4` game with the throw-away theories, the denial and the `Lied` theory, whose stored `HypothesisChanged` rows still carry the leaking evaluation, `support = [E_trace]`) opens under the
  repaired engine with the **same state hash** (`7f10e88c2378ef82...`, 20 rows) as under the engine that wrote it (I-22: the fold applies the recorded outcome). Its live notebook under the repaired engine shows `H00003` corroborated by the statement only and `H00008` open, with no tension.
  The old evaluation stays in the log (engine-side, never rendered).


## 11. Remaining, NON-BLOCKING and UNMEASURED

**Unchanged from the review, still open (all NON-BLOCKING, none touched by this repair):** H8-N1 (turn-shape rules narrower than documented; a provisional accusation's form fields unchecked), H8-N2 (typed line parsed before the duplicate/stale/closed checks),
H8-N3 (free text names only the addressee, visited places and held items), H8-N4 (multipart file part -> 500; the "every form field is validated here" docstring overstates), H8-N5 (no anti-framing header), H8-N6 (two guards with no killing test: `game.held_ref`'s held-only handle map,
`web._RESERVED`; the import test sees only `web.py`), H8-N7 (notebook cost O(live theories x material)), H8-N8 (UX/spec gaps), H8-N9 (the I-21 `confession_check` hook is never wired). H8-X2 (a room with no exit; strict-`xfail` witness added) and H8-N10 (TK3 now killed deterministically; no harness entry, property test not derandomised).

**New, found while repairing (NON-BLOCKING):**
- **R-1 Two server processes on one saves directory** still each cache a `Save`; the second one's cache goes stale and every form there reads "stale" until it is restarted. What is fixed is that it **shows nothing unrecorded** (`_commit` honours the store). Not run end to end with two real processes; the two-handle unit test is the evidence.
- **R-2 D-6's message is only repaired on the cross-handle path.** In one process a second tab's *different* form with the same `<op>@<seq>` id still reads "Already recorded as turn n ... nothing new was recorded" (`turn_for` hits before the content can be compared). Nothing double-commits.
- **R-3 A `HasItem` hint names the case object** it needs by display name (as the review asked). If that object is one the player has not yet seen named, the hint says it exists. Unreachable today: no sealed case gates on `HasItem`/`KnowsAbout`, and the browser has no `Take` control (D-4).
- **R-4 Pre-repair saves keep the leaking `support`/`status` of their theories in the log.** It is never rendered (the notebook re-evaluates live) and replays unchanged; the same C-1 note as before (a stored evaluation is checked only for held-ness).
- **R-5 Behaviour change:** on a case-insensitive file system `/g/G1` for a game saved as `g1` is now a 404 (it used to open a second, stale `Save`). The index lists the on-disk spelling.
- **R-6 The `Lied` evaluator applies no `strength >= 0.5` floor** (the review asked the floor of `_evaluate_plain_proposition` only). A weak implication can still corroborate a `Lied` theory while the tension list would not show it. It is unlocked-only now, so nothing is leaked.
- **R-7 `P8-I3-other-spelling-opens-a-second-save` is platform-dependent:** it is killed on this NTFS machine; on a case-sensitive file system the alias cannot exist and the mutant would be equivalent.

**Unmeasured (nothing claimed):** a live model (D-1, Phase 5's exit criteria); cross-machine / OS / Python-version replay (C-11); a human playtest of the pages (D-7) and the section 30 exit "a tester plays it in a browser" beyond the scripted HTTP test; DNS rebinding in a **real** browser (simulated with the `Host` header, in-process and against a live `uvicorn` with `curl`; Chrome's Private Network Access not exercised);
the 2x50 seed study and the Phase 6 mutation harness (nothing under `gen/` or `solve/` changed; the Phase 6 harness needs hours); `tests.decision.mutation_check` (both sets; no anchor of it lies in a changed region - checked by reading its anchors, not by running it); the `EIDOLON_LONG=1` 1000/2000-turn sessions and `spike/` (`store.py` is byte-identical; the default 500-turn session ran inside `tests/test_persistence.py`).


## 12. Comparison with every original acceptance criterion

Every item of the review's section 6 and every "Required fix" bullet, in the review's words.

| # | Original criterion | Met? | Evidence |
|---|---|---|---|
| 1 | **H8-B1** Evaluate only `unlocked_implications(ev, known)` in all three hypothesis evaluators and both evidence paths of `game._tensions`; `known` = the union of `known_evidence`, `known_statements` and `known_accounts` | **Met** | section 2; `held_material` + `unlocked_view`; mutants plain / lied / planted-target / planted-other / tension-items / claim-vs-implication / evidence-vs-evidence / accounts-do-not-unlock |
| 2 | Apply section 13.2's `strength >= 0.5` floor in `_evaluate_plain_proposition` | **Met** | through `evidence_implication_contradicts`; unit test at 0.49 / 0.5; mutant. (A too-weak contradiction is now neither against nor support.) |
| 3 | Hardening: the forms' object vocabulary from unlocked material; do not change `held_names` | **Met** | `game.player_objects`; `held_names` untouched; the test shows the bot reading sees the object, the player's does not; mutant |
| 4 | Regression test on every sealed case: while the cleaning account is unheld no theory status, support/against label or tension references `E_trace`; after it is heard they may; one mutant per filter | **Met** | 4 control-level + 4 HTTP cases; the "after" half asserts the tie appears for the murderer's theory only; 11 mutants |
| 5 | **H8-I1** A hint names only what the player may see: generic line for `EvidenceFound` / `StatementHeard`; display name for `HasItem` / `KnowsAbout` | **Met** | section 3 (R-3 as a note) |
| 6 | Regression test: blank save, every place and object x every method, every sealed case, `_leaks()` empty on every resulting page; a mutant that restores `{ref}` | **Met** | the HTTP sweep searches every place and every object (offered or crafted) x every method, twice round, `_leaks()` on each page, four cases; a hint-text unit test over a blank save; `P8-I1-hint-prints-*` mutants. Pre-fix the sweep fails on all four |
| 7 | **H8-I2** Refuse any request whose `Host` is not `127.0.0.1:<port>` / `localhost:<port>` | **Met** | section 4; middleware on every route and method; live `curl` |
| 8 | Compare `Origin` with that allow-list, not with `Host` | **Met** | `_same_origin` against `app.state.origins` |
| 9 | Test: a POST **and a GET** with a foreign Host and a matching Origin are both refused; a mutant that drops the Host check | **Met** | `...rebound_host_is_refused_on_every_route...` (GET and POST), `P8-I2-host-not-checked` |
| 10 | **H8-I3** `_commit` honours `AppendResult` (`appended=False` is a duplicate and shows the committed turn, never the recomputed reply; `same_events=False` reads as stale) | **Met** | section 5; two-handle test; two mutants |
| 11 | Saves and rate windows keyed by the resolved, case-folded path, **or** refuse a name whose on-disk spelling differs | **Met** (second option) | `Games.open` by on-disk spelling; one `Save` and one rate window per file; test with 8 spellings -> 30 parse calls |
| 12 | Tests for the second-spelling tab (no uncommitted text, one rate window per save) and for a duplicate the store detects but the cache missed; mutants for both | **Met** | 3 tests, 3 mutants (R-7 for the platform note) |
| 13 | Re-run `tests/test_phase8.py`, `tests/test_persistence.py`, the `P8-` mutation set with the new mutants, and the full suite on the repaired tree; record hashes | **Met** | section 8 (Phase 8 147/147, persistence 315/315, whole `P8-` set, full suite 2833 passed + 1 xfailed; the trees and their hashes are listed there) |
| 14 | (user brief) Preserve the oracle fix and its test; keep the two oracle residuals NON-BLOCKING; add a deterministic witness | **Met** | section 7 |
| 15 | (user brief) Revalidate all four bundles and proofs; confirm the oracle fix changed no acceptance decision | **Met** for the four bundles (fresh); the seed study is inherited | section 10 |
| 16 | (user brief) Do not accept Phase 8, do not start Phase 9, do not commit | **Met** | - |

