"""Kind for the grammar's player-counter verb (see mtgsim.cx_grammar_life)."""
from ..state import Player
from . import kind


@kind("player_counter")
def player_counter(game, p, eff, target, **_):
    """The named player gets N experience / poison counters (player counters, p.counters)."""
    if not isinstance(target, Player):
        return
    name = eff.data["counter"]
    target.counters[name] = target.counters.get(name, 0) + eff.amount
    game.log(f"gets {eff.amount} {name} counter(s)", target)
