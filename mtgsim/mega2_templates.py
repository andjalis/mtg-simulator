"""Return-from-graveyard riders of the mega-chonk-2 batch: "Put target creature card from a
graveyard onto the battlefield under your control. It gains haste." (Grave Upheaval) and
the same with "Exile it at the beginning of the next end step." (Gruesome Encore, which takes
a creature from an opponent's graveyard). The haste flag extends the gy_move kind; the
temporary shape reuses reanimate_temp with a zone bound.
"""
from __future__ import annotations

import re

_ZONES = {"a graveyard": "any", "an opponent's graveyard": "opp", "your graveyard": "mine"}

SUBS = [
    (re.compile(r"put target creature card from (a graveyard|an opponent's graveyard) onto the "
                r"battlefield under your control\. it gains haste\. exile it at the beginning of "
                r"the next end step\.?", re.I),
     lambda m: f"REANIM2 {m[1]}."),
    (re.compile(r"put target creature card from (a graveyard|an opponent's graveyard|your graveyard) "
                r"onto the battlefield under your control\. it gains haste\.", re.I),
     lambda m: f"GYHASTE {m[1]}."),
]

EFFECT_PATTERNS = [
    (r"GYHASTE (a graveyard|an opponent's graveyard|your graveyard)",
     lambda m: _gy_haste(_ZONES[m[1]])),
    (r"REANIM2 (a graveyard|an opponent's graveyard)",
     lambda m: _e("reanimate_temp", data={"zone": _ZONES[m[1]]})),
]


def _e(kind_, **kw):
    from .cards import Effect
    return Effect(kind_, 1, **kw)


def _gy_haste(zone):
    from .cards import Effect
    return Effect("gy_move", 1, data={"what": "creature", "dest": "bf", "tapped": False,
                                      "zone": zone, "cmc": None, "x_n": False, "haste": True})
