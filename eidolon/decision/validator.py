"""Response validation and repair (§14). Fail-closed (I-15): any check failure is reported,
never silently repaired into acceptance, and `turn.py` commits nothing on a hard failure.

Phase 4 runs every DETERMINISTIC check for real — (b) lexical guard, (c) per-segment slot
checks regardless of `kind` (I-36), (e) leak, (f) pairwise + joint consistency (I-28), (g)
modality — over `TemplateLLM`'s real (faithful-by-construction) output. (d) the verifier is
an LLM call at Phase 5; here it is a deterministic RE-RENDER equality check, which is the one
role `TemplateLLM` can play without a model (§28.2: "faithful claims") and is still a REAL
check — a hand-built mismatched `Draft` in the test suite proves it actually catches
something, exactly like a `MutantLLM` class would (T-13/T-14's own shape, without that
Phase 5 model).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, fields
from typing import Callable, Iterable

from ..evidence.contradiction import contradiction
from ..minds.character import VoiceSpec
from ..world.alias import render_time
from ..world.case import Case
from ..world.facts import FactIndex
from ..world.feasibility import Claim as FeasClaim
from ..world.feasibility import feasible
from ..world.ids import ActorId
from ..world.propositions import Proposition, entities
from .claims import Claim, ClaimId, StatementStore
from .context import DecisionContext
from .digest import ConversationDigest, evidence_labels
from .llm import Draft, Segment, render_claim
from .secrets import Ref
from .speech_acts import ACT_TABLE, RETRACTION_EXEMPT_ACTS
from .strategy import DeliveryDirective, ResponsePlan
from .envelope import Envelope, EnvelopeClaim, PersonaSlot, render_digest

FORBIDDEN_VOCAB = ("prompt", "instruction", "system prompt", "as an ai", "as an assistant",
                    "language model", "developer mode", "{", "}", "```")
# Engine vocabulary no in-world speaker has any reason to say (§22.3: a hidden sincerity label
# or a plan/claim id in the text is a side channel). Substring match, lowercase.
ENGINE_VOCAB = ("sincerity", "sincere_false", "deceptive", "refutation", "speech act", "layer peel",
                "layerpeel", "cover story", "authorized_reveals", "allowed_claims", "claim id", "claim_id", "claim_ids", "grounding",
                "provenance", "envelope")
_CLOCK = re.compile(r"\b\d{1,2}:\d{2}\b")
# Time expressions other than a verbatim clock time. Spelled-out numbers ("around ten") are not
# deterministically detectable and belong to the verifier (§14.2(d)), as lowercase nouns do for names.
_TIME_WORDS = re.compile(r"\bo'clock\b|\b(?:half|quarter)\s+(?:past|to|after|before)\b|\b\d+\s*(?:a\.?m|p\.?m)\b\.?"
                         r"|\b(?:minutes?|mins?)\s+(?:past|to|before|after)\b|\b(?:midnight|noon|midday)\b", re.I)
_TIME_RE = re.compile(_CLOCK.pattern + r"|\baround \d|" + _TIME_WORDS.pattern, re.I)
# Best-effort lexical backstops for §14.2(e) "must not entail Solution unless act = CONFESSION" and
# §22.3's sincerity tells. Least privilege is the real defense (a renderer that is never told the
# solution cannot state it); these only refuse the plainest phrasings a hostile one could try.
# Implicature is the verifier's (§33.3).
_CONFESSES = re.compile(r"\bi\s+(?:killed|murdered|stabbed|strangled|poisoned|shot|did it)\b|\bi(?:'m| am)\s+(?:guilty|the (?:killer|murderer))\b"
                        r"|\b(?:is|was)\s+the\s+(?:killer|murderer)\b|\bmurdered\s+(?:him|her)\b", re.I)
_LIE_TELLS = re.compile(r"\bi(?:'m| am)\s+lying\b|\bi\s+lied\b|\bthat\s+was\s+a\s+lie\b|\bmy\s+(?:cover|alibi)\s+(?:story|is\s+false)\b", re.I)
# I-42: the player-visible length band is a function of the plan's CLAIM CONTENT only, never of
# sincerity or act class — the draft must land in the band its canonical rendering lands in.
LENGTH_EDGES = (200, 400, 800)

# Violations the RENDERER can cause and the deterministic fallback cures. The fallback speaks
# the plan (§14.3), so it is only sound when the plan itself passed. Every other code — the
# plan-level checks (e) Solution, (f) consistency/feasibility, (g) modality, and anything added
# later — rejects the turn outright: nothing committed, no in-world text (I-12, I-15).
DRAFT_LEVEL_CODES = frozenset({
    "FORBIDDEN_VOCAB", "CANARY_LEAK", "UNKNOWN_ENTITY", "UNTAGGED_ASSERTION",
    "CLAIM_ID_NOT_IN_ENVELOPE", "SLOT_MISMATCH", "COLOR_CARRIES_CONTENT", "QUESTION_HAS_CLAIMS",
    "QUESTION_CARRIES_CONTENT", "NONVERBAL_LEAK", "ASSERTS_NOT_EXACTLY", "UNAUTHORIZED_CLAIM",
    "TIME_SLOT_MISMATCH", "INTERNAL_TOKEN_LEAK", "LENGTH_BAND", "EXTRA_ASSERTION",
    "UNREFERENCED_ASSERTION", "MODALITY_MISMATCH", "PLAN_CLAIM_OMITTED", "SELF_DISCLOSURE",
})


def violation_code(violation: str) -> str:
    return re.split(r"[\[:]", violation, maxsplit=1)[0]


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    text: str
    claim_ids: tuple[ClaimId, ...]
    violations: tuple[str, ...] = ()
    fallback: bool = False
    rejected: bool = False  # a plan-level failure: commit nothing, show nothing (I-15)

    def integrity(self) -> str | None:
        """`None` when the flag combination is one this module can actually produce; a code
        otherwise (F-7). There are exactly three shapes:

        - **accepted** — `ok`, no violations: the draft's own text and its own tags;
        - **fallback** — `fallback`, either `ok` (the template itself passed) or not (draft-level
          violations, cured by speaking the plan): text and ids are the PLAN's;
        - **rejected** — `rejected` with violations, no text and no claim ids (I-15).

        Anything else is a bug in a validator or a renderer — notably `ok=False` with neither
        `rejected` nor `fallback`, which the commit gate used to treat as success because it
        tested `rejected` rather than the semantics. A bug must fail the turn closed, not open."""
        if self.ok and self.rejected:
            return "OK_AND_REJECTED"
        if self.ok and self.violations:
            return "OK_WITH_VIOLATIONS"
        if self.rejected and (self.text or self.claim_ids):
            return "REJECTED_WITH_CONTENT"
        if not self.ok and not self.rejected and not self.fallback:
            return "NEITHER_OK_NOR_REJECTED"
        if not self.ok and not self.violations:
            return "FAILED_WITHOUT_VIOLATIONS"
        return None

    @property
    def committable(self) -> bool:
        """The ONLY predicate an authoritative caller may commit on. `not rejected` is not it."""
        return self.integrity() is None and not self.rejected and (self.ok or self.fallback)


def _name_index(case: Case) -> dict[str, str]:
    idx: dict[str, str] = {}
    for cid, actor in case.actors.items():
        idx[actor.name.lower()] = cid
    for lid, loc in case.locations.items():
        idx[loc.name.lower()] = lid
    for oid, obj in case.objects.items():
        idx[obj.name.lower()] = oid
    idx.update(case.alias.names)  # §4.4: every surface name/nickname, already lowercased
    return idx


# §14.2(b) is an ALLOW-list: "every proper noun / entity mention must resolve to an entity in
# known_entities(character) ∪ entities_in_query". A capitalised token is either a name that
# resolves through the case's name/alias table, or one of these closed-class words that are
# never names. Anything else names an entity the case does not contain, and fails (I-15).
# ponytail: closed class only, so a sentence-initial content word ("Honestly, ...") also fails
# and falls back; widen this list if the fallback rate says so, never swap it for a deny-list.
# Never add a word that is also a given name ("Will", "May"): an invented person would pass.
_NON_ENTITY_WORDS = frozenset("""
i i'm i've i'd i'll a an the this that these those it it's its he she we they you me my mine
our ours your yours his her hers their theirs them us him yes no not nor never and but or so
yet if then when where why what who whom whose which how well oh ah perhaps maybe of in on
at to from by with for as there here now once after before during until since because
although though while do does did don't didn't is was were are am be been have has had can
could would shall should might must nothing nobody none someone somebody something
everyone everybody everything anyone anybody anything all any some each every both either
neither one only just still even also really very quite sorry please thank thanks
look listen right alright okay ok fine good goodness heavens gosh dear hm hmm um er uh mind between rather
honestly frankly actually certainly indeed naturally obviously clearly truly surely exactly absolutely besides anyway
however again later earlier afterwards first tonight today yesterday night evening morning midnight
detective inspector officer sir madam ma'am
""".split())                                  # rows 9-12: spoken openers, interjections, times of day, forms of address (live Gemini)
_WORD = re.compile(r"[^\W\d_][\w'-]*")


def unresolved_names(text: str, name_index: dict[str, str]) -> list[str]:
    """The capitalised tokens in `text` that resolve to no entity at all: every known surface
    form (longest first) is masked out, and what is left capitalised must be a closed-class
    word. "Mr Fothergill" in a case without him is two such tokens."""
    masked = text.replace("\u2019", "'")
    for name in sorted(name_index, key=len, reverse=True):
        if name:
            masked = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", " ", masked, flags=re.IGNORECASE)
    return [t for t in _WORD.findall(masked) if t[0].isupper() and t.lower() not in _NON_ENTITY_WORDS]


def mentioned_entities(text: str, name_index: dict[str, str]) -> frozenset[str]:
    low = text.lower()
    return frozenset(eid for name, eid in name_index.items() if name and name in low)


def lexical_guard(draft: Draft, case: Case, allowed_entity_ids: frozenset[str],
                   canary: str | None = None) -> list[str]:
    """§14.2(b): forbidden strings, the canary, and entities — a known entity outside the
    permitted set, or a name that resolves to no entity at all, in any segment kind."""
    violations: list[str] = []
    name_index = _name_index(case)
    for i, seg in enumerate(draft.segments):
        low = seg.text.lower()
        for bad in FORBIDDEN_VOCAB:
            if bad in low:
                violations.append(f"FORBIDDEN_VOCAB[{i}]:{bad}")
        if canary and canary.lower() in low:
            violations.append(f"CANARY_LEAK[{i}]")
        mentioned = mentioned_entities(seg.text, name_index)
        unknown = mentioned - allowed_entity_ids
        if unknown:
            violations.append(f"UNKNOWN_ENTITY[{i}]:{sorted(unknown)}")
        unresolved = unresolved_names(seg.text, name_index)
        if unresolved:
            violations.append(f"UNKNOWN_ENTITY[{i}]:{unresolved}")
    return violations


def slot_checks(draft: Draft, envelope: Envelope, case: Case, speaker: ActorId,
                 traceable_objects: frozenset[str] = frozenset()) -> list[str]:
    """§14.2(c): EVERY segment, regardless of `kind` (I-36) — a mislabelled `color`/`question`
    segment gets no exemption."""
    violations: list[str] = []
    name_index = _name_index(case)
    allowed_by_id = {c.id: c for c in envelope.allowed_claims}
    envelope_entities: set[str] = set()
    for c in envelope.allowed_claims:
        a, l, o, amb = entities(c.proposition)
        envelope_entities |= a | l | o | amb

    for i, seg in enumerate(draft.segments):
        mentioned = mentioned_entities(seg.text, name_index)
        if seg.kind == "assert":
            if not seg.claim_ids:
                violations.append(f"UNTAGGED_ASSERTION[{i}]")
                continue
            referenced = [allowed_by_id[cid] for cid in seg.claim_ids if cid in allowed_by_id]
            if len(referenced) != len(seg.claim_ids):
                violations.append(f"CLAIM_ID_NOT_IN_ENVELOPE[{i}]")
                continue
            allowed: set[str] = {speaker}
            for c in referenced:
                a, l, o, amb = entities(c.proposition)
                allowed |= a | l | o | amb
            extra = mentioned - allowed
            if extra:
                violations.append(f"SLOT_MISMATCH[{i}]:{sorted(extra)}")
            # §14.2(c): "a different known ... time phrase" — only the clock times the referenced
            # claims themselves render may appear, and no other time expression at all.
            allowed_times = {render_time(t) for c in referenced
                             for t in (getattr(c.proposition, "interval", None) or ())}
            if set(_CLOCK.findall(seg.text)) - allowed_times or _TIME_WORDS.search(seg.text):
                violations.append(f"TIME_SLOT_MISMATCH[{i}]")
        elif seg.kind == "color":
            if seg.claim_ids:
                violations.append(f"COLOR_CARRIES_CONTENT[{i}]:has_claim_ids")
            if mentioned - {speaker}:
                violations.append(f"COLOR_CARRIES_CONTENT[{i}]:entity")
            if _TIME_RE.search(seg.text):
                violations.append(f"COLOR_CARRIES_CONTENT[{i}]:time")
            if mentioned & traceable_objects:
                violations.append(f"COLOR_CARRIES_CONTENT[{i}]:object")
        elif seg.kind == "question":
            if seg.claim_ids:
                violations.append(f"QUESTION_HAS_CLAIMS[{i}]")
            if mentioned - {speaker}:
                violations.append(f"QUESTION_CARRIES_CONTENT[{i}]")
        elif seg.kind == "nonverbal":
            if mentioned - envelope_entities - {speaker}:
                violations.append(f"NONVERBAL_LEAK[{i}]")  # I-24
    return violations


def verify_segments(draft: Draft, envelope: Envelope, case: Case) -> list[str]:
    """§14.2(d)'s role, played deterministically (module docstring): each `assert` segment's
    text must equal the deterministic re-render of every claim it references — TemplateLLM
    is faithful by construction, so this only fires on a hand-built/mutant `Draft`."""
    violations: list[str] = []
    allowed_by_id = {c.id: c for c in envelope.allowed_claims}
    for i, seg in enumerate(draft.segments):
        if seg.kind != "assert":
            continue
        for cid in seg.claim_ids:
            claim = allowed_by_id.get(cid)
            if claim is None:
                continue
            expected = render_claim(claim, case)
            if expected not in seg.text:
                violations.append(f"ASSERTS_NOT_EXACTLY[{i}]:{cid}")
    return violations


# The slot naming whose presence/action/perception/attitude a proposition is. A character has
# `Participated`/`Witnessed` provenance for a TRUE proposition about themselves (§6.2), which is
# the "provenance" half of §14.2(e)'s "computed lazily via FactIndex + provenance".
_FIRST_PERSON = {"At": "actor", "NotAt": "actor", "Moved": "actor", "Did": "actor", "DidNot": "actor",
                 "Has": "actor", "State": "actor", "Motive": "actor", "Saw": "observer",
                 "Heard": "observer", "Attitude": "a", "Said": "speaker"}

_FACT_INDEX: dict[int, tuple[Case, FactIndex]] = {}


def fact_index(case: Case) -> FactIndex:
    """`FactIndex` derives perception eagerly (~0.1 s on Vance): built once per sealed case
    (I-4), and only when a claim reaches the truth test at all.
    ponytail: unbounded per-process cache keyed by case identity; one case per session."""
    hit = _FACT_INDEX.get(id(case))
    if hit is None or hit[0] is not case:
        hit = _FACT_INDEX[id(case)] = (case, FactIndex(case))
    return hit[1]


def _asserted(claims: Iterable, *groups: Iterable[Proposition]) -> list[tuple[Proposition, bool]]:
    """(proposition, negated) for every claim and bare proposition the renderer can see."""
    return ([(c.proposition, c.modality == "negated") for c in claims]
            + [(p, False) for group in groups for p in group])


def leak_violations(visible: Iterable[tuple[Proposition, bool]], plan: ResponsePlan, speaker: ActorId,
                    ctx: DecisionContext) -> list[str]:
    """§14.2(e), all three rules, over every proposition the renderer can see:

    - no `Solution` unless act = CONFESSION;
    - no member of the speaker's unknowable set — a TRUE fact (`FactIndex`) the speaker has no
      provenance for (knowledge entry, own belief, or being its subject) — unless the plan
      authorizes it by listing it in `authorized_reveals` (SLIP/CONCESSION/CONFESSION);
    - no other character's protected fact unless the speaker has access to it. Authorization
      does not lift this one: a plan may reveal the speaker's secrets, never someone else's.

    Checked on what is ASSERTED: a `negated` claim asserts the negation (true when `p` is
    false), and a `Said` proposition's reported content is checked in its own right — being the
    one who spoke gives no access to what was said."""
    violations: list[str] = []
    knowledge = ctx.knowledge_with_overlay
    authorized = set(plan.authorized_reveals)
    pending, seen = list(visible), set()
    while pending:
        p, negated = pending.pop(0)
        if (p, negated) in seen:
            continue
        seen.add((p, negated))
        if p.kind == "Said":
            pending.append((p.proposition, False))
        if p.kind == "Solution" and plan.act != "CONFESSION":
            violations.append("SOLUTION_LEAK")
        slot = _FIRST_PERSON.get(p.kind)
        if ((slot is not None and getattr(p, slot) == speaker)
                or knowledge.find(speaker, p) is not None or ctx.beliefs.belief_for(speaker, p) is not None):
            continue
        if any(s.owner != speaker and s.is_protected(p) for s in ctx.secrets.all()):
            violations.append(f"FOREIGN_PROTECTED:{p.kind}")
        if p not in authorized and fact_index(ctx.case).truth_value(p) is (not negated):
            violations.append(f"UNKNOWABLE_CLAIM:{p.kind}")
    return list(dict.fromkeys(violations))


def leak_check(draft: Draft, plan: ResponsePlan, envelope: Envelope, speaker: ActorId,
               ctx: DecisionContext) -> list[str]:
    """§14.2(e): every referenced claim id must be one the envelope actually allowed, and every
    proposition the renderer can see (plan claims, frame padding, reveals, public facts) must
    pass `leak_violations` — not only the plan's own claims."""
    violations: list[str] = []
    allowed_ids = {c.id for c in envelope.allowed_claims}
    for i, seg in enumerate(draft.segments):
        for cid in seg.claim_ids:
            if cid not in allowed_ids:
                violations.append(f"UNAUTHORIZED_CLAIM[{i}]:{cid}")
    visible = _asserted((*plan.claims, *envelope.allowed_claims))
    visible += _asserted((), plan.authorized_reveals, envelope.authorized_reveals, envelope.persona.public_facts)
    violations += leak_violations(visible, plan, speaker, ctx)
    return violations


