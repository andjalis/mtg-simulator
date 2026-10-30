"""Prepare effect kinds (see mtgsim.prepare)."""
from . import kind


@kind("prepare")
def prepare(game, p, eff, target, **_):
    from ... import prepare as _prepare
    _prepare.prepare(game, p, eff, target)


@kind("prepare_all")
def prepare_all(game, p, eff, **_):
    from ... import prepare as _prepare
    _prepare.prepare_all(game, p, eff)
