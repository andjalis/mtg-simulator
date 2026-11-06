"""Grammar verbs for player actions beyond the ``players`` family: imperative sentences ("Draw two cards, then
discard a card at random.", "Discard your hand.", "Mill three cards.", "You gain 2 life" without "you") and the
discards a player subject makes at random or of a whole hand ("Target player discards two cards at random.",
"Each player discards their hand."). See mtgsim/GRAMMAR.md.

An imperative verb's object is "you", so its Effect resolves for the controller. A player subject is applied by
``cx_players`` (target player, each player, that player, ...). X ("discard X cards at random") is read only in an
imperative sentence (Game.resolve sets the amount from the X paid) and by the random discard, whose kind reads the X
paid itself; any other X inside a player subject is rejected.
"""
from __future__ import annotations

from .cx_grammar import Part, ai_value, count, object_phrase, verb

_N = r"(a|an|one|two|three|four|five|six|seven|eight|nine|ten|x|\d+)"


def _you():
    return object_phrase("you")


def _amount(word: str, clause, own_x=False):
    """(n, data), or None. X: in an imperative sentence (Game.resolve reads it), or with ``own_x`` for a kind that
    reads the X paid itself (inside cx_players the shared amount rules don't run)."""
    if word == "x":
        return (0, {"x": True}) if own_x or clause.subject.kind == "imperative" else None
    n = count(word)
    return (n, {}) if n else None


def _obj(clause):
    return {"obj": _you()} if clause.subject.kind == "imperative" else {}


@verb(rf"(draw|discard|mill) {_N} cards?", heads=("draw", "discard", "mill"), subjects=("imperative",))
def cards(m, clause):
    got = _amount(m[2], clause)
    if got is None or clause.duration or (m[2] in ("a", "an", "one")) != clause.verb.endswith(" card"):
        return None
    return [Part(m[1], got[0], 0, got[1], **_obj(clause))]


@verb(r"(gain|lose) (\w+) life", heads=("gain", "lose"), subjects=("imperative",))
def life(m, clause):
    n = count(m[2])
    if not n or clause.duration:
        return None
    return [Part("gain_life" if m[1] == "gain" else "lose_life", n, **_obj(clause))]


@verb(rf"discards? {_N} cards? at random", heads=("discard", "discards"), subjects=("imperative", "player"))
def at_random(m, clause):
    got = _amount(m[1], clause, own_x=True)
    if got is None or clause.duration or (m[1] in ("a", "an", "one")) != clause.verb.endswith(" card at random"):
        return None
    return [Part("cx_discard_random", got[0], 0, got[1], **_obj(clause))]


@verb(r"discards? (your|their) hand", heads=("discard", "discards"), subjects=("imperative", "player"))
def hand(m, clause):
    if clause.duration or (m[1] == "your") != (clause.subject.kind == "imperative" or clause.subject.who == "you"):
        return None
    return [Part("cx_discard_hand", **_obj(clause))]


@ai_value("cx_discard_random", "cx_discard_hand")
def _discard_value(game, me, eff, obj):
    """Cards out of a player's hand, valued like the core's discard: worse for me than good against them."""
    hand = len(getattr(obj, "hand", ()))
    n = hand if eff.kind == "cx_discard_hand" else min(eff.amount, hand)
    return -(0.8 if obj is me else -1.0) * n
