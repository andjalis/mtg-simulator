"""Emblems (#839): 'You get an emblem with "At the beginning of your end step, ..."' and 'You get an emblem with
"Creatures you control get +2/+2 and have flying."'.

An emblem (CR 114) is an object in the command zone. It has no types, can't be interacted with, and its abilities
work for the rest of the game. The engine keeps each emblem as a ``Permanent`` in ``Player.command``; it is never on
the battlefield, so removal, counts and "permanents you control" never see it.

* A triggered body is parsed with the reader for granted quoted triggers (``cx_trigger_grants.quoted_triggers``).
  ``_dispatch_trigger_event``, the cast-trigger loop in engine/play.py and the "ev:" watchers in cx_events walk
  ``Player.command`` after the battlefield, so its triggers fire like a permanent's.
* A static body is parsed as an enchantment's static line and accepted only when all it sets is a continuous effect
  the engine reads through the residual source index (``residual_templates.sources`` / ``field_sources``, which
  include the command zone): selector anthems (``advanced_rules["anthems"]``) and keyword grants
  (``static_keyword_grants``). The plain ``anthem`` / ``anthem_sub`` shapes are rewritten to selector anthems.
  "You have no maximum hand size" is the existing permanent player flag.

A body none of these reads exactly is left unparsed, so the card stays partial. The older single-shape emblem
("Xs you control get +N/+N", kind ``emblem``) is unchanged.
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

_MINE_CREATURES = {"controller": "mine", "types_all": ["creature"]}


def _fires(trig) -> bool:
    return trig.event in FIRING or trig.event.startswith("ev:")


def _static(body):
    """The continuous effect of a static emblem body as {"anthems": [...], "grants": (...)}, or None."""
    from .cards import card_from_scryfall
    from .cards.model import CardDef
    import dataclasses
    text = body if body.endswith(".") else body + "."
    try:
        c = card_from_scryfall({"name": "Emblem", "mana_cost": "", "type_line": "Enchantment", "oracle_text": text,
                                "cmc": 0})
    except Exception:
        return None
    blank = card_from_scryfall({"name": "Emblem", "mana_cost": "", "type_line": "Enchantment", "oracle_text": "",
                                "cmc": 0})
    if not c.fully_supported:
        return None
    changed = {f.name for f in dataclasses.fields(CardDef)
               if f.name != "oracle" and getattr(c, f.name) != getattr(blank, f.name)}
    if not changed or not changed <= {"anthem", "anthem_sub", "static_keyword_grants", "advanced_rules"}:
        return None
    if set(c.advanced_rules) - set(blank.advanced_rules) - {"anthems"}:
        return None
    anthems = list(c.advanced_rules.get("anthems", ()))
    if c.anthem:
        anthems.append((dict(_MINE_CREATURES), c.anthem[0], c.anthem[1]))
    for sub, pp, tt, other in c.anthem_sub:
        if other or not re.fullmatch(r"[A-Z][a-z]+", sub):
            return None
        anthems.append(({"controller": "mine", "subtypes": [sub.lower()], "types_all": ["creature"]}, pp, tt))
    return {"anthems": anthems, "grants": tuple(c.static_keyword_grants)}


def _emblem(m):
    from .cards.model import NO_MATCH, Effect
    from .cx_trigger_grants import quoted_triggers
    who, body = _WHO[m[1].lower()], m[2]
    if re.match(r"(?:At|Whenever|When) ", body):
        triggers = quoted_triggers(re.sub(r"\bthis emblem\b", "~", body))      # the emblem is its own source
        if not triggers or not all(_fires(t) for t in triggers):
            return NO_MATCH                    # stays unsupported: the card is partial, not silently full
        # "target opponent gets" / "each opponent gets": in a two-player game, the opponent
        return Effect("emblem_obj", data={"text": body, "triggers": list(triggers), "who": who})
    if who != "you":
        return NO_MATCH                        # an opponent's static emblem (locks on them): not read yet
    if re.fullmatch(r"You have no maximum hand size\.?", body, re.I):
        return Effect("cx_player_flag", data={"flag": "no_max_hand", "who": "you", "forever": True})
    static = _static(body)
    if static is None:
        return NO_MATCH
    return Effect("emblem_obj", data={"text": body, "triggers": [], "who": who, "static": static})


EFFECT_PATTERNS = [
    (r'(you get|each opponent gets|target opponent gets) an emblem with "([^"]+)"', _emblem),
]

# 'You get an emblem with "Lands you control have indestructible." Search your library ...' (Nissa, Who Shakes the
# World): the quote's own period ends the sentence; move it outside so the next sentence is read on its own.
SUBS = [
    (re.compile(r'(emblem with "[^"]*?)\."(?= [A-Z])'), lambda m: m[1] + '".'),
]


def make(game, p, eff, item=None):
    """Put the emblem into its owner's command zone: p's, or the opponent's for "each/target opponent gets"."""
    from .cards.model import CardDef
    from .engine.state import Permanent
    if eff.data.get("who") == "opponent":
        p = game.opponent(p)
    src = getattr(item, "source", None) if item is not None else None
    origin = getattr(getattr(src, "card", None), "name", None) or getattr(item, "name", "") or "a planeswalker"
    static = eff.data.get("static") or {}
    card = CardDef(name=f"Emblem ({origin})", mana_cost={"generic": 0}, cmc=0, types=frozenset({"Emblem"}),
                   triggers=list(eff.data["triggers"]), oracle=eff.data["text"],
                   static_keyword_grants=tuple(static.get("grants", ())),
                   advanced_rules={"anthems": list(static["anthems"])} if static.get("anthems") else {})
    emblem = Permanent(card, p)
    p.command.append(emblem)
    game._residual_source_index = None      # its anthems and keyword grants join the source index
    game.log(f"gets an emblem: \"{eff.data['text']}\"", p)
    return emblem


REPEATS = 3        # an emblem keeps working: count its ability a few times over


def value(game, me, eff) -> float:
    """What the AI expects from the emblem: its triggered effects a few times over, or its anthem on our creatures."""
    from .engine.policy import _mode_value
    if eff.data.get("who") == "opponent":
        # a drawback emblem for them (Chandra's "deals 1 damage to you" each upkeep): what it costs them, for us
        owner = game.opponent(me)
        return sum(REPEATS * max(-_mode_value(game, owner, list(t.effects)), 0.0) for t in eff.data["triggers"])
    total = 0.0
    for trig in eff.data["triggers"]:
        v = _mode_value(game, me, list(trig.effects))
        total += REPEATS * max(v, 0.0)
    static = eff.data.get("static") or {}
    n = max(1, len(me.creatures))            # creatures to come count too
    for _, pp, tt in static.get("anthems", ()):
        total += (pp + tt) * n
    for _, kws in static.get("grants", ()):
        total += 0.5 * len(kws) * n
    return total
