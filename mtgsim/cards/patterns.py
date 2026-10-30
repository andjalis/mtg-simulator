"""Oracle-text effect templates and their small helpers. Substitutions and trigger templates are in clauses.py.

New general templates go in a mechanic module (removal.py, copies.py, ...) that exports EFFECT_PATTERNS
or SUBS; the package __init__ joins them to the tables here."""
from __future__ import annotations

import re

from . import wordings
from .model import COLORS, COLOR_WORDS, Effect, KEYWORDS, NO_MATCH, _distinct_bounce, _distinct_pump, _num, parse_mana_cost


def _parse_mana_ability(rest: str) -> tuple[set, int]:
    """Colours a {T} ability can make, and how much mana it makes ({C}{C} is 2)."""
    if "any color" in rest:
        return set(COLORS), 1
    syms = re.findall(r"\{([WUBRGC])\}", rest)
    amount = 1 if " or " in rest else max(1, len(syms))
    return set(syms), amount


def _equipment_token(m):
    from .tokens import equipment_token
    kws = {k.strip() for k in re.split(r", and |, | and ", m[6])} if m[6] else set()
    if not kws <= KEYWORDS:
        return NO_MATCH
    return Effect("token_copy", data={"card": equipment_token(m[1] or m[2], (int(m[4]), int(m[5])), kws, int(m[7]),
                                                              legendary=bool(m[3]))})


def _token(m_count, power, toughness, desc, with_kw="", attacking=False, ability=""):
    from .parse import _parse_trigger  # deferred: parse imports this module
    words = desc.split()
    subtypes = [w for w in words if not re.fullmatch(COLOR_WORDS, w, re.I) and w.lower() != "and"]
    requested = [k.strip().lower() for k in re.split(r",\s*(?:and\s+)?|\s+and\s+", with_kw or "") if k.strip()]
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


def _add_amount(m):
    """``Add an amount of {C} equal to <quantity>``: one mana per unit, when the quantity is a known one."""
    return _add_xq(m[2], Effect("add_mana", 1, data={"colors": [m[1]]}))


def _per_token(what, power, toughness, desc):
    """``Create a N/N ... creature token for each <what> you control``: amount = the number you control."""
    eff = _token("a", power, toughness, desc)
    eff.data["per"] = {"what": what, "zone": "battlefield"}
    return eff


def _add_xq(text: str, eff: Effect):
    """eff with its amount scaled by the known X-quantity in text (", where X is ..." amounts), or NO_MATCH."""
    from .clauses import _xq
    spec = _xq(text)
    if spec is None:
        return NO_MATCH
    eff.data["xq"] = spec
    return eff


def _x_sized_token(m):
    """``Create an X/X <desc> creature token, where X is <quantity>``: a 0/0 token whose size is the quantity."""
    eff = _add_xq(m[2], _token("a", 0, 0, m[1]))
    if eff is NO_MATCH:
        return NO_MATCH
    eff.data["xq_size"] = True
    return eff


