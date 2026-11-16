"""'Another target creature you control' (#809): the source can't be that target.

    When this creature enters, put a +1/+1 counter on another target creature you control.   (Scuttling Sentinel)
    Another target creature you control gains indestructible until end of turn.                    (Selfless Savior)

Several templates read "another target creature you control" as a plain creature-you-control target and drop the
"another". When it is the sentence's first target, "another" means only "other than this object" (CR 115.3: it can
also exclude earlier targets of the same ability, but there are none yet), which is exactly what the "... other than
~" wording records (``other_than_source``) and the engine enforces. Later targets in the same sentence keep their own
template ("another" there also excludes the earlier target).
"""
from __future__ import annotations

import re

def _rewrite(m):
    """The sentence with "other than ~", if that wording parses fully; else the sentence as printed (some shapes
    have no "other than ~" template: those keep their own reading)."""
    from .cards.parse import _parse_effects
    new = f"{m[1]}target creature you control other than ~{m[2]}"
    effects, bad = _parse_effects(new[0].upper() + new[1:] if new else new)
    return new if effects and not bad else m[0]


SUBS = [
    (re.compile(r"(?:^|(?<=\. ))((?:(?!\btarget\b)[^.])*?)\banother target creature you control\b([^.]*\.?)", re.I),
     _rewrite),
]
