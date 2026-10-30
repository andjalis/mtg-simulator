"""Chance mechanics: clash and coin flips (the general shapes).

"Clash with an opponent. If you win, <X>." and "Flip a coin. If you win / lose the flip,
<X>." become a gate effect (``clash`` / ``flip_coin``: the kind resolves the chance and
sets item.gate_paid, the pay_gate pattern) followed by the payoff effects with cond
"paid". "Whenever you clash [, and win]" is a you_clash / you_win_clash trigger the
``clash`` kind fires. The revealed clash cards stay where they are (the real wording lets
each player put them on top or bottom: recorded simplification). Die rolls need per-face
amount plumbing the engine doesn't have — a foundation need, not covered here.
"""
from __future__ import annotations

import dataclasses
import re


def _gated(gate_effect, rider):
    from .cards import NO_MATCH, _parse_effects
    payoff, bad = _parse_effects(rider[0].upper() + rider[1:] + ".")
    if bad or not payoff:
        return NO_MATCH
    return [gate_effect] + [dataclasses.replace(e, cond=e.cond or "paid") for e in payoff]


SUBS = [
    # "Clash with an opponent. If you win, <X>." (also "defending player", "If you won")
    (re.compile(r"clash with (?:an opponent|defending player|target opponent)\. "
                r"if you (?:win|won), ([^.]+)\.?", re.I),
     lambda m: f"CLASHWIN {m[1]}."),
    # "Flip a coin. If/When you win/lose the flip, <X>."
    (re.compile(r"flip a coin\. (?:if|when) you (win|lose) the flip, ([^.]+)\.?", re.I),
     lambda m: f"FLIPCOIN {m[1].lower()} {m[2]}."),
]


def _clash(m):
    from .cards import Effect
    return _gated(Effect("clash"), m[1])


def _flip(m):
    from .cards import Effect
    data = {"on_lose": True} if m[1] == "lose" else {}
    return _gated(Effect("flip_coin", data=data), m[2])


def _plain(m):
    """A bare "Flip a coin." sentence: the coin toss on its own."""
    from .cards import Effect
    return Effect("flip_coin")


def _clash_plain(m):
    from .cards import Effect
    return Effect("clash")


EFFECT_PATTERNS = [
    (r"CLASHWIN (.+)", _clash),
    (r"FLIPCOIN (win|lose) (.+)", _flip),
    # "Clash with an opponent." with no rider (Oaken Brawler), and a coin flip with no
    # rider sentence ("You may flip a coin.")
    (r"clash with (?:an opponent|defending player|target opponent)", _clash_plain),
    (r"flip a coin", _plain),
]

TRIGGERS = [
    (r"Whenever you clash and win, (.+)", ("you_win_clash",)),
    (r"Whenever you win a clash, (.+)", ("you_win_clash",)),
    (r"Whenever you clash, (.+)", ("you_clash",)),
]
