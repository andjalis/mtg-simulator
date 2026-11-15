"""Characteristic-defining P/T from a quantity (#401): "~'s power ... equal to Q" as a general grammar.

    ~'s power and toughness are each equal to the number of cards in all graveyards.    (Lord of Extinction)
    ~'s power is equal to your devotion to red.                                         (Anax, Hardened in the Forge)
    ~'s power is equal to the number of creature cards in all graveyards and its toughness is equal to
        that number plus 1.                                                             (Lhurgoyf)
    ~'s power and toughness are each equal to twice the number of oil counters on it.   (Darksteel Hydra)

Parsing: ``parse_line`` (a face_lines hook after cx_grammar.parse_static, so the fixed tables in cx_cda /
counting / face_lines keep their lines) reads the whole line: both stats at once ("are each equal to Q"), one
stat ("~'s power is equal to Q"), or two clauses where the second may say "that number plus N". The quantity is
one ``cards.clauses._xq`` / ``cx_grammar_quantity.quantity`` already return ("on it" / "its" name ~); anything
else keeps the line ignored, as does a quantity that reads power or toughness (it would read the value it sets),
a referent that isn't fixed, a choice, or a condition / rider the line doesn't have. The record is
``advanced_rules["cda_pt"] = ((pspec, tspec), ...)`` with None for a stat the line doesn't define.

Engine: ``apply_cda`` is called from ``continuous.pt`` in layer 7a, before set-base effects, anthems, pumps and
counters, so every read of the permanent's power / toughness sees the defining value (CR 604.3, 613.2). A
re-entrancy guard keeps a quantity that reads a P/T from recursing.
"""
from __future__ import annotations

import re

_LABEL = re.compile(r"^[A-Z][\w'&/ ,-]* — ")
_BOTH = re.compile(r"~'s power and toughness are each equal to (.+)\.")
_ONE = re.compile(r"~'s (power|toughness) is equal to (.+)\.")
_TWO = re.compile(r"~'s (power|toughness) is equal to (.+?) and its (toughness|power) is equal to (.+)\.")

# x_quantity kinds whose referent is the resolving spell / cost / reveal, not the permanent: no referent in a static.
_CONTEXT = ("spell", "stat", "sac", "sac_plus", "tap", "revealed", "exiled_gy", "subj_counters", "this_way")


def _norm(text: str) -> str:
    """"on it" / "its" in a ~ line name ~ itself."""
    t = re.sub(r"\bon it\b", "on ~", text.strip(), flags=re.I)
    return re.sub(r"\bits\b", "~'s", t, flags=re.I)


def _quantity_spec(text: str, prev: str | None = None):
    """The xq spec for a CDA quantity, or None when it must stay ignored."""
    t = _norm(text)
    if prev is not None and re.search(r"\bthat number\b", t, re.I):
        t = re.sub(r"\bthat number\b", prev, t, flags=re.I)     # "that number plus 1" = the first clause's quantity
    from .cards.clauses import _xq
    from .cx_grammar_quantity import quantity
    spec = _xq(t) or quantity(t)
    if spec is None or spec[0] in _CONTEXT or re.search(r"power|toughness", t + repr(spec), re.I) \
            or re.search(r"\b(?:it|that|those|them)\b", t, re.I) or re.search(r"chosen|choice", t, re.I):
        return None
    return spec


def parse_line(line: str, st) -> bool:
    """The face_lines hook for a leftover "~'s ... equal to Q" characteristic-defining line."""
    s = _LABEL.sub("", line.strip())
    extra = st.extra
    if extra.get("pt_cda") or extra.get("pt_per") or extra.get("advanced_rules", {}).get("cda_pt"):
        return False                # another CDA / per-line parser already read this card's line
    m = _TWO.fullmatch(s)
    if m:
        first, q1, second, q2 = m.groups()
        spec1 = _quantity_spec(q1)
        spec2 = _quantity_spec(q2, prev=_norm(q1)) if spec1 is not None else None
        if spec1 is None or spec2 is None:
            return False
        pair = {first: spec1, second: spec2}
        pspec, tspec = pair.get("power"), pair.get("toughness")
    else:
        m = _BOTH.fullmatch(s)
        if m:
            spec = _quantity_spec(m[1])
            if spec is None:
                return False
            pspec = tspec = spec
        else:
            m = _ONE.fullmatch(s)
            if m is None:
                return False
            spec = _quantity_spec(m[2])
            if spec is None:
                return False
            pspec, tspec = (spec, None) if m[1] == "power" else (None, spec)
    rules = extra.setdefault("advanced_rules", {})
    rules["cda_pt"] = tuple(rules.get("cda_pt", ())) + ((pspec, tspec),)
    return True


# ---------------------------------------------------------------- engine

_BUSY: set = set()      # permanents whose CDA is being evaluated: a quantity reading a P/T must not recurse


def apply_cda(perm, p: int, t: int):
    """(power, toughness) with the card's cda_pt rows applied — layer 7a, before every other modifier."""
    card = getattr(perm, "_card", None)
    rules = card.advanced_rules if card is not None and card.advanced_rules else None
    rows = rules.get("cda_pt") if rules else None
    if not rows or not perm.is_creature or id(perm) in _BUSY:
        return p, t
    game = getattr(perm.controller, "_game", None)
    if game is None:
        return p, t
    from .engine.state import StackItem
    item = StackItem(perm.controller, [], [], source=perm)
    _BUSY.add(id(perm))
    try:
        for pspec, tspec in rows:
            if pspec is not None:
                p = game.x_quantity(perm.controller, pspec, item, None)
            if tspec is not None:
                t = game.x_quantity(perm.controller, tspec, item, None)
    finally:
        _BUSY.discard(id(perm))
    return p, t
