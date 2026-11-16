"""The AI's window for "Activate only during your upkeep" abilities (Mirror Universe, Magus of the Mirror).

The heuristic AI uses general abilities in its main phases, when an upkeep-only ability can't be activated, so
``upkeep`` (hooked in the turn's upkeep, after the triggers) offers each such ability once, judged by the usual
``ability_worth``. Abilities with X in their cost stay with their own upkeep logic (capped_counters, Clockwork).
"""
from __future__ import annotations


def upkeep(game, p) -> None:
    from .engine.policy import ability_worth
    for perm in list(p.battlefield):
        for idx, act in enumerate(perm.activated):
            if act.kind != "ability" or "my_upkeep" not in (act.restrictions or ()) or act.cost.get("X"):
                continue
            if perm in p.battlefield and not game.over and ability_worth(game, p, perm, idx):
                game.activate(p, perm, f"ability:{idx}")