# Every field the renderer can receive, and nothing else. `audit_envelope` fails closed on any
# field it has no rule for, so a slot added later cannot reach the LLM unaudited.
_AUDITED_SCHEMA = {
    Envelope: {"persona", "delivery", "allowed_claims", "authorized_reveals", "digest_text",
               "retrieved_statements", "recent_exchange", "query_text"},
    EnvelopeClaim: {"id", "proposition", "modality", "confidence"},
    PersonaSlot: {"voice", "public_facts"},
    VoiceSpec: {"voice_register", "idiom", "tics"},
    DeliveryDirective: {"tone", "notes"},
}


def _schema_fields(model) -> set[str]:
    return set(getattr(model, "model_fields", None) or {f.name for f in fields(model)})


def audit_envelope(envelope: Envelope, plan: ResponsePlan, frame: tuple[Claim, ...],
                    digest: ConversationDigest, speaker: ActorId, ctx: DecisionContext) -> list[str]:
    """§21.2 at the boundary itself, run BEFORE any renderer sees the envelope. Each field is
    checked against the one source it may come from:

    - `allowed_claims`/`authorized_reveals`: exactly the plan and its frame, projected (I-1),
      and every proposition in them, and in `persona.public_facts`, passes §14.2(e);
    - `digest_text`: the deterministic render of THIS speaker's digest, whose presented items
      the player has discovered and whose standing claims are the speaker's own;
    - `retrieved_statements`/`recent_exchange`: verbatim text the speaker committed — never
      another character's statement;
    - persona/delivery strings: may name only the speaker and entities the envelope's claims
      already carry (the nonverbal rule, I-24 — §10.3's own delivery example names a person);
    - `query_text`: the player's own words — untrusted input, not engine state (ingress is §22.2
      stage 0, review finding I-16), so it cannot carry hidden state out.
    Any violation fails the turn closed (I-15)."""
    parts = (envelope, envelope.persona, envelope.persona.voice, envelope.delivery, *envelope.allowed_claims)
    if any(_AUDITED_SCHEMA.get(type(o)) != _schema_fields(type(o)) for o in parts):
        return ["ENVELOPE_SCHEMA_UNAUDITED"]  # a subclass, or a field added without a rule
    violations: list[str] = []
    if envelope.allowed_claims != tuple(EnvelopeClaim.of(c) for c in (*plan.claims, *frame)):
        violations.append("ENVELOPE_CLAIMS_NOT_PLAN")
    if envelope.authorized_reveals != plan.authorized_reveals:
        violations.append("ENVELOPE_REVEALS_NOT_PLAN")
    violations += leak_violations(_asserted(envelope.allowed_claims, envelope.authorized_reveals,
                                            envelope.persona.public_facts), plan, speaker, ctx)

    own_claims = {c.id for s in ctx.statements.standing_for_speaker(speaker) for c in s.claims}
    labels = evidence_labels(ctx.evidence, ctx.case, ctx.discovery.known_evidence)
    if (digest.character != speaker or envelope.digest_text != render_digest(digest, labels)
            or not set(digest.standing_claims) <= own_claims):
        violations.append("ENVELOPE_DIGEST_NOT_SPEAKERS")
    if not set(digest.evidence_presented) <= ctx.discovery.known_evidence:
        violations.append("ENVELOPE_UNDISCOVERED_EVIDENCE")
    own_text = {s.text for s in ctx.statements.for_speaker(speaker)}
    if any(t not in own_text for t in (*envelope.retrieved_statements, *envelope.recent_exchange)):
        violations.append("ENVELOPE_FOREIGN_TEXT")
    names = _name_index(ctx.case)
    carried = {speaker}
    for c in envelope.allowed_claims:
        carried.update(*entities(c.proposition))
    voice, delivery = envelope.persona.voice, envelope.delivery
    style = (voice.voice_register, *voice.idiom, *voice.tics, delivery.tone, *delivery.notes)
    if any(mentioned_entities(t, names) - carried for t in style):
        violations.append("ENVELOPE_STYLE_CARRIES_CONTENT")
    return violations


