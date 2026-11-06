"""Grammar verbs for untargeted player subjects ("each player", "that creature's controller", "you", ...):
gain / lose life, draw, discard, mill. The cx_players kind applies them verb by verb. See mtgsim/GRAMMAR.md."""
from __future__ import annotations

from .cx_grammar import Part, count, verb


@verb(r"(gain|lose)s? (\w+) life", heads=("gain", "gains", "lose", "loses"), subjects=("player",))
def life(m, clause):
    n = count(m[2])
    if not n or clause.duration:
        return None
    return [Part("gain_life" if m[1] == "gain" else "lose_life", n)]


@verb(r"(draw|discard|mill)s? (a|an|one|two|three|four|five|six|seven|\d+) cards?",
      heads=("draw", "draws", "discard", "discards", "mill", "mills"), subjects=("player",))
def cards(m, clause):
    n = count(m[2])
    if not n or clause.duration or (n == 1) != clause.verb.endswith(" card"):
        return None
    return [Part(m[1], n)]
