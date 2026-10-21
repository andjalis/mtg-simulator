"""The line parsers behind _parse_face: each takes one oracle line of a face and returns None once it
has consumed it, or the line (possibly rewritten) for the next parser. They share a _FaceState."""
from __future__ import annotations

import re

from .. import discounts, graveyard, modal
from .. import alt_casts as _alt_casts, auras as _auras, copies as _copies, counting as _counting, creature_keywords as _creature_keywords
from .model import Activated, AltCost, COLORS, Effect, KEYWORDS, NUMBERS, Trigger, _num, parse_mana_cost
from .patterns import _parse_mana_ability
from .parse import _apply_speed_gate, _mana_restriction, _parse_ability, _parse_effects, _parse_trigger


class _FaceState:
    """What _parse_face has gathered so far for one face (its locals, shared with the line parsers)."""

    def __init__(self, **values):
        self.__dict__.update(values)


def _face_special_lines(st, line):
    """Speed gates, graveyard abilities, one-off statics, kicker and ability-word prefixes, keyword lines. Returns the line to keep parsing, or None once it is handled."""
    activated = st.activated
    approximations = st.approximations
    extra = st.extra
    gate = st.gate
    keywords = st.keywords
    kicked = st.kicked
    level_marks = st.level_marks
    triggers = st.triggers
    unsupported = st.unsupported
    try:
        if gate is not None:
            _apply_speed_gate(gate, triggers, activated)
            gate = None
        if not line:
            return None
        gm = re.fullmatch(r"Max speed — (.+)", line)
        if gm:
            gate = len(triggers), len(activated)
            line = gm[1]
            m = re.fullmatch(r"~ gets \+(\d+)/\+(\d+)(?: and has ([a-z ]+))?\.", line)
            if m:
                extra["pt_if"] = extra.get("pt_if", ()) + (("speed>=4", int(m[1]), int(m[2])),)
                if m[3] and m[3] in KEYWORDS:
                    extra["cond_keywords"] = extra.get("cond_keywords", ()) + ((m[3], "max_speed"),)
                return None
            m = re.fullmatch(r"~ has ([a-z ]+?)(?: and ([a-z ]+))?\.", line)
            if m and m[1] in KEYWORDS and (m[2] is None or m[2] in KEYWORDS):
                for kw in (m[1], m[2]):
                    if kw:
                        extra["cond_keywords"] = extra.get("cond_keywords", ()) + ((kw, "max_speed"),)
                return None
        if line == "Bargain":
            extra["bargain"] = True
            return None
        if "Copy those cards. You may cast any number of spells" in line:
            approximations.append("the exiled cards themselves are cast, not token copies")
        m = re.fullmatch(r"Gift (a card|a Food|a Treasure|a tapped Fish|an Octopus)", line)
        if m:
            extra["gift"] = m[1].split(" ", 1)[1].lower()
            return None
        m = re.fullmatch(r"((?:\{[WUBRGC0-9/]+\})+): Return (?:this card|~) from your graveyard to your hand\.", line)
        if m:
            extra["gy_return"] = parse_mana_cost(m[1])
            return None
        if graveyard.is_return_ability(line):
            act = graveyard.parse_ability(line, approximations)
            if act is None:
                unsupported.append(line)
            else:
                act.needs_max_speed = gate is not None
                extra.setdefault("gy_activated", []).append(act)
            return None
        m = re.fullmatch(r"((?:\{[WUBRGC0-9/]+\})+), Exile this card from your graveyard: Draw a card\.", line)
        if m:
            extra["gy_exile_draw"] = parse_mana_cost(m[1])
            extra["gy_needs_speed"] = gate is not None
            return None
        if re.fullmatch(r"If one or more tokens would be created under your control, twice that many of those tokens "
                        r"are created instead\.", line):
            extra["token_double"] = True
            return None
        m = re.fullmatch(r"Creatures you control of the chosen type get \+(\d+)/\+(\d+)\.", line)
        if m:
            extra["anthem_chosen"] = (int(m[1]), int(m[2]))
            return None
        m = re.fullmatch(r"~ can't be blocked by creatures with power (\d+) or greater\.", line)
        if m:
            extra["max_blocker_power"] = int(m[1])
            return None
        if line == "~ can't be blocked.":
            keywords.add("unblockable")
            return None
        if line == "You have no maximum hand size.":
            extra["no_max_hand"] = True
            return None
        if line == "~ attacks each combat if able.":
            extra["must_attack"] = True
            return None
        m = re.fullmatch(r"~ enters with (\w+) -1/-1 counters on it\.", line)
        if m:
            extra["etb_named_counters"] = ("-1/-1", _num(m[1]))
            return None
        if line == "Job select":
            triggers.append(Trigger("etb", [Effect("job_select")]))
            return None
        if line == "Start your engines!":
            extra["start_engines"] = True
            return None
        if any(a.startswith("never paid: As an additional cost") for a in approximations):
            line = re.sub(r"\s*If ~'s additional cost was paid, [^.]+\.", "", line).strip()
            if not line:
                return None
        kicked += re.findall(r"If ~ was kicked, (.+?\.)", line)
        line = re.sub(r"\s*If ~ was kicked, .+?\.", "", line).strip()
        lv = re.fullmatch(r"((?:\{[WUBRGC0-9/]+\})+): Level (\d+)", line)
        if lv:
            n = int(lv[2])
            activated.append(Activated("ability", parse_mana_cost(lv[1]), effects=[Effect("level_up", data={"to": n})],
                                       extra_costs={"level_from": n - 1}, sorcery=True, text=line))
            level_marks.append((n, len(triggers)))
            return None
        line = re.sub(r"^(?:Landfall|Revolt|Raid|Morbid|Eerie|Opus|Repartee|Valiant|Alliance|Void|Delirium|Hellbent|Metalcraft|Threshold|Ferocious|Flurry|Disappear|Celebration|Heroic) — (?=When|At|If)", "", line)
        line = re.sub(r"^[A-Z][a-z]+'s [A-Z][a-z]+ — (?=When )", "", line)    # a named trigger: Wasp's Sting
        if _creature_keywords.parse_line(line, st) or _alt_casts.parse_line(line, st):
            return None
        parts = [p.strip().lower() for p in re.split(r",(?: and)? | and |,", line)]
        if all(p in KEYWORDS or re.fullmatch(r"(?:ward \{\d+\}|toxic \d+|bushido \d+)", p) for p in parts):
            for p in parts:
                if p.startswith("ward"):
                    extra["ward"] = int(re.search(r"\d+", p)[0])
                elif p.startswith("toxic"):
                    extra["toxic"] = extra.get("toxic", 0) + int(p.split()[1])
                elif p.startswith("bushido"):
                    n = int(p.split()[1])     # whenever it blocks or becomes blocked, +N/+N until end of turn
                    triggers += [Trigger(event, [Effect("pump", n, n, target="self")])
                                 for event in ("blocks", "becomes_blocked")]
                else:
                    keywords.add(p)
                    if p == "exalted":
                        extra["exalted"] = extra.get("exalted", 0) + 1
                    elif p in ("cascade", "storm"):
                        extra[p] = extra.get(p, 0) + 1
                    elif p == "flanking":
                        triggers.append(Trigger("becomes_blocked", [Effect("flanking")]))
            return None
        return line
    finally:
        st.gate = gate
        st.kicked = kicked


