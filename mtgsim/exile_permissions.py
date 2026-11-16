"""Single-card exile permissions, valid only for the captured exile generation.

Owner-cast riders attach to the actual exile effect. Unsupported play/tax and
foreign-mana riders remain unmatched; they need a richer permission contract.
"""
from __future__ import annotations

import re
from dataclasses import replace


EFFECT_PATTERNS = []
SUBS = []
PREFIX = 'exile_cast_'


def parse_rider(sentence, effects):
    m = re.fullmatch(r'for as long as that card remains exiled, its owner may cast it( without paying its mana cost)?',
                     sentence, re.I)
    if not m or not effects or effects[-1].kind != 'exile_permanent':
        return False
    effects[-1] = replace(effects[-1], data=dict(effects[-1].data, owner_cast_exiled={'free': bool(m[1])}))
    return True


def grant(permanent, free):
    """Capture only the physical card that the effect really put into exile."""
    owner, card = permanent.owner, permanent.front
    if permanent.card.is_token or card.is_token or permanent.last_destination != 'exile' or card not in owner.exile:
        return
    if not hasattr(owner, 'exile_cast_permissions'):
        owner.exile_cast_permissions = []
    owner.exile_cast_permissions.append((owner.exile.reference(card), free))


def options(game, p):
    out = []
    alive = []
    for ref, free in getattr(p, 'exile_cast_permissions', ()):
        card = ref.find(p.exile)
        if card is None:
            continue
        alive.append((ref, free))
        if not card.is_land:
            kind = PREFIX + str(card.physical_id) + _suffix(free)
            out.append(game._variant(card, kind, alt_cost(card, kind, free)))
    p.exile_cast_permissions = alive
    return out


def _suffix(free):
    return '_any' if free == 'any' else '_free' if free else '_paid'


def alt_cost(card, kind, free):
    """The cost of a permission cast: nothing (free), the mana cost with every pip generic ("mana of any type can be
    spent to cast it", "any" from cx_exile_play), or None (the card's own cost)."""
    from .cards.model import AltCost
    if free == 'any':
        cost = dict(card.mana_cost)
        total = sum(n for k, n in cost.items() if k not in ('X',))
        return AltCost(kind, {'generic': total, **({'X': cost['X']} if cost.get('X') else {})})
    return AltCost(kind, {'generic': 0}) if free else None


def available(game, p, card, kind):
    base = game._origin(card)[0]
    return any(ref.find(p.exile) is base and kind.endswith(_suffix(free))
               for ref, free in getattr(p, 'exile_cast_permissions', ()))
