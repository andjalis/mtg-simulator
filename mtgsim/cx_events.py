"""Trigger-event library: one grammar for "When(ever) <subject> <event>, <effects>" heads.

The base trigger table (cards/clauses.py) has one regex per wording. Most remaining trigger heads are
combinations of a few parts, so this module parses them as a subject plus one or more events:

    subject  ~ | ~ or another <desc> | (a|an|another|one or more) <desc> [you control | an opponent controls]
             [with power N or greater | with flying | with a counter on it ...] | equipped/enchanted creature |
             you | a player | an opponent
    event    attacks [you] | blocks | becomes blocked | dies | enters | leaves the battlefield |
             becomes (un)tapped | deals [combat] damage [to a player | to a creature] | is dealt damage |
             becomes the target of a spell or ability [an opponent controls] | is turned face up |
             is put into a graveyard from the battlefield | casts <spell desc> | draws a card |
             gains life | loses life | discards a card | cycles a card | sacrifices <desc> | plays a land

A parsed head becomes ``Trigger("ev:<raw event>", effects, filter=<head text>)``. The engine's ``fire`` calls
``observe`` after its own dispatch; ``observe`` compiles the head (cached) into a matcher and queues every
battlefield trigger whose subject and event match. The "ev:" prefix keeps these triggers out of the
per-event dispatch in engine/stack.py, so nothing triggers twice. Words the grammar does not know make
the head fail to parse (the line stays ignored and visible in coverage) rather than match loosely.
"""
from __future__ import annotations

import functools
import re

_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}
_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_TYPES = {"creature", "artifact", "enchantment", "land", "planeswalker", "battle", "instant", "sorcery"}
_KEYWORDS = ("flying", "reach", "haste", "trample", "lifelink", "deathtouch", "vigilance", "menace", "first strike",
             "double strike", "defender", "indestructible", "hexproof", "shadow", "toxic", "flash", "infect")
_ADJ = {"token", "nontoken", "attacking", "blocking", "tapped", "untapped", "modified", "equipped", "enchanted",
        "legendary", "nonlegendary", "historic", "multicolored", "colorless", "monocolored", "basic", "nonbasic",
        "face-down", "outlaw", "permanent", "nonland", "noncreature", "nonartifact", "nonenchantment"} | \
       set(_COLORS) | {"non" + c for c in _COLORS}
_IRREGULAR = {"Elves": "Elf", "Dwarves": "Dwarf", "Wolves": "Wolf", "Werewolves": "Werewolf", "Fungi": "Fungus",
              "Mice": "Mouse", "Allies": "Ally", "Faeries": "Faerie", "Sphinxes": "Sphinx", "Foxes": "Fox",
              "Halflings": "Halfling", "Ninjas": "Ninja", "Thieves": "Thief", "Lizards": "Lizard",
              "Leeches": "Leech", "Octopuses": "Octopus", "Krakens": "Kraken", "Samurai": "Samurai",
              "Merfolk": "Merfolk", "Kithkin": "Kithkin", "Sliver": "Sliver", "Myr": "Myr", "Eldrazi": "Eldrazi",
              "Moonfolk": "Moonfolk", "Vedalken": "Vedalken", "Kor": "Kor", "Viashino": "Viashino"}


def _singular(word: str) -> str:
    if word in _IRREGULAR:
        return _IRREGULAR[word]
    low = word.lower()
    if low in ("creatures", "artifacts", "enchantments", "lands", "planeswalkers", "permanents", "tokens", "battles"):
        return low[:-1]
    if word[0].isupper() and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


# ---------------------------------------------------------------- object descriptions

def _is_noun(w: str) -> bool:
    return w.lower() in _TYPES or w.lower() in ("permanent", "spell", "token") or w[0].isupper()


def _known(w: str, adjectives) -> bool:
    lw = w.lower()
    return (lw in _TYPES or lw in adjectives or (lw.startswith("non") and lw[3:] in _TYPES) or
            re.fullmatch(r"[A-Z][a-z'-]+", w) is not None or re.fullmatch(r"non-[A-Z][a-z'-]+", w) is not None)


