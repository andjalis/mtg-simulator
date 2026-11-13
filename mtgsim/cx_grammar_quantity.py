"""Quantities for "... equal to <Q>", ", where X is <Q>" and "for each <thing>": the fallback of ``cards.clauses._xq``.

``quantity(text)`` reads a quantity the fixed ``_xq`` table doesn't know and returns a ``("cxq", ...)`` spec, or
None. ``value(game, p, spec, item, prev)`` evaluates it when the effect resolves (``Game.x_quantity``):

    your devotion to black                       (mana symbols of that colour among permanents you control)
    your devotion to white and black
    the number of attacking creatures            (a battlefield noun phrase, read like a grammar group subject)
    the number of Elves on the battlefield
    the number of creature cards in all graveyards / in your graveyard / in an opponent's graveyard
    the number of cards named ~ in your graveyard
    the number of card types among cards in your graveyard
    the number of creatures that died this turn  (turn history: died, entered, left, cast, sacrificed, discarded)
    the number of spells you've cast this turn
    the number of cards you've drawn this turn
    the life you've lost this turn / the total life lost by all players this turn
    the greatest mana value among artifacts you control
    the total power of creatures you control
    the number of opponents you have
    the number of colors of mana spent to cast ~ (converge)
    twice <Q> / half <Q>, rounded up|down

Only quantities whose referent is fixed by the words are read here. "its power", "that card's mana value" and
"the difference" depend on what came before and stay with the templates that know their referent.
"""
from __future__ import annotations

import re

_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_STATS = ("power", "toughness", "mana value")
_ZONES = {"in all graveyards": "all_gy", "in your graveyard": "your_gy", "in an opponent's graveyard": "opp_gy",
          "in your hand": "your_hand", "in exile": "exile", "you own in exile": "your_exile",
          "in your library": "your_library"}
# "the number of <things> <past event> this turn" -> the turn-history condition phrase cx_condlib already counts
_HISTORY = [
    (r"(.+?) (?:that|which) died(?: under your control)? this turn", "a {0} died{1} this turn"),
    # "put into your graveyard from the battlefield" is a death of a card you owned: read through the
    # died-under-your-control history (a permanent that dies goes to its owner's graveyard).
    (r"(.+?) put into your graveyard from the battlefield this turn", "a {0} died under your control this turn"),
    (r"(.+?) that entered(?: the battlefield)?(?: under your control)? this turn", "a {0} entered{1} this turn"),
    (r"(.+?) you've cast this turn", "you've cast a {0} this turn"),
    (r"(.+?) you've sacrificed this turn", "you've sacrificed a {0} this turn"),
]


def _singular(word: str) -> str:
    from .cx_events import _IRREGULAR
    irregular = _IRREGULAR.get(word.capitalize())
    if irregular:
        return irregular.lower() if word.islower() else irregular
    if word.lower() == "sorceries":
        return "sorcery"
    return word[:-1] if word.endswith("s") and not word.endswith("ss") else word


def _noun(text: str):
    """A grammar noun spec for a plural battlefield noun phrase, or None."""
    from .cx_grammar import _noun as noun
    if re.search(r"\b(it|its|that|this|them|their|those|target)\b", text, re.I):
        return None             # the phrase names something the effect pointed at: its referent is not fixed here
    return noun(text, plural=True)


def _cards(text: str):
    """A cx_condlib card filter for "creature cards" / "instant and sorcery cards" / "cards", or None."""
    from .cx_condlib import _filter
    if text.lower() == "cards":
        return {}
    m = re.fullmatch(r"(.+?) cards", text, re.I)
    return _filter(m[1], plural=False) if m else None


def quantity(text: str):
    """The ("cxq", ...) spec for a quantity phrase, or None."""
    t = re.sub(r"\s+", " ", text.strip().rstrip("."))
    low = t.lower()
    m = re.fullmatch(r"your devotion to (white|blue|black|red|green)(?: and (white|blue|black|red|green))?", low)
    if m:
        return ("cxq", "devotion", "".join(_COLORS[c] for c in m.groups() if c))
    if low == "the number of opponents you have":
        return ("cxq", "opponents")
    if low in ("the number of colors of mana spent to cast ~", "the number of colors of mana spent to cast this spell"):
        return ("cxq", "converge")
    if low == "the number of cards you've drawn this turn":
        return ("cxq", "drawn")
    if low == "the number of cards you've discarded this turn":
        return ("cxq", "discarded")
    if re.fullmatch(r"the (?:amount of )?life you(?:'ve)? lost this turn", low):
        return ("cxq", "life_lost")         # damage and life loss alike (Player.life_lost_amount)
    if low == "the total life lost by all players this turn":
        return ("cxq", "life_lost_all")
    m = re.fullmatch(r"(twice|half) (.+?)(?:, rounded (up|down))?", t, re.I)
    if m and (m[1].lower() == "half") == bool(m[3]):
        inner = _any(m[2])
        if inner is None:
            return None
        return ("cxq", "twice", inner) if m[1].lower() == "twice" else ("cxq", "half", inner, m[3].lower() == "up")
    m = re.fullmatch(r"the (greatest|total) (power|toughness|mana value) (?:among|of) (.+)", t, re.I)
    if m:
        noun = _noun(m[3])
        return ("cxq", m[1].lower(), m[2].lower(), noun) if noun else None
    m = re.fullmatch(r"the number of card types among cards (in all graveyards|in your graveyard)", low)
    if m:
        return ("cxq", "card_types", _ZONES[m[1]])
    m = re.fullmatch(r"the number of (.+?) (in all graveyards|in your graveyard|in an opponent's graveyard|"
                     r"in your hand|in exile|you own in exile|in your library)", t, re.I)
    if m:
        zone = _ZONES[m[2].lower()]
        named = re.fullmatch(r"cards named ~", m[1], re.I)
        if named:
            return ("cxq", "cards", zone, None)
        spec = _cards(m[1])
        return ("cxq", "cards", zone, spec) if spec is not None else None
    m = re.fullmatch(r"the number of (.+)", t, re.I)
    if m is None:
        return None
    for rx, phrase in _HISTORY:
        h = re.fullmatch(rx, m[1], re.I)
        if h:
            return _history(h, phrase, m[1])
    words = re.sub(r" on the battlefield$", "", m[1], flags=re.I)
    if words != m[1] and " control" in words:
        return None
    noun = _noun(words)
    return ("cxq", "perms", noun) if noun else None


