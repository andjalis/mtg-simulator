"""Activated abilities whose source returns from the graveyard."""
from __future__ import annotations

import re


def is_return_ability(line):
    return re.search(r": Return (?:this card|~) from your graveyard to the battlefield", line) is not None


def parse_ability(line, approximations):
    from .cards import _parse_ability
    text = re.sub(r"^(?:Delirium|Descend \d+) — ", "", line)
    condition = ""
    restrictions = {
        "there are four or more card types among cards in your graveyard": "delirium",
        "there are eight or more permanent cards in your graveyard": "gy8",
    }
    m = re.fullmatch(r"(.+\.) Activate only if (.+) and only as a sorcery\.", text)
    if m:
        condition = restrictions.get(m[2])
        if condition is None:
            return None
        text = m[1] + " Activate only as a sorcery."
    text = text.replace("Return this card from your graveyard", "Return ~ from your graveyard")
    approx = []
    act = _parse_ability(text, approx)
    if act is None or act.once or act.once_game or act.modes or \
            set(act.extra_costs) - {"discard", "life"} or \
            any(e.target in ("self", "prev") for e in act.effects) or \
            not any(e.kind == "return_self_gy" for e in act.effects):
        return None
    act.condition, act.text = condition, line
    approximations += approx
    return act


def can_activate(game, p, card, idx):
    from . import modal
    from .engine import payable
    if card not in p.graveyard or not 0 <= idx < len(card.gy_activated):
        return False
    act = card.gy_activated[idx]
    if act.sorcery and not (p is game.active and game.step in ("main1", "main2") and not game.stack):
        return False
    if act.condition and not modal.upgrade_active(game, p, act.condition):
        return False
    if act.needs_max_speed and p.speed < 4:
        return False
    costs = act.extra_costs
    if len(p.hand) < costs.get("discard", 0) or p.life < costs.get("life", 0):
        return False
    return payable(game.mana_sources(p, spell="ability"), act.cost)


def activate(game, p, card, idx):
    from .engine import StackItem
    if not can_activate(game, p, card, idx):
        return False
    card = p.graveyard.get(card)
    act = card.gy_activated[idx]
    if game.pay(p, act.cost) is None:
        return False
    if act.extra_costs.get("life"):
        game.change_life(p, -act.extra_costs["life"], f"{card.name}: graveyard ability cost")
    for _ in range(act.extra_costs.get("discard", 0)):
        game.discard_card(p, p.ai.choose_discard(game, p))
    item = StackItem(p, list(act.effects), game.auto_targets(p, act.effects), context=card,
                     name=f"{card.name} graveyard ability", kind="ability")
    game.stack.append(item)
    game.log(f"activates {item}", p)
    game.check_ward(item)
    game.settle()
    return True
