"""Oracle-text templates: effect patterns, substitutions and trigger patterns, with their small helpers.

New general templates go in a mechanic module (removal.py, copies.py, ...) that exports EFFECT_PATTERNS
or SUBS; the package __init__ joins them to the tables here."""
from __future__ import annotations

import re

from .model import COLORS, COLOR_WORDS, Effect, KEYWORDS, NO_MATCH, _distinct_bounce, _distinct_pump, _num


def _parse_mana_ability(rest: str) -> tuple[set, int]:
    """Colours a {T} ability can make, and how much mana it makes ({C}{C} is 2)."""
    if "any color" in rest:
        return set(COLORS), 1
    syms = re.findall(r"\{([WUBRGC])\}", rest)
    amount = 1 if " or " in rest else max(1, len(syms))
    return set(syms), amount


def _token(m_count, power, toughness, desc, with_kw="", attacking=False, ability=""):
    from .parse import _parse_trigger  # deferred: parse imports this module
    words = desc.split()
    subtypes = [w for w in words if not re.fullmatch(COLOR_WORDS, w, re.I) and w.lower() != "and"]
    requested = [k.strip().lower() for k in re.split(r",| and ", with_kw or "") if k.strip()]
    kws = frozenset(k for k in requested if k in KEYWORDS)
    triggers, pt_per = [], ""
    if ability:
        per = re.fullmatch(r"(?:This (?:token|creature)|~) gets \+1/\+1 for each (\w+?)s? you control\.?", ability)
        parsed = None if per else _parse_trigger(ability.rstrip("."). replace("this creature", "~") + ".")
        triggers = parsed[0] if parsed else []
        pt_per = per[1] if per else ""
    artifact = "artifact" in subtypes
    subtypes = [w for w in subtypes if w != "artifact"]
    return Effect("token", _num(m_count), data={"name": " ".join(subtypes) or "Token", "power": int(power),
                                                "toughness": int(toughness), "keywords": kws,
                                                "attacking": attacking, "triggers": triggers,
                                                "artifact": artifact, "pt_per": pt_per,
                                                **({"unparsed_token_keywords": tuple(k for k in requested if k not in KEYWORDS)}
                                                   if any(k not in KEYWORDS for k in requested) else {}),
                                                "colors": frozenset(c for word, c in zip(
                                                    ("white", "blue", "black", "red", "green"), "WUBRG")
                                                    if word in desc.lower().split())})


def _distinct_cant_block():
    return Effect("cant_block_turn", target="creature", data={"distinct": True})


