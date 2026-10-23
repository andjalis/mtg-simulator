"""Removal and fight templates: destroy/exile with a restriction (enchantment, noncreature artifact,
Vehicle, power 4 or greater, flying), "fights", "deals damage equal to its power" and "untap target
creature". Joined to the templates in mtgsim.cards; the engine hands KINDS to resolve() here.

A fight or bite is two effects: ``fight_mark`` picks the creature you control, the next effect picks the
opponent's creature, and resolve() reads the first target from the stack item.
"""
from __future__ import annotations

import re

KINDS = {"fight_mark", "fight", "bite", "untap_target", "bounce_own"}
_KW = "flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach"
_THEIRS = r"(?:an opponent controls|you don't control)"


def _destroy(target, flt):
    def build(m):
        from .cards import Effect  # at match time: this module loads before cards
        return Effect("destroy", target=target, filter=flt(m) if callable(flt) else flt)
    return build


EFFECT_PATTERNS = [
    (r"destroy (?:up to one )?target (nonbasic )?land(?: (an opponent controls|you don't control))?",
     lambda m: _effect("destroy", "land", filter="land:" + ("nonbasic:" if m[1] else "") + ("opp" if m[2] else ""))),
    (r"target creature you control deals damage equal to its power to each of two other target creatures",
     lambda m: _pair("bite") + [_distinct(_pair("bite")[1])]),
    (r"put a \+1/\+1 counter on each of up to two target creatures",
     lambda m: [_distinct(_counter()), _distinct(_counter())]),
    (r"destroy (?:up to one )?target artifact, enchantment, or creature with flying",
     _destroy("nonland_perm", "art_ench_fly")),
    (r"return up to one other target permanent you control to its owner's hand",
     lambda m: _effect_bounce_own()),
    (r"(?:destroy|exile) target enchantment(?: an opponent controls| you don't control)?",
     _destroy("artifact_enchantment", "enchantment")),
    (r"(?:destroy|exile) target noncreature artifact", _destroy("artifact_enchantment", "noncreature_artifact")),
    (r"(?:destroy|exile) target Vehicle", _destroy("artifact", "subtype:Vehicle")),
    (r"exile target artifact", _destroy("artifact", "")),
    (r"(?:destroy|exile) target creature with power (\d+) or greater",
     _destroy("creature", lambda m: f"min_power:{m[1]}")),
    (r"(?:destroy|exile) target creature with (flying|reach)", _destroy("creature", lambda m: f"kw:{m[1].lower()}")),
    (r"(destroy|exile) (?:up to one )?target ((?:artifact|enchantment|creature|planeswalker|nonland permanent)"
     r"(?:(?:,| or|, or) (?:artifact|enchantment|creature|planeswalker))*)(?: (an opponent controls|you don't control))?"
     r"(?: with (mana value|power|toughness) (\d+) or (less|greater))?", lambda m: _removal_pattern(m)),
    (r"(?:for each opponent, )?exile (?:up to one )?(?:other )?target (?:non-(\w+) )?((?:artifact|enchantment|creature|planeswalker|nonland permanent)"
     r"(?:(?:,| or|, or) (?:artifact|enchantment|creature|planeswalker))*)(?: other than enchanted creature)?(?: (an opponent controls|you control))?"
     r"(?: with (mana value) (\d+) or (less|greater))? until ~ leaves the battlefield", lambda m: _oring(m)),
    (r"target creature you control fights target creature " + _THEIRS, lambda m: _pair("fight")),
    (r"target creature you control deals damage equal to its power to target creature " + _THEIRS,
     lambda m: _pair("bite")),
    (r"(?:it|that creature|he|she) deals damage equal to its power to (?:up to one )?target creature " + _THEIRS,
     lambda m: _effect("bite", "creature", filter="opp")),
    (r"(?:it|that creature|he|she) deals damage equal to its power to up to one (?:other )?target creature",
     lambda m: _effect("bite", "creature", filter="opp")),     # any creature; the AI only aims at theirs
    (r"(?:it|that creature|he|she) fights (?:up to one )?target creature " + _THEIRS,
     lambda m: _effect("fight", "creature", filter="opp")),
    (r"target creature you control deals damage equal to its power to target creature or planeswalker( " + _THEIRS + ")?",
     lambda m: _pair("bite", "creature_pw", "opp" if m[1] else "")),
    (r"untap target creature", lambda m: _effect("untap_target", "creature")),
    (r"untap target (?:basic )?land", lambda m: _effect("untap_target", "land")),
    (r"untap target (Forest|Plains|Island|Swamp|Mountain|Gate)", lambda m: _effect("untap_target", "land",
                                                                                  filter=f"subtype:{m[1].capitalize()}")),
    (r"regenerate target ([A-Z][a-z]+)", lambda m: _regen_sub(m[1])),
    (rf"target creature you control gains ({_KW}) until end of turn",
     lambda m: _effect("grant", "creature_mine", data={"keyword": m[1].lower()})),
]


