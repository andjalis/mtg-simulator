"""Colour and type changes:

    {U}: ~ becomes the creature type of your choice until end of turn.          (Mistform Dreamer)
    {R}: ~ becomes the color of your choice until end of turn.                  (Caldera Kavu)
    {1}, {T}: Target permanent you control becomes the color of your choice.    (Alchor's Tomb, lasting)
    {U}: Target land becomes the basic land type of your choice until end of turn.   (Dream Thrush, Jinx)
    Target permanent becomes an artifact in addition to its other types until end of turn.
    It becomes an Angel in addition to its other types.

``cx_retype`` swaps the permanent's card for a changed copy. An "until end of turn" change keeps the old card in
``Permanent.copy_revert``, which the cleanup step restores (copies.revert). The controller's choices: a creature type
its other creatures share, a colour its other permanents have (an opponent's permanent gets the colour fewest of their
permanents have), the basic land type for the colour the controller's hand needs most (an opponent's land gets the
type for the colour they need least)."""
from __future__ import annotations


_BASIC = {"W": "Plains", "U": "Island", "B": "Swamp", "R": "Mountain", "G": "Forest"}
_CARD_TYPES = {"artifact": "Artifact", "enchantment": "Enchantment"}


def _effect(*args, **kwargs):
    from .cards.model import Effect
    return Effect(*args, **kwargs)


def _target(word: str):
    word = word.lower()
    if word in ("~", "this creature", "this permanent"):
        return "self", None
    if word in ("it", "that creature", "that permanent"):
        return "prev", None
    if word.startswith("target land"):
        return "land", None
    if word.startswith("target creature"):
        return "creature", None
    return "permanent", {"types_any": ["permanent"]}


def _change(what):
    def make(m):
        target, spec = _target(m["w"])
        data = {"what": what, "eot": bool(m["eot"]), "side": "mine"}
        if spec is not None:
            data["selector"] = dict(spec, controller="mine") if "you control" in m["w"].lower() else spec
        elif "you control" in m["w"].lower():
            data["selector"] = {"controller": "mine"}
        return _effect("cx_retype", target=target, data=data)
    return make


def _add_types(m):
    from .cards.model import NO_MATCH
    words = m["t"].split()
    if not words:
        return NO_MATCH
    types, subs = [], []
    for w in words:
        if w.lower() in _CARD_TYPES:
            types.append(_CARD_TYPES[w.lower()])
        elif w[:1].isupper() and w.isalpha() and w.lower() not in ("creature", "land"):
            subs.append(w)
        else:
            return NO_MATCH
    target, spec = _target(m["w"])
    data = {"what": "add", "types": types, "subs": subs, "eot": bool(m["eot"]), "side": "mine"}
    if spec is not None:
        data["selector"] = spec
    return _effect("cx_retype", target=target, data=data)


_WHO = r"(?P<w>~|it|that creature|target creature(?: you control)?|target permanent(?: you control)?)"
_EOT = r"(?P<eot> until end of turn)?"
EFFECT_PATTERNS = [
    (rf"{_WHO} becomes the creature type of your choice{_EOT}", _change("creature_type")),
    (rf"{_WHO} becomes the color of your choice{_EOT}", _change("color")),
    (rf"(?P<w>target land(?: you control)?) becomes the basic land type of your choice{_EOT}", _change("land_type")),
    (rf"{_WHO} becomes an? (?P<t>[\w ]+?) in addition to its other types{_EOT}", _add_types),
]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

def _creature_type(perm):
    from collections import Counter
    counts = Counter(s for x in perm.controller.creatures if x is not perm for s in x.card.subtypes)
    if counts:
        return counts.most_common(1)[0][0]
    return next(iter(sorted(perm.card.subtypes)), "Shapeshifter")


def _color(game, p, perm):
    from collections import Counter
    from .engine.mana import COLORS
    owner = perm.controller
    counts = Counter(c for x in owner.battlefield if x is not perm for c in x.card.colors)
    if owner is p:
        return max(COLORS, key=lambda c: (counts[c], c in perm.card.colors))
    return min(COLORS, key=lambda c: (counts[c], c in perm.card.colors))


def _land_color(game, p, perm):
    from .engine.mana import COLORS
    from .engine.policy import choose_color
    owner = perm.controller
    if owner is p:
        return choose_color(game, p)
    need = {c: sum(card.mana_cost.get(c, 0) for card in owner.hand) +
            sum(x.card.mana_cost.get(c, 0) for x in owner.battlefield) for c in COLORS}
    return min(COLORS, key=lambda c: need[c])


def retype(game, p, eff, perm):
    import dataclasses
    data = eff.data
    card = perm.card
    what = data["what"]
    if what == "creature_type":
        new = dataclasses.replace(card, subtypes=frozenset({_creature_type(perm)}) |
                                  frozenset(s for s in card.subtypes if s in ("Equipment", "Vehicle")))
        note = f"becomes a {next(iter(new.subtypes))}"
    elif what == "color":
        color = _color(game, p, perm)
        new = dataclasses.replace(card, color_override=frozenset({color}))
        note = f"becomes {color}"
    elif what == "land_type":
        if not card.is_land:
            return
        color = _land_color(game, p, perm)
        keep = frozenset(s for s in card.subtypes if s not in _BASIC.values())
        new = dataclasses.replace(card, subtypes=keep | {_BASIC[color]}, produces=frozenset({color}))
        note = f"becomes a {_BASIC[color]}"
    else:
        new = dataclasses.replace(card, types=card.types | frozenset(data["types"]),
                                  subtypes=card.subtypes | frozenset(data["subs"]))
        note = "becomes " + " ".join(data["types"] + data["subs"]) + " in addition to its other types"
    if data.get("eot") and getattr(perm, "copy_revert", None) is None:
        perm.copy_revert = card
    perm.card = new
    game.log(f"{card.name} {note}" + (" until end of turn" if data.get("eot") else ""), p)
