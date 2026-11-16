"""Promising a gift is a choice made while casting (CR 702.174, 601.2b) (#483).

    Gift a card (You may promise an opponent a gift as you cast this spell. If you do, they draw a card before its
    other effects.)
    Destroy target artifact or enchantment. If the gift was promised, instead destroy two target artifacts and/or
    enchantments.                                                                                   (Wear Down)

A gift card's effects carry the mode they belong to: ``cond`` "gifted" / "!gifted" (also as a condlib "not"), or an
"instead" gate on "gifted" (``instead_gate`` / ``instead_branch``). ``active`` says whether an effect belongs to the
chosen mode. ``Game.cast`` asks the caster's AI (``promise_gift``) before targets are checked, then requires and
fills targets only for the active effects: the other mode's target slots stay empty and are skipped on resolution.

HeuristicAI values both modes with its ordinary spell planner and promises only when the gifted mode is castable
and worth more than the other mode plus what the gift gives the opponent (``COST``); a mode that returns its exiled
target at end of turn counts as temporary removal. Other AIs, and HeuristicAI for a card it didn't plan (its
instant-speed removal paths) decide with the given targets: a removal spell aimed only at our own permanents is cast
unpromised when that mode is castable (Parting Gust on our own creature is a blink); when both modes are castable,
the engine policy's mode values (``worth``) decide; otherwise the castable mode is used.
"""
from __future__ import annotations

import dataclasses

COST = {"card": 1.0, "food": 0.5, "tapped fish": 0.6, "treasure": 0.6, "octopus": 3.0, "extra turn": 4.0}
_NOT = ("!gifted", 'lib:["not","gifted"]')
_HOSTILE = {"destroy", "exile_permanent", "bounce", "damage", "debuff_one", "oring"}


def active(eff, gifted: bool) -> bool:
    """Does this effect belong to the mode chosen by promising (or not promising) the gift?"""
    gate = eff.data.get("instead_gate")
    if gate and gate.get("cond") == "gifted":
        return eff.data.get("instead_branch") == gifted
    if eff.cond == "gifted":
        return gifted
    if eff.cond in _NOT:
        return not gifted
    return True


def mode_card(card, gifted: bool):
    """The card as it plays in one mode (only that mode's effects, their gift conditions dropped), and the index of
    each kept effect in the card's own list."""
    keep = [i for i, e in enumerate(card.spell_effects) if active(e, gifted)]
    effects = []
    for i in keep:
        e = card.spell_effects[i]
        data = {k: v for k, v in e.data.items() if k not in ("instead_gate", "instead_branch", "instead_base_cond")}
        cond = e.data.get("instead_base_cond", "") if "instead_gate" in e.data else \
            ("" if e.cond in ("gifted",) + _NOT else e.cond)
        effects.append(dataclasses.replace(e, cond=cond, data=data))
    return dataclasses.replace(card, spell_effects=effects, gift=""), keep


def cost(card) -> float:
    return COST.get(str(card.gift or "").lower(), 1.0)


def has_targets(game, p, card, gifted: bool, targets) -> bool:
    """Can this mode be cast with these targets (filled in where missing)?"""
    from .engine import TARGETED
    effects = card.spell_effects
    mask = [active(e, gifted) for e in effects]
    chosen = [t if m else None for t, m in zip(targets, mask)]
    missing = [i for i, e in enumerate(effects) if mask[i] and e.target in TARGETED and chosen[i] is None]
    if missing:
        filled = game.auto_targets(p, effects, card, preset=chosen)
        for i in missing:
            chosen[i] = filled[i]
    kept = [i for i, m in enumerate(mask) if m]
    return game.valid_action_targets(p, [effects[i] for i in kept], [chosen[i] for i in kept], card)


def decide(game, p, card, targets) -> bool:
    """Promise the gift? The caster's AI decides; by default, when the gifted mode can be cast (a permanent spell:
    always, its gift payoff is an enters trigger)."""
    choose = getattr(p.ai, "promise_gift", None)
    if choose is not None:
        got = choose(game, p, card)
        if got is not None:
            return got
    if card.is_permanent:
        return True
    from .engine.state import Permanent
    chosen = [t for e, t in zip(card.spell_effects, targets)
              if t is not None and active(e, True) and e.kind in _HOSTILE]
    if chosen and all(isinstance(t, Permanent) and t.controller is p for t in chosen) and \
            has_targets(game, p, card, False, targets):
        return False        # aimed at our own permanent: the gift's upgrade is meant for theirs (Parting Gust: a blink)
    can = {gifted: has_targets(game, p, card, gifted, targets) for gifted in (True, False)}
    if can[True] and can[False]:
        return worth(game, p, card, True) > worth(game, p, card, False)
    return can[True]


def _temporary(effects) -> bool:
    """"Return that card to the battlefield at the beginning of the next end step": the removal is temporary."""
    return any(e.kind == "cx_delay" and e.data.get("op") == "battlefield" and e.data.get("who") == "prev"
               for e in effects)


def worth(game, p, card, gifted: bool) -> float:
    """A mode's value by the engine policy's mode evaluator, net of what the gift gives the opponent."""
    from .engine.policy import _mode_value
    variant, _ = mode_card(card, gifted)
    with game.targeting(variant):
        value = _mode_value(game, p, variant.spell_effects)
    return value * (0.3 if _temporary(variant.spell_effects) else 1.0) - (cost(card) if gifted else 0.0)


def plan(ai, game, me, card, precombat):
    """HeuristicAI: (value, targets) of the better mode, recording the choice for ``promise_gift``."""
    best = None
    for gifted in (True, False):
        variant, keep = mode_card(card, gifted)
        got = ai.plan_spell(game, me, variant, precombat)
        if got is None or got[0] <= 0:
            continue
        value = got[0] - (cost(card) if gifted else 0.0)
        if _temporary(variant.spell_effects):
            value *= 0.3
        targets = None
        if got[1] is not None:
            targets = [None] * len(card.spell_effects)
            for j, i in enumerate(keep):
                targets[i] = got[1][j] if j < len(got[1]) else None
        if best is None or value > best[0]:
            best = (value, targets, gifted)
    if best is None:
        return None
    ai.gift_choices[card.name] = best[2]
    return best[0], best[1]
