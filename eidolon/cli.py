"""`eidolon play` — the Phase 4 exit criterion's minimal CLI ("playable end-to-end with
TemplateLLM via CLI", roadmap §30), plus Phase 5's `--llm`: the same case rendered by a live
model through stages 0-2 (screen, parse, ground) and 7-9 (view, validate, repair, fallback).
`gen`/`validate` are Phase 6 (§27.3); `replay`/`trace`/`cost` belong to later phases.

Usage: `python -m eidolon.cli play` (free text is a `did_you` question; `present <ref>` presents
evidence; `quit`), or `python -m eidolon.cli play --llm` (needs `pip install eidolon[llm]` and
ANTHROPIC_API_KEY or an `ant auth login` profile).
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from .decision.demo import DAVID, build_demo_state
from .decision.query import Query
from .decision.turn import run_ask_turn


def encountered(state, addressee: str) -> frozenset[str]:
    """§22.2: grounding resolves names only against `player-encountered ∪ addressee-known`, "so
    name-guessing cannot enumerate the cast". The whole case is NOT that set (F-9) — handing it in
    tells the parser every actor, location and object exists before the player has met any of them,
    and re-opens at stage 1 the enumeration F-3 closed at stage 7.

    What the player has encountered is derived from the discovery fold: where they have been, what
    they hold, and what each discovered item is made of. The addressee is added because they are
    standing there being spoken to.

    ponytail: derived per turn from `DiscoveryState`; Phase 8's UI owns the real encountered ledger
    (statements heard, characters met off-screen) and should pass it in instead."""
    seen = {addressee, *state.discovery.visited_locations, *state.discovery.held_items}
    for eid in state.discovery.known_evidence:
        item = state.evidence.get(eid)
        if item is None:
            continue
        seen |= {i for i in (item.object, item.location_at_investigation) if i}
    return frozenset(seen)


def _run_play(transport=None, llm: bool = False, clock=time.monotonic, provider: str | None = None, model: str | None = None) -> None:
    state = build_demo_state()
    renderer = parser = None
    scripted = transport is not None
    if provider is not None and transport is None:
        from .llm.provider import free_transport
        transport = free_transport(provider, model)
    if llm or transport is not None:
        from .llm.ingress import ModelParser
        from .llm.provider import AnthropicTransport
        from .llm.render import LATENCY_FLOOR_S, LLMRenderer, ModelLLM
        model = ModelLLM(transport if transport is not None else AnthropicTransport())
        # I-42's latency floor (§12.3): held here, on the live path, so act class is not readable
        # from the clock. A scripted transport needs no floor because there is no model to time.
        renderer, parser = LLMRenderer(model, min_latency_s=0.0 if scripted else LATENCY_FLOOR_S), ModelParser(model.transport)
    print("Playing the demo case. Address David; 'present <ref>' to present evidence; 'quit' to stop.")
    turn_times: list[float] = []
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            break
        if not line or line.lower() in ("quit", "exit"):
            break
        presented_ref = None
        if line.lower().startswith("present "):  # irreversible actions are controls, never parsed (I-26)
            presented_ref = line[len("present "):].strip()
            query = Query(kind="challenge", raw=line)
        elif parser is not None:
            from .llm.ingress import Asked, Clarify, interpret, rate_window
            # F-8: how many turns fall inside the TRAILING WINDOW, not how many have ever happened.
            out = interpret(line, parse=parser.parse, case=state.case, known=encountered(state, DAVID),
                            addressee=DAVID, turns_in_window=rate_window(turn_times, clock()))
            if isinstance(out, Clarify):
                print(f"David: {out.text}")
                continue
            if not isinstance(out, Asked):
                print("(That could not be completed and nothing was recorded. Try again.)")
                continue
            query = out.query
        else:
            query = Query(kind="did_you", raw=line)
        result = run_ask_turn(state, DAVID, query, presented_ref=presented_ref, renderer=renderer)
        state = result.state
        turn_times.append(clock())
        if result.rejected:
            print("(That turn could not be completed and nothing was recorded. Try again.)")
            continue
        if renderer is not None:  # the player sees the words only — never the act (I-12)
            from .llm.render import player_view
            print(f"David: {player_view(result).text}")
        else:
            print(f"David [{result.plan_act}]: {result.text}")


def main(argv: list[str] | None = None, *, transport=None, clock=time.monotonic) -> int:
    """`clock` is injectable so the rate window (F-8) is testable without sleeping."""
    parser = argparse.ArgumentParser(prog="eidolon")
    sub = parser.add_subparsers(dest="command", required=True)
    play = sub.add_parser("play", help="Play the demo case (TemplateLLM, or a live model with --llm).")
    play.add_argument("--llm", action="store_true", help="Render with the Anthropic API (Phase 5).")
    play.add_argument("--provider", choices=["gemini", "groq", "github", "openrouter", "ollama"], default=None,
                      help="render with a FREE model instead (key from GEMINI_API_KEY / GROQ_API_KEY / GITHUB_MODELS_TOKEN / OPENROUTER_API_KEY; Ollama needs none)")
    play.add_argument("--model", default=None, help="model name for --provider (required for openrouter and ollama)")
    gen = sub.add_parser("gen", help="Generate, validate and seal a case (Phase 6).")
    gen.add_argument("--skeleton", default="study_party")
    gen.add_argument("--seed", type=int, default=1)
    gen.add_argument("--out", default=None, help="write the sealed package and its proof as JSON")
    gen.add_argument("--attempts", type=int, default=20, help="§20.2 band loop: max regeneration attempts")
    gen.add_argument("--bluffs", type=int, default=None, help="V-7 bluff turns per character (default: the architecture's 500; a reduced run cannot be persisted)")
    gen.add_argument("--odd", type=int, default=None, help="V-7 adversarial turns per character (default 500)")
    val = sub.add_parser("validate", help="Re-validate a sealed package and independently verify its proof.")
    val.add_argument("path")
    rep = sub.add_parser("replay", help="Load a save, verifying everything, and report its state hash (Phase 7).")
    rep.add_argument("path")
    rep.add_argument("--verify", action="store_true", help="accepted for §27.3's spelling; replay always verifies")
    new = sub.add_parser("newsave", help="Create a save from a sealed case bundle (Phase 7).")
    new.add_argument("bundle")
    new.add_argument("path")
    new.add_argument("--seed", type=int, default=0)
    srv = sub.add_parser("serve", help="Play in a browser (Phase 8): the player app on 127.0.0.1.")
    srv.add_argument("--saves", default="saves", help="directory of save files")
    srv.add_argument("--cases", default="cases/generated", help="directory of sealed case bundles")
    srv.add_argument("--port", type=int, default=8000)
    srv.add_argument("--llm", action="store_true", help="free text and model rendering through the Anthropic API (Phase 5)")
    srv.add_argument("--provider", choices=["gemini", "groq", "github", "openrouter", "ollama"], default=None,
                     help="free text and model rendering through a FREE model (key from GEMINI_API_KEY / GROQ_API_KEY / GITHUB_MODELS_TOKEN / OPENROUTER_API_KEY)")
    srv.add_argument("--model", default=None, help="model name for --provider (required for openrouter and ollama)")
    args = parser.parse_args(argv)
    if args.command == "serve":
        return _run_serve(args)
    if args.command == "replay":
        return _run_replay(args)
    if args.command == "newsave":
        return _run_newsave(args)
    if args.command == "play":
        _run_play(transport, args.llm, clock=clock, provider=args.provider, model=args.model)
    elif args.command == "gen":
        return _run_gen(args)
    elif args.command == "validate":
        return _run_validate(args)
    return 0


def _run_gen(args) -> int:
    """§30 Phase 6 exit: "`eidolon gen` produces sealed, IN-BAND cases" — so the CLI runs §20.2's
    loop, not one attempt. `--attempts 1` asks for the single-attempt primitive instead."""
    from .gen.pipeline import generate_in_band, write_package
    scale = {k: v for k, v in (('bluffs', args.bluffs), ('odd', args.odd)) if v is not None}
    band = generate_in_band(args.skeleton, args.seed, max_attempts=args.attempts, **scale)
    res = band.result
    if not band.ok:
        print(f"REJECTED after {band.attempts} attempt(s) at {res.failed_at}: {'; '.join(res.problems)[:400]}")
        for r in band.rejections[-args.attempts:]:
            print(f"  seed {r['seed']}: {r['stage']}: {'; '.join(r['problems'])[:200]}")
        return 1
    print(f"sealed {res.package.id} seal={res.package.seal[:16]}… murderer={res.package.solution.murderer} "
          f"attempts={band.attempts} metrics={res.report.metrics} in {res.seconds:.1f}s")
    if args.out:
        write_package(res, args.out)
    return 0


def _run_validate(args) -> int:
    """I-58: the ONLY way a sealed case is read is `load_sealed_case` — every seal, the independent proof verifier and the
    full-scale report — and only then is the package re-validated stage by stage."""
    from .gen.pipeline import validate
    from .solve.package import SealRefusal, load_sealed_case
    try:
        case = load_sealed_case(args.path)
    except SealRefusal as e:
        print(json.dumps({"ok": False, "failed_at": "load", "problems": [str(e)]}, indent=1))
        return 1
    rep = validate(case.package)
    print(json.dumps({"ok": rep.ok, "failed_at": rep.failed_at, "problems": rep.problems}, indent=1))
    return 0 if rep.ok else 1


def _run_replay(args) -> int:
    """§26.3 + §27.3: refuses on any chain/seal/fold failure; trace gaps are REPORTED, never treated as corruption."""
    from .store import Save, SaveError, SaveRefusal
    try:
        s = Save.open(args.path)
        digest = s.state_hash()
    except SaveRefusal as e:
        print(json.dumps({"ok": False, "error": str(e), "at_seq": e.seq}, indent=1))
        return 1
    except SaveError as e:
        print(json.dumps({"ok": False, "error": str(e), "at_seq": None}, indent=1))
        return 1
    except ValueError as e:                                   # a state that cannot be hashed is a refusal, not a traceback
        print(json.dumps({"ok": False, "error": f"state cannot be hashed: {e}", "at_seq": None}, indent=1))
        return 1
    print(json.dumps({"ok": True, "case": s.bundle.package.id, "turns": s.state.turn_counter, "rows": s.last_seq,
                      "state_hash": digest, "trace_gaps": len(s.trace_gaps())}, indent=1))
    return 0


def _run_serve(args) -> int:
    """Local single-player: bound to the loopback interface only — saves hold the sealed solution (§26.1)."""
    import uvicorn
    from pathlib import Path
    from .web import create_app
    Path(args.saves).mkdir(parents=True, exist_ok=True)
    live = {}
    if args.provider is not None:
        from .llm.provider import free_transport
        from .llm.render import LATENCY_FLOOR_S
        live = dict(transport=free_transport(args.provider, args.model), latency_floor_s=LATENCY_FLOOR_S)
    elif args.llm:
        from .llm.provider import AnthropicTransport
        from .llm.render import LATENCY_FLOOR_S
        live = dict(transport=AnthropicTransport(), latency_floor_s=LATENCY_FLOOR_S)
    uvicorn.run(create_app(args.saves, args.cases, port=args.port, **live), host="127.0.0.1", port=args.port)
    return 0


def _run_newsave(args) -> int:
    from .solve.package import SealRefusal
    import sqlite3
    from .store import Save, SaveError
    if not 0 <= args.seed < 2 ** 31:
        print("refused: the seed must be from 0 to 2147483647")
        return 1
    try:
        Save.create(args.path, args.bundle, seed=args.seed).close()
    except (SealRefusal, SaveError, OSError, sqlite3.Error) as e:
        print(f"refused: {type(e).__name__}: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
