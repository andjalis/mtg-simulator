"""Prevention shields with "If damage is prevented this way" riders (Acolyte's Reward,
Vengeful Archon).

"Prevent the next X damage that would be dealt to <who> this turn" becomes a
``prevent_shield`` effect: the kind handler adds ``prevent_next`` to the shielded player
or permanent and, when the sentence has a rider, installs it as a temporary
``damage_prevented`` trigger on the shielded permanent (or the resolving source), so the
le-batch5 event — fired to the shield holder with ``event_amount`` set to the prevented
total — carries "that much" into the rider's effects. ", where X is your devotion to
<color>" sizes the shield at resolution; a literal X in an ability's cost sizes it from
``item.x`` (data ``x``, see resolve's shared amount rules).

The player-side family below has no permanent carrier: Divine Deflection, Deflecting
Palm, Intervention Pact and Channel Harm are spells (Ria Ivor's shield covers players),
so their riders ride ``install_player_rider`` — a one-turn EventBus listener on
``damage_prevented`` that queues the rider's effects with the prevented amount snapshotted
into "that much" effects, the same way the trigger dispatch snapshots ``event_amount``.
"""
from __future__ import annotations

import dataclasses
import re

_TARGETS = "target creature|target player|any target|you|~"
_MAP = {"target creature": "creature", "target player": "player", "any target": "any",
        "you": "none", "~": "self"}
_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}


def _shield(m):
    """Rewrite the sentence(s) into a PREVENTSHIELD sentinel.

    Takes a uniform 5-tuple: (whole, amount, target, devotion color, rider sentence)."""
    amount = "X" if m[1].lower() == "x" else m[1]
    color = _COLORS.get(m[3].lower(), "-") if m[3] else "-"
    rider = (m[4] or "-").rstrip(".") if m[4] else "-"
    if rider != "-":
        rider = rider.replace("target player or planeswalker", "target player")
    return f"PREVENTSHIELD {amount} {_MAP[m[2].lower()]} {color} RIDER {rider}."


SUBS = [
    # "Prevent the next X damage that would be dealt to <who> this turn[, where X is your
    # devotion to <color>]. If damage is prevented this way, <rider sentence>."
    (re.compile(r"prevent the next (x|\d+) damage that would be dealt to (" + _TARGETS +
                r") this turn(, where x is your devotion to (white|blue|black|red|green))?"
                r"\. if damage is prevented this way, (.+?)\.", re.I),
     lambda m: _shield((m[0], m[1], m[2], m[4], m[5]))),
    # The devotion-sized shield on its own (no rider sentence follows).
    (re.compile(r"prevent the next x damage that would be dealt to (" + _TARGETS +
                r") this turn, where x is your devotion to (white|blue|black|red|green)\.",
                re.I),
     lambda m: _shield((m[0], "X", m[1], m[2], None))),
    # "Prevent the next X damage that would be dealt to you and/or permanents you control
    # this turn. If damage is prevented this way, ..." (Divine Deflection): the same
    # PREVENTSHIELD sentinel with the player-side "youperms" target.
    (re.compile(r"prevent the next (x|\d+) damage that would be dealt to you and/or permanents "
                r"you control this turn\. if damage is prevented this way, (.+?)\.", re.I),
     lambda m: _sentinel(m, f"PREVENTSHIELD {m[1]} youperms - RIDER", m[2])),
    # "The next time a source of your choice would deal damage to you this turn, prevent
    # that damage. [If damage is prevented this way, ...]" (Deflecting Palm, Intervention
    # Pact, Reverse Damage): one source's next damage — approximated with a rest-of-turn
    # pool (the pool model can't tell sources apart).
    (re.compile(r"the next time a source of your choice would deal damage to you this turn, "
                r"prevent that damage\. (?:if damage is prevented this way, )?(.+?)\.\"?$", re.I),
     lambda m: _sentinel(m, "PALMSHIELD RIDER", m[1])),
    # "The next time target creature would deal combat damage to one or more players this
    # combat, prevent that damage. If damage is prevented this way, ..." (Ria Ivor, Bane
    # of Bladehold): the players' shield for the combat — approximated as the caster's
    # pool for the turn.
    (re.compile(r"the next time target creature would deal combat damage to one or more players "
                r"this combat, prevent that damage\. if damage is prevented this way, "
                r"(.+?)\.\"?$", re.I),
     lambda m: _sentinel(m, "PALMSHIELD RIDER", m[1])),
    # "Prevent all damage that would be dealt to you and permanents you control this turn
    # by sources you don't control. If damage is prevented this way, ..." (Channel Harm).
    (re.compile(r"prevent all damage that would be dealt to you and permanents you control "
                r"this turn by sources you don't control\. if damage is prevented this way, "
                r"(.+?)\.\"?$", re.I),
     lambda m: _sentinel(m, "ALLSHIELD RIDER", m[1])),
]


