"""Discard replacements onto the battlefield (#628):

    If a spell or ability an opponent controls causes you to discard this card, put it onto the battlefield instead
    of putting it into your graveyard.                                  (Obstinate Baloth, Loxodon Smiter, ...)
    ... put it onto the battlefield with two +1/+1 counters on it instead of putting it into your graveyard. (Dodecapod)

The line is recorded as ``advanced_rules["discard_to_bf"]`` (the +1/+1 counters it enters with). When a card with it
is discarded while a spell or ability an opponent controls is resolving (``game.resolving_item``, set around every
effect handler), the card enters the battlefield under its owner's control instead of going to the graveyard. It
is still a discard: discard triggers fire as usual. A discard you cause yourself (your own spell, a cost, cleanup)
puts it into your graveyard.
"""
from __future__ import annotations

import re

_LINE = re.compile(r"If a spell or ability an opponent controls causes you to discard (?:this card|~), put it onto the "
                   r"battlefield(?: with (?P<n>a|one|two|three|four) \+1/\+1 counters? on it)? instead of putting it "
                   r"into your graveyard\.")
_N = {"a": 1, "one": 1, "two": 2, "three": 3, "four": 4}


def parse_line(line: str, st) -> bool:
    m = _LINE.fullmatch(line.strip())
    if m is None:
        return False
    st.extra.setdefault("advanced_rules", {})["discard_to_bf"] = {"p1": _N[m["n"].lower()] if m["n"] else 0}
    return True


def onto_battlefield(game, p, card) -> bool:
    """Put a discarded card with the replacement onto the battlefield when an opponent's spell or ability is making
    p discard it. True if it did (the caller skips the graveyard)."""
    rule = (getattr(card, "advanced_rules", None) or {}).get("discard_to_bf")
    item = getattr(game, "resolving_item", None)
    if rule is None or item is None or getattr(item, "controller", p) is p or card not in p.hand:
        return False
    p.hand.remove(card)
    n = rule.get("p1", 0)
    game.enter_battlefield(p, card, counters={"+1/+1": n} if n else None)
    game.log(f"{card.name} is put onto the battlefield instead of into the graveyard", p)
    return True
