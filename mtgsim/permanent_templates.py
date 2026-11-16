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
    'advisor aenar aetherborn alien ally andorian android angel antelope ape archer archon armadillo armored army '
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


_OUTLAWS = ['assassin', 'mercenary', 'pirate', 'rogue', 'warlock']     # rule 700.12

_TRAITS = frozenset((
    'tapped', 'untapped', 'attacking', 'blocking', 'legendary', 'nonlegendary', 'token', 'nontoken',
    'nonland', 'noncreature', 'nonartifact', 'colorless', 'multicolored', 'monocolored',
    'suspected', 'snow', 'nonsnow', 'face-up'))
_IRREGULAR = {'elves': 'Elf', 'dwarves': 'Dwarf', 'wolves': 'Wolf'}


def _singular(word, plural):
    """One word of a plural noun phrase in the singular; "Frogs," in a list keeps its comma."""
    if not plural:
        return word
    comma = ',' if word.endswith(',') else ''
    word = word.rstrip(',')
    low = word.lower()
    return _IRREGULAR.get(low, word[:-1] if low.endswith('s') and not low.endswith('ss') else word) + comma


def _classify(low):
    """One lowercased selector word -> (bucket, value), or None when unsupported."""
    if low in _TYPES:
        return 'type', low
    if low in _TRAITS or low.startswith('non') and low[3:] in _TYPES:
        return 'traits', low
    if low in _COLORS:
        return 'colors', _COLORS[low]
    if low in ('outlaw', 'outlaws'):          # rule 700.12: Assassins, Mercenaries, Pirates, Rogues, Warlocks
        return 'any_subtypes', _OUTLAWS
    if low == 'non-outlaw':
        return 'not_subtypes', _OUTLAWS
    if low.startswith('non-') and low[4:] in _SUBTYPE_TYPES:
        return 'not_subtypes', low[4:]
    if low in _SUBTYPE_TYPES:
        return 'subtypes', low
    return None


def _words_spec(words):
    """Plain selector words (lower case, singular, no union) -> a spec fragment, or None when a word is
    unknown or no word names a type or subtype."""
    spec, types = {}, []
    for low in words:
        kind = _classify(low)
        if kind is None:
            return None
        bucket, value = kind
        if bucket == 'type':
            types.append(value)
        else:
            spec.setdefault(bucket, []).extend(value if isinstance(value, list) else [value])
    if not types and not spec.get('subtypes') and not spec.get('any_subtypes'):
        return None
    if types:
        spec['types_all'] = types
    else:
        spec['types_any'] = ['permanent']
    return spec


def _is_noun(word):
    return _classify(word)[0] in ('type', 'subtypes', 'any_subtypes')


