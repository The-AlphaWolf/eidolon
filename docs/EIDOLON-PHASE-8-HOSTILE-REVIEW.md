# EIDOLON — Phase 8 hostile review

Date: 2026-10-20. Reviewer: a fresh-context Claude Code session started from the implementing session's session group. It did
not write Phase 8 and read the code cold. It is **not** a human reviewer and not a separate team, the same caveat
`docs/EIDOLON-PHASE-7-R1-INDEPENDENT-REVIEW.md` states for itself.

**Object.** The tree as found in `D:\Murder Mystery` on 2026-10-20. Manifest (sha256 over `path sha256` lines of the 184 `.py`
files under `eidolon/` and `tests/`): `131887d83261ee7ceb4e4a3472552b29e1477ddd6e4a234a9a9e212d672699bb`. Key files (sha256,
first 16 hex): `game.py aef7d23c79be9b2c`, `web.py 4a65d8ebad0f10cb`, `store.py 333a3df8f1d853b4`, `decision/turn.py
6527e700518cd960`, `decision/hypotheses.py ed2b418aba1f4c5c`, `decision/exploration.py 8f51bb5cdf24b213`, `solve/session.py
7b1fce761b0f8a01`, `tests/test_phase8.py caabaa219b5134ee`, `tests/test_persistence.py 9b35ccc766dbcf58`. The manifest was
recomputed after every run in this review and was identical. Outside `.hypothesis/`, this file is the only one in the
repository newer than the author's report.

**Method.** Contract read first: `CLAUDE.md`; `docs/EIDOLON-ARCHITECTURE.md` §2.2 (I-1…I-60), §5.2, §12.1, §13.4, §16, §17,
§19.4, §22, §26, §30; the author's record `docs/EIDOLON-PHASE-8-IMPLEMENTATION-REPORT.md`; `docs/EIDOLON-KNOWN-DEBT.md` §C/§D.
Then `eidolon/game.py`, `eidolon/web.py`, the Phase 8 parts of `eidolon/store.py`, `eidolon/decision/turn.py`
(`run_hypothesis_turn`, `run_accusation_turn`, provisional rows), `eidolon/decision/hypotheses.py`, `eidolon/decision/exploration.py`,
`eidolon/solve/session.py`, `tests/test_phase8.py` and the `P8_*` forgeries. Every attack ran from a scratch directory **outside
the repository**, importing the tree read-only (`python -B`, `sys.dont_write_bytecode`, no bytecode written), with every save in
a fresh temp directory. No production code, test, fixture or report was changed; this file is the only document added. The one
other write was a side effect of re-running the suite: Hypothesis's example database (`.hypothesis/examples/`, 7 files). It now
holds a real falsifying example (§3a). The repository has no VCS, so nothing was committed.

## Verdict

**NOT ACCEPTED.** 1 BLOCKING, 3 IMPORTANT, 9 NON-BLOCKING.

The store side of Phase 8 holds. `CaseSolved.correct` is derived and cannot be forged. Nothing follows the verdict in the log.
Final citations are held-only. Two independent sweeps of random page-valid forms on all four sealed cases (2,680 with the
Appendix B script, 2,661 with an earlier variant) each committed every form, with no crash and no wrongly refused genuine turn.
The claimed Phase 8 test, persistence, mutation and long-session figures re-measured as stated. The full suite is the one
exception: one random property test outside Phase 8 found a real counterexample in the Phase 6 proof verifier's feasibility
oracle (§3a, H8-X1, not graded here).

The **player-facing projection does not hold.** The theory board and the tension list read evidence implications the player
has not unlocked. In every sealed case, two searches and one throw-away theory per suspect, before any testimony, tell the player
**whose print is on the murder weapon**: the murderer (H8-B1). Search hints print the ids of undiscovered evidence onto the page, on the first move
of a `manor_wing` game (H8-I1). The CSRF guard falls to DNS rebinding (H8-I2). Two URL spellings of one game make two writers.
The store's duplicate verdict is then ignored, and the player is shown in-world answers that were never recorded, even after the
case is closed (H8-I3).

Phase 9 should not start until H8-B1, H8-I1, H8-I2 and H8-I3 are repaired, each with a regression test and a mutant (§6).

## Findings

| ID | Grade | Finding | Where |
|---|---|---|---|
| H8-B1 | **BLOCKING** | Theory board and tensions evaluate LOCKED implications. They name the murderer as the owner of the weapon print before the unlocking account (all 4 cases) | `decision/hypotheses.py` evaluators, `game._tensions` |
| H8-I1 | IMPORTANT | Search hints render raw prerequisite refs, so undiscovered evidence ids reach the page (§22.2 "Storage") | `decision/exploration._hint` → `game.search` |
| H8-I2 | IMPORTANT | DNS rebinding defeats the CSRF guard: Origin is compared with the attacker-controlled Host. No Host allow-list | `web._same_origin` |
| H8-I3 | IMPORTANT | `/g/g1` and `/g/G1` are two `Save`s on one file. `_commit` ignores `AppendResult`, so uncommitted in-world answers are shown, also after the verdict. The rate window is per spelling | `game._commit`, `web.Games`, `web.Chat.times` |
| H8-N1 | NON-BLOCKING | Turn-shape rules are narrower than documented. A provisional accusation's form fields are never checked (I-15 house rule) | `store._fold_turn` |
| H8-N2 | NON-BLOCKING | A typed line is parsed before the duplicate, stale and closed checks: re-parsed retries, model calls and in-world text after the verdict | `web.dispatch` (`say`) |
| H8-N3 | NON-BLOCKING | Free text can name only the addressee, visited places and held items, while the page lists the whole cast | `web.dispatch` → `cli.encountered` |
| H8-N4 | NON-BLOCKING | A multipart file part where a string is expected gives a 500. "Every form field is validated here" overstates | `web.dispatch`, `new_game` |
| H8-N5 | NON-BLOCKING | No anti-framing header: clickjacking gets past the Origin check | `web` responses |
| H8-N6 | NON-BLOCKING | Test gaps: two guards with no killing test (surviving mutants). The import check sees `web.py` only | `game.held_ref`, `web._RESERVED`, `test_phase8` |
| H8-N7 | NON-BLOCKING | Notebook cost is O(live theories × held material) per render, beyond D-8 | `game.notebook` |
| H8-N8 | NON-BLOCKING | UX and spec gaps: items renumber, the §16.1 "plainly" warning is missing, the time axis is satisfied by the whole evening, a retry shows no projection | `game`, `web` |
| H8-N9 | NON-BLOCKING (inherited, unrecorded) | No production caller passes `confession_check` (I-21). Latent in generated cases | `game.ask` → `run_ask_turn` |
| H8-X1 | outside scope (Phase 6), not graded | The proof verifier's feasibility oracle over-approximates (`tail_ok`). It fails one random property test of the full suite | `solve/oracle.py` → `solve/proof_material.py` |

Every reproduction below is a script meant to be saved next to the preamble `p8h.py` (Appendix A) in a scratch directory
outside the repository and run with `python -B <script>`. The outputs are the observed ones, verbatim except where shortened
with `…`. As a final check, every code block was extracted from this document and run verbatim in a fresh directory, and each
reproduced its documented output. Only the timings differ.

---

## 1. BLOCKING

### H8-B1 — the theory board and the tension list read implications the player has not unlocked; they identify the murderer

**Contract.** §5.2: "The player sees `reveals_text`, kind, location, and implications they have **unlocked**." Phase 3
implements exactly that (`evidence.discovery.unlocked_implications`, `project_for_player`, guarded by
`test_player_view_only_shows_unlocked_implications`). §16.1: the engine evaluates hypotheses "only against material the player
has". §22.2, Storage row: "UI payloads are built from player-visible projections only". §30 Phase 8 promises a "strict
projection layer". The author's record (§1, §3) claims "tensions between two HELD items" and that "the notebook re-evaluates
live, because the player's material keeps growing (§16.1 'from player-held material only')".

**Defect.** `decision/hypotheses.py` (`_evaluate_plain_proposition`, `_evaluate_lied`, `_evaluate_planted`) and `game._tensions`
iterate `ev.implications`, which includes every implication of a held item. Implications whose `requires` the player does not
hold are included. `evaluate_hypothesis` is what `game.notebook` shows live (status plus "consistent with … / against it: …").
The solver drops such an implication entirely: `solve/lattice.py` pass C, `_resolve(...) is None → continue`. The peel weight
uses `unlocked_implications` too (`weight.py:91`). Only the notebook does not.

**Impact.** In every sealed case the weapon print's only implication is locked behind the housekeeper's cleaning account, and it
names the murderer. Its `reveals_text` is just "A print on the weapon.":

| case | item | locked implication | requires |
|---|---|---|---|
| study_party_s4 | `E_trace` | `Did(David, touch, (41,120), Decanter, Study)` | `clean@Elena` |
| study_party_s5 | `E_trace` | `Did(Robert, touch, (23,120), Decanter, Study)` | `clean@Elena` |
| manor_wing_s4 | `E_trace` | `Did(Delphine, touch, (41,120), Paperweight, Office)` | `clean@Beatrix` |
| manor_wing_s6 | `E_trace` | `Did(Cormac, touch, (27,120), Paperweight, Office)` | `clean@Beatrix` |

The player finds the scene, dusts the weapon, and files one throw-away theory per suspect about a place no item names. The
board links the print to exactly one suspect: the murderer. No question has been asked, the account is not held, and the item's
implication is still locked. Two more channels show the same thing: the tension list, and a `Lied` theory on the murderer's
denial. This happens in the shipped browser flow, from the page's own controls.

**Reproduction** (`r_b1_locked_implication.py`):

```python
from p8h import *  # noqa
from eidolon.evidence.discovery import project_for_player, unlocked_implications

with client() as c:
    page = new_game(c)
    for _ in range(3):
        page = post(c, "g1", "search", page, target="Study", method="Look")        # scene, watch, door log
    page = post(c, "g1", "search", page, target="Decanter", method="Dust")         # E_trace: "A print on the weapon."
    s = c.app.state.games.open("g1")
    d = s.state.discovery
    tr = s.state.evidence.get("E_trace")
    print("held accounts:", sorted(d.known_accounts), "| held statements:", sorted(d.known_statements))
    print("E_trace implication:", tr.implications[0].proposition, "requires", tr.implications[0].requires)
    print("unlocked for the player:", unlocked_implications(tr, frozenset(d.known_evidence | d.known_statements | d.known_accounts)))
    print("Phase 3 player view:", project_for_player(tr, d).unlocked)
    for who in ("David", "Elena", "Margaret", "Robert"):     # a place no held item names: only the actor can link a theory to an item
        page = post(c, "g1", "hypothesize", page, kind="At", actor=who, location="Hall", start="00:00", end="00:10", confidence="50")
    for t in re.findall(r"<li>([^<]*? — \d+% — [^<]*)<form", page):
        print("THEORY:", t.strip())
    page = post(c, "g1", "ask", page, addressee="David", topic="heard")             # "I never touch a crystal decanter."
    print("TENSIONS:", re.findall(r"<li>([^<]*do not sit together\.)</li>", page))
    sid = sorted(s.state.discovery.known_statements)[0]
    page = post(c, "g1", "hypothesize", page, kind="Lied", statement=sid, confidence="50")
    print("THEORY:", [t.strip() for t in re.findall(r"<li>([^<]*? — \d+% — [^<]*)<form", page) if "lied" in t])
    print("still locked:", unlocked_implications(tr, frozenset(s.state.discovery.known_evidence | s.state.discovery.known_statements
                                                               | s.state.discovery.known_accounts)) == [])
```

Observed:

```
held accounts: [] | held statements: []
E_trace implication: kind='Did' actor='David' action='touch' interval=(41, 120) object='Decanter' target_actor=None location='Study' requires ('clean@Elena',)
unlocked for the player: []
Phase 3 player view: ()
THEORY: David was in the hall 00:00–00:10 — 50% — corroborated; consistent with item 4: fingerprint (a crystal decanter)
THEORY: Elena was in the hall 00:00–00:10 — 50% — corroborated; consistent with item 1: digital (the study)
THEORY: Margaret was in the hall 00:00–00:10 — 50% — open
THEORY: Robert was in the hall 00:00–00:10 — 50% — open
TENSIONS: ['statement 9 (David) and item 4: fingerprint (a crystal decanter) do not sit together.']
THEORY: ['David lied in statement 9 (David) — 50% — corroborated; consistent with item 4: fingerprint (a crystal decanter)']
still locked: True
```

The fingerprint is linked to David and to nobody else. Elena's line is her own unlocked door log. The study_party_s4 solution is
David.

The same attack on every sealed case (`r_b1_all_cases.py`). It finds the scene, dusts the weapon, then files one theory per
living suspect about a place no held item names:

```python
from p8h import *  # noqa
from eidolon.evidence.discovery import unlocked_implications
from eidolon.world.propositions import entities

for case in ("study_party_s4", "study_party_s5", "manor_wing_s4", "manor_wing_s6"):
    with client() as c:
        page = new_game(c, "g1", case=case)
        s = c.app.state.games.open("g1")
        ev = s.state.evidence
        scene, trace = ev.get("E_scene"), ev.get("E_trace")
        moves = 0
        while "E_scene" not in s.state.discovery.known_evidence:
            page = post(c, "g1", "search", page, target=scene.discovery.at, method=scene.discovery.action)
            moves += 1
        page = post(c, "g1", "search", page, target=trace.discovery.at, method=trace.discovery.action)
        moves += 1
        d = s.state.discovery
        assert "E_trace" in d.known_evidence and not d.known_statements and not d.known_accounts
        assert unlocked_implications(trace, frozenset(d.known_evidence | d.known_statements | d.known_accounts)) == []
        named = set().union(*[set().union(*entities(i.proposition)) for e in d.known_evidence for i in ev.get(e).implications])
        quiet = sorted(set(s.state.case.locations) - named - {e_.discovery.at for e_ in map(ev.get, d.known_evidence)})[0]
        label = next(x["label"] for x in game.notebook(s)["evidence"] if x["ref"] == game.handle(s, "E_trace"))
        linked = []
        for who in sorted(s.state.characters):
            page = post(c, "g1", "hypothesize", page, kind="At", actor=who, location=quiet, start="00:00", end="00:10", confidence="50")
            h = next(x for x in game.notebook(s)["hypotheses"] if x["text"].startswith(game.name(s.state.case, who)))
            if label in h["support"] + h["against"]:
                linked.append(who)
        print(f"{case}: {moves} searches + 1 theory per suspect about {quiet!r}; tied to '{label}': {linked}; "
              f"proven murderer: {s.state.murderer}")
```

Observed:

```
study_party_s4: 2 searches + 1 theory per suspect about 'BackSteps'; tied to 'item 2: fingerprint (a crystal decanter)': ['David']; proven murderer: David
study_party_s5: 2 searches + 1 theory per suspect about 'BackSteps'; tied to 'item 2: fingerprint (a crystal decanter)': ['Robert']; proven murderer: Robert
manor_wing_s4: 2 searches + 1 theory per suspect about 'Conservatory'; tied to 'item 2: fingerprint (a brass paperweight)': ['Delphine']; proven murderer: Delphine
manor_wing_s6: 2 searches + 1 theory per suspect about 'Conservatory'; tied to 'item 1: fingerprint (a brass paperweight)': ['Cormac']; proven murderer: Cormac
```

**Why the tests missed it.** `test_no_projection_serializes_an_engine_only_field_or_identifier` searches pages for ids and
engine words. This leak carries no id. `test_every_notebook_tension_is_between_two_items_the_player_holds` checks that both
sides are held items, and they are. No test asks whether the *implication* behind a tension or a theory is unlocked.

**Required fix.**
1. Evaluate only `unlocked_implications(ev, known)` in all three hypothesis evaluators and in both evidence paths of
   `game._tensions` (claim against implication, evidence against evidence). `known` is
   `known_evidence | known_statements | known_accounts`, the set `weight.py:184` unlocks against (it also adds the presented
   item).
2. Apply §13.2's `strength >= 0.5` floor in `_evaluate_plain_proposition`, as `evidence_implication_contradicts` already does.
3. Hardening, no observable leak in the four cases today: `game.notebook` takes the forms' object vocabulary from
   `solve.bots.held_names`, which reads every implication, locked ones included. Build a player-side list from unlocked material
   instead. Do not change `held_names` itself: it is the V-7 bots' function, and changing it changes what seals.
4. Add a regression test, on every sealed case: while the cleaning account is unheld, no theory status, support/against label or
   tension references `E_trace`. After the account is heard, they may. Add one mutant per filter.

Replay is unaffected. `HypothesisChanged` rows store the commit-time evaluation and the fold applies them as recorded (I-22), so
old saves load unchanged.

---

## 2. IMPORTANT

### H8-I1 — search hints print the ids of undiscovered evidence onto the page

**Contract.** §22.2, Storage row: "player never receives IDs of undiscovered evidence". §30 Phase 8 test: "assert no engine-only
field names/IDs". The author claims "no … evidence id … reaches a page".

