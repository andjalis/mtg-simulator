"""Grammar verbs: type changes and animation ("becomes a 3/3 Elemental artifact creature until end of turn",
"become artifact creatures", "becomes a 2/2 Bird creature with flying in addition to its other types",
"... that's still a land"). See mtgsim/GRAMMAR.md.

The cx_animate kind (engine/kinds/cx_grammar_animate.py) sets the permanent's card types and subtypes in layer 4:
exactly the named ones ("becomes an artifact creature": it stops being anything else), the named ones added ("in
addition to its other types"), or the named ones plus its land types ("that's still a land" / "It's still a
land."). A power and toughness become its base P/T and keywords are gained, through the animation slot
(``Permanent.animated``), until end of turn or for good. Without a P/T, a creature keeps its printed one (a
Vehicle). A colour named becomes its colour (cx_color, layer 5)."""
from __future__ import annotations

import re

from .cx_grammar import Part, keyword_list, verb
from .cx_grammar_color import colors
from .permanent_templates import _SUBTYPE_TYPES

_CARD_TYPES = {"artifact": "Artifact", "enchantment": "Enchantment", "creature": "Creature"}
_COLOR_WORD = r"(?:white|blue|black|red|green|colorless)"


def _subtype(word: str):
    low = word.lower()
    if low in _SUBTYPE_TYPES and "creature" in _SUBTYPE_TYPES[low]:
        return "-".join(w.capitalize() for w in low.split("-"))
    if low.endswith("s") and low[:-1] in _SUBTYPE_TYPES and "creature" in _SUBTYPE_TYPES[low[:-1]]:
        return "-".join(w.capitalize() for w in low[:-1].split("-"))
    return None


def parse_animation(text: str, plural: bool):
    """The Part data for "[a|an] [N/N] [colours] [subtypes] [card types] creature[s] [with base power and toughness
    N/N] [with keywords] [that's still a land] [in addition to its other (colors and) types]", or None."""
    t = text.strip()
    data = {}
    m = re.search(r" in addition to (?:its|their) other (colors and types|types)$", t, re.I)
    if m:
        data["addition"] = True
        data["add_colors"] = m[1].startswith("colors")
        t = t[:m.start()]
    m = re.search(r",? that's still an? (land|planeswalker)$", t, re.I)
    if m:
        if data.get("addition"):
            return None
        data["still"] = m[1].capitalize()
        t = t[:m.start()]
    m = re.search(r" with power and toughness each equal to its mana value$", t, re.I)
    if m:           # Karn's Touch (#313): its mana value as it resolves (a permanent's mana value doesn't change)
        data.update(pt=(0, 0), pt_mv=True)
        t = t[:m.start()]
    m = re.search(r" with ([a-z ,]+)$", t)
    if m and not m[1].startswith("base ") and not m[1].startswith("power and toughness"):
        kws = keyword_list(m[1])
        if not kws:
            return None
        data["keywords"] = tuple(kws)
        t = t[:m.start()]
    m = re.search(r" with base power and toughness (\d+)/(\d+)(?:,? and |, )?([a-z ,]+)?$", t, re.I)
    if m:
        if m[3]:            # "with base power and toughness 4/4, flying, and haste"
            kws = keyword_list(re.sub(r"^and ", "", m[3]))
            if not kws or "keywords" in data:
                return None
            data["keywords"] = tuple(kws)
        data["pt"] = (int(m[1]), int(m[2]))
        t = t[:m.start()]
    if not plural:
        m = re.match(r"an? ", t, re.I)
        if not m:
            return None
        t = t[m.end():]
    m = re.match(r"(\d+)/(\d+) ", t)
    if m:
        if "pt" in data:
            return None
        data["pt"] = (int(m[1]), int(m[2]))
        t = t[m.end():]
    words = t.split()
    if words and not m and data.get("addition") and "pt" not in data and "keywords" not in data:
        added = _card_types_only(words, data, plural)
        if added is not None:
            return added
    if words and words[-1].lower() != ("creatures" if plural else "creature"):
        # "a 3/3 Golem" (no "creature", no "base"): left alone; "a Dragon with base power and toughness 4/4" reads
        return None if m else _subtypes_only(words, data, plural)
    if not words:
        return None
    cols, subs, types = [], [], ["Creature"]
    for w in words[:-1]:
        low = w.lower().rstrip(",")
        if low == "and":
            continue
        if re.fullmatch(_COLOR_WORD, low):
            cols.append(low)
        elif low.rstrip("s") in _CARD_TYPES and low.rstrip("s") != "creature":
            types.append(_CARD_TYPES[low.rstrip("s")])
        elif _subtype(w):
            subs.append(_subtype(w))
        else:
            return None
    if "and" in [w.lower() for w in words] and len(cols) < 2:
        return None
    data.update(types=tuple(types), subtypes=tuple(subs))
    if cols:
        found = colors(" and ".join(cols))
        if found is None:
            return None
        data["colors"] = "".join(sorted(found))
    if "keywords" in data and "pt" not in data:
        return None      # keywords ride on the animation slot with a P/T
    return data


