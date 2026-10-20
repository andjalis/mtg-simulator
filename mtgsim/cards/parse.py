"""Parsing a card: Scryfall JSON to CardDef, faces, effects, activated and triggered abilities."""
from __future__ import annotations

import dataclasses
import re

from .. import milling, modal, returns
from .. import auras as _auras
from .model import (
    Activated, AltCost, BASIC_MANA, CardDef, Effect, NO_MATCH, Trigger, _num, add_mana, parse_mana_cost,
)
from .clauses import _SUBS, _TRIGGERS, _if_cond, _opt_rider, _xq
from .patterns import _EFFECT_PATTERNS


# "You may <effect>" is always taken, so only for effects that cost the player nothing.
_MAY_DECLINED = {"sacrifice", "sacrifice_self", "discard", "discard_choice", "lose_life", "mill", "pay_gate",
                 "damage", "drain", "destroy", "exile", "wrath", "bounce"}


def _parse_effects(text: str, opts: bool = False):
    """Parse a run of sentences into effects. Returns (effects, unmatched_sentences)."""
    effects, unmatched = [], []
    for rx, rep in _SUBS:
        text = rx.sub(rep, text)
    gated = False
    for sentence in re.split(r"(?<=\.)\s+", text.strip()):
        s = sentence.strip().rstrip(".").strip()
        if not s:
            continue
        if re.fullmatch(r"(?:it|they|those creatures) can't be regenerated", s, re.I) and effects and \
                effects[-1].kind in ("destroy", "wrath", "wrath_pw"):
            effects[-1] = dataclasses.replace(effects[-1], data=dict(effects[-1].data, no_regen=True))
            continue
        if re.fullmatch(r"(?:a creature|creatures) dealt damage this way can't be regenerated this turn", s, re.I) \
                and effects and effects[-1].kind == "damage":
            effects[-1] = dataclasses.replace(effects[-1], data=dict(effects[-1].data, no_regen=True))
            continue
        end_rider = re.fullmatch(r"(sacrifice|exile) (?:it|that token|the token|them|those tokens|the tokens) at the "
                                 r"beginning of (?:the|your) next end step", s, re.I)
        if end_rider and effects and effects[-1].kind == "token":
            effects[-1] = dataclasses.replace(effects[-1], data=dict(effects[-1].data, end=end_rider[1].lower()))
            continue
        if re.fullmatch(r'(?:it|they) ha(?:s|ve) "sacrifice (?:~|this creature): add \{c\}\.?"', s, re.I) and effects \
                and effects[-1].kind == "token":
            effects[-1] = dataclasses.replace(effects[-1], data=dict(effects[-1].data, spawn_mana=True))
            continue
        conditional = milling.parse_conditional(s, effects)
        if conditional is not None:
            effects += conditional
            continue
        rider = returns.parse_rider(s)
        if rider is not None:
            effects += rider
            continue
        mp = re.fullmatch(r"you may pay ((?:\{[WUBRGC0-9]+\})+)", s, re.I)
        if mp:
            effects.append(Effect("pay_gate", data={"cost": parse_mana_cost(mp[1])}))
            gated = True
            continue
        mg = re.fullmatch(r"you may (?:(sacrifice (?:another |an? )(?:artifact, enchantment, or token|[a-z]+(?: or [a-z]+)?))"
                          r"|(discard a card)|(forage)|blight (\d+))", s, re.I)
        if mg:
            if mg[1]:
                what = mg[1].lower().split(" ", 1)[1]
                other = what.startswith("another ")
                kinds = re.sub(r"^(?:another|an?) ", "", what).replace(", or ", " or ").replace(", ", " or ")
                gate = ("sac", ("other " if other else "") + kinds)
            elif mg[2]:
                gate = ("discard", "")
            elif mg[3]:
                gate = ("forage", "")
            else:
                gate = ("blight", mg[4])
            effects.append(Effect("pay_gate", data={"gate": gate}))
            gated = True
            continue
        mm = re.fullmatch(r"you may (.+)", s, re.I)
        if mm:
            new, bad = _parse_effects(mm[1][0].upper() + mm[1][1:] + ".")
            if new and not bad and not any(e.kind in _MAY_DECLINED for e in new):
                effects += [Effect("pay_gate", data={"gate": ("may", "")})] + new   # always taken
                gated = True
                continue
        mx = re.fullmatch(r"(.+?),? where X is (.+)", s, re.I)
        if mx and re.search(r"\bX\b", mx[1]) and _xq(mx[2]):
            spec = _xq(mx[2])
            new, bad = [], True
            for one in ("1", "one", "a"):
                body = re.sub(r"\bX\b", one, mx[1])
                if one != "1":
                    body = re.sub(r"\b(creature |artifact )?tokens\b", r"\1token", body)
                new, bad = _parse_effects(body + ".")
                if new and not bad:
                    break
            if new and not bad:
                for e in new:
                    e.data["xq"] = spec
                    e.data["xq_size"] = bool(re.search(r"\bX/X\b", mx[1]))
                effects += new
                continue
        if opts:
            new = _opt_rider(s, effects)
            if new is not None:
                effects += new
                continue
        mi = re.fullmatch(r"if (.+?), (.+)", s, re.I)
        if mi:
            cond = _if_cond(mi[1])
            if cond:
                for body in (mi[2], re.sub(r"^you ", "", mi[2])):
                    new, bad = _parse_effects(body[0].upper() + body[1:] + ".")
                    if new and not bad:
                        effects += [dataclasses.replace(e, cond=e.cond or cond) for e in new]
                        break
                else:
                    unmatched.append(sentence.strip())
                continue
        first = len(effects)
        paid = False
        if gated:
            g = re.fullmatch(r"(?:if you do|when you do), (.+)", s, re.I)
            if g:
                s, paid = g[1], True
        for pat, build in _EFFECT_PATTERNS:
            m = re.fullmatch(pat, s, flags=re.IGNORECASE)
            if m is None and s.lower().startswith("then "):
                m = re.fullmatch(pat, s[5:], flags=re.IGNORECASE)
            if m:
                eff = build(m)
                if eff is NO_MATCH:
                    continue
                if isinstance(eff, list):
                    effects += eff
                elif eff is not None:
                    effects.append(eff)
                break
        else:
            parts = _split_compound(s)
            if parts:
                effects += parts
            else:
                unmatched.append(sentence.strip())
        if paid:
            for eff in effects[first:]:
                eff.cond = eff.cond or "paid"
        for eff in effects[first:]:
            if eff.data.get("unparsed_token_keywords"):
                unmatched.append("Unsupported token keywords: " + ", ".join(eff.data["unparsed_token_keywords"]))
    return effects, unmatched


