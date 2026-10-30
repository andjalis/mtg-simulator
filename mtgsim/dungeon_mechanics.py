"""Venture into the dungeon, the initiative, and die rolls (AFR / CLB / Un- sets).

Dungeon rooms are self-contained game state: a player's position is the room they are
in, in the dungeon of their choice (the three AFR dungeons are hard-coded below; the
card database has no dungeon cards). The initiative is a player flag like the monarch
(``game.initiative``); taking it ventures (CR 721.2). Die rolls store the last result
per player so "equal to the result" effects and outcome tables can act on it.

Outcome tables ("1—9 | ...") are parsed as ``die:LO-HI`` trigger events that only the
``die_roll`` handler dispatches, so they work on permanents and on spells alike.
"The result" amounts are ``die_amount`` effects resolved against the last roll, and
"If you roll a 5, ..." sentences are ``die_check`` effects.

Batch 3 adds several dice at once: ``die_roll`` data ``count`` (a number, or "x" for the
X paid / the shared ", where X is the number of ..." rule) rolls that many dice, the
faces of the last roll are kept in ``game._die_faces`` per player and the "you roll"
listeners fire once per face (outcome tables stay single-die). ``die_amount`` /
``die_check`` effects read the faces back through data ``agg``: ``chosen`` (the higher
face — the AI's "choose one result"), ``other`` (the remaining face), ``total``,
``difference``, or the count of ``even`` / ``odd`` faces; ``die_check`` also knows
``doubles``, a ``hi_sub`` dynamic upper bound ("equal to or less than the number of
Robots you control") and the repeat-total check (Free-Range Chicken). Roll-driven
kinds live here too: ``regrow_cmc`` (total-mana-value returns), ``fetch_basic_n``,
``destroy_power_ge`` and ``remove_all_counters``.

Recorded simplifications: Tomb of Annihilation "lose N life unless ..." rooms just
lose the life; Oubliette discards a card; "can't attack until your next turn" taps;
"you may play them" rooms draw; modified rolls keep only the hand-count, greatest-power
and previous-target modifiers; threshold triggers only listen to their controller's
rolls; a die rolled "for each player being attacked" is one roll; "choose one result"
picks the higher face and "the other result" the lower; the party die looks at the
current party; GO TO JAIL's owner-upkeep roll is made by the effect's controller (the
odds are the same); regrow-by-budget and fetch-N-lands pick greedily; "As ~ enters"
rolls resolve as ETB triggers just after entering, so 0/0 bodies that live on the
rolled counters (Hydradoodle, Neverwinter Hydra, Jumbo Imp, Hammer Jammer, Temp of the
Damned) stay unsupported until entering can roll.
"""
from __future__ import annotations

import re

# The result of the last roll, as an effect amount sentinel.
RESULT = 10 ** 6

