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

EFFECT_PATTERNS = [
    (r"(.+) at end of combat", _later),
    (r"(?:~|it) deals (\d+) damage to that creature", lambda m: _effect("damage", int(m[1]), target="prev")),
    (rf"{_SUBJECT} doesn't untap during its controller's next untap step", lambda m: _effect("skip_untap", target="prev")),
    (r"tap that creature", lambda m: _effect("tap", target="prev")),
    (r"untap that creature", lambda m: _effect("untap_prev", target="prev")),
    (r"return that creature to its owner's hand", lambda m: _effect("bounce", target="prev")),
    (r"put an? (-1/-1|\+1/\+1) counter on that creature",
     lambda m: _effect("add_counter", 1, target="prev", data={"counter": m[1]})),
    (r"exile ~", lambda m: _effect("exile_self")),
]


def resolve(game, p, eff, target, item):
    from .engine import Permanent
    if item is None:
        return
    if item.is_spell:
        item.exile_self = True
    elif isinstance(item.source, Permanent) and item.source in item.source.controller.battlefield:
        game.leave_battlefield(item.source, "exile")
