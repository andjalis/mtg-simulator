"""Blocking requirements and limits for the turn: see mtgsim/cx_lures.py."""
from __future__ import annotations

from . import kind
from ..state import Permanent


def _source(item):
    src = getattr(item, "source", None) if item is not None else None
    return src if isinstance(src, Permanent) else None


@kind("cx_must_block", "cx_cant_block_src")
def must_block(game, p, eff, target, item, **_):
    from ...cx_lures import add_pair
    source = _source(item)
    if not isinstance(target, Permanent) or source is None:
        return
    must = eff.kind == "cx_must_block"
    add_pair(game, "_cx_must_block" if must else "_cx_cant_block", target, source)
    verb = "must block" if must else "cannot block"
    game.log(f"{target.card.name} {verb} {source.card.name} this turn", p)


@kind("cx_mass_cant_block")
def mass_cant_block(game, p, eff, item, **_):
    from ...permanent_templates import matches
    source = _source(item)
    for pl in game.players:
        for x in pl.battlefield:
            if x.is_creature and matches(game, x, eff.data["selector"], p, source):
                x.temp_kw.add("cant_block_now")
    game.log("creatures can't block this turn", p)
