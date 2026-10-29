"""Emerge {6}{B}                (cast it by sacrificing a creature and paying the emerge cost reduced by that
                                creature's mana value)
   Emerge from artifact {5}{B}{B}   (the same, sacrificing an artifact)

``parse_line`` reads the keyword into an AltCost("emerge" / "emerge_artifact"), and two linked lines:
"When you sacrifice ~ while casting a spell with emerge, <effects>" (Foul Emissary) and Herigast's "Each creature
spell you cast has emerge. The emerge cost is equal to its mana cost." (``advanced_rules["grants_emerge"]``).
``variants`` offers the emerge cast of a hand card when its full cost can't be paid; the sacrifice is the card's
additional cost (``extra_sacrifice``) planned with the mana in costs.spell_plan, which takes the sacrificed
permanent's mana value off the generic part of the cost. ``sacrificing`` records the victim's toughness for
Adipose Offspring's "if its emerge cost was paid" rider.
"""
from __future__ import annotations

import re


def parse_line(line: str, st) -> bool:
    from .cards.model import AltCost, parse_mana_cost
    m = re.fullmatch(r"Emerge( from artifact)? ((?:\{[^}]+\})+)", line)
    if m:
        st.alt_costs.append(AltCost("emerge_artifact" if m[1] else "emerge", parse_mana_cost(m[2])))
        return True
    m = re.fullmatch(r"When you sacrifice ~ while casting a spell with emerge, (.+)", line)
    if m:
        from .cards.parse import _parse_effects
        effects, unmatched = _parse_effects(m[1])
        if not unmatched and effects:
            st.extra.setdefault("advanced_rules", {})["emerge_sacrificed"] = effects
            return True
        return False
    if line == "Each creature spell you cast has emerge. The emerge cost is equal to its mana cost.":
        st.extra.setdefault("advanced_rules", {})["grants_emerge"] = True
        return True
    return False


def parse_rider(s: str, effects: list) -> bool:
    """The Adipose Offspring rider: "If ~'s emerge cost was paid, instead create X of those tokens, where X is the
    sacrificed creature's toughness"."""
    import dataclasses
    if effects and effects[-1].kind == "token" and re.fullmatch(
            r"if ~'s emerge cost was paid, instead create X of those tokens, where X is the sacrificed creature's "
            r"toughness", s, re.I):
        effects[-1] = dataclasses.replace(effects[-1], data=dict(effects[-1].data, emerged_toughness=True))
        return True
    return False


def _alt(game, p, card):
    from .cards.model import AltCost
    own = next((a for a in card.alt_costs if a.kind in ("emerge", "emerge_artifact")), None)
    if own is not None:
        return own
    if card.is_creature and any(x.card.advanced_rules.get("grants_emerge") for x in p.battlefield):
        return AltCost("emerge", dict(card.mana_cost))
    return None


def variants(game, p, card) -> list:
    """The emerge cast of a hand card, when there is something to sacrifice and the full cost isn't payable."""
    alt = _alt(game, p, card)
    if alt is None or card.is_land or game.spell_payable(p, card):
        return []
    v = game._variant(card, "emerge", alt)
    v.extra_sacrifice = "artifact" if alt.kind == "emerge_artifact" else "creature"
    return [v] if game.extra_sac_candidates(p, v) else []


def sacrifice_options(game, p, card, candidates) -> list:
    """(victim, tax) pairs for costs.plan: the emerge cost is reduced by the victim's mana value."""
    return [(c, -c.card.cmc) for c in candidates]


def is_emerge(game, card) -> bool:
    origin = getattr(card, "origin", None)
    return bool(origin) and origin[1] == "emerge"


def sacrificing(game, p, victim, card):
    """Called as the cost is paid, before the sacrifice: remember its toughness and fire its emerge trigger."""
    game._emerge_toughness = max(0, victim.toughness) if victim.is_creature else 0
    effects = victim.card.advanced_rules.get("emerge_sacrificed")
    if effects:
        game.queue_trigger(p, list(effects), None, f"{victim.card.name}: sacrificed for emerge")
