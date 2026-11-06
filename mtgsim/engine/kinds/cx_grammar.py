"""Kinds for the compositional effect grammar (see mtgsim.cx_grammar)."""
from ..state import Permanent, Player
from . import kind


@kind("cx_group")
def group(game, p, item, eff, target, **_):
    """Apply each inner effect to every permanent the group names ("creatures target player controls": that
    player's), fixed when the effect resolves."""
    from ...cx_grammar import group_members
    from . import HANDLERS
    if eff.target == "player" and not isinstance(target, Player):
        return
    source = item.source if item else None
    for victim in group_members(game, p, eff.data, source, target if eff.target == "player" else None):
        for inner in eff.data["effects"]:
            HANDLERS[inner.kind](game, p=p, eff=inner, target=victim, item=item, opp=game.opponent(p))


@kind("cx_color")
def color(game, target, eff, **_):
    """Layer 5: the permanent becomes the colours (or gains them, "in addition to its other colors")."""
    if isinstance(target, Permanent) and target in target.controller.battlefield:
        game.add_continuous_effect(target, eff.data["op"], colors=frozenset(eff.data["colors"]),
                                   until_eot=eff.data["eot"])
