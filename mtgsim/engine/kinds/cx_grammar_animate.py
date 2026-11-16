"""The cx_animate kind (see mtgsim.cx_grammar_animate)."""
from ..state import Permanent
from . import kind

_LAND_TYPES = {"Plains", "Island", "Swamp", "Mountain", "Forest", "Desert", "Gate", "Lair", "Locus", "Mine",
               "Power-Plant", "Tower", "Urza's", "Cave", "Sphere", "Town", "Planet"}


@kind("cx_animate")
def animate(game, p, eff, target, item=None, **_):
    from ...cards import Activated
    if not isinstance(target, Permanent) or target not in target.controller.battlefield:
        return
    d = eff.data
    eot = d["eot"]
    if d.get("linked"):
        _linked(game, p, eff, target, item)
        return
    if d.get("subtypes_only"):
        _subtypes_only(game, target, d, eot)
        return
    if d.get("types_only"):         # "becomes an artifact in addition to its other types"
        game.add_continuous_effect(target, "add_types", types=set(d["types"]), until_eot=eot)
        return
    if "pt" in d:
        pt = (target.card.cmc, target.card.cmc) if d.get("pt_mv") else d["pt"]      # "each equal to its mana value"
        target.animated = Activated("animate", {}, pt[0], pt[1], frozenset(d.get("keywords", ())),
                                    subtypes=frozenset(d["subtypes"]), text="" if eot else "permanent")
    types, subtypes = set(d["types"]), set(d["subtypes"])
    if d.get("addition"):
        game.add_continuous_effect(target, "add_types", types=types, subtypes=target.card.subtypes | subtypes,
                                   until_eot=eot)
        return
    from ...permanent_templates import _SUBTYPE_TYPES
    kept = {t.lower() for t in types & set(target.card.types)} - {"creature"}
    subtypes |= {s for s in target.card.subtypes if kept & set(_SUBTYPE_TYPES.get(s.lower(), ()))}   # a Vehicle stays one
    keep = d.get("still")
    if keep and keep in target.card.types:
        types.add(keep)
        if keep == "Land":
            subtypes |= {s for s in target.card.subtypes if s in _LAND_TYPES}
        else:
            subtypes |= {s for s in target.card.subtypes}
    game.add_continuous_effect(target, "set_types", types=types, subtypes=subtypes, until_eot=eot)


def _subtypes_only(game, target, d, eot):
    """"becomes a Dragon [with base power and toughness 4/4]": a creature's creature types are replaced (or added
    to, "in addition to its other types"); its card types stay. A noncreature can't have creature types, so
    nothing happens to it (rule 205.3d)."""
    from ...cards import Activated
    from ...permanent_templates import _SUBTYPE_TYPES
    if not target.is_creature:
        return
    new = set(d["subtypes"])
    if "pt" in d:
        target.animated = Activated("animate", {}, d["pt"][0], d["pt"][1], frozenset(d.get("keywords", ())),
                                    subtypes=frozenset(new), text="" if eot else "permanent")
    if d.get("addition"):
        game.add_continuous_effect(target, "add_subtypes", subtypes=new, until_eot=eot)
        return
    kept = {s for s in target.card.subtypes if "creature" not in _SUBTYPE_TYPES.get(s.lower(), ("creature",))}
    game.add_continuous_effect(target, "set_subtypes", subtypes=new | kept, until_eot=eot)


def _linked(game, p, eff, target, item):
    """The animation tied to its source's "for as long as" duration (cx_statics._linked_animate): every change is a
    continuous effect sourced from ~ (the P/T as layer-7b base P/T, not ``animated``), linked to the duration."""
    from ...cx_statics import link_effect
    from ...permanent_templates import _SUBTYPE_TYPES
    d = eff.data
    src = item.source if item is not None and isinstance(getattr(item, "source", None), Permanent) else None
    if src is None or src not in src.controller.battlefield:
        return

    def add(op, **kw):
        link_effect(game, game.add_continuous_effect(target, op, source=src, **kw), d["linked"], p)

    types, subtypes = set(d["types"]), set(d["subtypes"])
    if d.get("addition"):
        add("add_types", types=types, subtypes=target.card.subtypes | subtypes)
    else:
        kept = {t.lower() for t in types & set(target.card.types)} - {"creature"}
        subtypes |= {s for s in target.card.subtypes if kept & set(_SUBTYPE_TYPES.get(s.lower(), ()))}
        keep = d.get("still")
        if keep and keep in target.card.types:
            types.add(keep)
            subtypes |= {s for s in target.card.subtypes if keep != "Land" or s in _LAND_TYPES}
        add("set_types", types=types, subtypes=subtypes)
    if "pt" in d:
        pt = (target.card.cmc, target.card.cmc) if d.get("pt_mv") else d["pt"]
        add("set_base", power=pt[0], toughness=pt[1])
    for kw in d.get("keywords", ()):
        add("grant", keyword=kw)
