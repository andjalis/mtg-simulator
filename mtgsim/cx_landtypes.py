"""Statics that change basic land types:

    Enchanted land is a Swamp.                                                   (Contaminated Ground)
    Lands you control are every basic land type in addition to their other types.  (Dryad of the Ilysian Grove)
    Each land is a Swamp in addition to its other land types.                     (Blanket of Night)
    All lands are Islands in addition to their other types.
    All Mountains are Plains.                                                     (Conversion)
    Lands you control are Plains.

Each line is ``advanced_rules["cx_landtype"]``: (scope, only, mode, types), scope "host", "mine" or "all", only a
land subtype the land must have (or ""), mode "set" (the land loses its other basic land types and makes only the
new types' mana) or "add". ``update`` (from advanced_templates.update_static) records on each land what applies,
and ``apply`` (from continuous.characteristics) rewrites its subtypes and the mana it makes."""
from __future__ import annotations

import re

_BASIC = {"Plains": "W", "Island": "U", "Swamp": "B", "Mountain": "R", "Forest": "G"}
_SING = {"plains": "Plains", "island": "Island", "islands": "Island", "swamp": "Swamp", "swamps": "Swamp",
         "mountain": "Mountain", "mountains": "Mountain", "forest": "Forest", "forests": "Forest"}
_T = r"(Plains|Islands?|Swamps?|Mountains?|Forests?)"
_LINES = [
    (re.compile(rf"Enchanted land is an? {_T}\."), "host", None, "set"),
    (re.compile(r"Lands you control are every basic land type in addition to their other types\."), "mine", None, "all"),
    (re.compile(rf"Each land is an? {_T} in addition to its other (?:land )?types\."), "all", None, "add"),
    (re.compile(rf"All lands are {_T} in addition to their other (?:land )?types\."), "all", None, "add"),
    (re.compile(rf"All {_T} are {_T}\."), "all", "only", "set"),
    (re.compile(rf"Lands you control are {_T}\."), "mine", None, "set"),
]


def parse_line(line: str, st) -> bool:
    for rx, scope, only, mode in _LINES:
        m = rx.fullmatch(line)
        if not m:
            continue
        if scope == "host" and not st.extra.get("aura"):
            return False
        if mode == "all":
            rule = (scope, "", "add", tuple(_BASIC))
        elif only:
            rule = (scope, _SING[m[1].lower()], mode, (_SING[m[2].lower()],))
        else:
            rule = (scope, "", mode, (_SING[m[1].lower()],))
        rules = st.extra.setdefault("advanced_rules", {})
        rules["cx_landtype"] = rules.get("cx_landtype", ()) + (rule,)
        return True
    return False


def update(game, board):
    from . import continuous
    sources = [(x, r) for x in board if not x.abilities_suppressed
               for r in (x.card.advanced_rules.get("cx_landtype", ()) if x.card.advanced_rules else ())]
    for perm in board:
        mods = ()
        if sources and perm.copiable_card.is_land:
            mods = tuple((r[2], r[3]) for x, r in sources
                         if (r[0] == "all" or r[0] == "mine" and x.controller is perm.controller or
                             r[0] == "host" and x.aura_host is perm)
                         and (not r[1] or r[1] in perm.copiable_card.subtypes))
        if perm.copiable_card.is_land and getattr(perm, "cx_landtype_extra", None):
            from .cx_grammar_landtype import extra      # one-shot changes ("becomes an Island until end of turn")
            mods = mods + extra(perm)
        if getattr(perm, "_cx_landtype", ()) != mods:
            perm._cx_landtype = mods
            continuous.refresh(perm)


def apply(base, mods):
    import dataclasses
    subtypes, produces = set(base.subtypes), set(base.produces)
    for mode, types in sorted(mods, key=lambda m: m[0] != "set"):
        if mode == "set":
            subtypes -= set(_BASIC)
            produces = set()
        subtypes |= set(types)
        produces |= {_BASIC[t] for t in types}
    return dataclasses.replace(base, subtypes=frozenset(subtypes), produces=frozenset(produces))
