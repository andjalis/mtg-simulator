"""Bounce residue (#638): "Each player returns a creature they control to its owner's hand."."""
from ... import permanent_templates
from ..policy import perm_value
from . import kind


@kind("bounce_choice")
def bounce_choice(game, p, eff, item, opp, **_):
    """Each named player returns one permanent of theirs that fits the selector: the cheapest (a tapped land
    first, the source itself last), as for the other choose-your-own effects."""
    src = item.source if item is not None else None
    who = {"you": [p], "each": [p, opp], "opponents": [opp]}[eff.data["who"]]
    for player in who:
        pool = [x for x in player.battlefield if permanent_templates.matches(game, x, eff.data["selector"], player, src)]
        if not pool:
            continue
        pick = min(pool, key=lambda x: (x is src, not (x.card.is_land and x.tapped), perm_value(x)))
        game.log(f"returns {pick.card.name} to hand", player)
        game.leave_battlefield(pick, "hand")
