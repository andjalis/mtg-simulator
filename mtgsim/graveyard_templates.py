"""Graveyard family templates: digging into hand-and-graveyard splits, self-return riders.

Joined at the end of ``cards/__init__.py``. Wordings that already parse are left to the
tables defined earlier; the DIGGY/FOF sentinels below are produced by SUBS rewrites of the
"look/reveal the top N ... put K into your hand and the rest into your graveyard" cluster.
The same goes for the bottom-of-library dig riders ("put the rest on the bottom of your
library in a random order"), the "put all <desc> cards revealed this way" splits, the
battlefield dig puts (DIGBPUT/DIGBATTLE) and "Shuffle ~ into its owner's library."
"""
from __future__ import annotations

import re


EFFECT_PATTERNS = [
    # "Look at the top N cards of your library. Put K of them into your hand and the rest
    # into your graveyard." (also "... and the other ...", for two cards looked at).
    (r"DIGGY (\w+) (\w+)", lambda m: _e("dig_gy", _num(m[1]), _num(m[2]))),
    # "Look at the top N cards of your library. You may put one of those cards back on top
    # of your library. Put the rest into your graveyard."
    (r"DIGGYTOP (\w+)", lambda m: _e("dig_gy", _num(m[1]), data={"to_top": 1})),
    # "Reveal the top N cards of your library. You may put a <desc> card from among them
    # into your hand. Put the rest into your graveyard."
    (r"DIGGYFILTER (\w+) (.+)", lambda m: _e("dig_gy", _num(m[1]), 1, data={"filter": m[2]})),
    # "... You may put any number of <desc> cards from among them into your hand. ..."
    (r"DIGGYANY (\w+) (.+)", lambda m: _e("dig_gy", _num(m[1]), 0, data={"filter": m[2], "any": True})),
    # "... You may put a <t1> card and/or a <t2> card from among them into your hand. ..."
    (r"DIGGYTYPES (\w+) (.+)", lambda m: _e("dig_gy", _num(m[1]), data={"types": m[2].split()})),
    # Fact or Fiction and friends: an opponent splits, you keep the better pile.
    (r"FOF (\w+)", lambda m: _e("fof", _num(m[1]))),
    (r"FOFXP1", lambda m: _e("fof", 1, data={"x_plus": 1})),
    # "Return this card from your graveyard to your hand / the battlefield" (modern wording;
    # the "~" phrasing is already handled in cards/patterns.py, including "you may" gates).
    (r"(?:you may )?return this card from your graveyard to your hand",
     lambda m: _e("return_self_gy", data={"to": "hand"})),
    (r"(?:you may )?return this card from your graveyard to the battlefield( tapped)?",
     lambda m: _e("return_self_gy", data={"tapped": bool(m[1])})),
    # "Shuffle ~ into its owner's library." (the Beacon and Zenith spells): a marker the
    # stack reads after the spell resolves (Game.to_graveyard_after_resolving).
    (r"shuffle ~ into its owner's library", lambda m: _e("shuffle_self")),
    # "Shuffle it / this card into its owner's library." on a dies (or put-into-a-graveyard)
    # trigger: the source has already left the battlefield, so shuffle_away takes the card
    # out of its owner's graveyard instead (Angel of Fury, Cavalier of Gales, Dread).
    (r"shuffle (?:it|this card) into (?:its|his|her) owner's library",
     lambda m: _e("shuffle_away", target="self")),
    # Bottom-of-library dig sentinels (see SUBS): keep up to K (or all matching, or up to
    # two revealed) in hand, the rest shuffled to the bottom; DIGBPUT puts up to K
    # matching cards onto the battlefield (tapped) instead of into the hand.
    (r"DIGB2 (\d+) (\d+) (.+)", lambda m: _e("dig", int(m[1]), int(m[2]), data={"filter": m[3]})),
    (r"DIGBANY (\d+) (.+)", lambda m: _e("dig", int(m[1]), int(m[1]), data={"filter": m[2]})),
    (r"DIGBPUT (\d+) (\d+) (.+?)( tapped)?(?: mv(\d+))?( hand)?",
     lambda m: _e("dig_put_filter", int(m[1]), int(m[2]),
                  data={"filter": m[3], "tapped": bool(m[4]),
                        "max_cmc": int(m[5]) if m[5] else None, "rest": "hand" if m[6] else "bottom"})),
    (r"DIGBATTLE (\d+) (.+?)( hand)?",
     lambda m: _e("dig_put_filter", int(m[1]), int(m[1]),
                  data={"filter": m[2], "rest": "hand" if m[3] else "bottom"})),
    (r"DIGALL (\d+) (hand|gy|bottom) (hand|gy|bottom) (.+)",
     lambda m: _e("dig_all", int(m[1]), data={"keep": m[2], "rest": m[3], "filter": m[4]})),
]



