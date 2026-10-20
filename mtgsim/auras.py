"""Auras, and Equipment that attaches itself when it enters.

    Enchant creature / creature you control / creature or Vehicle / artifact or creature / land / permanent
    Enchanted creature gets +2/+2 and has flying.      Enchanted creature gets -3/-3.
    Enchanted creature doesn't untap during its controller's untap step.   Enchanted creature can't attack or block.
    When this Aura enters, tap enchanted creature.
    When this Equipment enters, attach it to target creature you control.

An Aura is a permanent on its caster's battlefield that is also listed in ``host.auras``. An Aura spell targets
its host: ``is_legal_host`` is the rules check (the enchant restriction, on the battlefield, and when targeting,
hexproof), ``hosts`` lists every legal target and ``choose_host`` is the casting policy. Friendly Auras (a bonus,
a keyword) go on the caster's best creature, hostile ones (a penalty, "doesn't untap", "can't attack or block") on
the opponent's best; an Aura with no host on the wanted side isn't cast. Not modelled: "you control enchanted
creature", "loses all abilities", Auras that can be moved.
"""
from __future__ import annotations

import re

KINDS = {"tap_host", "attach_self"}
_KW = ("flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|"
       "menace|reach")
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
    if re.fullmatch(r"Enchanted (?:creature|permanent) doesn't untap during its controller's untap step\.", line):
        extra["aura_flags"] = extra.get("aura_flags", frozenset()) | {"no_untap"}
        return True
    if re.fullmatch(r"Enchanted creature can't attack or block\.", line):
        extra["aura_flags"] = extra.get("aura_flags", frozenset()) | {"cant_attack_block"}
        return True
    m = re.fullmatch(rf"Enchanted creature (?:gets ([+−-])(\d+)/([+−-])(\d+))?(?:,? and |, | )?"
                     rf"(?:has ((?:{_KW})(?:(?:, | and |, and )(?:{_KW}))*))?\.", line)
    if m and (m[1] or m[5]):
        bonus = (_n(m[1], m[2]), _n(m[3], m[4])) if m[1] else (0, 0)
        kws = frozenset(k.strip() for k in re.split(r", and |, | and ", m[5])) if m[5] else frozenset()
        extra["equip_bonus"] = bonus
        extra["equip_keywords"] = kws
        return True
    return False


def finish(extra: dict):
    """After all lines are parsed: is the Aura hostile (put on the opponent's creature)?"""
    if extra.get("aura"):
        b = extra.get("equip_bonus", (0, 0))
        extra["aura_hostile"] = bool(extra.get("aura_flags")) or b[0] < 0 or b[1] < 0 or \
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

def fits(card, host, p) -> bool:
    """Whether host meets card's enchant restriction for an Aura controlled by p (no targeting rules)."""
    kinds, c = card.aura, host.card
    if kinds in ("creature", "creature you control", "creature an opponent controls"):
        ok = host.is_creature
    elif kinds == "creature or Vehicle":
        ok = host.is_creature or "Vehicle" in c.subtypes
    elif kinds == "artifact or creature":
        ok = host.is_creature or c.is_artifact
    elif kinds == "artifact creature":
        ok = host.is_creature and c.is_artifact
    elif kinds == "land":
        ok = c.is_land
    elif kinds == "artifact":
        ok = c.is_artifact
    elif kinds == "nonland permanent":
        ok = not c.is_land
    else:
        ok = True
    if kinds == "creature you control":
        ok = ok and host.controller is p
    if kinds == "creature an opponent controls":
        ok = ok and host.controller is not p
    return ok


def is_legal_host(game, p, card, host, targeted=True) -> bool:
    """Whether an Aura card controlled by p may enchant host: a permanent on the battlefield that meets the enchant
    restriction; targeted=True (casting, resolving) also applies hexproof."""
    from .engine import Permanent
    if not isinstance(host, Permanent) or host not in host.controller.battlefield:
        return False
    if not fits(card, host, p):
        return False
    return game.targetable(host, p) if targeted else True


def hosts(game, p, card) -> list:
    """Every permanent p could target with the Aura card, whichever side it is on."""
    return [x for pl in game.players for x in pl.battlefield if is_legal_host(game, p, card, x)]


def wanted_hosts(game, p, card) -> list:
    """The legal hosts on the side the policy wants: p's own for friendly Auras, the opponent's for hostile ones."""
    hostile = card.aura_hostile
    return [x for x in hosts(game, p, card) if (x.controller is not p) == hostile]


def choose_host(game, p, card):
    from .engine import perm_value
    cands = wanted_hosts(game, p, card)
    if not cands:
        return None
    return max(cands, key=lambda x: perm_value(x) - (0.5 * len(x.auras) if not card.aura_hostile else 0))


def attach(game, aura, host):
    aura.aura_host = host
    host.auras.append(aura)
    game.log(f"{aura.card.name} enchants {host.card.name}", aura.controller)


def detach(aura):
    host = aura.aura_host
    if host is not None and aura in host.auras:
        host.auras.remove(aura)
    aura.aura_host = None


def blocks_untap(perm) -> bool:
    return any("no_untap" in a.card.aura_flags for a in perm.auras)


def stops_combat(perm) -> bool:
    return any("cant_attack_block" in a.card.aura_flags for a in perm.auras)


def resolve(game, p, eff, target, item):
    source = item.source if item is not None else None
    if eff.kind == "tap_host":
        host = getattr(source, "aura_host", None)
        if host is not None:
            host.tapped = True
            game.log(f"taps {host.card.name}", p)
    elif eff.kind == "attach_self":
        if source is not None and source in p.battlefield and target is not None and target in p.battlefield:
            source.attached_to = target
            game.log(f"{source.card.name} attaches to {target.card.name}", p)