**Defect.** `decision/exploration._hint` formats `_HINT_TEMPLATES[p.kind].format(ref=p.ref)`. That gives "You would need to
find {ref} first." with the raw `EvidenceId`, and the same raw form for `StatementId`, kit and location refs. `game.search`
shows the runner's `text` as the in-world reply. In `manor_wing_s4` and `_s6`, `E_gate_Terrace` (Terrace / Look) requires
`EvidenceFound(E_pin_clean)`. The Terrace is on every page's search list, so a first-move "look round the terrace" prints
`E_pin_clean`. In `study_party_s4` the murderer's denial ("I never touch a crystal decanter") puts the Decanter on the search
list before the scene is found. Dusting it then prints `E_scene`. The author's own `_leaks()` predicate flags both pages.

**Reproduction** (`r_i1_hint_ids.py`):

```python
from p8h import *  # noqa
sys.path.insert(0, str(ROOT))
from tests.test_phase8 import _leaks                 # the author's own leak predicate

with client() as c:
    page = new_game(c, "m", case="manor_wing_s4")
    assert '<option value="Terrace">' in page                     # every page offers every place as a search target
    out = post(c, "m", "search", page, target="Terrace", method="Look")
    s = c.app.state.games.open("m")
    print("manor_wing_s4, first action, look round the terrace ->", last_action(out))
    print("   _leaks():", _leaks(out, s), "| E_pin_clean held:", "E_pin_clean" in s.state.discovery.known_evidence)

    page = new_game(c, "p")                                       # study_party_s4
    page = post(c, "p", "ask", page, addressee="David", topic="heard")
    print("study_party_s4, ask David ->", last_action(page))
    print("   the decanter is now offered as a search target:", '<option value="Decanter">' in page)
    out = post(c, "p", "search", page, target="Decanter", method="Dust")
    s = c.app.state.games.open("p")
    print("   dust it ->", last_action(out), "| _leaks():", _leaks(out, s))
```

Observed:

```
manor_wing_s4, first action, look round the terrace -> | Look: the terrace | | You would need to find E_pin_clean first. |
   _leaks(): ['E_pin_clean'] | E_pin_clean held: False
study_party_s4, ask David -> | To David: “I&#39;d like to ask you about what was heard.” | | David: I never touch a crystal decanter. |
   the decanter is now offered as a search target: True
   dust it -> | Dust: a crystal decanter | | You would need to find E_scene first. | | _leaks(): ['E_scene']
```

**Required fix.** A hint names only what the player may see. For `EvidenceFound` and `StatementHeard`, use a generic in-world
line that names no item ("Something else would have to turn up first."). For `HasItem` and `KnowsAbout`, use the object's or
place's display name (`game.name`). Add a regression test: from a blank save of every sealed case, search every place and object
with every method, and assert `_leaks()` is empty on every resulting page. Add a mutant that restores `{ref}`.

### H8-I2 — DNS rebinding defeats the CSRF guard

**Contract.** The author claims "a cross-site POST is refused — no cookie identifies a player, so this is the CSRF guard". The
`serve` docstring says "bound to the loopback interface only — saves hold the sealed solution (§26.1)". §22.1 lists "engine
state" and "cost" as assets.

**Defect.** `web._same_origin` accepts a POST when `Origin`'s host:port equals the request's **own** `Host` header. Nothing
checks that `Host` is `127.0.0.1` or `localhost`. Neither Starlette nor uvicorn does by default, and `TrustedHostMiddleware` is
not installed. With DNS rebinding, `attacker.example` first serves a page and is then re-pointed at `127.0.0.1`. The page's
requests now go to the player's server, carrying `Host: attacker.example:8000` and `Origin: http://attacker.example:8000`. The
check passes, and the browser treats the responses as same-origin, so the page can read them. The attacker can list saves, read
notebooks, create games and make final accusations. With `--llm`, it can also spend the player's API budget. H8-I3 multiplies
that, because the rate window is per URL spelling. Chrome's Private Network Access may block this in some versions. Firefox and
Safari do not implement it. The standard fix is server-side Host validation.