def _diggy_choose(m):
    """"... you may put a <desc> card ... from among them into your hand. Put the rest into
    your graveyard": one card of any listed type ("or"), or one of each ("and/or")."""
    if " and/or " in m[2]:
        types = re.findall(r"(\w+) cards?", m[2])
        if len(set(types)) != len(types) or not types:
            return m[0]
        return f"DIGGYTYPES {_num(m[1])} {' '.join(types)}."
    return f"DIGGYFILTER {_num(m[1])} {m[2]}."


SUBS = [
    (re.compile(r"(?:look at|reveal) the top (\w+) cards of your library[.,]?\s*(?:then )?"
                r"put (one|two|three|four|five|six|seven|eight|nine|ten|\d+)(?: of them)? into your hand "
                r"and the (?:other|rest) into your graveyard\.?", re.I),
     lambda m: f"DIGGY {_num(m[1])} {_num(m[2])}."),
    (re.compile(r"(?:look at|reveal) the top (\w+) cards of your library\. you may reveal "
                r"an? ([^.]+? card) from among them and put it into your hand\. put the rest into your "
                r"graveyard\.?", re.I),
     lambda m: f"DIGGYFILTER {_num(m[1])} {m[2]}."),
    (re.compile(r"(?:look at|reveal) the top (\w+) cards of your library\. you may put "
                r"an? ([^.]+? cards?) from among them into your hand\. put the rest into your "
                r"graveyard\.?", re.I),
     _diggy_choose),
    (re.compile(r"(?:look at|reveal) the top (\w+) cards of your library\. you may put "
                r"any number of ([^.]+?) cards from among them into your hand\. put the rest into your "
                r"graveyard\.?", re.I),
     lambda m: f"DIGGYANY {_num(m[1])} {m[2]}."),
    (re.compile(r"look at the top (\w+) cards of your library\. you may put one of those cards back on "
                r"top of your library\. put the rest into your graveyard\.?", re.I),
     lambda m: f"DIGGYTOP {_num(m[1])}."),
    # Fact or Fiction wording, both split variants (and "X plus one" cards).
    (re.compile(r"reveal the top (\w+) cards of your library\. an opponent separates those cards into "
                r"two piles\. put (?:one|that) pile into your hand and the other into your graveyard\.?", re.I),
     lambda m: "FOFXP1." if m[1].lower() == "x" else f"FOF {_num(m[1])}."),
    (re.compile(r"reveal the top ((?:\w+) plus one) cards of your library and separate them into two "
                r"piles\. an opponent chooses one of those piles\. put that pile into your hand and the "
                r"other into your graveyard\.?", re.I),
     lambda m: "FOFXP1."),
    (re.compile(r"reveal the top (\w+) cards of your library and separate them into two piles\. "
                r"an opponent chooses one of those piles\. put that pile into your hand and the other into "
                r"your graveyard\.?", re.I),
     lambda m: f"FOF {_num(m[1])}."),
    # Bottom-of-library dig variants the cards/clauses.py sentinels don't cover: "put that
    # card into your hand", "reveal up to two <desc> cards ... put them", "any number of
    # <desc> cards" (reveal or plain) and "put (up to) <desc> cards onto the battlefield".
    (re.compile(r"(?:look at|reveal) the top (\w+) cards of your library\. you may reveal "
                r"(an? [^.]+? card) from among them and put that card into your hand\. "
                r"put the rest on the bottom of your library in (?:a random|any) order\.?", re.I),
     lambda m: _sentinel(m, "DIGFILTER", [1], extra=2)),
    (re.compile(r"(?:look at|reveal) the top (\w+) cards of your library\. you may reveal "
                r"up to (two|three|four) ([^.]+?) cards from among them and put them into your hand\. "
                r"put the rest on the bottom of your library in (?:a random|any) order\.?", re.I),
     lambda m: _sentinel(m, "DIGB2", [1, 2], desc=3)),
    (re.compile(r"(?:look at|reveal) the top (\w+) cards of your library\. you may reveal "
                r"any number of ([^.]+?) cards from among them and put the revealed cards into "
                r"your hand\. put the rest on the bottom of your library in (?:a random|any) order\.?",
                re.I), lambda m: _digbany(m)),
    (re.compile(r"(?:look at|reveal) the top (\w+) cards of your library\. you may put "
                r"any number of ([^.]+?) cards from among them into your hand\. "
                r"put the rest on the bottom of your library in (?:a random|any) order\.?", re.I),
     lambda m: _digbany(m)),
    (re.compile(r"(?:look at|reveal) the top (\w+) cards of your library\. put up to "
                r"(one|two|three|four) ([^.]+?) cards(?: with mana value (\w+) or less)? from among "
                r"them onto the battlefield( tapped)?[.,]? ?(?:and|then put|put) the rest on the "
                r"bottom of your library in (?:a random|any) order\.?", re.I),
     lambda m: _digbput(m)),
    (re.compile(r"(?:look at|reveal) the top (\w+) cards of your library\. you may put "
                r"an? ([^.]+?) card from among them onto the battlefield( tapped)?\. "
                r"put the rest on the bottom of your library in (?:a random|any) order\.?", re.I),
     lambda m: _digbput(m, single=True)),
    # "... Put any number of <desc> cards from among them onto the battlefield and the
    # rest into your hand / on the bottom of the library." (Genesis Ultimatum)
    (re.compile(r"(?:look at|reveal) the top (\w+) cards of your library\. (?:you may )?put "
                r"any number of ([^.]+?) cards? from among them onto the battlefield"
                r"(,? and the rest into your hand|\. put the rest on the bottom of your "
                r"library in (?:a random|any) order)\.?", re.I),
     lambda m: _digbattle(m)),
    # "Reveal the top N cards of your library. Put all <desc> cards revealed this way into
    # your hand or graveyard and the rest into the other zone / on the bottom of the
    # library." (Mulch, Beast Hunt, Goblin Ringleader, Elder Pine of Jukai, ...)
    (re.compile(r"(?:reveal|look at) the top (\w+) cards of your library\. put all ([^.]+?) cards "
                r"revealed this way into your (hand|graveyard) and the rest (?:into your "
                r"(graveyard|hand)|on the bottom of your library in (?:a random|any) order)\.?",
                re.I), lambda m: _digall(m)),
]


