"""Effects that set what a creature is: base power and toughness, switching, and "loses all abilities and becomes
a 1/1 blue Frog", until end of turn or for as long as an Aura stays attached.

    Target creature has base power and toughness 1/1 until end of turn.
    Switch target creature's power and toughness until end of turn.
    Until end of turn, target creature loses all abilities and becomes a blue Frog with base power and toughness 1/1.
    Enchanted creature loses all abilities and is a blue Frog creature with base power and toughness 1/1.   (an Aura)

Small bases (2/2 or less) are aimed at an opponent's creature, bigger ones at the caster's. "Loses all abilities"
removes keywords only (recorded on the card). Uses the layered effects in continuous.py.
"""
from __future__ import annotations

import re

KINDS = {"set_base", "switch_pt", "frog", "lose_kw", "half_life"}
_COLOR = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_FROG = r"loses all abilities and (?:becomes|is) an? (white|blue|black|red|green) (\w+)(?: creature)? with base power and " \
        r"toughness (\d+)/(\d+)"


def _effect(kind, target, data, flt=""):
    from .cards import Effect
    return Effect(kind, target=target, filter=flt, data=data)


def _base(m):
    p, t = int(m[1]), int(m[2])
    small = p + t <= 4
    return _effect("set_base", "creature" if small else "creature_mine", {"pt": (p, t)}, "opp" if small else "")


EFFECT_PATTERNS = [
    (r"target creature has base power and toughness (\d+)/(\d+) until end of turn", _base),
    (r"(?:that|target) creature loses (flying|indestructible|first strike|trample|reach|hexproof|deathtouch) until end of turn",
     lambda m: _effect("lose_kw", "prev" if m[0].lower().startswith("that") else "creature", {"keyword": m[1].lower()},
                       "" if m[0].lower().startswith("that") else "opp")),
    (r"switch target creature's power and toughness until end of turn",
     lambda m: _effect("switch_pt", "creature_mine", {})),
    (rf"until end of turn, target creature {_FROG}",
     lambda m: _effect("frog", "creature", {"color": _COLOR[m[1].lower()], "type": m[2].capitalize(),
                                            "pt": (int(m[3]), int(m[4]))}, "opp")),
]


def parse_aura_line(line: str, extra: dict) -> bool:
    """"Enchanted creature loses all abilities and is a blue Frog creature with base power and toughness 1/1." """
    m = re.fullmatch(rf"Enchanted creature {_FROG}\.", line)
    if not m:
        return False
    extra["aura_flags"] = extra.get("aura_flags", frozenset()) | {"loses_abilities"}
    extra["aura_becomes"] = (_COLOR[m[1].lower()], m[2].capitalize(), int(m[3]), int(m[4]))
    extra.setdefault("_approx", []).append("loses all abilities: only keywords are removed")
    return True


def _become(game, target, color, sub, pt, *, source=None, until_eot=False):
    game.add_continuous_effect(target, "set_base", power=pt[0], toughness=pt[1], source=source, until_eot=until_eot)
    game.add_continuous_effect(target, "set_colors", colors=frozenset({color}), source=source, until_eot=until_eot)
    game.add_continuous_effect(target, "set_subtypes", subtypes=frozenset({sub}), source=source, until_eot=until_eot)


def attached(game, aura, host):
    """An Aura that makes its creature something else: the effects last while the Aura stays (its source)."""
    becomes = aura.card.aura_becomes
    if becomes:
        _become(game, host, becomes[0], becomes[1], becomes[2:], source=aura)


def resolve(game, p, eff, target, item):
    from .engine.state import Permanent
    if eff.kind == "half_life":                 # Quietus Spike: rounded up
        foe = game.opponent(p)
        game.change_life(foe, -((foe.life + 1) // 2), "half their life")
        return
    if not isinstance(target, Permanent) or target not in target.controller.battlefield:
        return
    if eff.kind == "set_base":
        game.add_continuous_effect(target, "set_base", power=eff.data["pt"][0], toughness=eff.data["pt"][1], until_eot=True)
    elif eff.kind == "lose_kw":
        game.add_continuous_effect(target, "remove", keyword=eff.data["keyword"], until_eot=True)
    elif eff.kind == "switch_pt":
        game.add_continuous_effect(target, "switch", until_eot=True)
    elif eff.kind == "frog":
        _become(game, target, eff.data["color"], eff.data["type"], eff.data["pt"], until_eot=True)
        for kw in [k for k in target.card.keywords | target.temp_kw | target.perm_kw]:
            game.add_continuous_effect(target, "remove", keyword=kw, until_eot=True)
    game.log(f"{target.card.name} is now {target.power}/{target.toughness}", p)
