"""Damage modifiers over a source filter and a recipient filter:

    If a source would deal damage to a permanent or player, it deals double that damage to that permanent or player
    instead.                                                                              (Furnace of Rath)
    If a source you control would deal damage to a permanent or player, it deals triple that damage instead.
    If a creature you control would deal damage to a permanent or player, it deals double that damage instead.
    If a red instant or sorcery spell you control would deal damage, it deals double that damage instead.
    If a Giant source you control would deal damage to a permanent or player, it deals double that damage ...
    If a Lizard, Mouse, Otter, or Raccoon you control would deal damage to a permanent or player, it deals that much
    damage plus 1 to that permanent or player instead.
    If a source would deal damage to a permanent or player, it deals half that damage, rounded down, ... instead.
    Hellbent — As long as you have no cards in hand, if a source you control would deal damage ..., it deals ...

A rule is ``advanced_rules["cx_damage"]``: ``src`` (who controls the source, ``other``, and color / type / subtype /
spell-only alternatives), ``to`` ("any", "opp_side", "opp", "players"), ``op`` (("mul", k), ("add", n) or
("half", rounding)), ``cond`` (a ``cx_condlib`` code read from the static's source) and ``combat`` (None or False).
``modify`` runs from ``Game.deal_damage`` right after the older "plus N" statics (``that_much.damage_amount``).
When several apply, the player being dealt damage (or the controller of the permanent) picks the order (rule
616.1); the order dealing the least damage is used.
"""
from __future__ import annotations

import itertools
import re

_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_TYPES = ("artifact", "creature", "enchantment", "planeswalker", "instant", "sorcery", "land", "battle")
_TO = {None: "any", "a permanent or player": "any", "an opponent or a permanent an opponent controls": "opp_side",
       "an opponent": "opp", "a player": "players", "an opponent or a creature an opponent controls": "opp_side"}
_LINE = re.compile(
    r"(?:[A-Z][\w' ]* — )?(?:As long as (?P<al>.+?), i|I)f (?P<src>.+?) would deal (?P<nc>noncombat )?damage"
    r"(?: to (?P<to>.+?))?, it deals (?P<op>double that damage|triple that damage|that much damage plus (?P<n>\d+)|"
    r"half that damage, rounded (?P<round>down|up))(?: to that (?:permanent or player|player|creature))? instead\.")


def _source(text: str):
    """The source filter, or None: who controls it, other, and any-of alternatives."""
    spec: dict = {"ctl": None, "other": False, "spell": False, "alts": []}
    m = re.fullmatch(r"(.+?) you control", text)
    if m:
        spec["ctl"], text = "you", m[1]
    m = re.fullmatch(r"(?:a|an|another) (.+)", text)
    if not m:
        return None
    spec["other"] = text.startswith("another ")
    text = m[1]
    m = re.fullmatch(r"(.+?) (source|spell)", text)
    if m:
        text, spec["spell"] = m[1], m[2] == "spell"
    elif text in ("source", "spell"):
        spec["spell"] = text == "spell"
        return spec
    words = [w for w in re.split(r", or |, | or ", text) if w]
    alt: dict = {}
    for word in words:
        # "red instant or sorcery": one color qualifies a type list
        parts = word.split()
        for part in parts:
            low = part.lower()
            if low in _COLORS:
                alt.setdefault("colors", []).append(_COLORS[low])
            elif low in _TYPES:
                alt.setdefault("types", []).append(low)
            elif part[:1].isupper() and part.isalpha():
                alt.setdefault("subs", []).append(part)
            else:
                return None
    spec["alts"] = [alt]
    return spec


def parse_line(line: str, st) -> bool:
    m = _LINE.fullmatch(line)
    if not m or not st.types or "Instant" in st.types or "Sorcery" in st.types:
        return False
    src = _source(m["src"])
    to = _TO.get(m["to"])
    if src is None or to is None:
        return False
    if m["op"].startswith("double"):
        op = ("mul", 2)
    elif m["op"].startswith("triple"):
        op = ("mul", 3)
    elif m["n"]:
        op = ("add", int(m["n"]))
    else:
        op = ("half", m["round"])
    cond = ""
    if m["al"]:
        from .cx_condlib import as_static
        cond = as_static(m["al"])
        if not cond:
            return False
    rule = {"src": src, "to": to, "op": op, "cond": cond, "combat": False if m["nc"] else None}
    rules = st.extra.setdefault("advanced_rules", {})
    rules["cx_damage"] = rules.get("cx_damage", ()) + (rule,)
    return True


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

def _source_ok(spec, source, controller, owner, holder) -> bool:
    from .engine.state import Permanent
    if spec["ctl"] == "you" and controller is not owner:
        return False
    if spec["other"] and source is holder:
        return False
    is_perm = isinstance(source, Permanent)
    if spec["spell"] and is_perm:
        return False
    card = source.card if is_perm else source
    if card is None:
        return False
    for alt in spec["alts"]:
        colors = alt.get("colors", ())
        types = alt.get("types", ())
        subs = alt.get("subs", ())
        card_types = {t.lower() for t in card.types}
        if colors and not any(c in card.colors for c in colors):
            continue
        if types and not any(t in card_types for t in types):
            continue
        if subs and not any(s in card.subtypes for s in subs):
            continue
        return True
    return not spec["alts"]


def _to_ok(to, target, owner, game) -> bool:
    from .engine.state import Permanent, Player
    if to == "any":
        return True
    if to == "players":
        return isinstance(target, Player)
    opp = game.opponent(owner)
    if to == "opp":
        return target is opp
    return target is opp or isinstance(target, Permanent) and target.controller is opp


def _apply(amount, ops):
    for kind, n in ops:
        if kind == "add":
            amount += n
        elif kind == "mul":
            amount *= n
        else:
            amount = amount // 2 if n == "down" else (amount + 1) // 2
    return amount


def modify(game, target, amount: int, by, source, combat: bool) -> int:
    from .engine.state import Permanent
    ops = []
    controller = source.controller if isinstance(source, Permanent) else by
    for pl in game.players:
        for x in pl.battlefield:
            rules = x.card.advanced_rules.get("cx_damage") if x.card.advanced_rules else None
            if not rules or x.abilities_suppressed:
                continue
            for rule in rules:
                if rule["combat"] is False and combat:
                    continue
                if source is None or not _source_ok(rule["src"], source, controller, pl, x):
                    continue
                if not _to_ok(rule["to"], target, pl, game):
                    continue
                if rule["cond"]:
                    from .cx_condlib import holds_for
                    if not holds_for(x, rule["cond"]):
                        continue
                ops.append(rule["op"])
    if not ops:
        return amount
    if len(ops) == 1 or len(ops) > 5:
        return max(0, _apply(amount, ops))
    return max(0, min(_apply(amount, order) for order in itertools.permutations(ops)))
