"""Prototype: translate Forge card scripts into the built-in engine's effect objects.

    python3 -m mtgsim.forge_script --forge ~/forge                 # Standard-wide report
    python3 -m mtgsim.forge_script --forge ~/forge --card "Cut Down" --card "Stock Up"

Forge describes every card's abilities in a structured script: `A:` (spells and activated
abilities), `T:` (triggers), `S:` (static abilities), `R:` (replacements), `K:` (keywords) and
`SVar:` lines that hold the rest of an ability chain (`SubAbility$`, `Execute$`, `Choices$`).
Each step names an API (`Draw`, `DealDamage`, `ChangeZone`, `Token`, `PutCounter` ...) and its
parameters. This module maps the most common APIs, with the parameter values the engine can
represent, to `cards.Effect` / `cards.Trigger`. A step with an unmapped API, or a mapped API with a
parameter outside the known subset, is reported as untranslatable with the reason, never guessed.

The report answers one question for item I of the gap plan: if the engine read Forge scripts
instead of (or after) its oracle-text templates, how much of Standard's ignored text would it
cover, and which Forge APIs would have to be added to the engine to cover more? It does not
change how cards are loaded (`mtgsim/cards/` owns that).

Checks of the mapping itself: on the cards the oracle templates already play fully, the
translation is compared with the templates' effects (`agreement` in the report).
"""
from __future__ import annotations

import argparse
import re
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .build_carddb import normalize
from .cards import KEYWORDS, Effect, Trigger

# ---------------------------------------------------------------- parsing


@dataclass
class Step:
    api: str
    params: dict


@dataclass
class Ability:
    kind: str                       # spell, activated, loyalty, trigger, static, replacement, keyword, chapter
    params: dict
    desc: str
    steps: list = field(default_factory=list)      # Step chain (SubAbility$ / Execute$ followed)
    modes: list = field(default_factory=list)      # Charm: one Step chain per mode
    face: str = ""


@dataclass
class Face:
    name: str
    types: str = ""
    abilities: list = field(default_factory=list)


def parse_params(text: str) -> dict:
    """'SP$ Draw | NumCards$ 2' -> {'SP': 'Draw', 'NumCards': '2'}."""
    out = {}
    for part in text.split("|"):
        key, sep, val = part.partition("$")
        if sep:
            out[key.strip()] = val.strip()
    return out


def _api(params: dict) -> str:
    return params.get("SP") or params.get("AB") or params.get("DB") or ""


def _chain(first: dict, svars: dict, depth: int = 0) -> list:
    steps, params = [], first
    while params is not None and depth < 20:
        steps.append(Step(_api(params), params))
        sub = params.get("SubAbility")
        params = parse_params(svars[sub]) if sub in svars else None
        depth += 1
    return steps


def _desc(params: dict) -> str:
    return params.get("SpellDescription") or params.get("TriggerDescription") or params.get("Description") or ""


def parse_script(text: str) -> list[Face]:
    """All faces of a card script, with each ability's step chain resolved."""
    faces = []
    for block in re.split(r"^ALTERNATE\s*$", text, flags=re.M):
        lines = [ln.rstrip("\r") for ln in block.splitlines()]
        svars = {}
        for ln in lines:
            if ln.startswith("SVar:"):
                name, _, body = ln[5:].partition(":")
                svars[name] = body
        face = None
        for ln in lines:
            key, _, rest = ln.partition(":")
            if key == "Name":
                face = Face(rest.strip())
                faces.append(face)
            if face is None:
                continue
            if key == "Types":
                face.types = rest.strip()
            elif key == "A":
                p = parse_params(rest)
                kind = "loyalty" if p.get("Planeswalker") == "True" else "spell" if "SP" in p else "activated"
                ab = Ability(kind, p, _desc(p), _chain(p, svars), face=face.name)
                if _api(p) == "Charm":
                    ab.modes = [_chain(parse_params(svars[c]), svars) for c in p.get("Choices", "").split(",")
                                if c in svars]
                face.abilities.append(ab)
            elif key == "T":
                p = parse_params(rest)
                ex = p.get("Execute")
                steps = _chain(parse_params(svars[ex]), svars) if ex in svars else []
                face.abilities.append(Ability("trigger", p, _desc(p), steps, face=face.name))
            elif key == "S":
                p = parse_params(rest)
                face.abilities.append(Ability("static", p, _desc(p), face=face.name))
            elif key == "R":
                p = parse_params(rest)
                face.abilities.append(Ability("replacement", p, _desc(p), face=face.name))
            elif key == "K":
                rest = rest.strip()
                if rest.startswith("Chapter:"):
                    for i, sv in enumerate(rest.split(":")[2].split(","), 1):
                        p = parse_params(svars.get(sv, ""))
                        face.abilities.append(Ability("chapter", {"Chapter": str(i), **p}, _desc(p),
                                                      _chain(p, svars) if p else [], face=face.name))
                else:
                    face.abilities.append(Ability("keyword", {"K": rest}, rest, face=face.name))
    return faces


