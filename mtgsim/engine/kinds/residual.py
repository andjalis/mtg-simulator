"""Shared mass moves, graveyard actions, Adapt, and triggered casting."""
from ... import counter_mechanics, permanent_templates
from ...cards import AltCost
from ..state import Permanent
from . import kind


@kind('selected_mass_move')
def selected_mass_move(game, p, eff, item, **_):
    src = item.source if item else None
    victims = [x for pl in game.players for x in pl.battlefield
               if permanent_templates.matches(game, x, eff.data['selector'], p, src)]
    snapshots = counter_mechanics.death_sources(game)
    for victim in victims:
        if eff.data['dest'] == 'graveyard':
            game.destroy(victim, counter_sources=snapshots, no_regen=eff.data.get("no_regen", False))
        else:
            game.leave_battlefield(victim, 'hand')


@kind('filtered_grave_return')
def filtered_grave_return(game, p, eff, **_):
    for card in list(p.graveyard):
        value = card.cmc if eff.data['stat'] == 'mana value' else getattr(card, eff.data['stat'])
        if eff.data['type'].title() in card.types and value is not None and ((value <= eff.amount) if eff.data['less'] else (value >= eff.amount)):
            game.move_card(card, p.graveyard, p.hand)


@kind('graveyard_exile_all', 'graveyard_exile_choice')
def graveyard_exile(game, p, eff, target, **_):
    players = [target] if target in game.players else game.players if eff.target == 'none' else []
    for player in players:
        cards = list(player.graveyard)
        if eff.kind == 'graveyard_exile_choice' and cards:
            chooser = getattr(player.ai, 'choose_grave_exile', None)
            chosen = chooser(game, player, cards) if chooser else min(cards, key=lambda c: c.cmc)
            cards = [chosen] if any(chosen is c for c in cards) else [cards[0]]
        for card in cards:
            game.move_card(card, player.graveyard, player.exile)


@kind('counter_context')
def counter_context(game, p, item, **_):
    from ...cards import Effect
    if item is not None:
        game.counter(p, Effect('counter'), item.context)


@kind('destroy_idle_host')
def destroy_idle_host(game, item, **_):
    host = item.context if item else None
    if isinstance(host, Permanent) and host in host.controller.battlefield and getattr(host, 'attack_count', (None, 0))[0] != game.turn:
        game.destroy(host)


@kind('adapt_exception')
def adapt_exception(game, target, **_):
    if isinstance(target, Permanent):
        target.adapt_exceptions = getattr(target, 'adapt_exceptions', 0) + 1


@kind('adapt')
def adapt(game, target, eff, **_):
    if not isinstance(target, Permanent):
        return
    exceptions = getattr(target, 'adapt_exceptions', 0)
    if exceptions:
        target.adapt_exceptions -= 1
    if not target.p1 or exceptions:
        target.counters['+1/+1'] = target.p1 + eff.amount


@kind('miracle_cast')
def miracle_cast(game, p, item, **_):
    zone, ref, cost = item.context
    card = ref.find(zone)
    if card is None:
        return
    chooser = getattr(p.ai, 'cast_miracle', None)
    if chooser and not chooser(game, p, card):
        return
    previous = getattr(game, '_miracle_permission', None)
    game._miracle_permission = (p, card)
    try:
        game.cast(p, game._variant(card, 'miracle', AltCost('miracle', cost)))
    finally:
        game._miracle_permission = previous


@kind('pay_energy')
def pay_energy(game, p, eff, item, **_):
    """An energy pay gate ("you may pay {E}{E}. If you do, ...", energy_templates.py):
    pay the counters when there are enough, and mark the item so the cond "paid"
    payoff effects after it resolve (the pay_gate pattern)."""
    if item is not None:
        item.gate_paid = p.counters.get('energy', 0) >= eff.amount
        if item.gate_paid:
            p.counters['energy'] -= eff.amount
            game.log(f"pays {eff.amount} energy", p)
