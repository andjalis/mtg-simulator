"""Graveyard cards shuffled into their owner's library (#632):

    Shuffle your graveyard into your library.                                               (Feldon's Cane)
    Each player shuffles their graveyard into their library.                                (Mnemonic Nexus)
    Shuffle ~ and your graveyard into their owner's library.                                (Elixir of Immortality)
    Shuffle all creature cards from your graveyard into your library.                       (Barishi)
    Shuffle up to four target cards from your graveyard into your library.                  (Devious Cover-Up)
    Shuffle any number of target creature cards from your graveyard into your library.      (Renewing Touch)
    You shuffle up to four cards from your graveyard into your library.                     (Stream of Thought)

One kind, ``gy_to_library``: data ``who`` ("you" / "each"), ``what`` (a card description read by copies.fits, "" for
any card), ``n`` (None: every matching card; else at most n), ``self`` (the source goes too).

The graveyard is yours, so the cards picked are the controller's choice. "Up to N" / "any number of" picks are made
when the effect resolves, not as targets when it is put on the stack (the engine has no multi-card graveyard
targets); the AI picks the cards worth least in a graveyard (no flashback-like ability from there, cheapest first),
"any number" meaning all of them, which is what these cards are played for (refilling the library).

Not read: a target player's graveyard (Repopulate, Loaming Shaman), "from a single graveyard" (Serene Remembrance),
card qualities copies.fits doesn't know ("with mana value 3 or greater"), "of that type", and riders counting the
cards shuffled in ("You gain life equal to the number of cards shuffled ...").
"""
from __future__ import annotations

_N = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}
_QUAL = (r"(?P<what>(?:(?:nonland|noncreature|creature|land|artifact|enchantment|instant|sorcery|planeswalker)"
         r"(?:,? (?:and|or) |, | )?)+ )?")
_KNOWN = {"nonland", "noncreature", "creature", "land", "artifact", "enchantment", "instant", "sorcery",
          "planeswalker", "and", "or"}


def _effect(who="you", what="", n=None, self_too=False):
    from .cards.model import Effect      # deferred: mtgsim.cards imports this module (tests.test_imports)
    return Effect("gy_to_library", target="none", data={"who": who, "what": what, "n": n, "self": self_too})


def _what(m):
    what = (m["what"] or "").strip().rstrip(",")
    if what and not set(what.replace(",", " ").split()) <= _KNOWN:
        return None
    return what


def _some(m):
    what = _what(m)
    if what is None:
        from .cards.model import NO_MATCH
        return NO_MATCH
    n = None if m["count"].lower() == "any number of" else _N.get(m["count"].lower().split()[-1])
    return _effect(what=what, n=n)


def _all(m):
    what = _what(m)
    if what is None:
        from .cards.model import NO_MATCH
        return NO_MATCH
    return _effect(what=what)


EFFECT_PATTERNS = [
    (r"(?:you )?shuffle your graveyard into your library", lambda m: _effect()),
    (r"each player shuffles their graveyard into their library", lambda m: _effect("each")),
    (r"shuffle ~ and your graveyard into (?:their|its) owner's library", lambda m: _effect(self_too=True)),
    (rf"(?:you )?shuffle all {_QUAL}cards from your graveyard into your library", _all),
    (rf"(?:you )?shuffle (?P<count>up to (?:one|two|three|four|five|six|seven)|any number of) (?:target )?{_QUAL}"
     r"cards? from your graveyard into your library", _some),
]


def _keep_value(card) -> tuple:
    """How much a card is worth keeping in the graveyard: ones with abilities there (flashback, unearth, escape ...)
    first, then by mana value."""
    gy = bool(card.gy_activated or any(a.kind in ("flashback", "escape", "unearth", "embalm", "eternalize")
                                       for a in getattr(card, "alt_costs", ()) or ()))
    return gy, card.cmc


def resolve(game, p, eff, item=None):
    """The gy_to_library kind (engine/kinds/graveyard.py)."""
    from . import copies
    from .engine.state import Permanent
    d = eff.data
    players = [p, game.opponent(p)] if d["who"] == "each" else [p]
    for who in players:
        pool = [c for c in who.graveyard if not d["what"] or copies.fits(c, d["what"])]
        if d["n"] is not None:
            pool = sorted(pool, key=_keep_value)[:d["n"]]
        for card in pool:
            who.graveyard.remove(card)
            who.library.append(card)
        src = item.source if item is not None else None
        if d["self"] and who is p and isinstance(src, Permanent) and src in src.controller.battlefield:
            game.put_in_library(src, "shuffle")         # into its owner's library, shuffled
        who.library.shuffle(game.rng)
        game.log(f"shuffles {len(pool)} card(s) from the graveyard{' and ' + src.card.name if d['self'] and src else ''}"
                 f" into the library", who)


def ai_value(game, me, eff) -> float:
    """Worth something only against decking: half a point per card shuffled back into a library under ten cards
    (ours counts for us, the opponent's against us)."""
    d = eff.data
    value = 0.0
    for who in ([me, game.opponent(me)] if d["who"] == "each" else [me]):
        pool = [c for c in who.graveyard if not d["what"] or _fits(c, d["what"])]
        n = len(pool) if d["n"] is None else min(d["n"], len(pool))
        if len(who.library) < 10:
            value += (0.5 if who is me else -0.5) * n
    return value


def _fits(card, what):
    from . import copies
    return copies.fits(card, what)