def _alternatives(desc: str, adjectives, plural: bool = False):
    """'Goblin or Orc', 'white or blue instant or sorcery', 'Insect, Leech, Slug, or Worm', 'artifact and/or
    creature' -> list of word tuples (words ANDed, tuples ORed), or None if a word is unknown."""
    groups = [a.split() for a in re.split(r",? and/or |,? or |, ", desc.strip()) if a.strip()]
    groups = [[_singular(w) if plural or w[0].isupper() else w for w in ws] for ws in groups]
    if not groups or not all(_known(w, adjectives) for ws in groups for w in ws):
        return None
    flat = [w for ws in groups for w in ws]
    first = next((i for i, w in enumerate(flat) if _is_noun(w)), None)
    if first:
        adjs, nouns = flat[:first], flat[first:]
        if adjs and all(_is_noun(w) for w in nouns) and not any(_is_noun(w) for w in adjs):
            # "white or blue instant or sorcery": every adjective with every noun
            pos = 0
            noun_groups = []
            for ws in groups:
                if pos >= first:
                    noun_groups.append(tuple(ws))
                elif pos + len(ws) > first:
                    noun_groups.append(tuple(ws[first - pos:]))
                pos += len(ws)
            return [(a,) + ng for a in adjs for ng in noun_groups]
    # "white or black creature": an alternative without a noun borrows the last alternative's nouns
    last = [w for w in groups[-1] if _is_noun(w)]
    for ws in groups[:-1]:
        if not any(_is_noun(w) for w in ws) and last:
            ws.extend(last)
    return [tuple(ws) for ws in groups]


def _desc_alts(desc: str, plural: bool = False):
    return _alternatives(desc, _ADJ, plural)


def _perm_word(game, perm, w: str) -> bool:
    from .engine.state import OUTLAWS
    card = perm.card
    lw = w.lower()
    if lw == "creature":
        return perm.is_creature
    if lw in _TYPES:
        return lw.capitalize() in card.types
    if lw == "permanent":
        return True
    if lw.startswith("non") and lw[3:] in _TYPES:
        return not (perm.is_creature if lw == "noncreature" else lw[3:].capitalize() in card.types)
    if lw == "token":
        return card.is_token
    if lw == "nontoken":
        return not card.is_token
    if lw in _COLORS:
        return _COLORS[lw] in card.colors
    if lw.startswith("non") and lw[3:] in _COLORS:
        return _COLORS[lw[3:]] not in card.colors
    if lw == "multicolored":
        return len(card.colors) >= 2
    if lw == "monocolored":
        return len(card.colors) == 1
    if lw == "colorless":
        return not card.colors
    if lw == "legendary":
        return card.legendary
    if lw == "nonlegendary":
        return not card.legendary
    if lw == "historic":
        return card.is_artifact or card.legendary or card.is_saga
    if lw == "basic":
        return card.basic
    if lw == "nonbasic":
        return not card.basic
    if lw == "attacking":
        return perm in game.attackers
    if lw == "blocking":
        return any(perm is b for bl in game.blocks.values() for b in bl)
    if lw == "tapped":
        return perm.tapped
    if lw == "untapped":
        return not perm.tapped
    if lw == "equipped":
        return bool(perm.equipment)
    if lw == "enchanted":
        return bool(perm.auras)
    if lw == "modified":
        return bool(perm.counters) or bool(perm.equipment) or any(a.controller is perm.controller for a in perm.auras)
    if lw == "face-down":
        return perm.hidden is not None
    if lw == "outlaw":
        return any(o in card.subtypes for o in OUTLAWS) or card.changeling
    if w.startswith("non-"):
        return w[4:] not in card.subtypes
    return w in card.subtypes or card.changeling


def _perm_fits(game, perm, alts) -> bool:
    return any(all(_perm_word(game, perm, w) for w in ws) for ws in alts)


