"""Linked exile for the noun phrases the O-Ring templates don't read (#347):

    [When ~ enters,] exile target creature with mana value 3 or less an opponent controls until ~ leaves the
        battlefield.                                                   (Silkwrap: any battlefield selector)
    exile two target lands until ~ leaves the battlefield.             (Petradon: counted targets)
    For each opponent, exile up to one target nonland permanent that player controls until ~ leaves the
        battlefield.                                                   (Grasp of Fate: one slot per opponent)
    For each player, exile up to one target creature that player controls until ~ leaves the battlefield.
    exile all artifacts your opponents control until ~ leaves the battlefield.   (Consulate Crackdown)

The noun phrase is read by permanent_templates.subject (every word understood or the line stays ignored). Each
target slot is an ``oring`` Effect (engine: Game.exile_until_leaves); a group is ``oring_group``. Both exile
only while the source is still the same object on the battlefield, and the source returns exactly the cards it
exiled, under their owners' control, when it leaves (a token is gone; a card that left exile stays where it is).

A group is read only when the source can't be one of its members ("... your opponents control"): whether a source
that exiles itself along with the rest brings them back at once is left unread (Aligned Hedron Network, Temporary
Lockdown).

"Exile that creature until ~ leaves the battlefield" (#507) is the same link with the trigger's event object as
the exiled permanent: under "becomes blocked by a creature" that is the blocker, under "a creature deals combat
damage to you" the attacker — both are the trigger item's context, so the Effect is target ``prev``. The phrase
is read only under those heads (``_PREV_EVENTS``): anywhere else "that creature" names something else (a chosen
target, as in Turncoat Kunoichi) and the sentence stays ignored.

Joined at the end of cards/__init__.py.
"""
from __future__ import annotations

import re

_COUNT = {"one": 1, "two": 2, "three": 3}
_UNTIL = r" until ~ leaves the battlefield"
# Trigger heads whose event carries a creature as the trigger's context (the blocker / the attacker / the
# other combatant), so "that creature" in the payoff is target "prev". Read from cx_tokens._ctx_events while a
# trigger body parses.
_PREV_EVENTS = frozenset({"blocked_by", "blocks", "becomes_blocked", "combat_damage_player", "ally_combat_damage"})


def _prev_oring(m):
    from . import cx_tokens
    from .cards import Effect, NO_MATCH
    if not any(e in _PREV_EVENTS for e in cx_tokens._ctx_events):
        return NO_MATCH          # not a head that carries the creature: leave the sentence ignored
    return [Effect("oring", target="prev", data={"event_prev": True})]


def _slots(phrase, scope=None):
    """Effects for "[up to N] [another] target <np>" (one per target), or None."""
    from .cards import Effect
    from .permanent_templates import subject
    m = re.fullmatch(r"(?:(up to )?(one|two|three) )?((?:another |other )?target )(.+)", phrase, re.I)
    if m is None or m[1] and not m[2]:
        return None
    np = m[4]
    n = _COUNT[m[2].lower()] if m[2] else 1
    if n > 1:                       # "two target lands": the selector reads one noun
        np = re.sub(r"\b(creature|land|artifact|enchantment|permanent|planeswalker)s\b", r"\1", np)
    if scope is not None:
        if not np.endswith(" that player controls"):
            return None
        np = np[:-len(" that player controls")] + scope
    subj = subject(m[3] + np)
    if subj is None or subj[0] != "permanent":
        return None
    data = dict(subj[1])
    if m[1]:
        data["optional_target"] = True
    if n > 1:
        data["distinct"] = True
    return [Effect("oring", target="permanent", data=dict(data)) for _ in range(n)]


def _parse(each, phrase):
    from .cards import Effect, NO_MATCH
    from .permanent_templates import subject
    if each:
        if not re.match(r"up to one ", phrase, re.I):
            return NO_MATCH          # "for each opponent, exile target ...": one required target per player
        scopes = [" an opponent controls"] if each.lower() == "opponent" else [" you control", " an opponent controls"]
        out = []
        for scope in scopes:
            slots = _slots(phrase, scope)
            if slots is None:
                return NO_MATCH
            out += slots
        return out
    if re.match(r"(?:all|each) ", phrase, re.I):
        subj = subject(phrase)
        if subj is None or subj[0] != "group" or subj[1]["selector"].get("controller") != "opp":
            return NO_MATCH
        return Effect("oring_group", data={"selector": subj[1]["selector"]})
    slots = _slots(phrase)
    return slots if slots is not None else NO_MATCH


EFFECT_PATTERNS = [
    (r"exile (?:that creature|that permanent|it)" + _UNTIL, _prev_oring),
    (r"(?:for each (opponent|player), )?exile (.+?)" + _UNTIL, lambda m: _parse(m[1], m[2])),
]