# ---------------------------------------------------------------- translation

class Untranslatable(Exception):
    """Why a step can't be expressed with the engine's effect objects."""


# Parameters that only steer prompts, AI hints or text, never what the effect does.
NOISE = {"SP", "AB", "DB", "SpellDescription", "StackDescription", "TgtPrompt", "AILogic", "AITgts",
         "AIPreference", "IsCurse", "PrecostDesc", "SubAbility", "Cost", "Planeswalker", "TriggerDescription",
         "Ultimate", "AITgtOwnCards", "AIPhyrexianPayment", "TgtZone", "Description", "TargetMin",
         "ActivationPhases", "SorcerySpeed", "CostDesc", "AITgtsOnlyBetterThanSelf", "AIManaPref",
         "Secondary", "AnyPlayer", "ShowCurrentCard", "Prompt", "ValidDescription"}

_NUM = re.compile(r"^\+?(-?\d+)$")


def _int(params: dict, key: str, default=None) -> int:
    val = params.get(key)
    if val is None:
        if default is None:
            raise Untranslatable(f"{key} missing")
        return default
    m = _NUM.match(val)
    if not m:
        raise Untranslatable(f"variable amount {key}={val}")
    return int(m[1])


def _only(params: dict, allowed: set, api: str):
    extra = sorted(set(params) - NOISE - allowed)
    if extra:
        raise Untranslatable(f"{api}: parameter {extra[0]}={params[extra[0]]}")


def _tgt(params: dict, table: dict, api: str) -> str:
    val = params.get("ValidTgts") or params.get("Defined") or ""
    if val not in table:
        raise Untranslatable(f"{api}: target {val or 'none'}")
    return table[val]


_CREATURE = {"Creature": "creature", "Creature.OppCtrl": "creature", "Creature.YouDontCtrl": "creature"}
_PLAYER = {"Player": "player", "Opponent": "player", "Player,Planeswalker": "player",
           "Opponent,Planeswalker": "player", "Player.Opponent": "player"}
_DAMAGE_TGT = {"Any": "any", **_CREATURE, "Creature,Planeswalker": "creature",
               "Creature.OppCtrl,Planeswalker.OppCtrl": "creature", **_PLAYER,
               "Player.Opponent,Planeswalker": "player", "TriggeredTarget": "that_player",
               "TargetedController": "that_controller"}
_DAMAGE_FILTER = {"Creature.attacking,Creature.blocking": "attacking_blocking", "Creature.tapped": "tapped",
                  "Creature.withoutFlying": "nonflying"}
_DESTROY_TGT = {**_CREATURE, "Creature,Planeswalker": "creature_pw",
                "Creature.OppCtrl,Planeswalker.OppCtrl": "creature_pw", "Artifact": "artifact"}
_DESTROY_FILTER = {"Creature.nonArtifact": "nonartifact", "Creature.tapped": "tapped"}
_YOU = {"", "You"}
_EACH_OPP = {"Player.Opponent", "Opponent"}


def _damage(p):
    _only(p, {"NumDmg", "ValidTgts", "Defined"}, "DealDamage")
    n = _int(p, "NumDmg")
    val = p.get("ValidTgts") or p.get("Defined", "")
    if val in _DAMAGE_FILTER:
        return [Effect("damage", n, target="creature", filter=_DAMAGE_FILTER[val])]
    if val in _EACH_OPP:
        return [Effect("damage", n, target="player")]
    return [Effect("damage", n, target=_tgt(p, _DAMAGE_TGT, "DealDamage"))]


def _destroy(p):
    _only(p, {"ValidTgts"}, "Destroy")
    val = p.get("ValidTgts", "")
    m = re.fullmatch(r"Creature\.cmcLE(\d+)", val)
    if m:
        return [Effect("destroy", target="creature", filter=f"max_cmc:{m[1]}")]
    if val in _DESTROY_FILTER:
        return [Effect("destroy", target="creature", filter=_DESTROY_FILTER[val])]
    return [Effect("destroy", target=_tgt(p, _DESTROY_TGT, "Destroy"))]


def _change_zone(p):
    _only(p, {"ValidTgts", "Origin", "Destination", "Defined"}, "ChangeZone")
    route = (p.get("Origin"), p.get("Destination"))
    val = p.get("ValidTgts", "")
    if route == ("Battlefield", "Exile") and val in _DESTROY_TGT:     # the cards package plays exile as destroy
        return [Effect("destroy", target=_DESTROY_TGT[val])]
    if route == ("Battlefield", "Hand") and val in ("Permanent.nonLand", "Permanent.nonLand+OppCtrl", "Creature",
                                                     "Creature.OppCtrl", "Permanent.nonLand+YouDontCtrl"):
        return [Effect("bounce", target="nonland_perm")]
    if route == ("Graveyard", "Hand") and val in ("Creature.YouOwn", "Creature.YouCtrl"):
        return [Effect("regrow")]
    raise Untranslatable(f"ChangeZone: {route[0]} to {route[1]}" + (f" ({val})" if val else ""))


