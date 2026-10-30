"""Death triggers that count the source itself: "Whenever ~ or another creature dies" (Blood Artist) and
"Whenever ~ or another Zombie you control dies" (Archghoul of Thraben)."""
from __future__ import annotations

TRIGGERS = [
    (r"Whenever ~ or another creature dies, (.+)", ("dies", "creature_dies")),
    (r"Whenever (~ or another) ([\w, -]+?) you control( with (?:a|an|one or more) (?:\+1/\+1 )?counters? on it)? dies, "
     r"(.+)", ("ally_dies",)),
]