_IRREGULAR = {"elves": "elf", "dwarves": "dwarf", "wolves": "wolf", "fungi": "fungus", "mercenaries": "mercenary"}


def _number_subtype(low: str, plural: bool):
    """The creature subtype for a word in the right number ("Frog" singular, "Frogs" plural), or None."""
    if plural:
        low = _IRREGULAR.get(low) or (low[:-1] if low.endswith("s") and not low.endswith("ss") else "")
    found = _subtype(low) if low else None
    return found if found and found.lower() == low else None


def _card_types_only(words, data, plural):
    """"[a|an] [colours] artifact [and enchantment] in addition to its other types": card types added, nothing
    else changes (it doesn't become a creature)."""
    cols, types = [], []
    for w in words:
        low = w.lower().rstrip(",")
        if low == "and":
            continue
        if re.fullmatch(_COLOR_WORD, low) and low != "colorless":
            cols.append(low)
        elif (low[:-1] if plural and low.endswith("s") else low) in ("artifact", "enchantment"):
            types.append(_CARD_TYPES[low[:-1] if plural and low.endswith("s") else low])
        else:
            return None
    if not types or len(cols) > 1 or data.get("add_colors") != bool(cols):
        return None              # a colour only with "in addition to its other colors and types"
    data.update(types=tuple(types), subtypes=(), types_only=True)
    if cols:
        from .cx_grammar_color import colors as read_colors
        data["colors"] = "".join(sorted(read_colors(cols[0])))
    return data


def _subtypes_only(words, data, plural):
    """"[a] [colours] Dragon [Illusion] [with base power and toughness N/N]": no card type named, so only the
    creature types change (rule 205.1b: a creature that "becomes a Dragon" stops being its other creature types and
    keeps its card types); with "in addition to its other types" the Dragon type is added."""
    cols, subs = [], []
    for w in words:
        low = w.lower().rstrip(",")
        if low == "and":
            continue
        if re.fullmatch(_COLOR_WORD, low):
            cols.append(low)
        elif _number_subtype(low, plural):
            subs.append(_number_subtype(low, plural))
        else:
            return None
    if not subs or "keywords" in data and "pt" not in data or ("and" in [w.lower() for w in words]) != (len(cols) >= 2):
        return None              # "and" only between colours ("blue and red Dragon")
    if data.get("add_colors") and not cols:
        return None                  # "in addition to its other colors and types" names a colour
    data.update(types=(), subtypes=tuple(subs), subtypes_only=True)
    if cols:
        from .cx_grammar_color import colors as read_colors
        found = read_colors(" and ".join(cols))
        if found is None:
            return None
        data["colors"] = "".join(sorted(found))
    return data


@verb(r"becomes? (.+)", heads=("become", "becomes"), subjects=("permanent", "group"))
def becomes(m, clause):
    if clause.duration not in ("eot", ""):
        return None
    data = parse_animation(m[1], plural=clause.verb.startswith("become ") and clause.subject.kind == "group")
    if data is None:
        return None
    data["eot"] = clause.duration == "eot"
    # "becomes a white Rabbit with base power and toughness 0/1" shrinks a creature: aim it at theirs.
    side = "theirs" if data.get("subtypes_only") and "pt" in data and sum(data["pt"]) <= 2 else \
        "type" if data.get("subtypes_only") and "pt" not in data else "mine"      # see type_side
    parts = [Part("cx_animate", data=dict(data, side=side))]
    if "colors" in data:
        parts.append(Part("cx_color", data={"colors": data["colors"], "eot": data["eot"], "side": "mine",
                                            "op": "add_colors" if data.get("add_colors") else "set_colors"}))
    return parts


def type_side(game, eff) -> str:
    """The side for a bare creature-type change ("target creature becomes a Coward until end of turn"): "theirs"
    when the source or a permanent in play restricts that type ("Cowards can't block Warriors"), else "mine"."""
    words = "|".join(re.escape(s) for s in eff.data.get("subtypes", ()))
    if not words:
        return "mine"
    rx = re.compile(rf"\b(?:{words})s? (?:can't|don't|doesn't|get -|lose)", re.I)
    source = getattr(game, "target_source", None)
    texts = [getattr(getattr(source, "card", source), "oracle", "") or ""]
    texts += [x.card.oracle or "" for pl in game.players for x in pl.battlefield]
    return "theirs" if any(rx.search(t) for t in texts) else "mine"
