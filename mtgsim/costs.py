"""Joint planning for mana and supported sacrifice, craft and counter-removal costs.

Tapping a permanent for mana and then sacrificing/exiling it is legal. Consuming
it for mana and again for another cost is not. This planner reserves only those
mana sources that would be consumed. It enumerates the supported victim choices,
then delegates colored mana and filter assignment to the existing mana solver.
"""
from dataclasses import dataclass, replace
from itertools import combinations


@dataclass(frozen=True)
class PaymentPlan:
    cost: dict
    exclude: tuple
    sacrifice: object = None
    craft: object = None
    counter_payments: tuple = ()
    exile_gy_card: object = None      # "Exile a(n) <desc> card from your graveyard" cost: the chosen card

    @property
    def victims(self):
        return self.sacrifice if isinstance(self.sacrifice, tuple) else (() if self.sacrifice is None else (self.sacrifice,))


def consumed_for_mana(permanent):
    return permanent.card.token_kind == 'treasure' or permanent.card.mana_sac or permanent.card.mana_sac_only


def _gy_payout_stat(effects):
    """The stat an effect reads off the graveyard card exiled as a cost ("deals damage equal
    to the exiled card's power": Molten-Tail Masticore, Corpse Lunge), or None when the
    exile is a plain cost. Tolerant of effects without an x-quantity."""
    for e in effects:
        data = getattr(e, "data", None)
        spec = data.get("xq") if isinstance(data, dict) else None
        if spec and spec[0] == "exiled_gy":
            return spec[1] if len(spec) > 1 else "power"
    return None


def _pick_gy_exile(effects, candidates):
    """The card to exile from the graveyard: the best stat when the payout scales with it,
    else the least valuable candidate (a plain cost)."""
    stat = _gy_payout_stat(effects)
    if stat is None:
        return candidates[0]
    read = {"power": lambda c: int(getattr(c, "power", 0) or 0),
            "toughness": lambda c: int(getattr(c, "toughness", 0) or 0),
            "mana value": lambda c: c.cmc}.get(stat, lambda c: 0)
    return max(candidates, key=lambda c: (read(c), -c.cmc))


def counter_effects(ability, payment):
    """Preview counter X for target selection without changing the blueprint."""
    if ability.extra_costs.get('remove_creature_counters') not in ('x', 'positive'):
        return ability.effects
    amount = sum(n for _, _, n in payment.counter_payments)
    return [replace(e, amount=amount, amount2=amount if e.data.get('x2') else e.amount2)
            if e.data.get('x') else e for e in ability.effects]


def plan(game, player, cost, *, spell='ability', sacrifices=((None, 0),),
         materials=(None,), exclude=(), consumed=(), reserved_counters=()):
    from .engine import find_payment
    sources = game.mana_sources(player, spell=spell, reserved_counters=reserved_counters)
    for victim, tax in sacrifices:
        for material in materials:
            victims = victim if isinstance(victim, tuple) else (() if victim is None else (victim,))
            selected = list(victims) + ([material] if material is not None else []) + list(consumed)
            if len({id(x) for x in selected}) != len(selected):
                continue
            reserved = tuple(exclude) + tuple(x for x in selected if x in sources and consumed_for_mana(x))
            payable_cost = dict(cost)
            payable_cost['generic'] = max(0, payable_cost.get('generic', 0) + tax)
            if find_payment([s for s in sources if s not in reserved and getattr(s, 'stored_in', None) not in reserved], payable_cost) is not None:
                return PaymentPlan(payable_cost, reserved, victim, material)
    return None


def spell_plan(game, player, card, cost, *, exclude=()):
    from . import emerge
    options = [(None, 0)]
    if card.extra_sacrifice:
        candidates = game.extra_sac_candidates(player, card)
        options = [(c, 0) for c in candidates]
        if game._origin(card)[1] == "emerge":
            options = emerge.sacrifice_options(game, player, card, candidates)
        if card.extra_sac_or_pay:
            # cost_of already includes this tax when there are no candidates.
            options.append((None, card.extra_sac_or_pay if candidates else 0))
    result = plan(game, player, cost, spell=card, sacrifices=options, exclude=exclude)
    if result is not None and getattr(card, "extra_exile_gy", ""):
        # The exiled graveyard card never feeds the mana payment, so the candidate can be
        # attached after planning (can_cast_now gates on candidates existing). A payout that
        # scales with the exiled card (Corpse Lunge) wants the best stat, not the cheapest.
        result = replace(result, exile_gy_card=_pick_gy_exile(
            card.spell_effects, game.gy_exile_candidates(player, card.extra_exile_gy)))
    return result