def _union_spec(alts):
    """A type / subtype union whose alternatives carry modifiers (#506), or None when an alternative is unread.

    Adjectives written before the first alternative's noun distribute over the bare one-word alternatives after
    it: "nontoken artifact or creature" = nontoken (artifact or creature), "attacking Wolf or Werewolf",
    "tapped creature or Vehicle". A bare subtype takes the type the last alternative ends in when it is a subtype of
    it: "Elf or Soldier creature" = Elf creature or Soldier creature. When every alternative is then the same
    adjectives plus one type (or one subtype of the same type), the union reads flat (types_any / subtypes_any).
    Anything else is read exactly as written, as an "alts" list of word tuples, words ANDed within an alternative
    and ORed across them: "artifact or nontoken creature" = artifact, or nontoken creature."""
    parsed = [alt.split() for alt in alts]
    if any(not words or _words_spec(words) is None for words in parsed):
        return None
    run = []
    for word in parsed[0]:
        if _is_noun(word):
            break
        run.append(word)
    if run:
        parsed = parsed[:1] + [run + words if len(words) == 1 else words for words in parsed[1:]]
    last = parsed[-1]
    head = last[-1] if len(last) > 1 and last[-1] in _TYPES and _classify(last[-2])[0] == 'subtypes' else None
    if head:
        parsed = [words + [head] if _classify(words[-1])[0] == 'subtypes' and head in _SUBTYPE_TYPES[words[-1]]
                  else words for words in parsed]
    n = len(run)
    if all(words[:n] == run for words in parsed):
        nouns = [words[n:] for words in parsed]
        flat = None
        if all(len(noun) == 1 and noun[0] in _TYPES for noun in nouns):
            flat = {'types_any': [noun[0] for noun in nouns]}
        elif all(noun[1:] == ([head] if head else []) and _classify(noun[0])[0] == 'subtypes' for noun in nouns):
            flat = {'subtypes_any': [noun[0] for noun in nouns], 'types_all' if head else 'types_any': [head or 'permanent']}
        if flat is not None:
            spec = _words_spec(run + ['permanent'])
            del spec['types_all']
            spec.update(flat)
            return spec
    return {'alts': [tuple(words) for words in parsed]}



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
    # "creatures you control that entered this turn", "each creature that entered the battlefield under your control
    # this turn" (#327): the permanents whose current object entered on this turn (Permanent.entered_turn)
    # ("entered under your control" would need the controller it entered under, which isn't recorded: refused)
    entered = re.search(r' that entered(?: the battlefield)?( under your control)? this turn$', text, re.I)
    if entered:
        if entered[1]:
            return None
        result['entered_turn'] = True
        text = text[:entered.start()]
    # "target permanent other than ~" (#645): the source itself is excluded, like "another"
    other = re.search(r' other than (?:~|this (?:creature|permanent|artifact|enchantment|land))$', text, re.I)
    if other:
        result['other'] = result['other_than_source'] = True
        text = text[:other.start()]
    # "nonland, nontoken permanent", "non-Saga, nonland permanent" (#506)
    text = re.sub(r'(\bnon-?[a-z]+), (?=non-?[a-z]+\b)', r'\1 ', text, flags=re.I)
    # "creatures you control of the chosen type" (#627): the source's chosen creature type (perm.chosen_type)
    chosen = re.search(r" (that aren't )?of the chosen (?:creature )?type(?= you control| your opponents control|"
                       r" an opponent controls|$)", text, re.I)
    if chosen:
        result['chosen_type'] = 'not' if chosen[1] else True
        text = text[:chosen.start()] + text[chosen.end():]
    # "creatures named Paper Tiger", "other creatures you control named ~", "creature named ~ you control" (#314):
    # a name, read up to a controller / zone phrase or the end ("~" is the source's own name)
    text = re.sub(r" on the battlefield( named .+)$", r"\1", text)    # "other creature on the battlefield named ~"
    named = re.search(r" named (~|[A-Z][\w'-]*(?:,? (?:[A-Z][\w'-]*|of|the|and|de|la|to|from|in))*)"
                      r"(?=$| you control| an opponent controls| on the battlefield)", text)
    if named:
        result['name'] = named[1]
        text = text[:named.start()] + text[named.end():]
    for scope, label in ((" you own", 'mine'), (" an opponent owns", 'opp')):
        if scope in text.lower():
            if 'owner' in result or text.lower().count(scope) != 1:
                return None
            tail = text.lower().split(scope, 1)[1]
            if tail and not tail.startswith((' with ', ' without ')):
                return None
            text = re.sub(re.escape(scope), '', text, flags=re.I)
            result['owner'] = label
    for scope, label in ((" you control", 'mine'), (" an opponent controls", 'opp'), (" you don't control", 'opp'), (" your opponents control", 'opp'),
                         (" each opponent controls", 'opp'), (" target opponent controls", 'opp'),
                         (" that player controls", 'that_player'), (" defending player controls", 'defending')):
        if scope in text.lower():
            if 'controller' in result or text.lower().count(scope) != 1:
                return None
            tail = text.lower().split(scope, 1)[1]
            if tail and not tail.startswith((' with ', ' without ')):
                return None
            text = re.sub(re.escape(scope), '', text, flags=re.I)
            if label in ('that_player', 'defending'):
                # the trigger's player / the player the source attacks (#338): an opponent wherever only "opp" is
                # read; matches() narrows it to that exact player when the trigger gives one (scope_player)
                result['scope'] = label
                label = 'opp'
            result['controller'] = label
    base = re.search(r' with base power and toughness (\d+)/(\d+)$', text, re.I)
    if base:
        result['base_pt'] = [int(base[1]), int(base[2])]
        text = text[:base.start()]
    # Only one supported trailing predicate; additional text fails below.
    m = re.search(r' with (power|toughness|mana value) (\d+)(?: or (less|greater))?$', text, re.I)
    rel = re.search(r' with toughness greater than (?:its|their) power$', text, re.I)
    if rel:          # Doran's friends: "each creature you control with toughness greater than its power"
        result['tough_gt_power'] = True
        text = text[:rel.start()]
    elif m:
        result['stat'] = [m[1].lower(), '==' if not m[3] else '<=' if m[3].lower() == 'less' else '>=', int(m[2])]
        text = text[:m.start()]
    else:
        m = re.search(rf' (with|without) (?:an? )?({_COUNTER}) counters?(?: on (?:it|them))?$', text, re.I)
        if m:
            result['counter'] = [m[2].lower(), m[1].lower() == 'with']
            text = text[:m.start()]
        elif re.search(r' with (modular|fading|level up)$', text, re.I):
            # abilities kept as card fields, not keywords: "each creature you control with modular" (#327)
            m = re.search(r' with (modular|fading|level up)$', text, re.I)
            result['ability'] = m[1].lower()
            text = text[:m.start()]
        else:
            m = re.search(r' (with|without) ([a-z ]+)$', text, re.I)
            if m:
                kws = keywords(m[2])
                if not kws or len(kws) != 1:
                    return None
                result['keyword'] = [kws[0], m[1].lower() == 'with']
                text = text[:m.start()]
    words = [_singular(w, plural) for w in text.split()]
    if not words:
        return None
    # Type unions are explicit. Prefix modifiers are intersections.
    lows = [w.lower() for w in words]
    if 'or' in lows or 'and' in lows:
        # "artifact or creature"; a list of subtypes is a union too, with "or" or (for "each ...") "and":
        # "target Bird, Cat, Dog, Goat, Ox, or Snake", "each Pest, Bat, Insect, Snake, and Spider you control" (#327)
        alts = re.split(r',? or |,? and |, ', ' '.join(words).lower())
        if 'or' in lows and all(alt in _TYPES for alt in alts):
            result['types_any'] = alts
        elif len(alts) > 1 and all(alt in _SUBTYPE_TYPES for alt in alts):
            result['subtypes_any'] = alts
            result['types_any'] = ['permanent']
        else:
            union = _union_spec(alts) if 'or' in lows and 'and' not in lows else None
            if union is None:
                return None
            result.update(union)
    else:
        parsed = _words_spec(lows)
        if parsed is None:
            return None
        result.update(parsed)
    return result


