"""Kinds owned by mechanic modules: each module's resolve() handles the kinds in its KINDS set."""
from __future__ import annotations

from ... import auras, cast_triggers, combat_triggers, copies, creature_keywords, removal, ring, search, xspells
from . import kind


@kind(*sorted(cast_triggers.KINDS))
def cast_trigger(game, p, eff, item, **_):
    cast_triggers.resolve(game, p, eff, item)


def _module_kinds(module):
    @kind(*sorted(module.KINDS))
    def handle(game, p, eff, target, item, **_):
        module.resolve(game, p, eff, target, item)


for _module in (copies, xspells, search, auras, removal, combat_triggers, creature_keywords, ring):
    _module_kinds(_module)

from ... import cx_recycle as _cx_recycle
_module_kinds(_cx_recycle)
