"""Reusable rule boundaries for the thirty-item residual capability batch.

Only complete recognized clauses are consumed. Static flags describe rules rather
than card identities; optional choices have deterministic policy defaults.
"""
from __future__ import annotations

import dataclasses
import re

EFFECT_PATTERNS = []
SUBS = []


def rules(permanent):
    return {} if permanent.abilities_suppressed else permanent.card.advanced_rules


def parse_line(line, state):
    from .cards import Trigger
    static = {
        "Spells and abilities your opponents control can't cause you to sacrifice permanents.": ('sac_protection', True),
        'You control enchanted creature.': ('aura_control', True),
        'Each opponent can\'t draw more than one card each turn.': ('draw_limit', 1),
        'If an opponent would draw a card except the first one they draw in each of their draw steps, instead that player skips that draw and you draw a card.': ('draw_steal', True),
        'If a card or token would be put into a graveyard from anywhere, exile it instead.': ('grave_exile', True),
        'If one or more +1/+1 counters would be put on a creature you control, that many plus one +1/+1 counters are put on it instead.': ('counter_plus', 1),
        'If you would create a Clue, Food, or Treasure token, instead create one of each.': ('manufactor', True),
        'Nonbasic lands are Mountains.': ('land_conversion', 'Mountain'),
        'Sunburst': ('sunburst', True),
        'Cipher': ('cipher', True),
        'Aftermath': ('aftermath', True),
        "Each opponent can't cast noncreature spells with mana value greater than the number of lands that player controls.": ('land_cast_limit', True),
    }
    match = static.get(line)
    m = re.fullmatch(r"Creatures can't attack you unless their controller pays \{(\d+)\} for each creature they control that's attacking you\.", line)
    if m:
        match = ('attack_tax', int(m[1]))
    m = re.fullmatch(r"Activated abilities of creatures you control cost \{(\d+)\} less to activate\. This effect can't reduce the mana in that cost to less than one mana\.", line)
    if m:
        match = ('activation_discount', int(m[1]))
    if line == 'During each of your turns, you may cast an instant or sorcery spell from your graveyard. If a spell cast this way would be put into your graveyard, exile it instead.':
        match = ('grave_cast', True)
    if match:
        state.extra.setdefault('advanced_rules', {})[match[0]] = match[1]
        return True
    if line.startswith('Enchant non-') and 'Aura' in state.type_line:
        from .permanent_templates import selector
        spec = selector(line[8:])
        if spec is not None:
            state.extra['aura'] = line[8:]
            state.extra.setdefault('advanced_rules', {})['aura_selector'] = spec
            return True
    m = re.fullmatch(r'When ~ enters untapped, (.+)', line)
    if m:
        from .cards.parse import _parse_effects
        effects, bad = _parse_effects(m[1])
        if effects and not bad:
            state.triggers.append(Trigger('etb', effects, data={'enters_untapped': True}))
            return True
    return False


def parse_effect(text, previous):
    from .cards import Effect, _num
    s = text.lower().strip().rstrip('.')
    if s == 'populate':
        return [Effect('populate')]
    m = re.fullmatch(r'you get ((?:\{e\})+)', s)
    if m:
        return [Effect('energy', m[1].count('{e}'))]
    m = re.fullmatch(r'(?:you may )?draw a card unless that player pays \{(\d+)\}', s)
    if m:
        return [Effect('opponent_draw_gate', int(m[1]))]
    m = re.fullmatch(r'gain control of target (creature|permanent)( for as long as ~ remains on the battlefield)?', s)
    if m:
        return [Effect('control_permanent', target=m[1], data={'source_bound': bool(m[2])})]
    m = re.fullmatch(r'distribute (one|two|three|four|five|six|seven|eight|nine|ten|\d+) \+1/\+1 counters among any number of target creatures', s)
    if m:
        n = _num(m[1])
        if n > 0:
            # One declared allocation slot per counter. Repeated slots designate
            # one target with that total; every counter is assigned before payment.
            return [Effect('allocated_counter', 1, target='creature', data={'allocation': True}) for _ in range(n)]
    m = re.fullmatch(r'return up to (one|two|three|four|five|six|seven|eight|nine|ten|\d+) target creature cards of the creature type of your choice from your graveyard to your hand', s)
    if m:
        return [Effect('return_tribal_grave', target='graveyard_card', data={'grave_type': 'creature', 'optional_target': True,
                       'tribal_group': True, 'slot': i}) for i in range(_num(m[1]))]
    m = re.fullmatch(r'(?:you may )?put target (instant or sorcery|creature|artifact|enchantment) card from your graveyard on top of your library', s)
    if m:
        return [Effect('grave_library_top', target='graveyard_card', data={'grave_type': m[1]})]
    m = re.fullmatch(r'(.+?) gets ([+-][x\d]+)/([+-][x\d]+) until (end of turn|your next turn), where x is (.+)', s)
    if m:
        from .permanent_templates import subject
        obj = subject(m[1])
        quantity = m[5]
        if obj is not None and quantity in ('the amount of mana spent to cast that spell', 'the number of different mana values among cards in your graveyard'):
            target, data = obj
            return [Effect('advanced_quantity_stats', target=target, data=dict(data, power=m[2], toughness=m[3],
                           quantity=quantity, next_turn=m[4] == 'your next turn'))]
    m = re.fullmatch(r'it has "(.+)"', text.strip().rstrip('.'), re.I)
    if m and previous and previous[-1].kind == 'token':
        from .backlog_templates import ability
        act = ability(m[1].rstrip('.') + '.')
        if act:
            previous[-1] = dataclasses.replace(previous[-1], data=dict(previous[-1].data, activated=[act]))
            return []
    if s == 'look at the top four cards of target opponent\'s library, exile one of them face down, then put the rest on the bottom of that library in a random order':
        return [Effect('opponent_exile', 4, target='player', filter='opp')]
    if s == 'you may cast that card for as long as it remains exiled, and mana of any type can be spent to cast that spell':
        return [Effect('exile_permission')]
    return None


