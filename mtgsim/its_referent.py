"""'its' in a trigger body whose head is about the card itself (#535, part of #313).

    When this creature dies, create a number of tapped Treasure tokens equal to its power.        (Goldvein Hydra)
    Whenever this creature enters or attacks, create a number of 1/1 ... tokens equal to its power.  (Threefold
                                                                                                  Thunderhulk)
    When Nadier leaves the battlefield, create a number of 1/1 green Elf Warrior creature tokens equal to its power.

The where-X rule reads "its power" as the source's (``("stat", "self", ...)``), which is only right when "its" is
the card the head names. The rewrite therefore runs on the whole sentence, head included, and only for heads whose
subject is the card itself ("~", "this creature", "this permanent"). A "dies"/"leaves" head reads the card's last
known power (the permanent object keeps its counters and pumps when it leaves).
"""
from __future__ import annotations

import re

_HEAD = (r"(when(?:ever)? (?:~|this creature|this permanent) (?:dies|enters|attacks|blocks|enters or attacks|"
         r"attacks or blocks|leaves the battlefield|is put into a graveyard from the battlefield))")

_CREATE = re.compile(_HEAD + r", create a number of ([^.]+? tokens?) equal to its (power|toughness)\.", re.I)


def rewrite(text: str) -> str:
    """Card-text hook (cards.parse): runs while the trigger head is still attached to its body."""
    return _CREATE.sub(lambda m: f"{m[1]}, create X {m[2]}, where X is ~'s {m[3].lower()}.", text)
