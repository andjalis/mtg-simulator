"""Effect-kind handlers: Game.resolve looks up each effect's kind in HANDLERS.

A handler is `@kind("name", ...) def name(game, p, eff, target, ...)`. It receives, by keyword,
whichever of p, eff, target, item, prev, opp, k, source and cause it names (and **_ for the rest),
after resolve has applied the shared amount rules (per / xq / x). Returning NO_SBA skips the
state-based check that otherwise follows. Put a new kind in the family module it belongs to;
mechanic modules with their own KINDS set (copies.py, removal.py, ...) are dispatched after these.
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


from . import cards, damage, graveyard, other, permanents, stats  # noqa: E402,F401  (registers the handlers)
