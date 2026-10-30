"""Animate another land: "Target land you control becomes a 3/3 Elemental creature with
haste until end of turn. It's still a land." (Llanowar Loamspeaker, Embodiment of Fury,
Nissa of Shadowed Boughs).

The manland self-animations ("{X}: ~ becomes a N/N ... creature ... It's still a land.")
are face_lines.py patterns; these are the same effect aimed at another land — or at "it",
the land a previous effect targeted (Nissa's +1) — and become an ``animate_land`` effect.
The kind sets ``perm.animated`` (an "animate" Activated), so the land keeps being a land,
is a creature until end of turn, and the existing cleanup in turns.py clears it.
"""
from __future__ import annotations

import re

_KEYWORDS = ("flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|"
             "haste|hexproof|indestructible|menace|reach|defender|flash")
_WITH = (r"(?: with ((?:" + _KEYWORDS + r")(?:,? ?(?:and )?(?:" + _KEYWORDS + r"))*)?)?")
_UNTIL = r" until end of turn\. it's still a land\.?"


def _animate(m, target):
    from .cards import Effect
    kws = frozenset(k.strip().lower() for k in re.split(r",| and ", m[3] or "")
                    if k.strip().lower() in _KEYWORDS)
    return Effect("animate_land", int(m[1]), int(m[2]), target=target,
                  data={"selector": {"controller": "mine", "types_all": ["land"]},
                        "keywords": kws})


SUBS = [
    # "... you may have target land you control become a N/N ... creature [with kws]
    # until end of turn. It's still a land."
    (re.compile(r"(?:you may have |have )?target land you control becomes? an? "
                r"(\d+)/(\d+) [\w ]*? creature" + _WITH + _UNTIL, re.I),
     lambda m: f"ANIMLAND {m[1]} {m[2]} {m[3] or ''}."),
    # "... untap target land you control. You may have it become a N/N ... creature
    # [with kws] until end of turn. It's still a land." — "it" is the land just targeted.
    (re.compile(r"(?:you may have |have )?it becomes? an? "
                r"(\d+)/(\d+) [\w ]*? creature" + _WITH + _UNTIL, re.I),
     lambda m: f"ANIMLANDPREV {m[1]} {m[2]} {m[3] or ''}."),
]


EFFECT_PATTERNS = [
    (r"ANIMLAND (\d+) (\d+) ?(.*)", lambda m: _animate((m[0], m[1], m[2], m[3]), "permanent")),
    (r"ANIMLANDPREV (\d+) (\d+) ?(.*)", lambda m: _animate((m[0], m[1], m[2], m[3]), "prev")),
]
