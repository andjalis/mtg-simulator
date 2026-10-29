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
    m = re.fullmatch(r"To solve — You've gained (\d+) or more life this turn\.", line, re.I)
    if m:
        extra["case_solve_life"] = int(m[1])
        return True
    if line == "~ enters tapped unless you control two or more basic lands.":
        extra["tapped_condition"] = "unless_2_basics"
        return True
    if line == "~ enters tapped unless you have two or more opponents.":
        extra["tapped_condition"] = "unless_2_opponents"
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


def activation_discount(text):
    m = re.fullmatch(r"This ability costs \{(\d+)\} less to activate for each "
                     r"((?:legendary )?(?:creature|artifact|enchantment|land|planeswalker|permanent)) you control\.", text)
    return (m[2], int(m[1])) if m else ()


def reduced_ability_cost(game, player, cost, discount):
    cost = dict(cost)
    if discount:
        what, amount = discount
        legendary = what.startswith("legendary ")
        kind = what.removeprefix("legendary ")
        def fits(source):
            if legendary and not source.card.legendary:
                return False
            if kind == "creature":
                return source.is_creature
            return kind == "permanent" or kind.capitalize() in source.card.types
        count = sum(fits(x) for x in player.battlefield)
        cost["generic"] = max(0, cost.get("generic", 0) - amount * count)
    return cost


def parse_channel(line, source_types=()):
    from .cards import AltCost, _parse_effects, parse_mana_cost
    m = re.fullmatch(r"Channel — (\{[^,]+\}), Discard (?:this card|~): (.+)", line)
    if not m:
        return None
    mana_cost = parse_mana_cost(m[1])
    if mana_cost.get("X", 0) > 1:
        return None
    body, discount = m[2], ()
    rider = re.fullmatch(r"(.+\.) (This ability costs .+\.)", body)
    if rider:
        discount = activation_discount(rider[2])
        if not discount:
            return None
        body = rider[1]
    body = re.sub(r"^It deals\b", "~ deals", body, flags=re.I)
    if "Creature" in source_types and re.search(r"target [^.]+ from your graveyard", body, re.I):
        return None  # Targets must be chosen before discarding; resolution-time regrow cannot model that.
    effects, bad = _parse_effects(body)
    if bad or not effects:
        return None
    return AltCost("channel", mana_cost, effects=effects, activation_discount=discount)


def parse_solved_ability(line):
    from .cards import _parse_ability
    if not line.startswith("Solved — "):
        return None
    notes = []
    body = line[len("Solved — "):].replace("Sacrifice this Case:", "Sacrifice ~:")
    act = _parse_ability(body, notes)
    if act is None or notes or act.condition or not any(e.kind == "grant_gy_cast" for e in act.effects):
        return None
    act.condition = "case_solved"
    act.text = line
    return act


def queue_case_solutions(game, player):
    from .cards import Effect
    for source in list(player.battlefield):
        if source.card.case_solve_life and not source.solved and player.life_gained_turn >= source.card.case_solve_life:
            game.queue_trigger(player, [Effect("solve_case", source.card.case_solve_life, target="self")], source, f"{source.card.name}: solve")


def grant_gy_cast(game, player):
    for card in list(player.graveyard):
        if card.is_creature:
            player.granted_gy_cast.append((player.graveyard.reference(card), game.turn))


def graveyard_cast_options(game, player):
    cards = []
    for ref, turn in player.granted_gy_cast:
        card = ref.find(player.graveyard) if turn == game.turn else None
        if card is not None and not any(card is old for old in cards):
            cards.append(card)
    return cards


def can_counter_ability(effect, item):
    if item.is_spell or item.kind not in ("ability", "trigger", "chapter", "loyalty", "channel"):
        return False
    activated = item.kind in ("ability", "loyalty", "channel")
    if effect.filter == "activated" and not activated or effect.filter == "triggered" and activated:
        return False
    # Activated mana abilities have no target, can produce mana, and are not loyalty abilities.
    if item.kind in ("ability", "channel") and any(e.kind in ("add_mana", "firebend") for e in item.effects) and \
            all(e.target in ("none", "self") for e in item.effects):
        return False
    return True


def _effect(kind, **kw):
    from .cards import Effect
    return Effect(kind, **kw)


EFFECT_PATTERNS += [
    (r"counter (up to one )?target (activated or triggered|activated|triggered) ability",
     lambda m: _effect("counter_ability", target="ability", filter="" if " or " in m[2].lower() else m[2].lower(),
                       data={"optional": bool(m[1])})),
    (r"return (?:a|one) land you control to its owner's hand", lambda m: _effect("bounce_land_own")),
    (r'creature cards in your graveyard gain "you may cast (?:this card|~) from your graveyard" until end of turn',
     lambda m: _effect("grant_gy_cast")),
]


def can_use_graveyard_permission(game, player):
    return player is game.active and game.step in ("main1", "main2") and not game.stack and \
        any(c.is_creature and game.spell_payable(player, c) for c in player.graveyard)


def activate_graveyard_permission(game, player):
    """Grant permission before the policy loops over spells from other zones."""
    if not can_use_graveyard_permission(game, player):
        return
    for source in list(player.battlefield):
        for index, act in enumerate(source.card.activated):
            if act.condition == "case_solved" and any(e.kind == "grant_gy_cast" for e in act.effects) and \
                    game.can_activate(player, source, index):
                game.activate_ability(player, source, index)
                return  # A second Case should not be spent on the same graveyard cards.