EFFECT_PATTERNS = [
    # --- venture into the dungeon and the initiative -------------------------------
    (r"venture into the dungeon", lambda m: _e("venture")),
    (r"you take the initiative", lambda m: _e("take_initiative")),
    (r"you take the initiative, gain (\d+) life, draw a card, and create a treasure token",
     lambda m: [_e("take_initiative"), _e("gain_life", int(m[1])), _e("draw", 1),
                _e("token", 1, data={"kind": "treasure"})]),
    # --- die rolls -----------------------------------------------------------------
    (r"(?:you may )?roll a d20", lambda m: _e("die_roll", data={"sides": 20})),
    (r"(?:you may )?roll a d6", lambda m: _e("die_roll", data={"sides": 6})),
    (r"(?:you may )?roll a six-sided die", lambda m: _e("die_roll", data={"sides": 6})),
    (r"roll a d20 for each player being attacked and ignore all but the highest roll",
     lambda m: _e("die_roll", data={"sides": 20})),
    (r"roll a d20 and add the number of cards in your hand",
     lambda m: _e("die_roll", data={"sides": 20, "add": "hand"})),
    (r"roll a d20 and subtract the number of cards in your hand",
     lambda m: _e("die_roll", data={"sides": 20, "add": "neg_hand"})),
    (r"roll a d20 and add that spell's mana value",
     lambda m: _e("die_roll", data={"sides": 20, "add": "prev_cmc"})),
    (r"roll a d20 and add the greatest power among creatures you control",
     lambda m: _e("die_roll", data={"sides": 20, "add": "greatest_power"})),
    (r"roll a d20 and add the toughness of the creature you sacrificed this way",
     lambda m: _e("die_roll", data={"sides": 20})),
    (r"roll a d20 and add the total mana value of those cards",
     lambda m: _e("die_roll", data={"sides": 20})),
    (r"roll a d20 and add the number of creature cards in your graveyard that were put there "
     r"from the battlefield this turn",
     lambda m: _e("die_roll", data={"sides": 20, "add": "gy_creatures"})),
    # --- several dice at once, and the other die sizes -------------------------------
    # "and choose one result" rides the roll sentence; the effects below read the two
    # faces back as agg "chosen" (the higher, by the AI's simplification) and "other".
    (r"(?:you may )?roll two d(\d+)(?: and choose one result)?",
     lambda m: _e("die_roll", data={"sides": int(m[1]), "count": 2})),
    (r"roll X six-sided dice", lambda m: _e("die_roll", data={"sides": 6, "count": "x"})),
    (r"(?:you may )?roll (\w+) six-sided dice",
     lambda m: _e("die_roll", data={"sides": 6, "count": _num(m[1])})),
    (r"that player rolls two six-sided dice",
     lambda m: _e("die_roll", data={"sides": 6, "count": 2})),
    (r"roll a six-sided die twice", lambda m: _e("die_roll", data={"sides": 6, "count": 2})),
    (r"roll the party die", lambda m: _e("die_roll", data={"party": True})),
    (r"(?:you may )?roll a d(\d+)", lambda m: _e("die_roll", data={"sides": int(m[1])})),
    (r"(?:you may )?roll a (\w+)-sided die", lambda m: _e("die_roll", data={"sides": _sides(m[1])})),
    # "Choose target creature ..., then roll a die": the marker effect carries the target
    # for the outcomes ("return it to its owner's hand") to see; sides 0 rolls nothing.
    (r"choose target creature an opponent controls",
     lambda m: _e("die_roll", target="creature", filter="opp", data={"sides": 0})),
    (r"choose target creature you control",
     lambda m: _e("die_roll", target="creature_mine", data={"sides": 0})),
    # --- effects that use the roll result --------------------------------------------
    (r"(?:you )?create a number of (\d+)/(\d+) ((?:\w+ )+?)creature tokens?(?: with ([\w ,]+))? "
     r"equal to the result",
     lambda m: _die_amount("token", _token_data(m[1], m[2], m[3], m[4]))),
    (r"(?:you )?create a number of treasure tokens equal to the result",
     lambda m: _die_amount("token", {"kind": "treasure"})),
    (r"that player loses life equal to the result",
     lambda m: _die_amount("lose_life", {}, target="that_player")),
    (r"draw cards equal to the result", lambda m: _die_amount("draw", {})),
    (r"draw X cards", lambda m: _die_amount("draw", {})),
    (r"scry X", lambda m: _die_amount("scry", {})),
    (r"(?:you )?gain life equal to the result", lambda m: _die_amount("gain_life", {})),
    (r"~ gets \+X/\+([X0]) until end of turn, where X is the result( minus (\d+))?",
     lambda m: _die_amount("pump", {"minus": int(m[3] or 0), "t": m[1] == "X"}, target="self")),
    (r"target creature gets \+X/\+([X0]) until end of turn, where X is the result",
     lambda m: _die_amount("pump", {"minus": 0, "t": m[1] == "X"}, target="creature")),
    (r"that creature gets \+X/\+([X0]) until end of turn, where X is the result",
     lambda m: _die_amount("pump", {"minus": 0, "t": m[1] == "X"}, target="trigger_subject")),
    (r"~ deals damage to that player equal to the result",
     lambda m: _die_amount("damage", {}, target="that_player")),
    (r"put a number of \+1/\+1 counters on ~ equal to the result",
     lambda m: _die_amount("add_counter", {"counter": "+1/+1"}, target="self")),
    (r"remove a number of \+1/\+1 counters from ~ equal to the result",
     lambda m: _die_amount("add_counter", {"counter": "+1/+1", "remove": True}, target="self")),
    (r"put a number of (\w+) counters? on (?:him|her|it|~|this permanent) equal to the result",
     lambda m: _die_amount("add_counter", {"counter": m[1].lower()}, target="self")),
    (r"put a number of loyalty counters on (?:him|her|it|~) equal to the result",
     lambda m: _die_amount("add_counter", {"counter": "loyalty"}, target="self")),
    # more "where X is the result" carriers
    (r"put a number of (\w+) counters? on (?:~|this creature|this vehicle|it) equal to the result",
     lambda m: _die_amount("add_counter", {"counter": m[1].lower()}, target="self")),
    (r"remove a number of \+1/\+1 counters from (?:~|this creature|it) equal to the result",
     lambda m: _die_amount("add_counter", {"counter": "+1/+1", "remove": True}, target="self")),
    (r"remove all \+1/\+1 counters from (?:~|this creature|it)",
     lambda m: _e("remove_all_counters", target="self", data={"counter": "+1/+1"})),
    (r"target opponent loses life equal to the result",
     lambda m: _die_amount("lose_life", {}, target="player")),
    (r"target player mills X cards, where X is the result",
     lambda m: _die_amount("mill", {}, target="player")),
    (r"~ deals damage equal to the result to target creature an opponent controls",
     lambda m: _die_amount("damage", {}, target="creature", filter="opp")),
    (r"~ deals damage equal to the result to target creature",
     lambda m: _die_amount("damage", {}, target="creature")),
    (r"when you do, put X \+1/\+1 counters on each of up to two target creatures, where X is the result",
     lambda m: [_die_amount("add_counter", {"counter": "+1/+1", "distinct": True}, target="creature"),
                _die_amount("add_counter", {"counter": "+1/+1", "distinct": True}, target="creature")]),
    (r"when you do, put any number of target creature cards with total mana value X or less from "
     r"graveyards onto the battlefield under your control, where X is the result",
     lambda m: _die_amount("reanimate_total", {})),
    (r"put any number of target creature cards with total mana value X or less from graveyards onto "
     r"the battlefield under your control, where X is the result",
     lambda m: _die_amount("reanimate_total", {})),
    (r"until end of turn, it gains haste and gets \+X/\+0, where X is the result",
     lambda m: _die_amount("pump", {"keyword": "haste"}, target="prev")),
    (r"monstrosity X, where X is the result", lambda m: _die_amount("monstrosity", {}, target="none")),
    (r"return any number of cards with total mana value X or less from your graveyard to your hand, "
     r"where X is the total of those results",
     lambda m: _die_amount("regrow_cmc", {}, agg="total")),
    # the two results of a "roll two ... and choose one result" roll: "that result" is the
    # chosen (higher) face, "the other result" the remaining one
    (r"(?:you )?create a number of (\d+)/(\d+) ((?:\w+ )+?)creature tokens?(?: with ([\w ,]+))? "
     r"equal to (that result|the other result)",
     lambda m: _die_amount("token", _token_data(m[1], m[2], m[3], m[4]), agg=_that_or_other(m[5]))),
    (r"(?:you )?create a number of treasure tokens equal to (that result|the other result)",
     lambda m: _die_amount("token", {"kind": "treasure"}, agg=_that_or_other(m[1]))),
    (r"draw cards equal to that result", lambda m: _die_amount("draw", {}, agg="chosen")),
    (r"~ deals damage equal to that result to each creature",
     lambda m: _die_amount("damage", {}, target="each_creature", agg="chosen")),
    (r"destroy each creature with power greater than or equal to that result",
     lambda m: _die_amount("destroy_power_ge", {}, agg="chosen")),
    (r"return a creature card from your graveyard to the battlefield with a number of \+1/\+1 "
     r"counters on it equal to that result",
     lambda m: _die_amount("reanimate_one", {"entry_counters": {"+1/+1": RESULT}}, agg="chosen")),
    (r"each opponent loses X life and you gain X life, where X is the other result",
     lambda m: _die_amount("drain", {"gain": True}, target="each_opponent", agg="other")),
    (r"search your library for a number of basic land cards equal to the other result, put them "
     r"onto the battlefield tapped, then shuffle",
     lambda m: _die_amount("fetch_basic_n", {"tapped": True}, agg="other")),
    # per-face scaled effects ("for each odd result ... for each even result ...")
    (r"for each odd result, create a (\d+)/(\d+) ((?:\w+ )+?)creature tokens?(?: with ([\w ,]+))?",
     lambda m: _die_amount("token", _token_data(m[1], m[2], m[3], m[4]), agg="odd")),
    (r"for each even result, put a \+1/\+1 counter on (?:~|this vehicle|it)",
     lambda m: _die_amount("add_counter", {"counter": "+1/+1"}, target="self", agg="even")),
    (r"create a tapped treasure token for each even result",
     lambda m: _die_amount("token", {"kind": "treasure", "tapped": True}, agg="even")),
    # --- conditional on the roll ------------------------------------------------------
    (r"if the result is (\d+) or less, you lose that much life",
     lambda m: _die_check(1, int(m[1]), [_e("lose_life", RESULT)])),
    (r"if the result is (\d+) or less, scry a number of cards equal to the result",
     lambda m: _die_check(1, int(m[1]), [_e("scry", RESULT)])),
    (r"if you (?:a )?roll a (\d+), (.+)", lambda m: _die_check_parse(int(m[1]), int(m[1]), m[2])),
    (r"if you roll a (\d+) or higher, (.+)", lambda m: _die_check_parse(int(m[1]), 99, m[2])),
    (r"if you rolled a? ?(\d+) or higher, (.+)", lambda m: _die_check_parse(int(m[1]), 99, m[2])),
    (r"if any of those results was (\d+) or higher, (.+)",
     lambda m: _die_check_parse(int(m[1]), 99, m[2])),
    (r"on a (\d+) or (lower|higher), (.+)",
     lambda m: _die_check_parse(1 if m[2] == "lower" else int(m[1]),
                                int(m[1]) if m[2] == "lower" else 99, m[3])),
    (r"otherwise, put a \+1/\+1 counter on ~",
     lambda m: _die_check_parse(2, 99, "put a +1/+1 counter on ~")),
    (r"if the result is (\d+) or less, ~ deals that much damage to you",
     lambda m: _die_check(1, int(m[1]), [_e("lose_life", RESULT)])),
    (r"if the result is (\d+) or higher, (.+)", lambda m: _die_check_parse(int(m[1]), 99, m[2])),
    (r"if the result is (\d+), (.+)", lambda m: _die_check_parse(int(m[1]), int(m[1]), m[2])),
    (r"if the roll was (\d+) or higher, it gains (\w+) until end of turn",
     lambda m: _die_check(int(m[1]), 99,
                          [_e("grant", target="self", data={"keyword": m[2].lower()})])),
    (r"if the result is equal to or less than the number of (\w+)s you control, (.+)",
     lambda m: _die_check_dynamic(m[1], m[2])),
    (r"if both results are the same, ~ gets \+X/\+X until end of turn, where X is that result",
     lambda m: _die_check(1, 99, [_e("pump", RESULT, amount2=RESULT, target="self")],
                          doubles=True, agg="chosen")),
    (r"if the total of those results is equal to any other total you have rolled this turn "
     r"for this ability, sacrifice (?:~|it)",
     lambda m: _die_check(1, 99, [_e("sacrifice_self", target="self")], total_repeat=True)),
    (r"if you roll doubles, sacrifice ~", lambda m: _die_check(1, 99, [_e("sacrifice_self", target="self")],
                                                              doubles=True)),
    (r"if they roll doubles, sacrifice ~", lambda m: _die_check(1, 99, [_e("sacrifice_self", target="self")],
                                                               doubles=True)),
    # Monoxa: the threshold trigger's own body
    (r"~ gains (\w+) until end of turn",
     lambda m: _e("grant", target="self", data={"keyword": m[1].lower()})),
    # "Tap that creature." (outcome tables on a chosen creature)
    (r"tap that creature", lambda m: _e("tap", target="trigger_subject")),
    # counts the existing treasure template doesn't reach ("Create five Treasure tokens.")
    (r"create (\w+) (treasure|clue|blood|map|food) tokens?",
     lambda m: _e("token", _num(m[1]), data={"kind": m[2].lower()})),
]

