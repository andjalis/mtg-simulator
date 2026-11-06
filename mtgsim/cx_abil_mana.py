"""Restricted mana, in general: "Spend this mana only to cast <spells> [or activate abilities [of <sources>]]".

``parse`` turns the restriction text into a ``mana_restriction`` code ``pred:<json>`` that ``Game.mana_allowed``
checks through ``allowed``. Spell terms are card types, ``legendary``, ``non<type>`` or a subtype
("dragon spells", "instant and/or sorcery spells", "dwarf, equipment, and saga spells"); the ability part is
any ability, or only abilities of sources with those terms. Ability payments carry their source as
``AbilityPayment`` (a ``str`` equal to "ability", so the rest of the payment code is untouched)."""
from __future__ import annotations

import functools
import json
import re

_TYPES = {"creature", "artifact", "enchantment", "instant", "sorcery", "land", "planeswalker", "battle"}


class AbilityPayment(str):
    """The ``spell`` argument of mana_sources / pay for an activated ability: "ability" plus its source."""

    def __new__(cls, source=None):
        obj = super().__new__(cls, "ability")
        obj.source = source
        return obj


def _singular(word: str) -> str:
    w = word.lower()
    if w.endswith("ves"):
        return w[:-3] + "f"
    if w.endswith("ies"):
        return w[:-3] + "y"
    if w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def _atoms(phrase: str):
    """Atoms for "dwarf, equipment, and saga" / "instant and/or sorcery" / "noncreature" / "a creature", or None."""
    phrase = re.sub(r"^(?:an? )", "", phrase.strip())
    phrase = re.sub(r"\s*(?:spells?|sources?|permanents?)$", "", phrase)
    out = []
    for word in re.split(r",? (?:and/or|or|and) |, ", phrase):
        w = _singular(word.strip())
        if not w or " " in w:
            return None
        if w == "legendary":
            out.append("legendary")
        elif w in ("multicolored", "monocolored", "colorless", "colored"):
            out.append("k:" + w)
        elif w in _COLOR_LETTER:
            out.append("c:" + _COLOR_LETTER[w])
        elif w.startswith("non") and w[3:] in _TYPES:
            out.append("n:" + w[3:])
        elif w in _TYPES:
            out.append("t:" + w)
        elif w.isalpha():
            out.append("s:" + w)
        else:
            return None
    return out or None


def parse(text: str):
    text = text.strip().lower()
    cast = acts = None
    m = re.fullmatch(r"(?:to cast (.+?))?(?:,? (?:or|and) )?(?:(?:to )?activate (?:abilities|equip abilities)"
                     r"(?: of (.+))?)?", text)
    if m is None or not (m[1] or "activate" in text):
        return None
    if m[1]:
        if re.search(r"\b(?:from|with|that|kicked|your|exile|graveyard|commander|face-down)\b", m[1]):
            return None
        cast = _atoms(m[1])
        if cast is None:
            return None
    if "activate" in text:
        if "equip abilities" in text:
            return None
        acts = True if not m[2] else _atoms(m[2])
        if acts is None:
            return None
    return "pred:" + json.dumps({"s": cast or [], "a": acts or []}, separators=(",", ":"))


@functools.lru_cache(maxsize=None)
def _spec(code: str) -> dict:
    return json.loads(code[5:])


def _match(atoms, card, perm=None) -> bool:
    types, subtypes = card.types, {x.lower() for x in card.subtypes}
    creature = perm.is_creature if perm is not None else "Creature" in types
    for a in atoms:
        kind, _, v = a.partition(":")
        if a == "legendary" and card.legendary:
            return True
        if kind == "t" and (creature if v == "creature" else v.capitalize() in types):
            return True
        if kind == "n" and not (creature if v == "creature" else v.capitalize() in types):
            return True
        if kind == "s" and v in subtypes:
            return True
        if kind == "c" and v in card.colors:
            return True
        if kind == "k":
            n = len(card.colors)
            if {"multicolored": n >= 2, "monocolored": n == 1, "colorless": n == 0, "colored": n >= 1}[v]:
                return True
    return False


def allowed(code: str, spell) -> bool:
    spec = _spec(code)
    if isinstance(spell, str):                      # an activated ability
        if not spec["a"]:
            return False
        if spec["a"] is True:
            return True
        source = getattr(spell, "source", None)
        return source is not None and _match(spec["a"], source.card, source)
    return bool(spec["s"]) and _match(spec["s"], spell)


# ---- mana-adding effects -------------------------------------------------------------------------------------------

_WUBRG = ["W", "U", "B", "R", "G"]
_COLOR_LETTER = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_NUMS = {"two": 2, "three": 3, "four": 4, "five": 5}


def _effect(*args, **kwargs):
    from .cards.model import Effect
    return Effect(*args, **kwargs)


def _different_colors(m):
    return _effect("add_mana", _NUMS[m["n"]], data={"colors": [], "cx_mana": "distinct"})


