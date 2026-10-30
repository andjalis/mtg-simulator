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


@kind("phase_out_excess")
def phase_out_excess(game, p, eff, item, **_):
    from ... import phasing
    phasing.phase_out_excess(game, p, eff, item)


@kind("phase_out_realm")
def phase_out_realm(game, p, eff, target, item, **_):
    from ... import phasing
    phasing.phase_out_realm(game, p, eff, target, item)


@kind("pay_repeat")
def pay_repeat(game, p, eff, item, **_):
    from ... import phasing
    phasing.pay_repeat(game, p, eff, item)


@kind("phase_out_paid")
def phase_out_paid(game, p, eff, target, item, **_):
    from ... import phasing
    phasing.phase_out_paid(game, p, eff, target, item)


@kind("pay_repeat_counters")
def pay_repeat_counters(game, p, eff, target, item, **_):
    from ... import phasing
    phasing.pay_repeat_counters(game, p, eff, target, item)


@kind("pay_repeat_lands")
def pay_repeat_lands(game, p, eff, target, item, **_):
    from ... import phasing
    phasing.pay_repeat_lands(game, p, eff, target, item)


@kind("pay_repeat_tokens")
def pay_repeat_tokens(game, p, eff, item, **_):
    from ... import phasing
    phasing.pay_repeat_tokens(game, p, eff, item)