def _change_zone_all(p):
    _only(p, {"ChangeType", "Origin", "Destination"}, "ChangeZoneAll")
    if (p.get("ChangeType"), p.get("Origin"), p.get("Destination")) == ("Creature", "Battlefield", "Exile"):
        return [Effect("wrath", target="each_creature")]
    raise Untranslatable(f"ChangeZoneAll: {p.get('ChangeType')} {p.get('Origin')} to {p.get('Destination')}")


def _destroy_all(p):
    _only(p, {"ValidCards"}, "DestroyAll")
    val = p.get("ValidCards")
    if val == "Creature":
        return [Effect("wrath", target="each_creature")]
    if val == "Planeswalker":
        return [Effect("wrath_pw")]
    raise Untranslatable(f"DestroyAll: {val}")


def _draw(p):
    _only(p, {"NumCards", "Defined"}, "Draw")
    if p.get("Defined", "") not in _YOU:
        raise Untranslatable(f"Draw: player {p['Defined']}")
    return [Effect("draw", _int(p, "NumCards", 1))]


def _gain_life(p):
    _only(p, {"LifeAmount", "Defined"}, "GainLife")
    if p.get("Defined", "") not in _YOU:
        raise Untranslatable(f"GainLife: player {p['Defined']}")
    return [Effect("gain_life", _int(p, "LifeAmount"))]


def _lose_life(p):
    _only(p, {"LifeAmount", "Defined", "ValidTgts"}, "LoseLife")
    n, who = _int(p, "LifeAmount"), p.get("Defined") or p.get("ValidTgts") or ""
    if who in _EACH_OPP:
        return [Effect("drain", n, target="each_opponent")]
    if who in _YOU:
        return [Effect("lose_life", n)]
    if who in ("TriggeredCardController", "TriggeredPlayer", "TargetedController", "Player", "Opponent"):
        return [Effect("lose_life", n, target="that_player" if who != "Player" and who != "Opponent" else "player")]
    raise Untranslatable(f"LoseLife: player {who or 'none'}")


def _pump(p):
    _only(p, {"NumAtt", "NumDef", "ValidTgts", "Defined", "KW"}, "Pump")
    att, dfn = _int(p, "NumAtt", 0), _int(p, "NumDef", 0)
    who = p.get("ValidTgts") or p.get("Defined") or ""
    targets = {"Creature": "creature", "Creature.YouCtrl": "creature", "Self": "self", "Targeted": "prev",
               "Creature.OppCtrl": "creature"}
    if who not in targets:
        raise Untranslatable(f"Pump: target {who or 'none'}")
    tgt, out = targets[who], []
    if att < 0 or dfn < 0:
        if att > 0 or dfn > 0 or tgt != "creature":
            raise Untranslatable("Pump: mixed or self debuff")
        out.append(Effect("debuff_one", -att, -dfn, target="creature"))
    elif att or dfn:
        out.append(Effect("pump", att, dfn, target=tgt))
    for kw in filter(None, p.get("KW", "").split(" & ")):
        if kw.lower() not in KEYWORDS:
            raise Untranslatable(f"Pump: keyword {kw}")
        out.append(Effect("grant", target="prev" if out or tgt == "prev" else tgt, data={"keyword": kw.lower()}))
    if not out:
        raise Untranslatable("Pump: nothing to do")
    return out


def _pump_all(p):
    _only(p, {"NumAtt", "NumDef", "ValidCards"}, "PumpAll")
    att, dfn = _int(p, "NumAtt", 0), _int(p, "NumDef", 0)
    where = {"Creature.OppCtrl": "opp_creatures", "Creature": "each_creature"}.get(p.get("ValidCards"))
    if where is None or att > 0 or dfn > 0:
        raise Untranslatable(f"PumpAll: {p.get('ValidCards')} {att}/{dfn}")
    return [Effect("debuff", -att, -dfn, target=where)]


def _counter(p):
    _only(p, {"TargetType", "ValidTgts", "UnlessCost"}, "Counter")
    filt = {"Card": "", "Card.nonCreature": "noncreature", "Card.Creature": "creature", "Creature": "creature",
            "Instant,Sorcery": "instant_sorcery", "Card.Instant,Card.Sorcery": "instant_sorcery"}
    m = re.fullmatch(r"Card\.cmcEQ(\d+)", p.get("ValidTgts", ""))
    if p.get("TargetType") == "Spell" and m:
        return [Effect("counter", _int(p, "UnlessCost", 0), target="spell", filter=f"cmc:{m[1]}")]
    if p.get("TargetType") != "Spell" or p.get("ValidTgts") not in filt:
        raise Untranslatable(f"Counter: {p.get('TargetType')} {p.get('ValidTgts')}")
    return [Effect("counter", _int(p, "UnlessCost", 0), target="spell", filter=filt[p["ValidTgts"]])]


