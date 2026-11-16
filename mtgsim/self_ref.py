"""Which object "it" means after an untargeted effect on the source.

The resolve loop (engine/stack.py) points ``prev`` at the source after an untargeted ``*_self`` effect, so
"Untap ~ and put a +1/+1 counter on it" counts the counter onto ~ (Grimgrin, Corpse-Born, #791). An explicit
"that creature" / "the creature" names the trigger's subject instead, which the source rule would lose:

    When another creature enters, sacrifice ~. If you do, ~ deals 4 damage to that creature.  (Flame-Kin War Scout)
    When a nonblack creature enters, sacrifice ~. If you do, destroy that creature.            (Grave Peril)

The parser shares one template for "it" and "that creature", so the wording is read here, on the sentence run
``_parse_effects`` matched: such a ``*_self`` effect gets ``data["keep_ctx"]`` and the loop keeps ``prev``.
"""
from __future__ import annotations

import dataclasses
import re

_EXPLICIT = re.compile(r"\b(?:that|the) creature\b", re.I)


def keep_context(text: str, effects: list) -> None:
    """Mark the untargeted ``*_self`` effects of ``text`` whose later reference is an explicit "that creature"."""
    if not _EXPLICIT.search(text):
        return
    for i, eff in enumerate(effects):
        if eff.kind.endswith("_self") and eff.target in ("none", "self"):
            effects[i] = dataclasses.replace(eff, data={**eff.data, "keep_ctx": True})
