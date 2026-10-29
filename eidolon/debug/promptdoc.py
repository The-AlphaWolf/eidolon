"""`docs/EIDOLON-PROMPTS-AND-CONSTANTS.md` - the Phase 9 "documentation of prompts and constants", GENERATED from the code so it
cannot drift: the prompts are printed verbatim from the modules that send them, every wire schema from the constant that is
sent, and every module-level constant (found by parsing each module's source, not from a hand-kept list) with its value. A test fails the build when the checked-in file is not what this module renders; regenerate with

    python -m eidolon.debug promptdoc
"""
from __future__ import annotations

import ast
import importlib
import inspect
import json
import re
from pathlib import Path

MODULES = [
    ("llm.provider", "the provider boundary (ADR-12, I-11): model, effort per route, the call log"),
    ("llm.ingress", "stages 0-2: the length cap, the rate window, the marker scan, the parse prompt and schema"),
    ("llm.render", "stages 7-9: the generate and verify prompts, their schemas, the wire limits, the latency floor"),
    ("decision.validator", "stage 9's deterministic checks and their vocabularies"),
    ("decision.envelope", "stage 7: the envelope's slot caps"),
    ("decision.strategy", "stage 6: the utility weights"),
    ("decision.voice", "§9 speaking styles, derived at render time from name and seed"),
    ("decision.pressure", "verbal pressure and composure (delivery-only, I-16/I-29)"),
    ("decision.digest", "the conversation digest's budgets"),
    ("decision.turn", "the turn runner"),
    ("minds.memory", "memory salience, decay, retrieval bands"),
    ("minds.belief", "belief formation thresholds"),
    ("minds.scale", "the basis-point scale (I-17)"),
    ("store", "persistence: schema and engine versions, the trace sink's scrubber"),
    ("trace", "the TurnTrace bounds"),
    ("game", "the player's controls"),
    ("web", "the player app's boundary"),
    ("debug.slo", "the SLO thresholds"),
    ("debug.audit", "the offline audit's thresholds and vocabularies"),
    ("debug.nightly", "the nightly job"),
    ("debug.app", "the debug server's ports"),
]

