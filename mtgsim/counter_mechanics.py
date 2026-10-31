"""Counter movement, training, linked exile and delayed counter-death returns.

Templates describe abilities rather than card names. ZoneRef tracks cards across
delayed effects so another copy, or a card that left and reentered, cannot return.
"""
from __future__ import annotations

import re


def effect(kind, **kw):
    from .cards.model import Effect
    return Effect(kind, **kw)


def parse_line(line, st):
    from .cards.model import Trigger, KEYWORDS
    if line == "~ can't attack or block.":
        st.extra['cant_attack'] = st.extra['cant_block'] = True
        return True
    match = re.fullmatch(r"Graft (\d+)", line)
    if match:
        st.extra['graft'] = st.extra.get('graft', 0) + int(match[1])
        st.triggers.append(Trigger('any_creature_enters', [effect('graft_move')], filter='graft'))
        return True
    match = re.fullmatch(r"(Other )?[Cc]reatures you control have (training|dethrone)\.", line)
    if match:
        st.extra['granted_attack_keywords'] = st.extra.get('granted_attack_keywords', ()) + ((match[2], bool(match[1])),)
        return True
    match = re.fullmatch(r"Each (other )?creature you control enters with an additional (\w+) counter on it\.", line)
    if match and match[2] in KEYWORDS:
        st.extra['entry_counter_grant'] = (match[2], 1, bool(match[1]))
        return True
    if line == ('Whenever a creature you control with a +1/+1 counter on it dies, return that card to the '
                'battlefield under your control at the beginning of the next end step.'):
        st.extra['death_counter_return'] = True
        return True
    match = re.fullmatch(r"Whenever ~ trains, (.+)", line)
    if match:
        from .cards import _parse_effects
        effects, bad = _parse_effects(match[1])
        if not bad and effects:
            st.triggers.append(Trigger('trains', effects))
            return True
    if line == ("Whenever ~ attacks for the first time each turn, if it's attacking the player with the most life "
                "or tied for most life, untap all attacking creatures. After this phase, there is an additional combat phase."):
        st.triggers.append(Trigger('attacks', [effect('additional_combat')], filter='first_attack',
                                   intervening_if='attacking_most_life'))
        return True
    return False


EFFECT_PATTERNS = [
    (r"target creature with a \+1/\+1 counter on it gains (reach|flying|shroud) until end of turn",
     lambda m: effect('grant', target='creature', filter='p1', data={'keyword': m[1].lower()})),
    (r"regenerate target creature with a \+1/\+1 counter on it",
     lambda m: effect('regenerate', amount=1, target='creature', filter='p1')),
    (r"untap target creature with a \+1/\+1 counter on it",
     lambda m: effect('untap_prev', target='creature', filter='p1')),
    (r"gain control of target creature with a \+1/\+1 counter on it for as long as ~ remains on the battlefield",
     lambda m: effect('source_control', target='creature', filter='p1')),
    (r"put a \+1/\+1 counter on each other creature you control with a \+1/\+1 counter on it",
     lambda m: effect('counter_team')),
    (r"move a \+1/\+1 counter from target creature you control onto ~",
     lambda m: effect('move_counter_self', target='creature_mine')),
    (r'until end of turn, target creature with a \+1/\+1 counter on it gains "whenever (?:~|this creature) '
     r'deals combat damage to a creature, destroy that creature at end of combat\.?"',
     lambda m: effect('grant_combat_destroy', target='creature', filter='p1')),

    (r"put its counters on target creature you control",
     lambda m: effect('inherit_counters', target='creature_mine')),
    (r"exile up to one other target creature from the battlefield or creature card from a graveyard",
     lambda m: effect('linked_exile', target='creature_or_graveyard', data={'other': True, 'optional_target': True})),
    (r"put the exiled cards onto the battlefield under their owners' control",
     lambda m: effect('linked_return')),
    (r"create an X/X (white|blue|black|red|green) (\w+(?: \w+)*) creature token, where X is the number of "
     r"\+1/\+1 counters removed this way", lambda m: effect('counter_token', data={'color': m[1].lower(), 'name': m[2]})),
    (r"another target attacking creature without flying gains flying until end of turn",
     lambda m: effect('grant', target='creature', filter='attacking_nonflying',
                      data={'keyword': 'flying', 'other': True})),
]
SUBS = []


