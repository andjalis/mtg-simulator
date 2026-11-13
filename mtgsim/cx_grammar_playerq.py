"""Grammar riders for player verbs whose amount counts the subject's own things (#337).

    Target player draws a card for each basic land type among lands they control.      (Allied Strategies)
    Each player loses 1 life for each creature they control.                            (Stronghold Discipline)
    Each player draws a card for each creature card in their graveyard.                 (Nature's Resurgence)
    Defending player loses 1 life for each card in their graveyard.                     (Guiltfeeder)
    Target opponent loses life equal to the number of creatures they control.           (Villainous Wrath)
    Each opponent loses life equal to the life that player lost this turn.               (Archfiend of Despair)

"They" / "their" is the verb's subject, not the caster: the quantity is read with "you" in their place (the
shared ", where X is ..." quantities: cards.clauses._xq and cx_grammar_quantity) and marked ``xq_rel``, so
cx_players evaluates it once per named player, all before any of them acts. Only quantities that depend on nothing
but that player are accepted (``_REL_KINDS``); a phrase that also says "you" / "your" names the caster too and is
refused, as is a "you" subject (the plain grammar reads those).
"""
from __future__ import annotations

import re

from .cx_grammar import rider

_THEY = re.compile(r"\b(?:they|their|them|that player)\b", re.I)
# "that player" in the quantity is the subject too: "each opponent loses life equal to the life that player lost"
_SWAP = [(r"\bthey control\b", "you control"), (r"\bthey own\b", "you own"),
         (r"\btheir (graveyard|hand|library)\b", r"your \1"), (r"\b(?:they|that player) lost\b", "you lost")]
# the noun phrase ends before these words: "basic land TYPE among lands", "creature CARD in your graveyard"
_STOPS = {"among", "in", "you", "that", "with", "of", "on", "from", "named", "attached", "your"}
# x_quantity kinds that read only the player they are evaluated for (engine/costs.py, cx_grammar_quantity)
_REL_KINDS = {"count", "gy", "domain", "colors_among", "colors_among_lands", "named_lands", "tapped_any", "hand",
              "defenders", "greatest", "greatest_perm"}
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
    if spec[0] == "count":
        return isinstance(spec[1], str) and not re.search(r"\b(?:among|in|of|with|that|from)\b", spec[1])
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
