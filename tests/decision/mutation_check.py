"""Controlled mutation verification for the Phase 4 blocker repair and the Phase-5-readiness
repair (docs/EIDOLON-PHASE-4-REPAIR-REPORT.md). Run from the repository root:

    python -m tests.decision.mutation_check                 # against tests/decision
    python -m tests.decision.mutation_check tests           # against the full suite
    python -m tests.decision.mutation_check phase5          # the Phase 5 set (M5) against tests/llm

Each mutation = list of (relpath, old, new) exact replacements. `old` must occur exactly once,
so a mutation can never silently no-op. Applied to a fresh copy of the repo; the named test
selection is run; the mutation is KILLED iff pytest fails. The repo itself is never touched.
"""
import json, os, re, shutil, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
D = "eidolon/decision/"

M = {
  # ---------- pre-repair reversions: the new tests must fail on the old code ----------
  "R-B1 full revert (fallback commits plan-level failures; blanket waiver; plan-only Solution check)": [
    (D+"validator.py", "    if any(violation_code(v) not in DRAFT_LEVEL_CODES for v in violations):\n        return ValidationResult(ok=False, text=\"\", claim_ids=(), violations=tuple(violations), rejected=True)\n", ""),
    (D+"validator.py", "    violations: list[str] = []\n    excluded = retracting if plan.act in RETRACTION_EXEMPT_ACTS else frozenset()",
                       "    if plan.act in RETRACTION_EXEMPT_ACTS:\n        return []\n    violations: list[str] = []\n    excluded = frozenset()"),
    (D+"validator.py", "    visible = _asserted((*plan.claims, *envelope.allowed_claims))\n    visible += _asserted((), plan.authorized_reveals, envelope.authorized_reveals, envelope.persona.public_facts)",
                       "    visible = _asserted(plan.claims)"),
    (D+"turn.py", "    if result.rejected:\n        return TurnResult(state=state, text=\"\", plan_act=plan.act, events=(), envelope=envelope,\n                          rejected=True, violations=result.violations, render_audit=audit, stages=stages)\n", ""),
  ],
  "R-B1a only: validator falls back instead of rejecting": [
    (D+"validator.py", "    if any(violation_code(v) not in DRAFT_LEVEL_CODES for v in violations):\n        return ValidationResult(ok=False, text=\"\", claim_ids=(), violations=tuple(violations), rejected=True)\n", ""),
  ],
  "R-B1b only: run_ask_turn ignores result.rejected": [
    (D+"turn.py", "    if result.rejected:\n        return TurnResult(state=state, text=\"\", plan_act=plan.act, events=(), envelope=envelope,\n                          rejected=True, violations=result.violations, render_audit=audit, stages=stages)\n", ""),
  ],
  "R-B1c only: CONCESSION blanket consistency waiver": [
    (D+"validator.py", "    violations: list[str] = []\n    excluded = retracting if plan.act in RETRACTION_EXEMPT_ACTS else frozenset()",
                       "    if plan.act in RETRACTION_EXEMPT_ACTS:\n        return []\n    violations: list[str] = []\n    excluded = frozenset()"),
  ],
  "R-B2 revert: peel only the wording-selected secret": [
    (D+"turn.py", "             for s in state.secrets.for_owner(addressee)]", "             for s in ([topical] if topical else [])]"),
  ],
  "R-B3 full revert (meta drops voiced acts; STONEWALL outranks CONCESSION; no backstop)": [
    (D+"strategy.py", "        voiced = [c for c in (_confession(inp), _concession(inp)) if c is not None]", "        voiced = []"),
    (D+"strategy.py", 'for forced_act in ("CONFESSION", "CONCESSION", "STONEWALL", "SLIP"):', 'for forced_act in ("CONFESSION", "STONEWALL", "CONCESSION", "SLIP"):'),
    (D+"turn.py", '        if plan.act not in ("CONCESSION", "CONFESSION") or not owed <= {c.id for c in plan.claims}:', "        if False:"),
  ],
  "R-B3a only: meta restriction drops voiced acts": [
    (D+"strategy.py", "        voiced = [c for c in (_confession(inp), _concession(inp)) if c is not None]", "        voiced = []"),
  ],
  "R-B3b only: STONEWALL outranks CONCESSION": [
    (D+"strategy.py", 'for forced_act in ("CONFESSION", "CONCESSION", "STONEWALL", "SLIP"):', 'for forced_act in ("CONFESSION", "STONEWALL", "CONCESSION", "SLIP"):'),
  ],
  "R-B3c only: unvoiced-peel backstop removed": [
    (D+"turn.py", '        if plan.act not in ("CONCESSION", "CONFESSION") or not owed <= {c.id for c in plan.claims}:', "        if False:"),
  ],
  "R-B4a: disjointness only checked for single-ground claims": [
    (D+"admissibility.py", "    own_events, _ = provenance_origin(grounding, knowledge, beliefs)",
                           "    own_events, _ = provenance_origin(grounding if len(grounding) == 1 else (), knowledge, beliefs)"),
  ],
  "R-B4b: provenance walk not transitive through Inferred": [
    (D+"admissibility.py", "        elif isinstance(src, Inferred):\n            stack.extend(src.from_ids)", "        elif isinstance(src, Inferred):\n            pass"),
  ],
  "R-B4c: corroborator need not be an established perception": [
    (D+"admissibility.py", "        if not other_perceptual or own_events & other_events:", "        if own_events & other_events:"),
  ],
  "R-B5a: grouping ignores the requires derivation graph": [
    (D+"weight.py", '    tokens = _origin_events(evidence) | {f"ref:{r}" for r in closure} | {f"ref:{evidence.id}"}',
                    "    tokens = _origin_events(evidence)\n    closure = ()"),
  ],
  "A1 audit: EvidenceResponse claims not superseded on peel (livelock)": [
    (D+"peel.py", "    props |= {c.proposition for r in secret.evidence_responses if peeled_from <= r.layer < to_index for c in r.claims}\n", ""),
  ],
  "A2a audit: a required statement's perceptual sources ignored": [
    (D+"weight.py", "                tokens |= provenance_origin(c.grounding, knowledge, ctx.beliefs)[0]", "                pass"),
  ],
  "A2b audit: a required item's own origin events ignored": [
    (D+"weight.py", "        if ancestor is not None:\n            tokens |= _origin_events(ancestor)", "        if ancestor is not None:\n            pass"),
  ],
  "R-B5b: unknown-origin evidence treated as independent": [
    (D+"weight.py", "        known_origin = ev.created_by is not None or ev.planted_by is not None", "        known_origin = True"),
  ],
  # ---------- the review's original mutation set, against the repaired code ----------
  # ---------- ADR-30: a lie answers only its own topic ------------------------------------------
  "ADR30-a LIE ignores the question's topic": [
    (D+"strategy.py", "               and on_topic(c.proposition, inp.query) for c in layer.claims):", "               for c in layer.claims):"),
  ],
  "ADR30-b a question that names no topic gets no lie": [
    (D+"footprint.py", "    return topic is None or claim_prop.kind in TOPIC_KINDS[topic]",
                       "    return topic is not None and claim_prop.kind in TOPIC_KINDS[topic]"),
  ],
  "ADR30-c the heard topic is answered by deed denials": [
    (D+"footprint.py", '"heard": frozenset({"Heard"})', '"heard": frozenset({"Heard", "Did", "DidNot"})'),
  ],
  "M1 every item its own causal group (I-32)": [
    (D+"weight.py", "    groups = group_by_causal_support(frozenset(presented), items_by_ref)", "    groups = [[r] for r in sorted(presented)]"),
  ],
  "M2 final monotone floor removed (EQUIVALENT)": [
    (D+"peel.py", "    i = max(i, reached)  # I-38", "    i = i  # I-38"),
  ],
  "M2a both monotone floors removed (I-20/I-38)": [
    (D+"peel.py", "    i = max(i, reached)  # I-38", "    i = i  # I-38"),
    (D+"peel.py", "            i = max(i - 1, reached)", "            i = i - 1"),
  ],
  "M2b layer_index last-write instead of max-fold (I-38)": [
    (D+"peel.py", "    return max(tos, default=0)", "    return tos[-1] if tos else 0"),
  ],
  "M3 retracted material still weighs (I-38)": [
    (D+"weight.py", "                if item.retracted:\n                    continue", "                if False:\n                    continue"),
  ],
  "M4 _chain_poisoned disabled (EQUIVALENT)": [
    (D+"admissibility.py", "    if _chain_poisoned(claim.grounding, knowledge):", "    if False:"),
  ],
  "M4b InvestigationTold walks to L1 in minds (I-27)": [
    ("eidolon/minds/admissibility.py", "        return AdmissibilityLevel.L0  # I-27: always, and it poisons any chain containing it.",
                                        "        return AdmissibilityLevel.L1  # MUTANT"),
  ],
  "M5 planted evidence loses apparent strength (I-35)": [
    (D+"admissibility.py", "            return AdmissibilityLevel.L0\n    return AdmissibilityLevel.L3\n",
                           "            return AdmissibilityLevel.L0\n    return AdmissibilityLevel.L3 if evidence.authentic else AdmissibilityLevel.L0\n"),
  ],
  "M6 collusion graph connects nobody (I-37)": [
    (D+"admissibility.py", "    def connected(self, a: ActorId, b: ActorId) -> bool:\n        if a == b:",
                           "    def connected(self, a: ActorId, b: ActorId) -> bool:\n        return a == b\n        if a == b:"),
  ],
  "M7 slip on topic alone (I-16)": [
    (D+"strategy.py", "        if inp.peel.weight_bp >= min_weight:", "        if True:"),
  ],
  "M8 confession gate defaults OPEN (I-21)": [
    (D+"peel.py", "    if check is None:\n        return False\n", "    if check is None:\n        return True\n"),
  ],
  "M9 validator skips consistency (I-28)": [
    (D+"validator.py", "    violations += consistency_check(plan, speaker, statements, case, retracting)", "    pass"),
  ],
  "M10 envelope padded with own standing ledger (I-1)": [
    (D+"turn.py", "    frame = secret.cover.layers[layer_reached].frame if secret else ()",
                  "    frame = tuple(state.decision.statements.standing_claims(addressee))"),
  ],
  "M10b envelope padded with every speaker's claims (I-1, cross-character)": [
    (D+"turn.py", "    frame = secret.cover.layers[layer_reached].frame if secret else ()",
                  "    frame = tuple(c for s in state.decision.statements.all() for c in s.claims)"),
  ],
  "M11 slip gate reads composure (I-29, one level down)": [
    (D+"strategy.py", "        if slip.id in inp.state.slips_used:", "        if inp.state.composure < 0 or slip.id in inp.state.slips_used:"),
  ],
  # ---------- Phase-5 readiness: I-3 entity allow-list -----------------------------------
  "R-P5-1 revert: entity guard is a deny-list (a name the case lacks is invisible)": [
    (D+"validator.py", "        unresolved = unresolved_names(seg.text, name_index)\n        if unresolved:\n            violations.append(f\"UNKNOWN_ENTITY[{i}]:{unresolved}\")\n", ""),
  ],
  "P5-1b: alias table not consulted": [
    (D+"validator.py", "    idx.update(case.alias.names)", "    pass"),
  ],
  # ---------- I-4: §14.2(e) and the envelope boundary -------------------------------------
  "R-P5-2 full revert: (e) Solution-only, no envelope audit": [
    (D+"validator.py", "        if any(s.owner != speaker and s.is_protected(p) for s in ctx.secrets.all()):\n            violations.append(f\"FOREIGN_PROTECTED:{p.kind}\")\n", ""),
    (D+"validator.py", "        if p not in authorized and fact_index(ctx.case).truth_value(p) is (not negated):\n            violations.append(f\"UNKNOWABLE_CLAIM:{p.kind}\")\n", ""),
    (D+"turn.py", "    leaks = audit_envelope(envelope, plan, frame, digest, addressee, ctx)\n", "    leaks = []\n"),
  ],
  "P5-2a: unknowable-set rule removed": [
    (D+"validator.py", "        if p not in authorized and fact_index(ctx.case).truth_value(p) is (not negated):\n            violations.append(f\"UNKNOWABLE_CLAIM:{p.kind}\")\n", ""),
  ],
  "P5-2b: other characters' protected facts not checked": [
    (D+"validator.py", "        if any(s.owner != speaker and s.is_protected(p) for s in ctx.secrets.all()):\n            violations.append(f\"FOREIGN_PROTECTED:{p.kind}\")\n", ""),
  ],
  "P5-2c: authorization lifts another character's protected fact": [
    (D+"validator.py", "        if any(s.owner != speaker and s.is_protected(p)", "        if p not in authorized and any(s.owner != speaker and s.is_protected(p)"),
  ],
  "P5-2d: run_ask_turn skips the envelope audit": [
    (D+"turn.py", "    leaks = audit_envelope(envelope, plan, frame, digest, addressee, ctx)\n", "    leaks = []\n"),
  ],
  "P5-2e: audit does not pin allowed_claims to the plan": [
    (D+"validator.py", "    if envelope.allowed_claims != tuple(EnvelopeClaim.of(c) for c in (*plan.claims, *frame)):", "    if False:"),
  ],
  "P5-2f: audit does not pin authorized_reveals to the plan": [
    (D+"validator.py", "    if envelope.authorized_reveals != plan.authorized_reveals:", "    if False:"),
  ],
  "P5-2g: audit skips (e) on the envelope (persona.public_facts unchecked)": [
    (D+"validator.py", "    violations += leak_violations(_asserted(envelope.allowed_claims, envelope.authorized_reveals,\n                                            envelope.persona.public_facts), plan, speaker, ctx)\n", ""),
  ],
  "P5-2h: audit accepts any digest": [
    (D+"validator.py", "    if (digest.character != speaker or", "    if False and (digest.character != speaker or"),
  ],
  "P5-2i: audit accepts undiscovered evidence in the digest": [
    (D+"validator.py", "    if not set(digest.evidence_presented) <= ctx.discovery.known_evidence:", "    if False:"),
  ],
  "P5-2j: audit accepts another character's text": [
    (D+"validator.py", "    if any(t not in own_text for t in", "    if False and any(t not in own_text for t in"),
  ],
  "P5-2k: audit accepts content in style strings": [
    (D+"validator.py", "    if any(mentioned_entities(t, names) - carried for t in style):", "    if False:"),
  ],
  "P5-2l: audit skips the schema pin": [
    (D+"validator.py", "    if any(_AUDITED_SCHEMA.get(type(o)) != _schema_fields(type(o)) for o in parts):", "    if False:"),
  ],
  "P5-2m: sincerity handed to the renderer (field AND pin updated together)": [
    (D+"envelope.py", "    confidence: Confidence = \"certain\"\n\n    @classmethod", "    confidence: Confidence = \"certain\"\n    sincerity: str = \"\"\n\n    @classmethod"),
    (D+"envelope.py", "                   confidence=claim.confidence)", "                   confidence=claim.confidence, sincerity=claim.sincerity)"),
    (D+"validator.py", "    EnvelopeClaim: {\"id\", \"proposition\", \"modality\", \"confidence\"},", "    EnvelopeClaim: {\"id\", \"proposition\", \"modality\", \"confidence\", \"sincerity\"},"),
  ],
  # ---------- I-5: identity-bound confession gate ------------------------------------------
  "R-P5-3 revert: any truthy verdict opens anyone's gate": [
    (D+"peel.py", "    if secret.owner != confrontee:\n        return False\n    result = check(confrontee, secret, presented, ctx)\n    return isinstance(result, UniquenessResult) and result.unique and result.survivors == (confrontee,)",
                  "    result = check(confrontee, secret, presented, ctx)\n    return bool(result.unique if isinstance(result, UniquenessResult) else result)"),
  ],
  "P5-3a: survivor not compared with the confessor": [
    (D+"peel.py", " and result.survivors == (confrontee,)", ""),
  ],
  "P5-3b: secret owner not compared with the confessor": [
    (D+"peel.py", "    if secret.owner != confrontee:\n        return False\n", ""),
  ],
  "P5-3c: a bare True verdict accepted": [
    (D+"peel.py", "    return isinstance(result, UniquenessResult) and", "    return result is True or isinstance(result, UniquenessResult) and"),
  ],
  # ---------- N-2: gate-open landing ---------------------------------------------------------
  "R-P5-4 revert (N-2): the landing concession carries the Solution (rejected every turn)": [
    (D+"peel.py", "    if layer.terminal != \"confession\":\n        return layer.claims\n", "    return layer.claims\n"),
  ],
  "P5-4b: gate-open landing voiced as CONFESSION (post-peel layer read)": [
    (D+"strategy.py", "    layer = inp.secret.cover.layers[inp.layer_reached]\n    if layer.terminal == \"confession\" and",
                      "    layer = inp.secret.cover.layers[inp.peel.to_index if inp.peel else inp.layer_reached]\n    if layer.terminal == \"confession\" and"),
  ],
  # ---------- found by the fresh audit of the Phase-5-readiness repair ------------------------
  "A-3: a given name ('Will') in the closed class": [
    (D+"validator.py", "could would shall should might must nothing", "could will would shall should may might must nothing"),
  ],
  "A-4: ASCII-only capitals (non-ASCII names invisible)": [
    (D+"validator.py", "t[0].isupper() and", "t[0] in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' and"),
  ],
  "A-5: substring masking (a known name hides an invented one)": [
    (D+"validator.py", 'rf"(?<!\\w){re.escape(name)}(?!\\w)"', "re.escape(name)"),
  ],
  "A-6: Said content not checked in its own right": [
    (D+"validator.py", "        if p.kind == \"Said\":\n            pending.append((p.proposition, False))\n", ""),
  ],
  "A-7: negated claims tested as if asserted": [
    (D+"validator.py", "truth_value(p) is (not negated):", "truth_value(p) is True:"),
  ],
}


