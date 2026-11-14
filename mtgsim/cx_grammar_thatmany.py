"""Grammar rider for "<player> <puts cards away>, then draw(s) that many cards [plus/minus N]" (#337).

    Discard all the cards in your hand, then draw that many cards plus one.          (Heartwarming Redemption)
    Discard any number of cards, then draw that many cards.                           (Cavalier of Flame)
    Target player discards all the cards in their hand, then draws that many cards.   (Collective Defiance)
    Each player discards all the cards in their hand, then draws that many cards minus one.   (Dark Deal)
    Each player shuffles the cards from their hand into their library, then draws that many cards.   (Winds of Change)
    Put any number of cards from your hand on the bottom of your library, then draw that many cards plus one.
    Shuffle any number of cards from your hand into your library, then draw that many cards.   (Credit Voucher)
    Sacrifice any number of artifacts, enchantments, and/or tokens, then draw that many cards.   (Malevolent Witchkite)
    Each player discards their hand, then draws cards equal to the greatest number of cards a player discarded
    this way.                                                                         (Windfall)
    Target player draws cards equal to the number of cards in their hand, then discards that many cards.
    Draw cards equal to the number of cards in your hand, then discard a card for each card drawn this way.

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
    (r"sacrifice any number of (?P<sac>[\w ,/-]+?)", "sac_any"),
]
_SAC_TYPES = {"permanents": "permanent", "artifacts": "artifact", "creatures": "creature", "lands": "land",
              "enchantments": "enchantment", "tokens": "token", "planeswalkers": "planeswalker"}


def _sac_spec(text: str):
    """{"types": [...], "other": bool} for "other permanents" / "artifacts, enchantments, and/or tokens" /
    "permanents you control", or None."""
    t = re.sub(r" you control$", "", text.strip().lower())
    other = t.startswith("other ")
    t = t[6:] if other else t
    words = [w for w in re.split(r",? and/or |,? and |,? or |, ", t) if w]
    if not words or any(w not in _SAC_TYPES for w in words):
        return None
    return {"types": [_SAC_TYPES[w] for w in words], "other": other}


@rider(r"(?P<head>.+?), then (?P<draw>draws?) that many cards(?: (?P<op>plus|minus) (?P<n>one|two|three))?")
def put_away_then_draw(m, inner):
    head, delta = m["head"], 0
    if m["op"]:
        delta = _DELTA[m["n"].lower()] * (1 if m["op"].lower() == "plus" else -1)
    found = _action(head)
    if found is None:
        return None
    subj, mode, third, extra = found
    if third != (m["draw"].lower() == "draws"):
        return None             # "Discard ..., then draws" / "Target player discards ..., then draw"
    parts = [Part("cx_away", data={"mode": mode, **extra}),
             Part("cx_draw_that_many", data={"delta": delta, "mode": mode, **extra})]
    effects = assemble(subj, parts)
    if not effects or len(effects) != 1 or effects[0].kind != "cx_players":
        return None
    eff = effects[0]
    if eff.data.get("who") == "target" and eff.filter != "opp":
        # a chosen player: refilling a hand (plus) is for its controller's own side, "minus" for an opponent's
        eff.data["side"] = "theirs" if delta < 0 else "mine"
    return effects


@rider(r"sacrifice any number of (?P<sac>[\w ,/-]+)")
def sacrifice_any(m, inner):
    """"Sacrifice any number of artifacts, creatures, and/or lands." on its own (Reprocess, Renounce): the count is
    recorded "this way" for the next sentence's "for each permanent sacrificed this way"."""
    spec = _sac_spec(m["sac"])
    if spec is None:
        return None
    return assemble(Subject("player", who="you", text=""),
                    [Part("cx_away", data={"mode": "sac_any", "sac": spec, "alone": True})])


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


@rider(r"(?:(?P<subj>.+?) )?(?P<draw>draws?) cards equal to (?P<q>.+?), then (?P<disc>discards?) "
       r"(?P<what>that many cards|a card for each card drawn this way)")
