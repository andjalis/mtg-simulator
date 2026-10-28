"""Composable, conservative permanent selectors and effects.

This fallback grammar consumes a whole sentence or returns NO_MATCH. Unknown
qualifiers stay visible in coverage; it never discards a restriction to match.
"""
from __future__ import annotations

import re

_NUMBER = r'(?:a|an|one|two|three|four|five|six|seven|eight|nine|ten|\d+)'
_COUNTER = r'(?:[+-]\d+/[+-]\d+|[a-z]+(?:-[a-z]+)?)'
_TYPES = {'creature', 'artifact', 'enchantment', 'land', 'planeswalker', 'battle', 'permanent'}
_COLORS = {'white': 'W', 'blue': 'U', 'black': 'B', 'red': 'R', 'green': 'G'}

# Subtype vocabulary from the local Oracle snapshot; no runtime database dependency.
_CREATURE_SUBTYPES = frozenset((
    'advisor aenar aetherborn alien ally andorian android angel antelope ape archer archon armadillo armored '
    'artificer assassin assembly-worker astartes atog aurochs avatar azra badger barbarian bard basilisk bat '
    'bear beast beaver beeble beholder berserker bird bison boar borg brainiac bringer brushwagg caitian camel '
    'capybara carrier cat centaur chef child chimera citizen clamfolk cleric clown cockatrice construct cow '
    'coward coyote crab crocodile custodes cyberman cyborg cyclops dauthi demigod demon detective devil '
    'dinosaur djinn doctor dog dragon drake dreadnought drix drone druid dryad dwarf echidna efreet egg elder '
    'eldrazi elemental elephant elf elk employee eternal eye faerie ferret fish flagbearer fox fractal frog '
    'fungus gamer gamma gargoyle giant giraffe gith glimmer gnoll gnome goat goblin god golem gorgon gorn '
    'gremlin griffin guest hag halfling hamster harpy hedgehog hellion hero hippo hippogriff homarid '
    'homunculus horror horse human hydra hyena illusion imp incarnation inhuman inkling inquisitor insect '
    'jackal jellyfish judge juggernaut kangaroo kavu kelpien killbot kirin kithkin klingon knight kobold kor '
    'kraken kree lamia lammasu lanthanite leech lemur leviathan lhurgoyf licid lizard lobster lord mammoth '
    'manticore masticore mercenary merfolk metathran minion minotaur mite mole monger mongoose monk monkey '
    'moogle moonfolk mount mouse mutant myr mystic nautilus necron nephilim nightmare nightstalker ninja noble '
    'noggle nomad nymph octopus officer ogre ooze orc orgg orion otter ouphe ox oyster pangolin peasant '
    'pegasus performer pest phelddagrif phoenix phyrexian pilot pirate plant platypus porcupine possum praetor '
    'primarch processor q qu rabbit raccoon ranger rat rebel reflection rhino rigger robot rogue sable '
    'salamander samurai sand saproling satyr scarecrow scientist scorpion scout seal serpent shade shaman '
    'shapeshifter shark sheep siren skeleton skrull skunk slith sliver sloth slug snail snake soldier soltari '
    'sorcerer spawn specter spellshaper sphinx spider spike spirit sponge spy squid squirrel starfish surrakar '
    'survivor symbiote synth talosian tellarite thalakos tholian thopter thrull tiefling tosk toy treefolk '
    'tribble trill trilobite troll turtle tyranid unicorn utrom vampire varmint vedalken villain volver vorta '
    'vulcan wall walrus warlock warrior weasel weird werewolf whale wizard wolf wolverine wombat worm wraith '
    'wurm xindi yeti zombie zubera '
).split())
_SUBTYPE_TYPES = {name: ['creature'] for name in _CREATURE_SUBTYPES}
_SUBTYPE_TYPES.update({'ajani': ['planeswalker'],
 'aminatou': ['planeswalker'],
 'angrath': ['planeswalker'],
 'arlinn': ['planeswalker'],
 'arzakon': ['planeswalker'],
 'ashiok': ['planeswalker'],
 'attraction': ['artifact'],
 'aura': ['enchantment'],
 'background': ['enchantment'],
 'bahamut': ['planeswalker'],
 'basri': ['planeswalker'],
 'bobblehead': ['artifact'],
 'bolas': ['planeswalker'],
 'book': ['artifact'],
 'calix': ['planeswalker'],
 'cartouche': ['enchantment'],
 'case': ['enchantment'],
 'cave': ['land'],
 'chandra': ['planeswalker'],
 'class': ['enchantment'],
 'clue': ['artifact', 'land'],
 'comet': ['planeswalker'],
 'communicator': ['artifact'],
 'contraption': ['artifact'],
 'curse': ['enchantment'],
 'dack': ['planeswalker'],
 'dakkon': ['planeswalker'],
 'daretti': ['planeswalker'],
 'davriel': ['planeswalker'],
 'deb': ['planeswalker'],
 'dellian': ['planeswalker'],
 'desert': ['land'],
 'dihada': ['planeswalker'],
 'domri': ['planeswalker'],
 'dovin': ['planeswalker'],
 'duck': ['planeswalker'],
 'dyfed': ['planeswalker'],
 'ellywick': ['planeswalker'],
 'elminster': ['planeswalker'],
 'elspeth': ['planeswalker'],
 'equipment': ['artifact', 'planeswalker'],
 'ersta': ['planeswalker'],
 'estrid': ['planeswalker'],
 'feroz': ['planeswalker'],
 'food': ['artifact'],
 'forest': ['land'],
 'fortification': ['artifact'],
 'freyalise': ['planeswalker'],
 'garruk': ['planeswalker'],
 'gate': ['land'],
 'gideon': ['planeswalker'],
 'greensleeves': ['planeswalker'],
 'grist': ['planeswalker'],
 'guff': ['planeswalker'],
 'huatli': ['planeswalker'],
 'infinity': ['artifact'],
 'inzerva': ['planeswalker'],
 'island': ['artifact', 'land'],
 'jace': ['planeswalker'],
 'jared': ['planeswalker'],
 'jaya': ['planeswalker'],
 'jeska': ['planeswalker'],
 'kaito': ['planeswalker'],
 'karn': ['planeswalker'],
 'kasmina': ['planeswalker'],
 'kaya': ['planeswalker'],
 'key': ['artifact'],
 'kiora': ['planeswalker'],
 'koth': ['planeswalker'],
 'lair': ['land'],
 'liliana': ['planeswalker'],
 'locus': ['land'],
 'lolth': ['planeswalker'],
 'lukka': ['planeswalker'],
 'master': ['planeswalker'],
 'mine': ['land'],
 'minsc': ['planeswalker'],
 'monopoly': ['planeswalker'],
 'mordenkainen': ['planeswalker'],
 'mountain': ['land'],
 'nahiri': ['planeswalker'],
 'narset': ['planeswalker'],
 'niko': ['planeswalker'],
 'nissa': ['planeswalker'],
 'nixilis': ['planeswalker'],
 'oko': ['planeswalker'],
 'omenpath': ['land'],
 'plains': ['land'],
 'plan': ['enchantment'],
 'planet': ['land'],
 'power-plant': ['land'],
 'powerstone': ['artifact'],
 'quintorius': ['planeswalker'],
 'ral': ['planeswalker'],
 'room': ['enchantment'],
 'rowan': ['planeswalker'],
 'rune': ['enchantment'],
 'saga': ['enchantment', 'land'],
 'saheeli': ['planeswalker'],
 'samut': ['planeswalker'],
 'sarkhan': ['planeswalker'],
 'serra': ['planeswalker'],
 'shrine': ['enchantment'],
 'siege': ['battle'],
 'sifa': ['planeswalker'],
 'sivitri': ['planeswalker'],
 'sorin': ['planeswalker'],
 'spacecraft': ['artifact'],
 'sphere': ['land'],
 'stone': ['artifact', 'planeswalker'],
 'svega': ['planeswalker'],
 'swamp': ['land'],
 'szat': ['planeswalker'],
 'tamiyo': ['planeswalker'],
 'tasha': ['planeswalker'],
 'teferi': ['planeswalker'],
 'teyo': ['planeswalker'],
 'tezzeret': ['planeswalker'],
 'thomil': ['planeswalker'],
 'tibalt': ['planeswalker'],
 'tower': ['land'],
 'town': ['land'],
 'treasure': ['artifact'],
 'tyvar': ['planeswalker'],
 'ugin': ['planeswalker'],
 'urza': ['planeswalker'],
 'vehicle': ['artifact', 'land'],
 'venser': ['planeswalker'],
 'vivien': ['planeswalker'],
 'vraska': ['planeswalker'],
 'vronos': ['planeswalker'],
 'will': ['planeswalker'],
 'windgrace': ['planeswalker'],
 'worzel': ['planeswalker'],
 'wrenn': ['land', 'planeswalker'],
 'xenagos': ['planeswalker'],
 'yanggu': ['planeswalker'],
 'yanling': ['planeswalker'],
 'zariel': ['planeswalker']})


