"""Grammar verb for a player returning a permanent of their own (#638): "<player> returns a <permanent> they control to
its owner's hand", chosen by that player on resolution.

    That player returns a permanent they control to its owner's hand.          (Blizzard Specter)
    That player returns a land they control to its owner's hand.               (Mana Breach)
    Target opponent returns a creature they control to its owner's hand.
    Defending player returns a nonland permanent they control to its owner's hand.

Any player subject the grammar reads ("that player", "target player", "target opponent", "defending player", "each
player", "each opponent") works: the grammar wraps the verb in ``cx_players`` and hands each named player to the
``bounce_choice`` kind (bounce_own.py), which returns that player's cheapest fitting permanent. The noun phrase is a
battlefield selector; a restriction it can't read, or "you control" (whose permanents?), leaves the sentence ignored.
"""
from __future__ import annotations

from .cx_grammar import Part, ai_value, verb


@verb(r"returns? (?:an?|one) (.+?) (?:they|that player) controls? to (?:its|their) owners?'s? hands?",
      heads=("return", "returns"), subjects=("player",))
def returns_own(m, clause):
    from .permanent_templates import selector
    if clause.duration or clause.subject.who == "you":
        return None         # "you" have bounce_own.py's template
    sel = selector(m[1])
    if not sel or "cx_desc" in sel or sel.get("controller") or sel.get("owner"):
        return None
    return [Part("bounce_choice", 1, 0, {"selector": dict(sel, controller="mine"), "who": "named"})]


@ai_value("bounce_choice")
def _value(game, me, eff, obj):
    """A named player returning their cheapest fitting permanent: half its value, good when it is the opponent's."""
    from .engine.policy import perm_value
    from .engine.state import Player
    from .permanent_templates import matches
    if not isinstance(obj, Player):
        return 0.0
    pool = [x for x in obj.battlefield if matches(game, x, eff.data["selector"], obj, None)]
    if not pool:
        return 0.0
    pick = min(pool, key=lambda x: (not (x.card.is_land and x.tapped), perm_value(x)))
    worth = 0.5 * perm_value(pick) + 0.5
    return -worth if obj is me else worth
