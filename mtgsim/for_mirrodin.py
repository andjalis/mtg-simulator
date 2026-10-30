"""For Mirrodin! (The Brothers' War): "When this Equipment enters the battlefield, create a
2/2 red Rebel creature token, then attach this to that token."

The keyword line (its reminder text rides in parentheses the face parser strips) becomes an
enters-the-battlefield trigger, exactly like amplify. Resolving it creates the Rebel through
the shared token foundation and attaches the Equipment by the same ``attached_to`` assignment
the living-weapon path uses, so the Rebel immediately gets the equip bonus and the normal
equip ability can move the Equipment later.

Recorded simplification: the token is always created and always attached (no decline), and
the attachment does not re-check protection or "can't be equipped" restrictions.
"""
from __future__ import annotations


def _e(kind, amount=1, **kw):
    from .cards import Effect
    return Effect(kind, amount, **kw)


EFFECT_PATTERNS = [
    (r"for mirrodin!", lambda m: _e("for_mirrodin")),
]

TRIGGERS = [
    (r"(For Mirrodin!)", ("etb",)),
]


def for_mirrodin(game, p, eff, item):
    """Create the Rebel, then attach the entering Equipment to it."""
    from .engine.state import Permanent
    src = item.source if item is not None else None
    if not isinstance(src, Permanent) or src not in p.battlefield:
        return
    before = {id(x) for x in p.battlefield}
    game.create_token(p, _e("token", 1, data={"name": "Rebel", "power": 2, "toughness": 2,
                                             "colors": frozenset("R")}))
    rebels = [x for x in p.battlefield if id(x) not in before and x.is_creature]
    if rebels:
        src.attached_to = rebels[-1]
        game.log(f"attaches {src.card.name} to the Rebel", p)
