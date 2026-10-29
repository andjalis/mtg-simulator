"""Other effect kinds: the stack, mana, costs and one-off mechanics."""
from __future__ import annotations

import dataclasses

from ...cards import Activated, make_token
from ..policy import choose_earthbend
from ..state import FIREBEND_MANA, Permanent, StackItem, pool_mana
from . import kind


@kind("craft")
def craft(game, p, item, **_):
    card = item.source.front if item and item.source else None
    if card is not None and card in p.exile and card.back is not None:
        p.exile.remove(card)
        game.enter_battlefield(p, card.back, physical_card=card)
        game.log(f"crafts {card.back.name}", p)


@kind("counter", "bounce_spell")
def counter(game, p, eff, target, item, **_):
    if eff.data.get("tw") and getattr(item, "teamwork", False):
        eff = dataclasses.replace(eff, amount=eff.data["tw"])
    game.counter(p, eff, target)


@kind("add_mana")
def add_mana(game, p, eff, **_):
    for color in eff.data["colors"]:
        card = pool_mana(color)
        if eff.data.get("restriction"):
            card = dataclasses.replace(card, produces=frozenset(), restricted_produces=frozenset({color}),
                                       mana_restriction=eff.data["restriction"], restricted_mana_amount=1)
        p.pool.append(Permanent(card, p))
    game.log(f"adds {''.join(eff.data['colors'])}", p)


@kind("firebend")
def firebend(game, p, eff, item, **_):
    src = item.source if item is not None else None
    n = eff.amount
    if eff.data.get("x") == "power" and isinstance(src, Permanent):
        n = max(0, src.power)
    elif eff.data.get("x") == "creatures":
        n = len(p.creatures)
    for _ in range(n):
        mana = Permanent(FIREBEND_MANA, p)
        p.pool.append(mana)
    game.log(f"adds {n} red mana (firebending)", p)


@kind("pay_gate")
def pay_gate(game, p, eff, item, **_):
    if item is not None:
        item.gate_paid = False
        if "gate" in eff.data:
            item.gate_paid = game.pay_gate_cost(p, eff.data["gate"], item)
        elif game.can_pay(p, eff.data["cost"], spell="ability") and game.hook(p, "pay_optional")(game, p, eff.data["cost"], "gate"):
            game.pay(p, eff.data["cost"])
            item.gate_paid = True


@kind("job_select")
def job_select(game, p, item, **_):
    src = item.source if item is not None else None
    hero = game.enter_battlefield(p, dataclasses.replace(make_token("Hero", 1, 1), subtypes=frozenset({"Hero"})))
    if src is not None and src in p.battlefield and src.card.equip_cost is not None:
        src.attached_to = hero
        game.log(f"{src.card.name} attaches to the Hero", p)


@kind("discover")
def discover(game, p, eff, target, **_):
    skipped = []
    found = None
    limit = eff.amount
    if eff.data.get("x_of"):
        limit = target.card.cmc if isinstance(target, StackItem) and target.card else 0
    p.discovered_cmc = None
    while p.library:
        c = p.library.pop()
        p.exile.append(c)
        if not c.is_land and c.cmc <= limit:
            found = c
            break
        skipped.append(c)
    if found is not None:
        p.discovered_cmc = found.cmc
        game.log(f"discovers {found.name}", p)
        if not game.cast_free(p, found):
            game.log(f"puts {found.name} into their hand", p)
    game.rng.shuffle(skipped)
    for c in skipped:
        p.exile.remove(c)
    p.library[0:0] = skipped


@kind("earthbend")
def earthbend(game, p, eff, **_):
    land = choose_earthbend(game, p)
    if land is not None:
        # Target land you control becomes a 0/0 creature with haste that's still a land.
        land.animated = Activated("animate", {}, 0, 0, frozenset({"haste"}), text="earthbend")
        land.counters["+1/+1"] = land.p1 + eff.amount
        game.log(f"earthbends {land.card.name} ({eff.amount})", p)


@kind("counter_ability")
def counter_ability(game, p, eff, target, **_):
    from ... import cost_mana
    if isinstance(target, StackItem) and target in game.stack and cost_mana.can_counter_ability(eff, target):
        game.stack.remove(target)
        game.log(f"{target} is countered", p)


@kind("bounce_land_own")
def bounce_land_own(game, p, item, **_):
    lands = [x for x in p.battlefield if x.card.is_land]
    if lands:
        chosen = min(lands, key=lambda x: (x is getattr(item, "source", None), not x.tapped))
        game.leave_battlefield(chosen, "hand")
        game.log(f"returns {chosen.card.name} to its owner's hand", p)


@kind("solve_case")
def solve_case(game, p, eff, item, **_):
    source = item.source if item is not None else None
    if source is not None and source in source.controller.battlefield and not source.solved and \
            p.life_gained_turn >= eff.amount:
        source.solved = True
        game.log(f"solves {source.card.name}", p)


@kind("grant_gy_cast")
def grant_gy_cast(game, p, **_):
    from ... import cost_mana
    cost_mana.grant_gy_cast(game, p)
