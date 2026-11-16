"""Amounts read from a card an earlier effect moved or revealed (#313): "... equal to that card's mana value".

    Target opponent reveals a card at random from their hand. ~ deals damage equal to that card's mana value to
    that player.                                                                        (Planeswalker's Fury)
    You may put target creature card from your graveyard on top of your library. If you do, ~ deals damage equal
    to that card's power to target creature.                                            (Dead Reckoning)
    Mill a card, then draw cards equal to the milled card's mana value.                 (Heed the Mists)
    {R}, {T}, Discard a card: ~ deals damage to target creature equal to the discarded card's mana value.

"That card" (also "the milled / revealed / exiled / discarded card") is the card the previous effect of the same
ability moved or revealed. Its power, toughness and mana value are frozen on the stack item when it moves
(``referent.remember_card``), so later changes don't matter, and the X-quantity ("card", stat) reads them. The
sentence is accepted only right after an effect kind that records exactly one card (``RECORDERS``; a discard or a
mill of one card); anywhere else it stays unmatched. With no effect before it, "the discarded card" / "the exiled
card" is the card discarded or exiled to pay the cost: the ("discarded", stat) / ("exiled_gy", stat) quantities.

The amount is parsed by the templates that already read "... equal to <quantity>": the sentence is parsed with a
stand-in quantity, and the stand-in is then swapped for the card's stat. "A, then B" with the reference in B is
read as two sentences.

"Target player reveals a card at random from their hand" is the ``reveal_random`` kind: it reveals (and records)
one card, which stays in the hand.
"""
from __future__ import annotations

import dataclasses
import re

# Effect kinds whose handler records the one card they move or reveal (referent.remember_card): "card" quantities
# read it. discard and mill record only when they move exactly one card.
RECORDERS = {"regrow_any", "exile_top", "cx_card_move", "peek_top", "gy_move", "grave_library_top", "reveal_random"}
_ONE_CARD = {"discard", "mill"}
_STAND_IN = "your life total"
_REF = re.compile(r"\bequal to (that card's|the (?:exiled|discarded|revealed|milled) card's) "
                  r"(power|toughness|mana value)\b", re.I)


def _recorder(effects):
    """The effect "that card" refers to: the last one that isn't a gate, if it records one card."""
    last = next((e for e in reversed(effects) if e.kind not in ("pay_gate", "link_check")), None)
    if last is None:
        return None
    if last.kind in RECORDERS and (last.kind != "gy_move" or last.amount == 1):
        return last
    if last.kind in _ONE_CARD and last.amount == 1 and not last.data.get("xq"):
        return last
    return None


_X_FORMS = [      # "... equal to Q" -> the same sentence with X, read as ", where X is Q"
    (re.compile(r"\bdeals? damage equal to Q to (.+)", re.I), r"deals X damage to \1"),
    (re.compile(r"\bdeals? damage to (.+?) equal to Q\b", re.I), r"deals X damage to \1"),
    (re.compile(r"\b(gains?|loses?) life equal to Q\b", re.I), r"\1 X life"),
    (re.compile(r"\b(draws?|mills?) cards equal to Q\b", re.I), r"\1 X cards"),
]


def _swap(s, spec):
    """Effects for sentence s with its card reference read as the quantity spec, or None: first with a stand-in
    quantity the "equal to <quantity>" templates know, else as "... X ..., where X is <stand-in>"."""
    from .cards import _parse_effects
    m = _REF.search(s)
    body = s[:m.start()] + "equal to " + _STAND_IN + s[m.end():]
    if _REF.search(body):
        return None             # two references: not read here
    new, bad = _parse_effects(body[0].upper() + body[1:] + ".")
    swapped = [e for e in new if e.data.get("xq") == ("life",)]
    if bad or not new or len(swapped) != 1:
        q = s[:m.start()] + "equal to Q" + s[m.end():]
        for rx, rep in _X_FORMS:
            if rx.search(q) and not re.search(r"\bX\b", s):
                body = rx.sub(rep, q, count=1)
                new, bad = _parse_effects(body[0].upper() + body[1:] + ", where X is " + _STAND_IN + ".")
                swapped = [e for e in new if e.data.get("xq") == ("life",)]
                break
    if bad or not new or len(swapped) != 1:
        return None
    return [dataclasses.replace(e, data=dict(e.data, xq=spec)) if e is swapped[0] else e for e in new]


def parse_rider(s, effects) -> bool:
    """cards/parse.py sentence hook: True when s was read (its Effects appended to effects)."""
    from .they_each import parse_rider as they_each
    if they_each(s, effects):          # "They each get +2/+2 until end of turn" after counted targets
        return True
    m = _REF.search(s)
    if m is None:
        return False
    then = re.fullmatch(r"(.+?), then (.+)", s, re.I)
    if then and not _REF.search(then[1]) and _REF.search(then[2]):
        from .cards import _parse_effects
        first, bad = _parse_effects(then[1][0].upper() + then[1][1:] + ".")
        if first and not bad and _recorder(first) is not None:
            rest = _rest(then[1], then[2])
            if rest is not None:
                new = _swap(rest, ("card", m[2].lower()))
                if new is not None:
                    effects += first + _that_player(new, _recorder(first))
                    return True
        return False
    stat, which = m[2].lower(), m[1].lower()
    recorder = _recorder(effects)
    if recorder is not None:
        spec = ("card", stat)
    elif not [e for e in effects if e.kind not in ("pay_gate", "link_check")] and which in ("the discarded card's", "the exiled card's"):
        spec = ("discarded" if "discarded" in which else "exiled_gy", stat)      # the cost's card
    else:
        return False
    new = _swap(s, spec)
    if new is None:
        return False
    effects += _that_player(new, recorder)
    return True


def _that_player(new, recorder):
    """"That player" after "target player reveals / discards ...": the player that effect targeted (the previous
    target on resolution), not a trigger's event player."""
    if recorder is None or recorder.target != "player":
        return new
    return [dataclasses.replace(e, target="prev") if e.target == "that_player" else e for e in new]


def _rest(first: str, rest: str):
    """The second half of "A, then B" as a sentence of its own: "target player reveals ..., then loses life ..."
    -> "That player loses life ..."; an imperative B ("mill a card, then draw cards ...") stays as it is."""
    subj = re.match(r"(target player|target opponent|you) ", first, re.I)
    if rest.split(" ", 1)[0].lower().endswith("s"):         # a third-person verb: the subject of A
        if subj is None or subj[1].lower() == "you":
            return None
        return "That player " + rest
    return ("You " + rest) if subj is not None and subj[1].lower() == "you" else rest


def _reveal(m):
    from .cards import Effect
    opp = m[1].lower() == "opponent"
    return Effect("reveal_random", target="player", filter="opp" if opp else "", data={"side": "theirs"})


EFFECT_PATTERNS = [
    (r"target (player|opponent) reveals a card at random from their hand", _reveal),
]
