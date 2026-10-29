"""The case file the player opens with: the setting, the victim, the cast, the house, how to play, and next-step hints.

Presentation only, and only the case's OPENING material (§20, I-47): the victim, where the body lies, every questionable
character, the house with its doors and what can be seen or heard from where, and the one way in from outside. Nothing
here reads the solution, the schedule, the evidence or a mind: the prose is authored per skeleton and fixed per NAME, so
two cases on one skeleton (different murderers, different evenings) open with the same file — checked by test. The hints
read only the player's notebook projection (`game.notebook`), so they can say nothing the player does not already hold.
"""
from __future__ import annotations

from .gen.skeletons import SKELETONS

# Per skeleton: the title, the opening narration ({victim}, {scene}, {way_in}, {clock_end} are filled in), the victim's
# line, one neutral line per cast NAME (nothing about where they were, whom they love or why they might kill), and one
# line per room (atmosphere only: no object, trace or log is described).
_STORIES = {
    "study_party": {
        "title": "Death in the Study",
        "intro": (
            "A mild night at {victim}'s house on the edge of town. He had asked a few people over for drinks: nothing "
            "grand: a housekeeper to see to the glasses, and the run of the house and the garden for everyone else.",
            "At some point in the evening, behind the closed door of {scene}, someone struck {victim} on the head. He was "
            "found there, dead.",
            "You arrive at {clock_end} on your notes' clock, which counts the evening from 00:00. Everyone is still in "
            "the house. Nobody saw it happen, or so they say.",
            "One person here is lying to save themselves. The others may lie too, about smaller things they would "
            "rather keep quiet. Find out who killed {victim}, and prove it.",
        ),
        "victim": "The host. Comfortably rich, sharp-tongued, with a long memory and few close friends. Any of his "
                  "guests might have had a reason; part of your job is finding whose reason was strong enough.",
        "people": {
            "Elena": "Runs the house. Knows every room, every door, and most of what goes on behind them.",
            "David": "An acquaintance of Harold's from his business days. Charming, and never short of an answer.",
            "Margaret": "A neighbour who has known Harold for twenty years. Observant and proud.",
            "Robert": "Harold's younger cousin, up from the city for the week. Easy company, easily bored.",
        },
        "rooms": {
            "Hall": "The middle of the house. Most rooms open off it, so anyone crossing the house passes through here.",
            "Study": "Harold's private room. The door is usually kept shut. This is where he was found.",
            "Library": "Tall shelves and deep chairs: a place to talk quietly, away from the others.",
            "Kitchen": "Warm, with a back door to the steps outside.",
            "BackSteps": "Stone steps behind the kitchen, down to the garden path. A quiet spot for a cigarette.",
            "Gazebo": "At the bottom of the garden, beside the gate to the lane.",
            "Room": "The guest room, made up for whoever stays the night.",
            "EXT": "The lane and the dark fields beyond the garden gate.",
        },
    },
    "manor_wing": {
        "title": "The East Wing",
        "intro": (
            "Late evening in the east wing of {victim}'s manor. A small gathering: a handful of guests, the "
            "housekeeper, a fire in the parlor and a good deal of wine.",
            "At some point in the evening, in {scene}, someone struck {victim} on the head. He was found there, dead.",
            "You arrive at {clock_end} on your notes' clock, which counts the evening from 00:00. The guests have been "
            "kept in the wing. Each of them is sure they had nothing to do with it.",
            "One of them is lying to save themselves. The others may lie too, about smaller things they would rather "
            "keep quiet. Find out who killed {victim}, and prove it.",
        ),
        "victim": "Master of the manor. Generous when it suited him and ruthless when it did not. Any of his guests "
                  "might have had a reason; part of your job is finding whose reason was strong enough.",
        "people": {
            "Beatrix": "Has kept the manor for years. Knows its routines, its keys and everyone's habits.",
            "Cormac": "Alistair's business partner, down from the city for the weekend.",
            "Delphine": "A painter Alistair had taken an interest in. Quiet, watchful.",
            "Emeric": "Alistair's nephew, lately home from abroad.",
            "Fiora": "An old friend of the family and a regular at Alistair's table.",
        },
        "rooms": {
            "Foyer": "The entrance hall of the wing. Most rooms open off it.",
            "Office": "Alistair's private office. This is where he was found.",
            "Parlor": "Sofas, a card table and the fire.",
            "Kitchen": "At the far end of the wing.",
            "Conservatory": "A glass room full of plants, between the parlor and the kitchen.",
            "Terrace": "A stone terrace with steps down to the grounds.",
            "Suite": "The guest suite, made up for whoever stays the night.",
            "EXT": "The grounds and the dark drive beyond the terrace steps.",
        },
    },
}

ROLES = {"housekeeper": "Housekeeper", "guest": "Guest"}

