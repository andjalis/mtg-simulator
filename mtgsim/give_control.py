"""Giving control away (#640): "Target opponent gains control of target permanent you control."

    Target opponent gains control of target creature you control.                   (Harmless Offering, Donate)
    Target player gains control of target artifact, creature, or land you control.  (Bazaar Trader)
    Target opponent gains control of all other permanents you control.              (Sky Swallower)

Two-player games: the receiver is the caster's opponent ("target player" can only usefully be the opponent).
The AI treats it as a cost (it only gives away its worst matching permanent, and never casts it for the
effect alone: the effect values below zero).
"""
from __future__ import annotations


def _one(m):
    from .cards.model import NO_MATCH, Effect
    from .permanent_templates import selector
    sel = selector(m[2])
    if not sel or sel.get("controller") != "mine" or "cx_desc" in sel or "scope" in sel:
        return NO_MATCH
    return Effect("give_control_choice", target="permanent", data={"selector": sel})


def _all(m):
    from .cards.model import NO_MATCH, Effect
    from .permanent_templates import selector
    sel = selector(m[2], plural=True)
    if not sel or sel.get("controller") != "mine" or "cx_desc" in sel or "scope" in sel:
        return NO_MATCH
    return Effect("give_control_all", data={"selector": sel})


EFFECT_PATTERNS = [
    (r"target (opponent|player) gains control of target ([^.]+? you control)", _one),
    (r"target (opponent|player) gains control of all ((?:other )?[^,.]+? you control)", _all),
]