def _simple(kind, key, api, allowed=()):
    def f(p):
        _only(p, {key, "Defined", *allowed}, api)
        if p.get("Defined", "") not in _YOU:
            raise Untranslatable(f"{api}: player {p['Defined']}")
        return [Effect(kind, _int(p, key, 1))]
    return f


def _mill(p):
    _only(p, {"NumCards", "Defined", "ValidTgts"}, "Mill")
    n, who = _int(p, "NumCards", 1), p.get("ValidTgts") or p.get("Defined") or ""
    if who in _YOU:
        return [Effect("mill", n)]
    if who in ("Player", "Opponent", *_EACH_OPP):
        return [Effect("mill", n, target="player")]
    raise Untranslatable(f"Mill: player {who}")


def _discard(p):
    _only(p, {"NumCards", "Defined", "ValidTgts", "Mode"}, "Discard")
    who, mode, n = p.get("ValidTgts") or p.get("Defined") or "", p.get("Mode"), _int(p, "NumCards", 1)
    if who in ("Player", "Opponent") and mode == "RevealYouChoose":
        return [Effect("discard_choice", n, target="player")]
    if who in ("Player", "Opponent") and mode == "TgtChoose":
        return [Effect("discard", n, target="player")]
    if who in _YOU and mode == "TgtChoose":
        return [Effect("discard", n)]
    raise Untranslatable(f"Discard: {who or 'you'} {mode}")


_TOKEN_KINDS = {"c_a_treasure_sac": "treasure", "c_a_clue_draw": "clue", "c_a_blood_draw": "blood"}
_TOKEN_COLORS = set("wubrgc")


def _token(p):
    _only(p, {"TokenScript", "TokenAmount", "TokenOwner"}, "Token")
    if p.get("TokenOwner", "You") != "You":
        raise Untranslatable(f"Token: owner {p['TokenOwner']}")
    n, scripts = _int(p, "TokenAmount", 1), p.get("TokenScript", "").split(",")
    out = []
    for s in scripts:
        if s in _TOKEN_KINDS:
            out.append(Effect("token", n, data={"kind": _TOKEN_KINDS[s]}))
            continue
        parts = s.split("_")
        if len(parts) < 4 or not set(parts[0]) <= _TOKEN_COLORS or not parts[1].isdigit() or not parts[2].isdigit():
            raise Untranslatable(f"Token: {s}")
        words = [w for w in parts[3:] if w not in ("a", "e")]     # artifact / enchantment markers
        kws = frozenset(w.replace("firststrike", "first strike") for w in words
                        if w.replace("firststrike", "first strike") in KEYWORDS)
        name = " ".join(w.capitalize() for w in words if w.replace("firststrike", "first strike") not in KEYWORDS)
        out.append(Effect("token", n, data={"name": name or "Token", "power": int(parts[1]),
                                            "toughness": int(parts[2]), "keywords": kws,
                                            "attacking": False, "triggers": []}))
    return out


def _put_counter(p):
    _only(p, {"CounterType", "CounterNum", "Defined", "ValidTgts"}, "PutCounter")
    n, ctype, who = _int(p, "CounterNum", 1), p.get("CounterType", ""), p.get("ValidTgts") or p.get("Defined") or ""
    if ctype == "P1P1":
        tgt = {"Self": "self", "Creature.YouCtrl": "creature_mine", "Creature": "creature_mine"}.get(who)
        if tgt:
            return [Effect("p1_counters", n, target=tgt)]
    elif ctype == "Stun" and who == "Targeted":
        return [Effect("stun", n, target="prev")]
    elif who == "Self" and n == 1:
        return [Effect("add_counter", 1, target="self", data={"counter": ctype.lower()})]
    raise Untranslatable(f"PutCounter: {ctype} on {who or 'none'}")


def _tap(p):
    _only(p, {"ValidTgts", "TargetMax"}, "Tap")
    if p.get("ValidTgts") not in ("Creature", "Creature.OppCtrl", "Permanent.nonLand", "Permanent.nonLand+OppCtrl"):
        raise Untranslatable(f"Tap: {p.get('ValidTgts')}")
    return [Effect("tap", _int(p, "TargetMax", 1), target="creature")]


def _dig(p):
    _only(p, {"DigNum", "ChangeNum", "DestinationZone", "DestinationZone2", "LibraryPosition2",
              "RestRandomOrder", "Defined", "NoReveal"}, "Dig")
    if p.get("DestinationZone", "Hand") != "Hand" or p.get("Defined", "") not in _YOU:
        raise Untranslatable(f"Dig: to {p.get('DestinationZone')}")
    if p.get("DestinationZone2", "Library") != "Library":
        raise Untranslatable(f"Dig: rest to {p['DestinationZone2']}")
    return [Effect("dig", _int(p, "DigNum"), _int(p, "ChangeNum", 1))]


