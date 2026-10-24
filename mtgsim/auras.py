"""Auras, and Equipment that attaches itself when it enters.

    Enchant creature / creature you control / creature or Vehicle / artifact or creature / land / permanent
    Enchanted creature gets +2/+2 and has flying.      Enchanted creature gets -3/-3.
    Enchanted creature doesn't untap during its controller's untap step.   Enchanted creature can't attack or block.
    When this Aura enters, tap enchanted creature.
    When this Equipment enters, attach it to target creature you control.

An Aura is a permanent on its caster's battlefield that is also listed in ``host.auras``. The host is picked
when the Aura resolves (it isn't targeted, so it can't be fizzled by hexproof), and an Aura with no legal host
isn't cast. Friendly Auras (a bonus, a keyword) go on the caster's best creature, hostile ones (a penalty, "doesn't
untap", "can't attack or block") on the opponent's best. Not modelled: "you control enchanted creature", "loses all
abilities", Auras that can be moved.
"""
from __future__ import annotations

import re

KINDS = {"tap_host", "attach_self"}
_KW = ("flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|"
       "menace|reach|shroud|defender|fear|intimidate|protection from (?:white|blue|black|red|green)")
_ENCHANT = re.compile(r"Enchant (creature|creature you control|creature or Vehicle|artifact or creature|"
                      r"artifact creature|land|permanent|nonland permanent|artifact|creature an opponent controls)")
_SIGN = {"+": 1, "-": -1, "−": -1}


def _n(sign: str, num: str) -> int:
    return _SIGN[sign] * int(num)


