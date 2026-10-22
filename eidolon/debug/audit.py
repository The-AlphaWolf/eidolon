"""§27.4 offline audit: re-validate a SAMPLE of committed statements with the FULL deny-sets and, optionally, a stronger
verifier, and file every discrepancy as a regression fixture.

It is a DETECTOR, not a guarantee (§27.4): a clean audit says nothing about statements that were not sampled, about
implicature no deterministic check sees (§33), or about turns whose trace is missing. It asks one question of each statement
- "would the strictest version of the commit-time checks have let this through?" - and it can say yes to a statement the
runtime refused to be strict about, because it is allowed to be wrong in the strict direction:

* **Deny-sets**: every engine id the case and the session hold (secrets, ALL evidence, statements, claims, account tokens,
  knowledge/belief/memory ids), the act names, the meta/engine vocabulary and the canary. The runtime denies the ids a
  renderer was given; the audit denies all of them, whenever they were learned.
* **Checks** (the commit-time ones, re-run on the stored text): meta and engine vocabulary, the canary, an id or act name,
  an invented name, a clock time none of the statement's own claims renders, a confession or a lie-tell the act does not
  license, a `Solution` claim outside a CONFESSION, an unknowable or foreign-protected claim (`leak_violations`), and the
  speaker's own never-conceded protected facts in their plainest phrasing (§33.2's protected-phrase set).
* **Not checked, and said so**: which names were *permitted* that turn (the player's line is not in the log, C-4) - a known
  entity outside the statement's claims is listed as `review`, never counted.
* **Verifier**: a callable `(statement, state) -> [violation]`. `model_verifier` plays the §14.2(d) verifier with a stronger
  model; with none given, `verifier_used` is False and the report says the semantic pass did not run.

The 0.5% bound (Phase 9 tests) is only judged on a sample of `MIN_AUDIT` statements or more: with fewer, zero findings still
allow a true rate of several percent (the rule of three), so the status is UNMEASURED, not PASS.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..decision.claims import Statement
from ..decision.envelope import Envelope, EnvelopeClaim, PersonaSlot
from ..decision.llm import Draft, Segment, render_claim
from ..decision.speech_acts import ACT_TABLE
from ..decision.strategy import DeliveryDirective, ResponsePlan
from ..decision.turn import CANARY
from ..decision.validator import (
    ENGINE_VOCAB, FORBIDDEN_VOCAB, _CLOCK, _CONFESSES, _LIE_TELLS, _TIME_WORDS, _name_index, leak_violations, leaked_tokens,
    mentioned_entities, unresolved_names,
)
from ..trace import engine_ids
from ..world.alias import render_time
from ..world.propositions import entities

MIN_AUDIT = 200
MAX_BP = 50                     # Phase 9 tests: audit discrepancies < 0.5% of statements
REVEAL_ACTS = frozenset({"CONCESSION", "CONFESSION", "SLIP", "CORRECTION"})
Verifier = Callable[[Statement, object], list]


@dataclass(frozen=True)
class Finding:
    statement: str
    speaker: str
    act: str
    violations: tuple[str, ...]
    review: tuple[str, ...] = ()


@dataclass(frozen=True)
class AuditReport:
    seal: str
    sampled: int
    statements: int
    findings: tuple[Finding, ...] = ()
    review: tuple[Finding, ...] = ()
    verifier_used: bool = False
    picked: tuple[str, ...] = ()          # the statement ids that were sampled, in sample order: the audit trail

    @property
    def verifier_errors(self) -> int:
        """Statements the stronger verifier could not be asked about (provider error, budget): a hole in the audit."""
        return sum("VERIFIER_UNAVAILABLE" in f.review for f in (*self.findings, *self.review))

    @property
    def discrepancies(self) -> int:
        return len(self.findings)

    @property
    def rate_bp(self) -> int | None:
        return self.discrepancies * 10000 // self.sampled if self.sampled else None

    @property
    def upper95_bp(self) -> int | None:
        """A 95% upper bound on the true rate: the rule of three when nothing was found, a normal bound otherwise."""
        if not self.sampled:
            return None
        n, k = self.sampled, self.discrepancies
        return min(10000, round(10000 * (3 / n if k == 0 else k / n + 1.96 * (k * (n - k) / n) ** 0.5 / n)))

    @property
    def status(self) -> str:
        if self.sampled < MIN_AUDIT or (self.verifier_used and self.verifier_errors):
            return "UNMEASURED"
        return "PASS" if self.rate_bp < MAX_BP else "FAIL"

    def summary(self) -> dict:
        return {"seal": self.seal, "statements": self.statements, "sampled": self.sampled, "discrepancies": self.discrepancies,
                "rate_bp": self.rate_bp, "upper95_bp": self.upper95_bp, "target": f"< {MAX_BP} bp (0.5%)",
                "status": self.status, "verifier_used": self.verifier_used, "verifier_errors": self.verifier_errors,
                "review_items": len(self.review),
                "note": "" if self.sampled >= MIN_AUDIT and not self.verifier_errors else
                (f"sample below {MIN_AUDIT}: the bound is not judged" if self.sampled < MIN_AUDIT else
                 f"the stronger verifier was unavailable for {self.verifier_errors} statement(s): coverage is partial")}


def check_statement(state, stmt: Statement, *, ids: frozenset[str], names: dict, verifier: Verifier | None = None) -> tuple[list, list]:
    """(hard violations, review items) for ONE committed statement."""
    case, text, low = state.case, stmt.text, stmt.text.lower()
    hard: list[str] = []
    review: list[str] = []
    hard += [f"FORBIDDEN_VOCAB:{w}" for w in FORBIDDEN_VOCAB if w in low]
    if CANARY.lower() in low:
        hard.append("CANARY_LEAK")
    found = leaked_tokens(text, ids | set(ACT_TABLE)) + [w for w in ENGINE_VOCAB if w in low]
    hard += [f"INTERNAL_TOKEN_LEAK:{len(found)}"] if found else []
    invented = unresolved_names(text, names)
    if invented:
        hard.append("INVENTED_NAME")
    claim_entities = {stmt.speaker}
    for c in stmt.claims:
        a, l, o, amb = entities(c.proposition)
        claim_entities |= a | l | o | amb
    stray = mentioned_entities(text, names) - claim_entities
    if stray:
        review.append(f"ENTITY_OUTSIDE_CLAIMS:{len(stray)}")
    allowed_times = {render_time(t) for c in stmt.claims for t in (getattr(c.proposition, "interval", None) or ())}
    if set(_CLOCK.findall(text)) - allowed_times or _TIME_WORDS.search(text):
        hard.append("TIME_NOT_IN_CLAIMS")
    if stmt.act != "CONFESSION" and _CONFESSES.search(text):
        hard.append("SELF_DISCLOSURE:confession")
    if stmt.act not in ("CONFESSION", "CONCESSION", "CORRECTION") and _LIE_TELLS.search(text):
        hard.append("SELF_DISCLOSURE:lie_tell")
    if stmt.act != "CONFESSION" and any(c.proposition.kind == "Solution" for c in stmt.claims):
        hard.append("SOLUTION_OUTSIDE_CONFESSION")
    plan = ResponsePlan(act=stmt.act, claims=stmt.claims,
                        authorized_reveals=tuple(c.proposition for c in stmt.claims) if stmt.act in REVEAL_ACTS else ())
    hard += list(leak_violations([(c.proposition, c.modality == "negated") for c in stmt.claims], plan, stmt.speaker, state.ctx()))
    never_peeled = {s.id for s in state.secrets.for_owner(stmt.speaker)
                    if not any(p.character == stmt.speaker and p.secret_id == s.id for p in state.decision.layer_peels)}
    if stmt.act not in REVEAL_ACTS:
        for sec in state.secrets.for_owner(stmt.speaker):
            if sec.id in never_peeled:
                for p in sec.protected:
                    if p.kind != "Said" and render_claim(EnvelopeClaim(id="", proposition=p), case).lower() in low:
                        hard.append("PROTECTED_PHRASE")
                        break
    if verifier is not None:
        try:
            hard += [f"VERIFIER:{v}" for v in verifier(stmt, state)]
        except Exception:                                  # noqa: BLE001 - a provider failure is a gap in the audit, never a finding
            review.append("VERIFIER_UNAVAILABLE")
    return list(dict.fromkeys(hard)), review


def audit_state(state, seal: str, *, sample: int | None = None, seed: int = 0, verifier: Verifier | None = None) -> AuditReport:
    """Audit a folded `GameState`'s ledger. The sample is deterministic: statements ordered by a hash of (seed, seal, id)."""
    stmts = state.decision.statements.all()
    order = sorted(stmts, key=lambda s: hashlib.sha256(f"{seed}|{seal}|{s.id}".encode()).hexdigest())
    picked = order if sample is None else order[:sample]
    ids, names = engine_ids(state), _name_index(state.case)
    findings, review = [], []
    for s in picked:
        hard, soft = check_statement(state, s, ids=ids, names=names, verifier=verifier)
        if hard:
            findings.append(Finding(s.id, s.speaker, s.act, tuple(hard), tuple(soft)))
        elif soft:
            review.append(Finding(s.id, s.speaker, s.act, (), tuple(soft)))
    return AuditReport(seal=seal[:16], sampled=len(picked), statements=len(stmts), findings=tuple(findings), review=tuple(review),
                       verifier_used=verifier is not None, picked=tuple(s.id for s in picked))