def consistency_check(plan: ResponsePlan, speaker: ActorId, statements: StatementStore,
                       case: Case, retracting: frozenset[str] = frozenset()) -> list[str]:
    """§14.2(f): pairwise contradiction with standing claims, AND joint feasibility (I-28).
    Waived only "when plan.act ∈ {CONCESSION, CORRECTION} and the contradicted claims ⊆
    plan.retracts": such a plan is checked against the standing claims it does NOT retract
    this turn (`retracting`, statement ids) — never waived wholesale."""
    violations: list[str] = []
    excluded = retracting if plan.act in RETRACTION_EXEMPT_ACTS else frozenset()
    standing = [c for s in statements.standing_for_speaker(speaker) if s.id not in excluded for c in s.claims]
    for new_c in plan.claims:
        for old_c in standing:
            if contradiction(new_c.proposition, old_c.proposition, case=case) is not None:
                violations.append(f"CONTRADICTS_PRIOR:{old_c.id}")
    feas_claims = [FeasClaim(id=c.id, proposition=c.proposition) for c in (*standing, *plan.claims)]
    if not feasible(case, feas_claims).ok:
        violations.append("JOINTLY_INFEASIBLE")
    return violations


def modality_check(plan: ResponsePlan) -> list[str]:
    """§14.2(g)."""
    if plan.act == "HYPOTHETICAL" and any(c.modality != "hypothetical" for c in plan.claims):
        return ["HYPOTHETICAL_STATED_AS_ACTUAL"]
    return []