def keywords(text):
    from .cards.model import KEYWORDS
    parts = re.split(r',? and |, ', text.lower().strip())
    return parts if parts and all(p in KEYWORDS for p in parts) else None


def selector(text, *, plural=False):
    """Parse a restricted battlefield noun phrase, preserving every constraint."""
    text = text.strip()
    result = {}
    if text.lower().startswith(('other ', 'another ')):
        result['other'] = True
        text = text.split(' ', 1)[1]
    text = re.sub(r'^(?:a|an) ', '', text, flags=re.I)
    for scope, label in ((" you control", 'mine'), (" an opponent controls", 'opp'), (" you don't control", 'opp'), (" your opponents control", 'opp')):
        if scope in text.lower():
            if 'controller' in result or text.lower().count(scope) != 1:
                return None
            tail = text.lower().split(scope, 1)[1]
            if tail and not tail.startswith((' with ', ' without ')):
                return None
            text = re.sub(re.escape(scope), '', text, flags=re.I)
            result['controller'] = label
    base = re.search(r' with base power and toughness (\d+)/(\d+)$', text, re.I)
    if base:
        result['base_pt'] = [int(base[1]), int(base[2])]
        text = text[:base.start()]
    # Only one supported trailing predicate; additional text fails below.
    m = re.search(r' with (power|toughness|mana value) (\d+) or (less|greater)$', text, re.I)
    if m:
        result['stat'] = [m[1].lower(), '<=' if m[3].lower() == 'less' else '>=', int(m[2])]
        text = text[:m.start()]
    else:
        m = re.search(rf' (with|without) (?:an? )?({_COUNTER}) counters?(?: on (?:it|them))?$', text, re.I)
        if m:
            result['counter'] = [m[2].lower(), m[1].lower() == 'with']
            text = text[:m.start()]
        else:
            m = re.search(r' (with|without) ([a-z ]+)$', text, re.I)
            if m:
                kws = keywords(m[2])
                if not kws or len(kws) != 1:
                    return None
                result['keyword'] = [kws[0], m[1].lower() == 'with']
                text = text[:m.start()]
    words = text.split()
    if plural:
        irregular = {'elves': 'Elf', 'dwarves': 'Dwarf', 'wolves': 'Wolf'}
        words = [irregular.get(w.lower(), w[:-1] if w.lower().endswith('s') and
                 not w.lower().endswith('ss') else w) for w in words]
    if not words:
        return None
    # Type unions are explicit. Prefix modifiers are intersections.
    if 'or' in [w.lower() for w in words]:
        alts = re.split(r',? or |, ', ' '.join(words).lower())
        if not all(alt in _TYPES for alt in alts):
            return None
        result['types_any'] = alts
    else:
        types = []
        for word in words:
            low = word.lower()
            if low in _TYPES:
                types.append(low)
            elif low in ('tapped', 'untapped', 'attacking', 'blocking', 'legendary', 'nonlegendary', 'token', 'nontoken',
                         'nonland', 'noncreature', 'nonartifact', 'colorless', 'multicolored', 'monocolored'):
                result.setdefault('traits', []).append(low)
            elif low in _COLORS:
                result.setdefault('colors', []).append(_COLORS[low])
            elif low.startswith('non-') and low[4:] in _SUBTYPE_TYPES:
                result.setdefault('not_subtypes', []).append(word[4:].lower())
            elif low in _SUBTYPE_TYPES:
                result.setdefault('subtypes', []).append(low)
            else:
                return None
        if not types and not result.get('subtypes'):
            return None
        if types:
            result['types_all'] = types
        else:
            result['types_any'] = ['permanent']
    return result