# Outcome-table lines ("1—9 | ...", "4 or 5 — ...") become die:LO-HI triggers that the
# die_roll handler dispatches when a roll lands in range; the "you roll" listeners
# (one per die result) are fired by the same handler.
TRIGGERS = [
    (r"1[—–-]9 \| (.+)", ("die:1-9",)),
    (r"2[—–-]9 \| (.+)", ("die:2-9",)),
    (r"10[—–-]19 \| (.+)", ("die:10-19",)),
    (r"10[—–-]20 \| (.+)", ("die:10-20",)),
    (r"1[—–-]14 \| (.+)", ("die:1-14",)),
    (r"15[—–-]20 \| (.+)", ("die:15-20",)),
    (r"15\+ \| (.+)", ("die:15-99",)),
    (r"20\+ \| (.+)", ("die:20-99",)),
    (r"9 or less \| (.+)", ("die:1-9",)),
    (r"10 or higher \| (.+)", ("die:10-99",)),
    (r"20 \| (.+)", ("die:20-20",)),
    (r"1 \| (.+)", ("die:1-1",)),
] + [
    (rf"{n} — (.+)", (f"die:{n}-{n}",)) for n in range(1, 7)
] + [
    (rf"{a} or {b} — (.+)", (f"die:{a}-{b}",)) for a, b in ((1, 2), (4, 5))
] + [
    # Pack tactics needs its own entry: the generic prefixed patterns shadow it otherwise.
    (r"Pack tactics — Whenever ~ attacks, if you attacked with creatures with total power "
     r"\d+ or greater this combat, (.+)", ("attacks",)),
    # Ability-word-prefixed trigger lines the generic templates don't strip.
    (r"(?:[A-Z][\w' ]* — )?When ~ enters, (.+)", ("etb",)),
    (r"(?:[A-Z][\w' ]* — )?Whenever ~ attacks, (.+)", ("attacks",)),
    (r"(?:[A-Z][\w' ]* — )?When ~ dies, (.+)", ("dies",)),
    (r"(?:[A-Z][\w' ]* — )?Whenever you complete a dungeon, (.+)", ("complete_dungeon",)),
    (r"(?:[A-Z][\w' ]* — )?Whenever you roll one or more dice, (.+)", ("you_roll",)),
    (r"Whenever you roll a 1 or 2, (.+)", ("you_roll1_2",)),
    (r"Whenever you roll a 3 or higher(?: on a die)?, (.+)", ("you_roll>=3",)),
    (r"Whenever you roll a 4 or higher(?: on a die)?, (.+)", ("you_roll>=4",)),
    (r"Whenever you roll a 5 or higher(?: on a die)?, (.+)", ("you_roll>=5",)),
    (r"Whenever you roll a 6 or higher(?: on a die)?, (.+)", ("you_roll>=6",)),
    (r"Whenever a 6 is rolled on a six-sided die, (.+)", ("you_roll6",)),
    (r"When you roll a natural 20, (.+)", ("you_roll20",)),
    (r"Whenever ~ becomes untapped, (.+)", ("becomes_untapped",)),
    (r"Whenever one or more creature cards are put into your graveyard from anywhere, (.+)",
     ("creature_dies",)),
    # "As ~ enters, roll a die.": a roll the entering permanent makes itself (an ETB
    # trigger; the counters arrive just after entering, which 0/0 bodies would not survive).
    (r"As ~ enters, (.+)", ("etb",)),
    # GO TO JAIL: the exiled card's owner is (nearly always) the opponent.
    (r"At the beginning of the upkeep of the exiled card's owner, (.+)", ("opp_upkeep",)),
    (r"Whenever you cast an instant or sorcery spell with mana value (\d+) or greater, (.+)",
     ("cast_cmc",)),
]

