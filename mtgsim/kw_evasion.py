"""Protection and evasion: parser helpers and source-aware rules checks.

Protection keywords retain their quality, so temporary and equipment-granted
abilities use the same DEBT checks as printed abilities.
"""
import re
from functools import lru_cache

COLORS = dict(zip(('white', 'blue', 'black', 'red', 'green'), 'WUBRG'))
TYPES = {'artifact', 'creature', 'enchantment', 'instant', 'sorcery', 'planeswalker', 'land', 'battle'}
LANDWALK = {'plainswalk': 'Plains', 'islandwalk': 'Island', 'swampwalk': 'Swamp',
            'mountainwalk': 'Mountain', 'forestwalk': 'Forest', 'nonbasic landwalk': 'nonbasic',
            'legendary landwalk': 'legendary', 'snow landwalk': 'snow',
            'desertwalk': 'Desert', 'artifact landwalk': 'artifact',
            'snow-covered plainswalk': 'snow:Plains', 'snow-covered islandwalk': 'snow:Island',
            'snow-covered swampwalk': 'snow:Swamp', 'snow-covered mountainwalk': 'snow:Mountain',
            'snow-covered forestwalk': 'snow:Forest'}
LANDWALK.update({'snow ' + k: 'snow:' + v for k, v in list(LANDWALK.items()) if v in ('Plains', 'Island', 'Swamp', 'Mountain', 'Forest')})
KEYWORDS = {'shroud', 'horsemanship', 'shadow', 'fear', 'intimidate', 'skulk'} | set(LANDWALK)
SUBTYPES = {'robots': 'Robot', 'dragons': 'Dragon', 'vampires': 'Vampire', 'werewolves': 'Werewolf',
            'zombies': 'Zombie', 'clerics': 'Cleric', 'goblins': 'Goblin', 'wizards': 'Wizard',
            'assassins': 'Assassin', 'spirits': 'Spirit', 'arcane': 'Arcane', 'elves': 'Elf',
            'beasts': 'Beast', 'kavu': 'Kavu', 'humans': 'Human', 'angels': 'Angel',
            'archons': 'Archon', 'demons': 'Demon'}
QUALITIES = set(SUBTYPES) | {'snow', 'non-spirit creatures', 'sorceries'} | set(COLORS) | TYPES | {t + 's' for t in TYPES} | {
    'everything', 'all colors', 'each color', 'all colours', 'multicolored', 'monocolored',
    'colorless', 'the chosen player'}


def protection(text):
    """Return keywords only for a complete, supported protection phrase."""
    if not text.startswith('protection from '):
        return None
    qualities = re.split(r', (?:and )?(?:from )?| and (?:from )?', text[16:])
    if not qualities or any(q not in QUALITIES for q in qualities):
        return None
    return {'protection from ' + q for q in qualities}


@lru_cache(maxsize=8)
def _keyword_separator(known):
    next_keyword = '|'.join(re.escape(k) for k in sorted(known | KEYWORDS, key=len, reverse=True))
    return re.compile(r'(?:[,;]\s+(?:and )?| and )(?=(?:' + next_keyword + r')(?:[,;.]|$)|protection from |ward \{\d+\})')


def keyword_parts(line, known):
    # Commas and conjunctions inside protection lists belong to that ability.
    return _keyword_separator(frozenset(known)).split(line.lower().rstrip('.'))


def keyword_list(line, known):
    parts = keyword_parts(line, known)
    result = set()
    for part in parts:
        if part in known or part in KEYWORDS:
            result.add(part)
        else:
            parsed = protection(part)
            if parsed is None:
                return None
            result.update(parsed)
    return result