def _face_mode_and_ward_lines(st, line):
    """Bullet modes and ward variants. Returns the line to keep parsing, or None once it is handled."""
    approximations = st.approximations
    extra = st.extra
    mode_sink = st.mode_sink
    produces = st.produces
    unsupported = st.unsupported
    try:
        bullet = modal.parse_bullet(line) if mode_sink is not None else None
        if bullet is not None:
            effs, bad = _parse_effects(bullet[1])
            if bad or not effs:
                unsupported.append(line)
            else:
                modal.add_mode(mode_sink, effs, bullet[0])
            return None
        mode_sink = None
        m = re.fullmatch(r"Ward—Pay (\d+) life\.", line)
        if m:
            extra["ward_life"] = int(m[1])
            return None
        if re.fullmatch(r"Ward—Discard a card\.", line):
            extra["ward_discard"] = True
            return None
        m = re.fullmatch(r"~ has ward \{(\d+)\} as long as it's untapped\.", line, flags=re.I)
        if m:
            extra.update(ward=int(m[1]), ward_untapped_only=True)
            return None
        m = re.fullmatch(r"\{T\}(, Pay 1 life)?: Add (one mana of any color|\{[WUBRGC]\}+)\. Spend this mana only "
                         r"(.+)\.", line)
        if m:
            restriction = _mana_restriction(m[3])
            if restriction is None:
                produces |= set(COLORS) if "any color" in m[2] else set(re.findall(r"[WUBRGC]", m[2]))
                unsupported.append(f"mana restriction ignored: Spend this mana only {m[3]}.")
                return None
            cols, amount = _parse_mana_ability(m[2])
            extra["mana_restriction"] = restriction
            extra["restricted_produces"] = frozenset(cols)
            if amount > 1:
                extra["mana_amount"] = amount
            if m[1]:
                approximations.append("the 1 life for restricted mana isn't paid")
            return None
        return line
    finally:
        st.mode_sink = mode_sink
        st.produces = produces