SUBS = [
    # Treasure Chest: "1 | Trapped! — You lose 3 life."
    (re.compile(r"^[A-Z][\w' ]*! — "), ""),
]


def _e(kind, amount=1, **kw):
    from .cards import Effect
    return Effect(kind, amount, **kw)


def _num(word):
    from .cards import _num as number
    return number(word)


def _token_data(power, toughness, desc, with_kw=""):
    words = desc.split()
    colors = frozenset(c for word, c in zip(("white", "blue", "black", "red", "green"), "WUBRG")
                       if word in words)
    subtypes = [w for w in words if not re.fullmatch(r"white|blue|black|red|green", w, re.I)]
    from .cards import KEYWORDS
    kws = frozenset(k.strip().lower() for k in re.split(r",\s*(?:and\s+)?|\s+and\s+", with_kw or "")
                    if k.strip() and k.strip().lower() in KEYWORDS)
    return {"name": " ".join(subtypes) or "Token", "power": int(power), "toughness": int(toughness),
            "keywords": kws, "colors": colors}


def _die_amount(kind, data, target="none", agg=None, **kw):
    amount2 = RESULT if data.get("t") else 0          # "+X/+X": both halves are the result
    return _e("die_amount", target=target,
              data={"then": [_e(kind, RESULT, amount2=amount2, target=target, data=dict(data), **kw)],
                    "agg": agg})


