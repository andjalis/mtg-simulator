"""Composed extensions for triggers, granted abilities, targets and restrictions.

Every parser consumes a complete clause; unsupported bodies remain coverage gaps.
The helpers use existing permanent selectors and physical zone references.
"""
from __future__ import annotations

import re

from . import permanent_templates as pt


def _effect(kind, **kw):
    from .cards.model import Effect
    return Effect(kind, **kw)


def quantity(text):
    text = text.lower().strip()
    if text == 'the highest mana value among permanents you control':
        return {'kind': 'highest_cmc'}
    m = re.fullmatch(r'the number of (instant and sorcery|creature|artifact|enchantment|land) cards in (all graveyards|your graveyard)', text)
    if m:
        return {'kind': 'grave_count', 'types': m[1].split(' and '), 'all': m[2] == 'all graveyards'}
    m = re.fullmatch(r'the number of (creatures|artifacts|enchantments|lands) you control', text)
    if m:
        return {'kind': 'board_count', 'type': m[1][:-1]}
    return None


def amount(game, player, spec):
    if spec['kind'] == 'highest_cmc':
        return max((x.card.cmc for x in player.battlefield), default=0)
    if spec['kind'] == 'grave_count':
        return sum(any(k.title() in c.types for k in spec['types'])
                   for p in (game.players if spec['all'] else [player]) for c in p.graveyard)
    return sum(spec['type'].title() in x.card.types for x in player.battlefield)


def ability(text):
    from .cards.parse import _parse_ability
    from .cards.patterns import _parse_mana_ability
    from .cards.model import Activated
    text = re.sub(r'\bthis (?:creature|permanent|land|artifact)\b', '~', text, flags=re.I)
    m = re.fullmatch(r'\{T\}: Add (one mana of any color|(?:\{[WUBRGC]\})(?: or \{[WUBRGC]\})*)\.', text)
    if m:
        colors, n = _parse_mana_ability(m[1])
        if n == 1:
            return Activated('granted_mana', {}, keywords=frozenset(colors), text=text)
        return None
    approximations = []
    act = _parse_ability(text, approximations)
    # Once-per-turn grant identities require separate duration-aware bookkeeping.
    return act if act and not approximations and not act.once and not act.once_game else None


def grants(permanent):
    game = getattr(permanent.controller, '_game', None)
    if game is None or permanent.abilities_suppressed:
        return []
    out = list(permanent.temp_activated)
    for player in game.players:
        for source in player.battlefield:
            if not source.card.ability_grants or source.abilities_suppressed:
                continue
            for spec, act in source.card.ability_grants:
                if ((source.aura_host or source.attached_to) is permanent if spec.get('host') else
                        pt.matches(game, permanent, spec, source.controller, source)):
                    out.append(act)
    return out


def parse_line(line, state):
    from .cards.parse import _parse_trigger
    from .cards.model import _num
    m = re.fullmatch(r'When(?:ever)? (.+?) (enters?|dies?), (.+)', line)
    if m and not m[1].startswith(('~', 'equipped ', 'enchanted ')):
        established = _parse_trigger(line)
        if established and established[0] and not established[1]:
            return False  # Preserve existing event-specific context and graveyard listeners.
        desc, verb, body = m[1], m[2], m[3]
        grouped = desc.startswith('one or more ')
        desc = re.sub(r'^one or more ', '', desc)
        desc = re.sub(r'^another ', 'other ', desc)
        desc = re.sub(r'(noncreature|nonland|nontoken),\s+', r'\1 ', desc)
        spec = pt.selector(desc, plural=grouped)
        parsed = _parse_trigger('When ~ enters, ' + body)
        if spec is not None and parsed and not parsed[1] and parsed[2] is None:
            for trigger in parsed[0]:
                trigger.event = 'filtered_dies' if verb.startswith('die') else 'filtered_enters'
                trigger.data = {'selector': spec, 'grouped': grouped}
            state.extra['filtered_death_watch' if verb.startswith('die') else 'filtered_entry_watch'] = True
            state.triggers.extend(parsed[0])
            return True
    m = re.fullmatch(r'(.+?) (?:has|have) "(.+)"\.?', line)
    if m:
        act = ability(m[2].rstrip('.') + '.')
        spec = {'host': True} if m[1].lower() in ('enchanted land', 'enchanted creature', 'enchanted permanent', 'equipped creature') else pt.selector(re.sub(r'^All ', '', m[1]), plural=True)
        if act and spec is not None:
            state.extra['ability_grants'] = state.extra.get('ability_grants', ()) + ((spec, act),)
            return True
    m = re.fullmatch(r'~ enters(?: the battlefield)? with X (\+1/\+1|[a-z]+) counters on it, where X is (.+)\.', line)
    if m and quantity(m[2]):
        state.extra['entry_counter_quantity'] = (m[1], quantity(m[2]))
        return True
    m = re.fullmatch(r'No more than (one|two|three|four|\d+) creatures? can (attack|block) each combat\.', line)
    if m:
        state.extra[m[2] + '_limit'] = _num(m[1])
        return True
    if line == "Creatures can't attack.":
        state.extra['attack_limit'] = 0
        return True
    return False


