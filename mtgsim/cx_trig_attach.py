"""Equipment attachment heads (#538):

    Whenever ~ becomes attached to a creature, tap that creature.                       (Enormous Energy Blade)
    Whenever ~ becomes unattached from a permanent, sacrifice that permanent.         (Grafted Wargear, ...)
    Whenever ~ becomes unattached from a permanent, destroy that permanent.           (Captain's Hook)

Every change of ``Permanent.attached_to`` (equip, living weapon, "attach ~ to", the creature or the Equipment
leaving, state-based unattachment) goes through ``Permanent.__setattr__``, which calls ``moved``: it fires
``equip_unattached`` (context: the permanent it was attached to) and ``equip_attached`` (context: the new
creature) for the Equipment, so "that creature" / "that permanent" (``prev``) is that permanent. An Equipment that
leaves the battlefield while attached becomes unattached too, and its ability still triggers (ruling on Grafted
Wargear); a creature that left is no longer there to tap, destroy or sacrifice.
"""
from __future__ import annotations

TRIGGERS = [
    (r"Whenever ~ becomes attached to a creature, (.+)", ("equip_attached",)),
    (r"Whenever ~ becomes unattached from a permanent, (.+)", ("equip_unattached",)),
]


def _sac_that(m):
    from .cards.model import Effect
    return Effect("cx_sac_that", target="prev")


EFFECT_PATTERNS = [(r"sacrifice that permanent", _sac_that)]


def moved(equipment, old, new) -> None:
    """``equipment.attached_to`` changed from old to new."""
    game = getattr(getattr(equipment, "controller", None), "_game", None)
    if game is None or old is new:
        return
    if not any(t.event in ("equip_attached", "equip_unattached") for t in equipment.card.triggers):
        return
    if old is not None:
        game.fire(equipment.controller, "equip_unattached", equipment, context=old)
    if new is not None and new.is_creature:
        game.fire(equipment.controller, "equip_attached", equipment, context=new)
