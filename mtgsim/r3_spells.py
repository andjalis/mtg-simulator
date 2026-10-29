"""Spell return, conditional destruction/draw, and random-discard riders."""
from __future__ import annotations

import dataclasses
import re

KINDS = {"bounce_spell_permanent", "destroy_other_exact_power", "destroy_mv"}


def _effect(kind, **kwargs):
    from .cards.model import Effect
    return Effect(kind, **kwargs)


EFFECT_PATTERNS = [
    (r"return target spell or permanent to its owner's hand",
     lambda m: _effect("bounce_spell_permanent", target="spell_or_permanent")),
    (r"destroy all other creatures if its power is exactly (\d+)",
     lambda m: _effect("destroy_other_exact_power", amount=int(m[1]))),
    (r"draw a card if you control an? (artifact|enchantment)",
     lambda m: _effect("draw", amount=1, data={"control_type": m[1].capitalize()})),
    (r"discard a card at random", lambda m: _effect("discard", amount=1, data={"random": True})),
    (r"search your library for a card, put it into your hand, shuffle",
     lambda m: _effect("tutor", data={"what": "a card"})),
]
SUBS = []
TRIGGERS = [(r"Whenever one or more opponents are dealt noncombat damage, (.+)", ("opponents_noncombat_damage",))]


def parse_revolt(sentence, effects):
    """Fold the exact supported replacement into its preceding destruction effect."""
    m = re.fullmatch(r"revolt — destroy that creature if it has mana value (\d+) or less instead if a permanent "
                     r"(?:you controlled left the battlefield|left the battlefield under your control) this turn",
                     sentence, re.I)
    if m is None:
        return None
    if not effects or effects[-1].kind != "destroy" or not effects[-1].filter.startswith("max_cmc:"):
        return False
    old = effects[-1]
    effects[-1] = dataclasses.replace(old, kind="destroy_mv", filter="",
                                      data=dict(old.data, limit=int(old.filter.split(":")[1]),
                                                revolt_limit=int(m[1])))
    return True


def return_spell(game, item):
    """Move a spell card immediately, including flashback and copy exceptions."""
    if item.kind != "copy":
        base, origin, _ = game._origin(item.card)
        owner = getattr(base, "owner", None) or item.controller
        (owner.exile if origin == "flashback" else owner.hand).append(base)
    item.left_stack = True


def resolve(game, p, eff, target, item):
    from .engine.state import Permanent, StackItem
    if eff.kind == "bounce_spell_permanent":
        if isinstance(target, Permanent):
            game.leave_battlefield(target, "hand")
        elif isinstance(target, StackItem) and target in game.stack and target.is_spell:
            game.stack.remove(target)
            return_spell(game, target)
    elif eff.kind == "destroy_mv":
        limit = eff.data["revolt_limit"] if p.perm_left_turn else eff.data["limit"]
        if isinstance(target, Permanent) and target.card.cmc <= limit:
            game.destroy(target, no_regen=eff.data.get("no_regen", False))
    elif eff.kind == "destroy_other_exact_power":
        src = item.source if item is not None else None
        if src is not None:
            if src.power == eff.amount:
                for pl in game.players:
                    for perm in list(pl.creatures):
                        if perm is not src:
                            game.destroy(perm)