def parse_line(line, keywords, extra):
    low = line.lower().rstrip('.')
    m = re.fullmatch(r'(?:enchanted|equipped) creature has (.+)', low)
    if m:
        kws = keyword_list(m[1], KEYWORDS)
        if kws is not None:
            extra['equip_keywords'] = extra.get('equip_keywords', frozenset()) | kws
            return True
    if low == 'enchanted creature can block only creatures with flying':
        extra['equip_keywords'] = extra.get('equip_keywords', frozenset()) | {'blocks only flying'}
        return True
    if low == 'as ~ enters, choose a player':
        keywords.add('choose protection player')
        return True
    if low == '~ has protection from the chosen player':
        keywords.add('protection from the chosen player')
        return True
    if low == '~ can block only creatures with flying':
        keywords.add('blocks only flying')
        return True
    prefix = "~ can't be blocked except by "
    if low.startswith(prefix):
        quality = low[len(prefix):]
        options = {'creatures with flying': 'flying', 'creatures with flying or reach': 'flying or reach',
                   'creatures with horsemanship': 'horsemanship', 'creatures with shadow': 'shadow',
                   'artifact creatures': 'artifact', 'black creatures': 'black',
                   'artifact creatures and/or black creatures': 'artifact or black',
                   'artifact creatures and/or white creatures': 'artifact or white',
                   'two or more creatures': 'count:2', 'three or more creatures': 'count:3',
                   'creatures with defender': 'defender', 'legendary creatures': 'legendary',
                   'walls and/or creatures with flying': 'walls or flying',
                   'rogues': 'subtype:Rogue', 'vehicles': 'subtype:Vehicle',
                   'spirits': 'subtype:Spirit', 'walls': 'subtype:Wall'}
        options.update({color + ' creatures': color for color in COLORS})
        options.update({'artifact creatures and/or ' + color + ' creatures': 'artifact or ' + color for color in COLORS})
        if quality in options:
            keywords.add('blocked only by ' + options[quality])
            return True
    return False


def colors(source):
    card = getattr(source, 'card', source)
    if card is None:
        return frozenset()
    if card.colors is not None:
        return card.colors
    return frozenset(c for c in 'WUBRG' if c in card.mana_cost or any(c in h for h in card.hybrid))


def candidate_keywords(perm):
    """Potential abilities; has() still checks any condition before applying them."""
    keywords = perm.card.keywords | perm.temp_kw | perm.perm_kw
    for attachment in perm.equipment + perm.auras:
        keywords = keywords | attachment.card.equip_keywords
    if perm.animated:
        keywords = keywords | perm.animated.keywords
    keywords = keywords | {kw for kw, _ in perm.card.cond_keywords}
    if perm.card.keyword_at_counters:
        keywords = keywords | {perm.card.keyword_at_counters[1]}
    for teammate in perm.controller.battlefield:
        keywords = keywords | teammate.card.team_keywords | teammate.card.counter_team_keywords
        keywords = keywords | {kw for _, kw, _ in teammate.card.keyword_sub}
    return keywords


def protected(target, source, by=None):
    """Does target have protection from this source? Never infer color from controller."""
    if source is None:
        return False
    card = getattr(source, 'card', source)
    if card is None:
        return False
    source_controller = getattr(source, 'controller', by)
    for q in (k[16:] for k in candidate_keywords(target)
              if k.startswith('protection from ') and target.has(k)):
        if q == 'everything':
            return True
        if q == 'the chosen player':
            if getattr(target, 'protection_player', None) is source_controller:
                return True
        elif q in COLORS:
            if COLORS[q] in colors(source):
                return True
        elif q in ('all colors', 'each color', 'all colours'):
            if colors(source):
                return True
        elif q == 'colorless':
            if not colors(source):
                return True
        elif q == 'multicolored':
            if len(colors(source)) > 1:
                return True
        elif q == 'monocolored':
            if len(colors(source)) == 1:
                return True
        elif q in SUBTYPES:
            if SUBTYPES[q] in card.subtypes or (card.changeling and SUBTYPES[q] != 'Arcane'):
                return True
        elif q == 'snow':
            if card.snow:
                return True
        elif q == 'non-spirit creatures':
            if getattr(source, 'is_creature', card.is_creature) and 'Spirit' not in card.subtypes and not card.changeling:
                return True
        elif q == 'sorceries':
            if card.is_sorcery:
                return True
        elif q.rstrip('s') in TYPES:
            typ = q.rstrip('s').capitalize()
            if (getattr(source, 'is_creature', card.is_creature) if typ == 'Creature' else typ in card.types):
                return True
    return False


