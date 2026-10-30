"""Ripple effect kind (see mtgsim.ripple)."""
from . import kind


@kind("ripple")
def ripple(game, p, eff, item, **_):
    from ... import ripple as _ripple
    _ripple.ripple(game, p, eff, item)