def parse_line(line: str, extra: dict, types) -> bool:
    """Consume an Aura's rules line into extra (CardDef fields); True if the line was understood."""
    m = _ENCHANT.fullmatch(line)
    if m and "Aura" in extra.get("_subtypes", ()):
        extra["aura"] = m[1]
        return True
    if not extra.get("aura"):
        return False
    from . import becomes
    if becomes.parse_aura_line(line, extra):
        return True
    if re.fullmatch(r"Enchanted (?:creature|permanent) doesn't untap during its controller's untap step\.", line):
        extra["aura_flags"] = extra.get("aura_flags", frozenset()) | {"no_untap"}
        return True
    m = re.fullmatch(r"Enchanted land is an? (Plains|Island|Swamp|Mountain|Forest)\.", line)
    if m:                                       # Spreading Seas, Evil Presence: it taps only for that colour
        extra["aura_flags"] = extra.get("aura_flags", frozenset()) | {f"land_type:{m[1]}"}
        return True
    if line == 'Enchanted land has "{T}: Add two mana of any one color."':    # New Horizons, Weirding Wood
        extra["aura_flags"] = extra.get("aura_flags", frozenset()) | {"grant_two"}
        extra.setdefault("_approx", []).append("two mana of any one color: the land makes two mana of any colours")
        return True
    m = re.fullmatch(r'Enchanted (?:land|creature) has "\{T\}: Add (one mana of any color|\{[WUBRGC]\})\."', line)
    if m:                                       # Abundant Growth, Utopia Sprawl's kin
        cols = "WUBRG" if "any" in m[1] else m[1][1]
        extra["aura_flags"] = extra.get("aura_flags", frozenset()) | {f"grant_mana:{cols}"}
        return True
    if re.fullmatch(r"Enchanted (?:creature|permanent) can't attack or block, and its activated abilities can't be activated\.",
                    line):                      # Arrest, Pacifism-plus
        extra["aura_flags"] = extra.get("aura_flags", frozenset()) | {"cant_attack_block", "no_activate"}
        return True
    if line == "Prevent all combat damage that would be dealt to and dealt by enchanted creature.":   # Sandskin
        extra["aura_flags"] = extra.get("aura_flags", frozenset()) | {"no_combat_damage"}
        return True
    if line == "Enchanted creature can't be blocked.":
        extra["equip_keywords"] = extra.get("equip_keywords", frozenset()) | {"unblockable"}
        return True
    if re.fullmatch(r"Enchanted creature can't attack or block\.", line):
        extra["aura_flags"] = extra.get("aura_flags", frozenset()) | {"cant_attack_block"}
        return True
    m = re.fullmatch(r"Enchanted (?:creature|permanent) loses all abilities(?: and doesn't untap during its controller's "
                     r"untap step)?\.", line)
    if m:
        flags = {"loses_abilities"} | ({"no_untap"} if "untap" in line else set())
        extra["aura_flags"] = extra.get("aura_flags", frozenset()) | flags
        extra.setdefault("_approx", []).append("loses all abilities: only keywords are removed")
        return True
    line = line.replace(" This effect doesn't remove ~.", "")          # the Wards: protection that keeps the Aura
    m = re.fullmatch(rf"Enchanted creature gets ([+−-])(\d+)/([+−-])(\d+)(?:, has ({_KW}),)? and (attacks each combat if able|"
                     rf"can't block|can't attack|can't attack you or planeswalkers you control)\.", line)
    if m:                                       # Uncontrollable Anger, Copper Carapace, the Vows
        extra["equip_bonus"] = (_n(m[1], m[2]), _n(m[3], m[4]))
        if m[5]:
            extra["equip_keywords"] = frozenset({m[5]})
        flag = {"attacks each combat if able": "must_attack", "can't block": "cant_block", "can't attack": "cant_attack"}.get(
            m[6], "cant_attack_you")
        extra["aura_flags"] = extra.get("aura_flags", frozenset()) | {flag}
        return True
    m = re.fullmatch(rf"Enchanted creature has ({_KW}) as long as (.+)\.", line)
    if m:                                       # Runemarks: "... as long as you control a red or white permanent"
        from . import statics
        cond = statics._condition(m[2])
        if cond:
            extra["aura_cond_kw"] = extra.get("aura_cond_kw", ()) + ((m[1], cond),)
            return True
    m = re.fullmatch(r"Enchanted creature gets ([+−-])(\d+)/([+−-])(\d+) for each ([\w -]+?) you control\.", line)
    if m:                                       # "Enchanted creature gets +1/+1 for each Forest you control."
        from .counting import _singular
        extra["aura_per"] = (_singular(m[5]), _n(m[1], m[2]), _n(m[3], m[4]))
        return True
    m = re.fullmatch(r"Enchanted creature gets ([+−-])(\d+)/([+−-])(\d+) and loses all abilities\.", line)
    if m:
        extra["equip_bonus"] = (_n(m[1], m[2]), _n(m[3], m[4]))
        extra["aura_flags"] = extra.get("aura_flags", frozenset()) | {"loses_abilities"}
        extra.setdefault("_approx", []).append("loses all abilities: only keywords are removed")
        return True
    m = re.fullmatch(rf"Enchanted creature (?:gets ([+−-])(\d+)/([+−-])(\d+))?(?:,? and |, | )?"
                     rf"(?:has ((?:{_KW})(?:(?:, | and |, and )(?:{_KW}))*))?(?:(?:,? and | )?(?:has )?ward \{{(\d+)\}})?\.", line)
    if m and (m[1] or m[5] or m[6]):
        bonus = (_n(m[1], m[2]), _n(m[3], m[4])) if m[1] else (0, 0)
        kws = frozenset(k.strip() for k in re.split(r", and |, | and ", m[5])) if m[5] else frozenset()
        extra["equip_bonus"] = bonus
        extra["equip_keywords"] = kws
        if m[6]:
            extra["equip_ward"] = int(m[6])
        return True
    return False


def finish(extra: dict):
    """After all lines are parsed: is the Aura hostile (put on the opponent's creature)?"""
    if extra.get("aura"):
        b = extra.get("equip_bonus", (0, 0))
        per = extra.get("aura_per", ("", 0, 0))
        own_use = {"must_attack", "cant_block", "cant_attack_you"}      # Uncontrollable Anger, the Vows: for your creatures
        flags = {f for f in extra.get("aura_flags", frozenset()) if not f.startswith("grant_mana:") and f != "grant_two"}
        extra["aura_hostile"] = bool(flags - own_use) or b[0] < 0 or b[1] < 0 or per[1] < 0 or per[2] < 0 or \
            "defender" in extra.get("equip_keywords", ()) or \
            extra["aura"] == "creature an opponent controls"


EFFECT_PATTERNS = [
    (r"tap enchanted (?:creature|permanent)", lambda m: _effect("tap_host", "none")),
    (r"attach it to target creature you control", lambda m: _effect("attach_self", "creature_mine")),
    (rf"(?:that creature|it) gains ({_KW}) until end of turn",
     lambda m: _effect("grant", "prev", {"keyword": m[1].lower()})),
]


def _effect(kind, target, data=None):
    from .cards import Effect
    return Effect(kind, target=target, data=data or {})


# ------------------------------------------------------------------ the engine side

