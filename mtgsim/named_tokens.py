"""Named legendary tokens (#525, a #314 leftover).

    Create Mowu, a legendary 3/3 green Dog creature token.                                     (Jiang Yanggu)
    Create Voja, Friend to Elves, a legendary 3/3 green and white Wolf creature token.        (Tolsimir)
    If you don't control a creature named Darkstar, create Darkstar, a legendary 2/2 ... token. (Rufus Shinra)

The rest of the sentence ("a 3/3 green Dog creature token [with ...]") is read by the existing token templates;
the token then carries its own name (so "a creature named Mowu" and the legend rule see it) and is legendary.
Names built on the card's own name ("~ Twin", "~'s Notebook") stay unmatched: the parser has already replaced
the name with ~ and a token can't be named after that placeholder.
"""
from __future__ import annotations



def _named(m):
    from .cards.model import NO_MATCH
    from .cards.parse import _parse_effects
    name = m[1].strip()
    if "~" in name or not name[:1].isupper():
        return NO_MATCH
    effects, bad = _parse_effects("Create a " + m[2] + ".")
    if bad or len(effects) != 1 or effects[0].kind != "token" or effects[0].amount != 1 or effects[0].data.get("kind"):
        return NO_MATCH
    eff = effects[0]
    eff.data = dict(eff.data, token_name=name, legendary=True)
    return eff


EFFECT_PATTERNS = [
    (r"create ([A-Z][^.]*?), a legendary (\d+/\d+ [^.]+? creature token(?: with [^.\"]+)?)", _named),
]