def _split_compound(s: str):
    """Effects for "A, then B" / "A and B" when every part matches a template, else None."""
    for sep in (r",? then ", r" and "):
        pieces = re.split(sep, s, maxsplit=1, flags=re.I)
        if len(pieces) != 2:
            continue
        out = []
        for piece in pieces:
            effs, bad = _parse_effects(piece[0].upper() + piece[1:] + ".")
            if bad or not effs:
                break
            out += effs
        else:
            return out
    return None


def _apply_speed_gate(gate, triggers, activated):
    """Gate what a "Max speed — ..." line just added: its triggers' effects and its activated abilities."""
    for t in triggers[gate[0]:]:
        for eff in t.effects:
            eff.cond = eff.cond or "max_speed"
    for a in activated[gate[1]:]:
        a.needs_max_speed = True


def _face_types(type_line: str) -> frozenset:
    main_types = type_line.split("—")[0]
    return frozenset("Kindred" if t == "Tribal" else t for t in
                     ("Land", "Creature", "Instant", "Sorcery", "Artifact", "Enchantment", "Planeswalker",
                      "Battle", "Kindred", "Tribal") if t in main_types)


def card_from_scryfall(data: dict) -> CardDef:
    faces = data.get("card_faces")
    if faces and not data.get("oracle_text"):
        card = _parse_face({**data, **faces[0]})
        if len(faces) > 1:
            back = faces[1]
            back_types = back.get("type_line", "")
            if "Adventure" in back_types:
                card.adventure = _parse_face(back)
            elif "Land" in back_types and not card.is_land:
                card.land_face = _parse_face(back)   # modal double-faced: may be played as this land
            elif re.search(r"Daybound|Nightbound", card.oracle):
                pass  # day/night isn't tracked; the day side stays
            else:
                card.back = _parse_face(back)
        return card
    return _parse_face(data)


