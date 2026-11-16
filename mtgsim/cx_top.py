"""Playing cards from the top of your library.

    You may play lands from the top of your library.                       (Courser of Kruphix)
    You may cast creature spells from the top of your library.              (Ranger Class's third level)
    You may play lands and cast spells from the top of your library.        (Future Sight)
    You may cast Angel spells and Human spells from the top of your library. (Sigarda, Font of Blessings)
    You may play cards from the top of your library.

``parse_line`` adds ``(lands: bool or descriptions, spell descriptions or None, condition, once, life)`` to
``advanced_rules["cx_top"]`` (one entry per line).
"Play with the top card of your library revealed." is information only here. Engine: ``options``
offers the library's top card as a ``cx_top`` spell_options variant while a permanent with the rule allows it,
and ``land_ok`` lets ``Game.play_land`` and the AI play the top card when it is a land. "As long as <condition>, ..."
(a condition-library code, read with the permanent as source) and "Once each turn, you may cast ..." (``note_cast``
marks the permanent when a cast used it) gate a permission (#625). Extra costs ("by
sacrificing a nonland permanent") and once-each-turn land plays stay unparsed.
"""
from __future__ import annotations

import re

_TYPES = {"artifact", "creature", "enchantment", "instant", "sorcery", "planeswalker", "battle", "kindred",
          "historic", "colorless", "snow", "legendary", "multicolored", "noncreature", "nonartifact", "permanent",
          "white", "blue", "black", "red", "green"}


def _words(text: str):
    """'instant and sorcery' / 'Angel spells and Human' / 'artifact spells and colorless' -> word groups."""
    out = []
    for part in re.split(r",? and |,? or |, ", text.replace(" spells", "")):
        words = part.split()
        if not words or not all(w in _TYPES or re.fullmatch(r"[A-Z][a-z'-]+", w) for w in words):
            return None
        out.append(" ".join(words))
    return out


_MV = re.compile(r"(.*?)\s*spells with (mana value|power) (\d+) or (greater|less)")


def _spell_words(text, once=False):
    """The spell groups of "cast <text>": "creature spells", "spells with mana value 4 or greater", "a creature spell
    with power 2 or less" (only once each turn); None when unread."""
    if once:
        if not re.match(r"an? ", text):
            return None
        text = re.sub(r"\bspell\b", "spells", text[text.index(" ") + 1:])
    elif re.match(r"an? ", text):
        return None
    m = _MV.fullmatch(text)
    if m:                    # one stat bound for the whole group: card_matches reads it as a suffix
        words = _words(m[1]) if m[1] else [""]
        if words is None or len(words) != 1:
            return None
        return [(words[0] + " card" if words[0] else "card") + f" with {m[2]} {m[3]} or {m[4]}"]
    if text == "spells":
        return []
    mm = re.fullmatch(r"(.+?) spells", text)
    return _words(mm[1]) if mm else None


def parse_line(line: str, st) -> bool:
    if line == "Play with the top card of your library revealed.":
        return True     # information only: the AI players don't model hidden library cards
    gate = re.fullmatch(r"(?:[A-Z][\w' ]* — )?(?:As long as (.+?), |(Once each turn), )(.+)", line)
    cond, once = "", False
    if gate:            # "As long as <condition>, ..." (#625), "Once each turn, ..." (#625)
        if gate[1]:
            from .cx_condlib import parse
            cond = parse(gate[1])
            if not cond:
                return False
        once = bool(gate[2])
        line = gate[3][0].upper() + gate[3][1:]
    m = re.fullmatch(r"(?:You may look at the top card of your library any time,? and )?[Yy]ou may (.+?) from the top "
                     r"of your library\.( If you cast a spell this way, pay life equal to its mana value rather than pay "
                     r"its mana cost\.)?", line)
    if not m:
        return False
    what = m[1]
    if what == "play cards":
        lands, spells = True, []
    else:
        mm = re.fullmatch(r"(?:play (?:(\w+) )?lands)?(?: and )?(?:cast (.+))?", what)
        if not mm or not what:
            return False
        lands = what.startswith("play ")
        if lands and mm[1]:
            if mm[1] not in _TYPES:
                return False
            lands = [mm[1]]
        spells = None
        if mm[2]:
            spells = _spell_words(mm[2], once)
            if spells is None:
                return False
        elif "cast" in what:
            return False
    if m[2] and spells is None:
        return False
    if once and (lands or m[2]):
        return False        # once-each-turn land plays and life-paid casts aren't tracked
    rules = st.extra.setdefault("advanced_rules", {})
    rules["cx_top"] = tuple(rules.get("cx_top", ())) + ((lands, spells, cond, once, bool(m[2])),)
    return True


# ---------------------------------------------------------------- engine side

def _active(p, x, rule, game=None) -> bool:
    """x's permission works now: its condition holds and a once-each-turn one is unused this turn."""
    lands, spells, cond, once, life = rule
    game = game or getattr(p, "_game", None)
    if cond:
        from .cx_condlib import check
        if game is None or not check(game, p, cond, source=x):
            return False
    return not once or game is not None and getattr(x, "cx_top_turn", None) != game.turn


def _sources(p, life=False, game=None):
    """(permanent, rule) for every top-of-library permission p has now."""
    return [(x, rule) for x in p.battlefield if not x.abilities_suppressed
            for rule in x.card.advanced_rules.get("cx_top", ())
            if (not life or rule[4]) and _active(p, x, rule, game)]


def _rules(p, life=False, game=None):
    return [rule[:2] for _, rule in _sources(p, life, game)]


def _fits(card, spells) -> bool:
    if not spells:
        return True
    from .engine.state import card_matches
    return any(card_matches(card, "a " + (w if w == "card" or " card " in f" {w} " else w + " card")) for w in spells)


def note_cast(game, p, card):
    """A spell cast from the top: a once-each-turn permission is used up, unless an unlimited one allowed it."""
    fitting = [(x, rule) for x, rule in _sources(p, game=game) if rule[1] is not None and _fits(card, rule[1])]
    if fitting and all(rule[3] for _, rule in fitting):
        fitting[0][0].cx_top_turn = game.turn


def top(p):
    return p.library[-1] if len(p.library) else None


def spell_ok(p, card, life=False, game=None) -> bool:
    """card (the top of p's library) may be cast; life: by a permission that has it cost life (Bolas's Citadel)."""
    if card is None or card.is_land or top(p) is not card:
        return False
    return any(spells is not None and _fits(card, spells) for _, spells in _rules(p, life, game))


def land_ok(p, card, game=None) -> bool:
    return card is not None and card.is_land and top(p) is card and \
        any(lands is True or lands and _fits(card, lands) for lands, _ in _rules(p, game=game))


def options(game, p) -> list:
    """The top card as a spell option; with a Citadel, also paid with life equal to its mana value (rule 118.9: an
    alternative cost; additional costs and X still apply, and X is 0 when no mana pays it)."""
    from .cards import AltCost
    card = top(p)
    out = [game._variant(card, "cx_top")] if spell_ok(p, card, game=game) else []
    if spell_ok(p, card, life=True, game=game):
        out.append(game._variant(card, "cx_top_life", AltCost("cx_top_life", {}, zone="library", life=card.cmc)))
    return out