def _face_land_and_mana_lines(st, line):
    """Choices on entry, enters-tapped lands, mana abilities, equipment, counters on entry, station. Returns the line to keep parsing, or None once it is handled."""
    activated = st.activated
    alt_costs = st.alt_costs
    approximations = st.approximations
    enters_tapped = st.enters_tapped
    etb = st.etb
    extra = st.extra
    produces = st.produces
    station_min = st.station_min
    triggers = st.triggers
    types = st.types
    try:
        if re.fullmatch(r"As ~ enters(?: the battlefield)?, choose a creature type\.", line):
            extra["choose_type"] = "creature"
            return None
        if re.fullmatch(r"As ~ enters(?: the battlefield)?, choose a basic land type\. Then you may pay 2 life\. If you "
                        r"don't, it enters tapped\.", line):
            extra.update(choose_type="basic_land", tapped_condition="shock")
            return None
        if line == "~ is the chosen type." and extra.get("choose_type") == "basic_land":
            return None
        m = re.fullmatch(r"~ enters(?: the battlefield)? tapped unless you control (an? .+?)\.", line)
        if m and all(re.fullmatch(r"an? (basic land|[A-Z]\w+)", part) for part in m[1].split(" or ")):
            kinds = [re.fullmatch(r"an? (basic land|[A-Z]\w+)", part)[1] for part in m[1].split(" or ")]
            extra["tapped_condition"] = "unless_control:" + "|".join("basic" if k == "basic land" else k for k in kinds)
            return None
        if re.fullmatch(r"~ enters(?: the battlefield)? tapped unless you control a planeswalker\.", line):
            extra["tapped_condition"] = "unless_pw"
            return None
        if re.fullmatch(r"~ enters(?: the battlefield)? tapped unless a player has (\d+) or less life\.", line):
            extra["tapped_condition"] = "unless_player_life<=" + re.search(r"(\d+)", line)[1]
            return None
        m = re.fullmatch(r"As ~ enters(?: the battlefield)?, you may behold an? ([A-Z]\w+)\. If you don't, ~ enters "
                         r"(?:the battlefield )?tapped\.", line)
        if m:
            extra["tapped_condition"] = f"behold:{m[1]}"
            return None
        if line == "~ must be blocked if able.":
            extra["must_be_blocked"] = True
            return None
        if line == "Creatures with power less than ~'s power can't block it.":
            extra["blocker_power_rel"] = True
            return None
        m = re.fullmatch(r"~ can't attack unless defending player controls an? (Island|Swamp|Mountain|Forest|Plains)\.", line)
        if m:
            extra["attack_needs"] = m[1]
            return None
        if line == "~ enters tapped unless you have two or more opponents.":
            extra["tapped_condition"] = "always"         # two players: there is one opponent
            return None
        m = re.fullmatch(r"~ enters tapped unless you control (two|three) or more basic lands\.", line)
        if m:
            extra["tapped_condition"] = f"unless_basics>={_num(m[1])}"
            return None
        m = re.fullmatch(r"~ enters tapped unless your opponents control (\w+) or more lands\.", line)
        if m:
            extra["tapped_condition"] = f"unless_opp_lands>={_num(m[1])}"
            return None
        if line == "~ doesn't untap during your untap step.":
            extra["no_untap"] = True
            return None
        if re.fullmatch(r"~ can't block\.", line):
            extra["cant_block"] = True
            return None
        if line == "~ can block only creatures with flying.":
            extra["block_only_flying"] = True
            return None
        m = re.fullmatch(r"Equipped creature (?:gets \+(\d+)/\+(\d+))?(?: and )?(?:has (.+?))?"
                         r"(?:(?: and )?is an? ([A-Z]\w+) in addition to its other types)?\.", line)
        if m and m[4]:
            approximations.append(f"the {m[4]} type isn't added")
        if m and (m[1] or m[3]):
            kws, ward, ok = set(), 0, True
            for k in re.split(r", (?:and )?| and ", m[3] or ""):
                k = k.strip().lower()
                if not k:
                    continue
                if re.fullmatch(r"ward \{(\d+)\}", k):
                    ward = int(re.search(r"\d+", k)[0])
                elif k in KEYWORDS:
                    kws.add(k)
                elif k == "hexproof from monocolored":
                    kws.add("hexproof")
                    approximations.append("hexproof from monocolored is played as hexproof")
                else:
                    ok = False
            if ok:
                extra.update(equip_bonus=(int(m[1] or 0), int(m[2] or 0)), equip_keywords=frozenset(kws),
                             equip_ward=ward)
                return None
        m = re.fullmatch(r"Equip (\{[^ .]+\})(\. This ability costs [^.]+ less to activate[^.]*\.)?", line)
        if m:
            extra["equip_cost"] = parse_mana_cost(m[1])
            if m[2]:
                approximations.append(f"cost reduction ignored:{m[2]}")
            return None
        m = re.fullmatch(r"Equip abilities you activate that target ~ cost \{(\d+)\} less to activate\.", line)
        if m:
            extra["equip_discount"] = int(m[1])
            return None
        if re.fullmatch(r"If (?:~|this card) is in your opening hand, you may begin the game with it on the "
                        r"battlefield\.", line):
            extra["leyline"] = True
            return None
        m = re.fullmatch(r"~ has ([\w ]+?) as long as (you control another ([A-Z]\w+)|an opponent has (\d+) or less "
                         r"life)\.", line)
        if m and m[1].lower() in KEYWORDS:
            cond = f"another:{m[3]}" if m[3] else f"opp_life<={m[4]}"
            extra["cond_keywords"] = extra.get("cond_keywords", ()) + ((m[1].lower(), cond),)
            return None
        if line == "Activated abilities of artifacts, creatures, and planeswalkers can't be activated.":
            extra["stops_activations"] = True
            return None
        if re.fullmatch(r"\{1\}, \{T\}: Add one mana of any color\.", line):
            produces |= set(COLORS)
            extra["mana_filter"] = "tap"
            return None
        m = re.fullmatch(r"\{1\}: Add (one mana of any color|\{[WUBRG]\}, \{[WUBRG]\}, or \{[WUBRG]\})\. (?:~ becomes that "
                         r"color until end of turn\. )?Activate only once each turn\.", line)
        if m:
            produces |= set(COLORS) if "any color" in m[1] else set(re.findall(r"[WUBRG]", m[1]))
            extra["mana_filter"] = "once"
            return None
        m = re.fullmatch(r"\{T\}, Tap an untapped (creature|permanent) you control: Add one mana of any color\.", line)
        if m:
            produces |= set(COLORS)
            extra["mana_tap_other"] = m[1]
            return None
        if line == "{T}, Sacrifice ~: Add one mana of any color.":
            produces |= set(COLORS)
            extra["mana_sac"] = True
            return None
        m = re.fullmatch(r"\{T\}: Add one mana of any color\. Activate only if you control an? (\w+)\.", line)
        if m:
            produces |= set(COLORS)
            extra["mana_cond"] = m[1]
            return None
        m = re.fullmatch(r"\{T\}: Add (\{[WUBRG]\}(?: or \{[WUBRG]\})?)\. (Activate only if [^.]+\.)", line)
        if m:
            produces |= set(re.findall(r"[WUBRG]", m[1]))
            approximations.append(f"condition ignored: {m[2]}")
            return None
        if re.fullmatch(r"\{T\}, Pay 1 life: Add one mana of any color\.", line):
            produces |= set(COLORS)
            approximations.append("the 1 life for coloured mana isn't paid")
            return None
        if re.fullmatch(r"~ enters tapped unless it's your first, second, or third turn of the game\.", line):
            extra["tapped_condition"] = "after_turn3"
            return None
        if re.fullmatch(r"~ enters tapped if it's not your turn\.", line):
            extra["tapped_condition"] = "not_your_turn"
            return None
        m = re.fullmatch(r"\{T\}: Add ([^.]+)\.(?: ~ deals 1 damage to you\.)?", line)
        if m:
            cols, amount = _parse_mana_ability(m[1])
            produces |= cols
            extra["mana_amount"] = max(amount, extra.get("mana_amount", 1))
            return None
        if re.fullmatch(r"~ enters(?: the battlefield)? tapped\.", line):
            enters_tapped = True
            return None
        if re.fullmatch(r"~ enters(?: the battlefield)? tapped unless you control two or more other lands\.", line):
            extra["tapped_condition"] = "unless_2_lands"
            return None
        if re.fullmatch(r"~ enters(?: the battlefield)? tapped unless you control two or fewer other lands\.", line):
            extra["tapped_condition"] = "unless_le_2_lands"
            return None
        m = re.fullmatch(r"~ enters(?: the battlefield)? with (a|one|two|three|four|five) \+1/\+1 counters? on it\.",
                         line)
        if m:
            extra["etb_counters"] = _num(m[1])
            return None
        m = re.fullmatch(r"~ enters with (a|one|two|three|four|five) (\w+) counters? on it\.", line)
        if m:
            extra["etb_named_counters"] = (m[2].lower(), _num(m[1]))
            return None
        m = re.fullmatch(r"Craft with artifact (\{[^ (]+\})(?: \(.*\))?", line)
        if m:
            activated.append(Activated("ability", parse_mana_cost(m[1]), effects=[Effect("craft")],
                                       extra_costs={"exile_self": True, "craft": "artifact"}, sorcery=True,
                                       text=line))
            return None
        if re.fullmatch(r"Station(?: \(.*\))?", line):
            extra["station"] = True
            return None
        m = re.fullmatch(r"STATION (\d+)\+", line)
        if m:
            station_min = int(m[1])
            return None
        m = re.fullmatch(r"\{T\}, Sacrifice ~: (Search your library for a basic land card, put it onto the battlefield "
                         r"tapped, then shuffle\.(?: Then if you control four or more lands, untap that land\.)?)", line)
        if m and "Land" in types:
            effs, _ = _parse_effects(m[1])
            approximations.append("cracked as soon as it enters")
            effs[0].data["sacrifice"] = True
            triggers.append(Trigger("etb", effs))
            etb += effs
            return None
        if re.fullmatch(r"If a source you control would deal noncombat damage to a creature an opponent controls, put "
                        r"that many -1/-1 counters on that creature instead\.", line):
            extra["wither_noncombat"] = True
            return None
        if re.fullmatch(r"If a creature dealt damage this turn by a source you controlled would die, exile it "
                        r"instead\.", line):
            extra["exile_damaged"] = True
            return None
        if line in ("Daybound", "Nightbound"):
            approximations.append("day/night isn't tracked: it stays on its front face")
            return None
        if re.fullmatch(r"Casualty \d+", line):
            approximations.append(f"never paid: {line}")
            return None
        m = re.fullmatch(r"Impending (\d+)—(\{[^ ]+\})", line)
        if m:
            alt_costs.append(AltCost("impending", parse_mana_cost(m[2]), counters=int(m[1])))
            return None
        m = re.fullmatch(r"Spells your opponents cast that target ~ cost an additional (\d+) life to cast\.", line)
        if m:
            approximations.append(f"as ward (pay {m[1]} life): {line}")
            extra["ward_life"] = int(m[1])
            return None
        return line
    finally:
        st.enters_tapped = enters_tapped
        st.etb = etb
        st.produces = produces
        st.station_min = station_min