_WITH = [
    (r" with power (\d+) or greater", lambda m: ("power>=", int(m[1]))),
    (r" with power (\d+) or less", lambda m: ("power<=", int(m[1]))),
    (r" with toughness (\d+) or greater", lambda m: ("tough>=", int(m[1]))),
    (r" with mana value (\d+) or greater", lambda m: ("mv>=", int(m[1]))),
    (r" with mana value (\d+) or less", lambda m: ("mv<=", int(m[1]))),
    (r" with (?:a|one or more) \+1/\+1 counters? on (?:it|them)| with \+1/\+1 counters on them", lambda m: ("p1",)),
    (r" with (?:a|one or more) counters? on (?:it|them)| with counters on them", lambda m: ("counter",)),
    (r" with power greater than ~'s", lambda m: ("power>self",)),
    (r" with power equal to its toughness", lambda m: ("power=tough",)),
    (r" with (" + "|".join(_KEYWORDS) + ")", lambda m: ("kw", m[1])),
    (r" without (" + "|".join(_KEYWORDS) + ")", lambda m: ("nokw", m[1])),
    (r" that's enchanted or equipped", lambda m: ("modded",)),
]


def _with_ok(game, perm, w, source) -> bool:
    k = w[0]
    if k == "power>=":
        return perm.power >= w[1]
    if k == "power<=":
        return perm.power <= w[1]
    if k == "tough>=":
        return perm.toughness >= w[1]
    if k == "mv>=":
        return perm.card.cmc >= w[1]
    if k == "mv<=":
        return perm.card.cmc <= w[1]
    if k == "p1":
        return perm.counters.get("+1/+1", 0) > 0
    if k == "counter":
        return any(v > 0 for v in perm.counters.values())
    if k == "power>self":
        return source is not None and perm.power > source.power
    if k == "power=tough":
        return perm.power == perm.toughness
    if k == "kw":
        return perm.has(w[1])
    if k == "nokw":
        return not perm.has(w[1])
    if k == "modded":
        return bool(perm.auras or perm.equipment)
    return False


def _object_subject(text: str):
    """Subject spec dict for a permanent subject, or None."""
    spec = {"self": False, "host": "", "alts": None, "other": False, "ctrl": "any", "with": [], "batch": False}
    m = re.fullmatch(r"~ or (equipped|enchanted) creature", text)
    if m:
        return dict(spec, self=True, host=m[1])
    m = re.fullmatch(r"(equipped|enchanted) (creature|land|artifact|permanent)", text)
    if m:
        return dict(spec, host=m[1])
    if text == "~":
        return dict(spec, self=True)
    m = re.fullmatch(r"~ or (.+)", text)
    if m:
        rest = _object_subject(m[1])
        if rest is None or rest["self"] or rest["host"]:
            return None
        return dict(rest, self=True)
    m = re.fullmatch(r"(an?|another|one or more(?: other)?) (.+)", text)
    if not m:
        return None
    art, desc = m[1], m[2]
    spec["other"] = art == "another" or art.endswith("other")
    spec["batch"] = art.startswith("one or more")
    for _ in range(3):
        hit = None
        for pat, mk in _WITH:
            mm = re.search(pat + r"$", desc)
            if mm:
                hit = (mm, mk)
                break
        if hit:
            spec["with"].append(hit[1](hit[0]))
            desc = desc[:hit[0].start()]
            continue
        mm = re.search(r" (you control|an opponent controls|your opponents control|you don't control|"
                       r"you own|an opponent owns)$", desc)
        if mm and spec["ctrl"] == "any":
            spec["ctrl"] = "you" if mm[1] in ("you control", "you own") else "opp"
            desc = desc[:mm.start()]
            continue
        break
    alts = _desc_alts(desc, plural=spec["batch"])
    if alts is None:
        return None
    spec["alts"] = alts
    return spec


def _subject_ok(game, spec, perm, obj) -> bool:
    """Whether obj (the permanent the event happened to) is what perm's subject phrase describes."""
    if spec["host"]:
        host = getattr(perm, "attached_to", None) or getattr(perm, "aura_host", None)
        if obj is host and host is not None:
            return True
        return spec["self"] and obj is perm
    if obj is perm:
        return spec["self"] or (spec["alts"] is not None and not spec["other"] and _obj_match(game, spec, perm, obj))
    return spec["alts"] is not None and _obj_match(game, spec, perm, obj)


