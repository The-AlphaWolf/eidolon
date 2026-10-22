"""A save made by an earlier engine must keep loading (review NR-B1).

`store.initial_digest` binds everything `new_session` DERIVES from (case, seed) into a save's genesis (C-3), so any change to that
derivation — a personality weight, a voice, a memory — refuses every save made before it. That is the intended fail-closed
behaviour, but until a migrator exists (C-10) it bricks the player's games, and no other test notices: every persistence test
creates its save with the engine under test. This file is the save of record. It was created by the engine of 2026-10-22; if it
stops loading, the change that broke it needs a migrator (or must not change the derivation) — do not regenerate the fixture to
make this pass."""
from __future__ import annotations

import shutil
from pathlib import Path

from eidolon.store import Save

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "saves" / "golden_study_party_s4.db"
STATE_HASH = "152a5db9817c513b841180d4cdf3ac77d84f4ba5d6893b3058c2a0a0a84f74e3"


def test_a_save_made_by_an_earlier_engine_still_loads_and_replays_to_the_same_state(tmp_path):
    copy = tmp_path / FIXTURE.name                       # never open the fixture itself writable
    shutil.copyfile(FIXTURE, copy)
    s = Save.open(copy)
    try:
        assert s.state.turn_counter == 10 and s.last_seq == 38
        assert s.state_hash() == STATE_HASH
    finally:
        s.close()


def test_the_derived_voice_is_not_part_of_the_saved_world():
    """Voices are derived at render time (`decision.voice`); the session stores the legacy default, so a new voice table can
    never refuse a save."""
    from eidolon.decision.voice import DERIVED
    from eidolon.solve.session import default_personality
    assert default_personality("David", 7).voice == DERIVED
