"""Linked exile for the noun phrases the O-Ring templates don't read (#347):

    [When ~ enters,] exile target creature with mana value 3 or less an opponent controls until ~ leaves the
        battlefield.                                                   (Silkwrap: any battlefield selector)
    exile two target lands until ~ leaves the battlefield.             (Petradon: counted targets)
    For each opponent, exile up to one target nonland permanent that player controls until ~ leaves the
        battlefield.                                                   (Grasp of Fate: one slot per opponent)
    For each player, exile up to one target creature that player controls until ~ leaves the battlefield.
    exile all artifacts your opponents control until ~ leaves the battlefield.   (Consulate Crackdown)
    exile a land you control until ~ leaves the battlefield.          (Wormfang Newt: non-targeted single)
    exile any number of other nonland permanents you control until ~ leaves the battlefield.
                                                                    (Abdel Adrian: non-targeted "any number")

The noun phrase is read by permanent_templates.subject/selector (every word understood or the line stays ignored).
Each target slot is an ``oring`` Effect (engine: Game.exile_until_leaves); a group is ``oring_group``. Both exile
only while the source is still the same object on the battlefield, and the source returns exactly the cards it
exiled, under their owners' control, when it leaves (a token is gone; a card that left exile stays where it is).
The non-targeted forms are ``oring_pick`` (the controller chooses one; the AI gives up its least valuable) and
``oring_any`` ("any number": the AI exiles what pays off — enters-the-battlefield abilities re-fire on the return,
or everything when a "for each ... exiled this way" rider rewards each exile).

A group is read only when the source can't be one of its members ("... your opponents control"): whether a source
that exiles itself along with the rest brings them back at once is left unread (Aligned Hedron Network, Temporary
Lockdown). Joined at the end of cards/__init__.py.
"""
from __future__ import annotations

import dataclasses
import re

_COUNT = {"one": 1, "two": 2, "three": 3}
_UNTIL = r" until (?:~|it) leaves the battlefield"


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
    from .permanent_templates import subject, selector
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
    if re.search(r"\btarget\b", phrase, re.I):
        slots = _slots(phrase)
        return slots if slots is not None else NO_MATCH
    # Non-targeted "exile [any number of] [another|other] <np> you control until ~ leaves": the source's
    # controller chooses; only "you control" is read (exiling an opponent's thing without targeting is not).
    m = re.fullmatch(r"(any number of )?(.+)", phrase, re.I)
    spec = selector(m[2], plural=bool(m[1]))
    if spec is None or spec.get("controller") != "mine":
        return NO_MATCH
    if m[1]:
        return Effect("oring_any", data={"selector": spec})
    return Effect("oring_pick", data={"selector": spec})


EFFECT_PATTERNS = [
    (r"(?:for each (opponent|player), )?exile (.+?)" + _UNTIL, lambda m: _parse(m[1], m[2])),
]


def exiled_rider(s, effects):
    """"Create a 1/1 white Soldier creature token for each permanent exiled this way." (Abdel Adrian):
    scales a token by the count the preceding linked exile actually took, and tells its AI policy that
    every exile pays off."""
    if not effects or effects[-1].kind not in ("oring", "oring_group", "oring_pick", "oring_any",
                                               "blink_link_exile"):
        return False
    m = re.fullmatch(r"create (?:a|an) (.+?) creature tokens? for each permanent exiled this way", s, re.I)
    if m is None:
        return False
    from .cards.parse import _parse_effects
    new, bad = _parse_effects("Create a " + m[1] + " creature token.")
    if bad or len(new) != 1 or new[0].kind != "token":
        return False
    effects[-1] = dataclasses.replace(effects[-1], data=dict(effects[-1].data, for_each_token=new[0],
                                                            reward_each=True))
    return True