def hosts(game, p, card) -> list:
    """The permanents the Aura card could enchant when p casts it."""
    kinds = card.aura
    opp = game.opponent(p)
    pool = [x for pl in game.players for x in pl.battlefield]
    out = []
    for x in pool:
        c = x.card
        ok = (x.is_creature if "creature" in kinds and "artifact" not in kinds and "Vehicle" not in kinds
              else x.is_creature or c.is_artifact if kinds == "artifact or creature"
              else x.is_creature or "Vehicle" in c.subtypes if kinds == "creature or Vehicle"
              else c.is_land if kinds == "land"
              else c.is_artifact if kinds == "artifact"
              else not c.is_land if kinds == "nonland permanent" else True)
        if kinds in ("creature you control",) and x.controller is not p:
            ok = False
        if kinds == "creature an opponent controls" and x.controller is not opp:
            ok = False
        if ok and game.targetable(x, p, card):
            out.append(x)
    hostile = card.aura_hostile
    return [x for x in out if (x.controller is not p) == hostile]


def choose_host(game, p, card):
    from .engine import perm_value
    cands = hosts(game, p, card)
    if not cands:
        return None
    return max(cands, key=lambda x: perm_value(x) - (0.5 * len(x.auras) if not card.aura_hostile else 0))


_BASIC_COLOR = {"Plains": "W", "Island": "U", "Swamp": "B", "Mountain": "R", "Forest": "G"}


def attach(game, aura, host):
    aura.attachment_timestamp = game.next_effect_timestamp()
    aura.aura_host = host
    host.auras.append(aura)
    game.log(f"{aura.card.name} enchants {host.card.name}", aura.controller)
    _set_land_type(host)
    from . import becomes
    becomes.attached(game, aura, host)


def detach(aura):
    host = aura.aura_host
    if host is not None and aura in host.auras:
        host.auras.remove(aura)
        _set_land_type(host)
    aura.aura_host = None


def _set_land_type(host):
    """"Enchanted land is an Island": the land becomes that basic type and loses its other abilities while the
    Aura stays (the newest such Aura wins)."""
    import dataclasses
    kinds = [f[10:] for a in host.auras for f in a.card.aura_flags if f.startswith("land_type:")]
    two = any("grant_two" in a.card.aura_flags for a in host.auras)
    base = getattr(host, "pre_aura_card", None)
    if kinds or two:
        if base is None:
            host.pre_aura_card = base = host.card
        card = base
        if kinds:
            card = dataclasses.replace(card, produces=frozenset({_BASIC_COLOR[kinds[-1]]}), subtypes=frozenset({kinds[-1]}),
                                       activated=[], triggers=[], restricted_produces=frozenset())
        if two:                          # "{T}: Add two mana of any one color"
            card = dataclasses.replace(card, produces=frozenset("WUBRG"), mana_amount=2)
        host.card = card
    elif base is not None:
        host.card = base
        host.pre_aura_card = None


def granted_mana(perm) -> frozenset:
    """Colours an Aura lets its land tap for ("Enchanted land has "{T}: Add one mana of any color."")."""
    out = frozenset()
    for a in perm.auras:
        for f in a.card.aura_flags:
            if f.startswith("grant_mana:"):
                out |= frozenset(f[11:])
    return out


def blocks_untap(perm) -> bool:
    return any("no_untap" in a.card.aura_flags for a in perm.auras)


def stops_combat(perm) -> bool:
    return any("cant_attack_block" in a.card.aura_flags for a in perm.auras)


def stops_attack(perm) -> bool:
    """"Can't attack you" on an opponent's Aura, or an Aura that says it can't attack at all."""
    return any("cant_attack" in a.card.aura_flags or "cant_attack_you" in a.card.aura_flags and a.controller is not perm.controller
               for a in perm.auras)


def stops_block(perm) -> bool:
    return any("cant_block" in a.card.aura_flags for a in perm.auras)


def must_attack(perm) -> bool:
    return any("must_attack" in a.card.aura_flags for a in perm.auras)


def resolve(game, p, eff, target, item):
    source = item.source if item is not None else None
    if eff.kind == "tap_host":
        host = getattr(source, "aura_host", None)
        if host is not None:
            host.tapped = True
            game.log(f"taps {host.card.name}", p)
    elif eff.kind == "attach_self":
        if target is None and eff.target == "prev":     # "create a 1/1 Soldier token, then attach ~ to it"
            target = next((x for x in reversed(p.battlefield) if x.card.is_token and x.is_creature), None)
        if source is not None and source in p.battlefield and target is not None and target in p.battlefield:
            source.attached_to = target
            game.log(f"{source.card.name} attaches to {target.card.name}", p)
