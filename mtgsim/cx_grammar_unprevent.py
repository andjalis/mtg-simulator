"""Riders that make one effect's damage unpreventable (#519):

    ~ deals 6 damage to that permanent or player and the damage can't be prevented.   (Lightning Surge)

The damage effects get data["unpreventable"]; the damage handler deals them with prevention switched off
(Game.unpreventable_now, read where Game.deal_damage decides whether damage is preventable)."""
from __future__ import annotations

import dataclasses

from .cx_grammar import rider


@rider(r"(?P<body>.+ damage .+?),? and the damage can't be prevented")
def unpreventable(m, inner):
    effects = inner(m["body"])
    if not effects or not any(e.kind == "damage" for e in effects) or \
            any(e.kind not in ("damage", "damage_each_player") for e in effects):
        return None
    return [dataclasses.replace(e, data=dict(e.data, unpreventable=True)) for e in effects]