def scope_player(game, scope):
    """The player "that player" / "defending player" names for the ability whose targets are being chosen or
    checked, or None when it can't be told (then the selector's "opp" stands)."""
    if game is None:
        return None
    from .engine.state import Permanent, Player, StackItem
    item = getattr(game, "target_source", None)
    if not isinstance(item, StackItem):
        item = getattr(game, "resolving_item", None) or item       # group effects: the resolving ability
    ctx = getattr(game, "trigger_context", None)
    if ctx is None and isinstance(item, StackItem):
        ctx = item.context
    if scope == 'that_player':
        chosen = getattr(game, "_choosing_targets", None) if isinstance(getattr(game, "_choosing_targets", None), list) \
            else (item.targets if isinstance(item, StackItem) else [])
        named = [t for t in chosen or () if isinstance(t, Player)]
        if named:
            return named[0]                 # "Target player ... target creature that player controls"
        if isinstance(ctx, StackItem):
            ctx = ctx.controller            # a cast trigger's context is the spell: its caster
        return ctx if isinstance(ctx, Player) else None
    src = item.source if isinstance(item, StackItem) else item
    attacked = None
    for obj in (ctx, src):      # the attacker: the trigger's event object ("Whenever a creature attacks"), else ~
        attacked = game.attack_targets.get(obj) if isinstance(obj, Permanent) else None
        if attacked is not None:
            break
    if isinstance(attacked, Permanent):
        attacked = attacked.controller
    return attacked if isinstance(attacked, Player) else None


def _named(permanent, name, source) -> bool:
    """"named ~": the source's own name (its card's, so a copy of it counts); else the printed name."""
    if name == "~":
        card = getattr(source, "card", source)
        name = getattr(card, "name", None)
        if name is None:
            return False
    return permanent.card.name == name or getattr(permanent.card, "front_name", None) == name


