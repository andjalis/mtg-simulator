"""Scaled effects written "... equal to <quantity>": damage, life, draw and mill, when the quantity is one the engine
already knows (clauses._xq: cards in hand, creatures you control, counters on ~, cards in your graveyard, ...).

Each template rewrites to the fixed-amount sentence ("deals 1 damage to ...") that the parser already understands and
scales its amount by the quantity, the way ", where X is <quantity>" does. A quantity that reads the previous effect's
target ("that creature's power") is left alone: it is only right after a destroy or exile that records that target.
"""
from __future__ import annotations


def _known_words(what):
    """Whether copies.fits understands every word of a count's description (an unknown lower-case word counts nothing)."""
    from .copies import _TYPES
    return all(w[0].isupper() or w.lower() in _TYPES or w.lower() in ("creature", "token", "nontoken", "nonland",
                                                                    "noncreature", "nonartifact", "basic", "permanent")
               or w.lower().startswith("non-") for w in what.split())


def _quantity(text):
    from .cards.clauses import _xq
    spec = _xq(text)
    if spec is None or "prev" in spec or (spec[0] == "count" and not _known_words(spec[1])):
        return None
    return spec


def _scaled(fixed):
    """Template builder: fixed(m) is the plain sentence with amount 1; the last group is the quantity."""
    def build(m):
        from .cards import _parse_effects
        from .cards.model import NO_MATCH
        spec = _quantity(m[m.lastindex])
        if spec is None:
            return NO_MATCH
        effects, unmatched = _parse_effects(fixed(m))
        if unmatched or len(effects) != 1:
            return NO_MATCH
        effects[0].data["xq"] = spec
        return effects[0]
    return build


EFFECT_PATTERNS = [
    (r"~ deals damage to (any target|target [\w ,'-]+?) equal to (.+)",
     _scaled(lambda m: f"~ deals 1 damage to {m[1]}")),
    (r"you gain life equal to (.+)", _scaled(lambda m: "You gain 1 life")),
    (r"you lose life equal to (.+)", _scaled(lambda m: "You lose 1 life")),
    (r"(target player|target opponent|each opponent) loses life equal to (.+)",
     _scaled(lambda m: f"{m[1]} loses 1 life")),
    (r"draw cards equal to (.+)", _scaled(lambda m: "Draw a card")),
    (r"target player draws cards equal to (.+)", _scaled(lambda m: "Target player draws a card")),
    (r"(target player|target opponent|each opponent) mills cards equal to (.+)",
     _scaled(lambda m: f"{m[1]} mills a card")),
]
