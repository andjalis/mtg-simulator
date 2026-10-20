"""Combat keywords and spell-chain mechanics, isolated from the core engine."""
import re


SIMPLE = {'exalted', 'flanking', 'infect', 'wither', 'storm', 'cascade'}
NUMBERED = {'bushido', 'bloodthirst', 'soulshift', 'rampage', 'fabricate', 'modular', 'toxic', 'backup'}


def parse(line, keywords, extra, triggers):
    from .cards import Effect, Trigger
    parts = [s.strip().lower() for s in line.rstrip('.').split(',')]
    # Consume a whole keyword list only when every component is understood.
    from .cards import KEYWORDS
    if not all(s in KEYWORDS or s in SIMPLE or
               re.fullmatch(r'(?:' + '|'.join(NUMBERED) + r') \d+', s) for s in parts):
        return False
    if not any(s in SIMPLE or s.split(' ')[0] in NUMBERED for s in parts):
        return False
    for s in parts:
        if s in SIMPLE or s in KEYWORDS:
            keywords.add(s)
            if s in {'flanking', 'storm', 'cascade'}:
                extra['combat_mechanics'] = extra.get('combat_mechanics', ()) + ((s, 1),)
            if s == 'exalted':
                triggers.append(Trigger('attacks_alone', [Effect('pump', 1, 1, target='trigger_subject')]))
        else:
            kind, n = s.split(' ')
            n = int(n)
            extra['combat_mechanics'] = extra.get('combat_mechanics', ()) + ((kind, n),)
            if kind == 'backup':
                triggers.append(Trigger('etb', [Effect('kw_backup', n, target='creature')]))
            elif kind == 'fabricate':
                triggers.append(Trigger('etb', [Effect('kw_fabricate', n)]))
            elif kind == 'soulshift':
                triggers.append(Trigger('dies', [Effect('regrow', target='graveyard_card',
                    data={'what': 'Spirit', 'cmc': (n, 'less'), 'upto': True})]))
    return True


def values(obj, kind):
    cards = [obj.card] + getattr(obj, 'backup_grants', []) if hasattr(obj, 'card') else [obj]
    return [n for card in cards for k, n in card.combat_mechanics if k == kind]


def entering(game, perm):
    p = perm.controller
    n = sum(values(perm, 'modular'))
    if getattr(game.opponent(p), 'damaged_turn', False):
        n += sum(values(perm, 'bloodthirst'))
    if n:
        perm.counters['+1/+1'] = perm.p1 + n


def died(game, perm):
    from .cards import Effect
    for _ in values(perm, 'modular'):
        game.queue_trigger(perm.controller, [Effect('kw_modular', perm.p1, target='creature',
                           filter='artifact')], perm, 'Modular')


def blockers(game, attackers, blocks):
    from .cards import Effect
    for a in attackers:
        bl = blocks.get(a, [])
        if not bl:
            continue
        for n in values(a, 'bushido'):
            game.queue_trigger(a.controller, [Effect('pump', n, n, target='self')], a, 'Bushido')
        for n in values(a, 'rampage'):
            game.queue_trigger(a.controller, [Effect('kw_rampage', n)], a, 'Rampage')
        for b in bl:
            if a.has('flanking') and not b.has('flanking'):
                for _ in range(max(1, len(values(a, 'flanking')))):
                    game.queue_trigger(a.controller, [Effect('pump', -1, -1, target='trigger_subject')],
                                       a, 'Flanking', context=b)
            for n in values(b, 'bushido'):
                game.queue_trigger(b.controller, [Effect('pump', n, n, target='self')], b, 'Bushido')


def damage(game, target, amount, source):
    """Damage's results; return True if the ordinary life/damage result was replaced."""
    from .engine import Permanent, Player
    if amount <= 0:
        return True
    if isinstance(target, Player):
        target.damaged_turn = True
        if source is not None and has(source, 'infect'):
            target.counters['poison'] = target.counters.get('poison', 0) + amount
            return True
    elif isinstance(target, Permanent) and target.is_creature and source is not None:
        if has(source, 'infect') or has(source, 'wither'):
            target.counters['-1/-1'] = target.m1 + amount
            if target.is_planeswalker:
                target.counters['loyalty'] = target.loyalty - amount
            return True
    return False


def cast(game, p, item):
    from .cards import Effect
    # copies.on_cast has already counted this spell, for both players.
    counts = game.spells_cast
    before = sum(counts.get(name, 0) for name in {pl.name for pl in game.players}) - 1
    for _ in values(item.card, 'storm'):
        game.queue_trigger(p, [Effect('kw_storm', before)], name='Storm', context=item)
    for _ in values(item.card, 'cascade'):
        game.queue_trigger(p, [Effect('kw_cascade', item.card.cmc)], name='Cascade')