def filtered_entry(game, permanent, seen=None):
    from .residual_templates import suppressed
    if permanent.is_creature and (suppressed(game, 'entry') or getattr(game, '_batch_entry_suppressed', False)):
        return
    pending = getattr(game, '_entry_batch', None)
    if pending is not None:
        pending.append(permanent)
        return
    for player in game.players:
        for source in list(player.battlefield):
            if not source.card.filtered_entry_watch:
                continue
            for index, trig in enumerate(source.triggers):
                if trig.event != 'filtered_enters':
                    continue
                key = (source, id(trig))
                if seen is not None and trig.data.get('grouped') and key in seen:
                    continue
                if queue_filtered(game, source, player, trig, id(trig), permanent):
                    if seen is not None and trig.data.get('grouped'):
                        seen.add(key)


def entry_batch(game):
    """An explicit simultaneous-entry instruction; nested instructions share a batch."""
    from contextlib import contextmanager
    @contextmanager
    def batched():
        if getattr(game, '_entry_batch', None) is not None:
            yield
            return
        events = []
        game._entry_batch = events
        try:
            yield
        except BaseException:
            game._entry_batch = None
            raise
        game._entry_batch = None
        seen = set()
        for permanent in events:
            filtered_entry(game, permanent, seen)
        game.state_based_actions()
    return batched()


def queue_filtered(game, source, player, trig, index, subject):
    if not pt.matches(game, subject, trig.data['selector'], player, source):
        return
    if trig.intervening_if:
        from .engine.state import StackItem
        initial = trig.data.get('initial_condition')
        if initial is None:
            initial = game.check_cond(player, _effect('condition', cond=trig.intervening_if),
                                      StackItem(player, [], [], source=source, context=subject), None)
        if not initial:
            return
    key = ('filtered', index)
    if trig.once and source.ability_turns.get(key) == game.turn:
        return
    if trig.once:
        source.ability_turns[key] = game.turn
    # Trigger-subject references in the ability body refer to the entered/dying object.
    game.queue_trigger(player, trig.effects, source, source.card.name, context=subject,
                       modes=trig.modes, intervening_if=trig.intervening_if)
    return True


class DeathBatch(list):
    """A death wave's pre-action characteristics, separate from live permanent state."""
    def __bool__(self):
        return len(self) > 0 or getattr(self, "suppresses_death", False)


def capture_deaths(game, sources):
    from types import SimpleNamespace
    filtered = [t for source, _ in sources for t in source.triggers if t.event == 'filtered_dies']
    if not filtered:
        return sources
    batch = DeathBatch(sources)
    batch.subjects = {}
    batch.initial = {}
    batch.seen = set()
    needed = {t.data['selector']['keyword'][0] for t in filtered if 'keyword' in t.data['selector']}
    for player in game.players:
        for subject in player.battlefield:
            kws = {kw for kw in needed if subject.has(kw)}
            frozen = SimpleNamespace(card=subject.card, controller=subject.controller,
                is_creature=subject.is_creature, power=subject.power, toughness=subject.toughness,
                counters=dict(subject.counters), tapped=subject.tapped,
                has=lambda kw, values=kws: kw in values)
            frozen_game = SimpleNamespace(attackers=[frozen] if subject in game.attackers else [],
                blocks={None: [frozen]} if any(subject in bl for bl in game.blocks.values()) else {})
            batch.subjects[subject] = frozen, frozen_game
            from .engine.state import StackItem
            for source, controller in sources:
                for trig in source.triggers:
                    if trig.event == 'filtered_dies' and trig.intervening_if:
                        batch.initial[id(trig), subject] = game.check_cond(controller,
                            _effect('condition', cond=trig.intervening_if),
                            StackItem(controller, [], [], source=source, context=subject), None)
    return batch


def filtered_death(game, permanent, sources):
    for source, player in sources:
        triggers = getattr(source, 'last_triggers', None)
        if triggers is None:
            triggers = source.triggers
        for index, trig in enumerate(triggers):
            if trig.event != 'filtered_dies':
                continue
            identity = id(trig)
            if trig.data.get('grouped') and (source, identity) in sources.seen:
                continue
            spec = trig.data['selector']
            if spec.get('other') and source is permanent:
                continue
            frozen = getattr(sources, 'subjects', {}).get(permanent)
            if frozen:
                view, frozen_game = frozen
                if not pt.matches(frozen_game, view, dict(spec, other=False), player, source):
                    continue
                # The predicate was evaluated in the simultaneous death wave's state.
                import dataclasses
                trig = dataclasses.replace(trig, data=dict(trig.data, selector={'types_all': ['permanent']},
                    initial_condition=sources.initial.get((identity, permanent))))
            if queue_filtered(game, source, player, trig, identity, permanent) and trig.data.get('grouped'):
                sources.seen.add((source, identity))


