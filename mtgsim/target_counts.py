"""Counts over a targeted player (#337): "You gain 2 life for each creature target player controls" (Divine
Congregation), "Draw cards equal to the number of cards in target opponent's hand" (Recurring Insight), "you gain 1
life for each black and/or red creature target opponent controls" (Kithkin Zealot).

The player whose things are counted is a real target, chosen like any other: a ``cx_count_target`` marker effect
(target ``player``, filter ``opp`` for "target opponent") comes first and records the chosen player on the resolving
item. The counted sentence is read on its own ("You gain 2 life", "Draw a card") and its effects carry
``xq = ("of_target", <count relative to a player>)``: Game.x_quantity evaluates the inner count for the recorded
player, so the effect itself still happens to whoever the sentence names (you). The default AI targets the player with
the larger count.
"""
from __future__ import annotations

import dataclasses
import re

KINDS = {"cx_count_target"}

_WHO = r"(?P<who>target player|target opponent)"


def _inner_spec(m):
    """The count relative to a player, or None."""
    from .cards.clauses import _xq
    if "hand" in m.re.groupindex:
        return ("hand",)
    noun = m["noun"]
    if "each" in m.re.groupindex:
        from .cx_grammar import _count_spec
        return _count_spec(noun + " you control")
    return _xq("the number of " + noun + " you control")


def _rest(text: str) -> str:
    """The counted sentence with a unit amount: "Draw cards" -> "Draw a card", "you gain life" -> "you gain 1 life"."""
    text = re.sub(r"^(draw)s? cards$", r"\1 a card", text, flags=re.I)
    text = re.sub(r"^((?:you )?(?:gain|lose)s?) life$", r"\1 1 life", text, flags=re.I)
    return text


def _counted(m):
    from .cards.model import Effect, NO_MATCH
    from .cx_grammar import _SCALED, parse_sentence
    rest = m["rest"].strip()
    if re.search(r"\btarget\b|\bthen\b|,", rest, re.I):
        return NO_MATCH
    spec = _inner_spec(m)
    if spec is None:
        return NO_MATCH
    effects = parse_sentence(_rest(rest) + ".")
    if not effects:
        return NO_MATCH
    scaled = [e for e in effects for e in ([e] + list(e.data.get("effects", ()))) if e.kind in _SCALED]
    if not scaled or any(e.target not in ("none", "that_controller") for e in effects):
        return NO_MATCH
    marker = Effect("cx_count_target", target="player", filter="opp" if m["who"].lower() == "target opponent" else "")
    return [marker] + [dataclasses.replace(e, data=dict(e.data, xq=("of_target", spec))) for e in effects]


EFFECT_PATTERNS = [
    (rf"(?P<rest>.+?) for each (?P<each>)(?P<noun>[^.]+?) {_WHO} controls", _counted),
    (rf"(?P<rest>.+?) equal to the number of (?P<noun>[^.]+?) {_WHO} controls", _counted),
    (rf"(?P<rest>.+?) equal to the number of cards in {_WHO}'s hand(?P<hand>)", _counted),
]


def count(game, item, spec, prev) -> int:
    """Game.x_quantity for ("of_target", inner): the inner count for the player the marker recorded."""
    who = getattr(item, "count_target", None) if item is not None else None
    if who is None:
        who = (getattr(game, "_choosing_targets", None) or [None])[0]      # the AI sizing it before it casts
    if who is None or not hasattr(who, "battlefield"):
        return 0
    return game.x_quantity(who, spec[1], item, prev)


def resolve(game, item, target):
    if item is not None:
        item.count_target = target


def choose(game, me, eff):
    """The legal player with the larger count of what the spell counts (ties: the opponent)."""
    from .engine.state import Player
    legal = [x for x in game.legal_targets(me, eff) if isinstance(x, Player)]
    effects = getattr(game, "_choosing_effects", None) or ()        # set by the AI planner while it picks targets
    if not effects:
        spell = getattr(game, "target_source", None)
        effects = getattr(spell, "spell_effects", None) or getattr(spell, "effects", None) or ()
    spec = next((e.data["xq"][1] for e in effects if isinstance(e.data.get("xq"), tuple)
                 and e.data["xq"][0] == "of_target"), None)
    if spec is None:
        return next((x for x in legal if x is not me), None)
    return max(legal, key=lambda pl: (game.x_quantity(pl, spec, None, None), pl is not me), default=None)