def resolve(game, p, eff, target, item):
    from .cards import Effect
    from .engine import Permanent
    if eff.kind == 'proliferate':
        # The controller chooses a subset; each chosen object receives one of EVERY kind.
        for pl in game.players:
            if (pl is not p and pl.counters.get('poison', 0)) or (pl is p and not pl.counters.get('poison', 0)):
                for key, n in list(pl.counters.items()):
                    if n > 0:
                        pl.counters[key] += 1
            for perm in pl.battlefield:
                positive = perm.p1 + perm.loyalty
                negative = perm.m1 + perm.counters.get('stun', 0)
                if (pl is p and positive >= negative) or (pl is not p and negative > positive):
                    for key, n in list(perm.counters.items()):
                        if n > 0:
                            perm.counters[key] += 1
    elif eff.kind == 'kw_backup':
        if isinstance(target, Permanent) and target in target.controller.battlefield:
            target.counters['+1/+1'] = target.p1 + eff.amount
            if target is not item.source and eff.data.get('grant') is not None:
                target.backup_grants.append(eff.data['grant'])
    elif eff.kind == 'kw_fabricate':
        # A legal choice policy: prefer bodies, even when the source has left.
        game.create_token(p, Effect('token', eff.amount, data={
            'name': 'Servo', 'power': 1, 'toughness': 1, 'artifact': True}))
    elif eff.kind == 'kw_modular':
        if isinstance(target, Permanent) and target.is_creature and target.card.is_artifact:
            target.counters['+1/+1'] = target.p1 + eff.amount
    elif eff.kind == 'kw_rampage':
        src = item.source
        if src in src.controller.battlefield:
            n = sum(b.is_creature and b in game.opponent(src.controller).battlefield
                    for b in game.blocks.get(src, []))
            src.pump_p += max(0, n - 1) * eff.amount
            src.pump_t += max(0, n - 1) * eff.amount
    elif eff.kind == 'kw_storm':
        from .copies import copy_spell
        for _ in range(eff.amount):
            copy_spell(game, p, item.context)
    elif eff.kind == 'kw_cascade':
        exiled = []
        hit = None
        while p.library:
            c = p.library.pop()
            p.exile.append(c)
            exiled.append(c)
            if not c.is_land and c.cmc < eff.amount:
                hit = c
                break
        if hit is not None:
            p.exile.remove(hit)
            if cascade_cast(game, p, hit):
                exiled.remove(hit)
            else:
                p.exile.append(hit)
        game.rng.shuffle(exiled)
        for c in exiled:
            p.exile.remove(c)
        p.library[0:0] = exiled


# Joined to the ordinary effect parser, including triggered and compound effects.
def proliferate_effect(m):
    from .cards import Effect
    return Effect('proliferate')


EFFECT_PATTERNS = [(r'(?:You may )?proliferate', proliferate_effect)]


def has(source, keyword):
    return source.has(keyword) if hasattr(source, 'has') else keyword in source.keywords


def finish_backup(text, data, triggers, approximations):
    """Bind only the abilities printed below each backup ability (CR 702.165)."""
    from .cards import _parse_face, CardDef
    import dataclasses
    abilities = [e for t in triggers for e in t.effects if e.kind == 'kw_backup']
    if not abilities:
        return
    lines = text.split('\n')
    tails = ['\n'.join(lines[i+1:]) for i, line in enumerate(lines)
             if re.fullmatch(r'Backup \d+\.?', line.strip(), re.I)]
    allowed = {'name', 'oracle', 'mana_cost', 'cmc', 'types', 'subtypes', 'power', 'toughness',
               'keywords', 'triggers', 'activated', 'ward', 'combat_mechanics', 'unsupported',
               'approximations', 'legendary', 'snow', 'etb_effects', 'spent_colors', 'hybrid',
               'colors', 'basic', 'mana_cost_missing'}  # card characteristics, not granted abilities
    if len(tails) != len(abilities):
        approximations.append('backup: printed ability ordering could not be bound')
    empty = CardDef(name='', mana_cost={}, cmc=0, types=frozenset())
    for effect, tail in zip(abilities, tails):
        grant = _parse_face({**data, 'oracle_text': tail})
        effect.data['grant'] = grant
        if any(getattr(grant, f.name) != getattr(empty, f.name)
               for f in dataclasses.fields(grant) if f.name not in allowed):
            approximations.append('backup: granted static abilities beyond keywords and ward are not modeled')


def cascade_cast(game, player, card):
    """Decline when the policy cannot select legal targets or pay additional costs."""
    from .cards import AltCost
    from .engine import TARGETED
    player.hand.append(card)
    free = game._variant(card, 'free', AltCost('free', {'generic': 0}))
    targets = game.auto_targets(player, free.spell_effects)
    legal = (not free.modes and game.can_cast_now(player, free, ignore_timing=True)
             and all(e.data.get('upto') or game.legal_target(player, e, t)
                     for e, t in zip(free.spell_effects, targets) if e.target in TARGETED))
    if legal and game.cast(player, free, targets, settle=False):
        return True
    player.hand.remove(card)
    return False