def _that_or_other(wording):
    return "chosen" if wording == "that result" else "other"


_SIDES = {"four": 4, "six": 6, "eight": 8, "ten": 10, "twelve": 12, "twenty": 20}


def _sides(word):
    return _SIDES.get(word.lower(), int(word) if word.isdigit() else 6)


def _die_check(lo, hi, effects, **kw):
    return _e("die_check", data={"lo": lo, "hi": hi, "then": list(effects), **kw})


def _die_check_dynamic(sub, text):
    from .cards import NO_MATCH, _parse_effects
    effs, bad = _parse_effects(text[0].upper() + text[1:])
    if bad or not effs:
        return NO_MATCH
    return _die_check(1, 99, effs, hi_sub=sub)


def _die_check_parse(lo, hi, text):
    from .cards import NO_MATCH, _parse_effects
    effs, bad = _parse_effects(text[0].upper() + text[1:])
    if bad or not effs:
        return NO_MATCH
    return _die_check(lo, hi, effs)


# --------------------------------------------------------------------------- dungeons

# Each room: name -> (value, payload, next rooms). The payload is a tuple the
# _room_effects builder turns into engine effects (or the venture handler applies).
_LOST_MINE = "Lost Mine of Phandelver"
_TOMB = "Tomb of Annihilation"
_MAD_MAGE = "Dungeon of the Mad Mage"

_ROOMS: dict[str, tuple] = {
    # Lost Mine of Phandelver
    "Cave Entrance":       (0.4, ("scry", 1), ("Goblin Lair", "Mine Tunnels")),
    "Goblin Lair":         (1.2, ("token", 1, {"name": "Goblin", "power": 1, "toughness": 1,
                                                "colors": frozenset("R")}), ("Storeroom", "Dark Pool")),
    "Mine Tunnels":        (1.1, ("treasure", 1), ("Dark Pool", "Fungi Cavern")),
    "Storeroom":           (1.0, ("counter", 1), ("Temple of Dumathoin",)),
    "Dark Pool":           (0.6, ("drain", 1), ("Temple of Dumathoin",)),
    "Fungi Cavern":        (0.7, ("debuff", 4), ("Temple of Dumathoin",)),
    "Temple of Dumathoin": (1.8, ("draw", 1), ()),
    # Tomb of Annihilation
    "Trapped Entry":       (-0.4, ("each_lose", 1), ("Veils of Fear", "Oubliette")),
    "Veils of Fear":       (-0.6, ("each_lose", 2), ("Sandfall Cell",)),
    "Sandfall Cell":       (-0.6, ("each_lose", 2), ("Cradle of the Death God",)),
    "Oubliette":           (-1.2, ("discard", 1), ("Cradle of the Death God",)),
    "Cradle of the Death God": (2.2, ("token", 1, {"name": "The Atropal", "power": 4, "toughness": 4,
                                                  "keywords": frozenset({"deathtouch"}),
                                                  "colors": frozenset("B")}), ()),
    # Dungeon of the Mad Mage
    "Yawning Portal":      (0.3, ("gain", 1), ("Dungeon Level",)),
    "Dungeon Level":       (0.4, ("scry", 1), ("Goblin Bazaar", "Twisted Caverns")),
    "Goblin Bazaar":       (1.1, ("treasure", 1), ("Lost Level",)),
    "Twisted Caverns":     (0.8, ("tap", 1), ("Lost Level",)),
    "Lost Level":          (0.8, ("scry", 2), ("Runestone Caverns", "Muiral's Graveyard")),
    "Runestone Caverns":   (1.6, ("draw", 2), ("Deep Mines",)),
    "Muiral's Graveyard":  (1.6, ("token", 2, {"name": "Skeleton", "power": 1, "toughness": 1,
                                               "colors": frozenset("B")}), ("Deep Mines",)),
    "Deep Mines":          (1.2, ("scry", 3), ("Mad Wizard's Lair",)),
    "Mad Wizard's Lair":   (4.4, ("draw", 3), ()),
}