def matches(game, permanent, spec, controller, source=None):
    if 'cx_desc' in spec:            # a richer noun phrase (mtgsim.cx_grammar)
        from .cx_grammar import desc_matches
        return desc_matches(game, permanent, spec, controller, source)
    if 'base_pt' in spec:
        from .continuous import base_pt
        if tuple(spec['base_pt']) != base_pt(permanent):
            return False
    if spec.get('other') and permanent is source:
        return False
    if spec.get('chosen_type'):
        from .cx_chosen_type import type_of
        typ = type_of(game, source)
        if not typ:
            return False
        of_type = typ.lower() in {s.lower() for s in permanent.card.subtypes} or \
            permanent.card.changeling and permanent.is_creature
        if of_type != (spec['chosen_type'] is True):
            return False
    if 'name' in spec and not _named(permanent, spec['name'], source):
        return False
    scoped = scope_player(game, spec['scope']) if spec.get('scope') else None
    if scoped is not None:
        if permanent.controller is not scoped:
            return False
    elif spec.get('controller') and (permanent.controller is controller) != (spec['controller'] == 'mine'):
        return False
    if spec.get('owner') and (permanent.owner is controller) != (spec['owner'] == 'mine'):
        return False
    if 'alts' in spec and not any(matches(game, permanent, _words_spec(list(alt)), controller, source)
                                  for alt in spec['alts']):
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
    if 'subtypes_any' in spec and not any(s in subs or changeling and s in _CREATURE_SUBTYPES
                                          for s in spec['subtypes_any']):
        return False
    if spec.get('any_subtypes') and not (subs & set(spec['any_subtypes']) or changeling):
        return False
    if not all(c in permanent.card.colors for c in spec.get('colors', [])):
        return False
    if 'colors_any' in spec and not set(spec['colors_any']) & set(permanent.card.colors):       # "red or green"
        return False
    if set(spec.get('not_colors', ())) & set(permanent.card.colors):                            # "nonblack"
        return False
    for trait in spec.get('traits', []):
        if trait in ('tapped', 'untapped') and permanent.tapped != (trait == 'tapped'):
            return False
        if trait in ('legendary', 'nonlegendary') and permanent.card.legendary != (trait == 'legendary'):
            return False
        if trait in ('token', 'nontoken') and permanent.card.is_token != (trait == 'token'):
            return False
        if trait == 'face-up' and getattr(permanent, 'hidden', None) is not None:
            return False        # face down: manifested / morphed / disguised (Permanent.hidden) (#540)
        if trait.startswith('non') and trait[3:] in _TYPES and has_type(trait[3:]):
            return False
        if trait == 'colorless' and permanent.card.colors or trait == 'multicolored' and len(permanent.card.colors) < 2 or trait == 'monocolored' and len(permanent.card.colors) != 1:
            return False
        if trait == 'attacking' and permanent not in game.attackers:
            return False
        if trait == 'declared_attacker' and not (permanent in game.attackers and           # declared, not put onto
                                                 getattr(permanent, 'attack_count', (None, 0))[0] == game.turn):  # the battlefield attacking
            return False
        if trait == 'blocking' and not any(permanent in group for group in game.blocks.values()):
            return False
        if trait == 'suspected' and not permanent.has('suspected'):
            return False
        if trait in ('snow', 'nonsnow') and bool(permanent.card.snow) != (trait == 'snow'):
            return False
    if 'counter' in spec:
        name, positive = spec['counter']
        has = any(n > 0 for n in permanent.counters.values()) if name in ('a', 'an') else \
            permanent.counters.get(name, 0) > 0         # "with a counter on it": any kind (#630)
        if has != positive:
            return False
    if 'keyword' in spec:
        name, present = spec['keyword']
        if permanent.has(name) != present:
            return False
    if spec.get('entered_turn') and getattr(permanent, 'entered_turn', -1) != game.turn:
        return False
    if 'ability' in spec and not (permanent.card.level_blocks if spec['ability'] == 'level up'
                                  else getattr(permanent.card, spec['ability'], 0)):
        return False
    if spec.get('tough_gt_power') and not permanent.toughness > permanent.power:
        return False
    if 'stat' in spec:
        stat, op, n = spec['stat']
        value = permanent.card.cmc if stat == 'mana value' else getattr(permanent, stat)
        if not (value <= n if op == '<=' else value >= n if op == '>=' else value == n):
            return False
    return True


def subject(text):
    """Return target kind and selector data, or None for unsupported subjects."""
    low = text.lower().strip()
    if low in ('~', 'this creature', 'this permanent'):
        return 'self', {}
    if low in ('it', 'that creature', 'that permanent'):
        return 'prev', {}
    if low in ('enchanted creature', 'equipped creature') or \
            re.fullmatch(r'(?:enchanted|equipped) (?:planeswalker|permanent|battle)', low):
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
    if isinstance(more.get('selector'), dict) and more['selector'].get('other_than_source'):
        combined['other_than_source'] = True
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
    # "Other creatures you control have ward {1}": a parameter the plain keyword grants can't carry; Permanent.ward
    # reads advanced_rules["static_ward"] (selector, N) from every battlefield source.
    m = re.fullmatch(r'((?:Other |All |Each )?[A-Za-z][^.{}"]*? you control(?: with [^.{}"]+?)?) (?:have|has) ward \{(\d+)\}\.', line)
    if m:
        spec = selector(re.sub(r'^(?:All|Each) ', '', m[1]), plural=True)
        if spec is not None and 'keyword' not in spec and spec.get('counter', ('x',))[0] not in ('a', 'an', 'any'):
            rules = st.extra.setdefault('advanced_rules', {})
            rules['static_ward'] = rules.get('static_ward', ()) + ((spec, int(m[2])),)
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
