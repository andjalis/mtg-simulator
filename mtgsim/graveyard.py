"""Activated abilities whose source returns from the graveyard."""
from __future__ import annotations

import re


# cx_costs kinds a graveyard ability can pay (the card itself is never one of the cards it exiles or taps)
_GY_COSTS = ("discard", "discard_random", "mill", "tap", "exile_gy", "sacrifice_n")


def is_return_ability(line):
    return re.search(r": Return (?:this card|~) from your graveyard to (?:the battlefield|your hand)", line) is not None


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
    desc = act.extra_costs.pop("exile_gy_card", None) if act is not None else None
    if desc is not None:             # "Exile another creature card from your graveyard": paid by cx_costs, never the card itself
        from .cx_costs import parse_part
        if not parse_part("Exile another " + desc + " from your graveyard", act.extra_costs):
            return None
    if act is None or act.once or act.once_game or act.modes or \
            set(act.extra_costs) - {"discard", "life", "cx_costs", "sacrifice", "sac_n"} or \
            any(k not in _GY_COSTS for k, _n, _s in act.extra_costs.get("cx_costs", ())) or \
            any(e.target in ("self", "prev") for e in act.effects) or \
            not any(e.kind == "return_self_gy" for e in act.effects):
        return None
    act.condition, act.text = condition, line
    approximations += approx
    return act


class _Source:
    """Stand-in for the source of a graveyard ability when a restriction or condition reads it like a permanent."""

    def __init__(self, p, card):
        self.controller, self.card, self.counters = p, card, {}
        self.tapped = self.sick = False
        self.power = self.toughness = 0


def _sac_ok(game, p, card, costs):
    what = costs.get("sacrifice")
    return not what or len(game.sacrifice_candidates(p, card, what)) >= costs.get("sac_n", 1)


def worth(game, p, card, idx) -> bool:
    """Whether the AI should pay this graveyard ability's costs now: it doesn't sacrifice permanents worth more than
    the card it gets back, discard its last cards, pay life at 10 or less, or mill itself near an empty library."""
    from .engine.policy import perm_value
    act = card.gy_activated[idx]
    costs = act.extra_costs
    pt = [int(x) if str(x).isdigit() else 0 for x in (card.power, card.toughness)]
    value = card.cmc + sum(pt) / 2
    victims = []
    if costs.get("sacrifice"):
        victims = game.sacrifice_candidates(p, card, costs["sacrifice"])[:costs.get("sac_n", 1)]
    for kind, n, spec in costs.get("cx_costs", ()):
        if kind == "sacrifice_n":
            from .cx_abil_costs import _sac_pool
            victims += _sac_pool(game, p, card, spec)[:n]
        elif kind in ("discard", "discard_random") and len(p.hand) <= n:
            return False
        elif kind == "mill" and len(p.library) < n + 10:
            return False
    if costs.get("discard") and len(p.hand) <= costs["discard"]:
        return False
    if costs.get("life") and p.life <= 10:
        return False
    return all(v.card.is_token or perm_value(v) < value for v in victims)


def can_activate(game, p, card, idx):
    from . import modal
    from .engine import payable
    if game.nonmana_locked(p) or card not in p.graveyard or not 0 <= idx < len(card.gy_activated):
        return False
    act = card.gy_activated[idx]
    if act.sorcery and not (p is game.active and game.step in ("main1", "main2") and not game.stack):
        return False
    if act.condition and not modal.upgrade_active(game, p, act.condition):
        return False
    if act.needs_max_speed and p.speed < 4:
        return False
    costs = act.extra_costs
    if act.restrictions:
        from .cx_activation import allowed
        if not allowed(game, p, _Source(p, card), act.restrictions):
            return False
    if not _sac_ok(game, p, card, costs):
        return False
    if len(p.hand) < costs.get("discard", 0) or p.life < costs.get("life", 0):
        return False
    if costs.get("cx_costs"):
        from .cx_costs import payable as parts_payable
        if not parts_payable(game, p, p.graveyard.get(card), costs["cx_costs"]):
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
    if act.extra_costs.get("cx_costs"):
        from .cx_costs import pay as pay_parts
        if not pay_parts(game, p, card, act.extra_costs["cx_costs"]):
            return False
    if act.extra_costs.get("sacrifice"):
        for x in game.sacrifice_candidates(p, card, act.extra_costs["sacrifice"])[:act.extra_costs.get("sac_n", 1)]:
            game.sacrifice(x)
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