def grave_targets(game, p, eff):
    types = eff.data['grave_type'].split(' or ')
    cards = [c for c in p.graveyard if ('cmc_exact' not in eff.data or c.cmc == eff.data['cmc_exact']) and
             any(c.is_permanent if t == 'permanent' else t.title() in c.types for t in types)]
    if eff.data.get('tribal_group'):
        from .permanent_templates import _CREATURE_SUBTYPES
        def creature_types(c):
            return {t.lower() for t in c.subtypes} & _CREATURE_SUBTYPES
        cards = [c for c in cards if c.changeling or creature_types(c)]
        chosen = getattr(game, '_choosing_targets', None)
        if chosen is None:
            item = game.target_source
            chosen = getattr(item, 'targets', [])
        earlier = [c for c in chosen[:eff.data['slot']] if c is not None]
        if earlier:
            ordinary = [c for c in earlier if not c.changeling]
            shared = creature_types(ordinary[0]) if ordinary else set()
            for c in ordinary[1:]:
                shared.intersection_update(creature_types(c))
            cards = [c for c in cards if all(c is not x for x in earlier) and
                     (c.changeling or not ordinary or bool(shared & creature_types(c)))]
    return cards


def activation_cost(game, p, permanent, cost):
    if not permanent.is_creature:
        return cost
    discount = sum(rules(x).get('activation_discount', 0) for x in p.battlefield)
    if not discount:
        return cost
    out = dict(cost)
    colored = sum(v for k, v in out.items() if k not in ('generic', 'X'))
    out['generic'] = max(0 if colored else min(1, out.get('generic', 0)), out.get('generic', 0) - discount)
    return out


def counter_amount(permanent, name, amount):
    if name == '+1/+1' and permanent.is_creature:
        amount += sum(rules(x).get('counter_plus', 0) for x in permanent.controller.battlefield)
    return amount


def draw_recipient(game, p, replaced=()):
    count = getattr(p, 'drawn_turn', (None, 0))
    drawn = count[1] if count[0] == game.turn else 0
    opp = game.opponent(p)
    if drawn >= 1 and any(rules(x).get('draw_limit') for x in opp.battlefield):
        return None, None
    in_draw = game.active is p and game.step == 'draw'
    key = (game.turn, getattr(game, 'draw_step_serial', 0))
    first = in_draw and getattr(p, '_advanced_draw_step', None) != key
    if not first:
        source = next((x for x in opp.battlefield if rules(x).get('draw_steal') and x not in replaced), None)
        if source is not None:
            return opp, source
    return p, None


def begin_turn(game, p):
    waiting = getattr(game, 'next_turn_modifiers', [])
    for controller, effect in list(waiting):
        if controller is p:
            if effect in game.continuous_effects:
                game.continuous_effects.remove(effect)
            waiting.remove((controller, effect))


def attack_tax(game, defender):
    return sum(rules(x).get('attack_tax', 0) for x in defender.battlefield)


def cast_allowed(game, p, card):
    from .residual_templates import cast_locked
    if cast_locked(game, p, card):
        return False
    if not card.is_creature and any(rules(x).get('land_cast_limit') for x in game.opponent(p).battlefield):
        return card.cmc <= sum(x.card.is_land for x in p.battlefield)
    return True


