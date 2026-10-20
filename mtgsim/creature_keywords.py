"""Keyword abilities of creatures and Equipment that are a trigger or an "enters with" rule.

    Echo {2}{G}     Unleash     Evolve     Renown N     Mentor     Battle cry     Riot     Bloodthirst N
    Fabricate N     Living weapon     Heroic — Whenever you cast a spell that targets ~, ...
    ~ has first strike as long as it's attacking.     Whenever ~ deals damage, you gain that much life.

``parse_line`` turns a keyword line into CardDef fields and triggers. The "enters with" ones (unleash, riot,
bloodthirst) are applied in Game.enter_battlefield; echo is checked at the beginning of its controller's
upkeep. Choices: unleash always takes the counter, riot takes haste when the creature could still attack this
turn, fabricate always takes the counters. Not modelled: echo for permanents that changed control.
"""
from __future__ import annotations

import re

KINDS = {"evolve", "renown", "mentor", "battle_cry", "fabricate", "living_weapon", "echo"}


def _effect(kind, amount=0, **kw):
    from .cards import Effect
    return Effect(kind, amount, **kw)


def _trigger(event, effects, **kw):
    from .cards import Trigger
    return Trigger(event, effects, **kw)


def parse_line(line: str, extra: dict, triggers: list, keywords: set) -> bool:
    """Consume a keyword line; True if understood."""
    from .cards.model import parse_mana_cost
    m = re.fullmatch(r"Echo ((?:\{[^}]+\})+)", line)
    if m:
        extra["echo"] = parse_mana_cost(m[1])
        return True
    m = re.fullmatch(r"(Renown|Bloodthirst|Fabricate) (\d+)", line)
    if m:
        n = int(m[2])
        if m[1] == "Renown":
            triggers.append(_trigger("combat_damage_player", [_effect("renown", n)]))
        elif m[1] == "Fabricate":
            triggers.append(_trigger("etb", [_effect("fabricate", n)]))
        else:
            extra["bloodthirst"] = n
        return True
    if line in ("Unleash", "Riot"):
        extra[line.lower()] = True
        return True
    if line == "Evolve":
        triggers.append(_trigger("other_creature_enters", [_effect("evolve")], filter="evolve"))
        return True
    if line == "Mentor":
        triggers.append(_trigger("attacks", [_effect("mentor")]))
        return True
    if line == "Battle cry":
        triggers.append(_trigger("attacks", [_effect("battle_cry")]))
        return True
    if line == "Living weapon":
        triggers.append(_trigger("etb", [_effect("living_weapon")]))
        return True
    m = re.fullmatch(r"~ has (first strike|flying|trample|lifelink|deathtouch|menace|vigilance|double strike) as "
                     r"long as it's attacking\.", line)
    if m:
        extra["cond_keywords"] = extra.get("cond_keywords", ()) + ((m[1], "attacking"),)
        return True
    if line == "Whenever ~ deals damage, you gain that much life.":
        keywords.add("lifelink")
        return True
    return False


def enters(game, p, perm):
    """The "enters with" choices and rules, as perm enters the battlefield."""
    c = perm.card
    if c.bloodthirst and game.opponent(p).lost_life_turn:
        perm.counters["+1/+1"] = perm.p1 + c.bloodthirst
    if c.unleash:
        perm.counters["+1/+1"] = perm.p1 + 1
    if c.riot:
        if p is game.active and game.step in ("main1", "untap", "upkeep", "draw"):
            perm.perm_kw.add("haste")
        else:
            perm.counters["+1/+1"] = perm.p1 + 1


def upkeep(game, p):
    """Echo: at the beginning of your upkeep, pay the echo cost of what came under your control since your last one."""
    for perm in p.battlefield:
        if perm.card.echo and not getattr(perm, "echo_done", False):
            perm.echo_done = True
            game.queue_trigger(p, [_effect("echo")], perm, f"{perm.card.name}: echo")


def resolve(game, p, eff, target, item):
    from .engine import Permanent
    src = item.source if item is not None else None
    k = eff.kind
    if k == "echo":
        if isinstance(src, Permanent) and src in p.battlefield:
            cost = src.card.echo
            if game.can_pay(p, cost) and game.hook(p, "pay_optional")(game, p, cost, "echo"):
                game.pay(p, cost)
            else:
                game.sacrifice(src)
        return
    if not isinstance(src, Permanent) or src not in src.controller.battlefield:
        return
    if k == "evolve":
        new = item.context
        if isinstance(new, Permanent) and (new.power > src.power or new.toughness > src.toughness):
            src.counters["+1/+1"] = src.p1 + 1
    elif k == "renown":
        if not getattr(src, "renowned", False):
            src.counters["+1/+1"] = src.p1 + eff.amount
            src.renowned = True
    elif k == "fabricate":
        src.counters["+1/+1"] = src.p1 + eff.amount
    elif k == "mentor":
        from .engine import perm_value
        weaker = [a for a in game.attackers if a is not src and a.controller is p and a.power < src.power]
        if weaker:
            pick = max(weaker, key=perm_value)
            pick.counters["+1/+1"] = pick.p1 + 1
    elif k == "battle_cry":
        for a in game.attackers:
            if a is not src and a.controller is p:
                a.pump_p += 1
    elif k == "living_weapon":
        from .cards import make_token
        game._equip_on_enter = src         # attached before the 0/0 Germ would die
        game.enter_battlefield(p, make_token("Phyrexian Germ", 0, 0, colors=frozenset({"B"})))
        game.log(f"{src.card.name} is attached to a Germ token", p)
