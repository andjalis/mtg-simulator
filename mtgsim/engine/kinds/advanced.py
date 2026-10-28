"""Effects for shared quantities, control, player resources and zone permissions."""
from ... import counter_mechanics
from ..state import Permanent, StackItem
from . import kind


@kind('energy')
def energy(game, p, eff, **_):
    p.counters['energy'] = p.counters.get('energy', 0) + eff.amount


@kind('allocated_counter')
def allocated_counter(game, target, eff, item, **_):
    if not isinstance(target, Permanent):
        return
    if item is None:
        target.counters['+1/+1'] = target.p1 + eff.amount
        return
    if not hasattr(item, 'allocated_done'):
        item.allocated_done = set()
    if target not in item.allocated_done:
        item.allocated_done.add(target)
        n = sum(e.amount for e, t in zip(item.effects, item.targets) if e.kind == 'allocated_counter' and t is target)
        target.counters['+1/+1'] = target.p1 + n


@kind('advanced_quantity_stats')
def quantity_stats(game, p, target, item, eff, **_):
    if not isinstance(target, Permanent):
        return
    if eff.data['quantity'].startswith('the amount'):
        spell = getattr(item, 'context', None)
        n = getattr(spell, 'mana_spent', 0) + getattr(spell, 'x', 0)
    else:
        n = len({c.cmc for c in p.graveyard})
    def value(text):
        return (-1 if text.startswith('-') else 1) * (n if text[-1] == 'x' else int(text[1:]))
    effect = game.add_continuous_effect(target, 'modify', power=value(eff.data['power']),
                                        toughness=value(eff.data['toughness']), until_eot=not eff.data['next_turn'])
    if eff.data['next_turn']:
        if not hasattr(game, 'next_turn_modifiers'):
            game.next_turn_modifiers = []
        game.next_turn_modifiers.append((p, effect))


@kind('return_tribal_grave', 'grave_library_top')
def grave_move(game, p, target, eff, **_):
    if target is not None and target in p.graveyard:
        game.move_card(target, p.graveyard, p.library if eff.kind == 'grave_library_top' else p.hand)


@kind('control_permanent')
def control(game, p, target, eff, item, **_):
    if isinstance(target, Permanent):
        source = item.source if item and eff.data['source_bound'] else None
        if not eff.data['source_bound'] or isinstance(source, Permanent) and source in source.controller.battlefield:
            counter_mechanics.add_control(game, target, p, source=source)


@kind('opponent_draw_gate')
def draw_gate(game, p, eff, item, **_):
    payer = item.context if item is not None else game.opponent(p)
    if isinstance(payer, StackItem):
        payer = payer.controller
    if payer not in game.players:
        payer = game.opponent(p)
    cost = {'generic': eff.amount}
    if not (game.can_pay(payer, cost) and game.hook(payer, 'pay_optional')(game, payer, cost, 'prevent draw') and
            game.pay(payer, cost) is not None):
        game.draw(p)


@kind('populate')
def populate(game, p, **_):
    from ...copies import make_copy
    tokens = [x for x in p.creatures if x.card.is_token]
    if tokens:
        from ..policy import perm_value
        chooser = getattr(p.ai, "choose_populate", None)
        chosen = chooser(game, p, tokens) if chooser else max(tokens, key=perm_value)
        if chosen not in tokens:
            return
        from ...backlog_templates import entry_batch
        count = 2 ** sum(bool(x.card.token_double) for x in p.battlefield if not x.abilities_suppressed)
        with entry_batch(game):
            for _ in range(count):
                game.enter_battlefield(p, make_copy(chosen.copiable_card, {}))


@kind('opponent_exile')
def opponent_exile(game, p, target, item, eff, **_):
    if target not in game.players or target is p:
        return
    cards = list(target.library[-eff.amount:])
    if not cards:
        return
    chooser = getattr(p.ai, 'choose_exile_card', None)
    chosen = chooser(game, p, cards) if chooser else max(cards, key=lambda c: c.cmc)
    if chosen not in cards:
        chosen = cards[-1]
    for c in cards:
        target.library.remove(c)
    target.exile.append(chosen)
    chosen.face_down_exile = True
    remaining = [c for c in cards if c is not chosen]
    game.rng.shuffle(remaining)
    for c in remaining:
        target.library.insert(0, c)
    item.exiled_choice = (target.exile, target.exile.reference(chosen))


@kind('exile_permission')
def exile_permission(game, p, item, **_):
    choice = getattr(item, 'exiled_choice', None)
    if choice:
        if not hasattr(p, 'foreign_permissions'):
            p.foreign_permissions = []
        p.foreign_permissions.append(choice)


@kind('cipher_cast')
def cipher_cast(game, p, item, **_):
    import dataclasses
    zone, ref = item.context
    card = ref.find(zone)
    if card is None:
        return
    chooser = getattr(p.ai, "choose_cipher_cast", None)
    if chooser and not chooser(game, p, card):
        return
    copy = dataclasses.replace(card, name=card.name + ' (cipher copy)')
    p.hand.append(copy)
    copy = p.hand[-1]
    copy.spell_copy = True
    targets = game.auto_targets(p, copy.spell_effects, copy)
    from ..state import TARGETED
    with game.targeting(copy):
        for i, eff in enumerate(copy.spell_effects):
            if eff.target in TARGETED and targets[i] is None:
                legal = game.legal_targets(p, eff)
                targets[i] = legal[0] if legal else None
    if not game.cast(p, copy, targets) and copy in p.hand:
        p.hand.remove(copy)
