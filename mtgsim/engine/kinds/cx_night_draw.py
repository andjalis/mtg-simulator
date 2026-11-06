"""Draw for the player whose turn it is (draw-step triggers of every player's permanents)."""
from . import kind


@kind("draw_active")
def draw_active(game, p, eff, **_):
    game.draw(game.active, eff.amount)