def _face_cost_and_static_lines(st, line):
    """Alternative and additional costs, cost reductions, anthems and other static abilities. Returns the line to keep parsing, or None once it is handled."""
    alt_costs = st.alt_costs
    approximations = st.approximations
    enters_tapped = st.enters_tapped
    extra = st.extra
    produces = st.produces
    triggers = st.triggers
    unsupported = st.unsupported
    try:
        m = re.fullmatch(r"(Warp|Evoke|Offspring|Plot) (\{[^ ]+\})", line)
        if m:
            alt_costs.append(AltCost(m[1].lower(), parse_mana_cost(m[2]), hybrid=tuple(
                a + b for a, b in re.findall(r"\{([WUBRG])/([WUBRG])\}", m[2]))))
            return None
        m = re.fullmatch(r"(?:Renew — )?(\{[^:]+\}), Exile (?:~|this card) from your graveyard: (.+?)"
                         r"(?: Activate only as a sorcery\.)?", line)
        if m:
            effs, bad = _parse_effects(m[2])
            if effs and not bad:
                alt_costs.append(AltCost("gy_ability", parse_mana_cost(m[1]), zone="graveyard", effects=effs))
                return None
        m = re.fullmatch(r"Harmonize (\{[^ ]+\})", line)
        if m:
            alt_costs.append(AltCost("flashback", parse_mana_cost(m[1]), zone="graveyard"))
            approximations.append("harmonize: tapping a creature to reduce the cost isn't used")
            return None
        if line == "Spree":
            extra["is_spree"] = True
            return None
        m = re.fullmatch(r"\+ (\{[^ ]+\}) — (.+)", line)
        if m and extra.get("is_spree"):
            effs, bad = _parse_effects(m[2])
            if effs and not bad:
                extra.setdefault("spree", []).append((parse_mana_cost(m[1]), effs))
            else:
                unsupported.append(line)
            return None
        m = re.fullmatch(r"~ enters(?: the battlefield)? with X \+1/\+1 counters on it\.", line)
        if m:
            extra["etb_counters"] = -1
            return None
        m = re.fullmatch(r"Kicker (\{[^ ]+\})", line)
        if m:
            extra["kicker"] = parse_mana_cost(m[1])
            return None
        m = re.fullmatch(r"Teamwork (\d+)(?: \(.*\))?", line)
        if m:
            extra["teamwork"] = int(m[1])
            return None
        m = re.fullmatch(r"As an additional cost to cast ~, you may collect evidence (\d+)\.", line)
        if m:
            extra["collect_evidence"] = int(m[1])
            return None
        if re.fullmatch(r"As an additional cost to cast ~, you may [^.]+\.", line):
            approximations.append(f"never paid: {line}")
            return None
        if re.fullmatch(r"If ~'s additional cost was paid, [^.]+\.", line) and approximations:
            return None
        m = re.fullmatch(r"As an additional cost to cast ~, (?:discard a card or )?pay (\d+) life\.", line)
        if m:
            extra["extra_life_cost"] = int(m[1])
            return None
        if re.fullmatch(r"If you control two or more other lands, ~ enters(?: the battlefield)? tapped\.", line):
            extra["tapped_condition"] = "if_2_lands"
            return None
        if re.fullmatch(r"As ~ enters(?: the battlefield)?, you may pay 2 life\. If you don't, it enters "
                        r"(?:the battlefield )?tapped\.", line):
            extra["tapped_condition"] = "shock"
            return None
        if re.fullmatch(r"~ can't be countered\.", line):
            extra["uncounterable"] = True
            return None
        if re.fullmatch(r"Instant and sorcery spells you control can't be countered\.", line):
            extra["protects_spells"] = True
            return None
        m = re.fullmatch(r"~ costs \{1\} less to cast for each ([\w, /-]+?) cards? in your graveyard\.", line)
        if m and m[1] != "instant and sorcery":
            extra["cost_reduction"] = "gy:" + m[1].replace("and/or", "or")
            return None
        if re.fullmatch(r"~ costs \{1\} less to cast for each instant and sorcery card in your graveyard\.", line):
            extra["cost_reduction"] = "instant_sorcery_gy"
            return None
        if re.fullmatch(r"~ costs \{X\} less to cast, where X is the number of cards in your graveyard that are instant "
                        r"cards, sorcery cards, and/or have an Adventure\.", line):
            extra["cost_reduction"] = "instant_sorcery_adventure_gy"
            return None
        if re.fullmatch(r"~ costs \{X\} less to cast, where X is the greatest mana value among Elementals you control\.",
                        line):
            extra["cost_reduction"] = "greatest_elemental"
            return None
        if re.fullmatch(r"~ costs \{X\} less to cast, where X is the total power of creatures you control\.", line):
            extra["cost_reduction"] = "power"
            return None
        m = re.fullmatch(r"Affinity for (\w+?)s", line)
        if m:
            extra["cost_reduction"] = "affinity:" + m[1]
            return None
        if re.fullmatch(r"You may play an additional land on each of your turns\.", line):
            extra["extra_lands"] = 1
            return None
        if re.fullmatch(r"You may play lands from your graveyard\.", line):
            extra["lands_from_gy"] = True
            return None
        if _counting.parse_line(line, extra):
            return None
        m = re.fullmatch(r"As an additional cost to cast ~, (?:pay \{(\d+)\} or )?sacrifice (an? (?:artifact|creature|enchantment|"
                         r"planeswalker|land)(?: or (?:artifact|creature|enchantment|planeswalker))*)(?: or pay \{(\d+)\})?\.", line)
        if m:
            extra["extra_sacrifice"] = m[2]
            extra["extra_sac_or_pay"] = int(m[1] or m[3] or 0)
            return None
        m = re.fullmatch(r"~ can't be blocked by creatures with power (\d+) or less\.", line)
        if m:
            extra["min_blocker_power"] = int(m[1]) + 1
            return None
        m = re.fullmatch(r"As long as ~ has (three) or more \+1/\+1 counters on it, it has (\w+)\.", line)
        if m:
            extra["keyword_at_counters"] = (_num(m[1]), m[2].lower())
            return None
        m = re.fullmatch(r"Creatures you control have (haste|trample|vigilance|lifelink|menace|flying|reach)\.", line)
        if m:
            extra["team_keywords"] = extra.get("team_keywords", frozenset()) | {m[1]}
            return None
        m = re.fullmatch(r"(Red|White|Blue|Black|Green|Instant and sorcery|Creature|Artifact|Noncreature|[A-Z][a-z]+) "
                         r"spells you cast cost \{(\d+)\} less to cast\.", line)
        if m:
            extra["cost_discount"] = extra.get("cost_discount", ()) + ((m[1].lower(), int(m[2])),)
            return None
        m = re.fullmatch(r"(?:(Permanent|Creature|Artifact|Enchantment) )?[Ss]pells you cast that have an Adventure "
                         r"cost \{(\d+)\} less to cast\.", line)
        if m:
            scope = (m[1] or "all").lower()
            extra["cost_discount"] = extra.get("cost_discount", ()) + ((f"has_adventure:{scope}", int(m[2])),)
            return None
        m = re.fullmatch(r"(Creatures|Lands|Creature tokens|Foods|Other permanents|Each land and Ally) you control "
                         r"(?:have|has) \"\{T\}: Add (one mana of any color|\{[WUBRGC]\})\.\"", line)
        if m:
            scope = {"creatures": "creature", "lands": "land", "creature tokens": "creature_token", "foods": "food",
                     "other permanents": "other", "each land and ally": "land_or_ally"}[m[1].lower()]
            cols = frozenset(COLORS) if "any color" in m[2] else frozenset(re.findall(r"[WUBRGC]", m[2]))
            extra["grant_mana"] = extra.get("grant_mana", ()) + ((scope, cols),)
            return None
        if line in ("When this land enters, choose a land card name.", "When ~ enters, choose a land card name.") or \
                line.startswith("Activated abilities of sources with the chosen name can't be activated") or \
                line == 'Lands with the chosen name have "{T}: Add {C}."':
            extra["chosen_land_lock"] = True
            return None
        if line == "∞ — At the beginning of your end step, exile up to one other target nonland permanent you control, "\
                   "then return that card to the battlefield under its owner's control.":
            triggers.append(Trigger("end_step", [Effect("blink_own", cond="harnessed")]))
            return None
        m = re.fullmatch(r"Creatures you control with (flying|trample|menace|first strike|lifelink|deathtouch) get "
                         r"\+(\d+)/\+(\d+)\.", line)
        if m:
            extra["anthem_kw"] = extra.get("anthem_kw", ()) + ((m[1], int(m[2]), int(m[3])),)
            return None
        m = re.fullmatch(r"Creature tokens you control get \+(\d+)/\+(\d+)\.", line)
        if m:
            extra["anthem_sub"] = extra.get("anthem_sub", ()) + (("Token", int(m[1]), int(m[2]), False),)
            return None
        m = re.fullmatch(r"(Other )?(Merfolk|[A-Z][a-z]+?)s? you control get \+(\d+)/\+(\d+)\.", line)
        if m and m[2] != "Creature":
            extra["anthem_sub"] = extra.get("anthem_sub", ()) + ((m[2], int(m[3]), int(m[4]), bool(m[1])),)
            return None
        m = re.fullmatch(r"(Other )?([A-Z][a-z]+?)s you control have (menace|trample|flying|vigilance|haste|lifelink|"
                         r"first strike|double strike|deathtouch|reach|indestructible)\.", line)
        if m and m[2] != "Creature":
            extra["keyword_sub"] = extra.get("keyword_sub", ()) + ((m[2], m[3], bool(m[1])),)
            return None
        m = re.fullmatch(r"~ costs \{(\d+)\} less to cast if you control an? ([A-Z]\w+)\.", line)
        if m:
            extra["discount_if"] = extra.get("discount_if", ()) + ((m[2], int(m[1])),)
            return None
        m = re.fullmatch(r"(Other )?(?!Enchanted)([A-Z][\w-]+) creatures you control get \+(\d+)/\+(\d+)\.", line)
        if m:
            extra["anthem_sub"] = extra.get("anthem_sub", ()) + ((m[2], int(m[3]), int(m[4]), bool(m[1])),)
            return None
        m = re.fullmatch(r"Creatures you control with \+1/\+1 counters on them have (trample|flying|vigilance|haste|lifelink|"
                         r"first strike|deathtouch|menace|reach|indestructible)\.", line)
        if m:
            extra["counter_team_keywords"] = extra.get("counter_team_keywords", frozenset()) | {m[1]}
            return None
        m = re.fullmatch(r"The second spell you cast each turn costs \{(\d+)\} less to cast\.", line)
        if m:
            extra["second_spell_discount"] = int(m[1])
            return None
        m = re.fullmatch(r"As long as you control seven or more lands, ~ gets \+(\d+)/\+(\d+)\.", line)
        if m:
            extra["pt_if"] = extra.get("pt_if", ()) + (("lands>=7", int(m[1]), int(m[2])),)
            return None
        m = re.fullmatch(r"(?:(?:Delirium|Vivid|Flurry) — )?~ costs \{(\d+)\} less to cast if (.+)\.", line)
        key = discounts.parse_condition(m[2]) if m else None
        if key:
            extra["cond_discount"] = extra.get("cond_discount", ()) + ((key, int(m[1])),)
            return None
        m = re.fullmatch(r"(?:(?:Delirium|Vivid|Flurry) — )?~ costs \{(\d+)\} less to cast for each (.+)\.", line)
        key = discounts.parse_per(m[2]) if m else None
        if key:
            extra["per_discount"] = extra.get("per_discount", ()) + ((key, int(m[1])),)
            return None
        m = re.fullmatch(r"~ costs \{(\d+)\} less to cast if it targets a tapped creature\.", line)
        if m:
            extra["tapped_discount"] = int(m[1])
            return None
        m = re.fullmatch(r"As an additional cost to cast ~, behold an? (\w+) or pay \{(\d+)\}\.", line)
        if m:
            extra["behold_or_pay"] = (m[1], int(m[2]))
            return None
        m = re.fullmatch(r"As an additional cost to cast ~, discard a card(?: or pay \{(\d+)\})?\.", line)
        if m:
            extra["extra_discard"] = 1
            extra["discard_or_pay"] = int(m[1] or 0)
            return None
        if line == "Untap ~ during each other player's untap step.":
            extra["untap_each_untap"] = True
            return None
        m = re.fullmatch(r"Enchanted creatures you control get \+(\d+)/\+(\d+)\.", line)
        if m:
            extra["anthem_enchanted"] = (int(m[1]), int(m[2]))
            return None
        if line in ("~ enters tapped. As it enters, choose a color.", "As ~ enters, choose a color."):
            extra["choose_type"] = "basic_land"
            produces |= set(COLORS)
            if line.startswith("~ enters"):
                enters_tapped = True
            return None
        m = re.fullmatch(r"Activated abilities of artifact tokens you control cost \{(\d+)\} less to activate\.", line)
        if m:
            extra["token_ability_discount"] = int(m[1])
            return None
        if line == "Your opponents can't cast spells during your turn.":
            extra["opp_no_cast"] = True
            return None
        m = re.fullmatch(r"During your turn, ~ has (\w+(?: \w+)?)\.", line)
        if m and m[1].lower() in KEYWORDS:
            extra["cond_keywords"] = extra.get("cond_keywords", ()) + ((m[1].lower(), "your_turn"),)
            return None
        m = re.fullmatch(r"(?:Descend \d+ — |Threshold — )?~ (?:gets \+(\d+)/\+(\d+) and has ([a-z ]+?)|has ([a-z ]+?)|"
                         r"(can't be blocked)) as long as there are (\w+) or more (permanent )?cards in your graveyard\.",
                         line)
        if m and m[6].lower() in NUMBERS:
            kw = "unblockable" if m[5] else (m[3] or m[4])
            if kw in KEYWORDS or kw == "unblockable":
                cond = ("gy_perm>=" if m[7] else "gy>=") + str(_num(m[6]))
                if m[1]:
                    extra["pt_if"] = extra.get("pt_if", ()) + ((cond, int(m[1]), int(m[2])),)
                extra["cond_keywords"] = extra.get("cond_keywords", ()) + ((kw, cond),)
                return None
        m = re.fullmatch(r"(?:Descend \d+ — |Threshold — )?~ gets \+(\d+)/\+(\d+) as long as there are (four|seven) or more (permanent )?cards in your "
                         r"graveyard\.", line)
        if m:
            cond = ("gy_perm>=" if m[4] else "gy>=") + str(_num(m[3]))
            extra["pt_if"] = extra.get("pt_if", ()) + ((cond, int(m[1]), int(m[2])),)
            return None
        m = re.fullmatch(r"(?:Metalcraft — )?~ gets \+(\d+)/\+(\d+)(?: and has (flying|first strike|trample|haste|lifelink|"
                         r"vigilance|menace|deathtouch))? as long as (you control three or more artifacts|it's your turn|"
                         r"it's attacking)\.", line)
        if m:
            cond = {"you control three or more artifacts": "artifacts>=3", "it's your turn": "your_turn",
                    "it's attacking": "attacking"}[m[4]]
            extra["pt_if"] = extra.get("pt_if", ()) + ((cond, int(m[1]), int(m[2])),)
            if m[3]:
                extra["cond_keywords"] = extra.get("cond_keywords", ()) + ((m[3], cond),)
            return None
        m = re.fullmatch(r"All ([A-Z]\w+) creatures get \+(\d+)/\+(\d+)\.", line)
        if m:
            extra["anthem_all"] = (m[1], int(m[2]), int(m[3]))      # every player's creatures of that type
            return None
        m = re.fullmatch(r"~ can't be blocked except by (two|three) or more creatures\.", line)
        if m:
            extra["min_blockers"] = _num(m[1])
            return None
        m = re.fullmatch(r"Delirium — ~ gets \+(\d+)/\+(\d+) as long as there are four or more card types among cards "
                         r"in your graveyard\.", line)
        if m:
            extra["pt_if"] = extra.get("pt_if", ()) + (("delirium", int(m[1]), int(m[2])),)
            return None
        if line in ("Partner", "Choose a Background", "Friends forever", "Assist", "Doctor's companion"):
            return None          # deck-building or teammate rules: nothing to do in a two-player game
        if line == "Umbra armor" or line == "Totem armor":
            extra["umbra_armor"] = True
            return None
        m = re.fullmatch(r"~'s power and toughness are each equal to the number of (cards in your hand|cards in your "
                         r"graveyard|creatures you control|lands you control|artifacts you control)\.", line)
        if m:
            extra["pt_cda"] = m[1]
            return None
        if line == "All creatures able to block ~ do so.":
            extra["lure"] = True
            return None
        m = re.fullmatch(r"~ can't be blocked by more than (one|two) creatures?\.", line)
        if m:
            extra["max_blockers"] = _num(m[1])
            return None
        m = re.fullmatch(r"During your turn, ~ gets \+(\d+)/\+(\d+)\.", line)
        if m:
            extra["pt_if"] = extra.get("pt_if", ()) + (("your_turn", int(m[1]), int(m[2])),)
            return None
        m = re.fullmatch(r"\{T\}, Pay 1 life: Add (\{[WUBRG]\}) or (\{[WUBRG]\})\.", line)
        if m:
            produces |= {m[1][1], m[2][1]}
            approximations.append("the 1 life for its mana is not paid")
            return None
        m = re.fullmatch(r"When you control no (Islands|Swamps|Forests|Mountains|Plains|lands), sacrifice ~\.", line)
        if m:                                    # a state trigger: sacrificed while you control none
            extra["needs_land"] = {"lands": "Land", "Plains": "Plains"}.get(m[1], m[1][:-1])
            return None
        line = re.sub(r"^Raid — (?=~ enters with)", "", line)
        m = re.fullmatch(r"~ enters with a \+1/\+1 counter on it if (an opponent lost life|a creature died|you attacked) "
                         r"this turn\.", line)
        if m:
            extra["etb_counters_if"] = ({"an opponent lost life": "opp_lost_life", "a creature died": "creature_died",
                                         "you attacked": "attacked"}[m[1]], 1)
            return None
        m = re.fullmatch(r"Creatures you control get \+(\d+)/\+(\d+)\.", line)
        if m:
            extra["anthem"] = (int(m[1]), int(m[2]))
            return None
        m = re.fullmatch(r"Firebending (\d+|X)(?:, where X is (~'s power|the number of creatures you control))?\.?", line)
        if m:
            what = "" if m[1] != "X" else ("power" if "power" in m[2] else "creatures")
            triggers.append(Trigger("attacks", [Effect("firebend", 0 if what else int(m[1]), data={"x": what})]))
            return None
        if line == "Increment":
            triggers.append(Trigger("cast_spell", [Effect("increment")]))
            return None
        m = re.fullmatch(r"Mobilize (\d+|X)(?:, where X is the number of creature cards in your graveyard)?", line)
        if m:
            sac = Trigger("end_step", [Effect("copy_sac", target="self")])
            eff = Effect("token", 1 if m[1] == "X" else int(m[1]), data={
                "name": "Warrior", "power": 1, "toughness": 1, "keywords": frozenset(), "attacking": True,
                "triggers": [sac], "artifact": False, "pt_per": ""})
            if m[1] == "X":
                eff.data["per"] = {"what": "creature", "zone": "graveyard"}
            triggers.append(Trigger("attacks", [eff]))
            return None
        m = re.fullmatch(r"(Disguise|Morph|Megamorph) (\{[^ ]+\})", line)
        if m:
            alt_costs.append(AltCost(m[1].lower(), parse_mana_cost(m[2])))
            return None
        return line
    finally:
        st.enters_tapped = enters_tapped
        st.produces = produces


