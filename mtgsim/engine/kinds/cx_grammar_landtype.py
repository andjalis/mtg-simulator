"""The cx_landtype kind (see mtgsim.cx_grammar_landtype)."""
from ..state import Permanent
from . import kind


@kind("cx_landtype")
def landtype(game, eff, target, **_):
    if not isinstance(target, Permanent) or target not in target.controller.battlefield \
            or not target.copiable_card.is_land:
        return
    d = eff.data
    target.cx_landtype_extra = [e for e in getattr(target, "cx_landtype_extra", [])
                                if e[0] is None or e[0] == game.turn] + [(game.turn if d["eot"] else None, d["mode"],
                                                                         tuple(d["types"]))]
    from ...cx_landtypes import update
    update(game, [x for p in game.players for x in p.battlefield])
