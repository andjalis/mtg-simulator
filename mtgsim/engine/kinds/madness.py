"""Handler for mtgsim/madness.py."""
from . import kind
from ... import madness


@kind("madness")
def madness_trigger(game, p, eff, **_):
    madness.resolve(game, p, eff)
