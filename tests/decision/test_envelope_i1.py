"""I-1, structural: `props(envelope(plan, frame)) <= speakable(plan, frame)` for ANY plan —
proved over the typed `Envelope`, never by scanning rendered prompt text (§2.2's own
wording). Hypothesis-driven per §28.3's "Random ResponsePlans -> props(envelope(plan)) ⊆
speakable(plan)".
"""
from __future__ import annotations

from hypothesis import given, strategies as st

from eidolon.decision.claims import Claim
from eidolon.decision.digest import ConversationDigest
from eidolon.decision.envelope import PersonaSlot, build_envelope, props, speakable
from eidolon.decision.strategy import DeliveryDirective, ResponsePlan
from eidolon.world.propositions import At

ACTORS = ["David", "Elena", "Margaret"]
LOCATIONS = ["Hall", "Study", "Kitchen", "Library"]


@st.composite
def propositions(draw):
    actor = draw(st.sampled_from(ACTORS))
    location = draw(st.sampled_from(LOCATIONS))
    start = draw(st.integers(min_value=0, max_value=100))
    end = start + draw(st.integers(min_value=1, max_value=20))
    return At(actor=actor, location=location, interval=(start, end))


@st.composite
def claims(draw, prefix="c"):
    idx = draw(st.integers(min_value=0, max_value=10_000))
    return Claim(id=f"{prefix}{idx}", proposition=draw(propositions()),
                 sincerity=draw(st.sampled_from(["truthful", "sincere_false", "deceptive"])),
                 source=draw(st.sampled_from(["plan", "frame", "incidental", "slip"])))


@st.composite
def plans(draw):
    n = draw(st.integers(min_value=0, max_value=4))
    plan_claims = tuple(draw(claims("p")) for _ in range(n))
    n_reveal = draw(st.integers(min_value=0, max_value=2))
    reveals = tuple(draw(propositions()) for _ in range(n_reveal))
    act = draw(st.sampled_from(["TRUTH", "LIE", "VAGUE", "CONCESSION", "SLIP"]))
    return ResponsePlan(act=act, claims=plan_claims, authorized_reveals=reveals,
                         delivery=DeliveryDirective(tone="neutral"))


@given(plan=plans(), frame=st.lists(claims("f"), max_size=3).map(tuple))
def test_i1_structural_containment(plan, frame):
    digest = ConversationDigest(character="David", turns=1)
    envelope = build_envelope(plan, persona=PersonaSlot(), digest=digest, frame=frame)
    assert props(envelope) <= speakable(plan, frame)


def test_i1_would_fail_if_a_rogue_fact_leaked_sanity_check():
    """The property is not vacuous: adding a proposition the plan never authorized breaks
    containment, so the assertion above is actually testing something."""
    digest = ConversationDigest(character="David", turns=1)
    plan = ResponsePlan(act="LIE", claims=(), delivery=DeliveryDirective())
    envelope = build_envelope(plan, persona=PersonaSlot(), digest=digest)
    rogue = At(actor="David", location="Study", interval=(76, 77))
    leaked = envelope.model_copy(update={"authorized_reveals": (rogue,)})
    assert not (props(leaked) <= speakable(plan))
