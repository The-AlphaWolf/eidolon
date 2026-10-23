# EIDOLON — ADR-30 report: a lie answers only its own topic (and the answer-quality changes around it)

Date: 2026-10-22. Author's record (the session that made the change; not independently reviewed). No VCS; nothing committed.

## 1. Why

Playing with a live model (Gemini, free tier) showed answers no player would accept. Asked "What did you hear that night?", the
murderer in `study_party_s4` said "I never touch a crystal decanter." Two causes:

1. **Engine (ADR-30).** Topicality is a footprint — who, where, when (ADR-26, I-55) — with no notion of WHAT is asked. David's cover
   has one layer-0 lie, a deed denial, and any question about him at a matching time selected it.
2. **Parser / renderer.** The parse prompt never described `predicate_hint`, so typed questions lost their topic; typed times were
   kept as words and never became a window; every character had the same "plain" voice; a claimless answer rendered as "...".

## 2. ADR-30 (engine)

`decision/footprint.py`: `TOPIC_OF_HINT` (moved from `turn.py`; one map, read by memory retrieval and the LIE gate), `TOPIC_KINDS`
(`at` → At/NotAt/Saw, `heard` → Heard, `did` → Did/DidNot), `query_topic`, `on_topic`. `strategy._lie` additionally requires the
covering deceptive claim to be `on_topic`. A question naming no topic, or an unknown hint (the bluff bot's `bluffN`), is unrestricted
— unchanged behaviour, bluff parity untouched. The query KIND is not read (a ponytail note says where to add it). Off topic the
speaker does not lie; `speakable` (I-54) already withholds every protected truth, so the answer is a non-answer or an unprotected
truth, never a leak. Spec: I-55, the §10.3 act table and ADR-30 in `docs/EIDOLON-ARCHITECTURE.md`.

Live and engine checks on `study_party_s4` (David, murderer; cover lie = DidNot decanter; protected 00:56–01:01):

| question | before | after |
|---|---|---|
| what did you hear (that night) | LIE "I never touch a crystal decanter." | DONT_RECALL "I'm sorry. I honestly can't remember." (live) |
| what did you do, 01:00–01:30 | LIE | LIE (on topic: still told) |
| where were you, 01:00–01:30 | LIE | TRUTH "guest room 01:29–01:59" (nothing from the protected window) |

Tests: `tests/decision/test_topicality.py` `test_adr30_*` (8: every topic, no topic, an unknown hint, and a real sealed-case turn
asserting no LIE and no protected proposition off topic, LIE on topic). Mutants (`tests/decision/mutation_check.py`): ADR30-a (LIE
ignores topic), ADR30-b (no-topic question gets no lie), ADR30-c (heard answered by deed denials) — all killed; `RB2-c`
(`tests/solve/mutation_check.py`) re-pointed at the new line, same mutation.

Two existing tests changed, neither weakened: `test_H9_B1_showing_an_inert_item…` now samples every question instead of every other
(ADR-30 left fewer, on-topic lies; its coverage floor of 3 lies is unchanged and its escalation assertion untouched);
`test_H8_I1_a_denial_that_puts_the_weapon_on_the_list…` asks the murderer about `did` instead of `heard` to elicit the denial — the
old setup relied on the non-sequitur; what it asserts (searching the decanter early names no scene) is unchanged.

## 3. Parser, renderer and fallback (answer quality, no engine change)

* `llm.ingress.SYSTEM_PARSE`: describes `predicate_hint` (presence / heard / did), `time_text`, `subject` ("you" = the addressee).
* `ingress.clock_interval`: a typed time → the question form's half-hour window ("half past midnight" → 00:30–01:00, "2am",
  "1:30"); anything not read exactly, or outside the investigation, is no window. `ground` resolves "you" to the addressee only.
* `solve.session.default_voice`: each character gets a register, an idiom and a tic, chosen by hash of name and seed — never from
  secrets or guilt. **Corrected 2026-10-22 (review NR-B1):** the original version derived the voice in `solve.session`, and
  `store.initial_digest` binds the derived character state into every save's genesis — it made every older save unreadable.
  The voice is now derived at render time (`decision/voice.py`); the session stores the legacy default.
* `llm.render.SYSTEM_GENERATE`: speak naturally in the voice; a claimless reply still answers ("can't remember / don't know / won't
  say") without describing events.
* `decision.llm.CLAIMLESS_LINES`: the template's claimless reply is a tone-keyed line ("I'm sorry. I honestly can't remember.")
  instead of "..."; each passes every lexical check a model's colour segment must.
* `decision.validator._NON_ENTITY_WORDS`: spoken openers, interjections, times of day and forms of address added (no given names),
  as its own comment foresaw — natural speech starting "Look," or "Honestly," was being rejected as an unknown name.
* `llm.provider`: free OpenAI-compatible providers (Gemini, Groq, GitHub Models, OpenRouter, Ollama) for play — see `CLAUDE.md`.

## 4. Runs (tree `a18946074df764bb…`, byte-verified scratch copies; later edits noted)

| run | result |
|---|---|
| `python -m pytest -q -p no:cacheprovider` | 3862 passed, 1 failed (`test_H8_I1_a_denial…`, see §2), 1 skipped, 1 xfailed; after the fix: `tests/llm tests/test_phase8.py tests/test_phase9_corpus.py tests/test_phase9_nightly.py` 2291 passed, 1 skipped, exit 0 |
| `python -m tests.decision.mutation_check` | PASS: 60 killed (57 + ADR30-a/b/c), 2 justified equivalent (M2, M4), exit 0 |
| `MUT_TIMEOUT=6000 MUT_ONLY='^(RB1-c\|RB1-h\|RB2-a\|RB2-b\|RB2-c\|RB2-g\|RB2-h\|RB2-i) ' python -m tests.solve.mutation_check` | baseline green (349 passed, 1 xfailed); 8 killed, PASS, exit 0 |
| `python -m tests.phase9_mutation_check -k H9-B1` | baseline green; 8 killed, exit 0 |
| `python -m eidolon.cli validate cases/generated/<case>.json` × 4 | all `ok`, exit 0 |
| V-7 bots, full scale, four sealed cases | all 20 ok/solved; bluff bot byte-identical (parity holds); greedy/cue/peel acts shift from LIE to honest answers, credited atoms up slightly (e.g. 57 → 66), cue-following on `manor_wing_s4` 257 → 273 actions (budget 400); adversarial envelope 312 → 362 chars (the voices, ceiling 4096) |
| `python -m eidolon.gen.study --seeds 50 --start 1` | manor_wing 49/50 (the known `V-5:robust` rejection), study_party 50/50, all in band — same as before; 98/100 rows identical, `study_party` 28 and 49 seal with a different package seal (same metrics); the four goldens regenerate to their committed seals — no sealed case changes |

## 5. Open

* Truthful/vague answers can still be off topic when the speaker has no memory on the asked topic (memory retrieval returns the
  nearest memory): not a lie and not a leak, but loosely relevant. Same kind of fix, in `minds.memory` retrieval.
* Covers have one lie per secret; richer covers (a lie per topic, e.g. the murderer's "I heard nothing") are a cover-synthesis change.
* Hint-less questions are unrestricted; the query kind ("where") is not read.
* Needs an independent review like every phase change here.
