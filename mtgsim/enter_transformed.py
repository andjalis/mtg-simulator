"""Returning a dead or departed card to the battlefield, optionally transformed (#635).

    When this creature dies, return it to the battlefield transformed under your control.       (Harvest Hand)
    When enchanted creature dies, return this card to the battlefield transformed under your control.
                                                                                                (Skin Invasion)

"it" / "this card" / "~" is the card the trigger's own permanent became (CR 400.7), found where it went
(``Permanent.last_destination``), as "return it to its owner's hand" already does (kinds/permanents._from_graveyard).
Transformed: the back face enters (only its own enter abilities apply) and remembers its front, so it transforms
back and goes to a graveyard as the physical card. "Under your control" is the trigger's controller, "under its
owner's control" the owner. The delayed "at the beginning of the next end step" forms are left to cx_delay.
"""
from __future__ import annotations

EFFECT_PATTERNS = [
    (r"return (?P<obj>it|this card|~) to the battlefield (?P<tf>transformed )?(?P<tap>tapped )?"
     r"under (?P<who>your|its owner's) control", lambda m: _return(m)),
]


def _return(m):
    from .cards import Effect
    it = m["obj"].lower() == "it"
    return Effect("return_self_bf", target="prev" if it else "none",
                  data={"transformed": bool(m["tf"]), "tapped": bool(m["tap"]), "owner": m["who"].lower() != "your",
                        "it": it})


def _departed(obj):
    from .engine.state import Permanent
    return isinstance(obj, Permanent) and obj not in obj.controller.battlefield


def resolve(game, p, eff, item, target=None):
    """"this card" / "~" is the source; "it" is the previous object if it left the battlefield (Come Back Wrong's
    destroyed creature), else the permanent the trigger fired on (an Aura's "When enchanted creature dies"), else
    the source ("When this creature dies")."""
    source = item.source if item is not None else None
    if eff.data.get("it"):
        context = getattr(item, "context", None)
        perm = next((o for o in (target, context, source) if _departed(o)), None)
    else:
        perm = source if _departed(source) else None
    if perm is None:
        return          # nothing that left the battlefield for "it" to name
    card = getattr(perm, "front", None)
    dest = getattr(perm, "last_destination", None)
    zone = perm.owner.graveyard if dest == "graveyard" else perm.owner.exile if dest == "exile" else None
    if zone is None or card is None or card.is_token or card not in zone:
        return
    controller = perm.owner if eff.data.get("owner") else p
    face = getattr(card, "definition", card)
    if eff.data.get("transformed"):
        if face.back is None:
            return      # no back face: it stays where it is (CR 712.14a)
        zone.remove(card)
        new = game.enter_battlefield(controller, face.back, tapped=eff.data.get("tapped", False), physical_card=card)
        if new is not None:
            new.front_face = face
            game.log(f"{face.name} returns transformed as {face.back.name}", controller)
            _just_made(game, new)
        return
    zone.remove(card)
    new = game.enter_battlefield(controller, face, tapped=eff.data.get("tapped", False), physical_card=card)
    if new is not None:
        game.log(f"{face.name} returns to the battlefield", controller)
        _just_made(game, new)


def _just_made(game, perm):
    """The returned permanent is a new object: a following "it" in the same resolution names it (Retched Wretch's
    "... and it loses all abilities"), the way resolve_top hands a just-created token to the next effect."""
    game._token_serial = getattr(game, "_token_serial", 0) + 1
    game._last_token = perm