def combat_limit(game, kind):
    limits = [getattr(source.card, kind + '_limit') for p in game.players for source in p.battlefield
              if getattr(source.card, kind + '_limit') >= 0 and not source.abilities_suppressed]
    return min(limits) if limits else None


def parse_effect(text):
    m = re.fullmatch(r'(.+?) gains? "(.+)" until end of turn', text, re.I)
    if m:
        act = ability(m[2].rstrip('.') + '.')
        if act:
            return pt.build('grant_activated', m[1], data={'ability': act})
    m = re.fullmatch(r'(.+?) gets? ([+-](?:X|\d+))/([+-](?:X|\d+)) until end of turn, where X is (.+)', text, re.I)
    if m and quantity(m[4]):
        return pt.build('quantity_stats', m[1], data={'power': m[2], 'toughness': m[3], 'quantity': quantity(m[4])})
    m = re.fullmatch(r'return (?:up to one )?target (creature|artifact|enchantment|land|permanent) card with mana value (\d+) from your graveyard to (the battlefield|your hand)( tapped)?', text, re.I)
    if m:
        return _effect('return_grave_target', target='graveyard_card', data={'grave_type': m[1].lower(), 'cmc_exact': int(m[2]), 'dest': m[3].lower(), 'tapped': bool(m[4]), 'optional_target': text.lower().startswith('return up to one ')})
    m = re.fullmatch(r'DELAYEDBLINK (.+)', text)
    if m:
        return pt.build('blink_next_end', m[1])
    m = re.fullmatch(r'move (a|one|two|three|any number of) (\+1/\+1|[a-z]+) counters? from (target .+?) onto another target (creature|permanent) with the same controller', text, re.I)
    if m:
        from .cards.model import _num
        first = pt.build('relationship_mark', m[3], data={'relationship': 'counter'})
        second = pt.build('transfer_between', 'target ' + m[4], data={'anchor': 0, 'same_controller': True, 'different': True, 'counter': m[2].lower(), 'count': 'any' if m[1].lower() == 'any number of' else _num(m[1])})
        return [first, second] if first and second else None
    m = re.fullmatch(r'attach target Aura attached to a permanent to another permanent with the same controller', text, re.I)
    if m:
        return [pt.build('relationship_mark', 'target Aura', data={'attached_aura': True, 'relationship': 'aura'}),
                pt.build('move_aura', 'target permanent', data={'anchor': 0, 'same_controller': True, 'different': True, 'anchor_host': True})]
    if re.fullmatch(r'attach all Auras enchanting target permanent to another permanent with the same controller', text, re.I):
        return [pt.build('relationship_mark', 'target permanent', data={'relationship': 'auras'}),
                pt.build('move_auras', 'target permanent', data={'anchor': 0, 'same_controller': True, 'different': True})]
    if text.lower() == "until end of turn, target player can't cast instant or sorcery spells, and that player can't activate abilities that aren't mana abilities":
        return _effect('player_action_lock', target='player')
    m = re.fullmatch(r'create (a|one|two|three|\d+) (\d+)/(\d+) (.+?) creature tokens? named (.+?) with "(.+)"', text, re.I)
    if m:
        from .cards.patterns import _token
        from .cards.parse import _parse_trigger
        body = m[6].rstrip('.') + '.'
        parsed = _parse_trigger(body)
        if parsed and not parsed[1] and parsed[2] is None:
            eff = _token(m[1], m[2], m[3], m[4])
            eff.data.update({'token_name': m[5], 'triggers': parsed[0]})
            return eff
    return None


def related_targets(game, effect, choices):
    if 'anchor' not in effect.data:
        return choices
    source = game.target_source
    targets = getattr(source, 'targets', None) or getattr(game, '_choosing_targets', [])
    idx = effect.data['anchor']
    if len(targets) <= idx or targets[idx] is None:
        return []
    anchor = targets[idx]
    if effect.data.get('anchor_host'):
        anchor = getattr(anchor, 'aura_host', None)
    if anchor is None or not hasattr(anchor, 'controller'):
        return []
    return [p for p in choices if (not effect.data.get('different') or p is not anchor)
            and (not effect.data.get('same_controller') or p.controller is anchor.controller)]


def _fallback(match):
    from .cards.model import NO_MATCH
    return parse_effect(match[1]) or NO_MATCH


EFFECT_PATTERNS = [(r'(.+)', _fallback)]
SUBS = [(re.compile(r"Exile ([^.]+)\. Return (?:it|that card) to the battlefield under its owner's control at the beginning of the next end step\.", re.I),
         lambda m: 'DELAYEDBLINK ' + m[1] + '.')]