HOW_TO_PLAY = (
    ("Meet the cast", "Everyone alive in the house is a suspect. So is an outsider, but only if they could have got in."),
    ("Question people", "Start broad with “who was where”, then narrow it down by person, place and time. Every answer "
                        "goes into your notebook."),
    ("Search", "Search rooms and objects, trying each method. Whatever you find goes into your notebook as evidence."),
    ("Look for tensions", "When two things you hold cannot both be true, the notebook lists a tension. Someone is lying "
                          "or mistaken."),
    ("Confront", "Show someone a piece of evidence, or their own earlier statement. A lie does not survive the thing "
                 "that breaks it. The killer confesses only to real proof."),
    ("Theorise", "Write down theories. The notebook tells you what supports each one and what goes against it."),
    ("Accuse", "Say who, with what, where, when and why, and cite the evidence that rules everyone else out. You get "
               "one final accusation, and it closes the case."),
)


def case_label(case_name: str) -> str:
    """The new-game menu's line for a sealed case file, from its name (`<skeleton>_s<seed>`) and the skeleton."""
    skel_id = case_name.rsplit("_s", 1)[0]
    skel = SKELETONS.get(skel_id)
    if skel is None:
        return case_name
    return (f"{_STORIES.get(skel_id, {}).get('title', skel_id)}: {len(skel.cast)} suspects, {skel.difficulty} "
            f"({case_name})")


def _and(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def briefing(case, skeleton_id: str, clock_end: str) -> dict:
    """The case file. Reads the case's cast and house only, and the skeleton's public layout (murder room, way in)."""
    skel, story = SKELETONS.get(skeleton_id), _STORIES.get(skeleton_id, {})
    victims = [a.name for a in case.actors.values() if a.role == "victim"]
    victim = victims[0] if victims else "the victim"
    loc = lambda i: case.locations[i].name if i in case.locations else "?"
    scene = loc(skel.murder_loc) if skel else "a locked room"
    way_in = _and([loc(i) for i in skel.exterior]) if skel else "?"
    roles = dict(zip((n for n, _ in skel.cast), skel.roles)) if skel else {}
    fill = dict(victim=victim, scene=scene, way_in=way_in, clock_end=clock_end)
    intro = [p.format(**fill) for p in story.get("intro", ("{victim} is dead. Find out who killed them, and prove it.",))]
    intro.append(f"The only way into the grounds from outside is through {way_in}. If an outsider did this, they came "
                 "that way.")
    cast = [{"name": a.name, "role": ROLES.get(roles.get(a.name), "Guest"),
             "about": story.get("people", {}).get(a.name, "A guest of the house.")}
            for a in sorted(case.actors.values(), key=lambda a: a.name) if a.role != "victim"]
    rooms = []
    for i, place in sorted(case.locations.items(), key=lambda kv: kv[1].name):
        exits = sorted((f"{loc(e.b if e.a == i else e.a)} ({e.minutes} min)" for e in case.travel_edges if i in (e.a, e.b)))
        senses = [f"From here you can {'see into' if p.modality == 'sight' else 'hear'} {loc(p.perceives)}."
                  for p in case.perception_edges if p.observer_at == i]
        rooms.append({"id": i, "name": place.name, "about": story.get("rooms", {}).get(i, ""), "exits": exits,
                      "senses": senses})
    return {"title": story.get("title", "A Death in the House"), "intro": intro, "victim": victim,
            "victim_about": story.get("victim", ""), "scene": scene, "way_in": way_in, "cast": cast, "rooms": rooms,
            "steps": HOW_TO_PLAY}


def next_steps(v: dict, brief: dict) -> list[str]:
    """Hints from the notebook projection only: what the player has heard, found, visited and written down."""
    heard = {s["speaker"] for s in v["statements"]}
    silent = [p["name"] for p in v["people"] if p["name"] not in heard]
    tips = []
    if not v["statements"]:
        tips.append(f"Start by asking each of the {len(v['people'])} people about “who was where”. Their accounts are "
                    "the skeleton of the evening.")
    elif silent:
        tips.append(f"You have not heard anything from {_and(silent)} yet.")
    if not v["evidence"]:
        tips.append(f"Search {brief['scene']}, where {brief['victim']} was found, trying each method. Hard evidence "
                    "usually starts at the scene.")
    elif not v["tensions"]:
        tips.append("Show what you have found to the people it concerns (“Show them” on the question form), and ask "
                    "about the times it covers.")
    if v["tensions"]:
        n = len(v["tensions"])
        tips.append(f"Your notebook has {n} tension{'s' if n > 1 else ''}: things that cannot all be true. Show one side "
                    "to the person whose story it contradicts.")
    if not any(p["visited"] for p in v["places"] if p["name"] == brief["way_in"]):
        tips.append(f"Could it be an outsider? The only way in is through {brief['way_in']}. Go and search it.")
    if len(v["statements"]) >= 3 and not v["hypotheses"]:
        tips.append("Write a theory down, for example where you think someone was and when. The notebook will test it "
                    "against what you hold.")
    tips.append(f"Work out WHEN {brief['victim']} died, then who could not have been in {brief['scene']} at that time. "
                "Accuse when only one person is left, and cite the evidence that rules out the rest.")
    return tips