def matches(game, permanent, spec, controller, source=None):
    if 'base_pt' in spec:
        from .continuous import base_pt
        if tuple(spec['base_pt']) != base_pt(permanent):
            return False
    if spec.get('other') and permanent is source:
        return False
    if spec.get('controller') and (permanent.controller is controller) != (spec['controller'] == 'mine'):
        return False
    def has_type(kind):
        return permanent.is_creature if kind == 'creature' else True if kind == 'permanent' else kind.title() in permanent.card.types
    if not all(has_type(kind) for kind in spec.get('types_all', [])):
        return False
    if 'types_any' in spec and not any(has_type(kind) for kind in spec['types_any']):
        return False
    subs = {s.lower() for s in permanent.card.subtypes}
    changeling = permanent.card.changeling and permanent.is_creature
    if not all(s in subs or changeling and s in _CREATURE_SUBTYPES for s in spec.get('subtypes', [])):
        return False
    if any(s in subs or changeling and s in _CREATURE_SUBTYPES for s in spec.get('not_subtypes', [])):
        return False
    if not all(c in permanent.card.colors for c in spec.get('colors', [])):
        return False
    for trait in spec.get('traits', []):
        if trait in ('tapped', 'untapped') and permanent.tapped != (trait == 'tapped'):
            return False
        if trait in ('legendary', 'nonlegendary') and permanent.card.legendary != (trait == 'legendary'):
            return False
        if trait in ('token', 'nontoken') and permanent.card.is_token != (trait == 'token'):
            return False
        if trait.startswith('non') and trait[3:] in _TYPES and has_type(trait[3:]):
            return False
        if trait == 'colorless' and permanent.card.colors or trait == 'multicolored' and len(permanent.card.colors) < 2 or trait == 'monocolored' and len(permanent.card.colors) != 1:
            return False
        if trait == 'attacking' and permanent not in game.attackers:
            return False
        if trait == 'blocking' and not any(permanent in group for group in game.blocks.values()):
            return False
    if 'counter' in spec:
        name, positive = spec['counter']
        if (permanent.counters.get(name, 0) > 0) != positive:
            return False
    if 'keyword' in spec:
        name, present = spec['keyword']
        if permanent.has(name) != present:
            return False
    if 'stat' in spec:
        stat, op, n = spec['stat']
        value = permanent.card.cmc if stat == 'mana value' else getattr(permanent, stat)
        if not (value <= n if op == '<=' else value >= n):
            return False
    return True


