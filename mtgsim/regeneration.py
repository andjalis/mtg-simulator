"""Conservative priority responses for regeneration shields."""
from __future__ import annotations


def threatened(game, p):
    from .engine import Permanent
    from .ai import simulate_combat
    if game.stack:
        item = game.stack[-1]
        if item.controller is p:
            return []
        victims = []
        for eff, target in zip(item.effects, item.targets):
            if eff.data.get('no_regen'):
                continue
            if eff.kind in ('wrath', 'wrath_pw'):
                victims += p.creatures if eff.kind == 'wrath' else p.planeswalkers
            elif eff.kind == 'damage' and eff.target == 'each_creature':
                counter_damage = (item.card is not None and bool(item.card.keywords & {'infect','wither'})
                                  or item.source is not None and any(item.source.has(k) for k in ('infect','wither')))
                if not counter_damage:
                    victims += [x for x in p.creatures if x.damage + eff.amount >= x.toughness]
            elif isinstance(target, Permanent) and target.controller is p:
                if eff.kind == 'destroy':
                    victims.append(target)
                elif eff.kind == 'damage' and target.is_creature:
                    source = item.source
                    counter_damage = (source is not None and any(source.has(k) for k in ('infect','wither'))
                                      or item.card is not None and bool(item.card.keywords & {'infect','wither'}))
                    if not counter_damage and target.damage + eff.amount >= target.toughness:
                        victims.append(target)
        return victims
    if game.step == 'declare_blockers':
        dead = simulate_combat(game.attackers, game.blocks)[0]
        return [x for x in dead if x.controller is p]
    return []


def respond(game, p):
    from .engine import TARGETED, perm_value
    victims = [x for x in threatened(game, p) if x in p.battlefield and not x.regeneration_shields
               and not x.regeneration_blocked and not x.has('indestructible')
               and (not x.is_creature or x.toughness > 0)]
    for victim in sorted(victims, key=perm_value, reverse=True):
        for source in p.battlefield:
            for i, act in enumerate(source.card.activated):
                if not act.effects or any(e.kind != 'regenerate' for e in act.effects):
                    continue
                targets = []
                legal = True
                for eff in act.effects:
                    if eff.target == 'self':
                        legal &= source is victim
                        targets.append(None)
                    elif eff.target in TARGETED:
                        legal &= victim in game.legal_targets(p, eff)
                        targets.append(victim)
                    else:
                        legal &= eff.target in ('creatures_mine', 'each_creature')
                        targets.append(None)
                if legal and game.can_activate(p, source, i):
                    return 'activate', source, f'ability:{i}', targets
        for card in game.spell_options(p):
            if not card.instant_speed or not game.can_cast_now(p, card) or not card.spell_effects:
                continue
            if any(e.kind != 'regenerate' for e in card.spell_effects):
                continue
            targets = []
            legal = True
            for eff in card.spell_effects:
                if eff.target in TARGETED:
                    legal &= victim in game.legal_targets(p, eff)
                    targets.append(victim)
                else:
                    legal &= eff.target in ('creatures_mine', 'each_creature')
                    targets.append(None)
            if legal:
                return card, targets
    return None