# ---------- Phase 5 (`python -m tests.decision.mutation_check phase5`, selection `tests/llm`) ------------------
P = "eidolon/llm/"
M5 = {
  # provider boundary
  "P5-1: a `tools` parameter reaches the SDK (I-11)": [(P+"provider.py", '                messages=[{"role": "user", "content": request.user}],', '                messages=[{"role": "user", "content": request.user}], tools=[],')],
  "P5-2: the SDK retries invisibly": [(P+"provider.py", "anthropic.Anthropic(max_retries=0, timeout=timeout_s)", "anthropic.Anthropic(timeout=timeout_s)")],
  "P5-3: effort differs by route (I-42)": [(P+"provider.py", '{"parse": "low", "generate": "medium", "verify": "low"}', '{"parse": "low", "generate": "high", "verify": "low"}')],
  "P5-4: the prompt guard scans nothing": [(P+"provider.py", "        hits = self._scan(request)\n        if hits:", "        hits = []\n        if hits:")],
  "P5-5: the guard does not exempt the player's own text": [(P+"provider.py", "        for key in self._untrusted:\n            doc.pop(key, None)\n", "")],
  "P5-6: a refusal is not surfaced": [(P+"provider.py", '        if resp.stop_reason == "refusal":', "        if False:")],
  "P5-7: a timeout is not told from any other error": [(P+"provider.py", 'raise (ProviderTimeout if isinstance(exc, TimeoutError) or "Timeout" in name else ProviderError)(name) from exc', "raise ProviderError(name) from exc")],
  # structured output
  "P5-8: extra keys allowed in the wire schema": [(P+"render.py", "    if type(obj) is not dict or set(obj) != keys:", "    if type(obj) is not dict or not keys <= set(obj):")],
  "P5-9: duplicate keys accepted": [(P+"render.py", '        if len({k for k, _ in items}) != len(items):\n            raise MalformedOutput("DUPLICATE_KEY")\n', "")],
  "P5-10: control / zero-width characters allowed": [(P+"render.py", '        if any(unicodedata.category(ch)[0] == "C" and ch != "\\n" for ch in body):', "        if False:")],
  "P5-11: no NFKC normalization of model text": [(P+"render.py", '        body = unicodedata.normalize("NFKC", body)', "        pass")],
  # pipeline
  "P5-12: a plan-level failure is repaired/fallen back instead of rejected": [(P+"render.py", "            if result.rejected:  # the PLAN failed: no rendering can repair it", "            if False:")],
  "P5-13: repair is not bounded": [(P+"render.py", "        for n in range(1 + self.max_repairs):", "        for n in range(1 + 5 * self.max_repairs):")],
  "P5-14: a provider timeout is treated as a refusal (retried, then fallback)": [(P+"render.py", "            except ProviderRefusal:  # F-11", "            except ProviderError:  # F-11")],
  "P5-15: the fallback is not marked in the trace": [(P+"render.py", "        return dataclasses.replace(result, fallback=True) if result.ok or result.fallback else result", "        return result")],
  "P5-16: no latency floor": [(P+"render.py", "        if (wait := self.min_latency_s - (self.clock() - start)) > 0:\n            self.sleep(wait)", "        pass")],
  "P5-17: a verifier verdict of the wrong shape is tolerated": [(P+"render.py", "        if type(verdicts) is not list or len(verdicts) != len(draft.segments) or type(loose) is not list:", "        if False:")],
  "P5-18: extra assertions reported by the verifier are ignored": [(P+"render.py", '            if v["extra_assertions"]:\n                violations.append(f"EXTRA_ASSERTION[{i}]")', "            pass")],
  "P5-19: the player projection marks fallbacks (I-12)": [(P+"render.py", 'return PlayerTurn(text="" if result.rejected else result.text, ok=not result.rejected)', 'return PlayerTurn(text="" if result.rejected else result.text, ok=not (result.rejected or result.fallback))')],
  "P5-20: the view lists the whole cast, not what the reply may name": [(P+"render.py", "        names=tuple(sorted({_display(case, i) for i in ids if _known(case, i)})),", "        names=tuple(sorted({_display(case, i) for i in case.actors})),")],
  "P5-21: ports receive the sealed case, not a name book": [(P+"render.py", "        book, feedback, deny = NameBook.of(req.case, permitted_ids(req)), (), prompt_deny_tokens(req.ctx)", "        book, feedback, deny = req.case, (), prompt_deny_tokens(req.ctx)")],
  "P5-22: repair feedback may carry engine vocabulary": [(P+"render.py", "        if line and (leaked_tokens(line, deny) or any(w in line.lower() for w in ENGINE_VOCAB)):", "        if False:")],
  "P5-23: the guard's deny set is never set": [(P+"render.py", "            self.guard.deny = prompt_deny_tokens(req.ctx)", "            pass")],
  "P5-24: a renderer exception falls back instead of failing closed": [(P+"render.py", '            result, outcome, reason = ValidationResult(False, "", (), (code,), rejected=True), "rejected", code', '            result, outcome, reason = self._fallback(req), "fallback", code')],
  "P5-25: modality compared by exact string (polarity read as modality)": [(P+"render.py", '_MODAL_CLASS = {"actual": "asserted", "negated": "asserted",', '_MODAL_CLASS = {"actual": "actual", "negated": "negated",')],
  # ingress
  "P5-26: over-long input is not refused": [(P+"ingress.py", '    if len(raw) > MAX_CHARS:\n        return IngressResult(raw, "", blocked="TOO_LONG")', "    if False:\n        pass")],
  "P5-27: removed control characters are not reported": [(P+"ingress.py", '            dropped.add(f"U+{ord(ch):04X}")', "            pass")],
  "P5-28: marker scan without folding": [(P+"ingress.py", "    scan = fold(text)", "    scan = text.casefold()")],
  "P5-29: a meta marker does not raise the query kind": [(P+"ingress.py", '    kind = "meta" if ing.meta and action.query_kind not in ("meta", "coercion") else action.query_kind', "    kind = action.query_kind")],
  "P5-30: grounding ignores what the player has encountered": [(P+"ingress.py", "    ents = [i for i in sorted(known) if _known(case, i)]", "    ents = [i for i in sorted(case.actors) + sorted(case.locations) + sorted(case.objects)]")],
  "P5-31: the parser schema tolerates extra fields (I-26)": [(P+"ingress.py", 'model_config = ConfigDict(frozen=True, extra="forbid", strict=True)', 'model_config = ConfigDict(frozen=True, extra="ignore", strict=True)')],
  "P5-32: an ambiguous name resolves to the first candidate": [(P+"ingress.py", "            return hits[0] if len(hits) == 1 else None", "            return hits[0]")],
  "P5-33: no rate limit": [(P+"ingress.py", "    if turns_in_window >= RATE_LIMIT:", "    if False:")],
  "P5-34: the predicate hint is free text": [(P+"ingress.py", '    if action.predicate_hint is not None and not re.fullmatch(r"[a-z_]{1,24}", action.predicate_hint):', "    if False:")],
  # decision-layer guards Phase 5 added
  "P5-35: the verifier runs regardless of the deterministic checks": [(D+"validator.py", "    if not violations:\n        violations += verify(draft, envelope, case)", "    violations += verify(draft, envelope, case)")],
  "P5-36: a draft may omit a plan claim": [(D+"validator.py", "    violations += omission_violations(draft, plan)\n", "")],
  "P5-37: no length band (I-42)": [(D+"validator.py", "    violations += length_violations(draft, envelope, case)\n", "")],
  "P5-38: engine identifiers allowed in speech": [(D+"validator.py", "    violations += internal_token_violations(draft, internal_tokens(ctx, envelope))\n", "")],
  "P5-39: no time-slot check on asserting segments": [(D+"validator.py", '            if set(_CLOCK.findall(seg.text)) - allowed_times or _TIME_WORDS.search(seg.text):\n                violations.append(f"TIME_SLOT_MISMATCH[{i}]")', "            pass")],
  "P5-40: spelled-out times allowed in asserting segments": [(D+"validator.py", "            if set(_CLOCK.findall(seg.text)) - allowed_times or _TIME_WORDS.search(seg.text):", "            if set(_CLOCK.findall(seg.text)) - allowed_times:")],
  "P5-41: no self-disclosure guard": [(D+"validator.py", "    violations += disclosure_violations(draft, plan)\n", "")],
  "P5-42: engine vocabulary allowed in speech": [(D+"validator.py", "        hits = leaked_tokens(seg.text, tokens) + [w for w in ENGINE_VOCAB if w in low]", "        hits = leaked_tokens(seg.text, tokens)")],
  "P5-44: the deny-set includes the speaker's own protected facts": [(P+"seal.py", "        if secret.owner == speaker:\n            continue\n", "")],
  "P5-45: the deny-set omits the objects protected facts name": [(P+"seal.py", "            phrases |= {case.objects[o].name.lower() for o in entities(prop)[2] if o in case.objects}\n", "")],
  "P5-43: the turn runner does not catch a renderer exception": [(D+"turn.py", "        except Exception as exc:  # I-15: any renderer exception aborts the turn; nothing is committed", "        except ZeroDivisionError as exc:")],
  # ---------- the three BLOCKING findings of the Phase 5 hostile review ----------------------
  # Each is the pre-fix code, restored. `tests/llm/test_llm_blocking_repairs.py` must kill it.
  "P5-46 (F-1) revert: the committed claim sequence is the model's segment order": [
    (D+"turn.py", "    voiced = set(result.claim_ids)\n    committed_claims = tuple(\n        c.model_copy(update={\"statement\": statement_id})\n        for c in plan.claims if c.id in voiced\n    )",
                  "    committed_by_id = {c.id: c for c in plan.claims}\n    committed_claims = tuple(\n        committed_by_id[cid].model_copy(update={\"statement\": statement_id})\n        for cid in result.claim_ids if cid in committed_by_id\n    )"),
  ],
  "P5-47 (F-2) revert: repair feedback expands entity ids into canonical display names": [
    (P+"render.py", '    "UNKNOWN_ENTITY": "Segment {i}: it names something that is not in names; remove that reference and keep everything else.",\n'
                    '    "SLOT_MISMATCH": "Segment {i}: it names something its claims do not; remove that reference and keep everything else.",\n'
                    '    "NONVERBAL_LEAK": "Segment {i}: it names something its claims do not; remove that reference and keep everything else.",',
                    '    "UNKNOWN_ENTITY": "Segment {i}: remove the reference to {d}; keep everything else.",\n'
                    '    "SLOT_MISMATCH": "Segment {i}: remove the reference to {d}; keep everything else.",\n'
                    '    "NONVERBAL_LEAK": "Segment {i}: remove the reference to {d}; keep everything else.",'),
    (P+"render.py", "def repair_feedback(violations, deny: frozenset[str] = frozenset()) -> tuple[str, ...]:",
                    "def _names(detail, book):\n"
                    "    import ast\n"
                    "    try:\n"
                    "        items = ast.literal_eval(detail)\n"
                    "    except (ValueError, SyntaxError):\n"
                    "        return detail\n"
                    "    if not isinstance(items, (list, tuple)):\n"
                    "        return detail\n"
                    "    return \", \".join(_display(book, i) if book is not None and _known(book, i) else str(i) for i in items)\n"
                    "\n\n"
                    "def repair_feedback(violations, book=None, deny: frozenset[str] = frozenset()) -> tuple[str, ...]:"),
    (P+"render.py", '        line = tpl.format(i=idx.group(1) if idx else "?") if tpl else None',
                    '        line = tpl.format(i=idx.group(1) if idx else "?", d=_names(v.split(":", 1)[1], book) if ":" in v else "") if tpl else None'),
    (P+"render.py", "                feedback = repair_feedback(v, deny)", "                feedback = repair_feedback(v, book, deny)"),
    (P+"render.py", "            feedback = repair_feedback(result.violations, deny)", "            feedback = repair_feedback(result.violations, book, deny)"),
  ],
  "P5-48 (F-3) revert: the name book is built over the whole case": [
    (P+"render.py", "        book = lambda table: MappingProxyType({i: Named(e.name) for i, e in table.items() if i in permitted})",
                    "        book = lambda table: MappingProxyType({i: Named(e.name) for i, e in table.items()})"),
    (P+"render.py", "                   SimpleNamespace(names=MappingProxyType({n: t for n, t in case.alias.names.items() if t in permitted})))",
                    "                   SimpleNamespace(names=MappingProxyType(dict(case.alias.names))))"),
  ],
  "P5-48a (F-3) revert: only the alias half of the name book is left unfiltered": [
    (P+"render.py", "                   SimpleNamespace(names=MappingProxyType({n: t for n, t in case.alias.names.items() if t in permitted})))",
                    "                   SimpleNamespace(names=MappingProxyType(dict(case.alias.names))))"),
  ],
  "P5-48b (F-3) revert: the view re-admits whatever the player's raw line names": [
    (P+"render.py", "    return frozenset(set(req.allowed_entity_ids) | {req.speaker} | _entity_ids(\n        [c.proposition for c in envelope.allowed_claims] + list(envelope.persona.public_facts)))",
                    "    return frozenset(set(req.allowed_entity_ids) | {req.speaker} | _entity_ids(\n        [c.proposition for c in envelope.allowed_claims] + list(envelope.persona.public_facts))\n        | set(mentioned_entities(envelope.query_text, _name_index(req.case))))"),
  ],
  # ---------- the IMPORTANT findings F-5…F-13 ------------------------------------------------
  # Guards the third-party mutation battery showed surviving the whole suite (F-10), plus the
  # guards the other repairs added. Each is the pre-fix code restored, or the guard removed.
  "P5-49 (F-10) wire schema: no cap on the number of segments": [
    (P+"render.py", "    if type(segments) is not list or len(segments) > MAX_SEGMENTS:", "    if type(segments) is not list:"),
  ],
  "P5-50 (F-10) wire schema: no cap on a segment's length": [
    (P+"render.py", "        if type(body) is not str or len(body) > MAX_SEGMENT_CHARS:", "        if type(body) is not str:"),
  ],
  "P5-51 (F-10) wire schema: no cap on claim_ids per segment": [
    (P+"render.py", "        if type(ids) is not list or len(ids) > MAX_IDS or any(type(i) is not str for i in ids):",
                    "        if type(ids) is not list or any(type(i) is not str for i in ids):"),
  ],
  "P5-52 (F-10) no pre-parse cap on raw model output size": [
    (P+"render.py", '    if len(text) > MAX_RAW_CHARS:\n        raise MalformedOutput("TOO_LARGE")\n', ""),
  ],
  "P5-53 (F-10) spoken text may name any discovered evidence id": [
    (D+"validator.py", "            | {e.id for e in ctx.evidence.all()} | {s.id for s in ctx.statements.all()})",
                       "            | {s.id for s in ctx.statements.all()})"),
  ],
  "P5-54 (F-10) spoken text may name any statement id": [
    (D+"validator.py", "            | {e.id for e in ctx.evidence.all()} | {s.id for s in ctx.statements.all()})",
                       "            | {e.id for e in ctx.evidence.all()})"),
  ],
  "P5-55 (F-10) the deterministic fallback is emitted without re-validation": [
    (P+"render.py", "        result = self._validate(TemplateLLM().generate(req.envelope, req.case, req.speaker), req, verify_segments)\n        return dataclasses.replace(result, fallback=True) if result.ok or result.fallback else result",
                    "        from ..decision.validator import _fallback_text\n        return ValidationResult(ok=True, text=_fallback_text(req.plan, req.case), claim_ids=tuple(c.id for c in req.plan.claims), fallback=True)"),
  ],
  "P5-56 (F-10) plan-level codes reclassified as draft-level (a Solution leak would COMMIT)": [
    (D+"validator.py", '    "UNREFERENCED_ASSERTION", "MODALITY_MISMATCH", "PLAN_CLAIM_OMITTED", "SELF_DISCLOSURE",',
                       '    "UNREFERENCED_ASSERTION", "MODALITY_MISMATCH", "PLAN_CLAIM_OMITTED", "SELF_DISCLOSURE", "SOLUTION_LEAK", "UNKNOWABLE_CLAIM", "FOREIGN_PROTECTED",'),
  ],
  # ---------- F-7: the validation -> commit boundary ------------------------------------------
  "P5-57 (F-7) revert: the commit gate tests `rejected` instead of the result's semantics": [
    (D+"turn.py", "    if (malformed := result.integrity()) is not None:\n        return TurnResult(state=state, text=\"\", plan_act=plan.act, events=(), envelope=envelope,\n                          rejected=True, violations=(f\"RESULT_INTEGRITY:{malformed}\",), render_audit=audit, stages=stages)\n", ""),
  ],
  "P5-57a (F-7) the integrity check accepts every flag combination": [
    (D+"validator.py", '        if not self.ok and not self.rejected and not self.fallback:\n            return "NEITHER_OK_NOR_REJECTED"\n', ""),
  ],
  "P5-57b (F-7) a rejected result may carry text and claim ids": [
    (D+"validator.py", '        if self.rejected and (self.text or self.claim_ids):\n            return "REJECTED_WITH_CONTENT"\n', ""),
  ],
  "P5-57c (F-7) `committable` is just `not rejected`": [
    (D+"validator.py", "        return self.integrity() is None and not self.rejected and (self.ok or self.fallback)",
                       "        return not self.rejected"),
  ],
  # ---------- F-5: the shared output schema ---------------------------------------------------
  "P5-58 (F-5) revert: the request shares the module-level schema object": [
    (P+"provider.py", '    def __post_init__(self) -> None:\n        object.__setattr__(self, "schema", copy.deepcopy(self.schema))\n\n', ""),
  ],
  "P5-58a (F-5) the schema copy is shallow": [
    (P+"provider.py", 'object.__setattr__(self, "schema", copy.deepcopy(self.schema))', 'object.__setattr__(self, "schema", dict(self.schema))'),
  ],
  # ---------- F-8: the rate window ------------------------------------------------------------
  "P5-59 (F-8) revert: the limiter counts every turn ever, not the window": [
    (P+"ingress.py", "    return sum(1 for t in turn_times if now - t < window_s)", "    return sum(1 for _ in turn_times)"),
  ],
  "P5-59a (F-8) the CLI passes a monotonic total again": [
    ("eidolon/cli.py", "turns_in_window=rate_window(turn_times, clock()))", "turns_in_window=len(turn_times))"),
  ],
  # ---------- F-9: least privilege through the CLI ---------------------------------------------
  "P5-60 (F-9) revert: the CLI hands the parser the whole case": [
    ("eidolon/cli.py", "    seen = {addressee, *state.discovery.visited_locations, *state.discovery.held_items}",
                       "    return frozenset({*state.case.actors, *state.case.locations, *state.case.objects})\n    seen = {addressee}"),
  ],
  # ---------- F-11: evidence identifiers in the digest ------------------------------------------
  "P5-61 (F-11) revert: the digest renders raw evidence ids": [
    (D+"envelope.py", '        shown = [labels.get(e, "an item") for e in digest.evidence_presented]', "        shown = list(digest.evidence_presented)"),
  ],
  "P5-61a (F-11) labels are built for undiscovered evidence too": [
    (D+"digest.py", "        if item.id not in discovered:\n            continue\n", ""),
  ],
  # ---------- F-13: the marker scan's folding ---------------------------------------------------
  "P5-62 (F-13) the marker scan does not fold combining marks": [
    (P+"ingress.py", '    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)).casefold()',
                     '    return unicodedata.normalize("NFKC", text).casefold()'),
  ],
  "P5-62a (F-13) the override verbs and plurals are dropped from the marker": [
    (P+"ingress.py", r'"ignore_instructions": r"\b(?:ignores?|disregards?|forgets?|overrides?|bypass(?:es)?)\b.{0,30}\b(?:instructions?|rules?|prompts?|previous|above)\b",',
                     r'"ignore_instructions": r"\b(?:ignore|disregard|forget)\b.{0,30}\b(?:instructions?|rules|prompts?|previous|above)\b",'),
  ],
}