def _fallback_text(plan: ResponsePlan, case: Case) -> str:
    """§14.3's deterministic voice-variant render: the same dull template family
    `TemplateLLM` already uses, built directly from the plan (bypassing the draft
    entirely) — "producing dull but valid speech"."""
    return " ".join(render_claim(c, case) for c in plan.claims) or "..."


def length_band(n_chars: int) -> int:
    return sum(n_chars >= edge for edge in LENGTH_EDGES)


def canonical_text(envelope: Envelope, case: Case) -> str:
    """What the renderer is asked to express, in the dull template family (§14.3)."""
    return " ".join(render_claim(c, case) for c in envelope.allowed_claims) or "..."


def length_violations(draft: Draft, envelope: Envelope, case: Case) -> list[str]:
    """I-42/§22.3: the utterance's length band must equal the band of the canonical rendering.
    That rendering depends on the claims alone, so a LIE and a TRUTH about the same proposition
    are held to the same band — the renderer cannot make deception audible in length."""
    got = length_band(len(" ".join(seg.text for seg in draft.segments) or "..."))
    want = length_band(len(canonical_text(envelope, case)))
    return [f"LENGTH_BAND[{got}!={want}]"] if got != want else []


def prompt_deny_tokens(ctx: DecisionContext) -> frozenset[str]:
    """Engine identifiers that must never reach a renderer: secret ids, ids of evidence the
    player has not discovered, and act names. Used only to CHECK a serialized prompt — never
    given to the renderer (ADR-8: no deny-lists in prompts)."""
    return frozenset({s.id for s in ctx.secrets.all()}
                     | {e.id for e in ctx.evidence.all() if e.id not in ctx.discovery.known_evidence}
                     | set(ACT_TABLE))