def draw_then_discard(m, inner):
    """Laquatus's Creativity ("... draws cards equal to Q, then discards that many cards": Q, read once before the
    draw) and Ancient Excavation ("... then discard a card for each card drawn this way": the cards actually
    drawn, which a draw replacement can change)."""
    from .cx_grammar_playerq import _quantity, _swap
    if m["subj"] is None:
        subj = Subject("player", who="you", text="")
    else:
        subj = subject(m["subj"])
        if subj is None or subj.kind != "player":
            return None
    third = subj.who != "you"
    if third != (m["draw"].lower() == "draws") or third != (m["disc"].lower() == "discards"):
        return None
    if subj.who == "you":
        spec, rel = (None if re.search(r"\b(?:they|their|them)\b", m["q"], re.I) else _quantity(m["q"])), False
    else:
        q = _swap(m["q"])
        spec, rel = (_quantity(q) if q is not None else None), True
    if spec is None:
        return None
    second = Part("discard", 1) if m["what"].startswith("that many") else Part("cx_discard_drawn", 1)
    effects = assemble(subj, [Part("draw", 1), second])
    if not effects or len(effects) != 1 or effects[0].kind != "cx_players":
        return None
    effects[0].data.update(xq=spec, **({"xq_rel": True} if rel else {}))
    return effects


def _action(head: str):
    """(player Subject, mode, third person, extra Part data) for "<subject> <action>", or None."""
    for rx, mode in _ACTIONS:
        m = re.search(rf"(?:^|(?<= )){rx}$", head, re.I)
        if m is None:
            continue
        subj_text = head[:m.start()].strip()
        verb = m[0].split(" ", 1)[0].lower()
        third = verb in ("discards", "shuffles", "puts")
        extra = {}
        if mode == "sac_any":
            extra = {"sac": _sac_spec(m["sac"])}
            if extra["sac"] is None or head[:m.start()].strip():
                return None     # only "Sacrifice any number of ..." (you): no player-subject wording exists
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
        return subj, mode, third, extra
    return None


@ai_value("cx_away")
def _away_value(game, me, eff, obj):
    """Valued with the draw that follows it, except a sacrifice standing alone ("Sacrifice any number of ... ."):
    every such card rewards each permanent "sacrificed this way" in its next sentence, so it is worth what the
    conservative choice would give up (nothing when it would give up nothing)."""
    if not eff.data.get("alone"):
        return 0.0
    from .engine.kinds.cx_grammar_thatmany import sac_candidates, choose_sac_any
    return (1.0 if obj is me else -1.0) * len(choose_sac_any(game, obj, sac_candidates(game, obj, eff.data["sac"], None)))


@ai_value("cx_discard_drawn")
def _discard_drawn_value(game, me, eff, obj):
    """Sized like the draw before it (the AI scales the amount by the same count): cards out of that hand."""
    return -(0.8 if obj is me else -1.0) * eff.amount


@ai_value("cx_draw_that_many")
def _draw_value(game, me, eff, obj):
    """The swap: dead cards (policy.choose_rummage) become fresh draws, the rest of a whole hand is a coin flip
    worse than the cards kept, plus the extra (or missing) cards. Signed by whose hand it is."""
    from .engine.policy import choose_rummage
    hand = list(getattr(obj, "hand", ()))
    sign = 1.0 if obj is me else -1.0
    dead = len(choose_rummage(game, obj, len(hand))) if hand else 0
    if eff.data.get("mode") == "sac_any":       # a card for each permanent the conservative choice gives up
        from .engine.kinds.cx_grammar_thatmany import sac_candidates, choose_sac_any
        picks = choose_sac_any(game, obj, sac_candidates(game, obj, eff.data["sac"], None))
        return sign * (1.2 * len(picks) + 1.5 * eff.data.get("delta", 0))
    kept = 0 if eff.data.get("mode", "").endswith("_any") else len(hand) - dead      # "any number": only dead ones go
    extra = eff.data.get("delta", 0)
    if eff.data.get("greatest"):        # Windfall: everyone draws the biggest hand's count
        extra += max(len(pl.hand) for pl in game.players) - len(hand)
    return sign * (0.5 * dead - 0.2 * kept + 1.5 * extra)