def _effect(m):
    from .cards import Effect, NO_MATCH, _parse_effects
    amount = 0 if m[1] == "X" else int(m[1])
    data = {"x": True} if m[1] == "X" else {}
    if m[3] != "-":
        data["devotion"] = m[3]
    if m[4] != "-":
        rider, bad = _parse_effects(m[4][0].upper() + m[4][1:] + ".")
        if bad or not rider:
            return NO_MATCH
        data["rider"] = rider
    return Effect("prevent_shield", amount, target=m[2], data=data)


def _sentinel(m, head, rider):
    """head + RIDER + the rider, or the original text when the rider's effects don't parse
    (Ria Ivor's Mite rider: toxic isn't in the token keyword vocabulary yet), so the
    wording stays a readable ignored line."""
    from .cards import _parse_effects
    effects, bad = _parse_effects(rider[0].upper() + rider[1:] + ".")
    if bad or not effects:
        return m[0]
    return f"{head} {rider}."


def _shield_effect(m, kind):
    """A PALMSHIELD/ALLSHIELD sentinel: the rider effects plus which pool the kind fills
    (a full turn's worth for the one-shot wordings, whose real "the next time" limit the
    pool model can't express)."""
    from .cards import Effect, NO_MATCH, _parse_effects
    rider, bad = _parse_effects(m[1][0].upper() + m[1][1:] + ".")
    if bad or not rider:
        return NO_MATCH
    return Effect(kind, 99, data={"rider": rider})


def _that_many_tokens(m):
    """"Create that many <desc> tokens [with ...]" (Ria Ivor's Mite rider): the one-token
    wording of the description, with the prevented total snapshotted into its amount."""
    from .cards import NO_MATCH, _parse_effects
    one = re.sub(r" tokens\b", " token", m[1]) + (m[2] or "")
    effects, bad = _parse_effects("Create one " + one + ".")
    if bad or not effects or effects[0].kind != "token":
        return NO_MATCH
    return dataclasses.replace(effects[0], data=dict(effects[0].data, that_much=True))


EFFECT_PATTERNS = [
    (r"PREVENTSHIELD (\d+|X) (\w+) (-|[WUBRG]) RIDER (.+)", _effect),
    (r"PALMSHIELD RIDER (.+)", lambda m: _shield_effect(m, "prevent_shield")),
    (r"ALLSHIELD RIDER (.+)", lambda m: _shield_effect(m, "prevent_all_turn")),
    # The riders the player-side shields carry (the trigger's context is the damage source)
    (r"~ deals that much damage to that source's controller",
     lambda m: _e("deflect", data={"that_much": True})),
    (r"you gain life equal to the damage prevented this way",
     lambda m: _e("gain_life", data={"that_much": True})),
    (r"you may have ~ deal that much damage to target creature",
     lambda m: _e("damage", target="creature", data={"that_much": True})),
    (r"create that many (.+?) tokens( .+?)?\.\"?", _that_many_tokens),
]


def _e(kind, amount=1, **kw):
    from .cards import Effect
    return Effect(kind, amount, **kw)


def install_player_rider(game, holder, rider, turn):
    """A "damage_prevented" rider with no permanent carrier (Divine Deflection, Deflecting
    Palm: their spells are resolving, nothing of ours is on the battlefield): a one-turn
    EventBus listener queues the rider's effects when the holder's damage is prevented,
    with the prevented total snapshotted into "that much" effects the way the trigger
    dispatch snapshots Game.event_amount. The listener retires itself on the first event
    of a later turn (these shields are all "this turn" wordings)."""
    def listen(event, holder=holder, rider=list(rider), turn=turn):
        if game.turn != turn:
            game.rule_events.listeners.remove(listen)
            return
        if event.kind != "damage_prevented" or event.player is not holder:
            return
        effects = [dataclasses.replace(e, amount=event.amount) if e.data.get("that_much") else e
                   for e in rider]
        game.queue_trigger(holder, effects, None, "prevented-damage rider", context=event.context)
    game.rule_events.listeners.append(listen)
