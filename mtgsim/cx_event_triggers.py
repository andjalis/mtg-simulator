"""Trigger wordings the base table lacks. Death triggers that count the source itself: "Whenever ~ or another creature dies" (Blood Artist) and
"Whenever ~ or another Zombie you control dies" (Archghoul of Thraben); packs
("Whenever ~ and at least two other creatures attack", Boros Elite); and "Whenever ~ becomes the target of a spell or
ability an opponent controls" (Mossdog, Old Fat Spider; the event is fired from Game.check_ward)."""
from __future__ import annotations

TRIGGERS = [
    (r"Whenever ~ or another creature dies, (.+)", ("dies", "creature_dies")),
    (r"Whenever (~ or another) ([\w, -]+?) you control( with (?:a|an|one or more) (?:\+1/\+1 )?counters? on it)? dies, "
     r"(.+)", ("ally_dies",)),
    (r"Whenever ~ and at least (one|two|three) other creatures? attack, (.+)", ("attacks",)),
    (r"Whenever ~ becomes the target of a spell or ability an opponent controls, (.+)", ("targeted_opp",)),
]