def _history(h, phrase: str, whole: str):
    """("cxq", "hist", head) for "<things> that died this turn", read through cx_condlib's turn history."""
    from . import cx_condlib
    import json
    words = h[1].split()
    if not words:
        return None
    head = " ".join(words[:-1] + [_singular(words[-1])])
    mine = " under your control" if "under your control" in whole.lower() else ""
    code = cx_condlib._history(phrase.format(head, mine))
    if not code.startswith("lib:"):
        return None
    kind, head_text, _ = json.loads(code[4:])
    return ("cxq", "hist", head_text) if kind == "hist" else None


def _any(text: str):
    """Any quantity: the fixed table first, then this grammar."""
    from .cards.clauses import _xq
    return _xq(text)


# ---------------------------------------------------------------- evaluation

def _source(item):
    from .engine.state import Permanent
    src = getattr(item, "source", None)
    return src if isinstance(src, Permanent) else None


def _source_name(item) -> str:
    card = getattr(item, "card", None) or getattr(getattr(item, "source", None), "card", None)
    return card.name if card is not None else ""


def _devotion(p, colors: str) -> int:
    """Mana symbols among the mana costs of permanents p controls that are any of the colours (CR 700.5): a hybrid
    symbol counts once. ``mana_cost`` books a two-colour hybrid pip under its first colour; ``hybrid`` lists it."""
    n = 0
    for x in p.battlefield:
        card = x.card
        hybrid = getattr(card, "hybrid", ())
        n += sum(card.mana_cost.get(c, 0) for c in colors) - sum(1 for pip in hybrid if pip[0] in colors)
        n += sum(1 for pip in hybrid if any(c in pip for c in colors))
    return n


def _zone_cards(game, p, zone):
    opp = game.opponent(p)
    return {"all_gy": [c for pl in game.players for c in pl.graveyard], "your_gy": list(p.graveyard),
            "opp_gy": list(opp.graveyard), "your_hand": list(p.hand), "your_library": list(p.library),
            "exile": [c for pl in game.players for c in pl.exile], "your_exile": list(p.exile)}[zone]


def _stat(perm, stat: str) -> int:
    return perm.card.cmc if stat == "mana value" else getattr(perm, stat, 0)


def value(game, p, spec, item, prev) -> int:
    kind = spec[1]
    if kind == "flips":
        return getattr(item, "flips_" + spec[2], 0)
    if kind == "devotion":
        return _devotion(p, spec[2])
    if kind == "opponents":
        return sum(1 for pl in game.players if pl is not p and not pl.lost)
    if kind == "converge":
        # a spell's own payment, or the spell a permanent resolved from (recorded as it entered)
        if item is not None and getattr(item, "is_spell", False):
            return len(getattr(item, "mana_colors", ()))
        return len(getattr(_source(item), "mana_colors", ()))
    if kind == "drawn":
        drawn = getattr(p, "drawn_turn", (None, 0))
        return drawn[1] if drawn[0] == game.turn else 0
    if kind == "discarded":
        return len(p.discarded_cards)
    if kind == "life_lost":
        return p.life_lost_amount
    if kind == "life_lost_all":
        return sum(pl.life_lost_amount for pl in game.players)
    if kind == "twice":
        return 2 * game.x_quantity(p, spec[2], item, prev)
    if kind == "half":
        n = game.x_quantity(p, spec[2], item, prev)
        return (n + 1) // 2 if spec[3] else n // 2
    if kind in ("greatest", "total", "perms"):
        from .cx_grammar import group_members
        members = group_members(game, p, {"group": spec[-1]}, _source(item))
        if kind == "perms":
            return len(members)
        stats = [_stat(x, spec[2]) for x in members]
        return max(stats, default=0) if kind == "greatest" else sum(max(0, s) for s in stats)
    if kind == "card_types":
        return len({t for c in _zone_cards(game, p, spec[2]) for t in c.types})
    if kind == "cards":
        cards = _zone_cards(game, p, spec[2])
        if spec[3] is None:
            name = _source_name(item)
            return sum(1 for c in cards if c.name == name)
        from .cx_condlib import _card_ok
        return sum(1 for c in cards if _card_ok(c, spec[3]))
    if kind == "hist":
        hist = getattr(game, "_condlib_hist", None)
        return hist[1].get((spec[2], p.name), 0) if hist is not None and hist[0] == game.turn else 0
    return 0