_TENS = {"a": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def _tapped(eff):
    eff.data["tapped"] = True
    return eff


_SRC = r"(?:~|it|he|she)"
_EFFECT_PATTERNS = [
    (r"learn", lambda m: Effect("learn")),
    (r"regenerate (~|it|target creature(?: you control)?|target artifact)",
     lambda m: Effect("regenerate", 1, target={"~": "self", "it": "prev", "target creature": "creature",
                     "target creature you control": "creature_mine", "target artifact": "artifact"}[m[1].lower()])),
    (r"regenerate (each|all) creatures?( you control)?",
     lambda m: Effect("regenerate", 1, target="creatures_mine" if m[2] else "each_creature")),
    (r"draw (a card|one card|(?:\d+|two|three|four|five|six|seven|eight|nine|ten) cards) at the beginning of "
     r"(the next turn's upkeep|your next upkeep)",
     lambda m: Effect("draw_delayed", _num(m[1].split()[0]),
                      data={"upkeep": "you" if m[2].lower() == "your next upkeep" else "any"})),
    (r"proliferate(?: (twice|again))?", lambda m: Effect("proliferate", 2 if (m[1] or "").lower() == "twice" else 1)),
    (_SRC + r" deals (\d+) damage to any target", lambda m: Effect("damage", int(m[1]), target="any")),
    (_SRC + r" deals X damage to any target", lambda m: Effect("damage", 0, target="any", data={"x": True})),
    (_SRC + r" deals (\d+) damage to target attacking or blocking creature",
     lambda m: Effect("damage", int(m[1]), target="creature", filter="attacking_blocking")),
    (_SRC + r" deals (\d+) damage to target tapped creature(?: an opponent controls)?",
     lambda m: Effect("damage", int(m[1]), target="creature", filter="tapped")),
    (_SRC + r" deals (\d+) damage to target creature without flying",
     lambda m: Effect("damage", int(m[1]), target="creature", filter="nonflying")),
    (_SRC + r" deals (\d+) damage to (?:up to one )?target (?:creature or planeswalker|creature)"
     r"(?: an opponent controls| you don't control)?",
     lambda m: Effect("damage", int(m[1]), target="creature")),
    (_SRC + r" deals (\d+) damage to (?:target player or planeswalker|target player|target opponent"
     r"(?: or planeswalker)?|each opponent)",
     lambda m: Effect("damage", int(m[1]), target="player")),
    (_SRC + r" deals (\d+) damage to each opponent and each planeswalker they control",
     lambda m: Effect("damage", int(m[1]), target="each_opp_and_pw")),
    (_SRC + r" deals (\d+) damage to (?:that player|that spell's controller)",
     lambda m: Effect("damage", int(m[1]), target="that_player")),
    (_SRC + r" deals (\d+) damage to you", lambda m: Effect("lose_life", int(m[1]))),
    (r"~ also deals (\d+) damage to that permanent's controller if you control a modified creature",
     lambda m: Effect("damage", int(m[1]), target="that_controller", cond="modified")),
    (r"~ deals (\d+) damage to each creature", lambda m: Effect("damage", int(m[1]), target="each_creature")),
    (r"destroy target creature with mana value (\d+) or less",
     lambda m: Effect("destroy", target="creature", filter=f"max_cmc:{m[1]}")),
    (r"destroy target creature if it has mana value (\d+) or less",
     lambda m: Effect("destroy", target="creature", filter=f"max_cmc:{m[1]}")),
    (r"revolt — destroy that creature if it has mana value (\d+) or less instead if a permanent you "
     r"controlled left the battlefield this turn",
     lambda m: Effect("revolt", int(m[1]), target="prev")),
    (r"exile target creature with mana value less than or equal to the number of plains you control",
     lambda m: Effect("destroy", target="creature", filter="plains")),
    (r"(?:destroy|exile) target tapped creature(?: an opponent controls| you don't control)?",
     lambda m: Effect("destroy", target="creature", filter="tapped")),
    (r"(?:destroy|exile) target attacking or blocking creature",
     lambda m: Effect("destroy", target="creature", filter="attacking_blocking")),
    (r"(?:destroy|exile) target untapped creature(?: an opponent controls| you don't control)?",
     lambda m: Effect("destroy", target="creature", filter="untapped")),
    (r"destroy target nonartifact creature", lambda m: Effect("destroy", target="creature", filter="nonartifact")),
    # "non-Angel, non-Demon, non-Dragon" style restrictions are parsed but not enforced.
    (r"(?:destroy|exile) target (?:[\w-]+,? )*?creature(?:, enchantment,)? or planeswalker",
     lambda m: Effect("destroy", target="creature_pw")),
    (r"(?:destroy|exile) target (?:[\w-]+,? )*?creature(?: an opponent controls| you don't control)?",
     lambda m: Effect("destroy", target="creature")),
    (r"destroy target artifact", lambda m: Effect("destroy", target="artifact")),
    (r"(?:destroy|exile) target artifact or enchantment(?: an opponent controls)?",
     lambda m: Effect("destroy", target="artifact_enchantment", filter="opp")),
    (r"if you control a Squirrel or returned a Squirrel card to your hand this way, create a food token",
     lambda m: Effect("token", 1, data={"kind": "food"}, cond="squirrel")),
    (r"(?:you may )?return (?:a|up to one) (?:non-\w+ )?creature card(?: or a planeswalker card)? from your "
     r"graveyard to your hand", lambda m: Effect("regrow")),
    (r"DISCARDTUTOR", lambda m: Effect("discard_tutor", data={"desc": "a creature card"})),
    (r"when you discard one or more nonland cards this way, tap up to that many target creatures and put a stun "
     r"counter on each of them", lambda m: Effect("stun_discarded")),
    (_SRC + r" deals damage equal to that creature's power to any target",
     lambda m: Effect("damage", 0, target="any", data={"subject_power": True})),
    (r"shuffle ~ and target creature with a stun counter on it into their owners' libraries",
     lambda m: Effect("shuffle_away", target="creature", filter="stunned")),
    (r"RETURNENCHANT", lambda m: Effect("return_as_enchantment")),
    (r"LASTGIFT", lambda m: Effect("last_gift")),
    (r"target opponent exiles a creature they control and their graveyard",
     lambda m: [Effect("edict", 1, data={"exile": True}), Effect("exile_gy")]),
    (r"untap another target permanent", lambda m: Effect("untap_other")),
    (r"draw a card for each (artifact|creature|land) you control",
     lambda m: Effect("draw", 0, data={"x_count": m[1]})),
    (r"put ~ into its owner's library third from the top", lambda m: Effect("tuck_self", 3)),
    (r"(?:you )?draw (a|one|two|three|four|\d+) cards?", lambda m: Effect("draw", _num(m[1]))),
    (r"(?:then )?if you have fewer than (three) cards in hand, draw cards equal to the difference",
     lambda m: Effect("draw_up_to", _num(m[1]))),
    (r"you gain (\d+) life", lambda m: Effect("gain_life", int(m[1]))),
    (r"its controller gains (\d+) life", lambda m: Effect("gain_life", int(m[1]), target="that_controller")),
    (r"(?:each|target) opponent loses (\d+) life", lambda m: Effect("drain", int(m[1]), target="each_opponent")),
    (r"each opponent loses (\d+) life and you gain (\d+) life",
     lambda m: [Effect("drain", int(m[1]), target="each_opponent"), Effect("gain_life", int(m[2]))]),
    (r"DEVOTIONDRAIN ([WUBRG])", lambda m: Effect("drain_devotion", data={"color": m[1]})),
    (r"target creature(?: you control)? gets \+(\d+)/\+(\d+) until end of turn",
     lambda m: Effect("pump", int(m[1]), int(m[2]), target="creature")),
    (r"~ gets ([+-]\d+)/([+-]\d+) until end of turn",
     lambda m: Effect("pump", int(m[1]), int(m[2]), target="self")),
    (r"~ gets \+(\d+)/\+(\d+) and gains (flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach) until end of turn",
     lambda m: Effect("pump", int(m[1]), int(m[2]), target="self", data={"keyword": m[3].lower()})),
    (r"enchanted creature gains (flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach) until end of turn",
     lambda m: Effect("grant", target="none", data={"keyword": m[1].lower(), "host": True})),
    (r"destroy target creature or enchantment", lambda m: Effect("destroy", target="nonland_perm", filter="creature_or_ench")),
    (r"destroy target creature an opponent controls that was dealt damage this turn",
     lambda m: Effect("destroy", target="creature", filter="opp_damaged")),
    (r"exile target (artifact or creature|tapped creature) an opponent controls until ~ leaves the battlefield",
     lambda m: Effect("oring", target="nonland_perm", filter="opp_tapped_creature" if m[1].startswith("tapped")
                      else "opp_artifact_creature")),
    (r"counter target artifact or enchantment spell", lambda m: Effect("counter", target="spell", filter="artifact_ench")),
    (r"destroy target noncreature, nonland permanent", lambda m: Effect("destroy", target="nonland_perm", filter="noncreature")),
    (r"return target card from your graveyard to your hand", lambda m: Effect("regrow_any")),
    (r"return up to two target creatures to their owners' hands",
     lambda m: [_distinct_bounce(), _distinct_bounce()]),
    (r"one or two target creatures each get \+(\d+)/\+(\d+) until end of turn",
     lambda m: [_distinct_pump(m), _distinct_pump(m)]),
    (r"untap target artifact or creature", lambda m: Effect("untap_target", target="creature_mine")),
    (r"exile (?:each opponent's|target player's) graveyard", lambda m: Effect("exile_gy")),
    (r"exile target card from an opponent's graveyard", lambda m: Effect("exile_gy", 1)),
    (r"target player draws (a|two|three) cards?", lambda m: Effect("draw", _num(m[1]))),
    (r"target player draws (a|two|three) cards? and loses (\d+) life",
     lambda m: [Effect("draw", _num(m[1])), Effect("lose_life", int(m[2]))]),
    (r"~ deals (\d+) damage to each player", lambda m: Effect("damage_each_player", int(m[1]))),
    (r"put (a|one|two|three|four|five|six) \+1/\+1 counters? on it", lambda m: Effect("p1_counters", _num(m[1]), target="prev")),
    (r"put (a|one|two|three|four) -1/-1 counters? on (?:up to one )?target creature",
     lambda m: Effect("shrink", _num(m[1]), target="creature", filter="opp")),
    (r"put (a|one|two) -1/-1 counters? on each creature", lambda m: Effect("shrink_all", _num(m[1]))),
    (r"return all attacking creatures to their owner's hand", lambda m: Effect("mass_bounce", data={"only": "attacking"})),
    (r"tap target permanent", lambda m: Effect("tap", 1, target="nonland_perm")),
    (r"each player draws a card", lambda m: Effect("draw_each", 1)),
    (r"target creature(?: an opponent controls)? can't block this turn", lambda m: Effect("cant_block_turn", target="creature")),
    (r"(up to (?:one|two|three)|one or two|up to two) target creatures can't block this turn",
     lambda m: [_distinct_cant_block() for _ in range({"one": 1, "two": 2, "three": 3, "one or two": 2}.get(
         m[1].split()[-1] if m[1].startswith("up to") else m[1], 2))]),
    (r"(?:it|that creature|the other) can't block this turn", lambda m: Effect("cant_block_turn", target="prev")),
    (r"target creature blocks this turn if able", lambda m: Effect("force_block", target="creature")),
    (r"target creature attacks or blocks this turn if able",
     lambda m: Effect("force_block", target="creature", data={"attack": True})),
    (r"(?:it|~) must be blocked (?:this turn|each combat this turn) if able",
     lambda m: Effect("force_blocked", target="prev" if m[0].lower().startswith("it") else "self")),
    (r"target opponent exiles a card from their hand", lambda m: Effect("opp_exile_hand")),
    (r"return target creature card from your graveyard to the battlefield", lambda m: Effect("reanimate_one")),
    (r"return up to one target permanent card from your graveyard to your hand", lambda m: Effect("regrow_perm")),
    (r"counter target spell with mana value (\d+)",
     lambda m: Effect("counter", target="spell", filter=f"cmc:{m[1]}")),
    (r"counter target artifact or creature spell",
     lambda m: Effect("counter", target="spell", filter="artifact_creature")),
    (r"discover x, where x is that spell's mana value",
     lambda m: Effect("discover", 0, target="prev", data={"x_of": "spell"})),
    (r"if the discovered card's mana value is less than 10, create a number of tapped treasure tokens equal to "
     r"the difference", lambda m: Effect("discover_treasures")),
    (r"exile all creatures", lambda m: Effect("exile_all_creatures")),
    (r"empower jace x, where x is the number of creatures exiled this way",
     lambda m: Effect("empower", 0, data={"count": "exiled"})),
    (r"COUNTERTW (\d+) (\d+)",
     lambda m: Effect("counter", int(m[1]), target="spell", data={"tw": int(m[2])})),
    (r"counter target creature or enchantment spell",
     lambda m: Effect("counter", target="spell", filter="creature_ench")),
    (r"counter target (noncreature |creature |instant or sorcery )?spell"
     r"(?: unless its controller pays \{(\d+)\})?",
     lambda m: Effect("counter", int(m[2] or 0), target="spell",
                      filter=(m[1] or "").strip().replace("instant or sorcery", "instant_sorcery"))),
    (r"return target spell you don't control to its owner's hand", lambda m: Effect("bounce_spell", target="spell")),
    (r"you lose (\d+) life", lambda m: Effect("lose_life", int(m[1]))),
    (r"(?:that player|they) loses? (\d+) life", lambda m: Effect("lose_life", int(m[1]), target="that_player")),
    (r"creatures your opponents control get -(\d+)/-(\d+) until end of turn",
     lambda m: Effect("debuff", int(m[1]), int(m[2]), target="opp_creatures")),
    # Crippling Fear: approximated as "your creatures share the chosen type".
    (r"creatures that aren't of the chosen type get -(\d+)/-(\d+) until end of turn",
     lambda m: Effect("debuff", int(m[1]), int(m[2]), target="opp_creatures")),
    (r"target creature(?: an opponent controls| you don't control)? gets -(\d+)/-(\d+) until end of turn",
     lambda m: Effect("debuff_one", int(m[1]), int(m[2]), target="creature")),
    (r"(?:all creatures|each creature) gets? -(\d+)/-(\d+) until end of turn",
     lambda m: Effect("debuff", int(m[1]), int(m[2]), target="each_creature")),
    (r"choose a creature type", lambda m: None),
    (r"each player who controls a multicolored creature draws a card", lambda m: None),  # rarely matters
    (r"damage can't be prevented this turn", lambda m: None),
    (r"destroy all creatures", lambda m: Effect("wrath", target="each_creature")),
    (r"destroy all planeswalkers", lambda m: Effect("wrath_pw")),
    (r"return (?:up to one )?(?:other )?target (?:nonland permanent|creature|artifact, creature, enchantment, or "
     r"planeswalker)"
     r"(?: an opponent controls| you don't control)? to its owner's hand",
     lambda m: Effect("bounce", target="nonland_perm")),
    (r"scry (\d+)", lambda m: Effect("scry", int(m[1]))),
    (r"surveil (\d+)", lambda m: Effect("surveil", int(m[1]))),
    (r"put x \+1/\+1 counters on each creature you control, where x is the number of cards in your hand",
     lambda m: Effect("p1_counters", 0, target="my_creatures", data={"x": "hand"})),
    (r"for each opponent, return up to one target artifact or creature that player controls to its owner's hand",
     lambda m: Effect("bounce", target="nonland_perm", filter="opp")),
    (r"add ((?:\{[WUBRG]\})+)", lambda m: Effect("add_mana", data={"colors": re.findall(r"[WUBRG]", m[1])})),
    (r"transform ~", lambda m: Effect("transform", target="self")),
    (r"NETTAP", lambda m: Effect("tap", 1, target="nonland_perm", data={"net": True})),
    (r"OPTCOST (\S+) (\d+)", lambda m: Effect("opt_cost_draw", int(m[2]), data={"cost": m[1]})),
    (r"THREATEN", lambda m: Effect("threaten", target="creature", filter="opp")),
    (r"MERCENARY (\w+)", lambda m: Effect("token", 0 if m[1].lower() == "x" else _num(m[1]), data={
        "name": "Mercenary", "power": 1, "toughness": 1, "keywords": frozenset(), "mercenary": True,
        "x": m[1].lower() == "x"})),
    (r"IRENCRAG", lambda m: Effect("irencrag")),
    (r"harness ~", lambda m: Effect("harness")),
    (r"search your library for a card, put it into your graveyard, then shuffle", lambda m: Effect("tutor_gy")),
    (r"return up to two creature cards with total mana value 4 or less from your graveyard to the battlefield",
     lambda m: Effect("reanimate_total", 4)),
    (r"search your library for an artifact card with mana value equal to 1 plus the sacrificed artifact's mana value, "
     r"put that card onto the battlefield, then shuffle", lambda m: Effect("bay_search")),
    (r"STARCAGE", lambda m: Effect("starcage")),
    (r"COVERUP", lambda m: Effect("cover_up", cond="evidence")),
    (r"OBSESS", lambda m: Effect("add_counter", 0, target="creature_mine", data={"counter": "+1/+1", "x": "sacrificed"})),
    (r"SACDRAWTREASURE", lambda m: Effect("sac_draw_treasure")),
    (r"AZOG (\w+?)s?", lambda m: Effect("destroy", target="creature", data={"azog": m[1].capitalize()})),
    (r"DIGFLOW (\d+)", lambda m: Effect("dig", int(m[1]), 1, data={"instead_two": "instant+sorcery"})),
    (r"DIG (\d+) (\d+)", lambda m: Effect("dig", int(m[1]), int(m[2]))),
    (r"DIGPUT (\d+) (\d+)", lambda m: Effect("dig_put", int(m[1]), int(m[2]))),
    (r"DIGPUTNONCREATURE (\d+) (\d+) (\d+)",
     lambda m: Effect("dig_put", int(m[1]), int(m[2]), data={"count": int(m[3]), "noncreature": True})),
    (r"DIGFILTER (\d+) (.+)", lambda m: Effect("dig", int(m[1]), 1, data={"filter": m[2]})),
    (r"DIGLANDS (\d+)", lambda m: Effect("dig", 0, int(m[1]), data={"x_lands": True})),
    (r"DIGCOUNT (\w+) (\d+)", lambda m: Effect("dig", 0, int(m[2]), data={"x_count": m[1]})),
    (r"IMPULSE (\d+)", lambda m: Effect("draw", int(m[1]))),   # "exile the top N, you may play them"
    (r"TARGETDISCARD", lambda m: Effect("discard_choice", 1, target="player")),
    (r"TARGETDISCARDNONCREATURE", lambda m: Effect("discard_choice", 1, target="player", filter="noncreature")),
    (r"(?:you may )?exile the top (card|one card|two cards|three cards|four cards|\d+ cards) of your library",
     lambda m: Effect("exile_top", _N_WORDS.get(m[1].split()[0], 1) if m[1] != "card" else 1)
     if not m[1][0].isdigit() else Effect("exile_top", int(m[1].split()[0]))),
    (r"(?:you may play (?:that card|those cards|it|them|the exiled cards?) (this turn|until the end of your next turn|"
     r"until your next end step)|until the end of your next turn, you may play (?:that card|those cards|it|them))",
     lambda m: Effect("may_play_exiled", 0 if m[1] == "this turn" else 2)),
    (r"tap (?:up to one )?target (?:creature|nonland permanent)(?: an opponent controls| you don't control)?",
     lambda m: Effect("tap", 1, target="creature")),
    (r"tap up to (two|three) target creatures", lambda m: Effect("tap", _num(m[1]), target="creature")),
    (r"tap target creature(?: an opponent controls)? and put (a|two|three) stun counters? on it",
     lambda m: [Effect("tap", 1, target="creature"), Effect("stun", _num(m[1]), target="prev")]),
    (r"put (a|two|three) stun counters? on it", lambda m: Effect("stun", _num(m[1]), target="prev")),
    (r"put (a|two|three) stun counters? on (?:up to one )?target tapped creature(?: an opponent controls)?",
     lambda m: Effect("stun", _num(m[1]), target="creature", filter="tapped")),
    (r"target creature(?: you control)? with power (\d+) or less can't be blocked this turn",
     lambda m: Effect("unblockable", target="creature_mine", filter=f"max_power:{m[1]}")),
    (r"(?:up to one )?target creature you control can't be blocked this turn",
     lambda m: Effect("unblockable", target="creature_mine")),
    (r"earthbend (\w+)", lambda m: Effect("earthbend", _num(m[1]))),
    (r"GOBLINGUIDE", lambda m: Effect("reveal_land", target="each_opponent")),
    (r"FETCHBASIC( UNTAP4)?", lambda m: Effect("fetch_basic", data={"untap4": bool(m[1])})),
    (r"double the number of \+1/\+1 counters on ~", lambda m: Effect("double_counters", target="self")),
    (r"double the power of target creature you control until end of turn",
     lambda m: Effect("double_power", target="creature_mine")),
    (r"(?:then )?draw a card for each opponent who lost life this turn",
     lambda m: Effect("draw", 1, cond="opp_lost_life")),
    (r"target player discards a card", lambda m: Effect("discard", 1, target="player")),
    (r"each opponent discards a card", lambda m: Effect("discard", 1, target="player")),
    (r"if (?:that|the) (?:creature|permanent|creature or planeswalker) would die this turn, exile it instead",
     lambda m: Effect("exile_instead", target="prev")),
    (r"discard your hand, then draw two cards", lambda m: Effect("wheel_self")),
    (r"return all non-(\w+) creatures to their owners' hands", lambda m: Effect("mass_bounce", data={"except": m[1]})),
    (r"return one or two target creatures and/or enchantments you own to your hand",
     lambda m: Effect("bounce_own", target="nonland_perm", filter="mine")),
    (r"(?:you )?recruit", lambda m: Effect("recruit")),
    (r"return up to (one|two) target creature cards? from your graveyard to your hand",
     lambda m: Effect("regrow", _num(m[1]))),
    (r"return ~ to its owner's hand", lambda m: Effect("bounce_self")),
    (r"empower jace (\d+)", lambda m: Effect("empower", int(m[1]))),
    (r"empower jace x, where x is the number of (creatures|islands) you control",
     lambda m: Effect("empower", 0, data={"count": m[1].lower()})),
    (r"create x (mutagen) tokens", lambda m: Effect("token", 0, data={"kind": "mutagen", "x": True})),
    (r"discover (\d+)", lambda m: Effect("discover", int(m[1]))),
    (r"(?:~|it|he|she) connives", lambda m: Effect("connive", target="prev")),
    (r"(?:up to one )?target creature you control connives", lambda m: Effect("connive", target="creature_mine")),
    (r"create an? (royal|monster|wicked|cursed|sorcerer|young hero|virtuous) role token attached to "
     r"(it|that creature|(?:up to one )?(?:another |other )?target creature you control|target creature an opponent controls)",
     lambda m: Effect("role", target="prev" if m[2] in ("it", "that creature") else
                      "creature" if "opponent" in m[2] else "creature_mine",
                      filter="opp" if "opponent" in m[2] else "", data={"role": m[1].lower()})),
    (r"STUNLANDSWAP", lambda m: Effect("land_swap")),
    (r"(\w+) and (\w+)s you control gain (indestructible|hexproof|vigilance|trample|haste|lifelink|first strike|deathtouch) "
     r"until end of turn",
     lambda m: Effect("grant_types", data={"types": (m[1], m[2]), "keyword": m[3].lower()})),
    (r"amass (\w+) (\d+)", lambda m: Effect("amass", int(m[2]), data={"type": m[1].rstrip("s").capitalize()})),
    (r"(?:defending player|target opponent) loses (\d+) life and you gain (\d+) life",
     lambda m: [Effect("drain", int(m[1]), target="each_opponent"), Effect("gain_life", int(m[2]))]),
    (r"you draw a card and lose (\d+) life", lambda m: [Effect("draw", 1), Effect("lose_life", int(m[1]))]),
    (r"(?:target|each) opponent discards (a|two|three) cards?", lambda m: Effect("discard", _num(m[1]), target="player")),
    (r"(?:target|each) opponent sacrifices a creature(?: of their choice)?", lambda m: Effect("edict", 1)),
    (r"sacrifice ~", lambda m: Effect("sacrifice_self", target="self")),
    (r"another target creature you control gains (deathtouch|first strike|lifelink|trample|haste|indestructible|"
     r"hexproof|vigilance|menace|reach|flying) until end of turn",
     lambda m: Effect("grant", target="creature_mine", data={"keyword": m[1].lower()})),
    (r"put (a|one|two|three) \+1/\+1 counters? on another target creature you control",
     lambda m: Effect("p1_counters", _num(m[1]), target="creature_mine")),
    (r"~ deals 1 damage to each of one or two targets", lambda m: Effect("damage", 1, target="any")),
    (r"investigate", lambda m: Effect("token", 1, data={"kind": "clue"})),
    (r"(?:~|it|this creature) endures (\d+)", lambda m: Effect("endure", int(m[1]))),
    (r"manifest dread", lambda m: Effect("manifest_dread")),
    (r"untap ~", lambda m: Effect("untap_self")),
    (r"untap it", lambda m: Effect("untap_prev", target="prev")),
    (r"it explores", lambda m: Effect("explore", target="prev")),
    (r"exile up to (one|two) target cards? from (?:a|a single) graveyard",
     lambda m: Effect("exile_gy_cards", _num(m[1]))),
    (r"put target card from (a|your) graveyard on the bottom of (?:its owner's|your) library",
     lambda m: Effect("gy_bottom", data={"mine": m[1] == "your"})),
    (r"target creature(?: you control)? gets \+(\d+)/\+(\d+) and gains (flying|first strike|double strike|deathtouch|"
     r"lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach) until end of turn",
     lambda m: Effect("pump", int(m[1]), int(m[2]), target="creature", data={"keyword": m[3].lower()})),
    (r"(?:then )?discard (a|one|two|three) cards? unless you discard an? basic land card",
     lambda m: Effect("discard", _num(m[1]), data={"unless": "basic_land"})),
    (r"(?:then )?discard (a|one|two|three) cards?(?: unless .*)?", lambda m: Effect("discard", _num(m[1]))),
    (r"RUMMAGE (\d+)", lambda m: Effect("rummage", int(m[1]))),
    (r"create (a|one|two|three|four|five) (\d+)/(\d+) ((?:\w+ )+?)creature tokens?(?: named [\w' ,-]+?)?(?: that's "
     r"(tapped and attacking))?(?: with ([\w ,]+))?",
     lambda m: _token(m[1], m[2], m[3], m[4], m[6], bool(m[5]))),
    (r'create (a) (\d+)/(\d+) ((?:\w+ )+?)creature token with "(.+)"',
     lambda m: _token(m[1], m[2], m[3], m[4], "", False, m[5])),
    (r"create (a|one|two|three) (treasure|clue|blood|map|lander|food|mutagen) tokens?",
     lambda m: Effect("token", _num(m[1]), data={"kind": m[2].lower()})),
    (r"create (a|one|two|three|four|five|six|seven|eight|nine|ten) tapped (treasure|clue|blood|map|lander|food|mutagen) "
     r"tokens?", lambda m: Effect("token", _TENS.get(m[1].lower(), 1), data={"kind": m[2].lower(), "tapped": True})),
    (r"create (a|one|two|three|four|five) tapped (\d+)/(\d+) ((?:\w+ )+?)creature tokens?(?: with ([\w ,]+))?",
     lambda m: _tapped(_token(m[1], m[2], m[3], m[4], m[5]))),
    (r"target player creates (a|one|two|three) (treasure|clue|blood|map|lander|food|mutagen) tokens?",
     lambda m: Effect("token", _num(m[1]), data={"kind": m[2].lower()})),
    (r"its controller creates (a|one|two|three) (treasure|clue|blood|map|lander|food|mutagen) tokens?",
     lambda m: Effect("token", _num(m[1]), target="that_controller", data={"kind": m[2].lower()})),
    (r"target creature you control explores", lambda m: Effect("explore", target="creature_mine")),
    (r"(?:you may )?return ~ from your graveyard to the battlefield( tapped)?",
     lambda m: Effect("return_self_gy", data={"tapped": bool(m[1])})),
    (r"~ explores", lambda m: Effect("explore", target="self")),
    (r"its controller (?:may search their library|searches their library) for a basic land card, puts? it onto the "
     r"battlefield tapped, then shuffles?", lambda m: Effect("fetch_basic", target="that_controller")),
    (r"exile target nonland permanent(?: an opponent controls| you don't control)?(?: with mana value (\d+) or "
     r"less)? until ~ leaves the battlefield",
     lambda m: Effect("oring", target="nonland_perm", filter=f"max_cmc:{m[1]}" if m[1] else "opp")),
    (r"exile all artifacts and creatures with mana value (\d+) or less until ~ leaves the battlefield",
     lambda m: Effect("oring_all", int(m[1]))),
    (r"(?:destroy|exile) target nonland permanent(?: an opponent controls| you don't control)?",
     lambda m: Effect("destroy", target="nonland_perm")),
    (r"its controller loses (\d+) life and you gain (\d+) life",
     lambda m: [Effect("lose_life", int(m[1]), target="that_controller"), Effect("gain_life", int(m[2]))]),
    (_SRC + r" deals damage equal to the number of (treasures|artifacts|creatures|lands) you control to any target",
     lambda m: Effect("damage", 0, target="any", data={"count": m[1].lower()})),
    (r"its controller investigates", lambda m: Effect("token", 1, target="that_controller", data={"kind": "clue"})),
    (r"create a token that's a copy of target token you control", lambda m: Effect("copy_token")),
    (r"put (a|one|two|three) \+1/\+1 counters? on (?:up to one )?target creature(?: or Vehicle)?(?: you control)?",
     lambda m: Effect("p1_counters", _num(m[1]), target="creature_mine")),
    (r"put (a|one|two|three) \+1/\+1 counters? on ~", lambda m: Effect("p1_counters", _num(m[1]), target="self")),
    (r"ELSPETHPLUS", lambda m: Effect("p1_counters", 1, target="creature_mine", data={"keyword": "flying"})),
    (r"(?:it|~) deals (\d+) damage", lambda m: Effect("damage", int(m[1]), target="prev")),
    (r"that creature gets -(\d+)/-(\d+) until end of turn",
     lambda m: Effect("debuff_one", int(m[1]), int(m[2]), target="prev")),
    (r"that creature gets \+(\d+)/\+(\d+) until end of turn",
     lambda m: Effect("pump", int(m[1]), int(m[2]), target="prev")),
    (r"destroy that creature", lambda m: Effect("destroy", target="prev")),
    (r"(?:it|that creature) also gains ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach))(?: and ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)))? until end of turn",
     lambda m: [Effect("grant", target="prev", data={"keyword": k.lower()}) for k in m.groups() if k]),
    (r"~ also deals (\d+) damage to that creature's controller",
     lambda m: Effect("damage", int(m[1]), target="that_controller")),
    (r"(?:it|that creature) gets \+(\d+)/\+(\d+)(?: and gains ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach))(?: and ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)))?)? until end of turn",
     lambda m: [Effect("pump", int(m[1]), int(m[2]), target="prev")] +
     [Effect("grant", target="prev", data={"keyword": k.lower()}) for k in (m[3], m[4]) if k]),
    (r"(?:it|that creature) gains ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)) and ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)) until end of turn",
     lambda m: [Effect("grant", target="prev", data={"keyword": k.lower()}) for k in (m[1], m[2])]),
    (r"it gains (hexproof|first strike|haste|indestructible|trample|lifelink|flying|vigilance|menace) until end of turn",
     lambda m: Effect("grant", target="prev", data={"keyword": m[1].lower()})),
    (r"target creature gains ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)) and ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)) until end of turn",
     lambda m: [Effect("grant", target="creature", data={"keyword": m[1].lower()}),
                Effect("grant", target="prev", data={"keyword": m[2].lower()})]),
    (r"target creature gains your choice of ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)) or (?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach) until end of turn",
     lambda m: Effect("grant", target="creature", data={"keyword": m[1].lower()})),
    (r"put (a|one|two) \+1/\+1 counters? on each creature target player controls",
     lambda m: Effect("p1_counters", _num(m[1]), target="my_creatures")),
    (r"that creature deals (\d+) damage to each opponent", lambda m: Effect("damage", int(m[1]), target="player")),
    (r"target creature gains (double strike|first strike|trample|haste|hexproof|indestructible) until end of turn",
     lambda m: Effect("grant", target="creature", data={"keyword": m[1].lower()})),
    (r"(?:you may )?(?:return|put) (all |(?:up to )?(?:one|two|three|four|five|six|x) (?:other )?target |(?:up to one )?target |an? )?"
     r"([\w ,/'-]+?) cards?(?: each)?(?: with mana value (\d+|x) or (less|greater))? from (your|a|an opponent's) "
     r"graveyard (to your hand|(?:onto|to) the battlefield)( tapped)?(?: under your control)?",
     lambda m: _gy_move(m)),
    (r"target instant or sorcery card in your graveyard gains flashback until end of turn",
     lambda m: Effect("grant_flashback")),
    (r"put (?:a|an) ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)) counter on (target creature|~|it)",
     lambda m: Effect("grant", target=_kw_target(m[2]), data={"keyword": m[1].lower(), "perm": True})),
    (r"put (a|two) \+1/\+1 counters? and (?:a|an) ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)) counter on (target creature|~|it)",
     lambda m: [Effect("p1_counters", _num(m[1]), target=_kw_target(m[3])),
                Effect("grant", target="prev" if m[3] != "~" else "self", data={"keyword": m[2].lower(), "perm": True})]),
    (r"put (?:a|an) ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)) counter, (?:a|an) ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)) counter, and (?:a|an) ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)) counter on target creature",
     lambda m: [Effect("grant", target="creature_mine", data={"keyword": m[1].lower(), "perm": True})] +
     [Effect("grant", target="prev", data={"keyword": m[i].lower(), "perm": True}) for i in (2, 3)]),
    (r"put an? (\w+) counter on ~", lambda m: Effect("add_counter", 1, target="self", data={"counter": m[1].lower()})),
    (r"if you attacked with two or more creatures this turn, draw a card",
     lambda m: Effect("draw", 1, cond="attacked2")),
    (r"otherwise, create a (\d+)/(\d+) ((?:\w+ )+?)creature token",
     lambda m: Effect(**{**_token("a", m[1], m[2], m[3]).__dict__, "cond": "not_attacked2"})),
    (r"then if ~ has (three) or more \w+ counters on it, transform it",
     lambda m: Effect("transform", target="self", cond="counters3")),
    (r"exile this saga, then return it to the battlefield transformed under your control|exile ~, then return it "
     r"to the battlefield transformed under your control", lambda m: Effect("transform", target="self")),
    (r"if a player is dealt damage this way, scry (\d+)", lambda m: Effect("scry", int(m[1]), cond="target_player")),
    (r"return target creature card from your graveyard to your hand", lambda m: Effect("regrow")),
    (r"REANIMATESNOW", lambda m: Effect("reanimate_snow")),
    (r"GYHATE (\d+)", lambda m: Effect("gy_hate", int(m[1]))),
    (r"when you cast your next creature spell this turn, that creature enters with an additional \+1/\+1 counter "
     r"on it", lambda m: Effect("next_creature_counter")),
    (r"ADVERSARY", lambda m: Effect("adversary", data={"cost": {"generic": 2, "R": 1}})),
    (r"~ gains ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach))(?: and ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)))? until end of turn",
     lambda m: [Effect("grant", target="self", data={"keyword": k.lower()}) for k in m.groups() if k]),
    (r"BLINKEND", lambda m: Effect("blink_end", target="creature_mine")),
    (r"put (a|one|two|three) \+1/\+1 counters? on each (other )?(tapped |legendary )?(creature|[A-Z][a-z]+) you control",
     lambda m: Effect("p1_counters", _num(m[1]), target="my_creatures",
                      data={"other": bool(m[2]), "only": (m[3] or "").strip() or
                            (m[4] if m[4] != "creature" else "")})),
    (r"(other )?creatures you control get \+(\d+)/\+(\d+)(?: and gain ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)))? until end of turn",
     lambda m: Effect("pump_all", int(m[2]), int(m[3]), data={"other": bool(m[1]), "keyword": (m[4] or "").lower()})),
    (r"(other )?creatures you control gain (KW) and get \+(\d+)/\+(\d+) until end of turn".replace("KW", "(?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)"),
     lambda m: Effect("pump_all", int(m[3]), int(m[4]), data={"other": bool(m[1]), "keyword": m[2].lower()})),
    (r"(other )?creatures you control gain ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)) until end of turn",
     lambda m: Effect("pump_all", 0, 0, data={"other": bool(m[1]), "keyword": m[2].lower()})),
    (r"double the number of \+1/\+1 counters on each creature you control",
     lambda m: Effect("double_counters", target="my_creatures")),
    (r"search your library for (an? .+?), reveal it, put it into your hand, then shuffle",
     lambda m: Effect("tutor", data={"what": m[1]})),
    (r"search your library for (an? .+?), put it into your hand, then shuffle",
     lambda m: Effect("tutor", data={"what": m[1]})),
]

_SUBS = [
    (re.compile(r"exile (?:another )?target creature you control\. return (?:it|that card) to the battlefield under its "
                r"owner's control at the beginning of the next end step\.", re.I), lambda m: "BLINKEND."),
    (re.compile(r"counter target spell unless its controller pays \{(\d+)\}\. counter that spell unless its controller pays "
                r"\{(\d+)\} instead if ~ was cast using teamwork\.", re.I), lambda m: f"COUNTERTW {m[1]} {m[2]}."),
    (re.compile(r"tap another target nonland permanent\. its activated abilities can't be activated for as long as it "
                r"remains tapped\.", re.I), lambda m: "NETTAP."),
    (re.compile(r"you may discard a card\. if you do, draw (a card|two cards)\.", re.I),
     lambda m: f"OPTCOST discard {_num(m[1].split()[0])}."),
    (re.compile(r"you may sacrifice (another |an? )?(creature or artifact|artifact or creature|artifact|creature|"
                r"enchantment or creature|artifact or creature)\. if you do, draw (a card|two cards)\.", re.I),
     lambda m: f"OPTCOST sac{'other' if (m[1] or '').startswith('another') else ''}:{m[2].replace(' or ', '|')} "
               f"{_num(m[3].split()[0])}."),
    (re.compile(r"you may sacrifice an artifact or discard a card\. if you do, draw a card\.", re.I),
     lambda m: "OPTCOST either 1."),
    (re.compile(r"gain control of target creature until end of turn\. untap that creature\. it gains haste until end "
                r"of turn\.", re.I), lambda m: "THREATEN."),
    (re.compile(r"create (a|an|x|one|two|three) 1/1 red mercenary creature tokens? with \"\{t\}: target creature you "
                r"control gets \+1/\+0 until end of turn\.\s*activate only as a sorcery\.\"", re.I),
     lambda m: f"MERCENARY {m[1]}."),
    (re.compile(r"put each card exiled with ~ into its owner's graveyard, then create a 2/2 colorless robot artifact "
                r"creature token for each card put into a graveyard this way\. sacrifice ~\.", re.I),
     lambda m: "STARCAGE."),
    (re.compile(r"you may have ~ become a legendary equipment artifact named everflame, heroes' legacy\. if you do, "
                r"it gains equip \{3\} and \"equipped creature gets \+3/\+3\" and loses all other abilities\.", re.I),
     lambda m: "IRENCRAG."),
    (re.compile(r"if evidence was collected, exile a card from an opponent's graveyard\. then search its owner's "
                r"graveyard, hand, and library for any number of cards with that name and exile them\. that player "
                r"shuffles, then draws a card for each card exiled from their hand this way\.", re.I),
     lambda m: "COVERUP."),
    (re.compile(r"put x \+1/\+1 counters on target attacking creature, where x is the number of permanents you've "
                r"sacrificed this turn\. if x is three or greater, that creature gains lifelink until end of turn\.",
                re.I), lambda m: "OBSESS."),
    (re.compile(r"you may sacrifice another creature or artifact\. if you do, draw a card and create a treasure token\.",
                re.I), lambda m: "SACDRAWTREASURE."),
    (re.compile(r"destroy up to one other target creature\. its controller amasses (\w+) x, where x is that creature's "
                r"power\. if you controlled that creature, draw a card\.", re.I), lambda m: f"AZOG {m[1]}."),
    (re.compile(r"look at the top (\w+) cards of your library\. put (\w+) of them into your hand and the "
                r"rest on the bottom of your library(?: in (?:a random|any|any random) order)?\. if there is an "
                r"instant card and a sorcery card in your graveyard, instead put two of them into your hand and the "
                r"rest on the bottom of your library in any order\.", re.I),
     lambda m: f"DIGFLOW {_num(m[1])}."),
    (re.compile(r"(create a \d+/\d+ (?:\w+ )+?creature token) named [\w' ,-]+?\. it gains haste until end of turn\.",
                re.I), lambda m: f"{m[1]} with haste."),
    (re.compile(r"you may discard a card\. if you do, draw a card\.", re.I), lambda m: "RUMMAGE 1."),
    (re.compile(r"each opponent loses X life, where X is your devotion to (white|blue|black|red|green)\. you gain "
                r"life equal to the life lost this way\.", re.I),
     lambda m: f"DEVOTIONDRAIN {dict(white='W', blue='U', black='B', red='R', green='G')[m[1].lower()]}."),
    (re.compile(r"defending player reveals the top card of their library\. if it's a land card, that player puts "
                r"it into their hand\.", re.I), lambda m: "GOBLINGUIDE."),
    (re.compile(r"target (?:player|opponent) reveals their hand\. you choose a noncreature, nonland card from it\. "
                r"that player discards that card\.", re.I), lambda m: "TARGETDISCARDNONCREATURE."),
    (re.compile(r"look at the top (\w+) cards of your library\. put (one) of them into your hand and the (?:other|rest) "
                r"on the bottom of your library(?: in any order)?\.", re.I),
     lambda m: f"DIG {_num(m[1])} {_num(m[2])}."),
    (re.compile(r"search your library for a basic land card, put it onto the battlefield tapped, then shuffle\."
                r"( then if you control four or more lands, untap that land\.)?", re.I),
     lambda m: "FETCHBASIC UNTAP4." if m[1] else "FETCHBASIC."),
    (re.compile(r"you may discard up(?: to)? (\w+) cards\. if you do, draw that many cards\.", re.I),
     lambda m: f"RUMMAGE {_num(m[1])}."),
    (re.compile(r"destroy target nonbasic land an opponent controls\. its controller searches their library for a basic "
                r"land card, puts it (?:onto|on) the battlefield tapped with a stun counter on it, then shuffles\.", re.I),
     lambda m: "STUNLANDSWAP."),
    (re.compile(r"choose up to one target creature\. put a \+1/\+1 counter and a counter from among flying, first "
                r"strike, lifelink, or vigilance on it\.", re.I), lambda m: "ELSPETHPLUS."),
    (re.compile(r"exile up to one target card from a graveyard\. if a creature card was exiled this way, each "
                r"opponent loses (\d+) life and you gain \d+ life\.", re.I), lambda m: f"GYHATE {m[1]}."),
    (re.compile(r"look at the top (\w+) cards of your library\. put (\w+) of them into your hand and the "
                r"rest on the bottom of your library(?: in (?:a random|any|any random) order)?\.", re.I),
     lambda m: f"DIG {_num(m[1])} {_num(m[2])}."),
    (re.compile(r"look at the top (\w+) cards of your library\. you may reveal (an? .+? card) from among them and "
                r"put it into your hand\. put the rest on the bottom of your library in (?:a random|any) order\.",
                re.I), lambda m: f"DIGFILTER {_num(m[1])} {m[2]}."),
    (re.compile(r"look at the top \w+ cards of your library, where X is the number of lands you control\. put "
                r"(\w+) of those cards into your hand\. put the rest on the bottom of your library in (?:a random|"
                r"any) order\.", re.I), lambda m: f"DIGLANDS {_num(m[1])}."),
    (re.compile(r"look at the top \w+ cards of your library, where X is the number of (artifacts|creatures|lands) "
                r"you control\. put (\w+) of those cards into your hand and the rest on the bottom of your library "
                r"in (?:a random|any) order\.", re.I), lambda m: f"DIGCOUNT {m[1][:-1]} {_num(m[2])}."),
    (re.compile(r"look at the top (\w+) cards of your library\. put up to (two) noncreature, nonland permanent "
                r"cards with mana value (\d+) or less from among them onto the battlefield\. put the rest on the "
                r"bottom of your library in a random order\.", re.I),
     lambda m: f"DIGPUTNONCREATURE {_num(m[1])} {m[3]} {_num(m[2])}."),
    (re.compile(r"look at the top (\w+) cards of your library\. you may put a permanent card with mana value "
                r"(\d+) or less from among them onto the battlefield(?: with a shield counter on it)?\. put the rest "
                r"on the bottom of your library in a random order\.", re.I),
     lambda m: f"DIGPUT {_num(m[1])} {m[2]}."),
    (re.compile(r"exile the top (card|\w+ cards) of your library\. until (?:the end of your next turn|end of turn), you "
                r"may play (?:that card|those cards)(?: this turn)?\.", re.I),
     lambda m: f"IMPULSE {1 if m[1] == 'card' else _num(m[1].split()[0])}."),
    (re.compile(r"target (?:player|opponent) reveals their hand\. you choose a nonland card from it\. that player discards "
                r"that card\.", re.I), lambda m: "TARGETDISCARD."),
    (re.compile(r"then return a creature or planeswalker card with mana value X or less from your graveyard to "
                r"the battlefield, where X is the amount of \{S\} spent to cast ~\.", re.I),
     lambda m: "REANIMATESNOW."),
    (re.compile(r"each player sacrifices all other creatures they control\. then each player returns all creature "
                r"cards from their graveyard that weren't put there this way to the battlefield\.", re.I),
     lambda m: "LASTGIFT."),
    (re.compile(r"you may discard a card\. if you do, search your library for a creature card, reveal it, put it "
                r"into your hand, then shuffle\.", re.I), lambda m: "DISCARDTUTOR."),
    # Face-down permanents aren't modelled, so the "unless" clause never applies.
    (re.compile(r"you may draw a card\. if you do, discard a card unless a permanent entered the battlefield face "
                r"down under your control this turn or you turned a permanent face up this turn\.", re.I),
     lambda m: "Draw a card. Then discard a card."),
    (re.compile(r"return it to the battlefield under its owner's control\. it's an enchantment\.(?: \(It's not a "
                r"creature\.\))?", re.I), lambda m: "RETURNENCHANT."),
    (re.compile(r"you may pay \{2\}\{R\} any number of times\. when you pay this cost one or more times, .*",
                re.I | re.S), lambda m: "ADVERSARY."),
]

_TRIGGERS = [
    (r"When ~ becomes level (\d+), (.+)", ("class_level",)),
    (r"Whenever you proliferate, (.+)", ("proliferate",)),
    (r"When(?:ever)? ~ enters or attacks, (.+)", ("etb", "attacks")),
    (r"When ~ enters and at the beginning of your upkeep, (.+)", ("etb", "upkeep")),
    (r"When(?:ever)? ~ enters?(?: the battlefield)?, (.+)", ("etb",)),
    (r"Whenever ~ attacks, (.+)", ("attacks",)),
    (r"When(?:ever)? ~ dies, (?:if it was a creature, )?(.+)", ("dies",)),
    (r"Whenever ~ deals combat damage to a player, (.+)", ("combat_damage_player",)),
    (r"Whenever a creature you control deals combat damage to a player, (.+)", ("ally_combat_damage",)),
    (r"Whenever you cast a noncreature spell, (.+)", ("cast_noncreature",)),
    (r"Whenever you cast an instant or sorcery spell, (.+)", ("cast_instant_sorcery",)),
    (r"Whenever you cast an instant or sorcery spell that targets a creature, (.+)", ("cast_instant_sorcery",)),
    (r"Whenever ~ becomes the target of a spell or ability you control for the first time each turn, (.+)",
     ("targeted_mine",)),
    (r"Whenever you cast a spell, (.+)", ("cast_spell",)),
    (r"Whenever you cast an? ([A-Z]\w+|creature|artifact|enchantment|outlaw) spell, (.+)", ("cast_spell",)),
    (r"Whenever you gain life, (.+)", ("gain_life",)),
    (r"Whenever you attack, (.+)", ("you_attack",)),
    (r"Whenever you attack with one or more ([A-Z]\w+), (.+)", ("you_attack",)),
    (r"Whenever a creature you control attacks, (.+)", ("creature_attacks",)),
    (r"When(?:ever)? ~ enters or leaves the battlefield, (.+)", ("etb", "leaves")),
    (r"When(?:ever)? ~ leaves the battlefield, (.+)", ("leaves",)),
    (r"Whenever a player casts a spell with mana value (\d+) or less, (.+)", ("any_cast",)),
    (r"At the beginning of your upkeep, (.+)", ("upkeep",)),
    (r"At the beginning of each(?: player's)? upkeep, (.+)", ("each_upkeep",)),
    (r"At the beginning of each opponent's upkeep, (.+)", ("opp_upkeep",)),
    (r"At the beginning of each opponent's draw step, (.+)", ("opp_draw_step",)),
    (r"At the beginning of your end step, (.+)", ("end_step",)),
    (r"At the beginning of (?:each|the) end step, (.+)", ("each_end_step",)),
    (r"At the beginning of your first main phase, (.+)", ("main1_begin",)),
    (r"Survival — At the beginning of your second main phase, if ~ is tapped, (.+)", ("survival",)),
    (r"At the beginning of your second main phase, (.+)", ("main2_begin",)),
    (r"Whenever a creature an opponent controls dies, (.+)", ("opp_creature_dies",)),
    (r"Whenever another creature you control enters or dies, if that creature's power is greater than ~'s, (.+)",
     ("other_creature_enters", "other_creature_dies")),
    (r"Whenever a land you control enters, (.+)", ("land_enters",)),
    (r"When(?:ever)? (~ or )?(another|an?) ((?:[\w-]+(?:,? or |, | ))*?(?:creature|artifact|enchantment|planeswalker|"
     r"[A-Z]\w+)s?) you control( with mana value \d+ or greater| with (?:flying|reach|haste|trample|lifelink|deathtouch))? enters(?: and whenever an? ([A-Z]\w+) you control "
     r"enters| and whenever you fully unlock a Room)?, (.+)",
     ("permanent_enters",)),
    (r"Whenever you draw a card, (.+)", ("you_draw",)),
    (r"Whenever you sacrifice (an? [\w ]+?), (.+)", ("sacrifice",)),
    (r"Whenever an opponent draws a card, (.+)", ("opp_draw",)),
    (r"Whenever ~ becomes the target of a spell, (.+)", ("targeted_by_spell",)),
    (r"When(?:ever)? ~ enters or dies, (.+)", ("etb", "dies")),
    (r"When ~ is put into a graveyard from the battlefield, (.+)", ("dies",)),
    (r"At the beginning of combat on your turn, (.+)", ("begin_combat",)),
    (r"Whenever you draw your second card each turn, (.+)", ("draw_second",)),
    (r"Whenever you cast your second spell each turn, (.+)", ("cast_second",)),
    (r"Whenever a creature you control attacks alone, (.+)", ("attacks_alone",)),
    (r"Whenever you commit a crime, (.+)", ("crime",)),
    (r"Whenever you scry or surveil, (.+)", ("scry_surveil",)),
    (r"Whenever (?:one or more|an?) (?:(.+?) )?cards? (?:leaves?|leave) your graveyard( during your turn)?, (.+)",
     ("gy_leave",)),
    (r"Whenever you discard (?:a card|one or more cards), (.+)", ("you_discard",)),
    (r"Whenever you cast a spell with mana value (\d+) or greater, (.+)", ("cast_cmc",)),
    (r"Whenever ~ attacks while saddled, (.+)", ("attacks",)),
    (r"Whenever ~ becomes tapped, (.+)", ("becomes_tapped",)),
    (r"Whenever ~ enters or becomes tapped, (.+)", ("etb", "becomes_tapped")),
    (r"Whenever you expend (\d+), (.+)", ("expend",)),
    (r"Whenever (a|another) ([\w, -]+?) you control( with (?:a|an|one or more) (?:\+1/\+1 )?counters? on it)? dies, "
     r"(.+)", ("ally_dies",)),
    (r"Whenever (a|an|another) ([\w, -]+?) you control is put into a graveyard from the battlefield, (.+)",
     ("perm_to_gy",)),
]


_OPT_RIDER = re.compile(r"(?:then )?if (?:~|it|the spell) was bargained, (.+)|(?:then )?if the gift (was|wasn't) promised, (.+)",
                        re.I)


def _opt_rider(s: str, effects: list):
    """"If ~ was bargained / the gift was promised, X [instead]": X's effects carry cond bargained / gifted (or !gifted).
    With "instead" the earlier effect of the same kind (else every unconditional one) only happens otherwise.
    Returns the new effects, or None when X doesn't parse."""
    from .parse import _parse_effects  # deferred: parse imports this module
    m = _OPT_RIDER.fullmatch(s)
    if m is None:
        return None
    cond = "bargained" if m[1] else ("gifted" if m[2].lower() == "was" else "!gifted")
    rest = (m[1] or m[3]).strip()
    instead = bool(re.search(r"\binstead$", rest, re.I)) or re.match(r"instead,? ", rest, re.I) is not None
    rest = re.sub(r",? instead$|^instead,? ", "", rest, flags=re.I)
    new, bad = _parse_effects(rest[0].upper() + rest[1:] + ".")
    if bad or not new:
        return None
    if instead:
        same = [e for e in effects if not e.cond and e.kind == new[0].kind]
        for e in same or [e for e in effects if not e.cond]:
            e.cond = "!" + cond
    for e in new:
        e.cond = e.cond or cond
    return new


_N_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "x": 0}


