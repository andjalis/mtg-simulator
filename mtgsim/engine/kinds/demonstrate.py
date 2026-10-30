"""Demonstrate effect kind (see mtgsim.demonstrate)."""
from . import kind


@kind("demonstrate")
def demonstrate(game, p, eff, item, **_):
    from ... import demonstrate as _demonstrate
    _demonstrate.demonstrate(game, p, eff, item)