def can_block(blocker, attacker):
    if protected(attacker, blocker):
        return False
    if blocker.has('shadow') != attacker.has('shadow'):
        return False
    if attacker.has('horsemanship') and not blocker.has('horsemanship'):
        return False
    if blocker.has('blocks only flying') and not attacker.has('flying'):
        return False
    if attacker.has('fear') and not (blocker.card.is_artifact or 'B' in colors(blocker)):
        return False
    if attacker.has('intimidate') and not (blocker.card.is_artifact or colors(blocker) & colors(attacker)):
        return False
    if attacker.has('skulk') and blocker.power > attacker.power:
        return False
    for keyword in candidate_keywords(attacker):
        if keyword.startswith('blocked only by ') and attacker.has(keyword):
            if not _blocker_matches(keyword[16:], blocker):
                return False
        kind = LANDWALK.get(keyword)
        if kind is None or not attacker.has(keyword):
            continue
        for land in blocker.controller.battlefield:
            if not land.card.is_land:
                continue
            c = land.card
            if ((kind == 'nonbasic' and not c.basic) or (kind == 'legendary' and c.legendary)
                    or (kind == 'snow' and c.snow) or (kind == 'artifact' and c.is_artifact) or kind in c.subtypes or kind == land.chosen_land
                    or (kind.startswith('snow:') and c.snow and kind[5:] in c.subtypes)):
                return False
    return True


def _blocker_matches(quality, blocker):
    if quality.startswith('count:'):
        return True                 # checked on the entire blocking group
    if quality.startswith('subtype:'):
        sub = quality[8:]
        return sub in blocker.card.subtypes or (blocker.card.changeling and sub != 'Vehicle')
    if quality in COLORS:
        return COLORS[quality] in colors(blocker)
    if quality.startswith('artifact or '):
        return blocker.card.is_artifact or COLORS[quality[12:]] in colors(blocker)
    if quality == 'artifact':
        return blocker.card.is_artifact
    if quality == 'legendary':
        return blocker.card.legendary
    if quality == 'walls or flying':
        return 'Wall' in blocker.card.subtypes or blocker.card.changeling or blocker.has('flying')
    if quality == 'flying or reach':
        return blocker.has('flying') or blocker.has('reach')
    return blocker.has(quality)


def minimum_blockers(attacker):
    return max([2 if attacker.has('menace') else 1] +
               [n for n in (2, 3) if attacker.has('blocked only by count:' + str(n))])


def _grant(m):
    from .cards import Effect, NO_MATCH
    who, ability = m[1].lower(), m[2].lower()
    target = {'~': 'self', 'target creature': 'creature', 'target creature you control': 'creature_mine',
              'it': 'prev', 'that creature': 'prev'}[who]
    if ability == 'protection from the color of your choice':
        return Effect('grant', target=target, data={'keyword': 'protection from chosen color'})
    kws = keyword_list(ability, KEYWORDS)
    if kws is None:
        return NO_MATCH
    return [Effect('grant', target=target if i == 0 or target == 'self' else 'prev', data={'keyword': kw})
            for i, kw in enumerate(sorted(kws))]


EFFECT_PATTERNS = [
    (r'(~|target creature(?: you control)?|it|that creature) gains? '
     r'(protection from [a-z ,]+|shroud|shadow|horsemanship|fear|intimidate|skulk|'
     r'(?:plains|island|swamp|mountain|forest)walk|(?:nonbasic|legendary|snow) landwalk) until end of turn', _grant),
]


def fight(game, p, eff, target, item):
    """Fight/bite damage comes from the creature, including protection and lifelink."""
    mine = item.targets[0] if item and item.targets else None
    if mine is None and item:
        mine = item.source
    if mine is None or target is None or mine not in mine.controller.battlefield or target not in target.controller.battlefield:
        return
    hits = [(mine, target, mine.power)]
    if eff.kind == 'fight':
        hits.append((target, mine, target.power))
    for src, dst, amount in hits:
        if amount <= 0 or protected(dst, src):
            continue
        game.deal_damage(dst, amount, by=src.controller, cause=f'{src.card.name}: {eff.kind}', source=src)
        if src.has('deathtouch'):
            dst.deathtouched = True
        if src.has('lifelink'):
            game.change_life(src.controller, amount, f'{src.card.name}: lifelink')
