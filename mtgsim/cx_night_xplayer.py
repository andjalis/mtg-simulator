"""Player effects sized by the X paid for the spell: "Target player draws X cards", "Target opponent loses X life".

The sentence is read with X replaced by 1 and the effect is then flagged ``x`` so ``resolve`` replaces its amount with
the X paid (the way "Draw X cards" already works)."""
from __future__ import annotations

_KINDS = {"draw", "drain", "lose_life", "gain_life", "mill"}

_X = (r"(?P<who>target player|target opponent|each opponent|you|each player)\s+"
      r"(?P<verb>draws?|loses?|gains?|mills?)\s+X\s+(?P<what>cards?|life)")


def _x_player(m):
    from .cards import _parse_effects
    from .cards.model import NO_MATCH
    sent = f"{m['who']} {m['verb']} 1 {'card' if m['what'].startswith('card') else 'life'}"
    effects, unmatched = _parse_effects(sent[0].upper() + sent[1:])
    if unmatched or len(effects) != 1 or effects[0].kind not in _KINDS or effects[0].data:
        return NO_MATCH
    effects[0].data["x"] = True
    return effects


EFFECT_PATTERNS = [(_X, _x_player)]
