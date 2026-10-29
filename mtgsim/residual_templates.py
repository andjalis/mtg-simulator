"""Residual effects and shared restrictions, using existing selectors and identities."""
from __future__ import annotations

import re

from .advanced_templates import rules

EFFECT_PATTERNS = []
SUBS = []
NUMBER = r'(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)'


def sources(game, key):
    # Index possible providers, then check live text/suppression on every lookup.
    # Card setters and zone boundaries invalidate it; lengths also cover fixture
    # list appends/removals. Unrelated permanents need no ability checks.
    sizes = tuple(len(p.battlefield) for p in game.players)
    cached = getattr(game, '_residual_source_index', None)
    if cached is None or cached[0] != sizes:
        index = {}
        for player in game.players:
            for permanent in player.battlefield:
                keys = permanent.card.advanced_rules.keys() | permanent.copiable_card.advanced_rules.keys()
                for name in keys:
                    index.setdefault(name, []).append(permanent)
        cached = sizes, index
        game._residual_source_index = cached
    return [x for x in cached[1].get(key, ()) if x in x.controller.battlefield and
            x.card.advanced_rules.get(key) and not x.abilities_suppressed]


def parse_line(line, st):
    from .cards import Effect, Trigger, parse_mana_cost, _num
    flags = {
        "If a card would be put into an opponent's graveyard from anywhere, exile it instead.": 'opponent_grave_exile',
        "Creature cards in graveyards and libraries can't enter the battlefield.": 'zone_entry_lock',
        "Players can't cast spells from graveyards or libraries.": 'zone_cast_lock',
        "Creatures entering don't cause abilities to trigger.": 'suppress_entry',
        "Creatures entering or dying don't cause abilities to trigger.": 'suppress_entry_death',
        "Activated abilities of creatures can't be activated.": 'creature_activation_lock',
        "Activated abilities of artifacts and creatures can't be activated unless they're mana abilities.": 'nonmana_activation_lock',
        "Your life total can't change.": 'life_lock',
        "Players can't get counters.": 'player_counter_lock',
        "Counters can't be put on artifacts, creatures, enchantments, or lands.": 'permanent_counter_lock',
        "You can't get poison counters.": 'poison_lock',
        "Creatures you control can't have -1/-1 counters put on them.": 'negative_counter_lock',
        'Creatures your opponents control lose infect.': 'remove_infect',
    }
    if line in flags:
        st.extra.setdefault('advanced_rules', {})[flags[line]] = True
        return True
    m = re.fullmatch(r'(.+?) (?:get|gets) ([+-]\d+)/([+-]\d+)(?: and (?:have|has) (.+))?\.', line)
    if m:
        from .permanent_templates import selector, keywords
        spec = selector(m[1], plural=True)
        kws = keywords(m[4]) if m[4] else []
        if spec is not None and 'keyword' not in spec and 'stat' not in spec and kws is not None and (
                'your opponents control' in m[1] or m[1].lower().startswith('other creatures ') or 'tokens' in m[1].lower() or 'nontoken' in m[1].lower() or
                re.fullmatch(r'(?:Black|White|Blue|Red|Green) creatures', m[1], re.I)):
            st.extra.setdefault('advanced_rules', {}).setdefault('anthems', []).append((spec, int(m[2]), int(m[3])))
            if kws:
                st.extra['static_keyword_grants'] = st.extra.get('static_keyword_grants', ()) + ((spec, tuple(kws)),)
            return True
    m = re.fullmatch(r'(.+?) your opponents control enter tapped\.', line)
    if m:
        kinds = m[1].lower().replace(', and ', ' or ').replace(' and ', ' or ').replace(', ', ' or ').split(' or ')
        kinds = [k[:-1] for k in kinds]
        if all(k in ('creature', 'artifact', 'land', 'enchantment') for k in kinds):
            st.extra.setdefault('advanced_rules', {})['opponent_entry_tapped'] = kinds
            return True
    m = re.fullmatch(rf'~ enters tapped unless you control ({NUMBER}) or more other ([A-Za-z]+)s\.', line)
    if m:
        from .cards import BASIC_MANA
        if m[2] in BASIC_MANA:
            st.extra['tapped_condition'] = 'other_subtype:' + m[2] + ':' + str(_num(m[1]))
            return True
    m = re.fullmatch(rf"At the beginning of your end step, if you control ({NUMBER}) or more permanents you don't own, (.+)", line)
    if m:
        from .cards.parse import _parse_effects
        effects, bad = _parse_effects(m[2])
        if not bad:
            st.triggers.append(Trigger('end_step', effects, intervening_if='not_owned>=' + str(_num(m[1]))))
            return True
    if line == 'Whenever an opponent casts a spell, if no mana was spent to cast it, counter that spell.':
        st.triggers.append(Trigger('unpaid_opponent_cast', [Effect('counter_context')]))
        return True
    if line == "At the beginning of the end step of enchanted creature's controller, destroy that creature if it didn't attack this turn.":
        st.triggers.append(Trigger('host_end_step', [Effect('destroy_idle_host')]))
        return True
    m = re.fullmatch(r'Miracle ((?:\{[^}]+\})+)', line)
    if m:
        st.extra.setdefault('advanced_rules', {})['miracle'] = parse_mana_cost(m[1])
        return True
    return False


