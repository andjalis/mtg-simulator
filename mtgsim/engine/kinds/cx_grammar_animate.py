"""The cx_animate kind (see mtgsim.cx_grammar_animate)."""
from ..state import Permanent
from . import kind

_LAND_TYPES = {"Plains", "Island", "Swamp", "Mountain", "Forest", "Desert", "Gate", "Lair", "Locus", "Mine",
               "Power-Plant", "Tower", "Urza's", "Cave", "Sphere", "Town", "Planet"}


@kind("cx_animate")
def animate(game, p, eff, target, **_):
    from ...cards import Activated
    if not isinstance(target, Permanent) or target not in target.controller.battlefield:
        return
    d = eff.data
    eot = d["eot"]
    if "pt" in d:
        target.animated = Activated("animate", {}, d["pt"][0], d["pt"][1], frozenset(d.get("keywords", ())),
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