def _cost_line(m):
    return parse_mana_cost(m)


def _parse_face(data: dict) -> CardDef:
    name = data["name"].split(" // ")[0]
    type_line = data.get("type_line", "").split(" // ")[0]
    types = _face_types(type_line)
    cost = parse_mana_cost(data.get("mana_cost", "").split(" // ")[0])

    def stat(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0 if v is not None else None

    oracle = data.get("oracle_text", "") or ""
    text = re.sub(r"\([^)]*\)", "", oracle)
    text = text.replace(name, "~")
    if "," in name and "Legendary" in type_line:
        text = re.sub(rf"\b{re.escape(name.split(',')[0])}\b", "~", text)  # "Iymrith" for "Iymrith, Desert Doom"
    elif "Legendary" in type_line and " " in name and " the " not in name and len(name.split()[0]) >= 4 and \
            name.split()[0] not in ("The", "Lord", "Lady", "King", "Queen", "Sir") and \
            re.search(rf"\b{re.escape(name.split()[0])}\b", text):
        text = re.sub(rf"\b{re.escape(name.split()[0])}\b", "~", text)  # "Ajani" for "Ajani Resolute"
    elif " the " in name and "Legendary" in type_line:
        text = re.sub(rf"\b{re.escape(name.split(' the ')[0])}\b", "~", text)  # "Smaug the Magnificent"
    text = re.sub(r"\bthis (creature|land|spell|enchantment|artifact|permanent|token|vehicle|saga|aura|equipment|class)\b", "~",
                  text, flags=re.I)
    text = re.sub(r"\b(protection from (?:white|blue|black|red|green)) and from (white|blue|black|red|green)\b",
                  r"\1 and protection from \2", text)
    text = re.sub(r"(becomes the target of a spell or ability), sacrifice it\.", r"\1, sacrifice ~.", text)
    text = re.sub(r", where X is the amount of mana spent to cast ~\.", ".", text).replace(
        "the top X cards", f"the top {int(data.get('cmc', 0) or 0)} cards")

    text = re.sub(r"(?m)^((?:Exhaust — )?)Waterbend (\{\d+\}(?:, \{T\})?:)", r"\1\2", text)    # waterbend {N} pays like {N} here
    text = re.sub(r"(?m)^Ward—Waterbend (\{\d+\})", r"Ward \1", text)
    text = re.sub(r"(?m)^([A-Za-z ,]*[Ff]irebending \d+[A-Za-z ,]*)$", lambda m: "\n".join(x[0].upper() + x[1:] for x in m[1].split(", ")), text)
    keywords, produces, etb, spell, unsupported, approximations = set(), set(), [], [], [], []
    level_marks: list = []      # Class: (level, number of triggers parsed before that level's lines)
    triggers: list[Trigger] = []
    extra: dict = {"snow": "Snow" in type_line, "basic": "Basic" in type_line, "legendary": "Legendary" in type_line,
                   "color_override": frozenset(data["colors"]) if "colors" in data else None}
    modes: list = []
    chapters: list = []
    loyalty_abilities: list = []
    alt_costs: list = []
    activated: list = []
    enters_tapped = False
    mode_sink = None     # where bullet lines go: modes of the spell or of the last trigger
    for sub in type_line.split("—")[-1].split():
        if sub in BASIC_MANA and "Land" in types:
            produces.add(BASIC_MANA[sub])
    raw_cost = data.get("mana_cost", "").split(" // ")[0]
    extra["hybrid"] = tuple(a + b for a, b in re.findall(r"\{([WUBRG])/([WUBRG])\}", raw_cost))
    if data.get("loyalty"):
        extra["loyalty"] = stat(data["loyalty"]) or 0

    kicked: list = []
    station_min = 0
    gate = None            # set while parsing a "Max speed — ..." line: what the line added is gated on speed 4
    st = _FaceState(activated=activated, alt_costs=alt_costs, approximations=approximations, chapters=chapters,
                    enters_tapped=enters_tapped, etb=etb, extra=extra, gate=gate, keywords=keywords, kicked=kicked,
                    level_marks=level_marks, loyalty_abilities=loyalty_abilities, mode_sink=mode_sink, modes=modes,
                    produces=produces, spell=spell, station_min=station_min, triggers=triggers,
                    type_line=type_line, types=types, unsupported=unsupported)
    for line in (l.strip() for l in text.split("\n")):
        for handle in _FACE_LINE_PARSERS:
            line = handle(st, line)
            if line is None:
                break
    approximations = st.approximations
    enters_tapped = st.enters_tapped
    etb = st.etb
    gate = st.gate
    kicked = st.kicked
    mode_sink = st.mode_sink
    modes = st.modes
    produces = st.produces
    spell = st.spell
    station_min = st.station_min
    triggers = st.triggers
    unsupported = st.unsupported
    if "X is the amount of mana spent to cast" in oracle:
        for e in spell:
            if e.kind == "dig":
                e.data["x_mana"] = True
    if "kicker" in extra:
        kicked_effects = [dataclasses.replace(e) for e in spell]
        for k in kicked:
            m = re.fullmatch(r"it deals (\d+) damage instead\.", k)
            dmg = [e for e in kicked_effects if e.kind == "damage"]
            if m and dmg:
                dmg[0].amount = int(m[1])
                continue
            m = re.fullmatch(r"put (\w+) of those cards into your hand instead\.", k)
            dig = [e for e in kicked_effects if e.kind == "dig"]
            if m and dig:
                kicked_effects[kicked_effects.index(dig[0])] = dataclasses.replace(dig[0], amount2=_num(m[1]))
                continue
            effs, bad = _parse_effects(k)
            kicked_effects += effs
            unsupported += [f"if kicked: {b}" for b in bad]
        alt_costs.append(AltCost("kicker", add_mana(cost, extra.pop("kicker")), effects=kicked_effects))
    elif kicked:
        unsupported += [f"if kicked: {k}" for k in kicked]
    if gate is not None:
        _apply_speed_gate(gate, triggers, activated)
    for i, (n, start) in enumerate(level_marks):
        end = level_marks[i + 1][1] if i + 1 < len(level_marks) else len(triggers)
        for t in triggers[start:end]:
            t.min_level = n
    extra.pop("is_spree", None)
    extra.pop("_subtypes", None)
    _auras.finish(extra)
    extra["gy_triggers"] = [t for t in triggers if any(e.kind == "return_self_gy" for e in t.effects)]
    triggers = [t for t in triggers if t not in extra["gy_triggers"]]
    extra["spent_colors"] = frozenset(t.effects[0].cond[6:] for t in triggers
                                      if t.effects and t.effects[0].cond.startswith("spent:"))
    if "prowess" in keywords:
        triggers.append(Trigger("cast_noncreature", [Effect("pump", 1, 1, target="self")]))
    # Triggers with "choose up to one" get their bullet modes; drop ones that ended up empty.
    triggers = [t for t in triggers if t.effects or t.modes]

    return CardDef(
        name=name, mana_cost=cost, cmc=int(data.get("cmc", 0) or 0), types=types,
        subtypes=frozenset(type_line.split("—")[1].split()) if "—" in type_line else frozenset(),
        power=stat(data.get("power")), toughness=stat(data.get("toughness")),
        keywords=frozenset(keywords), produces=frozenset(produces), enters_tapped=enters_tapped,
        spell_effects=spell, etb_effects=etb, unsupported=unsupported, approximations=approximations, oracle=oracle,
        triggers=triggers, modes=modes, chapters=chapters, loyalty_abilities=loyalty_abilities,
        alt_costs=alt_costs, activated=activated, **extra,
    )


def _mana_restriction(text: str):
    """What "Spend this mana only ..." allows, or None if the wording isn't one we model."""
    text = text.lower()
    if text == "to cast a creature spell of the chosen type, and that spell can't be countered":
        return "chosen_type"
    if re.fullmatch(r"to cast (?:a creature spell|creature spells)", text):
        return "creature"
    if re.fullmatch(r"to cast (?:an artifact spell|artifact spells)", text):
        return "artifact"
    if re.fullmatch(r"to cast (?:an instant or sorcery spell|instant and sorcery spells)", text):
        return "instant_sorcery"
    m = re.fullmatch(r"to cast an? (\w+) spell(?: or an? (\w+) spell)?", text)
    if m:
        return "subtype:" + "|".join(t.capitalize() for t in m.groups() if t)
    return None


_SACRIFICE_KINDS = {"token", "artifact", "creature", "creature or artifact", "artifact or creature", "treasure",
                    "food", "land", "enchantment", "other creature", "other artifact"}


def _parse_ability_cost(text: str):
    """(mana cost, other costs) for an activated ability's cost, or None if a part isn't modelled."""
    mana, extra = {"generic": 0}, {}
    for part in text.split(", "):
        m = None
        if part == "{T}":
            extra["tap"] = True
        elif re.fullmatch(r"(\{[0-9WUBRGC/P]+\})+", part):        # Phyrexian {B/P} is paid as {B}, as in spell costs
            mana = add_mana(mana, parse_mana_cost(part))
        elif part == "Sacrifice ~":
            extra["sac_self"] = True
        elif part == "Exile ~":
            extra["exile_self"] = True
        elif part == "Discard a card":
            extra["discard"] = 1
        elif (m := re.fullmatch(r"Pay (\d+) life", part)):
            extra["life"] = int(m[1])
        elif (m := re.fullmatch(r"Remove an? ([\w/+-]+) counter from ~", part)):
            extra["remove_counter"] = m[1]
        elif (m := re.fullmatch(r"Sacrifice (?:a|an|another) (.+)", part)) and \
                m[1].lower() in _SACRIFICE_KINDS:
            what = m[1].lower()
            extra["sacrifice"] = ("other " + what if part.startswith("Sacrifice another") else what)
        elif (m := re.fullmatch(r"Sacrifice (two|three|four|five) ([A-Za-z]+?)s", part)) and \
                m[2].lower() in _SACRIFICE_KINDS:
            extra["sacrifice"] = m[2].lower()
            extra["sac_n"] = _num(m[1])
        else:
            return None
    return mana, extra


def _parse_ability(line: str, approximations: list):
    """A general activated ability ("{2}, {T}: Draw a card."), or None."""
    m = re.fullmatch(r"([^:\"•]+?): (.+)", line)
    if not m or not (m[1].startswith("{") or m[1].split()[0] in ("Sacrifice", "Discard", "Pay", "Remove", "Exile")):
        return None
    cost = _parse_ability_cost(m[1])
    if cost is None:
        return None
    body, sorcery, once, approx = m[2], False, False, []
    while True:
        r = re.fullmatch(r"(.+?\.) (Activate only as a sorcery|Activate only once each turn|This ability costs [^.]+ "
                         r"less to activate[^.]*)\.", body)
        if not r:
            break
        body = r[1]
        sorcery |= r[2] == "Activate only as a sorcery"
        once |= r[2] == "Activate only once each turn"
        if r[2].startswith("This ability costs"):
            approx.append(f"cost reduction ignored: {r[2]}.")
    head = modal.parse_header(body)
    if head is not None and not head[1]:
        approximations += approx
        return Activated("ability", cost[0], extra_costs=cost[1], sorcery=sorcery, once=once, text=line,
                         modes=modal.Modes(spec=head[0]))
    effects, bad = _parse_effects(body)
    if bad or not effects:
        return None
    approximations += approx
    return Activated("ability", cost[0], effects=effects, extra_costs=cost[1], sorcery=sorcery, once=once, text=line)


def _parse_trigger(line: str):
    """(triggers, unmatched, modes list to fill or None) for a triggered ability line, else None."""
    once = line.endswith(" This ability triggers only once each turn.")
    if once:
        line = line[:-len(" This ability triggers only once each turn.")]
    once_game = line.endswith(" This ability triggers only once.")
    if once_game:
        line = line[:-len(" This ability triggers only once.")]
    out = _parse_trigger_line(line)
    if out is not None and once:
        for t in out[0]:
            t.once = True
    if out is not None and once_game:
        for t in out[0]:
            t.once_game = True
    return out


def _parse_trigger_line(line: str):
    for pat, events in _TRIGGERS:
        m = re.fullmatch(pat, line)
        if not m:
            continue
        flt = ""
        rest = m[m.lastindex]
        intervening = rest.startswith("if ")
        if events == ("any_cast",):
            flt = f"cmc<={m[1]}"
        if "while saddled" in pat or events[-1] == "becomes_tapped":
            rest = re.sub(r"^it (gets|gains|deals)\b", r"~ \1", re.sub(r"\b(on|untap|to) it\b", r"\1 ~", rest))
        if events == ("expend",) or events == ("class_level",):
            flt = m[1]
        if events == ("gy_leave",):
            flt = f"{m[1] or ''}|{'turn' if m[2] else ''}"
        if events == ("ally_dies",):
            flt = f"{'other' if m[1] == 'another' else 'any'}|{'counter' if m[3] else ''}|{m[2]}"
        if events == ("perm_to_gy",):
            flt = f"{'other' if m[1] == 'another' else 'any'}||{m[2]}"
        if events == ("attacks",) and "while saddled" in pat:
            flt = "saddled"
        if events == ("cast_instant_sorcery",) and "that targets a creature" in pat:
            flt = "targets_creature"
        if events == ("targeted_mine",):
            rest = re.sub(r"^it (gets|gains|deals)\b", r"~ \1", re.sub(r"\b(on|untap|to) it\b", r"\1 ~", rest))
        if events == ("cast_cmc",):
            flt = f"cmc>={m[1]}"
        if events == ("cast_spell",) and "during an opponent's turn" in pat:
            flt = "opp_turn"
        if events == ("cast_spell",) and m.lastindex == 2:
            flt = f"spell:{m[1]}"
        if events == ("sacrifice",):
            flt = m[1]
        if events == ("you_attack",) and m.lastindex == 2:
            flt = f"with:{m[1].rstrip('s')}"
        if events[0] == "other_creature_enters":
            flt = "greater_power"
        if events == ("permanent_enters",):
            desc = m[3] + (f" or {m[5]}" if m[5] else "") + (m[4] or "")
            flt = f"{'self' if m[1] else 'noself'}|{'other' if m[2] == 'another' else 'any'}|{desc}"
        head = modal.parse_header(rest)
        if head is not None and not head[1]:
            modes = modal.Modes(spec=head[0])
            return [Trigger(e, [], flt, modes) for e in events], [], modes
        spent = re.fullmatch(r"if \{([WUBRG])\}\{\1\} was spent to cast it, (.+)", rest, flags=re.S)
        cond = f"spent:{spent[1]}" if spent else ""
        if spent:
            rest = spent[2]
        if events == ("attacks",) and pat == "Whenever ~ attacks while (?!saddled)(.+)":
            rest = "if " + rest
            intervening = True
        gate_if = re.fullmatch(r"if (.+?), (.+)", rest, flags=re.S)
        if gate_if and gate_if[1].lower().startswith(("you control", "there are", "a permanent left", "two or more",
                                                      "three or more", "four or more", "you don't control")):
            gated = _if_cond(gate_if[1])
            if gated:
                cond, rest = gated, gate_if[2]
        cast_if = re.match(r"if you cast (?:it|him|her|them), ", rest)
        if cast_if:
            cond, rest = "cast", rest[cast_if.end():]
        c = re.fullmatch(r"if (you gained life|you gained and lost life|you descended|(?:you've gained|you gained) (\d+) or more life|an opponent "
                         r"lost life) this turn, (.+)", rest, flags=re.S) or \
            re.fullmatch(r"(.+?) if (you gained life|(?:you've gained|you gained) (\d+) or more life) this turn\.", rest, flags=re.S)
        if c:
            phrase, n, rest = (c[1], c[2], c[3]) if not c[1][0].isupper() and c.re.pattern.startswith("if") \
                else (c[2], c[3], c[1] + ".")
            cond = {"you gained life": "gained_life", "you gained and lost life": "gained_and_lost",
                    "an opponent lost life": "opp_lost_life", "you descended": "descended"}.get(phrase, f"gained_life>={n}")
        if events[0] in ("each_upkeep", "opp_upkeep", "each_end_step") and rest.startswith("if that player has no cards in hand, "):
            cond, rest = "phase_player_empty_hand", rest[len("if that player has no cards in hand, "):]
        if cond:
            rest = rest[0].upper() + rest[1:]
        # "... When you do, if it has four or more quest counters on it, EFFECTS" (Earthbender Ascension)
        reflex = re.fullmatch(r"(.+?) When you do, if it has (\w+) or more (\w+) counters on it, (.+)", rest, flags=re.S)
        later: list = []
        if reflex:
            rest = reflex[1]
            later, bad2 = _parse_effects(reflex[4][0].upper() + reflex[4][1:])
            if bad2:
                return [], bad2, None
            later = [dataclasses.replace(e, cond=f"counters:{reflex[3]}>={_num(reflex[2])}") for e in later]
        opus = re.fullmatch(r"(.+?\.) If five or more mana was spent to cast that spell, (.+)", rest, flags=re.S)
        unless = re.fullmatch(r"(.+?\.) Then (.+?) unless five or more mana was spent to cast that spell\.?", rest, flags=re.S)
        if opus:
            instead = opus[2].rstrip(".").endswith(" instead")
            second = re.sub(r" instead$", "", opus[2].rstrip(".")).replace("~ also ", "~ ")
            first, bad = _parse_effects(opus[1])
            more, bad2 = _parse_effects(second[0].upper() + second[1:] + ".")
            bad += bad2
            effs = [dataclasses.replace(e, cond="mana<5") for e in first] if instead else first
            effs += [dataclasses.replace(e, cond="mana>=5") for e in more]
        elif unless:
            first, bad = _parse_effects(unless[1])
            more, bad2 = _parse_effects(unless[2][0].upper() + unless[2][1:] + ".")
            bad += bad2
            effs = first + [dataclasses.replace(e, cond="mana<5") for e in more]
        else:
            effs, bad = _parse_effects(rest)
            if cond:
                effs = [dataclasses.replace(e, cond=cond) for e in effs]
        effs += later
        if events == ("attacks_alone",):
            for e in effs:
                if e.target == "prev":
                    e.target = "trigger_subject"
        if not effs:
            return [], bad or [line], None
        gate = (cond or effs[0].cond) if intervening else ""
        return [Trigger(e, effs, flt, once=events == ("targeted_mine",),
                        intervening_if=gate) for e in events], bad, None
    return None


# deferred: face_lines imports the helpers above
from .face_lines import _FACE_LINE_PARSERS, _FaceState  # noqa: E402