def _obj_match(game, spec, perm, obj) -> bool:
    if spec["ctrl"] == "you" and obj.controller is not perm.controller:
        return False
    if spec["ctrl"] == "opp" and obj.controller is perm.controller:
        return False
    if not _perm_fits(game, obj, spec["alts"]):
        return False
    return all(_with_ok(game, obj, w, perm) for w in spec["with"])


# ---------------------------------------------------------------- spell descriptions

def _spell_word(item, w: str) -> bool:
    card = item.card
    lw = w.lower()
    if lw == "spell":
        return True
    if lw == "creature":
        return card.is_creature
    if lw in _TYPES:
        return lw.capitalize() in card.types
    if lw.startswith("non") and lw[3:] in _TYPES:
        return lw[3:].capitalize() not in card.types
    if lw == "permanent":
        return card.is_permanent
    if lw == "nonpermanent":
        return not card.is_permanent
    if lw in _COLORS:
        return _COLORS[lw] in card.colors
    if lw.startswith("non") and lw[3:] in _COLORS:
        return _COLORS[lw[3:]] not in card.colors
    if lw == "multicolored":
        return len(card.colors) >= 2
    if lw == "monocolored":
        return len(card.colors) == 1
    if lw == "colorless":
        return not card.colors
    if lw == "legendary":
        return card.legendary
    if lw == "historic":
        return card.is_artifact or card.legendary or card.is_saga
    if lw == "kicked":
        return bool(getattr(item, "kicks", 0))
    if lw == "outlaw":
        from .engine.state import OUTLAWS
        return any(o in card.subtypes for o in OUTLAWS) or card.changeling
    if w.startswith("non-"):
        return w[4:] not in card.subtypes
    return w in card.subtypes or card.changeling


_SPELL_ADJ = _ADJ | {"kicked", "nonpermanent", "spell"}


def _spell_spec(text: str):
    """'a creature spell with mana value 4 or greater', 'your first spell each turn', 'an instant or sorcery
    spell from your graveyard' -> spec, or None."""
    spec = {"alts": None, "nth": 0, "zone": "", "mv": None, "turn": "", "targets": ""}
    m = re.fullmatch(r"(?:your|their) (first|second|third) (.*?)spells? (?:each turn|during each opponent's turn)", text)
    if m:
        if text.endswith("during each opponent's turn"):
            spec["turn"] = "opp"
        spec["nth"] = {"first": 1, "second": 2, "third": 3}[m[1]]
        text = "a " + (m[2] or "") + "spell"
    tails = [
        (r" from your graveyard| from a graveyard", "zone", "graveyard"),
        (r" from exile", "zone", "exile"),
        (r" from anywhere other than your hand", "zone", "nothand"),
        (r" during your turn", "turn", "mine"),
        (r" during an opponent's turn", "turn", "opp"),
        (r" that targets a creature you control", "targets", "my_creature"),
        (r" that targets a creature", "targets", "creature"),
        (r" that targets (?:one or more permanents|a permanent)", "targets", "permanent"),
        (r" with one or more targets| that targets one or more", "targets", "any"),
        (r" with \{X\} in its mana cost", "zone_x", "x"),
    ]
    for _ in range(3):
        mm = re.search(r" with mana value (\d+) or (greater|less)$", text)
        if mm:
            spec["mv"] = (int(mm[1]), mm[2])
            text = text[:mm.start()]
            continue
        for pat, key, val in tails:
            mm = re.search("(?:" + pat + ")$", text)
            if mm:
                spec[key] = val
                text = text[:mm.start()]
                break
        else:
            break
    m = re.fullmatch(r"(?:an?|one or more) (.*?)spells?", text)
    if not m:
        return None
    desc = (m[1] or "").strip().rstrip(",")
    if not desc:
        spec["alts"] = [("spell",)]
        return spec
    spec["alts"] = _alternatives(desc, _SPELL_ADJ)
    return spec if spec["alts"] is not None else None


