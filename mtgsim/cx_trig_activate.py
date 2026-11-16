"""Activation events for the cx_events trigger grammar (#860 item 1):

    Whenever a player activates an ability that isn't a mana ability, ...                 (Burning-Tree Shaman)
    Whenever an opponent activates an ability of an artifact, creature, or land that isn't a mana ability, ...
                                                                                           (Immolation Shaman)
    Whenever an opponent activates an ability of an artifact, creature, or land on the battlefield,
        if it isn't a mana ability, ...                                                    (Harsh Mentor)
    Whenever an opponent activates an ability of an artifact they control, ...             (Avalanche of Sector 7)
    Whenever you activate an ability of a creature, ...                                    (Elrond, Moon-Reader)
    Whenever you / an opponent activate(s) a loyalty ability, ...                          (Ajani Unrelenting)
    Whenever you activate an exhaust ability, ...                                          (Afterburner Expert)

The engine calls ``note`` from every path that activates a non-mana ability (general and loyalty abilities, equip,
crew, saddle, Clue / Blood, graveyard and hand abilities such as cycling, channel and unearth, ninjutsu) and
``mana_paid`` for the mana abilities a payment used (CR 605: they are activated abilities too). Both fire
"ability_activated"; a mana activation only matches heads without "that isn't a mana ability". "That player" is
the activating player.
"""
from __future__ import annotations

import re

from . import cx_events

_KEYWORDS = ("loyalty", "exhaust")
_NONMANA = r"(?: that isn't a mana ability|, if it isn't a mana ability)"
_VERB = (r"activates? (?:an ability(?: of (?P<of>.+?))?(?P<bf> on the battlefield)?(?P<nm>" + _NONMANA + r")?"
         r"|an? (?P<kw>" + "|".join(_KEYWORDS) + r") ability(?P<nm2>" + _NONMANA + r")?)")


def parse(vm, spec) -> bool:
    """Read the activation verb into ``spec``; False refuses the head."""
    m = re.fullmatch(_VERB, vm[0])
    if not m:
        return False
    spec["nonmana"] = bool(m["nm"] or m["nm2"] or m["kw"])
    spec["kw"] = m["kw"] or ""
    spec["of"] = None
    spec["they_control"] = False
    if m["of"]:
        desc = m["of"]
        if desc.endswith(" they control"):          # "an artifact they control": the activating player's
            spec["they_control"] = True
            desc = desc[:-len(" they control")]
        am = re.fullmatch(r"an? (.+)", desc)
        alts = cx_events._desc_alts(am[1]) if am else None
        if alts is None:
            return False
        spec["of"] = alts
    return True


def match(game, spec, actor) -> bool:
    """The activation just noted fits the head (the player subject is checked by cx_events)."""
    info = getattr(game, "event_activation", None)
    if info is None or info["player"] is not actor or info["mana"] and spec["nonmana"]:
        return False
    if spec["kw"] and info["kw"] != spec["kw"]:
        return False
    if spec["of"] is not None:
        src = info["source"]
        from .engine.state import Permanent
        if not isinstance(src, Permanent) or info["zone"] != "battlefield":
            return False            # "an ability of an artifact": a permanent's ability, not a card in hand
        if not cx_events._perm_fits(game, src, spec["of"]):
            return False
        if spec["they_control"] and src.controller is not actor:
            return False
    return True


def note(game, p, source=None, item=None, kw: str = "", zone: str = "battlefield"):
    """``p`` activated a non-mana ability of ``source`` (a permanent, or the card for hand / graveyard abilities)."""
    _fire(game, p, source, item, kw, zone, False)


def mana_paid(game, payment):
    """The mana abilities a payment activated (lands, mana creatures and rocks, Treasures)."""
    from .engine.state import Permanent
    if not _listening(game):
        return          # a game.fire per mana source only when some head can hear it
    for s in payment:
        if isinstance(s, Permanent) and getattr(s, "stored_in", None) is None:
            _fire(game, s.controller, s, None, "", "battlefield", True)


def _listening(game) -> bool:
    """Some permanent, graveyard card or turn watcher has an "ev:ability_activated" trigger."""
    from . import cx_trig_turn
    if cx_trig_turn.watchers(game):
        return True
    for pl in game.players:
        if any(t.event == _EV for x in pl.battlefield if cx_events._has_ev(x) for t in x.triggers):
            return True
        if any(t.event == _EV for c in pl.graveyard for t in getattr(c, "gy_triggers", ())):
            return True
    return False


_EV = "ev:ability_activated"


def _fire(game, p, source, item, kw, zone, mana):
    from .engine.state import Permanent
    previous = getattr(game, "event_activation", None)
    game.event_activation = {"player": p, "source": source, "item": item, "kw": kw, "zone": zone, "mana": mana}
    try:
        game.fire(p, "ability_activated", source if isinstance(source, Permanent) else None, context=item)
    finally:
        game.event_activation = previous


def keyword_of(act) -> str:
    """The keyword an activated ability is printed with ("Exhaust — ...")."""
    text = getattr(act, "text", "") or ""
    return "exhaust" if text.startswith("Exhaust") else ""


cx_events._PLAYER_VERBS[0:0] = [(_VERB, "activate")]
cx_events._PLAYER_RAW["activate"] = ("ability_activated",)
cx_events._OBSERVED.add("ability_activated")