def internal_tokens(ctx: DecisionContext, envelope: Envelope) -> frozenset[str]:
    """What must not surface in SPOKEN text: the prompt-side set plus this turn's claim ids and
    every evidence and statement id (handles for the notebook, never things a character says)."""
    return (prompt_deny_tokens(ctx) | {c.id for c in envelope.allowed_claims}
            | {e.id for e in ctx.evidence.all()} | {s.id for s in ctx.statements.all()})


def leaked_tokens(text: str, tokens: Iterable[str]) -> list[str]:
    """Tokens present as whole words. Case-sensitive: `LIE` (an act) is not `lie` (a word)."""
    return sorted(t for t in tokens if t and re.search(rf"(?<![\w]){re.escape(t)}(?![\w])", text))


def omission_violations(draft: Draft, plan: ResponsePlan) -> list[str]:
    """The claims a turn commits are the plan's, so a draft must voice every one of them. A
    renderer that drops a claim would otherwise decide what the ledger records (I-2, I-22)."""
    voiced = {cid for seg in draft.segments if seg.kind == "assert" for cid in seg.claim_ids}
    return [f"PLAN_CLAIM_OMITTED:{c.id}" for c in plan.claims if c.id not in voiced]


def disclosure_violations(draft: Draft, plan: ResponsePlan) -> list[str]:
    violations: list[str] = []
    for i, seg in enumerate(draft.segments):
        if plan.act != "CONFESSION" and _CONFESSES.search(seg.text):
            violations.append(f"SELF_DISCLOSURE[{i}]:confession")
        if plan.act not in ("CONFESSION", "CONCESSION", "CORRECTION") and _LIE_TELLS.search(seg.text):
            violations.append(f"SELF_DISCLOSURE[{i}]:lie_tell")
    return violations