def _damage_all(p):
    _only(p, {"NumDmg", "ValidCards"}, "DamageAll")
    if p.get("ValidCards") != "Creature":
        raise Untranslatable(f"DamageAll: {p.get('ValidCards')}")
    return [Effect("damage", _int(p, "NumDmg"), target="each_creature")]


def _no_op(p):
    _only(p, {"ClearRemembered", "ClearChosenCard", "ClearImprinted"}, "Cleanup")
    return []


HANDLERS = {
    "DealDamage": _damage, "Destroy": _destroy, "ChangeZone": _change_zone, "ChangeZoneAll": _change_zone_all,
    "DestroyAll": _destroy_all, "DamageAll": _damage_all, "Draw": _draw, "GainLife": _gain_life, "LoseLife": _lose_life, "Pump": _pump,
    "PumpAll": _pump_all, "Counter": _counter, "Scry": _simple("scry", "ScryNum", "Scry"),
    "Surveil": _simple("surveil", "Amount", "Surveil"), "Mill": _mill, "Discard": _discard, "Token": _token,
    "PutCounter": _put_counter, "Tap": _tap, "Dig": _dig, "Cleanup": _no_op,
    "Investigate": lambda p: (_only(p, {"Num"}, "Investigate") or
                              [Effect("token", _int(p, "Num", 1), data={"kind": "clue"})]),
}


def _optional_cost(steps) -> list | None:
    """A trigger whose first step is an AB$ with a Cost$ means "you may pay that cost; if you do ...".
    Only the rummage case has an engine effect."""
    first = steps[0].params if steps else {}
    if "AB" not in first or "Cost" not in first:
        return None
    if steps[0].api == "Draw" and first["Cost"] in ("Discard<1/Card>", "Discard<1/Card/card>") \
            and _int(first, "NumCards", 1) == 1 and len(steps) == 1:
        return [Effect("rummage", 1)]
    raise Untranslatable(f"optional cost {first['Cost']}")


def translate_steps(steps) -> list:
    paid = _optional_cost(steps)
    if paid is not None:
        return paid
    out = []
    for st in steps:
        h = HANDLERS.get(st.api)
        if h is None:
            raise Untranslatable(f"API {st.api or '?'}")
        if "Condition" in st.params or "ConditionCheckSVar" in st.params or "ConditionDefined" in st.params:
            raise Untranslatable(f"{st.api}: condition")
        if st.params.get("Optional") == "True" or "UnlessCost" in st.params and st.api != "Counter":
            raise Untranslatable(f"{st.api}: optional or unless-cost")
        out += h(st.params)
    return out


# Trigger modes: (Mode, key params) -> engine event.
def _trigger_event(p: dict) -> str:
    mode, card = p.get("Mode"), p.get("ValidCard", "")
    allowed = {"Mode", "ValidCard", "Execute", "TriggerDescription", "TriggerZones", "OptionalDecider",
               "Origin", "Destination", "ValidPlayer", "ValidActivatingPlayer", "CombatDamage", "ValidSource",
               "ValidTarget", "Phase", "Secondary"}
    extra = sorted(set(p) - allowed)
    if extra:
        raise Untranslatable(f"trigger {mode}: parameter {extra[0]}")
    if mode == "ChangesZone" and p.get("Destination") == "Battlefield":
        return {"Card.Self": "etb", "Creature.Other+YouCtrl": "other_creature_enters",
                "Creature.YouCtrl+Other": "other_creature_enters", "Land.YouCtrl": "land_enters"}.get(card) or \
            _bad(f"trigger ChangesZone to Battlefield: {card}")
    if mode == "ChangesZone" and (p.get("Origin"), p.get("Destination")) == ("Battlefield", "Graveyard"):
        return {"Card.Self": "dies", "Creature.OppCtrl": "opp_creature_dies",
                "Creature.Other+YouCtrl": "other_creature_dies",
                "Creature.YouCtrl+Other": "other_creature_dies"}.get(card) or _bad(f"trigger dies: {card}")
    if mode == "Attacks" and card == "Card.Self":
        return "attacks"
    if mode == "DamageDone" and p.get("ValidSource") == "Card.Self" and p.get("CombatDamage") == "True" \
            and p.get("ValidTarget") == "Player":
        return "combat_damage_player"
    if mode == "SpellCast" and p.get("ValidActivatingPlayer") == "You":
        return {"Card.nonCreature": "cast_noncreature", "Card": "cast_spell",
                "Instant,Sorcery": "cast_instant_sorcery", "Card.Instant,Card.Sorcery": "cast_instant_sorcery"}.get(card) or _bad(f"trigger SpellCast: {card}")
    if mode == "Phase" and p.get("ValidPlayer") == "You":
        return {"Upkeep": "upkeep", "End of Turn": "end_step"}.get(p.get("Phase")) or _bad(f"trigger Phase {p.get('Phase')}")
    if mode == "Drawn":
        return {"Card.YouCtrl": "you_draw", "Card.OppCtrl": "opp_draw"}.get(card) or _bad(f"trigger Drawn: {card}")
    raise Untranslatable(f"trigger {mode}")


