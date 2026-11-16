"""Put "it" into its owner's library at a position (#628):

    When this creature dies, put it on top of its owner's library.                          (Dark Revenant)
    When this creature dies, put it on the bottom of its owner's library.                   (Fell Horseman)
    When this creature dies, you may put it on your choice of the top or bottom of its owner's library. (Arashin Sovereign)
    When Gandalf dies, you may put it into its owner's library fifth from the top.          (Gandalf, White Rider)
    Whenever a creature you control dies, put it on the bottom of its owner's library.      (The Cauldron of Eternity)

Only trigger lines about their own source are read ("When ~ ..."), and "it" is that source. Still on the battlefield,
it goes there directly (Game.put_in_library); already gone (a dies / put-into-a-graveyard / put-into-exile trigger),
the card it became is taken from its owner's graveyard or exile, if it is still there (CR 400.7), as the
"return it to its owner's hand" triggers do. A token is not moved.

"You may": taken when the card is yours (a card back in your library); a card an opponent owns stays where it is.
"Your choice of the top or bottom": the top when the card is yours, the bottom otherwise.
"""
from __future__ import annotations

import re

_NTH = {"second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7}
_SELF_HEAD = re.compile(r"(?:When|Whenever) (?:~|this (?:creature|permanent|artifact|enchantment|card|Vehicle))[ ,]", re.I)
_PUT_IT = re.compile(r"\b(?P<may>you may )?put it (?:(?P<end>on top of|on the bottom of|on your choice of the top or "
                     r"bottom of) its owner's library|into (?:its owner's|your) library (?P<n>\w+) from the top)", re.I)


def rewrite(line: str):
    """(line, refused). A trigger line about its own source ("When ~ dies, put it on top of its owner's library")
    gets the private sentence "OWNERLIB <where> [may]" for the move; with any other head ("Whenever a creature you
    control dies", "Whenever you cast a spell", "At the beginning of ...") "it" isn't the source (ally_dies carries
    no dying creature, a cast trigger's "it" is the spell), so the line is refused."""
    m = _PUT_IT.search(line)
    if m is None or not re.match(r"(?:When|Whenever|At) ", line):
        return line, False
    if ", " not in line or m.start() != line.index(", ") + 2:
        return line, False      # "it" after another effect of the body: not this rule's
    if not _SELF_HEAD.match(line):
        return line, True
    if m["end"]:
        end = m["end"].lower()
        where = "top" if end == "on top of" else "bottom" if end == "on the bottom of" else "choice"
    elif m["n"].lower() in _NTH:
        where = str(_NTH[m["n"].lower()])
    else:
        return line, False
    marker = f"OWNERLIB {where}{' may' if m['may'] else ''}"
    return line[:m.start()] + marker + line[m.end():], False


def _put(m):
    where = m[1].lower()
    from .cards.model import Effect      # deferred: mtgsim.cards imports this module (tests.test_imports)
    return Effect("owner_library", target="none", data={"where": int(where) if where.isdigit() else where,
                                                       "may": bool(m[2])})


EFFECT_PATTERNS = [(r"ownerlib (top|bottom|choice|\d)( may)?", _put)]


def resolve(game, p, eff, target, item):
    """The owner_library kind (engine/kinds/cards.py)."""
    from .engine.state import Permanent
    perm = item.source if item is not None and isinstance(item.source, Permanent) else None
    if perm is None:
        return
    mine = perm.owner is p
    if eff.data.get("may") and not mine:
        return
    where = eff.data["where"]
    if where == "choice":
        where = "top" if mine else "bottom"
    if perm in perm.controller.battlefield:
        name = perm.card.name
        if game.put_in_library(perm, where):
            game.log(f"{name} goes into its owner's library ({where})", p)
        return
    card = getattr(perm, "front", None)
    dest = getattr(perm, "last_destination", None)
    zone = perm.owner.graveyard if dest == "graveyard" else perm.owner.exile if dest == "exile" else None
    if zone is None or card is None or card.is_token or not any(c is card for c in zone):
        return
    library = perm.owner.library
    game.move_card(card, zone, library, reason="owner_library")          # appended: the top
    if where != "top" and where != 1:
        list.remove(library, card)                                        # a move inside the library
        index = 0 if where == "bottom" else max(0, len(library) - where + 1)
        list.insert(library, index, card)
    game.log(f"{card.name} goes into its owner's library ({where})", p)