def _sentinel(m, name, numbers, desc=None, extra=None):
    """name + the converted numbers + the normalized description (or an extra raw group),
    or the original line when a number word is beyond the table (fourteen, twenty, ...)."""
    from .cards import _num
    out = name
    for group in numbers:
        try:
            out += f" {_num(m[group])}"
        except ValueError:
            return m[0]
    if desc is not None:
        out += f" {_card_desc(m[desc])}"
    if extra is not None:
        out += f" {m[extra]}"
    return out + "."


def _digbput(m, single=False):
    """DIGBPUT with optional tapped and mana-value-bound suffixes."""
    from .cards import _num
    try:
        n = _num(m[1])
        k = 1 if single else _num(m[2])
        mv = _num(m[4]) if not single and m[4] else None
    except ValueError:
        return m[0]
    desc = _card_desc(m[2] if single else m[3])
    tapped = m[3] if single else m[5]
    out = f"DIGBPUT {n} {k} {desc}{' tapped' if tapped else ''}{' mv' + str(mv) if mv else ''}."
    return out


def _digbattle(m):
    """DIGBATTLE: all matching cards onto the battlefield, the rest to hand or bottom."""
    from .cards import _num
    try:
        n = _num(m[1])
    except ValueError:
        return m[0]
    return f"DIGBATTLE {n} {_card_desc(m[2])}{' hand' if 'hand' in (m[3] or '') else ''}."


def _digall(m):
    """"Put all <desc> cards revealed this way ...": the chosen type is not tracked, so the
    wording stays a readable ignored line rather than dumping every revealed card."""
    if "chosen" in m[2]:
        return m[0]
    from .cards import _num
    try:
        n = _num(m[1])
    except ValueError:
        return m[0]
    keep = "hand" if m[3] == "hand" else "gy"
    rest = {"graveyard": "gy", "hand": "hand"}.get(m[4], "bottom")
    return f"DIGALL {n} {keep} {rest} {_card_desc(m[2])}."


def _digbany(m):
    """"any number of <desc> cards": the chosen type is not tracked, so the wording
    stays a readable ignored line rather than keeping nothing."""
    if "chosen" in m[2]:
        return m[0]
    return _sentinel(m, "DIGBANY", [1], desc=2)


def _card_desc(words):
    """"artifact cards" / "creature cards" → "an artifact card", the filter style
    card_matches understands (alternatives stay alternatives)."""
    words = words.replace(" and/or ", " or ").replace(", or ", " or ").replace(", ", " or ").strip()
    return ("an " if words[0].lower() in "aeiou" else "a ") + words




def _e(kind, amount=1, amount2=0, **kw):
    from .cards import Effect
    return Effect(kind, amount, amount2, **kw)


def _num(word):
    from .cards import _num as number
    return number(word)


# "When ~ is put into a graveyard from anywhere, ..." (the Lorwyn incarnations and friends:
# Dread, Serra Avatar, Worldspine Wurm). Approximated as a dies trigger — the engine has no
# put-into-graveyard-from-anywhere event, so discards and mills of the card don't fire it.
TRIGGERS = [
    (r"When ~ is put into a graveyard from anywhere, (.+)", ("dies",)),
]