def _bad(reason):
    raise Untranslatable(reason)


def _keyword(k: str):
    word = k.split(":")[0]
    if word.lower() in KEYWORDS:
        return ("keyword", word.lower())
    m = re.fullmatch(r"Ward:(\d+)", k)
    if m:
        return ("ward", int(m[1]))
    m = re.fullmatch(r"Crew:(\d+)", k)
    if m:
        return ("crew", int(m[1]))
    m = re.fullmatch(r"(Flashback|Foretell|Kicker|Spectacle):([\dWUBRGC ]+)", k)
    if m:
        return (m[1].lower(), m[2].strip())
    raise Untranslatable(f"keyword {word}")


def _loyalty_cost(cost: str) -> int:
    m = re.fullmatch(r"(Add|Sub)Counter<(\d+)/LOYALTY>", cost or "")
    if not m:
        raise Untranslatable(f"loyalty cost {cost}")
    return int(m[2]) * (1 if m[1] == "Add" else -1)


def translate(ab: Ability):
    """The engine object for one ability, or raise Untranslatable with the reason."""
    if ab.kind == "keyword":
        return _keyword(ab.params["K"])
    if ab.kind == "spell":
        if ab.modes:
            _only(ab.params, {"Choices", "CharmNum", "MinCharmNum"}, "Charm")
            return ("modes", [translate_steps(m) for m in ab.modes])
        return ("spell", translate_steps(ab.steps))
    if ab.kind == "trigger":
        return ("trigger", Trigger(_trigger_event(ab.params), translate_steps(ab.steps)))
    if ab.kind == "chapter":
        return ("chapter", translate_steps(ab.steps))
    if ab.kind == "loyalty":
        steps = [Step(ab.steps[0].api, {k: v for k, v in ab.steps[0].params.items() if k != "Cost"})] + ab.steps[1:]
        return ("loyalty", (_loyalty_cost(ab.params.get("Cost")), translate_steps(steps)))
    if ab.kind == "activated" and _api(ab.params) == "Mana":
        if re.fullmatch(r"T", ab.params.get("Cost", "")) and set(ab.params) - NOISE <= {"Produced", "Amount"}:
            return ("mana", ab.params.get("Produced"))
        raise Untranslatable("mana ability with a cost or restriction")
    if ab.kind == "activated":
        raise Untranslatable(f"activated ability ({_api(ab.params)})")
    if ab.kind == "static":
        p = ab.params
        if p.get("Mode") == "Continuous" and p.get("Affected") in ("Creature.YouCtrl", "Creature.Other+YouCtrl",
                                                                   "Creature.YouCtrl+Other") \
                and set(p) - {"Mode", "Affected", "AddPower", "AddToughness", "Description"} == set():
            return ("anthem", (_int(p, "AddPower", 0), _int(p, "AddToughness", 0)))
        raise Untranslatable(f"static {p.get('Mode')}")
    if ab.kind == "replacement" and ab.params.get("ReplaceWith") == "ETBTapped" \
            and set(ab.params) <= {"Event", "ValidCard", "Destination", "ReplaceWith", "ReplacementResult",
                                   "Description", "ActiveZones"}:
        return ("enters_tapped", True)
    raise Untranslatable(f"{ab.kind} {ab.params.get('Event', '')}".strip())


def _unsupported_apis(ab: Ability) -> list[str]:
    """APIs in an ability's chain that have no handler (for the 'what to add' list)."""
    chains = ab.modes or [ab.steps]
    apis = [st.api for ch in chains for st in ch if st.api and st.api not in HANDLERS]
    return apis


# ---------------------------------------------------------------- scripts on disk

def cardsfolder(path: Path) -> Path:
    path = Path(path).expanduser()
    for cand in (path, path / "res" / "cardsfolder", path / "forge-gui" / "res" / "cardsfolder", path / "cardsfolder"):
        if cand.is_dir() and (any(cand.glob("*/*.txt")) or any(cand.glob("*.txt")) or (cand / "cardsfolder.zip").exists()):
            return cand
    raise FileNotFoundError(f"No Forge cardsfolder under {path}")


def script_index(folder: Path) -> dict[str, str]:
    """Normalized front-face name -> script text, for every card script in a cardsfolder (or its zip)."""
    out = {}

    def add(text: str):
        m = re.search(r"^Name:(.+)$", text, flags=re.M)
        if m:
            out[normalize(m[1].strip())] = text

    zipped = folder / "cardsfolder.zip"
    if zipped.exists():
        with zipfile.ZipFile(zipped) as z:
            for info in z.infolist():
                if info.filename.endswith(".txt"):
                    add(z.read(info).decode("utf-8", errors="replace"))
    for f in folder.rglob("*.txt"):
        add(f.read_text(encoding="utf-8", errors="replace"))
    return out


