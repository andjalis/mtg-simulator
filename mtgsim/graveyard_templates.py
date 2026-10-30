"""Graveyard family templates: digging into hand-and-graveyard splits, self-return riders.

Joined at the end of ``cards/__init__.py``. Wordings that already parse are left to the
tables defined earlier; the DIGGY/FOF sentinels below are produced by SUBS rewrites of the
"look/reveal the top N ... put K into your hand and the rest into your graveyard" cluster.
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
]




def _e(kind, amount=1, amount2=0, **kw):
    from .cards import Effect
    return Effect(kind, amount, amount2, **kw)


def _num(word):
    from .cards import _num as number
    return number(word)