DUNGEONS = {
    _LOST_MINE: "Cave Entrance",
    _TOMB: "Trapped Entry",
    _MAD_MAGE: "Yawning Portal",
}

def _reachable(start, target):
    if start == target:
        return True
    return any(_reachable(nxt, target) for nxt in _ROOMS[start][2])


_FINAL_ROOMS = {name: next(d for d, first in DUNGEONS.items() if _reachable(first, name))
                for name in _ROOMS if not _ROOMS[name][2]}


def _room_effects(room):
    """The room's payload as engine Effects (None for the payloads applied in _enter)."""
    kind = room[1][0]
    if kind == "scry":
        return [_e("scry", room[1][1])]
    if kind == "draw":
        return [_e("draw", room[1][1])]
    if kind == "gain":
        return [_e("gain_life", room[1][1])]
    if kind == "token":
        return [_e("token", room[1][1], data=dict(room[1][2]))]
    if kind == "treasure":
        return [_e("token", room[1][1], data={"kind": "treasure"})]
    if kind == "drain":
        return [_e("drain", room[1][1], target="each_opponent", data={"gain": True})]
    if kind == "counter":
        return [_e("add_counter", room[1][1], target="creature", data={"counter": "+1/+1"})]
    if kind == "debuff":
        return [_e("debuff_one", room[1][1], 0, target="creature")]
    if kind == "tap":
        return [_e("tap", target="creature")]
    return None           # each_lose / discard


def _best_path(dungeon):
    """(total value, rooms) of the most valuable room path through the dungeon."""
    def value(room_name, seen=()):
        room = _ROOMS[room_name]
        if room_name in seen:
            return (0, 0)
        leads = room[2]
        if not leads:
            return (room[0], 1)
        sub = max(value(nxt, seen + (room_name,)) for nxt in leads)
        return (room[0] + sub[0], 1 + sub[1])
    return value(DUNGEONS[dungeon])


def _dungeon_score(dungeon):
    """Average value per room of the best path: the AI prefers room quality over length."""
    total, rooms = _best_path(dungeon)
    return total / rooms


def _state(game, p):
    st = game.__dict__.setdefault("_dungeon_state", {})
    if p not in st:
        st[p] = {"dungeon": None, "room": None, "completed": set()}
    return st[p]


def venture(game, p):
    """Venture into the dungeon: enter the first room of a new dungeon, or advance."""
    st = _state(game, p)
    if st["room"] is None:
        dungeon = max(DUNGEONS, key=lambda d: (_dungeon_score(d), d))
        st["dungeon"] = dungeon
        game.log(f"enters {dungeon}", p)
        _enter(game, p, DUNGEONS[dungeon])
        return
    leads = _ROOMS[st["room"]][2]
    nxt = max(leads, key=lambda name: (_ROOMS[name][0], name)) if len(leads) > 1 else leads[0]
    _enter(game, p, nxt)


def _enter(game, p, room_name):
    st = _state(game, p)
    st["room"] = room_name
    game.log(f"enters {room_name} ({st['dungeon']})", p)
    payload = _ROOMS[room_name][1]
    if payload[0] == "each_lose":
        for pl in game.players:
            game.change_life(pl, -payload[1], f"dungeon: {room_name}")
    elif payload[0] == "discard" and p.hand:
        game.discard_card(p, p.ai.choose_discard(game, p))
    else:
        effects = _room_effects(_ROOMS[room_name])
        if effects:
            targets = game.auto_targets(p, effects)
            for eff, tgt in zip(effects, targets):
                game.resolve(p, eff, tgt)
    if not _ROOMS[room_name][2]:                # the final room completes the dungeon
        st["room"] = st["dungeon"] = None
        st["completed"].add(_FINAL_ROOMS[room_name])
        game.log(f"completes {_FINAL_ROOMS[room_name]}", p)
        game.event_amount = None
        game.fire(p, "complete_dungeon")
    game.state_based_actions()