EQUIVALENT = {"M2 final monotone floor removed (EQUIVALENT)", "M4 _chain_poisoned disabled (EQUIVALENT)",
              # P5-22 guarded the interpolation of a violation's DETAIL into a feedback line. The
              # F-2 repair removed that interpolation entirely (`_TEMPLATES` now substitutes only
              # `{i}`, an integer), so the guard is unreachable and disabling it changes nothing.
              # It is kept as a fail-closed backstop; the reachability is pinned by
              # `test_f2_no_template_interpolates_anything_but_the_segment_index`, and P5-47 is the
              # mutation that now covers the risk P5-22 used to. Re-introduce a placeholder and
              # this stops being equivalent — the harness then reports it as UNEXPECTED.
              "P5-22: repair feedback may carry engine vocabulary"}


def run(name, edits, selection):
    tmp = tempfile.mkdtemp(prefix="mut_")
    try:
        for d in ("eidolon", "tests"):
            shutil.copytree(os.path.join(REPO, d), os.path.join(tmp, d),
                            ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(os.path.join(REPO, "pyproject.toml"), tmp)
        if os.path.isdir(os.path.join(REPO, "cases")):      # the committed goldens are fixtures of tests/decision/test_topicality.py
            shutil.copytree(os.path.join(REPO, "cases"), os.path.join(tmp, "cases"))
        for rel, old, new in edits:
            p = os.path.join(tmp, rel)
            src = open(p, encoding="utf8").read()
            n = src.count(old)
            if n != 1:
                return {"name": name, "error": f"anchor matched {n}x in {rel}: {old[:60]!r}"}
            open(p, "w", encoding="utf8").write(src.replace(old, new))
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *selection],
                           cwd=tmp, capture_output=True, text=True)
        failed = sorted(set(re.findall(r"^FAILED (\S+)", r.stdout, re.M)))
        summary = (r.stdout.strip().splitlines() or ["?"])[-1]
        return {"name": name, "killed": r.returncode != 0, "summary": summary, "failed": failed}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    phase5 = sys.argv[1:2] == ["phase5"]
    selection = (sys.argv[2:] if phase5 else sys.argv[1:]) or (["tests/llm"] if phase5 else ["tests/decision"])
    base = run("baseline (no mutation)", [], selection)
    if base.get("killed") is not False:  # a red baseline would make every mutant look killed
        print("BASELINE IS NOT GREEN — mutation results would be meaningless:", base)
        sys.exit(2)
    with ThreadPoolExecutor(max_workers=4) as pool:  # each mutant runs in its own temp copy
        results = list(pool.map(lambda item: run(*item, selection), (M5 if phase5 else M).items()))
    ok = True
    for res in results:
        if "error" in res:
            ok = False
            print(f"ERROR     {res['name']}: {res['error']}")
            continue
        expect_kill = res["name"] not in EQUIVALENT
        good = res["killed"] == expect_kill
        ok &= good
        tag = ("KILLED   " if res["killed"] else "SURVIVED ") + ("" if good else "<-- UNEXPECTED")
        print(f"{tag} {res['name']}\n          {res['summary']}")
        for f in res["failed"][:6]:
            print(f"            - {f}")
        if len(res["failed"]) > 6:
            print(f"            ... +{len(res['failed']) - 6} more")
    print("\nMUTATION VERIFICATION:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
