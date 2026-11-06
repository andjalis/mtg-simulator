"""Lair lands: bounce a non-Lair land or sacrifice the source."""
from . import kind
from ..state import Permanent, is_basic_land


@kind("sac_unless_bounce")
def sac_unless_bounce(game, p, eff, item, **_):
    src = item.source if item is not None else None
    if not isinstance(src, Permanent) or src not in p.battlefield:
        return
    bad = eff.data.get("not_subtype", "")
    pool = [x for x in p.battlefield if x is not src and x.card.is_land and bad not in x.card.subtypes]
    if not pool:
        game.sacrifice(src)
        return
    pick = min(pool, key=lambda x: (not x.tapped, not is_basic_land(x.card)))
    game.log(f"returns {pick.card.name} to hand", p)
    game.leave_battlefield(pick, "hand")
