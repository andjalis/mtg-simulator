"""Suspect: the creature gets menace and can't block until it leaves the battlefield (or stops being suspected)."""
from ..state import Permanent
from . import kind

SUSPECT_KEYWORDS = ("menace", "cant_block_now", "suspected")


@kind("suspect")
def suspect(game, p, target, prev, item, **_):
    """"Suspect it": the creature the previous effect made or chose, else the ability's own source."""
    perm = target if isinstance(target, Permanent) else prev if isinstance(prev, Permanent) else \
        item.source if item is not None and isinstance(item.source, Permanent) else None
    if perm is None or perm not in perm.controller.battlefield or not perm.is_creature:
        return
    perm.perm_kw.update(SUSPECT_KEYWORDS)
    game.log(f"{perm.card.name} is suspected", p)