def internal_token_violations(draft: Draft, tokens: frozenset[str]) -> list[str]:
    violations: list[str] = []
    for i, seg in enumerate(draft.segments):
        low = seg.text.lower()
        hits = leaked_tokens(seg.text, tokens) + [w for w in ENGINE_VOCAB if w in low]
        if hits:
            violations.append(f"INTERNAL_TOKEN_LEAK[{i}]:{hits}")
    return violations


def validate_draft(draft: Draft, envelope: Envelope, plan: ResponsePlan, speaker: ActorId,
                    case: Case, statements: StatementStore, *, ctx: DecisionContext,
                    allowed_entity_ids: frozenset[str] = frozenset(),
                    traceable_objects: frozenset[str] = frozenset(),
                    canary: str | None = None,
                    retracting: frozenset[str] = frozenset(),
                    verify: Callable[[Draft, Envelope, Case], list[str]] = verify_segments) -> ValidationResult:
    """The full §14.1 pipeline, run once (`llm.render` owns the repair loop around it). `verify`
    is check (d): the deterministic re-render for `TemplateLLM`, an LLM verifier for a real model.
    It runs LAST and only when every deterministic check passed (§14.2(c): a mislabelled draft
    "fails before any LLM sees it"), so a verifier that raises can only fail a draft that already
    survived everything else. Two outcomes on failure, never a third:

    - only `DRAFT_LEVEL_CODES` violations: the renderer failed, the plan did not — the
      deterministic fallback speaks the plan (§14.3; I-12: never the failed draft).
    - anything else: the PLAN failed. Rendering it differently cannot repair it, so the result
      is `rejected` with no text and no claim ids — nothing for any caller to commit (I-15)."""
    envelope_entities: set[str] = set()
    for c in envelope.allowed_claims:
        a, l, o, amb = entities(c.proposition)
        envelope_entities |= a | l | o | amb

    violations: list[str] = []
    violations += lexical_guard(draft, case, allowed_entity_ids | envelope_entities | {speaker}, canary)
    violations += slot_checks(draft, envelope, case, speaker, traceable_objects)
    violations += internal_token_violations(draft, internal_tokens(ctx, envelope))
    violations += length_violations(draft, envelope, case)
    violations += omission_violations(draft, plan)
    violations += disclosure_violations(draft, plan)
    violations += leak_check(draft, plan, envelope, speaker, ctx)
    violations += consistency_check(plan, speaker, statements, case, retracting)
    violations += modality_check(plan)
    if not violations:
        violations += verify(draft, envelope, case)

    claim_ids = tuple(dict.fromkeys(cid for seg in draft.segments for cid in seg.claim_ids))
    if not violations:
        text = " ".join(seg.text for seg in draft.segments) or "..."
        return ValidationResult(ok=True, text=text, claim_ids=claim_ids, violations=())

    if any(violation_code(v) not in DRAFT_LEVEL_CODES for v in violations):
        return ValidationResult(ok=False, text="", claim_ids=(), violations=tuple(violations), rejected=True)

    fallback_claim_ids = tuple(c.id for c in plan.claims)
    return ValidationResult(ok=False, text=_fallback_text(plan, case), claim_ids=fallback_claim_ids,
                             violations=tuple(violations), fallback=True)
