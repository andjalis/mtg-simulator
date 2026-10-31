"""Flashback granted from the graveyard, "cast as though it had flash if you pay {N} more", and depletion lands.

* "Each instant and sorcery card in your graveyard gains flashback until end of turn. The flashback cost is equal to
  its mana cost." (Past in Flames, Backdraft Hellkite): ``grant_flashback`` with ``all``; the cost sentence is implied
  because the engine casts a granted card for its own mana cost.
* "You may cast ~ as though it had flash if you pay {2} more to cast it." (Rout, Ghitu Fire): an ``AltCost("flash_tax")``
  whose cost is the extra mana; the engine offers it as a copy of the spell with flash and the full cost.
* Peat Bog and friends: enters tapped with two depletion counters; "{T}, Remove a depletion counter: Add {B}{B}" makes
  two mana (``mana_amount``) and the land is sacrificed when the last counter is gone (``mana_depletion``)."""
from __future__ import annotations

import re

_GRAVEYARD = r"(?:each|all) (?:instant and sorcery|instant or sorcery|sorcery and instant) cards? in your graveyard"
_COST_IS_MV = r"the flashback cost is equal to (?:its|that card's|the card's) mana cost"


def _grant_all(m):
    from .cards.model import Effect
    return [Effect("grant_flashback", data={"all": True})]


def _grant_one(m):
    from .cards.model import Effect
    return [Effect("grant_flashback")]


def _no_effect(m):
    return []


EFFECT_PATTERNS = [
    (rf"{_GRAVEYARD} gains? flashback until end of turn", _grant_all),
    (r"target instant or sorcery card in your graveyard gains flashback until end of turn", _grant_one),
    (_COST_IS_MV, _no_effect),
]

_MANA = r"((?:\{[WUBRGC]\})+)"


def parse_line(st, line: str):
    """Face-line handler: returns None once the line is handled, else the line."""
    from .cards.model import AltCost, parse_mana_cost
    m = re.fullmatch(r"You may cast ~ as though it had flash if you pay ((?:\{[0-9WUBRGC]\})+) more to cast it\.", line)
    if m:
        st.alt_costs.append(AltCost("flash_tax", parse_mana_cost(m[1])))
        return None
    m = re.fullmatch(r"~ enters(?: the battlefield)? tapped with (two|three|four) depletion counters on it\.", line)
    if m:
        st.enters_tapped = True
        st.extra["etb_named_counters"] = ("depletion", {"two": 2, "three": 3, "four": 4}[m[1]])
        return None
    m = re.fullmatch(r"\{T\}, Remove a depletion counter from ~: Add " + _MANA + r"\. "
                     r"If there are no depletion counters on ~, sacrifice it\.", line)
    if m:
        colors = re.findall(r"\{([WUBRGC])\}", m[1])
        if len(set(colors)) == 1 and len(colors) > 1:
            st.produces |= {colors[0]}
            st.extra["mana_amount"] = len(colors)
            st.extra["mana_depletion"] = True
            return None
    return line
