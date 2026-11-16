"""#625: "Exile cards from the top of your library until you exile a nonland card. You may cast that card ..."

    Exile cards from the top of your library until you exile a nonland card. You may cast that card without paying
    its mana cost.                                                           (Wanda's Vision, Q, Nico Minoru)
    ... exile cards from the top of your library until you exile a nonland card. You may cast that card this turn.
    (also "You may play that card this turn.")                                (Territorial Bruntar, Exploratory Mission)

A SUB joins the two sentences into one marker, so the permission only ever lands on the card this exile found. The
``until_nonland`` kind exiles cards one at a time from the top of the controller's library until a nonland card
arrives (the lands stay in exile; with no nonland card the whole library ends up exiled). Then:

- ``free``: the controller may cast that card now, while the effect resolves, without paying its mana cost (cast
  from exile like a discovered card; the AI casts it whenever it legally can, otherwise it stays exiled);
- ``turn``: the card joins the controller's impulse cards until the end of this turn (cast it for its mana cost).
Other riders (an alternative cost, "if the spell's mana value is ...", "put it into your hand") stay unmatched.
"""
from __future__ import annotations

import re

_HEAD = r"exile cards from the top of your library until you exile a nonland card\. "
SUBS = [
    (re.compile(_HEAD + r"You may cast that card without paying its mana cost\.(?= |$|\n)", re.I),
     "exile until nonland free."),
    (re.compile(_HEAD + r"You may (?:cast|play) that card this turn\.(?= |$|\n)", re.I),
     "exile until nonland turn."),
]


def _build(m):
    from .cards.model import Effect
    return Effect("until_nonland", data={"then": m[1].lower()})


EFFECT_PATTERNS = [(r"exile until nonland (free|turn)", _build)]


def resolve(game, p, eff):
    found = None
    while p.library:
        card = game.move_card(p.library[-1], p.library, p.exile, reason="exile")
        if not card.is_land:
            found = card
            break
    if found is None:
        game.log("exiles their library without finding a nonland card", p)
        return
    game.log(f"exiles cards until {found.name}", p)
    if eff.data["then"] == "turn":
        p.impulse.append((found, game.turn))
        return
    from .cast_triggers import cast_exiled
    if found in p.exile and cast_exiled(game, p, found, "discover"):
        game.log(f"casts {found.name} without paying its mana cost", p)
