"""#643: "gains protection from [artifacts / colorless or from] the color of your choice" for any subject the grammar
reads (target permanent / creature or enchantment / Merfolk you control, ~, "artifact creatures you control").

    Target permanent you control gains protection from artifacts or from the color of your choice until end of turn.
    {T}: Another target creature you control gains protection from colorless or from the color of your choice ...

The keyword is protection.CHOICE ("protection_choice"), or "protection_choice|artifacts" / "...|colorless" when the
other quality may be chosen instead; cx_grammar.keyword_list asks ``keyword_list`` here, so the general verb readers
(grant to a target, to ~, to a group) accept it. The choice is made as the effect resolves (engine kinds.stats.grant
asks ``choose``): the alternative when the threat on the stack is an artifact / colourless, else the colour
protection.choose_color picks. "Protection from colorless" is protection_qualities' keyword (any colourless source).
"""
from __future__ import annotations

import re

from .protection import CHOICE

_RX = re.compile(r"protection from (?:(artifacts|colorless) or from )?the color of your choice", re.I)


def keyword_list(text: str):
    """[keyword] for the choice phrase, else None."""
    m = _RX.fullmatch(text.strip())
    if not m:
        return None
    return [CHOICE + ("|" + m[1].lower() if m[1] else "")]


def is_choice(keyword) -> bool:
    return isinstance(keyword, str) and keyword.split("|")[0] == CHOICE


def choose(game, p, target, keyword: str) -> str:
    """The protection keyword p picks for target."""
    from .protection import choose_color
    alt = keyword.split("|")[1] if "|" in keyword else ""
    if alt:
        opp = game.opponent(p)
        for item in reversed(game.stack):
            card = item.card or (item.source.card if item.source is not None else None)
            if item.controller is opp and card is not None:
                if alt == "artifacts" and card.is_artifact or alt == "colorless" and not card.colors:
                    return f"protection from {alt}"
                break
    return choose_color(game, p, target)
