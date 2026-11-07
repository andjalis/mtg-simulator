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
    m = re.search(r" with ([a-z ,]+)$", t)
    if m and not m[1].startswith("base "):
        kws = keyword_list(m[1])
        if not kws:
            return None
        data["keywords"] = tuple(kws)
        t = t[:m.start()]
    m = re.search(r" with base power and toughness (\d+)/(\d+)$", t, re.I)
    if m:
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
    if not words or words[-1].lower() != ("creatures" if plural else "creature"):
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


@verb(r"becomes? (.+)", heads=("become", "becomes"), subjects=("permanent", "group"))
def becomes(m, clause):
    if clause.duration not in ("eot", ""):
        return None
    data = parse_animation(m[1], plural=clause.verb.startswith("become ") and clause.subject.kind == "group")
    if data is None:
        return None
    data["eot"] = clause.duration == "eot"
    parts = [Part("cx_animate", data=dict(data, side="mine"))]
    if "colors" in data:
        parts.append(Part("cx_color", data={"colors": data["colors"], "eot": data["eot"], "side": "mine",
                                            "op": "add_colors" if data.get("add_colors") else "set_colors"}))
    return parts
