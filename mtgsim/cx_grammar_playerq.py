"""Grammar riders for player verbs whose amount counts the subject's own things (#337).

    Target player draws a card for each basic land type among lands they control.      (Allied Strategies)
    Each player loses 1 life for each creature they control.                            (Stronghold Discipline)
    Each player draws a card for each creature card in their graveyard.                 (Nature's Resurgence)
    Defending player loses 1 life for each card in their graveyard.                     (Guiltfeeder)
    Target opponent loses life equal to the number of creatures they control.           (Villainous Wrath)
    Each opponent loses life equal to the life that player lost this turn.               (Archfiend of Despair)
    ~ deals damage to each player equal to the number of lands they control.            (Acidic Soil)

"They" / "their" is the verb's subject, not the caster: the quantity is read with "you" in their place (the
shared ", where X is ..." quantities: cards.clauses._xq and cx_grammar_quantity) and marked ``xq_rel``, so
cx_players evaluates it once per named player, all before any of them acts. Only quantities that depend on nothing
but that player are accepted (``_REL_KINDS``); a phrase that also says "you" / "your" names the caster too and is
refused, as is a "you" subject (the plain grammar reads those).
"""
from __future__ import annotations

import re

from .cx_grammar import Part, rider, verb

_THEY = re.compile(r"\b(?:they|their|them|that player)\b", re.I)
# "that player" in the quantity is the subject too: "each opponent loses life equal to the life that player lost"
_SWAP = [(r"\b(?:they|that player) controls?\b", "you control"), (r"\b(?:they|that player) owns?\b", "you own"),
         (r"\b(?:their|that player's) (graveyard|hand|library)\b", r"your \1"),
         (r"\b(?:they|that player) lost\b", "you lost")]
# the noun phrase ends before these words: "basic land TYPE among lands", "creature CARD in your graveyard"
_STOPS = {"among", "in", "you", "that", "with", "of", "on", "from", "named", "attached", "your"}
# x_quantity kinds that read only the player they are evaluated for (engine/costs.py, cx_grammar_quantity)
_REL_KINDS = {"count", "gy", "domain", "colors_among", "colors_among_lands", "named_lands", "tapped_any", "hand",
              "defenders", "greatest", "greatest_perm", "selector"}
_REL_CXQ = {"perms", "devotion", "total", "greatest", "cards", "card_types", "life_lost"}
_OWN_ZONES = {"your_gy", "your_hand", "your_library", "your_exile"}
_BODY = {("loses", "life"): "loses 1 life", ("gains", "life"): "gains 1 life", ("draws", "cards"): "draws a card",
         ("discards", "cards"): "discards a card", ("mills", "cards"): "mills a card"}


def _swap(text: str):
    """The phrase seen from its subject ("they control" -> "you control"), or None."""
    if not _THEY.search(text) or re.search(r"\b(?:you|your|yours)\b", text, re.I):
        return None
    for rx, new in _SWAP:
        text = re.sub(rx, new, text, flags=re.I)
    return None if _THEY.search(text) else text


def _plural(word: str) -> str:
    low = word.lower()
    if low.endswith("y") and low[-2:-1] not in "aeiou":
        return word[:-1] + "ies"
    return word + ("es" if low.endswith(("s", "x", "ch", "sh")) else "s")


def _spec_ok(spec) -> bool:
    if not isinstance(spec, tuple) or not spec:
        return False
    if spec[0] == "count":      # counted by copies.fits, which reads only these words (#428): anything else is 0
        from .copies import _TYPES
        known = {"permanent", "token", "nontoken", "nonland", "noncreature", "nonartifact", "creature", "basic",
                 "other"} | set(_TYPES)
        return isinstance(spec[1], str) and all(w.lower() in known or w[:1].isupper() or w.lower().startswith("non-")
                                                for w in spec[1].split())
    if spec[0] == "cxq" and spec[1] in ("twice", "half"):
        return _spec_ok(spec[2])
    if spec[0] == "cxq":
        return spec[1] in _REL_CXQ and (spec[1] not in ("cards", "card_types") or spec[2] in _OWN_ZONES)
    return spec[0] in _REL_KINDS


def _quantity(text: str):
    """The spec for a "the number of ..." / quantity phrase already seen from the subject, or None."""
    from .cx_grammar_quantity import _any
    spec = _any(text)
    return spec if _spec_ok(spec) else None


def _for_each(desc: str):
    """"basic land type among lands you control" -> the spec of "the number of basic land types among ...", or None."""
    words = desc.split()
    head = next((i - 1 for i, w in enumerate(words) if i and w.lower() in _STOPS), len(words) - 1)
    if head < 0:
        return None
    words[head] = _plural(words[head])
    return _quantity("the number of " + " ".join(words))


def _relative(effects, spec):
    """The one cx_players effect of a non-"you" subject, with the subject-relative quantity, or None."""
    if not effects or len(effects) != 1 or effects[0].kind != "cx_players" or spec is None:
        return None
    eff = effects[0]
    if eff.data.get("who") == "you" or eff.data.get("xq") or eff.data.get("x") or len(eff.data["effects"]) != 1:
        return None
    eff.data.update(xq=spec, xq_rel=True)
    return effects


@rider(r"(?P<body>.+?) for each (?P<desc>.+)")
def for_each_theirs(m, inner):
    desc = _swap(m["desc"])
    if desc is None or re.search(r"\bfor each\b", desc, re.I):
        return None
    return _relative(inner(m["body"]), _for_each(desc))


@rider(r"(?P<subj>.+?) (?P<verb>loses|gains|draws|discards|mills) (?P<obj>life|cards) equal to (?P<q>.+)")
def equal_to_theirs(m, inner):
    body = _BODY.get((m["verb"].lower(), m["obj"].lower()))
    q = _swap(m["q"])
    if body is None or q is None:
        return None
    return _relative(inner(f"{m['subj']} {body}"), _quantity(q))


# ---------------------------------------------------------------- damage

@verb(r"deals? damage to (?P<obj>.+?) equal to (?P<q>.+)", heads=("deal", "deals"), subjects=("permanent", "host"))
def damage_equal_to_theirs(m, clause):
    """"~ deals damage to each player equal to the number of lands they control" (Acidic Soil), "... to that player
    equal to the number of Swamps they control" (Karma): each named player is dealt their own count, every count read
    before any damage. Only untargeted players: a chosen player stays with the damage family's own targeting."""
    from .cx_grammar_damage import _object, _source
    source = _source(clause)
    if clause.duration or source is None:
        return None
    written = re.fullmatch(r"deals? damage to (?P<obj>.+?) equal to (?P<q>.+)", clause.text, re.I)   # subtypes' case
    obj = _object(m["obj"], source)
    q = _swap(written["q"]) if written else None
    if obj is None or obj.kind != "player" or obj.who in ("target", "you") or q is None:
        return None
    spec = _quantity(q)
    if spec is None:
        return None
    from .cards.model import Effect
    from .cx_grammar import Subject
    # inside cx_players (one player at a time, target = that player) so the AI values it per named player
    inner = Effect("cx_damage", 0, target="that_controller", data={"source": source, "side": "theirs", "xq_each": spec})
    return [Part("cx_players", obj=Subject("player", who=obj.who), data={"effects": [inner]})]