def _spell_ok(game, spec, item, caster, me) -> bool:
    if item is None or item.card is None:
        return False
    if not any(all(_spell_word(item, w) for w in ws) for ws in spec["alts"]):
        return False
    if spec["mv"]:
        n, way = spec["mv"]
        if (item.card.cmc < n) if way == "greater" else (item.card.cmc > n):
            return False
    if spec.get("zone_x") and "X" not in (item.card.mana_cost or {}):
        return False
    zone = getattr(item, "cast_zone", "hand" if getattr(item, "cast_from_hand", False) else "other")
    if spec["zone"] == "graveyard" and zone != "graveyard":
        return False
    if spec["zone"] == "exile" and zone != "exile":
        return False
    if spec["zone"] == "nothand" and zone == "hand":
        return False
    if spec["turn"] == "mine" and game.active is not me:
        return False
    if spec["turn"] == "opp" and game.active is me:
        return False
    if spec["targets"]:
        from .engine.state import Permanent
        tg = [t for t in item.targets if t is not None]
        if spec["targets"] == "any" and not tg:
            return False
        if spec["targets"] == "permanent" and not any(isinstance(t, Permanent) for t in tg):
            return False
        if spec["targets"] == "creature" and not any(isinstance(t, Permanent) and t.is_creature for t in tg):
            return False
        if spec["targets"] == "my_creature" and not any(isinstance(t, Permanent) and t.is_creature
                                                         and t.controller is caster for t in tg):
            return False
    if spec["nth"] and game.spells_cast_turn(caster) != spec["nth"]:
        return False
    return True


# ---------------------------------------------------------------- events

# object verbs: (regex, raw events, extra filter)
_OBJ_VERBS = [
    (r"attacks? you or a planeswalker you control", ("attacks",), "atk_me"),
    (r"attacks? you", ("attacks",), "atk_me_only"),
    (r"attacks? (?:one of your opponents|an opponent)(?: or a planeswalker an opponent controls)?", ("attacks",),
     "atk_opp"),
    (r"attacks?", ("attacks",), ""),
    (r"attacks? or blocks?", ("attacks", "blocks"), ""),
    (r"blocks? or becomes? blocked", ("blocks", "becomes_blocked"), ""),
    (r"blocks?", ("blocks",), ""),
    (r"becomes? blocked", ("becomes_blocked",), ""),
    (r"becomes? blocked by (?:an?|one or more) [\w/ -]+?(?: creatures?)?", ("becomes_blocked",), "by"),
    (r"blocks? or becomes? blocked by (?:an?|one or more) [\w/ -]+?(?: creatures?)?", ("blocks", "becomes_blocked"),
     "by"),
    (r"dies|die", ("dies",), ""),
    (r"enters?(?: the battlefield)?", ("etb",), ""),
    (r"enters?(?: the battlefield)? under your control", ("etb",), "etb_mine"),
    (r"enters?(?: the battlefield)? under an opponent's control", ("etb",), "etb_opp"),
    (r"leaves? the battlefield", ("leaves",), ""),
    (r"becomes? tapped", ("becomes_tapped",), ""),
    (r"becomes? untapped", ("becomes_untapped",), ""),
    (r"deals? combat damage to (?:a player|an opponent|a player or planeswalker|a player or battle|one or more players)",
     ("combat_damage_player",), ""),
    (r"deals? combat damage to a creature", ("combat_damage_creature",), ""),
    (r"deals? combat damage", ("combat_damage_player", "combat_damage_creature"), ""),
    (r"deals? damage to (?:a player|an opponent)", ("damages_player",), ""),
    (r"deals? damage to you", ("damages_player",), "dmg_me"),
    (r"deals? damage to a creature", ("deals_damage",), "dmg_creature"),
    (r"deals? damage", ("deals_damage",), ""),
    (r"is dealt damage", ("dealt_damage",), ""),
    (r"becomes? the target of a spell or ability an opponent controls", ("targeted_opp",), ""),
    (r"becomes? the target of a spell or ability you control", ("targeted_mine",), ""),
    (r"becomes? the target of a spell or ability", ("targeted",), ""),
    (r"becomes? the target of a spell an opponent controls", ("targeted_by_spell",), ""),
    (r"is turned face up|are turned face up", ("turned_face_up",), ""),
    (r"(?:is|are) put into (?:a|your|an opponent's) graveyard from the battlefield", ("perm_to_gy",), "gy"),
]
_VERB_RE = "|".join(f"(?:{v[0]})" for v in _OBJ_VERBS)

