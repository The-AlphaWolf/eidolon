"""Phase 9 - everything that is allowed to see what the player must not (§27.2, I-10, ADR-13).

This package holds the debug server, the SLO calculation, the offline audit and the nightly job. It reads traces, saves and the
sealed case; it writes only audit fixtures, and only where it is told to. The player-facing process never imports it: a test
starts that process and asserts `eidolon.debug` is not in `sys.modules`, and another probes the player app's routes. Nothing in
`eidolon/` outside this package refers to it by name - it is started with `python -m eidolon.debug`, never from `eidolon.cli`.
"""