def parse_effect(text):
    from .cards import Effect, _num
    s = text.lower().strip().rstrip('.')
    m = re.fullmatch(r'(destroy|return) all (.+?)(?: to their owners\' hands)?', s)
    if m and (m[1] == 'destroy' or s.endswith("to their owners' hands")):
        from .permanent_templates import selector
        spec = selector(m[2], plural=True)
        if spec is not None and ('stat' in spec or m[1] == 'return' and m[2] == 'creatures'):
            return [Effect('selected_mass_move', data={'selector': spec, 'dest': 'graveyard' if m[1] == 'destroy' else 'hand'})]
    m = re.fullmatch(r'return all (creature|artifact|enchantment) cards with (power|toughness|mana value) (\d+) or (less|greater) from your graveyard to your hand', s)
    if m:
        return [Effect('filtered_grave_return', int(m[3]), data={'type': m[1], 'stat': m[2], 'less': m[4] == 'less'})]
    if s == 'exile all graveyards':
        return [Effect('graveyard_exile_all')]
    if s == "exile all cards from target player's graveyard":
        return [Effect('graveyard_exile_all', target='player')]
    if s == 'target player exiles a card from their graveyard':
        return [Effect('graveyard_exile_choice', target='player')]
    if s == 'the next time target creature adapts this turn, it adapts as though it had no +1/+1 counters on it':
        return [Effect('adapt_exception', target='creature')]
    m = re.fullmatch(rf'adapt ({NUMBER})', s)
    if m:
        return [Effect('adapt', _num(m[1]), target='self')]
    return None


def anthem_bonus(permanent):
    from .permanent_templates import matches
    game = getattr(permanent.controller, '_game', None)
    if game is None:
        return 0, 0
    power = toughness = 0
    for src in sources(game, 'anthems'):
        for spec, pp, tt in rules(src)['anthems']:
            if matches(game, permanent, spec, src.controller, src):
                power += pp
                toughness += tt
    return power, toughness


def activation_blocked(game, perm, *, mana=False):
    return bool(perm.is_creature and sources(game, 'creature_activation_lock') or
                perm.card.is_artifact and sources(game, 'artifact_activation_lock') or not mana and
                (perm.is_creature or perm.card.is_artifact) and sources(game, 'nonmana_activation_lock'))


def mana_ability(act):
    return bool(act.effects) and all(e.kind == 'add_mana' and e.target == 'none' for e in act.effects)


def life_locked(player):
    return any(rules(x).get('life_lock') for x in player.battlefield)


def player_counter_allowed(player, name):
    game = getattr(player, '_game', None)
    return not (game and sources(game, 'player_counter_lock') or
                name == 'poison' and any(rules(x).get('poison_lock') for x in player.battlefield))


def permanent_counter_allowed(perm, name):
    game = getattr(perm.controller, '_game', None)
    return not (game and sources(game, 'permanent_counter_lock') and
                (perm.is_creature or bool(perm.card.types & {'Artifact', 'Enchantment', 'Land'})) or
                name == '-1/-1' and perm.is_creature and any(rules(x).get('negative_counter_lock') for x in perm.controller.battlefield))


def grave_exiled(game, owner, *, token=False):
    return any(rules(x).get('grave_exile') or not token and x.controller is not owner and rules(x).get('opponent_grave_exile')
               for p in game.players for x in p.battlefield)


def suppressed(game, event):
    return bool(sources(game, 'suppress_entry_death') or event == 'entry' and sources(game, 'suppress_entry'))