def completed(game, p):
    """The names of the dungeons this player has completed."""
    return _state(game, p)["completed"]


def take_initiative(game, p):
    if getattr(game, "initiative", None) is not p:
        game.initiative = p
        game.log("takes the initiative", p)
    venture(game, p)     # CR 721.2: whenever a player takes the initiative, they venture


def initiative_upkeep(game, active):
    """The initiative's upkeep trigger: the player who has it ventures. Hook for turns.py."""
    if getattr(game, "initiative", None) is active:
        venture(game, active)


def initiative_combat(game, source, target):
    """Combat damage to the initiative's holder passes it to the attacker. Hook for combat.py."""
    if getattr(game, "initiative", None) is target and source.controller is not target:
        take_initiative(game, source.controller)


# --------------------------------------------------------------------------- die rolls

def _last_die(game, p):
    return game.__dict__.setdefault("_die_rolls", {}).get(p)


def _modifier(game, p, eff, prev):
    what = eff.data.get("add")
    if what == "hand":
        return len(p.hand)
    if what == "neg_hand":
        return -len(p.hand)
    if what == "greatest_power":
        return max((c.power for c in p.creatures), default=0)
    if what == "prev_cmc":
        card = getattr(prev, "card", None)
        return card.cmc if card is not None else 0
    if what == "gy_creatures":
        return min(6, sum(1 for c in p.graveyard if "Creature" in c.types))
    return 0


def _outcome_triggers(item):
    """The die:LO-HI outcome triggers of the resolving spell or permanent."""
    if item is None:
        return []
    triggers = []
    src = item.source
    if src is not None and hasattr(src, "triggers"):
        triggers = list(src.triggers)
    card = getattr(item, "card", None)
    if card is not None:
        triggers += [t for t in card.triggers if t not in triggers]
    return [t for t in triggers if t.event.startswith("die:")]


def _party_sides(p):
    """The party die (CLB): a d4 for a party of one (or none), d8 for two, d12 for three, d20 for four."""
    n = sum(1 for kind in ("Cleric", "Rogue", "Warrior", "Wizard")
            if any(kind in x.card.subtypes for x in p.battlefield))
    return {0: 4, 1: 4, 2: 8, 3: 12}.get(n, 20)


def _dice_count(game, p, eff, item):
    if eff.data.get("xq"):        # ", where X is the number of ...": resolve already scaled eff.amount
        return max(0, eff.amount)
    c = eff.data.get("count", 1)
    if c == "x":
        src = item.source if item is not None else None
        return max(0, getattr(src, "entered_x", 0) if src is not None else getattr(item, "x", 0))
    return c


def roll(game, p, eff, item, target, prev):
    sides = eff.data.get("party") and _party_sides(p) or eff.data.get("sides", 20)
    if not sides:                 # the "choose target creature" marker: no roll
        return
    from .engine.state import Permanent
    n = max(0, _dice_count(game, p, eff, item))
    if not n:
        return
    mod = _modifier(game, p, eff, prev)
    faces = [max(1, game.rng.randint(1, sides) + mod) for _ in range(n)]
    game.__dict__.setdefault("_die_faces", {})[p] = faces
    total = sum(faces)
    game.__dict__.setdefault("_die_rolls", {})[p] = total
    history = game.__dict__.setdefault("_die_totals", {}).setdefault((game.turn, p), [])
    history.append(total)
    game.log(f"rolls {n} d{sides}: {faces}" + (f" (+{mod} each)" if mod else ""), p)
    for face in faces:
        _fire_roll_events(game, p, face)
    if n > 1:
        return                    # outcome tables only exist on single-die cards
    total = faces[0]
    context = next((x for x in (target, prev, getattr(item, "context", None))
                    if isinstance(x, Permanent)), None)
    for trig in _outcome_triggers(item):
        lo, _, hi = trig.event[4:].partition("-")
        if int(lo) <= total <= int(hi):
            game.queue_trigger(p, trig.effects, item.source if item is not None else None,
                               f"{getattr(item, 'name', 'die')} outcome", context=context)


def _fire_roll_events(game, p, face):
    """The "you roll" listeners, once per die face."""
    saved = getattr(game, "event_amount", None)
    game.event_amount = face
    try:
        game.fire(p, "you_roll")
        for threshold in (2, 3, 4, 5, 6):
            if face >= threshold:
                game.fire(p, f"you_roll>={threshold}")
        if face <= 2:
            game.fire(p, "you_roll1_2")
        if face == 6:
            game.fire(p, "you_roll6")
        if face == 20:
            game.fire(p, "you_roll20")
    finally:
        game.event_amount = saved


