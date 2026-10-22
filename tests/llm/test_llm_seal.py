"""I-19 (T: "Voice spec containing a protected phrase -> seal refused") and the deny-set compiler."""
from __future__ import annotations

from eidolon.llm.seal import compile_deny_set, guard_text, voice_violations
from eidolon.minds.character import VoiceSpec
from tests.llm.llm_helpers import DAVID, MARGARET, build_initial_state

STATE = build_initial_state()


def test_deny_set_holds_other_peoples_protected_facts_and_the_objects_they_name():
    deny = compile_deny_set(STATE.secrets, STATE.case, DAVID)
    assert "i was in margaret's room from 00:30 until 01:30." in deny          # Margaret's protected alibi, rendered
    assert not any("i was in the library" in p for p in deny)                    # David's own protected facts are voiced by his layers
    for_margaret = compile_deny_set(STATE.secrets, STATE.case, MARGARET)
    assert "a drinking glass" in for_margaret                                    # the object David's protected fact names


def test_a_voice_spec_containing_a_protected_phrase_is_refused():
    deny = compile_deny_set(STATE.secrets, STATE.case, MARGARET)
    bad = VoiceSpec(voice_register="dry", idiom=("never touches a drinking glass without wiping it",), tics=("hm",))
    assert voice_violations(bad, deny) == ["SEAL_PROTECTED_PHRASE:a drinking glass"]
    assert voice_violations(VoiceSpec(voice_register="dry", idiom=("says 'well then'",), tics=("hm",)), deny) == []


def test_guard_text_is_case_insensitive_and_reports_every_phrase():
    assert guard_text("A Drinking Glass and A BRONZE BOOKEND", {"a drinking glass", "a bronze bookend", "x"}) == [
        "SEAL_PROTECTED_PHRASE:a bronze bookend", "SEAL_PROTECTED_PHRASE:a drinking glass"]