def payment_colors(payment, cost):
    """Choose an explicit legal color for each paid unit, favoring sunburst."""
    from .engine.mana import _mana_of, _amount
    slots = [set(_mana_of(s)) for s in payment for _ in range(max(1, _amount(s)))]
    pips = [c for c in 'WUBRGC' for _ in range(cost.get(c, 0))]
    pips.sort(key=lambda c: sum(c in s for s in slots))
    def colored(i, remaining):
        if i == len(pips):
            return remaining
        for j, slot in enumerate(remaining):
            if pips[i] in slot:
                result = colored(i + 1, remaining[:j] + remaining[j+1:])
                if result is not None:
                    return result
        return None
    remaining = colored(0, slots)
    colors = set(pips) & set('WUBRG')
    if remaining is None:
        return colors
    for slot in sorted(remaining, key=len)[:cost.get('generic', 0)]:
        candidates = sorted((slot & set('WUBRG')) - colors) or sorted(slot)
        if candidates and candidates[0] != 'C':
            colors.add(candidates[0])
    return colors


def permission_options(game, p):
    out = []
    sources = [x for x in p.battlefield if rules(x).get('grave_cast') and
               getattr(x, 'grave_cast_turn', None) != game.turn] if game.active is p else []
    for c in p.graveyard:
        if sources and (c.is_instant or c.is_sorcery):
            option = game._variant(c, 'grave_permission')
            option.permission_source = sources[0]
            out.append(option)
        if c.split_right is not None and c.split_right.advanced_rules.get('aftermath'):
            out.append(game._variant(c, 'aftermath'))
    for zone, ref in getattr(p, 'foreign_permissions', []):
        card = ref.find(zone)
        if card is not None:
            key = 'foreign_' + str(card.physical_id)
            if not hasattr(game, 'foreign_zones'):
                game.foreign_zones = {}
            game.foreign_zones[(id(p), key)] = zone
            option = game._variant(card, key)
            out.append(option)
    return out


def permission_available(game, p, card, kind):
    if kind == 'miracle':
        permission = getattr(game, '_miracle_permission', None)
        return permission is not None and permission[0] is p and permission[1] is game._origin(card)[0]
    if kind == 'grave_permission':
        source = getattr(card, 'permission_source', None)
        return game.active is p and source in p.battlefield and rules(source).get('grave_cast') and getattr(source, 'grave_cast_turn', None) != game.turn
    if kind == 'aftermath':
        return card.advanced_rules.get('aftermath', False)
    if kind.startswith('foreign_'):
        return any(ref.find(zone) is game._origin(card)[0] for zone, ref in getattr(p, 'foreign_permissions', []))
    return True


def encode(game, item, card):
    if not getattr(item, "resolved", False) or item.kind == 'copy' or not item.card.advanced_rules.get('cipher'):
        return False
    p = item.controller
    creatures = list(p.creatures)
    if not creatures:
        return False
    chooser = getattr(p.ai, 'choose_encode', None)
    from .engine.policy import perm_value
    host = chooser(game, p, card, creatures) if chooser else max(creatures, key=perm_value)
    if host not in creatures:
        return False
    owner = getattr(card, 'owner', None) or p
    owner.exile.append(card)
    if not hasattr(host, 'encoded'):
        host.encoded = []
    host.encoded.append((owner.exile, owner.exile.reference(card)))
    return True


def cipher_damage(game, source):
    if source.abilities_suppressed:
        return
    from .cards import Effect
    for zone, ref in getattr(source, 'encoded', []):
        if ref.find(zone) is not None:
            game.queue_trigger(source.controller, [Effect('cipher_cast')], source,
                               'encoded spell', context=(zone, ref))


def update_static(game):
    """Refresh continuous sources whose recipients can change without a trigger."""
    from . import continuous, counter_mechanics
    board = [x for p in game.players for x in p.battlefield]
    moons = [x for x in board if rules(x).get('land_conversion')]
    for perm in board:
        converting = bool(moons and perm.copiable_card.is_land and not perm.copiable_card.basic)
        if getattr(perm, '_mountain_conversion', False) != converting:
            perm._mountain_conversion = converting
            continuous.refresh(perm)
        aura = rules(perm).get('aura_control')
        host = perm.aura_host
        current = getattr(perm, 'controlled_host', None)
        controller = getattr(perm, 'control_grant_controller', None)
        active = any(e[0] is host and e[1] is perm.controller and e[2] is perm for e in game.control_effects)
        if aura and host is not None and (current is not host or controller is not perm.controller or not active):
            counter_mechanics.add_control(game, host, perm.controller, source=perm)
            perm.controlled_host = host
            perm.control_grant_controller = perm.controller
    counter_mechanics.expire_source_control(game)