def subject(text):
    """Return target kind and selector data, or None for unsupported subjects."""
    low = text.lower().strip()
    if low in ('~', 'this creature', 'this permanent'):
        return 'self', {}
    if low in ('it', 'that creature', 'that permanent'):
        return 'prev', {}
    if low in ('enchanted creature', 'equipped creature'):
        return 'host', {}
    m = re.fullmatch(r'(up to one )?(?:another |other )?target (.+)', text, re.I)
    if m:
        spec = selector(m[2])
        if spec is None:
            return None
        if re.search(r'\b(?:another|other) target', text, re.I):
            spec['other'] = True
        data = {'selector': spec}
        if m[1]:
            data['optional_target'] = True
        return 'permanent', data
    m = re.fullmatch(r'(?:each|all) (.+)', text, re.I)
    if m:
        spec = selector(m[1], plural=True)
        return ('group', {'selector': spec}) if spec is not None else None
    # "Creatures you control ..." has no each/all prefix.
    if low.startswith(('creatures ', 'other creatures ')):
        spec = selector(text, plural=True)
        return ('group', {'selector': spec}) if spec is not None else None
    return None


def build(kind, obj, *, amount=0, amount2=0, data=None):
    from .cards.model import Effect
    subj = subject(obj)
    if subj is None:
        return None
    target, more = subj
    combined = dict(more, **(data or {}))
    if target == 'group':
        return Effect('permanent_group', data={'selector': more['selector'], 'effect':
                      Effect(kind, amount, amount2, target='self', data=data or {})})
    return Effect(kind, amount, amount2, target=target, data=combined)