def _effect(kind, target, data=None, filter=""):
    from .cards import Effect
    return Effect(kind, target=target, data=data or {}, filter=filter)


def _regen_sub(sub):
    """"Regenerate target Elephant": one of your creatures of that type."""
    from .cards import Effect, NO_MATCH
    if not sub[0].isupper() or sub.lower() in ("creature", "artifact", "permanent"):
        return NO_MATCH
    return Effect("regenerate", 1, target="creature_mine", filter=f"subtype:{sub.capitalize()}")


def _distinct(eff):
    eff.data = dict(eff.data, distinct=True)
    return eff


def _counter():
    from .cards import Effect
    return Effect("add_counter", 1, target="creature_mine", data={"counter": "+1/+1"})


def _pair(kind, target="creature", flt="opp"):
    from .cards import Effect
    return [Effect("fight_mark", target="creature_mine"), Effect(kind, target=target, filter=flt)]


def _effect_bounce_own():
    from .cards import Effect
    return Effect("bounce_own", target="nonland_perm", filter="mine")


_ORD = ("artifact", "enchantment", "creature", "planeswalker")


def _removal_pattern(m):
    """destroy/exile target <types> [an opponent controls] [with mana value / power / toughness N or less / greater]."""
    from .cards import Effect, NO_MATCH
    types = [t for t in re.split(r",? or |, ", m[2]) if t]
    if not (m[3] or m[4]) and len(types) == 1 and types[0] in ("creature", "artifact", "enchantment"):
        return NO_MATCH            # the plain templates in cards/patterns.py handle these
    kind = types[0] if len(types) == 1 and types[0] in ("creature", "artifact") else "nonland_perm"
    stat = {"mana value": "cmc", "power": "power", "toughness": "toughness"}.get(m[4], "")
    cond = f"{stat}{'<=' if m[6] == 'less' else '>='}{m[5]}" if stat else ""
    flt = f"x:{','.join(types)}|{cond}|{'opp' if m[3] else ''}"
    return Effect("destroy", target=kind, filter=flt)


def _oring(m):
    from .cards import Effect
    types = [t for t in re.split(r",? or |, ", m[2]) if t]
    cond = f"cmc{'<=' if m[6] == 'less' else '>='}{m[5]}" if m[4] else ""
    who = "mine" if m[3] == "you control" else "opp" if m[3] else ""
    flt = f"x:{','.join(types)}|{cond}|{who}|{m[1] or ''}"
    return Effect("oring", target="nonland_perm", filter=flt)