def _face_keyword_ability_lines(st, line):
    """Keyword abilities with costs, loyalty abilities, saga chapters. Returns the line to keep parsing, or None once it is handled."""
    activated = st.activated
    alt_costs = st.alt_costs
    chapters = st.chapters
    extra = st.extra
    loyalty_abilities = st.loyalty_abilities
    types = st.types
    unsupported = st.unsupported
    try:
        if line == "Convoke":
            extra["convoke"] = True
            return None
        if line in ("Improvise", "Delve"):
            extra[line.lower()] = True
            return None
        if line == "~ enters prepared.":
            extra["prepared"] = True
            return None
        if line == "Changeling":
            extra["changeling"] = True
            return None
        m = re.fullmatch(r"(Cycling|Basic landcycling|Landcycling|(?:Plains|Island|Swamp|Mountain|Forest)cycling) "
                         r"(\{[^ ]+\})", line)
        if m:
            kind = m[1].lower()
            extra["cycling"] = {"cost": parse_mana_cost(m[2]), "land": "" if kind == "cycling" else
                                "basic" if kind == "basic landcycling" else "any" if kind == "landcycling" else
                                m[1][:-7]}
            return None
        m = re.fullmatch(r"Saddle (\d+)", line)
        if m:
            extra["saddle"] = int(m[1])
            return None
        m = re.fullmatch(r"Crew (\d+)", line)
        if m:
            extra["crew"] = int(m[1])
            return None
        m = re.fullmatch(r"(Flashback|Foretell|Spectacle) (\{[^ ]+\})", line)
        if m:
            kind = m[1].lower()
            alt_costs.append(AltCost(kind, parse_mana_cost(m[2]),
                                     zone={"flashback": "graveyard", "foretell": "foretold"}.get(kind, "hand")))
            return None
        m = re.fullmatch(r"Ninjutsu (\{[^ ]+\})", line)
        if m:
            alt_costs.append(AltCost("ninjutsu", parse_mana_cost(m[1]), zone="hand"))
            return None
        m = re.fullmatch(r"During your turn, as long as ~ has one or more loyalty counters on (?:him|her|it), "
                         r"(?:he|she|it)'s an? (\d+)/(\d+) ([A-Z][a-z]+) creature(?: and has (hexproof))?\.", line)
        if m:
            extra["turn_creature"] = (int(m[1]), int(m[2]), (m[3],), (m[4],) if m[4] else ())
            return None
        m = re.fullmatch(r"(Mayhem|Sneak) (\{[^ ]+\})", line)
        if m:
            alt_costs.append(AltCost(m[1].lower(), parse_mana_cost(m[2]), zone="graveyard" if m[1] == "Mayhem" else "hand"))
            return None
        m = re.fullmatch(r"Blitz (\{[^ ]+\})", line)
        if m:
            alt_costs.append(AltCost("blitz", parse_mana_cost(m[1]), zone="hand"))
            return None
        m = re.fullmatch(r"Blitz—(\{[^,]+\}), Pay (\d+) life\.", line)
        if m:
            alt_costs.append(AltCost("blitz", parse_mana_cost(m[1]), zone="hand", life=int(m[2])))
            return None
        if re.fullmatch(r"You may cast ~ from your graveyard using its blitz ability\.", line):
            for a in alt_costs:
                if a.kind == "blitz":
                    a.zone = "hand+graveyard"
            return None
        m = re.fullmatch(r"You may pay (\{[^ ]+\}) rather than pay ~'s mana cost\.", line)
        if m:
            alt_costs.append(AltCost("alt", parse_mana_cost(m[1])))
            return None
        m = re.fullmatch(r"If the \{[^ ]+\} cost was paid, an opponent draws a card\.", line)
        if m and alt_costs and alt_costs[-1].kind == "alt":
            alt_costs[-1].extra.append(Effect("draw", 1, target="each_opponent"))
            return None
        m = re.fullmatch(r"Channel — (\{[^,]+\}), Discard ~: (.+?)(?: This ability costs \{1\} less to activate "
                         r"for each legendary creature you control\.)?", line)
        if m:
            effs, bad = _parse_effects(m[2])
            if effs and not bad:
                alt_costs.append(AltCost("channel", parse_mana_cost(m[1]), effects=effs))
                return None
        if re.fullmatch(r"As long as ~ entered this turn, you may activate (?:her|his|its) loyalty abilities any "
                        r"time you could cast an instant\.", line):
            extra["pw_instant_on_entry"] = True
            return None
        m = re.fullmatch(r"\[([+−-]?\d+)\]: ?(.+)", line) or \
            ("Planeswalker" in types and re.fullmatch(r"([+−-]?\d+): ?(.+)", line))
        if m:
            effs, bad = _parse_effects(m[2])
            if effs:
                loyalty_abilities.append((int(m[1].replace("−", "-")), effs))
            unsupported += [f"[{m[1]}]: {b}" for b in bad]
            return None
        m = re.fullmatch(r"((?:I|II|III|IV|V)(?:, (?:I|II|III|IV|V))*) — (.+)", line)
        if m:
            effs, bad = _parse_effects(m[2])
            for numeral in m[1].split(", "):
                idx = ["I", "II", "III", "IV", "V"].index(numeral)
                while len(chapters) <= idx:
                    chapters.append([])
                chapters[idx] += effs
            unsupported += [f"{m[1]} — {b}" for b in bad]
            return None
        m = re.fullmatch(r"(\{[^:]+\}): Until end of turn, ~ becomes an? (\d+)/(\d+) [\w ]*? creature"
                         r"(?: with (ward \{\d+\}|[\w ,]+|\"[^\"]+\"))?\.? It's still a land\.", line)
        if m:
            act = Activated("animate", parse_mana_cost(m[1]), int(m[2]), int(m[3]))
            ability = m[4] or ""
            if ability.startswith("ward"):
                act.ward = int(re.search(r"\d+", ability)[0])
            elif ability.startswith('"'):
                inner = ability.strip('"')
                trig = _parse_trigger(inner)
                if trig:
                    act.triggers = trig[0]
            elif ability:
                act.keywords = frozenset(k.strip().lower() for k in ability.split(",") if k.strip().lower() in KEYWORDS)
            activated.append(act)
            return None
        return line
    finally:
        st.unsupported = unsupported