# ---------------------------------------------------------------- measuring

_WORD = re.compile(r"[a-z0-9+/-]+")
_STOP = {"a", "an", "the", "of", "to", "and", "or", "it", "its", "this", "that", "on", "you", "your", "~", "in"}


def _tokens(text: str, name: str = "") -> set:
    text = re.sub(r"\([^)]*\)", "", text)
    for n in filter(None, {name, name.split(",")[0]}):
        text = text.replace(n, "~")
    text = text.replace("CARDNAME", "~").replace("NICKNAME", "~").lower()
    return {w for w in _WORD.findall(text) if w not in _STOP}


def match_line(line: str, abilities, name: str = ""):
    """The ability whose description best covers an ignored line (most of the line's words), or None."""
    line = re.sub(r"^\[[^\]]*\]: |^[^:]+ — (?=[A-Z])", "", line)    # loyalty "[+1]: " / chapter prefixes
    words = _tokens(line, name)
    if not words:
        return None
    best, score = None, 0.0
    for ab in abilities:
        s = len(words & _tokens(ab.desc, name)) / len(words)
        if s > score:
            best, score = ab, s
    return best if score >= 0.6 else None


@dataclass
class ScriptReport:
    cards: int = 0                       # partly supported cards with a script
    no_script: int = 0
    lines: int = 0                       # ignored lines
    matched: int = 0                     # ignored lines matched to a Forge ability
    translated: int = 0                  # ... whose ability translates
    api_bound: int = 0                   # ... whose ability only uses mapped APIs (any parameters)
    cards_fixed: int = 0                 # partly supported cards whose every ignored line translates
    blockers: Counter = field(default_factory=Counter)      # reason -> ignored lines blocked by it
    api_cards: Counter = field(default_factory=Counter)     # API -> cards with an ignored line using it
    api_cards_ok: Counter = field(default_factory=Counter)  # API -> of those, cards where that line translates
    missing_api: Counter = field(default_factory=Counter)   # unmapped API -> cards it blocks
    agree: int = 0                       # fully supported cards where translation equals the templates
    compared: int = 0
    disagreements: list = field(default_factory=list)
    examples: list = field(default_factory=list)            # (card, line, effects) that would be gained


def _effect_key(e: Effect):
    return (e.kind, e.amount, e.amount2, e.target, e.filter)


def _template_shape(card) -> Counter:
    shape = Counter(("spell",) + _effect_key(e) for e in card.spell_effects)
    for t in card.triggers:
        shape.update(("trigger", t.event) + _effect_key(e) for e in t.effects)
    return shape


def _translated_shape(faces) -> Counter | None:
    shape = Counter()
    for ab in faces[0].abilities if faces else []:
        try:
            kind, val = translate(ab)
        except Untranslatable:
            if ab.kind in ("spell", "trigger"):
                return None
            continue
        if (kind, val) == ("keyword", "prowess"):       # the templates play prowess as a trigger
            shape[("trigger", "cast_noncreature", "pump", 1, 1, "self", "")] += 1
        elif kind == "spell":
            shape.update(("spell",) + _effect_key(e) for e in val)
        elif kind == "trigger":
            shape.update(("trigger", val.event) + _effect_key(e) for e in val.effects)
    return shape


def measure(partial: dict, full_names, scripts: dict, db=None) -> ScriptReport:
    """partial: card name -> ignored lines (from standard_coverage); full_names: cards the
    templates play fully (for the agreement check, needs db)."""
    rep = ScriptReport()
    for name, ignored in sorted(partial.items()):
        text = scripts.get(normalize(name.split(" // ")[0]))
        if text is None:
            rep.no_script += 1
            continue
        rep.cards += 1
        faces = parse_script(text)
        abilities = [ab for f in faces for ab in f.abilities]
        fixed, apis, apis_ok = True, set(), set()
        for line in ignored:
            rep.lines += 1
            ab = match_line(line, abilities, name)
            if ab is None:
                fixed = False
                rep.blockers["no matching Forge ability (keyword-only text, X cost or an engine note)"] += 1
                continue
            rep.matched += 1
            chain_apis = {st.api for ch in (ab.modes or [ab.steps]) for st in ch if st.api}
            apis |= chain_apis
            if ab.kind in ("spell", "trigger", "chapter", "loyalty") and chain_apis and chain_apis <= set(HANDLERS):
                rep.api_bound += 1
            try:
                kind, val = translate(ab)
            except Untranslatable as e:
                fixed = False
                reason = str(e)
                rep.blockers[reason] += 1
                continue
            rep.translated += 1
            apis_ok |= chain_apis
            if len(rep.examples) < 2000:
                rep.examples.append((name, line, kind, val))
        for api in apis:
            rep.api_cards[api] += 1
        for api in apis_ok:
            rep.api_cards_ok[api] += 1
        blocked_by = {api for ab in abilities for api in _unsupported_apis(ab)
                      if any(match_line(line, [ab], name) for line in ignored)}
        for api in blocked_by:
            rep.missing_api[api] += 1
        rep.cards_fixed += fixed
    if db is not None:
        for name in full_names:
            text = scripts.get(normalize(name.split(" // ")[0]))
            if text is None:
                continue
            card = db.get(name)
            if card.back or card.adventure or card.modes or card.chapters or card.loyalty_abilities:
                continue
            want = _template_shape(card)
            if not want:
                continue
            got = _translated_shape(parse_script(text))
            rep.compared += 1
            if got == want:
                rep.agree += 1
            else:
                rep.disagreements.append((name, sorted(want.elements()), None if got is None else sorted(got.elements())))
    return rep