def parse_effect(text):
    """Fallback operations; quantities and restrictions must be understood completely."""
    from .cards.model import _num
    quoted = re.fullmatch(r'(.+?) gains? "(.+)" until end of turn', text, re.I)
    reversed_quote = re.fullmatch(r'until end of turn, (.+?) gains? "(.+)"', text, re.I)
    quoted = quoted or reversed_quote
    if quoted:
        from .cards.parse import _parse_trigger
        body = re.sub(r'\bthis (?:creature|permanent)\b', '~', quoted[2], flags=re.I)
        body = body[0].upper() + body[1:]
        if not body.endswith('.'):
            body += '.'
        parsed = _parse_trigger(body)
        if parsed and parsed[0] and not parsed[1] and parsed[2] is None:
            return build('grant_triggers', quoted[1], data={'triggers': parsed[0]})
        return None
    m = re.fullmatch(r'(.+?) gets? ([+-]\d+)/([+-]\d+)(?: and gains? (.+))? until end of turn', text, re.I)
    if m:
        kws = keywords(m[4]) if m[4] else []
        if kws is None:
            return None
        p, t = int(m[2]), int(m[3])
        eff = build('debuff_one' if p <= 0 and t < 0 else 'pump', m[1],
                    amount=-p if p <= 0 and t < 0 else p, amount2=-t if p <= 0 and t < 0 else t)
        if eff is not None:
            out = [eff]
            for kw in kws:
                grant = build('grant', 'it' if eff.target == 'permanent' else m[1], data={'keyword': kw})
                out.append(grant)
            return out
    m = re.fullmatch(r'(.+?) gains? (.+) until end of turn', text, re.I)
    if m:
        kws = keywords(m[2])
        if kws:
            first = build('grant', m[1], data={'keyword': kws[0]})
            if first is not None:
                return [first] + [build('grant', 'it' if first.target == 'permanent' else m[1], data={'keyword': k}) for k in kws[1:]]
    m = re.fullmatch(rf'put ({_NUMBER}) ({_COUNTER}) counters? on (.+)', text, re.I)
    if m:
        return build('add_counter', m[3], amount=_num(m[1]), data={'counter': m[2].lower()})
    m = re.fullmatch(rf'remove ({_NUMBER}) ({_COUNTER}) counters? from (.+)', text, re.I)
    if m:
        return build('modify_counters', m[3], amount=_num(m[1]), data={'counter': m[2].lower(), 'operation': 'remove'})
    m = re.fullmatch(rf'double the number of ({_COUNTER}) counters on (.+)', text, re.I)
    if m:
        return build('modify_counters', m[2], data={'counter': m[1].lower(), 'operation': 'double'})
    m = re.fullmatch(r'double (?:the number of )?(?:each kind of )?counters? on (.+)', text, re.I)
    if m:
        return build('modify_counters', m[1], data={'operation': 'double'})
    m = re.fullmatch(r'(tap|untap|regenerate|destroy|exile) (.+)', text, re.I)
    if m:
        # Exile and destroy are distinct operations, never interchangeable.
        kind = {'untap': 'untap_prev', 'exile': 'exile_permanent'}.get(m[1].lower(), m[1].lower())
        # Group removal needs simultaneous-death bookkeeping; leave that to existing templates.
        eff = build(kind, m[2], amount=1 if kind == 'regenerate' else 0)
        if eff is not None and (kind != 'exile_permanent' or eff.target == 'permanent') and (eff.kind != 'permanent_group' or kind in ('tap', 'untap_prev', 'regenerate')):
            return eff
    m = re.fullmatch(r"return (.+) to (?:its|their) owner's hand", text, re.I)
    if m:
        eff = build('bounce', m[1])
        if eff is not None and eff.kind != 'permanent_group':
            return eff
    return None


def parse_line(line, st):
    from .cards.model import _num
    m = re.fullmatch(rf'~ enters(?: the battlefield)? with ({_NUMBER}) ({_COUNTER}) counters? on it\.', line, re.I)
    if m and m[2].lower() not in ('+1/+1', '-1/-1') and not st.extra.get('etb_named_counters'):
        st.extra['etb_named_counters'] = (m[2].lower(), _num(m[1]))
        return True
    # Static keyword grants reuse the same selectors as targeted operations.
    m = re.fullmatch(r'(.+?) (?:have|has) (.+)\.', line)
    if m:
        spec, kws = selector(re.sub(r'^All ', '', m[1]), plural=True), keywords(m[2])
        if spec is not None and kws and not any(k in ('training', 'dethrone', 'exalted') for k in kws):
            # Avoid recursive keyword dependencies until the layer system owns them.
            if 'keyword' in spec:
                return False
            st.extra['static_keyword_grants'] = st.extra.get('static_keyword_grants', ()) + ((spec, tuple(kws)),)
            return True
    return False


def _fallback(match):
    from .cards.model import Effect, NO_MATCH
    result = parse_effect(match[1])
    if isinstance(result, list) and result and all(e.kind == 'permanent_group' for e in result):
        spec = result[0].data['selector']
        if all(e.data['selector'] == spec for e in result):
            return Effect('permanent_group', data={'selector': spec, 'effects': [e.data['effect'] for e in result]})
    return result or NO_MATCH


def split_sentences(text):
    """Split Oracle sentences without breaking the body of a quoted ability."""
    start, quoted = 0, False
    for i, char in enumerate(text):
        if char == '"':
            quoted = not quoted
        if char == '.' and not quoted and i + 1 < len(text) and text[i + 1].isspace():
            yield text[start:i + 1]
            start = i + 1
    if text[start:].strip():
        yield text[start:]


def _exact_exile(match):
    from .cards.model import NO_MATCH
    effect = parse_effect('exile ' + match[1])
    return effect if effect is not None and effect.kind == 'exile_permanent' else NO_MATCH


PRIORITY_PATTERNS = [(r'exile (.+)', _exact_exile)]
EFFECT_PATTERNS = [(r'(.+)', _fallback)]
SUBS = []
