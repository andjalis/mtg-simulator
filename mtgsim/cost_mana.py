"""First-spell discounts, simple restricted mana, and counter-exhaustion rewards."""
from __future__ import annotations

import re

_TYPES = {"creature", "artifact", "enchantment", "instant", "sorcery", "planeswalker", "battle"}


def spell_filter(text, flying=False):
    """A bounded spell description; unknown qualifiers are never discarded."""
    kinds, subtype, excluded = (), "", ""
    if text in _TYPES:
        kinds = (text.capitalize(),)
    elif text in ("instant or sorcery", "instant and sorcery"):
        kinds = ("Instant", "Sorcery")
    elif text == "noncreature":
        kinds = ("noncreature",)
    elif not text:
        pass
    elif re.fullmatch(r"non-[A-Z][A-Za-z]+ creature", text):
        kinds, excluded = ("Creature",), text[4:-len(" creature")]
    elif re.fullmatch(r"[A-Z][A-Za-z]+", text):
        subtype = text
    else:
        return None
    return kinds, subtype, excluded, "flying" if flying else ""


def restriction(text):
    """Only unconditional spending on spell types/subtypes, not on abilities or extra clauses."""
    m = re.fullmatch(r"to cast (?:an? )?(.+?) spells?", text, re.I)
    if not m:
        return None
    what = m[1]
    if what.lower() in ("creature", "artifact"):
        return what.lower()
    if what.lower() in _TYPES:
        return "types:" + what.capitalize()
    if what.lower() in ("instant and sorcery", "instant or sorcery"):
        return "instant_sorcery"
    types = re.split(r" (?:or|and) (?:an? )?", what.lower())
    if len(types) > 1 and all(t in _TYPES for t in types):
        return "types:" + "|".join(t.capitalize() for t in types)
    parts = re.split(r" or (?:an? )?", what)
    if all(re.fullmatch(r"[A-Z][a-zA-Z]+", p) for p in parts):
        return "subtype:" + "|".join(parts)
    return None


def parse_line(line, extra):
    m = re.fullmatch(r"The first (?:(.+?) )?spell( with flying)? you cast (each turn|during each of your turns) "
                     r"costs \{(\d+)\} less to cast\.", line)
    if m:
        spec = spell_filter(m[1] or "", bool(m[2]))
        if spec is None:
            return False
        extra["first_spell_discounts"] = extra.get("first_spell_discounts", ()) + (
            (spec, int(m[4]), m[3] == "during each of your turns"),)
        return True
    m = re.fullmatch(r"\{T\}: Add ((?:\{[WUBRGC]\})+)\. Spend this mana only (.+)\.", line)
    if m:
        rule = restriction(m[2])
        colors = re.findall(r"\{([WUBRGC])\}", m[1])
        if rule is None or len(set(colors)) != 1 or extra.get("restricted_produces"):
            return False
        extra.update(mana_restriction=rule, restricted_produces=frozenset(colors))
        if len(colors) > 1:
            extra["restricted_mana_amount"] = len(colors)
        return True
    m = re.fullmatch(r"~ crews Vehicles as though its power were (\d+) greater\.", line)
    if m:
        extra["crew_bonus"] = int(m[1])
        return True
    return False


def signature(card):
    return card.types, card.subtypes, card.keywords, card.changeling


def matches(record, spec):
    types, subtypes, keywords, changeling = record
    kinds, subtype, excluded, keyword = spec
    if kinds == ("noncreature",):
        if "Creature" in types or "Land" in types:
            return False
    elif kinds and not (set(kinds) & types):
        return False
    if subtype and subtype not in subtypes and not (changeling and "Creature" in types):
        return False
    if excluded and (excluded in subtypes or changeling and "Creature" in types):
        return False
    return not keyword or keyword in keywords


def cast_history(game):
    history = getattr(game, "_cost_mana_casts", None)
    if history is None or history["turn"] != game.turn:
        history = {"turn": game.turn}
        game._cost_mana_casts = history
    return history


def on_cast(game, player, card):
    """Record an actual cast, regardless of whether it will resolve or a reducer is present."""
    cast_history(game).setdefault(player.name, []).append(signature(card))


def first_discount(game, player, card):
    earlier = cast_history(game).get(player.name, ())
    record = signature(card)
    return sum(amount for perm in player.battlefield for spec, amount, own_turn in perm.card.first_spell_discounts
               if (not own_turn or player is game.active) and matches(record, spec)
               and not any(matches(old, spec) for old in earlier))


def _restricted_add(m):
    from .cards import Effect, NO_MATCH
    rule = restriction(m[2])
    if rule is None:
        return NO_MATCH
    return Effect("add_mana", data={"colors": re.findall(r"[WUBRGC]", m[1].upper()), "restriction": rule})


def _empty_reward(m):
    from .cards import Effect
    condition = f"!counters:{m[1].lower()}>=1"
    return [Effect("token", 1, cond=condition, data={"kind": "treasure"}),
            Effect("token", 1, cond=condition, data={"name": "Pilot", "power": int(m[2]), "toughness": int(m[3]),
                                                    "crew_bonus": int(m[4])})]


SUBS = [
    (re.compile(r"add ((?:\{[WUBRGC]\})+)\. spend this mana only (to cast [^.]+)\.", re.I),
     lambda m: f"RESTRICTEDMANA {m[1]} {m[2]}."),
]
EFFECT_PATTERNS = [
    (r"RESTRICTEDMANA ((?:\{[WUBRGC]\})+) (.+)", _restricted_add),
    (r'then if there are no (\w+) counters on ~, create a Treasure token and a (\d+)/(\d+) colorless Pilot '
     r'creature token with "(?:~|this token) crews Vehicles as though its power were (\d+) greater\."', _empty_reward),
]