def x_passes(flt: str, perm, by) -> bool:
    parts = flt[2:].split("|")
    types, cond, opp = parts[:3]
    nonsub = parts[3] if len(parts) > 3 else ""
    if nonsub and nonsub.capitalize() in perm.card.subtypes:
        return False
    if opp == "mine":
        if perm.controller is not by:
            return False
    elif opp and perm.controller is by:
        return False
    ok = False
    for t in types.split(","):
        ok |= (perm.is_creature if t == "creature" else perm.card.is_artifact if t == "artifact" else
               "Enchantment" in perm.card.types if t == "enchantment" else perm.is_planeswalker if t == "planeswalker"
               else not perm.card.is_land)
    if cond:
        stat, op, n = re.fullmatch(r"(cmc|power|toughness)(<=|>=)(\d+)", cond).groups()
        val = {"cmc": perm.card.cmc, "power": perm.power, "toughness": perm.toughness}[stat]
        ok &= val <= int(n) if op == "<=" else val >= int(n)
    return ok


def passes(flt: str, perm):
    """True/False for the restrictions defined here, None for any other filter."""
    if flt == "noncreature":
        return not perm.is_creature
    if flt == "creature_or_ench":
        return perm.is_creature or "Enchantment" in perm.card.types
    if flt == "art_ench_fly":
        return perm.card.is_artifact or "Enchantment" in perm.card.types or (perm.is_creature and perm.has("flying"))
    if flt == "enchantment":
        return "Enchantment" in perm.card.types
    if flt == "noncreature_artifact":
        return perm.card.is_artifact and not perm.is_creature
    if flt.startswith("subtype:"):
        return flt[8:] in perm.card.subtypes
    if flt.startswith("min_power:"):
        return perm.power >= int(flt[10:])
    if flt.startswith("kw:"):
        return perm.has(flt[3:])
    return None


def choose(game, me, eff):
    """Targets for the kinds here (used by default_choose_target), or the string "n/a"."""
    mine = [x for x in game.legal_targets(me, eff) if x.controller is me]
    theirs = [x for x in game.legal_targets(me, eff) if x.controller is not me]
    from .engine import perm_value
    if eff.kind == "bounce_own":     # only worth it to replay a "when enters" ability
        return max((x for x in mine if (x.card.etb_effects or any(t.event == "etb" for t in x.card.triggers)) and x.card.cmc <= 3), key=perm_value, default=None)
    if eff.kind in ("fight_mark", "untap_target"):
        if eff.kind == "untap_target":
            mine = [x for x in mine if x.tapped]
        return max(mine, key=lambda x: (x.power, perm_value(x)), default=None)
    power = max((c.power for c in me.creatures), default=0)
    kill = [x for x in theirs if x.toughness - x.damage <= power and not x.has("indestructible")]
    if eff.kind == "fight":     # don't trade down: the creature must also survive or be worth less
        kill = [x for x in kill if x.power < max((c.toughness for c in me.creatures), default=0)
                or perm_value(x) >= max((perm_value(c) for c in me.creatures), default=0)]
    return max(kill, key=perm_value, default=None)


def resolve(game, p, eff, target, item):
    k = eff.kind
    if k == "untap_target":
        if target is not None:
            target.tapped = False
            game.log(f"untaps {target.card.name}", p)
        return
    if k == "fight_mark":
        return
    if k == "bounce_own":
        src = item.source if item is not None else None
        if target is not None and target is not src and target in target.controller.battlefield:
            game.log(f"{target.card.name} returns to hand", p)
            game.leave_battlefield(target, "hand")
        return
    mine = item.targets[0] if item is not None and item.targets else None
    if mine is None and item is not None:
        mine = item.source          # "When ~ enters, it deals damage equal to its power to ..."
    if mine is None or target is None:
        return
    if mine not in mine.controller.battlefield or target not in target.controller.battlefield:
        return
    game.log(f"{mine.card.name} {'fights' if k == 'fight' else 'strikes'} {target.card.name}", p)
    dmg_to_target, dmg_back = mine.power, target.power
    game.deal_damage(target, dmg_to_target, by=p, cause=f"{mine.card.name}: {k}", source=mine)
    if k == "fight":
        game.deal_damage(mine, dmg_back, by=target.controller, cause=f"{target.card.name}: fight", source=target)
