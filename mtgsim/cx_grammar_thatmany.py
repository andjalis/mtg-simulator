"""Grammar rider for "<player> <puts cards away>, then draw(s) that many cards [plus/minus N]" (#337).

    Discard all the cards in your hand, then draw that many cards plus one.          (Heartwarming Redemption)
    Discard any number of cards, then draw that many cards.                           (Cavalier of Flame)
    Target player discards all the cards in their hand, then draws that many cards.   (Collective Defiance)
    Each player discards all the cards in their hand, then draws that many cards minus one.   (Dark Deal)
    Each player shuffles the cards from their hand into their library, then draws that many cards.   (Winds of Change)
    Put any number of cards from your hand on the bottom of your library, then draw that many cards plus one.
    Shuffle any number of cards from your hand into your library, then draw that many cards.   (Credit Voucher)
    Each player discards their hand, then draws cards equal to the greatest number of cards a player discarded
    this way.                                                                         (Windfall)

"That many" is the number of cards each player actually put away this way (a discarded card counts even when
madness exiles it), counted per player: "each player discards ..., then draws that many" makes every player put
their cards away first, then each draws their own count. The two steps are the cx_players inner kinds
``cx_away`` and ``cx_draw_that_many`` (engine/kinds/cx_grammar_thatmany.py); the draw goes through Game.draw, so
draw replacements apply to each card. "Any number of cards" is the putting-away player's choice
(policy.choose_rummage). "Exiles all cards from their hand" is left out until the cards can be tied to the
exiling permanent's own return trigger (Induced Amnesia, #389). The sentence must be whole: a later rider
("..., or ~ deals damage ...") stays unparsed.
"""
from __future__ import annotations

import re

from .cx_grammar import Part, Subject, ai_value, assemble, rider, subject

_P = r"(?P<pron>your|their)"
_DELTA = {"one": 1, "two": 2, "three": 3}
# (regex over the action after the subject, mode); the verb is matched bare or with -s by the caller
_ACTIONS = [
    (rf"discard(?:s)? (?:all (?:the )?cards in )?{_P} hand", "discard_hand"),
    (r"discard(?:s)? any number of cards", "discard_any"),
    (rf"shuffle(?:s)? (?:all )?(?:the )?cards from {_P} hand into (?P<pron2>your|their) library", "shuffle_hand"),
    (rf"shuffle(?:s)? {_P} hand into (?P<pron2>your|their) library", "shuffle_hand"),
    (rf"shuffle(?:s)? any number of cards from {_P} hand into (?P<pron2>your|their) library", "shuffle_any"),
    (rf"put(?:s)? (?:all )?the cards (?:in|from) {_P} hand on the bottom of (?P<pron2>your|their) library"
     r"(?: in any order)?", "bottom_hand"),
    (rf"put(?:s)? any number of cards from {_P} hand on the bottom of (?P<pron2>your|their) library"
     r"(?: in any order)?", "bottom_any"),
]


@rider(r"(?P<head>.+?), then (?P<draw>draws?) that many cards(?: (?P<op>plus|minus) (?P<n>one|two|three))?")
def put_away_then_draw(m, inner):
    head, delta = m["head"], 0
    if m["op"]:
        delta = _DELTA[m["n"].lower()] * (1 if m["op"].lower() == "plus" else -1)
    found = _action(head)
    if found is None:
        return None
    subj, mode, third = found
    if third != (m["draw"].lower() == "draws"):
        return None             # "Discard ..., then draws" / "Target player discards ..., then draw"
    parts = [Part("cx_away", data={"mode": mode}), Part("cx_draw_that_many", data={"delta": delta, "mode": mode})]
    effects = assemble(subj, parts)
    if not effects or len(effects) != 1 or effects[0].kind != "cx_players":
        return None
    eff = effects[0]
    if eff.data.get("who") == "target" and eff.filter != "opp":
        # a chosen player: refilling a hand (plus) is for its controller's own side, "minus" for an opponent's
        eff.data["side"] = "theirs" if delta < 0 else "mine"
    return effects


@rider(r"(?P<head>each player discards their hand), then draws cards equal to the greatest number of cards a player "
       r"discarded this way")
def windfall(m, inner):
    """Windfall, Whispering Madness, Jace's Archivist: every hand is discarded first, then each player draws the
    largest count any one player discarded."""
    found = _action(m["head"])
    if found is None or found[0].who != "each":
        return None
    return assemble(found[0], [Part("cx_away", data={"mode": "discard_hand"}),
                               Part("cx_draw_that_many", data={"delta": 0, "mode": "discard_hand", "greatest": True})])


def _action(head: str):
    """(player Subject, mode, third person) for "<subject> <action>", or None."""
    for rx, mode in _ACTIONS:
        m = re.search(rf"(?:^|(?<= )){rx}$", head, re.I)
        if m is None:
            continue
        subj_text = head[:m.start()].strip()
        verb = m[0].split(" ", 1)[0].lower()
        third = verb in ("discards", "shuffles", "puts")
        if not subj_text:
            if third:
                return None
            subj = Subject("player", who="you", text="")
            mine = True
        else:
            subj = subject(subj_text)
            if subj is None or subj.kind != "player" or subj.who not in ("you", "target", "each", "that_player",
                                                                         "defending", "opponents"):
                return None
            if third != (subj.who != "you"):
                return None
            mine = subj.who == "you"
        prons = [g for g in (m.groupdict().get("pron"), m.groupdict().get("pron2")) if g]
        if any((pr.lower() == "your") != mine for pr in prons):
            return None         # "Target player shuffles your hand ...": not the same player's cards
        return subj, mode, third
    return None


@ai_value("cx_away")
def _away_value(game, me, eff, obj):
    return 0.0          # valued with the draw that follows it


@ai_value("cx_draw_that_many")
def _draw_value(game, me, eff, obj):
    """The swap: dead cards (policy.choose_rummage) become fresh draws, the rest of a whole hand is a coin flip
    worse than the cards kept, plus the extra (or missing) cards. Signed by whose hand it is."""
    from .engine.policy import choose_rummage
    hand = list(getattr(obj, "hand", ()))
    sign = 1.0 if obj is me else -1.0
    dead = len(choose_rummage(game, obj, len(hand))) if hand else 0
    kept = 0 if eff.data.get("mode", "").endswith("_any") else len(hand) - dead      # "any number": only dead ones go
    extra = eff.data.get("delta", 0)
    if eff.data.get("greatest"):        # Windfall: everyone draws the biggest hand's count
        extra += max(len(pl.hand) for pl in game.players) - len(hand)
    return sign * (0.5 * dead - 0.2 * kept + 1.5 * extra)
