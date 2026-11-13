"""Time counters on permanents and suspended cards (part of #345).

    Remove two time counters from target permanent or suspended card.                     (Fury Charm, Timebender)
    Put two time counters on target permanent with a time counter on it or suspended card. (Timebender)
    Remove X time counters from target permanent or suspended card.                        (Timecrafting)
    Remove two time counters from each permanent and each suspended card.                  (Dust of Moments)
    Put two time counters on each permanent with a time counter on it and each suspended card.

One effect kind, ``time_counters`` (``data["op"]`` "remove" or "put"), aimed at a ``perm_or_suspended`` target (a
permanent, or a card in a player's ``suspended`` list) or, with ``data["group"]``, at all of them. Removing a
suspended card's last time counter casts it without paying its mana cost, as suspend's own upkeep does; removing a
vanishing permanent's last one sacrifices it (vanishing's "when the last is removed" ability). The engine side is
``engine.kinds.cx_counters.time_counters``; the AI's choice is ``choose`` below.
"""
from __future__ import annotations

import re

_N = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "x": 0}
_NUM = r"(a|an|one|two|three|four|five|x|\d+)"


def _effect(op, n, group=False, has_time=False):
    from .cards.model import Effect
    word = n.lower()
    amount = _N[word] if word in _N else int(word)
    data = {"op": op}
    if word == "x":
        data["x"] = True
    if group:
        data["group"] = True
    if has_time:
        data["has_time"] = True        # "put ... on target permanent with a time counter on it or suspended card"
    return Effect("time_counters", amount, target="none" if group else "perm_or_suspended", data=data)


# "Whenever ..., if this card is suspended, remove a time counter from it" (Deep-Sea Kraken) / "... that player may put
# a time counter on this card" (Pardic Dragon): an ability that works only while the card is suspended. The effect is
# marked suspended_self; Game.fire skips it on the battlefield and ``suspended_triggers`` queues it from exile.
SUBS = [
    (re.compile(r"if this card is suspended, remove a time counter from (?:it|this card)\.", re.I),
     lambda m: "SUSPTICK remove you."),
    (re.compile(r"if this card is suspended, that player may put a time counter on this card\.", re.I),
     lambda m: "SUSPTICK put caster."),
]


def _self_tick(m):
    from .cards.model import Effect
    return Effect("time_counters", 1, data={"op": m[1], "suspended_self": True, "who": m[2]})


EFFECT_PATTERNS = [
    (r"SUSPTICK (remove|put) (you|caster)", _self_tick),
    (rf"remove {_NUM} time counters? from target permanent or suspended card",
     lambda m: _effect("remove", m[1])),
    (rf"put {_NUM} time counters? on target permanent with a time counter on it or suspended card",
     lambda m: _effect("put", m[1], has_time=True)),
    (rf"remove {_NUM} time counters? from each permanent and each suspended card",
     lambda m: _effect("remove", m[1], group=True)),
    (rf"put {_NUM} time counters? on each permanent with a time counter on it and each suspended card",
     lambda m: _effect("put", m[1], group=True, has_time=True)),
]


def suspended_cards(game):
    """(player, entry) for every suspended card: entry is the player's [card, time counters] list."""
    return [(pl, entry) for pl in game.players for entry in pl.suspended if entry[0] in pl.exile]


def legal(game, p, eff):
    """Targets for perm_or_suspended: permanents (only ones with a time counter for "put") and suspended cards."""
    perms = [x for pl in game.players for x in pl.battlefield if game.targetable(x, p)
             and (not eff.data.get("has_time") or x.counters.get("time", 0) > 0)]
    return perms + [entry[0] for _, entry in suspended_cards(game)]


def choose(game, me, eff):
    """Remove: speed up my own suspended card (the fewest counters left first), else my impending permanent, else
    hasten an opponent's vanishing one. Put: delay an opponent's suspended card or impending permanent, else keep my
    vanishing permanent longer. None when nothing helps."""
    from .engine.state import Permanent
    legal_now = legal(game, me, eff)
    cards = {id(entry[0]): (pl, entry) for pl, entry in suspended_cards(game)}
    opp = game.opponent(me)
    remove = eff.data["op"] == "remove"

    def susp(owner):
        return sorted((cards[id(c)] for c in legal_now if id(c) in cards and cards[id(c)][0] is owner),
                      key=lambda pe: pe[1][1])

    def perms(owner, want):
        return [x for x in legal_now if isinstance(x, Permanent) and x.controller is owner
                and x.counters.get("time", 0) > 0 and (x.impending if want == "impending" else x.card.vanishing)]

    if remove:
        options = [pe[1][0] for pe in susp(me)] + perms(me, "impending") + perms(opp, "vanishing")
    else:
        options = [pe[1][0] for pe in susp(opp)] + perms(opp, "impending") + perms(me, "vanishing")
    return options[0] if options else None


def _cast_suspended(game, owner, entry):
    from .cards import AltCost
    if entry in owner.suspended:
        owner.suspended.remove(entry)
    card = entry[0]
    if card in owner.exile:
        game.log(f"casts suspended {card.name}", owner)
        game.cast(owner, game._variant(card, "suspended", AltCost("suspended", {"generic": 0})))


def apply(game, p, eff, target, n):
    """Remove or put n time counters on target (a permanent or a suspended card), or on all of them (group)."""
    from .engine.state import Permanent
    remove = eff.data["op"] == "remove"
    if eff.data.get("group"):
        objects = [x for pl in game.players for x in pl.battlefield
                   if not eff.data.get("has_time") or x.counters.get("time", 0) > 0]
        objects += [entry[0] for _, entry in suspended_cards(game)]
    else:
        objects = [target] if target is not None else []
    cards = {id(entry[0]): (pl, entry) for pl, entry in suspended_cards(game)}
    for obj in objects:
        if isinstance(obj, Permanent):
            have = obj.counters.get("time", 0)
            if remove:
                if not have:
                    continue
                obj.counters["time"] = max(0, have - n)
                game.log(f"removes {have - obj.counters['time']} time counters from {obj.card.name}", p)
                if not obj.counters["time"] and obj.card.vanishing and obj in obj.controller.battlefield:
                    game.sacrifice(obj)          # vanishing: "when the last time counter is removed, sacrifice it"
            else:
                obj.counters["time"] = have + n
                game.log(f"puts {n} time counters on {obj.card.name}", p)
        elif id(obj) in cards:
            owner, entry = cards[id(obj)]
            if remove:
                if entry[1] <= 0:
                    continue
                entry[1] = max(0, entry[1] - n)
                game.log(f"removes time counters from suspended {obj.name} ({entry[1]} left)", p)
                if entry[1] == 0:
                    _cast_suspended(game, owner, entry)
            else:
                entry[1] += n
                game.log(f"puts {n} time counters on suspended {obj.name} ({entry[1]})", p)


def suspended_triggers(game, p, event, context):
    """Game.fire: p's suspended cards whose "if this card is suspended" ability triggers on event (an opponent's
    spell: the any_cast filter "opp")."""
    import dataclasses
    for _, entry in [(pl, e) for pl, e in suspended_cards(game) if pl is p]:
        card = entry[0]
        for trig in card.triggers:
            if trig.event != event or not any(e.data.get("suspended_self") for e in trig.effects):
                continue
            caster = getattr(context, "controller", context)
            if event == "any_cast" and trig.filter == "opp" and caster is p:
                continue
            effects = [dataclasses.replace(e, data=dict(e.data, card_ref=card)) if e.data.get("suspended_self")
                       else e for e in trig.effects]
            game.queue_trigger(p, effects, None, f"{card.name} (suspended)", context=context)