_EFFECT_PATTERNS = wordings.patterns("core") + [
    # "N plus the sacrificed <permanent>'s stat" (Broadside Bombardiers, Oswald Fiddlebender):
    # the ("sac_plus", n, stat) X-quantity reads the same recorded stats as ("sac", stat).
    (r"~ deals damage equal to (\w+) plus the sacrificed "
     r"(?:creature|artifact|enchantment|planeswalker|land|permanent)'s "
     r"(power|toughness|mana value) to (any target|target creature or planeswalker|target player)",
     lambda m: Effect("damage", 1, target={"any target": "any", "target creature or planeswalker": "creature",
                                           "target player": "player"}[m[3]],
                      data={"xq": ("sac_plus", _num(m[1]), m[2])})),
    # "the exiled card's stat": the graveyard card exiled to pay the spell or ability's cost
    # (Corpse Lunge, Molten-Tail Masticore): the ("exiled_gy", stat) X-quantity.
    (r"~ deals damage equal to the exiled card's (power|toughness|mana value) to "
     r"(any target|target creature or planeswalker|target creature|target player)",
     lambda m: Effect("damage", 1, target={"any target": "any", "target creature or planeswalker": "creature",
                                           "target creature": "creature", "target player": "player"}[m[2]],
                      data={"xq": ("exiled_gy", m[1])})),
    # Dark Confidant family: the mana value of the card the resolving dig just put into the hand.
    (r"you lose life equal to (?:its|it's|that card's) mana value",
     lambda m: Effect("lose_life", 1, data={"xq": ("revealed", "mana value")})),
    # Energy counters as a plain effect (the "If you do, ..." payoff of an energy pay gate).
    (r"you get ((?:\{E\})+)", lambda m: Effect("energy", m[1].count("{E}"))),
    # Candelabra of Tawnos / Magus of the Candelabra: X is the {X} paid for the ability.
    # Skullcrack / Atarka's Command: who can't gain life this turn.
    # Energy Tap sentinel (clauses.py folds the two sentences into this): the tap gate, then the
    # ("tap", stat) X-quantity read of the creature it tapped.
    (r"ENERGYTAP", lambda m: [Effect("pay_gate", data={"gate": ("tap", "creature")}),
                              Effect("add_mana", 1, data={"colors": ["C"], "xq": ("tap", "mana value")},
                                     cond="paid")]),
    # "reveal a number of cards ... equal to <quantity>" sentinel (clauses.py): a discard scaled
    # by the X-quantity (Acquisitions Expert: ("party",)).
    (r"XDISCARD (.+)", lambda m: _add_xq(m[1], Effect("discard", 1, target="player"))),
    # Literal-name library fetches (Squadron Hawk, Screaming Seahawk): "~" in the description is
    # the resolving card's own name (engine.resolve substitutes it).
    (r"(?:you may )?search your library for (?:up to (one|two|three|four) |a |an )cards? named ([^.]+?), "
     r"reveal (?:it|them), put (?:it|them) into your hand, then shuffle",
     lambda m: Effect("search", data={"what": f"a card named {m[2]}", "n": _num(m[1] or "a"),
                                       "dest": "hand"})),
    # "Equal to the sacrificed <permanent>'s stat" effects: amount 1 times the ("sac", stat) X-quantity,
    # which the engine reads from the permanent sacrificed to pay the spell or ability's cost.
    (r"~ deals damage equal to the sacrificed (?:creature|artifact|enchantment|planeswalker|land|permanent)'s "
     r"(power|toughness|mana value) to (any target|target creature or planeswalker|"
     r"target player or planeswalker|target player)",
     lambda m: Effect("damage", 1, target={"any target": "any", "target creature or planeswalker": "creature",
                                          "target player or planeswalker": "player", "target player": "player"}[m[2]],
                      data={"xq": ("sac", m[1])})),
    (r"you gain life equal to the sacrificed (?:creature|artifact|enchantment|planeswalker|land|permanent)'s "
     r"(power|toughness|mana value)",
     lambda m: Effect("gain_life", 1, data={"xq": ("sac", m[1])})),
    (r"draw cards equal to the sacrificed (?:creature|artifact|enchantment|planeswalker|land|permanent)'s "
     r"(power|toughness|mana value)",
     lambda m: Effect("draw", 1, data={"xq": ("sac", m[1])})),
    (r"target player discards a number of cards equal to the sacrificed "
     r"(?:creature|artifact|enchantment|planeswalker|land|permanent)'s (power|toughness|mana value)",
     lambda m: Effect("discard", 1, target="player", data={"xq": ("sac", m[1])})),
    (r"add an amount of \{([WUBRGC])\} equal to (.+)", _add_amount),
    (r"add \{([WUBRGC])\} for each ([\w' -]+?) you control",
     lambda m: Effect("add_mana", 1, data={"colors": [m[1]], "xq": ("count", m[2])})),
    (r"regenerate (each|all) creatures?( you control)?",
     lambda m: Effect("regenerate", 1, target="creatures_mine" if m[2] else "each_creature")),
    (r"draw (a card|one card|(?:\d+|two|three|four|five|six|seven|eight|nine|ten) cards) at the beginning of "
     r"(the next turn's upkeep|your next upkeep)",
     lambda m: Effect("draw_delayed", _num(m[1].split()[0]),
                      data={"upkeep": "you" if m[2].lower() == "your next upkeep" else "any"})),
    (r"proliferate(?: (twice|again))?", lambda m: Effect("proliferate", 2 if (m[1] or "").lower() == "twice" else 1)),
    (_SRC + r" deals (\d+|X) damage to each creature( with(?:out)? flying)? and each player",
     lambda m: (lambda n: [Effect("damage", n, target="each_creature",
                                  filter={" without flying": "nonflying", " with flying": "flying"}.get(m[2], ""),
                                  data={} if m[1].isdigit() else {"x": True}),
                            Effect("damage_each_player", n,
                                   data={} if m[1].isdigit() else {"x": True})])(int(m[1]) if m[1].isdigit() else 0)),
    (r"destroy target creature with mana value (\d+) or less",
     lambda m: Effect("destroy", target="creature", filter=f"max_cmc:{m[1]}")),
    (r"destroy target creature if it has mana value (\d+) or less",
     lambda m: Effect("destroy", target="creature", filter=f"max_cmc:{m[1]}")),
    # "non-Angel, non-Demon, non-Dragon" style restrictions are parsed but not enforced.
    (r"another target creature you control gets \+(\d+)/\+(\d+)(?: and gains (flying|first strike|double strike|deathtouch|"
     r"lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach))? until end of turn",
     lambda m: Effect("pump", int(m[1]), int(m[2]), target="creature_mine", data={"keyword": m[3].lower()} if m[3] else {})),
    (r"target creature(?: you control)? gets \+(\d+)/\+(\d+) until end of turn",
     lambda m: Effect("pump", int(m[1]), int(m[2]), target="creature")),
    (r"~ gets ([+-]\d+)/([+-]\d+) until end of turn",
     lambda m: Effect("pump", int(m[1]), int(m[2]), target="self")),
    (r"~ gets \+(\d+)/\+(\d+) and gains (flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach) until end of turn",
     lambda m: Effect("pump", int(m[1]), int(m[2]), target="self", data={"keyword": m[3].lower()})),
    (r"exile target (artifact or creature|tapped creature) an opponent controls until ~ leaves the battlefield",
     lambda m: Effect("oring", target="nonland_perm", filter="opp_tapped_creature" if m[1].startswith("tapped")
                      else "opp_artifact_creature")),
    (r"return up to two target creatures to their owners' hands",
     lambda m: [_distinct_bounce(), _distinct_bounce()]),
    (r"one or two target creatures each get \+(\d+)/\+(\d+) until end of turn",
     lambda m: [_distinct_pump(m), _distinct_pump(m)]),
    (r"airbend (?:up to one )?(?:another |other )?target (?:(nonland permanent)|creature( you control)?)(?: or spell)?",
     lambda m: Effect("airbend", target="nonland_perm" if m[1] else "creature_mine" if m[2] else "creature")),
    (r"destroy target creature with total power and toughness (\d+) or less",
     lambda m: Effect("destroy", target="creature", filter=f"total_pt<={m[1]}")),
    (r"up to one target creature gets \+(\d+)/\+(\d+) until end of turn",
     lambda m: Effect("pump", int(m[1]), int(m[2]), target="creature_mine")),
    (r"up to one target creature gets -(\d+)/-(\d+) until end of turn",
     lambda m: Effect("debuff_one", int(m[1]), int(m[2]), target="creature", filter="opp")),
    (r"~ gets \+(\d+)/\+(\d+) until end of turn and can't be blocked this turn",
     lambda m: [Effect("pump", int(m[1]), int(m[2]), target="self"), Effect("unblockable", target="self")]),
    (r"(?:you may have )?(another )?target creature gets? -(\d+)/-(\d+) until end of turn",
     lambda m: Effect("debuff_one", int(m[2]), int(m[3]), target="creature")),
    (r"target creature gets \+(\d+)/-(\d+) until end of turn",
     lambda m: Effect("debuff_one", -int(m[1]), int(m[2]), target="creature")),
    (r"(up to (?:one|two|three)|one or two|up to two) target creatures can't block this turn",
     lambda m: [_distinct_cant_block() for _ in range({"one": 1, "two": 2, "three": 3, "one or two": 2}.get(
         m[1].split()[-1] if m[1].startswith("up to") else m[1], 2))]),
    (r"(?:it|~) must be blocked (?:this turn|each combat this turn) if able",
     lambda m: Effect("force_blocked", target="prev" if m[0].lower().startswith("it") else "self")),
    (r"counter target spell with mana value (\d+)",
     lambda m: Effect("counter", target="spell", filter=f"cmc:{m[1]}")),
    (r"counter target (white|blue|black|red|green)(?: or (white|blue|black|red|green))? spell",
     lambda m: Effect("counter", target="spell", filter="colors:" + "".join(
         {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}[c] for c in (m[1], m[2]) if c))),
    (r"discover x, where x is that spell's mana value",
     lambda m: Effect("discover", 0, target="prev", data={"x_of": "spell"})),
    (r"counter target (noncreature |creature |instant or sorcery |artifact or creature )?spell"
     r"(?: unless its controller pays \{(\d+)\})?",
     lambda m: Effect("counter", int(m[2] or 0), target="spell",
                      filter=(m[1] or "").strip().replace("instant or sorcery", "instant_sorcery")
                      .replace("artifact or creature", "artifact_creature"))),
    (r'create (?:a colorless Equipment artifact token named ([A-Z][\w\' ]+)|([A-Z][\w\' ]+), a (legendary )?colorless '
     r'Equipment artifact token) with "Equipped creature gets \+(\d+)/\+(\d+)(?: and has ([a-z, ]+))?" and equip \{(\d+)\}',
     lambda m: _equipment_token(m)),
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
    (r"destroy all (artifacts|enchantments|lands)", lambda m: Effect("destroy_all", data={"type": m[1][:-1].capitalize()})),
    (r"enchanted creature gets \+(\d+)/\+(\d+) until end of turn", lambda m: Effect("pump", int(m[1]), int(m[2]), target="host")),
    (r"put x \+1/\+1 counters on each creature you control, where x is the number of cards in your hand",
     lambda m: Effect("p1_counters", 0, target="my_creatures", data={"x": "hand"})),
    (r"add ((?:\{[WUBRGC]\})+)", lambda m: Effect("add_mana", data={"colors": re.findall(r"[WUBRGC]", m[1])})),
    (r"add (one|two|three|four|five|six|seven|eight|nine|ten|\d+) \{([WUBRGC])\}",
     lambda m: Effect("add_mana", _num(m[1]), data={"colors": [m[2]]})),
    (r"add (one|two|three|four|five|six|\d+) mana of any colou?r",
     lambda m: Effect("add_mana", _num(m[1]), data={"colors": [], "choice": list(COLORS)})),
    (r"add (one|two|three|four|five|six|\d+) mana in any combination of \{([WUBRGC])\}(?:,? and/or \{([WUBRGC])\})?",
     lambda m: Effect("add_mana", _num(m[1]), data={"colors": [], "choice": [c for c in (m[2], m[3]) if c]})),
    (r"add (one|two|three|four|five|six|\d+) mana in any combination of colou?rs",
     lambda m: Effect("add_mana", _num(m[1]), data={"colors": [], "choice": list(COLORS)})),
    (r"add \{([WUBRG])\} or \{([WUBRG])\}", lambda m: Effect("add_mana", data={"colors": [], "choice": [m[1], m[2]]})),
    # shuffling the library changes nothing the engine can observe: a no-op
    (r"(?:then )?(?:you may shuffle|shuffle|that player shuffles|they shuffle)", lambda m: None),
    # the mana pool empties at each phase end anyway (see the approximation note in clauses._SUB_NOTES)
    (r"until end of turn, you don't lose (?:this|that) mana as steps and phases end", lambda m: None),
    # library information the engine's AI has anyway: no-ops
    (r"play with the top card of your library revealed", lambda m: None),
    (r"you may look at the top card of your library any time", lambda m: None),
    (r"add one mana of any color", lambda m: Effect("add_mana", data={"colors": [], "choice": list(COLORS)})),
    (r"MERCENARY (\w+)", lambda m: Effect("token", 0 if m[1].lower() == "x" else _num(m[1]), data={
        "name": "Mercenary", "power": 1, "toughness": 1, "keywords": frozenset(), "mercenary": True,
        "x": m[1].lower() == "x"})),
    (r"AZOG (\w+?)s?", lambda m: Effect("destroy", target="creature", data={"azog": m[1].capitalize()})),
    (r"DIGFLOW (\d+)", lambda m: Effect("dig", int(m[1]), 1, data={"instead_two": "instant+sorcery"})),
    (r"DIG (\d+) (\d+)", lambda m: Effect("dig", int(m[1]), int(m[2]))),
    (r"DIGPUT (\d+) (\d+)", lambda m: Effect("dig_put", int(m[1]), int(m[2]))),
    (r"DIGPUTNONCREATURE (\d+) (\d+) (\d+)",
     lambda m: Effect("dig_put", int(m[1]), int(m[2]), data={"count": int(m[3]), "noncreature": True})),
    (r"DIGFILTER (\d+) (.+)", lambda m: Effect("dig", int(m[1]), 1, data={"filter": m[2]})),
    (r"DIGLANDS (\d+)", lambda m: Effect("dig", 0, int(m[1]), data={"x_lands": True})),
    (r"DIGCOUNT (\w+) (\d+)", lambda m: Effect("dig", 0, int(m[2]), data={"x_count": m[1]})),
    # X-scaled look with a described keep (see the DIGCOUNTFILT sub in clauses.py)
    (r"DIGCOUNTFILT (\w+) (.+)", lambda m: Effect("dig", 0, 1,
     data={"x_lands": True, "filter": m[2]} if m[1] == "land" else {"x_count": m[1], "filter": m[2]})),
    # "Target opponent reveals their hand": the peek_hand kind logs the look; the AI never
    # acts on revealed information, so that log line is the whole honest simulation.
    (r"(?:(target) (?:player|opponent)|(that player)) reveals (?:their|his or her) hand",
     lambda m: Effect("peek_hand", target="that_player" if m[2] else "player")),
    (r"(?:you may )?exile the top (card|one card|two cards|three cards|four cards|\d+ cards) of your library",
     lambda m: Effect("exile_top", _N_WORDS.get(m[1].split()[0], 1) if m[1] != "card" else 1)
     if not m[1][0].isdigit() else Effect("exile_top", int(m[1].split()[0]))),
    (r"(?:you may play (?:that card|those cards|it|them|the exiled cards?) (this turn|until the end of your next turn|"
     r"until your next end step)|until the end of your next turn, you may play (?:that card|those cards|it|them)|"
     r"until end of turn, you may play (?:that card|those cards|it|them))",
     lambda m: Effect("may_play_exiled", 0 if m[1] == "this turn" or m[1] is None and "next" not in m[0]
                      else 2)),
    (r"target creature(?: you control)? with power (\d+) or less can't be blocked this turn",
     lambda m: Effect("unblockable", target="creature_mine", filter=f"max_power:{m[1]}")),
    (r"empower jace x, where x is the number of (creatures|islands) you control",
     lambda m: Effect("empower", 0, data={"count": m[1].lower()})),
    (r"create x (mutagen) tokens", lambda m: Effect("token", 0, data={"kind": "mutagen", "x": True})),
    (r"create an? (royal|monster|wicked|cursed|sorcerer|young hero|virtuous) role token attached to "
     r"(it|that creature|(?:up to one )?(?:another |other )?target creature you control|target creature an opponent controls)",
     lambda m: Effect("role", target="prev" if m[2] in ("it", "that creature") else
                      "creature" if "opponent" in m[2] else "creature_mine",
                      filter="opp" if "opponent" in m[2] else "", data={"role": m[1].lower()})),
    (r"(\w+) and (\w+)s you control gain (indestructible|hexproof|vigilance|trample|haste|lifelink|first strike|deathtouch) "
     r"until end of turn",
     lambda m: Effect("grant_types", data={"types": (m[1], m[2]), "keyword": m[3].lower()})),
    (r"amass (\w+) (\d+)", lambda m: Effect("amass", int(m[2]), data={"type": m[1].rstrip("s").capitalize()})),
    (r"reveal the top card of your library and put (?:it|that card) into your hand", lambda m: Effect("dig", 1, 1)),
    (r"attacking creatures (?:you control )?get \+(\d+)/\+(\d+) until end of turn",
     lambda m: Effect("pump_attackers", int(m[1]), int(m[2]))),
    (r"up to (two|three) target creatures each get \+(\d+)/\+(\d+) until end of turn",
     lambda m: [Effect("pump", int(m[2]), int(m[3]), target="creature_mine", data={"distinct": True})
                for _ in range(_num(m[1]))]),
    # "sacrifice ~ unless you pay {E}{E}" (Lathnu Hellion): pay the counters when there are
    # enough, sacrifice otherwise — the pay_energy gate plus a !paid sacrifice.
    (r"sacrifice (?:~|it) unless you pay ((?:\{E\})+)",
     lambda m: [Effect("pay_energy", m[1].count("{E}")),
                Effect("sacrifice_self", target="self", cond="!paid")]),
    # "tap ~ unless you pay {E}" (Electrozoa): the same energy gate keeping the permanent tapped.
    (r"tap (?:~|it) unless you pay ((?:\{E\})+)",
     lambda m: [Effect("pay_energy", m[1].count("{E}")),
                Effect("tap", 1, target="self", cond="!paid")]),
    # Energy in a pay_or_sac cost would be a free payment (parse_mana_cost drops {E}), so the
    # mana variant below must not swallow it.
    (r"sacrifice (?:~|it) unless you pay ((?:\{[WUBRGCX0-9/P]+\})+)", lambda m: Effect("pay_or_sac", data={"cost": parse_mana_cost(m[1])})),
    (r"monstrosity (\d+|x)", lambda m: Effect("monstrosity", 0 if m[1].lower() == "x" else int(m[1]),
                                              data={"x": True} if m[1].lower() == "x" else {})),
    (r"prevent the next (\d+) damage that would be dealt to (any target|target creature|target player|~|you) this turn",
     lambda m: Effect("prevent_next", int(m[1]), target={"any target": "any", "target creature": "creature",
                                                         "target player": "player", "~": "self"}.get(m[2].lower(), "none"))),
    (r"prevent all combat damage that would be dealt this turn by creatures your opponents control",
     lambda m: Effect("fog", data={"theirs": True})),
    (r"(?:another )?target creature you control gains your choice of ([a-z ]+?), ([a-z ]+?),? or ([a-z ]+?) until end of "
     r"turn", lambda m: Effect("grant", target="creature_mine", data={"keyword": f"choice:{m[1]}|{m[2]}|{m[3]}"})
     if {m[1], m[2], m[3]} <= KEYWORDS else NO_MATCH),
    (r"put target card from (a|your) graveyard on the bottom of (?:its owner's|your) library",
     lambda m: Effect("gy_bottom", data={"mine": m[1] == "your"})),
    (r"target creature(?: you control)? gets \+(\d+)/\+(\d+) and gains (flying|first strike|double strike|deathtouch|"
     r"lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach) until end of turn",
     lambda m: Effect("pump", int(m[1]), int(m[2]), target="creature", data={"keyword": m[3].lower()})),
    (r"create (a|one|two|three|four|five) (\d+)/(\d+) ((?:\w+ )+?)creature tokens?(?: named [\w' ,-]+?)?(?: that(?:'s| are) "
     r"(tapped and attacking))?(?: with ([\w ,]+))?",
     lambda m: _token(m[1], m[2], m[3], m[4], m[6], bool(m[5]))),
    (r'create (a|one|two|three|four|five|six) (\d+)/(\d+) ((?:\w+ )+?)creature tokens? with "(.+?)"'
     r'(?: (?:It|They|This token) gains? (haste) until end of turn)?',
     lambda m: _token(m[1], m[2], m[3], m[4], m[6] or "", False, m[5])),
    (r"create (?:a|one) (\d+)/(\d+) ((?:\w+ )+?)creature tokens? for each ([\w' -]+?) you control",
     lambda m: _per_token(m[4], m[1], m[2], m[3])),
    # "Create an X/X white Spirit creature token, where X is the greatest toughness ...": the token's
    # size is the known X-quantity (resolve.py reads xq/xq_size off any effect).
    (r"create an X/X ((?:\w+ )+?)creature token, where X is (.+)",
     lambda m: _x_sized_token(m)),
    (r"create (a|one|two|three|four|five|six|seven|eight|nine|ten) tapped (treasure|clue|blood|map|lander|food|mutagen) "
     r"tokens?", lambda m: Effect("token", _TENS.get(m[1].lower(), 1), data={"kind": m[2].lower(), "tapped": True})),
    (r"create (a|one|two|three|four|five) tapped (\d+)/(\d+) ((?:\w+ )+?)creature tokens?(?: with ([\w ,]+))?",
     lambda m: _tapped(_token(m[1], m[2], m[3], m[4], m[5]))),
    (r"exile target nonland permanent(?: an opponent controls| you don't control)?(?: with mana value (\d+) or "
     r"less)? until ~ leaves the battlefield",
     lambda m: Effect("oring", target="nonland_perm", filter=f"max_cmc:{m[1]}" if m[1] else "opp")),
    (r"put a number of \+1/\+1 counters? on ~ equal to (.+)",
     lambda m: _add_xq(m[1], Effect("p1_counters", 1, target="self"))),
    # "At the beginning of your draw step, draw an additional card": one more than the turn's draw
    (r"draw an additional card(, then discard a card)?",
     lambda m: [Effect("draw", 1)] + ([Effect("discard", 1)] if m[1] else [])),
    (r"(?:it|~) deals (\d+) damage", lambda m: Effect("damage", int(m[1]), target="prev")),
    (r"that creature gets -(\d+)/-(\d+) until end of turn",
     lambda m: Effect("debuff_one", int(m[1]), int(m[2]), target="prev")),
    (r"that creature gets \+(\d+)/\+(\d+) until end of turn",
     lambda m: Effect("pump", int(m[1]), int(m[2]), target="prev")),
    (r"(?:it|that creature) also gains ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach))(?: and ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)))? until end of turn",
     lambda m: [Effect("grant", target="prev", data={"keyword": k.lower()}) for k in m.groups() if k]),
    (r"(?:it|that creature) gets \+(\d+)/\+(\d+)(?: and gains ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach))(?: and ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)))?)? until end of turn",
     lambda m: [Effect("pump", int(m[1]), int(m[2]), target="prev")] +
     [Effect("grant", target="prev", data={"keyword": k.lower()}) for k in (m[3], m[4]) if k]),
    (r"(?:it|that creature) gains ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)) and ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)) until end of turn",
     lambda m: [Effect("grant", target="prev", data={"keyword": k.lower()}) for k in (m[1], m[2])]),
    (r"(?:you may )?(?:return|put) (all |(?:up to )?(?:one|two|three|four|five|six|x) (?:other )?target |(?:up to one )?target |an? )?"
     r"([\w ,/'-]+?) cards?(?: each)?(?: with mana value (\d+|x) or (less|greater))? from (your|a|an opponent's) "
     r"graveyard (to your hand|(?:onto|to) the battlefield)( tapped)?(?: under your control)?",
     lambda m: _gy_move(m)),
    (r"put (?:a|an) ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)) counter on (target creature|~|it)",
     lambda m: Effect("grant", target=_kw_target(m[2]), data={"keyword": m[1].lower(), "perm": True})),
    (r"put (a|two) \+1/\+1 counters? and (?:a|an) ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)) counter on (target creature|~|it)",
     lambda m: [Effect("p1_counters", _num(m[1]), target=_kw_target(m[3])),
                Effect("grant", target="prev" if m[3] != "~" else "self", data={"keyword": m[2].lower(), "perm": True})]),
    (r"put (?:a|an) ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)) counter, (?:a|an) ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)) counter, and (?:a|an) ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)) counter on target creature",
     lambda m: [Effect("grant", target="creature_mine", data={"keyword": m[1].lower(), "perm": True})] +
     [Effect("grant", target="prev", data={"keyword": m[i].lower(), "perm": True}) for i in (2, 3)]),
    (r"otherwise, create a (\d+)/(\d+) ((?:\w+ )+?)creature token",
     lambda m: Effect(**{**_token("a", m[1], m[2], m[3]).__dict__, "cond": "not_attacked2"})),
    (r"return target creature card from your graveyard to your hand", lambda m: Effect("regrow")),
    (r"when you cast your next creature spell this turn, that creature enters with an additional \+1/\+1 counter "
     r"on it", lambda m: Effect("next_creature_counter")),
    (r"~ gains ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach))(?: and ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)))? until end of turn",
     lambda m: [Effect("grant", target="self", data={"keyword": k.lower()}) for k in m.groups() if k]),
    (r'you get an emblem with "([A-Z][a-z]+)s you control get \+(\d+)/\+(\d+)\.?"',
     lambda m: Effect("emblem", _num(m[2]), _num(m[3]), data={"subtype": m[1]})),
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
    (r"each equipped attacking creature gains ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|"
     r"haste|indestructible|menace)) until end of turn",
     lambda m: Effect("pump_all", 0, 0, data={"keyword": m[1].lower(), "only": "equipped_attacking"})),
    (r"search your library for (an? .+?), reveal it, put it into your hand, then shuffle",
     lambda m: Effect("tutor", data={"what": m[1]})),
    (r"search your library for (an? .+?), put it into your hand, then shuffle",
     lambda m: Effect("tutor", data={"what": m[1]})),
]


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
