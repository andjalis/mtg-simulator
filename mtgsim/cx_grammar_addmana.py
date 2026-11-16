"""Quantity-based "Add mana" sentences outside the simple tap templates (#332).

    Add {R} for each Goblin on the battlefield.                         (Brightstone Ritual)
    add {B} for each charge counter on ~.                               (Altar of Shadows, Black Market)
    {2}, {T}: Add {B} for each black creature card in your graveyard.   (Crypt of Agadeem)
    Add one mana of any color for each charge counter removed this way. (Coalition Relic)
    Add {B} or {G} for each permanent destroyed this way.               (Culling Ritual)

The amount is one mana per counted thing, read through the shared quantity specs (cards.clauses._xq /
cx_grammar_quantity.quantity) as the effect's ``xq``, so the engine scales it at resolution. "Removed /
destroyed this way" binds to the resolved event result of the preceding effect of the same resolution
(a ("this_way", verb, noun) spec the engine reads from the resolving item), never to a global count.
Anything whose quantity has no fixed referent stays unmatched (NO_MATCH) so it remains visible.

Two-sentence wordings are rewritten into those forms first (SUBS):

    Choose a color. Add one mana of that color for each charge counter on ~.        (Astral Cornucopia)
    Choose a color. Add an amount of mana of that color equal to your devotion to that color.   (Nyx Lotus)
    Reveal any number of artifact cards in your hand. Add {C}{C} for each card revealed this way.  (Metalworker)

Revealing costs nothing, so every matching card is revealed: the count is the matching cards in hand. "Your
devotion to that color" counts the colour chosen, so the colour is chosen for the most devotion (add_mana's
data["devotion_choice"]).
"""
from __future__ import annotations

import re

_WUBRG = ["W", "U", "B", "R", "G"]
_SYMS = (r"(?:\{[WUBRGC]\}(?: or \{[WUBRGC]\})*|"                 # "{B}", "{B} or {G}"
         + "|".join(rf"\{{{c}\}}(?:\{{{c}\}})+" for c in "WUBRGC") + ")")   # "{C}{C}": that much per counted thing
# "for each <thing> removed/destroyed this way": only bare nouns the producers actually record.
_THIS_WAY_Q = r"(?:[\w+/-]+ counters?|(?:nonland )?permanents?|creatures?|artifacts?|enchantments?|lands?)"
_VERB = r"(?P<verb>removed|destroyed)"


def _effect(*args, **kwargs):
    from .cards.model import Effect
    return Effect(*args, **kwargs)


def _colors(syms: str) -> dict:
    """data colours for "{B}" (one fixed colour) vs "{B} or {G}" (one choice, made once)."""
    found = re.findall(r"[WUBRGC]", syms)
    if len(found) == 1 or " or " not in syms:
        return {"colors": found}           # "{C}{C} for each card": two of it per counted thing
    return {"colors": [], "choice": found}


def _this_way_noun(q: str) -> str:
    """The noun a producer records: the counter kind ("charge counter" -> "charge"), or the singular thing."""
    m = re.fullmatch(r"([\w+/-]+) counters?", q, re.I)
    if m:
        return m[1].lower()
    w = q.lower()
    return w[:-1] if w.endswith("s") and not w.endswith("ss") else w


def _count_spec(q: str):
    """The shared quantity spec for "for each <q>", or None when the phrase has no fixed referent."""
    from .cx_grammar_quantity import quantity
    q = re.sub(r"\s+", " ", q.strip())
    q = re.sub(r"\bon (?:this|that) \w+\b", "on ~", q, flags=re.I)      # "on this artifact" -> "on ~"
    m = re.fullmatch(r"([\w+/-]+) counters? on ~", q, re.I)
    if m:                                   # "for each charge counter on ~": the source's own counters
        return ("counters", m[1].lower())
    plural = re.sub(r"(?i)\bcards?\b", "cards", q)
    for cand in ("the number of " + q, "the number of " + plural):
        spec = quantity(cand)
        if spec is not None:
            return spec
    return None


def _this_way(m):
    data = _colors(m["syms"]) if m["syms"] else {"colors": [], "choice": list(_WUBRG)}
    data["xq"] = ("this_way", m["verb"].lower(), _this_way_noun(m["q"]))
    return _effect("add_mana", 1, data=data)


def _counted(m):
    spec = _count_spec(m["q"])
    if spec is None:
        from .cards.model import NO_MATCH
        return NO_MATCH
    data = _colors(m["syms"]) if m["syms"] else {"colors": [], "choice": list(_WUBRG)}
    data["xq"] = spec
    return _effect("add_mana", 1, data=data)


SUBS = [
    (re.compile(r"Choose a color\. Add one mana of that color for each ", re.I), "Add one mana of any one color for each "),
    (re.compile(r"Choose a color\. Add an amount of mana of that color equal to your devotion to that color", re.I),
     "Add an amount of mana of any one color equal to your devotion to that color"),
    (re.compile(r"Reveal any number of ([\w-]+(?: [\w-]+)?) cards (?:in|from) your hand\. Add ((?:\{[WUBRGC]\})+) for "
                r"each card revealed this way", re.I), r"Add \2 for each \1 card in your hand"),
]


EFFECT_PATTERNS = [
    (r"add an amount of mana of any one color equal to your devotion to that color",
     lambda m: _effect("add_mana", 1, data={"colors": [], "choice": list(_WUBRG), "devotion_choice": True})),
    (rf"add (?P<syms>{_SYMS}) for each (?P<q>{_THIS_WAY_Q}) {_VERB} this way", _this_way),
    (rf"add one mana of any (?:one )?color for each (?P<q>{_THIS_WAY_Q}) {_VERB} this way",
     lambda m: _this_way(dict(m.groupdict(), syms=""))),
    (rf"add (?P<syms>{_SYMS}) for each (?P<q>.+)", _counted),
    (r"add one mana of any (?:one )?color for each (?P<q>.+)", lambda m: _counted(dict(m.groupdict(), syms=""))),
]
