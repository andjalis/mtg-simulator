"""Joint planning for mana and the supported single sacrifice/craft costs.

Tapping a permanent for mana and then sacrificing/exiling it is legal. Consuming
it for mana and again for another cost is not. This planner reserves only those
mana sources that would be consumed. It enumerates the supported victim choices,
then delegates colored mana and filter assignment to the existing mana solver.
"""
from dataclasses import dataclass
from itertools import combinations


@dataclass(frozen=True)
class PaymentPlan:
    cost: dict
    exclude: tuple
    sacrifice: object = None
    craft: object = None

    @property
    def victims(self):
        return self.sacrifice if isinstance(self.sacrifice, tuple) else (() if self.sacrifice is None else (self.sacrifice,))


def consumed_for_mana(permanent):
    return permanent.card.token_kind == 'treasure' or permanent.card.mana_sac


def plan(game, player, cost, *, spell='ability', sacrifices=((None, 0),),
         materials=(None,), exclude=(), consumed=()):
    from .engine import find_payment
    sources = game.mana_sources(player, spell=spell)
    for victim, tax in sacrifices:
        for material in materials:
            victims = victim if isinstance(victim, tuple) else (() if victim is None else (victim,))
            selected = list(victims) + ([material] if material is not None else []) + list(consumed)
            if len({id(x) for x in selected}) != len(selected):
                continue
            reserved = tuple(exclude) + tuple(x for x in selected if x in sources and consumed_for_mana(x))
            payable_cost = dict(cost)
            payable_cost['generic'] = payable_cost.get('generic', 0) + tax
            if find_payment([s for s in sources if s not in reserved], payable_cost) is not None:
                return PaymentPlan(payable_cost, reserved, victim, material)
    return None


def spell_plan(game, player, card, cost, *, exclude=()):
    options = [(None, 0)]
    if card.extra_sacrifice:
        candidates = game.extra_sac_candidates(player, card)
        options = [(c, 0) for c in candidates]
        if card.extra_sac_or_pay:
            # cost_of already includes this tax when there are no candidates.
            options.append((None, card.extra_sac_or_pay if candidates else 0))
    return plan(game, player, cost, spell=card, sacrifices=options, exclude=exclude)


def ability_plan(game, player, permanent, ability, cost):
    costs = ability.extra_costs
    victims = game.sacrifice_candidates(player, permanent, costs['sacrifice']) if costs.get('sacrifice') else []
    choices = ((tuple(v), 0) for v in combinations(victims, costs.get('sac_n', 1))) if costs.get('sacrifice') else ((None, 0),)
    materials = game.craft_materials(player, permanent) if costs.get('craft') else [None]
    consumed = [permanent] if costs.get('sac_self') or costs.get('exile_self') else []
    return plan(game, player, cost, sacrifices=choices, materials=materials,
                consumed=consumed, exclude=[permanent] if costs.get('tap') else [])