def _substitute(eff, n, parent_data):
    """Fill the RESULT sentinel with the roll (minus any 'minus' adjustment)."""
    import dataclasses
    amount = n - parent_data.get("minus", 0) if eff.amount == RESULT else eff.amount
    amount2 = n - parent_data.get("minus", 0) if eff.amount2 == RESULT else eff.amount2
    data = dict(eff.data)
    if "entry_counters" in data:      # reanimate_one: "with a number of +1/+1 counters on it"
        data["entry_counters"] = {k: n if v == RESULT else v for k, v in data["entry_counters"].items()}
    return dataclasses.replace(eff, amount=amount, amount2=amount2, data=data)


def _aggregate(game, p, eff):
    """The amount a die_amount / die_check effect reads from the player's last roll.

    The default is the last roll's total (its only face, for a single die); the two faces
    of a two-dice roll are read back as "chosen" (the higher one, the AI's pick among
    "choose one result"), "other", their "difference", or the count of "even"/"odd" faces.
    """
    faces = game.__dict__.get("_die_faces", {}).get(p) or []
    agg = eff.data.get("agg")
    if agg in (None, "total"):
        return _last_die(game, p)
    if agg == "difference":
        return abs(faces[0] - faces[1]) if len(faces) >= 2 else 0
    if agg == "chosen":
        return max(faces) if faces else None
    if agg == "other":
        return sorted(faces)[0] if len(faces) >= 2 else _last_die(game, p)
    if agg == "even":
        return sum(1 for f in faces if f % 2 == 0)
    if agg == "odd":
        return sum(1 for f in faces if f % 2 == 1)
    return _last_die(game, p)


def die_amount(game, p, eff, target, item):
    """Resolve "the result"-carrying effects against the player's last roll."""
    total = _aggregate(game, p, eff)
    if total is None:
        return
    from .engine.state import Permanent
    for then in eff.data.get("then", []):
        sub = _substitute(then, total, eff.data)
        if eff.data.get("remove") and sub.kind == "add_counter" and isinstance(target, Permanent):
            name = sub.data.get("counter", "+1/+1")
            target.counters[name] = max(0, target.counters.get(name, 0) - total)
            game.log(f"removes {total} {name} counters from {target.card.name}", p)
            continue
        game.resolve(p, sub, target, item)


def die_check(game, p, eff, target, item, prev):
    """Resolve the effect only when the last roll is inside the checked range."""
    faces = game.__dict__.get("_die_faces", {}).get(p) or []
    if eff.data.get("doubles") and not (len(faces) >= 2 and all(f == faces[0] for f in faces)):
        return
    total = _aggregate(game, p, eff)
    if total is None:
        return
    hi = eff.data.get("hi", 99)
    if eff.data.get("hi_sub"):     # "equal to or less than the number of Robots you control"
        hi = sum(1 for x in p.battlefield if eff.data["hi_sub"] in x.card.subtypes)
    if eff.data.get("total_repeat"):
        history = game.__dict__.get("_die_totals", {}).get((game.turn, p), [])
        if history[:-1].count(total) == 0:
            return
    if not (eff.data.get("lo", 1) <= total <= hi):
        return
    for then in eff.data.get("then", []):
        game.resolve(p, _substitute(then, total, eff.data), target, item, prev)


# ---------------------------------------------------------------- roll-driven effect kinds

def regrow_cmc(game, p, eff):
    """Return cards from p's graveyard to their hand, total mana value up to the roll."""
    budget = eff.amount
    for card in sorted(list(p.graveyard), key=lambda c: -c.cmc):
        if card.cmc <= budget:
            p.graveyard.remove(card)
            p.hand.append(card)
            budget -= card.cmc
            game.log(f"returns {card.name} to hand", p)


def fetch_basic_n(game, p, eff):
    """Search the library for up to the roll's worth of basic lands, tapped."""
    from .engine.policy import choose_basic
    for _ in range(max(0, eff.amount)):
        land = choose_basic(game, p)
        if land is None:
            break
        p.library.remove(land)
        perm = game.enter_battlefield(p, land)
        if perm is not None and eff.data.get("tapped"):
            perm.tapped = True
    p.library.shuffle(game.rng)
    game.library_searched(p)


def destroy_power_ge(game, p, eff):
    """Destroy each creature with power greater than or equal to the roll."""
    from .counter_mechanics import death_sources
    sources = death_sources(game)
    for perm in [x for pl in game.players for x in pl.creatures if x.power >= eff.amount]:
        game.destroy(perm, counter_sources=sources)


def remove_all_counters(game, p, eff, item):
    from .engine.state import Permanent
    src = item.source if item is not None else None
    if isinstance(src, Permanent) and src in src.controller.battlefield:
        name = eff.data.get("counter", "+1/+1")
        n = src.counters.get(name, 0)
        src.counters[name] = 0
        game.log(f"removes all {n} {name} counters from {src.card.name}", p)
