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
       "menace|reach|protection from (?:white|blue|black|red|green)")
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
    m = re.fullmatch(r"Enchanted (?:creature|permanent) loses all abilities(?: and doesn't untap during its controller's "
                     r"untap step)?\.", line)
    if m:
        flags = {"loses_abilities"} | ({"no_untap"} if "untap" in line else set())
        extra["aura_flags"] = extra.get("aura_flags", frozenset()) | flags
        extra.setdefault("_approx", []).append("loses all abilities: only keywords are removed")
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

def can_attach(game, p, card, host, *, source=None, targeting=True):
    """Attachment legality is independent of the AI's friendly/hostile host preference."""
    from .engine.state import protected_from
    if host not in host.controller.battlefield:
        return False
    kinds = card.aura
    if card.advanced_rules.get("aura_selector"):
        from .permanent_templates import matches
        return matches(game, host, card.advanced_rules["aura_selector"], p, source) and not protected_from(host, source or card) and (not targeting or game.targetable(host, p, source or card))
    ok = (host.is_creature if "creature" in kinds and "artifact" not in kinds and "Vehicle" not in kinds
          else host.is_creature or host.card.is_artifact if kinds == 'artifact or creature'
          else host.is_creature or 'Vehicle' in host.card.subtypes if kinds == 'creature or Vehicle'
          else host.card.is_land if kinds == 'land'
          else host.card.is_artifact if kinds == 'artifact'
          else not host.card.is_land if kinds == 'nonland permanent' else bool(kinds))
    if kinds == 'creature you control' and host.controller is not p:
        ok = False
    if kinds == 'creature an opponent controls' and host.controller is p:
        ok = False
    return ok and not protected_from(host, source or card) and (not targeting or game.targetable(host, p, source or card))


def hosts(game, p, card) -> list:
    """The permanents the Aura card could enchant when p casts it."""
    kinds = card.aura
    opp = game.opponent(p)
    pool = [x for pl in game.players for x in pl.battlefield]
    out = []
    for x in pool:
        c = x.card
        if card.advanced_rules.get("aura_selector") and not can_attach(game, p, card, x):
            continue
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


def attach(game, aura, host):
    aura.attachment_timestamp = game.next_effect_timestamp()
    aura.aura_host = host
    host.auras.append(aura)
    if aura.card.advanced_rules.get("aura_control"):
        from .counter_mechanics import add_control
        add_control(game, host, aura.controller, source=aura)
        aura.controlled_host = host
    game.log(f"{aura.card.name} enchants {host.card.name}", aura.controller)


def detach(aura):
    host = aura.aura_host
    if host is not None and aura in host.auras:
        host.auras.remove(aura)
    aura.aura_host = None
    if getattr(aura, "controlled_host", None) is not None:
        from .counter_mechanics import expire_source_control
        game = aura.controller._game
        expire_source_control(game)
        aura.controlled_host = None


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
        if target is None and eff.target == "prev":     # "create a 1/1 Soldier token, then attach ~ to it"
            target = next((x for x in reversed(p.battlefield) if x.card.is_token and x.is_creature), None)
        if source is not None and source in p.battlefield and target is not None and target in p.battlefield:
            source.attached_to = target
            game.log(f"{source.card.name} attaches to {target.card.name}", p)