_PLAYER_SUBJ = {"you": "you", "a player": "any", "an opponent": "opp", "each opponent": "opp",
                "one or more opponents": "opp", "one of your opponents": "opp"}
_DISCARD = r"discards? (a card|one or more cards|an? (?:creature|land|noncreature|nonland|artifact|instant or sorcery|" \
           r"instant|sorcery|enchantment|noncreature, nonland) card|another card)"
_PLAYER_VERBS = [
    (r"casts? (.+)", "cast"),
    (r"draws? a card", "draw"),
    (r"draws? (?:their|your) (second|third) card each turn", "draw_nth"),
    (r"gains? life", "gain"),
    (r"gains? life for the first time each turn", "gain_first"),
    (r"loses? life", "lose"),
    (_DISCARD, "discard"),
    (r"cycles? (?:a card|another card)", "cycle"),
    (r"cycles? or discards? (?:a card|another card)", "cycle_discard"),
    (r"sacrifices? (an? .+|another .+|one or more .+)", "sacrifice"),
    (r"plays? a land", "land"),
    (r"attacks?", "attack"),
    (r"scry|scries", "scry"),
]
_PLAYER_RAW = {"cast": ("any_cast",), "draw": ("you_draw",), "draw_nth": ("you_draw",), "gain": ("gain_life",),
               "gain_first": ("gain_life",), "lose": ("opp_loses_life",), "discard": ("you_discard",),
               "cycle": ("you_cycle",), "cycle_discard": ("you_discard",), "sacrifice": ("sacrificed",),
               "land": ("land_played",), "attack": ("you_attack",), "scry": ("you_scry",)}


@functools.lru_cache(maxsize=None)
def compile_head(head: str):
    """The head ("Whenever a Goblin you control attacks") -> (raw events, matcher spec), or None."""
    m = re.fullmatch(r"When(?:ever)? (.+)", head)
    if not m or re.search(r"\b(?:this turn|this combat|while|commander|chosen|named|each combat)\b", m[1]) or \
            re.match(r"(?:it|that|they|this) ", m[1]):
        return None
    body = m[1]
    for subj, who in _PLAYER_SUBJ.items():
        if not body.startswith(subj + " "):
            continue
        verb = body[len(subj) + 1:]
        for pat, kind in _PLAYER_VERBS:
            vm = re.fullmatch(pat, verb)
            if not vm:
                continue
            spec = {"player": who, "kind": kind}
            if kind == "cast":
                spell = _spell_spec(vm[1])
                if spell is None:
                    return None
                spec["spell"] = spell
            elif kind == "draw_nth":
                spec["nth"] = {"second": 2, "third": 3}[vm[1]]
            elif kind == "discard":
                spec["card"] = "" if vm[1] in ("a card", "one or more cards") else vm[1]
                if vm[1] == "another card":
                    spec["card"] = ""
            elif kind == "sacrifice":
                sm = re.fullmatch(r"(an?|another|one or more) (.+)", vm[1])
                alts = _desc_alts(sm[2], plural=sm[1] == "one or more") if sm else None
                if alts is None:
                    return None
                spec["alts"] = alts
            return _PLAYER_RAW[kind], spec
        return None
    om = re.fullmatch(rf"(.+?) ((?:{_VERB_RE})(?: or (?:{_VERB_RE}))*)", body)
    if not om:
        return None
    subject = _object_subject(om[1])
    if subject is None:
        return None
    raws, flags = [], []
    by_alts = None
    rest = om[2]
    # split the verb chain on " or " where the right side starts a new verb
    parts = []
    while rest:
        best = None
        for pat, raw, flag in _OBJ_VERBS:
            for vm in (re.match(rf"(?:{pat})$", rest), re.match(rf"(?:{pat})(?= or )", rest)):
                if vm and (best is None or vm.end() > best[0]):
                    best = (vm.end(), raw, flag)
        if best is None:
            return None
        if best[2] == "by":
            by = re.search(r" by (?:an?|one or more) ([\w/ -]+?)(?: creatures?)?$", rest[:best[0]])
            alts = _desc_alts(by[1], plural=True) if by else None
            if alts is None:
                return None
            by_alts = alts
        parts.append(best[1:])
        rest = rest[best[0]:]
        rest = rest[4:] if rest.startswith(" or ") else rest
    for raw, flag in parts:
        for r in raw:
            if r not in raws:
                raws.append(r)
                flags.append(flag)
    subject["flags"] = dict(zip(raws, flags))
    subject["by"] = by_alts
    return tuple(raws), subject