def trigger_suppressed(game, event, source, context, subject):
    entry_events = {'etb', 'other_creature_enters', 'any_creature_enters', 'permanent_enters', 'land_enters'}
    creature = next((x for x in (subject, context, source) if getattr(x, 'is_creature', False)), None)
    return bool(event in entry_events and creature is not None and
                (suppressed(game, 'entry') or getattr(game, '_batch_entry_suppressed', False)))


def tapped_by_opponent(game, perm):
    return any(perm.controller is not src.controller and
               any(perm.is_creature if kind == 'creature' else kind.title() in perm.card.types
                   for kind in rules(src)['opponent_entry_tapped']) for src in sources(game, 'opponent_entry_tapped'))


def blocked_entry(game, card, physical=None):
    physical = physical if physical is not None else card
    if not getattr(physical, 'is_creature', False) or getattr(physical, 'is_token', False) or not sources(game, 'zone_entry_lock'):
        return False
    pending = getattr(physical, 'pending_move', None)
    zone = getattr(physical, 'zone', None)
    origin = getattr(zone, 'name', '') or (pending[1] if pending else '')
    if origin not in ('graveyard', 'library'):
        return False
    if zone is None and pending is not None:
        # Older effect handlers remove before entering. Restore the prevented move
        # without emitting a zone event or invalidating physical references.
        zone = getattr(physical, 'departure_zone', None)
        if zone is None:
            zone = getattr(physical.owner, origin)
        index = getattr(physical, 'departure_index', len(zone))
        list.insert(zone, min(index, len(zone)), physical)
        physical.generation = pending[0].generation
        zone.versions[physical.physical_id] = physical.generation
        physical.zone, physical.pending_move = zone, None
        if hasattr(zone, 'left'):
            zone.left[:] = [c for c in zone.left if c is not physical]
    return True


def cast_locked(game, p, card):
    base, kind, _ = game._origin(card)
    zone = game._zone(p, kind)
    return getattr(zone, 'name', '') in ('graveyard', 'library') and bool(sources(game, 'zone_cast_lock'))


def on_spell_cast(game, p, item):
    if item.mana_spent + getattr(item, 'x', 0):
        return
    for src in list(game.opponent(p).battlefield):
        for trig in src.triggers:
            if trig.event == 'unpaid_opponent_cast':
                game.queue_trigger(src.controller, trig.effects, src, src.card.name, context=item)


def on_end_step(game, active):
    for player in game.players:
        for src in list(player.battlefield):
            host = src.aura_host
            if host is not None and host.controller is active:
                for trig in src.triggers:
                    if trig.event == 'host_end_step':
                        game.queue_trigger(player, trig.effects, src, src.card.name, context=host)


def on_draw(game, p, card, first):
    cost = card.advanced_rules.get('miracle')
    chooser = getattr(p.ai, 'reveal_miracle', None)
    if cost is not None and first and (chooser is None or chooser(game, p, card)):
        from .cards import Effect
        game.queue_trigger(p, [Effect('miracle_cast')], name=card.name + ' miracle', context=(p.hand, p.hand.reference(card), cost))


def effect_value(game, player, effect, target):
    """Conservative values for new shared operations; no changes to older kinds."""
    from .engine.state import Permanent
    from .engine.policy import perm_value
    from .permanent_templates import matches
    if effect.kind == 'selected_mass_move':
        return sum((1 if p is not player else -1) * perm_value(x) for p in game.players for x in p.battlefield
                   if matches(game, x, effect.data['selector'], player))
    if effect.kind == 'filtered_grave_return':
        def eligible(c):
            value = c.cmc if effect.data['stat'] == 'mana value' else getattr(c, effect.data['stat'])
            return effect.data['type'].title() in c.types and value is not None and ((value <= effect.amount) if effect.data['less'] else value >= effect.amount)
        return sum(c.cmc + 1 for c in player.graveyard if eligible(c))
    if effect.kind in ('graveyard_exile_all', 'graveyard_exile_choice'):
        grave = target.graveyard if target in game.players else game.opponent(player).graveyard
        return min(1, len(grave)) if effect.kind == 'graveyard_exile_choice' else len(grave)
    if effect.kind == 'adapt':
        src = getattr(game.target_source, 'source', game.target_source)
        return effect.amount if isinstance(src, Permanent) and (not src.p1 or getattr(src, 'adapt_exceptions', 0)) and permanent_counter_allowed(src, '+1/+1') else 0
    return None
