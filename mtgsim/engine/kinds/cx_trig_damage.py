"""``cx_dmg_payoff``: the "that much" payoff of a damage trigger from any source (see mtgsim/cx_trig_damage.py, #521)."""
from __future__ import annotations

from . import kind


@kind("cx_dmg_payoff")
def dmg_payoff(game, p, eff, item=None, **_):
    from ...cx_trig_damage import resolve
    resolve(game, p, eff, item)
