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
    cands = [s for s in base if getattr(s.card, "mana_amount", 1) == 1]
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
    pips = [c for c in COLORS + ("C",) for _ in range(cost.get(c, 0))]
    generic = cost.get("generic", 0)
    # A source that makes several mana (Sol Ring) fills several slots.
    slots = [s for s in sources for _ in range(max(1, getattr(s.card, "mana_amount", 1)))]
    if len(pips) + generic > len(slots):
        return None
    # Mana that can only be spent on some spells goes first when it is allowed at all.
    slots = sorted(slots, key=lambda s: (not s.card.mana_restriction, s.card.token_kind == "treasure" or s.card.mana_sac_only,
                                         len(_mana_of(s)), s.is_creature, -getattr(s.card, "mana_amount", 1)))
    pips.sort(key=lambda c: sum(c in _mana_of(s) for s in slots))
    used = [False] * len(slots)

    def assign(i):
        if i == len(pips):
            return True
        for j, s in enumerate(slots):
            if not used[j] and pips[i] in _mana_of(s):
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
                             -getattr(s.card, "mana_amount", 1), len(_mana_of(s)), s.is_creature))
    if len(rest) < generic:
        return None
    out = []
    for s in chosen + rest[:generic]:
        if s not in out:
            out.append(s)
    return out


def payable(sources: list[Permanent], cost: dict) -> bool:
    """Whether find_payment(sources, cost) would find a payment, without choosing which sources
    to tap: coloured pips need a matching, and generic mana any slots left over."""
    if any(s.card.mana_filter for s in sources):
        return find_payment(sources, cost) is not None
    pips = [c for c in COLORS + ("C",) for _ in range(cost.get(c, 0))]
    generic = cost.get("generic", 0)
    slots = [_mana_of(s) for s in sources for _ in range(max(1, getattr(s.card, "mana_amount", 1)))]
    if len(pips) + generic > len(slots):
        return False
    if not pips:
        return True
    pips.sort(key=lambda c: sum(c in m for m in slots))
    used = [False] * len(slots)

    def assign(i):
        if i == len(pips):
            return True
        for j, m in enumerate(slots):
            if not used[j] and pips[i] in m:
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
