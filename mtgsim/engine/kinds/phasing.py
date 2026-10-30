"""Phasing effect kinds (see mtgsim.phasing)."""
from . import kind


@kind("phase_out")
def phase_out(game, p, eff, target, item, prev, **_):
    from ... import phasing
    phasing.resolve_phase_out(game, p, eff, target, item, prev)


@kind("phase_in_all")
def phase_in_all(game, p, eff, **_):
    from ... import phasing
    phasing.resolve_phase_in_all(game, p, eff)


@kind("phase_out_count")
def phase_out_count(game, p, eff, target, item, **_):
    from ... import phasing
    phasing.phase_out_count(game, p, eff, target, item)


@kind("phase_coin")
def phase_coin(game, p, eff, target, item, **_):
    from ... import phasing
    phasing.phase_coin(game, p, eff, target, item)