def _selector_owns(head: str) -> bool:
    """backlog_templates' filtered enters/dies watcher handles these heads with batch and last-known-power rules."""
    m = re.fullmatch(r"When(?:ever)? (.+?) (enters?|dies?)", head)
    if not m or m[1].startswith(("~", "equipped ", "enchanted ")):
        return False
    from . import permanent_templates as pt
    desc = re.sub(r"^another ", "other ", re.sub(r"^one or more ", "", m[1]))
    desc = re.sub(r"(noncreature|nonland|nontoken),\s+", r"\1 ", desc)
    return pt.selector(desc, plural=m[1].startswith("one or more ")) is not None


TRIGGERS = [
    (r"When you cycle this card, (.+)", ("cycle_self",)),
    (r"When you cycle ~ or it dies, (.+)", ("cycle_self", "dies")),
    (r"Whenever a \+1/\+1 counter is put on ~, (.+)", ("p1_added",)),
    (r"(When(?:ever)? .+)", ("ev",)),     # joined last: the table's own wordings win
]


def split_head(line: str):
    """For a trigger line: (events, filter, rest) when some comma split gives a head this library parses
    and the rest parses as effects."""
    from .cards.parse import _parse_effects
    parts = line.split(", ")
    for i in range(1, len(parts)):
        head = ", ".join(parts[:i])
        got = compile_head(head)
        if got is None or _selector_owns(head):
            continue
        rest = ", ".join(parts[i:])
        effs, bad = _parse_effects(rest[0].upper() + rest[1:] if not rest.startswith("~") else rest)
        if bad or not effs:
            return None
        return tuple("ev:" + r for r in got[0]), head, rest
    return None


# ---------------------------------------------------------------- engine side

_OBSERVED = {"attacks", "blocks", "becomes_blocked", "dies", "etb", "leaves", "becomes_tapped", "becomes_untapped",
             "combat_damage_player", "combat_damage_creature", "damages_player", "deals_damage", "dealt_damage",
             "targeted", "targeted_opp", "targeted_mine", "targeted_by_spell", "turned_face_up", "perm_to_gy",
             "any_cast", "you_draw", "gain_life", "opp_loses_life", "you_discard", "you_cycle", "sacrificed",
             "land_played", "you_attack", "you_scry"}


def _has_ev(perm) -> bool:
    return any(t.event.startswith("ev:") for t in perm.card.triggers) or bool(getattr(perm, "animated", None))


def observe(game, p, event, source=None, context=None, subject=None):
    """Queue the library triggers that this fired event matches."""
    if event not in _OBSERVED:
        return
    if event == "perm_to_gy" and source is not None:
        return      # fired twice (with and without a source); listen once
    if event == "any_cast" and context is not p:
        return      # fired once per player; listen to the caster's copy
    from .residual_templates import trigger_suppressed
    if trigger_suppressed(game, event, source, context, subject):
        return      # Torpor Orb and friends
    from .engine.state import Permanent
    watchers = [x for pl in game.players for x in pl.battlefield if _has_ev(x)]
    if isinstance(source, Permanent) and source not in watchers and _has_ev(source):
        watchers.append(source)     # "~ or another creature dies": the dying source still sees it
    if event == "perm_to_gy" and isinstance(subject, Permanent) and subject not in watchers and _has_ev(subject):
        watchers.append(subject)
    if not watchers:
        return
    ev = "ev:" + event
    for perm in watchers:
        for i, trig in enumerate(perm.triggers):
            if trig.event != ev:
                continue
            got = compile_head(trig.filter)
            if got is None:
                continue
            spec = got[1]
            ctx = _match(game, spec, event, perm, p, source, context, subject,
                         any(e.target in ("that_player", "that_controller") for e in trig.effects))
            if ctx is False:
                continue
            if spec.get("batch") or spec.get("kind") in ("gain_first",):
                key = ("ev_batch", i)
                stamp = (game.turn, game.step, getattr(game, "resolving_item", None) and id(game.resolving_item))
                if spec.get("kind") == "gain_first":
                    stamp = game.turn
                if perm.ability_turns.get(key) == stamp:
                    continue
                perm.ability_turns[key] = stamp
            if trig.intervening_if:
                from .cards import Effect
                from .engine.state import StackItem
                if not game.check_cond(perm.controller, Effect("condition", cond=trig.intervening_if),
                                       StackItem(perm.controller, [], [], source=perm, context=ctx), None):
                    continue
            if trig.once:
                if perm.ability_turns.get(("trigger", i)) == game.turn:
                    continue
                perm.ability_turns[("trigger", i)] = game.turn
            if trig.once_game:
                if ("tg", i) in perm.ability_turns:
                    continue
                perm.ability_turns[("tg", i)] = game.turn
            effects = trig.effects
            amount = getattr(game, "event_amount", None)
            if amount is not None and any(e.data.get("that_much") for e in effects):
                import dataclasses
                effects = [dataclasses.replace(e, amount=amount) if e.data.get("that_much") else e for e in effects]
            game.queue_trigger(perm.controller, effects, perm, perm.card.name, ctx, modes=trig.modes,
                               intervening_if=trig.intervening_if)


