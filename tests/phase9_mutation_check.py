"""Mutation check for the Phase 9 guards (`eidolon/trace.py`, the trace sink in `store.py`, the producer in `game.py`/`web.py`,
`eidolon/debug/*`, the T-25/T-26 properties in `llm/render.py`/`decision/strategy.py`, the corpus boundary in `llm/ingress.py`).
Same rules and the same engine as `tests/persistence_mutation_check.py`:

    python -m tests.phase9_mutation_check            # all mutants (4 workers)
    python -m tests.phase9_mutation_check -j 8 -k trace-
    python -m tests.phase9_mutation_check -k EQ      # list nothing: equivalents are justified in EQUIVALENT, not run

* a GREEN-BASELINE GATE: the unmutated selection must pass, or nothing is reported (exit 2);
* every mutant's anchor must match EXACTLY once (else it is BAD, i.e. malformed) and its test selection must collect tests;
* KILLED FOR THE RIGHT REASON: pytest must exit 1 and a failing test id must contain one of the mutant's `fail` names;
* mutants run in private copies of the tree, so the real sources are never touched.

The report keeps the five outcomes apart: killed / survived / malformed (BAD) / infrastructure error (ERROR) / justified
equivalent.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import pathlib
import shutil
import sys
import tempfile

from tests.persistence_mutation_check import ROOT, _pytest, _run_mutant

TRACE, STORE, GAME, WEB, INGRESS, RENDER, STRAT = ("eidolon/trace.py", "eidolon/store.py", "eidolon/game.py", "eidolon/web.py",
                                                   "eidolon/llm/ingress.py", "eidolon/llm/render.py", "eidolon/decision/strategy.py")
SLO, AUDIT, NIGHTLY, APP, FAKES = ("eidolon/debug/slo.py", "eidolon/debug/audit.py", "eidolon/debug/nightly.py", "eidolon/debug/app.py",
                                   "eidolon/llm/fakes.py")
PROMPTDOC = "eidolon/debug/promptdoc.py"
T_TRACE, T_CORPUS, T_SUITES = "tests/test_phase9_trace.py", "tests/test_phase9_corpus.py", "tests/test_phase9_suites.py"
T_REP = "tests/test_phase9_repairs.py"
T_OBS, T_DEBUG, T_NIGHT, T_DOCS = ("tests/test_phase9_observability.py", "tests/test_phase9_debug.py", "tests/test_phase9_nightly.py",
                                   "tests/test_phase9_docs.py")
TURN = "eidolon/decision/turn.py"


def M(name, file, edits, k, fail, tests):
    edits = [edits] if isinstance(edits, tuple) else edits
    return dict(name=name, file=file, edits=edits, k=k, fail=tuple(fail), tests=tests)


MUTANTS = [
    # ---- the TurnTrace model (§27.1): typed, bounded, coherent -----------------------------------------------------
    M("trace-model-allows-extra-fields", TRACE, ('model_config = ConfigDict(frozen=True, extra="forbid", strict=True)', 'model_config = ConfigDict(frozen=True, extra="ignore", strict=True)'),
      "invalid_trace_is_refused", ["invalid_trace_is_refused"], T_TRACE),
    M("trace-model-not-strict", TRACE, ('model_config = ConfigDict(frozen=True, extra="forbid", strict=True)', 'model_config = ConfigDict(frozen=True, extra="forbid")'),
      "invalid_trace_is_refused", ["invalid_trace_is_refused"], T_TRACE),
    M("trace-coherence-dropped", TRACE, ('if done != (self.turn_id is not None) or done != (self.committed is not None):', 'if False:'),
      "invalid_trace_is_refused", ["invalid_trace_is_refused"], T_TRACE),
    M("trace-fallback-flag-and-outcome-need-not-agree", TRACE, ('if self.fallback_used != (self.outcome == "committed_fallback"):', 'if False:'),
      "invalid_trace_is_refused", ["invalid_trace_is_refused"], T_TRACE),
    M("trace-size-bound-unchecked", TRACE, ('if len(self.model_dump_json()) > MAX_TRACE_BYTES:', 'if False:'),
      "size_bound_is_enforced", ["size_bound_is_enforced"], T_TRACE),
    M("trace-violation-detail-kept", TRACE, ('    return out[:96]\n\n\n# ------', '    return v[:96]\n\n\n# ------'),
      "validation_failure_that_a_repair_cures", ["validation_failure_that_a_repair"], T_TRACE),
    M("trace-handles-not-hashed", TRACE, ('    return hashlib.sha256(f"{seal}|{ident}".encode()).hexdigest()[:12]', '    return ident'),
      "every_control_commits or ask_trace_records_every_stage", ["every_control_commits", "ask_trace_records_every_stage"], T_TRACE),
    # ---- scrubbing: canary, credentials, engine ids, clamping -----------------------------------------------------
    M("scrub-leaves-the-canary", TRACE, ('text = _CREDENTIAL.sub("[secret]", _CANARY_RE.sub("[canary]", text))', 'text = _CREDENTIAL.sub("[secret]", text)'),
      "scrubber_clamps or leaking_model or credential", ["scrubber_clamps", "leaking_model", "credential"], T_TRACE),
    M("scrub-leaves-credentials", TRACE, ('text = _CREDENTIAL.sub("[secret]", _CANARY_RE.sub("[canary]", text))', 'text = _CANARY_RE.sub("[canary]", text)'),
      "credential or scrubber_clamps", ["credential", "scrubber_clamps"], T_TRACE),
    M("scrub-leaves-engine-ids", TRACE, ('    for token in {c for t in _TOKEN.findall(text) for c in (t, t.strip(".:-")) if c in ids}:', '    for token in ():'),
      "scrubber_clamps or no_engine_identifier", ["scrubber_clamps", "no_engine_identifier"], T_TRACE),
    M("scrub-ignores-trailing-punctuation", TRACE, ('for c in (t, t.strip(".:-")) if c in ids}', 'for c in (t,) if c in ids}'),
      "scrubber_clamps", ["scrubber_clamps"], T_TRACE),
    M("scrub-does-not-clamp", TRACE, ('    return text[:limit]', '    return text'), "scrubber_clamps", ["scrubber_clamps"], T_TRACE),
    M("engine-ids-forget-evidence", TRACE, ('    ids.update(e.id for e in state.evidence.all())\n', ''), "no_engine_identifier", ["no_engine_identifier"], T_TRACE),
    M("engine-ids-forget-statements", TRACE, ('        ids.add(st.id)\n        ids.update(c.id for c in st.claims)\n', ''), "no_engine_identifier", ["no_engine_identifier"], T_TRACE),
    M("engine-ids-forget-beliefs", TRACE, ('        ids.update(b.id for b in state.beliefs.for_character(who))\n', '        pass\n'), "no_engine_identifier", ["no_engine_identifier"], T_TRACE),
    M("engine-ids-forget-memories", TRACE, ('        ids.update(m.id for m in mems)\n', '        pass\n'), "no_engine_identifier", ["no_engine_identifier"], T_TRACE),
    M("engine-ids-forget-knowledge", TRACE, ('    ids.update(k.id for k in state.knowledge.all())\n', ''), "no_engine_identifier", ["no_engine_identifier"], T_TRACE),
    M("engine-ids-forget-secrets", TRACE, ('        ids.add(sec.id)\n', ''), "no_engine_identifier", ["no_engine_identifier"], T_TRACE),
    M("engine-ids-forget-cover-claims", TRACE, ('            ids.update(c.id for c in layer.claims)\n', ''), "no_engine_identifier", ["no_engine_identifier"], T_TRACE),
    M("sink-does-not-scrub", STORE, ('text = _canon(scrub_secrets(_plain(trace)))', 'text = _canon(_plain(trace))'), "sink_scrubs", ["sink_scrubs"], T_TRACE),
    M("sink-scrubs-the-json-not-its-strings", STORE, ('text = _canon(scrub_secrets(_plain(trace)))', 'text = _canon(_plain(trace))\n            text = _SECRET_RE.sub("[secret]", _CANARY_RE.sub("[canary]", text))'),
      "sink_scrubs", ["sink_scrubs"], T_TRACE),
    # ---- failure safety: the trace is best-effort and AFTER the commit ----------------------------------------------
    M("trace-write-failure-propagates", STORE, ('            logging.getLogger("eidolon.trace").warning("trace not written: %s", type(exc).__name__)\n            return False',
                                                '            raise'), "trace_write_failure_after or append_reports", ["trace_write_failure_after", "append_reports"], T_TRACE),
    M("trace-failure-logged-with-its-message", STORE, ('logging.getLogger("eidolon.trace").warning("trace not written: %s", type(exc).__name__)',
                                                       'logging.getLogger("eidolon.trace").warning("trace not written: %s", exc)'),
      "trace_failure_message_never_reaches or sink_logs_a_failure", ["trace_failure_message_never_reaches", "sink_logs_a_failure"], T_TRACE),
    M("trace-builder-failure-propagates", GAME, ('    except Exception as exc:                                             # noqa: BLE001 - best effort, by contract\n        logging.getLogger("eidolon.trace").warning("trace not built or written: %s", type(exc).__name__)\n        return False',
                                                 '    except KeyboardInterrupt:\n        return False'), "trace_builder_that_raises", ["trace_builder_that_raises", "trace_writer_that_raises"], T_TRACE),
    M("trace-write-failure-not-reported", STORE, ('        written = self.write_trace(turn, trace) if trace is not None else None', '        written = True if trace is not None else None'),
      "append_reports", ["append_reports"], T_TRACE),
    M("aborted-attempts-not-recorded", GAME, ('    return _traced(save.write_aborted, save, res,', '    return False and _traced(save.write_aborted, save, res,'),
      "aborted_attempt or fold_refusal or clarify_and_blocked", ["aborted_attempt", "fold_refusal", "clarify_and_blocked"], T_TRACE),
    M("committed-turn-not-traced", GAME, ('    _traced(lambda row: save.write_trace(got.ref.turn, row), save, res,', '    False and _traced(lambda row: save.write_trace(got.ref.turn, row), save, res,'),
      "every_control_commits or ask_trace_records", ["every_control_commits", "ask_trace_records"], T_TRACE),
    M("duplicate-submissions-traced", GAME, ('    if not got.appended:\n        return _already(got.ref, chip) if got.same_events else Outcome("stale", _STALE, chip)',
                                             '    if not got.appended:\n        note_attempt(save, kind=kind, outcome="rejected", character=character, observed=observed, res=res)\n        return _already(got.ref, chip) if got.same_events else Outcome("stale", _STALE, chip)'),
      "stale_and_duplicate or duplicate_only_the_store", ["stale_and_duplicate", "duplicate_only_the_store"], T_TRACE),
    M("trace-not-bound-to-the-commit", TRACE, ('first_seq=committed.ref.first_seq, last_seq=committed.ref.last_seq, head_hash=save.last_hash,', 'first_seq=committed.ref.first_seq, last_seq=committed.ref.last_seq, head_hash="0" * 64,'),
      "final_accusation_is_traced", ["final_accusation_is_traced"], T_TRACE),
    M("parse-calls-charged-to-the-next-turn", WEB, ('            calls = chat.parser.transport.drain()          # the parse-stage calls, charged to THIS line and no other', '            calls = ()'),
      "clarify_and_blocked or typed_line_traces", ["clarify_and_blocked", "typed_line_traces"], T_TRACE),
    M("a-refusal-with-no-reason-code-has-no-failure-kind", TRACE, ('    if outcome == "rejected" and not fails:\n        fails = ("rejected_action",)', '    if False:\n        fails = ("rejected_action",)'),
      "every_kind_of_refused_control", ["every_kind_of_refused_control"], T_TRACE),
    M("an-engine-gate-refusal-is-called-an-action-refusal", TRACE, ('        elif audit is None or audit.outcome == "rejected":\n            out.append("plan_rejected")', '        elif audit is None or audit.outcome == "rejected":\n            out.append("rejected_action")'),
      "plan_rejected_is_not_an_action", ["plan_rejected_is_not_an_action"], T_TRACE),
    M("refusal-counted-as-validation-failure", TRACE, ('"refused": "provider_refusal", "malformed": "malformed_output", "repair": "validation_failure",', '"refused": "validation_failure", "malformed": "malformed_output", "repair": "validation_failure",'),
      "model_refusal_is_not", ["model_refusal_is_not"], T_TRACE),
    M("transport-timeout-not-told-apart", TRACE, ('"ProviderTimeout": "provider_timeout",', '"ProviderTimeout": "provider_error",'), "provider_and_output_failures_are_told_apart", ["provider_and_output_failures_are_told_apart"], T_TRACE),
    M("fallback-not-recorded", TRACE, ('    fb = bool(getattr(res, "fallback", False)) and outcome in COMMITTED', '    fb = False'), "provider_and_output_failures_are_told_apart or model_refusal", ["provider_and_output_failures", "model_refusal"], T_TRACE),
    M("stage-data-not-captured", TURN, ('    plan, scored = select_plan(inp)\n', '    plan, scored = select_plan(inp)\n    scored = []\n'), "scores_are_integers or ask_trace_records", ["scores_are_integers", "ask_trace_records"], T_TRACE),
    # ---- the player process cannot reach the debug package (I-10) ---------------------------------------------------
    M("player-app-serves-a-trace-route", WEB, ('Route("/g/{name}/report", report)]', 'Route("/g/{name}/report", report), Route("/g/{name}/turns", index)]'),
      "http_probe_the_player_app or player_app_serves_no_trace", ["http_probe_the_player_app", "player_app_serves_no_trace"], T_DEBUG),
    M("player-stack-imports-the-debug-package", GAME, ('CLOCK = time.monotonic', 'import eidolon.debug  # noqa\nCLOCK = time.monotonic'),
      "nothing_outside_the_debug or importing_the_whole_player_stack", ["nothing_outside_the_debug", "importing_the_whole_player_stack"], T_DEBUG),
    # ---- the debug server --------------------------------------------------------------------------------------------
    M("debug-server-starts-unasked", APP, ('if env.get("EIDOLON_DEBUG") != "1":', 'if False:'), "does_not_start_unless_asked", ["does_not_start_unless_asked"], T_DEBUG),
    M("debug-server-accepts-any-method", APP, ('return Route(path, guarded(view), methods=["GET"])', 'return Route(path, guarded(view), methods=["GET", "POST"])'), "nothing_but_get", ["nothing_but_get"], T_DEBUG),
    M("debug-server-answers-any-host", APP, ('middleware=[Middleware(_LoopbackOnly, hosts=allowed_hosts(port))]', 'middleware=[]'), "loopback_names_on_the_served_port", ["loopback_names_on_the_served_port"], T_DEBUG),
    M("debug-server-opens-bad-names", APP, ('if not NAME.fullmatch(name) or not p.is_file():', 'if not p.is_file():'), "hostile_name_is_not_found or tampered_save", ["hostile_name_is_not_found", "tampered_save"], T_DEBUG),
    M("debug-server-does-not-bind-traces-to-the-log", APP, ('ok = t.committed.head_hash == heads.get(t.committed.last_seq) and t.committed.case == save.bundle.package.seal[:16]', 'ok = True'),
      "foreign_trace_file", ["foreign_trace_file"], T_DEBUG),
    M("debug-handles-not-resolved", APP, ('return f"{table_[x]}  [{x}]" if x in table_ else x', 'return x'), "turn_inspector_shows_the_stages", ["turn_inspector_shows_the_stages"], T_DEBUG),
    # ---- SLOs --------------------------------------------------------------------------------------------------------
    M("slo-fallback-bound-inclusive", SLO, ('"PASS" if bp < FALLBACK_MAX_BP else "FAIL"', '"PASS" if bp <= FALLBACK_MAX_BP else "FAIL"'), "fallback_rate_threshold", ["fallback_rate_threshold"], T_OBS),
    M("slo-drafts-bound-inclusive", SLO, ('"PASS" if mean_c < DRAFTS_MAX_CENTI else "FAIL"', '"PASS" if mean_c <= DRAFTS_MAX_CENTI else "FAIL"'), "mean_drafts_per_turn_threshold", ["mean_drafts_per_turn_threshold"], T_OBS),
    M("slo-flatness-never-fails", SLO, ('"PASS" if ratio <= FLAT_RATIO else "FAIL"', '"PASS"'), "tokens_per_turn_must_be_flat", ["tokens_per_turn_must_be_flat"], T_OBS),
    M("slo-no-model-turn-reads-as-pass", SLO, ('m.append(Metric(name, None, target, "UNMEASURED", "no model-rendered turn in the traces"))', 'm.append(Metric(name, 0, target, "PASS", "no model-rendered turn in the traces"))'),
      "empty_population_measures_nothing", ["empty_population_measures_nothing"], T_OBS),
    M("slo-peel-without-breaker-ignores-presented", SLO, ('and not t.assessment.presented and t.view', 'and t.view'), "peel_with_nothing_ever_presented", ["peel_with_nothing_ever_presented"], T_OBS),
    M("slo-peel-without-breaker-ignores-history", SLO, ('and t.view.detective_evidence + t.view.detective_statements == 0]', 'and True]'), "peel_with_nothing_ever_presented", ["peel_with_nothing_ever_presented"], T_OBS),
    M("slo-unreadable-rows-trusted", SLO, ('        except ValueError:\n            bad += 1', '        except ValueError:\n            pass'), "rows_that_are_not_traces", ["rows_that_are_not_traces"], T_OBS),
    M("slo-cost-guessed", SLO, ('"REPORTED" if priced else "UNMEASURED", "" if priced else "no price table', '"REPORTED", "" if priced else "no price table'), "latency_percentiles_cache_ratio_and_cost", ["latency_percentiles_cache_ratio_and_cost"], T_OBS),
    # ---- the offline audit -------------------------------------------------------------------------------------------
    M("audit-forbidden-vocab-off", AUDIT, ('    hard += [f"FORBIDDEN_VOCAB:{w}" for w in FORBIDDEN_VOCAB if w in low]\n', ''), "every_text_level_leak_class", ["every_text_level_leak_class"], T_OBS),
    M("audit-canary-off", AUDIT, ('    if CANARY.lower() in low:\n        hard.append("CANARY_LEAK")\n', ''), "every_text_level_leak_class", ["every_text_level_leak_class"], T_OBS),
    M("audit-denies-only-some-ids", AUDIT, ('found = leaked_tokens(text, ids | set(ACT_TABLE)) + [w for w in ENGINE_VOCAB if w in low]', 'found = [w for w in ENGINE_VOCAB if w in low]'),
      "every_text_level_leak_class or id_the_runtime_would_not", ["every_text_level_leak_class", "id_the_runtime_would_not"], T_OBS),
    M("audit-invented-names-off", AUDIT, ('    if invented:\n        hard.append("INVENTED_NAME")\n', ''), "every_text_level_leak_class", ["every_text_level_leak_class"], T_OBS),
    M("audit-times-off", AUDIT, ('    if set(_CLOCK.findall(text)) - allowed_times or _TIME_WORDS.search(text):\n        hard.append("TIME_NOT_IN_CLAIMS")\n', ''), "every_text_level_leak_class", ["every_text_level_leak_class"], T_OBS),
    M("audit-confession-off", AUDIT, ('    if stmt.act != "CONFESSION" and _CONFESSES.search(text):', '    if False:'), "every_text_level_leak_class", ["every_text_level_leak_class"], T_OBS),
    M("audit-lie-tell-off", AUDIT, ('    if stmt.act not in ("CONFESSION", "CONCESSION", "CORRECTION") and _LIE_TELLS.search(text):', '    if False:'), "every_text_level_leak_class", ["every_text_level_leak_class"], T_OBS),
    M("audit-solution-outside-confession-off", AUDIT, ('    if stmt.act != "CONFESSION" and any(c.proposition.kind == "Solution" for c in stmt.claims):', '    if False:'),
      "solution_claim_outside_a_confession", ["solution_claim_outside_a_confession"], T_OBS),
    M("audit-leak-check-off", AUDIT, ('    hard += list(leak_violations(', '    _ = list(leak_violations('), "solution_claim_outside_a_confession", ["solution_claim_outside_a_confession"], T_OBS),
    M("audit-protected-phrase-off", AUDIT, ('        for sec in state.secrets.for_owner(stmt.speaker):\n            if sec.id in never_peeled:', '        for sec in ():\n            if sec.id in never_peeled:'),
      "never_conceded_protected_fact", ["never_conceded_protected_fact"], T_OBS),
    M("audit-protected-phrase-ignores-concession", AUDIT, ('    if stmt.act not in REVEAL_ACTS:\n        for sec in', '    if True:\n        for sec in'), "never_conceded_protected_fact", ["never_conceded_protected_fact"], T_OBS),
    M("audit-verifier-ignored", AUDIT, ('            hard += [f"VERIFIER:{v}" for v in verifier(stmt, state)]', '            verifier(stmt, state)'), "stronger_verifier_is_a_port", ["stronger_verifier_is_a_port"], T_OBS),
    M("audit-verifier-failure-hides-as-clean", AUDIT, ('            review.append("VERIFIER_UNAVAILABLE")', '            pass'), "verifier_that_cannot_be_reached", ["verifier_that_cannot_be_reached"], T_OBS),
    M("audit-small-sample-judged", AUDIT, ('if self.sampled < MIN_AUDIT or (self.verifier_used and self.verifier_errors):', 'if self.sampled < 1:'), "threshold_is_half_a_percent or sample_is_deterministic", ["threshold_is_half_a_percent", "sample_is_deterministic"], T_OBS),
    M("audit-bound-inclusive", AUDIT, ('return "PASS" if self.rate_bp < MAX_BP else "FAIL"', 'return "PASS" if self.rate_bp <= MAX_BP else "FAIL"'), "threshold_is_half_a_percent", ["threshold_is_half_a_percent"], T_OBS),
    M("audit-sample-not-deterministic", AUDIT, ('order = sorted(stmts, key=lambda s: hashlib.sha256(f"{seed}|{seal}|{s.id}".encode()).hexdigest())', 'order = list(reversed(stmts))'),
      "sample_is_deterministic", ["sample_is_deterministic"], T_OBS),
    M("audit-fixtures-unstable-or-missing", AUDIT, ('        p.write_text(json.dumps(doc, indent=1, sort_keys=True), encoding="utf-8")', '        pass'), "discrepancy_is_filed", ["discrepancy_is_filed"], T_OBS),
    # ---- the nightly job: PASS/FAIL only from a real provider ---------------------------------------------------------
    M("nightly-any-client-is-live", NIGHTLY, ('            return type(getattr(transport, "_client", None)).__module__.split(".")[0] == "anthropic"', '            return True'),
      "nothing_but_the_real_sdk_client", ["nothing_but_the_real_sdk_client"], T_NIGHT),
    M("nightly-nothing-is-live", NIGHTLY, ('            return type(getattr(transport, "_client", None)).__module__.split(".")[0] == "anthropic"', '            return False'),
      "real_provider_is_recognised or live_run", ["real_provider_is_recognised", "live_run"], T_NIGHT),
    M("nightly-dry-run-claims-a-result", NIGHTLY, ('    if ok is None or not live:\n        return {**out, "status": "UNMEASURED"', '    if ok is None:\n        return {**out, "status": "UNMEASURED"'),
      "without_a_provider_every_metric", ["without_a_provider_every_metric"], T_NIGHT),
    M("nightly-budget-off-by-one", NIGHTLY, ('        if self.calls >= self.max_calls:\n            raise', '        if self.calls > self.max_calls:\n            raise'), "budgeted_transport_fails", ["budgeted_transport_fails"], T_NIGHT),
    M("nightly-incomplete-run-judged", NIGHTLY, ('    complete = committed == turns and not budget.exhausted', '    complete = True'), "budget_runs_out", ["budget_runs_out"], T_NIGHT),
    M("nightly-fail-exits-zero", NIGHTLY, ('    if "FAIL" in statuses:\n        return 1', '    if False:\n        return 1'), "live_run_fails", ["live_run_fails"], T_NIGHT),
    M("nightly-human-criterion-measured", NIGHTLY, ('"status": "UNMEASURED", "source": "human",', '"status": "PASS", "source": "human",'), "without_a_provider_every_metric", ["without_a_provider_every_metric"], T_NIGHT),
    M("nightly-live-suites-never-launched", NIGHTLY, ('    if live and run_suites:', '    if False:'), "launches_the_suites", ["launches_the_suites"], T_NIGHT),
    M("nightly-dry-run-launches-the-suites", NIGHTLY, ('    if live and run_suites:', '    if run_suites:'), "launches_the_suites", ["launches_the_suites"], T_NIGHT),
    M("nightly-audit-default-too-small-to-judge", NIGHTLY, ('DEFAULT_AUDIT_SAMPLE = 200 ', 'DEFAULT_AUDIT_SAMPLE = 100 '), "defaults_are_big_enough", ["defaults_are_big_enough"], T_NIGHT),
    M("cassette-source-unchecked", FAKES, ('    if source not in ("live", "scripted"):\n        raise ValueError', '    if False:\n        raise ValueError'), "scripted_cassette_can_never_pass", ["scripted_cassette_can_never_pass"], T_NIGHT),
    M("cassette-miss-falls-through", FAKES, ('            raise ProviderError("CASSETTE_MISS") from None', '            return Completion(text=\'{"segments": []}\', model="stale")'), "changed_prompt_is_a_miss", ["changed_prompt_is_a_miss"], T_NIGHT),
    # ---- the injection corpus, at the production boundary -------------------------------------------------------------
    M("ingress-fold-keeps-marks", INGRESS, ('    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)).casefold()', '    return unicodedata.normalize("NFKD", text).casefold()'),
      "stage_zero_classifies", ["stage_zero_classifies"], T_CORPUS),
    M("ingress-keeps-control-characters", INGRESS, ('        elif unicodedata.category(ch)[0] == "C":', '        elif False:'), "stage_zero_classifies", ["stage_zero_classifies"], T_CORPUS),
    M("ground-does-not-escalate-to-meta", INGRESS, ('kind = "meta" if ing.meta and action.query_kind not in ("meta", "coercion") else action.query_kind', 'kind = action.query_kind'),
      "stage_zero_classifies", ["stage_zero_classifies"], T_CORPUS),
    M("ingress-truncates-instead-of-refusing", INGRESS, ('    if len(raw) > MAX_CHARS:\n        return IngressResult(raw, "", blocked="TOO_LONG")', '    if False:\n        return IngressResult(raw, "", blocked="TOO_LONG")'),
      "length_cap_is_exact", ["length_cap_is_exact"], T_CORPUS),
    M("validator-accepts-whatever-the-model-says", RENDER, ('    def _validate(self, draft: Draft, req: RenderRequest, verify) -> ValidationResult:\n        return validate_draft(',
                                                           '    def _validate(self, draft: Draft, req: RenderRequest, verify) -> ValidationResult:\n        return ValidationResult(True, " ".join(s.text for s in draft.segments), tuple(c for s in draft.segments for c in s.claim_ids)) if True else validate_draft('),
      "every_line_is_contained", ["every_line_is_contained"], T_CORPUS),
    M("parse-schema-allows-present", INGRESS, ('    kind: Literal["ask", "search", "goto", "clarify"]\n    query_kind', '    kind: Literal["ask", "search", "goto", "clarify", "present"]\n    query_kind'),
      "obeying_parser_cannot_turn", ["obeying_parser_cannot_turn"], T_CORPUS),
    # ---- T-25 / T-26 and the §28.4 suites -------------------------------------------------------------------------------
    M("latency-floor-removed", RENDER, ('        if (wait := self.min_latency_s - (self.clock() - start)) > 0:\n            self.sleep(wait)', '        pass'),
      "t26_two_hundred_turns", ["t26_two_hundred_turns"], T_SUITES),
    M("verify-called-twice-on-a-lie", RENDER, ('            if result.ok:\n                attempts.append(AttemptRecord(n, "accepted", (), draft))', '            if result.ok:\n                if req.plan.act == "LIE":\n                    self.verify(draft, req.envelope, book)\n                attempts.append(AttemptRecord(n, "accepted", (), draft))'),
      "t26_two_hundred_turns", ["t26_two_hundred_turns"], T_SUITES),
    M("length-band-check-off", "eidolon/decision/validator.py", ('    violations += length_violations(draft, envelope, case)\n', ''),
      "pads_its_lies", ["pads_its_lies"], T_SUITES),
    M("render-view-carries-the-act", RENDER, ('    revise: tuple[str, ...] = ()\n\n\n@dataclass(frozen=True)\nclass Named:', '    revise: tuple[str, ...] = ()\n    act: str = ""\n\n\n@dataclass(frozen=True)\nclass Named:'),
      "differs_between_acts_only_in_the_delivery_directive", ["differs_between_acts_only_in_the_delivery_directive"], T_SUITES),
    M("repair-loop-disabled", RENDER, ('        for n in range(1 + self.max_repairs):', '        for n in range(1):'), "t25_a_long_session", ["t25_a_long_session"], T_SUITES),
    M("repair-feedback-empty", RENDER, ('    out: list[str] = []\n    for v in violations:\n        tpl', '    out: list[str] = []\n    for v in ():\n        tpl'), "t25_a_long_session", ["t25_a_long_session"], T_SUITES),
    M("repeat-prior-too-early", STRAT, ('    if inp.repeat_count >= 2 and inp.prior_claims:', '    if inp.repeat_count >= 1 and inp.prior_claims:'), "suite_2", ["suite_2"], T_SUITES),
    M("repeat-prior-too-late", STRAT, ('    if inp.repeat_count >= 2 and inp.prior_claims:', '    if inp.repeat_count >= 4 and inp.prior_claims:'), "suite_2", ["suite_2"], T_SUITES),
    M("refuse-never-escalates", STRAT, ('    if inp.repeat_count >= 5 and inp.state.refuse_streak < 2:', '    if False:'), "suite_2", ["suite_2"], T_SUITES),
    M("knowledge-probe-answers", STRAT, ('    if not inp.known_topic:\n        return Candidate(act="DONT_KNOW"', '    if False:\n        return Candidate(act="DONT_KNOW"'), "suite_7", ["suite_7"], T_SUITES),
    M("unknown-name-is-guessed", INGRESS, ('    if any(r is None for r in refs.values()) or (refs.get("location") and refs["location"].kind != "location"):\n        return Clarify("UNKNOWN_NAME")',
                                           '    if False:\n        return Clarify("UNKNOWN_NAME")'), "suite_8", ["suite_8"], T_SUITES),
    M("correct-detective-never-corrects", STRAT, ('    if inp.query.presupposes and inp.retrieved_claim is not None:', '    if False:'), "suite_6", ["suite_6"], T_SUITES),
    M("hypothetical-asserts-actual", STRAT, ('    if inp.query.kind == "hypothetical":\n        return Candidate(act="HYPOTHETICAL", delivery=DeliveryDirective("imagines"))', '    if False:\n        return None'),
      "suite_10", ["suite_10"], T_SUITES),
    # ---- the Phase 9 repair (docs/EIDOLON-PHASE-9-HOSTILE-REVIEW.md §10): H9-B1, H9-I1, H9-I2 -----------------------------
    M("H9-B1-repeat-prior-from-retrieval", STRAT, ('    if inp.repeat_count >= 2 and inp.prior_claims:\n        return Candidate(act="REPEAT_PRIOR", claims=inp.prior_claims,',
                                                   '    if inp.repeat_count >= 2 and inp.retrieved_claim is not None:\n        return Candidate(act="REPEAT_PRIOR", claims=(inp.retrieved_claim,),'),
      "H9_B1 or suite_2", ["H9_B1_a_lie_and_a_truth", "suite_2", "repeat_bot"], T_REP),
    M("H9-B1-repeat-prior-preference-dropped", STRAT, ('            return -REPEAT_PRIOR_PREFERENCE', '            return 0.0'),
      "H9_B1 or suite_2", ["H9_B1_a_lie_and_a_truth", "suite_2", "repeat_bot", "ceiling"], T_REP),
    M("H9-B1-refuse-preference-dropped", STRAT, ('            return -REFUSE_PREFERENCE', '            return 0.0'),
      "H9_B1 or suite_2", ["H9_B1_a_lie_and_a_truth", "suite_2", "repeat_bot", "ceiling"], T_REP),
    M("H9-B1-repeat-prior-preference-under-the-ceiling", STRAT, ('REPEAT_PRIOR_PREFERENCE = 1.4', 'REPEAT_PRIOR_PREFERENCE = 1.0'),
      "ceiling", ["ceiling"], T_REP),
    M("H9-B1-refuse-does-not-beat-repeat-prior", STRAT, ('REFUSE_PREFERENCE = 2.0', 'REFUSE_PREFERENCE = 1.4'),
      "ceiling", ["ceiling"], T_REP),
    M("H9-B1-repetition-preferred-even-when-an-authored-response-is-shown", STRAT,
      ('    if inp.presented_ref is None or _deny_evidence_or_reinterpret(inp) is None:\n', '    if True:\n'),
      "authored_evidence_response", ["authored_evidence_response"], T_REP),
    M("RR-B1-preference-off-for-any-shown-item", STRAT,
      ('    if inp.presented_ref is None or _deny_evidence_or_reinterpret(inp) is None:\n', '    if inp.presented_ref is None:\n'),
      "inert", ["inert_shown_item_escalates", "showing_an_inert_item"], T_REP),
    M("H9-B1-repeat-prior-resupplies-a-retracted-answer", TURN, ('    prior = next((s for s in reversed(state.decision.statements.standing_for_speaker(addressee))',
                                                                '    prior = next((s for s in reversed(state.decision.statements.for_speaker(addressee))'),
      "retracted", ["retracted"], T_REP),
    M("H9-B1-prior-answer-not-passed", TURN, ('                         prior_claims=prior.claims if prior is not None else ())', '                         prior_claims=())'),
      "H9_B1 or suite_2", ["H9_B1_a_lie_and_a_truth", "suite_2", "repeat_bot"], T_REP),
    M("H9-I1-parse-failure-counts-as-clarify", NIGHTLY, ('        except ProviderRefusal:\n            label = "refused"\n        except ProviderError:                                                 # incl. ProviderTimeout and BUDGET_EXHAUSTED\n            unmeasured += 1\n            continue\n        except Exception:                                                     # noqa: BLE001 - malformed output and the like: a miss\n            label = "failed"',
                                                           '        except Exception:                                                     # noqa: BLE001\n            label = "clarify"'),
      "H9_I1", ["H9_I1_a_parser_that_refuses", "H9_I1_a_provider_that_fails", "H9_I1_a_budget"], T_REP),
    M("H9-I1-transport-failure-is-a-miss", NIGHTLY, ('            unmeasured += 1\n            continue\n', '            label = "failed"\n'),
      "H9_I1", ["H9_I1_a_provider_that_fails", "H9_I1_a_budget"], T_REP),
    M("H9-I1-refusal-is-unmeasured", NIGHTLY, ('        except ProviderRefusal:\n            label = "refused"\n', ''),
      "H9_I1", ["H9_I1_a_parser_that_refuses"], T_REP),
    M("H9-I1-unanswered-lines-judged", NIGHTLY, ('None if not cls["lines"] or cls.get("unmeasured") else', 'None if not cls["lines"] else'),
      "H9_I1", ["H9_I1_a_provider_that_fails", "H9_I1_a_budget"], T_REP),
    M("H9-I1-cut-corpus-sample-judged", NIGHTLY, ('None if not cont["turns"] or cont_cut else', 'None if not cont["turns"] else'),
      "corpus_sample", ["corpus_sample"], T_REP),
    M("RR-I1-provider-failure-in-the-sample-judged", NIGHTLY, ('    cont_cut = budget.exhausted or unanswered.count > before\n', '    cont_cut = budget.exhausted\n'),
      "RR_I1_a_corpus_sample", ["RR_I1_a_corpus_sample"], T_REP),
    M("RR-I1-refusal-counted-as-no-answer", NIGHTLY, ('        except ProviderRefusal:\n            raise\n        except ProviderError:\n            self.count += 1',
                                                     '        except ProviderError:\n            self.count += 1'),
      "RR_I1_a_refusal", ["RR_I1_a_refusal"], T_REP),
    M("RR-I1-incomplete-session-judged-N6", NIGHTLY, ('by["mean_drafts_per_turn_centi"].value is None or not complete else', 'by["mean_drafts_per_turn_centi"].value is None else'),
      "RR_I1_a_session", ["RR_I1_a_session"], T_REP),
    M("RR-I1-incomplete-session-judged-N7", NIGHTLY, ('by["tokens_per_turn_flat"].status == "UNMEASURED" or not complete else', 'by["tokens_per_turn_flat"].status == "UNMEASURED" else'),
      "RR_I1_a_session", ["RR_I1_a_session"], T_REP),
    M("H9-I2-audit-on-the-generation-model", NIGHTLY, ('        return AnthropicTransport(transport._client, model=AUDIT_MODEL)', '        return transport'),
      "H9_I2", ["H9_I2_the_nightly_audit_runs"], T_REP),
    M("H9-I2-note-names-the-constant", NIGHTLY, ("verifier {', '.join(audit_models) or 'not reached'}", "verifier {AUDIT_MODEL}"),
      "H9_I2", ["H9_I2_a_run_without"], T_REP),
    M("promptdoc-skips-tuple-constants", PROMPTDOC, ('        for t in (n for tt in targets for n in (tt.elts if isinstance(tt, ast.Tuple) else [tt])):', '        for t in targets:'),
      "checked_in_document_is_exactly or every_constant_defined", ["checked_in_document_is_exactly", "every_constant_defined"], T_DOCS),
    # ---- the documentation of prompts and constants ------------------------------------------------------------------------
    M("prompt-changed-without-regenerating-the-doc", RENDER, ('Reply with the JSON object only."""\n\nVERIFY_SCHEMA', 'Reply with the JSON object, nothing else."""\n\nVERIFY_SCHEMA'),
      "checked_in_document_is_exactly", ["checked_in_document_is_exactly"], T_DOCS),
    M("constant-changed-without-regenerating-the-doc", INGRESS, ("RATE_LIMIT = 30      #", "RATE_LIMIT = 31      #"), "checked_in_document_is_exactly", ["checked_in_document_is_exactly"], T_DOCS),
    M("constant-added-but-undocumented", STRAT, ("W_SAFETY, W_CONSIST, W_PLAUS, W_PERSONA, W_EMOTION, W_GOAL, W_REPEAT = 1.0, 0.6, 0.4, 0.3, 0.3, 0.4, 0.5", "W_SAFETY, W_CONSIST, W_PLAUS, W_PERSONA, W_EMOTION, W_GOAL, W_REPEAT = 1.0, 0.6, 0.4, 0.3, 0.3, 0.4, 0.5\nW_NEW_UNDOCUMENTED = 1"),
      "every_constant_defined", ["every_constant_defined"], T_DOCS),
]

# Mutants whose guard is provably redundant with another; they are justified, not run.
EQUIVALENT: dict[str, str] = {}

def _copy_tree(dst: pathlib.Path) -> None:
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "out")
    for d in ("eidolon", "tests", "cases", "docs"):
        shutil.copytree(ROOT / d, dst / d, ignore=ignore)
    shutil.copy(ROOT / "pyproject.toml", dst / "pyproject.toml")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-j", "--jobs", type=int, default=4)
    ap.add_argument("-k", default="", help="only mutants whose name contains one of these (comma-separated)")
    args = ap.parse_args(argv)
    names = [m["name"] for m in MUTANTS]
    assert len(names) == len(set(names)), "duplicate mutant names"
    todo = [m for m in MUTANTS if any(k in m["name"] for k in args.k.split(","))]
    before = {f: (ROOT / f).read_bytes() for f in {m["file"] for m in MUTANTS}}
    with tempfile.TemporaryDirectory(prefix="eidolon-mut9-") as tmp:
        workers = []
        for i in range(args.jobs + 1):
            w = pathlib.Path(tmp) / f"w{i}"
            _copy_tree(w)
            workers.append(w)
        results: dict[str, tuple[str, str]] = {}
        with cf.ThreadPoolExecutor(max_workers=args.jobs + 1) as pool:
            baseline = pool.submit(_pytest, workers[0], sorted({m["tests"] for m in todo}), timeout=7200)
            queues = [todo[i::args.jobs] for i in range(args.jobs)]

            def drain(i):
                for m in queues[i]:
                    try:
                        results[m["name"]] = _run_mutant(workers[i + 1], m)
                    except Exception as e:                                          # noqa: BLE001 - a timeout / worker fault is a verdict
                        results[m["name"]] = ("ERROR", f"{type(e).__name__}: {e}"[:200])
                    v, why = results[m["name"]]
                    print(f"{v:8} {m['name']:56} {why}", flush=True)
            for f in [pool.submit(drain, i) for i in range(args.jobs)]:
                f.result()
            base = baseline.result()
    if base.returncode != 0:
        print(f"BASELINE IS NOT GREEN (pytest exit {base.returncode}): nothing above is evidence.\n{base.stdout[-1500:]}")
        return 2
    assert all((ROOT / f).read_bytes() == b for f, b in before.items()), "a source file changed"
    for n, why in EQUIVALENT.items():
        print(f"equivalent  {n}: {why}")
    tally = {v: sum(1 for r in results.values() if r[0] == v) for v in ("killed", "SURVIVED", "BAD", "ERROR")}
    print(f"baseline green; {tally['killed']} killed, {tally['SURVIVED']} survived, {tally['BAD']} malformed, "
          f"{tally['ERROR']} infrastructure errors, {len(EQUIVALENT)} justified equivalent ({len(todo)} run of {len(MUTANTS)})")
    return 0 if tally["killed"] == len(todo) else 1


if __name__ == "__main__":
    sys.exit(main())
