"""#625 FREE-CAST: "You may cast a <kind> spell [with mana value N or less] from your hand without paying its mana cost."

    You may cast a spell with mana value 4 or less from your hand without paying its mana cost.   (Baral's Expertise)
    You may cast a spell with mana value X or less from your hand without paying its mana cost.   (Electrodominance)
    {5}, {T}: You may cast a noncreature spell from your hand without paying its mana cost.       (Yue, the Moon Spirit)
    ... you may cast a sorcery spell from your hand with mana value less than or equal to that damage without paying
    its mana cost.                                                                                 (Aisha of Sparks and Smoke)
    ... you may cast a spell with mana value X or less from your hand without paying its mana cost, where X is the
    number of attacking creatures.                                                                (Epistolary Librarian)

One ``hand_free_cast`` effect: when it resolves, its controller may cast one matching card from their hand right
away (timing restrictions don't apply while an effect resolves, CR 608.2g / 601.2), with an alternative cost of
nothing (CR 118.9: additional costs and cost increases still apply, X is 0). The mana-value cap is the effect's
amount: a fixed number, the X paid for the spell (``data["x"]``), a ", where X is <quantity>" count (``xq``) or
the triggering damage ("that damage", ``that_much``). Spell kinds are read with ``card_matches``; a word it
doesn't know (or a relation such as "that shares a card type with it" or "with equal or lesser mana value") keeps
the sentence unmatched.

The choice is the caster's: the AI casts the most valuable matching card it can cast legally, and none when
nothing fits.
"""
from __future__ import annotations

import re

# words a spell description may use (card_matches vocabulary); a capitalised word is a subtype ("a Hero spell")
_WORDS = {"instant", "sorcery", "creature", "artifact", "enchantment", "planeswalker", "battle", "permanent",
          "noncreature", "nonartifact", "nonenchantment", "legendary", "historic", "colorless", "multicolored",
          "white", "blue", "black", "red", "green", "or"}

_RX = re.compile(
    r"you may cast (?P<desc>an?(?: [a-z][\w ,-]*?)?) spell"
    r"(?: with mana value (?P<cap1>\d+|x) or less)?"
    r" from your hand"
    r"(?: with mana value (?:(?P<cap2>\d+|x) or less|(?P<dmg>less than or equal to that damage)))?"
    r" without paying its mana cost"
    r"(?:, where x is (?P<xq>.+?))?\.?", re.I)


def desc_of(text: str) -> str | None:
    """The card_matches description for "an instant or sorcery" / "a noncreature or Robot", or None."""
    words = text.replace(",", " ").split()[1:]
    if not words:
        return "a card"
    if words[0] == "or" or words[-1] == "or":
        return None
    for w in words:
        if w.lower() not in _WORDS and not re.fullmatch(r"[A-Z][a-z]+", w):
            return None
    alts = [a.strip() for a in re.split(r",? or ", text.split(" ", 1)[1])]
    return " or ".join("a " + a + " card" for a in alts)


def _build(m):
    from .cards import Effect, NO_MATCH
    desc = desc_of(m["desc"])
    if desc is None:
        return NO_MATCH
    cap = (m["cap1"] or m["cap2"] or "").lower()
    if m["cap1"] and (m["cap2"] or m["dmg"]):
        return NO_MATCH
    data = {"desc": desc}
    if m["xq"]:
        if cap != "x":
            return NO_MATCH
        from .cards.clauses import _xq
        q = _xq(m["xq"])
        if q is None:
            return NO_MATCH
        return Effect("hand_free_cast", 1, data=dict(data, capped=True, xq=q))
    if m["dmg"]:
        return Effect("hand_free_cast", 0, data=dict(data, capped=True, that_much=True))
    if cap == "x":
        return Effect("hand_free_cast", 0, data=dict(data, capped=True, x=True))
    if cap:
        return Effect("hand_free_cast", int(cap), data=dict(data, capped=True))
    return Effect("hand_free_cast", 0, data=data)


EFFECT_PATTERNS = [(_RX.pattern, _build)]


def resolve(game, p, eff):
    """Cast the best matching hand card for nothing (or none, if none can be cast)."""
    from .ai import card_value
    from .cards import AltCost
    from .engine.state import card_matches
    cap = eff.amount if eff.data.get("capped") else None
    cands = [c for c in p.hand if not c.is_land and card_matches(c, eff.data["desc"])
             and (cap is None or c.cmc <= cap)]
    for card in sorted(cands, key=card_value, reverse=True):
        free = game._variant(card, "freecast", AltCost("freecast", {"generic": 0}))
        if not game.can_cast_now(p, free, during_resolution=True):
            continue
        if game.cast(p, free):
            game.log(f"casts {card.name} from hand without paying its mana cost", p)
            return


def value(me, eff, card=None) -> float:
    """What the AI expects from the free cast: the best matching card in hand (other than the spell itself) under a
    fixed cap; half of it when the cap is only known on resolution (X, a count, that damage)."""
    from .ai import card_value
    from .engine.state import card_matches
    fixed = not eff.data.get("capped") or not any(eff.data.get(k) for k in ("x", "xq", "that_much"))
    cap = eff.amount if eff.data.get("capped") and fixed else None
    cands = [c for c in me.hand if c is not card and not c.is_land and card_matches(c, eff.data["desc"])
             and (cap is None or c.cmc <= cap)]
    best = max((card_value(c) for c in cands), default=0.0)
    return best if fixed else 0.5 * best