def ability_plan(game, player, permanent, ability, cost, *, x=None, counter_choices=None):
    costs = ability.extra_costs
    if x is not None and (not isinstance(x, int) or isinstance(x, bool) or x < 0):
        return None
    if not game.can_pay(player, cost):
        return None
    victims = game.sacrifice_candidates(player, permanent, costs['sacrifice']) if costs.get('sacrifice') else []
    materials = game.craft_materials(player, permanent) if costs.get('craft') else [None]
    consumed = [permanent] if costs.get('sac_self') or costs.get('exile_self') else []
    for counters in creature_counter_payments(player, permanent, costs, x=x, choices=counter_choices):
        choices = ((tuple(v), 0) for v in combinations(victims, costs.get('sac_n', 1))) if costs.get('sacrifice') else ((None, 0),)
        # Mana abilities are used before paying the other costs. A donor must
        # therefore survive mana payment, but can be sacrificed as a later cost.
        excluded = [permanent] if costs.get('tap') else []
        excluded += [donor for donor, _, _ in counters if consumed_for_mana(donor)]
        own = ((permanent, costs['remove_counter'], costs.get('remove_counter_count', 1)),) if costs.get('remove_counter') else ()
        if own and consumed_for_mana(permanent):
            excluded.append(permanent)
        result = plan(game, player, cost, sacrifices=choices, materials=materials,
                      consumed=consumed, exclude=excluded, reserved_counters=counters + own)
        if result is not None:
            result = replace(result, counter_payments=counters)
            if costs.get('exile_gy_card'):
                result = replace(result, exile_gy_card=_pick_gy_exile(
                    ability.effects, game.gy_exile_candidates(player, costs['exile_gy_card'])))
            return result
    return None


def creature_counter_payments(player, source, costs, *, x=None, choices=None):
    """Allocate fixed/variable creature counter costs without changing state.

    Explicit choices are (permanent, counter type, amount) triples. Otherwise
    prefer non-stat counters, and try alternate donors to preserve usable mana.
    """
    from .engine.policy import perm_value
    spec = costs.get('remove_creature_counters', 0)
    if not spec:
        if choices or x not in (None, 0):
            return
        yield ()
        return
    counter_kind = costs.get('creature_counter_kind', '+1/+1')
    donors = []
    for donor in player.creatures:
        for kind, count in donor.counters.items():
            if counter_kind != 'any' and kind != counter_kind:
                continue
            count -= costs.get('remove_counter_count', 1) if donor is source and costs.get('remove_counter') == kind else 0
            if count > 0:
                donors.append((donor, kind, count))
    donors.sort(key=lambda v: (v[1] == '+1/+1', consumed_for_mana(v[0]), perm_value(v[0]), v[1]))
    minimum = 1 if spec == 'positive' else 0
    if choices is not None:
        selected = {}
        for donor, kind, n in choices:
            if not isinstance(n, int) or isinstance(n, bool) or n <= 0:
                return
            selected[donor, kind] = selected.get((donor, kind), 0) + n
        available = {(donor, kind): n for donor, kind, n in donors}
        if any(n > available.get(key, 0) for key, n in selected.items()):
            return
        amount = sum(selected.values())
        if isinstance(spec, int) and amount != spec or amount < minimum or x is not None and amount != x:
            return
        yield tuple((donor, kind, n) for (donor, kind), n in selected.items())
        return
    totals = [0] * (len(donors) + 1)
    for i in range(len(donors) - 1, -1, -1):
        totals[i] = totals[i + 1] + donors[i][2]

    if isinstance(spec, int):
        amounts = (spec,) if x in (None, spec) else ()
    elif x is not None:
        amounts = (x,) if isinstance(x, int) and not isinstance(x, bool) and minimum <= x <= totals[0] else ()
    else:
        amounts = range(totals[0], minimum - 1, -1)

    def allocate(i, remaining, chosen):
        if remaining == 0:
            yield chosen
        elif i < len(donors) and totals[i] >= remaining:
            donor, kind, available = donors[i]
            for n in range(min(remaining, available), -1, -1):
                yield from allocate(i + 1, remaining - n, chosen + ((donor, kind, n),) if n else chosen)

    for needed in amounts:
        yield from allocate(0, needed, ())
