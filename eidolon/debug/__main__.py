"""`python -m eidolon.debug <command>` - the debug tooling's own entry point (§27.3). It is not part of `eidolon.cli` on purpose: the
player-facing process imports `cli`, and nothing it imports may mention the debug package (I-10).

    serve   --saves DIR [--port 8001]      the debug server (EIDOLON_DEBUG=1; 127.0.0.1 only; never the player's port)
    trace   SAVE --turn N                  one turn's trace, handles resolved against the sealed case
    slo     SAVE [--json]                  the SLO dashboard from the save's traces
    audit   SAVE [--sample N] [--seed S] [--out DIR] [--live-verifier]
    nightly ...                            see `eidolon.debug.nightly`
    promptdoc                              regenerate docs/EIDOLON-PROMPTS-AND-CONSTANTS.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from ..store import Save, SaveRefusal


def _need_debug() -> bool:
    if os.environ.get("EIDOLON_DEBUG") != "1":
        print("the debug tooling is off unless asked: set EIDOLON_DEBUG=1", file=sys.stderr)
        return False
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="eidolon.debug")
    sub = ap.add_subparsers(dest="command", required=True)
    srv = sub.add_parser("serve")
    srv.add_argument("--saves", default="saves")
    srv.add_argument("--port", type=int, default=8001)
    tr = sub.add_parser("trace")
    tr.add_argument("save")
    tr.add_argument("--turn", type=int, required=True)
    sl = sub.add_parser("slo")
    sl.add_argument("save")
    sl.add_argument("--json", action="store_true")
    au = sub.add_parser("audit")
    au.add_argument("save")
    au.add_argument("--sample", type=int, default=None)
    au.add_argument("--seed", type=int, default=0)
    au.add_argument("--out", default=None, help="write each discrepancy as a regression fixture here")
    au.add_argument("--live-verifier", action="store_true", help="use a stronger model as the verifier (needs a key and the SDK)")
    sub.add_parser("nightly", add_help=False)
    sub.add_parser("promptdoc", help="regenerate docs/EIDOLON-PROMPTS-AND-CONSTANTS.md")
    args, rest = ap.parse_known_args(argv)
    if args.command == "nightly":
        from .nightly import main as nightly
        return nightly(rest)
    if args.command == "promptdoc":
        from .promptdoc import main as promptdoc
        return promptdoc()
    if rest:
        ap.error(f"unrecognised arguments: {' '.join(rest)}")
    if not _need_debug():
        return 2
    if args.command == "serve":
        from .app import PLAYER_PORT, create_debug_app
        if args.port == PLAYER_PORT:
            print("the debug server never shares the player's port", file=sys.stderr)
            return 2
        import uvicorn
        uvicorn.run(create_debug_app(args.saves, port=args.port), host="127.0.0.1", port=args.port)
        return 0
    try:
        save = Save.open(args.save)
    except SaveRefusal as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1
    if args.command == "trace":
        from .. import trace
        rows = dict(save.trace_rows())
        if args.turn not in rows:
            print(f"no trace for turn {args.turn} (a gap is expected after a crash)", file=sys.stderr)
            return 1
        table = trace.resolver(save)

        def res(x):
            if isinstance(x, str):
                return table.get(x, x)
            if isinstance(x, list):
                return [res(v) for v in x]
            return {k: res(v) for k, v in x.items()} if isinstance(x, dict) else x
        print(json.dumps(res(json.loads(rows[args.turn])), indent=1, sort_keys=True))
        return 0
    if args.command == "slo":
        from . import slo
        ms = slo.from_save(save)
        print(json.dumps([m.row() for m in ms], indent=1) if args.json else slo.render_text(ms))
        return 1 if any(m.status == "FAIL" for m in ms) else 0
    from . import audit
    verifier = None
    if args.live_verifier:
        from ..llm.provider import AnthropicTransport
        from .nightly import AUDIT_MODEL
        verifier = audit.model_verifier(AnthropicTransport(model=AUDIT_MODEL))
    rep = audit.audit_save(save, sample=args.sample, seed=args.seed, verifier=verifier)
    if args.out:
        audit.write_fixtures(rep, save.state, args.out)
    print(json.dumps({**rep.summary(), "findings": [{"statement": f.statement, "act": f.act, "violations": list(f.violations)}
                                                    for f in rep.findings]}, indent=1))
    return 1 if rep.status == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
