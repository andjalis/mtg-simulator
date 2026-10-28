"""Handlers for dynamic amounts, linked targets, granted abilities and delayed moves."""
from ... import auras, backlog_templates
from ...cards import Effect
from ..state import Permanent
from . import kind


@kind('grant_activated')
def grant_activated(game, target, eff, **_):
    if isinstance(target, Permanent) and target in target.controller.battlefield:
        target.temp_activated.append(eff.data['ability'])


@kind('quantity_stats')
def quantity_stats(game, p, target, eff, **_):
    if isinstance(target, Permanent):
        n = backlog_templates.amount(game, p, eff.data['quantity'])
        def value(text):
            return (-1 if text.startswith('-') else 1) * (n if text[-1].upper() == 'X' else int(text[1:]))
        target.pump_p += value(eff.data['power'])
        target.pump_t += value(eff.data['toughness'])


@kind('return_grave_target')
def return_grave_target(game, p, target, eff, **_):
    if target not in p.graveyard:
        return
    if eff.data['dest'] == 'your hand':
        game.move_card(target, p.graveyard, p.hand, reason='return_grave_target')
    else:
        p.graveyard.remove(target)
        game.enter_battlefield(p, target, tapped=eff.data['tapped'])


@kind('blink_next_end')
def blink_next_end(game, target, item, **_):
    if not isinstance(target, Permanent):
        return
    owner, card = target.owner, target.front
    if game.leave_battlefield(target, 'exile') and not card.is_token and card in owner.exile:
        game.delayed_end_step.append((owner, [Effect('return_exile_ref')], item.source if item else None,
                                     (owner.exile, owner.exile.reference(card))))


@kind('return_exile_ref')
def return_exile_ref(game, item, **_):
    zone, ref = item.context
    card = ref.find(zone)
    if card is not None:
        zone.remove(card)
        game.enter_battlefield(card.owner, card)


@kind('relationship_mark')
def relationship_mark(game, **_):
    pass


def anchor(game, p, item):
    first = item.targets[0] if item and item.targets else None
    if not isinstance(first, Permanent) or first not in first.controller.battlefield:
        return None
    with game.targeting(item):
        return first if game.legal_target(p, item.effects[0], first) else None


@kind('transfer_between')
def transfer_between(game, p, target, eff, item, **_):
    first = anchor(game, p, item)
    if first is None or not isinstance(target, Permanent) or first is target:
        return
    name = eff.data['counter']
    available = max(0, first.counters.get(name, 0))
    if eff.data['count'] == 'any':
        chooser = getattr(p.ai, 'choose_counter_transfer', None)
        n = chooser(game, p, first, target, name, available) if chooser else available
        if not isinstance(n, int) or isinstance(n, bool) or not 0 <= n <= available:
            n = 0
    else:
        n = min(available, eff.data['count'])
    first.counters[name] = available - n
    target.counters[name] = target.counters.get(name, 0) + n


@kind('move_aura', 'move_auras')
def move_auras(game, p, target, eff, item, **_):
    first = anchor(game, p, item)
    if first is None or not isinstance(target, Permanent):
        return
    moving = [first] if eff.kind == 'move_aura' else list(first.auras)
    for aura in moving:
        if auras.can_attach(game, aura.controller, aura.card, target, source=aura, targeting=False):
            auras.detach(aura)
            auras.attach(game, aura, target)


@kind('player_action_lock')
def player_action_lock(game, target, **_):
    if target in game.players:
        target.action_lock_turn = game.turn