def _match(game, spec, event, perm, p, source, context, subject, wants_player=False):
    """The trigger's context (the creature or player "it"/"that player" means) if the event matches, else False."""
    from .engine.state import Permanent, Player
    me = perm.controller
    if "player" in spec:
        actor = game.opponent(p) if event == "opp_loses_life" else p
        if spec["player"] == "you" and actor is not me:
            return False
        if spec["player"] == "opp" and actor is me:
            return False
        kind = spec["kind"]
        if kind == "cast":
            item = next((s for s in reversed(game.stack) if s.is_spell and s.card is subject), None) \
                if subject is not None else None
            if item is None and game.stack and game.stack[-1].is_spell:
                item = game.stack[-1]
            if not _spell_ok(game, spec["spell"], item, actor, me):
                return False
            return item if actor is me else actor
        if kind == "draw_nth":
            drawn = getattr(actor, "drawn_turn", (None, 0))
            n = drawn[1] + 1 if drawn[0] == game.turn else 1
            if n != spec["nth"]:
                return False
        if kind == "discard" and spec.get("card"):
            from .engine.state import card_matches
            card = actor.discarded_cards[-1] if getattr(actor, "discarded_cards", None) else None
            if card is None or not card_matches(card, spec["card"]):
                return False
        if kind == "gain_first" and actor.life_gained_turn != (getattr(game, "event_amount", None) or 0):
            return False
        if kind == "sacrifice":
            if not isinstance(source, Permanent) or not _perm_fits(game, source, spec["alts"]):
                return False
            return source
        return actor
    flag = spec["flags"].get(event, "")
    obj = source if source is not None else subject
    if not isinstance(obj, Permanent):
        return False
    if not _subject_ok(game, spec, perm, obj):
        return False
    if flag == "etb_mine" and obj.controller is not me:
        return False
    if flag == "etb_opp" and obj.controller is me:
        return False
    if flag in ("atk_me", "atk_me_only", "atk_opp"):
        tgt = game.attack_targets.get(obj)
        defender = tgt if isinstance(tgt, Player) else getattr(tgt, "controller", None)
        if flag == "atk_me_only" and tgt is not me:
            return False
        if flag == "atk_me" and defender is not me:
            return False
        if flag == "atk_opp" and (defender is None or defender is me):
            return False
    if flag == "by" and not (isinstance(context, Permanent) and _perm_fits(game, context, spec["by"])):
        return False
    if flag == "dmg_me" and context is not me:
        return False
    if flag == "dmg_creature" and not (isinstance(context, Permanent) and context.is_creature):
        return False
    if event in ("combat_damage_player", "damages_player") and wants_player:
        return context      # "that player"
    if obj is perm and context is not None:
        return context      # "~ blocks ..., destroy that creature": the other creature, as the base dispatch does
    return obj
