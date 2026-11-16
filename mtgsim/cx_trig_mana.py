"""Triggered mana abilities on tapping for mana (#860 item 6):

    Whenever a Forest is tapped for mana, its controller adds an additional {G}.                 (Vernal Bloom)
    Whenever a basic land is tapped for mana of the chosen color, its controller adds an additional one mana
        of that color.                                                                           (Gauntlet of Power)
    Whenever enchanted Forest is tapped for mana, its controller adds an additional one mana of the chosen color.
                                                                                                 (Utopia Sprawl)
    Whenever you tap a creature for mana, add an additional {G}.                                  (Leyline of Abundance)
    Whenever you tap a permanent for {C}, add an additional {C}.                                  (Forsaken Monument)
    Whenever you tap a nonland permanent for mana, add one mana of any type that permanent produced.  (Kinnan)
    Whenever you tap a land for mana while you're the monarch, add an additional one mana of any color.

A triggered mana ability resolves at once, inside the payment that tapped the source (CR 605.1b, 605.4a). The
engine pays from mana "slots" (engine/mana.py): each matching ability gives the tapped source one more slot of the
mana it adds, so the extra mana is there for the same cost, and using either slot taps the source. That is the
same model batch1_templates' "enchanted land ... adds an additional {G}" Auras use (``aura_mana_colors``), which keep
that wording; this module refuses it.

"Tapped for mana of the chosen color" / "for {C}": the source must make only mana of that kind, so the slot model
never counts a dual land tapped for its other colour. Sources that aren't tapped to make mana (filter lands,
sacrifice-only sources, storage counters) get no extra slot.
"""
from __future__ import annotations

import re

from . import cx_events

_KEY = "tap_mana_bonus"
_COLOR = r"\{[WUBRGC]\}"
_HOST = re.compile(r"Whenever enchanted (land|Forest|Plains|Island|Swamp|Mountain) is tapped for mana, its controller "
                   r"adds an additional one mana of the chosen color\.")
_ANY = re.compile(r"Whenever an? (?P<d>[\w ]+?) is tapped for mana(?P<ch> of the chosen color)?, its controller adds "
                  r"an additional (?P<x>" + _COLOR + r"|one mana of that color)\.")
_YOU = re.compile(r"Whenever you tap an? (?P<d>[\w ]+?) for (?P<of>mana|\{C\})(?P<mon> while you're the monarch)?, "
                  r"add (?P<x>an additional " + _COLOR + r"|an additional one mana of any color|one mana of any type "
                  r"that (?:permanent|land|creature|artifact|artifact token) produced|" + _COLOR + r")\.")


def _extra(x: str):
    """What the extra mana can be: a colour set, "chosen" or "same" (the source's own mana)."""
    m = re.search(r"\{([WUBRGC])\}", x)
    if m:
        return frozenset(m[1])
    if "any color" in x:
        return frozenset("WUBRG")
    if "chosen" in x or "that color" in x:
        return "chosen"
    return "same"


def parse(line: str):
    """The rule for one line, or None."""
    m = _HOST.fullmatch(line)
    if m:
        alts = None if m[1] == "land" else [(m[1],)]
        return {"scope": "host", "alts": alts, "need": "", "extra": "chosen", "monarch": False}
    m = _ANY.fullmatch(line)
    if m:
        alts = cx_events._desc_alts(m["d"])
        if alts is None or (m["x"] == "one mana of that color") != bool(m["ch"]):
            return None
        return {"scope": "all", "alts": alts, "need": "chosen" if m["ch"] else "", "extra": _extra(m["x"]),
                "monarch": False}
    m = _YOU.fullmatch(line)
    if m:
        alts = cx_events._desc_alts(m["d"])
        if alts is None:
            return None
        extra = _extra(m["x"])
        if extra == "same" and (m["of"] != "mana" or alts == [("land",)]):
            return None     # "tap a land ... any type that land produced": residual_templates' land_double
        return {"scope": "you", "alts": alts, "need": "C" if m["of"] == "{C}" else "", "extra": extra,
                "monarch": bool(m["mon"])}
    return None


def face_line(st, line):
    """Face-line parser (put first in cards/parse.py's list by cards/__init__.py)."""
    rule = parse(line)
    if rule is None:
        return line
    st.extra.setdefault("advanced_rules", {}).setdefault(_KEY, []).append(rule)
    if not own_mana(st.oracle or ""):
        st.produces.clear()     # "As ~ enters, choose a color." assumed the card itself makes that mana
    return None


def own_mana(oracle: str) -> bool:
    """The card has a mana ability of its own ("{T}: Add ..."), not just the triggered extra mana."""
    return re.search(r"(?:^|\n)[^\n\"]*: Add ", oracle) is not None


def extra_slots(src, make) -> list:
    """The extra payment slots tapping ``src`` for mana gives (``make(src, colors)`` builds one)."""
    game = getattr(src.controller, "_game", None)
    if game is None or getattr(src, "stored_in", None) is not None or src.card.mana_filter or src.card.mana_sac_only:
        return []
    from .residual_templates import sources
    watchers = sources(game, _KEY)
    if not watchers:
        return []
    from .engine.mana import _mana_of
    own = frozenset(_mana_of(src))
    out = []
    for w in watchers:
        for rule in w.card.advanced_rules.get(_KEY, ()):
            if rule["scope"] == "host" and w not in getattr(src, "auras", ()):
                continue
            if rule["scope"] == "you" and src.controller is not w.controller:
                continue
            if rule["monarch"] and getattr(game, "monarch", None) is not w.controller:
                continue
            if rule["alts"] is not None and not cx_events._perm_fits(game, src, rule["alts"]):
                continue
            chosen = getattr(w, "chosen_color", None)
            if rule["need"] == "C" and own != frozenset("C"):
                continue
            if rule["need"] == "chosen" and (chosen is None or own != frozenset(chosen)):
                continue
            extra = rule["extra"]
            if extra == "chosen":
                if chosen is None:
                    continue
                extra = frozenset(chosen)
            elif extra == "same":
                extra = own
            out.append(make(src, extra))
    return out
