"""Triggers an effect creates for the rest of the turn (#399): "Whenever <event> this turn, <effects>."

    Whenever a creature attacks this turn, put a +1/+1 counter on it.               (Basri, Devoted Paladin)
    Whenever you cast a creature spell this turn, draw a card.                      (Glimpse of Nature)
    Whenever a creature blocks this turn, its controller loses 1 life.              (Mage Hunters' Onslaught)

These are delayed triggered abilities (CR 603.7): the spell or ability that creates them is their source, its
controller controls them, and they last until the turn ends. The head is read by the trigger-event library
(``cx_events.compile_head``) and the body by the effect parser, as for a printed "ev:" trigger, so "it" is the
event object (the attacker, the entering creature) and "its controller" its controller.

On resolution ``cx_turn_trigger`` registers the triggers on a *watcher*: a Permanent that is never on the
battlefield, controlled by the effect's controller and named after its source. ``cx_events.observe`` adds this
turn's watchers to the permanents it checks (``watchers``), and drops older ones.

Refused: heads naming an earlier object ("that creature", "dealt damage this way": ``cx_trig_watch`` and the
damage referents own those), heads the event library can't read, bodies that don't parse fully, and bodies that
name ~ (the watcher is not a permanent anything can act on).
"""
from __future__ import annotations

import re

_LINE = re.compile(r"whenever (?P<head>.+?) this turn, (?P<body>.+)", re.I)


def _build(m):
    from .cards.model import NO_MATCH, Effect, Trigger
    from . import cx_events
    from .cards.parse import _parse_effects
    from . import cx_tokens
    head = "Whenever " + m["head"]
    if re.search(r"\b(?:that|this way|~|it|its)\b", m["head"], re.I):
        return NO_MATCH
    got = cx_events.compile_head(head)
    if got is None or not set(got[0]) <= cx_events._OBSERVED:
        return NO_MATCH
    body = m["body"]
    if "~" in body or re.search(r"\bthis (?:creature|permanent|spell|card)\b", body, re.I):
        return NO_MATCH
    with cx_tokens.event_amount_ctx(got[0]):
        effects, bad = _parse_effects(body[0].upper() + body[1:] + ("" if body.endswith(".") else "."))
    if bad or not effects or any(e.target == "self" for e in effects):
        return NO_MATCH
    triggers = [Trigger("ev:" + event, list(effects), filter=head) for event in got[0]]
    return Effect("cx_turn_trigger", target="none", data={"triggers": triggers, "head": m["head"], "body": body})


_BACK = re.compile(r"\b(?:it|its|they|them|their|those|that)\b", re.I)


def more(sentence: str, effects: list, unmatched: list) -> bool:
    """A sentence after the trigger that refers back to its objects ("It gains trample ...", "Sacrifice them at
    the beginning of the next end step") is part of the trigger's effect: parse it with the body. If the whole
    doesn't parse, the sentence is unmatched (it must not run when the trigger is created)."""
    if not _BACK.search(sentence):
        return False
    old = effects[-1]
    body = old.data["body"].rstrip(".") + ". " + sentence
    m = _LINE.fullmatch(f"whenever {old.data['head']} this turn, {body}")
    new = _build(m) if m else None
    from .cards.model import Effect
    if isinstance(new, Effect):
        effects[-1] = new
    else:
        unmatched.append(sentence)
    return True


EFFECT_PATTERNS = [(_LINE.pattern, _build)]


def register(game, p, eff, item):
    """Start the turn's watcher for these triggers, controlled by ``p``."""
    from .cards.model import CardDef
    from .engine.state import Permanent
    source = getattr(item, "card", None) or getattr(getattr(item, "source", None), "card", None)
    name = getattr(source, "name", "") or "delayed trigger"
    watcher = Permanent(CardDef(name, {}, 0, frozenset()), p)
    watcher.temp_triggers = list(eff.data["triggers"])
    if not hasattr(game, "cx_turn_watchers"):
        game.cx_turn_watchers = []
    game.cx_turn_watchers.append((game.turn, watcher))


def watchers(game) -> list:
    """This turn's watchers (older ones are dropped)."""
    live = [(turn, w) for turn, w in getattr(game, "cx_turn_watchers", ()) if turn == game.turn]
    if live or getattr(game, "cx_turn_watchers", None):
        game.cx_turn_watchers = live
    return [w for _, w in live]


# ---------------------------------------------------------------- AI
_BODY = {"draw": 1.0, "p1_counters": 1.0, "add_counter": 0.5, "token": 1.0, "cx_token": 1.0, "pump": 0.5,
         "grant": 0.5, "cx_temp_kw": 0.5, "lose_life": 0.5, "drain": 0.7, "damage": 0.7, "gain_life": 0.2,
         "cx_poison": 1.0, "become_monarch": 2.0, "debuff_one": 0.7, "proliferate": 0.7}


def value(game, me, eff, card=None, precombat=True) -> float:
    """HeuristicAI's estimate: the triggers expected this turn times what one resolution is worth."""
    from . import cx_events
    total = 0.0
    hand = [c for c in me.hand if c is not card and not c.is_land]
    ready = [c for c in me.creatures if c.can_attack() and c.power > 0]
    for trig in eff.data["triggers"]:
        got = cx_events.compile_head(trig.filter)
        if got is None:
            continue
        event, mine = trig.event[3:], got[1].get("ctrl") in ("you", None)
        if event == "any_cast":
            n = len(hand)
        elif event == "etb":
            n = sum(c.is_creature for c in hand) if mine else 0.5
        elif event in ("attacks", "you_attack", "combat_damage_player"):
            n = (len(ready) if event != "you_attack" else min(1, len(ready))) if precombat and mine else 0
        else:
            n = 0.5
        body = sum(_BODY.get(e.kind, 0.3) * max(1, e.amount) for e in trig.effects)
        total += n * body
    return total
