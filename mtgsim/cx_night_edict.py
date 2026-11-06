"""Choose-then-destroy edicts: "Target opponent chooses a creature they control. Destroy that creature." (Imperial
Edict, Wei Assassins). The opponent picks their least valuable creature, as for a sacrifice edict, but it is
destroyed, so indestructible and regeneration apply."""
from __future__ import annotations

import re

SUBS = [
    (re.compile(r"target opponent chooses a creature they control\. destroy that creature\.", re.I),
     lambda m: "EDICT DESTROY 1."),
]


def _edict(m):
    from .cards.model import Effect
    return Effect("edict", 1, data={"destroy": True})


EFFECT_PATTERNS = [(r"edict destroy 1", _edict)]