def format_report(rep: ScriptReport, partial_total: int, top: int = 20) -> str:
    pct = lambda a, b: f"{100 * a / b:.1f}%" if b else "n/a"
    lines = ["Forge script translation prototype (Standard, partly supported cards)", "",
             f"Partly supported cards with a Forge script: {rep.cards:,} of {partial_total:,}"
             + (f" ({rep.no_script} without)" if rep.no_script else ""),
             f"Ignored lines: {rep.lines:,}",
             f"  matched to a Forge ability:   {rep.matched:,} ({pct(rep.matched, rep.lines)})",
             f"  translatable with the mapping: {rep.translated:,} ({pct(rep.translated, rep.lines)})",
             f"  upper bound if every parameter of the mapped APIs were supported: {rep.api_bound:,} "
             f"({pct(rep.api_bound, rep.lines)})",
             f"Cards that would become fully supported: {rep.cards_fixed:,} ({pct(rep.cards_fixed, rep.cards)})"]
    if rep.compared:
        lines.append(f"Agreement with the templates on fully supported cards: {rep.agree} of {rep.compared} "
                     f"({pct(rep.agree, rep.compared)})")
    lines += ["", "Per mapped Forge API: cards with an ignored line using it, and how many of those lines translate:"]
    for api in sorted(HANDLERS, key=lambda a: -rep.api_cards[a]):
        if rep.api_cards[api]:
            lines.append(f"  {api:<16}{rep.api_cards[api]:>6,} cards  {rep.api_cards_ok[api]:>6,} translate "
                         f"({pct(rep.api_cards_ok[api], rep.api_cards[api])})")
    lines += ["", f"Unmapped Forge APIs in ignored lines (cards, top {top}):"]
    for api, n in rep.missing_api.most_common(top):
        lines.append(f"  {api:<22}{n:>6,}")
    lines += ["", f"What blocks the rest (ignored lines, top {top}):"]
    for reason, n in rep.blockers.most_common(top):
        lines.append(f"  {n:>6,}  {reason}")
    return "\n".join(lines)


def describe(name: str, text: str) -> str:
    out = [name]
    for face in parse_script(text):
        for ab in face.abilities:
            try:
                res = translate(ab)
                verdict = f"-> {res[0]}: {res[1]}"
            except Untranslatable as e:
                verdict = f"-- untranslatable: {e}"
            out.append(f"  [{ab.kind}] {ab.desc or ab.params.get('K', '')}\n      {verdict}")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m mtgsim.forge_script", description=__doc__.split("\n\n")[0])
    ap.add_argument("--forge", metavar="DIR", required=True, help="a Forge install or git checkout")
    ap.add_argument("--card", action="append", help="show how these cards' scripts translate, then stop")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--disagreements", action="store_true", help="list cards where translation and templates differ")
    args = ap.parse_args(argv)
    from . import standard_coverage as sc
    from .carddb import CardDB
    from .coverage import FULL
    scripts = script_index(cardsfolder(Path(args.forge)))
    if args.card:
        for c in args.card:
            text = scripts.get(normalize(c))
            print(describe(c, text) if text else f"{c}: no script")
        return 0
    try:
        res = sc.forge_res(Path(args.forge))
    except FileNotFoundError:
        res = sc.SAVED
    fmt, names = sc.standard_cards(res)
    db = CardDB(offline=True)
    cov = sc.measure(names, db, fmt)
    full = [n for n in names if n not in cov.partial and _status(db, n) == FULL]
    rep = measure(cov.partial, full, scripts, db)
    print(format_report(rep, len(cov.partial), args.top))
    if args.disagreements:
        for name, want, got in rep.disagreements:
            print(f"\n{name}\n  templates:   {want}\n  translation: {got}")
    return 0


def _status(db, name):
    from .coverage import card_coverage
    try:
        return card_coverage(db.get(name)).status
    except KeyError:
        return None


if __name__ == "__main__":
    sys.exit(main())
