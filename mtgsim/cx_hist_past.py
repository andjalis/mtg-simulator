"""Turn history in the past tense the trigger grammar reads in the present (#397, slice 2).

    if you lost life last turn, ...                           -> "Whenever you lose life", last turn
    if a creature card was put into your graveyard from anywhere this turn, ...
    if a player discarded a card this turn, ...
    if you didn't play a land this turn, ...                    -> not "Whenever you play a land"
    if no creatures died this turn, ...                          -> not "Whenever a creature dies"
    if you gained or lost life this turn, ...                    -> either head

``heads(body)`` turns the event part of "<event> this turn" / "<event> last turn" into present-tense trigger heads
that ``cx_events.compile_head`` must accept; cx_condlib's turn history (``record`` / the ``hist`` condition)
counts them. Anything it can't read faithfully stays unread:
- "another ...": the history isn't kept per source, so "another creature entered" would count ~ itself;
- a referent (it / that / this / ~ / they): the history is kept per player, not per object;
- an amount on life or damage ("lost 3 or more life"): the history counts events, not totals.
"""
from __future__ import annotations

import re

# past tense or past participle -> base form
_BASE = {
    "entered": "enter", "died": "die", "left": "leave", "cast": "cast", "gained": "gain", "lost": "lose",
    "attacked": "attack", "blocked": "block", "discarded": "discard", "drew": "draw", "drawn": "draw",
    "sacrificed": "sacrifice", "created": "create", "put": "put", "cycled": "cycle", "played": "play",
    "milled": "mill", "searched": "search", "scried": "scry", "surveilled": "surveil", "activated": "activate",
    "explored": "explore", "investigated": "investigate", "proliferated": "proliferate", "committed": "commit",
    "tapped": "tap", "untapped": "untap", "exiled": "exile", "returned": "return", "countered": "counter",
}
_THIRD = {"die": "dies", "leave": "leaves", "cast": "casts", "draw": "draws", "put": "puts", "lose": "loses",
          "search": "searches", "scry": "scries"}
_PASSIVE = ("put", "returned", "exiled", "countered", "tapped", "untapped", "sacrificed", "discarded", "milled",
            "cast", "dealt")
_SUBJ = r"(?P<s>you|an opponent|a player)"
_REFUSE = re.compile(r"\b(?:another|it|its|that|those|this|they|their|them|he|she|~)\b", re.I)
_AMOUNT = re.compile(r"\b(?:los[et]|gain(?:ed)?|dealt|damage)\b.*\b(?:\d+|one|two|three|four|five|six|seven|"
                     r"eight|nine|ten|or more|or less|or fewer|more than|less than)\b", re.I)


def _verb(base: str, subject: str) -> str:
    return base if subject.lower() == "you" else _THIRD.get(base, base + "s")


def _present(body: str) -> str | None:
    """"a creature card was put into your graveyard" -> "a creature card is put into your graveyard";
    "you've cast a red spell" -> "you cast a red spell"; "an opponent lost life" -> "an opponent loses life"."""
    body = re.sub(r"^(you)(?:'ve| have) ", r"\1 ", body, flags=re.I)
    passive = re.fullmatch(rf"(?P<a>.+?) (?P<be>was|were) (?P<v>{'|'.join(_PASSIVE)})\b(?P<r>.*)", body, re.I)
    if passive:
        return f"{passive['a']} {'is' if passive['be'].lower() == 'was' else 'are'} {passive['v']}{passive['r']}"
    words = body.split(" ")
    for i, w in enumerate(words[1:], 1):
        base = _BASE.get(w.lower())
        if base is not None:
            words[i] = _verb(base, " ".join(words[:i]))
            return " ".join(words)
    return None


def _singular(noun: str) -> str:
    return re.sub(r"ies$", "y", noun) if noun.endswith("ies") else re.sub(r"s$", "", noun)


def heads(body: str):
    """(present-tense heads, negated) for the event part of a turn-history condition, or None. Several heads
    mean any of them ("you gained or lost life")."""
    from .cx_events import compile_head
    body = body.strip()
    if "~" in body or _REFUSE.search(body) or _AMOUNT.search(body):
        return None
    negate = False
    neg = re.fullmatch(rf"{_SUBJ} (?:didn't|did not|haven't|hasn't|have not|has not) (?P<v>\w+)(?P<r>.*)", body, re.I)
    none = re.fullmatch(r"no (?P<n>[a-z]+s) (?P<v>\w+)(?P<r>.*)", body, re.I)
    pair = re.fullmatch(rf"{_SUBJ} (?P<v1>\w+) or (?P<v2>\w+)(?P<r>.*)", body, re.I)
    if neg:
        base = _BASE.get(neg["v"].lower(), neg["v"].lower())
        if base not in _BASE.values():
            return None
        texts, negate = [f"{neg['s']} {_verb(base, neg['s'])}{neg['r']}"], True
    elif none and none["v"].lower() in _BASE:
        noun = _singular(none["n"])
        art = "an" if noun[0] in "aeiou" else "a"
        texts, negate = [f"{art} {noun} {_THIRD.get(_BASE[none['v'].lower()], _BASE[none['v'].lower()] + 's')}"
                         f"{none['r']}"], True
    elif pair and pair["v1"].lower() in _BASE and pair["v2"].lower() in _BASE:
        texts = [f"{pair['s']} {_verb(_BASE[pair[v].lower()], pair['s'])}{pair['r']}" for v in ("v1", "v2")]
    else:
        text = _present(body)
        texts = [text] if text else []
    if not texts:
        return None
    out = []
    for text in texts:
        got = compile_head("Whenever " + text)
        if got is None:
            return None
        out.append((text, got))
    return out, negate
