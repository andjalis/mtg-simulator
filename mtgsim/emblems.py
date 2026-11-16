"""Emblems with a triggered ability (#839): 'You get an emblem with "At the beginning of your end step, ..."'.

An emblem (CR 114) is an object in the command zone. It has no types, can't be interacted with, and its abilities
work for the rest of the game. The quoted ability is parsed with the same reader as granted quoted triggers
(``cx_trigger_grants.quoted_triggers``); a body it doesn't match exactly is left unparsed, so the card stays partial.

The engine keeps each emblem as a ``Permanent`` in ``Player.command``. ``_dispatch_trigger_event`` walks that list
after the battlefield, so the emblem's triggers fire like a permanent's. Nothing else looks at ``command``: an emblem
isn't on the battlefield, so removal, counts and "permanents you control" never see it.

Static emblem bodies (anthems, "no maximum hand size", locks) are a later #839 slice. The older single-shape
emblem ("Xs you control get +N/+N", kind ``emblem``) is unchanged.
"""
from __future__ import annotations

import re


_WHO = {"you get": "you", "each opponent gets": "opponent", "target opponent gets": "opponent"}

# Trigger events checked to fire from the command zone: those dispatched by Game._dispatch_trigger_event, the
# cast-trigger loop in engine/play.py, and the "ev:" watchers in cx_events (each hooked to Player.command). Other
# events are dispatched by modules that walk the battlefield only, so an emblem using one stays unparsed (partial)
# rather than counted full and silent.
FIRING = {"end_step", "each_end_step", "upkeep", "opp_upkeep", "begin_combat", "cast_spell", "cast_noncreature",
          "cast_instant_sorcery", "any_cast", "permanent_enters", "land_enters", "gain_life", "you_draw",
          "ally_combat_damage"}


def _fires(trig) -> bool:
    return trig.event in FIRING or trig.event.startswith("ev:")


def _emblem(m):
    from .cards.model import NO_MATCH, Effect
    from .cx_trigger_grants import quoted_triggers
    who, body = _WHO[m[1].lower()], m[2]
    if not re.match(r"(?:At|Whenever|When) ", body):
        return NO_MATCH
    triggers = quoted_triggers(re.sub(r"\bthis emblem\b", "~", body))      # the emblem is its own source
    if not triggers or not all(_fires(t) for t in triggers):
        return NO_MATCH                    # stays unsupported: the card is partial, not silently full
    # "target opponent gets" / "each opponent gets": in a two-player game, the opponent
    return Effect("emblem_obj", data={"text": body, "triggers": list(triggers), "who": who})


EFFECT_PATTERNS = [
    (r'(you get|each opponent gets|target opponent gets) an emblem with "((?:At|Whenever|When) [^"]+)"', _emblem),
]


def make(game, p, eff, item=None):
    """Put the emblem into its owner's command zone: p's, or the opponent's for "each/target opponent gets"."""
    from .cards.model import CardDef
    from .engine.state import Permanent
    if eff.data.get("who") == "opponent":
        p = game.opponent(p)
    src = getattr(item, "source", None) if item is not None else None
    origin = getattr(getattr(src, "card", None), "name", None) or getattr(item, "name", "") or "a planeswalker"
    card = CardDef(name=f"Emblem ({origin})", mana_cost={"generic": 0}, cmc=0, types=frozenset({"Emblem"}),
                   triggers=list(eff.data["triggers"]), oracle=eff.data["text"])
    emblem = Permanent(card, p)
    p.command.append(emblem)
    game.log(f"gets an emblem: \"{eff.data['text']}\"", p)
    return emblem


REPEATS = 3        # an emblem keeps working: count its ability a few times over


def value(game, me, eff) -> float:
    """What the AI expects from the emblem: its triggered effects, a few times over."""
    from .engine.policy import _mode_value
    if eff.data.get("who") == "opponent":
        # a drawback emblem for them (Chandra's "deals 1 damage to you" each upkeep): what it costs them, for us
        owner = game.opponent(me)
        return sum(REPEATS * max(-_mode_value(game, owner, list(t.effects)), 0.0) for t in eff.data["triggers"])
    total = 0.0
    for trig in eff.data["triggers"]:
        v = _mode_value(game, me, list(trig.effects))
        total += REPEATS * max(v, 0.0)
    return total