def _face_ability_lines(st, line):
    """Manlands, auras, copies, activated and triggered abilities, and spell text. Returns the line to keep parsing, or None once it is handled."""
    activated = st.activated
    approximations = st.approximations
    etb = st.etb
    extra = st.extra
    mode_sink = st.mode_sink
    modes = st.modes
    spell = st.spell
    station_min = st.station_min
    triggers = st.triggers
    type_line = st.type_line
    types = st.types
    unsupported = st.unsupported
    try:
        m = re.fullmatch(r"(\{[^:]+\}): ~ becomes an? (\d+)/(\d+) creature with (\w+) and all creature types\. "
                         r"It's still a land\.", line)
        if m:   # permanently (Soulstone Sanctuary)
            activated.append(Activated("animate", parse_mana_cost(m[1]), int(m[2]), int(m[3]),
                                       keywords=frozenset({m[4].lower()}) & KEYWORDS, text="permanent"))
            return None
        m = re.fullmatch(r"(\{[^:]+\}): ~ becomes an? (\d+)/(\d+) [\w ]*? creature(?: with ([\w ,]+))? until end of "
                         r"turn\. It's still a land\.", line)
        if m:
            kws = frozenset(k.strip().lower() for k in re.split(r",| and ", m[4] or "") if k.strip().lower() in KEYWORDS)
            activated.append(Activated("animate", parse_mana_cost(m[1]), int(m[2]), int(m[3]), keywords=kws))
            return None
        m = re.fullmatch(r"(\{[^:]+\}): Put two \+1/\+1 counters on ~\. Then you may have it become a 0/0 \w+ "
                         r"creature until end of turn\. It's still a land\.", line)
        if m:
            activated.append(Activated("barrens", parse_mana_cost(m[1])))
            return None
        if re.fullmatch(r"\{T\}, Sacrifice ~: Target creature gets -X/-X until end of turn, where X is twice the "
                        r"number of Blood tokens you control\. Activate only as a sorcery\.", line):
            activated.append(Activated("sac_debuff", {"generic": 0}))
            return None
        extra["_subtypes"] = type_line
        if _auras.parse_line(line, extra, types):
            approximations += extra.pop("_approx", [])
            return None
        clone = _copies.parse_line(line)
        if clone is not None:
            extra.update(clone)
            return None
        mp = re.fullmatch(r"(Power-up|Exhaust) — (.+)", line)
        act = _parse_ability(mp[2] if mp else line, approximations)
        if act is not None and mp:
            act.once_game, act.power_up, act.text = True, mp[1] == "Power-up", line
        if act is not None:
            act.min_charge = station_min
            activated.append(act)
            if isinstance(act.modes, modal.Modes):
                mode_sink = act.modes
            return None
        opt_cond = ""
        mo = re.fullmatch(r"(When ~ enters), if (it was bargained|the gift was promised), (.+)", line)
        if mo and (extra.get("bargain") or extra.get("gift")):
            line = f"{mo[1]}, {mo[3]}"
            opt_cond = "bargained" if "bargained" in mo[2] else "gifted"
        trig = _parse_trigger(line)
        if trig is not None:
            new, bad, choose_modes = trig
            if opt_cond:
                for t in new:
                    for e in t.effects:
                        e.cond = e.cond or opt_cond
            triggers += new
            if choose_modes is not None:
                mode_sink = choose_modes
            for t in new:
                if t.event == "etb":
                    etb += t.effects
            unsupported += bad
            return None
        if not types.isdisjoint({"Instant", "Sorcery"}):
            head = modal.parse_header(line)
            if head is not None and not modes:
                modes = modal.Modes(spec=head[0])
                extra["modes_choose"] = min(head[0].most, 9)
                approximations += head[1]
                mode_sink = modes
                return None
            effs, bad = _parse_effects(line, opts=bool(extra.get("bargain") or extra.get("gift")))
            spell += effs
            unsupported += bad
            return None
        unsupported.append(line)
        return line
    finally:
        st.approximations = approximations
        st.etb = etb
        st.mode_sink = mode_sink
        st.modes = modes
        st.spell = spell
        st.triggers = triggers
        st.unsupported = unsupported


_FACE_LINE_PARSERS = (_face_special_lines, _face_mode_and_ward_lines, _face_land_and_mana_lines, _face_cost_and_static_lines, _face_keyword_ability_lines, _face_ability_lines)