NOTES = {
    "TRACE_KINDS": "the player control a trace row names (§27.1); unknown controls are traced as `ask`",
    "BUSY": "what the player sees when the model did not answer (NR-N2): a retry notice, nothing recorded",
    "ACCUSATION_WINDOW_MAX": "widest time window (minutes) that still earns the accusation's place-and-time axis (H8-N8)",
    "SEED_MAX": "a new game's seed is a non-negative 31-bit integer (NR-N4)",
    "MODEL": "the one model for the generate and parse routes (§24)", "VOICE_REGISTERS": "§9 public speaking style, chosen per character by hash of name and seed only (never guilt or secrets)", "VOICE_IDIOMS": "one per character, same rule", "VOICE_TICS": "one per character, same rule", "FREE_AUDIT_MODELS": "ADR-31: each free provider's stronger model for the offline audit's verifier (None = audit on the session's model)", "FREE_RPM": "ADR-31: default free-tier pacing for measurement runs (calls per minute)", "FREE_PROVIDERS": "OpenAI-compatible free endpoints for play/development (`--provider`); never counted as live by the nightly", "UNSUPPORTED_SCHEMA_KEYWORDS": "schema keywords a free endpoint rejects; dropped from what it is sent, replies still parsed strictly", "EFFORT": "constant per route (I-42): never computed from a plan, act or sincerity",
    "AUDIT_MODEL": "the stronger verifier the offline audit uses (§24)", "LATENCY_FLOOR_S": "every outcome takes at least this long (I-42); a placeholder until a live p99 is measured",
    "MAX_CHARS": "player line cap; over-long text is refused, never truncated (§22.2)", "RATE_LIMIT": "typed lines per window (§22.2)",
    "RATE_WINDOW_S": "the sliding window RATE_LIMIT is counted over", "MAX_SEGMENTS": "wire limit on a draft", "MAX_SEGMENT_CHARS": "wire limit on one segment",
    "MAX_RAW_CHARS": "wire limit on a model reply before it is parsed", "MAX_REPLY_CHARS": "top of the last length band",
    "LENGTH_EDGES": "length bands (I-42): the draft must land in the band of the plan's canonical rendering", "KINDS": "segment kinds (the only ones the schema allows)",
    "FORBIDDEN_VOCAB": "meta words no in-world speaker says (§14.2b)", "ENGINE_VOCAB": "engine words that would be a side channel (§22.3)",
    "DRAFT_LEVEL_CODES": "violations the renderer can cause and the deterministic fallback cures; every other code rejects the turn (I-15)",
    "W_SAFETY": "utility weight (§11.5)", "W_CONSIST": "utility weight", "W_PLAUS": "utility weight", "W_PERSONA": "utility weight",
    "W_EMOTION": "utility weight", "W_GOAL": "utility weight", "W_REPEAT": "utility weight (repetition penalty)",
    "minds.memory.W_NOVELTY": "memory salience weight (§8)", "minds.memory.W_EMOTION": "memory salience weight (§8)",
    "minds.memory.W_SELF": "memory salience weight (§8)", "MAX_IDS": "wire limit on the claim ids one segment may carry",
    "REPEAT_PRIOR_PREFERENCE": "§15.4: from the third identical question the standing answer beats every other act's utility ceiling, whatever is shown, unless an authored evidence response is in play (H9-B1, RR-B1)",
    "REFUSE_PREFERENCE": "§15.4: from the sixth identical question REFUSE beats REPEAT_PRIOR and every other act, under the same condition (H9-B1, RR-B1)",
    "MAX_RECENT_EXCHANGE_TURNS": "envelope slot cap (§15.1)", "MAX_RETRIEVED_STATEMENTS": "envelope slot cap (§15.1)",
    "SCHEMA_VERSION": "save schema; a newer one is refused", "ENGINE_VERSION": "recorded in meta for diagnosis",
    "TRACE_VERSION": "TurnTrace schema version", "MAX_TRACE_BYTES": "hard bound on one serialized trace", "PRICES_PER_MTOK": "empty on purpose: cost is UNMEASURED until filled in",
    "FALLBACK_MAX_BP": "SLO: fallback rate < 2% (§27.5)", "DRAFTS_MAX_CENTI": "SLO: mean drafts per turn < 1.3 (§27.5)", "FLAT_RATIO": "implementer's reading of 'tokens per turn flat'",
    "MIN_AUDIT": "the audit's 0.5% bound is judged only on at least this many statements", "MAX_BP": "Phase 9: audit discrepancies < 0.5%",
    "SESSION_FALLBACK_BP": "Phase 9: fallback < 2% on a 300-turn scripted session", "DEFAULT_PORT": "the debug server's default port", "PLAYER_PORT": "the player app's port: the debug server never uses it",
}
LONG = 400


def _constants(mod_name: str):
    mod = importlib.import_module(f"eidolon.{mod_name}")
    src = Path(inspect.getsourcefile(mod)).read_text(encoding="utf-8")
    out = []
    for node in ast.parse(src).body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        for t in (n for tt in targets for n in (tt.elts if isinstance(tt, ast.Tuple) else [tt])):     # `A, B = 1, 2` too
            if isinstance(t, ast.Name) and re.fullmatch(r"[A-Z][A-Z0-9_]{2,}", t.id) and not t.id.startswith("SYSTEM_") \
                    and not t.id.endswith("_SCHEMA") and t.id != "_TEMPLATES":
                out.append((t.id, node.lineno, getattr(mod, t.id)))
    return mod, out


def _plain(x):
    """A value as stable text: callables by name (their repr carries an address), objects by `str`."""
    if isinstance(x, (int, str, bool, type(None))):
        return x
    return getattr(x, "__name__", None) if callable(x) and hasattr(x, "__name__") and not isinstance(x, type) else str(x)


def show(v) -> str:
    if hasattr(v, "pattern"):
        return f"`{v.pattern}`"
    if isinstance(v, (set, frozenset)):
        v = sorted(map(str, v))
    elif isinstance(v, dict):
        v = {str(k): _plain(x) for k, x in v.items()}
    elif isinstance(v, tuple) and v and callable(v[0]):
        v = [f.__name__ for f in v]
    elif isinstance(v, (tuple, list)):
        v = [_plain(x) for x in v]
    elif callable(v):
        v = getattr(v, "__name__", repr(v))
    text = json.dumps(v, ensure_ascii=False, sort_keys=True, default=str) if not isinstance(v, str) else repr(v)
    text = text if len(text) <= LONG else text[:LONG] + f"... ({len(text)} chars)"
    return "`" + text.replace("|", "\\|").replace("\n", " ") + "`"