def audit_save(save, **kw) -> AuditReport:
    return audit_state(save.state, save.bundle.package.seal, **kw)


def write_fixtures(report: AuditReport, state, out_dir) -> list[Path]:
    """One JSON per discrepancy, named by case and statement: stable, so re-running the audit overwrites instead of
    accumulating. The text of a discrepancy is exactly what must not be said, so these are local debug artifacts."""
    out = Path(out_dir)
    written = []
    if not report.findings:
        return written
    out.mkdir(parents=True, exist_ok=True)
    for f in report.findings:
        s = state.decision.statements.get(f.statement)
        doc = {"version": 1, "case": report.seal, "statement": f.statement, "speaker": f.speaker, "act": f.act, "text": s.text,
               "claims": [json.loads(c.model_dump_json()) for c in s.claims], "violations": list(f.violations)}
        p = out / f"audit-{report.seal}-{re.sub(r'[^A-Za-z0-9_]', '_', f.statement)}.json"
        p.write_text(json.dumps(doc, indent=1, sort_keys=True), encoding="utf-8")
        written.append(p)
    return written


def model_verifier(transport) -> Verifier:
    """§14.2(d)'s verifier, played by whatever `transport` is - the nightly job gives it a stronger model than the one that
    rendered the turn (§24: `claude-fable-5-1` for offline audit passes). The statement's text is ONE `assert` segment tagged
    with all its claims; the verdict can only add violations."""
    from ..llm.render import ModelLLM

    def verify(stmt: Statement, state) -> list:
        if not stmt.claims:
            return []
        env = Envelope(persona=PersonaSlot(), delivery=DeliveryDirective(),
                       allowed_claims=tuple(EnvelopeClaim.of(c) for c in stmt.claims))
        draft = Draft(segments=(Segment(text=stmt.text, claim_ids=tuple(c.id for c in stmt.claims), kind="assert"),))
        return ModelLLM(transport).verify(draft, env, state.case)
    return verify
