"""A colour chosen as a permanent enters, and the statics that read it:

    As this land enters, choose a color other than black. / {T}: Add {B} or one mana of the chosen color.  (Gates)
    ~ enters tapped. As it enters, choose a color other than red.                          (Thriving lands)
    As ~ enters, choose a color. / ~ has protection from the chosen color.                 (Voice of All)

The choice is made by ``choose`` (from ``Game.enter_battlefield``) and kept as ``Permanent.chosen_color``. The
permanent then makes mana only through its own mana lines: the colours its "Add {C}" text names plus the chosen
colour when a line says "mana of the chosen color" (before this, a choose-a-colour card such as Iona tapped for
the chosen colour). "Protection from the chosen color" becomes that keyword on the permanent's card. The AI
picks the opponent's main colour for protection and the colour its own cards need most otherwise.
"""
from __future__ import annotations

import dataclasses
import re

_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_NAMES = {v: k for k, v in _COLORS.items()}
_OTHER = re.compile(r"(?:~ enters tapped\. )?As (?:~|it|this \w+) enters, choose a color other than "
                    r"(white|blue|black|red|green)\.")
_PROTECTION = "~ has protection from the chosen color."


def parse_line(line: str, st) -> bool:
    m = _OTHER.fullmatch(line)
    if m:
        st.extra["choose_type"] = "color_other:" + _COLORS[m[1]]
        if line.startswith("~ enters tapped"):
            st.enters_tapped = True
        return True
    if line == _PROTECTION and st.extra.get("choose_type") == "basic_land":
        st.extra.setdefault("advanced_rules", {})["chosen_protection"] = True
        return True
    return False


def _own_need(game, p, exclude=""):
    from .engine.policy import choose_color
    need = {col: sum(c.mana_cost.get(col, 0) for c in p.hand + p.library) for col in _NAMES if col != exclude}
    if not any(need.values()):
        return choose_color(game, p) if exclude != choose_color(game, p) else next(c for c in _NAMES if c != exclude)
    return max(need, key=need.get)


def _theirs(game, p):
    from .protection import choose_color
    return _COLORS[choose_color(game, p, None).rsplit(" ", 1)[1]]


def choose(game, p, perm, card):
    """Game.enter_battlefield, for a card that chooses a colour as it enters."""
    kind = card.choose_type
    exclude = kind.partition(":")[2] if kind.startswith("color_other:") else ""
    protect = card.advanced_rules.get("chosen_protection")
    color = _theirs(game, p) if protect else _own_need(game, p, exclude)
    perm.chosen_color = color
    oracle = card.oracle or ""
    produces = set(re.findall(r"Add \{([WUBRGC])\}", oracle))
    if exclude:
        produces |= set(card.produces)
    if "mana of the chosen color" in oracle:
        produces.add(color)
    keywords = card.keywords | {f"protection from {_NAMES[color]}"} if protect else card.keywords
    perm.card = dataclasses.replace(card, produces=frozenset(produces), keywords=frozenset(keywords))
    game.log(f"chooses {_NAMES[color]} for {card.name}", p)
