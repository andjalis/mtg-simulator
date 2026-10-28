"""Counter transfers, linked exile and identity-safe delayed returns."""
from ...cards import make_token, Effect
from ...identity import CardInstance
from ..state import Permanent, COLOR_WORDS
from . import kind


@kind('modify_counters')
def modify_counters(game, target, eff, **_):
    if isinstance(target, Permanent) and target in target.controller.battlefield:
        names = [eff.data['counter']] if 'counter' in eff.data else list(target.counters)
        for name in names:
            count = target.counters.get(name, 0)
            target.counters[name] = count * 2 if eff.data['operation'] == 'double' else max(0, count - eff.amount)


@kind('permanent_group')
def permanent_group(game, p, item, eff, **_):
    from ...permanent_templates import matches
    from . import HANDLERS
    source = item.source if item else None
    victims = [x for player in game.players for x in player.battlefield
               if matches(game, x, eff.data['selector'], p, source)]
    effects = eff.data.get('effects', [eff.data.get('effect')])
    # Apply the whole group before state-based actions (not one lethal creature at a time).
    for target in victims:
        for inner in effects:
            HANDLERS[inner.kind](game, p=p, eff=inner, target=target, item=item, opp=game.opponent(p))


@kind('graft_move')
def graft_move(game, p, item, **_):
    source, recipient = item.source, item.context
    if (not isinstance(source, Permanent) or source not in source.controller.battlefield or not source.p1
            or not isinstance(recipient, Permanent) or recipient not in recipient.controller.battlefield
            or recipient is source):
        return
    choose = getattr(p.ai, 'choose_graft', None)
    if choose(game, p, source, recipient) if choose else recipient.controller is p:
        source.counters['+1/+1'] -= 1
        recipient.counters['+1/+1'] = recipient.p1 + 1


@kind('inherit_counters')
def inherit_counters(game, eff, target, item, **_):
    if isinstance(target, Permanent):
        counters = eff.data.get('counters', dict(item.source.counters) if item and item.source else {})
        for name, amount in counters.items():
            if amount > 0:
                target.counters[name] = target.counters.get(name, 0) + amount


@kind('counter_token')
def counter_token(game, p, eff, item, **_):
    n = getattr(item, 'counter_x', 0)
    token = make_token(eff.data['name'].title(), n, n, colors={COLOR_WORDS[eff.data['color']]})
    game.enter_battlefield(p, token)


@kind('linked_exile')
def linked_exile(game, p, target, item, **_):
    source = item.source if item else None
    if not isinstance(source, Permanent):
        return
    if isinstance(target, Permanent):
        card, owner = target.front, target.owner
        if not game.leave_battlefield(target, 'exile') or card not in owner.exile:
            return
    elif isinstance(target, CardInstance) and target in target.owner.graveyard:
        card, owner = target, target.owner
        game.move_card(card, owner.graveyard, owner.exile, reason='linked_exile')
    else:
        return
    if not hasattr(source, 'linked_exiles'):
        source.linked_exiles = []
    source.linked_exiles.append((owner.exile, owner.exile.reference(card)))


@kind('linked_return')
def linked_return(game, item, **_):
    source = item.source if item else None
    if source is None:
        return
    returning = getattr(source, 'linked_exiles', [])
    source.linked_exiles = []
    for zone, ref in returning:
        card = ref.find(zone)
        if card is not None:
            zone.remove(card)
            game.enter_battlefield(card.owner, card)


@kind('schedule_counter_return')
def schedule_counter_return(game, p, item, **_):
    if item and item.context:
        game.delayed_end_step.append((p, [Effect('delayed_counter_return')], item.source, item.context))


@kind('delayed_counter_return')
def delayed_counter_return(game, p, item, **_):
    zone, ref = item.context
    if zone is None or ref is None:
        return
    card = ref.find(zone)
    if card is not None:
        zone.remove(card)
        game.enter_battlefield(p, card)


@kind('additional_combat')
def additional_combat(game, **_):
    for attacker in game.attackers:
        if attacker in attacker.controller.battlefield:
            attacker.tapped = False
    game.extra_combats += 1


@kind('counter_team')
def counter_team(game, p, item, **_):
    for creature in list(p.creatures):
        if creature is not item.source and creature.p1 > 0:
            creature.counters['+1/+1'] = creature.p1 + 1


@kind('move_counter_self')
def move_counter_self(game, target, item, **_):
    source = item.source if item else None
    if (isinstance(source, Permanent) and source in source.controller.battlefield
            and isinstance(target, Permanent) and target in target.controller.battlefield
            and target is not source and target.p1 > 0):
        target.counters['+1/+1'] -= 1
        source.counters['+1/+1'] = source.p1 + 1


@kind('source_control')
def source_control(game, p, target, item, **_):
    from ... import counter_mechanics
    source = item.source if item else None
    if isinstance(source, Permanent) and source in source.controller.battlefield and isinstance(target, Permanent):
        counter_mechanics.add_control(game, target, p, source=source)


@kind('grant_combat_destroy')
def grant_combat_destroy(game, target, **_):
    from ...cards import Trigger
    if isinstance(target, Permanent):
        target.temp_triggers.append(Trigger('combat_damage_creature', [Effect('end_of_combat', data={
            'effects': [Effect('destroy', target='prev')]
        })]))


@kind('exile_permanent')
def exile_permanent(game, target, **_):
    if isinstance(target, Permanent):
        game.leave_battlefield(target, 'exile')


@kind('grant_triggers')
def grant_triggers(game, target, eff, **_):
    if isinstance(target, Permanent) and target in target.controller.battlefield:
        target.temp_triggers.extend(eff.data['triggers'])