def _gy_move(m):
    head = (m[1] or "").lower()
    what = m[2]
    if re.search(r"\b(this|named|that)\b", what) or what.lower().startswith("up to"):
        return NO_MATCH
    w = re.search(r"(one|two|three|four|five|six|x)", head)
    n = 99 if head.startswith("all") else (_N_WORDS[w[1]] if w else 1)
    return Effect("gy_move", n, data={"what": what, "dest": "hand" if m[6].endswith("hand") else "bf",
                                      "tapped": bool(m[7]), "zone": {"your": "mine", "a": "any"}.get(m[5], "opp"),
                                      "x_n": bool(w and w[1] == "x"),
                                      "cmc": ((m[3].lower() if m[3].lower() == "x" else int(m[3])), m[4]) if m[3] else None})


def _kw_target(what: str) -> str:
    return {"~": "self", "it": "prev"}.get(what, "creature_mine")


def _xq(text: str):
    """The quantity in ", where X is ...": a tuple the engine evaluates, or None when it isn't a known one."""
    t = text.strip().rstrip(".")
    tl = t.lower()
    from ..counting import _singular
    if tl in ("your life total", "your speed", "the amount of life you gained this turn",
             "the number of cards in your hand"):
        return ({"your life total": ("life",), "your speed": ("speed",),
                 "the amount of life you gained this turn": ("gained",),
                 "the number of cards in your hand": ("hand",)}[tl])
    m = re.fullmatch(r"(~|its|that creature|that spell)'s? (power|toughness|mana value)", t, re.I) or \
        re.fullmatch(r"(its) (power|toughness)", t, re.I)
    if m:
        return ("stat", "prev" if m[1] == "that creature" else "self", m[2])
    m = re.fullmatch(r"the greatest (power|toughness) among creatures you control", t, re.I)
    if m:
        return ("greatest", m[1])
    m = re.fullmatch(r"the number of ([\w+/ -]+?) counters on ~", t, re.I)
    if m:
        return ("counters", m[1])
    m = re.fullmatch(r"the number of ([\w -]+?) cards? in your graveyard", t, re.I)
    if m:
        return ("gy", _singular(m[1]))
    if tl == "the number of cards in your graveyard":
        return ("gy", "")
    m = re.fullmatch(r"the number of ([\w -]+?) you control", t, re.I)
    if m and " with " not in m[1] and " that " not in m[1]:
        return ("count", _singular(m[1]))
    return None


_IF_CONDS = [
    (r"you attacked this turn", "attacked_turn"),
    (r"an opponent controls more lands than you", "opp_more_lands"),
    (r"a creature died this turn", "creature_died"),
    (r"a creature died under an opponent's control this turn", "opp_creature_died"),
    (r"you control another (outlaw|\w+)", None),
    (r"you control (two|three|four) or more tapped creatures", None),
    (r"you control a creature with power (\d+) or greater", None),
    (r"you sacrificed a permanent this turn", "sacrificed_turn"),
]


def _if_cond(phrase: str) -> str:
    """The engine condition name for the "if <phrase>," of a sentence, or ""."""
    phrase = phrase.strip()
    for rx, name in _IF_CONDS:
        m = re.fullmatch(rx, phrase, re.I)
        if not m:
            continue
        if name:
            return name
        if "another" in rx:
            return f"ctl_other:{m[1].capitalize() if m[1].lower() != 'outlaw' else 'outlaw'}"
        if "tapped" in rx:
            return f"tapped_creatures>={_N_WORDS.get(m[1].lower(), 2)}"
        return f"power_ge:{m[1]}"
    return ""
