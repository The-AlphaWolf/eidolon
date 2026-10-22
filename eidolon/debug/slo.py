"""§27.5 metrics / SLOs, computed from the trace file alone (committed turns in `traces`, attempts that committed nothing in
`aborted`) - the "SLO dashboards from `llm_calls`/traces" of the Phase 9 deliverables.

Every metric carries a STATUS, and the statuses mean exactly this:

    PASS        the population needed to judge it exists, and it meets the architecture's number
    FAIL        the population exists and it does not
    UNMEASURED  the traces do not contain what is needed (no model-rendered turn, no price table, too few turns to compare
                a start with an end). Never silently PASS, never silently zero.
    REPORTED    a figure with no target in the architecture (latency, per-check failure rates, outcome counts)

A trace population is BEST-EFFORT (§27.1: a crash between commit and trace write leaves a gap), so none of this is a guarantee
about the game, only a detector - which is why `trace_gaps` is a metric of its own and not an error.

Two things are the implementer's reading, not the architecture's: "tokens per turn must be flat" is operationalised as the last
third's mean <= `FLAT_RATIO` x the first third's (needs >= `MIN_FLAT_TURNS` model turns), and the audit's "< 0.5%" is judged
only on a sample of at least `MIN_AUDIT` statements (`audit.py`).
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from ..trace import COMMITTED, TurnTrace

FALLBACK_MAX_BP = 200            # §27.5: fallback rate < 2%
DRAFTS_MAX_CENTI = 130           # §27.5: mean drafts per turn < 1.3
FLAT_RATIO = 1.25
MIN_FLAT_TURNS = 9


@dataclass(frozen=True)
class Metric:
    name: str
    value: object
    target: str
    status: str
    note: str = ""

    def row(self) -> dict:
        return {"name": self.name, "value": self.value, "target": self.target, "status": self.status, "note": self.note}


def parse_rows(rows) -> tuple[list[TurnTrace], int]:
    """Valid traces and a count of rows that were not one (a forged or foreign row is skipped and counted, never trusted)."""
    out, bad = [], 0
    for _, text in rows:
        try:
            out.append(TurnTrace.model_validate_json(text))
        except ValueError:
            bad += 1
    return out, bad


def _p(values: list[int], q: float) -> int:
    v = sorted(values)
    return v[min(len(v) - 1, int(q * len(v)))]


def _mean(xs) -> float:
    xs = list(xs)
    return sum(xs) / len(xs)


def compute(committed: list[TurnTrace], aborted: list[TurnTrace], *, gaps: int | None = None, unreadable: int = 0) -> list[Metric]:
    m: list[Metric] = []
    model_turns = [t for t in committed if t.renderer == "model" and t.outcome in COMMITTED]
    attempts = [d for t in model_turns for d in t.drafts]
    calls = [c for t in committed + aborted for c in t.llm_calls]

    m.append(Metric("turns_committed", len(committed), "-", "REPORTED"))
    m.append(Metric("attempts_not_committed", len(aborted), "-", "REPORTED"))
    outcomes: dict[str, int] = {}
    failures: dict[str, int] = {}
    for t in committed + aborted:
        outcomes[t.outcome] = outcomes.get(t.outcome, 0) + 1
        for f in t.failures:
            failures[f] = failures.get(f, 0) + 1
    m.append(Metric("outcomes", dict(sorted(outcomes.items())), "-", "REPORTED"))
    m.append(Metric("failures_by_kind", dict(sorted(failures.items())), "-", "REPORTED",
                    "model refusal, validation failure, timeout, transport error, verifier failure and the fallback are separate"))
    if gaps is not None:
        m.append(Metric("trace_gaps", gaps, "-", "REPORTED", "expected after a crash (§27.1); not corruption"))
    if unreadable:
        m.append(Metric("unreadable_trace_rows", unreadable, "0", "FAIL", "rows that are not a valid TurnTrace"))

    if model_turns:
        fb = sum(t.outcome == "committed_fallback" for t in model_turns)
        bp = fb * 10000 // len(model_turns)
        m.append(Metric("fallback_rate_bp", bp, f"< {FALLBACK_MAX_BP}", "PASS" if bp < FALLBACK_MAX_BP else "FAIL",
                        f"{fb} of {len(model_turns)} model-rendered turns"))
        mean_c = round(_mean(len(t.drafts) for t in model_turns) * 100)
        m.append(Metric("mean_drafts_per_turn_centi", mean_c, f"< {DRAFTS_MAX_CENTI}", "PASS" if mean_c < DRAFTS_MAX_CENTI else "FAIL"))
        per_check: dict[str, int] = {}
        for d in attempts:
            for code in {v.split("[")[0].split(":")[0] for v in d.violations}:
                per_check[code] = per_check.get(code, 0) + 1
        m.append(Metric("validation_failure_by_check", {k: v for k, v in sorted(per_check.items())}, "-", "REPORTED",
                        f"draft attempts containing the check, of {len(attempts)} attempts"))
        runs = [t.timings_ms.run for t in model_turns]
        m.append(Metric("turn_latency_ms", {"p50": _p(runs, 0.5), "p95": _p(runs, 0.95)}, "-", "REPORTED",
                        "runner time incl. the model calls; excludes the page"))
    else:
        for name, target in (("fallback_rate_bp", f"< {FALLBACK_MAX_BP}"), ("mean_drafts_per_turn_centi", f"< {DRAFTS_MAX_CENTI}"),
                             ("validation_failure_by_check", "-"), ("turn_latency_ms", "-")):
            m.append(Metric(name, None, target, "UNMEASURED", "no model-rendered turn in the traces"))

    # tokens per turn must be flat over the session
    per_turn = [(sum(c.input_tokens + c.output_tokens for c in t.llm_calls), t.envelope.tokens if t.envelope else 0) for t in model_turns]
    real = any(a for a, _ in per_turn)
    series = [a if real else b for a, b in per_turn]
    if len(series) >= MIN_FLAT_TURNS and any(series):
        k = len(series) // 3
        first, last = _mean(series[:k]), _mean(series[-k:])
        ratio = last / first if first else float("inf")
        m.append(Metric("tokens_per_turn_flat", {"first_third": round(first), "last_third": round(last), "basis": "provider" if real else "envelope_estimate"},
                        f"last/first <= {FLAT_RATIO}", "PASS" if ratio <= FLAT_RATIO else "FAIL"))
    else:
        m.append(Metric("tokens_per_turn_flat", None, f"last/first <= {FLAT_RATIO}", "UNMEASURED",
                        f"needs >= {MIN_FLAT_TURNS} model turns"))

    read, seen = sum(c.cache_read_tokens for c in calls), sum(c.input_tokens for c in calls)
    m.append(Metric("cache_read_ratio_bp", read * 10000 // seen if seen else None, "-", "REPORTED" if seen else "UNMEASURED",
                    "" if seen else "no provider token counts (a scripted or template session has none)"))
    priced = [c.cost_micro_usd for c in calls if c.cost_micro_usd is not None]
    m.append(Metric("cost_per_turn_micro_usd", sum(priced) // max(1, len(model_turns)) if priced else None, "-",
                    "REPORTED" if priced else "UNMEASURED", "" if priced else "no price table configured (trace.PRICES_PER_MTOK): not guessed"))

    typed = [t for t in committed + aborted if t.kind == "say"]
    clar = sum(t.outcome == "clarify" for t in aborted if t.kind == "say")
    m.append(Metric("parser_clarify_rate_bp", clar * 10000 // len(typed) if typed else None, "-", "REPORTED" if typed else "UNMEASURED",
                    f"{clar} of {len(typed)} typed lines" if typed else "no typed line in the traces"))

    # LayerPeel vs presented breakers: a peel with nothing ever shown to this character is I-3 broken
    bad = [t.turn_id for t in committed if t.assessment and any(p.peeled for p in t.assessment.peels)
           and not t.assessment.presented and t.view and t.view.detective_evidence + t.view.detective_statements == 0]
    peels = sum(1 for t in committed if t.assessment and any(p.peeled for p in t.assessment.peels))
    m.append(Metric("peels_without_any_presented_breaker", len(bad), "0", "PASS" if not bad else "FAIL",
                    f"{peels} peel turn(s) in the population" + (f"; turns {bad}" if bad else "")))
    return m


def summary(metrics: list[Metric]) -> dict:
    counts: dict[str, int] = {}
    for x in metrics:
        counts[x.status] = counts.get(x.status, 0) + 1
    return counts


def render_text(metrics: list[Metric]) -> str:
    w = max(len(x.name) for x in metrics)
    lines = [f"{x.status:<10} {x.name:<{w}}  {json.dumps(x.value, sort_keys=True):<48} target {x.target}" + (f"   ({x.note})" if x.note else "")
             for x in metrics]
    return "\n".join(lines) + "\n\n" + "  ".join(f"{k}={v}" for k, v in sorted(summary(metrics).items()))


def from_save(save) -> list[Metric]:
    committed, bad1 = parse_rows(save.trace_rows())
    aborted, bad2 = parse_rows(save.trace_rows(aborted=True))
    return compute(committed, aborted, gaps=len(save.trace_gaps()), unreadable=bad1 + bad2)