**Reproduction** (`r_i2_rebinding.py`, the TestClient's `base_url` sets the Host header a rebound browser would send):

```python
from p8h import *  # noqa

EVIL = "http://attacker.example:8123"              # after rebinding, attacker.example resolves to 127.0.0.1
saves = tmpdir()
with client(saves, base_url=EVIL) as c:            # every request carries Host: attacker.example:8123
    hdr = {"origin": EVIL}
    r = c.post("/new", data={"name": "victim", "case": "study_party_s4", "seed": "7"}, headers=hdr, follow_redirects=False)
    print("POST /new from the attacker's page:", r.status_code, r.headers.get("location"))
    print("GET / readable by that page (same-origin to the browser):", "/g/victim" in c.get("/").text)
    page = c.get("/g/victim").text
    r = c.post("/g/victim", data={"op": "accuse", **hidden(page, "accuse"), "suspect": "Elena", "confirm": "on"}, headers=hdr)
    print("POST final accusation:", r.status_code, "|", last_action(r.text))
    print("on disk:", [k for (k,) in sqlite3.connect(saves / "victim.db").execute("SELECT kind FROM session_events")])
    print("control, foreign Origin with the real Host:", c.post("/g/victim", data={"op": "goto"}, headers={"origin": "http://evil.example"}).status_code)
```

Observed:

```
POST /new from the attacker's page: 303 /g/victim
GET / readable by that page (same-origin to the browser): True
POST final accusation: 200 | | You accuse Elena, citing 0 item(s) | | The case is closed. |
on disk: ['TurnCommitted', 'Accusation', 'CaseSolved']
control, foreign Origin with the real Host: 403
```

**Required fix.**
- Refuse any request whose `Host` is not `127.0.0.1:<port>` or `localhost:<port>`, for example with
  `TrustedHostMiddleware(allowed_hosts=["127.0.0.1", "localhost"])` plus a port check.
- Compare `Origin` with that allow-list, not with `Host`.
- Add a test: a POST and a GET with a foreign Host and a matching Origin are both refused.
- Add a mutant that drops the Host check.

### H8-I3 — two URL spellings of one game make two writers; `_commit` then shows answers that were never recorded

**Contract.** §26.2: a duplicate `action_id` "returns the existing turn's projection". I-15: a stage failure "commits nothing and
shows no in-world text". The author claims "a re-sent form returns its committed turn" and "every control commits ONLY via
`game._commit` → `Save.append`". §22.2 Ingress: a "per-session rate" limit.

**Defect.** Two faults combine.

1. `web.Games._open` is keyed by the URL's spelling of the name. NTFS is case-insensitive, so `/g/g1` and `/g/G1` resolve to the
   same `g1.db` but open two `Save` objects, each with its own in-memory state, head and `_actions`. Two `eidolon serve`
   processes on one saves directory would do the same by the same mechanism (not run separately).
2. `game._commit` decides "duplicate" only from the in-memory `save.turn_for()`. It discards the `AppendResult` that
   `Save.append` returns: `appended=False` together with the store's own `same_events` verdict.

So in a second tab opened at `/g/G1`, the form `ask@0` (deterministic ids, D-6) is not a duplicate to *its* `Save`. The runner
runs on the stale state. `Save.append` finds `ask@0` on disk and returns `appended=False`. `_commit` then reports **ok** with the
runner's in-world reply. That answer was never recorded. The tab stays at turn 0 forever. Every same-id form gives a fresh,
unrecorded answer from a stale state, and keeps doing so after the case is closed. `Chat.times` is keyed by `str(save.path)`, so
every spelling also has its own rate window: 8 spellings of "abc" give 240 parse calls inside one 30-per-window budget, and a
10-letter name has 1,024 spellings.

**Reproduction** (`r_i3_alias.py`):

```python
import json
from p8h import *  # noqa
from eidolon.llm.fakes import ScriptedTransport
from eidolon.llm.ingress import RATE_LIMIT
sys.path.insert(0, str(ROOT))
from tests.llm.llm_helpers import approve, faithful

saves = tmpdir()
with client(saves) as c:
    a = new_game(c)
    b = c.get("/g/G1").text
    games = c.app.state.games
    print("cached:", sorted(games._open), "same file:", games._open["g1"].path.resolve() == games._open["G1"].path.resolve())
    print("ask ids — tab A:", hidden(a, "ask"), "tab B:", hidden(b, "ask"))
    a = post(c, "g1", "ask", a, addressee="Elena", topic="presence")
    print("A:", turn_line(a), "|", last_action(a)[-60:])
    for who, topic in (("Robert", "did"), ("David", "heard")):
        rb = post(c, "G1", "ask", b, addressee=who, topic=topic)
        print("B:", turn_line(rb), "|", last_action(rb)[-70:])
    a = post(c, "g1", "accuse", a, suspect="David", confirm="on")
    print("A:", turn_line(a))
    rb = post(c, "G1", "ask", b, addressee="Margaret", topic="did", accuse="on")
    print("B after the verdict:", turn_line(rb), "|", last_action(rb)[-80:])
    st = Save.open(saves / "g1.db").state
    print("on disk: turns", st.turn_counter, "| speakers", [x.speaker for x in st.decision.statements.all()],
          "| provisional accusations", [x.target for x in st.decision.accusations if x.provisional])

# the ingress rate window is keyed by the URL's spelling of the save
t = ScriptedTransport(generate=[faithful()], verify=[approve], parse=[json.dumps({"kind": "clarify"})] * 1000, repeat_last=True)
with client(transport=t, clock=lambda: 100.0) as c:                                 # one frozen instant = one window
    new_game(c, "abc")
    for spelling in ("abc", "ABC", "Abc", "aBc", "abC", "ABc", "AbC", "aBC"):
        page = c.get(f"/g/{spelling}").text
        for _ in range(RATE_LIMIT + 1):
            post(c, spelling, "say", page, addressee="Elena", text="Hmm?")
    print(f"RATE_LIMIT {RATE_LIMIT}/window; parse calls made inside one window for one save: {t.calls('parse')}")
```

Observed:

```
cached: ['G1', 'g1'] same file: True
ask ids — tab A: {'action_id': 'ask@0', 'expected_seq': '0'} tab B: {'action_id': 'ask@0', 'expected_seq': '0'}
A: Turn 1 · The investigation is open. · | …| Elena: I was in the hall from 01:20 until 01:31. |
B: Turn 0 · The investigation is open. · | …| Robert: I was in the kitchen from 01:34 until 01:52. |
B: Turn 0 · The investigation is open. · | …| David: I never touch a crystal decanter. |
A: Turn 2 · The case is closed. ·
B after the verdict: Turn 0 · The investigation is open. · | and you accuse them | | Margaret: I was in the library from 00:17 until 00:38. |
on disk: turns 2 | speakers ['Elena'] | provisional accusations []
RATE_LIMIT 30/window; parse calls made inside one window for one save: 240
```

Robert's, David's and Margaret's answers, and the provisional accusation, were shown as done and are not in the save.

A GET needs no Origin, so a page on any site can trigger the same multiplication with `<img src>` tags. Each new spelling of a
guessable game name opens, fully verifies and caches another `Save` on the single event loop (`r_i3_gets.py`):

```python
import time
from p8h import *  # noqa

saves = tmpdir()
s = Save.create(saves / "game.db", CASES / "study_party_s4.json", seed=7)
for _ in range(4):
    for ev in sorted(s.state.evidence.all(), key=lambda e: e.id):
        if ev.id not in s.state.discovery.known_evidence:
            game.search(s, f"s@{s.last_seq}", s.last_seq, ev.discovery.at, ev.discovery.action)
for i in range(150):
    who = sorted(s.state.characters)[i % 4]
    game.ask(s, f"a@{s.last_seq}", s.last_seq, who, game.question(s.state.case, who, topic=["presence", "did", "heard"][i % 3], bucket=i % 4))
print("save: turns", s.state.turn_counter, "rows", s.last_seq)
s.close()
with client(saves) as c:
    t0 = time.perf_counter()
    spellings = ["game", "Game", "gAme", "gaMe", "gamE", "GAme", "GaMe", "GamE"]
    codes = [c.get(f"/g/{x}", headers={"referer": "http://evil.example/"}).status_code for x in spellings]
    print("GET status:", codes, f"| {time.perf_counter() - t0:.1f}s for {len(spellings)} GETs | Saves cached: {len(c.app.state.games._open)}")
```

Observed:

```
save: turns 160 rows 810
GET status: [200, 200, 200, 200, 200, 200, 200, 200] | 20.2s for 8 GETs | Saves cached: 8
```

That is about 2.5 s of blocked server per spelling (18.5 s for the 8 on a re-run), measured beside the full suite. A
`tracemalloc` run measured about 3 MiB of state per cached `Save`. "game" has 16 spellings; a 10-letter name has 1,024.

**Required fix.**
- `_commit` must honour `AppendResult`. `appended=False` is a duplicate. It shows the committed turn's projection and never the
  recomputed reply. `same_events=False` (a different action under a reused id) should read as stale, which also repairs D-6's
  message.
- Key `Games._open` and `Chat.times` by the resolved, case-folded path, or refuse a name whose on-disk spelling differs.
- Add tests for the second-spelling tab (no uncommitted text, one rate window per save) and for a duplicate that the store
  detects but the cache missed. Add mutants for both.

---

## 3. NON-BLOCKING

### H8-N1 — the Phase 8 turn-shape rules are narrower than the report states; a provisional accusation's form is unchecked

The report's §4 table says "A final accusation is a turn of its own" and "A board edit is a turn of its own". The fold enforces
only "not inside a conversation" (`who is not None`). Board edits, moves, `PlayerAction`, `FallbackUsed` and `ValidationFailure`
rows, and rows between the accusation and `CaseSolved`, all ride along. A provisional accusation is checked only for
target = addressee and for the detective-model entry. Its solution-form fields (`cited`, `weapon`, `location`, `interval`,
`motive_kind`) are never checked. Unheld and non-existent citations, a ghost weapon and place, and a `2**40` window are therefore
accepted. That is the I-15 house rule ("unresolvable references resolve to refusal") and the F-1 class. Nothing reads these fields
today (`game.report` reads finals only), so this is latent, like F1-b. A final accusation's `motive_kind` is not checked against
the case's vocabulary, although `weapon` and `location` are. Two provisional accusations can share one turn, leaving
`decision.accusations` with two entries and the accused's model with one. None of this changes a verdict or crashes a page: all
accepted forgeries render with status 200 or 404. They are C-1-class forgeries, but the report claims rules that do not exist.

**Reproduction** (`r_n1_shapes.py`; `offer` is in the preamble):

```python
from p8h import *  # noqa
from eidolon.decision.events import CaseSolved, FallbackUsed, HypothesisChanged, PlayerActionLogged, ValidationFailure
from eidolon.decision.exploration import LocationVisited
from eidolon.decision.turn import run_accusation_turn, run_ask_turn, run_goto_turn, run_hypothesis_turn
from eidolon.world.propositions import At

base = tmpdir() / "base.db"                      # like tests/test_phase8.py's `played` fixture
s = Save.create(base, CASES / "study_party_s4.json", seed=7)
game.goto(s, "goto@0", 0, "Study")
for _ in range(4):
    for ev in sorted(s.state.evidence.all(), key=lambda e: e.id):
        if ev.id not in s.state.discovery.known_evidence:
            game.search(s, f"search@{s.last_seq}", s.last_seq, ev.discovery.at, ev.discovery.action)
for who in sorted(s.state.case.living_actors()):
    game.ask(s, f"ask@{s.last_seq}", s.last_seq, who, game.question(s.state.case, who, topic="presence"))
st = s.state
s.close()
t, held = st.turn_counter + 1, sorted(st.discovery.known_evidence)


def swap(events, kind, **update):
    return tuple(e.model_copy(update=update) if e.kind == kind else e for e in events)


ask = run_ask_turn(st, "Margaret", game.question(st.case, "Margaret", topic="presence"), provisional_accusation=True).events
acc = next(e for e in ask if e.kind == "Accusation")
final = run_accusation_turn(st, "David", weapon="Decanter", location="Study", interval=(55, 65), motive_kind="blackmail", cited=held).events
hyp = run_hypothesis_turn(st, (At(actor="Elena", location="Study", interval=(50, 60)),), 5000).events
h = hyp[1].hypothesis
minds = ("PressureChange", "ComposureChange", "DetectiveModelUpdate", "CoverStateDelta")
cases = {
    "provisional accusation with an unheld/nonexistent cite, ghost weapon & place, a 2**40 window, any motive":
        swap(ask, "Accusation", cited=("E_never_existed", "S99999"), weapon="Excalibur", location="Atlantis", interval=(0, 2 ** 40), motive_kind="?"),
    "two provisional accusations in one turn (decision has 2, the accused's model 1)":
        tuple(e for e in ask if e.kind not in minds) + (acc.model_copy(update={"motive_kind": "x"}),) + tuple(e for e in ask if e.kind in minds),
    "final accusation turn that also edits the board": final[:1] + (HypothesisChanged(hypothesis=h.model_copy(update={"id": "Hx"})),) + final[1:],
    "final accusation turn that also moves the detective": final[:1] + (LocationVisited(location="Hall", turn=t),) + final[1:],
    "final accusation turn that also logs an action, a fallback and a validation failure":
        final[:1] + (PlayerActionLogged(turn=t, raw_text="anything", parsed_kind="teleport"), FallbackUsed(turn=t), ValidationFailure(turn=t, check="x")) + final[1:],
    "a row between the final accusation and CaseSolved": final[:2] + (LocationVisited(location="Hall", turn=t),) + final[2:],
    "final accusation with a motive outside the case's vocabulary": swap(final, "Accusation", motive_kind="<b>buried treasure</b>"),
    "a board edit riding on a goto turn": run_goto_turn(st, "Hall").events + (hyp[1],),
    "two board edits of one theory in one turn": hyp + (HypothesisChanged(hypothesis=h.model_copy(update={"player_confidence": 0.9})),),
    "a theory with no proposition": (hyp[0], HypothesisChanged(hypothesis=h.model_copy(update={"propositions": ()}))),
    "CONTROL CaseSolved.correct flipped": swap(final, "CaseSolved", correct=False),
    "CONTROL provisional accusation of someone not addressed": swap(ask, "Accusation", target="David"),
    "CONTROL final accusation citing an unheld item": swap(final, "Accusation", cited=("E_never_existed",)),
}
for name, evs in cases.items():
    a, l = offer(base, evs)
    print(f"{name}\n    append: {a}\n    load:   {l}")

# the accepted forgeries, re-chained into a saves directory and served
saves = tmpdir()
for i, (name, evs) in enumerate(n for n in cases.items() if not n[0].startswith("CONTROL")):
    shutil.copy(base, saves / f"f{i}.db")
    inject(saves / f"f{i}.db", evs, "forged")
with client(saves, raise_server_exceptions=False) as c:
    print("served:", [(f"f{i}", c.get(f"/g/f{i}").status_code, c.get(f"/g/f{i}/report").status_code) for i in range(10)])
```

Observed: every non-CONTROL case reports `append: ACCEPTED` / `load: ACCEPTED`. The three controls are refused at both
boundaries, for example `refused (CaseSolved.correct=False disagrees with the proven murderer (PN-10))` and
`refused (seq 47: Accusation cites 'E_never_existed', which the player does not hold)`. All ten accepted forgeries serve:

```
served: [('f0', 200, 404), ('f1', 200, 404), ('f2', 200, 200), ('f3', 200, 200), ('f4', 200, 200), ('f5', 200, 200), ('f6', 200, 200), ('f7', 200, 404), ('f8', 200, 404), ('f9', 200, 404)]
```

The report pages that answer 200 are f2–f6, the forgeries that carry a verdict. The others answer 404 because no verdict
exists yet.

**Fix (recommended with the next `store.py` change).**
- Require the exact runner shapes: `[TurnCommitted(None), HypothesisChanged]` and
  `[TurnCommitted(None), Accusation(final), CaseSolved]`.
- A provisional accusation carries the default form: no weapon, place, window or motive, and `cited=()`. At most one per turn.
- `motive_kind` is either None or in the skeleton's menu.
- Add one mutant and one single-defect forgery for each rule, as for R-1.

### H8-N2 — a typed line is parsed before the duplicate, stale and closed checks

`dispatch` (`op=say`) calls `interpret` (a parse model call) and only then `game.ask/goto/search` → `_commit`. As a result:

- A re-sent typed line (F5, lost response) is parsed again.
- A re-parse into `clarify` says "Nothing was recorded." for a line that **was** recorded.
- A re-parse into another action shows that action's chip over the committed turn.
- A stale or post-verdict line costs a model call, and the player gets in-world text after `CaseSolved`.

**Reproduction** (`r_n2_n3_free_text.py`, first half):

```python
from p8h import *  # noqa
from eidolon.llm.fakes import ScriptedTransport
sys.path.insert(0, str(ROOT))
from tests.llm.llm_helpers import approve, faithful


def chat():
    t = ScriptedTransport(generate=[faithful()], verify=[approve], repeat_last=True)
    return t, client(transport=t, clock=lambda: 100.0)


t, c = chat()
with c:
    page = post(c, "g1", "goto", new_game(c), location="Study")
    form = {"op": "say", **hidden(page, "say"), "addressee": "Elena", "text": "Were you in the study?"}
    t.queues["parse"] = [json.dumps({"kind": "ask", "query_kind": "did_you", "location": "the study", "predicate_hint": "presence"}),
                         json.dumps({"kind": "clarify"}), json.dumps({"kind": "goto", "target": "the study"})]
    for i in range(3):                                    # the browser re-sends the same form (lost response, F5)
        out = c.post("/g/g1", data=form).text
        print(f"send {i + 1}: parse calls {t.calls('parse')} | {turn_line(out)} | {last_action(out)[:120]}")
    page = post(c, "g1", "accuse", out, suspect="David", confirm="on")
    t.queues["parse"].append(json.dumps({"kind": "clarify"}))
    n = t.calls("parse")
    out = c.post("/g/g1", data={"op": "say", "action_id": "say@x", "expected_seq": "0", "addressee": "Elena", "text": "Hello?"}).text
    print(f"after the verdict, a stale typed line: parse calls {n} -> {t.calls('parse')} | {turn_line(out)} | {last_action(out)}")
```

Observed:

```
send 1: parse calls 1 | Turn 2 · The investigation is open. · | | To Elena: “Were you in the study?” — understood as: did you, about who was where, in the study | | Elena: Well, I was …
send 2: parse calls 2 | Turn 2 · The investigation is open. · | | To Elena | | Elena: I&#39;m not sure what you mean. | | Nothing was recorded. |
send 3: parse calls 3 | Turn 2 · The investigation is open. · | | Go to the study | | Already recorded as turn 2: this form was sent before. Nothing new was recorded. |
after the verdict, a stale typed line: parse calls 3 -> 4 | Turn 3 · The case is closed. · | | To Elena | | Elena: I&#39;m not sure what you mean. | | Nothing was recorded. |
```

**Fix.** Run `_commit`'s three pre-checks (duplicate, stale, closed) before `interpret`. Keep the rate-window entry for lines
that are actually parsed.

### H8-N3 — free text can name only the addressee, visited places and held items

`dispatch` passes `cli.encountered(st, who)`, which contains the addressee, visited places, held items and the objects and
locations of held evidence. It contains no other person, and no statement-named entity. `encountered`'s own docstring hands this
to Phase 8: "Phase 8's UI owns the real encountered ledger … and should pass it in instead." That was not done. Meanwhile the
structured form lists the whole cast under "Concerning" and every place, so the §22.2 enumeration concern does not apply. Typed
"Did you see David?" to Elena gets "I'm not sure what you mean." The same question from the form is answered.
`test_an_unclear_or_unknown_line_gets_one_in_world_answer…` treats Harold, who is listed on the page, as an "unmet" person.

**Reproduction** (`r_n2_n3_free_text.py`, second half):

```python
t, c = chat()
with c:
    page = new_game(c)
    print("'Concerning' on the structured form:", re.findall(r'<option value="(\w+)">', re.search(r'id="ask-about".*?</select>', page, re.S).group(0)))
    t.queues["parse"].append(json.dumps({"kind": "ask", "query_kind": "did_they", "subject": "David", "predicate_hint": "presence"}))
    out = post(c, "g1", "say", page, addressee="Elena", text="Did you see David?")
    print("typed 'Did you see David?' ->", last_action(out))
    out = post(c, "g1", "ask", page, addressee="Elena", about="David", topic="presence")
    print("structured, concerning David ->", last_action(out)[:130])
```

Observed:

```
'Concerning' on the structured form: ['David', 'Elena', 'Harold', 'Margaret', 'Robert']
typed 'Did you see David?' -> | To Elena | | Elena: I&#39;m not sure what you mean. | | Nothing was recorded. |
structured, concerning David -> | To Elena: “I&#39;d like to ask you about who was where concerning David.” | | Elena: I really cannot say. |
```

**Fix.** Pass the public cast and places (`solve.queries.public_names`), plus everything named by held material, as `known`.
Change the test to use a genuinely unknown name.

### H8-N4 — a multipart file part where a string is expected gives a 500; "every form field is validated here" overstates

`request.form()` yields an `UploadFile` for a multipart file part. `int(UploadFile)` and `NAME.fullmatch(UploadFile)` raise
`TypeError`, which `dispatch` and `new_game` do not catch (they catch only `ValueError`). Nothing is committed and the 500 body is
the bare "Internal Server Error", so this is robustness, not a leak. Separately, the module docstring's "Every form field is
validated here, at the trust boundary" overstates. `goto.location`, `withdraw.hypothesis`, `accuse.suspect`, `ask.addressee` and
`search.method` reach `game`/the runners raw and are refused there. Fuzzing found no crash through those paths.

**Reproduction** (`r_n4_n5_boundary.py`):

```python
from p8h import *  # noqa

with client(raise_server_exceptions=False) as c:
    page = new_game(c)
    r = c.post("/g/g1", data={"op": "goto", "location": "Hall", "action_id": "goto@0"}, files={"expected_seq": ("f", b"0")})
    print("expected_seq sent as a file part:", r.status_code, r.text)
    r = c.post("/g/g1", data={"op": "hypothesize", **hidden(page, "hypothesize"), "kind": "At", "actor": "Elena", "location": "Study",
                              "start": "00:10", "end": "00:20"}, files={"confidence": ("f", b"50")})
    print("confidence sent as a file part:", r.status_code, r.text)
    r = c.post("/new", data={"case": "study_party_s4", "seed": "7"}, files={"name": ("f", b"g2")})
    print("/new name sent as a file part:", r.status_code, r.text)
    print("game page response headers:", dict(c.get("/g/g1").headers))
```

Observed:

```
expected_seq sent as a file part: 500 Internal Server Error
confidence sent as a file part: 500 Internal Server Error
/new name sent as a file part: 500 Internal Server Error
game page response headers: {'content-length': '8651', 'content-type': 'text/html; charset=utf-8'}
```

**Fix.** Read only `str` values: a non-`str` value is treated as absent or refused. Correct the docstring.

### H8-N5 — no anti-framing header

The last line of the H8-N4 reproduction shows every page served with no `X-Frame-Options` and no CSP `frame-ancestors`. A page
on another site can frame `http://127.0.0.1:8000/g/<name>`. Its POSTs carry the server's own Origin, so the CSRF guard passes,
and a click-driven player can be steered through the two clicks of a final accusation. **Fix.** Send
`X-Frame-Options: DENY` and `Content-Security-Policy: frame-ancestors 'none'`. Add a test.

### H8-N6 — test gaps: two guards no test kills, and an import check that sees only `web.py`

The mutation harness (171 mutants) has no entry for two Phase 8 guards. Both survive the whole of `tests/test_phase8.py`. In a
scratch copy of `eidolon/`, `tests/`, `cases/` and `pyproject.toml`, with both edits applied, the run gives
`106 passed in 423.67s`, exit 0.

- **M-a**, `game.held_ref`: `by_handle = {handle(save, e): e for e in d.known_evidence}` →
  `{handle(save, e.id): e.id for e in save.state.evidence.all()}`. The handle map then covers items the player never found.
  This guard matters. `run_ask_turn`'s `unheld_reason` accepts any discoverable item (KNOWN-DEBT A, I-10 "held evidence" half),
  so for a presentation `held_ref` is the only barrier to showing an unfound item. Citations are refused again by the runner
  and by the fold. Every crafted-form test uses a fake handle (`e0123456789ab`), never a real one for an unheld item.
- **M-b**, `web.Games.valid_name`: `... and not _RESERVED.fullmatch(name)` removed. No test name is both NAME-valid and reserved.
  The test list uses `"con.db"`, which fails on its dot. On this Windows 11 machine `con.db` is creatable anyway, so the guard
  protects older Windows only.

`test_the_player_process_never_imports_engine_debug_tooling` checks only `web.py`'s direct imports for `…bots`. Importing
`eidolon.web` loads `eidolon.solve.bots` (via `game.py`) and `eidolon.gen.skeletons`. That is harmless, but the test's intent
is not what it checks.

**Reproduction.** Copy the four paths into a scratch directory. Apply the two string replacements above (each anchor matches
exactly once). In that directory run `python -B -m pytest tests/test_phase8.py -q -p no:cacheprovider` → `106 passed`. Then run
`python -B -c "import sys; sys.path.insert(0, r'D:\Murder Mystery'); import eidolon.web; print([m for m in sys.modules if 'bots' in m or m.startswith('eidolon.gen')])"`
→ `['eidolon.gen', 'eidolon.gen.skeletons', 'eidolon.solve.bots']`.

**Fix.** Add a test that presents and cites a real handle of an unheld item, and one that tries a bare reserved name such as `nul`.
Add both mutants to `tests/persistence_mutation_check.py`. Make the import test check the modules loaded by `import eidolon.web`.

### H8-N7 — the notebook re-evaluates every live theory on every page

`game.notebook` calls `evaluate_hypothesis` for each non-withdrawn theory, and each call scans all held evidence implications and
all held statements' claims. One render therefore costs about O(theories × material), and every GET and POST renders it on the
single event loop. D-8 records only the tension scan. With `--llm`, the latency floor is a blocking `time.sleep` inside the async
handler and the model calls are synchronous, so one turn stalls every tab (D-5 adjacent).

**Reproduction** (`r_n7_n8_notebook.py`, second half; times measured on this machine with other jobs running):

```
statements held: 168
  0 live theories: one notebook render 63 ms
100 live theories: one notebook render 1868 ms
300 live theories: one notebook render 5409 ms
```

A quieter re-run of the same script gave 25 / 985 / 2649 ms. The growth is linear in live theories either way.

**Fix.** Evaluate once per (theory, log head) and cache it, or evaluate only theories touched since the last render. Record this
in D-8.

### H8-N8 — UX and spec gaps

- Item numbers shift as items are found. `_labels` numbers by sorted hash handle, so "item 4" can become "item 5" after the
  next discovery, as the reproduction below shows.
- §16.1: "'Contradicted' means the player's own material contradicts it — the player can still be right if the material is a
  lie, **which the UI says plainly**." The page prints only the status word. §16.1's "the UI groups them by subject" is also not
  done.
- The place-and-time axis is satisfied by the whole evening: any window that overlaps the attack scores, `00:00–02:00`
  included. That is §16.3's literal "overlap", but vacuous. Consider bounding the width.
- A retried form shows "Already recorded as turn n" but not that turn's reply. §26.2 says a duplicate "returns the existing turn's
  projection".

**Reproduction** (`r_n7_n8_notebook.py`, first half):

```python
import time
from p8h import *  # noqa
from eidolon.solve.bots import held_names
from eidolon.solve.queries import expressible_queries, public_names
from eidolon.world.propositions import At


def step(s, control, *a, **k):
    return control(s, f"{control.__name__}@{s.last_seq}", s.last_seq, *a, **k)


s = Save.create(tmpdir() / "n.db", CASES / "study_party_s4.json", seed=7)
prev = {}
for target, method in [("Study", "Look")] * 3 + [("Decanter", "Dust"), ("Room", "Look"), ("Library", "Look"), ("Room", "Look")]:
    step(s, game.search, target, method)
    now = {e["ref"]: e["label"].split(":")[0] for e in game.notebook(s)["evidence"]}
    print(len(now), "items held; renumbered:", sorted(f"{prev[r]} -> {now[r]}" for r in prev if prev[r] != now[r]) or "-")
    prev = now
for who in sorted(s.state.case.living_actors()):                     # (H8-N7) every expressible question to everyone
    for q in expressible_queries(s.state.case, who, held_names(s.state, public_names(s.state.case))):
        step(s, game.ask, who, q)
print("statements held:", len(s.state.discovery.known_statements))
for n in (0, 100, 300):
    while len(s.state.decision.hypotheses) < n:
        k = len(s.state.decision.hypotheses)
        step(s, game.hypothesize, (At(actor="David", location="Study", interval=(k % 100, k % 100 + 10)),), 5000)
    t0 = time.perf_counter()
    game.notebook(s)
    print(f"{n:3} live theories: one notebook render {1000 * (time.perf_counter() - t0):.0f} ms")
```

Observed (renumbering):

```
1 items held; renumbered: -
2 items held; renumbered: -
3 items held; renumbered: ['item 1 -> item 2', 'item 2 -> item 3']
4 items held; renumbered: -
5 items held; renumbered: -
6 items held; renumbered: ['item 4 -> item 5', 'item 5 -> item 6']
7 items held; renumbered: ['item 4 -> item 5', 'item 5 -> item 6', 'item 6 -> item 7']
```

### H8-N9 — inherited, unrecorded: the I-21 confession hook is never wired

`run_ask_turn(confession_check=…)` is "the hook Phase 6's solver wires" (Phase 4 repair report, I-5). No production caller
passes it, including `game.ask`, so in the browser the confession gate is permanently closed. It is latent in the generated
cases: in `manor_wing_s4`, with every item found and every expressible question asked, the murderer's pre-terminal layer weighs 0,
so the `confession` terminal is unreachable whatever the gate does. A hand-authored case with a pre-terminal breaker set would
silently stonewall in play. **Fix.** Wire the solver-backed check in `game.ask`, or record the decision in KNOWN-DEBT §D.

**Reproduction** (`r_n9_confession_hook.py`):

```python
from p8h import *  # noqa
from eidolon.decision.weight import refutation_weight
from eidolon.solve.bots import held_names
from eidolon.solve.queries import expressible_queries, public_names

for f in sorted((ROOT / "eidolon").rglob("*.py")):
    for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
        if "confession_check" in line:
            print(f"{f.relative_to(ROOT)}:{n}: {line.strip()[:110]}")
s = Save.create(tmpdir() / "mw.db", CASES / "manor_wing_s4.json", seed=3)
for _ in range(4):
    for ev in sorted(s.state.evidence.all(), key=lambda e: e.id):
        if ev.id not in s.state.discovery.known_evidence:
            game.search(s, f"s@{s.last_seq}", s.last_seq, ev.discovery.at, ev.discovery.action)
for who in sorted(s.state.case.living_actors()):
    for q in expressible_queries(s.state.case, who, held_names(s.state, public_names(s.state.case))):
        game.ask(s, f"a@{s.last_seq}", s.last_seq, who, q)
st = s.state
sec = next(x for x in st.secrets.all() if x.owner == st.murderer)
held = frozenset(st.discovery.known_evidence | st.discovery.known_statements | st.discovery.known_accounts)
for i, layer in enumerate(sec.cover.layers):
    print(f"{st.murderer} layer {i} terminal={layer.terminal} resolve={layer.resolve} weight(everything held)="
          f"{refutation_weight(held, layer, st.murderer, st.ctx())}")
```

Observed:

```
eidolon\decision\peel.py:10: The `CONFESSION` gate defaults CLOSED (`confession_check=None` -> never allowed). I-21 says a
eidolon\decision\peel.py:77: ctx: DecisionContext, confession_check: ConfessionCheck | None = None) -> PeelResult:
eidolon\decision\peel.py:96: allowed = confession_permitted(confession_check, secret, confrontee, presented, ctx)
eidolon\decision\turn.py:260: confession_check: ConfessionCheck | None = None,
eidolon\decision\turn.py:263: stages 0-2 — ingress/parse/ground — are `llm.ingress`'s job). `confession_check` is the
eidolon\decision\turn.py:293: addressee, ctx, confession_check))
Delphine layer 0 terminal=None resolve=6000 weight(everything held)=8100
Delphine layer 1 terminal=None resolve=8000 weight(everything held)=0
Delphine layer 2 terminal=confession resolve=10000 weight(everything held)=0
```

---

## 3a. Outside Phase 8's scope, found by re-running the suite: H8-X1 — the proof verifier's feasibility oracle over-approximates

This is not graded against Phase 8 and is not one of its acceptance conditions. It is recorded here because it decides whether
the claimed full-suite baseline reproduces.

The full-suite run (§5: 1 failed, 2784 passed) failed one test, `tests/solve/test_oracle.py::test_dp_oracle_and_brute_force_agree`. That test is a
Hypothesis property with random draws and no `derandomize`. It compares the production DP (`world.feasibility._search`),
`solve/oracle.py:oracle_feasible` and exhaustive enumeration (`brute_feasible`). The falsifying example is deterministic:

```python
import sys; sys.dont_write_bytecode = True; sys.path.insert(0, r"D:\Murder Mystery")
from tests.solve.test_oracle import all_three          # (dp, oracle, brute) on the test's tiny house A -1- B -2- C
print(all_three({("C", 1)}, {0: "C", 2: "C"}, [], None))
```

Observed: `(False, True, False)`. To be in C at ticks 0 and 2 while C is barred at tick 1 is impossible: the only neighbour is
two minutes away. The DP and brute force say so. `oracle_feasible` says it is feasible.

The cause is `tail_ok` (`solve/oracle.py`), which accepts the remaining ticks after a visit, with `goal=None`, by checking only
forced ticks. It never checks that the stay-put ticks are unblocked. "Stay put" and "drift in transit" are mixed tick by tick, a
walk no actor can take.

`oracle_feasible` is what the **independent proof verifier** uses: `solve/proof_material.py`, `Oracle.feasible`. An
over-approximating oracle sees more candidates as feasible, so it fails closed. It can refuse a valid proof, and hence a valid
case or save. It also weakens the verifier's check that the proven survivor is feasible at all.

**Side effect of this review.** Hypothesis saved the falsifying example in the repository's example database
(`D:\Murder Mystery\.hypothesis\examples\`, 7 new files from this review's runs). Every later run of that test replays the
example and fails in about 1 s until `tail_ok` is fixed, so `CLAUDE.md`'s "2785 passed" baseline will not reproduce. The entries
were left in place because they reproduce a real defect. Deleting `.hypothesis/examples/` restores the old, luck-dependent
behaviour.

---

## 4. Attacked and held

| Attack | Result |
|---|---|
| `CaseSolved.correct` flipped, a verdict for an innocent, a verdict with no final accusation, a verdict in a conversation | refused at append **and** at a re-chained load (H8-N1 controls; `P8_case_solved_*`) |
| Any row after `CaseSolved` in its turn, any turn after it | refused at both boundaries. `_commit`'s "The case is closed" refuses first; the accusation and theory runners refuse too |
| Moving the verdict's reference (`GameState.murderer`, read from `proof["survivors"]`) by editing the save's embedded bundle (`r_held_bundle.py`, Appendix B): (1) survivors only, bundle seal recomputed; (2) survivors **and** the declared murderer, with package seal, bundle seal, `meta.case_hash`, genesis and head all recomputed | both refused at stage `'bundle'`: "proof does not verify: recorded survivor list disagrees with the independent solve". Changing the answer means forging a different, self-consistent case (§26.1) |
| Final citations: unheld, unknown, account token | refused by the runner (`UNHELD_CITATION`), the fold and, at the web boundary, `held_ref` (but see H8-N6) |
| Path traversal and reserved names in game names, cases outside the library | refused (NAME regex, library allow-list). Case aliasing is H8-I3 |
| Cross-site POST with a foreign `Origin`; `Origin: null` | 403, nothing recorded. Rebinding is H8-I2, framing H8-N5 |
| Double POST, a second tab with another form at the same head | duplicate / stale. Nothing is double-committed at the store (I-14) |
| A tampered (not re-chained) save | 409 refusal page with no engine detail |
| Forged saves the fold accepts (all of H8-N1) | every game and report page renders (200 / 404), no 500 |
| Projection after the verdict, every sealed case: every item found, everyone asked, then a final accusation of "someone from outside" citing everything (`r_report_leaks.py`, Appendix B) | the author's `_leaks()` finds nothing on the closed game page or the report page in any of the four cases. The report says "That was wrong." |
| Debug and engine routes | 404 (the author's 12-path probe, re-run in `tests/test_phase8.py`). No `eidolon.debug` module exists |
| Free text: an unknown name, an over-long line, a burst, I-26 | one in-world answer; refused before the parse call; throttled at 30 (per spelling, H8-I3); the parser has no present/accuse path |
| Page-valid random play through `web.dispatch` (`fuzz.py`, Appendix B: study_party_s4 at seed 1, then all four sealed cases at seed 2): 2,680 random ask (with presentations and provisional accusations), search, goto, theory and withdraw forms built only from what the page offers, then 5 page-built final accusations. An earlier variant of the script (different draw order) dispatched another 2,661 | every form committed. **0 exceptions out of `dispatch`, 0 fold refusals of a page-valid form** (`Save.append` wrapped to log any `SaveRefusal`), live == folded at every 60-action reload and at the end |
| I-42 in the default (no-model) browser mode, which has no latency floor (`timing.py`, Appendix B): one state, same speaker, LIE plan vs honest plan, 150 alternating runs each, three runs | no practically separable signal, though not zero. David's LIE is 0.5–0.7 ms slower than his TRUTH in all three runs (median 6.38/5.85, 5.42/4.88, 7.10/6.43 ms). Elena's LIE and TRUTH are equal; Margaret's and Robert's LIE are no slower than their VAGUE. Spreads overlap. A whole request (commit and render included) measured 25–33 ms median with a p10–p90 spread of roughly 13–80 ms. The gap could only be read statistically over very many turns. I-42's floor exists only with `--llm`; a constant floor in the template path would close even this |
| XSS via statement text, theory text, chip or names | autoescaped Jinja2, `StrictUndefined`; names restricted to `[A-Za-z0-9_-]` |

## 5. The report's key claims, re-measured

All commands ran on the reviewed tree with `PYTHONDONTWRITEBYTECODE=1 … python -B … -p no:cacheprovider` and pytest's
`--basetemp` in the scratch directory.

| Claim (report / `CLAUDE.md`) | Re-run | Result |
|---|---|---|
| `tests/test_phase8.py`: 106 | `python -B -m pytest tests/test_phase8.py -q` | **106 passed in 301.61s**, exit 0 ✔ |
| `tests/test_persistence.py`: 315 | `python -B -m pytest tests/test_persistence.py -q` | **315 passed in 629.26s**, exit 0 ✔ |
| Phase 8 mutants: 45 `P8-*` + F1-a killed, 0 survived, 8 equivalent | `python -B -m tests.persistence_mutation_check -j 6 -k "P8-,F1a-"` | **baseline green; 46 killed, 0 survived, 0 malformed, 0 infrastructure errors, 8 justified equivalent**, exit 0, 21 min ✔. Two guards have no mutant at all (H8-N6) |
| 171 mutants in the harness, 23 `P8_*` forgeries in `FORGERIES` | counted from the modules | 171 (45 `P8-`, 1 `F1a`), 8 equivalents ✔ |
| Long sessions 500/1000/2000 turns save, reload and replay | `EIDOLON_LONG=1 … -k long_session` | **3 passed in 733.44s**, exit 0 (40.64 s / 137.27 s / 554.11 s, run beside the full suite) ✔ |
| Full suite 2785 | `python -B -m pytest -q` | **1 failed, 2784 passed, 1 warning in 3870.01s**, exit 1. The count matches. The one failure is `tests/solve/test_oracle.py::test_dp_oracle_and_brute_force_agree`, a random Hypothesis property outside Phase 8 that drew a real counterexample (§3a, H8-X1). Run alone afterwards it fails in 1.44 s on the saved example. The author's green run did not draw it. Every Phase 8 and persistence test passed in this run. ✘ as a green baseline, ✔ for Phase 8 |
| "every `P8_*` forgery is refused at append and, re-chained, at load" | the persistence run above | ✔ for the listed forgeries. The rules they test are narrower than the report's table (H8-N1) |
| "no … evidence id … reaches a page" | H8-I1 | ✘ |
| "tensions between two HELD items", "the notebook re-evaluates live … (§16.1 'from player-held material only')" | H8-B1 | ✘ (held items, locked implications) |
| "a cross-site POST is refused" | H8-I2, H8-N5 | ✘ under rebinding or framing |
| "a re-sent form returns its committed turn" | H8-I3, H8-N2, H8-N8 | ✘ for a second spelling, typed lines, and the projection |
| Exit: "plays it over HTTP only, from what the pages offer, to a correct verdict" | `test_a_tester_can_play_the_case_to_a_proven_verdict_in_the_browser` | the suspect, room, window and motive are hard-coded in the test: `MURDERER`, `ROOM`, `"00:55"–"01:05"`, `MOTIVE`. Only the weapon and the citations are read from the page. The test proves the controls can express a right verdict, not that the pages lead to one. With H8-B1 open, the pages lead there for the wrong reason. Re-measure after the fix, as a human playtest (D-7) |

## 6. Required for acceptance

1. **H8-B1.** Evaluate only unlocked implications in every player-facing evaluator (theories, tensions, form vocabularies).
   Regression test on all four sealed cases, mutants per filter.
2. **H8-I1.** Hints name only player-visible things. Regression test: blank save, every place and object × every method, on
   every sealed case, with `_leaks()` empty. Mutant.
3. **H8-I2.** Host allow-list (`127.0.0.1` / `localhost`, with the port), and Origin compared against it. Test with a foreign
   Host plus a matching Origin. Mutant.
4. **H8-I3.** `_commit` honours `AppendResult` (`appended`, `same_events`). Saves and rate windows keyed by the resolved,
   case-folded path. Tests for a second spelling and for a store-detected duplicate. Mutants.
5. Re-run `tests/test_phase8.py`, `tests/test_persistence.py`, the `P8-` mutation set (with the new mutants) and the full suite
   on the repaired tree, and record their hashes as Phase 7 did. The full suite stays red on the saved Hypothesis example until
   H8-X1 is fixed. That fix belongs to Phase 6's verifier, not to this list, but it is needed for a green baseline.

The NON-BLOCKING items may move to `docs/EIDOLON-KNOWN-DEBT.md` §D. H8-N1, H8-N2 and H8-N6 are cheap and belong in the same
change.

---

## Appendix A — `p8h.py` (the preamble every reproduction imports)

```python
"""Preamble shared by the Phase 8 hostile-review reproductions. Imports the real tree READ-ONLY (no bytecode is written);
every save lives in a fresh temp directory outside the repository."""
import json, re, shutil, sqlite3, sys, tempfile, warnings
sys.dont_write_bytecode = True
warnings.filterwarnings("ignore")
from pathlib import Path

ROOT = Path(r"D:\Murder Mystery")
sys.path.insert(0, str(ROOT))
CASES = ROOT / "cases" / "generated"

from starlette.testclient import TestClient          # noqa: E402
from eidolon import game, store, web                 # noqa: E402
from eidolon.store import Save, SaveRefusal          # noqa: E402


def tmpdir() -> Path:
    return Path(tempfile.mkdtemp(prefix="p8rev-"))


def client(saves=None, base_url="http://testserver", raise_server_exceptions=True, **app_kw) -> TestClient:
    return TestClient(web.create_app(saves or tmpdir(), CASES, **app_kw), base_url=base_url,
                      raise_server_exceptions=raise_server_exceptions)


def hidden(page, op):
    """The action_id / expected_seq the page rendered into the form whose op is `op`."""
    block = re.search(rf'<form[^>]*>(?:(?!</form>).)*?value="{op}"(?:(?!</form>).)*</form>', page, re.S).group(0)
    return {k: re.search(rf'name="{k}" value="([^"]*)"', block).group(1) for k in ("action_id", "expected_seq")}


def new_game(c, name="g1", case="study_party_s4", seed="7"):
    c.post("/new", data={"name": name, "case": case, "seed": seed})
    return c.get(f"/g/{name}").text


def post(c, name, op, page, **fields):
    return c.post(f"/g/{name}", data={"op": op, **hidden(page, op), **fields}).text


def last_action(page):
    m = re.search(r"<h2>Last action</h2>(.*?)</section>", page, re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", m.group(1))).strip()


def turn_line(page):
    return re.search(r"Turn \d+ · [^<]*", page).group(0).strip()


def inject(path, events, action_id):
    """A forger who RE-CHAINS: append `events` as one more turn with a valid chain and head, bypassing Save.append."""
    c = sqlite3.connect(path, isolation_level=None)
    meta = dict(c.execute("SELECT key, value FROM meta"))
    seq, prev, turn = int(meta["head_seq"]), meta["head_hash"], events[0].turn
    for ev in events:
        seq += 1
        payload = store._plain(ev)
        h = store._row_hash(prev, seq, turn, ev.kind, action_id, payload)
        c.execute("INSERT INTO session_events VALUES (?,?,?,?,?,?,?)", (seq, turn, ev.kind, action_id, store._canon(payload), prev, h))
        prev = h
    c.execute("UPDATE meta SET value=? WHERE key='head_seq'", (str(seq),))
    c.execute("UPDATE meta SET value=? WHERE key='head_hash'", (prev,))
    c.close()


def offer(base, events, action_id="forged"):
    """-> (append verdict, re-chained load verdict) for one forged turn, each on its own copy of `base`."""
    out = []
    for how in ("append", "load"):
        p = tmpdir() / "f.db"
        shutil.copy(base, p)
        try:
            if how == "append":
                s = Save.open(p, writable=True)
                s.append(events, s.last_seq, action_id)
                s.close()
            else:
                inject(p, events, action_id)
                Save.open(p)
            out.append("ACCEPTED")
        except SaveRefusal as e:
            out.append(f"refused ({str(e)[:90]})")
    return tuple(out)
```

Set `PYTHONIOENCODING=utf-8` on a Windows console so the em dashes print.

## Appendix B — the "held" evidence: the bundle forgery, page-valid fuzzing and the I-42 probe

`r_held_bundle.py`:

```python
from p8h import *  # noqa
from eidolon.solve.package import CasePackage, SealedCase, bundle_seal

base = tmpdir() / "b.db"
Save.create(base, CASES / "study_party_s4.json", seed=7).close()


def forge(both):
    p = tmpdir() / "f.db"
    shutil.copy(base, p)
    c = sqlite3.connect(p, isolation_level=None)
    doc = json.loads(c.execute("SELECT doc FROM case_bundle").fetchone()[0])
    doc["proof"]["survivors"] = ["Elena"]
    if both:
        pkg = CasePackage.model_validate(doc["package"])
        pkg = pkg.model_copy(update={"solution": pkg.solution.model_copy(update={"murderer": "Elena"})}).sealed()
        doc["package"] = json.loads(pkg.model_dump_json())
        doc["proof"]["package_seal"] = pkg.seal
        meta = dict(c.execute("SELECT key, value FROM meta"))
        g = store._genesis(pkg.seal, int(meta["seed"]), int(meta["schema_version"]), meta["initial_digest"])
        for k, v in (("case_hash", pkg.seal), ("genesis", g), ("head_hash", g)):
            c.execute("UPDATE meta SET value=? WHERE key=?", (v, k))
    doc["bundle_seal"] = bundle_seal(doc["package"]["seal"], doc["proof"], doc["report"])
    c.execute("UPDATE case_bundle SET doc=?", (json.dumps(doc),))
    c.close()
    try:
        return f"LOADED, murderer={Save.open(p).state.murderer}"
    except SaveRefusal as e:
        return f"refused at stage {e.stage!r}: {str(e)[:120]}"


print("(1) proof survivors edited, bundle seal recomputed:", forge(False))
print("(2) survivors + declared murderer, every seal/meta/genesis recomputed:", forge(True))
```

Observed:

```
(1) proof survivors edited, bundle seal recomputed: refused at stage 'bundle': embedded case refused: proof does not verify: recorded survivor list disagrees with the independent solve
(2) survivors + declared murderer, every seal/meta/genesis recomputed: refused at stage 'bundle': embedded case refused: proof does not verify: recorded survivor list disagrees with the independent solve
```

`r_report_leaks.py`:

```python
from p8h import *  # noqa
sys.path.insert(0, str(ROOT))
from tests.test_phase8 import _leaks
for case in ("study_party_s4", "study_party_s5", "manor_wing_s4", "manor_wing_s6"):
    with client() as c:
        page = new_game(c, "g1", case=case)
        s = c.app.state.games.open("g1")
        for _ in range(4):
            for ev in sorted(s.state.evidence.all(), key=lambda e: e.id):
                if ev.id not in s.state.discovery.known_evidence:
                    page = post(c, "g1", "search", page, target=ev.discovery.at, method=ev.discovery.action)
        for who in sorted(s.state.characters):
            page = post(c, "g1", "ask", page, addressee=who, topic="presence")
        cites = re.findall(r'name="cited" value="([^"]+)"', page)
        page = c.post("/g/g1", data={"op": "accuse", **hidden(page, "accuse"), "suspect": "Outsider", "confirm": "on", "cited": cites}).text
        rep = c.get("/g/g1/report").text
        print(case, "| game page leaks:", _leaks(page, s), "| report leaks:", _leaks(rep, s), "| verdict line:",
              re.search(r"You accused [^<]*", rep).group(0))
```

Observed:

```
study_party_s4 | game page leaks: [] | report leaks: [] | verdict line: You accused someone from outside. That was wrong.
study_party_s5 | game page leaks: [] | report leaks: [] | verdict line: You accused someone from outside. That was wrong.
manor_wing_s4 | game page leaks: [] | report leaks: [] | verdict line: You accused someone from outside. That was wrong.
manor_wing_s6 | game page leaks: [] | report leaks: [] | verdict line: You accused someone from outside. That was wrong.
```

`fuzz.py` (`python -B fuzz.py study_party_s4 300 1`, then `<case> 600 2` for each of the four sealed cases):

```python
import random
from p8h import *  # noqa
from starlette.datastructures import FormData

case_name, N, SEED = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
rng = random.Random(SEED)
p = tmpdir() / "fuzz.db"
save = Save.create(p, CASES / f"{case_name}.json", seed=SEED)
REFUSALS, CRASHES, counts = [], [], {}
_append = Save.append


def logged(self, events, expected_seq, action_id, **kw):
    try:
        return _append(self, events, expected_seq, action_id, **kw)
    except SaveRefusal as e:
        REFUSALS.append((action_id, str(e)[:200]))
        raise


Save.append = logged
hhmm = lambda t: f"{t // 60:02d}:{t % 60:02d}"          # noqa: E731
for i in range(N):
    nb, T, seq = game.notebook(save), save.state.case.t_investigation, save.last_seq
    op = rng.choice(["ask"] * 5 + ["search"] * 3 + ["goto", "hypothesize", "hypothesize", "withdraw"])
    f = {"op": op, "action_id": f"{op}@{seq}", "expected_seq": str(seq)}
    held = [e["ref"] for e in nb["evidence"]] + [s["ref"] for s in nb["statements"]]
    if op == "ask":
        f.update(addressee=rng.choice(nb["people"])["id"], topic=rng.choice([""] + list(nb["topics"])),
                 about=rng.choice([""] + [a["id"] for a in nb["everyone"]]), place=rng.choice([""] + [l["id"] for l in nb["places"]]),
                 bucket=rng.choice([""] + [str(t["bucket"]) for t in nb["times"]]), present=rng.choice([""] * 3 + held) if held else "")
        if rng.random() < 0.2:
            f["accuse"] = "on"
    elif op == "search":
        f.update(target=rng.choice([l["id"] for l in nb["places"]] + [o["id"] for o in nb["objects"]]), method=rng.choice(nb["methods"]))
    elif op == "goto":
        f["location"] = rng.choice([l["id"] for l in nb["places"]])
    elif op == "hypothesize":
        kind = rng.choice(["At", "At", "Lied", "Planted"])
        a = rng.randint(0, T - 1)
        f.update(kind=kind, confidence=str(rng.randint(0, 100)), actor=rng.choice([a_["id"] for a_ in nb["everyone"]]),
                 location=rng.choice([l["id"] for l in nb["places"]]), start=hhmm(a), end=hhmm(rng.randint(a + 1, T)))
        if kind == "Lied":
            if not nb["statements"]:
                continue
            f["statement"] = rng.choice(nb["statements"])["ref"]
        if kind == "Planted":
            if not nb["evidence"]:
                continue
            f["item"] = rng.choice(nb["evidence"])["ref"]
    elif op == "withdraw":
        if not nb["hypotheses"]:
            continue
        hid = rng.choice(nb["hypotheses"])["id"]
        f.update(action_id=f"withdraw-{hid}@{seq}", hypothesis=hid)
    try:
        out = web.dispatch(save, FormData(list(f.items())))
        counts[(op, out.status)] = counts.get((op, out.status), 0) + 1
    except Exception as e:  # noqa: BLE001
        CRASHES.append((f, f"{type(e).__name__}: {e}"[:200]))
    if i % 60 == 59:
        assert Save.open(p).state_hash() == save.state_hash(), f"live != folded at action {i}"
nb, seq = game.notebook(save), save.last_seq
form = [("op", "accuse"), ("action_id", f"accuse@{seq}"), ("expected_seq", str(seq)), ("suspect", save.state.murderer), ("confirm", "on"),
        ("start", "00:00"), ("end", hhmm(save.state.case.t_investigation))] + [("cited", r["ref"]) for r in nb["evidence"] + nb["statements"]]
print("final accusation:", web.dispatch(save, FormData(form)).status)
assert Save.open(p).state_hash() == save.state_hash()
print(f"{case_name} seed {SEED}: outcomes {sorted(counts.items())}")
print("fold refusals of page-valid forms:", REFUSALS[:5] or 0, "| exceptions:", CRASHES[:5] or 0)
```

Observed: every run printed `final accusation: ok` and `fold refusals of page-valid forms: 0 | exceptions: 0`. The outcomes
were all `ok`:

```
study_party_s4 seed 1: outcomes [(('ask', 'ok'), 125), (('goto', 'ok'), 31), (('hypothesize', 'ok'), 48), (('search', 'ok'), 71), (('withdraw', 'ok'), 25)]
study_party_s4 seed 2: outcomes [(('ask', 'ok'), 258), (('goto', 'ok'), 59), (('hypothesize', 'ok'), 89), (('search', 'ok'), 145), (('withdraw', 'ok'), 42)]
study_party_s5 seed 2: outcomes [(('ask', 'ok'), 266), (('goto', 'ok'), 58), (('hypothesize', 'ok'), 82), (('search', 'ok'), 145), (('withdraw', 'ok'), 42)]
manor_wing_s4 seed 2: outcomes [(('ask', 'ok'), 261), (('goto', 'ok'), 50), (('hypothesize', 'ok'), 98), (('search', 'ok'), 137), (('withdraw', 'ok'), 51)]
manor_wing_s6 seed 2: outcomes [(('ask', 'ok'), 263), (('goto', 'ok'), 50), (('hypothesize', 'ok'), 96), (('search', 'ok'), 137), (('withdraw', 'ok'), 51)]
```

`timing.py`:

```python
import statistics as stats, time
from p8h import *  # noqa
from eidolon.decision.turn import run_ask_turn
from eidolon.solve.bots import held_names
from eidolon.solve.queries import expressible_queries, public_names

s = Save.create(tmpdir() / "t.db", CASES / "study_party_s4.json", seed=7)
for _ in range(4):
    for ev in sorted(s.state.evidence.all(), key=lambda e: e.id):
        if ev.id not in s.state.discovery.known_evidence:
            game.search(s, f"s@{s.last_seq}", s.last_seq, ev.discovery.at, ev.discovery.action)
st = s.state
by = {}
for who in sorted(st.case.living_actors()):
    for q in expressible_queries(st.case, who, held_names(st, public_names(st.case))):
        r = run_ask_turn(st, who, q)
        if not r.rejected:
            by.setdefault(who, {}).setdefault(r.plan_act, q)
for who, acts in by.items():
    honest = next((a for a in ("TRUTH", "VAGUE", "DONT_RECALL", "DONT_KNOW") if a in acts), None)
    if "LIE" not in acts or honest is None:
        continue
    times = {"LIE": [], honest: []}
    for _ in range(150):
        for act in times:
            t0 = time.perf_counter()
            run_ask_turn(st, who, acts[act])
            times[act].append((time.perf_counter() - t0) * 1000)
    print(who, {a: f"median {stats.median(x):.2f} ms, p10 {sorted(x)[15]:.2f}, p90 {sorted(x)[135]:.2f}" for a, x in times.items()})
```

Observed (second run):

```
David {'LIE': 'median 5.42 ms, p10 4.75, p90 7.45', 'TRUTH': 'median 4.88 ms, p10 4.23, p90 6.36'}
Elena {'LIE': 'median 5.96 ms, p10 4.77, p90 8.27', 'TRUTH': 'median 5.80 ms, p10 4.82, p90 8.35'}
Margaret {'LIE': 'median 4.66 ms, p10 4.10, p90 7.36', 'VAGUE': 'median 5.42 ms, p10 4.81, p90 8.18'}
Robert {'LIE': 'median 5.55 ms, p10 4.64, p90 8.19', 'VAGUE': 'median 5.74 ms, p10 4.80, p90 8.42'}
```


---

# Follow-up, 2026-10-20 (evening): the H8-X1 oracle fix, and Phase 8 resumed from §3a

Reviewer: a fresh Claude Code session continuing this review. The same caveat applies: not a human, not a separate
team. Everything above this line is the original review, unchanged. This part records what was re-checked after a
repair of H8-X1 was reported. **Verified** means a command was run on the tree described below and its output is quoted.
**Unmeasured** means it was not run, and nothing here claims it passed.

## 7.0 Verdict of the follow-up

**NOT ACCEPTED — REQUIRED FIXES.** Unchanged from the original verdict, for the same four reasons.

- **H8-X1 is repaired and verified.** The repaired `tail_ok` agrees with the production DP and with brute force on every
  instance tried in a house where every room has an exit: 2,228,224 exhaustive instances and 15,000 random ones, 0
  disagreements. The pre-fix body is wrong on 11,160 of those exhaustive instances. The fix changes no proof, seal, uniqueness result
  or acceptance decision (§7.5).
- **H8-B1, H8-I1, H8-I2 and H8-I3 are still open.** None of the Phase 8 files changed: `game.py`, `web.py`, `store.py`,
  `decision/turn.py`, `decision/hypotheses.py`, `decision/exploration.py` and `solve/session.py` hash exactly as in the
  original review. The H8-B1 and H8-I1 reproductions, extracted verbatim from this document, still print their documented
  output on today's tree (§7.6).
- **Two new NON-BLOCKING findings.** H8-X2: the oracle and the brute-force "ground truth" both let an actor leave a room that
  has no exit. This is latent, since no generated case has such a room. H8-N10: the new guard has no mutant in the Phase 6
  harness, and an under-approximating variant of the fix survives every deterministic test.

## 7.1 Object, and what changed

No VCS exists. To recover the pre-fix files, the stale bytecode `eidolon/solve/__pycache__/oracle.cpython-312.pyc` (source
mtime 2026-09-20, size 5658) was disassembled. Its `tail_ok` was rebuilt as source and spliced into today's file, and the new
test was removed from `tests/solve/test_oracle.py`. The rebuilt tree reproduces the original review's manifest **exactly**:
`131887d83261ee7ceb4e4a3472552b29e1477ddd6e4a234a9a9e212d672699bb`. The recipe is sha256 over sorted `path sha256` lines of the
184 `.py` files under `eidolon/` and `tests/`, with a trailing newline. The rebuilt pre-fix `oracle.py` is 5658 bytes, the size
the `.pyc` records, and the rebuilt test file is 3295 bytes, the size its own stale `.pyc` records. The fix therefore touches
exactly these two files, and no other `.py` file under `eidolon/` or `tests/` changed. `find -newer` on this document agrees:
it lists only those two files (no file under `cases/` is newer).

Today's tree: manifest `fb6efde63b921e7e70490315053139793178c4089efe783f0311ea0bc3831262` (same recipe, 184 files).
`oracle.py dd7a578955b316e3` (pre-fix `b5885f187e03d4c2`), `tests/solve/test_oracle.py 3b573cbddf1c4628` (pre-fix
`ada9f28bf8a32a2a`). The bundles (`cases/generated/*.json`, all dated 2026-10-15) are `manor_wing_s4 f762df353e8db19e`,
`manor_wing_s6 b749d3a0cc731c59`, `study_party_s4 fbfa9c1c21bd725c` and `study_party_s5 1a51e427b8fa0cb7`.

```diff
--- oracle.py (reviewed tree, 131887d8…)
+++ oracle.py (now)
@@ -45,4 +45,8 @@
         the layered DP accepts an unlocated final state when there is no `goal`."""
-        return all(forced.get(x) is None or (forced[x] == loc and (loc, x) not in blocked)
-                   for x in range(t + 1, T))
+        for k in range(t, T):                # stay put through tick k, drift in transit after it
+            if k > t and not ok(loc, k):
+                return False
+            if all(forced.get(x) is None for x in range(k + 1, T)):
+                return True
+        return False
--- test_oracle.py (reviewed tree)
+++ test_oracle.py (now)
@@ -44,2 +44,7 @@
+def test_tail_cannot_stay_put_on_a_blocked_tick():
+    # C at 0 and 2 with (C,1) blocked: staying is blocked, the only round trip takes 4 minutes (Hypothesis counterexample)
+    assert all_three({("C", 1)}, {0: "C", 2: "C"}, []) == (False, False, False)
```

**Method.** Same rules as the original review. Every script ran from the session scratch directory, outside the repository,
importing the tree read-only (`python -B`, `sys.dont_write_bytecode`). Hypothesis keeps its example database under the
**current working directory**, so every pytest run used a byte-identical scratch copy of the tree as its cwd: the copy's
Git Bash `sha256sum` manifest over every file of `eidolon/ tests/ cases/ pyproject.toml` was `1ddd2d9f…`, identical to the
repository's. No file in the repository was written except this document, and `.hypothesis/` was not touched this time. Two
repository files are newer than the fix: `.pytest_cache/v/cache/nodeids` (20:26) and `.hypothesis/tmp/tmpnj_uu8kt` (20:15).
The repairer's runs wrote them, before this follow-up's first scratch file (21:09).

## 7.2 Does `tail_ok` now model the intended semantics? (verified)

The question `oracle_feasible` must answer is the DP's (`world.feasibility._search`). Is there a per-tick walk from a start
that satisfies every forced, blocked and existential cell? Transit may last longer than the edge (lingering is allowed),
transit may not occupy a forced tick, and with `goal=None` the final state may be in transit. The DFS reaches states
`(loc, t, mask)` that are each already `ok`. `tail_ok(loc, t)` must say whether the remaining ticks can be finished from there.

- **Sound.** An accepted tail is "stay at `loc` on ticks t…k, each tick unblocked and not forced elsewhere (`ok`), then be in
  transit on k+1…T−1, none of which is forced". The DP accepts that walk whenever `loc` has at least one travel edge, since
  transit is entered along an edge. The old body accepted forced ticks at `loc` interleaved with unforced ticks spent
  "anywhere". That is a walk that leaves and returns in zero time, which is H8-X1.
- **Complete.** Take any feasible walk W and its last located tick t*. The DFS reproduces W's located ticks one by one, using
  stay-put steps and arrival jumps whose transit avoids forced ticks. It reaches `(W[t*], t*, full)`, where `k = t*` succeeds
  because every tick after t* is in transit and therefore unforced. Every other `k` only adds more sound tails. The stay-put
  loop is redundant for completeness, but harmless.
- **Exception.** A room with **no** travel edge. There the DP cannot enter transit at all, while `tail_ok` (and `check_walk`)
  still allow drifting. That is H8-X2 below. It does not arise in any house where every room has an exit, and no generated case
  has a room without one.

The counterexample, reproduced (`r_x1_counterexample.py`, with `pre.py` and `recon.py` from Appendix C):

```python
from pre import *  # noqa
from pre import _search
from tests.solve.test_oracle import TINY, T, STARTS
args = ({("C", 1)}, {0: "C", 2: "C"}, [])
print("instance: house A -1- B -2- C, T=7, blocked (C,1), forced C@0 and C@2, no existentials, goal None")
print("DP    :", _search(TINY, T, STARTS, *args, None)[0])
print("brute :", brute_feasible(TINY, T, *args, STARTS, None))
print("oracle (current) :", oracle_feasible(TINY, T, *args, STARTS, None))
print("oracle (pre-fix) :", prefix.oracle_feasible(TINY, T, *args, STARTS, None))
```

Observed:

```
instance: house A -1- B -2- C, T=7, blocked (C,1), forced C@0 and C@2, no existentials, goal None
DP    : False
brute : False
oracle (current) : False
oracle (pre-fix) : True
```

Differential, DP vs current oracle vs pre-fix oracle vs brute force (`diff.py`, Appendix C, 10 worker processes). The
exhaustive parts enumerate **every** blocked set × **every** forced map (× every goal where stated):

```
exhaustive tiny T=3, every blocked set x forced map x goal: 131072 instances | current DP/oracle/brute disagreements: 0 | pre-fix oracle != brute: 184
exhaustive iso  T=3, every blocked set x forced map x goal: 131072 instances | current DP/oracle/brute disagreements: 368 | pre-fix oracle != brute: 224
    house iso (dp, oracle, brute) = (False, True, True): 368x, e.g. ('iso', 3, (('C', 1),), ((0, 'C'),), (), None)
exhaustive tiny T=4, every blocked set x forced map, goal None: 1048576 instances | current DP/oracle/brute disagreements: 0 | pre-fix oracle != brute: 5200
exhaustive long T=4, every blocked set x forced map, goal None: 1048576 instances | current DP/oracle/brute disagreements: 0 | pre-fix oracle != brute: 5776
random x20000 (4 houses, existentials, goals): 20000 instances | current DP/oracle/brute disagreements: 41 | pre-fix oracle != brute: 32
    house iso (dp, oracle, brute) = (False, True, True): 41x, e.g. ('iso', 6, (('A', 0), ('B', 0), ('C', 2), ('C', 5)), (), (), None)
exit 0
```

`tiny` is the test's house A-1-B-2-C. `long` has a 3-minute edge (A-1-B-3-C). `ring` is A-1-B-1-C-2-D-3-A. `iso` is A-1-B
plus a room C with no edge. Every disagreement left involves `iso`, and in every one of them the oracle **agrees with brute
force** against the DP (H8-X2). On the connected houses there were 2,228,224 exhaustive instances (`tiny` T=3 and T=4, `long`
T=4) and 15,000 random ones (`tiny`, `long`, `ring`), with 0 disagreements. The pre-fix body is wrong on 11,160 of those
exhaustive instances, and on 32 of the 20,000 random ones (that count covers all four houses).

## 7.3 The dedicated mutant for the new guard (verified)

`tests/solve/mutation_check.py` contains **no** mutant of the new guard. Its only `oracle.py` entry is **P2**, "the oracle
lets an edge be crossed one tick early". P2 rewrites `t2 = t + d` in the arrival-jump loop and never touches `tail_ok`, so P2
being killed says nothing about this guard. Mutants of the repaired body, each applied to a fresh scratch copy of
`eidolon/` + `tests/` with no Hypothesis database (`mut.py`, Appendix C). The `mut.py` label is in brackets:

| Mutant | Regression test alone | All of `test_oracle.py` |
|---|---|---|
| — [T0] baseline | 1 passed | 6 passed |
| **TK1** [T1] the blocked-tick guard removed: stay-put checks the forced map only, `not ok(loc, k)` → `forced.get(k) not in (None, loc)` | **1 failed**, `assert (False, True, False) == (False, False, False)` | 2 failed (the regression test and the random property) |
| TK2 [T2] the whole stay-put guard deleted | **1 failed**, same assertion | 4 failed |
| TK3 [T4] no immediate drift: `range(t, T)` → `range(t + 1, T)` | 1 passed | **1 failed: only the random property** |
| TK4 [T3] the guard checks blocked cells only (a tick forced elsewhere is ignored) | 1 passed | 3 failed (`test_travel_semantics_fixed_points`, `test_three_minute_edge…`, property) |
| TK5 [T5] full revert to the pre-fix body | **1 failed**, `(False, True, False)` | 1 failed (the regression test; the property passed this run) |
| TK6 [T6] `k > t` → `k >= t` | 1 passed | 6 passed: **equivalent**, because every stacked state is already `ok` |

The regression test kills the guard mutant, TK1, for the right reason. The oracle answers `True` where the DP and brute force
answer `False`, and the failing assertion is the regression test's own. It also kills TK2 and TK5.

How much the random property contributes, measured over 30 Hypothesis seeds each, with a fresh database per run
(`killrate.py`, Appendix C):

```
T1 blocked-tick guard removed: stay-put checks the forced map only: killed by the property in 14/30 seeds (other exit codes: [])
T4 no immediate drift: loop starts at t + 1: killed by the property in 8/30 seeds (other exit codes: [])
T5 full revert to the pre-fix body: killed by the property in 1/30 seeds (other exit codes: [])
```

This is why H8-X1 slipped past the author's green run. The property finds the original defect once in 30 seeds. TK3 (an
oracle that under-approximates, which in the verifier means refusing valid proofs) survives every deterministic test and
dies only to luck. See H8-N10.

**The Phase 6 harness itself**, on a scratch copy with TK1–TK3 added to `M` and `MUT_ONLY="^(P2|TK)"`: baseline green, then:

```
baseline green: 348 passed in 2399.73s (0:39:59)
KILLED     P2 the oracle lets an edge be crossed one tick early
           1 failed, 74 passed in 276.11s (0:04:36)
             - tests/solve/test_negative_fixtures.py::test_transitive_alibi_cycle_and_pairwise_clean_triple_are_infeasible_in_solver_and_oracle
KILLED     TK1 tail_ok stays put on a blocked tick (guard checks the forced map only)
           1 failed, 89 passed in 303.94s (0:05:03)
             - tests/solve/test_oracle.py::test_tail_cannot_stay_put_on_a_blocked_tick
KILLED     TK2 tail_ok stay-put guard deleted
           1 failed, 74 passed in 276.05s (0:04:36)
             - tests/solve/test_negative_fixtures.py::test_transitive_alibi_cycle_and_pairwise_clean_triple_are_infeasible_in_solver_and_oracle
SURVIVED   <-- UNEXPECTED TK3 tail_ok never drifts at once (loop starts at t + 1)
           348 passed in 1847.07s (0:30:47)

COUNTS: {'KILLED': 3, 'SURVIVED': 1, 'EQUIVALENT': 0, 'ERROR': 0}
MUTATION VERIFICATION: FAIL
```

(The first attempt hit the harness's default 1500 s `MUT_TIMEOUT` on the baseline, because the machine was also running the
other suites. It reported `BASELINE IS NOT GREEN … TIMEOUT after 1500s` and ran no mutant. The run above used
`MUT_TIMEOUT=10800`.) Under the harness's own protocol, the regression test is what kills TK1. `test_negative_fixtures` did
not kill it, and the property did not either before `-x` stopped. TK3 survives `tests/solve` + `tests/gen` in full. P2 is
killed by a different test, which confirms that it guards the arrival jump and not `tail_ok`.

**The repository's Hypothesis database no longer holds the falsifying example.** §3a said every later run would replay it.
That is now stale. In a scratch copy with the pre-fix `oracle.py` and a byte copy of the repository's `.hypothesis/`, the
property **passed** under three seeds (`1 passed in 4.70s / 4.53s / 3.11s`). The seven example files present are
all dated 2026-09-19, so none of them is the original review's. The test function, and hence its database key, is unchanged.
Most likely Hypothesis dropped the entry when the fixed code passed it. Only the new deterministic test pins H8-X1
now.

## 7.4 Suites and bundles on today's tree (verified unless marked)

All runs: `PYTHONDONTWRITEBYTECODE=1 python -B -m pytest … -q -p no:cacheprovider --basetemp=<scratch>`, cwd = the verified
scratch copy, run concurrently with each other and with the scripts above, so the times are inflated.

| Run | Result |
|---|---|
| `tests/solve tests/gen` | **348 passed in 2891.99s**, exit 0 (collected: 268 in `tests/solve`, matching the repairer's figure; 80 in `tests/gen`). `CLAUDE.md`'s "194" for this pair is stale |
| `tests/test_phase8.py` | **106 passed, 1 warning in 722.69s**, exit 0 |
| `tests/test_persistence.py` | **315 passed in 1427.80s**, exit 0 |
| `tests/solve/test_oracle.py` | 6 passed (T0 row above) |
| Full suite `python -B -m pytest -q` | **2786 passed, 1 warning in 3924.10s**, exit 0: `CLAUDE.md`'s 2785 plus the one new test. The cwd copy carried the repository's `.hypothesis/`, which no longer holds the H8-X1 example (§7.3). This is one green run: the property tests are random, and one run does not show they can never fail |
| Phase 6 harness, full 102 mutants; `tests.persistence_mutation_check` (171); `tests.decision.mutation_check` (both sets) | **unmeasured**: not run in this follow-up |
| `EIDOLON_LONG=1` 1000/2000-turn sessions; `spike/` | **unmeasured** |
| `eidolon validate` (full re-validation including V-7 at full scale) on the four bundles | **unmeasured**. V-7 never consults the oracle (§7.5), but it was not re-run |

**All four bundles verify with today's code.** `load_sealed_case` checks every seal, runs `verify_proof`, checks the declared
solution against the proven survivor and checks the full-scale report. Each verifier oracle query was answered three ways
(current oracle, pre-fix oracle, production DP), and `verify_proof` was also run with the pre-fix oracle alone (`trace.py a`,
Appendix C):

```
manor_wing_s4.json: load_sealed_case OK (package seal 9ea995b0662e6ae6, unique=True, survivors=['Delphine']) | oracle queries 43, current!=pre-fix 0, current!=DP 0 | verify_proof with the PRE-FIX oracle: [] (verifies)
manor_wing_s6.json: load_sealed_case OK (package seal 604f720bb383ad51, unique=True, survivors=['Cormac']) | oracle queries 45, current!=pre-fix 0, current!=DP 0 | verify_proof with the PRE-FIX oracle: [] (verifies)
study_party_s4.json: load_sealed_case OK (package seal 00b709d689b3cea0, unique=True, survivors=['David']) | oracle queries 32, current!=pre-fix 0, current!=DP 0 | verify_proof with the PRE-FIX oracle: [] (verifies)
study_party_s5.json: load_sealed_case OK (package seal 88070a4e2a358b28, unique=True, survivors=['Robert']) | oracle queries 33, current!=pre-fix 0, current!=DP 0 | verify_proof with the PRE-FIX oracle: [] (verifies)
```

(The package seals of `manor_wing_s4` and `study_party_s5` differ from the ones `docs/EIDOLON-PHASE-6-RB-REPORT.md` §9 lists.
The bundle files are dated 2026-10-15, after that report, and the rebuild below reproduces them, so the RB report's list is
stale. The fix has nothing to do with it.)

## 7.5 Did the fix change any proof, seal, uniqueness result or acceptance decision? (verified: no)

**Where the oracle can act.** `oracle_feasible` is called only from `solve/proof_material.Oracle`, which only
`solve/proof.verify_proof` uses. `build_proof` writes the proof from the solver (`lattice` + the DP) and never calls the
oracle. So the fix cannot change a proof's content or any seal. It can change only `verify_proof`'s verdict, which gates
(a) generation at V-5 (`pipeline.py:228`) and (b) every `load_sealed_case` / `load_sealed_text`, hence every `Save.create` and
`Save.open`. V-4, V-6, V-7, the bots and `game.establishes` run on the solver or the engine and never on the oracle.

**The seed study, re-traced.** The 2×50 seed study (seeds 1–50, both skeletons, one attempt each) was run through
V-0…V-3 and V-5 with the three-way oracle tracer, stopping before V-4. Every oracle query the verifier made was answered by the
current oracle, the pre-fix oracle and the DP (`trace.py b 8`):

```
manor_wing: 50 seeds | passed V-5 49 | outcomes ['V-5:robust', 'passed V-5'] | oracle queries 2211 | current!=pre-fix 0 | current!=DP 0
study_party: 50 seeds | passed V-5 50 | outcomes ['passed V-5'] | oracle queries 1826 | current!=pre-fix 0 | current!=DP 0
```

There were 4,037 verifier queries and 0 disagreements. `verify_proof` is deterministic and only the oracle changed, so the
pre-fix verifier walks the identical path to the identical verdict on all 100 seeds. The one V-5 rejection is the RB report's
deliberate one, `manor_wing 45`: `proof does not verify: uniqueness fails when ['MBeatrix0024'] stay uncorrected (survivors
[])`, bucketed `V-5:robust`. The 99 others are unique with one survivor. The later stages never consult the oracle and receive
the same state, so the study's acceptance decisions (99/100) cannot have moved. V-7 itself was not re-run.

**The goldens, rebuilt.** For the four golden seeds the rebuilt package seal and the V-5 proof (sorted-key JSON) are
**byte-equal** to the stored bundles: `package_seal_equal: true, proof_equal: true` for `study_party 4`, `study_party 5`,
`manor_wing 4` and `manor_wing 6`.

**Saves across the fix** (`r_x1_downstream.py`, Appendix C). A save created under the pre-fix verifier opens under the current
one with the same murderer and the same state hash, and the reverse also holds. One bundle verification costs the same either
way (medians of 5, interleaved; manor_wing_s4 is pre-fix 7.11 s, current 7.09 s; the others are 6.98/6.85 s, 3.66/3.58 s
and 4.38/4.44 s). The new loop does not make `Save.open` slower, so it does not worsen H8-I3's per-spelling cost.

## 7.6 Phase 8 resumed from §3a: downstream effects

| Attack | Result |
|---|---|
| Does the fix move Phase 8's verdict reference? `GameState.murderer` is the proof's verified survivor | no: proofs byte-equal, all four verify, survivors unchanged (§7.4, §7.5) |
| Does it move the report's evidence axis? `game.establishes` → `solve.solver.evaluate` (lattice + DP) | no: that path never calls the oracle (code read: `game.py:285–291`; `oracle_feasible` callers are `proof_material.py:388, 395` only) |
| Old saves after the fix, new saves on an old engine | load both ways, identical state hash (§7.5) |
| `Save.open` cost, the H8-I3 amplifier | unchanged (§7.5) |
| The over-approximation concern of §3a ("weakens the verifier's check that the proven survivor is feasible at all") | closed on connected houses: the survivor-times recomputation now agrees with the DP on every query in 100 cases. Still open for a room with no exit (H8-X2) |
| Are the Phase 8 blockers still there? `r_b1_all_cases.py` and `r_i1_hint_ids.py`, extracted from this document by regex and run unmodified with Appendix A's `p8h.py` | **yes**: both print their §1 / §2 output exactly (`…tied to 'item 2: fingerprint (a crystal decanter)': ['David']; proven murderer: David`, `…'_leaks(): ['E_pin_clean']`, `…['E_scene']`) |
| H8-I2, H8-I3, H8-N1…N9 | not re-run: their code is byte-identical to the reviewed tree (§7.1), so the original reproductions stand |

## 7.7 New findings

### H8-X2 — NON-BLOCKING (Phase 6 scope, latent): the oracle and the brute-force "ground truth" let an actor leave a room with no exit

The DP enters transit only along a travel edge (`feasibility.py:111–115`), so an actor in a room with no edge stays there or
the walk dies. `tail_ok` accepts "drift in transit after k" without asking whether `loc` has an edge. `check_walk` never
validates a trailing `~` run, so `brute_feasible` agrees with the oracle. That makes the module docstring's "the ground truth
both of the above are tested against" untrue in this corner. The `Case` model accepts such a room. The test's houses are all
connected, so the property test cannot see this.

Reproduction (`r_x2_exitless.py`):

```python
import sys; sys.dont_write_bytecode = True; sys.path.insert(0, r"D:\Murder Mystery")
from eidolon.solve.oracle import brute_feasible, check_walk, oracle_feasible
from eidolon.world.case import Case
from eidolon.world.entities import Actor
from eidolon.world.feasibility import _search
from eidolon.world.space import Location, TravelEdge

# A -1- B, and C with NO travel edge (the Case model accepts it)
ISO = Case(id="iso", t_investigation=3, actors={"x": Actor(id="x", name="x", role="suspect")},
           locations={k: Location(id=k, name=k) for k in "ABC"}, travel_edges=(TravelEdge(a="A", b="B", minutes=1),))
starts, args = [(L, 0) for L in "ABC"], ({("C", 1)}, {0: "C"}, [])       # in C at 0, C barred at 1: C has no way out
print("DP    :", _search(ISO, 3, starts, *args, None)[0])
print("oracle:", oracle_feasible(ISO, 3, *args, starts, None))
print("brute :", brute_feasible(ISO, 3, *args, starts, None))
print("check_walk accepts leaving a room with no exit:", check_walk(ISO, ["C", "~", "~"], *args))
```

Observed:

```
DP    : False
oracle: True
brute : True
check_walk accepts leaving a room with no exit: True
```

**Reach.** No room without an exit exists in any of the four bundles or in any of the 100 study seeds (`iso.py`, Appendix C:
`no exit: []` for every bundle, and no study seed printed). In a hand-authored case with such a room (a locked vault, say) the
verifier would over-approximate. It would refuse a valid proof that excludes someone trapped there. That fails closed: the
cost is availability (a valid case or save refused), not integrity. This is inferred from the code path and not demonstrated
end to end, because no such sealed case exists.

**Fix.** In `tail_ok`, allow the drift only if `k == T - 1` or `edges[loc]` is non-empty. In `check_walk`, reject a transit
whose origin has no neighbour. Add a house with a room without an exit to `test_dp_oracle_and_brute_force_agree`, and the
instance above as a deterministic test. Alternatively, make `Case` refuse a location with no edge, and test that.

### H8-N10 — NON-BLOCKING (test gap): the new guard has no mutant in the harness, and an under-approximating variant of the fix survives every deterministic test

- `tests/solve/mutation_check.py` has no entry for `tail_ok`. Its only `oracle.py` mutant, P2, attacks the arrival jump. The
  repair report's results do not include a mutant of the new guard. TK1 is killed by the new test (§7.3), but no harness entry records that.
- TK3 (`range(t, T)` → `range(t + 1, T)`) makes the oracle reject every walk whose existentials are first met on the last
  tick. That is an under-approximation, and in the verifier it means refusing valid proofs. No deterministic test kills it,
  the random property kills it in 8 of 30 seeds, and it survived the harness's full `tests/solve` + `tests/gen` selection
  (§7.3). Witness (`r_x1_t4_witness.py`):

```python
import sys, types; sys.dont_write_bytecode = True; sys.path.insert(0, r"D:\Murder Mystery")
import eidolon.solve.oracle as real
from tests.solve.test_oracle import TINY, T, STARTS, all_three

# TK3: the repaired tail_ok with its loop started one tick late (no drift straight after the last visit)
src = open(real.__file__, encoding="utf-8").read().replace("        for k in range(t, T):", "        for k in range(t + 1, T):", 1)
tk3 = types.ModuleType("eidolon.solve._tk3"); tk3.__package__ = "eidolon.solve"; exec(compile(src, "tk3", "exec"), tk3.__dict__)
exist = [{("A", T - 1)}]                       # the only existential is met on the LAST tick
print("current (dp, oracle, brute):", all_three(set(), {}, exist))
print("TK3 oracle:", tk3.oracle_feasible(TINY, T, set(), {}, exist, STARTS, None))
print("regression test's instance under TK3:", tk3.oracle_feasible(TINY, T, {("C", 1)}, {0: "C", 2: "C"}, [], STARTS, None), "(want False: TK3 passes it)")
```

Observed:

```
current (dp, oracle, brute): (True, True, True)
TK3 oracle: False
regression test's instance under TK3: False (want False: TK3 passes it)
```

- The property test runs 40 random examples with no `derandomize`. It found the pre-fix defect in 1 of 30 seeds, and the
  repository's example database no longer holds the counterexample (§7.3).

**Fix.** Add TK1 and TK3 to `M` in `tests/solve/mutation_check.py`, and TK6 to `EQUIVALENT` with its reason. Add
`assert all_three(set(), {}, [{("A", T - 1)}]) == (True, True, True)` as a deterministic test. Consider
`@settings(derandomize=True)` with more examples, or an exhaustive small-horizon sweep like §7.2's, which runs in seconds at
T=3.

## 7.8 Status of every finding after the follow-up

| ID | Grade | Status |
|---|---|---|
| H8-B1 | BLOCKING | **open**: code unchanged, reproduction re-run (§7.6) |
| H8-I1 | IMPORTANT | **open**: code unchanged, reproduction re-run |
| H8-I2 | IMPORTANT | **open**: code unchanged (not re-run) |
| H8-I3 | IMPORTANT | **open**: code unchanged (not re-run) |
| H8-N1…N9 | NON-BLOCKING | open, unchanged |
| H8-X1 | outside scope (Phase 6) | **repaired, verified** (§7.2–§7.5). Its §3a side-effect note is stale (§7.3) |
| H8-X2 | NON-BLOCKING (Phase 6 scope) | **new**, latent |
| H8-N10 | NON-BLOCKING (test gap) | **new** |

§6's required list is unchanged except item 5, whose last sentence no longer applies: the full suite is no longer blocked by
H8-X1 (2786 passed, §7.4). Of the other runs item 5 asks for, the persistence and Phase 8 suites were re-run. The `P8-`
mutation set was not, because the Phase 8 files did not change.

## Appendix C — follow-up scripts

All of these live in one scratch directory outside the repository. Run `recon.py` first: it writes `oracle_prefix.py` and
`test_oracle_prefix.py` next to itself, and `pre.py` loads the former as a sibling module of `eidolon.solve`.

`recon.py`: rebuilds the pre-fix files and checks them against the original review's manifest.

```python
"""Reconstruct the pre-fix oracle.py / test_oracle.py and check them against the review's tree manifest."""
import hashlib, itertools, sys
from pathlib import Path
ROOT = Path(r"D:\Murder Mystery")
cur = (ROOT / "eidolon/solve/oracle.py").read_bytes().decode()
NEW = '''        for k in range(t, T):                # stay put through tick k, drift in transit after it\r
            if k > t and not ok(loc, k):\r
                return False\r
            if all(forced.get(x) is None for x in range(k + 1, T)):\r
                return True\r
        return False\r
'''
assert cur.count(NEW) == 1
cands = {}
for pad in range(10, 24):
    OLD = ("        return all(forced.get(x) is None or (forced[x] == loc and (loc, x) not in blocked)\r\n"
           + " " * pad + "for x in range(t + 1, T))\r\n")
    cands[pad] = cur.replace(NEW, OLD).encode()
tcur = (ROOT / "tests/solve/test_oracle.py").read_bytes().decode()
TNEW = '''def test_tail_cannot_stay_put_on_a_blocked_tick():\r
    # C at 0 and 2 with (C,1) blocked: staying is blocked, the only round trip takes 4 minutes (Hypothesis counterexample)\r
    assert all_three({("C", 1)}, {0: "C", 2: "C"}, []) == (False, False, False)\r
\r
\r
'''
assert tcur.count(TNEW) == 1
told = tcur.replace(TNEW, "").encode()
print("old test size", len(told), "(pyc of Sep 20 records 3295)")
files = sorted(p for p in itertools.chain((ROOT / "eidolon").rglob("*.py"), (ROOT / "tests").rglob("*.py")) if "__pycache__" not in p.parts)
base = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
TARGET = "131887d83261ee7ceb4e4a3472552b29e1477ddd6e4a234a9a9e212d672699bb"
def recipes(m):
    keys = sorted(m)
    for sep in (" ", "  "):
        for order in ("ph", "hp"):
            for nl, tail in (("\n", "\n"), ("\n", "")):
                lines = [(f"{k}{sep}{m[k]}" if order == "ph" else f"{m[k]}{sep}{k}") for k in keys]
                yield (sep, order, tail), hashlib.sha256((nl.join(lines) + tail).encode()).hexdigest()
print("current tree:", [r for r, h in recipes(base) if h == TARGET] or "no recipe matches (expected: tree changed)")
for pad, ob in cands.items():
    m = dict(base, **{"eidolon/solve/oracle.py": hashlib.sha256(ob).hexdigest(), "tests/solve/test_oracle.py": hashlib.sha256(told).hexdigest()})
    hit = [r for r, h in recipes(m) if h == TARGET]
    if hit:
        print("MATCH: pre-fix oracle.py size", len(ob), "(pyc records 5658), continuation pad", pad, "recipe", hit)
        Path("oracle_prefix.py").write_bytes(ob); Path("test_oracle_prefix.py").write_bytes(told)
        sys.exit(0)
print("no reconstruction matched; sizes:", {p: len(b) for p, b in cands.items()})
```

`pre.py`: the preamble: the tree read-only plus the pre-fix oracle.

```python
"""Shared: the real tree read-only, plus the byte-exact PRE-FIX oracle loaded as a sibling module."""
import importlib.util, sys
sys.dont_write_bytecode = True
from pathlib import Path
ROOT = Path(r"D:\Murder Mystery"); sys.path.insert(0, str(ROOT))
HERE = Path(__file__).parent
import eidolon.solve  # noqa: E402
spec = importlib.util.spec_from_file_location("eidolon.solve._oracle_prefix", HERE / "oracle_prefix.py")
prefix = importlib.util.module_from_spec(spec); spec.loader.exec_module(prefix)
from eidolon.solve.oracle import brute_feasible, oracle_feasible  # noqa: E402
from eidolon.world.feasibility import _search  # noqa: E402
```

`diff.py`: `python -B diff.py 20000`, the §7.2 differential.

```python
"""Differential DP / oracle (current) / oracle (pre-fix) / brute force.
Part 1: EXHAUSTIVE over every blocked set x every forced map (x every goal) on tiny horizons.
Part 2: random instances with existentials on four houses (incl. a 3-minute edge and an isolated room)."""
import itertools, random, sys
from multiprocessing import Pool
from pre import prefix, brute_feasible, oracle_feasible
from pre import _search
from eidolon.world.case import Case
from eidolon.world.entities import Actor
from eidolon.world.space import Location, TravelEdge


def house(name, locs, edges):
    return Case(id=name, t_investigation=8, actors={"x": Actor(id="x", name="x", role="suspect")},
                locations={k: Location(id=k, name=k) for k in locs},
                travel_edges=tuple(TravelEdge(a=a, b=b, minutes=m) for a, b, m in edges))


HOUSES = {"tiny": house("tiny", "ABC", [("A", "B", 1), ("B", "C", 2)]),
          "long": house("long", "ABC", [("A", "B", 1), ("B", "C", 3)]),
          "ring": house("ring", "ABCD", [("A", "B", 1), ("B", "C", 1), ("C", "D", 2), ("D", "A", 3)]),
          "iso":  house("iso", "ABC", [("A", "B", 1)])}          # C has no exit


def run(job):
    hname, T, blocked, forced, exist, goal = job
    h = HOUSES[hname]
    starts = [(L, 0) for L in sorted(h.locations)]
    dp = _search(h, T, starts, set(blocked), dict(forced), [set(s) for s in exist], goal)[0]
    orc = oracle_feasible(h, T, set(blocked), dict(forced), [set(s) for s in exist], starts, goal)
    old = prefix.oracle_feasible(h, T, set(blocked), dict(forced), [set(s) for s in exist], starts, goal)
    bru = brute_feasible(h, T, set(blocked), dict(forced), [set(s) for s in exist], starts, goal)
    return job, dp, orc, old, bru


def exhaustive(hname, T, goals):
    locs = sorted(HOUSES[hname].locations)
    cells = [(l, t) for l in locs for t in range(T)]
    for bits in range(1 << len(cells)):
        blocked = tuple(c for i, c in enumerate(cells) if bits >> i & 1)
        for fv in itertools.product([None] + locs, repeat=T):
            forced = tuple((t, l) for t, l in enumerate(fv) if l)
            for g in goals:
                yield hname, T, blocked, forced, (), g


def randoms(n, seed):
    rng = random.Random(seed)
    for i in range(n):
        hname = ["tiny", "long", "ring", "iso"][i % 4]
        locs = sorted(HOUSES[hname].locations)
        T = 5 if hname == "ring" else 6
        cell = lambda: (rng.choice(locs), rng.randrange(T))      # noqa: E731
        blocked = tuple(sorted({cell() for _ in range(rng.randint(0, 7))}))
        forced = tuple(sorted({rng.randrange(T): rng.choice(locs) for _ in range(rng.randint(0, 4))}.items()))
        exist = tuple(tuple(sorted({cell() for _ in range(rng.randint(1, 3))})) for _ in range(rng.randint(0, 2)))
        yield hname, T, blocked, forced, exist, rng.choice([None, None, locs[0], locs[-1]])


if __name__ == "__main__":
    parts = {"exhaustive tiny T=3, every blocked set x forced map x goal": exhaustive("tiny", 3, [None, "A", "B", "C"]),
             "exhaustive iso  T=3, every blocked set x forced map x goal": exhaustive("iso", 3, [None, "A", "B", "C"]),
             "exhaustive tiny T=4, every blocked set x forced map, goal None": exhaustive("tiny", 4, [None]),
             "exhaustive long T=4, every blocked set x forced map, goal None": exhaustive("long", 4, [None]),
             f"random x{sys.argv[1]} (4 houses, existentials, goals)": randoms(int(sys.argv[1]), 20261020)}
    with Pool(10) as pool:
        for label, jobs in parts.items():
            n, bad, oldbad, first = 0, {}, 0, {}
            for job, dp, orc, old, bru in pool.imap_unordered(run, jobs, chunksize=256):
                n += 1
                if not dp == orc == bru:
                    key = (job[0], dp, orc, bru)
                    bad[key] = bad.get(key, 0) + 1
                    first.setdefault(key, job)
                if old != bru:
                    oldbad += 1
            print(f"{label}: {n} instances | current DP/oracle/brute disagreements: {sum(bad.values())} "
                  f"| pre-fix oracle != brute: {oldbad}", flush=True)
            for k, v in bad.items():
                print(f"    house {k[0]} (dp, oracle, brute) = {k[1:]}: {v}x, e.g. {first[k]}", flush=True)
```

`mut.py`: §7.3 mutants.

```python
"""Mutants of the repaired `tail_ok`, each in its own scratch copy (no .hypothesis DB: the property test runs on luck alone).
For each: the regression test alone, then the whole of tests/solve/test_oracle.py."""
import os, re, shutil, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(r"D:\Murder Mystery")
GUARD = "            if k > t and not ok(loc, k):\n                return False\n"
LOOP = "        for k in range(t, T):"
BODY = ("        for k in range(t, T):                # stay put through tick k, drift in transit after it\n" + GUARD +
        "            if all(forced.get(x) is None for x in range(k + 1, T)):\n                return True\n        return False\n")
MUTANTS = {
    "T0 baseline (no mutation)": None,
    "T1 blocked-tick guard removed: stay-put checks the forced map only": (GUARD, GUARD.replace("not ok(loc, k)", "forced.get(k) not in (None, loc)")),
    "T2 whole stay-put guard deleted": (GUARD, ""),
    "T3 guard checks blocked cells only (a forced elsewhere tick is ignored)": (GUARD, GUARD.replace("not ok(loc, k)", "(loc, k) in blocked")),
    "T4 no immediate drift: loop starts at t + 1": (LOOP, "        for k in range(t + 1, T):"),
    "T5 full revert to the pre-fix body": (BODY, "        return all(forced.get(x) is None or (forced[x] == loc and (loc, x) not in blocked)\n"
                                                 "                   for x in range(t + 1, T))\n"),
    "T6 k > t -> k >= t (expected EQUIVALENT: every stacked state is already ok)": (GUARD, GUARD.replace("k > t", "k >= t")),
}
if __name__ == '__main__':
    REG = "tests/solve/test_oracle.py::test_tail_cannot_stay_put_on_a_blocked_tick"
    for name, edit in MUTANTS.items():
        d = Path(tempfile.mkdtemp(prefix="p8mut-"))
        for sub in ("eidolon", "tests"):
            shutil.copytree(ROOT / sub, d / sub, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.copy(ROOT / "pyproject.toml", d)
        f = d / "eidolon/solve/oracle.py"
        src = f.read_bytes().decode().replace("\r\n", "\n")
        if edit:
            assert src.count(edit[0]) == 1, name
            src = src.replace(edit[0], edit[1])
        f.write_bytes(src.replace("\n", "\r\n").encode())
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        out = {}
        for label, target in (("regression test", REG), ("test_oracle.py", "tests/solve/test_oracle.py")):
            r = subprocess.run([sys.executable, "-B", "-m", "pytest", target, "-q", "-p", "no:cacheprovider", "--basetemp", str(d / "bt")],
                               cwd=d, env=env, capture_output=True, text=True)
            tail = r.stdout.strip().splitlines()[-1]
            why = re.findall(r"^E\s+(assert .*)$", r.stdout, re.M)[:1]
            failed = re.findall(r"^FAILED (\S+)", r.stdout, re.M)
            out[label] = f"exit {r.returncode}: {tail}" + (f" | {why[0][:110]}" if why else "") + (f" | failed: {[x.split('::')[-1] for x in failed]}" if failed else "")
        print(name)
        for k, v in out.items():
            print(f"    {k:16} {v}")
        shutil.rmtree(d, ignore_errors=True)
```

`killrate.py`: §7.3 property kill rates; imports `mut.py`.

```python
"""How often does the random property test alone (no example DB) kill T4 and T5? 30 Hypothesis seeds each."""
import os, shutil, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from mut import MUTANTS, ROOT  # noqa  (mut.py's loop is guarded below)
PROP = "tests/solve/test_oracle.py::test_dp_oracle_and_brute_force_agree"


def tree(edit):
    d = Path(tempfile.mkdtemp(prefix="p8kr-"))
    for sub in ("eidolon", "tests"):
        shutil.copytree(ROOT / sub, d / sub, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy(ROOT / "pyproject.toml", d)
    f = d / "eidolon/solve/oracle.py"
    src = f.read_bytes().decode().replace("\r\n", "\n")
    assert src.count(edit[0]) == 1
    f.write_bytes(src.replace(edit[0], edit[1]).replace("\n", "\r\n").encode())
    return d


def one(d, seed):
    hyp = Path(tempfile.mkdtemp(prefix="p8krh-"))           # fresh cwd => fresh, empty .hypothesis per run
    r = subprocess.run([sys.executable, "-B", "-m", "pytest", str(d / PROP.split("::")[0]) + "::" + PROP.split("::")[1], "-q",
                        "-p", "no:cacheprovider", f"--hypothesis-seed={seed}", "--rootdir", str(d), "--basetemp", str(hyp / "bt")],
                       cwd=hyp, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(d)), capture_output=True, text=True)
    return r.returncode


for name in [n for n in MUTANTS if n.startswith(("T4", "T5", "T1"))]:
    d = tree(MUTANTS[name])
    with ThreadPoolExecutor(8) as ex:
        codes = list(ex.map(lambda s: one(d, s), range(30)))
    print(f"{name}: killed by the property in {sum(c == 1 for c in codes)}/30 seeds (other exit codes: {[c for c in codes if c not in (0, 1)]})", flush=True)
```

`addmut.py`: adds TK1–TK3 to a scratch copy of the Phase 6 harness: `python -B addmut.py <copy>/tests/solve/mutation_check.py`.

```python
import sys
p = sys.argv[1]
s = open(p, encoding="utf8").read()
anchor = '  "RB2-o finalize never climbs the boost ladder": [(G+"pipeline.py", "    for level in fair.BOOST_LADDER:", "    for level in fair.BOOST_LADDER[:1]:")],\n}'
assert s.count(anchor) == 1
BS = chr(92)
add = ('  "TK1 tail_ok stays put on a blocked tick (guard checks the forced map only)": [(S+"oracle.py", "            if k > t and not ok(loc, k):", "            if k > t and forced.get(k) not in (None, loc):")],\n'
       '  "TK2 tail_ok stay-put guard deleted": [(S+"oracle.py", "            if k > t and not ok(loc, k):' + BS + 'n                return False' + BS + 'n", "")],\n'
       '  "TK3 tail_ok never drifts at once (loop starts at t + 1)": [(S+"oracle.py", "        for k in range(t, T):", "        for k in range(t + 1, T):")],\n')
s = s.replace(anchor, anchor[:-1] + add + "}")
open(p, "w", encoding="utf8").write(s)
import importlib.util
spec = importlib.util.spec_from_file_location("mc", p); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print([k for k in m.M if k.startswith(("TK", "P2"))])
```

`trace.py`: `python -B trace.py a` (bundles), `python -B trace.py b 8` (seed study).

```python
"""Does the oracle fix change any proof, seal, uniqueness result or acceptance decision?

Every oracle query the proof verifier makes is answered by the CURRENT oracle and, side by side, by the byte-exact PRE-FIX oracle
and by the production DP (`world.feasibility._search`). Zero disagreements on the path the verifier actually takes means the
pre-fix verifier walks the same path to the same verdict (the verifier is deterministic and only the oracle changed).

Part A: the four sealed bundles, through `load_sealed_case` (every seal + `verify_proof`), plus `verify_proof` answered by the pre-fix
oracle alone.  Part B: the 2x50 seed study, generation run through V-0..V-3 and V-5 (the only stage that consults the oracle;
V-4/V-6/V-7 never do), with the golden seeds' rebuilt package seal and proof compared byte-for-byte with the stored bundles."""
import glob, hashlib, json, sys
from concurrent.futures import ProcessPoolExecutor
from pre import ROOT, prefix
from pre import _search
import eidolon.solve.proof_material as pm
from eidolon.solve import oracle as cur

MODE = {"answer": "new"}
STATS = {"calls": 0, "old_differs": [], "dp_differs": []}


def dual(case, T, blocked, forced, exist, starts, goal=None):
    a = cur.oracle_feasible(case, T, blocked, forced, exist, starts, goal)
    b = prefix.oracle_feasible(case, T, blocked, forced, exist, starts, goal)
    d = _search(case, T, list(starts), set(blocked), dict(forced), [set(s) for s in exist], goal)[0]
    STATS["calls"] += 1
    if a != b:
        STATS["old_differs"].append((sorted(forced.items())[:6], len(blocked), goal, a, b))
    if a != d:
        STATS["dp_differs"].append((sorted(forced.items())[:6], len(blocked), goal, a, d))
    return a if MODE["answer"] == "new" else b


pm.oracle_feasible = dual


def reset():
    STATS.update(calls=0, old_differs=[], dp_differs=[])


def part_a():
    from eidolon.solve.package import load_sealed_case
    from eidolon.solve.proof import verify_proof
    for p in sorted(glob.glob(str(ROOT / "cases/generated/*.json"))):
        reset(); MODE["answer"] = "new"
        sc = load_sealed_case(p)                       # raises unless every seal matches and verify_proof(...) == []
        n, od, dd = STATS["calls"], len(STATS["old_differs"]), len(STATS["dp_differs"])
        MODE["answer"] = "old"
        old = verify_proof(sc.package, sc.proof)
        MODE["answer"] = "new"
        print(f"{p.split(chr(92))[-1]}: load_sealed_case OK (package seal {sc.package.seal[:16]}, unique={sc.proof['unique']}, "
              f"survivors={sc.proof['survivors']}) | oracle queries {n}, current!=pre-fix {od}, current!=DP {dd} "
              f"| verify_proof with the PRE-FIX oracle: {old or '[] (verifies)'}", flush=True)


def one(job):
    sk, seed = job
    import eidolon.gen.pipeline as pl
    from eidolon.gen.study import _bucket
    real = pl._stage

    def stage(rep, name, fn):
        if name in ("V-4", "V-6", "V-7"):
            rep.failed_at = "stopped-after-V-5"
            return False
        return real(rep, name, fn)
    pl._stage = stage
    reset()
    r = pl.generate(sk, seed)
    out = {"sk": sk, "seed": seed, "calls": STATS["calls"], "old_differs": STATS["old_differs"][:3], "n_old": len(STATS["old_differs"]),
           "n_dp": len(STATS["dp_differs"]), "dp_differs": STATS["dp_differs"][:3],
           "outcome": "passed V-5" if r.failed_at == "stopped-after-V-5" else _bucket(r.failed_at, r.problems),
           "problems": [x[:140] for x in (r.problems if r.failed_at != "stopped-after-V-5" else [])][:2]}
    if r.package is not None:
        out["seal"] = r.package.seal
    if r.report is not None and r.report.proof is not None:
        out["proof_sha"] = hashlib.sha256(json.dumps(r.report.proof, sort_keys=True).encode()).hexdigest()
        out["unique"] = r.report.proof.get("unique"); out["survivors"] = r.report.proof.get("survivors")
        g = ROOT / "cases/generated" / f"{sk}_s{seed}.json"
        if g.exists():
            doc = json.loads(g.read_text(encoding="utf-8"))
            out["golden"] = {"package_seal_equal": doc["package"]["seal"] == r.package.seal,
                             "proof_equal": json.dumps(doc["proof"], sort_keys=True) == json.dumps(json.loads(json.dumps(r.report.proof)), sort_keys=True)}
    return out


if __name__ == "__main__":
    if sys.argv[1] == "a":
        part_a()
    else:
        from eidolon.gen.skeletons import SKELETONS
        jobs = [(sk, s) for sk in sorted(SKELETONS) for s in range(1, 51)]
        rows = []
        with ProcessPoolExecutor(int(sys.argv[2])) as ex:
            for row in ex.map(one, jobs):
                rows.append(row)
                if row["outcome"] != "passed V-5" or row["n_old"] or row["n_dp"] or "golden" in row:
                    print(json.dumps(row), flush=True)
        json.dump(rows, open("trace_rows.json", "w"), indent=1)
        for sk in sorted(SKELETONS):
            mine = [r for r in rows if r["sk"] == sk]
            print(f"{sk}: {len(mine)} seeds | passed V-5 {sum(r['outcome'] == 'passed V-5' for r in mine)} | outcomes "
                  f"{sorted({r['outcome'] for r in mine})} | oracle queries {sum(r['calls'] for r in mine)} | current!=pre-fix "
                  f"{sum(r['n_old'] for r in mine)} | current!=DP {sum(r['n_dp'] for r in mine)}", flush=True)
```

`r_x1_downstream.py`: §7.5 saves across the fix and verification cost.

```python
"""Phase 8 meets the oracle only where a save is made or opened (`load_sealed_text` -> `verify_proof`). (1) a save made with the
PRE-FIX verifier opens under the current one and vice versa, same murderer and state hash; (2) cost of one bundle verification,
pre-fix vs current oracle, interleaved."""
import glob, statistics, tempfile, time
from pathlib import Path
from pre import ROOT, prefix
import eidolon.solve.proof_material as pm
from eidolon.solve import oracle as cur
from eidolon.solve.package import load_sealed_text
from eidolon.store import Save

use = lambda f: setattr(pm, "oracle_feasible", f)          # noqa: E731
for p in sorted(glob.glob(str(ROOT / "cases/generated/*.json"))):
    name, text = Path(p).stem, Path(p).read_text(encoding="utf-8")
    d = Path(tempfile.mkdtemp(prefix="p8x1-"))
    use(prefix.oracle_feasible); a = Save.create(d / "old.db", p, seed=7); ha, ma = a.state_hash(), a.state.murderer; a.close()
    use(cur.oracle_feasible);    b = Save.open(d / "old.db"); hb, mb = b.state_hash(), b.state.murderer; b.close()
    c = Save.create(d / "new.db", p, seed=7); hc = c.state_hash(); c.close()
    use(prefix.oracle_feasible); e = Save.open(d / "new.db"); he = e.state_hash(); e.close()
    times = {"pre-fix": [], "current": []}
    for _ in range(5):
        for label, f in (("pre-fix", prefix.oracle_feasible), ("current", cur.oracle_feasible)):
            use(f); t0 = time.perf_counter(); load_sealed_text(text); times[label].append(time.perf_counter() - t0)
    use(cur.oracle_feasible)
    print(f"{name}: pre-fix save -> current open: murderer {ma}->{mb}, state hash equal {ha == hb} | current save -> pre-fix open: "
          f"state hash equal {hc == he}, both saves same initial state {ha == hc} | load_sealed_text median "
          + ", ".join(f"{k} {statistics.median(v):.2f}s" for k, v in times.items()), flush=True)
```

`iso.py`: H8-X2 reach: rooms with no exit in the bundles and the study seeds.

```python
"""Does any real case have a location with no travel edge (the room the DP cannot leave, but oracle/brute can drift from)?"""
from pre import *  # noqa
import json, glob
from eidolon.solve.package import load_sealed_case
from eidolon.world.case import Case
for p in sorted(glob.glob(str(ROOT / "cases/generated/*.json"))):
    sc = load_sealed_case(p)
    case = sc.package.case
    iso = sorted(l for l in case.locations if not list(case.travel_graph.neighbours(l)))
    print(p.split("\\")[-1], "locations", len(case.locations), "| no exit:", iso)
from eidolon.gen.skeletons import SKELETONS
from eidolon.gen.planner import plan
from eidolon.gen.compile import compile_draft
for k in sorted(SKELETONS):
    for seed in range(1, 51):
        dr = plan(SKELETONS[k], seed)
        if dr.error:
            continue
        case = compile_draft(dr).case
        iso = sorted(l for l in case.locations if not list(case.travel_graph.neighbours(l)))
        if iso:
            print("study seed", k, seed, "no exit:", iso)
print("skeleton sweep done (seeds 1-50, both skeletons)")
```


---

# Repair, 2026-10-21: H8-B1, H8-I1, H8-I2, H8-I3 (author's record, not a review)

Everything above this line is the independent review, unchanged. This section was added by the session that repaired the four
findings. It is **not** a re-review: it records what was changed and what was run, and the findings stay open until an independent
re-review closes them. The full record is `docs/EIDOLON-PHASE-8-REPAIR-REPORT.md` (root cause, exact reproductions before and
after, failing-first tests, mutants, run commands and exit statuses, the trees and their hashes).

**Object.** The tree of §7.1 (manifest `fb6efde63b92…`, byte-identical to the follow-up's "today's tree") → manifest
`282cc2662679aaf4a32c211e0ad7232181540be3885508d87b72a612d19da097`. Seven production files changed: `evidence/discovery.py`,
`decision/hypotheses.py`, `decision/exploration.py`, `decision/turn.py`, `game.py`, `web.py`, `cli.py`. `store.py`, `solve/**`, `gen/**`,
`world/**`, `minds/**`, `llm/**` and the four bundles are byte-identical; `solve/oracle.py` (the H8-X1 repair) is untouched.

| ID | Status after the repair | What changed |
|---|---|---|
| H8-B1 | **repaired, awaiting independent re-review** | the three hypothesis evaluators and `game._tensions` read only unlocked implications (`evidence.discovery.held_material` / `unlocked_view`); §13.2's `strength >= 0.5` floor in the plain evaluator; `game.player_objects` replaces `held_names` for the notebook vocabulary (`held_names` unchanged). The review's `r_b1_all_cases.py` now prints `[]` for all four cases |
| H8-I1 | **repaired, awaiting independent re-review** | `exploration._hint` names no evidence / statement / account / kit id; display names for places and objects; `run_search_turn` passes the case. `r_i1_hint_ids.py` now leaks nothing |
| H8-I2 | **repaired, awaiting independent re-review** | `web.allowed_hosts(port)` + a middleware that answers 400 to any request whose `Host` is not a loopback name on the served port (every route, GET and POST); `Origin` is compared with the matching origins, not with `Host`. Checked in-process and against a live `uvicorn` with `curl` |
| H8-I3 | **repaired, awaiting independent re-review** | `Games.open` opens a save only under its on-disk spelling (the review's second option); `game._commit` honours `AppendResult` (`appended=False` → duplicate; `same_events=False` → stale; the recomputed reply is never shown) |
| H8-N1…N9 | open, unchanged | not touched |
| H8-X1 | repaired (§7), preserved | `oracle.py` byte-identical; `test_tail_cannot_stay_put_on_a_blocked_tick` passes |
| H8-X2 | open, NON-BLOCKING, unchanged | a strict-`xfail` witness test was added |
| H8-N10 | open, NON-BLOCKING, partly addressed | the deterministic TK3 test was added and kills TK3; no harness entry, property test not derandomised |

New NON-BLOCKING items found by the repair (R-1…R-7) are listed in the repair report §11 and in `docs/EIDOLON-KNOWN-DEBT.md` §E.

§6's list, item by item: 1 (H8-B1) done, 2 (H8-I1) done, 3 (H8-I2) done, 4 (H8-I3) done; 5 re-runs: `tests/test_phase8.py` 147 passed,
`tests/test_persistence.py` 315 passed, the `P8-`/`F1a-` mutation set with the 26 new mutants, the full suite 2833 passed + 1 xfailed
(exit 0) — figures, commands and trees in the repair report §8. H8-N1, H8-N2 and H8-N6 (the "cheap, same change" items) were **not** done.