def render() -> str:
    from eidolon.llm import ingress, provider, render as rn
    from eidolon.decision.turn import CANARY
    sub = lambda text: text.replace(CANARY, "{CANARY}")                                         # noqa: E731
    L = ["# EIDOLON - prompts and constants",
         "",
         "*Generated by `python -m eidolon.debug promptdoc` from the code; `tests/test_phase9_docs.py` fails when this file is not what the "
         "generator renders. Do not edit by hand.*",
         "",
         "Everything a model is told, everything it may answer, and every tunable number, in one place (Phase 9, §30). The canary is "
         "`eidolon.decision.turn.CANARY`; it appears below as `{CANARY}`. It lives in the generate system prompt and nowhere else.",
         "",
         "## 1. Model routes (I-11, I-42, ADR-12)",
         "",
         "| route | model | effort | notes |", "|---|---|---|---|",
         f"| parse | `{provider.MODEL}` | `{provider.EFFORT['parse']}` | intent parse; sees the player's line, the names the player may use and the addressee's name only |",
         f"| generate | `{provider.MODEL}` | `{provider.EFFORT['generate']}` | the dialogue renderer; sees the typed `RenderView` only |",
         f"| verify | `{provider.MODEL}` | `{provider.EFFORT['verify']}` | segments, their tagged claims (neutrally rendered), the names in play |",
         "| offline audit verifier | `claude-fable-5-1` | `low` (route constant) | the nightly audit (§24); a stronger model, same schema |",
         "",
         "A call is `complete(system, user, schema)` and nothing else: no tools, no functions, no network switches (I-11); the SDK client "
         "is built with `max_retries=0` and a 30 s timeout - every retry is the renderer's own, bounded and audited "
         f"(`max_repairs` = 2, so at most 3 generate calls per turn); a refusal is surfaced as an error; the latency floor is {rn.LATENCY_FLOOR_S} s.",
         "",
         "## 2. Prompts (verbatim)",
         "", "### Parse (`llm.ingress.SYSTEM_PARSE`)", "", "```text", sub(ingress.SYSTEM_PARSE), "```", "",
         "### Generate (`llm.render.SYSTEM_GENERATE`)", "", "```text", sub(rn.SYSTEM_GENERATE), "```", "",
         "### Verify (`llm.render.SYSTEM_VERIFY`)", "", "```text", sub(rn.SYSTEM_VERIFY), "```", "",
         "The user message of each route is one canonical JSON document (`sort_keys`, `ensure_ascii=False`). The player's line is a JSON "
         "string value, so it cannot close the structure it sits in; `GuardedTransport` refuses to send any prompt that carries an engine id "
         "or engine word, except inside the untrusted keys (`player_query`, `player_text`).", "",
         "## 3. Wire schemas (strict: duplicate keys, NaN, extra fields, over-size and over-depth are refused)", ""]
    for title, schema in (("Parse -> `PlayerAction`", ingress.ACTION_SCHEMA), ("Generate -> `Draft`", rn.DRAFT_SCHEMA), ("Verify", rn.VERIFY_SCHEMA)):
        L += [f"### {title}", "", "```json", json.dumps(schema, indent=1, sort_keys=True), "```", ""]
    L += ["## 4. Repair feedback (`llm.render._TEMPLATES`)", "",
          "Phrased in terms of what the model wrote, never why; constant apart from the segment index, so a name the model guessed is "
          "indistinguishable whether or not it exists (F-2).", "", "| violation code | feedback line |", "|---|---|"]
    L += [f"| `{k}` | {v.replace('|', chr(92) + '|')} |" for k, v in sorted(rn._TEMPLATES.items())]
    L += ["", "## 5. Stage-0 marker scan (`llm.ingress._MARKERS`, matched against the folded line: NFKD, marks dropped, casefolded)", "",
          "| marker | pattern |", "|---|---|"]
    L += [f"| `{k}` | `{v}` |" for k, v in sorted(ingress._MARKERS.items())]
    L += ["", "## 6. Constants, by module", "",
          "Every module-level constant, found by parsing the module's source. Prompts and schemas are in sections 2-3.", ""]
    for name, about in MODULES:
        mod, consts = _constants(name)
        if not consts:
            continue
        L += [f"### `eidolon.{name}`", "", about, "", "| constant | value | note |", "|---|---|---|"]
        L += [f"| `{n}` | {show(v)} | {NOTES.get(f'{name}.{n}', NOTES.get(n, ''))} |" for n, ln, v in consts]
        L.append("")
    return sub("\n".join(L)) + "\n"


def main(path="docs/EIDOLON-PROMPTS-AND-CONSTANTS.md") -> int:
    text = render()
    Path(path).write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {path} ({len(text)} chars)")
    return 0
