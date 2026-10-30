"""Block triggers and what they do to "that creature" (the other creature in the block).

    Whenever ~ blocks, ...              Whenever ~ becomes blocked, ...
    Whenever ~ blocks or becomes blocked, ...                Whenever ~ attacks or blocks, ...
    Bushido N     Flanking     Toxic N
    ~ deals 1 damage to that creature.          Destroy that creature at end of combat.
    That creature doesn't untap during its controller's next untap step.
    Return that creature to its owner's hand at end of combat.     Exile ~.

The trigger events are fired in Game._combat once blockers are declared: "blocks" for each blocking creature
(context: the attacker it blocks) and "becomes_blocked" for each blocked attacker (context: its first
blocker). A trigger's "that creature" resolves to that context. "... at end of combat" holds the effects
until the end of combat step (Game.end_combat_effects). "Exile ~." on an instant or sorcery exiles it as it
resolves instead of putting it into the graveyard; on a permanent it exiles the permanent.
Not modelled: "blocks or becomes blocked by a <kind of> creature", banding, "blocking that creature" tokens.
"""
from __future__ import annotations
from . import wordings

KINDS = {"exile_self"}


def _effect(kind, amount=0, amount2=0, target="none", data=None):
    from .cards import Effect
    return Effect(kind, amount, amount2, target=target, data=data or {})


def _later(m):
    """"<effects> at end of combat": the effects, delayed, keeping "that creature"."""
    from .cards import NO_MATCH, _parse_effects
    body = m[1].strip()
    effects, bad = _parse_effects(body[0].upper() + body[1:] + ".")
    if bad or not effects:
        return NO_MATCH
    return _effect("end_of_combat", data={"effects": effects})


_SUBJECT = r"(?:that creature|it|the creature|that permanent)"

EFFECT_PATTERNS = wordings.patterns("combat_triggers") + [
    (r"(.+) at end of combat", _later),
]


def resolve(game, p, eff, target, item):
    from .engine import Permanent
    if item is None:
        return
    if item.is_spell:
        item.exile_self = True
    elif isinstance(item.source, Permanent) and item.source in item.source.controller.battlefield:
        game.leave_battlefield(item.source, "exile")
