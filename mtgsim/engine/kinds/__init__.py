"""Effect-kind handlers: Game.resolve looks up each effect's kind in HANDLERS.

A handler is `@kind("name", ...) def name(game, p, eff, target, ...)`. It receives, by keyword,
whichever of p, eff, target, item, prev, opp, k, source and cause it names (and **_ for the rest),
after resolve has applied the shared amount rules (per / xq / x). Returning NO_SBA skips the
state-based check that otherwise follows. Put a new kind in the family module it belongs to;
mechanics.py registers the KINDS sets of mechanic modules with their own resolve() (copies.py, removal.py, ...).
"""
from __future__ import annotations

HANDLERS: dict = {}
NO_SBA = object()


def kind(*names):
    def register(fn):
        for name in names:
            assert name not in HANDLERS, name
            HANDLERS[name] = fn
        return fn
    return register


from . import batch1, batch2, residual, advanced, roadmap, cards, counters, damage, dungeon, graveyard, mechanics, other, permanents, stats  # noqa: E402,F401  (registers the handlers)
from . import phasing, ripple, manifest, demonstrate, amplify, mirrodin, prepare, cx_damage, cx_triggers, cx_effects, madness, unearth  # noqa: E402,F401  (registers the handlers)
from . import cx_next_turn  # noqa: E402,F401
from . import cx_links  # noqa: E402,F401  (registers the handlers)
from . import cx_statics  # noqa: E402,F401
from . import cx_lures  # noqa: E402,F401
from . import cx_recolor  # noqa: E402,F401
from . import cx_shields  # noqa: E402,F401
from . import cx_night_suspect  # noqa: E402,F401
from . import cx_suspect  # noqa: E402,F401
from . import cx_delayed  # noqa: E402,F401
from . import cx_trig  # noqa: E402,F401
from . import cx_night_kinship  # noqa: E402,F401
from . import cx_night_lair  # noqa: E402,F401
from . import cx_night_draw  # noqa: E402,F401
from . import cx_night_dead  # noqa: E402,F401
from . import cx_night_flip  # noqa: E402,F401
from . import cx_night_lifemv  # noqa: E402,F401
from . import cx_night_endturn  # noqa: E402,F401
from . import cx_night_combat  # noqa: E402,F401
from . import cx_night_loot  # noqa: E402,F401
from . import cx_night_gy  # noqa: E402,F401
from . import cx_counters  # noqa: E402,F401
from . import cx_abil  # noqa: E402,F401
from . import cx_mech  # noqa: E402,F401
from . import cx_grammar  # noqa: E402,F401
from . import cx_tokens  # noqa: E402,F401
from . import cx_exchange  # noqa: E402,F401  (exchange of control, #334)
from . import card_referent  # noqa: E402,F401  ("that card's mana value", #313)
from . import cx_attach  # noqa: E402,F401  (attach an Aura / Equipment to another object, #343)
from . import cx_static_cost  # noqa: E402,F401  (one-shot spell-group discounts, #341)
from . import cx_static_chars  # noqa: E402,F401  ("loses all abilities", #406)
from . import cx_static  # noqa: E402,F401  (sim-static's small kinds)
from . import library_peek  # noqa: E402,F401  (#346)
from . import cx_trig_turn  # noqa: E402,F401  (triggers for the rest of the turn, #399)
from . import cx_trig_damage  # noqa: E402,F401  (damage triggers from any source, #521)
from . import cx_bounce  # noqa: E402,F401  (bounce residue, #638)
from . import votes  # noqa: E402,F401  (votes: will of the council, council's dilemma, #634)