def _each_color_among(m):
    among = [_COLOR_LETTER[c] for c in re.findall(r"white|blue|black|red|green", m["among"] or "")]
    return _effect("add_mana", 1, data={"colors": [], "cx_mana": "among", "among": among})


def _combination(m):
    return _effect("add_mana", _NUMS[m["n"]], data={"colors": [], "cx_mana": "combo"})


def _restrict(m):
    from .cards.model import NO_MATCH
    code = parse(m["r"])
    return _effect("mana_restrict", data={"code": code}) if code else NO_MATCH


EFFECT_PATTERNS = [
    (r"spend this mana only (?P<r>.+)", _restrict),
    (r"add (?P<n>two|three|four|five) mana in any combination of colors", _combination),
    # also what ", where X is <quantity>" leaves behind (the quantity scales the amount): amount is 1, not 0
    (r"add one mana of any one color", lambda m: _effect("add_mana", 1, data={"colors": [], "choice": list(_WUBRG)})),
    (r"add \{([WUBRG])\}, \{([WUBRG])\}, or \{([WUBRG])\}",
     lambda m: _effect("add_mana", data={"colors": [], "choice": [m[1], m[2], m[3]]})),
    (r"add (?P<n>two|three|four|five) mana of different colors", _different_colors),
    (r"for each color among (?:(?P<among>[a-z, ]+?) )?permanents you control, add one mana of that color",
     _each_color_among),
]


def add_special(game, p, eff) -> bool:
    """add_mana variants the plain handler can't do: N different colors (what the hand needs most),
    one mana per colour among the permanents you control."""
    mode = eff.data.get("cx_mana")
    if mode is None:
        return False
    if mode == "distinct":
        need = {c: sum(card.mana_cost.get(c, 0) for card in p.hand) for c in _WUBRG}
        colors = sorted(_WUBRG, key=lambda c: -need[c])[:eff.amount]
    elif mode == "combo":               # any combination: each mana is the colour the hand still needs most
        need = {c: sum(card.mana_cost.get(c, 0) for card in p.hand) for c in _WUBRG}
        colors = []
        for _ in range(eff.amount):
            c = max(_WUBRG, key=lambda k: need[k])
            colors.append(c)
            need[c] -= 1
    else:
        present = {c for x in p.battlefield for c in x.card.colors}
        colors = [c for c in _WUBRG if c in present and (not eff.data["among"] or c in eff.data["among"])]
    from .engine.state import Permanent, pool_mana
    p.last_added_mana = [Permanent(pool_mana(color), p) for color in colors]
    p.pool.extend(p.last_added_mana)
    game.log(f"adds {''.join(colors)}", p)
    return True


# ---- the AI -------------------------------------------------------------------------------------------------------

def _mana_abilities(game, me):
    """(permanent, index, mana it adds, restriction code or "") for activated abilities that only add mana."""
    from .cx_abil_costs import ai_cost_ok
    from .engine.policy import perm_value
    out = []
    for perm in me.battlefield:
        for i, act in enumerate(perm.activated):
            kinds = {e.kind for e in act.effects}
            if act.kind != "ability" or "add_mana" not in kinds or not kinds <= {"add_mana", "mana_restrict"}:
                continue
            c = act.extra_costs
            if c.get("sacrifice") or c.get("discard") or c.get("life") or c.get("energy") or \
                    ((c.get("sac_self") or c.get("exile_self")) and perm_value(perm) > 1) or \
                    not ai_cost_ok(game, me, perm, c) or not game.can_activate(me, perm, i):
                continue
            adds = sum(max(1, e.amount) * max(1, len(e.data.get("colors", []))) if not e.data.get("cx_mana")
                       and not e.data.get("xq") else max(1, e.amount) for e in act.effects if e.kind == "add_mana")
            code = next((e.data["code"] for e in act.effects if e.kind == "mana_restrict"), "")
            out.append((perm, i, adds, code))
    return out


def _supply(game, me) -> int:
    return sum(getattr(s, "amount_now", None) or max(1, s.card.mana_amount) for s in game.mana_sources(me))


def boost(ai, game, me, precombat=True):
    """Before casting spells: activate a mana-adding ability (Gilded-Lotus-style rocks with a cost other than {T} alone,
    restricted mana) when it makes a spell in hand castable that isn't castable now. The mana floats until the step
    ends, so only do it when a spell it can pay for is within reach."""
    supply = _supply(game, me)
    for _ in range(4):
        wanted = [c for c in me.hand if not c.is_land and not ai._can_cast(game, me, c) and c.cmc > supply]
        if not wanted:
            return
        for perm, i, adds, code in _mana_abilities(game, me):
            reach = [c for c in wanted if c.cmc <= supply + adds and (not code or allowed(code, c))]
            if reach and game.activate_ability(me, perm, i):
                game.settle()
                supply = _supply(game, me)
                break
        else:
            return
