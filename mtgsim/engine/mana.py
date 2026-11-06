"""Mana payment: finding a way to pay a cost from a set of mana sources."""
from __future__ import annotations

import itertools
from typing import TYPE_CHECKING

from ..cards import COLORS

if TYPE_CHECKING:
    from .state import Permanent


def _mana_of(s) -> frozenset:
    now = getattr(s, "produces_now", None)
    return s.card.produces if now is None else now


def _amount(s) -> int:
    """How much mana s makes right now (Tablet of Discovery's restricted {R}{R} is 2, its {R} is 1)."""
    now = getattr(s, "amount_now", None)
    base = getattr(s.card, "mana_amount", 1) if now is None else now
    if s.card.mana_dyn:
        from ..mana_count import dynamic_amount
        base = dynamic_amount(s)
    if s.card.is_land:
        base += sum(a.card.advanced_rules.get('aura_mana', 0) for a in s.auras if not a.abilities_suppressed)
        return base * 2 if _doubled(s) else base
    return base


class _Extra:
    """One extra mana a source makes in colours of its own (an Aura on a land: "adds an additional {G}"): it stands for
    the source in a payment but can only make `colors`."""

    def __init__(self, src, colors):
        self.src, self.produces_now = src, frozenset(colors)

    def __getattr__(self, name):
        return getattr(self.src, name)


def _extras(s) -> list:
    """The extra-mana slots of land s from Auras that name their colours (see batch1_templates)."""
    if not s.card.is_land:
        return []
    out = [_Extra(s, cols) for a in s.auras if not a.abilities_suppressed
           for cols in a.card.advanced_rules.get("aura_mana_colors", ())]
    return out * 2 if out and _doubled(s) else out


def _slots_of(s) -> list:
    """The payment slots of source s: its own mana, then the extras that have their own colours."""
    n = _amount(s) - sum(len(a.card.advanced_rules.get("aura_mana_colors", ())) for a in s.auras
                         if s.card.is_land and not a.abilities_suppressed) * (2 if s.card.is_land and _doubled(s) else 1)
    return [s] * (n if s.card.mana_dyn else max(1, n)) + _extras(s)


def _doubled(land) -> bool:
    """"Whenever you tap a land for mana, add one mana of any type that land produced" (Mirari's Wake, Heartbeat of Spring)."""
    game = getattr(land.controller, "_game", None)
    if game is None:
        return False
    from ..residual_templates import sources
    return any(x.controller is land.controller or x.card.advanced_rules['land_double'] == 'all' for x in sources(game, 'land_double'))


def _fits(pip: str, s) -> bool:
    """Whether source s can pay this pip: {S} is any mana from a snow source."""
    return bool(getattr(s.card, "snow", False)) if pip == "S" else pip in _mana_of(s)


def find_payment(sources: list[Permanent], cost: dict):
    """Pick which mana sources to tap for a cost, or None if it can't be paid. Filter lands ("{1}, {T}: Add one mana
    of any color") add no mana of their own: each one that is used recolours one other source's mana."""
    filt = [s for s in sources if s.card.mana_filter]
    if not filt:
        return _find_payment(sources, cost)
    base = [s for s in sources if not s.card.mana_filter]
    got = _find_payment(base, cost)
    if got is not None:
        return got
    cands = [s for s in base if _amount(s) == 1]
    for u in range(1, min(len(filt), len(cands)) + 1):
        for combo in itertools.combinations(cands, u):
            saved = [getattr(s, "produces_now", None) for s in combo]
            for s, f in zip(combo, filt):
                s.produces_now = f.card.produces
            got = _find_payment(base, cost)
            for s, old in zip(combo, saved):
                s.produces_now = old
            if got is not None:
                used = sum(1 for s in got if s in combo)
                return got + filt[:used]
    return None


def _find_payment(sources: list[Permanent], cost: dict):
    pips = [c for c in COLORS + ("C", "S") for _ in range(cost.get(c, 0))]
    generic = cost.get("generic", 0)
    # A source that makes several mana (Sol Ring) fills several slots.
    slots = [m for s in sources for m in _slots_of(s)]
    if len(pips) + generic > len(slots):
        return None
    # Mana that can only be spent on some spells goes first when it is allowed at all.
    slots = sorted(slots, key=lambda s: (not s.card.mana_restriction, s.card.token_kind == "treasure" or s.card.mana_sac_only,
                                         len(_mana_of(s)), s.is_creature, -_amount(s)))
    pips.sort(key=lambda c: sum(_fits(c, s) for s in slots))
    used = [False] * len(slots)

    def assign(i):
        if i == len(pips):
            return True
        for j, s in enumerate(slots):
            if not used[j] and _fits(pips[i], s):
                used[j] = True
                if assign(i + 1):
                    return True
                used[j] = False
        return False

    if not assign(0):
        return None
    chosen = [s for j, s in enumerate(slots) if used[j]]
    # Generic mana: first use leftover slots of sources already being tapped, then multi-mana ones.
    rest = [s for j, s in enumerate(slots) if not used[j]]
    rest.sort(key=lambda s: (s not in chosen, not s.card.mana_restriction, s.card.token_kind == "treasure" or s.card.mana_sac_only,
                             -_amount(s), len(_mana_of(s)), s.is_creature))
    if len(rest) < generic:
        return None
    out = []
    for s in chosen + rest[:generic]:
        s = getattr(s, "src", s)
        if s not in out:
            out.append(s)
    return out


def payable(sources: list[Permanent], cost: dict) -> bool:
    """Whether find_payment(sources, cost) would find a payment, without choosing which sources
    to tap: coloured pips need a matching, and generic mana any slots left over."""
    if any(s.card.mana_filter for s in sources):
        return find_payment(sources, cost) is not None
    pips = [c for c in COLORS + ("C", "S") for _ in range(cost.get(c, 0))]
    generic = cost.get("generic", 0)
    slots = [m for s in sources for m in _slots_of(s)]
    if len(pips) + generic > len(slots):
        return False
    if not pips:
        return True
    pips.sort(key=lambda c: sum(_fits(c, m) for m in slots))
    used = [False] * len(slots)

    def assign(i):
        if i == len(pips):
            return True
        for j, m in enumerate(slots):
            if not used[j] and _fits(pips[i], m):
                used[j] = True
                if assign(i + 1):
                    return True
                used[j] = False
        return False

    return assign(0)


def add_costs(*costs) -> dict:
    out = {"generic": 0}
    for c in costs:
        for k, v in c.items():
            out[k] = out.get(k, 0) + v
    return out