def death_sources(game):
    sources = [(src, player) for player in game.players for src in player.battlefield
            if (src.card.death_counter_return or src.card.filtered_death_watch) and not src.silenced
            and not any('loses_abilities' in a.card.aura_flags for a in src.auras)]

    from .backlog_templates import capture_deaths
    batch = capture_deaths(game, sources)
    from .backlog_templates import DeathBatch
    from .residual_templates import suppressed
    if not isinstance(batch, DeathBatch):
        batch = DeathBatch(batch)
    batch.suppresses_death = suppressed(game, "death")
    return batch


def queue_death_return(game, permanent, sources):
    if not permanent.p1 or permanent.last_destination != 'graveyard':
        return
    zone = permanent.owner.graveyard
    context = (zone, zone.reference(permanent.front)) if permanent.front in zone else (None, None)
    for source, controller in sources:
        if source.card.death_counter_return and controller is permanent.controller:
            game.queue_trigger(controller, [effect('schedule_counter_return')], source,
                               source.card.name, context=context)


def is_attacking_most_life(game, source, controller):
    from .engine.state import Player
    defender = game.attack_targets.get(source)
    return (source is not None and source in game.attackers and source in source.controller.battlefield
            and source.controller is controller and source.is_creature
            and isinstance(defender, Player) and defender.life >= max(p.life for p in game.players))


def graveyard_targets(game):
    return [card for player in game.players for card in player.graveyard if card.is_creature]


def protect_graveyard_targets(game, effects, targets):
    """Freeze the generation of targeted graveyard cards as a trigger is stacked."""
    import dataclasses
    from .identity import CardInstance, CardZone
    out = []
    for eff, target in zip(effects, targets):
        if eff.target in ('creature_or_graveyard', 'graveyard_card') and isinstance(target, CardInstance) and isinstance(target.zone, CardZone):
            eff = dataclasses.replace(eff, data=dict(eff.data, graveyard_ref=target.zone.reference(target),
                                                     graveyard_zone=target.zone))
        out.append(eff)
    return out + list(effects[len(out):])


def change_control(game, permanent, controller):
    """A control change preserves the object, removes it from combat and resets control tenure."""
    if permanent.controller is controller:
        return
    permanent.controller.battlefield.remove(permanent)
    permanent.controller = controller
    controller.battlefield.append(permanent)
    permanent.sick = True
    if permanent in game.attackers:
        game.attackers.remove(permanent)
    game.attack_targets.pop(permanent, None)
    game.blocks.pop(permanent, None)
    for blockers in game.blocks.values():
        blockers[:] = [b for b in blockers if b is not permanent]


def add_control(game, target, controller, *, source=None, until_eot=False):
    """Timestamped supported control effects, retaining the pre-effect controller."""
    if not hasattr(target, 'control_base'):
        target.control_base = target.controller
    game.control_effects.append((target, controller, source, until_eot))
    change_control(game, target, controller)


def expire_source_control(game, *, cleanup=False):
    effects = game.control_effects
    if not effects:
        return
    from .cx_statics import control_lasts
    targets = {entry[0] for entry in effects}
    game.control_effects = [entry for entry in effects if entry[0] in entry[0].controller.battlefield
                           and (entry[2] is None or entry[2] in entry[2].controller.battlefield and
                                (not entry[2].card.advanced_rules.get("aura_control") or
                                 entry[2].aura_host is entry[0] and not entry[2].abilities_suppressed))
                           and not (cleanup and entry[3]) and control_lasts(game, entry[0], entry[2])]
    for target in targets:
        active = [entry for entry in game.control_effects if entry[0] is target]
        if target in target.controller.battlefield:
            change_control(game, target, active[-1][1] if active else target.control_base)
        if not active and hasattr(target, 'control_base'):
            del target.control_base
