"""Mutation check for `eidolon/store.py` (+ the one PI-7 guard in `solve/package.py`), and since Phase 8 for the guards of the
player's controls (`decision/turn.py`, `solve/session.py`, `solve/bots.py`, `game.py`, `web.py`, killed by `tests/test_phase8.py`;
the new FOLD rules are killed by their `P8_*` forgeries in the persistence file). Same rule as
`tests/decision/mutation_check.py`: each guard is disabled in turn and the persistence tests that name it must FAIL.

    python -m tests.persistence_mutation_check            # all mutants, 4 workers (~20-40 min)
    python -m tests.persistence_mutation_check -j 8 -k X39
    python -m tests.persistence_mutation_check -k P8-       # the Phase 8 set only

What it enforces (the Phase 7 hostile review's PN-12):
  * a GREEN-BASELINE GATE: the unmutated persistence file must pass, or nothing is reported (exit 2);
  * every mutant's anchor must match EXACTLY once, and its test selection must collect at least one test unmutated;
  * KILLED FOR THE RIGHT REASON: pytest must exit 1 (a collection error, exit 2/5, a crash in a fixture is not a kill) AND
    one of the failing test ids must contain one of the mutant's `fail` names — the test written for that guard;
  * mutants run in private copies of the tree (`-j` workers), so the real sources are never touched.

A mutant listed in EQUIVALENT is one whose guard is provably redundant with another (the reason is the entry); they are
not run, they are justified.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
STORE, PACKAGE = "eidolon/store.py", "eidolon/solve/package.py"
TESTS = "tests/test_persistence.py"
P8 = "tests/test_phase8.py"
HYP, DISC, HYPT = "eidolon/decision/hypotheses.py", "eidolon/evidence/discovery.py", "tests/decision/test_hypotheses.py"
EXPL, EXPT = "eidolon/decision/exploration.py", "tests/decision/test_exploration.py"
CLI = "eidolon/cli.py"
TURN, SESSION, BOTS, GAME, WEB = ("eidolon/decision/turn.py", "eidolon/solve/session.py", "eidolon/solve/bots.py",
                                  "eidolon/game.py", "eidolon/web.py")


def M(name, file, edits, k, fail=None, tests=TESTS):
    """edits: one (old, new) pair or a list of them. fail: substrings of the test id that must be among the failures.
    tests: the test file whose selection must kill it."""
    edits = [edits] if isinstance(edits, tuple) else edits
    if k == "PI1" and fail:                       # the forged-turn tests are parametrized by name: run only the guard's own
        k = "PI1 and (" + " or ".join(fail) + ")"
    return dict(name=name, file=file, edits=edits, k=k, fail=tuple(fail or k.replace(" or ", " ").split()), tests=tests)


MUTANTS = [
    # ---- the original 17 (anchors follow the repaired code) ----
    M("hearing-need-not-be-this-turns-commit", STORE, ("if made is None or ev.statement_id != made.id:", "if False:"), "hearing_row_cannot"),
    M("head-does-not-pin-the-tail", STORE, ("if (str(len(rows)), last_hash) != (meta[\"head_seq\"], meta[\"head_hash\"]):", "if False:"), "deleting_a_middle_row"),
    M("unearned-accounts-accepted", STORE, ("if not set(st.accounts) <= delivered:", "if False:"), "cannot_list_an_account"),
    M("grounding-unresolved-accepted", STORE, ("if owner is None:", "if False:"), "grounded_in_nothing"),
    M("chain-ignores-kind", STORE, ("\"kind\": kind, \"action_id\"", "\"action_id\""), "flipping_a_rows_kind"),
    M("chain-ignores-action-id", STORE, ("\"action_id\": action_id, \"payload\"", "\"payload\""), "editing_any_hashed_column"),
    M("genesis-unchecked", STORE, ("if meta[\"genesis\"] != prep.genesis:\n        _refuse(", "if False:\n        _refuse("), "different_seed_or_case"),
    M("payload-roundtrip-unchecked", STORE, ("if _canon(_plain(ev)) != _canon(obj):", "if False:"), "extra_payload_fields"),
    M("fold-state-unchecked", STORE, ("if problems := check_state(new):", "if False:"), "PI1 or undiscovered_evidence or detective_model_cannot",
      ["detective_model_ahead", "detective_model_cannot"]),
    M("peel-continuity-unchecked", STORE, ("ev.from_index != layer_index(decision.layer_peels, ev.character, ev.secret_id)", "False"), "layer_peel_must_continue or skip_a_layer"),
    M("peel-does-not-advance-unchecked", STORE, ("not ev.from_index < ev.to_index < len(s.cover.layers)", "not ev.to_index < len(s.cover.layers)"), "PI1", ["peel_that_does_not_advance"]),
    # killed by a CRASH, not a message: with the bound gone the voicing check indexes past the cover (the property is "refuses cleanly")
    M("peel-past-the-end-unchecked", STORE, ("not ev.from_index < ev.to_index < len(s.cover.layers)", "not ev.from_index < ev.to_index"), "PI1", ["peel_past_the_end"]),
    M("action-id-reuse-unchecked", STORE, ("or group[0][3] in actions", ""), "reusing_an_action_id"),
    M("stale-append-accepted", STORE, ("if head != expected_seq or head != self.last_seq or head_hash != self.last_hash:", "if False:"), "stale_expected_seq"),
    M("duplicate-action-appended", STORE, ("if hit[1] is not None:", "if False:"), "stale_expected_seq or PI5"),
    M("unknown-kind-accepted-on-write", STORE, ("if model is None or type(ev) is not model:", "if model is None:"), "not_a_registered_event"),
    M("overlay-target-unchecked", STORE, ("_check_epistemic_target(state, ev, who)\n            if kind", "if kind"), "overlay_rows_must_name"),
    M("proof-verifier-bypassed", STORE, ("bundle = load_sealed_text(docs[0][0])", "bundle = __import__('eidolon.solve.package', fromlist=['x']).SealedCase.model_validate({**json.loads(docs[0][0]), 'package': json.loads(docs[0][0])['package']})"), "proof_with_its_exclusions"),
    # ---- PB-1: recovery ----
    M("trunc-trusts-the-stored-genesis", STORE, ("n, last_hash, _why = _valid_prefix(rows, prep.genesis)", "n, last_hash, _why = _valid_prefix(rows, prep.meta[\"genesis\"])"), "PB1_a_damaged_genesis"),
    M("trunc-does-not-reverify", STORE, ("                _replay(conn, prep)                     # the repaired file must LOAD, or nothing is changed", "                pass"), "PB1_a_repair_that_would_not_load"),
    M("trunc-drops-the-complete-turn", STORE, ("candidates = [n] if n == 0 or _is_turn_start(rows[n], rows[n - 1][1]) else []", "candidates = [n] if n == 0 else []"), "PB1_a_break_between_turns"),
    M("trunc-never-finds-the-turn-start", STORE, ("candidates += [start] if start != n else []", "candidates += []"), "PB1_a_break_inside_a_turn"),
    M("trunc-acts-on-a-fold-refusal", STORE, ("            except SaveRefusal as e:\n                return _refusal_plan(total, e)\n            return TruncationPlan(\"none\"", "            except SaveRefusal as e:\n                pass\n            return TruncationPlan(\"none\""), "PB1_a_chain_valid_row"),
    M("trunc-without-confirmation", STORE, ("    if not confirm:\n        raise ConfirmationRequired(plan)", "    if False:\n        raise ConfirmationRequired(plan)"), "PB1_the_dry_run or PB1_recovery_without_confirm"),
    M("trunc-dry-run-commits", STORE, ("if chosen is None or not apply:", "if chosen is None:"), "PB1_the_dry_run"),
    M("trunc-head-reset-loses-rows", STORE, ("\"reset_meta\", [total],", "\"reset_meta\", [total - 1],"), "PB1_a_damaged_genesis or PB1_a_head_record"),
    M("trunc-may-create-a-file", STORE, [("    if not p.is_file():\n        raise SaveRefusal(f\"no such save: {p}\")        # never create", "    if False:\n        raise SaveRefusal(f\"no such save: {p}\")        # never create"),
                                         ("?mode=rw\", uri=True, isolation_level=None)\n        return _plan_and_apply", "?mode=rwc\", uri=True, isolation_level=None)\n        return _plan_and_apply")], "PB1_recovery_refuses_or_repairs"),
    M("trunc-guesses-when-genesis-and-chain-both-fail", STORE, ("        if prep.meta[\"genesis\"] != prep.genesis:\n            return TruncationPlan(\"refuse\"", "        if False:\n            return TruncationPlan(\"refuse\""), "PB1_a_damaged_genesis_and"),
    # ---- PI-1: the validating fold ----
    M("retraction-of-another-speaker", STORE, ("if old is None or old.speaker != who or old.retracted_by is not None:", "if old is None:"), "PI1", ["retraction_of_another_speaker"]),
    M("retraction-of-itself", STORE, ("if ev.statement_id == ev.retracted_by:", "if False:"), "PI1", ["retraction_of_itself"]),
    M("retraction-without-a-peel", STORE, ("if retracts and not peels:", "if False:"), "PI1", ["retraction_without_a_peel"]),
    M("retraction-by-an-uncommitted-statement", STORE, ("if made is None or ev.retracted_by != made.id:", "if False:"), "PI1", ["retraction_by_an_uncommitted"]),
    M("peel-beside-a-non-concession", STORE, ("if made is None or made.act not in (\"CONCESSION\", \"CONFESSION\"):", "if made is None:"), "PI1", ["peel_beside_a_non_concession"]),
    M("peel-nobody-voiced", STORE, ("if any(said.get(c.id) is None or said[c.id].model_copy(update={\"statement\": c.statement}) != c for c in owed):", "if False:"),
      "PI1", ["peel_nobody_voiced", "R1_peel_voiced_with_other"]),
    M("grounding-in-another-speakers-knowledge", STORE, ("if owner != st.speaker:", "if False:"), "PI1", ["another_characters_knowledge"]),
    M("statement-by-another-speaker", STORE, ("if who is None or st.speaker != who or st.turn != turn or st.id != f\"S{turn:05d}\":", "if who is None:"), "PI1", ["statement_by_another_speaker"]),
    M("claim-bound-to-another-statement", STORE, ("if c.statement != st.id:", "if False:"), "PI1", ["claim_bound_to_another"]),
    M("meta-attempt-for-someone-else", STORE, ("elif kind == \"MetaAttemptLogged\" and ev.character != who:", "elif False:"), "PI1", ["meta_attempt_for_someone_else"]),
    M("location-inside-a-conversation", STORE, ("if who is not None:\n                _refuse(f\"{kind} inside a conversation turn\"", "if False:\n                _refuse(f\"{kind} inside a conversation turn\""), "PI1", ["location_visited_inside"]),
    M("unknown-speaker-accepted", STORE, ("if who is not None and who not in state.characters:", "if False:"), "PI1", ["a_character_who_does_not_exist"]),
    M("conversation-without-a-statement", STORE, ("if made is None:\n            _refuse(\"a conversation turn carries no statement\"", "if False:\n            _refuse(\"a conversation turn carries no statement\""), "PI1", ["bare_conversation", "no_statement", "minds_rows"]),
    M("statement-not-heard-once", STORE, ("if heard != [made.id] or sorted(accounts) != sorted(made.accounts):", "if False:"), "PI1", ["a_statement_nobody_heard"]),
    M("detective-model-rewrites-other-fields", STORE, ("if (new.accusations, new.probed_topics", "if False and (new.accusations, new.probed_topics"), "PI1", ["detective_model_rewrites"]),
    M("detective-model-told-everything", STORE, ("or len(added) > 1:", "or False:"), "PI1", ["shown_everything"]),
    M("unknown-place-accepted", STORE, ("if kind == \"LocationVisited\" and ev.location not in known_locations(state.case, state.evidence):", "if False:"), "PI1", ["go_to_a_place"]),
    M("unknown-item-accepted", STORE, ("if kind == \"ItemTaken\" and ev.item not in known_items(state.case, state.evidence):", "if False:"), "PI1", ["take_an_item"]),
    M("pressure-on-a-secret-not-owned", STORE, ("if s is None or s.owner != who:", "if False:"), "PI1", ["pressure_on_a_secret"]),
    M("suspicion-of-an-unknown-actor", STORE, ("elif kind == \"SuspicionShift\" and ev.target is not None and ev.target not in state.characters:", "elif False:"), "PI1", ["suspicion_of_nobody"]),
    M("accusation-outside-the-domain", STORE, ("                if ev.target not in state.characters and ev.target != \"Outsider\":", "                if False:"), "PI1", ["accusation_of_nobody"]),
    M("turn-names-another-action", STORE, ("if head.action_id is not None and head.action_id != action_id:", "if False:"), "PI1", ["turn_names_another_action"]),
    M("duplicate-row-in-a-turn", STORE, ("if row in rows_seen:", "if False:"), "PI1", ["the_same_row_twice"]),
    M("hypothesis-on-unheld-material", STORE, ("if stray := [r for r in (*ev.hypothesis.support, *ev.hypothesis.against) if r not in held]:", "if False:"), "PI1", ["never_held"]),
    # Phase 8: "solved twice" is now refused by the turn-level PN-10 rule (no turn follows CaseSolved); the old in-row check was dead code
    M("case-solved-twice", STORE, ('    if state.decision.solved is not None:\n        _refuse("the case is already solved: no turn',
                                   '    if False:\n        _refuse("the case is already solved: no turn'), "PI1_the_case_cannot"),
    M("told-more-reliably-than-trusted", STORE, ("if bp(e.reliability) > chars[e.character].trust_detective:", "if False:"), "PI1", ["I25"]),
    M("turn-order-unchecked", STORE, ("if turn != state.turn_counter + 1:", "if False:"), "a_turn_must_open_with_turn_committed"),
    M("turn-need-not-open-with-a-bracket", STORE, ("if not events or not isinstance(events[0], TurnCommitted):", "if not events:"), "a_turn_must_open_with_turn_committed or not_a_registered_event"),
    M("row-turn-inside-a-turn-unchecked", STORE, ("if getattr(ev, \"turn\", turn) != turn:", "if False:"), "a_turn_must_open_with_turn_committed"),
    M("peel-of-the-addressees-secret-by-another", STORE, ("if s is None or s.owner != ev.character or ev.character != who:", "if s is None or s.owner != ev.character:"),
      "PI1", ["peel_of_another_characters_secret"]),
    M("peel-by-a-character-who-does-not-own-the-secret", STORE, ("if s is None or s.owner != ev.character or ev.character != who:", "if s is None or ev.character != who:"),
      "PI1", ["peel_of_a_secret_its_character_does_not_own"]),
    # ---- R-1 (re-review): the nested references and shapes. Each forgery in FORGERIES carries ONE defect, so these are real kills
    M("R1-memory-of-another-character", STORE, ("if m.character != who:", "if False:"), "PI1",
      ["R1_memory_recall_of_another", "R1_memory_recall_in_an_exploration", "R1_memory_corrected_for_another"]),
    M("R1-belief-of-another-character", STORE, ("if b.character != who:", "if False:"), "PI1", ["R1_belief_revised_for", "R1_belief_revised_in"]),
    M("R1-knowledge-for-another-character", STORE, ("elif ev.entry.character != who:", "elif False:"), "PI1", ["R1_knowledge_added_for", "R1_knowledge_added_in"]),
    M("R1-memory-field-the-memory-does-not-distort", STORE, ("if ev.kind == \"MemoryCorrected\" and ev.field not in {d.field for d in m.distortions}:", "if False:"),
      "PI1", ["R1_memory_corrected_field"]),
    M("R1-turn-id-of-an-overlay-row", STORE, ("getattr(ev, \"turn_id\", turn),", "turn,"), "PI1", ["R1_memory_recall_carrying"]),
    M("R1-turn-id-of-a-recall-record", STORE, ("getattr(getattr(ev, \"record\", None), \"turn_id\", turn)", "turn"), "PI1", ["R1_recall_record_carrying"]),
    M("R1-turn-id-of-a-revision", STORE, ("getattr(getattr(ev, \"revision\", None), \"turn_id\", turn)", "turn"), "PI1", ["R1_belief_revision_carrying"]),
    M("R1-two-detective-model-updates", STORE, ("if model_updates > 1:", "if False:"), "PI1", ["R1_two_detective"]),
    M("R1-slip-nobody-has", STORE, ("if ev.slips_used is not None and not set(ev.slips_used) <= mine:", "if False:"), "PI1", ["R1_slip_nobody"]),
    M("R1-contradiction-nothing-resolves", STORE, ("if ev.contradictions_caught is not None and not set(ev.contradictions_caught) <= set(chars[who].contradictions_caught):", "if False:"),
      "PI1", ["R1_contradiction_nothing"]),
    M("R1-negative-refuse-streak", STORE, ("if (ev.refuse_streak or 0) < 0 or any(", "if any("), "PI1", ["R1_negative_refuse_streak"]),
    M("R1-negative-topic-counter", STORE, ("or any(n < 0 for n in (ev.topics_probed or {}).values()):", ":"), "PI1", ["R1_negative_topic"]),
    M("R1-incidental-by-a-non-addressee", STORE, ("if who is None or ev.speaker != who:", "if False:"), "PI1", ["R1_incidental_pinned"]),
    M("R1-incidental-scope-unchecked", STORE, ("if ev.layer_scope is not None:\n                    _check_layer_scope(", "if False:\n                    _check_layer_scope("),
      "PI1", ["R1_incidental_scoped"]),
    M("R1-statement-scope-unchecked", STORE, ("if st.layer_scope is not None:\n        _check_layer_scope(", "if False:\n        _check_layer_scope("), "PI1", ["R1_statement_scoped"]),
    M("R1-layer-scope-index-unchecked", STORE, (" or not 0 <= scope[1] < len(s.cover.layers)", ""), "PI1",
      ["R1_incidental_scoped_to_a_layer", "R1_statement_scoped_to_a_layer"]),
    M("R1-layer-scope-owner-unchecked", STORE, ("s.owner != owner or ", ""), "PI1",
      ["R1_incidental_scoped_to_a_secret", "R1_statement_scoped_to_a_secret"]),
    # killed by a CRASH (`s.owner` on None), not a message: the property is "refuses cleanly"
    M("R1-layer-scope-of-no-secret", STORE, ("if s is None or s.owner != owner", "if s.owner != owner"), "PI1", ["R1_incidental_scoped_to_no_secret"]),
    M("R1-duplicate-claim-ids", STORE, ("if len({c.id for c in st.claims}) != len(st.claims):", "if False:"), "PI1", ["R1_two_claims"]),
    M("R1-claim-proposition-unchecked", STORE, ("_check_proposition(state, c.proposition, f\"claim {c.id!r}\")", "pass"), "PI1", ["R1_claim_naming"]),
    M("R1-hypothesis-proposition-unchecked", STORE, ("_check_proposition(state, p, f\"hypothesis {h.id!r}\")", "pass"), "PI1", ["R1_hypothesis_naming"]),
    M("R1-told-proposition-unchecked", STORE, ("_check_proposition(state, e.proposition, f\"KnowledgeAdded {e.id!r}\")", "pass"), "PI1", ["R1_knowledge_told_naming"]),
    M("R1-entity-slots-unchecked", STORE, ("if stray := sorted(named - pool):", "if False:"), "PI1",
      ["R1_claim_naming_an_unknown_actor", "R1_claim_naming_an_unknown_object", "R1_hypothesis_naming", "R1_knowledge_told_naming"]),
    M("R1-ambiguous-slot-unchecked", STORE, ("if stray := sorted(either - everything):", "if False:"), "PI1", ["R1_claim_naming_an_unknown_holder"]),
    M("R1-lied-on-an-unheld-statement", STORE, ("if isinstance(p, Lied) and p.statement not in disc.known_statements:", "if False:"), "PI1", ["R1_hypothesis_Lied"]),
    M("R1-planted-on-unheld-evidence", STORE, ("if isinstance(p, Planted) and p.evidence not in disc.known_evidence:", "if False:"), "PI1", ["R1_hypothesis_Planted"]),
    M("R1-peel-voiced-by-claim-id-only", STORE, ("said[c.id].model_copy(update={\"statement\": c.statement}) != c", "False"), "PI1", ["R1_peel_voiced_with_other"]),
    # ---- F-1 (closure review): time slots inside the case's clock [0, t_investigation] ----
    M("F1-times-not-checked", STORE, ("    _check_times(prop, state.case.t_investigation, what)\n", ""), "PI1", ["F1_claim_", "F1_hypothesis_", "F1_knowledge_"]),
    M("F1-interval-start-unbounded", STORE, ("if iv is not None and not 0 <= iv[0] < iv[1] <= horizon:", "if iv is not None and not iv[0] < iv[1] <= horizon:"),
      "PI1", ["F1_claim_interval_starting_before"]),
    M("F1-interval-end-unbounded", STORE, ("if iv is not None and not 0 <= iv[0] < iv[1] <= horizon:", "if iv is not None and not 0 <= iv[0] < iv[1]:"),
      "PI1", ["F1_claim_interval_far_beyond", "F1_hypothesis_interval", "F1_knowledge_told_interval"]),
    M("F1-interval-end-one-tick-too-lax", STORE, ("iv[1] <= horizon:", "iv[1] <= horizon + 1:"), "PI1", ["F1_claim_interval_ending_one_tick"]),
    M("F1-moved-tick-unbounded", STORE, ("if tick is not None and not 0 <= tick <= horizon:", "if False:"), "PI1", ["F1_claim_moved"]),
    M("F1-said-interval-not-descended-into", STORE, ("if prop.kind == \"Said\":\n        _check_times(", "if False:\n        _check_times("), "PI1", ["F1_claim_said_nesting"]),
    # false-refusal side: a clock one tick too tight refuses a real claim, so the inclusive control must fail
    M("F1-clock-excludes-its-last-tick", STORE, ("iv[1] <= horizon:", "iv[1] < horizon:"), "F1_the_clock_is_inclusive"),
    M("F1-moved-tick-excludes-the-last-tick", STORE, ("not 0 <= tick <= horizon:", "not 0 <= tick < horizon:"), "F1_the_clock_is_inclusive"),
    M("F1a-moved-tick-has-no-lower-bound", STORE, ("not 0 <= tick <= horizon:", "not tick <= horizon:"), "PI1", ["F1a_claim_moved_at_a_negative"]),
    # ---- H9-I3: the confession gate is wired, and a forged confession is refused ----
    M("H9I3-fold-accepts-any-confession", STORE, ('    if made is not None and made.act == "CONFESSION":\n        _check_confession(state, decision, made, who)\n', ''),
      "PI1", ["H9I3_confession_where", "H9I3_confession_by"]),
    M("H9I3-game-passes-no-gate", GAME, ("confession_check=confession_gate(st, save.bundle.package), ", ""),
      "shipped_ask_control", ["shipped_ask_control"], tests="tests/test_confession_gate.py"),
    M("H9I3-gate-ignores-what-was-presented", GAME, ("credited_material(st, only=frozenset(presented))", "credited_material(st)"),
      "opens_only_on_material", ["opens_only_on_material"], tests="tests/test_confession_gate.py"),
    # ---- F-15: a refuse_streak is the run of REFUSE turns the log shows ----
    M("F15-fold-accepts-any-refuse-streak", STORE, ('            if kind == "CoverStateDelta" and ev.refuse_streak is not None and ev.refuse_streak != (', '            if False and ('),
      "PI1", ["F15_refuse_streak_in_a_turn"]),
    # ---- ADR-32: a proof breaks the last denial before a gated confession ----
    M("ADR32-the-proof-breaks-nothing", "eidolon/decision/peel.py", ('            if not (nxt.terminal == "confession" and confession_gated(secret, nxt)', '            if True or not (nxt.terminal == "confession" and confession_gated(secret, nxt)'),
      "ADR32", ["ADR32_a_murderer"], tests="tests/test_confession_gate.py"),
    M("ADR32-the-step-ignores-the-gate", "eidolon/decision/peel.py", ('                    and confession_permitted(confession_check, secret, confrontee, presented, ctx)):\n                break', '                    and True):\n                break'),
      "ADR32", ["ADR32_short"], tests="tests/test_confession_gate.py"),
    # ---- the full review's web/CLI/provider/trace fixes (docs/EIDOLON-FULL-REVIEW-2026-10-22.md §5) ----
    M("H8N3-typed-text-names-only-the-encountered", WEB, ("known = encountered(st, who) | frozenset(case.actors) | frozenset(case.locations)", "known = encountered(st, who)"),
      "H8_N3", ["H8_N3_typed_text"], tests="tests/test_phase8.py"),
    M("H8N4-file-parts-accepted", WEB, ("if any(not isinstance(v, str) for _, v in items):", "if False:"),
      "H8_N4", ["H8_N4"], tests="tests/test_review_fixes.py"),
    M("H8N5-framing-allowed", WEB, ('(b"x-frame-options", b"DENY"), ', ""), "H8_N5", ["H8_N5"], tests="tests/test_review_fixes.py"),
    M("NRN4-seed-unbounded-above", WEB, ("if not 0 <= seed < SEED_MAX:", "if not 0 <= seed:"), "NR_N4", ["NR_N4"], tests="tests/test_review_fixes.py"),
    M("NRN6-redirect-followed", "eidolon/llm/provider.py", ("            return None\n    return urllib.request.build_opener", "            return super().redirect_request(*a, **k)\n    return urllib.request.build_opener"),
      "NR_N6", ["NR_N6"], tests="tests/test_review_fixes.py"),
    M("NRN7-pm-ignored", "eidolon/llm/ingress.py", ('if ampm == "p" and h < 12:', "if False:"), "NR_N7", ["NR_N7"], tests="tests/test_review_fixes.py"),
    M("H9N1-prompt-leak-traced-as-provider-error", "eidolon/trace.py", ('"PromptLeak": "prompt_leak", "PROMPT_LEAK": "prompt_leak"}', '"PromptLeak": "prompt_leak"}'),
      "H9_N1", ["H9_N1"], tests="tests/test_review_fixes.py"),
    M("H9N2-stale-traces-adopted", STORE, ('stale.rename(stale.with_name(f"{stale.name}.stale-{n}"))', "None"), "H9_N2", ["H9_N2"], tests="tests/test_review_fixes.py"),
    M("H8N8-any-window-earns-the-time-axis", GAME, ("and acc.interval[1] - acc.interval[0] <= ACCUSATION_WINDOW_MAX", ""),
      "H8_N8_a_window", ["H8_N8_a_window"], tests="tests/test_review_fixes.py"),
    M("H8N7-notebook-recomputed-every-render", GAME, ("    if key not in _NOTEBOOK:", "    if True:"), "H8_N7", ["H8_N7"], tests="tests/test_review_fixes.py"),
    # ---- NR-I4: a lie per topic - only the asked one is told ----
    M("NRI4-lie-recites-every-topic", "eidolon/decision/strategy.py",
      ("    told = tuple(c for c in layer.claims if on_topic(c.proposition, inp.query)", "    told = tuple(c for c in layer.claims if True"),
      "NR_I4", ["lies_on_topic"], tests="tests/gen/test_topic_covers.py"),
    # ---- NR-B1: a save made by an earlier engine keeps loading (the derivation may not move) ----
    M("NRB1-derived-personality-moves", SESSION, ('voice=VoiceSpec(voice_register="plain"))', 'voice=VoiceSpec(voice_register="plain", tics=("hm.",)))'),
      "earlier_engine", ["a_save_made_by_an_earlier_engine"], tests="tests/test_committed_saves.py"),
    # ---- N-3: the dry run must not write ----
    M("N3-dry-run-rolls-back-a-hot-journal", STORE, ("if journal.is_file() and journal.stat().st_size:", "if False:"), "N3"),
    # ---- PI-2: floats / canonical text ----
    M("float-whitelist-off", STORE, ("if path != _FLOAT_FIELDS.get(kind) or bp(x) / BP_MAX != x:", "if False:"), "PI1", ["a_float_in_an_overlay", "off_the_basis_point_grid", "outside_0_1"]),
    M("float-grid-off", STORE, ("if path != _FLOAT_FIELDS.get(kind) or bp(x) / BP_MAX != x:", "if path != _FLOAT_FIELDS.get(kind):"), "PI1", ["off_the_basis_point_grid", "outside_0_1"]),
    M("confidence-hashed-as-float", STORE, ("h[\"player_confidence\"] = bp(h[\"player_confidence\"])", "pass"), "PI2_a_bp_confidence"),
    M("state-hash-allows-floats", STORE, ("    _no_floats(doc)\n    return doc", "    return doc"), "PI2_canonical_state_refuses"),
    M("payload-text-malleable", STORE, ("ok = payload == _canon(obj) and h ==", "ok = h =="), "PN2_the_stored_payload_text"),
    M("meta-integers-uncanonical", STORE, ("if str(version) != meta[\"schema_version\"] or str(seed) != meta[\"seed\"]:", "if False:"), "PN13"),
    M("write-time-roundtrip-unchecked", STORE, ("    if not round_trips:\n        _refuse(", "    if False:\n        _refuse("), "X30"),
    # ---- PI-3 / PI-4 / PI-5 / PI-6 / PI-7 ----
    M("older-schema-opens-writable", STORE, ("if writable and version < SCHEMA_VERSION:", "if False:"), "PI3_an_older_save or upcaster_round_trip"),
    M("genesis-does-not-bind-the-schema", STORE, ("\"seed\": seed, \"schema\": version, \"initial\"", "\"seed\": seed, \"initial\""), "PI3_relabelling"),
    M("head-hash-not-compared-on-append", STORE, (" or head_hash != self.last_hash:", ":"), "PI4"),
    M("duplicate-does-not-return-its-turn", STORE, ("return AppendResult(False, hit[2], TurnRef(*hit), same)", "return AppendResult(False, self.last_seq)"), "PI5"),
    M("duplicate-reports-same-events-blindly", STORE, ("same = [_encode(ev) for ev in events] == stored", "same = True"), "PI5"),
    M("initial-digest-unchecked", STORE, ("if meta[\"initial_digest\"] != digest:", "if False:"), "PI6_an_engine or PI6_meta_records"),
    M("digest-omits-memories", STORE, ("\"memories\": {a: [_plain(m) for m in state.memories.get(a, ())] for a in actors},", "\"memories\": {},"), "PI6_every_derived_store"),
    M("digest-omits-characters", STORE, ("\"characters\": {a: _plain(state.characters[a]) for a in actors}}", "\"characters\": {}}"), "PI6_every_derived_store"),
    M("digest-omits-beliefs", STORE, ("\"beliefs\": [_plain(b) for a in actors for b in sorted(state.beliefs.for_character(a), key=lambda b: b.id)],", "\"beliefs\": [],"), "PI6_every_derived_store"),
    M("digest-omits-knowledge", STORE, ("doc = {\"knowledge\": sorted((_plain(e) for e in state.knowledge.all()), key=_canon),", "doc = {\"knowledge\": [],"), "PI6_every_derived_store"),
    M("declared-murderer-unchecked", PACKAGE, ("proof.get(\"survivors\") != [sol.murderer]", "False"), "PI7", ["update0"]),
    M("declared-place-and-moment-unchecked", PACKAGE, ("if proof.get(\"murder_loc\") != sol.location or list(proof.get(\"window\", ())) != list(sol.interval):", "if False:"), "PI7", ["update1", "update2"]),
    # ---- the audit's real-gap survivors ----
    M("X35-row-turn-column-unchecked", STORE, ("if evs[0].kind != \"TurnCommitted\" or evs[0].turn != group[0][1]:", "if evs[0].kind != \"TurnCommitted\":"), "X35"),
    M("X36-one-action-id-per-turn-unchecked", STORE, ("if len({r[3] for r in group}) != 1 or ", "if "), "X36"),
    M("X39-read-only-open-is-read-write", STORE, ("?mode={'rw' if writable else 'ro'}", "?mode=rw"), "X39"),
    M("X47-empty-action-id-accepted", STORE, ("if not isinstance(action_id, str) or not action_id:", "if not isinstance(action_id, str):"), "X47"),
    M("X38-no-rollback-on-failure", STORE, ("        except BaseException:\n            if c.in_transaction:\n                c.execute(\"ROLLBACK\")\n            raise\n        first", "        except BaseException:\n            raise\n        first"), "not_a_registered_event or refused_append"),
    M("X40-sets-not-sorted", STORE, ("return sorted((_plain(v) for v in x), key=_canon)", "return [_plain(v) for v in x]"), "fresh_process"),
    M("X45-prev-hash-column-unchecked", STORE, ("if seq != i or ph != prev or not ok:", "if seq != i or not ok:"), "X45"),
    M("X46-genesis-does-not-bind-the-seed", STORE, ("{\"case\": case_hash, \"seed\": seed, \"schema\"", "{\"case\": case_hash, \"schema\""), "X46"),
    M("X32-meta-case-unchecked", STORE, ("if meta[\"case_hash\"] != bundle.package.seal or meta[\"case_id\"] != bundle.package.id:", "if False:"), "different_seed_or_case"),
    M("X33-meta-key-set-unchecked", STORE, ("if set(meta) != _META_KEYS:", "if False:"), "missing_or_extra_meta_key"),
    M("X34-newer-schema-accepted", STORE, ("if version > SCHEMA_VERSION:", "if False:"), "newer_schema"),
    # ---- Phase 8: the fold rules of the new producers (killed by their P8_* forgeries, at append AND at a re-chained load) ----
    M("P8-turn-after-verdict-accepted", STORE, ('    if state.decision.solved is not None:\n        _refuse("the case is already solved: no turn',
                                                '    if False:\n        _refuse("the case is already solved: no turn'), "no_turn_follows_the_verdict", tests=P8),
    M("P8-row-after-verdict-accepted", STORE, ('        if decision.solved is not None:\n            _refuse(f"{kind} after CaseSolved',
                                               '        if False:\n            _refuse(f"{kind} after CaseSolved'), "PI1", ["P8_a_row_after_the_verdict"]),
    M("P8-provisional-target-unchecked", STORE, ("                    if ev.target != who:                # (outside a conversation `who` is None)",
                                                 "                    if False:"), "PI1",
      ["P8_provisional_accusation_outside", "P8_provisional_accusation_of_someone"]),
    M("P8-final-inside-conversation-accepted", STORE, ('                    if who is not None:\n                        _refuse("a final accusation',
                                                       '                    if False:\n                        _refuse("a final accusation'), "PI1",
      ["P8_final_accusation_inside_a_conversation"]),
    M("P8-two-final-accusations-accepted", STORE, ('                    if final is not None:\n                        _refuse("two final',
                                                   '                    if False:\n                        _refuse("two final'), "PI1", ["P8_two_final_accusations"]),
    M("P8-unheld-citation-accepted", STORE, ("    if stray := [r for r in ev.cited if r not in held]:", "    if False:"), "PI1",
      ["P8_final_accusation_citing_material", "P8_final_accusation_citing_an_account"]),
    M("P8-unknown-weapon-accepted", STORE, ("    if ev.weapon is not None and ev.weapon not in known_items(state.case, state.evidence):", "    if False:"),
      "PI1", ["P8_final_accusation_naming_a_weapon"]),
    M("P8-unknown-place-accepted", STORE, ("    if ev.location is not None and ev.location not in known_locations(state.case, state.evidence):",
                                           "    if False:"), "PI1", ["P8_final_accusation_naming_a_place"]),
    M("P8-accusation-window-unbounded", STORE, ('    _check_times(ev, state.case.t_investigation, "Accusation")', "    pass"), "PI1",
      ["P8_final_accusation_window"]),
    M("P8-verdict-without-accusation", STORE, ('    if final is None:\n        _refuse("CaseSolved without', '    if False:\n        _refuse("CaseSolved without'),
      "PI1", ["P8_case_solved_without", "P8_case_solved_inside"]),
    M("P8-verdict-unproven-accepted", STORE, ('    if state.murderer is None:\n        _refuse("CaseSolved in a case with no proven',
                                              '    if False:\n        _refuse("CaseSolved in a case with no proven'), "proven_murderer_to_be_judged",
      tests=P8),
    M("P8-verdict-trusted", STORE, ("    if ev.correct != (final.target == state.murderer):", "    if False:"), "PI1",
      ["P8_case_solved_correct_for", "P8_case_solved_incorrect_for"]),
    M("P8-final-need-not-close", STORE, ("    if final is not None and decision.solved is None:", "    if False:"), "PI1",
      ["P8_final_accusation_that_does_not_close"]),
    M("P8-model-accusation-unbound", STORE, ("        owed = old.accusations + (((turn, True, who),) if accused else ())", "        owed = new.accusations"),
      "PI1", ["P8_model_records"]),
    M("P8-accusation-unrecorded-accepted", STORE, ("    if accused and chars[who].detective_model.accusations[-1:] != ((turn, True, who),):", "    if False:"),
      "PI1", ["P8_provisional_accusation_the_model_does_not_record"]),
    M("P8-board-in-conversation", STORE, ('    if who is not None:\n        _refuse(f"HypothesisChanged', '    if False:\n        _refuse(f"HypothesisChanged'),
      "PI1", ["P8_hypothesis_inside_a_conversation"]),
    M("P8-board-updated-turn-F3", STORE, ("    if h.updated_turn != turn:", "    if False:"), "PI1", ["P8_hypothesis_updated_in_another_turn"]),
    M("P8-board-created-turn-F3", STORE, ('    if old is None and (h.created_turn != turn or h.status == "withdrawn"):', '    if old is None and h.status == "withdrawn":'),
      "PI1", ["P8_hypothesis_created_in_another_turn"]),
    M("P8-board-born-withdrawn", STORE, ('    if old is None and (h.created_turn != turn or h.status == "withdrawn"):', "    if old is None and h.created_turn != turn:"),
      "PI1", ["P8_hypothesis_born_withdrawn"]),
    M("P8-board-revives-withdrawn", STORE, ('    if old is not None and (old.status == "withdrawn" or h.created_turn != old.created_turn):',
                                            "    if old is not None and h.created_turn != old.created_turn:"), "withdrawn_hypothesis_cannot_be_revised"),
    M("P8-board-rewrites-creation", STORE, ('    if old is not None and (old.status == "withdrawn" or h.created_turn != old.created_turn):',
                                            '    if old is not None and old.status == "withdrawn":'), "revision_cannot_rewrite"),
    M("P8-lied-speaker-unchecked", STORE, ("        if isinstance(p, Lied) and state.decision.statements.get(p.statement).speaker != p.actor:", "        if False:"),
      "PI1", ["P8_hypothesis_Lied_about"]),
    # ---- Phase 8: producers, controls, projection, browser boundary (killed by tests/test_phase8.py) ----
    M("P8-runner-accuses-after-the-verdict", TURN, ('    if state.decision.solved is not None or state.murderer is None:\n        return _refused(state, "CASE_CLOSED")',
                                                    '    if state.murderer is None:\n        return _refused(state, "CASE_CLOSED")'), "runners_reject", tests=P8),
    M("P8-runner-domain-unchecked", TURN, ('    if target not in state.characters and target != "Outsider":\n        return _refused',
                                           '    if False:\n        return _refused'), "runners_reject", tests=P8),
    M("P8-runner-unheld-citation", TURN, ("    if not set(cited) <= state.discovery.known_evidence | state.discovery.known_statements:", "    if False:"),
      "runners_reject", tests=P8),
    M("P8-runner-unknown-hypothesis", TURN, ('    if target and (old is None or old.status == "withdrawn"):', "    if False:"), "runners_reject", tests=P8),
    M("P8-runner-theory-after-the-verdict", TURN, ('    if state.decision.solved is not None:\n        return _refused(state, "CASE_CLOSED")\n    if target',
                                                   '    if False:\n        return _refused(state, "CASE_CLOSED")\n    if target'), "runners_reject", tests=P8),
    M("P8-provisional-row-not-emitted", TURN, ("    if provisional_accusation:\n        # §16.3/§11.3", "    if False:\n        # §16.3/§11.3"),
      "provisional_accusation_is_recorded", tests=P8),
    M("P8-provisional-not-in-model", TURN, ("    new_accusations = detective_model.accusations + (((turn_id, True, addressee),) if provisional_accusation else ())",
                                            "    new_accusations = detective_model.accusations"), "provisional_accusation_is_recorded", tests=P8),
    M("P8-session-has-no-proven-murderer", SESSION, ('    murderer = proof["survivors"][0] if proof.get("unique") is True and len(proof.get("survivors", ())) == 1 else None',
                                                     "    murderer = None"), "final_accusation_closes or shapes_the_verdict", tests=P8),
    M("P8-control-retry-not-deduplicated", GAME, ("    if (ref := save.turn_for(action_id)) is not None:", "    if False:"), "retried_action", tests=P8),
    M("P8-handle-is-the-evidence-id", GAME, ('    return "e" + hashlib.sha256(f"{save.bundle.package.seal}|{evidence_id}".encode()).hexdigest()[:12]',
                                             "    return evidence_id"), "no_projection_serializes", tests=P8),
    M("P8-evidence-axis-free", GAME, ("    return verdict.unique and list(verdict.survivors) == [st.murderer]", "    return True"), "each_axis_is_scored",
      tests=P8),
    M("P8-cited-filter-ignored", BOTS, ("if state.evidence.get(i) is not None and (only is None or i in only)}", "if state.evidence.get(i) is not None}"),
      "each_axis_is_scored", tests=P8),
    M("P8-report-window-ignored", GAME, ("and overlaps(tuple(acc.interval), tuple(attack.interval))", "and True"), "each_axis_is_scored", tests=P8),
    M("P8-web-confirmation-unchecked", WEB, ('            if form.get("confirm") != "on":', "            if False:"), "without_confirmation", tests=P8),
    M("P8-web-game-name-unchecked", WEB, ("        return bool(NAME.fullmatch(name)) and not _RESERVED.fullmatch(name)", "        return True"), "hostile_game_name",
      tests=P8),
    M("P8-web-case-outside-the-library", WEB, ("        if not self.valid_name(name) or case not in self.cases():", "        if not self.valid_name(name):"),
      "only_a_library_case", tests=P8),
    M("P8-web-field-unvalidated", WEB, ("    if value not in allowed:\n        raise ValueError", "    if False:\n        raise ValueError"), "crafted_form", tests=P8),
    M("P8-web-cross-site-post-accepted", WEB, ('    return origin is None or origin in request.app.state.origins', "    return True"),
      "cross_site_post", tests=P8),
    M("P8-web-tampered-save-crashes-the-page", WEB, ("        except SaveRefusal:                             # a damaged or forged save",
                                                     "        except ZeroDivisionError:                       # a damaged or forged save"),
      "tampered_save", tests=P8),
    M("P8-web-empty-search-target", WEB, ('            if target is None:\n                raise ValueError("nothing to search")',
                                          '            if False:\n                raise ValueError("nothing to search")'), "crafted_form", tests=P8),
    M("P8-web-chat-rate-window-unfed", WEB, ("            times.append(chat.clock())", "            pass"), "rate_window_throttles", tests=P8),
    M("P8-web-chat-without-a-model", WEB, ('            if chat is None:\n                raise ValueError("no model',
                                           '            if False:\n                raise ValueError("no model'), "without_a_model", tests=P8),
    M("P8-web-unheld-presentation", WEB, ('            if raw and present is None:\n                raise ValueError("not held")',
                                          '            if False:\n                raise ValueError("not held")'), "crafted_form", tests=P8),
    # ---- the Phase 8 repair (H8-B1): the player reasons over UNLOCKED implications only ----
    M("P8-B1-plain-board-reads-locked", HYP, ("        for imp in unlocked_implications(ev, known):\n            if not _shares_entity(imp.proposition, prop):",
                                              "        for imp in ev.implications:\n            if not _shares_entity(imp.proposition, prop):"),
      "locked_implication_is_neither", tests=HYPT),
    M("P8-B1-lied-board-reads-locked", HYP, ("        for imp in unlocked_implications(ev, known):\n            if any(contradiction(imp.proposition, c.proposition)",
                                             "        for imp in ev.implications:\n            if any(contradiction(imp.proposition, c.proposition)"),
      "lied_theory_is_not_corroborated", tests=HYPT),
    M("P8-B1-planted-target-not-unlocked", HYP, ("    target = unlocked_view(target, discovery)\n", ""), "planted_theory_is_not_corroborated", tests=HYPT),
    M("P8-B1-planted-other-not-unlocked", HYP, ("evidence_vs_evidence(target, unlocked_view(other, discovery))", "evidence_vs_evidence(target, other)"),
      "planted_theory_is_not_corroborated", tests=HYPT),
    M("P8-B1-board-strength-floor-dropped", HYP, ('            elif evidence_implication_contradicts(imp, prop, imp_id=eid, other_id="hypothesis") is not None:',
                                                  "            else:"), "weaker_than_half", tests=HYPT),
    M("P8-B1-accounts-do-not-unlock", DISC, ("    return state.known_evidence | state.known_statements | state.known_accounts\n\n\ndef unlocked_view",
                                             "    return state.known_evidence | state.known_statements\n\n\ndef unlocked_view"),
      "locked_implication_is_neither", tests=HYPT),
    M("P8-B1-unlocked-view-is-the-whole-item", DISC, ('    return evidence.model_copy(update={"implications": tuple(unlocked_implications(evidence, held_material(state)))})',
                                                       "    return evidence"), "planted_theory_is_not_corroborated", tests=HYPT),
    M("P8-B1-tension-items-unfiltered", GAME, ("    found = [unlocked_view(st.evidence.get(e), st.discovery) for e in sorted(st.discovery.known_evidence)]   # H8-B1: unlocked only",
                                               "    found = [st.evidence.get(e) for e in sorted(st.discovery.known_evidence)]"),
      "H8_B1_a_locked or H8_B1_a_tension or H8_B1_the_rendered", ["H8_B1_a_locked", "H8_B1_a_tension", "H8_B1_the_rendered"], tests=P8),
    M("P8-B1-claim-vs-implication-reads-locked", GAME, ("for imp in ev.implications):\n                pairs[(a, ev.id)] = None",
                                                        "for imp in st.evidence.get(ev.id).implications):\n                pairs[(a, ev.id)] = None"),
      "H8_B1_a_locked or H8_B1_the_rendered", ["H8_B1_a_locked", "H8_B1_the_rendered"], tests=P8),
    M("P8-B1-evidence-vs-evidence-reads-locked", GAME, ("            if evidence_vs_evidence(e1, e2, case):        # §13.1",
                                                        "            if evidence_vs_evidence(st.evidence.get(e1.id), st.evidence.get(e2.id), case):        # §13.1"),
      "H8_B1_a_tension", tests=P8),
    M("P8-B1-form-vocabulary-reads-locked", GAME, ("            names = names.union(names_from_evidence(st.case, unlocked_view(ev, st.discovery)))",
                                                   "            names = names.union(names_from_evidence(st.case, ev))"), "form_vocabulary", tests=P8),
    # ---- the Phase 8 repair (H8-I1): a search hint names nothing the player has not seen ----
    M("P8-I1-hint-prints-the-evidence-id", EXPL, ('        "EvidenceFound": "Something else would have to turn up first.",', '        "EvidenceFound": f"You would need to find {p.ref} first.",'),
      "no_search_hint_in_any_sealed_case or no_page_of_a_search_sweep or denial_that_puts", ["no_search_hint_in_any_sealed_case"], tests=P8),
    M("P8-I1-hint-prints-the-statement-id", EXPL, ('        "StatementHeard": "Someone would have to tell you something first.",', '        "StatementHeard": f"Someone would have to tell you about {p.ref} first.",'),
      "names_a_place_or_an_object", tests=EXPT),
    M("P8-I1-hint-prints-the-kit-ref", EXPL, ('else "You need something you do not have yet for that.",', 'else f"You need {p.ref} for that.",'),
      "names_a_place_or_an_object or without_kit", ["names_a_place_or_an_object", "without_kit"], tests=EXPT),
    M("P8-I1-hint-prints-the-place-ref", EXPL, ('else "You would need to know more about this place first.",', 'else f"You would need to know about {p.ref} first.",'),
      "names_a_place_or_an_object", tests=EXPT),
    M("P8-I1-hint-ignores-the-display-name", EXPL, ('f"You need {kit.name} for that." if kit else', 'f"You need something you do not have yet for that." if kit else'),
      "names_a_place_or_an_object", tests=EXPT),
    M("P8-I1-runner-forgets-the-case", TURN, ("exploration_search(state.evidence, state.discovery, target, action, turn_id, state.case)",
                                              "exploration_search(state.evidence, state.discovery, target, action, turn_id)"),
      "search_runner_hands_the_case", tests=P8),
    # ---- the Phase 8 repair (H8-I2): the Host is judged against the loopback allow-list, the Origin against its origins ----
    M("P8-I2-host-not-checked", WEB, ('        if scope["type"] == "http" and Headers(scope=scope).get("host", "").lower() not in self.hosts:', "        if False:"),
      "rebound_host_is_refused or allow_list_is_the_loopback", ["rebound_host_is_refused", "allow_list_is_the_loopback"], tests=P8),
    M("P8-I2-origin-compared-with-host", WEB, ("    return origin is None or origin in request.app.state.origins",
                                               '    return origin is None or origin.split("://", 1)[-1] == request.headers.get("host")'),
      "allow_list_is_the_loopback", tests=P8),
    M("P8-I2-any-port-accepted", WEB, ('    return frozenset(f"{h}:{port}" for h in LOOPBACK) |', '    return frozenset(f"{h}:{p}" for h in LOOPBACK for p in range(1, 10000)) |'),
      "allow_list_is_the_loopback", tests=P8),
    M("P8-I2-bare-host-accepted", WEB, ("(frozenset(LOOPBACK) if port == 80 else frozenset())", "frozenset(LOOPBACK)"), "allow_list_is_the_loopback", tests=P8),
    M("P8-I2-host-compared-case-sensitively", WEB, ('Headers(scope=scope).get("host", "").lower() not in self.hosts', 'Headers(scope=scope).get("host", "") not in self.hosts'),
      "allow_list_is_the_loopback", tests=P8),
    M("P8-I2-serve-ignores-its-port", CLI, ("create_app(args.saves, args.cases, port=args.port, **live)", "create_app(args.saves, args.cases, **live)"),
      "cli_serves_the_player_app", tests=P8),
    # ---- the Phase 8 repair (H8-I3): one save, one writer; the store has the last word on a duplicate ----
    M("P8-I3-other-spelling-opens-a-second-save", WEB, ("        if not self.valid_name(name) or name not in self.saves():", "        if not self.valid_name(name):"),
      "second_spelling_of_a_game or one_rate_window", ["second_spelling_of_a_game", "one_rate_window"], tests=P8),
    M("P8-I3-commit-ignores-the-append-result", GAME, ("    if not got.appended:", "    if False:"), "store_detects_but_this_save_missed", tests=P8),
    M("P8-I3-a-different-action-under-a-reused-id-is-a-duplicate", GAME, ("if got.same_events else Outcome(", "if True else Outcome("),
      "store_detects_but_this_save_missed", tests=P8),
]

# Mutants that are redundant by construction (not run). Each says what else already refuses the same input.
EQUIVALENT = {
    "X23 no minds rows outside a conversation": "a missing `chars[who]` / the statement-required rule refuses the same rows",
    "X26 one TurnCommitted per turn": "`_fold_turn` has no fold for a second bracket and the duplicate-row rule also refuses it",
    "X31 payload kind equals column kind": "the pydantic `Literal` on every payload's `kind` refuses it",
    "two statements in one turn": "a statement id is forced to S{turn} (`_check_statement`), so a second statement always clashes in `apply_decision`; the guard only gives the refusal a clearer message",
    "float range 0<=x<=1": "implied by the basis-point grid check (`bp` clamps, so an out-of-range x can never equal its own grid point)",
    "P8 web: an unresolvable cited handle": "`web.dispatch` maps it to None; `run_accusation_turn` refuses a citation outside the held set "
                                            "(UNHELD_CITATION, mutant P8-runner-unheld-citation) and the fold refuses it again",
    "P8 control: stale expected_seq": "`game._commit`'s check only names the outcome early; `Save.append` raises StaleAppend on the "
                                      "same input and `_commit` maps that to the same `stale` outcome",
    "P8 session: murderer from the declared solution": "for every sealed case `load_sealed_text` requires solution.murderer == the "
                                                        "proof's unique survivor (PI-7), so the two spellings are equal on every save",
}


def _copy_tree(dst: pathlib.Path) -> None:
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")
    for d in ("eidolon", "tests", "cases"):
        shutil.copytree(ROOT / d, dst / d, ignore=ignore)
    for f in ("pyproject.toml",):
        if (ROOT / f).exists():
            shutil.copy(ROOT / f, dst / f)


def _pytest(cwd, tests, *args, timeout=3600):
    tests = [tests] if isinstance(tests, str) else list(tests)
    return subprocess.run([sys.executable, "-m", "pytest", *tests, "-q", "-p", "no:cacheprovider", *args], cwd=cwd,
                          capture_output=True, text=True, timeout=timeout)


def _run_mutant(workdir: pathlib.Path, m) -> tuple[str, str]:
    """-> (verdict, why). verdict in killed / SURVIVED / BAD."""
    target = workdir / m["file"]
    original = target.read_text(encoding="utf-8")
    try:
        mutated = original
        for old, new in m["edits"]:
            if mutated.count(old) != 1:
                return "BAD", f"anchor found {mutated.count(old)}x: {old[:60]!r}"
            mutated = mutated.replace(old, new)
        collect = _pytest(workdir, m["tests"], "--collect-only", "-k", m["k"])
        if collect.returncode != 0 or not re.search(r"\d+ tests? collected|^\S+::", collect.stdout, re.M):
            return "BAD", "the test selection collects nothing unmutated"
        target.write_text(mutated, encoding="utf-8")
        r = _pytest(workdir, m["tests"], "-x", "-rf", "-k", m["k"])
        if r.returncode == 0:
            return "SURVIVED", "the selected tests still pass"
        if r.returncode != 1:
            return "BAD", f"pytest exit {r.returncode} is not a test failure: {(r.stdout + r.stderr)[-200:]!r}"
        failed = re.findall(r"^FAILED (\S+)", r.stdout, re.M)
        if not any(any(n in f for n in m["fail"]) for f in failed):
            return "SURVIVED", f"killed by the WRONG test: {failed[:2]} (wanted {m['fail']})"
        return "killed", failed[0].split("::")[-1][:70]
    finally:
        target.write_text(original, encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-j", "--jobs", type=int, default=4)
    ap.add_argument("-k", default="", help="only mutants whose name contains this (comma-separated: any of these)")
    args = ap.parse_args(argv)
    todo = [m for m in MUTANTS if any(k in m["name"] for k in args.k.split(","))]
    names = [m["name"] for m in MUTANTS]
    assert len(names) == len(set(names)), "duplicate mutant names"
    before = {f: (ROOT / f).read_bytes() for f in {m["file"] for m in MUTANTS}}
    with tempfile.TemporaryDirectory(prefix="eidolon-mut-") as tmp:
        workers = []
        for i in range(args.jobs + 1):
            w = pathlib.Path(tmp) / f"w{i}"
            _copy_tree(w)
            workers.append(w)
        results: dict[str, tuple[str, str]] = {}
        with cf.ThreadPoolExecutor(max_workers=args.jobs + 1) as pool:
            baseline = pool.submit(_pytest, workers[0], sorted({m["tests"] for m in todo}))   # the green-baseline gate
            futures = {}
            queues = [todo[i::args.jobs] for i in range(args.jobs)]

            def drain(i):
                for m in queues[i]:
                    try:
                        results[m["name"]] = _run_mutant(workers[i + 1], m)
                    except Exception as e:                                # noqa: BLE001 - a timeout / worker fault is a verdict, not a crash
                        results[m["name"]] = ("ERROR", f"{type(e).__name__}: {e}"[:200])
                    v, why = results[m["name"]]
                    print(f"{v:8} {m['name']:46} {why}", flush=True)
            for i in range(args.jobs):
                futures[i] = pool.submit(drain, i)
            for f in futures.values():
                f.result()
            base = baseline.result()
    if base.returncode != 0:
        print(f"BASELINE IS NOT GREEN (pytest exit {base.returncode}): nothing above is evidence.\n{base.stdout[-1500:]}")
        return 2
    assert all((ROOT / f).read_bytes() == b for f, b in before.items()), "a source file changed"
    bad = {n: r for n, r in results.items() if r[0] != "killed"}
    for n, why in EQUIVALENT.items():
        print(f"equivalent  {n}: {why}")
    tally = {v: sum(1 for r in results.values() if r[0] == v) for v in ("killed", "SURVIVED", "BAD", "ERROR")}
    print(f"baseline green; {tally['killed']} killed, {tally['SURVIVED']} survived, {tally['BAD']} malformed, "
          f"{tally['ERROR']} infrastructure errors, {len(EQUIVALENT)} justified equivalent")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
