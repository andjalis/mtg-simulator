"""Prepare (Secrets of Strixhaven): "Target creature becomes prepared. (Only creatures with
prepare spells can become prepared.)"

The engine already carries the payload: a creature that "~ enters prepared" carries its
prepare spell on ``card.back`` and ``perm.prepared`` lets its controller cast a copy of that
spell once (engine/costs.py, play.py). This module adds the *becomes prepared* effects that
flip that flag on creatures already on the battlefield: single-target prepared / unprepared,
and the all-creatures wording (Codie). The reminder text rides in parentheses the face
parser strips.

The current card database holds no creature with a prepare spell, so the flag is inert here;
it matters as soon as Prepare creatures are added. "Becomes unprepared" clears the flag
(only meaningful once a creature was prepared).

Recorded simplifications: Hexhaven Dueling Arena's "creature that attacked this turn"
restriction is dropped (any creature can be targeted); Codie's "Whenever you cast a prepared
spell" trigger is not built — the cast event cannot see the prepared variant kind (see the
cross-area note in this batch's report).
"""
from __future__ import annotations

import re


def _e(kind, amount=1, **kw):
    from .cards import Effect
    return Effect(kind, amount, **kw)


EFFECT_PATTERNS = [
    (r"target creature becomes prepared", lambda m: _e("prepare", target="creature",
                                                       data={"prepared": True})),
    (r"target creature becomes unprepared", lambda m: _e("prepare", target="creature",
                                                        data={"prepared": False})),
    (r"each creature you control becomes prepared", lambda m: _e("prepare_all")),
    (r"it becomes unprepared", lambda m: _e("prepare", target="prev", data={"prepared": False})),
]

SUBS = [
    (re.compile(r"target creature that attacked this turn becomes prepared", re.I),
     "target creature becomes prepared"),
]


def prepare(game, p, eff, target):
    """Set or clear the target's prepared flag (creatures with a prepare spell only)."""
    from .engine.state import Permanent
    if not isinstance(target, Permanent) or not target.is_creature \
            or target not in target.controller.battlefield:
        return
    if eff.data.get("prepared"):
        if target.card.back is None:      # "only creatures with prepare spells"
            return
        target.prepared = True
        game.log(f"{target.card.name} becomes prepared", p)
    else:
        target.prepared = False
        game.log(f"{target.card.name} becomes unprepared", p)


def prepare_all(game, p, eff):
    """Each of the controller's creatures with a prepare spell becomes prepared."""
    for perm in list(p.creatures):
        if perm.card.back is not None:
            perm.prepared = True
    game.log("prepares each creature they control", p)
